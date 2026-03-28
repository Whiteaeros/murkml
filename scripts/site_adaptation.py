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
    python scripts/site_adaptation.py --temporal
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

from murkml.evaluate.metrics import safe_inv_boxcox1p

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"


def _forward_transform(y_native, transform_type, lmbda):
    """Transform native SSC values to model space."""
    if transform_type == "log1p" or transform_type is None:
        return np.log1p(y_native)
    elif transform_type == "boxcox":
        from scipy.special import boxcox1p
        return boxcox1p(y_native, lmbda)
    elif transform_type == "sqrt":
        return np.sqrt(y_native)
    elif transform_type == "none":
        return y_native.copy()
    else:
        return np.log1p(y_native)


def _inverse_transform(y_transformed, transform_type, lmbda):
    """Back-transform from model space to native SSC."""
    if transform_type == "log1p" or transform_type is None:
        return np.expm1(y_transformed)
    elif transform_type == "boxcox":
        return safe_inv_boxcox1p(y_transformed, lmbda)
    elif transform_type == "sqrt":
        return np.square(y_transformed)
    elif transform_type == "none":
        return y_transformed.copy()
    else:
        return np.expm1(y_transformed)


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

    # Merge all basic attrs that the model expects (includes lat/lon added in Batch A)
    basic_cols_available = [c for c in basic_attrs.columns if c != "site_id"]
    holdout_data = holdout_data.merge(
        basic_attrs[["site_id"] + basic_cols_available].drop_duplicates("site_id"),
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

    # Build output — transform-aware
    transform_type = meta.get("transform_type", "log1p")
    lmbda = meta.get("transform_lmbda")
    native_vals = holdout_data["lab_value"].values

    result = pd.DataFrame({
        "site_id": holdout_data["site_id"].values,
        "sample_time": holdout_data["sample_time"].values if "sample_time" in holdout_data.columns else np.nan,
        "y_true_log": _forward_transform(native_vals, transform_type, lmbda),
        "y_pred_log": y_pred_log,
        "y_true_native": native_vals,
        "y_pred_native": np.clip(_inverse_transform(y_pred_log, transform_type, lmbda), 0, None),
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

    # Median absolute percentage error (robust to outliers)
    nonzero = y_true_native > 0
    if nonzero.sum() > 0:
        ape = np.abs(y_pred_native[nonzero] - y_true_native[nonzero]) / y_true_native[nonzero]
        mape = float(np.median(ape) * 100)
        # Fraction of predictions within factor of 2
        ratio = y_pred_native[nonzero] / y_true_native[nonzero]
        f2 = float(np.mean((ratio >= 0.5) & (ratio <= 2.0)))
    else:
        mape = np.nan
        f2 = np.nan

    return {
        "r2_native": float(r2),
        "native_slope": float(slope),
        "rmse_native": float(rmse),
        "kge_native": float(kge),
        "mape_pct": mape,
        "frac_within_2x": f2,
    }


def _fit_and_evaluate(cal, test, site_id, N, trial, transform_type="log1p", lmbda=None):
    """Fit log-space correction on cal set, evaluate on test set, return result dict."""
    if N == 1:
        a = 1.0
        b = float(cal["y_true_log"].values[0] - cal["y_pred_log"].values[0])
    else:
        try:
            a, b, _, _, _ = linregress(
                cal["y_pred_log"].values, cal["y_true_log"].values
            )
            a = np.clip(a, 0.1, 10.0)
        except Exception:
            a, b = 1.0, 0.0

    corrected_log = a * test["y_pred_log"].values + b
    corrected_native = _inverse_transform(corrected_log, transform_type, lmbda)
    corrected_native = np.clip(corrected_native, 0, None)

    # Snowdon BCF
    cal_corrected_native = _inverse_transform(a * cal["y_pred_log"].values + b, transform_type, lmbda)
    cal_corrected_native = np.clip(cal_corrected_native, 1e-6, None)
    cal_true_mean = np.mean(cal["y_true_native"].values)
    cal_pred_mean = np.mean(cal_corrected_native)
    bcf = cal_true_mean / cal_pred_mean if cal_pred_mean > 0 else 1.0
    bcf = np.clip(bcf, 0.1, 10.0)
    corrected_native *= bcf

    metrics = compute_site_metrics(test["y_true_native"].values, corrected_native)

    return {
        "site_id": site_id,
        "n_cal": N,
        "trial": trial,
        "n_test": len(test),
        "correction_a": a,
        "correction_b": b,
        "bcf": bcf,
        **metrics,
    }


def run_adaptation_experiment(predictions, n_trials=50, temporal=False,
                              transform_type="log1p", lmbda=None):
    """Run the site-adaptive correction experiment.

    Parameters
    ----------
    temporal : bool
        If True, use temporal ordering (first N chronologically) instead of
        random Monte Carlo splits. Only 1 trial per N since the split is
        deterministic.
    transform_type : str
        Target transform used by the model ('log1p', 'boxcox', 'sqrt', 'none').
    lmbda : float or None
        Box-Cox lambda value (required for boxcox transform).
    """
    N_VALUES = [0, 1, 2, 3, 5, 10, 20]
    rng = np.random.default_rng(42)
    split_label = "temporal" if temporal else "random"

    if temporal:
        has_time = (
            "sample_time" in predictions.columns
            and predictions["sample_time"].notna().any()
        )
        if not has_time:
            logger.error("Temporal mode requested but sample_time is missing or all NaN")
            return pd.DataFrame()
        logger.info("Using TEMPORAL splits (first N chronologically for calibration)")

    results = []
    sites = predictions["site_id"].unique()
    trials_desc = "1 trial (deterministic)" if temporal else f"{n_trials} trials"
    logger.info(f"Running {split_label} adaptation: {len(sites)} sites, {trials_desc} per N")

    for site_idx, site_id in enumerate(sites):
        site_data = predictions[predictions["site_id"] == site_id].copy()
        if temporal:
            site_data = site_data.sort_values("sample_time").reset_index(drop=True)
        else:
            site_data = site_data.reset_index(drop=True)
        n_samples = len(site_data)

        if site_idx % 10 == 0:
            logger.info(f"  Site {site_idx+1}/{len(sites)} ({site_id}, {n_samples} samples)")

        for N in N_VALUES:
            if N >= n_samples - 2:
                continue

            if N == 0:
                metrics = compute_site_metrics(
                    site_data["y_true_native"].values,
                    site_data["y_pred_native"].values,
                )
                results.append({
                    "site_id": site_id,
                    "n_cal": 0,
                    "trial": 0,
                    "n_test": n_samples,
                    "split_type": split_label,
                    **metrics,
                })
                continue

            if temporal:
                # Deterministic: first N samples for cal, rest for test
                cal = site_data.iloc[:N]
                test = site_data.iloc[N:]
                row = _fit_and_evaluate(cal, test, site_id, N, trial=0,
                                       transform_type=transform_type, lmbda=lmbda)
                row["split_type"] = split_label
                results.append(row)
            else:
                for trial in range(n_trials):
                    cal_idx = rng.choice(n_samples, N, replace=False)
                    test_idx = np.setdiff1d(np.arange(n_samples), cal_idx)
                    cal = site_data.iloc[cal_idx]
                    test = site_data.iloc[test_idx]
                    row = _fit_and_evaluate(cal, test, site_id, N, trial,
                                           transform_type=transform_type, lmbda=lmbda)
                    row["split_type"] = split_label
                    results.append(row)

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


def _print_effort_curve(summary, label):
    """Print a calibration effort curve table."""
    logger.info("\n" + "=" * 60)
    logger.info(f"CALIBRATION EFFORT CURVE — {label}")
    logger.info("=" * 60)
    logger.info(f"\n{'N_cal':>5}  {'Sites':>5}  {'R²(native)':>20}  {'Slope':>20}  {'RMSE':>8}  {'KGE':>6}")
    logger.info("-" * 75)
    for _, row in summary.iterrows():
        n = int(row["n_cal"])
        r2_str = f"{row['r2_native_median']:.3f} [{row['r2_native_q25']:.3f}-{row['r2_native_q75']:.3f}]"
        slope_str = f"{row['slope_median']:.3f} [{row['slope_q25']:.3f}-{row['slope_q75']:.3f}]"
        logger.info(f"{n:>5}  {int(row['n_sites']):>5}  {r2_str:>20}  {slope_str:>20}  {row['rmse_median']:>8.1f}  {row['kge_median']:>6.3f}")


def _print_comparison(summary_random, summary_temporal):
    """Print side-by-side comparison of random vs temporal splits."""
    logger.info("\n" + "=" * 60)
    logger.info("COMPARISON: RANDOM vs TEMPORAL")
    logger.info("=" * 60)
    logger.info(f"\n{'N_cal':>5}  {'R²_random':>10}  {'R²_temporal':>12}  {'KGE_random':>11}  {'KGE_temporal':>13}")
    logger.info("-" * 60)

    n_values = sorted(set(summary_random["n_cal"]) | set(summary_temporal["n_cal"]))
    for n in n_values:
        n = int(n)
        r_row = summary_random[summary_random["n_cal"] == n]
        t_row = summary_temporal[summary_temporal["n_cal"] == n]
        r2_r = f"{r_row['r2_native_median'].values[0]:.3f}" if not r_row.empty else "   —"
        r2_t = f"{t_row['r2_native_median'].values[0]:.3f}" if not t_row.empty else "   —"
        kge_r = f"{r_row['kge_median'].values[0]:.3f}" if not r_row.empty else "   —"
        kge_t = f"{t_row['kge_median'].values[0]:.3f}" if not t_row.empty else "   —"
        logger.info(f"{n:>5}  {r2_r:>10}  {r2_t:>12}  {kge_r:>11}  {kge_t:>13}")


def main():
    parser = argparse.ArgumentParser(description="Site-adaptive fine-tuning experiment")
    parser.add_argument("--n-trials", type=int, default=50,
                        help="Monte Carlo trials per N value (default: 50)")
    parser.add_argument("--temporal", action="store_true",
                        help="Use temporal ordering (first N chronologically) instead of random splits")
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

    # Step 2: Run adaptation experiment(s)
    results_dir = DATA_DIR / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    # Extract transform info from model metadata
    transform_type = meta.get("transform_type", "log1p")
    lmbda = meta.get("transform_lmbda")
    logger.info(f"Transform: {transform_type}, lambda: {lmbda}")

    # Always run random splits
    results_random = run_adaptation_experiment(
        predictions, n_trials=args.n_trials, temporal=False,
        transform_type=transform_type, lmbda=lmbda)
    summary_random = summarize_results(results_random)

    _print_effort_curve(summary_random, "RANDOM SPLIT")

    if args.temporal:
        # Also run temporal splits
        results_temporal = run_adaptation_experiment(
            predictions, n_trials=args.n_trials, temporal=True,
            transform_type=transform_type, lmbda=lmbda)

        if not results_temporal.empty:
            summary_temporal = summarize_results(results_temporal)
            _print_effort_curve(summary_temporal, "TEMPORAL SPLIT")

            # Side-by-side comparison
            _print_comparison(summary_random, summary_temporal)

            # Combine both into one output
            results_df = pd.concat([results_random, results_temporal], ignore_index=True)
        else:
            logger.warning("Temporal experiment returned no results; saving random only")
            results_df = results_random
    else:
        results_df = results_random

    # Step 3: Save results
    curve_path = results_dir / "site_adaptation_curve.parquet"
    results_df.to_parquet(curve_path, index=False)
    logger.info(f"\nFull results: {curve_path} ({len(results_df)} rows)")

    summary_path = results_dir / "site_adaptation_summary.parquet"
    # Save per-split-type summary
    summaries = []
    for split_type in results_df["split_type"].unique():
        s = summarize_results(results_df[results_df["split_type"] == split_type])
        s["split_type"] = split_type
        summaries.append(s)
    summary_combined = pd.concat(summaries, ignore_index=True)
    summary_combined.to_parquet(summary_path, index=False)
    logger.info(f"Summary: {summary_path}")

    # Key takeaway (from random split)
    baseline_r2 = summary_random[summary_random["n_cal"] == 0]["r2_native_median"].values
    if len(baseline_r2) > 0:
        baseline_r2 = baseline_r2[0]
        for n in [5, 10, 20]:
            row = summary_random[summary_random["n_cal"] == n]
            if not row.empty:
                adapted_r2 = row["r2_native_median"].values[0]
                logger.info(f"\n  {n} calibration samples: R²(native) {baseline_r2:.3f} → {adapted_r2:.3f}")

    logger.info("\nDone.")


if __name__ == "__main__":
    main()
