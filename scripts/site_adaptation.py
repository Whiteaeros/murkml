"""Site-adaptive fine-tuning experiment.

Evaluates how many local grab samples a new site needs to achieve
good SSC predictions using the global model as a prior.

For each holdout site:
1. Generate predictions using the final trained model
2. Simulate having N calibration samples (N=0,1,2,3,5,10,20)
3. Fit a 2-parameter log-space correction per site
4. Evaluate on remaining samples
5. Build calibration effort curve

Usage:
    python scripts/site_adaptation.py
    python scripts/site_adaptation.py --n-trials 100
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import linregress

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"


def load_model_and_meta():
    """Load the final CatBoost model and its metadata."""
    from catboost import CatBoostRegressor

    model_path = DATA_DIR / "results" / "models" / "ssc_C_sensor_basic_watershed.cbm"
    meta_path = DATA_DIR / "results" / "models" / "ssc_C_sensor_basic_watershed_meta.json"

    model = CatBoostRegressor()
    model.load_model(str(model_path))

    with open(meta_path) as f:
        meta = json.load(f)

    logger.info(f"Loaded model: {model.tree_count_} trees, {len(meta['feature_cols'])} features")
    return model, meta


def generate_holdout_predictions(model, meta):
    """Generate predictions for all holdout sites using the final model."""
    paired = pd.read_parquet(DATA_DIR / "processed" / "turbidity_ssc_paired.parquet")
    split = pd.read_parquet(DATA_DIR / "train_holdout_split.parquet")

    holdout_ids = set(split[split["role"] == "holdout"]["site_id"])
    holdout_data = paired[paired["site_id"].isin(holdout_ids)].copy()

    logger.info(f"Holdout sites in paired data: {holdout_data['site_id'].nunique()}")
    logger.info(f"Holdout samples: {len(holdout_data)}")

    if holdout_data.empty:
        logger.error("No holdout data found!")
        return pd.DataFrame()

    # Merge watershed attributes (not in paired dataset, added during tier building)
    from murkml.data.attributes import load_streamcat_attrs
    ws_attrs = load_streamcat_attrs(DATA_DIR)
    basic_attrs = pd.read_parquet(DATA_DIR / "site_attributes.parquet")

    holdout_data = holdout_data.merge(
        basic_attrs[["site_id", "altitude_ft", "drainage_area_km2", "huc2"]].drop_duplicates("site_id"),
        on="site_id", how="left",
    )
    # Drop basic cols that overlap with StreamCat before merging
    ws_cols = set(ws_attrs.columns) - {"site_id"}
    for col in ["drainage_area_km2", "huc2", "slope_pct"]:
        if col in holdout_data.columns and col in ws_cols:
            holdout_data = holdout_data.drop(columns=[col])

    holdout_data = holdout_data.merge(ws_attrs, on="site_id", how="left")
    logger.info(f"After attribute merge: {len(holdout_data)} rows, {len(holdout_data.columns)} cols")

    feature_cols = meta["feature_cols"]
    cat_cols = meta["cat_cols"]
    num_cols = [c for c in feature_cols if c not in cat_cols]

    # Check which features are available
    missing_feats = [c for c in feature_cols if c not in holdout_data.columns]
    if missing_feats:
        logger.warning(f"Missing features (will fill with NaN): {missing_feats}")
        for c in missing_feats:
            holdout_data[c] = np.nan

    # Prepare features
    X = holdout_data[feature_cols].copy()

    # Fill NaN in numeric cols with training medians
    train_median = meta.get("train_median", {})
    for col in num_cols:
        if col in X.columns and col in train_median:
            X[col] = X[col].fillna(train_median[col])

    # Fill NaN in categorical cols
    for col in cat_cols:
        if col in X.columns:
            X[col] = X[col].fillna("missing").astype(str)

    # Generate predictions
    from catboost import Pool
    cat_indices = [feature_cols.index(c) for c in cat_cols]
    pool = Pool(X, cat_features=cat_indices)
    y_pred_log = model.predict(pool)

    # Build output
    result = pd.DataFrame({
        "site_id": holdout_data["site_id"].values,
        "sample_time": holdout_data["sample_time"].values if "sample_time" in holdout_data.columns else np.nan,
        "y_true_log": np.log1p(holdout_data["lab_value"].values),
        "y_pred_log": y_pred_log,
        "y_true_native": holdout_data["lab_value"].values,
        "y_pred_native": np.expm1(y_pred_log),
    })

    logger.info(f"Generated {len(result)} predictions for {result['site_id'].nunique()} holdout sites")
    return result


def compute_site_metrics(y_true_native, y_pred_native):
    """Compute native-space metrics for a single site."""
    if len(y_true_native) < 3:
        return {"r2_native": np.nan, "native_slope": np.nan,
                "rmse_native": np.nan, "kge_native": np.nan}

    # R² and slope
    ss_res = np.sum((y_true_native - y_pred_native) ** 2)
    ss_tot = np.sum((y_true_native - np.mean(y_true_native)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan

    try:
        slope, _, r, _, _ = linregress(y_true_native, y_pred_native)
    except ValueError:
        slope, r = np.nan, np.nan

    # RMSE
    rmse = np.sqrt(np.mean((y_true_native - y_pred_native) ** 2))

    # KGE
    try:
        r_corr = np.corrcoef(y_true_native, y_pred_native)[0, 1] if len(y_true_native) > 2 else np.nan
    except Exception:
        r_corr = np.nan
    alpha = np.std(y_pred_native) / np.std(y_true_native) if np.std(y_true_native) > 0 else np.nan
    beta = np.mean(y_pred_native) / np.mean(y_true_native) if np.mean(y_true_native) > 0 else np.nan
    kge = 1 - np.sqrt((r_corr - 1)**2 + (alpha - 1)**2 + (beta - 1)**2) if not np.isnan(r_corr) else np.nan

    return {
        "r2_native": float(r2),
        "native_slope": float(slope),
        "rmse_native": float(rmse),
        "kge_native": float(kge),
    }


def run_adaptation_experiment(predictions, n_trials=50):
    """Run the site-adaptive correction experiment."""
    N_VALUES = [0, 1, 2, 3, 5, 10, 20]
    rng = np.random.default_rng(42)

    results = []
    sites = predictions["site_id"].unique()
    logger.info(f"Running adaptation experiment: {len(sites)} sites, {n_trials} trials per N")

    for site_idx, site_id in enumerate(sites):
        site_data = predictions[predictions["site_id"] == site_id].reset_index(drop=True)
        n_samples = len(site_data)

        if site_idx % 10 == 0:
            logger.info(f"  Site {site_idx+1}/{len(sites)} ({site_id}, {n_samples} samples)")

        for N in N_VALUES:
            # Need at least 3 test samples for meaningful metrics
            if N >= n_samples - 2:
                continue

            if N == 0:
                # Baseline: no correction
                metrics = compute_site_metrics(
                    site_data["y_true_native"].values,
                    site_data["y_pred_native"].values,
                )
                results.append({
                    "site_id": site_id,
                    "n_cal": 0,
                    "trial": 0,
                    "n_test": n_samples,
                    **metrics,
                })
                continue

            for trial in range(n_trials):
                # Random split
                cal_idx = rng.choice(n_samples, N, replace=False)
                test_idx = np.setdiff1d(np.arange(n_samples), cal_idx)

                cal = site_data.iloc[cal_idx]
                test = site_data.iloc[test_idx]

                # Fit log-space correction
                if N == 1:
                    # Only intercept (1 point can't determine slope)
                    a = 1.0
                    b = float(cal["y_true_log"].values[0] - cal["y_pred_log"].values[0])
                else:
                    # OLS: y_true_log = a * y_pred_log + b
                    try:
                        a, b, _, _, _ = linregress(
                            cal["y_pred_log"].values, cal["y_true_log"].values
                        )
                        # Sanity: clamp extreme slopes
                        a = np.clip(a, 0.1, 10.0)
                    except Exception:
                        a, b = 1.0, 0.0

                # Apply correction to test set
                corrected_log = a * test["y_pred_log"].values + b
                corrected_native = np.expm1(corrected_log)
                corrected_native = np.clip(corrected_native, 0, None)

                # Snowdon BCF from calibration data
                cal_corrected_native = np.expm1(a * cal["y_pred_log"].values + b)
                cal_corrected_native = np.clip(cal_corrected_native, 1e-6, None)
                cal_true_mean = np.mean(cal["y_true_native"].values)
                cal_pred_mean = np.mean(cal_corrected_native)
                bcf = cal_true_mean / cal_pred_mean if cal_pred_mean > 0 else 1.0
                bcf = np.clip(bcf, 0.1, 10.0)  # sanity clamp
                corrected_native *= bcf

                # Metrics on test set
                metrics = compute_site_metrics(
                    test["y_true_native"].values,
                    corrected_native,
                )

                results.append({
                    "site_id": site_id,
                    "n_cal": N,
                    "trial": trial,
                    "n_test": len(test),
                    "correction_a": a,
                    "correction_b": b,
                    "bcf": bcf,
                    **metrics,
                })

    return pd.DataFrame(results)


def summarize_results(results_df):
    """Build calibration effort curve summary."""
    summary = results_df.groupby("n_cal").agg(
        r2_native_median=("r2_native", "median"),
        r2_native_q25=("r2_native", lambda x: np.nanpercentile(x, 25)),
        r2_native_q75=("r2_native", lambda x: np.nanpercentile(x, 75)),
        slope_median=("native_slope", "median"),
        slope_q25=("native_slope", lambda x: np.nanpercentile(x, 25)),
        slope_q75=("native_slope", lambda x: np.nanpercentile(x, 75)),
        rmse_median=("rmse_native", "median"),
        kge_median=("kge_native", "median"),
        n_sites=("site_id", "nunique"),
    ).reset_index()

    return summary


def main():
    parser = argparse.ArgumentParser(description="Site-adaptive fine-tuning experiment")
    parser.add_argument("--n-trials", type=int, default=50,
                        help="Monte Carlo trials per N value (default: 50)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("SITE-ADAPTIVE FINE-TUNING EXPERIMENT")
    logger.info("=" * 60)

    # Step 1: Load model and generate holdout predictions
    model, meta = load_model_and_meta()
    predictions = generate_holdout_predictions(model, meta)

    if predictions.empty:
        logger.error("No predictions generated. Exiting.")
        return

    # Step 2: Run adaptation experiment
    results_df = run_adaptation_experiment(predictions, n_trials=args.n_trials)

    # Step 3: Summarize
    summary = summarize_results(results_df)

    # Print calibration effort curve
    logger.info("\n" + "=" * 60)
    logger.info("CALIBRATION EFFORT CURVE")
    logger.info("=" * 60)
    logger.info(f"\n{'N_cal':>5}  {'Sites':>5}  {'R²(native)':>20}  {'Slope':>20}  {'RMSE':>8}  {'KGE':>6}")
    logger.info("-" * 75)
    for _, row in summary.iterrows():
        n = int(row["n_cal"])
        r2_str = f"{row['r2_native_median']:.3f} [{row['r2_native_q25']:.3f}-{row['r2_native_q75']:.3f}]"
        slope_str = f"{row['slope_median']:.3f} [{row['slope_q25']:.3f}-{row['slope_q75']:.3f}]"
        logger.info(f"{n:>5}  {int(row['n_sites']):>5}  {r2_str:>20}  {slope_str:>20}  {row['rmse_median']:>8.1f}  {row['kge_median']:>6.3f}")

    # Step 4: Save results
    results_dir = DATA_DIR / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    curve_path = results_dir / "site_adaptation_curve.parquet"
    results_df.to_parquet(curve_path, index=False)
    logger.info(f"\nFull results: {curve_path} ({len(results_df)} rows)")

    summary_path = results_dir / "site_adaptation_summary.parquet"
    summary.to_parquet(summary_path, index=False)
    logger.info(f"Summary: {summary_path}")

    # Key takeaway
    baseline_r2 = summary[summary["n_cal"] == 0]["r2_native_median"].values
    if len(baseline_r2) > 0:
        baseline_r2 = baseline_r2[0]
        for n in [5, 10, 20]:
            row = summary[summary["n_cal"] == n]
            if not row.empty:
                adapted_r2 = row["r2_native_median"].values[0]
                logger.info(f"\n  {n} calibration samples: R²(native) {baseline_r2:.3f} → {adapted_r2:.3f}")

    logger.info("\nDone.")


if __name__ == "__main__":
    main()
