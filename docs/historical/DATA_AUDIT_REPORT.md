# Data Pipeline Audit Report

**Auditor:** Marcus Webb, Data Quality Engineer
**Date:** 2026-03-28
**Dataset:** `data/processed/turbidity_ssc_paired.parquet`
**Stats:** 36,103 samples, 396 sites, 44 columns

---

## Stratified Sample

| Category | Site | Samples |
|----------|------|---------|
| High-sample | USGS-385553107243301 | 834 |
| High-sample | USGS-12189500 | 618 |
| Low-sample | USGS-07257500 | 8 |
| Low-sample | USGS-11447903 | 7 |
| ISCO auto_point | USGS-12189500 | 520 auto |
| ISCO auto_point | USGS-09326500 | 236 auto |
| Discrete turbidity | USGS-01658000 | 320 discrete |
| Discrete turbidity | USGS-04165500 | 214 discrete |
| Batch_v2 recovery | USGS-01311875 | mixed |
| Batch_v2 recovery | USGS-12186000 | batch_v2 only |
| Alaska | USGS-15024800 | 29 |
| Sensor calibration | USGS-385553107243301 | 823 calibrated |

---

## Check 1: Raw SSC to Paired Output - PASS

Traced 12 individual samples across 4 sites. Every one matched exactly:

- **SSC values:** Raw `ResultMeasureValue` matches `lab_value` exactly (0 mismatches out of 12)
- **UTC conversion:** Local times with timezone offsets convert correctly to UTC `sample_time` (0s difference on all checked)
- **Nondetect flags:** `is_nondetect` correctly set based on `ResultDetectionConditionText`
- **Collection method:** Correctly mapped from USGS method codes (e.g., method 900 + "Sampler, point, automatic" -> auto_point; method 10 + "US DH-95" -> depth_integrated; method 70 + "Grab sample" -> grab)

**Sites verified:** USGS-385553107243301, USGS-12189500, USGS-07257500, USGS-01658000

---

## Check 2: Turbidity Interpolation - PASS

Verified linear interpolation between flanking continuous readings for 6 samples across 2 sites.

- **USGS-385553107243301:** 3 samples verified - interpolated values match to <0.01 FNU
- **USGS-12189500:** 3 samples verified - interpolated values match exactly

Example trace: Sample at 2023-10-24 16:05 UTC, flanking readings at 16:00 (11.2 FNU) and 16:15 (9.7 FNU). Expected interpolation: 11.2 + (5/15) * (9.7 - 11.2) = 10.70. Paired value: 10.70. Correct.

**`match_gap_seconds` definition confirmed:** When both flanking readings exist, gap = MAX(gap_before, gap_after), representing the interpolation bracket width. This is documented in `src/murkml/data/align.py` line 80. When a sample falls exactly on a reading, gap_before=0 but gap_after=900s (15-min interval), so gap=900s. Not a bug -- it represents interpolation uncertainty.

---

## Check 3: Window Features - PASS

Verified +/-1hr window statistics for all 6 samples above.

- `turbidity_mean_1hr`: Matches manual computation (tolerance <0.5 FNU)
- `turbidity_min_1hr`: Exact match
- `turbidity_max_1hr`: Exact match
- Window sizes reasonable (5-18 readings depending on reporting interval)

---

## Check 4: Weather Features - PASS WITH CAVEAT

Verified precipitation and temperature features for USGS-385553107243301 across multiple dates.

**Confirmed definitions:**
- `precip_24h` = same day (day 0) precipitation in mm
- `precip_48h` = today + yesterday (day 0 + day -1) sum
- `precip_7d` = 7 prior days sum (day -7 to day -1, **EXCLUDES today**)
- `precip_30d` = 30 prior days sum (day -30 to day -1, **EXCLUDES today**)
- `temp_at_sample` = daily mean temperature (tmean_c) on sample date
- `days_since_rain` = days since last day with precip > 0

### CAVEAT C4-1: Inconsistent window definitions (LOW severity)

`precip_24h` and `precip_48h` INCLUDE the sample day, but `precip_7d` and `precip_30d` EXCLUDE the sample day. This means `precip_48h` is NOT simply the sum of two `precip_24h` values -- it's today + yesterday, while `precip_7d` is 7 days BEFORE today. The definitions work but the naming is misleading.

### CAVEAT C4-2: Weather data coverage gaps (MEDIUM severity)

2,969 samples (8.2%) have NaN weather features:
- **1,215 samples** from 6 Alaska + 9 Hawaii sites: GridMET coverage does not extend to AK/HI. Weather directories exist but are empty. All weather features are NaN for these sites.
- **1,754 samples** from 43 CONUS sites: Weather files exist but data range starts 2006-01-01. Samples before 2006 (e.g., USGS-01658000 has discrete data back to 2003) have NaN weather.
- **397 samples** from USGS-250802081035500 (Everglades): Weather directory exists but is empty (download failure).

These NaN values are handled correctly by the tree-based models (LightGBM natively handles NaN), but it's important to know these sites never get weather-informed predictions.

---

## Check 5: Sensor Calibration Features - PASS

Verified 3 samples at USGS-385553107243301:

