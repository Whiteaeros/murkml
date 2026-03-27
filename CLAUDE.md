# CLAUDE.md

## What This Project Is

`murkml` predicts suspended sediment concentration (SSC) in rivers using turbidity sensors and machine learning. The core innovation is **cross-site generalization**: one model trained on 243 USGS sites that works at new sites it's never seen, optionally improved with a handful of local grab samples.

**Owner:** Kaleb — water science student, graduating mid-2026. Not on a deadline. Exploring what's possible, with eventual commercial product and paper goals.

## Current State (2026-03-26)

**What works:**
- CatBoost model trained on 243 sites, 92 EPA StreamCat watershed features
- LOGO CV (leave-one-site-out): log R²=0.71, native R²=0.36
- Holdout (57 unseen sites): native R²=0.55, pred-vs-obs slope=0.65
- Site-adaptive calibration: 10 local grab samples → slope=0.79, R²=0.60
- Beats USGS standard OLS regression on 30/46 holdout sites
- Prediction intervals: 90% coverage=91.7% (well-calibrated)
- All code fixes from red team review implemented and active

**Known limitations:**
- Native-space slope=0.19-0.65 (model compresses magnitudes — fundamental to multi-site generalization)
- Urban sites and sandy watersheds perform worst
- GridMET weather data (861 sites, daily precip+temp) is downloaded but NOT integrated as features
- 143 qualified sites dropped during assembly (had data but no aligned turbidity-SSC pairs)

**What's next:** See plan file at `C:\Users\kaleb\.claude\plans\frolicking-snacking-emerson.md` — Batch A: add monotonicity constraints + quantile regression + weather features + lat/lon, then retrain once.

## How the Pipeline Works

```
1. DISCOVERY: Find USGS sites with SSC samples
   → data/all_discovered_sites.parquet (860 sites)

2. QUALIFICATION: Check which sites have turbidity + temporal overlap
   → data/qualified_sites.parquet (413 sites)
   → data/train_holdout_split.parquet (324 train / 89 holdout)

3. DOWNLOAD: Get continuous sensor data + discrete lab samples
   → data/continuous/{site}/{param}/*.parquet (15-min sensor readings)
   → data/discrete/{site}_ssc.parquet (grab samples)
   → data/weather/{site}/daily_weather.parquet (GridMET precip+temp)

4. ASSEMBLY: Align grab samples with sensor readings (±15 min window)
   Script: scripts/assemble_dataset.py
   → data/processed/turbidity_ssc_paired.parquet (270 sites, 14,393 samples, 29 cols)

5. ATTRIBUTES: Load watershed features
   Script: src/murkml/data/attributes.py (load_streamcat_attrs, build_feature_tiers)
   → Tier A: sensor-only (22 features, 270 sites)
   → Tier B: + basic attrs (25 features, 270 sites)
   → Tier C: + StreamCat (92 features, 243 sites)

6. TRAINING: CatBoost LOGO CV with joblib parallelization
   Script: scripts/train_tiered.py
   Flags: --param ssc --tier C --n-jobs 6 --transform log1p --weight-scheme sqrt --slope-correction --quantile
   → data/results/tiered_comparison.parquet
   → data/results/logo_predictions_ssc_*.parquet
   → data/results/models/ssc_*.cbm + *_meta.json

7. EVALUATION:
   → scripts/site_adaptation.py (calibration effort curve, --temporal flag)
   → scripts/prediction_intervals.py (conformal intervals)
   → scripts/error_analysis.py (failure modes by site characteristics)
   → scripts/compare_vs_usgs.py (head-to-head vs USGS OLS)
   → scripts/significance_tests.py (Wilcoxon tier tests + lit comparison)
```

## Key Files

