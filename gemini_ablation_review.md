# Phase 5 Ablation Results - Full Data for Red Team Review

## Context

murkml is a CatBoost model predicting suspended sediment concentration (SSC, mg/L) from
turbidity sensor data + watershed characteristics across 396 USGS stream sites.

We ran a two-stage ablation:
1. **GKF5 screening** (GroupKFold 5-fold CV on training data): Drop each of 72 features one at a time,
   measure aggregate metrics. Also tested re-introducing 10 previously dropped features. 83 experiments.
2. **Holdout evaluation** (76 never-seen sites, 5847 samples): For 46 ambiguous/harmful features,
   trained a model without that feature and ran the full evaluation pipeline including
   disaggregated metrics, adaptation curves, and external validation.

The key discovery: **GKF5 aggregate screening and holdout evaluation disagree dramatically.**
Features that look neutral or harmful on GKF5 are often critical for holdout generalization.

## What We Want You to Check

1. **Is the GKF5 vs holdout disagreement real, or is there a bug?** Could data leakage,
   different sample populations, or evaluation methodology explain the discrepancy?
2. **Which features should we keep vs drop?** Given the disagreement, what decision framework?
3. **Are we measuring the right things?** Trust pooled NSE, median per-site R2, MAPE, Spearman?
4. **Is there any evidence of overfitting, data leakage, or methodological error?**
5. **What would you do with these results?**

---

## Baseline Model (72 features: 44 original + 28 SGMC lithology)

**GKF5 CV (training data, 357 sites, 32046 samples):**
- R2(native) = 0.239, R2(log) = 0.775, KGE = 0.795, alpha = 0.836
- RMSE = 853.0 mg/L, Bias = -9.2%, BCF = 1.343

**Holdout (76 sites, 5847 samples - never seen during training):**
- Pooled NSE = 0.3676
- Log-NSE = 0.7656
- KGE = 0.3667
- MAPE = 59.7%
- Within 2x = 61.4%
- Bias = -6.7%
- Spearman rho = 0.9019
- Median per-site R2 = 0.2846

---

## GKF5 Screening Results (all 83 experiments)

Delta = change when feature is DROPPED (negative = feature helps, positive = feature hurts)

