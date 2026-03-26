"""Run trained SSC + TP models on external validation sites.

Assembles data from validation sites (new states not in training),
runs the saved CatBoost models, and computes per-site metrics.
Also computes per-site OLS for comparison.

Usage:
    python scripts/run_external_validation.py
"""

from __future__ import annotations

import logging
import pickle
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from murkml.data.align import align_samples
from murkml.data.discrete import load_discrete_param
from murkml.data.features import engineer_features
from murkml.data.qc import filter_continuous
from murkml.evaluate.metrics import kge, r_squared, rmse
from murkml.provenance import start_run, log_step, log_file, end_run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"
VAL_DIR = DATA_DIR / "validation"

CONTINUOUS_PARAMS = {
    "63680": "turbidity",
    "00095": "conductance",
    "00300": "do",
    "00400": "ph",
    "00010": "temp",
    "00060": "discharge",
}


def load_continuous_val(site_id: str, param_code: str) -> pd.DataFrame:
    """Load continuous data from validation directory."""
    cont_dir = VAL_DIR / "continuous" / site_id.replace("-", "_") / param_code
    if not cont_dir.exists():
        return pd.DataFrame()
    chunks = []
    for f in sorted(cont_dir.glob("*.parquet")):
        chunk = pd.read_parquet(f)
        if len(chunk) > 0:
            chunks.append(chunk)
    if not chunks:
        return pd.DataFrame()
    df = pd.concat(chunks, ignore_index=True)
    df = df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    return df


def assemble_validation_site(site_id: str, param_name: str, value_col: str) -> pd.DataFrame:
    """Assemble paired dataset for one validation site."""
    # Load discrete from validation directory
    discrete = load_discrete_param(
        site_id=site_id, param_name=param_name,
        data_dir=VAL_DIR, value_col_out=value_col,
    )
    if discrete.empty:
        return pd.DataFrame()

    # Load continuous turbidity
    turb = load_continuous_val(site_id, "63680")
    if turb.empty:
        logger.warning(f"  No turbidity for {site_id}")
        return pd.DataFrame()

    turb_filtered, _ = filter_continuous(turb)
    if turb_filtered.empty or "time" not in turb_filtered.columns:
        logger.warning(f"  No usable turbidity after QC for {site_id}")
        return pd.DataFrame()
    turb_clean = turb_filtered[["time", "value"]].copy()
    turb_clean.columns = ["datetime", "value"]

    disc_clean = discrete[["datetime", value_col]].copy()
    disc_clean.columns = ["datetime", "value"]

    aligned = align_samples(continuous=turb_clean, discrete=disc_clean,
                            max_gap=pd.Timedelta(minutes=15))
    if aligned.empty:
        return pd.DataFrame()

    aligned = aligned.rename(columns={
        "sensor_instant": "turbidity_instant",
        "window_mean": "turbidity_mean_1hr",
        "window_min": "turbidity_min_1hr",
        "window_max": "turbidity_max_1hr",
        "window_std": "turbidity_std_1hr",
        "window_range": "turbidity_range_1hr",
        "window_slope": "turbidity_slope_1hr",
    })

    # Add secondary sensors
    for pcode, pname in CONTINUOUS_PARAMS.items():
        if pcode == "63680":
            continue
        cont = load_continuous_val(site_id, pcode)
        if cont.empty:
            aligned[f"{pname}_instant"] = np.nan
            continue
        cont_filtered, _ = filter_continuous(cont)
        if cont_filtered.empty:
            aligned[f"{pname}_instant"] = np.nan
            continue
        cont_clean = cont_filtered[["time", "value"]].copy().reset_index(drop=True)
        cont_clean["time"] = pd.to_datetime(cont_clean["time"], utc=True)
        cont_clean = cont_clean.sort_values("time").reset_index(drop=True)

        sample_df = aligned[["sample_time"]].copy().reset_index(drop=True)
        sample_df["sample_time"] = pd.to_datetime(sample_df["sample_time"], utc=True)
        cont_clean["time"] = pd.to_datetime(cont_clean["time"], utc=True)
        merged = pd.merge_asof(
            sample_df.rename(columns={"sample_time": "_t"}),
            cont_clean.rename(columns={"time": "_t", "value": "_v"}),
            on="_t",
            direction="nearest",
            tolerance=pd.Timedelta(minutes=15),
        )
        aligned[f"{pname}_instant"] = merged["_v"].values

    aligned["site_id"] = site_id
    return aligned


