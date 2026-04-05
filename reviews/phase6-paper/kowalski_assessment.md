# Operational Assessment: murkml Cross-Site SSC Estimation Model

**Reviewer:** Dr. James Kowalski, Chief of Water Quality Monitoring
**Agency:** [State Environmental Agency], 15 years operational experience
**Date:** 2026-04-02
**Document reviewed:** WRR draft v1, RESULTS_LOG, DECISION_LOG, v11 evaluation JSON, load comparison JSON, SHAP/feature importance data

---

## 1. Operational Feasibility Assessment

### Would I deploy this at my stations?

**Short answer: Yes, conditionally, at screening grade only -- and only at sites with depth-integrated sampling programs or where I can pair it with a grab-sampling protocol.**

The model has real operational value in a specific niche: the ~3,600 USGS turbidity-monitored sites that lack calibrated SSC regressions. For a state agency managing 200+ stations, this could give us a first-pass sediment estimate at sites where we currently have nothing. That alone justifies attention.

However, I would not deploy this for TMDL compliance or regulatory reporting without site-specific adaptation (N >= 10 grab samples) and independent validation against at least one year of discrete SSC data. The zero-shot MedSiteR2 of 0.40 means that at the median site, the model explains 40% of SSC variance -- which means 60% is unexplained. For a compliance context, that is not defensible.

### What I would need to see first:

1. **A site-screening tool** that tells me upfront whether murkml is likely to work at MY site, based on geology, drainage area, and collection method. The model knows where it fails (volcanic, glacial flour, urban) -- expose that as a pre-deployment check.
2. **Clear documentation that auto-point performance is R2 = 0.24, not R2 = 0.40.** Most of my operational sensors are fixed-point installations. The headline number misleads.
3. **Prediction intervals displayed alongside every estimate.** The conformal intervals achieving 90.6% coverage are good, but the 52% coverage above 2,000 mg/L must be prominently flagged. That is exactly the range where regulatory decisions about flood events and TMDL exceedances are made.
4. **A bias-correction protocol** for my specific watershed geology. The -36.6% global bias is not uniformly distributed -- carbonate sites are well-estimated, volcanic sites are not. I need to know which side of that line I am on.

### Deployment scenario I would actually use:

Deploy at 20-30 turbidity-monitored sites that lack SSC regressions. Use zero-shot predictions as a screening layer for 6-12 months. Simultaneously collect 10+ grab samples per site, targeting storm events. Apply Bayesian adaptation. Validate against an independent set of 5-10 grab samples. Promote to monitoring grade only at sites where adapted R2 > 0.5 and bias < 25%.

---

## 2. Collection Method Confound

This is the elephant in the room and the paper handles it with more honesty than most, but not enough.

### The core problem:

- **Auto-point R2 = 0.238** (RESULTS_LOG disaggregated, v11). This is the collection method used by most operational continuous monitoring installations.
- **Depth-integrated R2 = 0.321** (RESULTS_LOG disaggregated, v11). This is the collection method used in research and USGS calibration programs.
- Collection method is SHAP rank #3 (mean |SHAP| = 0.349), meaning the model relies heavily on knowing which method was used.

### What this means operationally:

A state agency deploying continuous turbidity sensors with fixed-point ISCO samplers is operating in the R2 = 0.24 regime, not the R2 = 0.40 regime. The headline MedSiteR2 of 0.40 is a blended number that mixes depth-integrated research programs with operational auto-point installations. **This distinction must be in the abstract.**

The paper's Section 5.3 correctly identifies the "operational irony" -- the model works best for the method least commonly deployed. But it then moves on without quantifying the consequence. The consequence is this: for a typical state monitoring network using fixed-point samplers, the zero-shot model explains roughly 24% of SSC variance. That is screening grade at best, and arguably below useful for individual predictions.

### The deeper concern:

Collection method at SHAP rank #3 means the model has learned a systematic offset between auto-point and depth-integrated SSC. At the same turbidity, depth-integrated samples yield ~4x higher SSC (paper Section 5.3). This is real physics -- vertical concentration gradients are real. But it also means the model is partially learning a bias correction for sampling methodology, not just a turbidity-to-SSC relationship. For deployment at sites with unknown or mixed collection methods, this is a fragility.

### Recommendation:

