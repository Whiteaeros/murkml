"""
Prepare data for the murkml dashboard.
Reads eval parquets from data/results/evaluations/ and builds compact
dashboard-ready data in dashboard/dashboard_data/.

Run this before `quarto render`:
    python _scripts/data_prep.py
"""
import json
import shutil
from pathlib import Path

import pandas as pd

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EVAL_DIR = PROJECT_ROOT / "data" / "results" / "evaluations"
DASH_DATA = Path(__file__).resolve().parent.parent / "dashboard_data"

# v11 is the current model
EVAL_PREFIX = "v11_extreme_eval"


def prep():
    DASH_DATA.mkdir(exist_ok=True)

    # --- Per-site metrics ---
    per_site_path = EVAL_DIR / f"{EVAL_PREFIX}_per_site.parquet"
    if per_site_path.exists():
        shutil.copy(per_site_path, DASH_DATA / "per_site.parquet")
        print(f"  Copied per_site.parquet ({per_site_path.stat().st_size // 1024} KB)")

    # --- Per-reading predictions ---
    per_reading_path = EVAL_DIR / f"{EVAL_PREFIX}_per_reading.parquet"
    if per_reading_path.exists():
        shutil.copy(per_reading_path, DASH_DATA / "per_reading.parquet")
        print(f"  Copied per_reading.parquet ({per_reading_path.stat().st_size // 1024} KB)")

    # --- Summary JSON ---
    summary_path = EVAL_DIR / f"{EVAL_PREFIX}_summary.json"
    if summary_path.exists():
        shutil.copy(summary_path, DASH_DATA / "summary.json")
        print("  Copied summary.json")

    # --- Disaggregated metrics ---
    diag_dir = EVAL_DIR / f"{EVAL_PREFIX}_diagnostics"
    if diag_dir.exists():
        for f in diag_dir.iterdir():
            shutil.copy(f, DASH_DATA / f"diag_{f.name}")
        print(f"  Copied diagnostics ({len(list(diag_dir.iterdir()))} files)")

    # --- External validation ---
    ext_dir = EVAL_DIR / f"{EVAL_PREFIX}_external"
    if ext_dir.exists():
        for f in ext_dir.iterdir():
            shutil.copy(f, DASH_DATA / f"ext_{f.name}")
        print(f"  Copied external validation ({len(list(ext_dir.iterdir()))} files)")

    # --- OLS benchmark ---
    ols_dir = EVAL_DIR / "ols_benchmark"
    if ols_dir.exists():
        for f in ols_dir.iterdir():
            shutil.copy(f, DASH_DATA / f"ols_{f.name}")
        print(f"  Copied OLS benchmark ({len(list(ols_dir.iterdir()))} files)")

    # --- Bootstrap CIs (v11) ---
    ci_path = EVAL_DIR / "v11_bootstrap_ci_results.json"
    if ci_path.exists():
        shutil.copy(ci_path, DASH_DATA / "bootstrap_ci.json")
        print("  Copied bootstrap_ci.json (v11)")

    # --- Failing sites analysis ---
    failing_path = EVAL_DIR / "failing_sites_analysis.json"
    if failing_path.exists():
        shutil.copy(failing_path, DASH_DATA / "failing_sites.json")
        print("  Copied failing_sites.json")

    # --- Empirical conformal intervals ---
    conformal_dir = EVAL_DIR / "empirical_conformal"
    if conformal_dir.exists():
        for f in conformal_dir.iterdir():
            shutil.copy(f, DASH_DATA / f"conformal_{f.name}")
        print(f"  Copied empirical conformal ({len(list(conformal_dir.iterdir()))} files)")

    # --- Sediment load comparison (v11 vs OLS vs USGS 80155) ---
    load_dir = EVAL_DIR / "load_comparison"
    if load_dir.exists():
        for f in load_dir.iterdir():
            shutil.copy(f, DASH_DATA / f"load_{f.name}")
        print(f"  Copied load comparison ({len(list(load_dir.iterdir()))} files)")

    print("\nDashboard data prep complete.")
    print(f"Files in {DASH_DATA}:")
    for f in sorted(DASH_DATA.iterdir()):
        size = f.stat().st_size // 1024
        print(f"  {f.name} ({size} KB)")


if __name__ == "__main__":
    print("Preparing dashboard data...")
    prep()
