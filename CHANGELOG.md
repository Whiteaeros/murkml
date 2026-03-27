# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Initial project structure
- Data pipeline: USGS data fetching, QC filtering, temporal alignment
- Feature engineering for sensor time-series
- CatBoost cross-site baseline model

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
