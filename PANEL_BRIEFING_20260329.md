# Expert Panel Briefing — 2026-03-29

## Project: murkml — Cross-Site SSC Prediction from Turbidity

### What This Model Does
CatBoost gradient boosting model predicts suspended sediment concentration (SSC, mg/L) from continuous turbidity sensor data + watershed characteristics across 396 USGS stream sites nationwide.

### Current Best Model: murkml-v4-boxcox
- **Transform:** Box-Cox lambda=0.2 with Snowdon BCF
- **Features:** 44 (41 numeric + 3 categorical: collection_method, turb_source, sensor_family)
- **Monotone constraints:** ON for turbidity_instant and turbidity_max_1hr
- **Training:** 357 sites (Tier C with StreamCat watershed attributes), 32,046 samples
- **Holdout:** 76 sites, 5,847 samples (never seen during training)

### Performance Summary
- **LOGO CV (357 folds):** R²(log)=0.718, R²(native) median=0.290, mean=-1.075
- **Holdout zero-shot:** R²(native)=0.472
- **Pooled R²(native):** 0.211 (all 32K predictions in one bucket)
- **Per-site R² distribution:** 15% excellent (>0.8), 20% good (0.5-0.8), 22% fair (0.2-0.5), 11% poor (0-0.2), 18% bad (-1 to 0), 15% catastrophic (<-1)

### Site Adaptation Curve (murkml-v4)
| N calibration samples | Median site R²(native) |
|---|---|
| 0 (zero-shot) | 0.472 |
| 1 | 0.397 (worse) |
| 2 | -0.012 (catastrophic) |
| 3 | 0.216 (worse) |
| 5 | 0.359 (worse) |
| 10 | 0.457 (barely recovers) |
| 20 | 0.487 (finally improves) |

Adaptation with <10 samples HURTS. 2-parameter linear correction in Box-Cox space overfits.

---

## What We Tested (30+ models across 5 experiments)

### Experiment A: Collection Method Split (7 models)
**Question:** 43% of samples are auto_point (ISCO), 29% depth_integrated, 11% grab, 17% unknown. These have a 4x SSC difference at the same sites. Should we split models?

**Result: NO.** Every specialist model performed WORSE than v4 on its own domain:
- auto_point specialist: R²=0.215 vs v4's 0.377 on auto_point data (-0.162)
- depth_integrated specialist: R²=0.389 vs v4's 0.548 on depth_integrated data (-0.159)
- grab specialist: R²=0.111 vs v4's 0.282 on grab data (-0.171)

Grouped models and "known-only" (exclude unknown) also didn't beat v4. The model already handles collection_method well as a feature (SHAP rank 3).

### Experiment B: Exclude Low-Quality Sites (3 models)
**Question:** 51 sites have R²<-1 (catastrophic). Are they poisoning the model?

**Result: Exclusion is cosmetic.** Removing bad sites improves pooled R² (fewer bad predictions in the average) but HURTS per-site R² (less training data):
- B1 (remove 42 catastrophic): pooled 0.312 (+0.101) but med site 0.273 (-0.017)
- B3 (remove 75 low-variability): pooled 0.324 (+0.113) but med site 0.236 (-0.054)
- B2 (remove 90 negative): med site R² drops to 0.128 — aggressive pruning is worst

SSC variability threshold analysis:
- Q1 (std 1-81 mg/L): median R² = -0.611 (model fails at calm sites)
- Q2 (std 82-205): median R² = 0.270
- Q3 (std 208-480): median R² = 0.452 (best tier)
- Q4 (std 488-12797): median R² = 0.382

### Experiment C: Flow-Stratified Metrics (analysis only)
**Question:** Is the model bad at storms?

**Result: No — MAPE is actually BEST at storms.**
- Low flow: MAPE=74.5%, within-2x=52%, R²=0.331
- Storm: MAPE=48.2%, within-2x=69%, R²=0.109

R² drops during storms because absolute values are large, but proportional accuracy improves. Per-site R² is negative at ALL flow regimes (median -0.07 to -0.39). Problem is site heterogeneity, not flow condition.

### Experiment D: Site Count Impact
**Quality-tiered (deterministic):**
- D1 (96 highest quality): pooled R²=0.386 (best), med site R²=0.158 (worst)
- D2 (194 good quality): pooled 0.315, med site 0.293 (best per-site)
- D4 (287 all): pooled 0.319, med site 0.266

