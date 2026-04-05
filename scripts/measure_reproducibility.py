"""Measure CatBoost surrogate reproducibility by training twice and comparing.

Runs before generate_golden_master.py to establish empirical tolerance.
Uses the SAME _build_surrogate() function as the golden master scripts.
"""
from __future__ import annotations

import json
import logging
import sys
import tempfile
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from golden_master_utils import (
    GOLDEN_MASTER_DIR,
    SURROGATE_HOLDOUT,
    assert_pinned_environment,
    build_surrogate,
    load_legacy_data,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    assert Path.cwd() == PROJECT_ROOT or PROJECT_ROOT.exists(), (
        f"CWD must be project root or project root must exist: {PROJECT_ROOT}"
    )

    versions = assert_pinned_environment()
    logger.info(f"Versions: {versions}")

    logger.info("Loading legacy data...")
    data = load_legacy_data()
    X, y = data["X"], data["y"]
    cat_indices = data["cat_indices"]

    if data["holdout"] is None:
        raise RuntimeError("No holdout data available for reproducibility test")

    X_holdout = data["holdout"]["X"]

    logger.info(f"Training data: {X.shape}, Holdout: {X_holdout.shape}")
    logger.info(f"Surrogate config: {SURROGATE_HOLDOUT}")

    # Train twice
    logger.info("Training surrogate run 1...")
    model1 = build_surrogate(X, y, cat_indices, SURROGATE_HOLDOUT)
    preds1 = model1.predict(X_holdout)

    logger.info("Training surrogate run 2...")
    model2 = build_surrogate(X, y, cat_indices, SURROGATE_HOLDOUT)
    preds2 = model2.predict(X_holdout)

    # Measure delta
    delta = np.max(np.abs(preds1 - preds2))
    logger.info(f"Max absolute delta between runs: {delta:.2e}")

    if delta == 0.0:
        logger.info("Delta is 0.0 (expected with thread_count=1, pinned seed, same machine)")
    else:
        logger.warning(f"Nonzero delta: {delta:.2e} — investigate environment drift")

    tolerance = max(1e-10, 10 * delta)
    logger.info(f"Recommended validation tolerance: atol={tolerance:.2e}")

    # Save result
    GOLDEN_MASTER_DIR.mkdir(parents=True, exist_ok=True)
    result = {
        "measured_reproducibility_delta": float(delta),
        "recommended_atol": float(tolerance),
        "surrogate_config": SURROGATE_HOLDOUT,
        "n_holdout_samples": len(preds1),
        "pinned_versions": versions,
    }
    out_path = GOLDEN_MASTER_DIR / "reproducibility_measurement.json"
    out_path.write_text(json.dumps(result, indent=2))
    logger.info(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
