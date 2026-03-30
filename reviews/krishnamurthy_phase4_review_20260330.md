# Phase 4 Diagnostic Review — Dr. Ananya Krishnamurthy
**Date:** 2026-03-30
**Reviewer:** Dr. Ananya Krishnamurthy (Applied Environmental Statistics, 12 yr)
**Subject:** murkml Phase 4 Diagnostic Observations (murkml-4-boxcox, 396 sites)

---

## Executive Summary

The Phase 4 diagnostics are a substantial and thoughtful disaggregation effort. The team is asking the right questions and, importantly, has resisted the temptation to paper over problems with aggregate metrics. That said, there are significant statistical gaps that must be addressed before any publication claim can be made. The most critical issues are: (1) absence of standard hydrological evaluation metrics, (2) sample size problems in several disaggregated cells, (3) systematic misuse of R-squared in conditional/within-tier analyses, and (4) no formal uncertainty quantification anywhere. Below I address each item in the terms of reference.

---

## 1. Disaggregated Metrics: Correctness and Sample Size Adequacy

### Computation

The disaggregated metrics appear to be computed correctly in concept: R-squared, MAPE, within-2x accuracy, and mean percent bias are standard and appropriate choices for a first-pass disaggregation. I have no reason to suspect computational errors based on the reported values — the patterns are internally consistent (e.g., low-variability sites yield low R-squared, extreme events show compression bias).

However, I note that the **bias metric is ambiguous as reported**. "Bias = -3.0%" for the pooled set — is this mean percent bias (MPB), median percent bias, or fractional bias? These are not interchangeable. MPB is dominated by outliers in skewed distributions like SSC. The document should specify the formula used. For sediment, I recommend reporting both **mean bias** (in mg/L) and **median percent bias** to avoid outlier distortion.

### Sample Size Concerns

Several disaggregated cells have dangerously small n:

| Cell | n | Issue |
|---|---|---|
| HUC13 Rio Grande | 16 | Cannot compute meaningful R-squared. CI on R-squared from n=16 spans roughly +/-0.3. The reported 0.824 could easily be 0.5 or 0.95. |
| HUC19 Alaska | 21 | Same problem. The -10.522 R-squared from 21 samples at a single site is not a regional statistic — it is one site's failure. |
| SSC Extreme >5K mg/L | 18 | Insufficient for any reliable metric. |
| Turbidity >1000 FNU | 43 | Marginal. R-squared=0.805 from 43 samples is suggestive but not conclusive. |
| 17 "thin" holdout sites | <20 each | Acknowledged in the document but still included in aggregates. |

**Recommendation:** For any cell with n < 30, report confidence intervals on all metrics (bootstrap with site-level resampling). For cells with n < 20, flag them as "insufficient for inference" and exclude from any publication table. The HUC-level results with single sites should be presented only as site-level case studies, never as regional performance estimates.

The 8 single-site HUC2 regions are not regional statistics at all. They are individual site evaluations wearing regional labels. This distinction matters for how readers interpret the results.

---

## 2. Missing Standard Hydrological Goodness-of-Fit Statistics

This is the most significant gap in the current evaluation. The following are standard in the hydrological modeling literature and **must** be reported for a Water Resources Research or similar journal submission:

### Must-Have Metrics

1. **Nash-Sutcliffe Efficiency (NSE):** The standard benchmark in hydrology. NSE = 1 - SS_res/SS_tot. Mathematically equivalent to R-squared only when computed on the same dataset with the same mean — but the conventions differ in practice (R-squared as squared correlation vs. coefficient of determination). Report NSE explicitly.

2. **NSE on log-transformed values (log-NSE):** Critical for sediment because the distribution is heavily right-skewed. Log-NSE penalizes errors at low concentrations more heavily, which is exactly where this model struggles. I predict log-NSE will be substantially worse than native NSE given the +121% bias at low SSC.

3. **Kling-Gupta Efficiency (KGE):** Already reported for the CV results (0.767) but **not reported for the holdout disaggregation**. KGE decomposes into correlation (r), variability bias (alpha), and mean bias (beta). This decomposition is far more informative than a single R-squared. Report KGE and its three components for every disaggregated cell.

4. **Percent Bias (PBIAS):** Already partially reported as "bias" but needs to follow the standard formula: PBIAS = 100 * sum(pred - obs) / sum(obs). Clarify whether this is what is being computed. Moriasi et al. (2007, 2015) provide performance thresholds: PBIAS < +/-25% is "satisfactory" for sediment. Several cells fail this threshold.

