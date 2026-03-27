# CLAUDE.md

## Project Overview

`murkml` is an open-source Python toolkit for water quality surrogate modeling. It predicts expensive lab-measured water quality parameters (suspended sediment, nutrients) from cheap continuous sensor data (turbidity, conductance, dissolved oxygen, pH, temperature) using machine learning, with cross-site generalization as the key innovation.

## Architecture

- `src/murkml/data/` — Data acquisition (USGS NWIS API via `dataretrieval`), QC filtering, temporal alignment, feature engineering
- `src/murkml/models/` — ML models (CatBoost regressor)
- `scripts/` — Training (train_tiered.py), assembly, site adaptation, error analysis, comparison scripts
- `src/murkml/evaluate/` — Metrics (R², RMSE, KGE, SHAP) and visualization
- `notebooks/` — Jupyter notebooks for exploration and demos
- `tests/` — pytest test suite

## Critical API Notes

The `dataretrieval` package's `nwis` module is DEPRECATED. Always use the `waterdata` module:
- `waterdata.get_continuous(monitoring_location_id=..., parameter_code=..., time="YYYY-MM-DD/YYYY-MM-DD")`
- `waterdata.get_samples(monitoringLocationIdentifier=..., usgsPCode=...)`
- `waterdata.get_time_series_metadata(parameter_code=..., state_name="Kansas")`
  - Note: uses full state NAMES, not codes
- Site IDs use `"USGS-"` prefix (e.g., `"USGS-07144100"`)
- QC: `approval_status = "Approved"` (spelled out, not `"A"`)
- QC: `qualifier` is `None` when clean (not empty string)
- Continuous data has 3-year max per API call — loop in chunks
- Time parameter uses ISO 8601 interval format: `"2024-01-01/2024-12-31"`

## Data Rules

- Use SSC (param 80154) only, NOT TSS (00530) — different methods, 25-50% divergence
- Use turbidity FNU (param 63680) only, NOT NTU (00076) — diverge above 400 units
- Lat/lon: currently NOT used as features but under consideration. Previous note about leakage is debatable — lat/lon encode spatial climate gradients, not site identity.
- Target variable: `log1p(SSC)` — handles zeros, back-transform with Duan's smearing estimator (or Snowdon BCF for non-log transforms)
- All timestamps stored as UTC
- **DO saturation: MUST use Benson & Krause (1984) nonlinear polynomial.** NEVER use a linear approximation like `14.6 - 0.4*T` — this has 27-65% error at common stream temperatures (5-25C). The broken linear formula was in the code for months before discovery. This is a physics equation, not something CatBoost can compensate for in feature engineering.
- **USGS QC qualifier format:** The API returns qualifiers as array-like strings, e.g., `"['ICE' 'EQUIP']"`, NOT simple strings like `"Ice"`. Any code parsing qualifiers must handle this format or it will silently match nothing. The bug went undetected because no error is raised — the filter just excludes zero records.

## Testing

```bash
pytest tests/
ruff check src/
```

## Random Seed

Global seed is `42`, defined in `src/murkml/__init__.py`. Use it everywhere for reproducibility.

## Data Integrity Rules (MANDATORY — added 2026-03-24 after critical bug)

A bug where `prune_gagesii()` was called on already-pruned data silently destroyed ALL GAGES-II attributes. The model trained on 25 columns of zeros/NaN for months without any error. These rules prevent this class of bug:

1. **Before reporting ANY model results**, verify the training data actually contains expected values (not all zeros/NaN). Spot-check with `df.describe()` or `df.head()`.

2. **Never call `prune_gagesii()` on `site_attributes_gagesii.parquet`** — that file already has pruned column names. `prune_gagesii()` expects raw GAGES-II column names (e.g., `FORESTNLCD06`). Call it on `site_attributes_gagesii_full.parquet` instead, or skip it if data is already pruned.

3. **Check column name format before any transformation.** If a function uses `_safe_col()` with hardcoded column names, verify those names exist in the input. If >50% of expected columns are missing, fail — don't fill with defaults.

4. **All results need a provenance chain:** raw data → processing step → features → model → metrics. Every parquet file should have a clear owner (which script creates it, which script reads it).

5. **Two GAGES-II files exist with different schemas:**
   - `site_attributes_gagesii_full.parquet` — RAW column names (`FORESTNLCD06`, `GEOL_HUNT_DOM_CODE`), ~270 columns
   - `site_attributes_gagesii.parquet` — PRUNED column names (`forest_pct`, `geol_class`), ~26 columns

   Code that reads these must know which format to expect.

6. **Categorical columns (`geol_class`, `ecoregion`, `reference_class`, `huc2`) must be dtype `object` (string) when passed to CatBoost.** If they become float64 (e.g., from NaN fill), they won't be detected as categoricals and will be treated as numeric garbage. Always verify dtype after merges.

7. **QC filtering must be validated by checking exclusion counts.** If a QC filter excludes zero records (e.g., no Ice flags matched), investigate — it likely means the qualifier format doesn't match. The USGS array string format `"['ICE' 'EQUIP']"` caused a silent total failure of QC filtering.

8. **Report metrics in both log-space and native-space (mg/L).** Log-space R²=0.80 corresponds to native-space R²=0.61. Reporting only log-space metrics overstates practical accuracy. Use Duan's smearing factor (computed from TRAINING residuals per fold, never test) for back-transformation.

9. **Watershed attributes now use StreamCat** (replaced GAGES-II + NLCD). 370/413 qualified sites covered (43 uncoverable AK/HI). 69 static features after dropping time-varying and all-null columns. Loaded via `load_streamcat_attrs()` in `attributes.py`.

10. **Current model state (2026-03-26):** 243 training sites, 92 features (Tier C), log R²=0.71 LOGO CV, holdout native R²=0.55. Site-adaptive calibration with N=10 local samples gets slope=0.79. Beats USGS OLS on 30/46 holdout sites. Prediction intervals well-calibrated (90% coverage=91.7%).

11. **GridMET weather data downloaded but NOT YET integrated as features.** 861 sites, daily precip+temp 2006-2025, at `data/weather/USGS_{site_no}/daily_weather.parquet`. Planned: antecedent precip features (24h, 48h, 7d, 30d rolling sums).

12. **Scripts created this session:** site_adaptation.py, prediction_intervals.py, error_analysis.py, significance_tests.py, compare_vs_usgs.py, download_resilient.py, fill_missing_streamcat.py. All committed to git.
