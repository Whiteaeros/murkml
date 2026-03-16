# CLAUDE.md

## Project Overview

`murkml` is an open-source Python toolkit for water quality surrogate modeling. It predicts expensive lab-measured water quality parameters (suspended sediment, nutrients) from cheap continuous sensor data (turbidity, conductance, dissolved oxygen, pH, temperature) using machine learning, with cross-site generalization as the key innovation.

## Architecture

- `src/murkml/data/` — Data acquisition (USGS NWIS API via `dataretrieval`), QC filtering, temporal alignment, feature engineering
- `src/murkml/models/` — ML models (CatBoost baseline, later LSTM)
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
- Do NOT use raw lat/lon as model features — causes leakage in leave-one-site-out CV
- Target variable: `log1p(SSC)` — handles zeros, back-transform with Duan's smearing estimator
- All timestamps stored as UTC

## Testing

```bash
pytest tests/
ruff check src/
```

## Random Seed

Global seed is `42`, defined in `src/murkml/__init__.py`. Use it everywhere for reproducibility.
