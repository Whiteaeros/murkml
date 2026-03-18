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

from murkml.data.attributes import prune_gagesii, build_feature_tiers, get_gagesii_original_sites
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
    cat_features: list[str] | None = None,
) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Run CatBoost LOGO CV. Returns (summary, fold_metrics_df, per_sample_df)."""
    from catboost import CatBoostRegressor, Pool

    clean = df.dropna(subset=[target_col]).copy()
    sites = clean["site_id"].values
    y = clean[target_col].values

    # Grab discharge for per-sample output (needed for flow stratification)
    discharge_col = "discharge_instant"
    has_discharge = discharge_col in clean.columns
    discharge_vals = clean[discharge_col].values if has_discharge else np.full(len(clean), np.nan)

    X_df = clean[feature_cols].copy()

    if cat_features is None:
        cat_features = []
    cat_indices = [i for i, c in enumerate(feature_cols) if c in cat_features]
    num_cols = [c for c in feature_cols if c not in cat_features]

    for c in cat_features:
        if c in X_df.columns:
            X_df[c] = X_df[c].fillna("missing").astype(str)

    logo = LeaveOneGroupOut()
    fold_metrics = []
    sample_records = []

    for fold_idx, (train_idx, test_idx) in enumerate(logo.split(X_df, y, groups=sites)):
        X_train_df = X_df.iloc[train_idx]
        X_test_df = X_df.iloc[test_idx]
        y_train = y[train_idx]
        y_test = y[test_idx]
        test_site = sites[test_idx][0]

        if len(y_test) < 5:
            continue

        train_median = X_train_df[num_cols].median()
        X_train_df = X_train_df.copy()
        X_test_df = X_test_df.copy()
        X_train_df[num_cols] = X_train_df[num_cols].fillna(train_median)
        X_test_df[num_cols] = X_test_df[num_cols].fillna(train_median)

        gss = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=42)
        train_sites = sites[train_idx]
        sub_train_idx, val_idx = next(gss.split(X_train_df, y_train, groups=train_sites))

        train_pool = Pool(
            X_train_df.iloc[sub_train_idx], y_train[sub_train_idx],
            cat_features=cat_indices,
        )
        val_pool = Pool(
            X_train_df.iloc[val_idx], y_train[val_idx],
            cat_features=cat_indices,
        )
        test_pool = Pool(X_test_df, cat_features=cat_indices)

        model = CatBoostRegressor(
            iterations=500, learning_rate=0.05, depth=6,
            l2_leaf_reg=3, random_seed=42, verbose=0,
            early_stopping_rounds=50,
        )
        model.fit(train_pool, eval_set=val_pool)

        y_pred = model.predict(test_pool)

        # KGE with decomposition
        kge_result = kge(y_test, y_pred, return_components=True)

        fold_metrics.append({
            "site_id": test_site,
            "r2_log": r_squared(y_test, y_pred),
            "kge_log": kge_result["kge"],
            "kge_r": kge_result["kge_r"],
            "kge_alpha": kge_result["kge_alpha"],
            "kge_beta": kge_result["kge_beta"],
            "n_test": len(y_test),
        })

        # Per-sample predictions for flow stratification
        test_discharge = discharge_vals[test_idx]
        for i in range(len(y_test)):
            sample_records.append({
                "site_id": test_site,
                "y_true_log": float(y_test[i]),
                "y_pred_log": float(y_pred[i]),
                "discharge_instant": float(test_discharge[i]),
            })

    if not fold_metrics:
        empty_folds = pd.DataFrame()
        empty_samples = pd.DataFrame()
        return {"r2_log": np.nan, "kge_log": np.nan, "n_folds": 0}, empty_folds, empty_samples

    metrics_df = pd.DataFrame(fold_metrics)
    samples_df = pd.DataFrame(sample_records)

    summary = {
        "r2_log": metrics_df["r2_log"].median(),
        "kge_log": metrics_df["kge_log"].median(),
        "n_folds": len(metrics_df),
        "n_samples": len(clean),
    }
    return summary, metrics_df, samples_df


def run_tier(param_name: str, tier_name: str, tier_data: pd.DataFrame,
             feature_cols: list[str], target_col: str) -> dict:
    """Run one parameter × tier combination."""
    # Map target to standard name
    if target_col != "ssc_log1p" and target_col in tier_data.columns:
        tier_data = tier_data.rename(columns={target_col: "ssc_log1p"})
        target_col = "ssc_log1p"

    # Filter feature cols to those actually in the data
    available = [c for c in feature_cols if c in tier_data.columns and c not in EXCLUDE_COLS]
    numeric_available = [c for c in available if tier_data[c].dtype in [np.float64, np.float32, np.int64, np.int32, float, int]]
    cat_available = [c for c in available if tier_data[c].dtype == object]
    all_available = numeric_available + cat_available

    logger.info(f"  {param_name} / {tier_name}: {tier_data['site_id'].nunique()} sites, "
                f"{len(tier_data)} samples, {len(numeric_available)} numeric + {len(cat_available)} categorical features")

    if len(numeric_available) == 0:
        return {"r2_log": np.nan, "kge_log": np.nan, "n_folds": 0, "n_samples": 0}

    summary, folds_df, samples_df = train_catboost_logo_quick(
        tier_data, all_available, target_col, cat_features=cat_available
    )
    summary["param"] = param_name
    summary["tier"] = tier_name
    summary["n_features"] = len(all_available)

    # Save per-fold and per-sample results
    results_dir = DATA_DIR / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    safe_tier = tier_name.replace("/", "_")
    if not folds_df.empty:
        folds_df.to_parquet(results_dir / f"logo_folds_{param_name}_{safe_tier}.parquet", index=False)
    if not samples_df.empty:
        samples_df.to_parquet(results_dir / f"logo_predictions_{param_name}_{safe_tier}.parquet", index=False)

    return summary


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

    # Identify original GAGES-II sites (not NLCD backfill) for vintage confound test
    original_gagesii_sites = get_gagesii_original_sites(DATA_DIR)
    logger.info(f"Original GAGES-II sites: {len(original_gagesii_sites)}")

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
        tiers = build_feature_tiers(assembled, basic_attrs, gagesii_attrs, original_gagesii_sites)

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

        # Save CV results
        out_path = DATA_DIR / "results" / "tiered_comparison.parquet"
        results_df.to_parquet(out_path, index=False)
        logger.info(f"\nSaved: {out_path}")

    # =========================================================
    # Save final trained models (one per param × tier)
    # =========================================================
    logger.info(f"\n{'='*60}")
    logger.info("SAVING FINAL MODELS")
    logger.info(f"{'='*60}")

    from catboost import CatBoostRegressor, Pool
    import json

    model_dir = DATA_DIR / "results" / "models"
    model_dir.mkdir(parents=True, exist_ok=True)

    for param_name, cfg in params.items():
        dataset_path = DATA_DIR / "processed" / cfg["dataset"]
        if not dataset_path.exists():
            continue

        assembled = pd.read_parquet(dataset_path)
        target_col = cfg["target_col"]
        tiers = build_feature_tiers(assembled, basic_attrs, gagesii_attrs, original_gagesii_sites)

        for tier_name, tier_info in tiers.items():
            if args.tier and not tier_name.startswith(args.tier):
                continue

            tier_data = tier_info["data"].copy()
            feature_cols = tier_info["feature_cols"]

            # Remap target col
            if target_col != "ssc_log1p" and target_col in tier_data.columns:
                tier_data = tier_data.rename(columns={target_col: "ssc_log1p"})
                tc = "ssc_log1p"
            else:
                tc = target_col

            available = [c for c in feature_cols if c in tier_data.columns and c not in EXCLUDE_COLS]
            numeric_cols = [c for c in available if tier_data[c].dtype in [np.float64, np.float32, np.int64, np.int32, float, int]]
            cat_cols = [c for c in available if tier_data[c].dtype == object]
            all_cols = numeric_cols + cat_cols
            cat_indices = [i for i, c in enumerate(all_cols) if c in cat_cols]

            if len(numeric_cols) == 0:
                continue

            clean = tier_data.dropna(subset=[tc]).copy()
            y = clean[tc].values
            X_df = clean[all_cols].copy()

            for c in cat_cols:
                X_df[c] = X_df[c].fillna("missing").astype(str)
            train_median = X_df[numeric_cols].median()
            X_df[numeric_cols] = X_df[numeric_cols].fillna(train_median)

            # Early stopping split
            sites = clean["site_id"].values
            gss = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=42)
            train_idx, val_idx = next(gss.split(X_df, y, groups=sites))

            train_pool = Pool(X_df.iloc[train_idx], y[train_idx], cat_features=cat_indices)
            val_pool = Pool(X_df.iloc[val_idx], y[val_idx], cat_features=cat_indices)

            model = CatBoostRegressor(
                iterations=500, learning_rate=0.05, depth=6,
                l2_leaf_reg=3, random_seed=42, verbose=0,
                early_stopping_rounds=50,
            )
            model.fit(train_pool, eval_set=val_pool)

            # Save model
            safe_tier = tier_name.replace("/", "_")
            model_path = model_dir / f"{param_name}_{safe_tier}.cbm"
            model.save_model(str(model_path))

            # Save metadata (schema v2 with applicability fields)
            # Feature ranges for applicability domain detection
            feature_ranges = {}
            for col in numeric_cols:
                if col in X_df.columns:
                    feature_ranges[col] = {
                        "min": float(X_df[col].min()),
                        "max": float(X_df[col].max()),
                    }

            # Categorical values seen
            cat_values_seen = {}
            for col in cat_cols:
                if col in X_df.columns:
                    cat_values_seen[col] = sorted(X_df[col].unique().tolist())

            # Per-regime site counts
            sites_per_ecoregion = {}
            sites_per_geology = {}
            site_df = clean[["site_id"]].drop_duplicates()
            if "ecoregion" in clean.columns:
                eco_map = clean.drop_duplicates("site_id").groupby("ecoregion")["site_id"].nunique()
                sites_per_ecoregion = eco_map.to_dict()
            elif "ecoregion" in X_df.columns:
                eco_map = X_df.assign(site_id=clean["site_id"]).drop_duplicates("site_id")
                sites_per_ecoregion = eco_map["ecoregion"].value_counts().to_dict()
            if "geol_class" in clean.columns:
                geo_map = clean.drop_duplicates("site_id").groupby("geol_class")["site_id"].nunique()
                sites_per_geology = geo_map.to_dict()
            elif "geol_class" in X_df.columns:
                geo_map = X_df.assign(site_id=clean["site_id"]).drop_duplicates("site_id")
                sites_per_geology = geo_map["geol_class"].value_counts().to_dict()

            meta = {
                "schema_version": 2,
                "param": param_name,
                "tier": tier_name,
                "feature_cols": all_cols,
                "cat_cols": cat_cols,
                "cat_indices": cat_indices,
                "train_median": train_median.to_dict(),
                "feature_ranges": feature_ranges,
                "categorical_values_seen": cat_values_seen,
                "target_range": {"min": float(y.min()), "max": float(y.max())},
                "target_range_native": {"min": float(np.expm1(y.min())), "max": float(np.expm1(y.max()))},
                "sites_per_ecoregion": sites_per_ecoregion,
                "sites_per_geology": sites_per_geology,
                "n_sites": int(clean["site_id"].nunique()),
                "n_samples": len(clean),
                "n_trees": model.tree_count_,
            }
            meta_path = model_dir / f"{param_name}_{safe_tier}_meta.json"
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)

            size_kb = model_path.stat().st_size / 1024
            logger.info(f"  Saved {param_name}/{tier_name}: {model.tree_count_} trees, "
                       f"{size_kb:.0f} KB → {model_path.name}")


if __name__ == "__main__":
    main()
