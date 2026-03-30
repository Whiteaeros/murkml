#!/usr/bin/env python
"""Phase 4: Diagnostic Validation & Stress Testing.

Runs disaggregated metrics and physics-based validation on holdout predictions.
Produces a comprehensive diagnostic report.

Usage:
    python scripts/phase4_diagnostics.py --predictions data/results/evaluations/v4_bayesian_per_reading.parquet
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(y_true, y_pred):
    """Compute R², RMSE, MAPE, within-2x for a group."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    valid = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true, y_pred = y_true[valid], y_pred[valid]
    n = len(y_true)
    if n < 2:
        return {"n": n, "r2": np.nan, "rmse": np.nan, "mape_pct": np.nan,
                "within_2x_pct": np.nan, "mean_true": np.nan, "mean_pred": np.nan,
                "median_abs_error": np.nan, "bias_pct": np.nan}

    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 1e-10 else np.nan
    rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))

    # MAPE on nonzero
    nonzero = y_true > 0
    if nonzero.sum() > 0:
        pct_err = np.abs(y_true[nonzero] - y_pred[nonzero]) / y_true[nonzero] * 100
        mape = float(np.median(pct_err))
    else:
        mape = np.nan

    # Within 2x
    if nonzero.sum() > 0:
        ratio = y_pred[nonzero] / y_true[nonzero]
        within_2x = float(np.mean((ratio >= 0.5) & (ratio <= 2.0)) * 100)
    else:
        within_2x = np.nan

    bias_pct = float((np.mean(y_pred) - np.mean(y_true)) / np.mean(y_true) * 100) if np.mean(y_true) > 0 else np.nan

    return {
        "n": n,
        "r2": float(r2),
        "rmse": float(rmse),
        "mape_pct": float(mape),
        "within_2x_pct": float(within_2x),
        "mean_true": float(np.mean(y_true)),
        "mean_pred": float(np.mean(y_pred)),
        "median_abs_error": float(np.median(np.abs(y_true - y_pred))),
        "bias_pct": float(bias_pct),
    }


# ---------------------------------------------------------------------------
# 4.1 Disaggregated Metrics
# ---------------------------------------------------------------------------

def disaggregate_by(df, group_col, y_true_col="y_true_native", y_pred_col="y_pred_native"):
    """Compute metrics for each group in group_col."""
    results = []
    for group, gdf in df.groupby(group_col):
        m = compute_metrics(gdf[y_true_col], gdf[y_pred_col])
        m["group"] = str(group)
        m["dimension"] = group_col
        results.append(m)
    return pd.DataFrame(results)


def run_disaggregated_metrics(df):
    """Run all disaggregation dimensions."""
    all_results = []

    # Overall
    overall = compute_metrics(df["y_true_native"], df["y_pred_native"])
    overall["group"] = "ALL"
    overall["dimension"] = "overall"
    all_results.append(pd.DataFrame([overall]))

    # By collection method
    if "collection_method" in df.columns:
        all_results.append(disaggregate_by(df, "collection_method"))

    # By HUC2 region
    if "huc2" in df.columns:
        all_results.append(disaggregate_by(df, "huc2"))

    # By SSC variability (per-site std quartile)
    site_stats = df.groupby("site_id")["y_true_native"].agg(["std", "count"])
    site_stats["ssc_var_tier"] = pd.qcut(site_stats["std"], 4, labels=["Q1_low", "Q2_med", "Q3_high", "Q4_extreme"])
    df = df.merge(site_stats[["ssc_var_tier"]], left_on="site_id", right_index=True, how="left")
    all_results.append(disaggregate_by(df, "ssc_var_tier"))

    # By sample count per site
    site_counts = df.groupby("site_id").size().rename("site_n")
    bins = [0, 10, 20, 50, 200, 99999]
    labels = ["1-10", "11-20", "21-50", "51-200", "200+"]
    site_counts_binned = pd.cut(site_counts, bins=bins, labels=labels).rename("sample_count_tier")
    df = df.merge(site_counts_binned, left_on="site_id", right_index=True, how="left")
    all_results.append(disaggregate_by(df, "sample_count_tier"))

    # By sensor family
    if "sensor_family" in df.columns:
        all_results.append(disaggregate_by(df, "sensor_family"))

    # By SGMC geology (if available)
    if "dominant_lithology" in df.columns:
        all_results.append(disaggregate_by(df, "dominant_lithology"))

    # By turbidity level
    df["turb_tier"] = pd.cut(df["turbidity_instant"],
                              bins=[0, 10, 50, 200, 1000, 999999],
                              labels=["<10 FNU", "10-50", "50-200", "200-1000", ">1000"])
    all_results.append(disaggregate_by(df, "turb_tier"))

    # By SSC level
    df["ssc_tier"] = pd.cut(df["y_true_native"],
                             bins=[0, 50, 500, 5000, 999999],
                             labels=["Low <50", "Med 50-500", "High 500-5K", "Extreme >5K"])
    all_results.append(disaggregate_by(df, "ssc_tier"))

    return pd.concat(all_results, ignore_index=True)


