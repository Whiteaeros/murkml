"""Train models across all feature tiers and parameters.

Runs CatBoost LOGO CV for each combination of:
- Parameter: ssc, total_phosphorus, nitrate_nitrite, orthophosphate
- Tier: A (sensor-only), B (sensor+basic), C (sensor+GAGES-II)

Produces a comparison table showing how catchment attributes affect performance.

Usage:
    python scripts/train_tiered.py
    python scripts/train_tiered.py --param total_phosphorus
    python scripts/train_tiered.py --tier C
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import LeaveOneGroupOut, GroupShuffleSplit

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from murkml.data.attributes import prune_gagesii, build_feature_tiers
from murkml.evaluate.metrics import kge, percent_bias, r_squared, rmse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"

PARAM_CONFIG = {
    "ssc": {"dataset": "turbidity_ssc_paired.parquet", "target_col": "ssc_log1p"},
    "total_phosphorus": {"dataset": "total_phosphorus_paired.parquet", "target_col": "total_phosphorus_log1p"},
    "nitrate_nitrite": {"dataset": "nitrate_nitrite_paired.parquet", "target_col": "nitrate_nitrite_log1p"},
    "orthophosphate": {"dataset": "orthophosphate_paired.parquet", "target_col": "orthophosphate_log1p"},
}

EXCLUDE_COLS = {
    "site_id", "sample_time", "lab_value", "match_gap_seconds", "window_count",
    "is_nondetect", "hydro_event",
    "ssc_log1p", "ssc_value", "total_phosphorus_log1p",
    "nitrate_nitrite_log1p", "orthophosphate_log1p", "tds_evaporative_log1p",
}


def train_catboost_logo_quick(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str = "ssc_log1p",
) -> dict:
    """Run CatBoost LOGO CV and return median metrics. Streamlined version."""
    from catboost import CatBoostRegressor

    clean = df.dropna(subset=[target_col]).copy()
    sites = clean["site_id"].values
    y = clean[target_col].values

    X_df = clean[feature_cols].copy()

    logo = LeaveOneGroupOut()
    fold_metrics = []

    for fold_idx, (train_idx, test_idx) in enumerate(logo.split(X_df, y, groups=sites)):
        X_train_df = X_df.iloc[train_idx]
        X_test_df = X_df.iloc[test_idx]
        y_train = y[train_idx]
        y_test = y[test_idx]
        test_site = sites[test_idx][0]

        if len(y_test) < 5:
            continue

        # Train median imputation
        train_median = X_train_df.median()
        X_train = X_train_df.fillna(train_median).values
        X_test = X_test_df.fillna(train_median).values

        # Early stopping split
        gss = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=42)
        train_sites = sites[train_idx]
        sub_train_idx, val_idx = next(gss.split(X_train, y_train, groups=train_sites))

        model = CatBoostRegressor(
            iterations=500, learning_rate=0.05, depth=6,
            l2_leaf_reg=3, random_seed=42, verbose=0,
            early_stopping_rounds=50,
        )
        model.fit(
            X_train[sub_train_idx], y_train[sub_train_idx],
            eval_set=(X_train[val_idx], y_train[val_idx]),
        )

        y_pred = model.predict(X_test)

        fold_metrics.append({
            "site_id": test_site,
            "r2_log": r_squared(y_test, y_pred),
            "kge_log": kge(y_test, y_pred),
            "n_test": len(y_test),
        })

    if not fold_metrics:
        return {"r2_log": np.nan, "kge_log": np.nan, "n_folds": 0}

    metrics_df = pd.DataFrame(fold_metrics)
    return {
        "r2_log": metrics_df["r2_log"].median(),
        "kge_log": metrics_df["kge_log"].median(),
        "n_folds": len(metrics_df),
        "n_samples": len(clean),
    }


def run_tier(param_name: str, tier_name: str, tier_data: pd.DataFrame,
             feature_cols: list[str], target_col: str) -> dict:
    """Run one parameter × tier combination."""
    # Map target to standard name
    if target_col != "ssc_log1p" and target_col in tier_data.columns:
        tier_data = tier_data.rename(columns={target_col: "ssc_log1p"})
        target_col = "ssc_log1p"

    # Filter feature cols to those actually in the data and numeric
    available = [c for c in feature_cols if c in tier_data.columns and c not in EXCLUDE_COLS]
    numeric_available = [c for c in available if tier_data[c].dtype in [np.float64, np.float32, np.int64, np.int32, float, int]]

    logger.info(f"  {param_name} / {tier_name}: {tier_data['site_id'].nunique()} sites, "
                f"{len(tier_data)} samples, {len(numeric_available)} features")

    if len(numeric_available) == 0:
        return {"r2_log": np.nan, "kge_log": np.nan, "n_folds": 0, "n_samples": 0}

    result = train_catboost_logo_quick(tier_data, numeric_available, target_col)
    result["param"] = param_name
    result["tier"] = tier_name
    result["n_features"] = len(numeric_available)
    return result


def main():
    warnings.filterwarnings("ignore")

    parser = argparse.ArgumentParser(description="Train tiered models")
    parser.add_argument("--param", type=str, default=None, choices=list(PARAM_CONFIG.keys()))
    parser.add_argument("--tier", type=str, default=None, choices=["A", "B", "C"])
    args = parser.parse_args()

    # Load attributes
    basic_attrs = pd.read_parquet(DATA_DIR / "site_attributes.parquet")
    gagesii_path = DATA_DIR / "site_attributes_gagesii.parquet"
    gagesii_attrs = None
    if gagesii_path.exists():
        gagesii_raw = pd.read_parquet(gagesii_path)
        gagesii_attrs = prune_gagesii(gagesii_raw)

    # Select parameters
    params = {args.param: PARAM_CONFIG[args.param]} if args.param else PARAM_CONFIG

    all_results = []

    for param_name, cfg in params.items():
        dataset_path = DATA_DIR / "processed" / cfg["dataset"]
        if not dataset_path.exists():
            logger.warning(f"Skipping {param_name}: dataset not found at {dataset_path}")
            continue

        logger.info(f"\n{'='*60}")
        logger.info(f"PARAMETER: {param_name}")
        logger.info(f"{'='*60}")

        assembled = pd.read_parquet(dataset_path)
        target_col = cfg["target_col"]

        # Build tiers
        tiers = build_feature_tiers(assembled, basic_attrs, gagesii_attrs)

        for tier_name, tier_info in tiers.items():
            if args.tier and not tier_name.startswith(args.tier):
                continue

            result = run_tier(
                param_name, tier_name,
                tier_info["data"], tier_info["feature_cols"], target_col
            )
            all_results.append(result)
            logger.info(f"    R²(log)={result['r2_log']:.3f}  KGE(log)={result['kge_log']:.3f}")

    # Summary table
    if all_results:
        results_df = pd.DataFrame(all_results)
        logger.info(f"\n{'='*60}")
        logger.info("TIERED COMPARISON")
        logger.info(f"{'='*60}")

        pivot = results_df.pivot_table(
            index="param", columns="tier", values="r2_log", aggfunc="first"
        )
        logger.info(f"\nMedian R² (log) by parameter × tier:")
        logger.info(f"\n{pivot.to_string()}")

        pivot_kge = results_df.pivot_table(
            index="param", columns="tier", values="kge_log", aggfunc="first"
        )
        logger.info(f"\nMedian KGE (log) by parameter × tier:")
        logger.info(f"\n{pivot_kge.to_string()}")

        # Save
        out_path = DATA_DIR / "results" / "tiered_comparison.parquet"
        results_df.to_parquet(out_path, index=False)
        logger.info(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