| File | What it does |
|------|-------------|
| `scripts/train_tiered.py` | Main training script. LOGO CV, Ridge baseline, SHAP, native metrics. ~850 lines. |
| `scripts/assemble_dataset.py` | Builds paired dataset from continuous + discrete data. ~400 lines. |
| `src/murkml/data/features.py` | Feature engineering: hydrograph, cross-sensor, seasonality. ~200 lines. |
| `src/murkml/data/attributes.py` | Loads StreamCat, builds feature tiers. `load_streamcat_attrs()`, `build_feature_tiers()`. |
| `src/murkml/evaluate/metrics.py` | All metrics: R², KGE, Duan BCF, Snowdon BCF, slope correction, native-space metrics. |
| `src/murkml/data/qc.py` | QC filtering: approval status, qualifier parsing, ice/maint buffers. |
| `src/murkml/data/align.py` | Temporal alignment of grab samples to sensor readings. |
| `scripts/site_adaptation.py` | Calibration effort curve (random + temporal splits). |
| `scripts/prediction_intervals.py` | Conformal prediction intervals from LOGO residuals. |

## Data Rules

- SSC only (param 80154), NOT TSS (00530) — different methods
- Turbidity FNU only (param 63680), NOT NTU (00076) — diverge above 400
- Target: `log1p(SSC)` with Duan's smearing for back-transform
- All timestamps UTC
- DO saturation: Benson & Krause (1984) polynomial ONLY — never linear approx
- QC qualifiers come as array strings `"['ICE' 'EQUIP']"` — must parse this format
- Report metrics in BOTH log-space and native-space (mg/L) — log-space flatters the model

## Watershed Attributes

**Current: EPA StreamCat** (replaced GAGES-II). 370/413 sites, 69 static features. Loaded by `load_streamcat_attrs()`. Time-varying StreamCat columns (85 cols: forest loss, burn severity, impervious by year) are currently dropped but could be matched to sample years.

**GAGES-II is legacy** — `prune_gagesii()` exists but is dead code. Don't use it.

## Lessons Learned (Things That Bit Us)

1. `prune_gagesii()` called on already-pruned data silently destroyed all attributes. Model trained on zeros for months. **Always verify data contains expected values before training.**
2. USGS qualifier format `"['ICE' 'EQUIP']"` caused QC to silently skip all filtering. **Check exclusion counts.**
3. Log-space R²=0.71 looks good but native slope=0.19. **Always report native-space metrics.**
4. `huc2` column contains "unknown" strings that crash `.astype(int)`. `build_feature_tiers()` handles it.
5. CatBoost venv `python.exe` on Windows is a thin launcher — zombie child processes accumulate. See `download_resilient.py`.
6. The `dataretrieval.nwis` module is deprecated. `waterdata` module uses the OGC API (separate rate pool).

## Documentation Map

| File | Contents | Update when... |
|------|----------|----------------|
| `CLAUDE.md` | This file — project rules and current state | Architecture changes, new data rules, model numbers change |
| `RESULTS_LOG.md` | All model results with numbers | New training run or evaluation |
| `CHANGELOG.md` | History of changes by date | Significant feature, fix, or data change |
| `PIPELINE.md` | Data pipeline flow | Pipeline architecture changes |
| `PRODUCT_VISION.md` | Commercial product vision | Vision/strategy changes |

(EXPANSION_PLAN.md, DATA_DOWNLOAD_PLAN.md, AUDIT_FIX_PLAN.md are superseded — reference only.)

## Technical Notes

- **Python venv:** `.venv/Scripts/python` (Windows). UV-managed, cpython 3.12.9.
- **Random seed:** 42 everywhere
- **Parallelization:** joblib with 6 workers, 4 CatBoost threads each (24-core i9)
- **CatBoost:** v1.2.10, Ordered boosting, GPU verified working but NOT recommended for LOGO CV (too small per fold, overhead dominates)
- **MultiQuantile + monotone_constraints:** verified compatible in CatBoost
- **Weather data format:** `data/weather/USGS_{site_no}/daily_weather.parquet`, cols: date (datetime64), precip_mm, tmax_c, tmin_c, tmean_c (float32). Zero nulls. 270/270 paired sites have coverage.
