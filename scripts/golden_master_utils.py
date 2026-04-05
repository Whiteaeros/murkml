"""Shared utilities for golden master generation and validation.

Contains: hash_dataframe(), _build_surrogate(), stratified site sampler.
Used by generate_golden_master.py, validate_golden_master.py, and measure_reproducibility.py.
"""
from __future__ import annotations

import gc
import hashlib
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
GOLDEN_MASTER_DIR = DATA_DIR / "golden_master"

# Surrogate config — single source of truth, never duplicated
SURROGATE_HOLDOUT = {"iterations": 50, "depth": 4, "thread_count": 1, "random_seed": 42}
SURROGATE_CV = {"iterations": 10, "depth": 6, "thread_count": 1, "random_seed": 42}
SURROGATE_MEDIUM = {"iterations": 30, "depth": 6, "thread_count": 1, "random_seed": 42}


def assert_pinned_environment(manifest_path: Path | None = None) -> dict:
    """Assert CatBoost/pandas/numpy versions match pinned requirements. Returns version dict."""
    import catboost
    versions = {
        "catboost": catboost.__version__,
        "pandas": pd.__version__,
        "numpy": np.__version__,
    }
    if manifest_path and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        pinned = manifest.get("pinned_versions", {})
        for lib, ver in pinned.items():
            if lib in versions and versions[lib] != ver:
                raise RuntimeError(
                    f"Version mismatch for {lib}: installed={versions[lib]}, pinned={ver}"
                )
    return versions


def hash_dataframe(df: pd.DataFrame) -> str:
    """Hash LOGICAL values, not memory layout.

    Normalizes categoricals to strings, numeric NaN to masked 0.0 + boolean mask,
    rounds floats to 8 decimals, sorts deterministically.
    """
    # Guard against mask column collision
    mask_collisions = [c for c in df.columns if c.startswith("_mask_")]
    assert not mask_collisions, (
        f"Original columns starting with _mask_ would collide with null masks: {mask_collisions}"
    )

    df_norm = df.copy()

    # 1. Coerce categoricals to strings
    for col in df_norm.select_dtypes(include=["category"]).columns:
        df_norm[col] = df_norm[col].astype(str)

    # 2. Coerce object columns with strict null token
    for col in df_norm.select_dtypes(include=["object"]).columns:
        df_norm[col] = df_norm[col].fillna("__MURKML_NULL__").astype(str)

    # 3. Numeric: mask NaN separately, fill with 0.0, round to 8 decimals
    num_cols = df_norm.select_dtypes(include=["number"]).columns.tolist()
    mask_frames = []
    for col in num_cols:
        mask_frames.append(df_norm[col].isna().astype("float64").rename(f"_mask_{col}"))
        df_norm[col] = df_norm[col].fillna(0.0).astype("float64").round(8)
    if mask_frames:
        df_norm = pd.concat([df_norm] + mask_frames, axis=1)

    # 4. Sort columns alphabetically
    df_norm = df_norm.reindex(sorted(df_norm.columns), axis=1)

    # 5. Sort rows by deterministic keys
    if "site_id" in df_norm.columns and "sample_time" in df_norm.columns:
        df_norm = df_norm.sort_values(["site_id", "sample_time"]).reset_index(drop=True)
    elif "site_id" in df_norm.columns:
        df_norm = df_norm.sort_values(["site_id"]).reset_index(drop=True)
    else:
        df_norm = df_norm.sort_values(list(df_norm.columns)).reset_index(drop=True)

    # 6. Hash
    result = hashlib.sha256(
        pd.util.hash_pandas_object(df_norm, index=False).values
    ).hexdigest()

    del df_norm
    gc.collect()
    return result


def get_dtypes_dict(df: pd.DataFrame) -> dict[str, str]:
    """Return {column: dtype_string} for manifest storage."""
    return {col: str(df[col].dtype) for col in df.columns}


def select_stratified_sites(
    df: pd.DataFrame,
    cat_cols: list[str],
    n_target: int = 12,
) -> list[str]:
    """Greedy stratified sampler: cover all categorical values, then pad.

    Sorts site_id as STRING (lexicographic) for determinism.
    Returns list of site_id strings.
    """
    selected = set()
    sites_sorted = sorted(df["site_id"].unique())  # lexicographic

    # Phase 1: Cover all categorical values
    for col in cat_cols:
        if col not in df.columns:
            continue
        for val in sorted(df[col].dropna().unique()):
            # Find first site (lexicographic) with this value
            candidates = df[df[col] == val]["site_id"].unique()
            for site in sites_sorted:
                if site in candidates and site not in selected:
                    selected.add(site)
                    break

    # Phase 2: Add site with most NaN features (if any)
    nan_counts = df.groupby("site_id").apply(
        lambda g: g.select_dtypes(include=["number"]).isna().any().sum()
    )
    if len(nan_counts) > 0:
        most_nan_site = nan_counts.sort_values(ascending=False).index[0]
        selected.add(most_nan_site)

    # Phase 3: Pad to target count
    for site in sites_sorted:
        if len(selected) >= n_target:
            break
        selected.add(site)

    return sorted(selected)