5. **RMSE and normalized RMSE (NRMSE):** RMSE is reported for the aggregate (165.6 mg/L) but not for disaggregated cells. Report it — MAPE alone is insufficient because MAPE is undefined when observed values are zero and is biased toward underprediction.

### Should-Have Metrics

6. **Volume Error / Total Load Bias:** For sediment, what matters operationally is whether cumulative predicted load matches cumulative observed load. Compute sum(predicted_SSC) / sum(observed_SSC) for each disaggregated cell. A model with zero mean bias can still have terrible load estimation if errors are correlated with magnitude.

7. **Flow-Duration Curve (FDC) statistics — adapted for SSC:** Compute the SSC-duration curve for observed and predicted, then report bias at key exceedance percentiles (10%, 50%, 90%). This reveals whether the model compresses the distribution (which it clearly does based on the alpha=0.882 in CV).

8. **Scatter around the 1:1 line at key percentiles:** Rather than a single R-squared, report the ratio of predicted/observed at the 10th, 25th, 50th, 75th, and 90th percentiles of observed SSC. This is more informative than any single aggregate metric.

### Nice-to-Have Metrics

9. **Willmott's Index of Agreement (d):** Sometimes requested by reviewers as it is bounded [0,1] and avoids some R-squared pathologies.

10. **Mean Absolute Error (MAE):** More robust than RMSE to outliers. Report alongside RMSE.

---

## 3. R-squared Usage: Where It Is Appropriate and Where It Is Misleading

### Where R-squared is appropriate:
- **Pooled holdout (R-squared=0.665):** Acceptable as a summary statistic, though NSE and KGE are preferred in hydrology.
- **By geology type:** Reasonable because each geology group spans the full SSC range.
- **First flush vs. normal (R-squared=0.864 vs. 0.487):** Appropriate comparison because both groups span a range of values.

### Where R-squared is misleading or inappropriate:

**By turbidity band:** R-squared=0.138 at <10 FNU and R-squared=0.442 at 10-50 FNU are misleading because R-squared within a narrow band of the predictor is dominated by the residual variance relative to the within-band outcome variance. A model could be making perfectly reasonable predictions (e.g., all within 20% of truth) and still show low R-squared if the true SSC values within that turbidity band don't vary much. **MAPE and within-2x are the correct metrics here**, and the document already uses them — but the R-squared column should not be in this table at all, as it will confuse readers.

**By SSC level (within-tier):** R-squared is negative everywhere. This is discussed in detail in Section 4 below, but the bottom line is that this R-squared column is actively misleading and should be removed from the table.

**By SSC variability quartile:** R-squared=0.094 for Q1 (low-variability sites) is not evidence of model failure. It means the model explains 9.4% of variance at sites where there is almost no variance to explain. The real question is: what is the MAE at these sites? If the MAE is 5 mg/L at a site where SSC ranges from 8 to 15 mg/L, the model is doing fine despite the low R-squared.

**By collection method ("unknown" = 0.873):** The high R-squared for "unknown" is flagged as suspicious. I agree this needs investigation, but note that R-squared=0.873 from n=1,248 across 13 sites could easily reflect that those 13 sites happen to have high SSC variance and good turbidity-SSC correlation. Before attributing the R-squared to the categorical encoding, compute the expected R-squared given those sites' characteristics. A simple check: compute R-squared for those 13 sites using a model trained WITHOUT the collection method feature. If it stays high, it is the sites, not the encoding.

---

## 4. Within-Tier Negative R-squared: Problem or Expected?

The within-tier R-squared values (all negative, ranging from -0.12 to -52.4) are **entirely expected and not a problem**. Here is the precise explanation:

R-squared = 1 - SS_res / SS_tot, where SS_tot is the total sum of squares around the **within-tier mean**. When you restrict to a narrow SSC band (e.g., 50-500 mg/L), the within-tier variance is small by construction. But the model's prediction errors don't shrink proportionally — a model trained on the full range makes predictions with a certain error magnitude that does not magically decrease just because you filter to a narrow band. So SS_res > SS_tot, and R-squared goes negative.

This is a well-known artifact. The model is not "worse than predicting the mean" in any meaningful sense — it is worse than predicting the **within-band** mean, which is a much easier benchmark than the full-range mean.

**What metric should replace within-tier R-squared?**

