# Editorial Assessment: Cross-Site Suspended Sediment Estimation from Continuous Turbidity Using Gradient Boosting

**Reviewer:** Dr. Amara Osei, Associate Editor, Water Resources Research
**Manuscript:** wrr_draft_v1.md
**Date:** 2026-04-02

---

## 1. Editorial Verdict

**MAJOR REVISION**

This manuscript presents a genuinely novel contribution -- the first continental-scale cross-site SSC model using continuous turbidity -- and the sediment load validation against USGS 80155 records is compelling. However, the paper has structural problems, several overclaims, inconsistencies in reported numbers, and gaps in the analysis that prevent acceptance in its current form.

The core science is sound and the problem is real. The 30% failure rate is honestly reported, which I respect. The load comparison at Brandywine is the strongest result and should anchor the entire paper. But the draft tries to be simultaneously a methods paper, a benchmarking paper, and a practical deployment paper, and does not fully succeed at any of these. With focused revision -- primarily restructuring results around disaggregated metrics, tightening claims to match evidence, and adding missing analyses -- this can reach WRR quality.

I would not accept this paper if the pooled metrics were leading the results. The draft does use MedSiteR2 as primary, which is correct, but the presentation still buries some of the most important findings (the R2 < 0 sites, the geology story, the collection method confound) in favor of headline numbers.

---

## 2. Scientific Contribution Assessment

### Does this advance understanding or is it "just another ML paper"?

This is NOT just another ML paper, and I want to be clear about that. The paper makes three contributions that are genuinely new:

1. **No prior work uses continuous turbidity in a cross-site ML framework for SSC.** Every published cross-site water quality model (Song et al. 2024, Zhi et al. 2024, Kratzert et al. 2019) uses discharge and hydrometeorology. Turbidity is the most direct SSC surrogate and it is remarkable that nobody has done this at scale. This alone is publishable.

2. **The sediment load validation against USGS 80155** is, to my knowledge, unprecedented for an automated cross-site model. Matching the USGS published record within 2.6% at Brandywine without site-specific calibration is a striking result. This is not just R2 on holdout samples -- it is an end-to-end operational test against the gold standard.

3. **The site heterogeneity characterization** (between-site CV 3.2x larger than within-site CV, geology as primary driver) provides a quantitative answer to a question the sediment community has discussed qualitatively for decades.

### Testable hypothesis

The hypothesis is stated clearly in the introduction: "adding continuous turbidity as a primary input to a cross-site model will substantially improve SSC estimation over discharge-only approaches." This is testable, falsifiable, and directly addressed by the results. Good.

However, the paper also implicitly tests a second hypothesis -- that watershed geology controls cross-site transferability -- that should be explicitly stated. This is arguably the more important scientific finding.

### Comparison to key papers

- **Song et al. (2024):** Direct comparison is complicated because Song et al. predict SSC from discharge at sites *without* turbidity, while this paper predicts SSC from turbidity at sites *with* sensors. The draft acknowledges this correctly (Section 5.5) but undersells the comparison. Song et al. MedR2 = 0.55 at gauged sites (with site-specific data in training); this paper's zero-shot MedSiteR2 = 0.40 at truly ungauged sites. The comparison is apples-to-oranges, but the Spearman = 0.907 vs. whatever Song et al. report for ranking ability would be valuable if available.

- **Zhi et al. (2024):** Not directly comparable (water quality broadly, not SSC specifically), but the paper should cite it as evidence of the general paradigm.

- **Kratzert et al. (2019):** The CatBoost vs. LSTM comparison is implicitly raised but never tested. A reviewer WILL ask why you did not use an LSTM. This needs to be addressed in the discussion (see Section 5, Reviewer Attack Surface).

### Is the contribution sufficient for WRR?

Yes, IF the paper is properly restructured. The combination of (1) novel input data type for cross-site prediction, (2) operational load validation, and (3) honest characterization of failure modes exceeds the bar for WRR. But the current draft dilutes these contributions by trying to cover too much ground.

---

## 3. Paper Structure Critique

### Abstract

The abstract is good but slightly too long and tries to pack in every result. The opening sentence is effective. The Bayesian adaptation result is buried. The 30% R2 < 0 finding -- which is one of the paper's most interesting contributions -- appears near the end.

**Recommendation:** Lead with the problem, the turbidity novelty, the Brandywine result (strongest evidence), then the heterogeneity finding. Move adaptation and CQR failure to later. Cut the abstract to ~250 words.