def build_surrogate(
    X: pd.DataFrame,
    y: np.ndarray,
    cat_indices: list[int],
    config: dict,
    X_val: pd.DataFrame | None = None,
    y_val: np.ndarray | None = None,
) -> CatBoostRegressor:
    """Train a surrogate model with given config. Single source of truth."""
    params = {
        "iterations": config["iterations"],
        "depth": config["depth"],
        "learning_rate": 0.05,
        "l2_leaf_reg": 3,
        "random_seed": config["random_seed"],
        "thread_count": config["thread_count"],
        "verbose": 0,
        "boosting_type": "Plain",
        "allow_writing_files": False,
    }
    model = CatBoostRegressor(**params)
    train_pool = Pool(X, y, cat_features=cat_indices)

    if X_val is not None and y_val is not None:
        val_pool = Pool(X_val, y_val, cat_features=cat_indices)
        model.fit(train_pool, eval_set=val_pool)
    else:
        model.fit(train_pool)

    return model


def load_legacy_data() -> dict:
    """Reproduce the EXACT data loading path from train_tiered.py.

    Returns dict with intermediate DataFrames at each stage for lineage capture.
    Verified correct by matching output feature list against v11 model metadata.
    """
    import sys
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from murkml.data.attributes import load_streamcat_attrs, build_feature_tiers
    from scipy.special import boxcox1p

    stages = {}

    # Step 1: Load paired dataset
    assembled = pd.read_parquet(DATA_DIR / "processed" / "turbidity_ssc_paired.parquet")
    stages["post_load"] = {
        "rows": len(assembled),
        "cols": len(assembled.columns),
        "columns": sorted(assembled.columns.tolist()),
        "hash": hash_dataframe(assembled),
        "dtypes": get_dtypes_dict(assembled),
    }

    # Step 2: Load attributes
    basic_attrs = pd.read_parquet(DATA_DIR / "site_attributes.parquet")
    watershed_attrs = load_streamcat_attrs(DATA_DIR)

    # Step 3: Merge SGMC
    sgmc_path = DATA_DIR / "sgmc" / "sgmc_features_for_model.parquet"
    if sgmc_path.exists() and watershed_attrs is not None:
        sgmc = pd.read_parquet(sgmc_path)
        watershed_attrs = watershed_attrs.merge(sgmc, on="site_id", how="left")

    # Step 4: Exclude holdout/vault sites
    split_path = DATA_DIR / "train_holdout_vault_split.parquet"
    dropped_sites = set()
    if split_path.exists():
        split_df = pd.read_parquet(split_path)
        non_train = set(split_df[split_df["role"] != "training"]["site_id"])
        dropped_sites = non_train
        n_before = len(assembled)
        assembled_train = assembled[~assembled["site_id"].isin(non_train)].copy()
        dropped_df = assembled[assembled["site_id"].isin(non_train)]
        stages["post_split"] = {
            "rows": len(assembled_train),
            "cols": len(assembled_train.columns),
            "dropped_count": n_before - len(assembled_train),
            "dropped_keys_hash": hash_dataframe(
                dropped_df[["site_id", "sample_time"]]
            ) if len(dropped_df) > 0 else None,
            "reason": "holdout_vault_exclusion",
        }
    else:
        assembled_train = assembled.copy()
        stages["post_split"] = {
            "rows": len(assembled_train),
            "cols": len(assembled_train.columns),
            "dropped_count": 0,
            "dropped_keys_hash": None,
        }

    # Step 5: Apply Box-Cox transform (lambda=0.2, matching v11)
    raw_y = assembled_train["lab_value"].values
    global_lmbda = 0.2
    assembled_train["ssc_log1p"] = boxcox1p(raw_y, global_lmbda)

    # Step 6: Build feature tiers
    tiers = build_feature_tiers(assembled_train, basic_attrs, watershed_attrs)

    # Extract Tier C data
    tier_c = tiers.get("C_sensor_basic_watershed")
    if tier_c is None:
        raise RuntimeError("Tier C not found in build_feature_tiers output")

    tier_data = tier_c["data"]
    feature_cols = tier_c["feature_cols"]

    stages["post_merge"] = {
        "rows": len(tier_data),
        "cols": len(tier_data.columns),
        "dropped_count": 0,
        "dropped_keys_hash": None,
        "per_feature_nonnull": {
            col: int(tier_data[col].notna().sum())
            for col in feature_cols if col in tier_data.columns
        },
    }

    # Step 7: Feature selection (reproducing run_tier logic from train_tiered.py)
    EXCLUDE_COLS = {
        "site_id", "sample_time", "lab_value", "match_gap_seconds", "window_count",
        "is_nondetect", "hydro_event",
        "ssc_log1p", "ssc_value", "total_phosphorus_log1p",
        "nitrate_nitrite_log1p", "orthophosphate_log1p", "tds_evaporative_log1p",
    }
    available = [c for c in feature_cols if c in tier_data.columns and c not in EXCLUDE_COLS]
    numeric_available = [
        c for c in available
        if tier_data[c].dtype in [np.float64, np.float32, np.int64, np.int32, float, int]
    ]
    cat_available = [c for c in available if tier_data[c].dtype == object]
    all_features = numeric_available + cat_available
    cat_indices = [i for i, c in enumerate(all_features) if c in cat_available]

    stages["post_select"] = {
        "rows": len(tier_data),
        "cols": len(all_features),
        "dropped_count": 0,
        "dropped_keys_hash": None,
        "features_selected": len(all_features),
    }

    # Prepare training data
    target_col = "ssc_log1p"
    clean = tier_data.dropna(subset=[target_col]).copy()

    # Check for duplicate keys — legacy data has some (paired samples)
    dupes = clean.duplicated(subset=["site_id", "sample_time"]).sum()
    if dupes > 0:
        logger.warning(
            f"Found {dupes} duplicate (site_id, sample_time) rows. "
            f"Keeping first occurrence to match legacy behavior. "
            f"These should be investigated in the data assembly pipeline."
        )
        # Keep first to match pd.drop_duplicates default (legacy behavior)
        clean = clean.drop_duplicates(subset=["site_id", "sample_time"], keep="first")

    # Sort deterministically
    clean = clean.sort_values(["site_id", "sample_time"]).reset_index(drop=True)

    X = clean[all_features].copy()
    # Fill categorical NaN with "missing" — matches legacy train_tiered.py behavior (lines 573, 1315)
    for c in cat_available:
        if c in X.columns:
            X[c] = X[c].fillna("missing").astype(str)
    y = clean[target_col].values
    sites = clean["site_id"].values
    lab_values = clean["lab_value"].values

    # Also get holdout data for surrogate predictions
    holdout_data = None
    if split_path.exists():
        holdout_ids = set(split_df[split_df["role"] == "holdout"]["site_id"])
        holdout_assembled = assembled[assembled["site_id"].isin(holdout_ids)].copy()
        holdout_assembled["ssc_log1p"] = boxcox1p(holdout_assembled["lab_value"].values, global_lmbda)
        holdout_tiers = build_feature_tiers(holdout_assembled, basic_attrs, watershed_attrs)
        holdout_tier_c = holdout_tiers.get("C_sensor_basic_watershed")
        if holdout_tier_c is not None:
            holdout_td = holdout_tier_c["data"]
            holdout_clean = holdout_td.dropna(subset=[target_col]).copy()
            holdout_clean = holdout_clean.sort_values(["site_id", "sample_time"]).reset_index(drop=True)
            X_holdout = holdout_clean[all_features].copy()
            # Fill categorical NaN with "missing" — matches legacy behavior
            for c in cat_available:
                if c in X_holdout.columns:
                    X_holdout[c] = X_holdout[c].fillna("missing").astype(str)
            y_holdout = holdout_clean[target_col].values
            holdout_data = {
                "X": X_holdout,
                "y": y_holdout,
                "site_id": holdout_clean["site_id"].values,
                "sample_time": holdout_clean["sample_time"].values,
                "lab_value": holdout_clean["lab_value"].values,
            }

    return {
        "X": X,
        "y": y,
        "sites": sites,
        "lab_values": lab_values,
        "all_features": all_features,
        "cat_indices": cat_indices,
        "cat_available": cat_available,
        "numeric_available": numeric_available,
        "stages": stages,
        "global_lmbda": global_lmbda,
        "holdout": holdout_data,
        "split_df": split_df if split_path.exists() else None,
    }