1. **Within-tier MAPE** — already computed and far more informative. The document correctly identifies this.
2. **Within-tier MAE (in mg/L)** — gives absolute accuracy in physical units.
3. **Within-tier median absolute percent error** — more robust than MAPE to outliers.
4. **Conditional bias: mean(predicted - observed) within each tier** — reveals whether the model systematically over- or underpredicts in each concentration range. The document reports this as "bias" and the pattern is clear: overprediction at low SSC, underprediction at high SSC. This is the key finding.

**Remove the R-squared column from the within-tier SSC table.** It adds no information and will confuse reviewers.

---

## 5. Answers to the 8 Questions

### Q1: Unknown collection method R-squared=0.873

This is most likely site selection effects, not categorical encoding signal. Thirteen sites is a small sample, and if they happen to have high turbidity variance and clean turbidity-SSC relationships, R-squared will be high regardless of the method label. **Test this rigorously:** retrain the model with "unknown" recoded to the most common method (e.g., "auto_point") and evaluate those 13 sites. If R-squared barely changes, it is site characteristics. If it drops substantially, the model is leveraging the label. Also compute per-site R-squared for these 13 sites individually — if a few are very high and pull up the pooled number, it is site-level, not encoding-level.

### Q2: Low-SSC bias (+121%) and loss function

Yes, this is directly related to the loss function. RMSE in Box-Cox space (lambda=0.2) heavily weights large absolute errors, which occur at high SSC. A 50 mg/L error at SSC=20 mg/L is a 250% relative error but a small absolute error in Box-Cox space. The model rationally allocates its capacity to reducing large Box-Cox errors (i.e., getting high-SSC values right) at the expense of low-SSC precision.

Asymmetric loss could help, but I would first try a **simpler diagnostic:** compute the loss function contribution by SSC quintile. What fraction of the total Box-Cox loss comes from each quintile? If the bottom quintile contributes <5% of total loss, the model literally does not care about getting low SSC right. This diagnosis points to the solution: either reweight samples inversely by SSC (so low-SSC samples matter more) or use a loss that operates in relative space (log-scale or percent-error-based).

However, be careful what you optimize for. If the operational use case is sediment load estimation, +121% bias at low SSC barely matters because low SSC contributes negligibly to total load. If the use case is water quality compliance (e.g., "is SSC above 50 mg/L?"), then it matters enormously. Define the use case before changing the loss function.

### Q3: Within-tier R-squared alternatives

Addressed fully in Section 4. Use MAPE, MAE, median absolute percent error, and conditional bias. Drop R-squared from within-tier tables.

### Q4: Spring SSC/turbidity ratio higher than expected

Both explanations are partially correct, and they are not mutually exclusive. The holdout is dominated by temperate/subtropical sites with few high-latitude sites, so you are observing spring storms and agricultural tillage, not snowmelt. Snowmelt produces glacial flour and fine clays with high turbidity per unit SSC, which would *lower* the ratio. Spring storms on bare agricultural soil produce coarse sediment with low turbidity per unit SSC, which raises the ratio.

The proper test requires stratifying by latitude and land use. Compute the spring vs. non-spring ratio separately for (a) sites above 45 degrees N with >30% forest cover (likely snowmelt-influenced) vs. (b) sites below 40 degrees N with >30% agriculture (likely storm-driven). With only 1 site above 50 degrees N, you simply cannot test the snowmelt hypothesis with this holdout. Acknowledge this limitation explicitly.

### Q5: Other physics-based phenomena to test

From a statistical perspective, the phenomena worth testing are those that would create **systematic, predictable bias patterns** in the model. I recommend:

- **Diurnal cycling:** Compute hour-of-day bias. If the model systematically overpredicts at night (when algal photosynthesis is absent and turbidity from organics drops), this is a confounding signal.
- **Baseflow vs. stormflow partitioning:** Use a baseflow separation index (e.g., ratio of sample turbidity to 30-day median turbidity). Model accuracy should differ between baseflow-dominated and event-dominated samples.
- **Post-fire sediment response:** If any holdout watersheds have recent burn scars, the turbidity-SSC relationship changes dramatically (charcoal particles are highly turbid but low density). Check for fire history in the watershed metadata.
- **Freeze-thaw cycles:** At sites with winter data, ice breakup and bank slumping produce sediment slugs with anomalous turbidity-SSC ratios.
- **Algal bloom interference:** Spring and fall algal blooms inflate turbidity without SSC. If chlorophyll-a data is available at any holdout site, test whether model bias correlates with chlorophyll.

