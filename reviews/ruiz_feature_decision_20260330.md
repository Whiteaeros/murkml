# Feature Set Decision Review — Dr. Catherine Ruiz
## Sediment Transport Physics Assessment

**Date:** 2026-03-30
**Reviewer:** Dr. Catherine Ruiz, sediment transport researcher (15 yr experience)
**Material reviewed:** PANEL_BRIEFING_FEATURE_DECISION_20260330.md, 5-seed stability data, group ablation results, my prior Phase 5 ablation review

---

## Position Statement

I support **Position A: Keep all 72 features**, with a caveat. The evidence does not justify removal, but I would flag 5 features for monitoring and potential removal after the next round of validation data comes in.

Here is my reasoning, question by question.

---

## Question 1: Given the statistical evidence (p=0.81, d=-0.28), which position do you support and why?

**Position A. Keep all 72 features.**

The 5-seed stability check is the most important piece of evidence in this briefing, and it resolves the disagreement clearly: the compound drop of 12 features produces no statistically significant improvement. The p-value of 0.81 is not borderline — it is emphatically null. Cohen's d of -0.28 is small and in the *wrong direction* (favoring 72 features, not 58). The proposed 58-feature model wins only 2 of 5 seeds.

Position B argues "if they are indistinguishable, choose simpler." I reject this framing for two reasons:

**First, the models are not indistinguishable — the 72-feature model is slightly better on every metric except variance.** The mean MedSiteR-squared favors 72 features (0.2898 vs 0.2867). R-squared(log) shows a medium effect size (d=-0.52) favoring 72 features. "Not significant" does not mean "equivalent." It means we lack power to distinguish them, which with 5 seeds we clearly do. The conservative action when you cannot distinguish two options and one of them involves irreversible information loss is to retain the information.

**Second, Occam's razor applies to models, not feature sets in tree ensembles.** Occam's razor penalizes unnecessary *model complexity* — parameters that increase variance without improving fit. But CatBoost does not use all 72 features equally. It uses features selectively, giving near-zero importance to irrelevant ones. The "complexity" of carrying 14 extra features in CatBoost is not the same as carrying 14 extra coefficients in a linear regression. The tree ensemble already implements its own internal feature selection. The ablation results confirm this: the 72-feature model has functionally identical performance to the 58-feature model because CatBoost is already ignoring the "harmful" features in most splits.

**The burden of proof is on the change.** The change failed to prove itself. Keep all 72.

---

## Question 2: Is the tighter variance of the 58-feature model (std 0.009 vs 0.013) meaningful with only 5 seeds?

**No. It is not meaningful.**

With 5 observations, the standard deviation of the standard deviation is enormous. The sampling distribution of variance from a sample of n=5 follows a chi-squared distribution with 4 degrees of freedom. The 95% confidence interval for the true standard deviation, given an observed std of 0.013, ranges from approximately 0.008 to 0.032. The observed std of 0.009 for the 58-feature model falls well within this interval. We cannot distinguish these variances.

Furthermore, the range statistic tells the same story. The 72-feature range is 0.274-0.313 (span = 0.039). The 58-feature range is 0.273-0.300 (span = 0.027). But the minimum of both distributions is nearly identical (0.274 vs 0.273), which means the entire variance difference is driven by the 72-feature model having one seed with an unusually good result (0.313). Removing one lucky seed and calling it "tighter variance" is not a statistical argument.

To make a credible claim about variance reduction, you would need at minimum 20-30 seeds. At 5 seeds, the observed variance difference is noise.

---

## Question 3: How should deployment complexity factor into a feature decision when performance is equivalent?

Deployment complexity is a legitimate concern, but it should not override statistical and physical reasoning when the evidence is this weak.

**The deployment argument for dropping features is strongest when:**
- A feature requires a fundamentally different data source (different agency, different API, different spatial resolution)
- A feature has high missingness in production (many sites will not have it)
- A feature requires real-time computation that adds latency
- The performance cost of including the feature is clearly negative