### Plain Language Summary

Well written. Accessible without condescension. One issue: "ranking sediment concentrations correctly 91% of the time" is a misstatement of what Spearman rho = 0.907 means. Spearman is a correlation coefficient, not a percentage of correct rankings.

### Introduction

Strong. The bottleneck framing (4,000 turbidity sensors, fraction with SSC regressions) is compelling and provides immediate practical motivation. The contributions list is clear. One weakness: the introduction does not preview the negative results (30% failure rate), which means the reader is set up for a success story and then surprised. Previewing the limits in the introduction strengthens credibility.

### Methods (Section 3)

Generally reproducible with the following gaps:

1. **Feature count discrepancy.** The abstract says "137 features." Table 1 says 137. Section 3.2 says "137 input features." But the RESULTS_LOG and DECISION_LOG are clear that only 72 features are active after ablation, with 65 dropped. The paper says this in a table footnote ("65 features were pruned after ablation analysis, leaving 72 active features") but this is buried. A reader will be confused about whether the model uses 137 or 72 features. This MUST be clarified prominently in the methods.

2. **Box-Cox BCF.** The dual BCF approach (BCF_mean for loads, BCF_median for individual predictions) is scientifically defensible but needs more justification. Using two different BCFs for two different purposes creates an impression of post-hoc optimization. Explain the statistical rationale more clearly.

3. **Bayesian adaptation.** The prior specification (Student-t, k=15, df=4) is stated but not justified. Why these specific values? Were they tuned? If so, on what data?

4. **Event detection algorithm.** The storm event detection (1.5x 7-day rolling minimum, 6-hour minimum duration, 24-hour separation) is described but not validated. How sensitive are the load comparison results to these thresholds?

### Results (Section 4)

The results are presented in roughly the right order (transform selection, feature importance, zero-shot, adaptation, benchmark, external, loads, uncertainty), but the section is too long and mixes findings of vastly different importance.

**Major problem:** The results section leads with the transform sweep (Section 4.1) and feature importance (Section 4.2). These are *methods decisions*, not *results*. Move them to methods or supplementary. The results should lead with the main finding: cross-site performance and where it works/fails.

**Second problem:** The disaggregated results (geology, collection method, SSC range) are the scientific backbone of this paper but they are compressed into a few sentences within Section 4.3. These need their own subsection with proper tables and figures.

### Discussion

The discussion is above average. Section 5.1 (hysteresis argument) is strong. Section 5.2 (site heterogeneity) is the paper's most important scientific contribution and is well-articulated. Section 5.4 (deployment tiers) is practical and appropriate for WRR.

Weaknesses:
- Section 5.3 (collection method) is interesting but reads as a results finding, not a discussion point. Move the quantitative results to Results and discuss the implications here.
- Section 5.5 (comparison) is too short and too hedged. Be more direct.
- Missing: discussion of what the 30% failure rate implies for the paradigm of cross-site prediction.
- Missing: discussion of residual autocorrelation and its implications for effective sample size and confidence intervals.

### Limitations

Honestly presented. Good. One addition needed: the ablation analysis that produced the final 72 features was never evaluated with disaggregated metrics (this is noted in DECISION_LOG). Some dropped features may matter for specific subgroups. This should be disclosed.

---

## 4. Claim-Evidence Alignment

### Claim 1: "predicts suspended sediment concentration from turbidity across 405 U.S. sites without per-site calibration (Spearman rho = 0.907)"

**Evidence:** v11_extreme_eval_summary.json reports pooled_spearman_rho = 0.9065, consistent. MedSiteSpearman = 0.8735, which is the per-site median.

**Problem:** The Key Points and abstract use the POOLED Spearman (0.907) while the per-site median Spearman is 0.874. The pooled Spearman is inflated by the between-site variance in SSC (sites with very different median SSC get ranked correctly trivially). The paper should report the per-site median Spearman (0.874) or at minimum clearly label which is which.

**Verdict:** Mild overclaim. The pooled Spearman overstates per-site ranking ability.

### Claim 2: "the model matches the USGS published sediment record within 2.6% over 8 years"

**Evidence:** The load_comparison_summary.json shows Brandywine v11 total_load_ratio = 1.594, which is a +59.4% overprediction on daily totals, NOT 2.6%. However, the draft Table 6 shows 42,059 vs 41,007 tons for the total period load. These numbers come from different time windows or accounting methods.

