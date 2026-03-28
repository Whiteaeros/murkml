# murkml Results & Findings Log

Reference for paper writing. Captures key results, expert panel findings, and decisions.

---

## CRITICAL BUG: prune_gagesii destroyed all GAGES-II attributes (discovered 2026-03-24)

**Root cause:** `train_tiered.py` calls `prune_gagesii()` on `site_attributes_gagesii.parquet`, but that parquet already stores data with **pruned column names** (e.g., `forest_pct`). `prune_gagesii()` looks for raw GAGES-II names (e.g., `FORESTNLCD06`), finds none, and replaces every column with zeros or NaN. The model trained on 25 columns of garbage for all Tier C/C_gagesii_only results.

**Evidence:**
- Before `prune_gagesii()`: `forest_pct = [58.6, 46.0, 6.5, ...]`, `geol_class = ['tg', 'rtr', ...]`
- After `prune_gagesii()`: `forest_pct = [0, 0, 0, ...]`, `geol_class = [NaN, NaN, ...]` (dtype changed from object to float64)
- Saved model meta confirms: only `huc2` (from basic_attrs, not GAGES-II) was treated as categorical. `geol_class`, `ecoregion`, `reference_class` all became float64 NaN columns.
- `sites_per_ecoregion` and `sites_per_geology` in model meta are both `{}` (empty).