| Feature | Type | dR2_native | dR2_log | dKGE | dAlpha | dRMSE | dBias |
|---|---|---|---|---|---|---|---|
| turbidity_instant | drop | -0.0490 | -0.1610 | -0.1320 | -0.1090 | +27.0 | -3.9 |
| pct_alluvial_coastal | drop | -0.0280 | -0.0010 | -0.0060 | +0.0040 | +15.9 | -2.6 |
| sgmc_sedimentary_iron_formation_undifferentiated | drop | -0.0260 | -0.0040 | -0.0040 | +0.0020 | +14.5 | -1.2 |
| sgmc_igneous_intrusive | drop | -0.0220 | +0.0020 | -0.0010 | +0.0020 | +12.1 | -0.7 |
| conductance_instant | drop | -0.0190 | -0.0020 | +0.0030 | +0.0040 | +10.6 | +1.6 |
| pct_eolian_coarse | drop | -0.0180 | -0.0080 | +0.0020 | +0.0100 | +10.3 | +3.3 |
| sgmc_metamorphic_amphibolite | drop | -0.0140 | -0.0030 | -0.0060 | -0.0020 | +8.1 | -1.1 |
| sgmc_metamorphic_gneiss | drop | -0.0130 | -0.0060 | -0.0010 | +0.0040 | +7.4 | +0.6 |
| clay_pct | drop | -0.0110 | -0.0060 | -0.0040 | +0.0030 | +6.5 | -0.2 |
| elevation_m | drop | -0.0110 | -0.0090 | +0.0010 | +0.0060 | +6.2 | -0.7 |
| precip_7d | drop | -0.0100 | -0.0050 | -0.0040 | +0.0020 | +5.6 | -0.8 |
| turbidity_max_1hr | drop | -0.0100 | -0.0050 | +0.0010 | +0.0060 | +5.9 | +0.8 |
| rising_limb | drop | -0.0100 | -0.0020 | -0.0070 | +0.0040 | +5.6 | -2.6 |
| turbidity_std_1hr | drop | -0.0090 | -0.0050 | -0.0020 | +0.0020 | +5.3 | +2.3 |
| sgmc_metamorphic_sedimentary | drop | -0.0090 | -0.0040 | -0.0030 | +0.0040 | +5.2 | -1.2 |
| soil_organic_matter | drop | -0.0090 | -0.0060 | -0.0040 | +0.0030 | +5.5 | -0.8 |
| sgmc_igneous_undifferentiated | drop | -0.0090 | -0.0060 | -0.0060 | -0.0060 | +5.5 | -0.6 |
| temp_mean_c | reintroduce | -0.0090 | -0.0020 | -0.0010 | +0.0040 | +5.0 | -1.6 |
| sgmc_tectonite_undifferentiated | drop | -0.0080 | -0.0030 | -0.0030 | +0.0030 | +5.2 | -0.3 |
| agriculture_pct | drop | -0.0080 | -0.0080 | -0.0080 | -0.0040 | +5.8 | -0.8 |
| sgmc_igneous_sedimentary_undifferentiated | drop | -0.0070 | -0.0010 | -0.0010 | +0.0030 | +4.7 | -0.0 |
| sgmc_metamorphic_intrusive | drop | -0.0070 | -0.0040 | -0.0040 | +0.0000 | +4.7 | -0.4 |
| sgmc_metamorphic_granulite | drop | -0.0070 | -0.0010 | -0.0010 | +0.0030 | +4.7 | -0.1 |
| drainage_area_km2 | drop | -0.0070 | -0.0070 | -0.0070 | -0.0030 | +4.7 | -0.7 |
| soil_permeability | reintroduce | -0.0070 | -0.0070 | -0.0020 | -0.0050 | +3.8 | -1.9 |
| doy_sin | drop | -0.0070 | -0.0020 | -0.0020 | +0.0020 | +4.7 | -0.2 |
| wetness_index | drop | -0.0060 | -0.0050 | -0.0050 | -0.0010 | +4.2 | -0.5 |
| sgmc_igneous_metamorphic_undifferentiated | drop | -0.0060 | -0.0050 | -0.0050 | -0.0010 | +4.2 | -0.5 |
| discharge_instant | reintroduce | -0.0060 | -0.0060 | -0.0060 | +0.0000 | +3.2 | -1.1 |
| wwtp_minor_density | drop | -0.0050 | +0.0000 | +0.0000 | +0.0000 | +3.7 | +0.0 |
| Q_7day_mean | drop | -0.0050 | -0.0010 | -0.0010 | +0.0030 | +3.7 | -0.1 |
| turb_below_detection | drop | -0.0050 | -0.0120 | -0.0050 | -0.0050 | +3.7 | -0.5 |
| precip_48h | drop | -0.0040 | -0.0050 | -0.0050 | -0.0050 | +2.8 | -0.4 |
| fertilizer_rate | drop | -0.0040 | -0.0090 | -0.0090 | -0.0090 | +2.8 | -0.9 |
| doy_cos | drop | -0.0030 | -0.0070 | -0.0070 | -0.0070 | +2.3 | -0.7 |
| flush_intensity | drop | -0.0030 | -0.0110 | -0.0110 | -0.0110 | +2.3 | -1.1 |
| sgmc_sedimentary_clastic | drop | -0.0030 | -0.0060 | -0.0060 | -0.0060 | +2.3 | -0.6 |
| turb_source | drop | -0.0030 | -0.0060 | -0.0060 | -0.0060 | +2.3 | -0.6 |
| baseflow_index | drop | -0.0030 | -0.0030 | -0.0030 | -0.0030 | +2.3 | -0.3 |
| sgmc_melange | drop | -0.0020 | -0.0070 | -0.0070 | -0.0070 | +1.8 | -0.7 |
| sgmc_metamorphic_undifferentiated | drop | -0.0020 | -0.0080 | -0.0080 | -0.0080 | +1.8 | -0.8 |
| longitude | drop | -0.0020 | -0.0090 | -0.0090 | -0.0090 | +1.8 | -0.9 |
| nitrogen_surplus | drop | -0.0020 | -0.0010 | -0.0010 | +0.0010 | +1.8 | -0.1 |
| soil_erodibility | reintroduce | -0.0020 | -0.0080 | -0.0060 | +0.0010 | +1.1 | -2.4 |
| slope_pct | reintroduce | -0.0020 | -0.0040 | -0.0040 | +0.0050 | +1.0 | -3.0 |
| sgmc_metamorphic_other | drop | -0.0020 | -0.0060 | -0.0060 | -0.0060 | +1.8 | -0.6 |
| discharge_slope_2hr | drop | -0.0010 | +0.0010 | +0.0010 | +0.0010 | +1.3 | +0.1 |
| developed_pct | drop | -0.0010 | -0.0080 | -0.0080 | -0.0080 | +1.3 | -0.8 |
| temp_instant | drop | -0.0010 | -0.0040 | -0.0040 | -0.0040 | +1.3 | -0.4 |
| sand_pct | drop | -0.0010 | -0.0060 | -0.0060 | -0.0060 | +1.3 | -0.6 |
| water_table_depth | reintroduce | -0.0010 | -0.0060 | -0.0060 | +0.0010 | +0.8 | -3.0 |
| sensor_offset | drop | -0.0010 | -0.0020 | -0.0020 | -0.0020 | +1.3 | -0.2 |
| days_since_last_visit | drop | -0.0010 | -0.0080 | -0.0080 | -0.0080 | +1.3 | -0.8 |
| sgmc_metamorphic_schist | drop | -0.0010 | -0.0070 | -0.0070 | -0.0070 | +1.3 | -0.7 |
| phase5_baseline | baseline | +0.0000 | +0.0000 | +0.0000 | +0.0000 | +0.0 | +0.0 |
| precip_30d | drop | +0.0000 | -0.0070 | -0.0070 | -0.0070 | +0.0 | -0.7 |
| pct_eolian_fine | drop | +0.0000 | -0.0050 | -0.0050 | -0.0050 | +0.0 | -0.5 |
| precip_24h | reintroduce | +0.0000 | -0.0110 | -0.0050 | +0.0010 | +0.2 | -2.5 |
| collection_method | drop | +0.0000 | -0.0110 | -0.0110 | -0.0110 | +0.0 | -1.1 |
| pct_carbonate_resid | drop | +0.0000 | -0.0100 | -0.0100 | -0.0100 | +0.0 | -1.0 |
| forest_pct | drop | +0.0000 | -0.0070 | -0.0070 | -0.0070 | +0.0 | -0.7 |
| geo_fe2o3 | drop | +0.0010 | -0.0010 | -0.0010 | -0.0010 | -1.0 | -0.1 |
| sgmc_metamorphic_sedimentary_clastic | drop | +0.0010 | -0.0040 | +0.0000 | +0.0040 | -1.0 | -0.4 |
| sensor_family | drop | +0.0010 | -0.0030 | +0.0030 | +0.0030 | -1.0 | -0.3 |
| ph_instant | reintroduce | +0.0010 | -0.0030 | -0.0050 | +0.0000 | -0.4 | -2.2 |
| temp_at_sample | reintroduce | +0.0010 | -0.0010 | -0.0040 | +0.0060 | -0.7 | -3.0 |
| sgmc_water | drop | +0.0010 | -0.0130 | -0.0060 | -0.0130 | -1.0 | -1.3 |
| pct_colluvial_sediment | drop | +0.0020 | -0.0040 | -0.0040 | -0.0040 | -1.5 | -0.4 |
| DO_sat_departure | drop | +0.0020 | -0.0030 | -0.0080 | -0.0030 | -1.5 | -0.5 |
| sgmc_metamorphic_sedimentary_undifferentiated | drop | +0.0020 | -0.0100 | -0.0110 | -0.0100 | -1.5 | -1.0 |
| wwtp_all_density | drop | +0.0020 | -0.0090 | -0.0020 | -0.0090 | -1.5 | -0.9 |
| sgmc_unconsolidated_sedimentary_undifferentiated | drop | +0.0020 | +0.0000 | +0.0000 | +0.0000 | -1.5 | +0.0 |
| sgmc_sedimentary_undifferentiated | drop | +0.0030 | -0.0010 | +0.0010 | +0.0040 | -1.5 | +0.0 |
| do_instant | reintroduce | +0.0030 | -0.0090 | -0.0040 | +0.0030 | -1.6 | +0.6 |
| sgmc_metamorphic_carbonate | drop | +0.0030 | -0.0090 | -0.0040 | +0.0030 | -1.4 | +0.1 |
| sgmc_unconsolidated_undifferentiated | drop | +0.0030 | -0.0040 | -0.0030 | -0.0050 | -1.6 | -2.0 |
| turb_Q_ratio | drop | +0.0040 | -0.0130 | -0.0100 | +0.0030 | -2.4 | -0.7 |
| sgmc_igneous_volcanic | drop | +0.0050 | -0.0120 | -0.0100 | +0.0000 | -2.8 | -1.6 |
| sgmc_metamorphic_volcanic | drop | +0.0050 | -0.0030 | -0.0040 | +0.0060 | -2.7 | -0.3 |
| dam_storage_density | drop | +0.0070 | -0.0060 | -0.0030 | -0.0010 | -3.7 | -0.3 |
| sgmc_metamorphic_serpentinite | drop | +0.0070 | -0.0110 | -0.0090 | -0.0060 | -3.6 | -0.4 |
| sgmc_sedimentary_carbonate | drop | +0.0080 | -0.0050 | -0.0080 | +0.0030 | -4.2 | -2.1 |
| sgmc_sedimentary_chemical | drop | +0.0090 | -0.0050 | -0.0050 | +0.0100 | -5.1 | +1.6 |

