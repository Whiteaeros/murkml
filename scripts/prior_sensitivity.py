"""
Bayesian prior sensitivity grid for WRR Appendix.
Varies k and df independently, records N=10 random MedSiteR² for each.
"""
import subprocess
import json
import re
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
PYTHON = PROJECT / ".venv" / "Scripts" / "python"
MODEL = PROJECT / "data/results/models/ssc_C_sensor_basic_watershed_v11_extreme_expanded.cbm"
META = PROJECT / "data/results/models/ssc_C_sensor_basic_watershed_v11_extreme_expanded_meta.json"

GRID = [
    (10, 2), (10, 4), (10, 8),
    (15, 2), (15, 4), (15, 8),
    (20, 2), (20, 4), (20, 8),
]

results = {}
for k, df in GRID:
    label = f"v11_sens_k{k}_df{df}"
    cmd = [
        str(PYTHON), str(PROJECT / "scripts" / "evaluate_model.py"),
        "--model", str(MODEL),
        "--meta", str(META),
        "--label", label,
        "--adaptation", "bayesian",
        "--k", str(k),
        "--df", str(df),
        "--n-trials", "50",
        "--seed", "42",
        "--bcf-mode", "median",
    ]
    print(f"\n{'='*60}")
    print(f"  k={k}, df={df} (label: {label})")
    print(f"{'='*60}")
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT), timeout=1200)
    elapsed = time.time() - t0

    # Parse MedSiteR2 at N=10 random from the summary JSON
    summary_path = PROJECT / "data/results/evaluations" / f"{label}_summary.json"
    if summary_path.exists():
        with open(summary_path) as f:
            s = json.load(f)
        curves = s.get("adaptation_curves", {}).get("random", {})
        n10 = curves.get("10", {})
        med_r2 = n10.get("median_site_r2", "?")
        results[(k, df)] = {"med_site_r2_n10": med_r2, "elapsed": round(elapsed)}
        print(f"  N=10 random MedSiteR2 = {med_r2}  ({elapsed:.0f}s)")
    else:
        print(f"  FAILED — no summary JSON")
        # Check stderr
        for line in result.stderr.strip().split("\n")[-10:]:
            print(f"    {line}")
        results[(k, df)] = {"error": "no output", "elapsed": round(elapsed)}

# Print summary table
print(f"\n\n{'='*60}")
print("  PRIOR SENSITIVITY GRID")
print(f"{'='*60}")
print(f"{'k':>4} {'df':>4} {'MedSiteR2 (N=10 random)':>25} {'Time':>8}")
print("-" * 50)
for (k, df), v in sorted(results.items()):
    r2 = v.get("med_site_r2_n10", "ERR")
    t = v.get("elapsed", "?")
    r2_s = f"{r2:.4f}" if isinstance(r2, float) else str(r2)
    print(f"{k:>4} {df:>4} {r2_s:>25} {t:>7}s")

# Save
out = PROJECT / "data/results/prior_sensitivity_grid.json"
with open(out, "w") as f:
    json.dump({f"k{k}_df{df}": v for (k, df), v in results.items()}, f, indent=2)
print(f"\nSaved to {out}")
