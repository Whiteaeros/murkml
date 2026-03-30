# Feature Set Decision Review — Dr. Marcus Rivera
## USGS Water Resources Division (ret.), Sediment Transport & Surrogate Methods
### 2026-03-30

---

## Summary Recommendation

**Position A: Keep all 72 features.** No changes to the feature set at this stage.

I am not going to sugarcoat this. The data does not support dropping features. Every attempt to justify removal is either aesthetic preference or premature optimization of deployment complexity that does not yet exist. Here is my reasoning on each question.

---

## Question 1: Given the statistical evidence (p=0.81, d=-0.28), which position do you support and why?

**Position A. Keep 72.**

p=0.81 means the 58-feature model is statistically indistinguishable from the 72-feature model. Position B argues that when two models tie, simpler wins. That logic is correct in a textbook, but these models are not tied — the 72-feature model has a higher mean MedSiteR² (0.2898 vs 0.2867) and a higher mean R²(log) with a medium effect size (d=-0.52) favoring the fuller model. The "tie" only holds if you ignore direction.

More critically: the group ablation physics validation table should end this debate. Dropping the legacy geology/soil group improved median R² slightly (+0.012) but degraded first flush R² from 0.394 to 0.359 and crushed Top 1% R² from 0.109 to 0.066. That is a 40% degradation in extreme event capture. For anyone who has actually operated a surrogate monitoring site during a major runoff event, that is not a tradeoff you make voluntarily.

The burden of proof is on the change, and the change failed. This is a 254-site model. We do not have the statistical power to detect small subgroup effects from 5 seeds. Features that look useless in aggregate may be carrying specific site clusters that we have not examined.

---

## Question 2: Is the tighter variance of the 58-feature model (std 0.009 vs 0.013) meaningful with only 5 seeds?

**No. It is noise.**

Five seeds is not enough to draw conclusions about variance. You have 5 data points. The standard deviation of a standard deviation estimate from n=5 is enormous — roughly sigma/sqrt(2n) gives you error bars wider than the difference you are trying to interpret.

Furthermore, 0.013 vs 0.009 in MedSiteR² standard deviation across seeds is operationally meaningless. Both are within 5% of the mean. If you want to claim tighter variance as an advantage, run 25+ seeds. Until then, this is a distraction.

---

## Question 3: How should deployment complexity factor into a feature decision when performance is equivalent?

**It should factor in, but not yet, and not this way.**

I have deployed surrogate regression models at dozens of USGS streamgages. Deployment complexity is real. Every additional data dependency is a point of failure — a server goes down, a dataset gets reformatted, a GIS layer gets deprecated.

But here is the thing: all 72 of these features are static catchment attributes plus weather data. They are computed once per site at setup time, not streamed in real-time. The marginal deployment cost of 14 extra static features is near zero. You are not maintaining 14 additional real-time data feeds. You are looking up 14 extra values from a GIS database one time when you onboard a new site.

If these were 14 additional real-time sensor inputs, I would weigh deployment complexity heavily. For static catchment descriptors, this argument has almost no weight.

The time to simplify for deployment is when you have a production system with actual users reporting actual pain points. Not during model development when you have 254 training sites and need every bit of generalization power you can get.

---

## Question 4: Are there features in the "drop" list that you would specifically argue to KEEP?

**Yes. Three stand out.**

1. **baseflow_index** (dMedSiteR² = +0.038 when dropped). This is one of the most physically meaningful features in the entire set. Baseflow index controls the fraction of streamflow coming from groundwater vs. surface runoff. It directly determines how responsive a stream is to precipitation events, which directly determines sediment transport dynamics. The fact that dropping it slightly improves median R² likely means it is correlated with other hydrologic features and CatBoost is splitting on it in suboptimal ways at some sites — not that it lacks information. I would never remove this feature from a sediment model.

2. **precip_30d** (dMedSiteR² = +0.012 when dropped). Antecedent moisture conditions are foundational to sediment availability and transport. The physics validation table shows exactly what happens when you remove weather: extreme event prediction collapses. precip_30d captures soil saturation state. Keep it.

3. **pct_eolian_fine** (dMedSiteR² = +0.056 when dropped). This is the largest individual improvement from dropping, which makes it suspicious. But eolian fine sediment deposits are a direct source of easily mobilized fine particles. In the western US, loess deposits are major contributors to turbidity. The large ablation delta suggests this feature may be interacting badly with the SGMC lithology features (collinearity in geology representation), not that it lacks physical relevance. The correct response is to investigate the interaction, not delete the feature.

---

## Question 5: Are there features NOT in the "drop" list that you think should be removed?

**No.**

I am not going to recommend removing features that passed ablation screening. The ablation already tested every feature individually. If a feature was not flagged, there is no evidence-based reason to remove it.

If anything, I would want to see the SHAP importance rankings for the bottom 10 features by mean absolute SHAP value. If features have near-zero SHAP across all sites AND failed to show up in ablation, those would be candidates for a future simplification pass. But that is a separate analysis, not something to decide based on the current briefing.

---

## Question 6: What is your recommended final feature set?

**All 72 features. No changes.**

The evidence for removal is weak (p=0.81, negative mean delta, degraded extreme events). The evidence for keeping is strong (physics validation, subgroup risk, near-zero deployment cost for static features). This is not a close call.

If the team wants to revisit this after the model is validated on the 76-site holdout and the 36-site vault, and if specific features show zero contribution across all validation sites, then we can have the simplification conversation with real evidence. Right now, we are optimizing based on noise.

---

## Additional Note

The one thing in this briefing that genuinely concerns me is the Top 1% R² = 0.109 at baseline. That is low for extreme events regardless of feature set. Before spending more time on which features to drop, I would investigate why extreme events are so poorly captured and whether the loss function or training data distribution is the bottleneck. Dropping features is not going to fix a 0.109 R² on the events that matter most.

---

*Dr. Marcus Rivera*
*Review submitted 2026-03-30*
