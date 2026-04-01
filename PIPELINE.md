# murkml Data Pipeline

How raw USGS data becomes an ML-ready dataset. Read this before running anything.

---

## Overview

```
Download  -->  QC  -->  Align  -->  Features  -->  Attributes  -->  Train
```

Each step has a script. They run in order. Skipping a step will break the next one.

---

## Step 1: Download Raw Data

**Scripts:** `download_gap_fill_fast.py` (reference RDB implementation), `download_batch.py`, `qualify_sites.py`

**What it does:**
- Pulls continuous sensor data (15-min interval) from USGS waterdata API
- Pulls discrete lab samples (grab samples, irregular timing) from the same API
- Stores everything locally so we never re-download

**Continuous sensors pulled (per site):**

| Parameter | pcode | Stored as |
|-----------|-------|-----------|
| Turbidity (FNU) | 63680 | `data/continuous/{site_id}/63680/*.parquet` |
| Specific conductance | 00095 | `data/continuous/{site_id}/00095/*.parquet` |
| Dissolved oxygen | 00300 | `data/continuous/{site_id}/00300/*.parquet` |
| pH | 00400 | `data/continuous/{site_id}/00400/*.parquet` |
| Temperature | 00010 | `data/continuous/{site_id}/00010/*.parquet` |
| Discharge | 00060 | `data/continuous/{site_id}/00060/*.parquet` |

Continuous data is chunked into 3-year windows because the API has row limits.

**Discrete lab samples pulled (per site):**

| Parameter | pcode | Stored as |
|-----------|-------|-----------|
| Suspended sediment (SSC) | 80154 | `data/discrete/{site_id}_ssc.parquet` |
| Total phosphorus | 00665 | `data/discrete/{site_id}_total_phosphorus.parquet` |
| Nitrate+nitrite | 00631 | `data/discrete/{site_id}_nitrate_nitrite.parquet` |
| Orthophosphate | 00671 | `data/discrete/{site_id}_orthophosphate.parquet` |

**Rate limits:** USGS allows 1000 requests/hour with an API token (`API_USGS_PAT` env var). Scripts track remaining requests and pause if needed.

**How to verify:** Check `data/continuous/` has a folder per site, and `data/discrete/` has parquet files per site+parameter. Currently 396 sites.

---

## Step 2: Quality Control (QC)

**Code:** `src/murkml/data/qc.py` (called automatically during assembly)

**What it does to continuous sensor data:**
- Keeps only USGS "Approved" data (drops Provisional)
- Removes records flagged with bad qualifiers: Ice, Equipment malfunction (Eqp), Backwater (Bkw), Maintenance (Mnt), estimated (e)
- **Ice buffer (IMPLEMENTED 2026-03-24):** Extends Ice exclusion by 48 hours after the flag ends (bottom ice releases trapped sediment when it melts — sensor reads are unreliable)
- **Maintenance buffer (IMPLEMENTED 2026-03-24):** Extends Maintenance exclusion by 4 hours (freshly cleaned sensors have step discontinuities)
- Keeps Flood (Fld) flagged data — those are the storm events we care most about
- **Raises `ValueError` on missing expected columns** instead of silently skipping (hardened 2026-03-24)

**USGS qualifier format note (2026-03-24 fix):** The USGS API returns qualifier values as array-like strings, e.g., `"['ICE' 'EQUIP']"`, NOT as simple strings like `"Ice"`. The QC code now parses this format correctly. Prior to the fix, qualifier matching was silently failing — no Ice/Equip/Maint records were ever being excluded.

**What it does to discrete lab samples:**
- Drops samples with no timestamp (does NOT default to noon — that would create false alignment)
- Drops samples with unrecognized timezones
- Converts all timestamps to UTC using USGS timezone codes
- Handles non-detects: substitutes detection limit / 2 (standard DL/2 method)
- Keeps SSC = 0 (valid measurement, log1p handles it)
- Deduplicates samples with identical timestamp + value

**Why this matters:** Raw USGS data includes ice-affected readings, equipment glitches, and provisional estimates. Training on bad data teaches the model bad relationships. The QC step is the difference between R² = 0.6 and R² = 0.8.

---

## Step 3: Temporal Overlap Audit

**Script:** `check_temporal_overlap.py`

**What it does:** For each site and each discrete parameter, counts how many lab samples fall within the continuous turbidity sensor record period. A site might have 200 TP samples total, but if the turbidity sensor wasn't installed until 2018, only 40 of those samples are usable.

