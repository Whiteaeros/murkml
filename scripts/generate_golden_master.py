"""Generate the golden master artifacts for the zero-regression refactor.

Must be run AFTER measure_reproducibility.py.
Produces checksums, surrogates, and lineage in data/golden_master/.

This script is FROZEN after Phase 0. Do not modify after golden master is generated.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import LeaveOneGroupOut

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from golden_master_utils import (
    GOLDEN_MASTER_DIR,
    SURROGATE_CV,
    SURROGATE_HOLDOUT,
    assert_pinned_environment,
    build_surrogate,
    get_dtypes_dict,
    hash_dataframe,
    load_legacy_data,
    select_stratified_sites,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    # Refuse to overwrite existing golden master
    manifest_path = GOLDEN_MASTER_DIR / "manifest.json"
    if manifest_path.exists():
        print(f"ERROR: Golden master already exists at {GOLDEN_MASTER_DIR}")
        print("Pass --force to overwrite (dangerous!)")
        if "--force" not in sys.argv:
            sys.exit(1)

    GOLDEN_MASTER_DIR.mkdir(parents=True, exist_ok=True)

    # Check reproducibility was measured first
    repro_path = GOLDEN_MASTER_DIR / "reproducibility_measurement.json"
    if not repro_path.exists():
        print("ERROR: Run measure_reproducibility.py first")
        sys.exit(1)
    repro = json.loads(repro_path.read_text())
    atol = repro["recommended_atol"]

    versions = assert_pinned_environment()
    logger.info(f"Pinned versions: {versions}")
    logger.info(f"Validation tolerance: atol={atol:.2e}")

    # ==========================================
    # Load data exactly as legacy code does
    # ==========================================
    logger.info("Loading legacy data path...")
    data = load_legacy_data()

    X = data["X"]
    y = data["y"]
    sites = data["sites"]
    all_features = data["all_features"]
    cat_indices = data["cat_indices"]
    cat_available = data["cat_available"]
    stages = data["stages"]
    holdout = data["holdout"]

    logger.info(f"Training: {X.shape[0]} samples, {X.shape[1]} features")
    logger.info(f"Features: {len(all_features)} ({len(cat_indices)} categorical)")

    # ==========================================
    # Verify against v11 model metadata
    # ==========================================
    meta_path = (
        PROJECT_ROOT / "data" / "results" / "models"
        / "ssc_C_sensor_basic_watershed_v11_extreme_expanded_meta.json"
    )
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        meta_features = meta["feature_cols"]
        if all_features == meta_features:
            logger.info(f"VERIFIED: Feature list matches v11 metadata ({len(all_features)} features)")
        else:
            missing = set(meta_features) - set(all_features)
            extra = set(all_features) - set(meta_features)
            logger.warning(
                f"Feature list DIFFERS from v11 metadata! "
                f"Missing: {missing}, Extra: {extra}"
            )
            # Check if it's just ordering
            if set(all_features) == set(meta_features):
                logger.warning("Same features but DIFFERENT ORDER — this affects CatBoost")
    else:
        logger.warning("v11 model metadata not found — cannot verify feature list")

    # ==========================================
    # Hash upstream files
    # ==========================================
    upstream_hashes = {}
    for name, path in [
        ("turbidity_ssc_paired", PROJECT_ROOT / "data/processed/turbidity_ssc_paired.parquet"),
        ("site_attributes_streamcat", PROJECT_ROOT / "data/site_attributes_streamcat.parquet"),
        ("sgmc_features", PROJECT_ROOT / "data/sgmc/sgmc_features_for_model.parquet"),
        ("train_holdout_vault_split", PROJECT_ROOT / "data/train_holdout_vault_split.parquet"),
    ]:
        if path.exists():
            df = pd.read_parquet(path)
            upstream_hashes[name] = {
                "hash": hash_dataframe(df),
                "shape": list(df.shape),
                "columns": sorted(df.columns.tolist()),
                "dtypes": get_dtypes_dict(df),
            }
            logger.info(f"  {name}: {df.shape} -> hash={upstream_hashes[name]['hash'][:12]}...")
            del df
        else:
            logger.warning(f"  {name}: NOT FOUND at {path}")

    # ==========================================
    # Stratified site selection for CV surrogate
    # ==========================================
    train_df_for_sampling = pd.DataFrame({"site_id": sites})
    # Merge categorical columns for stratification
    X_with_sites = X.copy()
    X_with_sites["site_id"] = sites
    cat_cols_for_strat = [c for c in cat_available if c in X_with_sites.columns]

    cv_site_ids = select_stratified_sites(
        X_with_sites[["site_id"] + cat_cols_for_strat].drop_duplicates(subset=["site_id"]),
        cat_cols_for_strat,
        n_target=12,
    )
    logger.info(f"CV surrogate sites ({len(cv_site_ids)}): {cv_site_ids[:5]}...")

    # ==========================================
    # Train surrogate holdout model
    # ==========================================
    logger.info("Training surrogate holdout model...")
    surrogate_holdout = build_surrogate(X, y, cat_indices, SURROGATE_HOLDOUT)
    logger.info(f"  Trees: {surrogate_holdout.tree_count_}")

    if holdout is not None:
        holdout_preds = surrogate_holdout.predict(holdout["X"])
        holdout_pred_df = pd.DataFrame({
            "site_id": holdout["site_id"],
            "sample_time": holdout["sample_time"],
            "y_true": holdout["y"],
            "y_pred": holdout_preds,
            "lab_value": holdout["lab_value"],
        })
        holdout_pred_df.to_parquet(GOLDEN_MASTER_DIR / "surrogate_holdout_predictions.parquet")
        surrogate_holdout.save_model(str(GOLDEN_MASTER_DIR / "surrogate_holdout_model.cbm"))
        logger.info(f"  Holdout predictions: {len(holdout_pred_df)} samples")
    else:
        logger.warning("  No holdout data — skipping holdout surrogate")

    # ==========================================
    # Train surrogate CV model (LOGO on stratified sites)
    # ==========================================
    logger.info("Training surrogate CV model...")
    cv_mask = np.isin(sites, cv_site_ids)
    X_cv = X[cv_mask].copy()
    y_cv = y[cv_mask]
    sites_cv = sites[cv_mask]

    logo = LeaveOneGroupOut()
    oof_preds = np.full(len(y_cv), np.nan)
    oof_fold_ids = np.full(len(y_cv), -1, dtype=int)

    fold_assignments = {}
    for fold_idx, (train_idx, test_idx) in enumerate(logo.split(X_cv, y_cv, groups=sites_cv)):
        site_held_out = sites_cv[test_idx[0]]
        fold_assignments[fold_idx] = site_held_out

        model_cv = build_surrogate(
            X_cv.iloc[train_idx], y_cv[train_idx], cat_indices, SURROGATE_CV
        )
        oof_preds[test_idx] = model_cv.predict(X_cv.iloc[test_idx])
        oof_fold_ids[test_idx] = fold_idx

    cv_oof_df = pd.DataFrame({
        "site_id": sites_cv,
        "y_true": y_cv,
        "y_pred": oof_preds,
        "fold_idx": oof_fold_ids,
    })
    # Add sample_time for sorting
    if "sample_time" in X_cv.columns:
        cv_oof_df["sample_time"] = X_cv["sample_time"].values

    cv_oof_df.to_parquet(GOLDEN_MASTER_DIR / "surrogate_cv_oof_predictions.parquet")
    logger.info(f"  CV OOF predictions: {len(cv_oof_df)} samples, {len(fold_assignments)} folds")

    # ==========================================
    # Save all artifacts
    # ==========================================

    # Feature list (ordered)
    (GOLDEN_MASTER_DIR / "feature_cols_ordered.json").write_text(
        json.dumps(all_features, indent=2)
    )

    # Fold assignments
    (GOLDEN_MASTER_DIR / "fold_assignments.json").write_text(
        json.dumps(fold_assignments, indent=2)
    )

    # CV site IDs
    (GOLDEN_MASTER_DIR / "cv_site_ids.json").write_text(
        json.dumps(cv_site_ids, indent=2)
    )

    # Lineage
    (GOLDEN_MASTER_DIR / "lineage.json").write_text(
        json.dumps(stages, indent=2)
    )

    # Actual feature count (human-readable guard)
    (GOLDEN_MASTER_DIR / "ACTUAL_FEATURE_COUNT.txt").write_text(
        f"ACTUAL FEATURE COUNT: {len(all_features)}\n"
    )

    # Model meta parsed values
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        parsed_meta = {
            "feature_cols": meta.get("feature_cols"),
            "transform_type": meta.get("transform_type"),
            "transform_lmbda": meta.get("transform_lmbda"),
            "bcf": meta.get("bcf"),
            "bcf_mean": meta.get("bcf_mean"),
            "bcf_median": meta.get("bcf_median"),
            "cat_cols": meta.get("cat_cols"),
            "cat_indices": meta.get("cat_indices"),
            "n_trees": meta.get("n_trees"),
            "n_sites": meta.get("n_sites"),
            "n_samples": meta.get("n_samples"),
        }
        (GOLDEN_MASTER_DIR / "meta_parsed_values.json").write_text(
            json.dumps(parsed_meta, indent=2)
        )

    # Manifest
    manifest = {
        "upstream_hashes": upstream_hashes,
        "feature_count": len(all_features),
        "cat_count": len(cat_indices),
        "training_samples": X.shape[0],
        "training_sites": len(np.unique(sites)),
        "holdout_samples": len(holdout["X"]) if holdout else 0,
        "cv_surrogate_sites": len(cv_site_ids),
        "cv_surrogate_folds": len(fold_assignments),
        "surrogate_holdout_config": SURROGATE_HOLDOUT,
        "surrogate_cv_config": SURROGATE_CV,
        "measured_reproducibility_delta": repro["measured_reproducibility_delta"],
        "recommended_atol": atol,
        "pinned_versions": versions,
        "training_data_hash": hash_dataframe(X),
    }
    (GOLDEN_MASTER_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2)
    )

    logger.info(f"\nGolden master generated: {GOLDEN_MASTER_DIR}")
    logger.info(f"  Features: {len(all_features)}")
    logger.info(f"  Training: {X.shape[0]} samples, {len(np.unique(sites))} sites")
    logger.info(f"  Holdout predictions: {len(holdout_pred_df) if holdout else 0}")
    logger.info(f"  CV OOF predictions: {len(cv_oof_df)}")
    logger.info(f"  Tolerance: atol={atol:.2e}")


if __name__ == "__main__":
    main()
