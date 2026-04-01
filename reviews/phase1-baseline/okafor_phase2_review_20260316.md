# Phase 2 Data Download Review -- Dr. Jenna Okafor
**Date:** 2026-03-16
**Scope:** Scan, discrete download, GAGES-II, and NLDI scripts + output data
**Verdict:** Two medium-severity bugs, one low-severity issue, several informational notes. No showstoppers, but the duplicate and catchment-attribute gaps need fixes before model training.

---

## Severity Legend
- **HIGH** -- Will corrupt model training or produce silently wrong results
- **MEDIUM** -- Will cause data loss or requires a code fix before production use
- **LOW** -- Suboptimal but not currently causing errors
- **INFO** -- Worth knowing, no action needed now

---

## Finding 1: Scan vs. Download Race Condition

**Severity: INFO -- No bug found**

The scan script (`scan_parameters.py`) calls `waterdata.get_samples()` but only extracts `len(df)` from the result. It does NOT cache the returned DataFrame to `data/discrete/`. The download script (`download_discrete_params.py`) independently calls `get_samples()` and writes to `data/discrete/{site}_{param}.parquet`, with a cache-hit check on that path.

There is no race condition. The scan discards the full data; the download script writes fresh results. The scan's `parameter_scan_progress.parquet` stores only counts (site_id, pcode, param_name, n_samples), not row data.

**One concern remains:** The scan and download scripts make identical API calls at different times. If the WQP database was updated between runs (new samples added, old records revised), the scan count could differ from the actual downloaded row count. This is a minor theoretical issue -- the scan counts are only used for the >= 10 filter, so a few rows of drift is harmless.

**No action required.**

---

## Finding 2: GAGES-II STAID Matching for Long-Format Site IDs

**Severity: LOW -- Correctly handled, but one site has zero catchment attributes**

The matching logic in `download_gagesii.py` lines 181-189 explicitly handles long IDs:

```python
if len(num) <= 8:
    num_padded = num.zfill(8)
else:
    num_padded = num
```

This is correct. `zfill(8)` is a no-op for the 15-digit site `USGS-385903107210800` because `len("385903107210800") = 15 > 8`.

However, **this site is simply not in the GAGES-II dataset at all** (GAGES-II has 9 sites with 15-digit STAIDs, none matching `385903107210800`). So it correctly falls through to the "unmatched" list.

The NLDI fallback (`fill_attributes_nldi.py`) retrieved a COMID (1337100) for this site but failed to get any characteristics -- all 20 unmatched sites returned `source=none`. This means **20 of 57 sites (35%) have zero catchment attributes**. That is a significant gap for any model that uses basin characteristics as features.

**Recommended action:** Investigate why NLDI returned no characteristics for any of the 20 sites. 17 of the 20 did return valid COMIDs, so the sites exist in NHD. The `/tot` endpoint may have changed its response format, or the NLDI API may have been down during the run. Consider re-running, or using the COMIDs to query NHDPlus characteristics via a different endpoint.

---

## Finding 3: Discrete Data Column Consistency

**Severity: INFO -- Clean**

All 182 discrete files (across 4 parameters) return exactly 181 columns. The column names and order are identical across all files and all parameters. There are no extra or missing columns.

Each parameter returns exactly one `Result_SampleFraction` value:
- **Total Phosphorus (00665):** `Unfiltered` (30,637 rows)
- **Nitrate+Nitrite (00631):** `Filtered field and/or lab` (28,309 rows)
- **TDS Evaporative (70300):** `Filtered field and/or lab` (14,488 rows)
- **Orthophosphate (00671):** `Filtered field and/or lab` (21,137 rows)

**Note on TP fraction naming:** WQP returns `Unfiltered` rather than `Total` for TP (pcode 00665). This is semantically correct -- total phosphorus is measured on an unfiltered sample. The SSC pipeline should label this as "Total P" in any user-facing output, but the underlying data is correct.

