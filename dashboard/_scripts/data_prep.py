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

# v12 is the current model (88 features, refactored pipeline)
EVAL_PREFIX = "v12"


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

    # --- SHAP values and feature importance ---
    # Try v12 SHAP first, fall back to v11
    shap_vals = EVAL_DIR.parent / "shap_values_ssc_C_sensor_basic_watershed_v12.parquet"
    shap_imp = EVAL_DIR.parent / "shap_importance_ssc_C_sensor_basic_watershed_v12.parquet"
    if not shap_vals.exists():
        shap_vals = EVAL_DIR.parent / "shap_values_ssc_C_sensor_basic_watershed_v11.parquet"
    if not shap_imp.exists():
        shap_imp = EVAL_DIR.parent / "shap_importance_ssc_C_sensor_basic_watershed_v11.parquet"
    if shap_vals.exists():
        shutil.copy(shap_vals, DASH_DATA / "shap_values.parquet")
        print(f"  Copied shap_values.parquet ({shap_vals.stat().st_size // 1024} KB)")
    if shap_imp.exists():
        shutil.copy(shap_imp, DASH_DATA / "shap_importance.parquet")
        print(f"  Copied shap_importance.parquet ({shap_imp.stat().st_size // 1024} KB)")

    # Generate CatBoost built-in feature importance as JSON
    model_dir = PROJECT_ROOT / "data" / "results" / "models"
    model_cbm = model_dir / "ssc_C_sensor_basic_watershed_v12.cbm"
    model_meta = model_dir / "ssc_C_sensor_basic_watershed_v12_meta.json"
    if model_cbm.exists() and model_meta.exists():
        try:
            from catboost import CatBoostRegressor
            import numpy as np
            m = CatBoostRegressor()
            m.load_model(str(model_cbm))
            with open(model_meta) as f:
                meta = json.load(f)
            fi = m.get_feature_importance()
            cols = meta["feature_cols"]
            order = np.argsort(fi)[::-1]
            importance = [{"feature": cols[i], "importance": float(fi[i])} for i in order]
            with open(DASH_DATA / "feature_importance.json", "w") as f:
                json.dump(importance, f, indent=2)
            print(f"  Generated feature_importance.json ({len(importance)} features)")
        except Exception as e:
            print(f"  Warning: Could not generate feature importance: {e}")

    # --- Deep SHAP (full holdout, interactions, per-site) ---
    shap_deep_dir = PROJECT_ROOT / "data" / "results" / "shap_deep"
    latest_marker = shap_deep_dir / "LATEST"
    if latest_marker.exists():
        latest_ts = latest_marker.read_text().strip()
        deep_dir = shap_deep_dir / latest_ts
        if deep_dir.exists():
            for f in deep_dir.iterdir():
                if f.suffix in (".parquet", ".json", ".npy"):
                    shutil.copy(f, DASH_DATA / f"deep_{f.name}")
            print(f"  Copied deep SHAP ({latest_ts})")

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