The paper should include a table in the main text (not supplementary) showing MedSiteR2, MAPE, and within-2x broken out by collection method. The abstract should state something like: "Performance varies by collection method, with depth-integrated sites (R2 = 0.32) outperforming automated point-sampler sites (R2 = 0.24)." Yes, these numbers are low. That is the honest result.

---

## 3. Three-Tier Deployment Critique

### Screening Grade (N = 0, MedSiteR2 = 0.40)

**Honestly described?** Mostly. The paper correctly positions this as order-of-magnitude and ranking. But calling it useful for "TMDL screening and regulatory prioritization" is a stretch. A model with 40% R2 and -36.6% bias is going to flag the wrong sites. Spearman = 0.91 is legitimately useful for ranking -- "which of my 50 sites has the highest sediment?" -- but not for "does this site exceed 100 mg/L?" The paper should distinguish ranking use from threshold-exceedance use.

**Regulatory context concern:** The word "screening" has a specific meaning in the regulatory world. EPA's TMDL screening typically requires 90th percentile estimates with known uncertainty bounds. A model with 30% of sites at R2 < 0 and 52% interval coverage at the extreme tail does not meet that bar. Use the word "reconnaissance" or "prioritization" instead of "screening" to avoid creating expectations the model cannot meet.

### Monitoring Grade (N = 5-10, MedSiteR2 = 0.45-0.49)

**Honestly described?** Reasonably. The adaptation curve data supports this. N = 10 random raises MedSiteR2 to 0.49, which is genuinely useful for trend detection.

**Missing caveat:** Temporal adaptation at N = 10 gives MedSiteR2 = 0.39 -- WORSE than zero-shot. The paper discusses this (baseflow-dominated early samples) but does not flag that the "monitoring grade" designation assumes storm-event-targeted sampling. If a field crew collects 10 routine monthly samples (the most common protocol), they will get the temporal result, not the random result. **The tier definition should specify: "10 calibration samples including at least 3 storm events."**

### Publication Grade (N >= 30, site-specific validation)

**Overstated.** The paper says "the model may approach per-site OLS accuracy (R2 > 0.70)." The data does not support this. At N = 30 random, MedSiteR2 = 0.48. At N = 50 random, MedSiteR2 = 0.50. There is no evidence that N = 30 produces R2 > 0.70 at the median site. The adaptation curve plateaus around 0.50. "Publication grade" requires R2 > 0.70, bias < 10%, and validated prediction intervals -- the model does not reach this at any N shown.

**Recommendation:** Either drop the "publication grade" tier or redefine it honestly: "At well-behaved sites (carbonate geology, depth-integrated sampling), R2 may exceed 0.70 with N = 30 adaptation. At the median site, N = 30 adaptation achieves MedSiteR2 = 0.48."

---

## 4. Sensor QC Reality Check

### Approved-only training excludes extreme events

The paper acknowledges this (Section 6.1) but underestimates its operational impact. In my experience, 30-50% of extreme event data remains "Provisional" for 1-3 years because the USGS review backlog prioritizes routine data. The highest SSC values -- the ones that matter most for TMDL compliance and flood damage estimation -- are systematically underrepresented in the training data.

The top-1% underprediction of -25% is almost certainly related to this. The model has never seen the true extreme tail during training. This is not just a limitation -- it is a structural bias that will cause the model to underestimate every major flood event. For an operational agency, that is the worst possible failure mode: underestimating sediment during the events that dominate annual loads and cause regulatory exceedances.

**Recommendation:** The paper should explicitly state: "Approved-only training creates a systematic underrepresentation of extreme events. Users should expect underprediction during flood conditions and apply wider prediction intervals than the nominal 90% during events exceeding the 99th percentile of training data."

### 15-minute turbidity matching

Linear interpolation within a 15-minute window is reasonable for continuous sensors reporting at 15-minute intervals. This is standard practice (Rasmussen et al., 2009). No concerns here.

### Biofouling, sensor drift, ice

The QC protocol removes ICE-flagged records with 48-hour buffers and MAINTENANCE records with 4-hour buffers. This is appropriate. However, the paper does not discuss:

