# Fix Plan: murkml Audit Remediation

> **SUPERSEDED (2026-03-26): ALL AUDIT ITEMS COMPLETE.** Expanded to 270 paired sites (243 training). All red team fixes implemented and active in current model. StreamCat replaced GAGES-II. Current: log R²=0.71, native R²=0.55 on holdout. See RESULTS_LOG.md.
>
> Previous (2026-03-25): ORIGINAL AUDIT SUBSTANTIALLY COMPLETE.
> All critical and most important fixes from this 4-reviewer audit (Mar 16-17) have been implemented. The project has since expanded to 102 sites, R² reached 0.80 (log) / 0.61 (native), and a **new 5-reviewer red team panel** was conducted on 2026-03-24 with additional findings.
>
> **For the current plan, see `RESULTS_LOG.md`** — sections on "Red Team Panel Review" and "Code Fixes Implemented" document the new findings and their status.
>
> The content below is preserved as historical record of the original audit. Items marked [DONE] have been implemented.

## Context

Four expert reviewers (ML Engineer, Domain Scientist, Critical Reviewer, Data Engineer) independently audited the murkml codebase and results. They found **4 critical bugs, 15 important issues, and 10 minor issues.** Three of the critical bugs were flagged by all four reviewers independently (highest confidence). The current R²=0.67 result is **inflated and unreliable** due to information leakage and data corruption. This plan addresses every finding, prioritized by impact.

**Current state (at time of audit):** 57 sites, 17,054 paired samples, 11 states, 4.9GB continuous data. CatBoost LOGO R²=0.67 (log) — but this number is wrong due to bugs below. The real number is probably 0.55-0.62.

**Goal:** Fix all critical and important issues, re-run baselines, and get honest numbers we can stand behind.

---

## CRITICAL FIXES (must do first — results are invalid without these) — ALL DONE

### [DONE] Fix 1: Timezone Bug (Okafor — confirmed)
**File:** `scripts/assemble_dataset.py` lines 57-66
**Problem:** Discrete sample timestamps are in local time (EST, CST, MST, etc.) but `pd.to_datetime(..., utc=True)` labels them as UTC without converting. Every temporal alignment is off by 5-8 hours. Continuous data IS in UTC (from the new API). So a Kansas sample collected at 10:00 AM CST is matched to the 10:00 AM UTC sensor reading (which is 4:00 AM local — 6 hours wrong).
**Evidence:** Data confirms EST, EDT, CST, CDT, MST, MDT timezone codes in `Activity_StartTimeZone` column — all ignored.
**Fix (do together with Fix 6 — they touch the same lines):**
1. Map USGS timezone abbreviations to UTC offsets: `{"EST": -5, "EDT": -4, "CST": -6, "CDT": -5, "MST": -7, "MDT": -6, "PST": -8, "PDT": -7, "AKST": -9, "AKDT": -8, "HST": -10}`
2. Apply offset before labeling as UTC: `pd.to_datetime(time_str) - pd.Timedelta(hours=offset)` then localize to UTC. **Sign convention:** CST = -6, so `time - (-6hr) = time + 6hr`. 10:00 CST → 16:00 UTC. Document this.
3. Drop rows where `Activity_StartTimeZone` is null or unrecognized — log the unrecognized values and counts so we know what we're losing. Do NOT silently drop.
4. Drop rows where `Activity_StartTime` is null (do NOT default to "12:00:00"). Also handle the case where the `Activity_StartTime` column is entirely absent (line 58 fallback).
5. **Validation step (Okafor):** After conversion, verify match rates DECREASE (samples that were matching wrong data 5-8 hours offset will now fail the ±15 min window). If match rates increase, something is wrong.
6. **Sanity check (Okafor):** Verify no converted timestamps fall outside the site's continuous data range by more than expected — catches the "EST year-round ignoring DST" problem.
**Test:** Add tests for CST→UTC, EST→UTC, missing timezone → dropped, missing time → dropped, column-absent → dropped

### [DONE] Fix 2: Early Stopping on Test Set (Chen, Rivera, Okafor, Patel — all four)
**File:** `scripts/train_baseline.py` line 396
**Problem:** `model.fit(X_train, y_train, eval_set=(X_test, y_test), early_stopping_rounds=50)` — the held-out test site is used to decide when to stop training. The model peeks at the test distribution. Inflates R² by ~0.02-0.05.
**Fix:** Split training sites into 85% train / 15% validation (Chen: 10% gives only 5-6 sites, too noisy; 15% = 8-9 sites for more stable stopping). Use `GroupShuffleSplit` with site-level groups for the validation split.
```python
from sklearn.model_selection import GroupShuffleSplit
gss = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=RANDOM_SEED)
train_idx, val_idx = next(gss.split(X_train, y_train, groups=train_site_ids))
model.fit(X_train_sub, y_train_sub, eval_set=(X_val, y_val), early_stopping_rounds=50)
```
**Quantile model (line ~505):** Currently has NO early stopping (fixed 500 iterations). Add early stopping with the same validation split. (Patel: not a blocker if kept at 500, but consistency is better.)
**Note (Chen):** X_train is a numpy array at this point (line 370). Use `np.where(np.isnan(...), median, ...)` for imputation, not `fillna`.