**Note on nitrate fraction:** Nitrate+nitrite (00631) returns `Filtered field and/or lab`, which is the standard dissolved fraction. If you later need to distinguish dissolved vs. total nitrogen, you would need pcode 00600 (total nitrogen). The current download is internally consistent.

Each parameter has exactly one `USGSpcode` value per file -- no cross-contamination.

**No action required.**

---

## Finding 4: Unit Consistency

**Severity: INFO -- Clean**

All 4 parameters report `mg/L` exclusively across all files. There are zero rows with `ug/L`, `mg/kg`, or any other unit variant. No order-of-magnitude conversion bugs are possible from this data.

**No action required.**

---

## Finding 5: Duplicate Detection

**Severity: MEDIUM -- 88 same-key duplicates across 12 files, including 5 with conflicting values**

### What I found:

Across all 246 discrete files (including SSC), there are **0 exact row duplicates** but **88 rows that share the same (Activity_StartDate, Activity_StartTime, USGSpcode) key** with at least one other row (i.e., 88 duplicate rows to remove if keeping first).

Breakdown by parameter:
| Parameter | Files with dupes | Dupe rows | Worst file |
|-----------|-----------------|-----------|------------|
| total_phosphorus | 2 | 12 | USGS_04188496 (10 rows) |
| nitrate_nitrite | 2 | 12 | USGS_04188496 (10 rows) |
| tds_evaporative | 6 | 44 | USGS_09152500 (16 rows) |
| orthophosphate | 2 | 12 | USGS_04188496 (10 rows) |

### Two distinct dupe patterns:

**Pattern A -- Same-value dupes (USGS_04188496):** These rows have identical `Result_Measure` values and even the same `Activity_ActivityIdentifier`, differing only in `Result_MeasureIdentifier` (a UUID). This is a WQP artifact where the same result was returned twice with different result-level IDs. Safe to deduplicate by keeping first.

**Pattern B -- Different-value dupes (USGS_09152500 TDS):** These rows share the same date/time/pcode but have **different `Result_Measure` values** and different `Activity_ActivityIdentifier` UUIDs. Examples:
- 1959-10-01: TDS = 1290 vs 1310 mg/L
- 1960-05-10: TDS = 350 vs 269 mg/L (23% difference)
- 1960-07-20: TDS = 1560 vs 1460 mg/L

These are likely replicate analyses or different analytical methods on the same sample. Blindly keeping the first row is lossy. The correct approach is to average replicates or flag them for review.

### Comparison with SSC pipeline:

The SSC pipeline in `assemble_dataset.py` (line 154) deduplicates on `(datetime, ssc_value)`, which means it only removes rows where both the timestamp AND value match. This would miss Pattern B dupes (same time, different value). However, SSC had zero such dupes in practice, so the logic worked. The new parameters DO have Pattern B dupes.

**Recommended action:**
1. Add dedup logic to any script that consumes the new discrete parameters.
2. For Pattern A (same key, same value): drop duplicates, keep first.
3. For Pattern B (same key, different values): average the values, or keep the one with the more recent `Activity_ActivityIdentifier` (which may indicate a revised result). At minimum, log these cases.

---

## Finding 6: GAGES-II Mixed-Type Column Handling (80% Threshold)

**Severity: LOW -- Threshold is reasonable but caused one semantic issue**

The 80% threshold in `download_gagesii.py` (lines 231-236) converts object columns to float if >80% of non-null values parse as numeric. This is a sensible heuristic and in practice it worked correctly for the vast majority of columns:

- **576 total columns:** 516 float64, 39 int64, 21 object
- No columns fell in the 15-25% NaN range that would indicate edge-case threshold behavior
- The 21 remaining object columns are genuinely categorical (STATE, CLASS, STANAME, etc.)

