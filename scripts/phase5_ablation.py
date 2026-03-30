#!/usr/bin/env python
"""Phase 5: Informed feature ablation with crash-safe incremental saves.

Screens all features by drop-one GKF5 training, saving results after each
experiment. Resumes from checkpoint if interrupted.

Usage:
    python scripts/phase5_ablation.py                    # full screening
    python scripts/phase5_ablation.py --mode reintroduce # re-test dropped features
    python scripts/phase5_ablation.py --mode both        # do both (default)
    python scripts/phase5_ablation.py --parallel 2       # run 2 experiments at a time
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = DATA_DIR / "results"
OUTPUT_PATH = RESULTS_DIR / "phase5_ablation_screen.parquet"
LOCK_PATH = RESULTS_DIR / "phase5_ablation.lock"
PYTHON = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")
TRAIN_SCRIPT = str(PROJECT_ROOT / "scripts" / "train_tiered.py")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Feature lists
# ---------------------------------------------------------------------------

def get_current_features() -> list[str]:
    """Get the 44 features from the current model meta."""
    meta_path = DATA_DIR / "results" / "models" / "ssc_C_sensor_basic_watershed_meta.json"
    with open(meta_path) as f:
        meta = json.load(f)
    return meta["feature_cols"]


def get_sgmc_features() -> list[str]:
    """Get the 28 SGMC lithology feature names."""
    sgmc_path = DATA_DIR / "sgmc" / "sgmc_features_for_model.parquet"
    if not sgmc_path.exists():
        return []
    df = pd.read_parquet(sgmc_path)
    return [c for c in df.columns if c != "site_id"]


def get_drop_list() -> list[str]:
    """Read the optimized drop list."""
    drop_path = DATA_DIR / "optimized_drop_list.txt"
    with open(drop_path) as f:
        return [x.strip() for x in f.read().split(",") if x.strip()]


# Features to re-introduce (currently on drop list but physics-plausible)
REINTRODUCE_CANDIDATES = [
    "ph_instant",
    "discharge_instant",
    "precip_24h",
    "temp_at_sample",
    "temp_mean_c",
    "slope_pct",
    "soil_erodibility",
    "do_instant",
    "soil_permeability",
    "water_table_depth",
]


# ---------------------------------------------------------------------------
# Experiment runner
# ---------------------------------------------------------------------------

def parse_train_output(output: str) -> dict:
    """Extract metrics from train_tiered.py stderr output."""
    metrics = {}
    for line in output.split("\n"):
        if "Trees per fold:" in line:
            try:
                metrics["median_trees"] = int(line.split("median=")[1].split(",")[0])
                metrics["min_trees"] = int(line.split("min=")[1].split(",")[0])
                metrics["max_trees"] = int(line.split("max=")[1].strip())
            except (ValueError, IndexError):
                pass

        # Match the results line with R² and other metrics
        if "R\u00b2(log)=" in line or "R²(log)=" in line:
            try:
                for kv in line.split("|"):
                    for part in kv.split():
                        if "R\u00b2(log)=" in part or "R²(log)=" in part:
                            metrics["r2_log"] = float(part.split("=")[1])
                        elif "KGE(log)=" in part:
                            metrics["kge_log"] = float(part.split("=")[1])
                        elif "alpha=" in part:
                            metrics["alpha"] = float(part.split("=")[1])
                        elif "R\u00b2(mg/L)=" in part or "R²(mg/L)=" in part:
                            metrics["r2_native"] = float(part.split("=")[1])
                        elif "RMSE(mg/L)=" in part:
                            metrics["rmse_native"] = float(part.split("=")[1])
                        elif "Bias=" in part:
                            metrics["bias_pct"] = float(part.split("=")[1].rstrip("%"))
                        elif "BCF=" in part:
                            metrics["bcf"] = float(part.split("=")[1])
            except (ValueError, IndexError):
                pass

        if "features" in line and "numeric" in line and "categorical" in line:
            try:
                parts = line.split("samples, ")[1] if "samples, " in line else ""
                if "numeric" in parts:
                    n_num = int(parts.split(" numeric")[0])
                    n_cat = int(parts.split("+ ")[1].split(" cat")[0])
                    metrics["n_features"] = n_num + n_cat
            except (ValueError, IndexError):
                pass

    return metrics


def run_one_experiment(label: str, drop_features: list[str], timeout: int = 600) -> dict:
    """Run a single GKF5 training experiment.

    Returns dict with metrics + status. Never raises — catches all errors.
    """
    cmd = [
        PYTHON, TRAIN_SCRIPT,
        "--param", "ssc",
        "--tier", "C",
        "--cv-mode", "gkf5",
        "--transform", "boxcox",
        "--boxcox-lambda", "0.2",
        "--n-jobs", "8",
        "--skip-ridge",
        "--skip-shap",
        "--label", label,
        "--drop-features", ",".join(drop_features),
    ]

    start = time.time()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=str(PROJECT_ROOT),
        )
        elapsed = time.time() - start

        if result.returncode != 0:
            logger.error(f"  FAILED ({elapsed:.0f}s): {result.stderr[-2000:]}")
            return {
                "label": label,
                "status": "FAILED",
                "error_msg": result.stderr[-2000:],
                "elapsed_sec": elapsed,
            }

        metrics = parse_train_output(result.stderr)
        metrics["label"] = label
        metrics["status"] = "OK"
        metrics["elapsed_sec"] = round(elapsed, 1)
        return metrics

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        logger.error(f"  TIMEOUT after {elapsed:.0f}s")
        return {"label": label, "status": "TIMEOUT", "error_msg": f"Timeout after {timeout}s", "elapsed_sec": elapsed}
    except Exception as e:
        elapsed = time.time() - start
        logger.error(f"  ERROR: {e}")
        return {"label": label, "status": "ERROR", "error_msg": str(e), "elapsed_sec": elapsed}


# ---------------------------------------------------------------------------
# Crash-safe result management
# ---------------------------------------------------------------------------

def load_existing_results() -> pd.DataFrame:
    """Load existing results from checkpoint."""
    if OUTPUT_PATH.exists():
        df = pd.read_parquet(OUTPUT_PATH)
        logger.info(f"Loaded {len(df)} existing results from checkpoint")
        return df
    return pd.DataFrame()


def save_result(result: dict, existing: pd.DataFrame) -> pd.DataFrame:
    """Append one result and save atomically to parquet."""
    new_row = pd.DataFrame([result])
    combined = pd.concat([existing, new_row], ignore_index=True)

    # Atomic write: write to temp, then rename
    tmp_path = OUTPUT_PATH.with_suffix(".tmp")
    combined.to_parquet(tmp_path, index=False)
    shutil.move(str(tmp_path), str(OUTPUT_PATH))

    return combined


def acquire_lock() -> bool:
    """Acquire a simple file lock. Returns True if acquired."""
    if LOCK_PATH.exists():
        # Check if the lock is stale (>6 hours old)
        age_hrs = (time.time() - LOCK_PATH.stat().st_mtime) / 3600
        if age_hrs > 12:
            logger.warning(f"Removing stale lock file ({age_hrs:.1f} hours old)")
            LOCK_PATH.unlink()
        else:
            return False
    LOCK_PATH.write_text(f"PID={os.getpid()} time={time.time()}")
    return True


def release_lock():
    """Release the file lock."""
    if LOCK_PATH.exists():
        LOCK_PATH.unlink()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Phase 5 informed feature ablation")
    parser.add_argument("--mode", choices=["drop", "reintroduce", "both"], default="both",
                        help="drop: screen current features. reintroduce: test adding back dropped features. both: do both.")
    parser.add_argument("--parallel", type=int, default=1,
                        help="Number of experiments to run in parallel (default: 1)")
    args = parser.parse_args()

    # Acquire lock
    if not acquire_lock():
        logger.error("Another instance is running (lock file exists). Exiting.")
        logger.error(f"Lock file: {LOCK_PATH}")
        logger.error("If this is a mistake, delete the lock file and retry.")
        sys.exit(1)

    try:
        _run(args)
    finally:
        release_lock()


def _run(args):
    # Validate inputs
    logger.info("Validating inputs...")
    meta_path = DATA_DIR / "results" / "models" / "ssc_C_sensor_basic_watershed_meta.json"
    assert meta_path.exists(), f"Model meta not found: {meta_path}"
    drop_list_path = DATA_DIR / "optimized_drop_list.txt"
    assert drop_list_path.exists(), f"Drop list not found: {drop_list_path}"
    assert Path(PYTHON).exists(), f"Python not found: {PYTHON}"
    assert Path(TRAIN_SCRIPT).exists(), f"Train script not found: {TRAIN_SCRIPT}"

    current_features = get_current_features()
    sgmc_features = get_sgmc_features()
    base_drop_list = get_drop_list()

    logger.info(f"  Current model features: {len(current_features)}")
    logger.info(f"  SGMC features: {len(sgmc_features)}")
    logger.info(f"  Base drop list: {len(base_drop_list)} features")

    all_features = current_features + sgmc_features
    logger.info(f"  Total features to screen: {len(all_features)}")

    # Build experiment list
    experiments = []

    # Baseline (current model, no changes)
    experiments.append({
        "label": "phase5_baseline",
        "type": "baseline",
        "feature": None,
        "drop_list": base_drop_list,
    })

    # Step 2: Drop-one screening for each current feature
    if args.mode in ("drop", "both"):
        for feat in all_features:
            experiments.append({
                "label": f"drop_{feat}",
                "type": "drop",
                "feature": feat,
                "drop_list": base_drop_list + [feat],
            })

    # Step 3: Re-introduce candidates
    if args.mode in ("reintroduce", "both"):
        for feat in REINTRODUCE_CANDIDATES:
            if feat in base_drop_list:
                new_drop = [f for f in base_drop_list if f != feat]
                experiments.append({
                    "label": f"add_{feat}",
                    "type": "reintroduce",
                    "feature": feat,
                    "drop_list": new_drop,
                })
            else:
                logger.warning(f"  {feat} not in drop list — skipping reintroduce")

    # Load checkpoint and filter already-completed experiments
    existing = load_existing_results()
    completed_labels = set(existing["label"]) if len(existing) > 0 else set()
    remaining = [e for e in experiments if e["label"] not in completed_labels]

    logger.info(f"\n{'='*70}")
    logger.info(f"PHASE 5 ABLATION SCREENING")
    logger.info(f"{'='*70}")
    logger.info(f"Total experiments: {len(experiments)}")
    logger.info(f"Already completed: {len(completed_labels)}")
    logger.info(f"Remaining: {len(remaining)}")
    est_min = len(remaining) * 4 / max(args.parallel, 1)
    logger.info(f"Estimated time: ~{est_min:.0f} min ({est_min/60:.1f} hrs)")
    logger.info(f"{'='*70}\n")

    if not remaining:
        logger.info("All experiments already completed!")
        _print_summary(existing)
        return

    # Run experiments
    n_total = len(experiments)
    n_done = len(completed_labels)
    n_failed = 0

    for i, exp in enumerate(remaining):
        n_done += 1
        logger.info(f"[{n_done}/{n_total}] {exp['label']} ({exp['type']}: {exp['feature'] or 'baseline'})")

        result = run_one_experiment(exp["label"], exp["drop_list"])
        result["type"] = exp["type"]
        result["feature"] = exp["feature"]

        if result["status"] != "OK":
            n_failed += 1
            logger.warning(f"  >>> {result['status']}: {result.get('error_msg', '')[:200]}")
        else:
            r2n = result.get("r2_native", np.nan)
            r2l = result.get("r2_log", np.nan)
            logger.info(f"  R2_native={r2n:.4f}  R2_log={r2l:.4f}  ({result['elapsed_sec']:.0f}s)")

        # Save immediately
        existing = save_result(result, existing)

    # Final summary
    logger.info(f"\n{'='*70}")
    logger.info(f"COMPLETED: {n_done} experiments, {n_failed} failures")
    logger.info(f"{'='*70}")

    _print_summary(existing)


def _print_summary(results: pd.DataFrame):
    """Print a sorted summary of ablation results."""
    if len(results) == 0:
        return

    ok = results[results["status"] == "OK"].copy()
    if len(ok) == 0:
        logger.warning("No successful experiments!")
        return

    # Get baseline
    baseline = ok[ok["label"] == "phase5_baseline"]
    if len(baseline) == 0:
        logger.warning("No baseline found — cannot compute deltas")
        return

    base_r2n = baseline.iloc[0].get("r2_native", np.nan)
    base_r2l = baseline.iloc[0].get("r2_log", np.nan)

    ok["delta_r2_native"] = ok["r2_native"] - base_r2n
    ok["delta_r2_log"] = ok["r2_log"] - base_r2l

    # Sort drop experiments by impact (most harmful to drop = most important feature)
    drops = ok[ok["type"] == "drop"].sort_values("delta_r2_native")
    adds = ok[ok["type"] == "reintroduce"].sort_values("delta_r2_native", ascending=False)

    logger.info(f"\nBaseline: R2_native={base_r2n:.4f}, R2_log={base_r2l:.4f}")

    if len(drops) > 0:
        logger.info(f"\n--- DROP-ONE SCREENING (drop = feature removed) ---")
        logger.info(f"{'Feature':<45s}  {'R2_nat':>8s}  {'delta':>8s}  {'R2_log':>8s}  {'delta':>8s}")
        logger.info("-" * 85)
        for _, row in drops.iterrows():
            feat = row.get("feature", "?")
            r2n = row.get("r2_native", np.nan)
            dn = row.get("delta_r2_native", np.nan)
            r2l = row.get("r2_log", np.nan)
            dl = row.get("delta_r2_log", np.nan)
            flag = " <<<" if abs(dn) > 0.005 else ""
            logger.info(f"{feat:<45s}  {r2n:>8.4f}  {dn:>+8.4f}  {r2l:>8.4f}  {dl:>+8.4f}{flag}")

    if len(adds) > 0:
        logger.info(f"\n--- RE-INTRODUCE SCREENING (add = feature added back) ---")
        logger.info(f"{'Feature':<45s}  {'R2_nat':>8s}  {'delta':>8s}  {'R2_log':>8s}  {'delta':>8s}")
        logger.info("-" * 85)
        for _, row in adds.iterrows():
            feat = row.get("feature", "?")
            r2n = row.get("r2_native", np.nan)
            dn = row.get("delta_r2_native", np.nan)
            r2l = row.get("r2_log", np.nan)
            dl = row.get("delta_r2_log", np.nan)
            flag = " <<<" if dn > 0.005 else ""
            logger.info(f"{feat:<45s}  {r2n:>8.4f}  {dn:>+8.4f}  {r2l:>8.4f}  {dl:>+8.4f}{flag}")

    # Summary of failures
    failed = results[results["status"] != "OK"]
    if len(failed) > 0:
        logger.info(f"\n--- FAILURES ({len(failed)}) ---")
        for _, row in failed.iterrows():
            logger.info(f"  {row['label']}: {row['status']} — {row.get('error_msg', '')[:100]}")


if __name__ == "__main__":
    main()
