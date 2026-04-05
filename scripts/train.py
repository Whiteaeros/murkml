"""Train murkml CatBoost model.

Thin CLI: loads config → loads data → trains model → saves artifacts.
All logic lives in src/murkml/ modules.

Usage:
    python scripts/train.py --config config/features.yaml --cv-mode logo --label v12
    python scripts/train.py --config config/features.yaml --cv-mode logo --label v12 --n-jobs 6
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from murkml.config import load_config
from murkml.data.loader import prepare_training_data
from murkml.training.cv import run_logo_cv
from murkml.training.model import (
    build_catboost_params,
    compute_monotone_constraints,
    save_model,
    train_final_model,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"
MODELS_DIR = DATA_DIR / "results" / "models"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train murkml CatBoost model")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config" / "features.yaml",
                        help="Path to YAML config")
    parser.add_argument("--cv-mode", choices=["logo", "none"], default="logo",
                        help="Cross-validation mode (logo=Leave-One-Group-Out)")
    parser.add_argument("--label", type=str, default=None,
                        help="Model label (overrides config version for output naming)")
    parser.add_argument("--n-jobs", type=int, default=6,
                        help="Parallel jobs for LOGO CV")
    parser.add_argument("--skip-cv", action="store_true",
                        help="Skip CV, only train and save final model")
    parser.add_argument("--skip-save", action="store_true",
                        help="Skip saving final model (CV metrics only)")
    return parser.parse_args()


def main():
    args = parse_args()
    t0 = time.time()

    # Load config
    config = load_config(args.config)
    label = args.label or config.version
    logger.info(f"Config: {args.config} | Version: {config.version} | Label: {label}")
    logger.info(f"Features: {len(config.features.all_features)} | CatBoost: {config.catboost.boosting_type}")

    # Load data
    logger.info("Loading data...")
    data = prepare_training_data(DATA_DIR, config)
    X, y = data["X"], data["y"]
    sites = data["sites"]
    feature_names = data["feature_names"]
    cat_indices = data["cat_indices"]

    logger.info(f"Training: {X.shape[0]} samples, {len(np.unique(sites))} sites, {X.shape[1]} features")

    # Cross-validation
    if args.cv_mode == "logo" and not args.skip_cv:
        logger.info(f"Running LOGO CV (n_jobs={args.n_jobs})...")
        cv_result = run_logo_cv(
            X, y, sites, cat_indices, config, feature_names,
            thread_count=max(1, (6 * 5) // args.n_jobs),  # ~5 threads per job
            n_jobs=args.n_jobs,
        )

        # Report CV metrics
        oof = cv_result["oof_predictions"]
        from murkml.evaluate.metrics import r_squared, kge, rmse
        from scipy.special import inv_boxcox1p

        r2_log = r_squared(y, oof)
        kge_log = kge(y, oof)

        # Native-space metrics
        y_native = inv_boxcox1p(y, config.transform.lmbda)
        oof_native = inv_boxcox1p(np.clip(oof, 0, None), config.transform.lmbda)
        rmse_native = rmse(y_native, oof_native)

        logger.info(
            f"CV Results: R²(log)={r2_log:.4f} | KGE(log)={kge_log:.4f} | "
            f"RMSE(native)={rmse_native:.1f} mg/L"
        )

    # Save final model
    if not args.skip_save:
        logger.info("Training final model...")
        model, metadata = train_final_model(
            X, y, cat_indices, config, feature_names,
            thread_count=config.catboost.thread_count,
        )
        model_path, meta_path = save_model(model, metadata, config, MODELS_DIR, label)

        # Verify feature count in saved meta
        saved_meta = json.loads(meta_path.read_text())
        assert len(saved_meta["feature_cols"]) == len(feature_names), (
            f"Feature count mismatch! Saved: {len(saved_meta['feature_cols'])}, "
            f"Expected: {len(feature_names)}"
        )
        logger.info(f"VERIFIED: Saved model has {len(saved_meta['feature_cols'])} features")

    elapsed = time.time() - t0
    logger.info(f"Done in {elapsed:.0f}s")


if __name__ == "__main__":
    main()
