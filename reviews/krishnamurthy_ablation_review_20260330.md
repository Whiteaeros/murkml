# Ablation Methodology & Feature Selection Review — Dr. Ananya Krishnamurthy

**Date:** 2026-03-30
**Reviewer:** Dr. Ananya Krishnamurthy (Applied Environmental Statistics, 12 yr)
**Subject:** Phase 5 Ablation Results — Statistical Assessment per Panel Briefing (2026-03-30)

---

## Executive Summary

The ablation study has improved markedly since the early-stopping bug was caught and fixed. However, I have serious concerns about (a) the statistical reliability of single-feature ablation deltas on 76 holdout sites, (b) the use of median per-site R-squared as the sole decision metric, and (c) the cumulative risk of holdout overfitting from running 47+ ablation experiments on the same 76 sites. The proposed group ablation tests (A-D) are well-motivated but need variance estimates before any feature can be confidently added or removed. Below I address each item in the terms of reference.

---

## 1. Ablation Methodology Soundness

### Early-Stopped Models with GroupShuffleSplit

The fix is sound in principle. GroupShuffleSplit with groups=site_id prevents within-site leakage in the validation set, and early_stopping_rounds=50 is a reasonable regularization choice for CatBoost with 500 max iterations at lr=0.05.

**Concerns:**

1. **Single random split.** The `_save_quick_model` function uses `random_state=42` to produce exactly one GroupShuffleSplit (85/15 train/val). This means every ablated model is trained on the same 85% of training sites and validated on the same 15%. If those particular validation sites happen to favor or disfavor a specific feature, the early-stopping point will be systematically biased. With 320 training sites, 15% is roughly 48 sites for validation. That is a single draw from the possible site-level splits. I would strongly prefer 3-5 different random seeds for the GroupShuffleSplit, with the ablation delta reported as mean +/- std across seeds. This is the single most actionable recommendation in this review.

2. **Mismatch between GKF5 and quick-model training.** The GKF5 screening uses 5-fold GroupKFold (each fold trained on ~256 sites, validated on ~64 sites, averaged over 5 folds). The quick-model for holdout evaluation trains on ~272 sites (85% of 320) with early stopping against ~48 sites, then predicts on 76 holdout sites. These are different training set sizes, different regularization dynamics, and different effective model capacities. The GKF5 vs holdout disagreement may partly reflect this mismatch rather than true generalization differences.

3. **No variance estimate on holdout deltas.** Every dMedR-squared value in the briefing is a point estimate. Without confidence intervals, we cannot distinguish signal from noise. A delta of +0.008 (fertilizer_rate) could easily be within the noise band. Even the largest delta (-0.102 for turb_Q_ratio) needs a CI before we can be confident it is real.

### Recommendation

Run the top 5 most important features and top 5 candidates-to-drop through 5 random seeds (change only the GroupShuffleSplit random_state). If the ranking is stable across seeds, the methodology is trustworthy. If rankings shuffle dramatically, the single-seed results are unreliable and all decisions based on them should be revisited.

---

## 2. Are the Early-Stopped Models Trustworthy Now?

### The GKF5 vs Holdout Disagreement

The briefing correctly identifies a dramatic discrepancy. For example, `turb_Q_ratio` shows dR2_native = +0.004 on GKF5 (dropping it is neutral) but dMedR2 = -0.102 on holdout (dropping it is catastrophic). This is a 25x magnification from CV to holdout.

Several explanations are possible, and they are not mutually exclusive:

1. **GKF5 R-squared(native) is the wrong metric to compare.** GKF5 reports R-squared on native (untransformed) predictions, which is dominated by a handful of high-SSC sites. The holdout uses median per-site R-squared, which gives equal weight to every site. These metrics ask fundamentally different questions. The disagreement may be an artifact of metric mismatch, not model mismatch. To test this: compute median per-site R-squared from the GKF5 out-of-fold predictions and compare directly.

2. **Training set composition differs.** GKF5 trains on ~256 sites per fold; the quick model trains on ~272 sites. More importantly, the holdout sites are a fixed set of 76 sites that may be systematically different from the training sites (the Phase 4 review documented Eastern US dominance, few high-latitude sites, etc.). Features that help generalize to underrepresented geographies will look unimportant in GKF5 (where both train and validation are drawn from the same pool) but critical on holdout (where the sites are genuinely novel).

