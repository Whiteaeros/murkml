# murkml

Predict water quality from continuous sensor data using ML surrogate models.

**[Dashboard](dashboard/_site/index.html)** — Interactive results explorer (performance, adaptation curves, site maps, load estimation, diagnostics).

## What it does

- **Loads USGS data automatically** — continuous sensors (turbidity, conductance, DO, pH, temp) and discrete lab samples (sediment, nutrients) via the `dataretrieval` package
- **Trains cross-site ML models** — a model trained on data-rich USGS sites can predict at new sites without per-site calibration
- **Explains predictions** — SHAP plots showing which inputs drive each prediction
- **Quantifies uncertainty** — prediction intervals via quantile regression
- **Provides benchmark datasets** — compiled cross-site paired sensor+lab data

## Quick start

```python
import murkml

# Discover USGS sites with paired turbidity + sediment data
sites = murkml.discover_sites(
    continuous_params=["turbidity"],
    discrete_params=["SSC"],
    min_samples=30,
)

# Build ML-ready dataset
dataset = murkml.build_dataset(sites, start="2015-01-01", end="2024-12-31")

# Train cross-site model
model = murkml.train(dataset, target="SSC", method="catboost")

# Predict at a new site
predictions = model.predict(site="USGS-12345678")

# Explain
model.explain(site="USGS-12345678")
```

## Installation

```bash
pip install murkml            # Core (data pipeline + scikit-learn)
pip install murkml[boost]     # + CatBoost
pip install murkml[explain]   # + SHAP
pip install murkml[all]       # Everything
```

## Who this is for

Water quality scientists, environmental consultants, and state/federal agencies who have continuous sensor data and want to estimate lab-measured parameters without building per-site regression models.

## License

BSD-3-Clause