| Sample | Last Visit | Expected Offset | Paired Offset | Expected Days | Paired Days |
|--------|-----------|-----------------|---------------|---------------|-------------|
| #50 | 2015-05-07 | 0.00 | 0.00 | 16.8 | 16.8 |
| #200 | 2016-06-06 | 0.00 | 0.00 | 2.1 | 2.1 |
| #500 | 2018-05-11 | -0.10 | -0.10 | 55.1 | 55.1 |

- `sensor_offset` correctly inherits from most recent calibration visit BEFORE sample
- `days_since_last_visit` accurate to within 0.1 days
- `sensor_family` matches calibration record

18,211/36,103 samples (50.4%) have non-NaN sensor_offset. The remainder have NaN because either no calibration data exists for their site or no calibration visit preceded their sample date.

---

## Check 6: Collection Method - PASS WITH NOTE

- USGS-12189500: Correctly classified (520 auto_point, 97 depth_integrated, 1 grab)
- USGS-07257500: Correctly classified based on raw equipment names
- Discrete turbidity pairs: 13.1% have `collection_method = "unknown"` (1,177 samples)

### NOTE C6-1: "Unknown" collection method in discrete pairs (LOW severity)

1,177 discrete pairs have `collection_method = "unknown"`. These are primarily from older USGS records where the `SampleCollectionMethod/MethodIdentifier` is "USGS" (generic) and `SampleCollectionEquipmentName` is "Unknown". Sites most affected: USGS-14180300 (177), USGS-14179000 (136), USGS-01658000 (76). This is a data quality issue in the source records, not a pipeline bug.

---

## Check 7: Discrete Turbidity Pairs - PASS

- **Duplicate timestamps:** 4 pairs found where the same site + sample_time appears twice. In all 4 cases, the turbidity value is identical (same continuous reading matched), but the SSC values differ. These are genuinely different lab samples collected at the same time (e.g., replicate cross-section samples). Not a bug.
- **Window features:** All 8,975 discrete pairs correctly have NaN window features (turbidity_mean_1hr, etc.)
- **Continuous window features:** All 27,128 continuous pairs have populated window features (0% NaN)

**Duplicate details:**
| Site | Time | SSC_1 | SSC_2 | Turbidity |
|------|------|-------|-------|-----------|
| USGS-06893970 | 2015-07-07 00:00 | 4420 | 3070 | 640.0 |
| USGS-12166300 | 2014-10-13 11:00 | 33 | 518 | 22.0 |
| USGS-12187900 | 2017-07-20 21:40 | 121 | 109 | 27.5 |
| USGS-12189500 | 2011-11-21 12:00 | 4 | 51 | 1.2 |

NOTE: USGS-12166300 (SSC 33 vs 518) and USGS-12189500 (SSC 4 vs 51) show extremely large divergence between co-located samples. These may warrant investigation -- either the lab made an error or the cross-section had extreme heterogeneity.

---

## Check 8: Value Sanity Checks - MOSTLY PASS

| Check | Result | Status |
|-------|--------|--------|
| turbidity_instant < 0 | 0 | PASS |
| lab_value < 0 | 0 | PASS |
| turbidity_instant NaN | 0 | PASS |
| Continuous match_gap > 900s | 0 | PASS |
| Discrete match_gap > 3600s | 0 | PASS |
| Zero turbidity_instant | 57 (0.16%) | OK |
| Sites with identical lab_values | 0 | PASS |

### SSC Distribution (plausible):
- Mean: 292.2, Median: 56.0, P95: 1210.0, P99: 3360.0, Max: 70,000
- The max (70,000 mg/L) is extreme but physically possible (lahar/volcanic debris flow at USGS-12170300)

### Turbidity Distribution:
- Mean: 106.8, Median: 26.4, P95: 474.9, P99: 1160.0, Max: 5790.0
- Min: 0.0 (57 samples with exactly zero, physically reasonable for clear water)

### FINDING C8-1: Three zero-SSC samples NOT flagged as nondetect (LOW severity)
Three samples at USGS-01646000 have `lab_value = 0.0` and `is_nondetect = False`. The raw WQP data confirms `ResultMeasureValue = 0.0` with no detection condition text. These are either true zero concentrations or lab reporting errors. Since the detection limit is typically 1 mg/L, these should likely be flagged as nondetect or set to 0.5.

### FINDING C8-2: Anti-correlated sites (INFORMATIONAL)
Two sites show weak negative turbidity-SSC correlation:
- **USGS-12170300** (Nooksack River near Deming, WA): r = -0.085, n=73. SSC max = 70,000 mg/L with turb = 260 FNU. This is a glacial/lahar-prone watershed where high sediment loads can occur with relatively low turbidity (fine clay/glacial flour).
- **USGS-12186000** (Nisqually River near McKenna, WA): r = -0.015, n=120. This site is affected by the phantom pairing issue (see Check 9/Finding F1).

### FINDING C8-3: High NaN rates in derived features (MEDIUM severity)
Several derived features have >50% NaN:
- `discharge_slope_2hr`, `rising_limb`: 51.8% NaN (no discharge data)
- `Q_ratio_7d`, `turb_Q_ratio`: 59.1% NaN
- `DO_sat_departure`: 79.5% NaN
- `SC_turb_interaction`: 69.0% NaN

