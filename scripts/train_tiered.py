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
from murkml.evaluate.metrics import (
    kge, percent_bias, r_squared, rmse,
    duan_smearing_factor, native_space_metrics,
)
from murkml.provenance import start_run, log_step, log_file, end_run

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
    # Nitrate and orthoP are confirmed negative results (R² < -1.5 across all tiers).
    # Skipping to avoid ~1000 unnecessary LOGO CV folds per retrain.
    # "nitrate_nitrite": {"dataset": "nitrate_nitrite_paired.parquet", "target_col": "nitrate_nitrite_log1p"},
    # "orthophosphate": {"dataset": "orthophosphate_paired.parquet", "target_col": "orthophosphate_log1p"},
}

EXCLUDE_COLS = {
    "site_id", "sample_time", "lab_value", "match_gap_seconds", "window_count",
    "is_nondetect", "hydro_event",
    "ssc_log1p", "ssc_value", "total_phosphorus_log1p",
    "nitrate_nitrite_log1p", "orthophosphate_log1p", "tds_evaporative_log1p",
}


def train_ridge_logo(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str = "ssc_log1p",
    cat_features: list[str] | None = None,
) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Run Ridge regression LOGO CV as a linear baseline.

    Uses the same splits and preprocessing as CatBoost for fair comparison.
    Categorical features are one-hot encoded. Returns same format as CatBoost version.
    """
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import OneHotEncoder

    clean = df.dropna(subset=[target_col]).copy()
    sites = clean["site_id"].values
    y = clean[target_col].values

    discharge_col = "discharge_instant"
    has_discharge = discharge_col in clean.columns
    discharge_vals = clean[discharge_col].values if has_discharge else np.full(len(clean), np.nan)

    if cat_features is None:
        cat_features = []
    num_cols = [c for c in feature_cols if c not in cat_features]
    cat_cols_present = [c for c in cat_features if c in df.columns]

    X_num = clean[num_cols].copy()

    logo = LeaveOneGroupOut()
    fold_metrics = []
    sample_records = []

    for fold_idx, (train_idx, test_idx) in enumerate(logo.split(X_num, y, groups=sites)):
        y_train = y[train_idx]
        y_test = y[test_idx]
        test_site = sites[test_idx][0]

        if len(y_test) < 5:
            continue

        # Numeric features: fill NaN with training median
        X_train_num = X_num.iloc[train_idx].copy()
        X_test_num = X_num.iloc[test_idx].copy()
        train_median = X_train_num.median()
        X_train_num = X_train_num.fillna(train_median)
        X_test_num = X_test_num.fillna(train_median)

        # One-hot encode categoricals
        if cat_cols_present:
            cat_train = clean[cat_cols_present].iloc[train_idx].fillna("missing").astype(str)
            cat_test = clean[cat_cols_present].iloc[test_idx].fillna("missing").astype(str)
            enc = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
            enc.fit(cat_train)
            cat_train_enc = enc.transform(cat_train)
            cat_test_enc = enc.transform(cat_test)
            X_train = np.hstack([X_train_num.values, cat_train_enc])
            X_test = np.hstack([X_test_num.values, cat_test_enc])
        else:
            X_train = X_train_num.values
            X_test = X_test_num.values

        model = Ridge(alpha=1.0)
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        bcf = duan_smearing_factor(y_train, model.predict(X_train))
        kge_result = kge(y_test, y_pred, return_components=True)
        native = native_space_metrics(y_test, y_pred, smearing_factor=bcf)

        fold_metrics.append({
            "site_id": test_site,
            "r2_log": r_squared(y_test, y_pred),
            "kge_log": kge_result["kge"],
            "kge_r": kge_result["kge_r"],
            "kge_alpha": kge_result["kge_alpha"],
            "kge_beta": kge_result["kge_beta"],
            "r2_native": native["r2_native"],
            "rmse_native_mgL": native["rmse_native_mgL"],
            "pbias_native": native["pbias_native"],
            "smearing_factor": bcf,
            "n_test": len(y_test),
        })

        test_discharge = discharge_vals[test_idx]
        for i in range(len(y_test)):
            sample_records.append({
                "site_id": test_site,
                "y_true_log": float(y_test[i]),
                "y_pred_log": float(y_pred[i]),
                "y_pred_native_mgL": float(np.expm1(y_pred[i]) * bcf),
                "y_true_native_mgL": float(np.expm1(y_test[i])),
                "discharge_instant": float(test_discharge[i]),
            })

    if not fold_metrics:
        return {"r2_log": np.nan, "kge_log": np.nan, "n_folds": 0}, pd.DataFrame(), pd.DataFrame()

    metrics_df = pd.DataFrame(fold_metrics)
    samples_df = pd.DataFrame(sample_records)
    summary = {
        "r2_log": metrics_df["r2_log"].median(),
        "kge_log": metrics_df["kge_log"].median(),
        "r2_native": metrics_df["r2_native"].median(),
        "rmse_native_mgL": metrics_df["rmse_native_mgL"].median(),
        "pbias_native": metrics_df["pbias_native"].median(),
        "smearing_factor": metrics_df["smearing_factor"].median(),
        "n_folds": len(metrics_df),
        "n_samples": len(clean),
    }
    return summary, metrics_df, samples_df


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

        # Compute Duan's smearing factor from training residuals
        y_train_pred = model.predict(
            Pool(X_train_df.iloc[sub_train_idx], cat_features=cat_indices)
        )
        bcf = duan_smearing_factor(y_train[sub_train_idx], y_train_pred)

        # KGE with decomposition (log-space)
        kge_result = kge(y_test, y_pred, return_components=True)

        # Native-space metrics (mg/L) with smearing correction
        native = native_space_metrics(y_test, y_pred, smearing_factor=bcf)

        fold_metrics.append({
            "site_id": test_site,
            "r2_log": r_squared(y_test, y_pred),
            "kge_log": kge_result["kge"],
            "kge_r": kge_result["kge_r"],
            "kge_alpha": kge_result["kge_alpha"],
            "kge_beta": kge_result["kge_beta"],
            "r2_native": native["r2_native"],
            "rmse_native_mgL": native["rmse_native_mgL"],
            "pbias_native": native["pbias_native"],
            "smearing_factor": bcf,
            "n_test": len(y_test),
        })

        # Per-sample predictions for flow stratification
        test_discharge = discharge_vals[test_idx]
        for i in range(len(y_test)):
            sample_records.append({
                "site_id": test_site,
                "y_true_log": float(y_test[i]),
                "y_pred_log": float(y_pred[i]),
                "y_pred_native_mgL": float(np.expm1(y_pred[i]) * bcf),
                "y_true_native_mgL": float(np.expm1(y_test[i])),
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
        "r2_native": metrics_df["r2_native"].median(),
        "rmse_native_mgL": metrics_df["rmse_native_mgL"].median(),
        "pbias_native": metrics_df["pbias_native"].median(),
        "smearing_factor": metrics_df["smearing_factor"].median(),
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

    # Data integrity checks (added 2026-03-24 after prune_gagesii bug)
    if "gagesii" in tier_name.lower() or "C_" in tier_name:
        expected_cats = {"geol_class", "ecoregion", "reference_class", "huc2"}
        found_cats = set(cat_available)
        missing_cats = expected_cats - found_cats - {"huc2"}  # huc2 may be in basic, not gagesii
        if missing_cats:
            logger.warning(
                f"  INTEGRITY: Tier {tier_name} missing expected categoricals: {missing_cats}. "
                f"Found: {found_cats}. Check that GAGES-II attributes were not destroyed."
            )
    # Check for all-NaN numeric features
    all_nan_cols = [c for c in numeric_available if tier_data[c].isna().all()]
    if all_nan_cols:
        logger.warning(
            f"  INTEGRITY: {len(all_nan_cols)} feature(s) are entirely NaN: {all_nan_cols[:5]}..."
        )
    # Check for zero-variance numeric features
    zero_var_cols = [c for c in numeric_available if tier_data[c].dropna().nunique() <= 1]
    if zero_var_cols:
        logger.warning(
            f"  INTEGRITY: {len(zero_var_cols)} feature(s) have zero variance: {zero_var_cols[:5]}..."
        )

    if len(numeric_available) == 0:
        return {"r2_log": np.nan, "kge_log": np.nan, "n_folds": 0, "n_samples": 0}

    # Run Ridge linear baseline
    ridge_summary, ridge_folds, ridge_samples = train_ridge_logo(
        tier_data, all_available, target_col, cat_features=cat_available
    )
    logger.info(
        f"    Ridge baseline: R²(log)={ridge_summary['r2_log']:.3f}  "
        f"R²(mg/L)={ridge_summary.get('r2_native', float('nan')):.3f}"
    )

    # Run CatBoost
    summary, folds_df, samples_df = train_catboost_logo_quick(
        tier_data, all_available, target_col, cat_features=cat_available
    )
    summary["param"] = param_name
    summary["tier"] = tier_name
    summary["n_features"] = len(all_available)
    summary["ridge_r2_log"] = ridge_summary["r2_log"]
    summary["ridge_r2_native"] = ridge_summary.get("r2_native", np.nan)

    # Save per-fold and per-sample results
    results_dir = DATA_DIR / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    safe_tier = tier_name.replace("/", "_")
    if not folds_df.empty:
        folds_df.to_parquet(results_dir / f"logo_folds_{param_name}_{safe_tier}.parquet", index=False)
    if not samples_df.empty:
        samples_df.to_parquet(results_dir / f"logo_predictions_{param_name}_{safe_tier}.parquet", index=False)
    # Save Ridge folds too for comparison
    if not ridge_folds.empty:
        ridge_folds.to_parquet(results_dir / f"logo_folds_{param_name}_{safe_tier}_ridge.parquet", index=False)

    return summary


def main():
    warnings.filterwarnings("ignore")
    start_run("train_tiered")

    parser = argparse.ArgumentParser(description="Train tiered models")
    parser.add_argument("--param", type=str, default=None, choices=list(PARAM_CONFIG.keys()))
    parser.add_argument("--tier", type=str, default=None, choices=["A", "B", "C"])
    args = parser.parse_args()

    # Load attributes
    basic_attrs = pd.read_parquet(DATA_DIR / "site_attributes.parquet")
    log_file(DATA_DIR / "site_attributes.parquet", role="input")
    gagesii_path = DATA_DIR / "site_attributes_gagesii.parquet"
    gagesii_attrs = None
    if gagesii_path.exists():
        gagesii_raw = pd.read_parquet(gagesii_path)
        gagesii_attrs = prune_gagesii(gagesii_raw)
        log_file(gagesii_path, role="input")

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
        log_file(dataset_path, role="input")
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
            logger.info(
                f"    R²(log)={result['r2_log']:.3f}  KGE(log)={result['kge_log']:.3f}  |  "
                f"R²(mg/L)={result.get('r2_native', float('nan')):.3f}  "
                f"RMSE(mg/L)={result.get('rmse_native_mgL', float('nan')):.1f}  "
                f"Bias={result.get('pbias_native', float('nan')):.1f}%  "
                f"BCF={result.get('smearing_factor', float('nan')):.3f}"
            )

    # Summary table
    if all_results:
        results_df = pd.DataFrame(all_results)
        logger.info(f"\n{'='*60}")
        logger.info("TIERED COMPARISON")
        logger.info(f"{'='*60}")

        pivot = results_df.pivot_table(
            index="param", columns="tier", values="r2_log", aggfunc="first"
        )
        logger.info(f"\nMedian R² (log-space) by parameter × tier:")
        logger.info(f"\n{pivot.to_string()}")

        pivot_native = results_df.pivot_table(
            index="param", columns="tier", values="r2_native", aggfunc="first"
        )
        logger.info(f"\nMedian R² (native mg/L, Duan-corrected) by parameter × tier:")
        logger.info(f"\n{pivot_native.to_string()}")

        pivot_rmse = results_df.pivot_table(
            index="param", columns="tier", values="rmse_native_mgL", aggfunc="first"
        )
        logger.info(f"\nMedian RMSE (mg/L) by parameter × tier:")
        logger.info(f"\n{pivot_rmse.to_string()}")

        pivot_bias = results_df.pivot_table(
            index="param", columns="tier", values="pbias_native", aggfunc="first"
        )
        logger.info(f"\nMedian % Bias (native) by parameter × tier:")
        logger.info(f"\n{pivot_bias.to_string()}")

        pivot_kge = results_df.pivot_table(
            index="param", columns="tier", values="kge_log", aggfunc="first"
        )
        logger.info(f"\nMedian KGE (log-space) by parameter × tier:")
        logger.info(f"\n{pivot_kge.to_string()}")

        # Save CV results
        out_path = DATA_DIR / "results" / "tiered_comparison.parquet"
        results_df.to_parquet(out_path, index=False)
        log_file(out_path, role="output")
        for _, row in results_df.iterrows():
            log_step("logo_cv", param=row["param"], tier=row["tier"],
                     r2_log=round(float(row["r2_log"]), 4),
                     kge_log=round(float(row["kge_log"]), 4),
                     r2_native=round(float(row.get("r2_native", float("nan"))), 4),
                     rmse_native_mgL=round(float(row.get("rmse_native_mgL", float("nan"))), 2),
                     pbias_native=round(float(row.get("pbias_native", float("nan"))), 2),
                     smearing_factor=round(float(row.get("smearing_factor", float("nan"))), 4),
                     n_folds=int(row["n_folds"]),
                     n_samples=int(row["n_samples"]))
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

            # Compute Duan's smearing factor for the final model
            y_train_pred_final = model.predict(train_pool)
            final_bcf = duan_smearing_factor(y[train_idx], y_train_pred_final)

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
                "duan_smearing_factor": final_bcf,
            }
            # Post-training integrity checks (added 2026-03-24)
            nan_ranges = [c for c, r in feature_ranges.items()
                          if np.isnan(r["min"]) or np.isnan(r["max"])]
            if nan_ranges:
                logger.warning(
                    f"  INTEGRITY: {len(nan_ranges)} feature(s) have NaN min/max in ranges: "
                    f"{nan_ranges[:5]}... Features may have been destroyed."
                )
            if "gagesii" in tier_name.lower() and not cat_values_seen:
                logger.warning(
                    f"  INTEGRITY: Tier {tier_name} has no categorical values seen. "
                    f"Expected geol_class, ecoregion, reference_class."
                )
            if "gagesii" in tier_name.lower() and not sites_per_ecoregion:
                logger.warning(
                    f"  INTEGRITY: Tier {tier_name} has empty sites_per_ecoregion. "
                    f"Ecoregion data may not have been loaded."
                )

            meta_path = model_dir / f"{param_name}_{safe_tier}_meta.json"
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)

            size_kb = model_path.stat().st_size / 1024
            logger.info(f"  Saved {param_name}/{tier_name}: {model.tree_count_} trees, "
                       f"{size_kb:.0f} KB → {model_path.name}")
            log_file(model_path, role="output")
            log_file(meta_path, role="output")
            log_step("save_model", param=param_name, tier=tier_name,
                     n_trees=model.tree_count_, n_sites=meta["n_sites"],
                     n_cat_cols=len(cat_cols))

            # SHAP analysis for Tier C models (where GAGES-II features are)
            if "C_" in tier_name or "gagesii" in tier_name.lower():
                try:
                    import shap
                    logger.info(f"  Computing SHAP values for {param_name}/{tier_name}...")

                    # Use a sample for speed (SHAP on full dataset is slow)
                    shap_sample_size = min(2000, len(X_df))
                    rng = np.random.default_rng(42)
                    shap_idx = rng.choice(len(X_df), shap_sample_size, replace=False)
                    X_shap = X_df.iloc[shap_idx]

                    explainer = shap.TreeExplainer(model)
                    shap_values = explainer.shap_values(Pool(X_shap, cat_features=cat_indices))

                    # Global feature importance (mean |SHAP|)
                    mean_abs_shap = np.abs(shap_values).mean(axis=0)
                    shap_importance = sorted(
                        zip(all_cols, mean_abs_shap),
                        key=lambda x: x[1], reverse=True
                    )

                    logger.info(f"  SHAP top-15 features:")
                    for fname, fval in shap_importance[:15]:
                        logger.info(f"    {fname:30s} {fval:.4f}")

                    # Save SHAP values and importance
                    shap_df = pd.DataFrame(shap_values, columns=all_cols)
                    shap_df["site_id"] = clean["site_id"].iloc[shap_idx].values
                    shap_path = results_dir / f"shap_values_{param_name}_{safe_tier}.parquet"
                    shap_df.to_parquet(shap_path, index=False)

                    importance_df = pd.DataFrame(shap_importance, columns=["feature", "mean_abs_shap"])
                    importance_path = results_dir / f"shap_importance_{param_name}_{safe_tier}.parquet"
                    importance_df.to_parquet(importance_path, index=False)

                    log_file(shap_path, role="output")
                    log_file(importance_path, role="output")
                    log_step("shap_analysis", param=param_name, tier=tier_name,
                             n_samples=shap_sample_size,
                             top_feature=shap_importance[0][0],
                             top_feature_importance=round(float(shap_importance[0][1]), 4))

                except ImportError:
                    logger.warning("  shap package not installed — skipping SHAP analysis")
                except Exception as e:
                    logger.warning(f"  SHAP analysis failed: {e}")

    end_run()


if __name__ == "__main__":
    main()