---

## Holdout Evaluation Results (47 models)

Delta = change vs baseline when feature is DROPPED

| Label | Pooled NSE | dNSE | Log-NSE | dLogNSE | MAPE | dMAPE | Spearman | dSpear | Med Site R2 | dMedR2 | GKF5 dR2_nat |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **BASELINE** | **0.3676** | -- | **0.7656** | -- | **59.7%** | -- | **0.9019** | -- | **0.2846** | -- | -- |
| drop_turb_Q_ratio | 0.3182 | -0.0494 | 0.7368 | -0.0288 | 65.3% | +5.7 | 0.8956 | -0.0063 | 0.1828 | -0.1017 | +0.004 |
| drop_sgmc_unconsolidated_sedimentary_undifferentiated | 0.3521 | -0.0155 | 0.7419 | -0.0237 | 64.6% | +4.9 | 0.8983 | -0.0035 | 0.1828 | -0.1017 | +0.002 |
| drop_collection_method | 0.3549 | -0.0127 | 0.7642 | -0.0014 | 59.2% | -0.5 | 0.8998 | -0.0020 | 0.2195 | -0.0651 | +0.000 |
| drop_flush_intensity | 0.3414 | -0.0262 | 0.7678 | +0.0022 | 56.8% | -2.8 | 0.9015 | -0.0003 | 0.2303 | -0.0542 | -0.003 |
| drop_sensor_family | 0.3763 | +0.0087 | 0.7674 | +0.0018 | 59.3% | -0.4 | 0.9028 | +0.0010 | 0.2325 | -0.0520 | +0.001 |
| drop_temp_instant | 0.3317 | -0.0359 | 0.7577 | -0.0079 | 59.6% | -0.1 | 0.9000 | -0.0018 | 0.2392 | -0.0454 | -0.001 |
| drop_turb_source | 0.3381 | -0.0295 | 0.7636 | -0.0020 | 59.3% | -0.3 | 0.9014 | -0.0004 | 0.2433 | -0.0413 | -0.003 |
| drop_sgmc_igneous_volcanic | 0.3369 | -0.0307 | 0.7590 | -0.0066 | 59.7% | +0.1 | 0.9003 | -0.0016 | 0.2433 | -0.0412 | +0.005 |
| drop_sgmc_metamorphic_volcanic | 0.3452 | -0.0224 | 0.7534 | -0.0122 | 60.7% | +1.1 | 0.8995 | -0.0023 | 0.2461 | -0.0385 | +0.005 |
| drop_developed_pct | 0.3190 | -0.0486 | 0.7651 | -0.0004 | 59.5% | -0.1 | 0.9025 | +0.0007 | 0.2533 | -0.0313 | -0.001 |
| drop_dam_storage_density | 0.3379 | -0.0297 | 0.7581 | -0.0075 | 60.4% | +0.7 | 0.8993 | -0.0025 | 0.2537 | -0.0308 | +0.007 |
| drop_turb_below_detection | 0.3313 | -0.0363 | 0.7604 | -0.0052 | 60.1% | +0.4 | 0.9029 | +0.0010 | 0.2553 | -0.0292 | -0.005 |
| drop_sand_pct | 0.3437 | -0.0240 | 0.7557 | -0.0099 | 60.8% | +1.2 | 0.8998 | -0.0021 | 0.2586 | -0.0260 | -0.001 |
| drop_sensor_offset | 0.3252 | -0.0424 | 0.7668 | +0.0012 | 58.3% | -1.4 | 0.9032 | +0.0014 | 0.2594 | -0.0251 | -0.001 |
| drop_longitude | 0.3267 | -0.0410 | 0.7614 | -0.0041 | 60.7% | +1.1 | 0.9015 | -0.0003 | 0.2603 | -0.0242 | -0.002 |
| drop_sgmc_metamorphic_other | 0.3376 | -0.0301 | 0.7613 | -0.0043 | 60.5% | +0.8 | 0.9014 | -0.0004 | 0.2671 | -0.0175 | -0.002 |
| drop_Q_7day_mean | 0.3409 | -0.0267 | 0.7696 | +0.0040 | 56.9% | -2.8 | 0.9019 | +0.0000 | 0.2715 | -0.0130 | -0.005 |
| drop_precip_48h | 0.3377 | -0.0299 | 0.7589 | -0.0067 | 58.6% | -1.1 | 0.9001 | -0.0017 | 0.2721 | -0.0124 | -0.004 |
| drop_nitrogen_surplus | 0.3554 | -0.0122 | 0.7590 | -0.0066 | 60.6% | +1.0 | 0.9008 | -0.0011 | 0.2756 | -0.0090 | -0.002 |
| drop_sgmc_metamorphic_serpentinite | 0.3401 | -0.0275 | 0.7657 | +0.0001 | 58.5% | -1.1 | 0.9025 | +0.0006 | 0.2763 | -0.0082 | +0.007 |
| drop_DO_sat_departure | 0.3559 | -0.0118 | 0.7649 | -0.0007 | 59.3% | -0.3 | 0.9028 | +0.0009 | 0.2771 | -0.0075 | +0.002 |
| drop_sgmc_sedimentary_carbonate | 0.3438 | -0.0239 | 0.7640 | -0.0016 | 59.6% | -0.1 | 0.9014 | -0.0005 | 0.2783 | -0.0063 | +0.008 |
| drop_sgmc_metamorphic_schist | 0.3632 | -0.0044 | 0.7635 | -0.0021 | 60.4% | +0.8 | 0.9029 | +0.0010 | 0.2784 | -0.0062 | -0.001 |
| drop_forest_pct | 0.3517 | -0.0159 | 0.7658 | +0.0002 | 60.5% | +0.8 | 0.9025 | +0.0007 | 0.2792 | -0.0054 | +0.000 |
| drop_days_since_last_visit | 0.3271 | -0.0405 | 0.7643 | -0.0013 | 58.1% | -1.6 | 0.9016 | -0.0002 | 0.2794 | -0.0052 | -0.001 |
| drop_sgmc_metamorphic_undifferentiated | 0.3497 | -0.0179 | 0.7635 | -0.0021 | 59.9% | +0.2 | 0.9018 | -0.0001 | 0.2802 | -0.0044 | -0.002 |
| drop_sgmc_sedimentary_chemical | 0.3277 | -0.0399 | 0.7707 | +0.0051 | 58.7% | -0.9 | 0.9035 | +0.0016 | 0.2808 | -0.0037 | +0.009 |
| drop_sgmc_water | 0.3392 | -0.0285 | 0.7622 | -0.0034 | 59.4% | -0.3 | 0.9025 | +0.0006 | 0.2814 | -0.0032 | +0.001 |
| drop_doy_cos | 0.3648 | -0.0028 | 0.7609 | -0.0047 | 60.5% | +0.8 | 0.9015 | -0.0003 | 0.2831 | -0.0015 | -0.003 |
| drop_sgmc_metamorphic_sedimentary_clastic | 0.3582 | -0.0094 | 0.7629 | -0.0027 | 60.5% | +0.8 | 0.9021 | +0.0002 | 0.2839 | -0.0007 | +0.001 |
| drop_pct_colluvial_sediment | 0.3267 | -0.0409 | 0.7609 | -0.0047 | 59.9% | +0.2 | 0.9009 | -0.0009 | 0.2848 | +0.0002 | +0.002 |
| drop_discharge_slope_2hr | 0.3290 | -0.0386 | 0.7596 | -0.0060 | 59.7% | +0.0 | 0.9013 | -0.0005 | 0.2863 | +0.0018 | -0.001 |
| drop_wwtp_minor_density | 0.3298 | -0.0378 | 0.7607 | -0.0049 | 60.0% | +0.4 | 0.9014 | -0.0005 | 0.2890 | +0.0044 | -0.005 |
| drop_sgmc_sedimentary_clastic | 0.3438 | -0.0238 | 0.7676 | +0.0020 | 57.8% | -1.8 | 0.9025 | +0.0007 | 0.2893 | +0.0047 | -0.003 |
| drop_sgmc_sedimentary_undifferentiated | 0.3347 | -0.0329 | 0.7678 | +0.0022 | 59.1% | -0.6 | 0.9027 | +0.0009 | 0.2913 | +0.0067 | +0.003 |
| drop_fertilizer_rate | 0.3433 | -0.0243 | 0.7613 | -0.0043 | 60.7% | +1.0 | 0.9013 | -0.0006 | 0.2929 | +0.0084 | -0.004 |
| drop_sgmc_unconsolidated_undifferentiated | 0.3559 | -0.0117 | 0.7672 | +0.0016 | 58.5% | -1.2 | 0.9025 | +0.0006 | 0.2943 | +0.0097 | +0.003 |
| drop_wwtp_all_density | 0.3566 | -0.0110 | 0.7621 | -0.0035 | 60.0% | +0.3 | 0.9014 | -0.0004 | 0.2951 | +0.0105 | +0.002 |
| drop_precip_30d | 0.3459 | -0.0217 | 0.7590 | -0.0066 | 59.8% | +0.1 | 0.9015 | -0.0003 | 0.2965 | +0.0119 | +0.000 |
| drop_geo_fe2o3 | 0.3480 | -0.0197 | 0.7662 | +0.0007 | 59.4% | -0.2 | 0.9032 | +0.0013 | 0.3037 | +0.0192 | +0.001 |
| drop_sgmc_metamorphic_carbonate | 0.3331 | -0.0345 | 0.7651 | -0.0005 | 57.8% | -1.9 | 0.9017 | -0.0002 | 0.3045 | +0.0200 | +0.003 |
| drop_pct_carbonate_resid | 0.3521 | -0.0156 | 0.7689 | +0.0033 | 58.6% | -1.0 | 0.9028 | +0.0009 | 0.3118 | +0.0273 | +0.000 |
| drop_baseflow_index | 0.3299 | -0.0377 | 0.7632 | -0.0023 | 60.5% | +0.8 | 0.9015 | -0.0004 | 0.3223 | +0.0378 | -0.003 |
| drop_sgmc_metamorphic_sedimentary_undifferentiated | 0.3484 | -0.0192 | 0.7660 | +0.0004 | 59.0% | -0.6 | 0.9019 | +0.0000 | 0.3277 | +0.0432 | +0.002 |
| drop_sgmc_melange | 0.3296 | -0.0381 | 0.7691 | +0.0035 | 59.8% | +0.1 | 0.9032 | +0.0014 | 0.3392 | +0.0547 | -0.002 |
| drop_pct_eolian_fine | 0.3365 | -0.0311 | 0.7642 | -0.0014 | 58.5% | -1.2 | 0.9014 | -0.0005 | 0.3406 | +0.0560 | +0.000 |

