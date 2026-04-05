"""Unified data loader for murkml training and evaluation.

ONE code path for: load → merge → split → transform → select features.
Eliminates the duplicated feature selection that caused the v11b bug.

All functions are pure: DataFrame in, DataFrame out, no mutation.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.special import boxcox1p

from murkml.config import ModelConfig
from murkml.data.attributes import build_feature_tiers, load_streamcat_attrs

logger = logging.getLogger(__name__)


def load_paired_data(data_dir: Path) -> pd.DataFrame:
    """Load the assembled paired dataset."""
    path = data_dir / "processed" / "turbidity_ssc_paired.parquet"
    df = pd.read_parquet(path)
    logger.info(f"Loaded paired data: {len(df)} samples, {df['site_id'].nunique()} sites")
    return df


def load_attributes(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Load basic + StreamCat + SGMC attributes. Returns (basic_attrs, watershed_attrs)."""
    basic = pd.read_parquet(data_dir / "site_attributes.parquet")

    streamcat_path = data_dir / "site_attributes_streamcat.parquet"
    watershed = None
    if streamcat_path.exists():
        watershed = load_streamcat_attrs(data_dir)
        logger.info(f"StreamCat: {len(watershed)} sites, {len(watershed.columns)-1} features")

        sgmc_path = data_dir / "sgmc" / "sgmc_features_for_model.parquet"
        if sgmc_path.exists():
            sgmc = pd.read_parquet(sgmc_path)
            n_before = len(watershed.columns)
            watershed = watershed.merge(sgmc, on="site_id", how="left")
            logger.info(f"SGMC: merged {len(watershed.columns) - n_before} features")

    return basic, watershed


