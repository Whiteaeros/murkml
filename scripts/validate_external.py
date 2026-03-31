#!/usr/bin/env python
"""Validate the v4 model on external (non-USGS) paired turbidity-SSC data.

Loads external data from download_external_validation.py output, formats it
for our CatBoost model (turbidity_instant from grab samples, everything else
NaN), runs predictions, and reports metrics in two buckets:
  - NTU < 400: fair comparison (NTU ≈ FNU in this range)
  - NTU >= 400: supplementary (NTU-FNU divergence makes this unreliable)

Usage:
    python scripts/validate_external.py
    python scripts/validate_external.py --model data/results/models/ssc_C_sensor_basic_watershed.cbm
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool
from scipy.special import boxcox1p

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from murkml.evaluate.metrics import safe_inv_boxcox1p

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)


def compute_metrics(y_true, y_pred):
    """Compute R²/NSE, log-NSE, RMSE, MAPE, within-2x, bias."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    valid = np.isfinite(y_true) & np.isfinite(y_pred) & (y_true > 0) & (y_pred > 0)
    y_true, y_pred = y_true[valid], y_pred[valid]
    n = len(y_true)
    if n < 2:
        return {"n": n}

    # NSE (= R² for our computation)
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    nse = 1 - ss_res / ss_tot if ss_tot > 1e-10 else np.nan

    # Log-NSE
    log_true, log_pred = np.log(y_true), np.log(y_pred)
    ss_res_log = np.sum((log_true - log_pred) ** 2)
    ss_tot_log = np.sum((log_true - np.mean(log_true)) ** 2)
    log_nse = 1 - ss_res_log / ss_tot_log if ss_tot_log > 1e-10 else np.nan

    rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))

    # MAPE
    pct_err = np.abs(y_true - y_pred) / y_true * 100
    mape = float(np.median(pct_err))

    # Within 2x
    ratio = y_pred / y_true
    within_2x = float(np.mean((ratio >= 0.5) & (ratio <= 2.0)) * 100)

    # Bias
    bias_pct = float((np.mean(y_pred) - np.mean(y_true)) / np.mean(y_true) * 100)

    # Spearman rank correlation
    from scipy.stats import spearmanr
    rho, _ = spearmanr(y_true, y_pred)

    return {
        "n": n,
        "nse": float(nse),
        "log_nse": float(log_nse),
        "rmse": float(rmse),
        "mape_pct": float(mape),
        "within_2x_pct": float(within_2x),
        "bias_pct": float(bias_pct),
        "spearman_rho": float(rho),
        "mean_true": float(np.mean(y_true)),
        "mean_pred": float(np.mean(y_pred)),
        "median_abs_error": float(np.median(np.abs(y_true - y_pred))),
    }


