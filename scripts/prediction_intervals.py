"""Conformal prediction intervals for the SSC model.

Uses LOGO CV out-of-fold predictions (honest — each prediction from a model
that never saw that site) to calibrate empirical conformal intervals, then
evaluates coverage on holdout sites.

This is split conformal prediction: the LOGO CV residuals from training sites
form the calibration set, and holdout site predictions are the test set.
With 9,800+ calibration points this gives tight, well-calibrated intervals.

All interval computation is done in log1p space, then bounds are
back-transformed via expm1().

Usage:
    python scripts/prediction_intervals.py
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = DATA_DIR / "results"


def load_logo_predictions() -> pd.DataFrame:
    """Load LOGO CV out-of-fold predictions for SSC Tier C model."""
    path = RESULTS_DIR / "logo_predictions_ssc_C_sensor_basic_watershed.parquet"
    df = pd.read_parquet(path)
    logger.info(f"Loaded LOGO predictions: {len(df)} rows, {df['site_id'].nunique()} sites")
    return df


def load_split() -> tuple[set[str], set[str]]:
    """Return (training_site_ids, holdout_site_ids)."""
    split = pd.read_parquet(DATA_DIR / "train_holdout_split.parquet")
    training = set(split[split["role"] == "training"]["site_id"])
    holdout = set(split[split["role"] == "holdout"]["site_id"])
    return training, holdout


def generate_holdout_predictions() -> pd.DataFrame:
    """Generate predictions for holdout sites using the final model.

    Reuses the same logic as site_adaptation.py.
    """
    from catboost import CatBoostRegressor, Pool
    from murkml.data.attributes import load_streamcat_attrs

    model_path = RESULTS_DIR / "models" / "ssc_C_sensor_basic_watershed.cbm"
    meta_path = RESULTS_DIR / "models" / "ssc_C_sensor_basic_watershed_meta.json"

    model = CatBoostRegressor()
    model.load_model(str(model_path))

    with open(meta_path) as f:
        meta = json.load(f)

    feature_cols = meta["feature_cols"]
    cat_cols = meta["cat_cols"]
    num_cols = [c for c in feature_cols if c not in cat_cols]

    # Load paired data and filter to holdout sites
    paired = pd.read_parquet(DATA_DIR / "processed" / "turbidity_ssc_paired.parquet")
    _, holdout_ids = load_split()
    holdout_data = paired[paired["site_id"].isin(holdout_ids)].copy()

    if holdout_data.empty:
        logger.error("No holdout data found!")
        return pd.DataFrame()

    # Merge attributes
    ws_attrs = load_streamcat_attrs(DATA_DIR)
    basic_attrs = pd.read_parquet(DATA_DIR / "site_attributes.parquet")
    # Merge all basic attrs that the model expects (includes lat/lon added in Batch A)
    basic_cols_available = [c for c in basic_attrs.columns if c != "site_id"]
    holdout_data = holdout_data.merge(
        basic_attrs[["site_id"] + basic_cols_available].drop_duplicates("site_id"),
        on="site_id", how="left",
    )
    ws_cols = set(ws_attrs.columns) - {"site_id"}
    for col in ["drainage_area_km2", "huc2", "slope_pct"]:
        if col in holdout_data.columns and col in ws_cols:
            holdout_data = holdout_data.drop(columns=[col])
    holdout_data = holdout_data.merge(ws_attrs, on="site_id", how="left")

    # Fill missing features
    missing_feats = [c for c in feature_cols if c not in holdout_data.columns]
    if missing_feats:
        logger.warning(f"Missing features (filling NaN): {missing_feats}")
        for c in missing_feats:
            holdout_data[c] = np.nan

    X = holdout_data[feature_cols].copy()
    train_median = meta.get("train_median", {})
    for col in num_cols:
        if col in X.columns and col in train_median:
            X[col] = X[col].fillna(train_median[col])
    for col in cat_cols:
        if col in X.columns:
            X[col] = X[col].fillna("missing").astype(str)

    cat_indices = [feature_cols.index(c) for c in cat_cols]
    pool = Pool(X, cat_features=cat_indices)
    y_pred_log = model.predict(pool)

    result = pd.DataFrame({
        "site_id": holdout_data["site_id"].values,
        "y_true_log": np.log1p(holdout_data["lab_value"].values),
        "y_pred_log": y_pred_log,
        "y_true_native_mgL": holdout_data["lab_value"].values,
        "y_pred_native_mgL": np.expm1(y_pred_log),
    })

    logger.info(
        f"Holdout predictions: {len(result)} rows, "
        f"{result['site_id'].nunique()} sites"
    )
    return result, model, meta


def empirical_conformal_intervals(
    cal_residuals: np.ndarray,
    y_pred_log: np.ndarray,
    alphas: list[float] = [0.05, 0.10],
) -> dict[float, tuple[np.ndarray, np.ndarray]]:
    """Compute prediction intervals from empirical residual quantiles.

    Uses the symmetric quantile approach: for confidence level (1-alpha),
    take the alpha/2 and 1-alpha/2 quantiles of (y_true - y_pred) residuals.

    Parameters
    ----------
    cal_residuals : array
        Log-space residuals (y_true_log - y_pred_log) from calibration set.
    y_pred_log : array
        Log-space predictions for test set.
    alphas : list of float
        Significance levels (0.05 = 95% CI, 0.10 = 90% CI).

    Returns
    -------
    dict mapping alpha -> (lower_native, upper_native) in mg/L.
    """
    intervals = {}
    for alpha in alphas:
        q_lo = np.percentile(cal_residuals, 100 * alpha / 2)
        q_hi = np.percentile(cal_residuals, 100 * (1 - alpha / 2))
        lower_log = y_pred_log + q_lo
        upper_log = y_pred_log + q_hi
        lower_native = np.clip(np.expm1(lower_log), 0, None)
        upper_native = np.expm1(upper_log)
        intervals[alpha] = (lower_native, upper_native)
    return intervals


def compute_coverage_metrics(
    y_true_native: np.ndarray,
    intervals: dict[float, tuple[np.ndarray, np.ndarray]],
) -> dict:
    """Compute coverage, interval width, and width ratio for each alpha."""
    metrics = {}
    for alpha, (lower, upper) in intervals.items():
        conf = int(100 * (1 - alpha))
        in_interval = (y_true_native >= lower) & (y_true_native <= upper)
        coverage = np.mean(in_interval)
        width = upper - lower
        # Avoid division by zero for width ratio
        safe_true = np.where(y_true_native > 0, y_true_native, np.nan)
        width_ratio = width / safe_true

        metrics[f"coverage_{conf}pct"] = float(coverage)
        metrics[f"median_width_{conf}pct_mgL"] = float(np.median(width))
        metrics[f"mean_width_{conf}pct_mgL"] = float(np.mean(width))
        metrics[f"median_width_ratio_{conf}pct"] = float(np.nanmedian(width_ratio))

    return metrics


def main():
    logger.info("=" * 60)
    logger.info("CONFORMAL PREDICTION INTERVALS FOR SSC MODEL")
    logger.info("=" * 60)

    # -- Load data --
    logo_preds = load_logo_predictions()
    training_ids, holdout_ids = load_split()

    # Split LOGO predictions into calibration (training sites) and test (holdout)
    logo_train = logo_preds[logo_preds["site_id"].isin(training_ids)].copy()
    logo_holdout = logo_preds[logo_preds["site_id"].isin(holdout_ids)].copy()

    logger.info(f"Calibration set (training sites): {len(logo_train)} samples, {logo_train['site_id'].nunique()} sites")
    logger.info(f"Test set (holdout sites in LOGO): {len(logo_holdout)} samples, {logo_holdout['site_id'].nunique()} sites")

    # Compute calibration residuals in log space
    cal_residuals = (logo_train["y_true_log"] - logo_train["y_pred_log"]).values

    logger.info(f"Calibration residuals — mean: {cal_residuals.mean():.4f}, "
                f"std: {cal_residuals.std():.4f}, "
                f"median: {np.median(cal_residuals):.4f}")

    # ============================================================
    # Compute empirical conformal intervals
    # ============================================================
    logger.info("\n" + "=" * 60)
    logger.info("EMPIRICAL SPLIT CONFORMAL INTERVALS")
    logger.info("=" * 60)

    alphas = [0.05, 0.10]

    # -- Evaluate on LOGO holdout predictions --
    emp_intervals_logo = empirical_conformal_intervals(
        cal_residuals,
        logo_holdout["y_pred_log"].values,
        alphas=alphas,
    )
    logo_metrics = compute_coverage_metrics(
        logo_holdout["y_true_native_mgL"].values,
        emp_intervals_logo,
    )
    logger.info("Coverage on LOGO holdout sites (out-of-fold):")
    for k, v in logo_metrics.items():
        logger.info(f"  {k}: {v:.4f}")

    # -- Generate and evaluate on final-model holdout predictions --
    holdout_preds, model, meta = generate_holdout_predictions()

    emp_intervals_holdout = empirical_conformal_intervals(
        cal_residuals,
        holdout_preds["y_pred_log"].values,
        alphas=alphas,
    )
    holdout_metrics = compute_coverage_metrics(
        holdout_preds["y_true_native_mgL"].values,
        emp_intervals_holdout,
    )
    logger.info("\nCoverage on holdout sites (final model predictions):")
    for k, v in holdout_metrics.items():
        logger.info(f"  {k}: {v:.4f}")

    # ============================================================
    # Build output DataFrame
    # ============================================================
    logger.info("\n" + "=" * 60)
    logger.info("SAVING RESULTS")
    logger.info("=" * 60)

    # Primary output: holdout predictions with empirical intervals
    out = holdout_preds.copy()
    for alpha in alphas:
        conf = int(100 * (1 - alpha))
        lower, upper = emp_intervals_holdout[alpha]
        out[f"lower_{conf}pct_mgL"] = lower
        out[f"upper_{conf}pct_mgL"] = upper

    out_path = RESULTS_DIR / "prediction_intervals.parquet"
    out.to_parquet(out_path, index=False)
    logger.info(f"Saved: {out_path} ({len(out)} rows)")

    # Summary table
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)

    logger.info(f"\nCalibration: {len(cal_residuals)} residuals from {logo_train['site_id'].nunique()} training sites")
    logger.info(f"Calibration residual quantiles (log space):")
    for q in [2.5, 5, 10, 25, 50, 75, 90, 95, 97.5]:
        logger.info(f"  {q:5.1f}th percentile: {np.percentile(cal_residuals, q):+.4f}")

    logger.info(f"\n{'Metric':<35} {'LOGO holdout':>15} {'Final holdout':>15}")
    logger.info("-" * 70)
    for alpha in alphas:
        conf = int(100 * (1 - alpha))
        logger.info(
            f"  {conf}% coverage:                  "
            f"{logo_metrics[f'coverage_{conf}pct']:>14.1%} "
            f"{holdout_metrics[f'coverage_{conf}pct']:>14.1%}"
        )
        logger.info(
            f"  {conf}% median width (mg/L):       "
            f"{logo_metrics[f'median_width_{conf}pct_mgL']:>14.1f} "
            f"{holdout_metrics[f'median_width_{conf}pct_mgL']:>14.1f}"
        )
        logger.info(
            f"  {conf}% median width ratio:         "
            f"{logo_metrics[f'median_width_ratio_{conf}pct']:>14.3f} "
            f"{holdout_metrics[f'median_width_ratio_{conf}pct']:>14.3f}"
        )
        logger.info("")

    logger.info("Done.")


if __name__ == "__main__":
    main()