3. **Residual overfitting concern.** Even with early stopping, a single validation split can produce models that are overfit to the quirks of those 48 validation sites. If a dropped feature happens to decorrelate with the validation-site noise pattern, early stopping may select a different (worse) tree count, and the holdout delta reflects this instability rather than true feature importance.

### Additional Validation to Confirm Trustworthiness

- **Multi-seed ablation** (as above). This is the minimum.
- **External validation deltas.** You have 260 external sites (113 usable NTU sites). Run at least the top 5 ablated models through external validation and check whether the holdout ranking holds. If turb_Q_ratio is truly critical, dropping it should also degrade external R-squared.
- **Permutation importance on the holdout set.** Instead of retraining without a feature, randomly permute each feature's values within the holdout set and measure degradation. This is model-agnostic, requires no retraining, and provides a complementary importance ranking. If permutation importance agrees with the retrain-and-drop ablation, the signal is credible.

---

## 3. Proposed Group Ablation Tests (A-D): Statistical Evaluation

### Test A: SGMC Subgroups (A1-A6)

Six tests on correlated lithology subgroups. This is well-motivated: 28 SGMC features in a 72-feature model is 39% of the feature space, and many are likely collinear (e.g., a watershed that is 40% metamorphic is necessarily lower in other categories).

**Sample size concern:** Each ablation model is evaluated on 76 holdout sites. Many SGMC features are relevant only to sites in specific geologic settings. When you drop all metamorphic SGMC (A1), the effect may concentrate on the 10-15 holdout sites in metamorphic watersheds. A median per-site R-squared computed over 76 sites will heavily dilute this signal. Report not just the overall dMedR-squared but also the median delta for the geologically relevant subset of holdout sites (e.g., sites where the dropped SGMC category accounts for >20% of watershed area).

**Recommendation:** Tests A5 and A6 are the most informative (SGMC-only vs StreamCat-only). Prioritize those. A1-A4 are useful but lower priority.

### Test B: Combined Drop of 12 Individually Harmful Features

This is critical. Additivity of single-feature effects is almost never observed in tree-based models due to interaction effects and CatBoost's ability to reroute splits. The compound effect could be larger (if features were masking each other's noise) or smaller (if features were providing redundant but complementary information).

**Statistical concern:** Dropping 12 features simultaneously changes the model substantially. The early-stopping point will shift, the tree structure will differ, and the comparison to baseline is confounded by all these changes. There is no clean way to attribute the compound delta to individual contributions. This test answers a practical question (is the reduced feature set better?) but not a mechanistic one (which features were truly harmful?).

**Recommendation:** Run Test B. If the compound improvement exceeds the sum of individual improvements, there are negative interaction effects worth investigating. If it falls short, the individual deltas were partly absorbing shared variance.

### Test C: Precipitation Decomposition (C1-C3)

Three tests on highly correlated precipitation windows (48h, 7d, 30d). The group ablation showed that dropping all three helps median R-squared (+0.062) but destroys first-flush R-squared (-0.089) and extreme event prediction (top 1% R-squared drops from 0.109 to 0.005).

**Statistical concern:** The 43 samples in the >1000 FNU bin and the first-flush identification heuristic (precip_30d in bottom 25% AND flush_intensity in top 75%) mean these extreme-event metrics have very wide confidence intervals. The drop from 0.109 to 0.005 in top 1% R-squared is based on approximately 59 samples. Bootstrap that number — I suspect the 95% CI on the baseline top 1% R-squared includes 0.005.

**Recommendation:** C1-C3 are well-designed. In addition, compute event-conditional metrics with bootstrap CIs (site-level block bootstrap, 1000 replicates). If the first-flush degradation is real at the 95% level, keep precip_7d (the most likely first-flush proxy). If it is not significant, the weather features may be safe to drop.

### Test D: Old Geology vs SGMC Replacement

D1 and D2 are clean substitution tests. Good design.

**Concern:** D2 (keep only 5 individually helpful SGMC features) presupposes that the single-feature ablation rankings are reliable, which I have questioned above. If the rankings are noisy, the "5 helpful SGMC" selection is itself unstable.

### Multiple Comparisons