**Critical inconsistency:** The daily-level Brandywine v11 pbias_pct is +59.4%, but the total period load ratio is claimed at 1.03 (2.6%). This likely reflects the difference between available turbidity days and the full 80155 record. The paper MUST explain this discrepancy. If the 2.6% result only holds for days where both turbidity and 80155 data exist (which may be a selected subset), this needs to be stated clearly. A reviewer will catch this.

**Verdict:** Potentially serious. The claim is plausible but the supporting JSON data tells a different story at daily resolution. Needs transparent reconciliation.

### Claim 3: "Median per-site R2 of 0.40 (95% CI: 0.36-0.44)"

**Evidence:** Bootstrap CI from v11_bootstrap_ci_results.json shows MedSiteR2 point = 0.4015, ci_lo = 0.3579, ci_hi = 0.4396. Consistent.

**Verdict:** Well-supported.

### Claim 4: "Adding as few as two grab samples for Bayesian site adaptation raises median R2 to 0.49"

**Evidence:** The adaptation curve shows random N=2 MedR2 = 0.413, not 0.49. Random N=10 MedR2 = 0.493. The abstract conflates N=2 with the N=10 result.

**Verdict:** Overclaim. N=2 raises R2 to 0.41, not 0.49. N=10 reaches 0.49. The abstract should say "as few as 10 grab samples" or accurately report the N=2 improvement (+0.01 over zero-shot).

### Claim 5: "Storm-event loads show 2-4x smaller median error than discharge-only baseline"

**Evidence:** Brandywine: v11 median error +119% vs OLS +165% -- ratio is 1.4x, not 2-4x. Valley Creek: v11 +169% vs OLS +591% -- ratio is 3.5x. Ferron: v11 -39% vs OLS +124% -- ratio is ~3.2x (using absolute values: 39 vs 124 = 3.2x).

**Verdict:** Partially supported. The 2-4x claim holds for Valley Creek and Ferron Creek but NOT for Brandywine (only 1.4x). The aggregate "2-4x" is cherry-picked. Report the actual range: 1.4x to 3.5x.

### Claim 6: "30% of holdout sites have R2 < 0"

**Evidence:** Bootstrap frac_R2_gt_0 = 0.757, meaning 24.3% have R2 < 0 (not 30%). The 95% CI is [0.681, 0.837], so the 30% claim is within the CI but is not the point estimate.

**Verdict:** Mild overclaim. Point estimate is ~24%, not 30%. Use the actual number with CI.

### Claim 7: "Watershed geology explains much of this variation, with carbonate-dominated sites (R2 = 0.81) far outperforming volcanic sites (R2 = 0.20)"

**Evidence:** From RESULTS_LOG: Carbonate R2 = 0.807, Volcanic R2 = 0.195. Consistent.

**Verdict:** Well-supported. This is one of the paper's strongest findings.

---

## 5. Reviewer Attack Surface

### 1. Why not an LSTM? (Severity: SERIOUS)

**Objection:** Kratzert et al. (2019) and Song et al. (2024) use LSTMs, which can capture temporal dependencies in the turbidity signal (hysteresis, rising/falling limb dynamics) natively. CatBoost operates on instantaneous features and requires hand-engineered temporal features (slopes, rolling windows). Did you test a recurrent architecture?

**Strength:** Serious. The paper's hysteresis claims (Section 5.1) suggest temporal dynamics are important, yet the model architecture cannot learn them from data -- it relies on pre-computed features.

**Currently addressed?** No. Not discussed.

**Preemption:** Add a paragraph in the discussion explaining the choice. CatBoost was chosen for (a) native categorical handling (collection method is SHAP rank 3), (b) native missing value handling (79% of sites missing pH), (c) interpretability via SHAP, and (d) computational efficiency enabling extensive ablation. Acknowledge LSTM as future work. Note that the hand-engineered temporal features (turbidity_slope_1hr, Q_ratio_7d, rising_limb) capture the most important temporal dynamics, as evidenced by their SHAP contributions.

### 2. Pooled Spearman is inflated by between-site variance (Severity: SERIOUS)

**Objection:** A pooled Spearman of 0.907 across 78 sites with wildly different median SSC is trivially high -- even a model that predicts site means would get high pooled Spearman because the between-site variance dominates. What is the per-site Spearman?