**Output:** `data/temporal_overlap_audit.parquet` — a table of site_id, param_name, n_total, n_pairable

**Why this matters:** The assembly step uses this audit to decide which sites have enough pairable samples (default threshold: 20). Without this step, the assembler doesn't know which sites to include for TP, nitrate, etc.

**When to run:** After downloading new sites, before assembling TP/nutrient datasets. The SSC assembler doesn't use this file (it checks directly), but the multi-param assembler does.

---

## Step 4: Align Discrete Samples to Continuous Sensors

**Scripts:** `assemble_dataset.py` (SSC only — TP/nitrate/orthoP were dropped, see DECISION_LOG)

**What it does:** This is the core step. For each discrete lab sample:

1. Find the closest continuous turbidity reading within +/- 15 minutes
2. If no match within 15 min, discard the sample (per Rasmussen 2009 standard)
3. For matched samples, compute a 1-hour window around the match time:
   - Turbidity: instant, mean, min, max, std, range, slope
4. For each other continuous sensor (conductance, DO, pH, temp, discharge):
   - Find the nearest reading within +/- 15 min of the same match time
   - Store as instantaneous value (NaN if no reading available)

**Output:**
- `data/processed/turbidity_ssc_paired.parquet` — SSC dataset (396 sites, 35,209 samples)

Each row = one lab sample matched to its sensor context. Columns include the lab value, all sensor readings, site_id, timestamp, and non-detect flag.

**The 15-minute rule:** If a technician collected a water sample at 10:30 AM but the turbidity sensor's nearest reading is 10:52 AM, that's a 22-minute gap. The river could have changed. We throw that sample out. This is strict but prevents training on mismatched pairs.

---

## Step 5: Feature Engineering

**Code:** `src/murkml/data/features.py` (called automatically during assembly)

**Features added:**
- **Hydrograph position:** Rate of change in discharge and turbidity over 1hr, 6hr, 24hr windows — tells the model whether the river is on a rising limb, peak, or falling limb
- **Cross-sensor ratios:** Turbidity/discharge ratio, turbidity/conductance ratio — these capture whether sediment is supply-limited or transport-limited
- **DO saturation departure:** Uses Benson & Krause (1984) nonlinear polynomial for DO saturation as a function of temperature and pressure. **(Fixed 2026-03-24 — was using a broken linear approximation `14.6 - 0.4*T` with 27-65% error at common stream temperatures. Never use a linear DO saturation formula.)**
- **Seasonality:** Sin/cos encoded day-of-year and hour-of-day — captures snowmelt timing, diurnal biological cycles
- **Log transforms:** log1p of the target variable (SSC, TP, etc.) — water quality values are log-normally distributed

---

## Step 6: Watershed Attributes (EPA StreamCat + SGMC Lithology)

**Scripts:** `download_streamcat.py` (StreamCat), `compute_watershed_lithology.py` + `extract_sgmc_lithology.py` (SGMC)

**What it does:** Loads two complementary attribute datasets:

1. **EPA StreamCat** — 781 sites, 69 static catchment features after filtering. Loaded by `src/murkml/data/attributes.py` → `load_streamcat_attrs()`. Covers land cover, soils, climate, topography, hydrology from a single consistent framework.

2. **SGMC Lithology** — 355 sites, 28 watershed geology percentage features. Loaded from `data/sgmc/sgmc_features_for_model.parquet`, merged into training in `train_tiered.py`. Categories include igneous, metamorphic, sedimentary, unconsolidated rock types as watershed percentages.

**Output:**
- StreamCat attributes loaded dynamically by `build_feature_tiers()` in `src/murkml/data/attributes.py`
- `data/sgmc/sgmc_features_for_model.parquet` — SGMC lithology features

**Note:** GAGES-II was the original attribute source but was replaced by StreamCat after a critical bug (`prune_gagesii()` silently destroying data). `prune_gagesii()` still exists in code but is dead — do not use it. See DECISION_LOG for full history.

---

## Step 7: Build Feature Tiers

**Code:** `src/murkml/data/attributes.py`

Three tiers used for ablation testing:

| Tier | Features | Purpose |
|------|----------|---------|
| A | Sensor readings only (turbidity, conductance, DO, pH, temp, discharge + engineered) — 37 features, 396 sites | Baseline — what can sensors alone tell us? |
| B | A + basic site attributes (lat, lon, drainage area, elevation) — 42 features, 396 sites | Does location help? |
| C | B + StreamCat + SGMC lithology — 137 features pre-drop, 72 post-drop, 357 sites | Does watershed context help? |

