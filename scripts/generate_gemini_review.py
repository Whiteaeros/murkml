#!/usr/bin/env python
"""Generate the Gemini red-team review file from Phase 5 ablation results."""
import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
OUT = Path(__file__).parent.parent / "gemini_ablation_review.md"

comp = pd.read_csv(DATA_DIR / "results" / "phase5_deep_eval" / "comparison_table.csv")
screen = pd.read_csv(DATA_DIR / "results" / "phase5_screening_results.csv")

base = comp[comp["label"] == "phase5_baseline"].iloc[0]
others = comp[comp["label"] != "phase5_baseline"].copy()
others["d_nse"] = others["pooled_nse"] - base["pooled_nse"]
others["d_log_nse"] = others["pooled_log_nse"] - base["pooled_log_nse"]
others["d_mape"] = others["pooled_mape"] - base["pooled_mape"]
others["d_spearman"] = others["pooled_spearman"] - base["pooled_spearman"]
others["d_med_r2"] = others["med_persite_r2"] - base["med_persite_r2"]

screen_map = {}
for _, r in screen.iterrows():
    key = f"drop_{r['feature']}" if r["type"] == "drop" else f"add_{r['feature']}"
    screen_map[key] = r["dR2_nat"]

with open(OUT, "w", encoding="utf-8") as f:
    f.write("# Phase 5 Ablation Results - Full Data for Red Team Review\n\n")

    f.write("## Context\n\n")
    f.write("murkml is a CatBoost model predicting suspended sediment concentration (SSC, mg/L) from\n")
    f.write("turbidity sensor data + watershed characteristics across 396 USGS stream sites.\n\n")
    f.write("We ran a two-stage ablation:\n")
    f.write("1. **GKF5 screening** (GroupKFold 5-fold CV on training data): Drop each of 72 features one at a time,\n")
    f.write("   measure aggregate metrics. Also tested re-introducing 10 previously dropped features. 83 experiments.\n")
    f.write("2. **Holdout evaluation** (76 never-seen sites, 5847 samples): For 46 ambiguous/harmful features,\n")
    f.write("   trained a model without that feature and ran the full evaluation pipeline including\n")
    f.write("   disaggregated metrics, adaptation curves, and external validation.\n\n")
    f.write("The key discovery: **GKF5 aggregate screening and holdout evaluation disagree dramatically.**\n")
    f.write("Features that look neutral or harmful on GKF5 are often critical for holdout generalization.\n\n")

    f.write("## What We Want You to Check\n\n")
    f.write("1. **Is the GKF5 vs holdout disagreement real, or is there a bug?** Could data leakage,\n")
    f.write("   different sample populations, or evaluation methodology explain the discrepancy?\n")
    f.write("2. **Which features should we keep vs drop?** Given the disagreement, what decision framework?\n")
    f.write("3. **Are we measuring the right things?** Trust pooled NSE, median per-site R2, MAPE, Spearman?\n")
    f.write("4. **Is there any evidence of overfitting, data leakage, or methodological error?**\n")
    f.write("5. **What would you do with these results?**\n\n")

    f.write("---\n\n")
    f.write("## Baseline Model (72 features: 44 original + 28 SGMC lithology)\n\n")
    f.write("**GKF5 CV (training data, 357 sites, 32046 samples):**\n")
    f.write("- R2(native) = 0.239, R2(log) = 0.775, KGE = 0.795, alpha = 0.836\n")
    f.write("- RMSE = 853.0 mg/L, Bias = -9.2%, BCF = 1.343\n\n")
    f.write("**Holdout (76 sites, 5847 samples - never seen during training):**\n")
    f.write(f"- Pooled NSE = {base['pooled_nse']:.4f}\n")
    f.write(f"- Log-NSE = {base['pooled_log_nse']:.4f}\n")
    f.write(f"- KGE = {base['pooled_kge']:.4f}\n")
    f.write(f"- MAPE = {base['pooled_mape']:.1f}%\n")
    f.write(f"- Within 2x = {base['pooled_within_2x']:.1%}\n")
    f.write(f"- Bias = {base['pooled_bias']:+.1f}%\n")
    f.write(f"- Spearman rho = {base['pooled_spearman']:.4f}\n")
    f.write(f"- Median per-site R2 = {base['med_persite_r2']:.4f}\n\n")

    f.write("---\n\n")
    f.write("## GKF5 Screening Results (all 83 experiments)\n\n")
    f.write("Delta = change when feature is DROPPED (negative = feature helps, positive = feature hurts)\n\n")
    f.write("| Feature | Type | dR2_native | dR2_log | dKGE | dAlpha | dRMSE | dBias |\n")
    f.write("|---|---|---|---|---|---|---|---|\n")
    for _, r in screen.sort_values("dR2_nat").iterrows():
        f.write(f"| {r['feature']} | {r['type']} | {r['dR2_nat']:+.4f} | {r['dR2_log']:+.4f} | "
                f"{r['dKGE']:+.4f} | {r['dAlpha']:+.4f} | {r['dRMSE']:+.1f} | {r['dBias']:+.1f} |\n")

    f.write("\n---\n\n")
    f.write("## Holdout Evaluation Results (47 models)\n\n")
    f.write("Delta = change vs baseline when feature is DROPPED\n\n")
    f.write("| Label | Pooled NSE | dNSE | Log-NSE | dLogNSE | MAPE | dMAPE | Spearman | dSpear | Med Site R2 | dMedR2 | GKF5 dR2_nat |\n")
    f.write("|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    f.write(f"| **BASELINE** | **{base['pooled_nse']:.4f}** | -- | **{base['pooled_log_nse']:.4f}** | -- | "
            f"**{base['pooled_mape']:.1f}%** | -- | **{base['pooled_spearman']:.4f}** | -- | "
            f"**{base['med_persite_r2']:.4f}** | -- | -- |\n")
    for _, r in others.sort_values("d_med_r2").iterrows():
        s = screen_map.get(r["label"], np.nan)
        s_str = f"{s:+.3f}" if pd.notna(s) else "--"
        f.write(f"| {r['label']} | {r['pooled_nse']:.4f} | {r['d_nse']:+.4f} | {r['pooled_log_nse']:.4f} | "
                f"{r['d_log_nse']:+.4f} | {r['pooled_mape']:.1f}% | {r['d_mape']:+.1f} | "
                f"{r['pooled_spearman']:.4f} | {r['d_spearman']:+.4f} | "
                f"{r['med_persite_r2']:.4f} | {r['d_med_r2']:+.4f} | {s_str} |\n")

    f.write("\n---\n\n")
    f.write("## The Core Discrepancy\n\n")
    f.write("Features where GKF5 and holdout DISAGREE on importance:\n\n")
    f.write("| Feature | GKF5 dR2_nat | Holdout dMedR2 | GKF5 says | Holdout says |\n")
    f.write("|---|---|---|---|---|\n")
    for _, r in others.sort_values("d_med_r2").iterrows():
        s = screen_map.get(r["label"], np.nan)
        if pd.isna(s):
            continue
        gkf5_v = "HARMFUL" if s > 0.005 else ("helpful" if s < -0.005 else "neutral")
        hold_v = "CRITICAL" if r["d_med_r2"] < -0.10 else ("helpful" if r["d_med_r2"] < -0.01 else ("neutral" if r["d_med_r2"] < 0.01 else "harmful"))
        if gkf5_v != hold_v:
            f.write(f"| {r['label']} | {s:+.4f} | {r['d_med_r2']:+.4f} | {gkf5_v} | {hold_v} |\n")

    f.write("\n---\n\n")
    f.write("## Features Where Dropping Actually Helps on Holdout\n\n")
    helps = others[others["d_med_r2"] > 0.005].sort_values("d_med_r2", ascending=False)
    if len(helps) > 0:
        f.write("| Feature | dMedR2 | dNSE | dMAPE | GKF5 dR2_nat |\n")
        f.write("|---|---|---|---|---|\n")
        for _, r in helps.iterrows():
            s = screen_map.get(r["label"], np.nan)
            s_str = f"{s:+.3f}" if pd.notna(s) else "--"
            f.write(f"| {r['label']} | {r['d_med_r2']:+.4f} | {r['d_nse']:+.4f} | {r['d_mape']:+.1f} | {s_str} |\n")
    else:
        f.write("None found.\n")

    f.write("\n---\n\n")
    f.write("## Model Architecture\n\n")
    f.write("- CatBoost gradient boosting, Box-Cox lambda=0.2, Snowdon BCF\n")
    f.write("- Monotone constraints on turbidity_instant, turbidity_max_1hr\n")
    f.write("- Training: 320 sites, 32046 samples / Holdout: 76 sites, 5847 samples\n")
    f.write("- GKF5 = GroupKFold 5 folds (groups=sites, ~4 min/experiment)\n")
    f.write("- Holdout eval: Bayesian adaptation (Student-t, k=15), 3 split modes, disaggregated metrics\n\n")

    f.write("## Feature Categories (72 total)\n\n")
    f.write("- **Sensor (7):** turbidity_instant, turbidity_max_1hr, turbidity_std_1hr, conductance_instant, temp_instant, sensor_offset, days_since_last_visit\n")
    f.write("- **Hydrograph (7):** discharge_slope_2hr, rising_limb, Q_7day_mean, turb_Q_ratio, DO_sat_departure, flush_intensity, turb_below_detection\n")
    f.write("- **Temporal (2):** doy_sin, doy_cos\n")
    f.write("- **Weather (3):** precip_48h, precip_7d, precip_30d\n")
    f.write("- **Watershed (21):** longitude, drainage_area_km2, forest_pct, agriculture_pct, developed_pct, pct_carbonate_resid, pct_alluvial_coastal, pct_eolian_coarse, pct_eolian_fine, pct_colluvial_sediment, geo_fe2o3, clay_pct, sand_pct, soil_organic_matter, elevation_m, baseflow_index, wetness_index, dam_storage_density, wwtp_all_density, wwtp_minor_density, fertilizer_rate, nitrogen_surplus\n")
    f.write("- **Categorical (3):** collection_method, turb_source, sensor_family\n")
    f.write("- **SGMC Lithology (28):** Watershed bedrock type percentages\n\n")

    f.write("## Re-introduced Features (tested adding back 10 previously dropped)\n\n")
    f.write("None helped. Best was do_instant (+0.003 R2_native). discharge_instant (-0.006),\n")
    f.write("soil_permeability (-0.007), temp_mean_c (-0.009) actively hurt when re-added.\n\n")

    f.write("## Previous Expert Panel Findings (for context)\n\n")
    f.write("- Low-SSC overprediction (+121% bias) is sensor contamination (DOM, algae), not model failure\n")
    f.write("- Extreme underprediction (-37%) is particle size shift, not just sensor saturation\n")
    f.write("- Within-tier R2 is meaningless (guaranteed negative in narrow bands)\n")
    f.write("- NSE and R2 are identical for our computation (1-SS_res/SS_tot)\n")
    f.write("- Residuals are non-normal (skew=2.0, kurtosis=13.8)\n")

print(f"Written to {OUT}")