---

## The Core Discrepancy

Features where GKF5 and holdout DISAGREE on importance:

| Feature | GKF5 dR2_nat | Holdout dMedR2 | GKF5 says | Holdout says |
|---|---|---|---|---|
| drop_turb_Q_ratio | +0.0040 | -0.1017 | neutral | CRITICAL |
| drop_sgmc_unconsolidated_sedimentary_undifferentiated | +0.0020 | -0.1017 | neutral | CRITICAL |
| drop_collection_method | +0.0000 | -0.0651 | neutral | helpful |
| drop_flush_intensity | -0.0030 | -0.0542 | neutral | helpful |
| drop_sensor_family | +0.0010 | -0.0520 | neutral | helpful |
| drop_temp_instant | -0.0010 | -0.0454 | neutral | helpful |
| drop_turb_source | -0.0030 | -0.0413 | neutral | helpful |
| drop_sgmc_igneous_volcanic | +0.0050 | -0.0412 | neutral | helpful |
| drop_sgmc_metamorphic_volcanic | +0.0050 | -0.0385 | neutral | helpful |
| drop_developed_pct | -0.0010 | -0.0313 | neutral | helpful |
| drop_dam_storage_density | +0.0070 | -0.0308 | HARMFUL | helpful |
| drop_turb_below_detection | -0.0050 | -0.0292 | neutral | helpful |
| drop_sand_pct | -0.0010 | -0.0260 | neutral | helpful |
| drop_sensor_offset | -0.0010 | -0.0251 | neutral | helpful |
| drop_longitude | -0.0020 | -0.0242 | neutral | helpful |
| drop_sgmc_metamorphic_other | -0.0020 | -0.0175 | neutral | helpful |
| drop_Q_7day_mean | -0.0050 | -0.0130 | neutral | helpful |
| drop_precip_48h | -0.0040 | -0.0124 | neutral | helpful |
| drop_sgmc_metamorphic_serpentinite | +0.0070 | -0.0082 | HARMFUL | neutral |
| drop_sgmc_sedimentary_carbonate | +0.0080 | -0.0063 | HARMFUL | neutral |
| drop_sgmc_sedimentary_chemical | +0.0090 | -0.0037 | HARMFUL | neutral |
| drop_wwtp_all_density | +0.0020 | +0.0105 | neutral | harmful |
| drop_precip_30d | +0.0000 | +0.0119 | neutral | harmful |
| drop_geo_fe2o3 | +0.0010 | +0.0192 | neutral | harmful |
| drop_sgmc_metamorphic_carbonate | +0.0030 | +0.0200 | neutral | harmful |
| drop_pct_carbonate_resid | +0.0000 | +0.0273 | neutral | harmful |
| drop_baseflow_index | -0.0030 | +0.0378 | neutral | harmful |
| drop_sgmc_metamorphic_sedimentary_undifferentiated | +0.0020 | +0.0432 | neutral | harmful |
| drop_sgmc_melange | -0.0020 | +0.0547 | neutral | harmful |
| drop_pct_eolian_fine | +0.0000 | +0.0560 | neutral | harmful |

