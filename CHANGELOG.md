# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Initial project structure
- Data pipeline: USGS data fetching, QC filtering, temporal alignment
- Feature engineering for sensor time-series
- CatBoost cross-site baseline model

## [2026-03-30] — Phase 3: Pipeline Fixes & Data Corrections

### Bug Fixes (evaluate_model.py — from Gemini red-team review)
- hash() → hashlib.md5() for deterministic cross-session seeding of adaptation trials
- Slope clipping in adapt_old_2param now recalculates intercept to maintain calibration centroid
- adapt_bayesian upgraded from simple Gaussian to Student-t shrinkage (w_t influence weighting)
- Default k changed from 30 to 15, --df CLI arg added for Student-t degrees of freedom

### Staged Bayesian Adaptation (ported from site_adaptation_bayesian.py)
- evaluate_model.py now has full staged adaptation: intercept-only N<10, slope+intercept N>=10
- Per-trial BCF shrunk toward 1.0 (more conservative than global BCF)
- MAD-based robust scale estimation instead of std
- Slope shrunk toward 1.0 with separate --slope-k parameter (default 10)
- BCF shrinkage controlled by --bcf-k-mult (default 3.0)

### SGMC Lithology Features (28 watershed geology categories)
- Created data/sgmc/sgmc_features_for_model.parquet (355 sites, 28 features)
- Modified train_tiered.py to auto-merge SGMC into watershed_attrs at Tier C
- Categories: igneous, metamorphic, sedimentary, unconsolidated rock types as watershed %
- GKF5 quick test: net flat on aggregate (R²_native -0.007), but subgroup effects unknown
- Ablation deferred to Phase 5 (after disaggregated diagnostics in Phase 4)

### Collection Method Resolution
- Applied 218/231 resolved collection methods from data/unknown_method_resolution.csv
- Unknown samples reduced: 6,282 → 746 (88% resolved)
- Most resolved to depth_integrated (182 sites), auto_point (30), grab (6)
- Original paired dataset backed up to turbidity_ssc_paired_pre_method_resolution.parquet
- GKF5 sanity check: small improvement (R²_native +0.005, RMSE -2.7)

## [2026-03-29] — Experiments A-E + Bayesian Breakthrough

### 30+ Experiments Completed
- Experiment A (7 models): Collection method splitting — NO improvement
- Experiment B (3 models): Site exclusion — cosmetic only (pooled up, per-site down)
- Experiment C: Flow stratification — NOT a flow problem, site heterogeneity at all regimes
- Experiment D (17+ models): Site count — sweet spot ~200 sites
- Experiment E: MERF — concept works but loses categoricals
- v8 mixed-effects: GPBoost failed, CatBoost-MERF EM failed, post-hoc RE won

### Bayesian Site Adaptation
- Student-t shrinkage (k=15, df=4): N=2 goes from -0.012 to 0.485
- Monotonically non-decreasing curve (200 MC trials)
- CatBoost+Bayesian with 2 samples beats USGS OLS with 50 samples
- evaluate_model.py written, expert-reviewed (Dr. Patel), 5 issues fixed

### SGMC Lithology Overlay
- 355 sites with watershed-level lithology percentages
- 5 categories significant at p<0.05 (metamorphic_undiff, amphibolite, sed_carbonate, sed_chemical, sed_clastic)
- Bedrock type predicts turbidity-SSC slope (Kruskal-Wallis p=0.0024)

### Anchor Sites
- 50 curated sites beat all-287 on per-site R² (0.367 vs 0.266)
- Gemini review identified data leak in selection (holdout used to select training data)

## [2026-03-28] — Transform Sweep + Data Expansion

### Transform Sweep (24 experiments)
- Box-Cox lambda=0.2 + monotone ON wins (R²_native=0.241)
- Raw SSC ruled out (all configs R²≤0.012)
- KGE eval_metric tested (no improvement)
- Monotone helps Box-Cox but hurts log1p (transform-dependent interaction)

