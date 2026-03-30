# Final Feature Set Decision — Dr. Ananya Krishnamurthy

**Date:** 2026-03-30
**Reviewer:** Dr. Ananya Krishnamurthy (Applied Environmental Statistics, 12 yr)
**Subject:** Independent recommendation on final feature set per PANEL_BRIEFING_FEATURE_DECISION_20260330.md

---

## Executive Summary

The data do not support dropping features. The 5-seed stability check -- which I explicitly requested in my prior ablation review -- was conducted properly, and it delivers a clear verdict: the 58-feature model is not statistically distinguishable from the 72-feature model on any metric, and the point estimate actually favors the 72-feature model on 3 of 5 seeds and on mean performance. I support **Position A (keep all 72 features)**, with one narrowly scoped exception described below.

---

## Question 1: Given the statistical evidence (p=0.81, d=-0.28), which position do you support and why?

**Position A: Keep all 72 features.**

The statistical case is straightforward:

1. **The null hypothesis is "no difference."** The Wilcoxon p=0.81 means you cannot reject the null. Cohen's d=-0.28 is a small effect favoring the 72-feature model. The proposed change fails its own test.

2. **The burden of proof is on the change.** In model selection, the incumbent model retains its position unless there is positive evidence that the alternative is better. There is no such evidence here. The 58-feature model wins 2 of 5 seeds. That is worse than a coin flip.

3. **The R-squared(log) result is concerning.** Cohen's d=-0.52 favoring the 72-feature model on R-squared(log) is a medium effect size. With only 5 seeds this does not reach significance (p=0.63), but the direction is consistent: the 72-feature model is better at predicting log-transformed SSC, which is the regime where low-concentration accuracy matters. Dropping features appears to degrade performance in the low-SSC regime while providing no compensating gain elsewhere.

4. **Position B's argument from Occam's razor is misapplied.** Occam's razor applies when two models have genuinely equivalent performance and you choose the simpler one. But "not statistically distinguishable with n=5" is not the same as "equivalent." It means you do not have enough data to tell. In this situation, the correct response is to keep the model you have, not to make a change justified by absence of evidence against it. Absence of evidence is not evidence of absence.

5. **Position C (drop 5-6 "most confidently harmful") has the same problem.** There is no confidence here. The single-feature ablation deltas range from +0.007 to +0.056 on MedSiteR-squared. My prior review established that without multi-seed variance estimates on individual feature ablations, these are point estimates of unknown precision. The 5-seed check was done on the aggregate 72-vs-58 comparison, not on individual features. We do not know which of the 12 features are genuinely harmful vs. which are noise.

**Bottom line:** You ran the right experiment. It told you there is no justification for the change. Respect the result.

---

## Question 2: Is the tighter variance of the 58-feature model (std 0.009 vs 0.013) meaningful with only 5 seeds?

**No.**

The ratio of variances is 0.013^2 / 0.009^2 = 2.09. An F-test for equality of variances with df1=4, df2=4 gives F=2.09, p=0.45 (two-tailed). This is nowhere near significance. You would need approximately 25-30 seeds to detect a variance ratio of 2 at alpha=0.05 with reasonable power.

Moreover, 5 seeds is too few to reliably estimate a standard deviation. The 95% confidence interval on a standard deviation estimated from n=5 observations spans roughly [0.6*s, 2.9*s]. So the 72-feature model's true standard deviation could be anywhere from 0.008 to 0.038, and the 58-feature model's could be anywhere from 0.005 to 0.026. These intervals overlap almost completely.

The tighter variance is a suggestive observation, not a conclusion. It would need 20+ seeds to confirm. Given that the mean performance favors the 72-feature model, trading a possible (unconfirmed) variance reduction for a possible (also unconfirmed but directionally consistent) mean performance loss is not a good trade.

---

## Question 3: How should deployment complexity factor into a feature decision when performance is equivalent?

Deployment complexity is a legitimate engineering consideration, but it should be evaluated honestly, not used as a tiebreaker when the statistics are actually ambiguous.

**My framework:**

1. **If the performance difference is genuinely zero** (confirmed by a well-powered test, say 20+ seeds), deployment complexity should absolutely favor the simpler model. Every feature is a data pipeline dependency, a potential failure mode in production, and a documentation burden.

2. **If the performance difference is uncertain** (as it is now, with n=5 seeds and a directional trend favoring the larger model), deployment complexity should NOT override the statistical uncertainty. You risk removing features that help generalize to new geographies or extreme events -- effects that are precisely the hardest to detect with small seed counts.

3. **Practical assessment of the 12 features in question:** The features proposed for removal are mostly static GIS attributes (StreamCat geology, SGMC lithology) and infrastructure metrics (WWTP density, fertilizer rate). These are computed once per site from publicly available datasets. They are not real-time data dependencies. They do not require sensor maintenance, API calls, or time-series processing. The deployment cost of retaining them is a one-time GIS lookup per new site. This is trivial compared to the real-time data dependencies (turbidity, discharge, weather) that are already in the model.

**Conclusion:** The deployment argument for dropping these features is weak because they are static attributes, not real-time feeds. If they were real-time features requiring continuous data pipelines, the calculus would change.

---

## Question 4: Are there features in the "drop" list that you would specifically argue to KEEP?

Yes. Two features deserve specific defense:

### baseflow_index (dMedSiteR-squared = +0.038 when dropped)

Baseflow index is the ratio of baseflow to total streamflow. It is a first-order control on sediment dynamics: high-baseflow watersheds are groundwater-dominated (low event-driven sediment response), while low-baseflow watersheds are flashy (high event-driven sediment response). This is one of the most physically meaningful features in the entire model for predicting how a watershed responds to storm events.

The single-feature ablation showing that dropping it improves MedSiteR-squared by +0.038 likely reflects the metric's insensitivity to extreme events (as documented in the weather feature analysis). Baseflow index probably helps most at high-flow sites during events -- exactly the regime that MedSiteR-squared underweights. Before dropping it, check its impact on first-flush R-squared and extreme-event underprediction.

### precip_30d (dMedSiteR-squared = +0.012 when dropped)

The group ablation already proved that precipitation features are essential for extreme events (top 1% R-squared: 0.109 to 0.005 without weather). The briefing proposes keeping precip_7d while dropping precip_30d. But 30-day antecedent precipitation captures soil moisture state, which determines infiltration capacity and therefore runoff generation. In rain-snow transition watersheds (like north Idaho, where this model is likely to be deployed first), 30-day precipitation distinguishes between saturated soils (high runoff, high SSC) and dry soils (low runoff, low SSC) far better than 7-day precipitation does.

The group ablation test "Only precip_7d" (dropping precip_48h + precip_30d) showed MedSiteR-squared = 0.2893, essentially identical to baseline (0.2868). But this test was not evaluated on extreme-event metrics. Without that information, dropping precip_30d is a gamble on the assumption that precip_7d alone captures all weather-related extreme event signal. I am not confident in that assumption.

### The other 10 features

I do not have strong physical arguments for the remaining 10 features (pct_eolian_fine, sgmc_melange, etc.). They are geologically specific categories that may help at a handful of sites but are unlikely to be broadly important. However, the statistical evidence does not support dropping them either. The correct decision under uncertainty is inaction.

---

## Question 5: Are there features NOT in the "drop" list that you think should be removed?

No, not based on current evidence.

My prior review flagged turb_Q_ratio as a feature warranting scrutiny (potential circularity risk), but that is a separate investigation, not a removal recommendation. turb_Q_ratio showed dMedSiteR-squared = -0.102 when dropped -- by far the most important feature -- and removing it without understanding why it matters would be reckless.

I also previously suggested testing sensor metadata features (collection_method, turb_source, sensor_family) as a group. If that test revealed they were encoding sensor bias rather than environmental physics, I would want them flagged for the paper narrative but not necessarily removed (sensor bias correction is a valid model function in a multi-sensor deployment context).

No feature in the current 72 has shown evidence strong enough to warrant removal. The appropriate action is to keep all 72 and move on to validation.

---

## Question 6: What is your recommended final feature set?

**All 72 features. No changes.**

### Rationale

The research team has now invested substantial effort in ablation analysis. The results are clear:

- No single feature removal produces a statistically significant improvement after accounting for seed variance.
- The compound removal of 12 features produces a non-significant change (p=0.81, d=-0.28) that trends in the wrong direction (mean MedSiteR-squared: 0.2867 vs 0.2898 baseline).
- The 58-feature model wins 2 of 5 seeds.
- The R-squared(log) metric shows a medium-sized effect favoring 72 features.

There is no statistical justification for any feature removal. The ablation study served its purpose: it confirmed that no features are clearly harmful, and it identified which features are most and least important. That information is valuable for interpretation and for the paper narrative, but it does not support changing the model.

### One narrow exception (conditional)

If the team runs individual multi-seed ablation on baseflow_index and precip_30d and confirms they are genuinely neutral or harmful across all metrics (MedSiteR-squared, first-flush R-squared, extreme-event R-squared, KGE), then and only then would I support dropping them. But this has not been done, and I do not recommend investing additional compute in it. The current 72-feature model is the model. Finalize it and move to validation.

### What to do next

1. **Freeze the feature set at 72.** Stop running ablation experiments.
2. **Run the 36-site vault evaluation exactly once.** This is your clean holdout. Do not run intermediate models against it.
3. **Report the ablation analysis in the paper** as a robustness check demonstrating that the feature set is stable. The fact that removing 12 features produces statistically indistinguishable results is itself a finding: the model is not brittle, and CatBoost is handling the feature space appropriately.
4. **Report feature importances from SHAP or CatBoost native importance** for interpretation, not for feature selection. The two are different tasks with different standards of evidence.

---

## Summary Table

| Question | Answer |
|----------|--------|
| Q1: Which position? | **Position A (keep 72).** p=0.81 means no evidence for change. |
| Q2: Is tighter variance meaningful? | **No.** F-test p=0.45. Need 25+ seeds to detect this. |
| Q3: Deployment complexity? | **Not a tiebreaker here.** The 12 features are static GIS attributes with trivial deployment cost. |
| Q4: Keep any "drop" candidates? | **Yes: baseflow_index and precip_30d** have strong physical justification. But the real answer is keep all 72. |
| Q5: Remove any non-listed features? | **No.** No evidence supports any removal. |
| Q6: Final feature set? | **All 72 features, unchanged.** Freeze and proceed to validation. |

---

*Dr. Ananya Krishnamurthy*
*Applied Environmental Statistics*