Across Tests A-D, you are running approximately 12 comparisons against the same baseline on the same 76 holdout sites. With no correction, the probability of at least one false positive at alpha=0.05 is 1 - 0.95^12 = 0.46. However, standard multiple comparison corrections (Bonferroni, Holm) assume you have p-values, which you do not currently compute.

**Recommendation:** You need variance estimates (from multi-seed runs) before multiple comparison corrections are even meaningful. Once you have them, use the Holm-Bonferroni correction for the family of tests within each group (A, B, C, D separately). Do not correct across groups unless you are making a single claim about "the best feature set" from all experiments.

---

## 4. Responses to the 8 Panel Questions

### Q1: Are these the right group ablation tests?

Yes, with two additions: (a) a combined sensor metadata group (collection_method + turb_source + sensor_family) should be tested as a unit, since all three encode measurement methodology rather than environmental physics; and (b) a "redundant hydrograph" test dropping discharge_slope_2hr + Q_7day_mean together, since these overlap conceptually with turb_Q_ratio and flush_intensity.

### Q2: Should we keep ALL weather features despite the median R-squared penalty?

Yes, keep them. The median R-squared penalty (+0.062 when dropped) is a distributional shift: weather features add noise for typical sites but are essential for the tail events that define real-world model utility. Dropping weather to improve the median is classic Goodhart's Law — optimizing the metric at the expense of the objective. However, I note that the evidence for weather's extreme-event importance rests on small samples (59 samples in top 1%). Confirm with bootstrap CIs.

My statistical recommendation: keep precip_7d and precip_48h, drop precip_30d tentatively (it is the most individually harmful weather feature on holdout, dMedR2 = +0.012, and is also the least physically direct proxy for event-scale dynamics). Test C3 will confirm or refute this.

### Q3: How to weigh the human infrastructure tradeoff?

The human infrastructure block (8 features) hurts median R-squared by -0.022 but improves extreme-event underprediction bias from -37.6% to -53.5% when dropped. Wait — dropping it makes underprediction WORSE (-53.5% vs -37.6%). So infrastructure features help with extreme events. Keep them.

From a statistical perspective, median R-squared gives equal weight to sites with 10 samples and sites with 200 samples. Extreme-event performance concentrates at high-sample, high-variability sites. The tradeoff is partly an artifact of the metric weighting. If you computed sample-weighted median R-squared, the infrastructure penalty would likely shrink.

### Q4: Is turb_Q_ratio importance (-0.102) suspicious?

Yes, it warrants scrutiny but is not necessarily leakage. turb_Q_ratio = turbidity / discharge is a physically meaningful ratio: it captures the sediment supply signal independent of flow volume. High turb_Q_ratio implies the watershed is producing turbidity disproportionate to flow (source-limited vs transport-limited erosion).

**Leakage check:** turb_Q_ratio is computed from turbidity_instant and discharge_instant, which are measured at prediction time. This is not leakage — these are legitimate input features. However, if turb_Q_ratio is essentially a proxy for the SSC/turbidity slope (which is what the model is trying to predict), it could be creating a circularity. Specifically: turb_Q_ratio varies with site and event, and the model may be learning "when turb_Q_ratio is high, predict high SSC/turbidity ratio" — which is tautological if the reason turb_Q_ratio is high is because SSC is high relative to turbidity.

**Test:** Compute the correlation between turb_Q_ratio and the target variable (SSC) across the training data. If Spearman rho > 0.7, the feature is likely doing most of the model's work and you have a fragility risk: any site where the turb_Q_ratio-SSC relationship breaks down will produce catastrophic errors. Also check: does turb_Q_ratio vary more between sites or within sites? If it is mostly a site-level constant, it is acting as a site identifier.

### Q5: Test keeping only the 5 helpful SGMC features?

Yes. This is Test D2 in the briefing, which I support. But see my caveat under Test D above: the "5 helpful" list is based on noisy point estimates. Run multi-seed ablation on those 5 features first to confirm they are genuinely helpful before building a reduced model around them.

### Q6: Re-introduced features all failed — accept or test in groups?

Accept the individual failures for now. The re-introduced features (do_instant, ph_instant, temp_at_sample, etc.) all showed dMedR2 near zero or slightly negative on holdout. With 76 sites and no variance estimates, "near zero" is indistinguishable from "no effect." Group testing is low priority unless you have a strong physical hypothesis for why a combination would be synergistic. I do not see such a hypothesis in the current feature set.

