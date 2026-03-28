"""Transform & constraint ablation sweep for SSC model.

Runs systematic experiments varying Box-Cox lambda, monotone constraints,
and HP sets. Uses GKF5 fast mode (~20 sec per experiment).

Usage:
    python scripts/transform_sweep.py              # Run Phase 1 (10 experiments)
    python scripts/transform_sweep.py --phase 2    # Run Phase 2 (needs Phase 1 results)
    python scripts/transform_sweep.py --phase all  # Run Phase 1 + 2 sequentially
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = str(PROJECT_ROOT / ".venv" / "Scripts" / "python")
TRAIN_SCRIPT = str(PROJECT_ROOT / "scripts" / "train_tiered.py")
DROP_LIST = PROJECT_ROOT / "data" / "optimized_drop_list.txt"
RESULTS_PATH = PROJECT_ROOT / "data" / "results" / "transform_sweep.parquet"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


def load_drop_features() -> str:
    """Load comma-separated drop list for 37-feature set."""
    return DROP_LIST.read_text().strip()


def parse_train_output(output: str, label: str) -> dict:
    """Extract metrics from train_tiered.py stderr output."""
    metrics = {"label": label}

    for line in output.split("\n"):
        if "Trees per fold:" in line:
            parts = line.split("median=")[1] if "median=" in line else ""
            if parts:
                try:
                    metrics["median_trees"] = int(parts.split(",")[0])
                    metrics["min_trees"] = int(parts.split("min=")[1].split(",")[0])
                    metrics["max_trees"] = int(parts.split("max=")[1].strip())
                except (ValueError, IndexError):
                    pass

        if "R²(log)=" in line or "R\u00b2(log)=" in line:
            try:
                for kv in line.split("|"):
                    for part in kv.split():
                        if "R²(log)=" in part or "R\u00b2(log)=" in part:
                            metrics["r2_log"] = float(part.split("=")[1])
                        elif "KGE(log)=" in part:
                            metrics["kge_log"] = float(part.split("=")[1])
                        elif "alpha=" in part:
                            metrics["kge_alpha"] = float(part.split("=")[1])
                        elif "R²(mg/L)=" in part or "R\u00b2(mg/L)=" in part:
                            metrics["r2_native"] = float(part.split("=")[1])
                        elif "RMSE(mg/L)=" in part:
                            metrics["rmse_native"] = float(part.split("=")[1])
                        elif "Bias=" in part:
                            val = part.split("=")[1].rstrip("%")
                            metrics["bias_pct"] = float(val)
                        elif "BCF=" in part:
                            metrics["bcf"] = float(part.split("=")[1])
            except (ValueError, IndexError):
                pass

        if "Box-Cox lambda" in line:
            try:
                metrics["actual_lambda"] = float(line.split(": ")[1].strip())
            except (ValueError, IndexError):
                pass

        if "Box-Cox lambdas:" in line:
            try:
                metrics["lambda_median"] = float(line.split("median=")[1].split(",")[0])
                metrics["lambda_std"] = float(line.split("std=")[1].split(",")[0])
            except (ValueError, IndexError):
                pass

    return metrics


def run_experiment(
    label: str,
    transform: str = "log1p",
    boxcox_lambda: float | None = None,
    no_monotone: bool = False,
    config_json: dict | None = None,
    weight_scheme: str | None = None,
    kge_eval: bool = False,
    timeout: int = 600,
) -> dict | None:
    """Run a single GKF5 experiment and return parsed metrics."""
    drop_features = load_drop_features()

    cmd = [
        PYTHON, TRAIN_SCRIPT,
        "--param", "ssc",
        "--tier", "C",
        "--cv-mode", "gkf5",
        "--n-jobs", "12",
        "--skip-ridge",
        "--skip-save-model",
        "--skip-shap",
        "--transform", transform,
        "--label", label,
        "--drop-features", drop_features,
    ]

    if boxcox_lambda is not None:
        cmd.extend(["--boxcox-lambda", str(boxcox_lambda)])
    if no_monotone:
        cmd.append("--no-monotone")
    if config_json:
        cmd.extend(["--config-json", json.dumps(config_json)])
    if weight_scheme:
        cmd.extend(["--weight-scheme", weight_scheme])
    if kge_eval:
        cmd.append("--kge-eval")

    logger.info(f"\n{'='*60}")
    logger.info(f"EXPERIMENT: {label}")
    logger.info(f"  transform={transform}, lambda={boxcox_lambda}, "
                f"monotone={'OFF' if no_monotone else 'ON'}, "
                f"weights={weight_scheme or 'none'}")
    if config_json:
        logger.info(f"  HP overrides: {config_json}")
    logger.info(f"{'='*60}")

    start = time.time()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=str(PROJECT_ROOT),
        )
        elapsed = time.time() - start
        logger.info(f"Completed in {elapsed:.1f}s (exit code {result.returncode})")

        if result.returncode != 0:
            logger.error(f"FAILED:\n{result.stderr[-1000:]}")
            return None

        metrics = parse_train_output(result.stderr, label)
        metrics["elapsed_sec"] = round(elapsed, 1)
        metrics["transform"] = transform
        metrics["boxcox_lambda"] = boxcox_lambda
        metrics["monotone"] = not no_monotone
        metrics["weight_scheme"] = weight_scheme
        return metrics

    except subprocess.TimeoutExpired:
        logger.error(f"TIMEOUT after {timeout}s")
        return None
    except Exception as e:
        logger.error(f"ERROR: {e}")
        return None


def save_results(results: list[dict]):
    """Save results to parquet (crash-safe — overwrites on each call)."""
    df = pd.DataFrame(results)
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(RESULTS_PATH, index=False)
    logger.info(f"Results saved to {RESULTS_PATH} ({len(df)} experiments)")
    return df


def print_results_table(df: pd.DataFrame):
    """Pretty-print comparison table."""
    cols = ["label", "transform", "boxcox_lambda", "monotone",
            "r2_log", "r2_native", "kge_log", "kge_alpha",
            "rmse_native", "bias_pct", "bcf", "median_trees", "elapsed_sec"]
    display_cols = [c for c in cols if c in df.columns]
    print("\n" + "=" * 120)
    print("TRANSFORM SWEEP RESULTS")
    print("=" * 120)
    print(df[display_cols].to_string(index=False, float_format="%.4f"))
    print("=" * 120)


def run_phase1() -> list[dict]:
    """Phase 1: Transform × constraint sweep (9 experiments + 1 conditional)."""
    results = []

    # Load existing results if any (crash recovery)
    if RESULTS_PATH.exists():
        existing = pd.read_parquet(RESULTS_PATH)
        done_labels = set(existing["label"].values)
        results = existing.to_dict("records")
        logger.info(f"Resuming: {len(done_labels)} experiments already done")
    else:
        done_labels = set()

    experiments = [
        # (label, transform, lambda, no_monotone, config_json)
        ("1_baseline_log1p", "log1p", None, False, None),
        ("2_log1p_noMono", "log1p", None, True, None),
        ("3_boxcox_auto", "boxcox", None, False, None),
        ("4_boxcox_auto_noMono", "boxcox", None, True, None),
        ("5_boxcox_0.1", "boxcox", 0.1, False, None),
        ("6_boxcox_0.2", "boxcox", 0.2, False, None),
        ("7_boxcox_0.3", "boxcox", 0.3, False, None),
        ("8_boxcox_0.5", "boxcox", 0.5, False, None),
        ("9_sqrt", "sqrt", None, False, None),
    ]

    for label, transform, lmbda, no_mono, config in experiments:
        if label in done_labels:
            logger.info(f"Skipping {label} (already done)")
            continue

        metrics = run_experiment(
            label=label,
            transform=transform,
            boxcox_lambda=lmbda,
            no_monotone=no_mono,
            config_json=config,
        )
        if metrics:
            results.append(metrics)
            save_results(results)

    # Experiment 10: best lambda + no monotone
    if not results:
        logger.error("No experiments succeeded — cannot pick best lambda")
        return results
    df = pd.DataFrame(results)
    if "transform" not in df.columns:
        logger.error("No valid results — 'transform' column missing")
        return results
    boxcox_rows = df[df["transform"] == "boxcox"]
    if not boxcox_rows.empty and "r2_native" in boxcox_rows.columns:
        best_row = boxcox_rows.loc[boxcox_rows["r2_native"].idxmax()]
        best_lambda = best_row.get("boxcox_lambda") or best_row.get("actual_lambda")
        label = "10_best_boxcox_noMono"
        if label not in done_labels and best_lambda is not None:
            metrics = run_experiment(
                label=label,
                transform="boxcox",
                boxcox_lambda=float(best_lambda),
                no_monotone=True,
            )
            if metrics:
                results.append(metrics)
                save_results(results)

    return results


def run_phase2(results: list[dict]) -> list[dict]:
    """Phase 2: Top lambdas × HP sets."""
    df = pd.DataFrame(results)
    done_labels = set(df["label"].values)

    # Find top 2 Box-Cox lambdas by r2_native
    boxcox_rows = df[df["transform"] == "boxcox"].copy()
    if boxcox_rows.empty or "r2_native" not in boxcox_rows.columns:
        logger.warning("No Box-Cox results — skipping Phase 2")
        return results

    boxcox_rows = boxcox_rows.sort_values("r2_native", ascending=False)
    top_lambdas = []
    for _, row in boxcox_rows.iterrows():
        lmbda = row.get("boxcox_lambda") or row.get("actual_lambda")
        if lmbda is not None and lmbda not in top_lambdas:
            top_lambdas.append(float(lmbda))
        if len(top_lambdas) >= 2:
            break

    hp_b = {"depth": 8, "learning_rate": 0.03, "l2_leaf_reg": 5}

    phase2_experiments = []
    for i, lmbda in enumerate(top_lambdas):
        phase2_experiments.append(
            (f"11_winner{i+1}_hpB", "boxcox", lmbda, False, hp_b)
        )
    if top_lambdas:
        phase2_experiments.append(
            (f"13_winner1_noMono_hpA", "boxcox", top_lambdas[0], True, None)
        )
        phase2_experiments.append(
            (f"14_winner1_noMono_hpB", "boxcox", top_lambdas[0], True, hp_b)
        )

    for label, transform, lmbda, no_mono, config in phase2_experiments:
        if label in done_labels:
            logger.info(f"Skipping {label} (already done)")
            continue

        metrics = run_experiment(
            label=label,
            transform=transform,
            boxcox_lambda=lmbda,
            no_monotone=no_mono,
            config_json=config,
        )
        if metrics:
            results.append(metrics)
            save_results(results)

    return results


def run_phase3_raw(results: list[dict]) -> list[dict]:
    """Phase 3: Raw SSC (no transform) with various weight schemes.

    Training on raw SSC naturally emphasizes extreme events (high-SSC storms),
    which is where traditional models fail and our competitive advantage lies.
    """
    df = pd.DataFrame(results)
    done_labels = set(df["label"].values)

    raw_experiments = [
        # (label, transform, lambda, no_monotone, config, weight_scheme)
        # Spectrum from maximum extreme emphasis to maximum baseflow emphasis:
        # linear weights = SSC itself as weight (MAXIMUM extreme emphasis)
        ("15_raw_linear_weights", "none", None, False, None, "linear"),
        # no weights = RMSE naturally overweights extremes
        ("16_raw_noWeights", "none", None, False, None, None),
        # sqrt weights = mild dampening of extremes
        ("17_raw_sqrt_weights", "none", None, False, None, "sqrt"),
        # log weights = moderate dampening of extremes
        ("18_raw_log_weights", "none", None, False, None, "log"),
        # no-monotone variants
        ("19_raw_noWeights_noMono", "none", None, True, None, None),
        ("20_raw_sqrt_weights_noMono", "none", None, True, None, "sqrt"),
        # HP set B on best raw config (decided after above)
        ("21_raw_noWeights_hpB", "none", None, False,
         {"depth": 8, "learning_rate": 0.03, "l2_leaf_reg": 5}, None),
    ]

    for label, transform, lmbda, no_mono, config, weights in raw_experiments:
        if label in done_labels:
            logger.info(f"Skipping {label} (already done)")
            continue

        metrics = run_experiment(
            label=label,
            transform=transform,
            boxcox_lambda=lmbda,
            no_monotone=no_mono,
            config_json=config,
            weight_scheme=weights,
        )
        if metrics:
            results.append(metrics)
            save_results(results)

    return results


def run_phase4_kge_and_fine_lambda(results: list[dict]) -> list[dict]:
    """Phase 4: Fine lambda sweep + KGE eval_metric experiments."""
    df = pd.DataFrame(results)
    done_labels = set(df["label"].values)

    phase4_experiments = [
        # Fine lambda sweep around 0.2
        ("22_boxcox_0.15", "boxcox", 0.15, False, None, None, False),
        ("23_boxcox_0.18", "boxcox", 0.18, False, None, None, False),
        ("24_boxcox_0.22", "boxcox", 0.22, False, None, None, False),
        ("25_boxcox_0.25", "boxcox", 0.25, False, None, None, False),
        # KGE eval_metric on Box-Cox 0.2 (the key experiment)
        ("26_boxcox_0.2_kgeEval", "boxcox", 0.2, False, None, None, True),
        # KGE eval_metric on log1p for comparison
        ("27_log1p_kgeEval", "log1p", None, False, None, None, True),
        # KGE eval_metric + no monotone (full freedom)
        ("28_boxcox_0.2_kgeEval_noMono", "boxcox", 0.2, True, None, None, True),
    ]

    for label, transform, lmbda, no_mono, config, weights, kge in phase4_experiments:
        if label in done_labels:
            logger.info(f"Skipping {label} (already done)")
            continue

        metrics = run_experiment(
            label=label,
            transform=transform,
            boxcox_lambda=lmbda,
            no_monotone=no_mono,
            config_json=config,
            weight_scheme=weights,
            kge_eval=kge,
        )
        if metrics:
            results.append(metrics)
            save_results(results)

    return results


def check_alpha_gate(results: list[dict]):
    """Check alpha diagnostic gate and recommend next step."""
    df = pd.DataFrame(results)
    if "kge_alpha" not in df.columns:
        logger.warning("No KGE alpha in results — cannot check gate")
        return

    # Find the best overall configuration
    best = df.loc[df["r2_native"].idxmax()]
    alpha = best.get("kge_alpha", float("nan"))

    print("\n" + "=" * 80)
    print("ALPHA DIAGNOSTIC GATE")
    print("=" * 80)
    print(f"Best config: {best['label']}")
    print(f"  R²(native) = {best['r2_native']:.4f}")
    print(f"  KGE alpha  = {alpha:.4f}")
    print()

    if alpha > 0.92:
        print(">>> alpha > 0.92: Spread problem SOLVED. Skip to HP sweep.")
    elif alpha > 0.85:
        print(">>> alpha 0.85-0.92: Try KGE eval_metric for early stopping (Phase 3, Exp 2).")
    else:
        print(">>> alpha < 0.85: Try SpreadAwareMSE custom loss (Phase 3, Exp 4).")
    print("=" * 80)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Transform & constraint ablation sweep")
    parser.add_argument("--phase", type=str, default="1", choices=["1", "2", "3", "4", "all"],
                        help="Which phase to run: 1 (transforms), 2 (HP sets), 3 (raw SSC), 4 (fine lambda + KGE), all")
    args = parser.parse_args()

    logger.info("Transform & Constraint Ablation Sweep")
    logger.info(f"Dataset: 396 sites, ~35K samples")
    logger.info(f"CV mode: GKF5 (5-fold, ~20 sec/experiment)")
    logger.info(f"Feature set: 37 features (via drop list)")

    if args.phase in ("1", "all"):
        results = run_phase1()
        df = save_results(results)
        print_results_table(df)

    if args.phase in ("2", "all"):
        if RESULTS_PATH.exists():
            existing = pd.read_parquet(RESULTS_PATH)
            results = existing.to_dict("records")
        else:
            logger.error("No Phase 1 results found — run Phase 1 first")
            return

        results = run_phase2(results)
        df = save_results(results)
        print_results_table(df)

    if args.phase in ("3", "all"):
        if RESULTS_PATH.exists():
            existing = pd.read_parquet(RESULTS_PATH)
            results = existing.to_dict("records")
        else:
            results = []

        results = run_phase3_raw(results)
        df = save_results(results)
        print_results_table(df)

    if args.phase in ("4", "all"):
        if RESULTS_PATH.exists():
            existing = pd.read_parquet(RESULTS_PATH)
            results = existing.to_dict("records")
        else:
            results = []

        results = run_phase4_kge_and_fine_lambda(results)
        df = save_results(results)
        print_results_table(df)

    # Always check alpha gate if we have results
    if RESULTS_PATH.exists():
        all_results = pd.read_parquet(RESULTS_PATH).to_dict("records")
        check_alpha_gate(all_results)


if __name__ == "__main__":
    main()
