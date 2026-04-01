# Expert Panel Briefing — Final Feature Set Decision (2026-03-30)

## The Question

We have a 72-feature CatBoost model. Phase 5 ablation identified features that individually appear harmful. The question: **should we drop any features, and if so, which ones?**

Two analyses produced conflicting guidance. We need your independent judgment.

---

## The Data

### Baseline Model
- 72 features (44 original + 28 SGMC lithology)
- GKF5 on 254 training sites (excluding 76 validation + 36 vault)
- MedSiteR² = 0.2868, R²(log) = 0.749

### Single-Feature Ablation (corrected, early-stopped)
12 features where dropping individually improved MedSiteR²:

| Feature | dMedSiteR² | Category | Notes |
|---|---|---|---|
| pct_eolian_fine | +0.056 | StreamCat geology | Wind-deposited fine sediment % |
| sgmc_melange | +0.055 | SGMC | Tectonic melange rock % |
| sgmc_metamorphic_sedimentary_undiff | +0.043 | SGMC | Mixed meta/sed category |
| baseflow_index | +0.038 | StreamCat hydrology | Groundwater contribution |
| pct_carbonate_resid | +0.027 | StreamCat geology | Carbonate residuum soil % |
| sgmc_metamorphic_carbonate | +0.020 | SGMC | Metamorphic carbonate rock % |
| geo_fe2o3 | +0.019 | StreamCat geochemistry | Iron oxide in bedrock |
| precip_30d | +0.012 | Weather | 30-day precipitation |
| wwtp_all_density | +0.011 | Infrastructure | Wastewater plant density |
| sgmc_unconsolidated_undiff | +0.010 | SGMC | Unconsolidated sediment % |
| fertilizer_rate | +0.008 | Infrastructure | Agricultural fertilizer |
| sgmc_sedimentary_undiff | +0.007 | SGMC | Undifferentiated sedimentary % |

### Group Ablation Results (GKF5 MedSiteR²)

| Test | Dropped | MedSiteR² | Delta |
|---|---|---|---|
| Baseline | — | 0.2868 | — |
| Compound drop all 12 | The 12 above | 0.2988 | +0.012 |
| Only precip_7d | precip_48h + precip_30d | 0.2893 | +0.003 |
| Drop precip_30d only | precip_30d | 0.2843 | -0.003 |
| Drop old geology | 9 StreamCat geology features | 0.2833 | -0.004 |
| Drop ALL SGMC | 28 SGMC features | 0.2795 | -0.007 |

### Group Ablation — Physics Validation (holdout, from earlier round)

| Group Dropped | MedR² | First Flush R² | Top 1% R² | Extreme Underpred |
|---|---|---|---|---|
| Baseline | 0.285 | 0.394 | 0.109 | -37.6% |
| Legacy geology+soil (9) | 0.297 | 0.359 | 0.066 | -33.7% |
| Human land+infra (8) | 0.262 | 0.378 | 0.104 | -53.5% |
| Antecedent weather (3 precip) | 0.347 | 0.305 | 0.005 | -31.8% |

Note: Dropping weather improved median R² but destroyed first flush (-0.089) and extreme event prediction (0.109 → 0.005).

### 5-Seed Stability Check

Ran both 72-feature and 58-feature (drop all 12 + precip_48h + precip_30d) models across 5 random seeds:

| Config | Mean MedSiteR² | Std | Range |
|---|---|---|---|
| Baseline 72 features | 0.2898 | 0.0127 | 0.274 - 0.313 |
| Proposed 58 features | 0.2867 | 0.0090 | 0.273 - 0.300 |

Statistical tests (Wilcoxon signed-rank, paired by seed):
- MedSiteR²: p=0.81, Cohen's d=-0.28 (not significant, small effect)
- R²_native: p=0.81, Cohen's d=-0.26 (not significant, small effect)
- R²_log: p=0.63, Cohen's d=-0.52 (not significant, medium effect favoring 72 features)

Proposed model wins 2 of 5 seeds. Mean improvement: -0.003 (slightly worse).

Per-seed deltas range from +0.015 to -0.022 — dominated by seed variance.

---

## The Disagreement

**Position A: Keep all 72 features.**
- The 5-seed check shows no statistically significant improvement from dropping features.
- The burden of proof is on the change, and the change failed to prove itself.
- CatBoost handles irrelevant features reasonably well (tree-based, not linear).
- Risk of removing something that helps a subgroup we haven't specifically tested.

**Position B: Drop 12 features (the GIS/geology/infrastructure ones, keep weather).**
- If 72 and 58 are statistically indistinguishable, the simpler model wins (Occam's razor).
- Every feature is a deployment dependency (GIS processing, data pipelines).
- The 58-feature model has tighter variance (0.009 vs 0.013 std).
- Features like fertilizer_rate, geo_fe2o3, and sgmc_melange have no clear physical mechanism for turbidity-SSC prediction.
- Weather features (precip) are kept because group ablation proved they're essential for extreme events.

**Position C: Drop only 5-6 most confidently harmful features.**
- A middle ground: remove only features where individual ablation, group ablation, AND physics all agree.
- Candidates: sgmc_melange, sgmc_metamorphic_sedimentary_undiff, pct_eolian_fine, sgmc_metamorphic_carbonate, sgmc_sedimentary_undiff.

---

## What We Need From You

1. Given the statistical evidence (p=0.81, d=-0.28), which position do you support and why?
2. Is the tighter variance of the 58-feature model (std 0.009 vs 0.013) meaningful with only 5 seeds?
3. How should deployment complexity factor into a feature decision when performance is equivalent?
4. Are there features in the "drop" list that you would specifically argue to KEEP based on their physical or operational value?
5. Are there features NOT in the "drop" list that you think should be removed?
6. What is your recommended final feature set?