One exception: if ph_instant and do_instant together capture a biogeochemical state (e.g., eutrophication-driven turbidity), testing them jointly could be informative. But this is speculative.

### Q7: What other group ablation tests would you run?

1. **Sensor metadata group** (collection_method + turb_source + sensor_family): These are not environmental features. They encode measurement protocol. If the model requires them for generalization, that reveals a sensor-bias problem, not an environmental insight. Knowing their group importance is critical for interpreting what the model has learned.

2. **Site-identifier proxies** (longitude + elevation_m + drainage_area_km2 + baseflow_index + wetness_index): These static watershed attributes may be acting as site fingerprints rather than providing mechanistic information. Drop them as a group to test whether the model is memorizing site-specific patterns.

3. **Turbidity-derived features** (turbidity_instant + turbidity_max_1hr + turbidity_std_1hr + turb_Q_ratio + turb_below_detection): These are all computed from the turbidity time series. The core model is SSC = f(turbidity), so these are the primary predictors. Ablating them as a group tells you what fraction of model skill comes from the turbidity signal alone vs. auxiliary features. This is important for the paper narrative.

### Q8: When to stop ablating and declare the feature set final?

From a statistical standpoint, the stopping criterion is: **when no remaining ablation test has a delta that exceeds the estimated noise level.** You do not currently know the noise level because you have no variance estimates.

Practical stopping rule: (1) Run multi-seed ablation (5 seeds) on the current top-10 features and top-10 drop candidates. (2) Compute the standard deviation of dMedR-squared across seeds. (3) Any feature with |dMedR-squared| < 2 * std is "indeterminate" and should be decided on physical grounds, not statistics. (4) Apply the group ablation results (Tests A-D) to remove clearly harmful groups. (5) Freeze the feature set.

You are currently at 72 features. I expect the final set will be 50-60 features after removing the clearly harmful SGMC subtypes and a few noise features. Do not chase marginal improvements below the noise floor.

---

## 5. Median Per-Site R-squared as Primary Metric

### Is it appropriate?

Median per-site R-squared is a defensible choice for a multi-site model because it gives equal weight to each site regardless of sample count, and the median is robust to outlier sites (Alaska R-squared = -10.5 would destroy a mean).

### Blind Spots

1. **Insensitive to pooled performance.** The briefing already demonstrated this: dropping weather features improves median R-squared by +0.062 while destroying first-flush and extreme-event performance. Median per-site R-squared cannot see this because extreme events are a small fraction of samples at each site.

2. **Penalizes low-variability sites.** Phase 4 showed Q1 (low SSC variability) sites have R-squared ~ 0.09. These sites drag the median down regardless of model quality. The model would be better off predicting the site mean for Q1 sites, which would yield R-squared = 0 by definition. Including them in the median biases the metric downward and dilutes the signal from sites where the model is actually being tested.

3. **Ignores bias direction.** A site with R-squared = 0.5 and +50% bias is counted identically to a site with R-squared = 0.5 and -50% bias. Systematic underprediction at high SSC is far more consequential for sediment management than overprediction at low SSC, but median R-squared cannot distinguish them.

4. **Small-n sites are noisy.** With 17 holdout sites having <20 samples, the per-site R-squared at those sites has enormous variance. These noisy estimates contribute equally to the median.

5. **Not a standard metric.** No major hydrology journal uses median per-site R-squared as a primary metric. Reviewers will expect NSE, KGE, and PBIAS. Using a non-standard metric as the decision criterion for feature selection risks making decisions that do not translate to the metrics that will be reported in the paper.

### Recommendation

Use a multi-metric decision framework, not a single metric. For feature selection decisions, require that a feature change is supported by at least 2 of the following 4 metrics moving in the same direction:

- Median per-site R-squared (current primary)
- Pooled NSE (penalizes large errors at any site)
- KGE (captures correlation, variability bias, and mean bias separately)
- First-flush / extreme-event R-squared (task-critical performance)

A feature should only be dropped if median R-squared improves AND at least one of the other three does not degrade significantly. The weather feature result demonstrates exactly why a single metric is dangerous.