def main():
    warnings.filterwarnings("ignore")
    start_run("external_validation")

    # Load saved models
    models = {}
    for param in ["ssc", "total_phosphorus"]:
        model_path = DATA_DIR / "results" / "models" / f"{param}_tierB_final.cbm"
        meta_path = DATA_DIR / "results" / "models" / f"{param}_tierB_final_meta.pkl"
        if model_path.exists():
            from catboost import CatBoostRegressor
            model = CatBoostRegressor()
            model.load_model(str(model_path))
            with open(meta_path, "rb") as f:
                meta = pickle.load(f)
            models[param] = {"model": model, "meta": meta}
            log_file(model_path, role="input")
            log_file(meta_path, role="input")
            logger.info(f"Loaded {param} model: {meta['n_sites']} training sites, "
                       f"{meta['n_train']} samples, {len(meta['feature_cols'])} features")

    if not models:
        logger.error("No saved models found!")
        sys.exit(1)

    # Load basic attributes for Tier B features
    basic_attrs = pd.read_parquet(DATA_DIR / "site_attributes.parquet")

    # Find validation sites by scanning the validation directory for turbidity data
    cont_dir = VAL_DIR / "continuous"
    viable_sites = []
    if cont_dir.exists():
        for site_dir in sorted(cont_dir.iterdir()):
            if not site_dir.is_dir():
                continue
            turb_dir = site_dir / "63680"
            if turb_dir.exists():
                # Check for non-empty parquet files
                has_data = False
                for f in turb_dir.glob("*.parquet"):
                    df = pd.read_parquet(f)
                    if len(df) > 0:
                        has_data = True
                        break
                if has_data:
                    site_id = site_dir.name.replace("_", "-")
                    viable_sites.append({"site_id": site_id})

    viable = pd.DataFrame(viable_sites)
    logger.info(f"\nViable validation sites (have turbidity): {len(viable)}")

    all_results = []
    all_predictions = []

    for param_name, param_cfg in [("ssc", "ssc"), ("total_phosphorus", "total_phosphorus")]:
        if param_name not in models:
            continue

        model = models[param_name]["model"]
        meta = models[param_name]["meta"]
        feature_cols = meta["feature_cols"]
        train_median = pd.Series(meta["train_median"])
        smearing = meta["smearing_factor"]

        logger.info(f"\n{'='*60}")
        logger.info(f"EXTERNAL VALIDATION: {param_name}")
        logger.info(f"{'='*60}")

        value_col = "ssc_value" if param_name == "ssc" else "value"

        for _, site_row in viable.iterrows():
            site_id = site_row["site_id"]

            # Check if discrete data file exists
            site_stem = site_id.replace("-", "_")
            disc_file = VAL_DIR / "discrete" / f"{site_stem}_{param_name}.parquet"
            if not disc_file.exists():
                continue

            logger.info(f"\n  {site_id}")
            try:
                assembled = assemble_validation_site(site_id, param_name, value_col)
            except Exception as e:
                logger.error(f"    Assembly error: {e}")
                continue
            if assembled.empty or len(assembled) < 10:
                logger.warning(f"    Too few samples: {len(assembled) if not assembled.empty else 0}")
                continue

            # Add basic attributes
            site_attrs = basic_attrs[basic_attrs["site_id"] == site_id]
            if not site_attrs.empty:
                for col in ["drainage_area_km2", "altitude_ft", "huc2"]:
                    if col in site_attrs.columns:
                        assembled[col] = site_attrs[col].values[0]

            # Feature engineering
            assembled = engineer_features(assembled)

            # Target
            y_true_log = np.log1p(assembled["lab_value"].values)

            # Prepare features (same as training)
            X_df = assembled[feature_cols].copy() if all(c in assembled.columns for c in feature_cols) else None
            if X_df is None:
                # Use available features, fill missing with training median
                available = [c for c in feature_cols if c in assembled.columns]
                X_df = assembled[available].copy()
                for c in feature_cols:
                    if c not in X_df.columns:
                        X_df[c] = train_median.get(c, 0)
                X_df = X_df[feature_cols]

            X = X_df.fillna(train_median).values

            # CatBoost prediction
            y_pred_log = model.predict(X)
            cb_r2 = r_squared(y_true_log, y_pred_log)
            cb_kge = kge(y_true_log, y_pred_log)
            cb_rmse = rmse(y_true_log, y_pred_log)

            # Collect per-sample predictions
            sample_preds = pd.DataFrame({
                "site_id": site_id,
                "param": param_name,
                "sample_time": assembled["sample_time"].values,
                "lab_value": assembled["lab_value"].values,
                "y_true_log": y_true_log,
                "y_pred_log": y_pred_log,
                "turbidity_instant": assembled["turbidity_instant"].values,
                "discharge_instant": assembled.get("discharge_instant", np.nan),
            })
            all_predictions.append(sample_preds)

            # Per-site OLS (log-log with turbidity)
            ols_r2 = np.nan
            if "turbidity_instant" in assembled.columns:
                valid_ols = assembled.dropna(subset=["turbidity_instant"])
                if len(valid_ols) >= 10:
                    X_ols = np.log1p(valid_ols["turbidity_instant"].values).reshape(-1, 1)
                    y_ols = np.log1p(valid_ols["lab_value"].values)
                    # 70/30 temporal split
                    n_train = int(len(valid_ols) * 0.7)
                    if n_train >= 5 and (len(valid_ols) - n_train) >= 5:
                        lr = LinearRegression().fit(X_ols[:n_train], y_ols[:n_train])
                        y_ols_pred = lr.predict(X_ols[n_train:])
                        ols_r2 = r_squared(y_ols[n_train:], y_ols_pred)

            logger.info(f"    n={len(assembled)}, CatBoost R²={cb_r2:.3f}, "
                       f"KGE={cb_kge:.3f}, OLS R²={ols_r2:.3f}")

            log_step("validate_site", site_id=site_id, param=param_name,
                     n_samples=len(assembled), catboost_r2=round(cb_r2, 4),
                     catboost_kge=round(cb_kge, 4), ols_r2=round(ols_r2, 4) if not np.isnan(ols_r2) else None)

            all_results.append({
                "site_id": site_id,
                "param": param_name,
                "n_samples": len(assembled),
                "catboost_r2_log": cb_r2,
                "catboost_kge_log": cb_kge,
                "catboost_rmse_log": cb_rmse,
                "per_site_ols_r2_log": ols_r2,
            })

    # Summary
    if all_results:
        results_df = pd.DataFrame(all_results)
        results_df.to_parquet(DATA_DIR / "results" / "external_validation.parquet", index=False)

        logger.info(f"\n{'='*60}")
        logger.info("EXTERNAL VALIDATION SUMMARY")
        logger.info(f"{'='*60}")

        for param in ["ssc", "total_phosphorus"]:
            subset = results_df[results_df["param"] == param]
            if len(subset) == 0:
                continue
            logger.info(f"\n{param}:")
            logger.info(f"  Sites tested: {len(subset)}")
            logger.info(f"  CatBoost median R² (log): {subset['catboost_r2_log'].median():.3f}")
            logger.info(f"  CatBoost median KGE (log): {subset['catboost_kge_log'].median():.3f}")
            logger.info(f"  Per-site OLS median R² (log): {subset['per_site_ols_r2_log'].median():.3f}")
            logger.info(f"  CatBoost wins: {(subset['catboost_r2_log'] > subset['per_site_ols_r2_log']).sum()}/{len(subset)}")

            for _, row in subset.iterrows():
                winner = "CB" if row["catboost_r2_log"] > row["per_site_ols_r2_log"] else "OLS"
                logger.info(f"    {row['site_id']}: CB={row['catboost_r2_log']:.3f} "
                           f"OLS={row['per_site_ols_r2_log']:.3f} [{winner}] n={row['n_samples']}")

        logger.info(f"\nSaved: data/results/external_validation.parquet")

    if all_predictions:
        pred_df = pd.concat(all_predictions, ignore_index=True)
        pred_path = DATA_DIR / "results" / "external_validation_predictions.parquet"
        pred_df.to_parquet(pred_path, index=False)
        log_file(pred_path, role="output")
        logger.info(f"Saved per-sample predictions: {pred_path} ({len(pred_df)} rows)")

    end_run()


if __name__ == "__main__":
    main()