### Data Expansion
- 266 → 396 sites via QC approval code fix (A/P → Approved/Provisional normalization)
- Bug fixes: dedup key (numpy vs pandas datetime string format), precip temporal leakage, weather tz mismatch, flush_intensity NaN handling
- Linear interpolation for turbidity-SSC alignment
- Collection method feature added (auto_point, depth_integrated, grab, unknown)
- Sensor calibration features: sensor_offset, days_since_last_visit, sensor_family

### Feature Ablation
- Single-feature ablation on 102 features (all metrics)
- Feature reduction 102 → 62 → 37 (expert panel consensus)
- Native-space effects 10-100x larger than log-space effects
- R²(native) improved from 0.295 to 0.361 (+22%) after feature reduction

## [2026-03-26] — Major Expansion + Site Adaptation

### Data Foundation
- Expanded from 102 to 413 qualified sites (860 discovered → 723 with turbidity → 413 with temporal overlap)
- Smart batch download: 168 API calls, 171M rows, 1.4 GB continuous data
- Resilient download wrapper with zombie process cleanup (download_resilient.py)
- EPA StreamCat replaces GAGES-II + NLCD (370/413 sites, 69 static features)
- GridMET daily weather downloaded for 861 sites (NOT YET integrated as features)
- Discrete SSC batch download: 94K samples via WQP for 585 sites
- Site qualification pipeline: qualify_sites.py with waterservices metadata API

### Model Training
- 270 sites in paired dataset (14,393 aligned samples)
- Tier C (StreamCat): log R²=0.710, native R²=0.363, RMSE=111 mg/L
- Holdout (57 unseen sites): native R²=0.552, slope=0.650
- All red team code fixes active: DO formula, QC hardening, native metrics, Ridge baseline, SHAP
- Joblib parallelization (6 workers) + Ordered boosting
- Box-Cox transform tested (lambda≈0, confirms log is optimal)
- Weighted loss tested (sqrt, log schemes — modest native improvement)

### Site-Adaptive Fine-Tuning
- Calibration effort curve: N=10 samples gets R²=0.60, slope=0.79
- Temporal splits (realistic deployment): N=10 gets R²=0.47
- Head-to-head vs USGS OLS: wins 30/46 sites at N=10
- Agriculture_pct predicts where USGS wins (rho=-0.48)

### Evaluation
- Prediction intervals: 95% coverage=96.1%, 90%=91.7% (well-calibrated)
- Error analysis: sand_pct strongest negative correlate, urban sites worst
- Significance tests: all tier improvements p<0.01 for native metrics
- Literature comparison: first multi-site transferable SSC model (243+ CONUS sites)

### New Scripts
- scripts/site_adaptation.py — calibration effort curve (random + temporal)
- scripts/prediction_intervals.py — conformal prediction intervals
- scripts/error_analysis.py — per-site failure mode analysis
- scripts/significance_tests.py — Wilcoxon tests + literature comparison
- scripts/compare_vs_usgs.py — head-to-head vs USGS OLS
- scripts/download_batch.py — smart batch USGS download
- scripts/download_resilient.py — autonomous download with zombie cleanup
- scripts/qualify_sites.py — site qualification pipeline
- scripts/fill_missing_streamcat.py — StreamCat gap-fill

### Bug Fixes
- huc2 "unknown" crash in build_feature_tiers()
- Column collision (_x/_y) in Tier C merge (basic + StreamCat overlap)
- WQP batch column names (ActivityStartDate vs Activity_StartDate)
- Merge schema: datetime→time column for assembly compatibility
- Socket timeout + process tree kill for hung API downloads

## [2026-03-24] — Red Team + Bug Fixes

### Fixed
- prune_gagesii() double-pruning bug (silently destroyed all GAGES-II attributes)
- DO saturation: Benson & Krause 1984 polynomial (replaced broken linear approx)
- QC qualifier parsing: handles USGS array string format
- Ice buffer (48hr) and maintenance buffer (4hr) exclusion
- QC raises on missing columns instead of silently skipping

### Added
- Native-space metrics with Duan's smearing correction
- Ridge linear baseline under same LOGO CV
- SHAP analysis for Tier C models
- Per-fold data integrity checks
- 5-reviewer red team panel synthesis
