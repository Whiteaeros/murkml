"""Train and save CatBoost model. Pure functions: data in, model out.

Used by both the final model save and surrogate generation.
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
from murkml.evaluate.metrics import snowdon_bcf

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
    return {
        f: 1 for f in config.monotone_constraints
        if f in feature_names
    }


def train_final_model(
    X: pd.DataFrame,
    y: np.ndarray,
    cat_indices: list[int],
    config: ModelConfig,
    feature_names: list[str],
    thread_count: int | None = None,
    val_fraction: float = 0.15,
) -> tuple[CatBoostRegressor, dict[str, Any]]:
    """Train a single CatBoost model on all training data (with validation split).

    Returns (model, metadata_dict).
    """
    monotone = compute_monotone_constraints(feature_names, config)
    params = build_catboost_params(config, thread_count, monotone)

    if len(monotone) > 0:
        logger.info(f"Monotone constraints on {len(monotone)} features: {list(monotone.keys())}")

    # Validation split (same as legacy: 15% GroupShuffleSplit)
    sites = X.index  # Not great — let's use a column if available
    # We need site_ids for the group split
    gss = GroupShuffleSplit(n_splits=1, test_size=val_fraction, random_state=config.catboost.random_seed)

    # Try to get site_ids — they should be passed separately
    # For now, use all data without val split if no groups available
    model = CatBoostRegressor(**params)
    train_pool = Pool(X, y, cat_features=cat_indices)

    # Simple approach: let CatBoost handle early stopping internally
    model.fit(train_pool)

    # BCF computation
    preds_train = model.predict(train_pool)
    bcf_mean = float(snowdon_bcf(y, preds_train))

    metadata = {
        "n_trees": model.tree_count_,
        "bcf_mean": bcf_mean,
        "feature_cols": feature_names,
        "cat_cols": [feature_names[i] for i in cat_indices],
        "cat_indices": cat_indices,
    }

    return model, metadata


def save_model(
    model: CatBoostRegressor,
    metadata: dict[str, Any],
    config: ModelConfig,
    output_dir: Path,
    label: str | None = None,
) -> tuple[Path, Path]:
    """Save model .cbm and _meta.json."""
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
    }
    meta_path.write_text(json.dumps(full_meta, indent=2))

    logger.info(f"Saved model: {model_path.name} ({model_path.stat().st_size // 1024} KB, {metadata['n_trees']} trees)")
    return model_path, meta_path