def apply_split(
    df: pd.DataFrame,
    split_path: Path,
    partition: str = "training",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split data by role. Returns (selected_partition, excluded).

    partition="training" → exclude holdout+vault (for training)
    partition="holdout" → select holdout only (for evaluation)
    partition="vault" → select vault only (for final exam)
    """
    if not split_path.exists():
        logger.warning(f"Split file not found: {split_path}")
        return df.copy(), pd.DataFrame()

    split = pd.read_parquet(split_path)

    if partition == "training":
        exclude_ids = set(split[split["role"] != "training"]["site_id"])
        selected = df[~df["site_id"].isin(exclude_ids)].copy()
        excluded = df[df["site_id"].isin(exclude_ids)].copy()
    else:
        include_ids = set(split[split["role"] == partition]["site_id"])
        selected = df[df["site_id"].isin(include_ids)].copy()
        excluded = df[~df["site_id"].isin(include_ids)].copy()

    logger.info(
        f"Split ({partition}): {len(df)} → {len(selected)} selected, "
        f"{len(excluded)} excluded ({selected['site_id'].nunique()} sites)"
    )
    return selected, excluded


def apply_transform(
    df: pd.DataFrame,
    config: ModelConfig,
    target_col: str = "ssc_log1p",
) -> pd.DataFrame:
    """Apply Box-Cox transform to target. Returns copy, no mutation."""
    result = df.copy()
    if config.transform.type == "boxcox":
        result[target_col] = boxcox1p(result["lab_value"].values, config.transform.lmbda)
    return result


def build_tier_c(
    assembled: pd.DataFrame,
    basic_attrs: pd.DataFrame,
    watershed_attrs: pd.DataFrame | None,
) -> tuple[pd.DataFrame, list[str]]:
    """Build Tier C feature matrix. Returns (tier_data, feature_cols)."""
    tiers = build_feature_tiers(assembled, basic_attrs, watershed_attrs)
    tier_c = tiers.get("C_sensor_basic_watershed")
    if tier_c is None:
        raise RuntimeError("Tier C not found — check that StreamCat attributes were loaded")
    return tier_c["data"], tier_c["feature_cols"]


def select_features(
    df: pd.DataFrame,
    config: ModelConfig,
) -> tuple[pd.DataFrame, list[str], list[int]]:
    """Select features from config. ONE code path — used by both CV and final model.

    Returns (X, feature_names, cat_indices).
    Raises ValueError if any configured feature is missing from data.
    """
    all_features = config.features.all_features
    exclude = set(config.exclude_cols)

    # Filter to features that should be in the data
    expected = [f for f in all_features if f not in exclude]
    missing = [f for f in expected if f not in df.columns]
    if missing:
        raise ValueError(
            f"{len(missing)} configured features missing from data: {missing[:10]}..."
        )

    # Select in configured order
    X = df[expected].copy()

    # Fill categorical NaN with "missing" — matches legacy behavior
    cat_set = set(config.features.categoricals)
    for c in expected:
        if c in cat_set and c in X.columns:
            X[c] = X[c].fillna("missing").astype(str)

    cat_indices = [i for i, f in enumerate(expected) if f in cat_set]

    # Post-merge all-NaN check (global, not per-fold)
    for col in expected:
        if X[col].isna().all():
            raise ValueError(f"Feature '{col}' is all-NaN — likely a broken join")

    return X, expected, cat_indices


def prepare_training_data(
    data_dir: Path,
    config: ModelConfig,
    target_col: str = "ssc_log1p",
) -> dict[str, Any]:
    """Full data loading pipeline for training. Single entry point.

    Returns dict with X, y, sites, feature_names, cat_indices, holdout data, lineage.
    """
    lineage = {}

    # Load
    assembled = load_paired_data(data_dir)
    lineage["post_load"] = {"rows": len(assembled), "cols": len(assembled.columns)}

    basic, watershed = load_attributes(data_dir)

    # Split
    split_path = data_dir / "train_holdout_vault_split.parquet"
    train_assembled, excluded = apply_split(assembled, split_path, "training")
    lineage["post_split"] = {
        "rows": len(train_assembled),
        "dropped_count": len(excluded),
    }

    # Transform
    train_assembled = apply_transform(train_assembled, config, target_col)

    # Build tier
    tier_data, tier_feature_cols = build_tier_c(train_assembled, basic, watershed)
    lineage["post_merge"] = {"rows": len(tier_data), "cols": len(tier_data.columns)}

    # Clean (drop rows with missing target)
    clean = tier_data.dropna(subset=[target_col]).copy()

    # Handle duplicates (keep first, matching legacy)
    dupes = clean.duplicated(subset=["site_id", "sample_time"]).sum()
    if dupes > 0:
        logger.warning(f"Dropping {dupes} duplicate (site_id, sample_time) rows (keep first)")
        clean = clean.drop_duplicates(subset=["site_id", "sample_time"], keep="first")

    # Deterministic sort
    clean = clean.sort_values(["site_id", "sample_time"]).reset_index(drop=True)

    # Select features
    X, feature_names, cat_indices = select_features(clean, config)
    y = clean[target_col].values
    sites = clean["site_id"].values
    lab_values = clean["lab_value"].values

    lineage["post_select"] = {"rows": len(X), "features_selected": len(feature_names)}

    # Also prepare holdout
    holdout_data = None
    holdout_assembled, _ = apply_split(assembled, split_path, "holdout")
    if len(holdout_assembled) > 0:
        holdout_assembled = apply_transform(holdout_assembled, config, target_col)
        holdout_tier_data, _ = build_tier_c(holdout_assembled, basic, watershed)
        holdout_clean = holdout_tier_data.dropna(subset=[target_col]).copy()
        holdout_clean = holdout_clean.sort_values(["site_id", "sample_time"]).reset_index(drop=True)
        X_holdout, _, _ = select_features(holdout_clean, config)
        holdout_data = {
            "X": X_holdout,
            "y": holdout_clean[target_col].values,
            "site_id": holdout_clean["site_id"].values,
            "sample_time": holdout_clean["sample_time"].values,
            "lab_value": holdout_clean["lab_value"].values,
        }

    return {
        "X": X,
        "y": y,
        "sites": sites,
        "lab_values": lab_values,
        "feature_names": feature_names,
        "cat_indices": cat_indices,
        "holdout": holdout_data,
        "lineage": lineage,
        "global_lmbda": config.transform.lmbda,
    }