**One semantic issue found:** `HUC02` (Hydrologic Unit Code, 2-digit) was converted to float64. It now contains values like `1.0, 2.0, ... 18.0` instead of the proper string codes `"01", "02", ... "18"`. HUC codes are categorical identifiers, not continuous numbers -- HUC 01 is not "less than" HUC 02 in any meaningful sense. The 10.2% NaN rate on this column is because GAGES-II doesn't assign HUC02 to Alaska/Hawaii/PR sites.

If HUC02 is used as a model feature, it should be treated as a categorical variable (one-hot encoded or label encoded), not as a continuous float. The current float representation will mislead any tree-based model into thinking HUC 3 is "between" HUC 2 and HUC 4.

**Recommended action:** When building model features from GAGES-II, explicitly cast `HUC02` (and similar code columns like `FIPS_SITE`) to string/categorical before encoding. The 80% threshold does not need to change -- this is a downstream encoding concern.

---

## Finding 7: Censored Data Handling

**Severity: INFO -- Rates are manageable, but needs pipeline code**

Censoring rates by parameter:
| Parameter | Not Detected rows | Total rows | Rate |
|-----------|------------------|------------|------|
| Total Phosphorus | 284 | 30,637 | 0.9% |
| Nitrate+Nitrite | 1,581 | 28,309 | 5.6% |
| TDS Evaporative | 4 | 14,488 | 0.0% |
| Orthophosphate | 1,927 | 21,137 | 9.1% |

For censored rows, `Result_Measure` is NaN and `DetectionLimit_MeasureA` contains the detection limit (e.g., 0.001-0.01 mg/L for orthophosphate). The SSC pipeline uses DL/2 substitution (line 144 of `assemble_dataset.py`), which is standard practice when censoring is <10%.

Orthophosphate at 9.1% is right at the threshold. Some individual sites likely exceed 10%, which the existing `analyze_new_params.py` script already flags.

**No action required now** -- but when building the multi-target pipeline, the DL/2 substitution logic from the SSC assembler needs to be replicated for each new parameter. The censoring analysis is already done (`data/censoring_rates.parquet`).

---

## Finding 8: NLDI Total Failure

**Severity: MEDIUM -- 20 sites (35%) have no catchment attributes**

All 20 NLDI queries for upstream characteristics returned non-JSON responses (the script notes this in the task description). COMIDs were successfully retrieved for 17 of the 20 sites via the base NLDI endpoint, but the `/tot` (total upstream characteristics) endpoint returned nothing usable.

This is likely an API issue rather than a code bug. The NLDI `/tot` endpoint has been unreliable historically, and the response format may have changed. The sites themselves are valid USGS gages with real COMIDs.

**Recommended action:**
1. Re-run `fill_attributes_nldi.py` to see if the API has recovered.
2. If still failing, use the 17 COMIDs to query `https://www.sciencebase.gov/catalog/items?filter=nhdplusv2comid%3D{comid}` or the EPA StreamCat dataset as an alternative source of catchment characteristics.
3. Consider whether the 37 GAGES-II-matched sites are sufficient for a model that uses catchment attributes, or if the 20-site gap is a problem for spatial generalization.

---

## Summary Table

| # | Finding | Severity | Action Needed |
|---|---------|----------|---------------|
| 1 | Scan vs download race condition | INFO | None |
| 2 | Long-format STAID matching | LOW | None (code is correct) |
| 3 | Column consistency across params | INFO | None |
| 4 | Unit consistency | INFO | None |
| 5 | 88 duplicate rows (12 files) | MEDIUM | Add dedup logic for new params |
| 6 | HUC02 stored as float | LOW | Cast to categorical at model time |
| 7 | Censored data rates | INFO | Replicate DL/2 logic for new params |
| 8 | NLDI total failure (20 sites) | MEDIUM | Re-run or use alternative data source |

**Bottom line:** The download pipeline is well-constructed. Units are clean, columns are consistent, the scan-download interaction is correct, and the STAID matching handles edge cases properly. The two items that need attention before model training are (a) deduplicating the 88 same-key rows in the new parameter files, especially the 5 cases where values conflict, and (b) filling the catchment attribute gap for 20 sites.