---

## Features Where Dropping Actually Helps on Holdout

| Feature | dMedR2 | dNSE | dMAPE | GKF5 dR2_nat |
|---|---|---|---|---|
| drop_pct_eolian_fine | +0.0560 | -0.0311 | -1.2 | +0.000 |
| drop_sgmc_melange | +0.0547 | -0.0381 | +0.1 | -0.002 |
| drop_sgmc_metamorphic_sedimentary_undifferentiated | +0.0432 | -0.0192 | -0.6 | +0.002 |
| drop_baseflow_index | +0.0378 | -0.0377 | +0.8 | -0.003 |
| drop_pct_carbonate_resid | +0.0273 | -0.0156 | -1.0 | +0.000 |
| drop_sgmc_metamorphic_carbonate | +0.0200 | -0.0345 | -1.9 | +0.003 |
| drop_geo_fe2o3 | +0.0192 | -0.0197 | -0.2 | +0.001 |
| drop_precip_30d | +0.0119 | -0.0217 | +0.1 | +0.000 |
| drop_wwtp_all_density | +0.0105 | -0.0110 | +0.3 | +0.002 |
| drop_sgmc_unconsolidated_undifferentiated | +0.0097 | -0.0117 | -1.2 | +0.003 |
| drop_fertilizer_rate | +0.0084 | -0.0243 | +1.0 | -0.004 |
| drop_sgmc_sedimentary_undifferentiated | +0.0067 | -0.0329 | -0.6 | +0.003 |