**Strength:** Serious. The per-site median Spearman is 0.874, which is still good but noticeably lower.

**Currently addressed?** The paper uses pooled Spearman in the key points, abstract, and throughout. The bootstrap CIs report MedSiteSpearman = 0.874 but this is buried.

**Preemption:** Replace pooled Spearman with median per-site Spearman everywhere. Report pooled as secondary.

### 3. The 2.6% Brandywine result is for a selected subset of days (Severity: SERIOUS)

**Objection:** The daily-level load analysis shows +59% pbias for v11 at Brandywine, yet the headline claims 2.6%. How many days does the 2.6% number cover? Are turbidity-missing days excluded? If so, the model is only evaluated on the "easy" days where the turbidity sensor was working.

**Strength:** Potentially fatal if the discrepancy cannot be explained transparently.

**Currently addressed?** No. The paper presents 42,059 vs 41,007 tons without explaining the day coverage.

**Preemption:** Report the exact number of days with concurrent turbidity, discharge, and 80155 data. If the 2.6% comes from a subset (e.g., 1,366 days out of 2,549), state this explicitly. Report both the full-period and same-day-coverage totals.

### 4. BCF is a fudge factor (Severity: MANAGEABLE)

**Objection:** The model systematically underpredicts by 36.6% (holdout bias), requiring a bias correction factor of 1.297 for loads and 0.975 for individual predictions. Using two different BCFs for two different purposes looks like post-hoc fitting.

**Strength:** Manageable. BCF is standard practice in log-space regressions (Duan 1983, Snowdon 1991), and the dual BCF is statistically principled. But the framing matters.

**Currently addressed?** Section 3.3 describes the approach but does not justify why dual BCFs are needed or cite the statistical basis for choosing between them.

**Preemption:** Frame dual BCF as addressing two different loss functions (L1 for individual predictions, L2 for totals). Cite the well-known property that the ratio estimator is unbiased for the mean but biased for the median, and vice versa. This is textbook material.

### 5. 72 features after ablation but 137 described (Severity: MANAGEABLE)

**Objection:** The paper describes 137 features in detail (Section 3.2, Table 1) but then mentions in a table footnote that 65 were dropped. Which features are actually in the model? Were the 65 dropped features properly evaluated for subgroup effects?

**Strength:** Manageable but sloppy. A reviewer will feel deceived by the detailed description of features that are not in the model.

**Currently addressed?** Only in a table footnote.

**Preemption:** Add a clear statement in Section 3.2: "Of these 137 candidate features, 65 were removed through systematic ablation analysis (Appendix B), leaving 72 active features." Table 1 should mark which features are active vs. dropped. The ablation methodology (including the limitation that disaggregated metrics were not used for drop decisions) should be in an appendix.

### 6. Temporal adaptation performs worse than zero-shot at N=10 (Severity: MANAGEABLE)

**Objection:** Table 5 shows temporal N=10 R2 = 0.389, which is LOWER than zero-shot R2 = 0.401. The most operationally realistic adaptation strategy actually makes the model worse. This undermines the practical value proposition.

**Strength:** Manageable because the paper acknowledges this, but the implications are understated.

**Currently addressed?** Section 4.4 discusses this briefly.

**Preemption:** Frame this as a finding, not a bug. The temporal degradation is scientifically informative: it reveals that the first 10 samples at most sites are baseflow-biased, and that naive chronological calibration is worse than no calibration. This has direct operational implications for sampling design. Make this a prominent finding.

### 7. No uncertainty propagation to load estimates (Severity: MANAGEABLE)

**Objection:** The paper reports point estimates for sediment loads (42,059 tons at Brandywine) but no uncertainty bounds. The conformal prediction intervals are for individual SSC predictions, not integrated loads. What is the uncertainty on the 2.6% match?

**Strength:** Manageable. Load uncertainty estimation is genuinely difficult and rarely done well, but a WRR paper should at least acknowledge the issue.

**Currently addressed?** No.

**Preemption:** Add a paragraph noting that propagating prediction interval uncertainty to integrated loads is non-trivial (because errors are temporally correlated, lag-1 autocorrelation up to 0.69) and is left for future work. Report at minimum a bootstrap estimate of load uncertainty.

### 8. Only 3 load validation sites, and 2 are in Pennsylvania (Severity: MANAGEABLE)