### Q6: Better performance at high turbidity than low

Yes, this is expected from a tree-based model and from the physics.

**Statistical explanation:** Tree models partition the feature space into bins. At high turbidity, the turbidity-SSC relationship is approximately linear and the signal-to-noise ratio is high. At low turbidity, multiple confounders (dissolved organics, algae, fine clays, sensor noise) create a weak and noisy relationship. R-squared reflects the signal-to-noise ratio, so it is naturally higher where the signal is cleaner.

**Practical implication:** Yes, prediction intervals should be wider at low turbidity. Specifically, compute the empirical distribution of percent errors within each turbidity bin and report the 80% or 90% prediction interval. This is trivially easy to do from the holdout residuals and would add significant value to the paper.

### Q7: Auxiliary data for sensor saturation

From a statistical modeling perspective, useful auxiliary predictors for SSC when turbidity is clipped must satisfy two conditions: (a) they continue to vary when turbidity is saturated, and (b) they correlate with SSC conditional on turbidity being at ceiling.

Candidates ranked by expected information content:
1. **Discharge rate-of-change (dQ/dt):** Strong predictor of sediment supply during events. Available at most USGS sites. This is the single best auxiliary variable.
2. **Cumulative event precipitation (storm total):** Indicates event magnitude. Available from gridded products.
3. **Antecedent soil moisture or antecedent precipitation index:** Determines runoff generation and sediment availability. Available from gridded products.
4. **Time since last major event:** Sediment supply is exhaustible; the first big storm after a dry spell mobilizes more sediment than the third storm in a week.

Note: with only 43 samples above 1000 FNU and 18 above 5000 mg/L SSC, you do not have enough data to train a reliable auxiliary model. You would need to dramatically expand the extreme-event sample size, possibly by targeted data collection. This is indeed a Paper 2 problem.

### Q8: Missing standard goodness-of-fit statistics

Addressed fully in Section 2. The critical gaps are NSE, log-NSE, KGE with decomposition, PBIAS (clearly defined), RMSE by disaggregated cell, volume/load error, and SSC-duration curve metrics. Any submission to WRR or Environmental Modelling & Software without NSE and KGE will be returned at desk review.

---

## 6. Additional Statistical Tests Before Publication

### Required

1. **Bootstrap confidence intervals on all reported metrics.** Use site-level block bootstrap (resample sites, not individual observations) to account for within-site correlation. Report 95% CIs on pooled R-squared, KGE, PBIAS, NSE.

2. **Formal test for spatial autocorrelation in residuals.** Sites in the same HUC or with similar watershed characteristics may have correlated errors. Compute Moran's I on per-site mean residuals using the geographic coordinates. If significant, the effective sample size (76 sites) is inflated.

3. **Residual diagnostics:** Plot residuals vs. predicted values, vs. each key predictor, and vs. time. Look for heteroscedasticity, non-random patterns, and temporal trends. Report the Breusch-Pagan test for heteroscedasticity (I expect it to be significant given the SSC-dependent bias pattern).

4. **Per-site performance distribution:** Report the full distribution of per-site R-squared (or per-site KGE) across the 76 holdout sites — not just the pooled number. The pooled R-squared can be dominated by a few high-variance sites. Report the median per-site R-squared and the interquartile range.

5. **Comparison to naive baselines:** Report the performance of at least two baselines: (a) site-mean predictor (predicts the training-set mean SSC for each site), and (b) simple power-law regression SSC = a * Turbidity^b (the traditional USGS approach). Without baselines, R-squared=0.665 is uninterpretable — is this good or bad? A reviewer will ask.

### Strongly Recommended

6. **Cross-validation vs. holdout consistency:** The CV R-squared(native) is 0.290 but the holdout R-squared(native) is 0.472. This discrepancy needs explanation. Is the holdout set easier? Are the holdout sites systematically different from training sites? Compare the distribution of key watershed characteristics (drainage area, % agriculture, mean annual precipitation) between training and holdout sets.

7. **Sensitivity to holdout split:** The current holdout is a single 76-site draw from 396 sites. How sensitive are the results to which sites are held out? Run at least 5 random holdout splits and report the variance in pooled metrics. If the variance is large, the single-split results are unreliable.

8. **Influence diagnostics:** Identify the 5-10 most influential sites (those whose removal changes pooled metrics the most). Report whether the conclusions depend on a handful of sites.

