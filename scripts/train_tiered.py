"""Train models across all feature tiers and parameters.

Runs CatBoost LOGO CV for each combination of:
- Parameter: ssc, total_phosphorus, nitrate_nitrite, orthophosphate
- Tier: A (sensor-only), B (sensor+basic), C (sensor+StreamCat)

Produces a comparison table showing how catchment attributes affect performance.

Usage:
    python scripts/train_tiered.py
    python scripts/train_tiered.py --param total_phosphorus
    python scripts/train_tiered.py --tier C
    python scripts/train_tiered.py --transform boxcox --n-jobs 4
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import LeaveOneGroupOut, GroupShuffleSplit, GroupKFold

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from murkml.data.attributes import build_feature_tiers, load_streamcat_attrs
from murkml.evaluate.metrics import (
    kge, percent_bias, r_squared, rmse,
    duan_smearing_factor, snowdon_bcf, native_space_metrics,
    safe_inv_boxcox1p,
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
    transform_type: str = "log1p",
    transform_lmbda: float | None = None,
    sample_weights: np.ndarray | None = None,
    fixed_lambda: bool = False,
) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Run Ridge regression LOGO CV as a linear baseline.

    Uses the same splits and preprocessing as CatBoost for fair comparison.
    Categorical features are one-hot encoded. Returns same format as CatBoost version.
    """
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import OneHotEncoder

    clean_mask = df[target_col].notna()
    clean = df.loc[clean_mask].copy()
    sites = clean["site_id"].values
    y = clean[target_col].values
    lab_values = clean["lab_value"].values if "lab_value" in clean.columns else None

    # Align sample weights to clean rows
    if sample_weights is not None:
        clean_weights = sample_weights[clean_mask.values]
    else:
        clean_weights = None

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
        y_train = y[train_idx].copy()
        y_test = y[test_idx].copy()
        test_site = sites[test_idx][0]

        if len(y_test) < 5:
            continue

        # Per-fold Box-Cox refit (skip when using manual fixed lambda)
        fold_lmbda = transform_lmbda
        if transform_type == "boxcox" and lab_values is not None and not fixed_lambda:
            from scipy.stats import boxcox_normmax
            from scipy.special import boxcox1p
            raw_train = lab_values[train_idx]
            fold_lmbda = float(boxcox_normmax(raw_train + 1, method="mle"))
            # Re-transform targets with fold-specific lambda
            y_train = boxcox1p(raw_train, fold_lmbda)
            raw_test = lab_values[test_idx]
            y_test = boxcox1p(raw_test, fold_lmbda)

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
        fold_weights = clean_weights[train_idx] if clean_weights is not None else None
        model.fit(X_train, y_train, sample_weight=fold_weights)
        y_pred = model.predict(X_test)

        # BCF: Duan for log1p, Snowdon for boxcox/sqrt
        if transform_type == "log1p":
            bcf = duan_smearing_factor(y_train, model.predict(X_train))
        else:
            # Snowdon: needs native-space predictions (uncorrected)
            y_train_pred = model.predict(X_train)
            if transform_type == "boxcox":
                train_native_true = lab_values[train_idx]
                train_native_pred = safe_inv_boxcox1p(y_train_pred, fold_lmbda)
            else:  # sqrt
                train_native_true = np.square(y_train)
                train_native_pred = np.square(y_train_pred)
            bcf = snowdon_bcf(train_native_true, train_native_pred)

        kge_result = kge(y_test, y_pred, return_components=True)
        native = native_space_metrics(
            y_test, y_pred, smearing_factor=bcf,
            transform=transform_type, lmbda=fold_lmbda,
        )

        # Back-transform for per-sample output
        if transform_type == "log1p":
            y_pred_native = np.expm1(y_pred) * bcf
            y_true_native = np.expm1(y_test)
        elif transform_type == "boxcox":
            y_true_native = lab_values[test_idx]
            y_pred_native = safe_inv_boxcox1p(y_pred, fold_lmbda) * bcf
        else:  # sqrt
            y_true_native = np.square(y_test)
            y_pred_native = np.square(y_pred) * bcf

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
            "fold_lmbda": fold_lmbda,
        })

        test_discharge = discharge_vals[test_idx]
        for i in range(len(y_test)):
            sample_records.append({
                "site_id": test_site,
                "y_true_log": float(y_test[i]),
                "y_pred_log": float(y_pred[i]),
                "y_pred_native_mgL": float(y_pred_native[i]),
                "y_true_native_mgL": float(y_true_native[i]),
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


# Feature whitelists for pruning (Dr. Dalton hydrology review + SHAP analysis)
_MINIMAL_FEATURES = {
    # Sensor (11)
    "turbidity_instant", "turbidity_mean_1hr", "turbidity_max_1hr",
    "turbidity_std_1hr", "turbidity_slope_1hr", "conductance_instant",
    "Q_ratio_7d", "turb_Q_ratio", "precip_24h", "doy_sin", "doy_cos",
    # Watershed (15)
    "latitude", "longitude", "elevation_m", "drainage_area_km2",
    "forest_pct", "clay_pct", "soil_erodibility", "soil_permeability",
    "water_table_depth", "hydraulic_conductivity", "precip_mean_mm",
    "baseflow_index", "mine_density", "dam_density", "geo_k2o",
}

# Features to DROP for "pruned" set (zero-SHAP or no physical basis)
_DROP_FOR_PRUNED = {
    # Sensor features with no value when turbidity is present
    "discharge_instant", "rising_limb", "Q_7day_mean", "Q_30day_mean",
    "do_instant", "DO_sat_departure", "SC_turb_interaction",
    "ph_instant", "temp_instant",
    # Redundant turbidity stats
    "turbidity_min_1hr", "turbidity_range_1hr",
    # Weather features with zero/near-zero SHAP
    "days_since_rain", "precip_7d", "precip_30d", "temp_at_sample",
    # Categoricals with zero SHAP
    "geol_class", "huc2",
    # Sparse surficial geology percentages
    "pct_carbonate_resid", "pct_glacial_till_loam", "pct_glacial_till_coarse",
    "pct_coastal_coarse", "pct_eolian_coarse", "pct_saline_lake",
    "pct_glacial_till_clay", "pct_alkaline_intrusive", "pct_extrusive_volcanic",
    "pct_glacial_lake_fine", "pct_eolian_fine",
    # Geochemistry with zero SHAP
    "geo_cao", "geo_fe2o3", "compressive_strength",
    # Anthropogenic with no sediment mechanism
    "npdes_density", "wwtp_all_density", "wwtp_major_density", "wwtp_minor_density",
    "bio_n_fixation",
}


def _filter_feature_set(feature_cols: list[str], feature_set: str) -> list[str]:
    """Filter features based on pruning level."""
    if feature_set == "minimal":
        filtered = [c for c in feature_cols if c in _MINIMAL_FEATURES]
        logger.info(f"    Feature set 'minimal': {len(feature_cols)} → {len(filtered)} features")
        return filtered
    elif feature_set == "pruned":
        filtered = [c for c in feature_cols if c not in _DROP_FOR_PRUNED]
        logger.info(f"    Feature set 'pruned': {len(feature_cols)} → {len(filtered)} features")
        return filtered
    return feature_cols


def _assign_stratified_groups(df: pd.DataFrame, target_col: str, n_splits: int = 5) -> np.ndarray:
    """Assign sites to GroupKFold groups with stratification.

    Sorts sites by median target value (descending), then round-robin assigns
    to folds. This ensures each fold gets a mix of high and low SSC sites.
    ISCO autosampler clusters are handled automatically since all samples from
    one site stay in the same fold.

    Returns array of group assignments (0 to n_splits-1), one per row in df.
    """
    site_stats = df.groupby("site_id").agg(
        median_target=(target_col, "median"),
        count=("site_id", "size"),
    ).reset_index()

    # Sort by median target descending, then round-robin assign
    site_stats = site_stats.sort_values("median_target", ascending=False).reset_index(drop=True)
    site_stats["fold"] = site_stats.index % n_splits

    # Map back to per-row group assignments
    site_to_fold = dict(zip(site_stats["site_id"], site_stats["fold"]))
    return df["site_id"].map(site_to_fold).values


def _build_monotone_constraints(feature_cols: list[str]) -> dict[int, int]:
    """Build monotone constraint dict for CatBoost.

    Higher turbidity → higher SSC (monotonically increasing).
    Only constrains level-based turbidity features, NOT std/range/slope.
    """
    constraints = {}
    monotone_features = {"turbidity_instant", "turbidity_mean_1hr",
                         "turbidity_min_1hr", "turbidity_max_1hr"}
    for i, col in enumerate(feature_cols):
        if col in monotone_features:
            constraints[i] = 1  # monotonically increasing
    return constraints


def _train_one_fold(
    fold_idx: int,
    train_idx: np.ndarray,
    test_idx: np.ndarray,
    X_df: pd.DataFrame,
    y: np.ndarray,
    sites: np.ndarray,
    lab_values: np.ndarray | None,
    discharge_vals: np.ndarray,
    num_cols: list[str],
    cat_indices: list[int],
    transform_type: str,
    transform_lmbda: float | None,
    thread_count: int,
    sample_weights: np.ndarray | None = None,
    monotone_constraints: dict | None = None,
    quantile_mode: bool = False,
    cb_overrides: dict | None = None,
    fixed_lambda: bool = False,
    kge_eval: bool = False,
) -> tuple[dict | None, list[dict]]:
    """Train and evaluate a single LOGO fold. Returns (fold_metric, sample_records)."""
    from catboost import CatBoostRegressor, Pool

    y_train = y[train_idx].copy()
    y_test = y[test_idx].copy()
    test_site = sites[test_idx][0]

    if len(y_test) < 5:
        return None, []

    # Per-fold Box-Cox refit from raw lab_value (skip when using manual fixed lambda)
    fold_lmbda = transform_lmbda
    if transform_type == "boxcox" and lab_values is not None and not fixed_lambda:
        from scipy.stats import boxcox_normmax
        from scipy.special import boxcox1p
        raw_train = lab_values[train_idx]
        fold_lmbda = float(boxcox_normmax(raw_train + 1, method="mle"))
        y_train = boxcox1p(raw_train, fold_lmbda)
        raw_test = lab_values[test_idx]
        y_test = boxcox1p(raw_test, fold_lmbda)

    X_train_df = X_df.iloc[train_idx]
    X_test_df = X_df.iloc[test_idx]

    train_median = X_train_df[num_cols].median()
    X_train_df = X_train_df.copy()
    X_test_df = X_test_df.copy()
    X_train_df[num_cols] = X_train_df[num_cols].fillna(train_median)
    X_test_df[num_cols] = X_test_df[num_cols].fillna(train_median)

    gss = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=42)
    train_sites = sites[train_idx]
    sub_train_idx, val_idx = next(gss.split(X_train_df, y_train, groups=train_sites))

    # Slice weights for this fold's train/val split
    fold_train_weights = None
    fold_val_weights = None
    if sample_weights is not None:
        fold_weights = sample_weights[train_idx]
        fold_train_weights = fold_weights[sub_train_idx]
        fold_val_weights = fold_weights[val_idx]

    train_pool = Pool(
        X_train_df.iloc[sub_train_idx], y_train[sub_train_idx],
        cat_features=cat_indices,
        weight=fold_train_weights,
    )
    val_pool = Pool(
        X_train_df.iloc[val_idx], y_train[val_idx],
        cat_features=cat_indices,
        weight=fold_val_weights,
    )
    test_pool = Pool(X_test_df, cat_features=cat_indices)

    # Build CatBoost params
    cb_params = dict(
        iterations=500, learning_rate=0.05, depth=6,
        l2_leaf_reg=3, random_seed=42, verbose=0,
        early_stopping_rounds=50,
        thread_count=thread_count,
        boosting_type="Ordered",
    )
    if monotone_constraints:
        cb_params["monotone_constraints"] = monotone_constraints
    if quantile_mode:
        cb_params["loss_function"] = "MultiQuantile:alpha=0.05,0.1,0.25,0.5,0.75,0.9,0.95"
    if kge_eval:
        from murkml.evaluate.metrics import KGEMetric
        cb_params["eval_metric"] = KGEMetric()
    if cb_overrides:
        cb_params.update(cb_overrides)

    model = CatBoostRegressor(**cb_params)
    model.fit(train_pool, eval_set=val_pool)

    raw_pred = model.predict(test_pool)

    # Handle MultiQuantile output: shape (n_samples, 7)
    if quantile_mode:
        raw_pred = np.array(raw_pred)
        if raw_pred.ndim == 2:
            # Sort to prevent quantile crossing
            raw_pred = np.sort(raw_pred, axis=1)
            # Median (index 3 = 0.5 quantile) for point metrics
            y_pred = raw_pred[:, 3]
            quantile_preds = raw_pred  # keep all quantiles
        else:
            y_pred = raw_pred
            quantile_preds = None
    else:
        y_pred = raw_pred
        quantile_preds = None

    # BCF: Duan for log1p, Snowdon for boxcox/sqrt
    y_train_pred_raw = model.predict(
        Pool(X_train_df.iloc[sub_train_idx], cat_features=cat_indices)
    )
    # In quantile mode, extract median for BCF computation
    if quantile_mode and np.ndim(y_train_pred_raw) == 2:
        y_train_pred = np.sort(np.array(y_train_pred_raw), axis=1)[:, 3]
    else:
        y_train_pred = y_train_pred_raw
    if transform_type == "log1p":
        bcf = duan_smearing_factor(y_train[sub_train_idx], y_train_pred)
    else:
        if transform_type == "boxcox":
            train_native_true = lab_values[train_idx][sub_train_idx]
            train_native_pred = safe_inv_boxcox1p(y_train_pred, fold_lmbda)
        else:  # sqrt
            train_native_true = np.square(y_train[sub_train_idx])
            train_native_pred = np.square(y_train_pred)
        bcf = snowdon_bcf(train_native_true, train_native_pred)

    # KGE with decomposition (transformed-space)
    kge_result = kge(y_test, y_pred, return_components=True)

    # Native-space metrics with smearing correction
    native = native_space_metrics(
        y_test, y_pred, smearing_factor=bcf,
        transform=transform_type, lmbda=fold_lmbda,
    )

    # Back-transform for per-sample output
    if transform_type == "log1p":
        y_pred_native = np.expm1(y_pred) * bcf
        y_true_native = np.expm1(y_test)
    elif transform_type == "boxcox":
        y_true_native = lab_values[test_idx]
        y_pred_native = safe_inv_boxcox1p(y_pred, fold_lmbda) * bcf
    else:  # sqrt
        y_true_native = np.square(y_test)
        y_pred_native = np.square(y_pred) * bcf

    fold_metric = {
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
        "fold_lmbda": fold_lmbda,
        "n_trees": model.tree_count_,
    }

    # Per-sample predictions for flow stratification
    test_discharge = discharge_vals[test_idx]
    sample_records = []
    quantile_labels = ["q05", "q10", "q25", "q50", "q75", "q90", "q95"]
    for i in range(len(y_test)):
        record = {
            "site_id": test_site,
            "y_true_log": float(y_test[i]),
            "y_pred_log": float(y_pred[i]),
            "y_pred_native_mgL": float(y_pred_native[i]),
            "y_true_native_mgL": float(y_true_native[i]),
            "discharge_instant": float(test_discharge[i]),
        }
        if quantile_preds is not None:
            for j, qlabel in enumerate(quantile_labels):
                record[qlabel] = float(quantile_preds[i, j])
        sample_records.append(record)

    return fold_metric, sample_records


def train_catboost_logo_quick(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str = "ssc_log1p",
    cat_features: list[str] | None = None,
    transform_type: str = "log1p",
    transform_lmbda: float | None = None,
    n_jobs: int = 6,
    thread_count: int = 4,
    sample_weights: np.ndarray | None = None,
    monotone_constraints: dict | None = None,
    quantile_mode: bool = False,
    cb_overrides: dict | None = None,
    cv_mode: str = "logo",
    fixed_lambda: bool = False,
    kge_eval: bool = False,
) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Run CatBoost CV with joblib parallelization.

    cv_mode: "logo" (LeaveOneGroupOut, 243+ folds) or "gkf5" (GroupKFold 5 folds, ~25x faster)
    Returns (summary, fold_metrics_df, per_sample_df).
    """
    from joblib import Parallel, delayed

    clean_mask = df[target_col].notna()
    clean = df.loc[clean_mask].copy()
    sites = clean["site_id"].values
    y = clean[target_col].values
    lab_values = clean["lab_value"].values if "lab_value" in clean.columns else None

    # Align sample weights to clean rows
    if sample_weights is not None:
        clean_weights = sample_weights[clean_mask.values]
    else:
        clean_weights = None

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

    if cv_mode == "gkf5":
        fold_assignments = _assign_stratified_groups(clean, target_col, n_splits=5)
        splits = []
        for fold_id in range(5):
            test_mask = fold_assignments == fold_id
            test_idx = np.where(test_mask)[0]
            train_idx = np.where(~test_mask)[0]
            splits.append((train_idx, test_idx))
        fold_sizes = [len(t) for _, t in splits]
        logger.info(f"    GroupKFold(5) stratified: {len(splits)} folds "
                    f"(test sizes: {fold_sizes})")
    else:
        logo = LeaveOneGroupOut()
        splits = [
            (train_idx, test_idx)
            for train_idx, test_idx in logo.split(X_df, y, groups=sites)
        ]

    # Parallel LOGO folds
    results = Parallel(n_jobs=n_jobs, backend="loky")(
        delayed(_train_one_fold)(
            fold_idx, train_idx, test_idx,
            X_df, y, sites, lab_values, discharge_vals,
            num_cols, cat_indices,
            transform_type, transform_lmbda, thread_count,
            sample_weights=clean_weights,
            monotone_constraints=monotone_constraints,
            quantile_mode=quantile_mode,
            cb_overrides=cb_overrides,
            fixed_lambda=fixed_lambda,
            kge_eval=kge_eval,
        )
        for fold_idx, (train_idx, test_idx) in enumerate(splits)
    )

    fold_metrics = []
    sample_records = []
    for fold_metric, fold_samples in results:
        if fold_metric is not None:
            fold_metrics.append(fold_metric)
            sample_records.extend(fold_samples)

    if not fold_metrics:
        empty_folds = pd.DataFrame()
        empty_samples = pd.DataFrame()
        return {"r2_log": np.nan, "kge_log": np.nan, "n_folds": 0}, empty_folds, empty_samples

    metrics_df = pd.DataFrame(fold_metrics)
    samples_df = pd.DataFrame(sample_records)

    # Log per-fold lambdas for boxcox
    if transform_type == "boxcox" and "fold_lmbda" in metrics_df.columns:
        lambdas = metrics_df["fold_lmbda"].dropna()
        logger.info(
            f"    Box-Cox lambdas: median={lambdas.median():.4f}, "
            f"std={lambdas.std():.4f}, range=[{lambdas.min():.4f}, {lambdas.max():.4f}]"
        )

    # Log per-fold tree counts
    if "n_trees" in metrics_df.columns:
        trees = metrics_df["n_trees"]
        logger.info(
            f"    Trees per fold: median={trees.median():.0f}, "
            f"min={trees.min():.0f}, max={trees.max():.0f}"
        )

    # Compute per-site R² from out-of-fold predictions
    # In GKF5, each fold has multiple sites — use sample_records to get per-site metrics
    per_site_r2_native = []
    if len(samples_df) > 0 and "site_id" in samples_df.columns:
        for site_id, sdf in samples_df.groupby("site_id"):
            yt = sdf["y_true_native_mgL"].values
            yp = sdf["y_pred_native_mgL"].values
            if len(yt) >= 2:
                ss_tot = np.sum((yt - yt.mean()) ** 2)
                if ss_tot > 1e-10:
                    ss_res = np.sum((yt - yp) ** 2)
                    per_site_r2_native.append(1 - ss_res / ss_tot)

    median_per_site_r2 = float(np.nanmedian(per_site_r2_native)) if per_site_r2_native else np.nan
    if per_site_r2_native:
        logger.info(
            f"    Per-site R²(native): median={median_per_site_r2:.4f}, "
            f"n_sites={len(per_site_r2_native)}"
        )

    summary = {
        "r2_log": metrics_df["r2_log"].median(),
        "kge_log": metrics_df["kge_log"].median(),
        "kge_alpha": metrics_df["kge_alpha"].median() if "kge_alpha" in metrics_df.columns else None,
        "kge_beta": metrics_df["kge_beta"].median() if "kge_beta" in metrics_df.columns else None,
        "r2_native": metrics_df["r2_native"].median(),
        "rmse_native_mgL": metrics_df["rmse_native_mgL"].median(),
        "pbias_native": metrics_df["pbias_native"].median(),
        "smearing_factor": metrics_df["smearing_factor"].median(),
        "n_folds": len(metrics_df),
        "n_samples": len(clean),
        "median_trees": float(metrics_df["n_trees"].median()) if "n_trees" in metrics_df.columns else None,
        "median_per_site_r2": median_per_site_r2,
    }
    return summary, metrics_df, samples_df


def run_tier(param_name: str, tier_name: str, tier_data: pd.DataFrame,
             feature_cols: list[str], target_col: str, *,
             transform_type: str = "log1p", transform_lmbda: float | None = None,
             fixed_lambda: bool = False,
             n_jobs: int = 6, thread_count: int = 4,
             weight_scheme: str | None = None,
             slope_correction: bool = False,
             quantile_mode: bool = False,
             no_monotone: bool = False,
             feature_set: str = "full",
             cb_overrides: dict | None = None,
             drop_features: set | None = None,
             label: str | None = None,
             skip_ridge: bool = False,
             cv_mode: str = "logo",
             kge_eval: bool = False) -> dict:
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

    # Feature set pruning (based on domain expert + SHAP review)
    if feature_set != "full":
        all_available = _filter_feature_set(all_available, feature_set)
        numeric_available = [c for c in all_available if c in numeric_available or (c in tier_data.columns and tier_data[c].dtype in [np.float64, np.float32, np.int64, np.int32, float, int])]
        cat_available = [c for c in all_available if c not in numeric_available]

    # Drop specific features (for ablation experiments)
    if drop_features:
        before = len(all_available)
        all_available = [c for c in all_available if c not in drop_features]
        numeric_available = [c for c in numeric_available if c not in drop_features]
        cat_available = [c for c in cat_available if c not in drop_features]
        logger.info(f"    Dropped {before - len(all_available)} features: {sorted(drop_features & set(all_available + list(drop_features)))}")

    logger.info(f"  {param_name} / {tier_name}: {tier_data['site_id'].nunique()} sites, "
                f"{len(tier_data)} samples, {len(numeric_available)} numeric + {len(cat_available)} categorical features")

    # Data integrity checks (added 2026-03-24 after prune_gagesii bug)
    if "watershed" in tier_name.lower() or "C_" in tier_name:
        found_cats = set(cat_available)
        if not found_cats:
            logger.warning(
                f"  INTEGRITY: Tier {tier_name} has no categorical features. "
                f"Check that watershed attributes were loaded correctly."
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

    # Compute sample weights from tier_data's lab_value (safe across merges)
    if weight_scheme is not None and "lab_value" in tier_data.columns:
        lv = tier_data["lab_value"].values
        if weight_scheme == "sqrt":
            sample_weights = np.sqrt(lv)
        elif weight_scheme == "log":
            sample_weights = np.log1p(lv)
        elif weight_scheme == "linear":
            sample_weights = lv.copy()
        else:
            sample_weights = None
        if sample_weights is not None:
            sample_weights = sample_weights / sample_weights.mean()  # normalize to mean=1
    else:
        sample_weights = None

    # Run Ridge linear baseline
    if skip_ridge:
        ridge_summary = {"r2_log": np.nan, "r2_native": np.nan}
        ridge_folds = pd.DataFrame()
        ridge_samples = pd.DataFrame()
        logger.info("    Ridge baseline: SKIPPED")
    else:
        ridge_summary, ridge_folds, ridge_samples = train_ridge_logo(
            tier_data, all_available, target_col, cat_features=cat_available,
            transform_type=transform_type, transform_lmbda=transform_lmbda,
            sample_weights=sample_weights, fixed_lambda=fixed_lambda,
        )
        logger.info(
            f"    Ridge baseline: R²(log)={ridge_summary['r2_log']:.3f}  "
            f"R²(mg/L)={ridge_summary.get('r2_native', float('nan')):.3f}"
        )

    # Build monotone constraints (unless --no-monotone)
    if no_monotone:
        monotone_map = {}
        logger.info("    Monotone constraints: DISABLED")
    else:
        monotone_map = _build_monotone_constraints(all_available)
        if monotone_map:
            logger.info(f"    Monotone constraints on {len(monotone_map)} features: "
                        f"{[all_available[i] for i in monotone_map]}")

    # Run CatBoost
    summary, folds_df, samples_df = train_catboost_logo_quick(
        tier_data, all_available, target_col, cat_features=cat_available,
        transform_type=transform_type, transform_lmbda=transform_lmbda,
        n_jobs=n_jobs, thread_count=thread_count,
        sample_weights=sample_weights,
        monotone_constraints=monotone_map if monotone_map else None,
        quantile_mode=quantile_mode,
        cb_overrides=cb_overrides,
        cv_mode=cv_mode,
        fixed_lambda=fixed_lambda,
        kge_eval=kge_eval,
    )

    # Quantile interval coverage stats
    if quantile_mode and not samples_df.empty and "q05" in samples_df.columns:
        y_true_log = samples_df["y_true_log"].values
        q05 = samples_df["q05"].values
        q95 = samples_df["q95"].values
        q10 = samples_df["q10"].values
        q90 = samples_df["q90"].values
        coverage_90 = np.mean((y_true_log >= q05) & (y_true_log <= q95))
        coverage_80 = np.mean((y_true_log >= q10) & (y_true_log <= q90))
        median_width_90 = np.median(q95 - q05)
        median_width_80 = np.median(q90 - q10)
        summary["quantile_coverage_90"] = float(coverage_90)
        summary["quantile_coverage_80"] = float(coverage_80)
        summary["quantile_width_90"] = float(median_width_90)
        summary["quantile_width_80"] = float(median_width_80)
        logger.info(
            f"    Quantile coverage: 90%={coverage_90:.1%} (width={median_width_90:.2f}), "
            f"80%={coverage_80:.1%} (width={median_width_80:.2f})"
        )

    # Post-hoc slope correction on out-of-fold predictions
    if slope_correction and not samples_df.empty:
        from murkml.evaluate.metrics import fit_slope_correction, apply_slope_correction
        sc_slope, sc_intercept = fit_slope_correction(
            samples_df["y_true_log"].values, samples_df["y_pred_log"].values
        )
        logger.info(f"    Slope correction: y = {sc_slope:.3f} * pred + {sc_intercept:.3f}")

        # Apply and recompute native metrics
        corrected_log = apply_slope_correction(samples_df["y_pred_log"].values, sc_slope, sc_intercept)
        corrected_native = np.expm1(corrected_log)
        true_native = samples_df["y_true_native_mgL"].values

        from scipy.stats import linregress
        corr_slope, _, corr_r, _, _ = linregress(true_native, corrected_native)
        logger.info(f"    After correction: native slope={corr_slope:.3f}, R\u00b2={corr_r**2:.3f}")

        summary["slope_correction_a"] = float(sc_slope)
        summary["slope_correction_b"] = float(sc_intercept)
        summary["r2_native_corrected"] = float(corr_r**2)
        summary["native_slope_corrected"] = float(corr_slope)

    summary["param"] = param_name
    summary["tier"] = tier_name
    summary["n_features"] = len(all_available)
    if label:
        summary["label"] = label
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
    parser.add_argument(
        "--transform", type=str, default="log1p",
        choices=["log1p", "boxcox", "sqrt", "none"],
        help="Target transform: log1p, boxcox, sqrt, or none (raw SSC)",
    )
    parser.add_argument(
        "--n-jobs", type=int, default=6,
        help="Number of parallel LOGO folds via joblib (default: 6)",
    )
    parser.add_argument(
        "--weight-scheme", type=str, default=None,
        choices=["sqrt", "log", "linear"],
        help="Sample weight scheme: sqrt(SSC), log1p(SSC), or raw SSC",
    )
    parser.add_argument(
        "--slope-correction", action="store_true",
        help="Apply post-hoc slope correction on out-of-fold predictions",
    )
    parser.add_argument(
        "--quantile", action="store_true",
        help="Use MultiQuantile loss instead of RMSE (outputs 7 quantiles: 0.05-0.95)",
    )
    parser.add_argument(
        "--no-monotone", action="store_true",
        help="Disable monotone constraints on turbidity features",
    )
    parser.add_argument(
        "--feature-set", type=str, default="full",
        choices=["full", "pruned", "minimal"],
        help="Feature set: full (all), pruned (drop zero-SHAP), minimal (26 physics-based)",
    )
    parser.add_argument(
        "--config-json", type=str, default=None,
        help="JSON string of CatBoost param overrides, e.g. '{\"depth\": 8, \"learning_rate\": 0.01}'",
    )
    parser.add_argument(
        "--label", type=str, default=None,
        help="Label for this experiment run (saved in results)",
    )
    parser.add_argument(
        "--drop-features", type=str, default=None,
        help="Comma-separated feature names to exclude from training",
    )
    parser.add_argument(
        "--cv-mode", type=str, default="logo",
        choices=["logo", "gkf5"],
        help="CV strategy: logo (LeaveOneGroupOut) or gkf5 (GroupKFold 5 folds, ~25x faster)",
    )
    parser.add_argument(
        "--skip-ridge", action="store_true",
        help="Skip Ridge linear baseline",
    )
    parser.add_argument(
        "--skip-save-model", action="store_true",
        help="Skip final model training, saving, and SHAP (ablation only needs CV metrics)",
    )
    parser.add_argument(
        "--skip-shap", action="store_true",
        help="Skip SHAP analysis even when saving models",
    )
    parser.add_argument(
        "--boxcox-lambda", type=float, default=None,
        help="Manual Box-Cox lambda (skips MLE estimation). Use with --transform boxcox.",
    )
    parser.add_argument(
        "--kge-eval", action="store_true",
        help="Use KGE as eval_metric for early stopping instead of RMSE",
    )
    parser.add_argument(
        "--exclude-sites", type=str, default=None,
        help="Path to CSV with site_id column — additional sites to exclude from training/CV",
    )
    parser.add_argument(
        "--include-all-sites", action="store_true",
        help="Override automatic holdout/vault exclusion (DANGEROUS — use only if you know what you're doing)",
    )
    args = parser.parse_args()

    transform_type = args.transform
    n_jobs = args.n_jobs

    # Parse config overrides
    cb_overrides = None
    if args.config_json:
        import json as _json
        cb_overrides = _json.loads(args.config_json)
        logger.info(f"CatBoost overrides: {cb_overrides}")

    # Parse drop features
    drop_features = None
    if args.drop_features:
        drop_features = set(args.drop_features.split(","))
        logger.info(f"Dropping {len(drop_features)} features: {sorted(drop_features)}")

    if args.label:
        logger.info(f"Experiment label: {args.label}")

    # CatBoost threads per job: split total CPU count across parallel folds
    import os
    cpu_count = os.cpu_count() or 24
    thread_count = max(cpu_count // n_jobs, 2)
    logger.info(f"Transform: {transform_type} | n_jobs: {n_jobs} | thread_count/model: {thread_count}")

    # Load attributes
    basic_attrs = pd.read_parquet(DATA_DIR / "site_attributes.parquet")
    log_file(DATA_DIR / "site_attributes.parquet", role="input")
    streamcat_path = DATA_DIR / "site_attributes_streamcat.parquet"
    watershed_attrs = None
    if streamcat_path.exists():
        watershed_attrs = load_streamcat_attrs(DATA_DIR)
        log_file(streamcat_path, role="input")
        logger.info(f"StreamCat attributes: {len(watershed_attrs)} sites, {len(watershed_attrs.columns)-1} features")
    else:
        logger.warning("No StreamCat attributes found — Tier C will be skipped")

    # Merge SGMC lithology features if available
    sgmc_path = DATA_DIR / "sgmc" / "sgmc_features_for_model.parquet"
    if sgmc_path.exists() and watershed_attrs is not None:
        sgmc = pd.read_parquet(sgmc_path)
        n_before = len(watershed_attrs.columns)
        watershed_attrs = watershed_attrs.merge(sgmc, on="site_id", how="left")
        n_added = len(watershed_attrs.columns) - n_before
        logger.info(f"SGMC lithology: merged {n_added} features for {sgmc['site_id'].nunique()} sites")
        log_file(sgmc_path, role="input")

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

        # --- Site exclusion: auto-detect split file + optional CSV ---
        _excluded_site_ids = set()

        # Auto-exclude holdout/vault from split file (unless --include-all-sites)
        _split_path = DATA_DIR / "train_holdout_vault_split.parquet"
        if _split_path.exists() and not args.include_all_sites:
            _split = pd.read_parquet(_split_path)
            _non_train = _split[_split["role"] != "training"]["site_id"]
            _excluded_site_ids.update(_non_train)
            logger.info(f"Split file: auto-excluding {len(_non_train)} holdout/vault sites")
        elif _split_path.exists() and args.include_all_sites:
            logger.warning("--include-all-sites: SKIPPING automatic holdout/vault exclusion")

        # Additional CSV exclusion (on top of split-based exclusion)
        if args.exclude_sites:
            exclude_df = pd.read_csv(args.exclude_sites)
            _excluded_site_ids.update(exclude_df["site_id"])
            logger.info(f"CSV exclude: {len(exclude_df)} additional sites")

        if _excluded_site_ids:
            n_before = len(assembled)
            assembled = assembled[~assembled["site_id"].isin(_excluded_site_ids)]
            logger.info(f"Excluded {n_before - len(assembled)} samples from {len(_excluded_site_ids)} sites "
                        f"({assembled['site_id'].nunique()} sites remain, {len(assembled)} samples)")

        # HARD GUARD: verify no holdout/vault sites leaked through
        if _split_path.exists() and not args.include_all_sites:
            _split = pd.read_parquet(_split_path)
            _vault = set(_split[_split["role"] == "vault"]["site_id"])
            _holdout = set(_split[_split["role"] == "holdout"]["site_id"])
            _leaked = (_vault | _holdout) & set(assembled["site_id"].unique())
            if _leaked:
                raise RuntimeError(
                    f"CONTAMINATION: {len(_leaked)} holdout/vault sites in training data: "
                    f"{sorted(list(_leaked))[:5]}... "
                    f"This would produce invalid evaluation metrics. "
                    f"Pass --include-all-sites to override (not recommended)."
                )

        target_col = cfg["target_col"]

        # Apply chosen transform to target (overwrite the log1p column)
        global_lmbda = None
        if transform_type == "log1p":
            global_lmbda = None
            # ssc_log1p already exists from assembly — no change needed
        elif transform_type == "boxcox":
            from scipy.stats import boxcox_normmax
            from scipy.special import boxcox1p
            raw_y = assembled["lab_value"].values
            if args.boxcox_lambda is not None:
                global_lmbda = args.boxcox_lambda
                logger.info(f"Box-Cox lambda (manual): {global_lmbda:.4f}")
            else:
                global_lmbda = float(boxcox_normmax(raw_y + 1, method="mle"))
                logger.info(f"Box-Cox lambda (MLE): {global_lmbda:.4f}")
            assembled[target_col] = boxcox1p(raw_y, global_lmbda)
        elif transform_type == "sqrt":
            assembled[target_col] = np.sqrt(assembled["lab_value"])
            global_lmbda = 0.5
        elif transform_type == "none":
            assembled[target_col] = assembled["lab_value"].values
            global_lmbda = None
            logger.info("Transform: NONE (raw SSC values)")

        # Log sample weight scheme if requested
        if args.weight_scheme is not None:
            lv = assembled["lab_value"].values
            if args.weight_scheme == "sqrt":
                _w = np.sqrt(lv)
            elif args.weight_scheme == "log":
                _w = np.log1p(lv)
            else:
                _w = lv.copy()
            _w = _w / _w.mean()
            logger.info(f"  Sample weights ({args.weight_scheme}): min={_w.min():.3f}, max={_w.max():.3f}, mean={_w.mean():.3f}")
            del _w

        # Build tiers
        tiers = build_feature_tiers(assembled, basic_attrs, watershed_attrs)

        for tier_name, tier_info in tiers.items():
            if args.tier and not tier_name.startswith(args.tier):
                continue

            result = run_tier(
                param_name, tier_name,
                tier_info["data"], tier_info["feature_cols"], target_col,
                transform_type=transform_type, transform_lmbda=global_lmbda,
                fixed_lambda=(args.boxcox_lambda is not None),
                n_jobs=n_jobs, thread_count=thread_count,
                weight_scheme=args.weight_scheme,
                slope_correction=args.slope_correction,
                quantile_mode=args.quantile,
                no_monotone=args.no_monotone,
                feature_set=args.feature_set,
                cb_overrides=cb_overrides,
                drop_features=drop_features,
                label=args.label,
                skip_ridge=args.skip_ridge,
                cv_mode=args.cv_mode,
                kge_eval=args.kge_eval,
            )
            all_results.append(result)
            logger.info(
                f"    R²(log)={result['r2_log']:.3f}  KGE(log)={result['kge_log']:.3f}  "
                f"alpha={result.get('kge_alpha', float('nan')):.3f}  |  "
                f"R²(mg/L)={result.get('r2_native', float('nan')):.3f}  "
                f"MedSiteR²={result.get('median_per_site_r2', float('nan')):.4f}  "
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
    if args.skip_save_model:
        logger.info(f"\n{'='*60}")
        logger.info("SKIPPING final model save + SHAP (--skip-save-model)")
        logger.info(f"{'='*60}")
        end_run()
        return

    logger.info(f"\n{'='*60}")
    logger.info("SAVING FINAL MODELS")
    logger.info(f"{'='*60}")

    from catboost import CatBoostRegressor, Pool
    import json

    results_dir = DATA_DIR / "results"
    model_dir = results_dir / "models"
    model_dir.mkdir(parents=True, exist_ok=True)

    for param_name, cfg in params.items():
        dataset_path = DATA_DIR / "processed" / cfg["dataset"]
        if not dataset_path.exists():
            continue

        assembled = pd.read_parquet(dataset_path)
        target_col = cfg["target_col"]

        # --- Apply same site exclusion as CV section ---
        _split_path = DATA_DIR / "train_holdout_vault_split.parquet"
        if _split_path.exists() and not args.include_all_sites:
            _split = pd.read_parquet(_split_path)
            _non_train = set(_split[_split["role"] != "training"]["site_id"])
            n_before = len(assembled)
            assembled = assembled[~assembled["site_id"].isin(_non_train)]
            logger.info(f"Final model: excluded {n_before - len(assembled)} samples from "
                        f"{len(_non_train)} holdout/vault sites "
                        f"({assembled['site_id'].nunique()} sites remain)")
        if args.exclude_sites:
            exclude_df = pd.read_csv(args.exclude_sites)
            assembled = assembled[~assembled["site_id"].isin(set(exclude_df["site_id"]))]

        # HARD GUARD: verify no holdout/vault sites in final model training data
        if _split_path.exists() and not args.include_all_sites:
            _split = pd.read_parquet(_split_path)
            _vault = set(_split[_split["role"] == "vault"]["site_id"])
            _holdout = set(_split[_split["role"] == "holdout"]["site_id"])
            _leaked = (_vault | _holdout) & set(assembled["site_id"].unique())
            if _leaked:
                raise RuntimeError(
                    f"CONTAMINATION in final model: {len(_leaked)} holdout/vault sites. "
                    f"Refusing to train. Pass --include-all-sites to override."
                )

        # Apply chosen transform to target for final model training
        final_lmbda = None
        if transform_type == "boxcox":
            from scipy.stats import boxcox_normmax
            from scipy.special import boxcox1p
            raw_y = assembled["lab_value"].values
            if args.boxcox_lambda is not None:
                final_lmbda = args.boxcox_lambda
                logger.info(f"Final model Box-Cox lambda (manual): {final_lmbda:.4f}")
            else:
                final_lmbda = float(boxcox_normmax(raw_y + 1, method="mle"))
                logger.info(f"Final model Box-Cox lambda (MLE): {final_lmbda:.4f}")
            assembled[target_col] = boxcox1p(raw_y, final_lmbda)
        elif transform_type == "sqrt":
            assembled[target_col] = np.sqrt(assembled["lab_value"])
            final_lmbda = 0.5

        tiers = build_feature_tiers(assembled, basic_attrs, watershed_attrs)

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
            # Apply feature set pruning (same as run_tier)
            if args.feature_set != "full":
                available = _filter_feature_set(available, args.feature_set)
            # Apply drop features (same as run_tier)
            if drop_features:
                available = [c for c in available if c not in drop_features]
            numeric_cols = [c for c in available if tier_data[c].dtype in [np.float64, np.float32, np.int64, np.int32, float, int]]
            cat_cols = [c for c in available if tier_data[c].dtype == object]
            all_cols = numeric_cols + cat_cols
            cat_indices = [i for i, c in enumerate(all_cols) if c in cat_cols]

            logger.info(f"  Final model: {len(numeric_cols)} numeric + {len(cat_cols)} cat features")

            if len(numeric_cols) == 0:
                continue

            clean = tier_data.dropna(subset=[tc]).copy()
            y = clean[tc].values
            lab_values = clean["lab_value"].values if "lab_value" in clean.columns else None
            X_df = clean[all_cols].copy()

            # Compute sample weights for final model from clean tier data
            if args.weight_scheme is not None and "lab_value" in clean.columns:
                lv = clean["lab_value"].values
                if args.weight_scheme == "sqrt":
                    final_clean_weights = np.sqrt(lv)
                elif args.weight_scheme == "log":
                    final_clean_weights = np.log1p(lv)
                elif args.weight_scheme == "linear":
                    final_clean_weights = lv.copy()
                else:
                    final_clean_weights = None
                if final_clean_weights is not None:
                    final_clean_weights = final_clean_weights / final_clean_weights.mean()
            else:
                final_clean_weights = None

            for c in cat_cols:
                X_df[c] = X_df[c].fillna("missing").astype(str)
            train_median = X_df[numeric_cols].median()
            X_df[numeric_cols] = X_df[numeric_cols].fillna(train_median)

            # Early stopping split
            sites = clean["site_id"].values
            gss = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=42)
            train_idx, val_idx = next(gss.split(X_df, y, groups=sites))

            final_train_w = final_clean_weights[train_idx] if final_clean_weights is not None else None
            final_val_w = final_clean_weights[val_idx] if final_clean_weights is not None else None
            train_pool = Pool(X_df.iloc[train_idx], y[train_idx], cat_features=cat_indices, weight=final_train_w)
            val_pool = Pool(X_df.iloc[val_idx], y[val_idx], cat_features=cat_indices, weight=final_val_w)

            # Build CatBoost params for final model
            final_cb_params = dict(
                iterations=500, learning_rate=0.05, depth=6,
                l2_leaf_reg=3, random_seed=42, verbose=0,
                early_stopping_rounds=50,
                thread_count=thread_count,
                boosting_type="Ordered",
            )
            if not args.no_monotone:
                final_monotone = _build_monotone_constraints(all_cols)
                if final_monotone:
                    final_cb_params["monotone_constraints"] = final_monotone
            else:
                final_monotone = {}
            if args.quantile:
                final_cb_params["loss_function"] = "MultiQuantile:alpha=0.05,0.1,0.25,0.5,0.75,0.9,0.95"
            if cb_overrides:
                final_cb_params.update(cb_overrides)

            model = CatBoostRegressor(**final_cb_params)
            model.fit(train_pool, eval_set=val_pool)

            # Compute BCF for the final model
            raw_train_pred = model.predict(train_pool)
            if args.quantile and np.ndim(raw_train_pred) == 2:
                y_train_pred_final = np.sort(np.array(raw_train_pred), axis=1)[:, 3]  # median
            else:
                y_train_pred_final = raw_train_pred
            if transform_type == "log1p":
                final_bcf = duan_smearing_factor(y[train_idx], y_train_pred_final)
            else:
                if transform_type == "boxcox":
                    train_native_true = lab_values[train_idx] if lab_values is not None else np.expm1(y[train_idx])
                    train_native_pred = safe_inv_boxcox1p(y_train_pred_final, final_lmbda)
                else:  # sqrt
                    train_native_true = np.square(y[train_idx])
                    train_native_pred = np.square(y_train_pred_final)
                final_bcf = snowdon_bcf(train_native_true, train_native_pred)

            # Save model — include label if provided for versioned filenames
            safe_tier = tier_name.replace("/", "_")
            if args.label:
                model_path = model_dir / f"{param_name}_{safe_tier}_{args.label}.cbm"
            else:
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

            # Compute native target range based on transform
            if transform_type == "log1p":
                target_range_native = {
                    "min": float(np.expm1(y.min())),
                    "max": float(np.expm1(y.max())),
                }
            elif transform_type == "boxcox":
                target_range_native = {
                    "min": float(safe_inv_boxcox1p(np.array([y.min()]), final_lmbda)[0]),
                    "max": float(safe_inv_boxcox1p(np.array([y.max()]), final_lmbda)[0]),
                }
            else:  # sqrt
                target_range_native = {
                    "min": float(np.square(y.min())),
                    "max": float(np.square(y.max())),
                }

            meta = {
                "schema_version": 3,
                "param": param_name,
                "tier": tier_name,
                "transform_type": transform_type,
                "transform_lmbda": final_lmbda,
                "feature_cols": all_cols,
                "cat_cols": cat_cols,
                "cat_indices": cat_indices,
                "train_median": train_median.to_dict(),
                "feature_ranges": feature_ranges,
                "categorical_values_seen": cat_values_seen,
                "target_range": {"min": float(y.min()), "max": float(y.max())},
                "target_range_native": target_range_native,
                "sites_per_ecoregion": sites_per_ecoregion,
                "sites_per_geology": sites_per_geology,
                "n_sites": int(clean["site_id"].nunique()),
                "n_samples": len(clean),
                "n_trees": model.tree_count_,
                "bcf": final_bcf,
                "bcf_method": "duan" if transform_type == "log1p" else "snowdon",
                "weight_scheme": args.weight_scheme,
                "slope_correction": args.slope_correction,
                "quantile_mode": args.quantile,
                "monotone_constraints": bool(final_monotone),
                "holdout_vault_excluded": not args.include_all_sites and _split_path.exists(),
            }

            # If slope correction was used, look up the fitted params from CV results
            if args.slope_correction and all_results:
                for cv_res in all_results:
                    if cv_res.get("param") == param_name and cv_res.get("tier") == tier_name:
                        if "slope_correction_a" in cv_res:
                            meta["slope_correction_a"] = cv_res["slope_correction_a"]
                            meta["slope_correction_b"] = cv_res["slope_correction_b"]
                        break
            # Post-training integrity checks (added 2026-03-24)
            nan_ranges = [c for c, r in feature_ranges.items()
                          if np.isnan(r["min"]) or np.isnan(r["max"])]
            if nan_ranges:
                logger.warning(
                    f"  INTEGRITY: {len(nan_ranges)} feature(s) have NaN min/max in ranges: "
                    f"{nan_ranges[:5]}... Features may have been destroyed."
                )
            if "watershed" in tier_name.lower() and not cat_values_seen:
                logger.warning(
                    f"  INTEGRITY: Tier {tier_name} has no categorical values seen. "
                    f"Check that watershed attributes were loaded correctly."
                )
            if "watershed" in tier_name.lower() and not sites_per_ecoregion:
                logger.warning(
                    f"  INTEGRITY: Tier {tier_name} has empty sites_per_ecoregion. "
                    f"Ecoregion data may not have been loaded."
                )

            if args.label:
                meta_path = model_dir / f"{param_name}_{safe_tier}_{args.label}_meta.json"
            else:
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

            # SHAP analysis for Tier C models (where watershed features are)
            if ("C_" in tier_name or "watershed" in tier_name.lower()) and not args.skip_shap:
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
