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

## Documentation Map

Keep these updated when making significant changes:

| File | What it covers | Update when... |
|------|---------------|----------------|
| `CLAUDE.md` | Project rules, API notes, current state | Any architectural change, new data rules, current model numbers change |
| `RESULTS_LOG.md` | All model results with numbers | Any new training run or evaluation |
| `CHANGELOG.md` | History of changes by date | Any significant feature, fix, or data change |
| `EXPANSION_PLAN.md` | Site expansion history (SUPERSEDED) | Reference only — expansion complete |
| `DATA_DOWNLOAD_PLAN.md` | Download history (SUPERSEDED) | Reference only — downloads complete |
| `AUDIT_FIX_PLAN.md` | Audit remediation (SUPERSEDED) | Reference only — all fixes applied |
| `PIPELINE.md` | Data pipeline flow | Pipeline architecture changes |
| `PRODUCT_VISION.md` | Commercial product vision | Vision/strategy changes |

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

2. **GAGES-II is legacy — use StreamCat.** `prune_gagesii()` and GAGES-II files still exist for backward compatibility but are NOT used in current training. `load_streamcat_attrs()` in `attributes.py` is the current attribute loader. If you see GAGES-II references in old code, they're dead paths.

3. **Check column name format before any transformation.** If a function uses `_safe_col()` with hardcoded column names, verify those names exist in the input. If >50% of expected columns are missing, fail — don't fill with defaults.

4. **All results need a provenance chain:** raw data → processing step → features → model → metrics. Every parquet file should have a clear owner (which script creates it, which script reads it).

5. **Categorical columns (`geol_class`, `huc2`) must be dtype `object` (string) when passed to CatBoost.** If they become float64 (e.g., from NaN fill), they won't be detected as categoricals. StreamCat's `geol_class` is derived from dominant lithology. `huc2` comes from NLDI supplementary. Both handled by `load_streamcat_attrs()` and `build_feature_tiers()`.

6. **huc2 "unknown" values must be converted to NaN** before any int conversion. 102 sites have huc2="unknown" from lost NLDI checkpoints. `build_feature_tiers()` handles this, but any new code touching huc2 must be aware.

7. **QC filtering must be validated by checking exclusion counts.** If a QC filter excludes zero records (e.g., no Ice flags matched), investigate — it likely means the qualifier format doesn't match. The USGS array string format `"['ICE' 'EQUIP']"` caused a silent total failure of QC filtering.

8. **Report metrics in both log-space and native-space (mg/L).** Log-space R²=0.80 corresponds to native-space R²=0.61. Reporting only log-space metrics overstates practical accuracy. Use Duan's smearing factor (computed from TRAINING residuals per fold, never test) for back-transformation.

9. **Watershed attributes now use StreamCat** (replaced GAGES-II + NLCD). 370/413 qualified sites covered (43 uncoverable AK/HI). 69 static features after dropping time-varying and all-null columns. Loaded via `load_streamcat_attrs()` in `attributes.py`.

10. **Current model state (2026-03-26):** 243 training sites, 92 features (Tier C), log R²=0.71 LOGO CV, holdout native R²=0.55. Site-adaptive calibration with N=10 local samples gets slope=0.79. Beats USGS OLS on 30/46 holdout sites. Prediction intervals well-calibrated (90% coverage=91.7%).

11. **GridMET weather data downloaded but NOT YET integrated as features.** 861 sites, daily precip+temp 2006-2025, at `data/weather/USGS_{site_no}/daily_weather.parquet`. Planned: antecedent precip features (24h, 48h, 7d, 30d rolling sums).

12. **Scripts created this session:** site_adaptation.py, prediction_intervals.py, error_analysis.py, significance_tests.py, compare_vs_usgs.py, download_resilient.py, fill_missing_streamcat.py. All committed to git.
