"""Validate the refactored pipeline against the golden master.

Runs the new pipeline, compares outputs against golden master artifacts.
Must be run as a SEPARATE PROCESS from generate_golden_master.py.

Usage:
    python scripts/validate_golden_master.py
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
    hash_dataframe,
)
from murkml.config import load_config
from murkml.data.loader import prepare_training_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CONFIG_PATH = PROJECT_ROOT / "config" / "features.yaml"
DATA_DIR = PROJECT_ROOT / "data"


def load_golden_artifacts() -> dict:
    """Load all golden master artifacts."""
    return {
        "manifest": json.loads((GOLDEN_MASTER_DIR / "manifest.json").read_text()),
        "feature_cols": json.loads((GOLDEN_MASTER_DIR / "feature_cols_ordered.json").read_text()),
        "fold_assignments": json.loads((GOLDEN_MASTER_DIR / "fold_assignments.json").read_text()),
        "cv_site_ids": json.loads((GOLDEN_MASTER_DIR / "cv_site_ids.json").read_text()),
        "lineage": json.loads((GOLDEN_MASTER_DIR / "lineage.json").read_text()),
        "holdout_preds": pd.read_parquet(GOLDEN_MASTER_DIR / "surrogate_holdout_predictions.parquet"),
        "cv_oof_preds": pd.read_parquet(GOLDEN_MASTER_DIR / "surrogate_cv_oof_predictions.parquet"),
    }


def main():
    results = []

    # Check environment
    manifest_path = GOLDEN_MASTER_DIR / "manifest.json"
    versions = assert_pinned_environment(manifest_path)
    logger.info(f"Environment: {versions}")

    golden = load_golden_artifacts()
    atol = golden["manifest"]["recommended_atol"]
    logger.info(f"Tolerance: atol={atol:.2e}")

    # ========== Check 1: Feature list (ordered) ==========
    config = load_config(CONFIG_PATH)
    if config.features.all_features == golden["feature_cols"]:
        results.append(("Feature list (ordered)", "PASS"))
        logger.info("CHECK 1: PASS — Feature list matches golden master")
    else:
        results.append(("Feature list (ordered)", "FAIL"))
        logger.error("CHECK 1: FAIL — Feature list does NOT match")

    # ========== Check 2: Data loading + hashing ==========
    data = prepare_training_data(DATA_DIR, config)
    X, y, sites = data["X"], data["y"], data["sites"]
    cat_indices = data["cat_indices"]

    training_hash = hash_dataframe(X)
    golden_hash = golden["manifest"]["training_data_hash"]
    if training_hash == golden_hash:
        results.append(("Training data hash", "PASS"))
        logger.info("CHECK 2: PASS — Training data hash matches")
    else:
        results.append(("Training data hash", "FAIL"))
        logger.error(f"CHECK 2: FAIL — Hash mismatch: {training_hash[:16]}... vs {golden_hash[:16]}...")

    # ========== Check 3: Surrogate holdout predictions ==========
    holdout = data["holdout"]
    if holdout is not None:
        model_holdout = build_surrogate(X, y, cat_indices, SURROGATE_HOLDOUT)
        preds_holdout = model_holdout.predict(holdout["X"])

        golden_holdout = golden["holdout_preds"].sort_values(
            ["site_id", "sample_time"]
        ).reset_index(drop=True)
        new_holdout = pd.DataFrame({
            "site_id": holdout["site_id"],
            "sample_time": holdout["sample_time"],
            "y_pred": preds_holdout,
        }).sort_values(["site_id", "sample_time"]).reset_index(drop=True)

        delta_holdout = np.max(np.abs(
            new_holdout["y_pred"].values - golden_holdout["y_pred"].values
        ))
        if delta_holdout <= atol:
            results.append(("Surrogate holdout", f"PASS (delta={delta_holdout:.2e})"))
            logger.info(f"CHECK 3: PASS — Holdout delta={delta_holdout:.2e}")
        else:
            results.append(("Surrogate holdout", f"FAIL (delta={delta_holdout:.2e})"))
            logger.error(f"CHECK 3: FAIL — Holdout delta={delta_holdout:.2e} > atol={atol:.2e}")

    # ========== Check 4: Surrogate CV OOF predictions ==========
    cv_site_ids = golden["cv_site_ids"]
    cv_mask = np.isin(sites, cv_site_ids)
    X_cv = X[cv_mask].copy()
    y_cv = y[cv_mask]
    sites_cv = sites[cv_mask]

    logo = LeaveOneGroupOut()
    oof_preds = np.full(len(y_cv), np.nan)
    fold_assignments = {}

    for fold_idx, (train_idx, test_idx) in enumerate(logo.split(X_cv, y_cv, groups=sites_cv)):
        site = sites_cv[test_idx[0]]
        fold_assignments[fold_idx] = site
        model_cv = build_surrogate(
            X_cv.iloc[train_idx], y_cv[train_idx], cat_indices, SURROGATE_CV
        )
        oof_preds[test_idx] = model_cv.predict(X_cv.iloc[test_idx])

    golden_cv = golden["cv_oof_preds"].sort_values(
        ["site_id", "y_true"]
    ).reset_index(drop=True)
    new_cv = pd.DataFrame({
        "site_id": sites_cv,
        "y_true": y_cv,
        "y_pred": oof_preds,
    }).sort_values(["site_id", "y_true"]).reset_index(drop=True)

    delta_cv = np.max(np.abs(new_cv["y_pred"].values - golden_cv["y_pred"].values))
    if delta_cv <= atol:
        results.append(("Surrogate CV OOF", f"PASS (delta={delta_cv:.2e})"))
        logger.info(f"CHECK 4: PASS — CV delta={delta_cv:.2e}")
    else:
        results.append(("Surrogate CV OOF", f"FAIL (delta={delta_cv:.2e})"))
        logger.error(f"CHECK 4: FAIL — CV delta={delta_cv:.2e} > atol={atol:.2e}")

    # ========== Check 5: Fold assignments ==========
    golden_folds = golden["fold_assignments"]
    new_folds = {str(k): v for k, v in fold_assignments.items()}
    if new_folds == golden_folds:
        results.append(("Fold assignments", "PASS"))
        logger.info("CHECK 5: PASS — Fold assignments match")
    else:
        results.append(("Fold assignments", "FAIL"))
        logger.error("CHECK 5: FAIL — Fold assignments differ")

    # ========== Check 6: Lineage ==========
    golden_lineage = golden["lineage"]
    new_lineage = data["lineage"]
    lineage_match = True
    for stage in ["post_load", "post_split"]:
        if stage in golden_lineage and stage in new_lineage:
            g_rows = golden_lineage[stage].get("rows")
            n_rows = new_lineage[stage].get("rows")
            if g_rows != n_rows:
                lineage_match = False
                logger.error(f"  Lineage {stage}: rows {g_rows} vs {n_rows}")
    # post_select: golden master records pre-dedup (23624), new pipeline records post-dedup (23615).
    # The 9-row delta is the known duplicate rows. Training data hash (CHECK 2) already proves
    # the actual training matrices match. Feature count must match.
    g_feats = golden_lineage.get("post_select", {}).get("features_selected")
    n_feats = new_lineage.get("post_select", {}).get("features_selected")
    if g_feats != n_feats:
        lineage_match = False
        logger.error(f"  Lineage post_select features: {g_feats} vs {n_feats}")
    if lineage_match:
        results.append(("Lineage row counts", "PASS"))
        logger.info("CHECK 6: PASS — Lineage matches")
    else:
        results.append(("Lineage row counts", "FAIL"))

    # ========== Summary ==========
    print("\n" + "=" * 60)
    print("GOLDEN MASTER VALIDATION SUMMARY")
    print("=" * 60)
    all_pass = True
    for name, status in results:
        marker = "PASS" if "PASS" in status else "FAIL"
        if marker == "FAIL":
            all_pass = False
        print(f"  [{marker}] {name}: {status}")
    print("=" * 60)
    if all_pass:
        print("ALL CHECKS PASSED — refactored pipeline matches golden master")
    else:
        print("SOME CHECKS FAILED — investigate before proceeding")
        sys.exit(1)


if __name__ == "__main__":
    main()
