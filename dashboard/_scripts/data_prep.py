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


def prep():
    DASH_DATA.mkdir(exist_ok=True)

    # --- Per-site metrics ---
    per_site_path = EVAL_DIR / "v10_clean_dualbcf_eval_per_site.parquet"
    if per_site_path.exists():
        shutil.copy(per_site_path, DASH_DATA / "per_site.parquet")
        print(f"  Copied per_site.parquet ({per_site_path.stat().st_size // 1024} KB)")

    # --- Per-reading predictions ---
    per_reading_path = EVAL_DIR / "v10_clean_dualbcf_eval_per_reading.parquet"
    if per_reading_path.exists():
        shutil.copy(per_reading_path, DASH_DATA / "per_reading.parquet")
        print(f"  Copied per_reading.parquet ({per_reading_path.stat().st_size // 1024} KB)")

    # --- Summary JSON ---
    summary_path = EVAL_DIR / "v10_clean_dualbcf_eval_summary.json"
    if summary_path.exists():
        shutil.copy(summary_path, DASH_DATA / "summary.json")
        print("  Copied summary.json")

    # --- bcf_median eval ---
    median_summary = EVAL_DIR / "v10_dualbcf_median_eval_summary.json"
    if median_summary.exists():
        shutil.copy(median_summary, DASH_DATA / "summary_median.json")
        print("  Copied summary_median.json")

    median_per_site = EVAL_DIR / "v10_dualbcf_median_eval_per_site.parquet"
    if median_per_site.exists():
        shutil.copy(median_per_site, DASH_DATA / "per_site_median.parquet")
        print("  Copied per_site_median.parquet")

    median_per_reading = EVAL_DIR / "v10_dualbcf_median_eval_per_reading.parquet"
    if median_per_reading.exists():
        shutil.copy(median_per_reading, DASH_DATA / "per_reading_median.parquet")
        print("  Copied per_reading_median.parquet")

    # --- Disaggregated metrics ---
    diag_dir = EVAL_DIR / "v10_clean_dualbcf_eval_diagnostics"
    if diag_dir.exists():
        for f in diag_dir.iterdir():
            shutil.copy(f, DASH_DATA / f"diag_{f.name}")
        print(f"  Copied diagnostics ({len(list(diag_dir.iterdir()))} files)")

    # --- External validation ---
    ext_dir = EVAL_DIR / "v10_clean_dualbcf_eval_external"
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

    # --- Bootstrap CIs ---
    ci_path = EVAL_DIR / "bootstrap_ci_results.json"
    if ci_path.exists():
        shutil.copy(ci_path, DASH_DATA / "bootstrap_ci.json")
        print("  Copied bootstrap_ci.json")

    # --- Failing sites analysis ---
    failing_path = EVAL_DIR / "failing_sites_analysis.json"
    if failing_path.exists():
        shutil.copy(failing_path, DASH_DATA / "failing_sites.json")
        print("  Copied failing_sites.json")

    print("\nDashboard data prep complete.")
    print(f"Files in {DASH_DATA}:")
    for f in sorted(DASH_DATA.iterdir()):
        size = f.stat().st_size // 1024
        print(f"  {f.name} ({size} KB)")


if __name__ == "__main__":
    print("Preparing dashboard data...")
    prep()