**Objection:** The load validation -- the paper's strongest result -- is based on only 3 sites, 2 of which are in the same state and likely the same geologic regime (Piedmont Piedmont, carbonate-influenced). This is not representative.

**Strength:** Manageable because the paper is constrained by data availability (sites must have concurrent 80155, turbidity, and discharge records), but the limitation is real.

**Currently addressed?** Not discussed.

**Preemption:** Explicitly state why only 3 sites were available. Note that the Ferron Creek (UT) site provides a contrasting geologic regime (semiarid, different lithology). Acknowledge that the strong Brandywine result may not generalize to volcanic or glacial settings.

### 9. No comparison to existing turbidity-SSC regressions (Severity: MANAGEABLE)

**Objection:** The natural comparison for a turbidity-based SSC model is not discharge-only OLS but the standard per-site turbidity-SSC regression (Rasmussen et al. 2009). How does CatBoost compare to per-site log(SSC) ~ log(Turb) regression with the same number of calibration samples?

**Strength:** Manageable. The paper compares to OLS(Q) but not to OLS(Turb).

**Currently addressed?** Section 3.6 defines the OLS benchmark as discharge-only. Per-site turbidity regression is mentioned in the introduction (R2 = 0.78-0.90) but never directly compared.

**Preemption:** Add a turbidity-OLS baseline: per-site log(SSC) ~ log(Turb) with the same N calibration samples used in the adaptation experiments. This is essential. The model's value is not just "better than discharge-only" but specifically "approaching per-site turbidity regression accuracy without per-site calibration."

### 10. Residual autocorrelation inflates effective sample size (Severity: COSMETIC)

**Objection:** With lag-1 autocorrelation up to 0.69 at individual sites, the 6,026 holdout samples are not independent. The bootstrap CIs (which use site-level blocking) partially address this, but the within-site effective sample size is much smaller than the nominal count.

**Strength:** Cosmetic for the main results (because site-level blocking handles between-site correlation), but relevant for per-site metrics.

**Currently addressed?** Section 6.4 mentions spatial autocorrelation but not temporal residual autocorrelation.

**Preemption:** Add a sentence to Section 6.4 noting temporal autocorrelation within sites and its implications.

---

## 6. Paper-Worthy Results and Quotes

### Headline Numbers (with CIs where available)

- **MedSiteR2 = 0.40 [95% CI: 0.36, 0.44]** -- primary zero-shot metric
- **Median per-site Spearman = 0.874 [95% CI: 0.84, 0.90]** -- use THIS, not pooled 0.907
- **MAPE = 40.1%** -- practical interpretability
- **Fraction within 2x = 70.0%** -- 7 in 10 predictions within half to double observed
- **Fraction of sites with R2 > 0 = 75.7% [95% CI: 68.1%, 83.7%]** -- meaning ~24% of sites fail
- **Fraction of sites with R2 > 0.5 = 36.5% [95% CI: 27.3%, 44.5%]** -- only 1 in 3 sites are "good"

### Disaggregated Results (THE BACKBONE)

These must each get proper treatment in a table or figure:

- **By geology:** Carbonate R2 = 0.81, Sedimentary R2 = (report), Volcanic R2 = 0.20. This is a 4x range driven by particle mineralogy. MOST IMPORTANT DISAGGREGATED RESULT.
- **By collection method:** Depth-integrated R2 = 0.32, Auto-point R2 = 0.24. The most common operational method performs worst.
- **By SSC range:** SSC < 50 mg/L R2 = -60.6 (catastrophic overprediction), SSC > 5,000 mg/L R2 = -3.4 (underprediction). The model fails at both extremes.
- **Between-site vs within-site variation:** CV = 4.37 (between) vs 1.35 (within), ratio = 3.2x. This is the paper's most important physics finding.
- **Holdout SSC/turb ratio systematically harder than training:** 2.17 vs 1.74 (+25%). The holdout is genuinely harder.

### Negative Results (CREDIBILITY BUILDERS)

- **30% (actually ~24%) of holdout sites have R2 < 0.** The model is worse than the site mean at 1 in 4 sites.
- **Temporal adaptation at N=10 degrades to R2 = 0.39**, below zero-shot R2 = 0.40. Naive chronological calibration hurts.
- **CQR failed** after 23-hour training run. Box-Cox compression is structurally incompatible with quantile regression for heavy-tailed data.
- **SSC < 50 mg/L overpredicted by 2.45x.** Low-SSC predictions are unreliable.
- **Top 1% SSC underpredicted by 25%.** Extreme events are systematically missed.
- **Conformal intervals fail at SSC > 2,000 mg/L:** 52% coverage at 90% nominal level.

