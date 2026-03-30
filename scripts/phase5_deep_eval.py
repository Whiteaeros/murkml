#!/usr/bin/env python
"""Phase 5 Step 5: Disaggregated evaluation of ablation models.

Runs evaluate_model.py on each saved ablation model to get disaggregated
metrics (by geology, collection method, turbidity level, etc.) and physics
validation (first flush, hysteresis, extremes).

Only evaluates models that need it (harmful + ambiguous features from screening).
Skips models that already have evaluation results.

Usage:
    python scripts/phase5_deep_eval.py
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = DATA_DIR / "results"
MODELS_DIR = RESULTS_DIR / "models"
EVAL_DIR = RESULTS_DIR / "phase5_deep_eval"
PYTHON = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")
EVAL_SCRIPT = str(PROJECT_ROOT / "scripts" / "evaluate_model.py")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)


def get_models_to_evaluate() -> list[dict]:
    """Identify which ablation models need disaggregated evaluation."""
    # Load screening results
    screen = pd.read_csv(RESULTS_DIR / "phase5_screening_results.csv")
    drops = screen[screen["type"] == "drop"]

    # Harmful: aggregate R2_native improves when dropped (feature hurts on aggregate)
    harmful = drops[drops["dR2_nat"] > 0.003]
    # Ambiguous: within ±0.005
    ambiguous = drops[(drops["dR2_nat"] >= -0.005) & (drops["dR2_nat"] <= 0.003)]

    models = []

    # Always include baseline
    models.append({
        "label": "phase5_baseline",
        "feature": None,
        "type": "baseline",
        "dR2_nat": 0.0,
    })

    # Harmful features — need to check if they help subgroups
    for _, row in harmful.iterrows():
        models.append({
            "label": f"drop_{row['feature']}",
            "feature": row["feature"],
            "type": "harmful",
            "dR2_nat": row["dR2_nat"],
        })

    # Ambiguous features — need disaggregated info to decide
    for _, row in ambiguous.iterrows():
        models.append({
            "label": f"drop_{row['feature']}",
            "feature": row["feature"],
            "type": "ambiguous",
            "dR2_nat": row["dR2_nat"],
        })

    return models


def run_evaluation(label: str, model_path: Path, meta_path: Path,
                   output_dir: Path) -> bool:
    """Run evaluate_model.py on one model. Returns True if successful."""
    cmd = [
        PYTHON, EVAL_SCRIPT,
        "--model", str(model_path),
        "--meta", str(meta_path),
        "--label", label,
        "--adaptation", "bayesian",
        "--split-modes", "random",
        "--n-trials", "20",
        "--output-dir", str(output_dir),
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode != 0:
            logger.error(f"  FAILED: {result.stderr[-500:]}")
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.error(f"  TIMEOUT")
        return False
    except Exception as e:
        logger.error(f"  ERROR: {e}")
        return False


def main():
    EVAL_DIR.mkdir(parents=True, exist_ok=True)

    models = get_models_to_evaluate()
    logger.info(f"Models to evaluate: {len(models)}")
    logger.info(f"  Baseline: 1")
    logger.info(f"  Harmful: {sum(1 for m in models if m['type']=='harmful')}")
    logger.info(f"  Ambiguous: {sum(1 for m in models if m['type']=='ambiguous')}")

    # Check which already have evaluation results
    already_done = set()
    for f in EVAL_DIR.glob("*_summary.json"):
        already_done.add(f.stem.replace("_summary", ""))

    remaining = [m for m in models if m["label"] not in already_done]
    logger.info(f"Already evaluated: {len(already_done)}")
    logger.info(f"Remaining: {len(remaining)}")

    if not remaining:
        logger.info("All evaluations complete!")
    else:
        est_min = len(remaining) * 1.5
        logger.info(f"Estimated time: ~{est_min:.0f} min")

    logger.info(f"{'='*70}\n")

    n_done = 0
    n_failed = 0

    for m in remaining:
        label = m["label"]
        model_path = MODELS_DIR / f"ssc_C_sensor_basic_watershed_{label}_es.cbm"
        meta_path = MODELS_DIR / f"ssc_C_sensor_basic_watershed_{label}_es_meta.json"

        if not model_path.exists():
            logger.warning(f"  Model not found: {model_path.name} — skipping")
            n_failed += 1
            continue
        if not meta_path.exists():
            logger.warning(f"  Meta not found: {meta_path.name} — skipping")
            n_failed += 1
            continue

        n_done += 1
        logger.info(f"[{n_done}/{len(remaining)}] {label} ({m['type']}, dR2_nat={m['dR2_nat']:+.4f})")

        t0 = time.time()
        ok = run_evaluation(label, model_path, meta_path, EVAL_DIR)
        elapsed = time.time() - t0

        if ok:
            logger.info(f"  Done ({elapsed:.0f}s)")
        else:
            n_failed += 1

    logger.info(f"\n{'='*70}")
    logger.info(f"COMPLETE: {n_done} evaluated, {n_failed} failed")
    logger.info(f"Results in: {EVAL_DIR}")
    logger.info(f"{'='*70}")

    # Now compare: load all summaries and build comparison table
    if n_done > 0 or already_done:
        _build_comparison()


def _build_comparison():
    """Build a comparison table across all evaluated models."""
    screen = pd.read_csv(RESULTS_DIR / "phase5_screening_results.csv")

    rows = []
    for f in sorted(EVAL_DIR.glob("*_summary.json")):
        label = f.stem.replace("_summary", "")
        with open(f) as fh:
            summary = json.load(fh)

        zs = summary.get("zero_shot", {})
        row = {
            "label": label,
            "pooled_nse": zs.get("pooled_nse"),
            "pooled_log_nse": zs.get("pooled_log_nse"),
            "pooled_kge": zs.get("pooled_kge"),
            "pooled_mape": zs.get("pooled_mape_pct"),
            "pooled_within_2x": zs.get("pooled_frac_within_2x"),
            "pooled_bias": zs.get("pooled_bias_pct"),
            "pooled_spearman": zs.get("pooled_spearman_rho"),
            "med_persite_r2": zs.get("median_per_site_r2"),
        }

        # Get screening delta
        if label == "phase5_baseline":
            row["screen_dR2_nat"] = 0.0
        else:
            feat = label.replace("drop_", "").replace("add_", "")
            match = screen[screen["feature"] == feat]
            if len(match) > 0:
                row["screen_dR2_nat"] = match.iloc[0]["dR2_nat"]

        rows.append(row)

    if rows:
        comp = pd.DataFrame(rows)
        comp.to_csv(EVAL_DIR / "comparison_table.csv", index=False)
        logger.info(f"\nComparison table saved: {EVAL_DIR / 'comparison_table.csv'}")

        # Print summary
        if "phase5_baseline" in comp["label"].values:
            base = comp[comp["label"] == "phase5_baseline"].iloc[0]
            logger.info(f"\nBaseline: NSE={base['pooled_nse']:.4f}, "
                        f"MAPE={base['pooled_mape']:.1f}%, "
                        f"Spearman={base['pooled_spearman']:.4f}")

            others = comp[comp["label"] != "phase5_baseline"].copy()
            if len(others) > 0:
                others["delta_nse"] = others["pooled_nse"] - base["pooled_nse"]
                others["delta_mape"] = others["pooled_mape"] - base["pooled_mape"]

                logger.info(f"\n{'Label':<50s}  {'dNSE':>7s}  {'dMAPE':>7s}  {'Spear':>6s}  {'Bias':>7s}")
                logger.info("-" * 85)
                for _, row in others.sort_values("delta_nse").iterrows():
                    logger.info(f"{row['label']:<50s}  {row['delta_nse']:>+7.4f}  "
                                f"{row['delta_mape']:>+7.1f}  {row['pooled_spearman']:>6.4f}  "
                                f"{row['pooled_bias']:>+7.1f}%")


if __name__ == "__main__":
    main()