def main():
    parser = argparse.ArgumentParser(description="Validate model on external data")
    parser.add_argument("--model", type=str,
                        default=str(DATA_DIR / "results/models/ssc_C_sensor_basic_watershed.cbm"))
    parser.add_argument("--meta", type=str,
                        default=str(DATA_DIR / "results/models/ssc_C_sensor_basic_watershed_meta.json"))
    parser.add_argument("--external-data", type=str,
                        default=str(DATA_DIR / "external_validation/filtered_external.parquet"))
    parser.add_argument("--output-dir", type=str,
                        default=str(DATA_DIR / "results/external_validation"))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load model and metadata
    logger.info("Loading model...")
    model = CatBoostRegressor()
    model.load_model(args.model)

    with open(args.meta) as f:
        meta = json.load(f)

    feature_cols = meta["feature_cols"]
    cat_cols = meta.get("cat_cols", [])
    cat_indices = meta.get("cat_indices", [])
    train_median = meta.get("train_median", {})
    transform_type = meta.get("transform_type", "log1p")
    lmbda = meta.get("transform_lmbda", None)
    bcf = meta.get("bcf", 1.0)

    logger.info(f"Model: {len(feature_cols)} features, transform={transform_type}, "
                f"lambda={lmbda}, BCF={bcf:.4f}")

    # Load external data
    logger.info(f"Loading external data from {args.external_data}...")
    ext = pd.read_parquet(args.external_data)
    logger.info(f"  {len(ext)} samples, {ext['site_id'].nunique()} sites")
    logger.info(f"  Turbidity units: {ext['turb_unit'].value_counts().to_dict()}")

    # Build feature matrix — turbidity_instant from their grab sample, everything else NaN
    logger.info("Building feature matrix...")
    X = pd.DataFrame(index=ext.index)
    for col in feature_cols:
        if col == "turbidity_instant":
            X[col] = ext["turb_value"].values
        elif col in train_median:
            # Fill with NaN — CatBoost handles it
            X[col] = np.nan
        elif col in cat_cols:
            X[col] = "unknown"
        else:
            X[col] = np.nan

    # Fill categorical features
    for col in cat_cols:
        if col == "sensor_family":
            X[col] = "unknown"  # NTU sensors not in our training categories
        elif col == "collection_method":
            X[col] = "grab"  # external samples are grab samples
        elif col == "turb_source":
            X[col] = "discrete"  # grab-sample turbidity, not continuous
        else:
            X[col] = "unknown"

    # Try to add watershed features from StreamCat by matching coordinates
    if "latitude" in ext.columns and "longitude" in ext.columns:
        try:
            from murkml.data.attributes import load_streamcat_attrs
            ws = load_streamcat_attrs(DATA_DIR)
            our_attrs = pd.read_parquet(DATA_DIR / "site_attributes.parquet")
            our_coords = our_attrs[["site_id", "latitude", "longitude"]].dropna()

            # For each external site, find nearest USGS site and use its watershed features
            ext_coords = ext[["site_id", "latitude", "longitude"]].drop_duplicates("site_id")
            ext_coords = ext_coords.dropna(subset=["latitude", "longitude"])

            matches = {}
            for _, erow in ext_coords.iterrows():
                dists = np.sqrt(
                    (our_coords["latitude"] - erow["latitude"])**2 +
                    (our_coords["longitude"] - erow["longitude"])**2
                )
                nearest_idx = dists.idxmin()
                nearest_dist = dists[nearest_idx]
                if nearest_dist < 0.5:  # ~50 km — generous for watershed similarity
                    matches[erow["site_id"]] = our_coords.loc[nearest_idx, "site_id"]

            logger.info(f"  Matched {len(matches)}/{len(ext_coords)} external sites to nearby USGS sites")

            # Fill watershed features from matched USGS sites
            if matches:
                ext_to_usgs = ext["site_id"].map(matches)
                ws_features = [c for c in feature_cols if c in ws.columns and c != "site_id"]
                ws_indexed = ws.set_index("site_id")
                for col in ws_features:
                    if col in ws_indexed.columns:
                        mapped_vals = ext_to_usgs.map(
                            ws_indexed[col].to_dict()
                        )
                        X[col] = mapped_vals.values

        except Exception as e:
            logger.warning(f"  Could not match watershed features: {e}")

    # Ensure no NaN in categorical features (CatBoost rejects them)
    for col in cat_cols:
        if col in X.columns and X[col].isna().any():
            X[col] = X[col].fillna("missing").astype(str)

    # Compute derived features if needed
    if "log_drainage_area" in feature_cols and "log_drainage_area" not in X.columns:
        if "drainage_area_km2" in X.columns:
            X["log_drainage_area"] = np.log1p(X["drainage_area_km2"].clip(lower=0))
        else:
            X["log_drainage_area"] = np.nan

    # Make predictions
    logger.info("Running predictions...")
    pool = Pool(X, cat_features=cat_indices)
    y_pred_ms = model.predict(pool)

    # Back-transform
    if transform_type == "boxcox":
        y_pred_native = safe_inv_boxcox1p(y_pred_ms, lmbda) * bcf
    elif transform_type == "log1p":
        y_pred_native = np.expm1(y_pred_ms) * bcf
    else:
        y_pred_native = y_pred_ms * bcf

    y_pred_native = np.clip(y_pred_native, 0, None)
    y_true = ext["ssc_value"].values

    # Results
    ext_results = ext.copy()
    ext_results["y_pred_native"] = y_pred_native
    ext_results["y_true_native"] = y_true

    # Split by turbidity threshold
    low_mask = ext_results["turb_value"] < 400
    high_mask = ext_results["turb_value"] >= 400

    logger.info("\n" + "=" * 70)
    logger.info("EXTERNAL VALIDATION RESULTS")
    logger.info("=" * 70)

    # Overall (all data)
    logger.info(f"\n--- ALL DATA ({len(ext_results)} samples, {ext_results['site_id'].nunique()} sites) ---")
    m_all = compute_metrics(y_true, y_pred_native)
    for k, v in m_all.items():
        logger.info(f"  {k}: {v}")

    # NTU < 400 (fair comparison)
    low_data = ext_results[low_mask]
    logger.info(f"\n--- NTU < 400 (MAIN RESULTS) ({len(low_data)} samples, {low_data['site_id'].nunique()} sites) ---")
    m_low = compute_metrics(low_data["y_true_native"], low_data["y_pred_native"])
    for k, v in m_low.items():
        logger.info(f"  {k}: {v}")

    # NTU >= 400 (supplementary — known NTU-FNU divergence)
    high_data = ext_results[high_mask]
    logger.info(f"\n--- NTU >= 400 (SUPPLEMENTARY — NTU-FNU divergence) ({len(high_data)} samples, {high_data['site_id'].nunique()} sites) ---")
    if len(high_data) > 1:
        m_high = compute_metrics(high_data["y_true_native"], high_data["y_pred_native"])
        for k, v in m_high.items():
            logger.info(f"  {k}: {v}")
    else:
        logger.info("  Insufficient samples")
        m_high = {}

    # By organization
    logger.info(f"\n--- BY ORGANIZATION (NTU < 400 only) ---")
    org_results = {}
    for org, gdf in low_data.groupby("org_id"):
        m = compute_metrics(gdf["y_true_native"], gdf["y_pred_native"])
        org_results[org] = m
        logger.info(f"  {org:20s}  n={m.get('n',0):5d}  NSE={m.get('nse',float('nan')):+.3f}  "
                    f"MAPE={m.get('mape_pct',float('nan')):5.1f}%  "
                    f"2x={m.get('within_2x_pct',float('nan')):5.1f}%  "
                    f"bias={m.get('bias_pct',float('nan')):+.1f}%")

    # Save results
    ext_results.to_parquet(output_dir / "external_predictions.parquet", index=False)

    summary = {
        "all_data": m_all,
        "ntu_below_400": m_low,
        "ntu_above_400": m_high,
        "by_organization": org_results,
        "n_total": len(ext_results),
        "n_below_400": int(low_mask.sum()),
        "n_above_400": int(high_mask.sum()),
        "n_sites": int(ext_results["site_id"].nunique()),
        "n_watershed_matched": len(matches) if "matches" in dir() else 0,
    }
    with open(output_dir / "external_validation_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    logger.info(f"\nSaved to {output_dir}/")


if __name__ == "__main__":
    main()
