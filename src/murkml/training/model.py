"""Train and save CatBoost model. Pure functions: data in, model out.

Matches legacy train_tiered.py final model section (lines 1262-1506):
- GroupShuffleSplit 85/15 validation split for early stopping
- Per-column median NaN imputation (saved in metadata for inference)
- BCF computation in native space (Snowdon for Box-Cox)
- Complete metadata matching legacy schema v3
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool
from sklearn.model_selection import GroupShuffleSplit

from murkml.config import ModelConfig
from murkml.evaluate.metrics import safe_inv_boxcox1p, snowdon_bcf

logger = logging.getLogger(__name__)


def build_catboost_params(
    config: ModelConfig,
    thread_count: int | None = None,
    monotone_dict: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Build CatBoost parameter dict from config."""
    params = {
        "iterations": config.catboost.iterations,
        "depth": config.catboost.depth,
        "learning_rate": config.catboost.learning_rate,
        "l2_leaf_reg": config.catboost.l2_leaf_reg,
        "random_seed": config.catboost.random_seed,
        "thread_count": thread_count or config.catboost.thread_count,
        "verbose": 0,
        "boosting_type": config.catboost.boosting_type,
        "early_stopping_rounds": config.catboost.early_stopping_rounds,
        "allow_writing_files": False,
    }
    if monotone_dict:
        params["monotone_constraints"] = monotone_dict
    return params


def compute_monotone_constraints(
    feature_names: list[str],
    config: ModelConfig,
) -> dict[str, int]:
    """Build monotone constraint dict: feature_name → +1 for configured features."""
    return {f: 1 for f in config.monotone_constraints if f in feature_names}


def train_final_model(
    X: pd.DataFrame,
    y: np.ndarray,
    site_ids: np.ndarray,
    cat_indices: list[int],
    config: ModelConfig,
    feature_names: list[str],
    lab_values: np.ndarray | None = None,
    thread_count: int | None = None,
    val_fraction: float = 0.15,
) -> tuple[CatBoostRegressor, dict[str, Any]]:
    """Train a single CatBoost model on all training data with early stopping.

    Matches legacy train_tiered.py lines 1314-1378:
    - Median NaN imputation for numeric columns
    - GroupShuffleSplit site-level 85/15 validation split
    - BCF in native space (Snowdon for Box-Cox)

    Returns (model, metadata_dict).
    """
    monotone = compute_monotone_constraints(feature_names, config)
    params = build_catboost_params(config, thread_count, monotone)

    if len(monotone) > 0:
        logger.info(f"Monotone constraints on {len(monotone)} features: {list(monotone.keys())}")

    # Identify numeric columns for imputation
    cat_set = set(config.features.categoricals)
    numeric_cols = [f for f in feature_names if f not in cat_set and f in X.columns]

    # Median imputation (matching legacy lines 1316-1317)
    X = X.copy()
    train_median = X[numeric_cols].median()
    X[numeric_cols] = X[numeric_cols].fillna(train_median)

    # Early stopping validation split (matching legacy lines 1321-1327)
    gss = GroupShuffleSplit(n_splits=1, test_size=val_fraction, random_state=42)
    train_idx, val_idx = next(gss.split(X, y, groups=site_ids))

    train_pool = Pool(X.iloc[train_idx], y[train_idx], cat_features=cat_indices)
    val_pool = Pool(X.iloc[val_idx], y[val_idx], cat_features=cat_indices)

    model = CatBoostRegressor(**params)
    model.fit(train_pool, eval_set=val_pool)
    logger.info(f"Final model: {model.tree_count_} trees (early-stopped from {config.catboost.iterations})")

    # BCF computation in native space (matching legacy lines 1352-1377)
    y_train_pred = model.predict(train_pool)
    if lab_values is not None:
        train_native_true = lab_values[train_idx]
        train_native_pred = safe_inv_boxcox1p(y_train_pred, config.transform.lmbda)
        bcf_mean = float(snowdon_bcf(train_native_true, train_native_pred))

        # Dual BCF: median-optimal
        ratios = train_native_true / np.clip(train_native_pred, 1e-6, None)
        bcf_median = float(np.clip(np.median(ratios), 0.1, 10.0))
    else:
        bcf_mean = 1.0
        bcf_median = 1.0
    logger.info(f"BCF mean (Snowdon): {bcf_mean:.4f}, BCF median: {bcf_median:.4f}")

    # Feature ranges for applicability domain
    feature_ranges = {}
    for col in numeric_cols:
        feature_ranges[col] = {"min": float(X[col].min()), "max": float(X[col].max())}

    # Categorical values seen
    cat_values_seen = {}
    for col in config.features.categoricals:
        if col in X.columns:
            cat_values_seen[col] = sorted(X[col].unique().tolist())

    # Target range
    target_range_native = {
        "min": float(safe_inv_boxcox1p(np.array([y.min()]), config.transform.lmbda)[0]),
        "max": float(safe_inv_boxcox1p(np.array([y.max()]), config.transform.lmbda)[0]),
    }

    metadata = {
        "n_trees": model.tree_count_,
        "feature_cols": feature_names,
        "cat_cols": [feature_names[i] for i in cat_indices],
        "cat_indices": cat_indices,
        "train_median": {k: float(v) for k, v in train_median.to_dict().items()},
        "feature_ranges": feature_ranges,
        "categorical_values_seen": cat_values_seen,
        "target_range": {"min": float(y.min()), "max": float(y.max())},
        "target_range_native": target_range_native,
        "n_sites": int(len(np.unique(site_ids))),
        "n_samples": len(X),
        "bcf": bcf_mean,
        "bcf_mean": bcf_mean,
        "bcf_median": bcf_median,
        "bcf_method": "snowdon",
    }

    return model, metadata


def save_model(
    model: CatBoostRegressor,
    metadata: dict[str, Any],
    config: ModelConfig,
    output_dir: Path,
    label: str | None = None,
) -> tuple[Path, Path]:
    """Save model .cbm and _meta.json with complete legacy-compatible metadata."""
    version = label or config.version
    base = f"ssc_C_sensor_basic_watershed_{version}"
    model_path = output_dir / f"{base}.cbm"
    meta_path = output_dir / f"{base}_meta.json"

    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_model(str(model_path))

    full_meta = {
        "schema_version": 4,
        "param": "ssc",
        "tier": "C_sensor_basic_watershed",
        "transform_type": config.transform.type,
        "transform_lmbda": config.transform.lmbda,
        **metadata,
        "version": version,
        "monotone_constraints": len(config.monotone_constraints) > 0,
        "holdout_vault_excluded": True,
    }
    meta_path.write_text(json.dumps(full_meta, indent=2))

    logger.info(
        f"Saved model: {model_path.name} "
        f"({model_path.stat().st_size // 1024} KB, {metadata['n_trees']} trees)"
    )
    return model_path, meta_path