**Random selection (5 seeds per size):**
| N sites | Pooled R² (mean±std) | Med Site R² (mean±std) |
|---|---|---|
| 100 | 0.281 ± 0.031 | 0.205 ± 0.083 |
| 150 | 0.286 ± 0.016 | 0.226 ± 0.089 |
| 200 | 0.316 ± 0.025 | 0.191 ± 0.071 |
| 250 | 0.305 ± 0.021 | 0.275 ± 0.064 |
| 287 (all) | 0.319 | 0.266 |

Per-site variance across random seeds is HUGE (std 0.064-0.089). More sites helps slightly and reduces variance, but site heterogeneity dominates.

### Experiment E: MERF (Mixed-Effects Random Forest)
**Question:** Does per-site random effects with shrinkage help?

**Result: Promising concept, but v4 wins on fair comparison.**
- MERF zero-shot holdout R²: 0.417 vs v4's 0.472 (v4 wins by 0.055)
- MERF had to drop 3 categorical features (collection_method = SHAP rank 3)
- Random effects confirm site heterogeneity: intercept std=0.360, slope std=0.179
- If MERF could use categoricals, it might win — but current package can't

---

## Key Diagnostic Findings

### SHAP Feature Importance (v4 model)
1. turbidity_instant: 2.544 (dominates)
2. turbidity_max_1hr: 0.394
3. **collection_method: 0.310** (3rd most important!)
4. turbidity_std_1hr: 0.203
5. longitude: 0.170
6. discharge_slope_2hr: 0.158
7. wetness_index: 0.153
...
turb_source: 0.000 (unused)

### What Predicts Per-Site R²? (Meta-Analysis)
| Feature | Spearman rho with site R² | Sig |
|---|---|---|
| SSC variability (std) | +0.342 | *** |
| SSC range | +0.323 | *** |
| Max SSC | +0.321 | *** |
| CV of SSC | +0.309 | *** |
| Turbidity variability | +0.296 | *** |
| turb_ssc_ratio | -0.253 | *** |
| % discrete turbidity | +0.222 | *** |
| % depth_integrated | +0.187 | *** |
| % unknown method | -0.141 | ** |
| N samples | +0.062 | NS |
| Drainage area | +0.040 | NS |
| Latitude/longitude | ~0.035 | NS |

Model performance is driven by DATA QUALITY and SITE CHARACTER, not geography or sample count.

### Catastrophic vs Excellent Sites
| Characteristic | Excellent (R²>0.8, 49 sites) | Catastrophic (R²<-1, 51 sites) |
|---|---|---|
| SSC std | 223 mg/L | 39 mg/L |
| Max SSC | 1,240 mg/L | 168 mg/L |
| % depth_integrated | 50% | 25% |
| % unknown method | 12% | **37%** |
| Dominant method | depth_integrated (51%) | **unknown (37%)** |

### Per-Site Turbidity-SSC Relationship
- Median per-site R² = 0.782 (strong within sites)
- Log-log slope: mean=0.92, std=0.22 (23% CV across sites)
- Watershed features CANNOT predict slopes (R²=-0.21)
- Percent fines (NWIS 70331): 88% of sites have data, doesn't correlate with slope
- All sites use same sensor type (pCode 63680, FNU infrared)

### Transform Comparison (24 experiments earlier)
- Box-Cox 0.2 vs log1p: identical on holdout (0.472 vs 0.460)
- Raw SSC: catastrophic (all configs R²≤0.012)
- KGE eval_metric: no improvement over RMSE early stopping
- Monotone helps Box-Cox but hurts log1p

---

## The Core Tension

The model explains 78% of variance WITHIN a site but only 21% ACROSS sites (pooled). The turbidity-SSC slope varies 23% between sites and nothing we've measured predicts which sites have which slopes.

The model works well at 35% of sites (R²>0.5) and catastrophically fails at 33% (R²<0). The failures are at low-variability sites (SSC std < 81 mg/L) with unknown collection methods.

Site adaptation with calibration samples should fix this, but currently adaptation with <10 samples makes things worse due to the 2-parameter correction overfitting.

---

## Questions for the Panel

1. Given everything above, what is the most promising path forward? We've tried splitting, excluding, flow-stratifying, more/fewer sites, and MERF. What haven't we tried?

2. The adaptation curve is broken at small N. The panel previously recommended shrinkage. Given that MERF with shrinkage (k=10) still couldn't fix N<5, what else could work?

3. Pooled R² and per-site R² tell opposite stories in every experiment. Which metric should we optimize for, and why?

4. The model's proportional accuracy is actually good (MAPE ~50%, within-2x ~60%). R²(native) is dragged down by a few extreme events. Are we measuring the wrong thing?

5. Is there a pattern in the results that we're missing? Something that connects the findings across experiments?

6. What would you do next if you were running this project?