1. **Biofouling between cleanings.** Turbidity sensors drift upward over 2-8 week deployment periods as biofilm accumulates. This drift is typically 5-30% of reading and is NOT flagged in NWIS unless the hydrographer identifies it post-hoc. The model trains on data that includes this drift as though it were real turbidity variation.
2. **Sensor saturation.** The paper includes a saturation flag at 3,000 FNU, which is good. But many sensors clip at 1,000 or 4,000 FNU depending on model. Clipped readings paired with high SSC teach the model the wrong relationship.
3. **Wiper failures.** Common failure mode where the self-cleaning wiper stops functioning, causing rapid biofouling. Often not flagged until data review weeks later.

These are not dealbreakers, but the paper should note that training data quality depends entirely on USGS QC diligence, which varies by water science center.

### What happens when turbidity goes down?

The model handles NaN turbidity natively through CatBoost's missing-value handling. This is mentioned in the methods but its operational implication is not discussed. When the turbidity sensor fails (which happens 10-30% of the time at my stations), the model reverts to predicting SSC from discharge, watershed attributes, and seasonality alone. This is essentially the Song et al. (2024) discharge-only approach, which they report at MedSiteR2 = 0.55 with an LSTM. The CatBoost model's performance in this degraded mode is not characterized. **This needs to be quantified.**

---

## 5. Paper-Worthy Results and Quotes

These are the numbers and findings that would make practitioners sit up:

### Adaptation curve (the money result for operations):

- "Zero-shot (no site data): MedSiteR2 = 0.40, MAPE = 40%, 70% of predictions within 2x of observed."
- "With 10 randomly selected grab samples including storm events: MedSiteR2 = 0.49, MAPE = 35%, 76% within 2x."
- "The improvement from 10 to 50 samples (+0.005 R2) is negligible compared to 0 to 10 (+0.09). One well-designed sampling campaign captures most adaptation benefit."
- "CRITICAL: Temporal adaptation (first 10 chronological samples) degrades to MedSiteR2 = 0.39 because early samples are baseflow-dominated. Storm-event targeting is essential."

### Collection method impact (the honest result):

- "Auto-point sampler sites: R2 = 0.24. Depth-integrated sites: R2 = 0.32. Collection method is the 3rd most important feature (SHAP = 0.349)."
- "At the same turbidity reading, depth-integrated samples yield ~4x higher SSC than auto-point samples."

### Load estimation (the headline result):

- "At Brandywine Creek PA (8 years, 2,549 days), the model reproduced the USGS published sediment record within 2.6% (42,059 vs 41,007 tons) without any site-specific calibration."
- "Discharge-only OLS overpredicted by 67% at the same site (68,666 tons)."
- "Storm events: CatBoost median event error 119% vs OLS 165% at Brandywine; 169% vs 591% at Valley Creek."

### Geology controls (the science result):

- "Carbonate watersheds: R2 = 0.81. Volcanic watersheds: R2 = 0.20."
- "Between-site variation in the turbidity-SSC relationship (CV = 4.37) is 3.2x larger than within-site variation (CV = 1.35)."

### CatBoost vs OLS at low N (the practical result):

- "With only 2 temporal samples, CatBoost achieves R2 = 0.36 while per-site OLS produces R2 = -0.56."
- "CatBoost beats OLS at every calibration level and every splitting strategy."

### Where the model fails (the credibility result):

- "30% of holdout sites have R2 < 0 (worse than predicting the site mean)."
- "Low-SSC overprediction: 2.45x overprediction below 10 mg/L, attributed to sensor contamination by DOM and algae."
- "Top 1% SSC underprediction: -25%, attributed to training data exclusion of provisional extreme event records."
- "Prediction interval coverage collapses to 52% above 2,000 mg/L."

### The meta-finding (the science contribution):

- "Site heterogeneity is the fundamental problem. No architecture, feature set, or training strategy can replace site-specific calibration. The cross-site model is a ranking engine; Bayesian adaptation is the calibrator."

---

## 6. What's Missing (Operational Perspective)

### A state agency reviewer would demand:

1. **Temporal validation.** The paper uses spatial holdout (78 unseen sites) but does not show temporal holdout at the same site. For regulatory use, I need to know: "If I train on 2010-2020 data, how well does it predict 2021-2025?" Stationarity is assumed but never tested.

2. **Performance at regulatory thresholds.** Can the model correctly classify whether SSC exceeds 100 mg/L? 500 mg/L? 1,000 mg/L? Binary classification metrics (precision, recall, F1) at regulatory thresholds are far more operationally relevant than R2 for TMDL work. Every TMDL I have written asks "how often does SSC exceed X?" -- not "what is the R2?"