# ---------------------------------------------------------------------------
# 4.2 Physics-Based Phenomenon Validation
# ---------------------------------------------------------------------------

def validate_first_flush(df):
    """Check if model correctly predicts elevated SSC during first flush events."""
    results = {}

    if "precip_30d" not in df.columns or "flush_intensity" not in df.columns:
        results["status"] = "SKIPPED — missing precip_30d or flush_intensity"
        return results

    # First flush: dry antecedent (low precip_30d) + storm (high flush_intensity)
    p30_thresh = df["precip_30d"].quantile(0.25)  # driest 25%
    flush_thresh = df["flush_intensity"].quantile(0.75)  # highest 25% intensity

    first_flush = df[(df["precip_30d"] <= p30_thresh) & (df["flush_intensity"] >= flush_thresh)]
    not_flush = df[~((df["precip_30d"] <= p30_thresh) & (df["flush_intensity"] >= flush_thresh))]

    results["n_first_flush"] = len(first_flush)
    results["n_not_flush"] = len(not_flush)

    if len(first_flush) < 10:
        results["status"] = f"SKIPPED — only {len(first_flush)} first flush samples"
        return results

    # Expected: first flush has higher SSC/turbidity ratio
    ff_ratio = (first_flush["y_true_native"] / first_flush["turbidity_instant"].clip(lower=1)).median()
    nf_ratio = (not_flush["y_true_native"] / not_flush["turbidity_instant"].clip(lower=1)).median()
    results["ssc_turb_ratio_flush"] = float(ff_ratio)
    results["ssc_turb_ratio_normal"] = float(nf_ratio)
    results["ratio_elevation"] = float(ff_ratio / nf_ratio) if nf_ratio > 0 else np.nan

    # Model accuracy on first flush vs normal
    results["metrics_first_flush"] = compute_metrics(first_flush["y_true_native"], first_flush["y_pred_native"])
    results["metrics_normal"] = compute_metrics(not_flush["y_true_native"], not_flush["y_pred_native"])

    # Does model underpredict first flush? (systematic bias)
    ff_bias = (first_flush["y_pred_native"] - first_flush["y_true_native"]).median()
    results["first_flush_median_bias_mgL"] = float(ff_bias)
    results["status"] = "OK"
    return results


def validate_hysteresis(df):
    """Check if rising_limb=1 has higher SSC at same turbidity (clockwise hysteresis)."""
    results = {}

    if "rising_limb" not in df.columns:
        results["status"] = "SKIPPED — missing rising_limb"
        return results

    rising = df[df["rising_limb"] == 1]
    falling = df[df["rising_limb"] == 0]

    results["n_rising"] = len(rising)
    results["n_falling"] = len(falling)

    if len(rising) < 20 or len(falling) < 20:
        results["status"] = f"SKIPPED — rising={len(rising)}, falling={len(falling)}"
        return results

    # Compare SSC/turbidity ratio
    r_ratio = (rising["y_true_native"] / rising["turbidity_instant"].clip(lower=1)).median()
    f_ratio = (falling["y_true_native"] / falling["turbidity_instant"].clip(lower=1)).median()
    results["ssc_turb_ratio_rising"] = float(r_ratio)
    results["ssc_turb_ratio_falling"] = float(f_ratio)
    results["clockwise_hysteresis"] = r_ratio > f_ratio

    # Does model capture this?
    r_pred_ratio = (rising["y_pred_native"] / rising["turbidity_instant"].clip(lower=1)).median()
    f_pred_ratio = (falling["y_pred_native"] / falling["turbidity_instant"].clip(lower=1)).median()
    results["model_captures_hysteresis"] = r_pred_ratio > f_pred_ratio
    results["pred_ssc_turb_ratio_rising"] = float(r_pred_ratio)
    results["pred_ssc_turb_ratio_falling"] = float(f_pred_ratio)

    results["metrics_rising"] = compute_metrics(rising["y_true_native"], rising["y_pred_native"])
    results["metrics_falling"] = compute_metrics(falling["y_true_native"], falling["y_pred_native"])
    results["status"] = "OK"
    return results


