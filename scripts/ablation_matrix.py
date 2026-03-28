"""Ablation matrix runner for murkml.

Runs a systematic series of experiments varying features and hyperparameters,
collecting results into a single comparison table.

Also validates data availability for other parameters (nitrate, orthophosphate, etc.)
without training models for them.

Usage:
    python scripts/ablation_matrix.py
    python scripts/ablation_matrix.py --phase feature  # only feature experiments
    python scripts/ablation_matrix.py --phase hp       # only hyperparameter sweep
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

DATA_DIR = PROJECT_ROOT / "data"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# =====================================================================
# Feature group definitions (from Dr. Dalton hydrology review)
# =====================================================================

FEATURE_GROUPS = {
    "F1_discharge": [
        "discharge_instant", "rising_limb", "Q_7day_mean", "Q_30day_mean",
        "discharge_slope_2hr",
    ],
    "F2_do_ph_temp": [
        "do_instant", "DO_sat_departure", "ph_instant", "temp_instant",
        "SC_turb_interaction",
    ],
    "F3_nutrients": [
        "nitrogen_surplus", "fertilizer_rate", "manure_rate",
        "rock_nitrogen", "bio_n_fixation",
    ],
    "F4_wastewater": [
        "npdes_density", "wwtp_all_density", "wwtp_major_density",
        "wwtp_minor_density",
    ],
    "F5_sparse_geology": [
        "pct_carbonate_resid", "pct_glacial_till_loam", "pct_glacial_till_coarse",
        "pct_coastal_coarse", "pct_eolian_coarse", "pct_saline_lake",
        "pct_glacial_till_clay", "pct_alkaline_intrusive", "pct_extrusive_volcanic",
        "pct_glacial_lake_fine", "pct_eolian_fine",
    ],
    "F6_redundant_geochem": [
        "geo_na2o", "geo_sio2", "geo_al2o3", "geo_mgo", "geo_cao", "geo_fe2o3",
    ],
    "F7_redundant_turb": [
        "turbidity_min_1hr", "turbidity_range_1hr",
    ],
    "F8_weak_weather": [
        "precip_7d", "precip_30d", "days_since_rain", "temp_at_sample",
    ],
    "F9_categoricals": [
        "geol_class", "huc2",
    ],
}

# F10 = all of the above combined
FEATURE_GROUPS["F10_all_suspect"] = []
for group in ["F1_discharge", "F2_do_ph_temp", "F3_nutrients", "F4_wastewater",
              "F5_sparse_geology", "F6_redundant_geochem", "F7_redundant_turb",
              "F8_weak_weather", "F9_categoricals"]:
    FEATURE_GROUPS["F10_all_suspect"].extend(FEATURE_GROUPS[group])


# =====================================================================
# Hyperparameter experiments
# =====================================================================

HP_EXPERIMENTS = {
    "H1_depth4": {"depth": 4},
    "H2_depth8": {"depth": 8},
    "H3_lr001_iter2000": {"learning_rate": 0.01, "iterations": 2000},
    "H4_lr01": {"learning_rate": 0.1},
    "H5_es100": {"early_stopping_rounds": 100},
    "H6_l2reg1": {"l2_leaf_reg": 1},
    "H7_l2reg10": {"l2_leaf_reg": 10},
    "H8_plain": {"boosting_type": "Plain"},
}


def run_experiment(label: str, drop_features: list[str] | None = None,
                   config_json: dict | None = None, feature_set: str = "full",
                   no_monotone: bool = False, timeout: int = 10800,
                   ablation_fast: bool = True) -> dict | None:
    """Run a single training experiment via subprocess.

    ablation_fast=True (default): GroupKFold(5), Plain boosting, no monotone,
    skip Ridge/SHAP/model save. ~5-8 min per experiment instead of ~130 min.
    """
    # Build effective config (merge ablation defaults with experiment overrides)
    effective_config = {}
    if ablation_fast:
        effective_config["boosting_type"] = "Plain"
    if config_json:
        effective_config.update(config_json)  # experiment overrides win

    cmd = [
        str(PROJECT_ROOT / ".venv" / "Scripts" / "python"),
        str(PROJECT_ROOT / "scripts" / "train_tiered.py"),
        "--param", "ssc",
        "--tier", "C",
        "--n-jobs", "8",
        "--label", label,
        "--feature-set", feature_set,
    ]

    if drop_features:
        cmd.extend(["--drop-features", ",".join(drop_features)])
    if effective_config:
        cmd.extend(["--config-json", json.dumps(effective_config)])
    if no_monotone or ablation_fast:
        cmd.append("--no-monotone")
    if ablation_fast:
        cmd.extend(["--cv-mode", "gkf5"])
        cmd.append("--skip-ridge")
        cmd.append("--skip-save-model")

    logger.info(f"\n{'='*60}")
    logger.info(f"EXPERIMENT: {label}")
    logger.info(f"{'='*60}")
    logger.info(f"Command: {' '.join(cmd[-8:])}")  # last 8 args for brevity

    start = time.time()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=str(PROJECT_ROOT),
        )
        elapsed = time.time() - start
        logger.info(f"Completed in {elapsed/60:.1f} min (exit code {result.returncode})")

        if result.returncode != 0:
            logger.error(f"FAILED: {result.stderr[-500:]}")
            return None

        # Parse key metrics from output (logging goes to stderr, not stdout)
        metrics = parse_train_output(result.stderr, label)
        metrics["elapsed_min"] = round(elapsed / 60, 1)
        return metrics

    except subprocess.TimeoutExpired:
        logger.error(f"TIMEOUT after {timeout/3600:.1f} hours — skipping")
        return None
    except Exception as e:
        logger.error(f"ERROR: {e}")
        return None


def parse_train_output(output: str, label: str) -> dict:
    """Extract key metrics from train_tiered.py stdout."""
    metrics = {"label": label}

    for line in output.split("\n"):
        if "Trees per fold:" in line:
            # Trees per fold: median=300, min=98, max=500
            parts = line.split("median=")[1] if "median=" in line else ""
            if parts:
                metrics["median_trees"] = int(parts.split(",")[0])
                metrics["min_trees"] = int(parts.split("min=")[1].split(",")[0])
                metrics["max_trees"] = int(parts.split("max=")[1].strip())

        if "R²(log)=" in line or "R\u00b2(log)=" in line:
            # Parse the main results line
            try:
                for kv in line.split("|"):
                    for part in kv.split():
                        if "R²(log)=" in part or "R\u00b2(log)=" in part:
                            val = part.split("=")[1]
                            metrics["r2_log"] = float(val)
                        elif "KGE(log)=" in part:
                            metrics["kge_log"] = float(part.split("=")[1])
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

        if "features" in line and "numeric" in line:
            # "97 numeric + 2 categorical features"
            try:
                parts = line.split("samples, ")[1] if "samples, " in line else ""
                if "numeric" in parts:
                    n_num = int(parts.split(" numeric")[0])
                    n_cat = int(parts.split("+ ")[1].split(" cat")[0])
                    metrics["n_features"] = n_num + n_cat
            except (ValueError, IndexError):
                pass

        if "Feature set" in line and "→" in line:
            # Feature set 'pruned': 99 → 63 features
            try:
                metrics["n_features"] = int(line.split("→ ")[1].split(" ")[0])
            except (ValueError, IndexError):
                pass

        if "Dropped" in line and "features:" in line:
            try:
                metrics["n_dropped"] = int(line.split("Dropped ")[1].split(" ")[0])
            except (ValueError, IndexError):
                pass

    return metrics


def validate_other_parameters():
    """Check data availability for non-SSC parameters without training."""
    logger.info("\n" + "="*60)
    logger.info("PARAMETER DATA VALIDATION (no training)")
    logger.info("="*60)

    # Check what paired datasets exist
    processed_dir = DATA_DIR / "processed"
    disc_dir = DATA_DIR / "discrete"

    params_to_check = {
        "total_phosphorus": "total_phosphorus_paired.parquet",
        "nitrate_nitrite": "nitrate_nitrite_paired.parquet",
        "orthophosphate": "orthophosphate_paired.parquet",
    }

    for param_name, filename in params_to_check.items():
        path = processed_dir / filename
        if path.exists():
            df = pd.read_parquet(path)
            logger.info(f"\n{param_name}: {len(df)} samples, {df['site_id'].nunique()} sites")
            logger.info(f"  Target range: {df['lab_value'].min():.3f} - {df['lab_value'].max():.3f}")
            logger.info(f"  Median samples/site: {df.groupby('site_id').size().median():.0f}")
            # Sites with enough data for LOGO CV (>=5 samples)
            site_counts = df.groupby("site_id").size()
            n_viable = (site_counts >= 5).sum()
            logger.info(f"  Sites with >=5 samples: {n_viable}")
            n_viable_10 = (site_counts >= 10).sum()
            logger.info(f"  Sites with >=10 samples: {n_viable_10}")
        else:
            logger.info(f"\n{param_name}: NO paired dataset found at {path}")
            # Check if discrete data exists
            if disc_dir.exists():
                disc_files = list(disc_dir.glob(f"*_{param_name.split('_')[0]}*.parquet"))
                if not disc_files:
                    disc_files = list(disc_dir.glob("*.parquet"))
                logger.info(f"  Discrete files in {disc_dir}: {len(disc_files)}")

    # Also check SSC for reference
    ssc_path = processed_dir / "turbidity_ssc_paired.parquet"
    if ssc_path.exists():
        df = pd.read_parquet(ssc_path)
        logger.info(f"\nSSC (reference): {len(df)} samples, {df['site_id'].nunique()} sites")
        site_counts = df.groupby("site_id").size()
        logger.info(f"  Sites >=5 samples: {(site_counts >= 5).sum()}")
        logger.info(f"  Sites >=10 samples: {(site_counts >= 10).sum()}")
        if "log_turbidity_instant" in df.columns:
            logger.info(f"  log_turbidity_instant: present ✓")
        else:
            logger.info(f"  log_turbidity_instant: MISSING")


def main():
    parser = argparse.ArgumentParser(description="Run ablation matrix")
    parser.add_argument("--phase", type=str, default="all",
                        choices=["all", "feature", "hp", "validate", "single"],
                        help="Which phase to run (single = test every feature individually)")
    parser.add_argument("--skip", type=int, default=0,
                        help="Skip the first N experiments (for resuming)")
    parser.add_argument("--full", action="store_true",
                        help="Use full LOGO CV (no speed shortcuts). Default is fast GKF5 mode.")
    args = parser.parse_args()
    use_fast = not args.full

    results_path = DATA_DIR / "results" / "ablation_feature_groups.parquet"

    # Load existing results if resuming
    results = []
    if args.skip > 0 and results_path.exists():
        existing = pd.read_parquet(results_path)
        results = existing.to_dict("records")
        logger.info(f"Loaded {len(results)} existing results from {results_path}")

    def save_results(results_list, path):
        """Save results after every experiment — crash-safe."""
        if results_list:
            df = pd.DataFrame(results_list)
            df.to_parquet(path, index=False)
            logger.info(f"  → Saved {len(results_list)} results to {path.name}")

    # Always validate other parameters first
    validate_other_parameters()

    if args.phase in ("all", "feature"):
        logger.info("\n" + "#"*60)
        logger.info("# PHASE 1: FEATURE GROUP REMOVAL")
        logger.info("#"*60)

        # Build experiment list
        experiments = [("baseline_101feat", None)]
        for group_name, features in FEATURE_GROUPS.items():
            experiments.append((f"drop_{group_name}", features))

        # Skip already-completed experiments
        experiments = experiments[args.skip:]
        if args.skip > 0:
            logger.info(f"Skipping first {args.skip} experiments (already done)")

        baseline = None

        for label, drop_feats in experiments:
            r = run_experiment(label, drop_features=drop_feats, ablation_fast=use_fast)
            if r:
                results.append(r)
                save_results(results, results_path)  # Save after EVERY experiment
                if label.startswith("baseline"):
                    baseline = r

        # Print comparison table
        if results:
            logger.info(f"\nSaved {len(results)} feature group results")

            # Print comparison table
            logger.info("\n" + "="*80)
            logger.info("FEATURE GROUP ABLATION RESULTS")
            logger.info("="*80)
            for r in results:
                r2 = r.get("r2_log", float("nan"))
                trees = r.get("median_trees", "?")
                nfeat = r.get("n_features", "?")
                elapsed = r.get("elapsed_min", "?")
                delta = r2 - baseline.get("r2_log", 0) if baseline and r.get("label") != "baseline_99feat" else 0
                sign = "+" if delta >= 0 else ""
                logger.info(
                    f"  {r['label']:30s}  R²={r2:.4f} ({sign}{delta:.4f})  "
                    f"trees={trees}  feat={nfeat}  {elapsed}min"
                )

    if args.phase in ("all", "hp"):
        logger.info("\n" + "#"*60)
        logger.info("# PHASE 2: HYPERPARAMETER SWEEP")
        logger.info("#"*60)

        # Determine best feature set from Phase 1
        # For now, use full features + whatever drops helped
        # (Will be refined after Phase 1 analysis)

        hp_results = []

        # HP baseline (default params, for comparison within this phase)
        hp_base = run_experiment("hp_baseline", ablation_fast=use_fast)
        if hp_base:
            hp_results.append(hp_base)

        for hp_name, hp_config in HP_EXPERIMENTS.items():
            r = run_experiment(
                f"hp_{hp_name}",
                config_json=hp_config,
                ablation_fast=use_fast,
            )
            if r:
                hp_results.append(r)

        results.extend(hp_results)

        # Save HP results
        if hp_results:
            df = pd.DataFrame(hp_results)
            df.to_parquet(DATA_DIR / "results" / "ablation_hp_sweep.parquet", index=False)
            logger.info(f"\nSaved {len(hp_results)} HP sweep results")

            logger.info("\n" + "="*80)
            logger.info("HYPERPARAMETER SWEEP RESULTS")
            logger.info("="*80)
            for r in hp_results:
                r2 = r.get("r2_log", float("nan"))
                trees = r.get("median_trees", "?")
                elapsed = r.get("elapsed_min", "?")
                delta = r2 - hp_base.get("r2_log", 0) if hp_base and r.get("label") != "hp_baseline" else 0
                sign = "+" if delta >= 0 else ""
                logger.info(
                    f"  {r['label']:30s}  R²={r2:.4f} ({sign}{delta:.4f})  "
                    f"trees={trees}  {elapsed}min"
                )

    if args.phase in ("all", "single"):
        logger.info("\n" + "#"*60)
        logger.info("# PHASE 3: SINGLE-FEATURE ABLATION (drop each feature individually)")
        logger.info("#"*60)

        single_results_path = DATA_DIR / "results" / "ablation_single_features.parquet"
        single_results = []

        # Get feature list from a quick baseline run's output
        # We need to know all available feature names
        import subprocess as _sp
        _r = _sp.run(
            [str(PROJECT_ROOT / ".venv" / "Scripts" / "python"), "-c",
             "import pandas as pd; from pathlib import Path; "
             "from murkml.data.attributes import build_feature_tiers, load_streamcat_attrs; "
             "d=Path('data'); a=pd.read_parquet(d/'processed'/'turbidity_ssc_paired.parquet'); "
             "b=pd.read_parquet(d/'site_attributes.parquet'); "
             "w=load_streamcat_attrs(d); "
             "t=build_feature_tiers(a,b,w); "
             "tc=t['C_sensor_basic_watershed']; "
             "print(','.join(tc['feature_cols']))"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        all_features = _r.stdout.strip().split(",") if _r.returncode == 0 else []

        if all_features:
            logger.info(f"Testing {len(all_features)} features individually")

            # Baseline first
            base = run_experiment("single_baseline", ablation_fast=use_fast)
            if base:
                single_results.append(base)
                save_results(single_results, single_results_path)

            for feat in all_features:
                feat = feat.strip()
                if not feat:
                    continue
                r = run_experiment(
                    f"drop_{feat}",
                    drop_features=[feat],
                    ablation_fast=use_fast,
                )
                if r:
                    r["dropped_feature"] = feat
                    single_results.append(r)
                    save_results(single_results, single_results_path)

            # Print ranked results
            if single_results and len(single_results) > 1:
                sdf = pd.DataFrame(single_results)
                baseline_r2 = sdf[sdf["label"] == "single_baseline"]["r2_log"].iloc[0]
                sdf["delta"] = sdf["r2_log"] - baseline_r2

                logger.info(f"\n{'='*80}")
                logger.info("SINGLE-FEATURE ABLATION — RANKED BY IMPACT")
                logger.info(f"Baseline R²={baseline_r2:.4f}")
                logger.info(f"{'='*80}")

                ranked = sdf[sdf["label"] != "single_baseline"].sort_values("delta")
                for _, r in ranked.iterrows():
                    delta = r["delta"]
                    feat = r.get("dropped_feature", r["label"])
                    sign = "+" if delta >= 0 else ""
                    verdict = "HARMFUL" if delta > 0.001 else "HELPFUL" if delta < -0.001 else "neutral"
                    logger.info(f"  {feat:35s}  {sign}{delta:.4f}  [{verdict}]")
        else:
            logger.error("Could not get feature list")

    # Save all results
    if results:
        all_df = pd.DataFrame(results)
        all_df.to_parquet(DATA_DIR / "results" / "ablation_matrix.parquet", index=False)
        logger.info(f"\n{'='*60}")
        logger.info(f"ALL RESULTS saved to ablation_matrix.parquet ({len(results)} experiments)")
        logger.info(f"{'='*60}")

        # Find best
        if "r2_log" in all_df.columns:
            best = all_df.loc[all_df["r2_log"].idxmax()]
            logger.info(f"\nBEST EXPERIMENT: {best['label']}")
            logger.info(f"  R²(log)={best['r2_log']:.4f}  trees={best.get('median_trees', '?')}")


if __name__ == "__main__":
    main()