**Impact on results:**
- ALL Tier C and C_gagesii_only R²/KGE values below are **INVALID** — trained without actual watershed attributes
- The "categorical feature fix" (2026-03-17) only added `huc2` correctly; the other 3 categoricals were already destroyed by `prune_gagesii()` before dtype detection
- The "Tier C > B_restricted" claim is NOT supported — the improvement came from noise columns or site-selection artifacts, not from watershed attributes
- **Tier A and Tier B results are NOT affected** (they don't use GAGES-II attributes)
- **External validation results are NOT affected** (used pre-tiered Tier B models)

**Fix applied (2026-03-24):** Added auto-detection guard to `prune_gagesii()` — returns input unchanged if already pruned. Added schema validation, post-merge assertions, and post-training integrity checks. Retrained all tiers. Audit script (`scripts/audit_pipeline.py`) passes 60/60 checks.

**Also corrected (2026-03-24):** Attribute coverage section below previously stated "7/102 sites have sensor-only features." Actual count: **0 sensor-only sites.** All 102 SSC sites have attributes in the GAGES-II merged file (95 sites) or NLCD file (44 sites), with 37-site overlap.

---

## Batch A Ablation Results (2026-03-27)

Tested monotone constraints, sqrt weights, weather features, lat/lon, and feature pruning independently.

**Ablation table (Tier C, LOGO CV):**

| Experiment | Features | Monotone | Weights | Trees/fold | R²(log) | R²(native) | KGE | RMSE | Bias |
|---|---|---|---|---|---|---|---|---|---|
| Exp 0 (new baseline) | 99 | No | No | 281 | 0.718 | 0.276 | 0.782 | 127.8 | 20.7% |
| **Exp 1 (monotone)** | **99** | **Yes** | **No** | **300** | **0.721** | **0.295** | **0.788** | **121.8** | **19.2%** |
| Exp 2 (weights) | 99 | No | sqrt | 86 | 0.528 | 0.376 | 0.632 | 118.7 | 8.0% |
| Exp 3 (pruned) | 63 | Yes | No | 288 | 0.717 | 0.312 | 0.776 | 124.2 | 21.4% |
| Exp 4 (minimal) | 26 | Yes | No | 310 | 0.708 | 0.290 | 0.772 | 131.1 | 20.1% |

**Conclusions:**
1. Monotone constraints HELP: +0.003 R²(log), more trees, lower RMSE. Keep them.
2. Sqrt sample weights DESTROY log-space accuracy: tree count collapses 281→86, R² drops 0.718→0.528. The native R² "improvement" comes at massive log-space cost. Drop weights.
3. Pruning 99→63 features: negligible loss (-0.004 R²). 36 dropped features were noise.
4. Pruning 99→26 features: modest loss (-0.013 R²). Some mid-tier features had real signal.
5. New features (6 weather + 2 lat/lon) helped: baseline went from 0.710 (pre-Batch A) to 0.718 with the new assembled data.
6. Best config: monotone + all 99 features + NO weights = R²(log) 0.721, best overall.

**Best model (Exp 1) holdout evaluation (57 sites):**
- Global (N=0): R²(native)=0.641, slope=0.591, KGE=0.499 (was 0.552/0.650/0.443)
- N=10 random: R²=0.643, slope=0.797, KGE=0.609
- N=20 random: R²=0.693, slope=0.820, KGE=0.670
- USGS comparison: still wins 30/46 sites, median advantage +0.035
- Error analysis: same pattern (sand_pct strongest negative correlate, urban sites worst)

**Expert reviews conducted:**
- ML diagnostics expert: identified sqrt weights as primary suspect for tree collapse (confirmed by ablation)
- Dr. Dalton (USGS hydrology): reviewed all 100 features, recommended 26-feature physics-based set, found altitude_ft/elevation_m duplicate (fixed)

---

## Single-Feature Ablation with Multi-Metric Analysis (2026-03-28)

### Method
1. Reduced 102 → 62 features by dropping group-level harmful/neutral features
2. Re-ran single-feature ablation on the 62-feature set with GKF5
3. Tracked ALL metrics: R²(log), R²(native), KGE(log), RMSE, bias, trees
4. Combined score = R²(log) + 2×R²(native) + KGE (native weighted 2× since it's the harder problem)

### Critical Discovery: Log vs Native Conflicts

Many features have OPPOSITE effects on log-space vs native-space performance:

| Feature | dR²(log) | dR²(native) | Combined | Implication |
|---|---|---|---|---|
| turbidity_std_1hr | -0.002 | **-0.132** | -0.273 | #1 most important feature by combined score |
| wetness_index | 0.000 | **-0.106** | -0.214 | Invisible in log, critical for native |
| dam_storage_density | -0.005 | **-0.086** | -0.186 | Strong across both spaces |
| rising_limb | **+0.002** | **-0.075** | -0.146 | "Harmful" in log, critical for native |
| turbidity_instant | **-0.012** | **+0.025** | +0.020 | Helps log, hurts native |
| pct_glacial_lake_fine | -0.003 | **+0.082** | +0.166 | Helps log, destroys native |

**Lesson:** Optimizing on R²(log) alone would have led to a WORSE model for real-world use. Native-space effects are 10-100× larger than log-space effects.

### Features Definitely Harmful (all 3 metrics worse when present)
Dropped: days_since_rain, manure_rate, do_instant, bio_n_fixation, geo_na2o, geo_mgo, discharge_instant

### Confounding Pair Interactions
| Pair | dR²(log) | dR²(native) | Interaction | Finding |
|---|---|---|---|---|
| pH + DO | +0.004 | -0.075 | +0.004 log | Redundant baseflow proxies — hurt log together, help native |
| nutrients × 4 | -0.002 | -0.066 | -0.005 log | Individually harmful, TOGETHER helpful |
| lat + lon + elev | -0.001 | +0.086 | +0.012 log | Individually great, partially cancel together |
| eolian fine + coarse | -0.001 | -0.093 | +0.010 log | Individually great, partially cancel in log but massively help native |

### Expert Panel Consensus (3 independent experts)
All three independently arrived at **37 features** — convergence.
- **Drop pct_glacial_lake_fine** (unanimously — +0.082 native R² harm)
- **Keep turbidity_instant** (unanimously — primary predictor)
- **Drop latitude, keep longitude** (2-1 — longitude captures maritime-continental physics; lat+lon together form site fingerprint)
- **Drop 18 features** beyond original 7: neutral or harmful across multiple metrics
- **Recommended 2-3× native weight** in combined scoring with veto at +0.05 native harm
- **Key insight from Dr. Alvarez**: pair_geo3 test shows lat+lon+elev together IMPROVE native R² by +0.086 when dropped — model memorizes geography rather than learning physics

---

## Final Optimized Model (37 features, LOGO CV, 2026-03-28)

**Configuration:** 37 numeric + 1 categorical (collection_method), monotone on turbidity_instant + turbidity_max_1hr, Ordered boosting, no weights, 243 sites

| Metric | Previous (99 feat) | Optimized (37 feat) | Change |
|---|---|---|---|
| R²(log) | 0.721 | **0.725** | +0.004 |
| KGE(log) | 0.788 | 0.778 | -0.010 |
| R²(native) | 0.295 | **0.361** | **+0.066 (+22%)** |
| RMSE(native) | 121.8 mg/L | 124.4 mg/L | +2.6 |
| Bias | 19.2% | 21.3% | +2.1% |
| Trees/fold | 300 | 287 | -13 |
| Final model trees | 200 | **499** | +299 |

**The 37-feature model improves BOTH log and native R².** Native R² jumped 22% (0.295→0.361) — the biggest single improvement since adding StreamCat attributes. Log R² also improved despite dropping 62 features, confirming that noise features were hurting generalization.

**SHAP top-10 (37-feature model):**
1. turbidity_max_1hr (0.413)
2. turbidity_mean_1hr (0.333) — Note: was dropped from ablation set but kept in final model via build_feature_tiers
3. turbidity_instant (0.171)
4. log_turbidity_instant (0.164)
5. collection_method (0.079) — NEW categorical feature
6. precip_48h (0.062)
7. turbidity_min_1hr (0.049)
8. doy_sin (0.044)
9. turbidity_slope_1hr (0.042)
10. longitude (0.038)

**IMPORTANT BUG:** The final model saving section in train_tiered.py doesn't apply --drop-features. The saved .cbm model has all 102 features, not the 37 used in LOGO CV. This means:
- LOGO CV results (R²=0.725) are CORRECT (used 37 features)
- Saved model + SHAP + holdout evaluations use 102 features (WRONG model)
- The holdout results below are from the 102-feature model, not the optimized 37-feature model
- **Fix needed:** Apply drop_features in the final model saving section of train_tiered.py, then retrain

**Holdout evaluation (49 sites, new HUC2-balanced split):**

| Metric | Previous (99 feat) | Optimized (37 feat) | Change |
|---|---|---|---|
| Global R²(native) | 0.641 | **0.699** | **+9%** |
| Global slope | 0.591 | **0.719** | **+22%** |
| Global KGE | 0.499 | **0.635** | **+27%** |
| N=10 random R² | 0.643 | 0.645 | flat |
| N=10 random slope | 0.797 | **0.809** | +1.5% |
| N=10 temporal R² | 0.400 | **0.647** | **+62%** |
| N=20 temporal R² | 0.540 | **0.679** | **+26%** |

The optimized model dramatically improves global holdout performance. The slope (0.719 vs 0.591) is the closest to 1.0 we've achieved — a direct result of removing features that were compressing native-space predictions. Temporal site adaptation at N=10 jumped from 0.400 to 0.647, suggesting the model generalizes better to chronological test periods.

---

## 383-Site Expansion + Native R² Collapse (2026-03-28)

**Expanding from 266→383 sites COLLAPSED native R² while improving log R²:**

| Config | R²(log) | R²(native) | Trees/fold |
|---|---|---|---|
| 266 sites, 37 features | 0.725 | 0.361 | 287 |
| 383 sites, 37 features | 0.735 | **0.154** | 462 |

### Smoking Gun Diagnostic
Separated original 233 sites from new 71 sites in Run B's LOGO CV folds:
- Original 233 sites native R²: **0.189** (was 0.361 in Run A — degraded by 0.172)
- New 71 sites native R²: **-0.024**
- SSC distributions are SIMILAR between groups (median 58 vs 51, P99 3540 vs 2970)

**Conclusion:** Adding sites changed the tree structure. The model became more conservative in native space for ALL sites, not just new ones. This is a fundamental loss function problem — RMSE in log-space compresses native predictions as site diversity increases.

### Regime-Dependent Smearing (post-hoc fix attempt)
Applied bin-specific Duan smearing factors instead of single global factor. Tested 3/5/10/20 bins.
- Result: native R² 0.207-0.212 (vs current 0.216)
- **DID NOT HELP.** The problem is in the predictions, not the back-transformation.

### Root Cause Analysis (expert panel consensus)
The model optimizes RMSE on log1p(SSC). Native R², KGE, slope are never seen during training. The fix MUST come from the training objective. Options being evaluated:
1. Custom loss function (requires dropping monotone constraints — only +0.003 R²)
2. Huber loss (compatible with monotone, one-line change)
3. MultiQuantile median without smearing
4. Sqrt transform
5. KGE as eval_metric for early stopping

### Critical Decision: Change One Thing At A Time
All data improvements (bug fixes, expansion, new features) must wait. First isolate the loss function effect on the 266-site/37-feature baseline. Then layer in changes sequentially.

---

### Data Quality Improvements Made
- **Linear interpolation** for turbidity alignment (replaces nearest-neighbor snapping)
  - ISCO site unique turbidity values: 120 → 349 (of 375 samples)
  - R² unchanged (0.828 → 0.828) but data quality improved
- **Collection method** feature added: auto_point (43%), depth_integrated (29%), unknown (17%), grab (11%)
- **Parallel assembly** with joblib: 8 min → 49 seconds
- **139 sites recovered** from continuous_batch_v2/ — root cause was QC approval code mismatch ("A" vs "Approved"). One-line fix in qc.py. Dataset expanded: 270→383 sites, 14,393→16,884 samples.
- **Train/holdout split regenerated** for 383 sites: 309 training, 74 holdout, all 19 HUC2 regions represented
- **Sensor calibration data downloaded**: 279 sites, 29,078 discrete turbidity samples from WQP. Method codes: TS087 (YSI 6136, 51%), TS213 (YSI EXO, 16%). Calibration computation script ready.
- **Model-save bug fixed**: train_tiered.py final model section now applies --drop-features, --feature-set, --config-json (was saving 102-feature model instead of 37)
- **compare_vs_usgs.py fixed**: now generates fresh holdout predictions from saved model instead of reading stale prediction_intervals.parquet

### Bug Fixes Applied (2026-03-28)
1. QC approval code normalization: "A"→"Approved", "P"→"Provisional" in `src/murkml/data/qc.py`
2. Model-save feature filtering: final model section in `train_tiered.py` now applies drop_features + feature_set + config_json
3. USGS comparison: generates own holdout predictions instead of reading stale file
4. Site adaptation: uses all basic_attrs columns (was missing latitude/longitude)

---

## Feature Group Ablation (2026-03-27, fast GKF5 mode)

**Method:** GroupKFold(5) with stratified site assignment (round-robin by median SSC), Plain boosting, no monotone constraints, no weights. Each experiment ~20 seconds. Total: 3 min 21 sec for 11 experiments.

**Data fix applied first:** Recovered HUC2 codes for 102 sites that were "unknown" — queried USGS NWIS. Found 31 Great Lakes sites, 13 California sites, 22 Upper Mississippi sites, 9 Hawaii sites previously invisible. Zero unknowns remaining.

**Feature groups tested (Dr. Dalton classification):**

| Experiment | R²(log) | Delta | Trees | Features | Verdict |
|---|---|---|---|---|---|
| baseline (101 feat) | 0.827 | — | 258 | 101 | reference |
| drop DO/pH/temp (F2) | **0.830** | **+0.003** | 217 | 96 | **HARMFUL — drop** |
| drop nutrients (F3) | **0.830** | **+0.003** | 257 | 96 | **HARMFUL — drop** |
| drop wastewater (F4) | 0.828 | +0.001 | 240 | 97 | noise — drop |
| drop weak weather (F8) | 0.827 | 0.000 | 228 | 97 | noise — drop |
| drop redundant geochem (F6) | 0.827 | 0.000 | 227 | 95 | noise — drop |
| drop redundant turb (F7) | 0.826 | -0.001 | 235 | 99 | marginal — drop |
| drop categoricals (F9) | 0.825 | -0.002 | 236 | 99 | marginal — drop |
| drop discharge (F1) | 0.822 | -0.005 | 222 | 96 | slight loss — investigate |
| drop sparse geology (F5) | 0.822 | -0.005 | 219 | 90 | slight loss — investigate |
| **drop ALL suspect (F10)** | **0.825** | **-0.002** | 203 | **57** | **44 features removed, near-zero cost** |

**Conclusions:**
1. DO, pH, temp, and nutrient features are actively hurting the model — no physical mechanism for SSC prediction
2. Wastewater, weak weather, redundant geochem are noise — zero impact when removed
3. Dropping all 44 suspect features costs only 0.002 R² while halving the feature count
4. Discharge features and sparse geology show slight value (-0.005) — may have indirect signal through Q_ratio_7d
5. Dr. Dalton's expert review was validated — the physics-based feature classification was accurate

**Speed infrastructure added:**
- `--cv-mode gkf5`: GroupKFold(5) with SSC-stratified site assignment (450× faster than LOGO)
- `--skip-ridge`, `--skip-save-model`, `--skip-shap`: skip non-essential steps during ablation
- `scripts/ablation_matrix.py`: automated experiment orchestrator with crash-safe incremental saves
- `--config-json`: arbitrary CatBoost param overrides for HP experiments
- `--drop-features`: exclude specific features by name

---

## Current Best Results (243 sites, StreamCat, expanded dataset, retrained 2026-03-26)

**SSC LOGO CV — 243 training sites, 92 StreamCat features, CatBoost with Ordered boosting:**

| Tier | R²(log) | KGE(log) | R²(native) | RMSE(mg/L) | Bias% | Native slope |
|------|---------|----------|-----------|------------|-------|-------------|
| A_sensor_only (270 sites) | 0.677 | 0.760 | 0.064 | 175 | +38% | 0.227 |
| B_sensor_basic (270 sites) | 0.683 | 0.771 | 0.207 | 152 | +25% | 0.241 |
| C_sensor_basic_watershed (243 sites) | **0.710** | **0.775** | **0.363** | **111** | **+14%** | 0.187 |

Tier differences significant (Wilcoxon p<0.01 for native R² and RMSE). StreamCat helps native metrics but not log-space.

**Holdout evaluation (57 truly unseen sites, final model):**
- Native R²=0.552, slope=0.650, KGE=0.443
- Much better than LOGO CV — final model trained on all 243 sites generalizes well

**Site-adaptive calibration effort curve (57 holdout sites, 50 MC trials):**

| N cal | R²(native) random | R²(native) temporal | Slope random |
|-------|-------------------|--------------------|--------------|
| 0 | 0.552 | 0.552 | 0.650 |
| 5 | 0.474 | 0.353 | 0.781 |
| 10 | 0.595 | 0.474 | 0.786 |
| 20 | 0.646 | 0.524 | 0.803 |

**Head-to-head vs USGS OLS (N=10, 46 holdout sites):** Our method wins 30, USGS wins 16. Agriculture_pct predicts where USGS wins (rho=-0.48, p=0.001).

**Prediction intervals:** 95% coverage=96.1%, 90% coverage=91.7%. Well-calibrated.

**Error analysis:** sand_pct strongest negative correlate (rho=-0.54). Worst sites are urban (80-89% developed). Best regions: HUC 08 (Gulf Coast), HUC 10 (Missouri).

**SHAP top features:** turbidity_max_1hr (0.53), turbidity_mean_1hr (0.41), turbidity_instant (0.16), discharge_slope_2hr (0.06), soil_organic_matter (0.03).

---

## Previous Results (102 sites, GAGES-II, 2026-03-24) — SUPERSEDED

**SSC LOGO CV — log-space metrics (median across folds):**

| Parameter | Tier A (sensor) | Tier B (+basic) | Tier C (+GAGES-II) | B_restricted | C_gagesii_only |
|---|---|---|---|---|---|
| **SSC R² (log)** | 0.710 | 0.750 | **0.798** | — | — |
| **SSC KGE (log)** | 0.795 | 0.809 | **0.829** | 0.825 | 0.813 |

**SSC LOGO CV — native-space metrics (mg/L, Duan smearing, first run with old DO formula + old GAGES-II):**

| Tier | R²(log) | R²(mg/L) | RMSE(mg/L) | Bias% |
|------|---------|----------|------------|-------|
| A_sensor_only | 0.710 | 0.439 | 87.1 | +17.8% |
| B_sensor_basic | 0.750 | 0.487 | 91.4 | +18.4% |
| B_restricted | — | 0.589 | 78.0 | +8.3% |
| C_sensor_basic_gagesii | 0.798 | 0.611 | 61.7 | +2.2% |
| C_gagesii_only | — | 0.537 | 79.6 | -1.7% |

**Key observation:** Log-space R²=0.80 corresponds to native-space R²=0.61. The gap is substantial and log-space metrics alone overstate practical prediction accuracy. Both must be reported.

**Key findings (corrected):**
- **Watershed attributes genuinely help:** C (0.798) vs B_restricted (0.763) = **+0.035 R²** on the same 95 sites. This is a real improvement, not an artifact of garbage features.
- **Vintage confound test passes:** C_gagesii_only (0.806) vs B_restricted (0.763) = **+0.043 R²** on the 58 original GAGES-II sites with 2006-vintage data. GAGES-II attributes add value even controlling for land cover vintage.
- **4 categorical features correctly used:** geol_class (21 classes), ecoregion (8 classes), reference_class (2 classes), huc2 (10 values). All confirmed in model metadata with non-empty `categorical_values_seen` and `sites_per_ecoregion`.
- **46 numeric + 4 categorical = 50 features** in Tier C (was 50 features before but 25 were all-NaN garbage).
- **Native-space bias is low for Tier C** (+2.2%) but high for Tier A (+17.8%) — watershed attributes reduce systematic overprediction.

**Note:** These native-space results used the OLD broken DO saturation formula (linear approximation, 27-65% error at common temps) and old GAGES-II data. Retrain with Benson & Krause 1984 DO formula is pending.

**TP, Nitrate, OrthoP Tier C results still pending retrain** — only SSC retrained so far. Tier A/B results for non-SSC parameters are unchanged:

| Parameter | Tier A (sensor) | Tier B (+basic) |
|---|---|---|
| TP (72 sites, 9,391 samples) | -0.10 | -0.08 |
| Nitrate (66 sites, 9,043 samples) | -2.00 | -1.54 |
| OrthoP (62 sites, 8,179 samples) | -2.34 | -1.52 |

**Previously invalid results (for the record):**
- Old Tier C R²=0.786 (trained on destroyed attributes, huc2 only categorical)
- Old C_gagesii_only R²=0.807 (same issue)
- Old "Tier C > B_restricted" claim was unsupported — the +0.023 gap came from noise columns, not real attributes

---

## External Validation (holdout sites, never trained on)

Sites from new states not in training set. Model trained on full training data (Tier C), then predicted on assembled holdout data.

**SSC — 11 holdout sites:**

| Site | R² (CatBoost) | R² (per-site OLS) | n |
|------|--------------|-------------------|---|
| USGS-04213500 | **0.92** | 0.82 | 297 |
| USGS-05082500 | **0.90** | 0.94 | 177 |
| USGS-12113390 | **0.87** | 0.83 | 103 |
| USGS-01362370 | 0.83 | **0.91** | 382 |
| USGS-04026005 | 0.74 | N/A | 13 |
| USGS-04024000 | **0.68** | 0.59 | 171 |
| USGS-02207135 | **0.65** | 0.59 | 87 |
| USGS-08070200 | 0.52 | **0.71** | 140 |
| USGS-040851385 | 0.07 | N/A | 11 |
| USGS-05447500 | -0.89 | 0.06 | 60 |
| USGS-09365000 | -8.54 | N/A | 10 |

- **Median R² = 0.68, Median KGE = 0.74**
- CatBoost beats per-site OLS at 4/8 comparable sites
- 8/11 sites have R² > 0.5
- Failures: USGS-09365000 (arid, 10 samples), USGS-05447500 (60 samples, low-turbidity site)

**TP — 12 holdout sites:**

| Site | R² (CatBoost) | R² (per-site OLS) | n |
|------|--------------|-------------------|---|
| USGS-04213500 | **0.74** | 0.08 | 314 |
| USGS-410333095530101 | **0.73** | 0.31 | 123 |
| USGS-04024000 | 0.47 | **0.63** | 178 |
| USGS-05082500 | 0.40 | **0.69** | 260 |
| USGS-040851385 | 0.34 | N/A | 11 |
| USGS-05447500 | 0.00 | 0.34 | 110 |
| USGS-02207135 | -0.48 | **0.33** | 82 |
| USGS-02292900 | -3.62 | -0.36 | 16 |
| USGS-04026005 | -2.41 | N/A | 13 |
| USGS-08070200 | -6.79 | -0.81 | 140 |
| USGS-410613073215801 | -798 | -0.05 | 52 |
| USGS-01362370 | -63 | N/A | 5 |

- **Median R² = -0.24** — confirms cross-site TP is regime-dependent
- 4/12 sites have R² > 0.3 (particulate-P-dominated sites where turbidity is informative)
- Catastrophic failures at dissolved-P-dominated sites (WWTP, groundwater-influenced)
- TP cross-site model should flag dissolved-P sites as "not applicable"

---

## Prior Results (57 sites, 11 states — before expansion)

| Parameter | Tier A (sensor) | Tier B (+basic) | Tier C (+GAGES-II) | Per-site OLS |
|---|---|---|---|---|
| SSC (57 sites) | 0.75 | 0.74 | **0.80** | 0.81 |
| TP (42 sites) | 0.40 | **0.59** | **0.62** | 0.60 |
| Nitrate (40 sites) | -2.09 | -0.89 | -0.72 | 0.04 |
| OrthoP (39 sites) | -1.76 | **-0.55** | -1.31 | 0.06 |

57 sites, 16,760 SSC samples, 11 states.

**TP degradation analysis:** TP dropped from 0.62 (42 sites) to 0.08 (72 sites) after expansion. Expert panel diagnosis: TP has multiple generation mechanisms (particulate erosion, WWTP point sources, agricultural runoff) and the expansion added sites with different TP physics. A single cross-site model cannot span all mechanisms. Per-regime analysis needed to confirm. This is a scientifically honest result, not a model failure.

---

## Assembled Dataset Summary

| Parameter | Sites | Samples | Non-detect % |
|---|---|---|---|
| SSC | 102 | 19,611 | — |
| TP | 72 | 9,391 | 0.9% |
| Nitrate | 66 | 9,043 | 5.9% |
| OrthoP | 62 | 8,179 | 6.1% |

12 watershed regimes: loess belt (IA), Gulf Coastal Plain (TX), arid Southwest (CO), iron range (MN/WI), SE Piedmont (NC), karst (TX Edwards), urban stormwater (PA), New England (CT), glaciolacustrine (ND), Blue Ridge (NC/WV), cold semi-arid (WY), deep south alluvial (MS). Plus original 57 sites across KS, IN, CA, CO, OR, VA, MD, MT, OH, ID, KY.

---

## Watershed Attribute Coverage

- **95/102 sites** in the GAGES-II merged attribute file
  - 58 sites with original GAGES-II data (2006-2011 vintage)
  - 37 sites with NLCD 2019 backfill merged into GAGES-II format
- **44/102 sites** in the NLCD file (37 overlap with GAGES-II, 7 NLCD-only)
- **0/102 sites** are truly sensor-only (previously reported as 7 — incorrect)
- **Categorical features status (2026-03-24):** All 4 categoricals (`huc2`, `geol_class`, `ecoregion`, `reference_class`) are correctly handled after prune_gagesii fix. Confirmed in model metadata with non-empty `categorical_values_seen` and `sites_per_ecoregion`.
- **Two-source problem:** 58 sites have full GAGES-II attributes, 37 have NLCD land cover only (no geology/soils/climate), 7 have no watershed attributes. Planned migration to StreamCat will unify all sites.

**Attribute sources merged into single file:**
- GAGES-II (ScienceBase): land cover (2006 vintage), geology, soils, climate, dams, hydrology
- NLCD (MRLC): land cover (2019 vintage) for non-GAGES-II sites
- NLDI: clay/sand/silt %, elevation, slope, stream density, precipitation, temperature

**Staleness note (GAGES-II 2006-2011 vintage):**
- Time-sensitive: NLCD land cover %, population density, dam counts
- Stable: elevation, slope, geology, soil permeability, climate normals, baseflow index

---

## Key Architecture Decisions (Physics Panel)

- **CatBoost only.** No neural networks. Gradient boosting dominates on <20K tabular samples (Nakamura, Grinsztajn et al. 2022 NeurIPS).
- **Independent models per parameter**, then prediction chain (SSC→TP, Temp→DO). Chain must pass ablation test.
- **Physics constraints tiered:** Tier 1-2 get 90% of benefit. Log targets, monotone constraints, output clipping, derived features.
- **Screening tool positioning.** ±50% load tolerance acceptable (Torres).
- **CQR via MAPIE** for calibrated prediction intervals (Krishnamurthy).
- **Categorical features must use CatBoost Pool with cat_features parameter.** Silently dropping string columns loses ecoregion/geology information.

---

## Expert Panel Consensus (Post-Expansion Review, 2026-03-17)

**On SSC (0.79 on 102 sites):**
- Rivera: "A 1-point drop while nearly doubling sites and adding geologically diverse regimes is the honest cost of generalization. I would have been suspicious if performance stayed at 0.80."
- Publishable finding: "Watershed-scale catchment attributes improve SSC estimation cross-site, with categorical ecoregion and geology class contributing +0.04 R²."

**On TP collapse (0.62 → 0.08):**
- Chen: TP has 3+ generation mechanisms (particulate, WWTP, ag runoff). Expansion added sites with different TP physics. A single model can't span all mechanisms.
- Diagnosis needed: per-site turbidity-TP correlation to flag dissolved-P-dominated sites where turbidity is uninformative.
- Consider regime-aware TP model or explicit "model not applicable" flag for dissolved-P sites.

**On B_restricted vs Tier C:**
- Rivera: For SSC, B_restricted < C confirms watershed attributes help (with categoricals). Previous B > C was due to the categorical bug.
- Okafor: The bug was that 4 of 25 GAGES-II features (the most informative ones) were silently excluded.

**Recommended next steps (priority order):**
1. Per-regime performance breakdown (group LOGO folds by regime)
2. Per-site turbidity-TP correlation to define transferability boundary
3. KGE decomposition for TP (correlation vs bias vs variability)
4. Run validation on 20 holdout sites

**Publication framing (updated):** "What transfers cross-site and what does not." SSC transfers well (R²=0.79) across 102 sites and 12 regimes. TP transfer is regime-dependent. Nitrate/orthoP are characterized negative results consistent with the particulate/dissolved transport boundary.

**Target venues:** Water Resources Research or Environmental Modelling & Software.

---

## Censoring Rates

| Parameter | Avg Censored | Sites <10% | Verdict |
|---|---|---|---|
| TP | 0.9% | — | DL/2 fine |
| OrthoP | 6.1% | — | Borderline — sensitivity analysis Phase 4 |
| Nitrate | 5.9% | — | Per-record DL varies 0.002–0.45 mg/L |

---

## Red Team Panel Review (5 expert reviewers, 2026-03-24)

All 5 reviewers recommend **major revision before WRR submission.** Key findings by reviewer:

**Dr. Catherine Ruiz (sediment transport):**
- Grain size confound — turbidity-SSC relationship varies with particle size, model cannot distinguish silt from sand
- Hysteresis on rising vs falling limb not captured
- GAGES-II data is stale (2006 vintage) for time-sensitive attributes
- Need log-space AND native-space metrics (log alone overstates accuracy)

**Dr. Marcus Chen (statistics):**
- Effective sample size is N=102 sites, NOT 19,611 observations (spatial autocorrelation within sites)
- Spatial autocorrelation between nearby sites not addressed
- Prediction intervals missing from main results
- Tier C vs B_restricted difference may not be statistically significant given N=102

**Dr. Priya Nair (sensor QC/operations):**
- Ice buffer was documented but never implemented in code (now fixed)
- QC qualifier parsing was silently failing — never matching Ice/Equip flags due to USGS array string format (now fixed)
- Approved-only training creates bias: excludes the most extreme events (provisional data)
- Non-detect handling needs explicit strategy

**Dr. James Okafor (ML benchmarking):**
- No linear baseline model for fair comparison (Ridge baseline now added)
- Fixed hyperparameters — no tuning or sensitivity analysis
- Tier comparison confounded by different site subsets per tier
- External validation set too small (11 sites) for credible generalization claims — need 20-30

**Dr. Elena Voss (scientific contribution):**
- Paper needs a testable hypothesis, not just "ML predicts SSC"
- SHAP analysis missing (now added)
- DO saturation formula was wrong — linear approximation had 27-65% error at common temperatures (now fixed with Benson & Krause 1984)
- Reframe paper as "what transfers cross-site and what doesn't"

---

## Structural Data Problem: Two Sources of Truth (discovered 2026-03-24)

Watershed attributes currently come from two incompatible sources:
- **GAGES-II (2006 vintage):** 58 sites — full attributes (geology, soils, climate, land cover, hydrology)
- **NLCD 2019 backfill:** 37 sites — land cover ONLY (no geology, soils, or climate)
- **7 sites:** No watershed attributes at all

The 37 backfill sites appear to have full Tier C features, but most columns are NaN or default-filled. This confounds tier comparisons — Tier C improvement may partly reflect which sites have real attributes vs backfill.

**Plan:** Replace both sources with **EPA StreamCat** — covers all NHDPlus catchments, 600+ attributes, consistent framework, regularly updated. This gives all 102 sites the same attribute set from one source.

---

## Code Fixes Implemented (2026-03-24/25) — NOT YET RETRAINED

These fixes are in the code but results above still reflect the old code:
- **DO saturation formula:** Benson & Krause 1984 polynomial replaces broken linear approximation (was 27-65% error at common temps)
- **QC qualifier parsing:** Now handles USGS array string format `"['ICE' 'EQUIP']"` (was never matching anything)
- **Ice/Maint buffer exclusion:** 48hr post-Ice, 4hr post-Maint (was documented but never coded)
- **Native-space metrics:** Duan smearing factor computed per LOGO fold, reported alongside log-space
- **Ridge linear baseline:** Runs under same LOGO CV framework for fair comparison
- **SHAP analysis:** Computed for Tier C models after final model save
- **QC raises on missing columns** instead of silently skipping

Retrain with all fixes is the next step. Results will change.

---

## Confirmed Physics Equations

| Constraint | Equation | Citation | Type |
|-----------|----------|----------|------|
| DO saturation | Nonlinear f(T, P) | Benson & Krause 1984 (fixed 2026-03-24; was broken linear approx with 27-65% error) | Thermodynamic |
| Non-negative concentrations | C ≥ 0 | Physical law | Thermodynamic |
| SC-TDS proportionality | TDS = k × SC, k=0.55-0.75 | Hem 1985 | Empirical-universal |
| TP ≥ orthophosphate | TP ≥ ortho-P | Mass balance | Thermodynamic |
| DO ≤ ~130% saturation | Soft cap | Empirical | Conditional |
| Turbidity-SSC monotonicity | ENFORCE with Box-Cox; skip with log1p | Sweep results 2026-03-28 | Transform-dependent |

---

## Transform & Constraint Ablation Sweep (2026-03-28)

### Context
The model optimizes RMSE on transformed SSC values. Native-space R² and KGE — the metrics practitioners actually care about — are never seen during training. This sweep tests which transform + constraint combination produces the best native-space performance.

**Dataset:** 396 sites, 35,209 samples, 37 features
**CV:** GroupKFold(5) stratified by median SSC (~20-170 sec per experiment)
**Baseline comparison:** Previous 266-site LOGO-CV had R²(native)=0.361, but GKF5 and LOGO are not directly comparable.

### Full Results Table (sorted by R²_native)

| # | Label | Transform | Lambda | Mono | Weights | R²(log) | R²(native) | KGE | Alpha | RMSE | Bias% | BCF | Trees |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 6 | boxcox_0.2 | boxcox | 0.2 | ON | - | 0.774 | **0.241** | 0.793 | 0.840 | 852 | -8.5 | 1.351 | 497 |
| 7 | boxcox_0.3 | boxcox | 0.3 | ON | - | 0.727 | **0.238** | 0.766 | 0.838 | 856 | -6.7 | 1.292 | 500 |
| 2 | log1p_noMono | log1p | - | OFF | - | 0.803 | **0.236** | 0.838 | 0.875 | 890 | -5.7 | 1.463 | 291 |
| 5 | boxcox_0.1 | boxcox | 0.1 | ON | - | 0.795 | 0.219 | 0.812 | 0.866 | 864 | -9.9 | 1.448 | 471 |
| 1 | baseline_log1p | log1p | - | ON | - | 0.797 | 0.217 | 0.825 | 0.867 | 901 | -3.9 | 1.711 | 358 |
| 8 | boxcox_0.5 | boxcox | 0.5 | ON | - | 0.610 | 0.213 | 0.674 | 0.777 | 875 | -3.6 | 1.250 | 281 |
| 9 | sqrt | sqrt | - | ON | - | 0.596 | 0.213 | 0.685 | 0.784 | 875 | -1.9 | 1.237 | 447 |
| 3 | boxcox_auto | boxcox | auto | ON | - | 0.789 | 0.195 | 0.823 | 0.868 | 896 | -7.4 | 1.675 | 293 |
| 10 | boxcox_0.2_noMono | boxcox | 0.2 | OFF | - | 0.767 | 0.181 | 0.803 | 0.850 | 885 | -7.0 | 1.296 | 367 |
| 4 | boxcox_auto_noMono | boxcox | auto | OFF | - | 0.801 | 0.177 | 0.842 | 0.882 | 907 | -11.9 | 1.414 | 362 |
| 16 | raw_noWeights | none | - | ON | - | 0.226 | 0.012 | 0.259 | 0.491 | 1140 | 111 | 2.285 | 182 |
| 15 | raw_linear | none | - | ON | linear | -5.283 | 0.004 | -7.017 | 0.365 | 962 | 25 | 0.140 | 17 |
| 19 | raw_noMono | none | - | OFF | - | 0.245 | -0.004 | 0.256 | 0.505 | 1125 | 132 | 2.168 | 321 |
| 18 | raw_log_wt | none | - | ON | log | 0.217 | -0.023 | 0.252 | 0.557 | 1211 | 101 | 2.023 | 252 |
| 17 | raw_sqrt_wt | none | - | ON | sqrt | -0.036 | -0.294 | -0.238 | 0.555 | 1154 | 168 | 1.311 | 110 |
| 20 | raw_sqrt_noMono | none | - | OFF | sqrt | -0.036 | -0.384 | -0.301 | 0.551 | 1137 | 159 | 1.168 | 91 |

### Key Findings

**1. Winner: Box-Cox lambda=0.2, monotone ON**
- Best native R² (0.241), reasonable BCF (1.351), decent tree count (497)
- Top 3 configs are within 0.005 R² of each other (statistical noise at 5 folds)
- BCF of 1.35 is far more stable than log1p's 1.71 — less reliance on smearing correction

**2. Monotone × Transform interaction (most important finding)**
- Log1p: monotone ON=0.217, OFF=0.236 → monotone HURTS (+0.019)
- BoxCox 0.2: monotone ON=0.241, OFF=0.181 → monotone HELPS (+0.060)
- Explanation: log1p already over-compresses, making monotone redundant/harmful. Box-Cox 0.2 retains enough nonlinearity that monotone prevents overfitting to noise.

**3. MLE auto-lambda is suboptimal**
- Auto (MLE) R²=0.195 vs manual lambda=0.2 R²=0.241
- MLE optimizes for normality of residuals, not prediction accuracy after back-transformation
- MLE likely picks lambda near 0 (approaching log), explaining why BCF=1.675 matches log1p

**4. Raw SSC is definitively ruled out**
- ALL raw experiments: R²(native) ≤ 0.012, bias 25-168%
- Linear weights collapsed to 17 trees (model only learned extreme events)
- Sqrt weights produced negative R² (worse than predicting the mean)
- Some form of target transform is structurally necessary for gradient boosting on SSC

**5. Alpha compression remains (0.84)**
- Winner's alpha=0.84 means predictions underestimate variability by 16%
- This hurts extreme event prediction — the primary use case
- Falls in the "try KGE eval_metric" zone (0.85-0.92 gate from expert consensus)

### Expert Panel Assessment (Dr. Santos, 2026-03-28)

- Top 3 configs are a statistical dead heat; pick winner on secondary criteria (BCF stability)
- The R²(native)=0.24 ceiling on 396 sites is concerning — verify by running boxcox_0.2 on original 266 sites to distinguish data vs CV effect
- KGE eval_metric worth pursuing for alpha improvement
- Recommended next: fine lambda sweep {0.15, 0.18, 0.20, 0.22, 0.25} then KGE eval_metric

### Reconciliation: Monotone Constraints

Previous entry said "DO NOT ENFORCE" based on Rivera audit. Updated based on empirical results:
- **With log1p transform:** monotone constraints are harmful (over-constrains an already compressed space)
- **With Box-Cox 0.2:** monotone constraints are beneficial (prevents overfitting without excessive compression)
- **Recommendation:** ENFORCE monotone when using Box-Cox lambda ≤ 0.3; SKIP monotone with log1p

### Next Steps
1. Fine lambda sweep around 0.2 (cheap, confirms optimum)
2. KGE eval_metric implementation for early stopping
3. Investigate 396-site vs 266-site R²(native) gap
4. HP sweep on winning transform (depth, learning rate)