def validate_extreme_events(df):
    """Check model accuracy on top 1% and top 5% turbidity events."""
    results = {}

    turb_99 = df["turbidity_instant"].quantile(0.99)
    turb_95 = df["turbidity_instant"].quantile(0.95)

    top1 = df[df["turbidity_instant"] >= turb_99]
    top5 = df[df["turbidity_instant"] >= turb_95]
    bottom95 = df[df["turbidity_instant"] < turb_95]

    results["turb_99th_threshold"] = float(turb_99)
    results["turb_95th_threshold"] = float(turb_95)
    results["n_top1pct"] = len(top1)
    results["n_top5pct"] = len(top5)

    results["metrics_top1pct"] = compute_metrics(top1["y_true_native"], top1["y_pred_native"])
    results["metrics_top5pct"] = compute_metrics(top5["y_true_native"], top5["y_pred_native"])
    results["metrics_bottom95pct"] = compute_metrics(bottom95["y_true_native"], bottom95["y_pred_native"])

    # Compression check: does the model systematically underpredict extreme SSC?
    if len(top1) > 0:
        results["top1_median_underprediction_pct"] = float(
            ((top1["y_true_native"] - top1["y_pred_native"]) / top1["y_true_native"].clip(lower=1) * 100).median()
        )
    if len(top5) > 0:
        results["top5_median_underprediction_pct"] = float(
            ((top5["y_true_native"] - top5["y_pred_native"]) / top5["y_true_native"].clip(lower=1) * 100).median()
        )

    results["status"] = "OK"
    return results


def validate_snowmelt(df):
    """Check if spring + high-latitude sites show low SSC/turb ratio (clean meltwater)."""
    results = {}

    if "doy_sin" not in df.columns or "latitude" not in df.columns:
        # Try to infer season from sample_time
        if "sample_time" in df.columns:
            df = df.copy()
            df["month"] = pd.to_datetime(df["sample_time"]).dt.month
            spring = df[df["month"].isin([3, 4, 5])]
            other = df[~df["month"].isin([3, 4, 5])]
        else:
            results["status"] = "SKIPPED — no season info"
            return results
    else:
        # doy_sin > 0.5 roughly corresponds to spring (March-May)
        spring = df[df["doy_sin"] > 0.5]
        other = df[df["doy_sin"] <= 0.5]

    results["n_spring"] = len(spring)
    results["n_other"] = len(other)

    if len(spring) < 20:
        results["status"] = f"SKIPPED — only {len(spring)} spring samples"
        return results

    # Compare SSC/turbidity ratio
    s_ratio = (spring["y_true_native"] / spring["turbidity_instant"].clip(lower=1)).median()
    o_ratio = (other["y_true_native"] / other["turbidity_instant"].clip(lower=1)).median()
    results["ssc_turb_ratio_spring"] = float(s_ratio)
    results["ssc_turb_ratio_other"] = float(o_ratio)
    results["spring_lower_ratio"] = s_ratio < o_ratio  # expected: True for snowmelt

    results["metrics_spring"] = compute_metrics(spring["y_true_native"], spring["y_pred_native"])
    results["metrics_other"] = compute_metrics(other["y_true_native"], other["y_pred_native"])
    results["status"] = "OK"
    return results


def validate_regulated_flow(df):
    """Check if regulated sites (high dam_storage_density) behave differently."""
    results = {}

    if "dam_storage_density" not in df.columns:
        results["status"] = "SKIPPED — missing dam_storage_density"
        return results

    # Split by dam density
    dam_thresh = df["dam_storage_density"].quantile(0.75)
    regulated = df[df["dam_storage_density"] >= dam_thresh]
    unregulated = df[df["dam_storage_density"] < df["dam_storage_density"].quantile(0.25)]

    results["n_regulated"] = len(regulated)
    results["n_unregulated"] = len(unregulated)
    results["dam_density_threshold_75th"] = float(dam_thresh)

    if len(regulated) < 20 or len(unregulated) < 20:
        results["status"] = f"SKIPPED — regulated={len(regulated)}, unregulated={len(unregulated)}"
        return results

    results["metrics_regulated"] = compute_metrics(regulated["y_true_native"], regulated["y_pred_native"])
    results["metrics_unregulated"] = compute_metrics(unregulated["y_true_native"], unregulated["y_pred_native"])
    results["status"] = "OK"
    return results


# ---------------------------------------------------------------------------
# Enrichment: add features from paired dataset and attributes
# ---------------------------------------------------------------------------