3. **Degraded-sensor performance.** When turbidity drops out (NaN), what does the model produce? Quantify the discharge-only fallback performance on the same holdout sites. Operators need to know whether predictions during sensor outages are usable or garbage.

4. **Regional performance map.** The disaggregated geology results are useful but incomplete. Show a map of the CONUS with each holdout site colored by R2. State agencies think geographically. "Does this work in the Pacific Northwest?" requires a map, not a table.

5. **Minimum site data requirements.** The paper says the model uses 137 features. How many features are actually available at a typical operational site? If a site has turbidity, discharge, and no StreamCat attributes -- what happens? Document the graceful degradation from Tier C to Tier B to Tier A.

6. **Residual autocorrelation impact.** The DECISION_LOG notes lag-1 autocorrelation up to 0.69 at individual sites. This inflates effective sample sizes and narrows confidence intervals. The paper's bootstrap CIs with site-level blocking partially address this but do not correct for within-site temporal autocorrelation. The reported CIs may be optimistic.

7. **Spatial autocorrelation assessment.** The limitations section mentions Moran's I has not been conducted. A reviewer will ask for it. Nearby sites sharing similar errors could inflate the effective number of independent holdout sites from 78 to something much smaller.

8. **A comparison to USGS LOADEST or WRTDS.** The OLS benchmark is useful but dated. Modern load estimation uses Weighted Regressions on Time, Discharge, and Season (WRTDS; Hirsch et al., 2010) or LOADEST (Runkel et al., 2004). A comparison against these standard tools would make the load estimation claim far more credible.

---

## 7. What's Overstated

1. **"Matches the USGS published record within 2.6%."** This is one site over one period. Valley Creek is 55% off. Ferron Creek is 25% off. The 2.6% is cherry-picked as the headline. The paper should lead with "total load errors of 3-55% across three validation sites" and let Brandywine be the best case, not the summary.

2. **"Screening grade" for TMDL.** As discussed in Section 3 above, this word creates regulatory expectations the model cannot meet. "Reconnaissance grade" or "prioritization grade" is more accurate.

3. **MedSiteR2 = 0.40 as the headline performance.** This blends collection methods, geologies, and SSC ranges. For an operational user with auto-point sensors in a volcanic watershed, the true expected R2 is far lower. The headline should acknowledge the range, not just the median.

4. **"Publication grade" at N >= 30.** The adaptation curve data shows MedSiteR2 = 0.48 at N = 30 random, and the curve is plateauing. R2 = 0.48 is not publication grade by any standard I am aware of. This tier should be removed or substantially redefined.

5. **Spearman = 0.907.** This is a pooled metric across all sites and samples. It is impressive and real, but it benefits from the massive SSC range (0.1 to 121,000 mg/L). Any model that roughly captures the turbidity-SSC correlation will have high Spearman on data spanning 6 orders of magnitude. Within a single site's SSC range (typically 1-2 orders of magnitude), the ranking accuracy will be much lower. Per-site Spearman would be more honest.

6. **The Brandywine load comparison uses BCF_mean = 1.297.** This is the bias correction that overpredicts 75% of individual samples (Wilcoxon p < 10^-100). Of course the total load matches well -- the systematic overprediction is baked into the BCF to make totals work. This is honest accounting for loads, but the paper should be transparent that this BCF makes individual predictions biased high by ~44% to achieve unbiased totals.

---

## 8. What's Understated

1. **The adaptation breakthrough.** The Bayesian shrinkage adaptation going from R2 = -0.012 (old 2-parameter linear) to R2 = 0.485 (Bayesian, N = 2) is extraordinary. This is the single most important methodological contribution of the paper and it gets less attention than the cross-site headline numbers. The old approach was catastrophic at small N; the Bayesian approach makes small-N adaptation actually work. This should be elevated in the abstract.

2. **Collection method resolution.** Resolving 88% of "unknown" method designations by cross-referencing WQP metadata is a data contribution that other researchers will benefit from. This should be more prominent.

3. **The bug history as scientific process.** The DECISION_LOG documents 16+ bugs that changed results, including one (prune_gagesii) that invalidated months of work. This level of transparency about the development process is rare and valuable. A brief mention of the data provenance audit in the methods section would strengthen credibility.

