"""
Hyperparameter sensitivity analysis for the v11 CatBoost model.

Varies one parameter at a time around the v11 defaults to show
model stability. For WRR Appendix A.

Usage:
    python scripts/hp_sensitivity_sweep.py
"""
import json
import subprocess
import sys
import re
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "train_tiered.py"
PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python"

# v11 defaults (the actual config used for the published model)
V11_DEFAULTS = {
    "depth": 6,
    "learning_rate": 0.05,
    "l2_leaf_reg": 3,
    "iterations": 500,
    "early_stopping_rounds": 50,
    "boosting_type": "Plain",
    "random_seed": 42,
}

# Sensitivity experiments: vary ONE parameter at a time
EXPERIMENTS = {
    # Baseline (v11 config)
    "baseline_v11": {},

    # Tree depth
    "depth_4": {"depth": 4},
    "depth_8": {"depth": 8},
    "depth_10": {"depth": 10},

    # Learning rate
    "lr_0.01": {"learning_rate": 0.01, "iterations": 2000},
    "lr_0.03": {"learning_rate": 0.03, "iterations": 1000},
    "lr_0.10": {"learning_rate": 0.10},
    "lr_0.20": {"learning_rate": 0.20},

    # L2 regularization
    "l2_1": {"l2_leaf_reg": 1},
    "l2_5": {"l2_leaf_reg": 5},
    "l2_10": {"l2_leaf_reg": 10},
    "l2_30": {"l2_leaf_reg": 30},

    # Early stopping patience
    "es_25": {"early_stopping_rounds": 25},
    "es_100": {"early_stopping_rounds": 100},

    # Boosting type
    "ordered": {"boosting_type": "Ordered"},
}


def parse_metrics(output: str) -> dict:
    """Extract metrics from train_tiered.py output."""
    metrics = {}
    # Look for the summary line patterns
    for line in output.split("\n"):
        # R²(log)
        m = re.search(r"R..\(log\)\s*[=:]\s*([-\d.]+)", line)
        if m:
            metrics["r2_log"] = float(m.group(1))
        # R²(native) or R²(mg/L)
        m = re.search(r"R..\((?:native|mg/L)\)\s*[=:]\s*([-\d.]+)", line)
        if m:
            metrics["r2_native"] = float(m.group(1))
        # KGE
        m = re.search(r"KGE(?:\(log\))?\s*[=:]\s*([-\d.]+)", line)
        if m:
            metrics["kge"] = float(m.group(1))
        # Alpha
        m = re.search(r"[Aa]lpha\s*[=:]\s*([-\d.]+)", line)
        if m:
            metrics["alpha"] = float(m.group(1))
        # RMSE
        m = re.search(r"RMSE\s*[=:]\s*([-\d.]+)", line)
        if m:
            metrics["rmse"] = float(m.group(1))
        # Bias
        m = re.search(r"[Bb]ias\s*[=:]\s*([-\d.]+)", line)
        if m:
            metrics["bias"] = float(m.group(1))
        # Trees
        m = re.search(r"[Tt]rees\s*[=:]\s*([\d.]+)", line)
        if m:
            metrics["trees"] = float(m.group(1))
        # MedSiteR2
        m = re.search(r"MedSiteR..\s*[=:]\s*([-\d.]+)", line)
        if m:
            metrics["med_site_r2"] = float(m.group(1))
        # BCF / smearing
        m = re.search(r"(?:BCF|[Ss]mearing)\s*[=:]\s*([-\d.]+)", line)
        if m:
            metrics["bcf"] = float(m.group(1))
    return metrics