---

## Model Architecture

- CatBoost gradient boosting, Box-Cox lambda=0.2, Snowdon BCF
- Monotone constraints on turbidity_instant, turbidity_max_1hr
- Training: 320 sites, 32046 samples / Holdout: 76 sites, 5847 samples
- GKF5 = GroupKFold 5 folds (groups=sites, ~4 min/experiment)
- Holdout eval: Bayesian adaptation (Student-t, k=15), 3 split modes, disaggregated metrics

## Feature Categories (72 total)

- **Sensor (7):** turbidity_instant, turbidity_max_1hr, turbidity_std_1hr, conductance_instant, temp_instant, sensor_offset, days_since_last_visit
- **Hydrograph (7):** discharge_slope_2hr, rising_limb, Q_7day_mean, turb_Q_ratio, DO_sat_departure, flush_intensity, turb_below_detection
- **Temporal (2):** doy_sin, doy_cos
- **Weather (3):** precip_48h, precip_7d, precip_30d
- **Watershed (21):** longitude, drainage_area_km2, forest_pct, agriculture_pct, developed_pct, pct_carbonate_resid, pct_alluvial_coastal, pct_eolian_coarse, pct_eolian_fine, pct_colluvial_sediment, geo_fe2o3, clay_pct, sand_pct, soil_organic_matter, elevation_m, baseflow_index, wetness_index, dam_storage_density, wwtp_all_density, wwtp_minor_density, fertilizer_rate, nitrogen_surplus
- **Categorical (3):** collection_method, turb_source, sensor_family
- **SGMC Lithology (28):** Watershed bedrock type percentages

## Re-introduced Features (tested adding back 10 previously dropped)

None helped. Best was do_instant (+0.003 R2_native). discharge_instant (-0.006),
soil_permeability (-0.007), temp_mean_c (-0.009) actively hurt when re-added.

## Previous Expert Panel Findings (for context)

- Low-SSC overprediction (+121% bias) is sensor contamination (DOM, algae), not model failure
- Extreme underprediction (-37%) is particle size shift, not just sensor saturation
- Within-tier R2 is meaningless (guaranteed negative in narrow bands)
- NSE and R2 are identical for our computation (1-SS_res/SS_tot)
- Residuals are non-normal (skew=2.0, kurtosis=13.8)