4. **Drainage area predicts error (rho = -0.375).** Small basins (< 100 km2) have 121% MAPE vs large basins at 47%. This is operationally critical -- most state monitoring networks include many small headwater sites. The paper should state explicitly that the model is more reliable at larger watersheds.

5. **Low-SSC overprediction.** The 2.45x overprediction below 10 mg/L, attributed to sensor contamination (DOM, algae), is an important physical finding. It means the model will cry wolf at low-sediment sites during algal blooms. For drinking water utilities that use turbidity as a treatment trigger, this false positive rate matters.

6. **The 30% of sites with R2 < 0.** The paper mentions this but treats it as acceptable. For an operational tool, 30% catastrophic failure rate means roughly 1 in 3 deployments will produce predictions worse than "guess the mean." That demands a pre-screening protocol, and the paper should provide one (or at least the features that predict failure).

7. **Residuals are heavily non-normal (skewness = 2.0, kurtosis = 13.8).** This means Gaussian-based prediction intervals are structurally wrong, and it validates the Student-t prior choice. The paper should explicitly connect the residual distribution to the choice of adaptation prior.

---

## 9. Specific Recommendations

### For making the paper credible to the operational community:

1. **Rewrite the abstract** to lead with MedSiteR2 = 0.40 and the 30% failure rate alongside the Spearman = 0.91 and Brandywine load match. Operational reviewers will smell cherry-picking if the failures are buried in Section 5.2.

2. **Add a "Who should use this?" section** (or a decision flowchart). Inputs: collection method, dominant geology, drainage area, SSC range of interest. Output: expected performance tier and recommended adaptation sample size. This is what practitioners will look for first.

3. **Report all collection-method-disaggregated metrics in the main text.** Auto-point R2 = 0.24 is the number most users will experience. Hiding it in the supplementary (or only in the RESULTS_LOG) is a mistake.

4. **Add threshold-exceedance classification metrics.** Precision/recall for SSC > 100, > 500, > 1,000 mg/L. These are directly useful for TMDL and permit compliance.

5. **Quantify the degraded-sensor (no-turbidity) fallback.** Run the same holdout evaluation with turbidity features set to NaN. Report the performance drop. Operators need this for designing backup monitoring protocols.

6. **Replace "publication grade" with "enhanced monitoring grade"** and redefine it as R2 > 0.50 with validated prediction intervals. Reserve "publication grade" for per-site OLS with 50+ samples.

7. **Add a Moran's I analysis** before submission. If spatial autocorrelation is present (the DECISION_LOG suggests it is, with 39% vs 55% error difference at 50km), the effective sample size may be substantially smaller than 78 sites, and the CIs need adjustment.

8. **Expand the load comparison to more than 3 sites.** Three sites is anecdotal. If 80155 records exist at more holdout sites, use them. If not, state the limitation clearly.

9. **State the recommended minimum adaptation protocol explicitly:** "We recommend collecting at least 10 paired turbidity-SSC samples at a new site, with deliberate targeting of 3+ storm events across at least 2 seasons. Baseflow-only sampling degrades adaptation performance below zero-shot levels."

10. **Include a candid limitations paragraph about the training data temporal window.** The model is trained on 2000-2026 data. Land use change, urbanization, dam removals, and post-wildfire sediment pulses could all violate the model's assumptions. State this.

---

## Summary Assessment

This is a strong first paper on a tool with genuine operational value. The scientific contribution -- demonstrating that continuous turbidity enables cross-site SSC estimation better than discharge alone, quantifying the site heterogeneity boundary, and developing a Bayesian adaptation framework that works at small N -- is solid and novel.

The primary risk for WRR review is the gap between the headline performance (Spearman = 0.91, Brandywine within 2.6%) and the disaggregated operational reality (auto-point R2 = 0.24, 30% site failure rate, -25% extreme underprediction, 52% interval coverage at the extreme tail). If a reviewer with operational experience reads the abstract and then digs into the disaggregated numbers, they will feel misled. Close that gap by leading with honesty.

The adaptation curve is the paper's strongest practical contribution. Emphasize it. The fact that 10 grab samples (cost: ~$2,000 in laboratory analysis, one day of field work) raises MedSiteR2 from 0.40 to 0.49 and that CatBoost beats per-site OLS at EVERY N -- that is the result that changes practice.

---

*Dr. James Kowalski*
*Chief, Water Quality Monitoring Division*