Tier C is the production tier. 65 features on `data/optimized_drop_list.txt` are always dropped via `--drop-features`. The B vs C improvement is statistically significant (p<0.01).

---

## Step 8: Train

**Script:** `train_tiered.py` (main training — all tiers, all params)

**Model:** CatBoost (gradient-boosted trees) with depth=6, lr=0.05, l2_reg=3, 500 iter max, ordered boosting. Key flags: `--cv-mode gkf5|logo`, `--transform boxcox`, `--boxcox-lambda 0.2`, `--drop-features`, `--skip-ridge`, `--n-jobs 12`, `--label`.

**Target:** Box-Cox(SSC, lambda=0.2) with Dual BCF back-transformation (bcf_mean=1.327 for loads, bcf_median=1.021 for individual predictions).

**Monotone constraints:** ON for turbidity_instant and turbidity_max_1hr (physics: turb up -> SSC up). Helps Box-Cox but would hurt log1p.

**Validation:** Leave-One-Group-Out (LOGO) cross-validation, where each "group" is a site. 254 training sites, with 76 holdout + 36 vault excluded. GKF5 (5-fold grouped shuffle) used for quick experiments.

**3-way split:** `data/train_holdout_vault_split.parquet` — 254 train / 76 holdout / 36 vault. Created after identifying that repeated ablation on holdout constitutes implicit overfitting.

**Early stopping:** GroupShuffleSplit validation + early_stopping_rounds=50.

**Metrics:** R²(log), R²(native), KGE, RMSE, bias, MedSiteR², MAPE, Within-2x, Spearman. Always report both log-space and native-space.

---

## Running the Full Pipeline

From the murkml project root, with `.venv` activated (`.venv/Scripts/python` on Windows):

```bash
# 1. Discover + qualify sites
python scripts/qualify_sites.py

# 2. Download sensor + discrete data (RDB format, 8 concurrent workers)
python scripts/download_gap_fill_fast.py

# 3. Assemble SSC dataset (includes QC, alignment, feature engineering)
python scripts/assemble_dataset.py

# 4. Download StreamCat attributes (once)
python scripts/download_streamcat.py

# 5. Compute SGMC lithology features (once)
python scripts/compute_watershed_lithology.py

# 6. Train (Tier C, Box-Cox 0.2, LOGO CV)
python scripts/train_tiered.py --param ssc --tier C --transform boxcox --boxcox-lambda 0.2 \
    --n-jobs 12 --drop-features "$(cat data/optimized_drop_list.txt)"

# 7. Evaluate (holdout + adaptation + external)
python scripts/evaluate_model.py --model data/results/models/ssc_C_sensor_basic_watershed_v10_clean_dualbcf.cbm \
    --bcf-mode median --k 15 --df 4
```

---

## Data Directory Layout

```
data/
  continuous/          <- 15-min sensor data, one folder per site (396 sites)
    USGS_01491000/
      63680/           <- turbidity parquet chunks
      00095/           <- conductance
      ...
  discrete/            <- lab samples, one file per site+param
    USGS_01491000_ssc.parquet
    ...
  processed/           <- ML-ready aligned datasets
    turbidity_ssc_paired.parquet  (396 sites, 35,209 samples)
  sgmc/                <- SGMC lithology features
    sgmc_features_for_model.parquet  (355 sites, 28 features)
  weather/             <- GridMET daily weather per site
    USGS_{site_no}/daily_weather.parquet
  train_holdout_vault_split.parquet  <- 3-way split (254/76/36)
  optimized_drop_list.txt            <- 65 features to drop
  results/
    models/            <- saved .cbm + _meta.json files
    evaluations/       <- per-reading, per-site, summary JSONs
```

---

## Data Integrity Rules (added 2026-03-24)

These rules exist because of a bug where `prune_gagesii()` was called on already-pruned data, silently destroying all watershed attributes. The model trained on 25 columns of zeros/NaN without any error or warning. See DECISION_LOG for the full post-mortem.

1. **Verify intermediate data products contain expected values.** After any transformation, check that output columns have real values (not all zeros, not all NaN, correct dtypes). A 5-row `head()` check would have caught the original bug.

2. **Transformation functions should validate their inputs and fail loudly on unexpected column names.** Never silently fill with defaults at scale.

3. **All results must have a clear provenance chain:** raw data file -> processing function -> feature columns -> model -> metrics. If you can't trace a reported R² value back to the exact input data and code path that produced it, it's not publishable.

4. **Never overwrite model files.** Version everything, commit to git immediately.
