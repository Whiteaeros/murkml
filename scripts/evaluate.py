"""Evaluate murkml model on holdout/vault partition.

Thin CLI wrapper. During Phase 4 migration, delegates to evaluate_model.py
functions. After full migration, evaluate/holdout.py replaces those functions.

Usage:
    python scripts/evaluate.py --model data/results/models/ssc_C_..._v12.cbm --label v12
    python scripts/evaluate.py --config config/features.yaml --model ... --label ...
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# During Phase 4: delegate to existing evaluate_model.py
# This wrapper exists to provide the new CLI interface while
# the full evaluate/holdout.py extraction happens.
# After extraction, this file calls evaluate/holdout.py directly.

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate murkml model")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config" / "features.yaml")
    parser.add_argument("--model", type=Path, required=True, help="Path to .cbm model file")
    parser.add_argument("--meta", type=Path, default=None, help="Path to _meta.json (auto-detected if not given)")
    parser.add_argument("--label", type=str, required=True, help="Evaluation label for output files")
    parser.add_argument("--partition", choices=["holdout", "vault"], default="holdout")
    parser.add_argument("--adaptation", choices=["bayesian", "none"], default="bayesian")
    return parser.parse_args()


def main():
    args = parse_args()

    # Auto-detect meta path
    if args.meta is None:
        args.meta = args.model.with_name(args.model.stem + "_meta.json")
        if not args.meta.exists():
            logger.error(f"Meta file not found: {args.meta}")
            sys.exit(1)

    logger.info(f"Model: {args.model}")
    logger.info(f"Meta: {args.meta}")
    logger.info(f"Label: {args.label}")
    logger.info(f"Partition: {args.partition}")

    # During Phase 4 migration: call legacy evaluate_model.py via its main function
    # After Phase 4: call evaluate/holdout.py functions directly
    from evaluate_model import main as legacy_main

    # Reconstruct sys.argv for legacy script
    legacy_args = [
        "evaluate_model.py",
        "--model", str(args.model),
        "--meta", str(args.meta),
        "--label", args.label,
        "--partition", args.partition,
        "--adaptation", args.adaptation,
    ]
    sys.argv = legacy_args
    legacy_main()


if __name__ == "__main__":
    main()
