# Unknown Collection Method Audit
Date: 2026-03-28

## 1. Scope of the Problem

- Total samples in paired dataset: 35,209
- Samples with unknown collection method: 6,282 (17.8%)
- Sites with unknown method: 231
- collection_method is 3rd most important feature (SHAP=0.310)

### Collection method distribution (full dataset):
  - auto_point: 12,653 (35.9%)
  - depth_integrated: 11,714 (33.3%)
  - unknown: 6,282 (17.8%)
  - grab: 4,560 (13.0%)

## 2. WQP Equipment Data Retrieved

Queried all 231 unknown-method sites via WQP `get_results` for
'Suspended Sediment Concentration (SSC)' records.

- Sites with known equipment in WQP records: 218/231
- Sites with ONLY 'Unknown' equipment: 13/231

## 3. Resolution Results

### 3a. Timestamp Matching (highest confidence)
Matched WQP records to our paired samples by exact date.

- Sites with at least 1 date match: 85
- Total samples resolved by date: 594/6,282 (9.5%)
  - depth_integrated: 336
  - auto_point: 74
  - grab: 12
  - still unknown (matched to 'Other'): 172

### 3b. Site-Level Dominant Method
For sites where timestamp matching failed, assigned the most common
known equipment type across ALL WQP records at that site.

- Single-method sites (high confidence): 47 sites, 967 samples
- Multi-method sites (dominant assigned): 171 sites, 4,569 samples
- Truly unresolvable: 13 sites, 746 samples

### 3c. Combined Resolution Summary

Proposed method assignments (site-level dominant, all confidence levels):
  - depth_integrated: 182 sites, 3,667 samples
  - auto_point: 30 sites, 1,791 samples
  - grab: 6 sites, 78 samples
  - unresolvable: 13 sites, 746 samples

## 4. Catastrophic Sites Cross-Reference

Total catastrophic sites (R2 < -1): 51
Catastrophic sites with unknown method: 30 (59%)

| Site | R2_native | Unknown Samples | Date-Matched | Proposed Method | Confidence |
|------|-----------|-----------------|--------------|-----------------|------------|
| USGS-01311875 | -1.9 | 47 | 0 | unresolvable | unresolvable |
| USGS-01372043 | -2.4 | 12 | 0 | depth_integrated | low_mixed |
| USGS-01478185 | -2.0 | 13 | 10 | depth_integrated | low_mixed |
| USGS-01573695 | -1.9 | 21 | 0 | depth_integrated | low_mixed |
| USGS-01573710 | -2.5 | 23 | 0 | depth_integrated | low_mixed |
| USGS-01576980 | -1.2 | 10 | 0 | depth_integrated | high |
| USGS-04026005 | -24.8 | 13 | 0 | unresolvable | unresolvable |
| USGS-04095090 | -18.8 | 45 | 0 | auto_point | high |
| USGS-04108660 | -1.1 | 1 | 0 | depth_integrated | low_mixed |
| USGS-04195500 | -1.9 | 11 | 0 | depth_integrated | low_mixed |
| USGS-04249000 | -13.0 | 80 | 0 | depth_integrated | high |
| USGS-05406479 | -2.2 | 20 | 0 | unresolvable | unresolvable |
| USGS-06887000 | -1.7 | 6 | 6 | depth_integrated | high |
| USGS-06893820 | -1.5 | 52 | 1 | auto_point | low_mixed |
| USGS-06893830 | -36.8 | 50 | 0 | auto_point | low_mixed |
| USGS-07030392 | -4.8 | 52 | 0 | depth_integrated | low_mixed |
| USGS-07048600 | -2.5 | 1 | 0 | depth_integrated | low_mixed |
| USGS-071948095 | -1.3 | 2 | 0 | depth_integrated | low_mixed |
| USGS-07263296 | -3.3 | 3 | 1 | depth_integrated | low_mixed |
| USGS-0728875070 | -2.3 | 1 | 1 | depth_integrated | low_mixed |
| USGS-07381600 | -1.8 | 1 | 0 | depth_integrated | high |
| USGS-11185185 | -6.3 | 13 | 0 | auto_point | low_mixed |
| USGS-11336680 | -44.8 | 5 | 0 | depth_integrated | low_mixed |
| USGS-11336685 | -45.9 | 5 | 2 | depth_integrated | low_mixed |
| USGS-11336790 | -12.8 | 12 | 0 | depth_integrated | low_mixed |
| USGS-11455280 | -5.3 | 7 | 2 | depth_integrated | low_mixed |
| USGS-11455335 | -27.3 | 10 | 8 | depth_integrated | low_mixed |
| USGS-11455350 | -15.1 | 13 | 0 | grab | low_mixed |
| USGS-12323700 | -24.5 | 2 | 0 | depth_integrated | low_mixed |
| USGS-14181500 | -34.6 | 20 | 0 | unresolvable | unresolvable |

## 5. Recommendations

### What to change:
1. **High confidence (47 sites, 967 samples):** Sites where WQP shows only ONE
   known equipment category. Safe to reclassify.
2. **Timestamp-matched (85 sites, 594 samples with direct date match):**
   Per-sample resolution where the exact WQP record has known equipment.
   Most reliable, but only covers ~9% of unknown samples.
3. **Site-level dominant (171 sites, 4,569 samples):** Multiple equipment
   types used at site. Can assign dominant method but introduces noise.

### Recommended approach:
- **Phase 1:** Apply high-confidence single-method resolution (47 sites).
  These sites only ever used one known method, so the 'unknown' records
  almost certainly used the same method.
- **Phase 2:** Apply timestamp-matched resolutions where available.
  This gives per-sample accuracy for 594 samples.
- **Phase 3 (optional):** For remaining mixed-method sites, assign dominant
  method. This reduces 'unknown' from 6,282 to ~746 samples but adds noise.
- **13 truly unresolvable sites (746 samples)** have no equipment info in WQP.
  These stay 'unknown'.

### Impact on catastrophic sites:
- 30/51 catastrophic sites have unknown method
- Only 4 of these are truly unresolvable (USGS-01311875, USGS-04026005,
  USGS-05406479, USGS-14181500)
- 26 catastrophic sites can get a method assignment
- However, fixing collection_method alone will not fix catastrophic performance --
  these sites likely have other issues (data quality, regime mismatch, etc.)

### Files produced:
- `data/unknown_method_wqp_results.json` - Raw WQP equipment data per site
- `data/unknown_method_resolution.csv` - Site-level resolution table
- `data/unknown_method_resolution_detail.json` - Full detail with equipment lists
- `data/unknown_method_timestamp_match.json` - Per-sample timestamp matching
- `data/unknown_method_audit_report.md` - This report
