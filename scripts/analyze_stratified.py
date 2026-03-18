"""Standalone stratified analysis of LOGO CV predictions.

Reads saved per-sample predictions from train_tiered.py and computes:
- Flow-stratified metrics (per-site discharge percentile bins)
- Threshold fractions with bootstrap CIs
- Native-space R² and RMSE (mg/L)

Can re-run without retraining.

Usage:
    python scripts/analyze_stratified.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from murkml.evaluate.metrics import (
    native_space_metrics,
    stratified_metrics_by_flow,
    threshold_fractions,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

RESULTS_DIR = PROJECT_ROOT / "data" / "results"


def analyze_predictions(param: str, tier: str, predictions_path: Path, folds_path: Path):
    """Run stratified analysis for one param/tier combination."""
    logger.info(f"\n{'='*60}")
    logger.info(f"{param} / {tier}")
    logger.info(f"{'='*60}")

    preds = pd.read_parquet(predictions_path)
    folds = pd.read_parquet(folds_path)

    logger.info(f"  Samples: {len(preds)}, Sites: {preds['site_id'].nunique()}")

    # --- Native-space metrics ---
    nat = native_space_metrics(preds["y_true_log"].values, preds["y_pred_log"].values)
    logger.info(f"  Native-space: R²={nat['r2_native']:.3f}, RMSE={nat['rmse_native_mgL']:.1f} mg/L")

    # --- Flow-stratified metrics ---
    n_valid_discharge = preds["discharge_instant"].notna().sum()
    logger.info(f"  Discharge available: {n_valid_discharge}/{len(preds)} samples")

    flow_results = {}
    if n_valid_discharge > 50:
        flow_results = stratified_metrics_by_flow(
            preds["y_true_log"].values,
            preds["y_pred_log"].values,
            preds["discharge_instant"].values,
            preds["site_id"].values,
        )
        logger.info(f"  Flow-stratified (per-site percentiles):")
        for bin_label, metrics in sorted(flow_results.items()):
            logger.info(f"    {bin_label:10s}: R²={metrics['r2']:.3f}  KGE={metrics['kge']:.3f}  "
                       f"RMSE={metrics['rmse']:.3f}  n={metrics['n_samples']}")
    else:
        logger.warning(f"  Insufficient discharge data for flow stratification")

    # --- Threshold fractions with bootstrap CIs ---
    r2_values = folds["r2_log"].values
    fracs = threshold_fractions(r2_values, {
        "r2_gt_0.5": 0.5,
        "r2_gt_0": 0.0,
        "r2_lt_neg1": -1.0,
    })
    logger.info(f"  Threshold fractions (with 95% bootstrap CI):")
    for name, result in fracs.items():
        logger.info(f"    {name:15s}: {result['fraction']:.1%} [{result['ci_lower']:.1%}, {result['ci_upper']:.1%}]")

    # --- KGE decomposition summary ---
    if "kge_r" in folds.columns:
        logger.info(f"  KGE decomposition (medians across {len(folds)} folds):")
        logger.info(f"    r (correlation):  {folds['kge_r'].median():.3f}")
        logger.info(f"    α (variability):  {folds['kge_alpha'].median():.3f}")
        logger.info(f"    β (bias):         {folds['kge_beta'].median():.3f}")

    # --- Per-site flow bin sample counts ---
    if n_valid_discharge > 50:
        valid = preds.dropna(subset=["discharge_instant"])
        site_counts = {}
        for site_id, grp in valid.groupby("site_id"):
            q = grp["discharge_instant"].values
            q50 = np.quantile(q, 0.5)
            q90 = np.quantile(q, 0.9)
            site_counts[site_id] = {
                "n_Q<50": int((q < q50).sum()),
                "n_Q50-90": int(((q >= q50) & (q < q90)).sum()),
                "n_Q>90": int((q >= q90).sum()),
            }
        counts_df = pd.DataFrame(site_counts).T
        low_storm = counts_df[counts_df["n_Q>90"] < 3]
        if len(low_storm) > 0:
            logger.info(f"  Sites with <3 samples in Q>90 bin: {len(low_storm)}/{len(counts_df)}")

    return {
        "param": param,
        "tier": tier,
        "n_samples": len(preds),
        "n_sites": preds["site_id"].nunique(),
        **nat,
        **{f"flow_{k}_{m}": v for k, metrics in flow_results.items() for m, v in metrics.items()},
        **{f"frac_{k}": v["fraction"] for k, v in fracs.items()},
        "kge_r_median": folds["kge_r"].median() if "kge_r" in folds.columns else np.nan,
        "kge_alpha_median": folds["kge_alpha"].median() if "kge_alpha" in folds.columns else np.nan,
        "kge_beta_median": folds["kge_beta"].median() if "kge_beta" in folds.columns else np.nan,
    }


def main():
    # Find all saved prediction files
    pred_files = sorted(RESULTS_DIR.glob("logo_predictions_*.parquet"))
    if not pred_files:
        logger.error("No prediction files found! Run train_tiered.py first.")
        return

    all_results = []
    for pred_path in pred_files:
        # Parse param and tier from filename: logo_predictions_{param}_{tier}.parquet
        stem = pred_path.stem.replace("logo_predictions_", "")
        # Find matching folds file
        folds_path = RESULTS_DIR / f"logo_folds_{stem}.parquet"
        if not folds_path.exists():
            logger.warning(f"No folds file for {stem}, skipping")
            continue

        # Parse param (first token) and tier (rest)
        parts = stem.split("_", 1)
        if len(parts) == 2:
            param, tier = parts
        else:
            param, tier = stem, "unknown"

        try:
            result = analyze_predictions(param, tier, pred_path, folds_path)
            all_results.append(result)
        except Exception as e:
            logger.error(f"Error analyzing {stem}: {e}")

    if all_results:
        out_df = pd.DataFrame(all_results)
        out_path = RESULTS_DIR / "stratified_metrics.parquet"
        out_df.to_parquet(out_path, index=False)
        logger.info(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