def enrich_predictions(predictions):
    """Add features needed for disaggregation from paired dataset and site attributes."""
    df = predictions.copy()

    # Load paired dataset for features
    paired = pd.read_parquet(DATA_DIR / "processed" / "turbidity_ssc_paired.parquet")

    # Join features we need for physics validation
    feature_cols = ["sample_time", "site_id", "collection_method", "turbidity_instant",
                    "discharge_instant", "rising_limb", "precip_30d", "precip_7d",
                    "precip_48h", "flush_intensity", "doy_sin", "doy_cos",
                    "sensor_family", "turb_source", "turb_below_detection"]
    available = [c for c in feature_cols if c in paired.columns]

    # If predictions already have these columns, only add missing ones
    missing = [c for c in available if c not in df.columns]
    if missing and "sample_time" in df.columns and "sample_time" in paired.columns:
        # Normalize timezones before merging
        if hasattr(df["sample_time"].dtype, "tz") and df["sample_time"].dtype.tz is not None:
            df["sample_time"] = df["sample_time"].dt.tz_localize(None)
        if hasattr(paired["sample_time"].dtype, "tz") and paired["sample_time"].dtype.tz is not None:
            paired["sample_time"] = paired["sample_time"].dt.tz_localize(None)
        merge_cols = ["site_id", "sample_time"] + missing
        merge_from = paired[[c for c in merge_cols if c in paired.columns]].drop_duplicates(
            subset=["site_id", "sample_time"])
        df = df.merge(merge_from, on=["site_id", "sample_time"], how="left", suffixes=("", "_paired"))

    # Add site attributes
    try:
        site_attrs = pd.read_parquet(DATA_DIR / "site_attributes.parquet")
        attr_cols = ["site_id", "huc2", "latitude", "longitude"]
        attr_available = [c for c in attr_cols if c in site_attrs.columns]
        attr_missing = [c for c in attr_available if c not in df.columns]
        if attr_missing:
            df = df.merge(site_attrs[["site_id"] + attr_missing].drop_duplicates("site_id"),
                          on="site_id", how="left")
    except Exception as e:
        logger.warning(f"Could not load site_attributes: {e}")

    # Add StreamCat watershed features
    try:
        from murkml.data.attributes import load_streamcat_attrs
        ws = load_streamcat_attrs(DATA_DIR)
        ws_cols = ["site_id", "dam_storage_density", "forest_pct", "agriculture_pct",
                   "developed_pct", "sand_pct", "clay_pct"]
        ws_available = [c for c in ws_cols if c in ws.columns]
        ws_missing = [c for c in ws_available if c not in df.columns]
        if ws_missing:
            df = df.merge(ws[["site_id"] + ws_missing].drop_duplicates("site_id"),
                          on="site_id", how="left")
    except Exception as e:
        logger.warning(f"Could not load StreamCat: {e}")

    # Add SGMC dominant lithology
    try:
        sgmc = pd.read_parquet(DATA_DIR / "sgmc" / "watershed_lithology_pct.parquet")
        lith_cols = [c for c in sgmc.columns if c != "site_id"]
        sgmc["dominant_lithology"] = sgmc[lith_cols].idxmax(axis=1)
        df = df.merge(sgmc[["site_id", "dominant_lithology"]].drop_duplicates("site_id"),
                      on="site_id", how="left")
    except Exception as e:
        logger.warning(f"Could not load SGMC: {e}")

    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Phase 4 Diagnostic Validation")
    parser.add_argument("--predictions", type=str, required=True,
                        help="Path to per-reading predictions parquet")
    parser.add_argument("--output-dir", type=str, default=None)
    args = parser.parse_args()

    pred_path = Path(args.predictions)
    output_dir = Path(args.output_dir) if args.output_dir else DATA_DIR / "results" / "phase4_diagnostics"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Loading predictions from {pred_path}")
    predictions = pd.read_parquet(pred_path)
    logger.info(f"  {len(predictions)} samples, {predictions['site_id'].nunique()} sites")

    # Enrich with features
    logger.info("Enriching predictions with features for disaggregation...")
    df = enrich_predictions(predictions)
    logger.info(f"  Enriched columns: {len(df.columns)}")

    # ===== 4.1 Disaggregated Metrics =====
    logger.info("=" * 70)
    logger.info("4.1 DISAGGREGATED METRICS")
    logger.info("=" * 70)
    disagg = run_disaggregated_metrics(df)
    disagg.to_parquet(output_dir / "disaggregated_metrics.parquet", index=False)

    # Print summary
    for dim in disagg["dimension"].unique():
        subset = disagg[disagg["dimension"] == dim]
        logger.info(f"\n--- {dim} ---")
        for _, row in subset.iterrows():
            logger.info(f"  {row['group']:25s}  n={row['n']:5.0f}  R²={row['r2']:+.3f}  "
                        f"RMSE={row['rmse']:8.1f}  MAPE={row['mape_pct']:5.1f}%  "
                        f"2x={row['within_2x_pct']:5.1f}%  bias={row['bias_pct']:+.1f}%")

    # ===== 4.2 Physics Validation =====
    logger.info("\n" + "=" * 70)
    logger.info("4.2 PHYSICS-BASED VALIDATION")
    logger.info("=" * 70)

    physics = {}

    # First flush
    logger.info("\n--- First Flush ---")
    physics["first_flush"] = validate_first_flush(df)
    ff = physics["first_flush"]
    if ff["status"] == "OK":
        logger.info(f"  SSC/turb ratio: flush={ff['ssc_turb_ratio_flush']:.2f}, "
                    f"normal={ff['ssc_turb_ratio_normal']:.2f} "
                    f"(elevation={ff['ratio_elevation']:.2f}x)")
        logger.info(f"  Flush R²={ff['metrics_first_flush']['r2']:.3f}, "
                    f"Normal R²={ff['metrics_normal']['r2']:.3f}")
        logger.info(f"  Flush median bias: {ff['first_flush_median_bias_mgL']:.1f} mg/L")
    else:
        logger.info(f"  {ff['status']}")

    # Hysteresis
    logger.info("\n--- Hysteresis ---")
    physics["hysteresis"] = validate_hysteresis(df)
    hyst = physics["hysteresis"]
    if hyst["status"] == "OK":
        logger.info(f"  True SSC/turb: rising={hyst['ssc_turb_ratio_rising']:.2f}, "
                    f"falling={hyst['ssc_turb_ratio_falling']:.2f}")
        logger.info(f"  Clockwise hysteresis in data: {hyst['clockwise_hysteresis']}")
        logger.info(f"  Model captures hysteresis: {hyst['model_captures_hysteresis']}")
        logger.info(f"  Rising R²={hyst['metrics_rising']['r2']:.3f}, "
                    f"Falling R²={hyst['metrics_falling']['r2']:.3f}")
    else:
        logger.info(f"  {hyst['status']}")

    # Extreme events
    logger.info("\n--- Extreme Events ---")
    physics["extreme_events"] = validate_extreme_events(df)
    ext = physics["extreme_events"]
    logger.info(f"  Top 1% threshold: {ext['turb_99th_threshold']:.0f} FNU ({ext['n_top1pct']} samples)")
    logger.info(f"  Top 5% threshold: {ext['turb_95th_threshold']:.0f} FNU ({ext['n_top5pct']} samples)")
    logger.info(f"  Top 1% R²={ext['metrics_top1pct']['r2']:.3f}, "
                f"Bottom 95% R²={ext['metrics_bottom95pct']['r2']:.3f}")
    if "top1_median_underprediction_pct" in ext:
        logger.info(f"  Top 1% median underprediction: {ext['top1_median_underprediction_pct']:.1f}%")
    if "top5_median_underprediction_pct" in ext:
        logger.info(f"  Top 5% median underprediction: {ext['top5_median_underprediction_pct']:.1f}%")

    # Snowmelt
    logger.info("\n--- Snowmelt ---")
    physics["snowmelt"] = validate_snowmelt(df)
    snow = physics["snowmelt"]
    if snow["status"] == "OK":
        logger.info(f"  SSC/turb ratio: spring={snow['ssc_turb_ratio_spring']:.2f}, "
                    f"other={snow['ssc_turb_ratio_other']:.2f}")
        logger.info(f"  Spring lower ratio (expected for snowmelt): {snow['spring_lower_ratio']}")
        logger.info(f"  Spring R²={snow['metrics_spring']['r2']:.3f}, "
                    f"Other R²={snow['metrics_other']['r2']:.3f}")
    else:
        logger.info(f"  {snow['status']}")

    # Regulated flow
    logger.info("\n--- Regulated Flow ---")
    physics["regulated_flow"] = validate_regulated_flow(df)
    reg = physics["regulated_flow"]
    if reg["status"] == "OK":
        logger.info(f"  Regulated R²={reg['metrics_regulated']['r2']:.3f} (n={reg['n_regulated']}), "
                    f"Unregulated R²={reg['metrics_unregulated']['r2']:.3f} (n={reg['n_unregulated']})")
    else:
        logger.info(f"  {reg['status']}")

    # Save physics results
    with open(output_dir / "physics_validation.json", "w") as f:
        json.dump(physics, f, indent=2, default=str)

    logger.info("\n" + "=" * 70)
    logger.info(f"Results saved to {output_dir}")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