### Comparison Results

- **CatBoost vs OLS(Q) at N=2 temporal:** CatBoost R2 = 0.36, OLS R2 = -0.56. Delta = +0.93. The strongest low-N advantage.
- **CatBoost vs OLS(Q) at N=10 random:** CatBoost R2 = 0.49, OLS R2 = 0.37. Delta = +0.13.
- **CatBoost beats OLS at every N, every split mode.** Universal dominance.
- **agriculture_pct predicts where OLS wins** (rho = -0.48, p = 0.001). Simple agricultural sites do not need ML.

### Load Estimation Results

- **Brandywine 8-year total:** CatBoost 42,059 vs USGS 41,007 tons (ratio 1.03). OLS 68,666 tons (ratio 1.67). But day-count discrepancy must be resolved.
- **Ferron Creek daily R2 = 0.76, Spearman = 0.96.** Best single-site load result.
- **Storm events at Valley Creek:** CatBoost median error +169% vs OLS +591%. 3.5x advantage.
- **Storm events at Brandywine:** CatBoost +119% vs OLS +165%. Only 1.4x advantage (weakest site).
- **Ferron Creek storms:** CatBoost -39% (underprediction) vs OLS +124%. CatBoost errs conservatively.

### Adaptation Results

- **N=10 random adaptation:** MedSiteR2 = 0.49 [95% CI: 0.44, 0.55]. The plateau is real.
- **Diminishing returns after N=10:** Going from N=10 to N=50 adds only +0.005 R2.
- **Temporal adaptation is worse than random** at every N from 2 to 20. First samples are baseflow-biased.
- **Bayesian adaptation prevents catastrophic small-N collapse:** At N=2 temporal, Bayesian R2 = +0.40 vs old 2-parameter R2 = -0.01.

### External Validation

- **260 NTU sites, 11,026 samples:** Spearman = 0.927, cross-sensor-standard generalization demonstrated.
- **Adaptation to NTU sites at N=10:** R2 = 0.50, matching USGS holdout performance.

### Physics Findings Worth Highlighting

- **Collection method SHAP rank 3:** Depth-integrated samples yield 4x higher SSC than point samples at same turbidity. This is a known physics effect (vertical concentration gradient) that the model has learned from data.
- **Hysteresis:** 39.5% clockwise, 24.4% counterclockwise, 36.1% linear. Rising-limb SSC/turb ratio 16% higher than falling.
- **Power-law slopes:** Median 0.952, range 0.29-1.55. 50% steepen at high turbidity, 32% flatten.
- **Drainage area predicts error:** rho = -0.375, p = 0.004. Small basins are harder (121% MAPE vs 47% for large).

---

## 7. What's Missing from the Draft

### Critical additions (must-have for revision)

1. **Per-site turbidity-OLS baseline.** The most natural comparison -- per-site log(SSC) ~ log(Turb) regression with N calibration samples -- is missing. Without this, the paper cannot claim to improve on existing practice. The discharge-only baseline is a straw man.

2. **Explicit per-site R2 distribution.** A histogram or CDF of per-site R2 values across the 78 holdout sites, with annotations for the 24% that are negative, the 36% above 0.5, and the 76% above 0. This should be a main-text figure.

3. **Geology subsection in Results.** The carbonate vs volcanic result deserves its own subsection with a box plot (currently described as Figure 3 in captions but the text compresses it into two sentences in Section 4.3).

4. **Day-coverage reconciliation for load estimates.** How many days of the Brandywine 8-year record have concurrent turbidity, discharge, and 80155 data? What is the total load comparison when restricted to the same days? The 2.6% headline number needs transparent support.

5. **Residual autocorrelation analysis.** Lag-1 autocorrelation up to 0.69 is mentioned in the RESULTS_LOG but not in the paper. Report effective sample sizes.

6. **Moran's I for spatial autocorrelation.** Mentioned as "not conducted" in Section 6.4. This should be done before submission.

7. **Model architecture justification.** Why CatBoost and not LSTM? This needs at least a paragraph.

### Desirable additions (strengthen the paper)

8. **Seasonal disaggregation table.** Spring R2 = 0.42 vs other seasons R2 = 0.70 is a large seasonal effect that deserves reporting.