---

## 7. Temporal Stationarity Testing

The document does not test for temporal stationarity, which is a serious gap for a model that will be applied in real-time.

### Proper Testing Protocol

1. **Split-by-time validation:** Within each holdout site, split data into early (first 50%) and late (last 50%) by date. Compare per-site bias and MAE between the two periods. A paired t-test or Wilcoxon signed-rank test across sites detects systematic temporal drift.

2. **Year-over-year bias trends:** For sites with multi-year records, compute annual bias. Regress annual bias against year. A significant slope indicates non-stationarity (sensor drift, land use change, channel evolution).

3. **Seasonal decomposition:** Compute monthly bias (averaged across sites). Report whether the model has systematic seasonal patterns. The spring result (R-squared=0.421 vs. 0.700 for other seasons) suggests it does.

4. **Change-point detection:** Apply the Pettitt test or CUSUM test to the per-site residual time series. Flag sites where the error distribution shifts over time. These are sites where the turbidity-SSC relationship has changed — likely due to sensor replacement, channel migration, or upstream land use change.

5. **Training-period vs. application-period performance:** If the model will be deployed forward in time, the relevant test is: does performance degrade for observations that are temporally far from the training data? Compute performance as a function of temporal distance from the nearest training observation.

### Why This Matters

Turbidity sensors drift. Channels evolve. Land use changes. A model trained on 2010-2020 data may not perform the same on 2025 data. If you cannot demonstrate temporal robustness, the operational value claim is weakened.

---

## 8. Adversarial and Stress Tests

### Statistically Meaningful Stress Tests

1. **Leave-one-region-out (LORO):** Train on all HUC2 regions except one, predict the held-out region. This tests geographic generalization more rigorously than LOGO (which leaves out individual sites). If performance collapses for certain regions, the model cannot claim national applicability.

2. **Extrapolation beyond training range:** Identify holdout observations where any feature value exceeds the training range (e.g., turbidity higher than any training sample, drainage area larger than any training watershed). Report performance separately for in-range vs. extrapolated predictions. Tree models cannot extrapolate — they will predict the value of the nearest leaf, which may be arbitrarily wrong.

3. **Synthetic sensor degradation:** Add realistic noise to the turbidity input (e.g., +/-10%, +/-20%, random dropouts) and measure performance degradation. This simulates real-world sensor problems.

4. **Worst-site analysis:** Report the 10 worst-performing holdout sites by KGE. Characterize what makes them different (geology, drainage area, land use, data quality). This is more informative than aggregate metrics for understanding failure modes.

5. **Subsample stability:** For the 10 best and 10 worst sites, randomly subsample to n=20 observations 100 times and report the variance of per-site metrics. This tests whether the per-site results are stable or driven by a few extreme observations.

6. **Feature knockout:** Remove one feature group at a time (all watershed features, all temporal features, all weather features) and evaluate on the holdout set. This reveals which feature groups drive the model's cross-site generalization vs. its within-site accuracy.

7. **Permutation test for cross-site skill:** Randomly permute the site labels (assign each site's watershed features to a different site's observations) and evaluate. If performance drops substantially, the watershed features are providing real cross-site information. If it barely changes, the model is essentially doing per-site regression on turbidity alone.

---

## Summary of Critical Actions

In priority order:

1. **Compute NSE, log-NSE, KGE (with decomposition), and PBIAS for all disaggregated cells.** This is table stakes for a hydrology journal submission.

2. **Remove R-squared from within-tier and within-band tables.** Replace with MAPE, MAE, and conditional bias.

3. **Report bootstrap confidence intervals** (site-level block bootstrap) on all key metrics.

4. **Report per-site performance distributions** (median, IQR, worst decile of per-site KGE).

5. **Add baseline comparisons** (site-mean predictor, site-specific power-law regression).

6. **Test temporal stationarity** using split-by-time validation and annual bias trends.

7. **Flag small-n cells** (<30 observations) with confidence intervals; exclude <20 from inferential tables.

8. **Clarify the bias definition** (formula, units, mean vs. median).

The model shows genuine skill for high-variability, sedimentary-geology sites in the continental US. The diagnostics are honest about the limitations. But the statistical evaluation needs to meet journal standards before any publication claims are made. The framework is solid — it just needs the right metrics.

---

*Review completed 2026-03-30. Dr. Ananya Krishnamurthy, Applied Environmental Statistics.*