**For the 12 candidate features, the deployment burden is low:**
- The SGMC features (melange, metamorphic_sedimentary_undiff, etc.) are static GIS lookups. You compute them once per site during onboarding. They add zero runtime cost and near-zero pipeline complexity. The GIS processing pipeline already handles 28 SGMC features; dropping 5-6 does not simplify the pipeline in any meaningful way. You still need the SGMC layer, the spatial join, and the column extraction.
- pct_eolian_fine, pct_carbonate_resid, and geo_fe2o3 come from StreamCat, which is already a dependency. Dropping 3 of dozens of StreamCat columns does not eliminate the StreamCat dependency.
- precip_30d comes from the same weather data pipeline as precip_48h and precip_7d. Dropping one precipitation window does not simplify the pipeline.
- wwtp_all_density and fertilizer_rate are StreamCat columns. Same argument.
- baseflow_index is a static watershed characteristic from StreamCat.

**Net deployment simplification from dropping all 12: effectively zero.** You would still need every data source, every API call, every spatial join. You would just extract 12 fewer columns from datasets you are already downloading. This is not a meaningful reduction in deployment complexity.

If any of these features required a *unique* data source that nothing else in the model uses, the deployment argument would be stronger. None of them do.

---

## Question 4: Are there features in the "drop" list that you would specifically argue to KEEP based on their physical or operational value?

**Yes. Three features deserve explicit retention arguments:**

### baseflow_index (+0.038 when dropped individually)

Baseflow index is the fraction of streamflow derived from groundwater. This is a first-order control on watershed sediment dynamics:

- High-baseflow watersheds have stable flow regimes with less flashy event responses. Sediment mobilization is dominated by gradual bank erosion and channel processes, producing consistent particle populations with predictable turbidity-SSC relationships.
- Low-baseflow watersheds are flashy, event-driven systems where surface erosion dominates during storms. Particle populations shift dramatically between baseflow and stormflow.
- The baseflow index directly modulates how the model should interpret turb_Q_ratio. A high turb_Q_ratio in a high-baseflow watershed has a different physical meaning than the same ratio in a low-baseflow watershed.