9. **Drainage area effect.** The strong relationship between drainage area and error (rho = -0.375) is not in the draft.

10. **Ablation methodology appendix.** The 72-feature model is the result of extensive ablation, but the paper does not describe how features were selected. At minimum, mention the approach in methods and add an appendix.

11. **Sensitivity to event detection parameters.** The storm event results are sensitive to the 1.5x baseflow threshold and 6-hour minimum duration. Test sensitivity to these choices.

---

## 8. What Should Be Cut

1. **Section 4.1 (Transform and Constraint Selection).** Move to supplementary. This is a methods decision, not a result. Retain one sentence in methods: "We selected Box-Cox lambda = 0.2 with monotone constraints from a 20-experiment sweep (Appendix A)."

2. **Section 4.2 (Feature Importance).** Compress significantly. The three "information channels" can be described in 3 sentences. The full SHAP analysis belongs in supplementary. Keep only the headline: turbidity dominates, geology and collection method provide critical site context.

3. **Hyperparameter sensitivity analysis (Appendix A).** This is fine as an appendix but too detailed. Compress Table A1 to show only the 5 most informative experiments (baseline, depth=4, depth=10, lr=0.01, Ordered vs Plain). The conclusion is "model is robust" and that can be stated in 2 sentences.

4. **The CQR failure narrative.** Section 6.2 is interesting but allocates too much space to a negative result. Compress to 3 sentences: we tried CQR, it failed because Box-Cox compression prevents quantile models from reaching extreme values, so we used empirical conformal intervals instead.

5. **The Ferron Creek load comparison.** This site has only 260 days and 23 storm events. It adds comparatively little to the Brandywine story. Consider moving to supplementary or presenting as a brief comparison table only.

---

## 9. Framing Recommendations

### Current framing
The paper is framed as "we built a gradient boosting model for SSC prediction across sites." This is accurate but undersells the contribution. It reads as a methods paper.

### Recommended framing
Frame this as **a paper about the transferability boundary of the turbidity-SSC relationship**, using the model as a diagnostic tool. The central scientific question is: "What controls whether a turbidity-SSC relationship transfers across sites?" The answer -- watershed geology and particle properties -- is the finding. The model is the instrument, not the subject.

Specific framing shifts:

1. **Title:** Consider "Geology Controls Cross-Site Transferability of Turbidity-Sediment Relationships: A Continental-Scale Machine Learning Assessment" or similar. The current title reads like a methods paper. A results-oriented title signals a science paper.

2. **Key Points:** Reorder to lead with the geology/transferability finding, then the Brandywine load validation, then the adaptation result. Currently leads with a methods statement ("a gradient boosting model predicts...").

3. **Abstract structure:** Problem (4,000 sensors without SSC) -> Approach (CatBoost with turbidity + watershed context) -> Key finding 1 (geology controls transferability: carbonate R2 = 0.81, volcanic R2 = 0.20) -> Key finding 2 (load validation within 2.6% at Brandywine) -> Key finding 3 (site adaptation with 10 samples reaches R2 = 0.49) -> Honest limitation (24% of sites R2 < 0, driven by site heterogeneity).

4. **Lead metric:** Lead with MedSiteR2 = 0.40 and the per-site R2 distribution, NOT Spearman and NOT pooled metrics. The fact that the median is modest but the distribution is bimodal (good at carbonate, bad at volcanic) is the STORY.

5. **Brandywine framing:** Do not present this as "the model matches USGS." Present it as "at a site where geology and particle properties are favorable (carbonate-influenced Piedmont), the model reproduces the operational record. At sites where geology is unfavorable, it does not." This is more honest and more scientifically interesting.

6. **Position relative to Song et al. (2024):** Do not compete on R2. Compete on the input data innovation (turbidity vs discharge) and the operational validation (load estimation vs cross-validation only). These are complementary papers, not competitors.

7. **The honest failure story is a STRENGTH.** The 24% failure rate, the geology explanation, the temporal adaptation degradation -- these are findings. Frame them as contributions to understanding, not as apologies. A paper that claims MedSiteR2 = 0.40 and honestly explains why is more publishable than a paper that claims MedSiteR2 = 0.60 and sweeps the failures under the rug.

---

*End of assessment. I am available for follow-up discussion on any section. This paper has genuine merit and can reach WRR quality with focused revision.*

-- Dr. Amara Osei