### [DONE] Fix 3 + Fix 5 Combined: Hydrograph & Antecedent Features from Continuous Record (all four)
**Files:** `src/murkml/data/features.py` lines 43-44, 49-67; `scripts/assemble_dataset.py` line 242
**Problem:** `df[discharge_col].diff()` computes difference between consecutive rows in the concatenated multi-site DataFrame — garbage across sites AND within a single site (grab samples are days/weeks apart). `rising_limb` inherits this. Antecedent features are stubs.
**Chen clarification:** The groupby-only approach will NOT fix this — even within a single site, grab samples are too sparse for `diff()` to approximate dQ/dt. MUST use continuous discharge record.
**Fix:** Build one shared function that loads continuous discharge for each site during assembly and computes ALL discharge-derived features at once (Rivera: avoid loading the same data twice):

**Hydrograph position features (Fix 3):**
- `discharge_slope_2hr`: linear slope of Q over ±2hr window from continuous record
- `rising_limb`: binary from discharge_slope_2hr > 0
- `time_since_Q_peak`: hours since most recent local Q maximum (Rivera: rising_limb alone doesn't tell you WHERE on the limb you are)
- `Q_ratio_recent_peak`: current Q / peak Q in the prior 48 hours

**Antecedent features (Fix 5 — Rivera: needs precipitation too):**
- `Q_7day_mean`: mean discharge over prior 7 days
- `Q_30day_mean`: mean discharge over prior 30 days
- `Q_ratio_7d`: current Q / Q_7day_mean
- `days_since_high_Q`: days since Q exceeded the site's Q75 threshold (Rivera: use Q75 consistently, not Q90; compute from full period of record)

**Deferred to later version (Rivera recommends but not MVP-blocking):**
- Antecedent precipitation/dry days from PRISM or GridMET (best first-flush predictor per literature, but requires external data source)
- Season × antecedent interaction features

**Also:** Ensure `add_cross_sensor_features()` doesn't produce garbage across site boundaries (Rivera: turb_Q_ratio will also be wrong if discharge magnitudes differ). Add `groupby(site_id)` to all feature functions that use row-ordering operations.

### [DONE] Fix 4: Median Imputation Before CV Split (Chen, Okafor, Patel)
**File:** `scripts/train_baseline.py` lines 366-368, 283-285, 472-476
**Problem:** Missing values filled with global median (includes test site data) before the LOGO loop. Leaks test-site feature distributions into training.
**Fix:** Move imputation inside the CV loop. For each fold:
```python
train_median = X_train.median()
X_train = X_train.fillna(train_median)
X_test = X_test.fillna(train_median)  # use TRAINING median for test
```

---

## IMPORTANT FIXES (do after critical fixes, before re-running baselines) — MOSTLY DONE

### [DONE] Fix 5: Implement Antecedent Features (all four)
**File:** `src/murkml/data/features.py` lines 49-67
**Problem:** `add_antecedent_features()` is a stub that returns input unchanged. These are the features domain experts say matter most (7-day/30-day cumulative discharge, days since high flow).
**Fix:** For each sample, load the site's continuous discharge data for the 30 days prior. Compute:
- `Q_7day_mean`: mean discharge over prior 7 days
- `Q_30day_mean`: mean discharge over prior 30 days
- `Q_ratio_7d`: current Q / Q_7day_mean (is this event above or below recent average?)
- `days_since_high_Q`: days since Q exceeded the 90th percentile for that site
**Requires:** Access to continuous discharge data during assembly. The data exists in `data/continuous/{site}/00060/`.

### [DONE] Fix 6: Tighten Alignment Window + Drop Bad Timestamps
**Files:** `scripts/assemble_dataset.py` line 145, lines 58-59
**Problems:**
- Alignment window relaxed to ±30 min (should be ±15 min for turbidity-SSC)
- Missing sample times defaulted to "12:00:00" (should be dropped)
**Fix:**
- Change `max_gap=pd.Timedelta(minutes=15)`
- Replace `time_str.fillna("12:00:00")` with dropping rows where time is null
- Accept the data loss — bad timestamps = bad training pairs

### [DONE] Fix 7: Make All Baselines Use Same CV Protocol (Patel)
**File:** `scripts/train_baseline.py`
**Problem:** Per-site OLS uses temporal split within each site. CatBoost uses LOGO. Comparing R² across different CV protocols is apples-to-oranges.
**Fix:** Add LOGO versions of Global OLS and Multi-feature Linear. Keep per-site OLS as the "ceiling" with clear labeling. The comparison table should separate:
- **Cross-site models (LOGO):** Global OLS, Multi-feature Linear, CatBoost
- **Per-site ceiling (temporal split):** Per-site OLS (labeled as "upper bound — requires per-site calibration")

### [DONE] Fix 8: Value-Range QC (Rivera — revised per plan review)
**File:** `src/murkml/data/qc.py`
**Problem:** No check for physically impossible values. Turbidity of -5? SSC of 500,000?
**Fix:** Add bounds checking (Rivera corrections applied):
- Turbidity FNU: 0 to **10,000** (Rivera: newer Hach TU5400 goes to 10K; add WARNING flag at >4000 for sensor-dependent saturation zone). **Flag turbidity == 0 exactly** as suspect (natural streams rarely read 0.0 FNU — usually sensor malfunction or ice).
- SSC: 0 to 200,000 mg/L (hard cap); **WARNING flag at >20,000** for manual inspection
- Discharge: ≥ 0 (check if any sites are tidal-influenced first)
- Temperature: -2 to 50 °C
- DO: **0** to 25 mg/L (Rivera: do NOT exclude DO=0 — anoxic conditions are real). Flag pH < 3 or > 11 for inspection.
- pH: 0 to 14
- Conductance: 0 to 100,000 µS/cm; flag > 10,000 for non-brine sites
Log and count excluded/flagged records. **Run BEFORE alignment** (Rivera: impossible values shouldn't participate in window feature computation).

### [DONE] Fix 9: Fix Smearing Factor for Overall CV Metrics (Chen, Rivera, Patel — ALL FOUR flagged revision)
**File:** `scripts/train_baseline.py` line 426
**Problem:** `smearing_factor=1.0` for pooled LOGO metrics = no bias correction in natural space.
**REVISION (all four reviewers):** Original fix proposed using TEST residuals — WRONG. Duan's smearing estimator must use TRAINING residuals (the residuals of the model on data it was trained on). Using test residuals peeks at test values to correct predictions.
**Correct fix:** Collect per-fold TRAINING residuals during the CV loop, compute pooled smearing from those:
```python
all_train_resids = []  # collect during CV loop
for fold_idx, (train_idx, test_idx) in enumerate(logo.split(X, y, groups)):
    ...
    train_resid = y_train - model.predict(X_train)
    all_train_resids.append(train_resid)
    ...
pooled_smearing = np.mean(np.exp(np.concatenate(all_train_resids)))
```
Alternative (simpler): average the per-fold smearing factors: `pooled_smearing = np.mean(per_fold_smearing_factors)`

### [DONE] Fix 10: QC Buffer Periods (Rivera, Okafor, Patel)
**File:** `src/murkml/data/qc.py` lines 86-89
**Problem:** 48-hour post-Ice and 4-hour post-Mnt buffers defined but never implemented.
**Fix:** Extend exclusion window forward by buffer duration after each Ice/Mnt episode.
**Rivera critical ordering detail:** Buffer logic must run on the RAW data BEFORE qualifier-based removal. If you first remove Ice-flagged records (line 82), you lose the information about when Ice ENDED. Implementation must:
1. Identify Ice/Mnt flag boundaries on raw data (before filtering)
2. Find the END of each Ice/Mnt episode
3. Create the buffer exclusion mask
4. THEN apply qualifier + buffer exclusion together

### [DONE] Fix 11: Non-Detect and Zero Handling (Okafor — revised per plan review)
**File:** `scripts/assemble_dataset.py` lines 72-81
**Problems:**
- Non-detects handled inconsistently (lab-dependent)
- SSC=0 dropped despite log1p handling it fine
**Fix:**
- For rows with `ResultDetectionCondition == "Not Detected"`: set value to detection_limit / 2 (standard EPA/USGS practice for left-censored data)
- **Okafor revision:** Detection limit may be in `Result_Measure` OR in a separate column `DetectionQuantitationLimitMeasure_MeasureValue`. Check both; use whichever is available. If NEITHER has a detection limit for a non-detect row, set to a conservative 1 mg/L (typical SSC gravimetric MDL) and log a warning.
- Change `ssc_value > 0` to `ssc_value >= 0` — log1p(0) = 0 is valid
- Add a `is_nondetect` boolean column so the model can learn from it

### [DONE] Fix 12: Secondary Sensor Time Coordination (Okafor)
**File:** `scripts/assemble_dataset.py` lines 180-193
**Problem:** Each secondary sensor (conductance, DO, pH, temp, discharge) is independently matched to the sample time. Two sensors in the same row could be from readings 30+ minutes apart.
**Fix:** Use the PRIMARY turbidity match timestamp as the anchor. For secondary sensors, find the reading nearest to the TURBIDITY match time, not the grab sample time. This ensures all sensor readings in a row are from the same moment.

### [DONE] Fix 13: Reduce Collinear Turbidity Features (Chen)
**Problem:** 7 turbidity window features from the same 1hr signal. Dilutes feature importance and SHAP interpretability.
**Fix:** Keep `turbidity_instant`, `turbidity_slope_1hr`, `turbidity_std_1hr`. Drop `turbidity_mean_1hr`, `turbidity_min_1hr`, `turbidity_max_1hr`, `turbidity_range_1hr`. Run ablation to confirm no performance loss.

### [DONE] Fix 14: Add Catchment Attributes as Features
**File:** `scripts/train_baseline.py`, `data/site_attributes.parquet`
**Problem:** Model has no information about what kind of watershed each site is in. Can't distinguish mountain stream from agricultural plains river.
**Fix:** Join `site_attributes.parquet` (already downloaded: drainage area, elevation, HUC2 region) to the training data. Add as features:
- `log_drainage_area_km2` (log-transformed)
- `altitude_ft`
- `huc2` (as categorical — CatBoost handles this natively)
Do NOT add lat/lon (leakage in LOGO).

### Fix 15: Add Storm-Event Metrics (Rivera, Patel)
**File:** `scripts/train_baseline.py`
**Problem:** `storm_rmse` and `load_bias` are defined in metrics.py but never called. Storms are where 90% of sediment moves — this is the key evaluation.
**Fix:** After LOGO CV, stratify predictions by discharge percentile. Compute:
- RMSE for samples above Q90 (storms — matching existing `storm_rmse` function default)
- RMSE for samples above Q75 (elevated flow)
- RMSE for samples below Q25 (baseflow)
- Total load bias (sum of C×Q predicted vs observed)
- **Rivera addition:** Report NUMBER of storm samples per site. If a site has 200 samples but only 3 above Q75, that site's storm RMSE is meaningless. Report sample distribution across flow regimes alongside stratified metrics.

### Fix 16: Wildfire Disturbance Signal (Rivera, Kaleb — deferred per Patel)
**Problem:** Post-wildfire, turbidity-SSC relationships fundamentally change for 2-5 years. The model has no way to detect this. Idaho and Montana sites are at high risk.
**Patel recommendation:** Defer MTBS integration to a future version. Not needed for publication. Document as known limitation.
**Rivera ideal (future version):** Need burn fraction (not binary), burn severity, and years-since-fire as continuous variable. Binary flag is too coarse.
**v0.1.0 fix:** Document wildfire as a known limitation in the paper. Add a `fire_prone` boolean column to site catalog for ID, MT, CO, CA, OR sites based on manual lookup. Report whether fire-prone sites have worse model performance. Do NOT attempt MTBS API integration now.

### Fix 17: Provisional Data Strategy (Rivera)
**Problem:** Excluding ALL provisional data loses 1-3 years of recent data at active sites.
**Fix:** Include Provisional data but add a `is_provisional` boolean flag. Run models with and without provisional data. Report both. If performance is similar, include it.

### [DONE] Fix 18: Duplicate Sample Check (Chen)
**File:** `scripts/assemble_dataset.py`
**Problem:** No deduplication of discrete samples (same site, same time, same value).
**Fix:** Add `df.drop_duplicates(subset=["site_id", "datetime", "ssc_value"])` after loading discrete data.

### [DONE] Fix 19: Add Missing Tests for Critical Code Paths (Okafor)
**File:** `tests/`
**Problem:** No tests for timezone handling, non-detect handling, cross-site dQ/dt, or the full assembly pipeline.
**Fix:** Add tests for:
- Timezone conversion (CST→UTC, EST→UTC, missing timezone → dropped)
- Non-detect handling (detection limit / 2 substitution)
- dQ/dt not crossing site boundaries
- Full integration test: small synthetic dataset → assembly → verify output shape and values

---

## MINOR FIXES (do when convenient)

### Fix 20: KGE ddof (Okafor) — `metrics.py` line 35
Change `np.std(y_pred)` to `np.std(y_pred, ddof=1)` for sample std.

### Fix 21: Dead code in models/baseline.py (Chen, Patel)
Remove `src/murkml/models/baseline.py` divergent CatBoost config or sync it with train_baseline.py.

### [DONE] Fix 22: DO saturation formula (Rivera) — `features.py` line 88
Replace `14.6 - 0.4 * T` with Benson & Krause (1984) nonlinear formula. **Fixed 2026-03-24. The linear approximation had 27-65% error at common stream temperatures.** Turned out to be higher priority than originally assessed.

### Fix 23: Alignment performance (Okafor, Patel) — `align.py`
Replace O(N*M) brute-force with `pd.merge_asof()`. Same results, orders of magnitude faster.

### Fix 24: Cached empty DataFrames on transient errors (Okafor — revised) — `download_diverse.py`
**Okafor revision:** Distinguish `df is None` (ambiguous — could be error) from `len(df) == 0` (confirmed empty response). Only cache empty on `df is not None and len(df) == 0`. Do NOT cache on `df is None`. Once cached, the file is never retried.

### Fix 25: README quickstart shows non-existent API (Patel)
Either implement the promised `murkml.discover_sites()` etc., or replace quickstart with working code using current scripts.

### Fix 26: `"e"` qualifier exclusion (Rivera — revised per plan review)
**Rivera revision:** `"e"` (Estimated) DOES appear on Approved records. Critical distinction:
- **Exclude `"e"` on turbidity** — the primary predictor needs direct measurements
- **Keep `"e"` on discharge** — most high-flow readings are estimated from rating curves. Excluding them would eliminate the storm data we need most.
- Document this parameter-specific qualifier handling.

### Fix 27: Add confidence intervals to reported metrics (Patel)
Bootstrap or report IQR across the 57 LOGO folds. Show the distribution, not just the median.

### Fix 28: PICP aggregate analysis (Patel)
Compute overall 80% interval coverage. Report whether intervals are calibrated.

### Fix 29: Novelty framing (Patel)
Scope the claim correctly: "first open-source, pip-installable toolkit that automates cross-site WQ surrogate modeling from USGS data." NOT "first cross-site WQ prediction" (Zheng 2025, Guo 2018 exist). Emphasize the compiled dataset as an independent contribution.

---

## EXECUTION ORDER (revised per all four reviewers)

**Principle (Rivera, Okafor): Get the DATA right first, then fix the MODEL.**

**Round 1A — Data pipeline fixes:**
1. Fix 1 + Fix 6 together (timezone + null times + alignment window ±15 min) — they touch the same lines (Okafor)
2. Fix 8 (value-range QC) — run BEFORE alignment so impossible values don't corrupt window features (Rivera)
3. Fix 11 (non-detect/zero handling) — affects which rows are in the dataset (Okafor)
4. Fix 18 (dedup) — one-liner, affects sample counts (Patel)
5. Fix 3+5 combined (dQ/dt + antecedent features from continuous discharge) — share one data-loading function (Rivera, Chen)
6. Fix 10 (QC buffers) — must run on raw data before qualifier removal (Rivera)
7. **CHECKPOINT:** Re-assemble dataset. Log sample count change. Expect 20-40% sample loss from timezone fix (Chen). Verify match rates decreased (Okafor).
8. **Write tests alongside each fix** (Patel: don't defer Fix 19 to Round 3)

**Round 1B — Model evaluation fixes (after re-assembly):**
9. Fix 2 (early stopping — use 15% validation split from training sites)
10. Fix 4 (imputation inside CV loop — use training median only)
11. Fix 9 (smearing — use TRAINING residuals, not test)
12. Fix 13 (reduce collinear turbidity features) — moved here from Round 3 so SHAP is interpretable (Chen)
13. Re-run baselines → **honest numbers**

**Round 2 — Improve results:**
14. Fix 14 (catchment attributes as features)
15. Fix 7 (LOGO versions of all baselines for fair comparison)
16. Fix 15 (storm metrics + load bias + sample count per flow regime)
17. Fix 27 (confidence intervals — report median + IQR across folds)
18. Fix 28 (PICP aggregate)
19. **Hyperparameter search** (Chen: missing from original plan. Coarse grid: depth 4/6/8, learning_rate 0.03/0.05/0.1, l2_leaf_reg 1/3/10)
20. Re-run → publication-quality numbers

**Round 3 — Polish:**
21. Fix 12 (secondary sensor time coord — Patel: deprioritize, slow-changing sensors)
22. Fix 16 (wildfire — document as limitation, add fire_prone flag to catalog)
23. Fix 17 (provisional data — include with flag, compare with/without)
24. Fix 26 ("e" qualifier — keep on discharge, exclude on turbidity only)
25. Fixes 20-25, 29 (minor fixes)
26. Final re-run with all fixes

---

## VERIFICATION

After each round:
1. All 37+ existing tests still pass
2. New tests for each fix pass
3. Re-assemble dataset and log sample count change
4. Re-run baselines and compare to previous numbers
5. Check SHAP — are the top features physically sensible?
6. Spot-check 5 random samples: is the turbidity match time actually close to the grab sample time?

**Key files to modify:**
- `scripts/assemble_dataset.py` — timezone fix, non-detect handling, alignment window, dedup
- `src/murkml/data/features.py` — dQ/dt fix, antecedent features
- `src/murkml/data/qc.py` — value-range QC, buffer periods
- `scripts/train_baseline.py` — early stopping, imputation, LOGO baselines, storm metrics, catchment features
- `src/murkml/evaluate/metrics.py` — KGE ddof
- `tests/` — new tests for all critical fixes

---

## ALREADY COMPLETED (reference only, do not re-execute)

## Phase 0: Project Setup (Day 1)

1. Create `~/Documents/murkml/`, init git, BSD-3-Clause license
2. Register `murkml` on PyPI with placeholder
3. Get free USGS API token — set `API_USGS_PAT` env var (rate limit relief)
4. Package structure:
   ```
   murkml/
   ├── pyproject.toml           # hatchling backend, pinned deps
   ├── README.md
   ├── CLAUDE.md
   ├── LICENSE                  # BSD-3-Clause
   ├── CONTRIBUTING.md
   ├── CODE_OF_CONDUCT.md       # Contributor Covenant
   ├── CHANGELOG.md
   ├── src/murkml/
   │   ├── __init__.py
   │   ├── data/
   │   │   ├── __init__.py
   │   │   ├── fetch.py         # USGS data pulls + incremental caching
   │   │   ├── align.py         # Temporal alignment
   │   │   ├── qc.py            # QC flag filtering
   │   │   └── features.py      # Feature engineering
   │   ├── models/
   │   │   ├── __init__.py
   │   │   └── baseline.py      # CatBoost + quantile regression
   │   └── evaluate/
   │       ├── __init__.py
   │       └── metrics.py       # R², RMSE, KGE, bias, SHAP
   ├── notebooks/
   ├── paper/paper.md           # JOSS paper (start early)
   ├── data/                    # Cached data (gitignored)
   ├── tests/
   │   └── test_fetch.py
   └── .github/
       ├── workflows/ci.yml     # pytest on push — JOSS requires CI from start
       └── ISSUE_TEMPLATE/
           ├── bug_report.md
           └── feature_request.md
   ```
5. Core dependencies (keep light):
   ```
   dataretrieval>=1.1
   pandas>=2.0
   numpy>=1.24
   scikit-learn>=1.3
   matplotlib>=3.7
   pyarrow>=14.0
   ```
   Optional extras:
   ```
   [boost]  → catboost>=1.2      # 80-100MB wheel
   [explain] → shap>=0.42         # pulls numba/llvmlite
   [all]    → catboost, shap, jupyter
   ```
   Later (Phase 4): `keras>=3.0`, `tsai`, `optuna`, `torch>=2.0`
6. `.gitignore`: data/, .venv/, __pycache__/, *.pyc, wandb/, .env
7. Global random seed in config. Experiment log from Day 1.
8. GitHub Actions CI: `ruff check` + `pytest` on push

**Verify:** `pip install -e ".[all]"` works, `import murkml` succeeds, CI passes.

---

## Phase 1: Data Pipeline (Weeks 1-4)

**Goal:** ML-ready dataset of paired (continuous sensor → grab sample) data across 15-30 diverse sites.

**This is 60-70% of the project effort.** Budget 4 weeks.

### CRITICAL: API Changes in dataretrieval v1.1.2

The `nwis` module is **deprecated**. All plan references use the NEW `waterdata` module:

| Old (deprecated) | New (use this) |
|-------------------|----------------|
| `nwis.get_iv()` | `waterdata.get_continuous()` |
| `nwis.get_qwdata()` | `waterdata.get_samples()` |
| `nwis.what_sites()` | `waterdata.get_time_series_metadata()` |
| Site ID: `"06041000"` | Site ID: `"USGS-06041000"` |
| QC: `approval_status = "A"` | QC: `approval_status = "Approved"` |
| QC in `_cd` column | QC in separate `qualifier` column |

**Server limits:** 3-year max per call for continuous data. 10K records per page. Pagination can **silently swallow errors** (truncated data, no warning). Budget 28-37 hours download for full dataset. Use `ThreadPoolExecutor` with 3-5 threads.

### Week 1 Milestone: Feasibility Check
Run discovery on 5 Kansas WSC sites (best data: 20+ years, 200-500 paired samples, published benchmark R²). Pull data, attempt alignment, report:
- What % of grab samples have matching continuous sensor data after QC?
- What does the paired data look like?
- How long does the API take?

**Start with Kansas, not Idaho.** Kansas has the best-documented surrogate modeling program. Idaho rain-snow sites are harder → Phase 2 expansion.

### Step 1.1: Site Discovery

Use `waterdata.get_time_series_metadata(parameter_code="63680")` to find sites with continuous turbidity. Chunk by state to avoid timeouts. Cross-reference with `waterdata.get_samples()` to find sites with discrete SSC (80154).

**Cannot use `get_monitoring_locations()` for this** — it has no parameter filter.

**Site selection criteria:**
- ≥30 discrete SSC samples + ≥2 years continuous turbidity
- ≥4-5 distinct ecoregion/land-use combinations
- Include sites outside Midwest (CO, CA, ID, MD, PA for diversity)
- Document diversity: geology (karst, igneous, glacial till), land use (ag, forest, urban), climate (arid, humid, snow)

**Also pull published USGS regression equations** from NRTWQ methods pages — these are the benchmark to compare against.

**Output:** `data/site_catalog.parquet`

### Step 1.2: Data Fetching (`fetch.py`)

**Continuous data:** `waterdata.get_continuous()`
- 3-year max per call → loop in 3-year chunks
- **Write Parquet incrementally:** `data/continuous/{site_id}/{pcode}/{year}.parquet` — resume-safe, cacheable
- Build retry wrapper around `_walk_pages()` — the built-in pagination silently drops data on 429/timeout errors. Validate record count against expected count.
- Parameters: turbidity FNU (`63680`), conductance (`00095`), DO (`00300`), pH (`00400`), temp (`00010`), discharge (`00060`)
- Data comes back in **long format** — pivot to wide for multi-parameter features

**Discrete data:** `waterdata.get_samples()`
- **No pagination** — query one site at a time
- **SSC (80154) only for MVP.** Do NOT mix SSC and TSS (different methods, 25-50% divergence).
- **FNU (63680) only.** Do NOT mix FNU and NTU (diverge above ~400 units).
- **Pull activities data** (second API call: `get_samples(service="activities", profile="sampact")`) to get sampling method (EWI vs bank grab). Join by activity identifier. Flag or filter.
- **Exclude QC blanks, replicates, spike samples** from training.

**Non-detect handling:** `ResultDetectionCondition = "Not Detected"` means value column = detection limit, not zero. 10-30% of nutrient samples. For MVP (SSC), non-detects are rare but check.

**Everything stored as UTC.** New API returns UTC. Discrete samples may be inconsistent — verify.

### Step 1.3: QC Filtering (`qc.py`)

- Keep only `approval_status = "Approved"` (note: spelled out in new API, not `"A"`)
- Exclude qualifier: `Ice` + **48hr buffer after flag ends** (bottom ice releases sediment)
- Exclude: `Eqp`, `Bkw`, `***`, `--`
- Exclude: `Mnt` + **4hr buffer after** (freshly cleaned sensor = step discontinuity)
- Exclude: `e` (Estimated — not directly measured)
- **Keep** `Fld` (flood) — storm events are where ML adds the most value
- Log filter stats per site

### Step 1.4: Temporal Alignment (`align.py`)

**Primary match:** Nearest sensor reading within ±15 min of grab sample time T.
**Feature window:** ±1 hour.
**Antecedent:** 24hr, 7-day, 30-day.

For each grab sample, compute:
- **Instantaneous:** nearest 15-min sensor reading
- **Window (±1hr):** mean, min, max, std per sensor
- **Slopes:** linear regression of each sensor over ±1hr, ±6hr, ±24hr
- **Hydrograph position (all reviewers flagged this as critical):**
  - dQ/dt (discharge rate of change)
  - Time since last discharge peak
  - Q / Q_recent_peak ratio
  - Rising/falling limb indicator
- **Antecedent conditions:**
  - 7-day and 30-day cumulative discharge
  - Days since last Q > Q75 event
- **Cross-sensor features:**
  - Turbidity / discharge ratio (sediment source signal)
  - DO departure from saturation
  - Conductance × turbidity interaction (surface runoff dilution)
- **Seasonality:** sin/cos(day-of-year)
- Check for overlapping windows (storm campaign samples <2hr apart) — flag
- Check for rounded timestamps (:00 minute = imprecise)

### Step 1.5: Static Site Attributes

**Do NOT use raw lat/lon** (leakage in leave-one-site-out CV).

Use catchment attributes from:
- **HyRiver ecosystem** (`pynhd`, `pygeohydro`) — programmatic access to basin characteristics, land use, slope, climate, soils. Preferred over manual GAGES-II download.
- **NLDI** (via `dataretrieval.nldi`) — basin delineation, flowlines
- **StreamCat** (EPA REST API at `java.epa.gov/StreamCAT/metrics`) — ~600 metrics per catchment, query by COMID (get COMIDs from NLDI)

Key attributes: drainage area, % forest/ag/urban, dominant geology, mean annual precip, baseflow index, soil clay content, slope. **Normalize discharge by drainage area** for cross-site transfer.

Replace lat/lon with ecoregion or climate zone if geographic context needed.

### Step 1.6: Dataset Assembly

- Target: `log1p(SSC)` — handles zero/below-detection values
- Save as `data/processed/turbidity_ssc_paired.parquet`
- Notebook `01_data_exploration.ipynb`: distributions, turbidity vs SSC by site, site map, data availability heatmap

**Verify:**
- ≥15 sites, ≥500 total pairs, ≥4 ecoregions
- Notebook showing data makes physical sense

**Decision gate:** If <15 sites with ≥30 pairs each → expand Tier 2 search, or reduce scope to dataset paper.

---

## Phase 2: Baseline Models (Weeks 5-7)

**Success criteria (set BEFORE running):**
- Cross-site CatBoost median R² > 0.60 = publishable
- Matching published USGS per-site OLS R² at held-out sites = exceptional
- Useful predictions at sites with NO existing model = the real value proposition

### Step 2.1: Baselines
- **Per-site OLS:** log(SSC) = a × log(turbidity) + b (temporal splits within site, not random)
- **Published USGS regressions** from NRTWQ methods pages — direct comparison
- **Global OLS:** all sites pooled
- **Multi-feature linear regression:** all engineered features

### Step 2.2: Cross-Site CatBoost (`baseline.py`)
- All engineered features + static catchment attributes
- Target: `log1p(SSC)`
- Leave-one-site-out CV (`LeaveOneGroupOut`)
- **Quantile regression** (10th/50th/90th) for prediction intervals
- **Back-transformation:** Duan's smearing estimator. Report metrics in BOTH log and natural space.

### Step 2.3: Metrics (`metrics.py`)

| Metric | Why |
|--------|-----|
| R² (log + natural) | Standard |
| RMSE (log + natural) | Standard |
| **KGE** | Replacing NSE in hydrology — decomposes into correlation, variability, mean bias |
| Percent bias | Systematic over/under |
| **Storm-period RMSE** | Above Q10 discharge — where 90% of sediment load occurs |
| **Load bias** | % error in total load (C × Q) |
| **PICP** | 90% prediction interval coverage |
| Per-site distributions | Median, IQR, worst sites — don't hide behind means |

### Step 2.4: SHAP + Results Notebook
- `shap.TreeExplainer` — does model use catchment attributes or just global curve?
- Predicted vs observed by site, comparison table vs USGS published OLS
- Results stratified by ecoregion, data richness, event magnitude

### Decision gates (end of Phase 2):
1. CatBoost vs global OLS → if no improvement, investigate data/features
2. Cross-site vs per-site OLS → if worse at instrumented sites, reframe as "predictions where none existed"
3. **Lagged features test:** add turbidity at t-1hr, t-6hr, t-24hr to CatBoost. If it helps → temporal dynamics matter, LSTM justified. If not → skip LSTM.

---

## Phase 2.5: Analysis Pause (Week 8)

1 week to analyze Phase 2 residuals before expanding:
- Which sites fail and why?
- Data quality issues surfaced by the model?
- Geographic, geologic, or data-related failures?
- **Publishability check:** dataset + CatBoost baselines + SHAP = enough for paper? If yes, don't let Phase 3-4 delay Phase 5 release.

---

## Phase 3: Expand Parameters (Weeks 9-11)

Only after Phase 2 results are solid.

1. **Conductance → TDS** — near-linear, confirms pipeline generalizes
2. **Multi-sensor → Nitrate** (`00631`) — add sin/cos(DOY) for seasonal cycling. **Handle non-detects** (10-30% of nutrient samples — detection limit is NOT zero).
3. **Multi-sensor → Total Phosphorus** (`00665`)

**RegressorChain:** SSC prediction → feature for TP. Always compare chain vs direct.

---

## Phase 4: Sequence Models (Weeks 12-16) — STRETCH GOAL

Only if lagged features help CatBoost (Phase 2 gate).

### Self-supervised pretraining (required for LSTM to beat CatBoost at this data volume)
- Pretrain LSTM encoder on next-step sensor prediction (millions of continuous timesteps)
- Fine-tune on sparse grab samples

### LSTM: 12-hour lookback (48 timesteps), not 48hr
- Feed longer-term context as static features at final hidden state

### Physics loss (if LSTM shows promise):
- Non-negative concentrations
- DO: soft penalty above 150% saturation (supersaturation is real)
- SC-TDS proportionality (0.55-0.75 range)
- **Dropped:** turbidity-SSC monotonicity (grain size varies across sites)

### Multi-task: only if ≥1K samples per target, residual correlation confirmed

**Decision gate:** LSTM doesn't beat CatBoost → keep CatBoost. Ship it.

---

## Phase 5: Package and Release (Weeks 17-19)

### Practitioner quickstart (the selling point)
"You have a turbidity sensor. You have no lab data. Get a sediment estimate in 5 minutes using a pre-trained model."

### Deliverables
1. `pip install murkml` (PyPI, v0.1.0)
2. README: one-line description → badges → 5 bullet points → quickstart → installation
3. 2 Jupyter notebooks (Little Arkansas site demo + cross-site training)
4. Dataset on Zenodo with DOI
5. MkDocs site with `mkdocstrings` for API docs (deploy to GitHub Pages)
6. Automated tests passing in CI

### v0.1.0 scope (from OS Strategist — cut ruthlessly):
- Turbidity → SSC cross-site
- CatBoost + quantile regression
- SHAP explanations
- Comparison to linear regression
- Data pipeline with USGS API

NOT in 0.1.0: multi-task, LSTM, physics constraints, sensor QC, web UI

---

## Phase 6: Publication & Adoption (Months 5-8)

### Publication sequence:
1. **Dataset paper** (may be most impactful) — ESSD, Scientific Data, or Data-in-Brief
2. **JOSS software paper** — earliest Sept 2026 (requires 6-month dev history). Requirements: CI tests, docs, community guidelines, AI disclosure. Review: 1-3 months.
3. **Research paper** — scientific results. Environmental Modelling & Software, JAWRA, or Frontiers in Water.
4. Conference poster — AWRA or AGU

### Getting first 5 users:
1. Email `dataretrieval` maintainers at USGS — tool builds on theirs
2. Blog post with real results on LinkedIn (water science LinkedIn is active)
3. PR to [Python-Hydrology-Tools](https://github.com/raoulcollenteur/Python-Hydrology-Tools) (317+ stars)
4. Email 5-10 researchers: Zhi, Appling, Kratzert, NRTWQ team
5. Publish benchmark dataset independently on Zenodo/HuggingFace

### JOSS tips (from OS Strategist):
- Having Aaron Brooks as co-author (if he contributes) adds U of I affiliation → credibility
- Disclose AI (Claude Code) involvement honestly — not disqualifying
- Statement of Need is where most papers get sent back — our handoff doc has this covered

---

## Revenue Path

1. **Open-source library** → reputation (Month 4)
2. **Papers** → credibility (Month 5-8)
3. **Demonstrations** on real TMDL assessments / state monitoring gaps, blog posts, LinkedIn → visibility (Month 6-12)
4. **Freelance/consulting** for environmental firms → initial revenue (Month 12-18)
5. **EPA/WRF grant** → funded development (Month 18-24)
6. **SaaS** web interface → sustained revenue (Month 24-36)

The toolkit is your portfolio piece. "The person who knows ML for water quality" in a field where most practitioners use Excel.

---

## Decision Gates

| When | Gate | If NO |
|------|------|-------|
| Week 1 | Feasibility: ≥60% grab sample match rate at 5 Kansas sites? | Revise alignment or site targets |
| Week 4 | Data: ≥15 sites, ≥500 pairs, ≥4 ecoregions? | Expand search or pivot to dataset paper |
| Week 7 | Value: CatBoost beats global OLS? | Investigate data/features |
| Week 7 | Temporal: lagged features help CatBoost? | Skip LSTM entirely |
| Week 8 | Publishable: dataset + baselines + SHAP = paper? | Ship Phase 5 now, don't wait |
| Week 16 | LSTM beats CatBoost? | Keep CatBoost |

---

## Key Risks

| Risk | Mitigation |
|------|-----------|
| **Data pipeline consumes all time** | Hard 4-week cap. Min viable dataset (5 sites, 200 pairs) by Week 2. |
| **Cross-site ML doesn't beat per-site OLS** | Reframe: "predictions where none existed." Dataset is still a contribution. |
| **Graduation mid-2026** | Dataset + CatBoost must be publishable BEFORE graduation. Download papers now. |
| **API pagination silently drops data** | Build validation wrapper, check record counts. |
| **Survivorship bias** | First paper claims "cross-site among well-instrumented USGS sites." |
| **Turbidity sensor saturation** | Sensors cap 1-4K FNU. Include saturation flag, report storm metrics separately. |

## What NOT to Do

- Don't use deprecated `nwis` module — use `waterdata`
- Don't mix SSC and TSS without method flag
- Don't mix FNU and NTU turbidity
- Don't use raw lat/lon as features
- Don't enforce turbidity-SSC monotonicity globally
- Don't hard-cap DO at saturation
- Don't start LSTM before proving CatBoost + confirming temporal features help
- Don't build sensor QC, web UI, or multi-task before 0.1.0 ships
- Don't skip CI/tests — JOSS requires them

## USGS Parameter Codes

| Continuous Sensor (15-min) | Code | Discrete Lab | Code |
|---|---|---|---|
| Turbidity (FNU only) | **63680** | SSC (primary) | **80154** |
| Specific conductance | 00095 | TDS | 70300 |
| Dissolved oxygen | 00300 | Nitrate+nitrite | 00631 |
| pH | 00400 | Total phosphorus | 00665 |
| Temperature | 00010 | Orthophosphate | 00671 |
| Discharge | 00060 | Ammonia | 00608 |

## QC Flags (new API format)

| qualifier value | Action |
|-----------------|--------|
| `approval_status = "Approved"` | Keep |
| `approval_status = "Provisional"` | Exclude for MVP |
| `Ice` | Exclude + 48hr buffer |
| `Eqp` | Exclude |
| `Fld` (Flood) | **Keep** |
| `Mnt` | Exclude + 4hr buffer |
| `Bkw` | Exclude |
| `e` (Estimated) | Exclude |

## API Function Reference (dataretrieval v1.1.2+)

| Task | Function |
|------|----------|
| Find sites with parameter | `waterdata.get_time_series_metadata(parameter_code="63680")` |
| Continuous sensor data | `waterdata.get_continuous(site="USGS-07144100", parameter_code="63680", ...)` |
| Discrete grab samples | `waterdata.get_samples(monitoringLocationIdentifier="USGS-07144100", ...)` |
| Sampling method | `waterdata.get_samples(service="activities", profile="sampact", ...)` |
| Basin delineation | `dataretrieval.nldi` + `pynhd`/`pygeohydro` |
| Catchment attributes | StreamCat API or HyRiver ecosystem |