The individual ablation showed +0.038 improvement when dropped, but the group ablation showed that dropping all 9 StreamCat geology features (which includes baseflow_index's correlated partners) actually *hurt* performance (-0.004). This suggests baseflow_index's individual harm is an artifact of correlation with other features that compensate when it is removed.

**My position: retain baseflow_index.** Its individual ablation signal is misleading because it is correlated with other hydrologic features. It encodes a physically distinct mechanism (groundwater contribution) that no other feature captures directly.

### precip_30d (+0.012 when dropped individually)

I argued this extensively in my prior review. precip_30d is the primary antecedent moisture indicator and first-flush discriminator. The group ablation confirms that dropping it individually hurts median performance (-0.003 from group ablation row "Drop precip_30d only"). The individual ablation says it helps to drop it; the group ablation says it hurts. This contradiction means the individual signal is unreliable. Keep it. First flush and extreme events depend on it.

### geo_fe2o3 (+0.019 when dropped individually)

Iron oxide content in bedrock controls the color and optical properties of weathering products. Iron-rich soils and sediments scatter light differently from iron-poor ones — specifically, iron oxides are strong absorbers at blue wavelengths, which affects turbidity sensor readings (most optical sensors use near-infrared, but some use broadband white light or 860nm where iron still has measurable effects on reflectance spectra of suspended particles).

The physical mechanism is real but indirect. I would not fight hard for this one, but I note that it is a static GIS lookup with zero deployment cost. The risk of keeping it (minor overfitting noise) is lower than the risk of removing it (losing a real but subtle optical correction).

---

## Question 5: Are there features NOT in the "drop" list that you think should be removed?

**No confident removals, but one feature to investigate:**

I do not have the full feature list with individual ablation scores for all 72 features, only the 12 that appeared harmful. Without seeing the full ablation table, I cannot identify features that are merely useless (delta near zero) versus actively helpful. Features with near-zero individual ablation impact AND no physical justification are the most logical candidates for removal, but I need the data to identify them.

One feature I would *investigate* (not necessarily remove) is **turb_below_detection**. This is a binary indicator for whether turbidity is below the sensor's detection limit. It carries important censoring information, but if it is correlated with low-SSC conditions where the model already performs poorly, it may be acting as a "this sample is unreliable" flag that the model leans on to excuse poor predictions. Check the partial dependence plot: if turb_below_detection=1 causes the model to predict near-zero SSC regardless of other features, it may be a shortcut that prevents the model from learning the low-turbidity regime properly.

---

## Question 6: What is your recommended final feature set?

**Retain all 72 features for the current model version.**

My reasoning:

1. **The statistical evidence does not support removal.** p=0.81, d=-0.28. The proposed change is indistinguishable from noise.

2. **The deployment simplification is negligible.** No unique data sources are eliminated by dropping the 12 features.

3. **The physical risks of removal are asymmetric.** Several of the "harmful" features (baseflow_index, precip_30d, geo_fe2o3) encode real physical mechanisms. Removing them risks degrading performance on subgroups we have not specifically tested (e.g., groundwater-dominated watersheds, iron-rich lithologies, spring first-flush events in snowmelt regions). We have tested median, first flush, and top 1% — but we have not tested these specific physical subgroups.

4. **CatBoost's internal feature selection is already handling the noise.** The fact that the 72-feature and 58-feature models perform identically means CatBoost is already suppressing the harmful features. Explicit removal provides no additional benefit.

5. **The variance argument is not credible at n=5 seeds.** The apparent tighter variance of the 58-feature model is within sampling noise.

**However, I recommend the following for the next model iteration:**

- Run a 30-seed stability comparison between 72 and 58 features. If the variance reduction holds with adequate statistical power, reconsider Position B.
- For publication, report both the 72-feature and a physics-informed reduced feature set (my ~17-20 feature set from the prior review) as a sensitivity analysis. This demonstrates that the model is not dependent on noisy features, which reviewers will want to see.
- Monitor the 12 individually harmful features' importance scores across future training runs as the site count grows. If they remain near-zero importance consistently, they become safe to prune in a future version.

---

## Summary Table

| Feature | Individual dMedSiteR-squared | My Recommendation | Reasoning |
|---|---|---|---|
| pct_eolian_fine | +0.056 | Keep (low confidence) | Static GIS, zero deployment cost; may matter for loess-dominated watersheds |
| sgmc_melange | +0.055 | Keep (low confidence) | Physically uninformative but harmless in CatBoost |
| sgmc_metamorphic_sedimentary_undiff | +0.043 | Keep (low confidence) | Grab-bag category, but no cost to retain |
| baseflow_index | +0.038 | **Keep (high confidence)** | Physically essential; individual signal contradicted by group ablation |
| pct_carbonate_resid | +0.027 | Keep (moderate confidence) | Carbonate chemistry affects dissolved/particulate partitioning |
| sgmc_metamorphic_carbonate | +0.020 | Keep (low confidence) | Redundant with other carbonate features but harmless |
| geo_fe2o3 | +0.019 | Keep (moderate confidence) | Iron oxide controls particle optical properties |
| precip_30d | +0.012 | **Keep (high confidence)** | First flush and antecedent moisture; group ablation contradicts individual |
| wwtp_all_density | +0.011 | Keep (low confidence) | Nutrient/biological turbidity source; marginal |
| sgmc_unconsolidated_undiff | +0.010 | Keep (low confidence) | Distinct from the important unconsolidated_sedimentary_undiff |
| fertilizer_rate | +0.008 | Keep (low confidence) | Agricultural nutrient loading proxy; marginal |
| sgmc_sedimentary_undiff | +0.007 | Keep (low confidence) | Small effect, harmless to retain |

**Bottom line: Do not drop features when the evidence for dropping them is this weak. The conservative, physically justified position is to retain the full feature set and let CatBoost continue to perform its own internal feature selection. Revisit with more statistical power (30+ seeds) or after expanding to more sites, where subgroup effects may become detectable.**

---

*Dr. Catherine Ruiz*
*Sediment Transport & Erosion Mechanics*
