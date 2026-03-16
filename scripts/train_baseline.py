"""Train baseline models on the assembled turbidity-SSC dataset.

Phase 2 of the murkml build plan. Trains five model tiers:
1. Per-site OLS  — replicates current USGS practice
2. Global OLS    — pooled single regression
3. Global multi-feature linear — all engineered features
4. Cross-site CatBoost — leave-one-site-out CV with all features
5. CatBoost quantile — prediction intervals (10th/50th/90th)

All metrics are reported in both log-space and natural-space (mg/L).
Back-transformation uses Duan's smearing estimator for bias correction.

Usage:
    python scripts/train_baseline.py
    python scripts/train_baseline.py --skip-shap --skip-quantile
"""

from __future__ import annotations

import argparse
import logging
import pickle
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import LeaveOneGroupOut

# ---------------------------------------------------------------------------
# Path setup — allow running from repo root without pip install
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from murkml.evaluate.metrics import (
    kge,
    percent_bias,
    prediction_interval_coverage,
    r_squared,
    rmse,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RANDOM_SEED = 42
DATASET_PATH = PROJECT_ROOT / "data" / "processed" / "turbidity_ssc_paired.parquet"
RESULTS_DIR = PROJECT_ROOT / "data" / "results"
FIGURES_DIR = PROJECT_ROOT / "notebooks" / "figures"
MODEL_DIR = PROJECT_ROOT / "data" / "results" / "models"

# Columns that are NOT features
EXCLUDE_COLS = {
    "site_id",
    "sample_time",
    "lab_value",
    "ssc_log1p",
    "match_gap_seconds",
    "window_count",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

np.random.seed(RANDOM_SEED)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def identify_features(df: pd.DataFrame) -> list[str]:
    """Return numeric feature column names, excluding metadata and target."""
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    return [c for c in numeric_cols if c not in EXCLUDE_COLS]


def duan_smearing(residuals_log: np.ndarray) -> float:
    """Duan's smearing estimator for retransformation bias correction.

    When back-transforming from log-space predictions, E[exp(y)] != exp(E[y]).
    The smearing factor corrects this: multiply natural-space predictions by
    mean(exp(residuals)) where residuals are in log-space.

    Reference: Duan, N. (1983). Smearing Estimate: A Nonparametric
    Retransformation Method. JASA 78(383), 605-610.
    """
    return float(np.mean(np.exp(residuals_log)))


def to_natural(log1p_values: np.ndarray) -> np.ndarray:
    """Inverse of log1p transform: expm1."""
    return np.expm1(log1p_values)


def compute_metrics_both_spaces(
    y_true_log: np.ndarray,
    y_pred_log: np.ndarray,
    smearing_factor: float = 1.0,
) -> dict:
    """Compute R2, RMSE, KGE, percent_bias in log-space and natural-space.

    Natural-space predictions are bias-corrected with the smearing factor.
    """
    # Log-space metrics
    metrics = {
        "r2_log": r_squared(y_true_log, y_pred_log),
        "rmse_log": rmse(y_true_log, y_pred_log),
        "kge_log": kge(y_true_log, y_pred_log),
        "pbias_log": percent_bias(y_true_log, y_pred_log),
    }

    # Natural-space (mg/L) metrics with smearing correction
    y_true_nat = to_natural(y_true_log)
    y_pred_nat = to_natural(y_pred_log) * smearing_factor

    metrics.update({
        "r2_nat": r_squared(y_true_nat, y_pred_nat),
        "rmse_nat": rmse(y_true_nat, y_pred_nat),
        "kge_nat": kge(y_true_nat, y_pred_nat),
        "pbias_nat": percent_bias(y_true_nat, y_pred_nat),
        "smearing_factor": smearing_factor,
    })

    return metrics


def temporal_split(df: pd.DataFrame, train_frac: float = 0.7):
    """Split a site's data by time: first train_frac% for training, rest for test."""
    df_sorted = df.sort_values("sample_time").reset_index(drop=True)
    split_idx = int(len(df_sorted) * train_frac)
    return df_sorted.iloc[:split_idx], df_sorted.iloc[split_idx:]


# ---------------------------------------------------------------------------
# Model 1: Per-site OLS (log-log)
# ---------------------------------------------------------------------------

def train_per_site_ols(df: pd.DataFrame) -> list[dict]:
    """log(SSC) = a * log(turbidity) + b per site, temporal 70/30 split."""
    logger.info("=" * 60)
    logger.info("Model 1: Per-site OLS (log-log)")
    logger.info("=" * 60)

    results = []
    for site_id, site_df in df.groupby("site_id"):
        site_df = site_df.dropna(subset=["turbidity_instant", "ssc_log1p"])
        if len(site_df) < 10:
            logger.warning(f"  {site_id}: only {len(site_df)} samples, skipping")
            continue

        train, test = temporal_split(site_df)
        if len(test) < 3:
            logger.warning(f"  {site_id}: test set too small ({len(test)}), skipping")
            continue

        # Feature: log1p(turbidity) — same transform USGS uses
        X_train = np.log1p(train["turbidity_instant"].values).reshape(-1, 1)
        X_test = np.log1p(test["turbidity_instant"].values).reshape(-1, 1)
        y_train = train["ssc_log1p"].values
        y_test = test["ssc_log1p"].values

        model = LinearRegression()
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        # Smearing factor from training residuals
        train_resid = y_train - model.predict(X_train)
        sf = duan_smearing(train_resid)

        metrics = compute_metrics_both_spaces(y_test, y_pred, sf)
        metrics.update({
            "model": "per_site_ols",
            "site_id": site_id,
            "n_train": len(train),
            "n_test": len(test),
            "slope": float(model.coef_[0]),
            "intercept": float(model.intercept_),
        })
        results.append(metrics)

        logger.info(
            f"  {site_id}: R2_log={metrics['r2_log']:.3f}  "
            f"R2_nat={metrics['r2_nat']:.3f}  "
            f"KGE_nat={metrics['kge_nat']:.3f}  "
            f"n={len(train)}+{len(test)}"
        )

    return results


# ---------------------------------------------------------------------------
# Model 2: Global OLS (pooled log-log)
# ---------------------------------------------------------------------------

def train_global_ols(df: pd.DataFrame) -> list[dict]:
    """Single log-log regression across all sites pooled."""
    logger.info("=" * 60)
    logger.info("Model 2: Global OLS (pooled log-log)")
    logger.info("=" * 60)

    results = []
    clean = df.dropna(subset=["turbidity_instant", "ssc_log1p"]).copy()

    # Temporal split per site, then pool
    train_frames, test_frames = [], []
    for _site_id, site_df in clean.groupby("site_id"):
        tr, te = temporal_split(site_df)
        train_frames.append(tr)
        test_frames.append(te)

    train = pd.concat(train_frames, ignore_index=True)
    test = pd.concat(test_frames, ignore_index=True)

    X_train = np.log1p(train["turbidity_instant"].values).reshape(-1, 1)
    X_test = np.log1p(test["turbidity_instant"].values).reshape(-1, 1)
    y_train = train["ssc_log1p"].values
    y_test = test["ssc_log1p"].values

    model = LinearRegression()
    model.fit(X_train, y_train)

    train_resid = y_train - model.predict(X_train)
    sf = duan_smearing(train_resid)

    # Per-site metrics on test set
    for site_id, site_test in test.groupby("site_id"):
        if len(site_test) < 3:
            continue
        X_s = np.log1p(site_test["turbidity_instant"].values).reshape(-1, 1)
        y_s = site_test["ssc_log1p"].values
        y_p = model.predict(X_s)

        metrics = compute_metrics_both_spaces(y_s, y_p, sf)
        metrics.update({
            "model": "global_ols",
            "site_id": site_id,
            "n_train": len(train),
            "n_test": len(site_test),
        })
        results.append(metrics)

    # Overall metrics
    y_pred_all = model.predict(X_test)
    overall = compute_metrics_both_spaces(y_test, y_pred_all, sf)
    overall.update({
        "model": "global_ols",
        "site_id": "ALL",
        "n_train": len(train),
        "n_test": len(test),
    })
    results.append(overall)

    logger.info(
        f"  Overall: R2_log={overall['r2_log']:.3f}  "
        f"R2_nat={overall['r2_nat']:.3f}  KGE_nat={overall['kge_nat']:.3f}"
    )

    return results


# ---------------------------------------------------------------------------
# Model 3: Global multi-feature linear
# ---------------------------------------------------------------------------

def train_global_multifeature(df: pd.DataFrame, feature_cols: list[str]) -> list[dict]:
    """Linear regression using ALL engineered features, temporal split."""
    logger.info("=" * 60)
    logger.info("Model 3: Global multi-feature linear")
    logger.info("=" * 60)

    results = []
    clean = df.dropna(subset=["ssc_log1p"]).copy()

    # Fill missing features with column median (some sensors not at all sites)
    for col in feature_cols:
        if clean[col].isna().any():
            clean[col] = clean[col].fillna(clean[col].median())

    # Temporal split per site, then pool
    train_frames, test_frames = [], []
    for _site_id, site_df in clean.groupby("site_id"):
        tr, te = temporal_split(site_df)
        train_frames.append(tr)
        test_frames.append(te)

    train = pd.concat(train_frames, ignore_index=True)
    test = pd.concat(test_frames, ignore_index=True)

    X_train = train[feature_cols].values
    X_test = test[feature_cols].values
    y_train = train["ssc_log1p"].values
    y_test = test["ssc_log1p"].values

    model = LinearRegression()
    model.fit(X_train, y_train)

    train_resid = y_train - model.predict(X_train)
    sf = duan_smearing(train_resid)

    # Per-site metrics
    for site_id, site_test in test.groupby("site_id"):
        if len(site_test) < 3:
            continue
        X_s = site_test[feature_cols].values
        y_s = site_test["ssc_log1p"].values
        y_p = model.predict(X_s)

        metrics = compute_metrics_both_spaces(y_s, y_p, sf)
        metrics.update({
            "model": "global_multifeature",
            "site_id": site_id,
            "n_train": len(train),
            "n_test": len(site_test),
        })
        results.append(metrics)

    # Overall
    y_pred_all = model.predict(X_test)
    overall = compute_metrics_both_spaces(y_test, y_pred_all, sf)
    overall.update({
        "model": "global_multifeature",
        "site_id": "ALL",
        "n_train": len(train),
        "n_test": len(test),
    })
    results.append(overall)

    logger.info(
        f"  {len(feature_cols)} features | "
        f"R2_log={overall['r2_log']:.3f}  R2_nat={overall['r2_nat']:.3f}  "
        f"KGE_nat={overall['kge_nat']:.3f}"
    )

    return results


# ---------------------------------------------------------------------------
# Model 4: Cross-site CatBoost (leave-one-site-out)
# ---------------------------------------------------------------------------

def train_catboost_logo(
    df: pd.DataFrame, feature_cols: list[str]
) -> tuple[list[dict], object | None]:
    """CatBoost with LeaveOneGroupOut CV by site_id. Returns results + final model."""
    logger.info("=" * 60)
    logger.info("Model 4: Cross-site CatBoost (leave-one-site-out)")
    logger.info("=" * 60)

    try:
        from catboost import CatBoostRegressor
    except ImportError:
        logger.error(
            "CatBoost not installed. Run: pip install murkml[boost]"
        )
        return [], None

    clean = df.dropna(subset=["ssc_log1p"]).copy()
    for col in feature_cols:
        if clean[col].isna().any():
            clean[col] = clean[col].fillna(clean[col].median())

    X = clean[feature_cols].values
    y = clean["ssc_log1p"].values
    groups = clean["site_id"].values

    logo = LeaveOneGroupOut()
    results = []
    all_y_true, all_y_pred = [], []

    for fold_idx, (train_idx, test_idx) in enumerate(logo.split(X, y, groups)):
        held_out_site = groups[test_idx[0]]
        if len(test_idx) < 3:
            logger.warning(f"  Fold {fold_idx}: {held_out_site} has <3 samples, skipping")
            continue

        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        model = CatBoostRegressor(
            iterations=500,
            learning_rate=0.05,
            depth=6,
            l2_leaf_reg=3,
            random_seed=RANDOM_SEED,
            verbose=0,
            loss_function="RMSE",
        )
        model.fit(X_train, y_train, eval_set=(X_test, y_test), early_stopping_rounds=50)

        y_pred = model.predict(X_test)

        # Smearing factor from training residuals
        train_resid = y_train - model.predict(X_train)
        sf = duan_smearing(train_resid)

        metrics = compute_metrics_both_spaces(y_test, y_pred, sf)
        metrics.update({
            "model": "catboost_logo",
            "site_id": held_out_site,
            "n_train": len(train_idx),
            "n_test": len(test_idx),
        })
        results.append(metrics)

        all_y_true.extend(y_test)
        all_y_pred.extend(y_pred)

        logger.info(
            f"  Fold {fold_idx} ({held_out_site}): "
            f"R2_log={metrics['r2_log']:.3f}  KGE_nat={metrics['kge_nat']:.3f}  "
            f"n_test={len(test_idx)}"
        )

    # Overall cross-validated metrics (smearing from pooled residuals is approximate)
    if all_y_true:
        all_y_true_arr = np.array(all_y_true)
        all_y_pred_arr = np.array(all_y_pred)
        overall = compute_metrics_both_spaces(all_y_true_arr, all_y_pred_arr, smearing_factor=1.0)
        overall.update({
            "model": "catboost_logo",
            "site_id": "ALL_CV",
            "n_train": 0,
            "n_test": len(all_y_true),
        })
        results.append(overall)
        logger.info(
            f"  Overall CV: R2_log={overall['r2_log']:.3f}  "
            f"R2_nat={overall['r2_nat']:.3f}  KGE_nat={overall['kge_nat']:.3f}"
        )

    # Train final model on ALL data for saving/SHAP
    logger.info("  Training final model on all data...")
    final_model = CatBoostRegressor(
        iterations=500,
        learning_rate=0.05,
        depth=6,
        l2_leaf_reg=3,
        random_seed=RANDOM_SEED,
        verbose=0,
        loss_function="RMSE",
    )
    final_model.fit(X, y)

    return results, final_model


# ---------------------------------------------------------------------------
# Model 5: CatBoost quantile regression
# ---------------------------------------------------------------------------

def train_catboost_quantile(
    df: pd.DataFrame, feature_cols: list[str]
) -> list[dict]:
    """CatBoost quantile regression (10th, 50th, 90th) with LOGO CV."""
    logger.info("=" * 60)
    logger.info("Model 5: CatBoost quantile regression (prediction intervals)")
    logger.info("=" * 60)

    try:
        from catboost import CatBoostRegressor
    except ImportError:
        logger.error("CatBoost not installed. Run: pip install murkml[boost]")
        return []

    clean = df.dropna(subset=["ssc_log1p"]).copy()
    for col in feature_cols:
        if clean[col].isna().any():
            clean[col] = clean[col].fillna(clean[col].median())

    X = clean[feature_cols].values
    y = clean["ssc_log1p"].values
    groups = clean["site_id"].values

    logo = LeaveOneGroupOut()
    results = []
    quantiles = [0.1, 0.5, 0.9]

    for fold_idx, (train_idx, test_idx) in enumerate(logo.split(X, y, groups)):
        held_out_site = groups[test_idx[0]]
        if len(test_idx) < 3:
            continue

        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        preds = {}
        for q in quantiles:
            model = CatBoostRegressor(
                iterations=500,
                learning_rate=0.05,
                depth=6,
                l2_leaf_reg=3,
                random_seed=RANDOM_SEED,
                verbose=0,
                loss_function=f"Quantile:alpha={q}",
            )
            model.fit(X_train, y_train)
            preds[q] = model.predict(X_test)

        # Metrics for 50th percentile (median)
        y_pred_median = preds[0.5]
        metrics = compute_metrics_both_spaces(y_test, y_pred_median, smearing_factor=1.0)

        # Prediction interval coverage (80% interval: 10th to 90th)
        picp_log = prediction_interval_coverage(y_test, preds[0.1], preds[0.9])
        picp_nat = prediction_interval_coverage(
            to_natural(y_test), to_natural(preds[0.1]), to_natural(preds[0.9])
        )
        metrics.update({
            "model": "catboost_quantile",
            "site_id": held_out_site,
            "n_train": len(train_idx),
            "n_test": len(test_idx),
            "picp_80_log": picp_log,
            "picp_80_nat": picp_nat,
        })
        results.append(metrics)

        logger.info(
            f"  Fold {fold_idx} ({held_out_site}): "
            f"R2_log={metrics['r2_log']:.3f}  PICP_80={picp_log:.2%}  "
            f"n_test={len(test_idx)}"
        )

    return results


# ---------------------------------------------------------------------------
# SHAP analysis
# ---------------------------------------------------------------------------

def run_shap_analysis(
    model, X: np.ndarray, feature_names: list[str]
) -> None:
    """Generate SHAP summary plot for the CatBoost model."""
    logger.info("=" * 60)
    logger.info("SHAP feature importance analysis")
    logger.info("=" * 60)

    try:
        import shap
    except ImportError:
        logger.warning(
            "shap not installed — skipping SHAP analysis. "
            "Install with: pip install murkml[explain]"
        )
        return

    try:
        import matplotlib
        matplotlib.use("Agg")  # Non-interactive backend for saving
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib not available, skipping SHAP plot")
        return

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X)

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIGURES_DIR / "shap_summary.png"

    plt.figure(figsize=(10, 8))
    shap.summary_plot(shap_values, X, feature_names=feature_names, show=False)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()

    logger.info(f"  SHAP summary plot saved to {out_path}")

    # Also log top features by mean |SHAP|
    mean_abs_shap = np.abs(shap_values).mean(axis=0)
    top_idx = np.argsort(mean_abs_shap)[::-1][:10]
    logger.info("  Top 10 features by mean |SHAP value|:")
    for rank, idx in enumerate(top_idx, 1):
        logger.info(f"    {rank}. {feature_names[idx]}: {mean_abs_shap[idx]:.4f}")


# ---------------------------------------------------------------------------
# Results display
# ---------------------------------------------------------------------------

def print_comparison_table(results_df: pd.DataFrame) -> None:
    """Print a formatted comparison table: models x sites."""
    logger.info("")
    logger.info("=" * 80)
    logger.info("COMPARISON TABLE: All Models x All Sites")
    logger.info("=" * 80)

    # Pivot: rows = site_id, columns = model, values = key metrics
    for metric_name in ["r2_log", "r2_nat", "kge_nat", "rmse_nat"]:
        if metric_name not in results_df.columns:
            continue

        pivot = results_df.pivot_table(
            index="site_id", columns="model", values=metric_name, aggfunc="first"
        )
        logger.info(f"\n--- {metric_name} ---")
        logger.info(pivot.to_string(float_format=lambda x: f"{x:.3f}"))

    # Summary statistics per model
    logger.info(f"\n--- Model summary (median across sites, excluding 'ALL' rows) ---")
    site_results = results_df[
        ~results_df["site_id"].isin(["ALL", "ALL_CV"])
    ]
    summary = site_results.groupby("model")[
        ["r2_log", "r2_nat", "kge_nat", "rmse_nat", "pbias_nat"]
    ].median()
    logger.info(summary.to_string(float_format=lambda x: f"{x:.3f}"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Train baseline models on the turbidity-SSC dataset."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DATASET_PATH,
        help="Path to the assembled parquet dataset",
    )
    parser.add_argument(
        "--skip-catboost",
        action="store_true",
        help="Skip CatBoost models (Models 4 and 5)",
    )
    parser.add_argument(
        "--skip-quantile",
        action="store_true",
        help="Skip quantile regression (Model 5)",
    )
    parser.add_argument(
        "--skip-shap",
        action="store_true",
        help="Skip SHAP analysis",
    )
    args = parser.parse_args()

    warnings.filterwarnings("ignore")

    # Load .env if present (pattern from other scripts, not needed here)
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass

    # ------------------------------------------------------------------
    # Load dataset
    # ------------------------------------------------------------------
    logger.info(f"Loading dataset from {args.dataset}")
    if not args.dataset.exists():
        logger.error(
            f"Dataset not found at {args.dataset}. "
            "Run scripts/assemble_dataset.py first."
        )
        sys.exit(1)

    df = pd.read_parquet(args.dataset)
    logger.info(f"Loaded {len(df)} samples across {df['site_id'].nunique()} sites")
    logger.info(f"Columns: {list(df.columns)}")

    # Identify feature columns
    feature_cols = identify_features(df)
    logger.info(f"Feature columns ({len(feature_cols)}): {feature_cols}")

    # Sanity checks
    assert "ssc_log1p" in df.columns, "Missing target column 'ssc_log1p'"
    assert "site_id" in df.columns, "Missing 'site_id' column"
    assert "turbidity_instant" in df.columns or len(feature_cols) > 0, "No features found"

    # ------------------------------------------------------------------
    # Train all models, collect results
    # ------------------------------------------------------------------
    all_results = []

    # Model 1: Per-site OLS
    all_results.extend(train_per_site_ols(df))

    # Model 2: Global OLS
    all_results.extend(train_global_ols(df))

    # Model 3: Global multi-feature linear
    all_results.extend(train_global_multifeature(df, feature_cols))

    # Model 4: Cross-site CatBoost
    catboost_model = None
    if not args.skip_catboost:
        cb_results, catboost_model = train_catboost_logo(df, feature_cols)
        all_results.extend(cb_results)
    else:
        logger.info("Skipping CatBoost (--skip-catboost)")

    # Model 5: CatBoost quantile
    if not args.skip_catboost and not args.skip_quantile:
        all_results.extend(train_catboost_quantile(df, feature_cols))
    else:
        logger.info("Skipping quantile regression")

    # ------------------------------------------------------------------
    # SHAP analysis on the final CatBoost model
    # ------------------------------------------------------------------
    if catboost_model is not None and not args.skip_shap:
        clean = df.dropna(subset=["ssc_log1p"]).copy()
        for col in feature_cols:
            if clean[col].isna().any():
                clean[col] = clean[col].fillna(clean[col].median())
        X_all = clean[feature_cols].values
        run_shap_analysis(catboost_model, X_all, feature_cols)

    # ------------------------------------------------------------------
    # Assemble and save results
    # ------------------------------------------------------------------
    if not all_results:
        logger.error("No results produced!")
        sys.exit(1)

    results_df = pd.DataFrame(all_results)

    # Print comparison table
    print_comparison_table(results_df)

    # Save results parquet
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results_path = RESULTS_DIR / "baseline_results.parquet"
    results_df.to_parquet(results_path, index=False)
    logger.info(f"\nResults saved to {results_path}")

    # Save CatBoost model
    if catboost_model is not None:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        model_path = MODEL_DIR / "catboost_logo_final.cbm"
        catboost_model.save_model(str(model_path))
        logger.info(f"CatBoost model saved to {model_path}")

        # Also save feature names for inference
        meta_path = MODEL_DIR / "catboost_logo_meta.pkl"
        with open(meta_path, "wb") as f:
            pickle.dump({"feature_cols": feature_cols, "random_seed": RANDOM_SEED}, f)
        logger.info(f"Model metadata saved to {meta_path}")

    logger.info("\nDone.")


if __name__ == "__main__":
    main()