---

## 6. Holdout Overfitting Risk (72 features, 76 sites, 47+ experiments)

This is the most important methodological concern in the current study.

### The Problem

You have run 47 ablation experiments plus 4 group ablation experiments plus an upcoming 12 tests (A-D), evaluated on the same 76 holdout sites every time. Each experiment generates a dMedR-squared value. You are using these values to make feature inclusion/exclusion decisions. This is adaptive data analysis: the holdout set is being used not just for final evaluation but for iterative model selection.

Classical holdout theory assumes one evaluation. After k evaluations with adaptive choices, the effective sample size shrinks. Dwork et al. (2015, "The Reusable Holdout") showed that after k adaptive queries, the holdout set behaves as if it has n/k effective samples if no correction is applied. With 76 sites and ~60 adaptive queries, the effective sample size could be as low as 1-2 sites. This is an extreme bound, and the actual degradation depends on the correlation between queries, but the direction is unambiguous: you are eroding the holdout set's validity.

### Evidence It May Already Be Happening

The baseline holdout median R-squared has been reported at different values across documents:
- 0.472 (earlier model version, different holdout split)
- 0.285 (current 72-feature model)
- Values in between for various ablations

The declining baseline is partly real (more features, different model), but the fact that you are making feature decisions to maximize holdout dMedR-squared means the features kept in the model are those that happen to score well on these specific 76 sites. A new set of 76 sites might rank features differently.

### Mitigations

1. **External validation as the true holdout.** You have 113 usable NTU sites from WQP. Designate these as the final holdout and stop evaluating ablation experiments on them. Run external validation exactly once, at the end, on the final feature set. If you have already run external validation on intermediate models, that ship has sailed for those sites.

2. **Thresholdout.** If you must continue using the 76-site holdout adaptively, implement a thresholdout mechanism (Dwork et al., 2015): add Laplace noise to each reported metric with scale calibrated to the number of adaptive queries. This guarantees that the holdout remains valid at the cost of noisier individual readings.

3. **Bootstrap confidence intervals on the holdout.** For every dMedR-squared, compute a site-level block bootstrap (resample 76 sites with replacement, 1000 times, recompute median R-squared each time). This gives you a CI. If the CI includes zero, the feature change is not significant on this holdout, regardless of the point estimate. This does not fix the adaptive analysis problem, but it at least quantifies uncertainty on each individual decision.

4. **Cross-validation for feature selection, holdout for final confirmation only.** The cleanest design: use GKF5 (with the correct metric — median per-site R-squared, not R-squared native) to make all feature selection decisions. Use the holdout only to confirm the final model. This requires computing median per-site R-squared from GKF5 out-of-fold predictions, which should be straightforward.

### Bottom Line

The current workflow of running dozens of experiments on the holdout and using the results to choose features is a textbook example of adaptive overfitting. The fact that the external validation at N=10 matches holdout performance (R-squared ~0.5 vs ~0.5) is reassuring, but this may not survive further adaptation. I strongly recommend switching feature selection decisions to GKF5-based median per-site R-squared and reserving the holdout for a single final evaluation.

---

## Summary of Recommendations (Priority Order)

1. **Compute variance estimates.** Run 5-seed multi-seed ablation on the top 10 features and top 10 drop candidates. Without variance, all current deltas are point estimates of unknown precision.

2. **Stop using holdout for iterative feature selection.** Switch to GKF5-based median per-site R-squared for all feature decisions. Reserve the 76-site holdout for a single final evaluation.

3. **Adopt a multi-metric decision framework.** Require feature changes to be supported by at least 2 of 4 metrics (median per-site R-squared, pooled NSE, KGE, extreme-event R-squared).

4. **Bootstrap all reported holdout deltas.** Site-level block bootstrap, 1000 replicates. Report 95% CIs alongside point estimates.

5. **Validate turb_Q_ratio.** Compute its Spearman correlation with SSC and check within-site vs between-site variance ratio. If it is a near-tautological feature, the model is fragile.

6. **Proceed with Tests A5, A6, B, C3, and D2 as highest priority** from the proposed ablation plan.

7. **Run external validation on the final feature set only.** Do not use external sites for iterative decisions.

---

*Dr. Ananya Krishnamurthy*
*Applied Environmental Statistics*