def run_experiment(label: str, hp_overrides: dict) -> dict:
    """Run one GKF5 experiment and return metrics."""
    config = {**V11_DEFAULTS, **hp_overrides}

    cmd = [
        str(PYTHON), str(SCRIPT),
        "--param", "ssc",
        "--tier", "C",
        "--cv-mode", "gkf5",
        "--n-jobs", "5",
        "--transform", "boxcox",
        "--boxcox-lambda", "0.2",
        "--skip-ridge",
        "--skip-save-model",
        "--label", f"hp_{label}",
        "--config-json", json.dumps(config),
    ]

    print(f"\n{'='*70}")
    print(f"  Experiment: {label}")
    print(f"  Overrides: {hp_overrides or '(baseline)'}")
    print(f"{'='*70}")

    t0 = time.time()
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        timeout=600,  # 10 min max
    )
    elapsed = time.time() - t0

    # Combine stdout and stderr for metric parsing
    output = result.stdout + "\n" + result.stderr
    metrics = parse_metrics(output)
    metrics["elapsed_sec"] = round(elapsed, 1)
    metrics["returncode"] = result.returncode

    if result.returncode != 0:
        print(f"  FAILED (rc={result.returncode})")
        # Print last 20 lines of stderr for debugging
        for line in result.stderr.strip().split("\n")[-20:]:
            print(f"    {line}")
    else:
        r2l = metrics.get("r2_log", "?")
        r2n = metrics.get("r2_native", "?")
        kge = metrics.get("kge", "?")
        trees = metrics.get("trees", "?")
        print(f"  R2(log)={r2l}  R2(native)={r2n}  KGE={kge}  Trees={trees}  ({elapsed:.0f}s)")

    return metrics


def main():
    print("=" * 70)
    print("  HYPERPARAMETER SENSITIVITY SWEEP — v11 CatBoost")
    print("  GKF5, Box-Cox 0.2, Monotone ON (matching v11 config)")
    print("=" * 70)

    results = {}
    for label, overrides in EXPERIMENTS.items():
        try:
            metrics = run_experiment(label, overrides)
            results[label] = metrics
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT: {label}")
            results[label] = {"error": "timeout"}
        except Exception as e:
            print(f"  ERROR: {label}: {e}")
            results[label] = {"error": str(e)}

    # Print summary table
    print("\n\n" + "=" * 100)
    print("  SENSITIVITY SWEEP RESULTS")
    print("=" * 100)
    header = f"{'Experiment':<20} {'R2(log)':>8} {'R2(nat)':>8} {'KGE':>8} {'Alpha':>8} {'RMSE':>8} {'Bias%':>8} {'Trees':>6} {'BCF':>6} {'Time':>6}"
    print(header)
    print("-" * 100)

    baseline_r2_log = results.get("baseline_v11", {}).get("r2_log")
    baseline_r2_nat = results.get("baseline_v11", {}).get("r2_native")

    for label, m in results.items():
        if "error" in m:
            print(f"{label:<20} {'ERROR':>8}")
            continue

        r2l = m.get("r2_log", "")
        r2n = m.get("r2_native", "")
        kge = m.get("kge", "")
        alpha = m.get("alpha", "")
        rmse = m.get("rmse", "")
        bias = m.get("bias", "")
        trees = m.get("trees", "")
        bcf = m.get("bcf", "")
        t = m.get("elapsed_sec", "")

        # Delta markers
        dl = ""
        dn = ""
        if baseline_r2_log and isinstance(r2l, float) and label != "baseline_v11":
            dl = f" ({r2l - baseline_r2_log:+.3f})"
        if baseline_r2_nat and isinstance(r2n, float) and label != "baseline_v11":
            dn = f" ({r2n - baseline_r2_nat:+.3f})"

        r2l_s = f"{r2l:.3f}" if isinstance(r2l, float) else str(r2l)
        r2n_s = f"{r2n:.3f}" if isinstance(r2n, float) else str(r2n)
        kge_s = f"{kge:.3f}" if isinstance(kge, float) else str(kge)
        alpha_s = f"{alpha:.3f}" if isinstance(alpha, float) else str(alpha)
        rmse_s = f"{rmse:.0f}" if isinstance(rmse, float) else str(rmse)
        bias_s = f"{bias:.1f}" if isinstance(bias, float) else str(bias)
        trees_s = f"{trees:.0f}" if isinstance(trees, float) else str(trees)
        bcf_s = f"{bcf:.3f}" if isinstance(bcf, float) else str(bcf)
        t_s = f"{t:.0f}s" if isinstance(t, float) else str(t)

        print(f"{label:<20} {r2l_s:>8}{dl}  {r2n_s:>8}{dn}  {kge_s:>8}  {alpha_s:>8}  {rmse_s:>8}  {bias_s:>8}  {trees_s:>6}  {bcf_s:>6}  {t_s:>6}")

    # Save results as JSON
    out_path = PROJECT_ROOT / "data" / "results" / "hp_sensitivity_sweep.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