These reflect the reality that many sites lack co-located sensor data for conductance, DO, and discharge. LightGBM handles NaN natively, but features with >50% NaN may have reduced predictive value.

### Nondetect handling: CORRECT
185 samples are `is_nondetect = True`. Lab values are set to half the detection limit (154 samples at 0.50, 26 at 2.00, etc.). This is the standard substitution approach.

---

## Check 9: Dedup Bug (C2) - PASS

**Zero overlap between continuous and discrete pairs.** No sample appears in both `turb_source='continuous'` and `turb_source='discrete'`. The dedup logic in `assemble_dataset.py` (using `existing_pairs` set on line ~470) correctly prevents this.

226 sites have both continuous and discrete pairs, confirming the dedup is actively working.

---

## CRITICAL FINDING F1: 2,695 Phantom Continuous Pairings

### Description

78 sites (2,695 samples) have `turb_source='continuous'` but their sample timestamps fall OUTSIDE the date range of available continuous turbidity (63680) data. These pairings are **impossible to reproduce** from the current data on disk.

### Magnitude

- 2,695 / 27,128 continuous pairs = **9.9% of all continuous data**
- 2,695 / 36,103 total = **7.5% of the entire dataset**

### Most affected sites (top 10):

| Site | Phantom / Total | % |
|------|----------------|---|
| USGS-040851385 | 213 / 274 | 77.7% |
| USGS-03432504 | 192 / 217 | 88.5% |
| USGS-03432100 | 138 / 139 | 99.3% |
| USGS-12186000 | 116 / 120 | 96.7% |
| USGS-01581752 | 104 / 140 | 74.3% |
| USGS-11516530 | 98 / 98 | 100.0% |
| USGS-11520500 | 96 / 272 | 35.3% |
| USGS-01651730 | 87 / 120 | 72.5% |
| USGS-01585075 | 84 / 91 | 92.3% |
| USGS-12170300 | 73 / 73 | 100.0% |

### Root cause (probable)

The `turbidity_ssc_paired.parquet` was generated from a previous run when full continuous turbidity data existed. Subsequently, a data recovery/reorganization process (batch_v2) replaced original continuous files with partial data, reducing temporal coverage. The paired output was not regenerated.

Evidence:
- batch_v2 files (created 02:11 today) contain only partial time ranges (e.g., USGS-12186000 has only Sep 2011 - Jan 2012)
- Manual re-alignment of USGS-12186000 with current data produces only 4 matches (vs 120 in paired output)
- The pipeline script (`assemble_dataset.py`) was modified at 10:39 AM, AFTER the paired file timestamp (10:14 AM)
- 78 affected sites all have batch_v2 files in their 63680 directories

### Impact

- The 2,695 phantom pairs have turbidity values that CANNOT be verified against current data
- Anti-correlation at USGS-12186000 (SSC=12200 paired with turb=8.6) may be a data integrity issue rather than a real physical phenomenon
- Model training on unverifiable data undermines reproducibility
- Any rerun of `assemble_dataset.py` would produce a significantly different dataset

### Recommendation

**Regenerate `turbidity_ssc_paired.parquet`** by re-running the assembly pipeline. This will drop the 2,695 phantom pairs but ensure all remaining pairs are verifiable. If the original full continuous data is recoverable (from USGS NWIS re-download), do that first to maximize sample retention.

---

## SUMMARY

| Check | Result | Severity |
|-------|--------|----------|
| 1. Raw SSC -> Paired | PASS | - |
| 2. Turbidity interpolation | PASS | - |
| 3. Window features | PASS | - |
| 4. Weather features | PASS with caveats | LOW-MED |
| 5. Sensor calibration | PASS | - |
| 6. Collection method | PASS with note | LOW |
| 7. Discrete turb pairs | PASS | - |
| 8. Value sanity | MOSTLY PASS | LOW-MED |
| 9. Dedup bug (C2) | PASS | - |
| **F1. Phantom pairings** | **FAIL** | **HIGH** |

### Action Items

1. **HIGH: Regenerate paired output** after recovering full continuous data or accepting sample loss (F1)
2. **MEDIUM: Investigate weather download failures** for USGS-250802081035500 and other CONUS sites with empty weather dirs (C4-2)
3. **LOW: Consider flagging 3 zero-SSC samples** as nondetect at USGS-01646000 (C8-1)
4. **LOW: Document weather window definitions** to avoid confusion about what "7d" means (C4-1)
5. **INFORMATIONAL: Investigate duplicate co-samples** at USGS-12166300 (SSC 33 vs 518) -- possible lab error

### What's Working Well

The core pipeline logic is sound:
- SSC values correctly propagated from raw WQP data
- UTC conversion is flawless
- Turbidity interpolation is mathematically correct
- Window features computed correctly
- Sensor calibration linked properly
- Dedup between continuous and discrete tiers works
- Nondetect handling follows standard substitution
- All derived features (log transforms, doy encoding) verify correctly
