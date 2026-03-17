# Dr. Ananya Krishnamurthy — Environmental Statistics Review

**Panel Role:** Environmental Statistician
**Date:** 2026-03-16
**Reviewed Materials:** PRODUCT_VISION.md, physics_panel_plan.md, project codebase structure

---

## Question 1: How should non-detects be handled in a multi-target ML model?

### The problem with DL/2 substitution (current approach)

The current DL/2 approach (replacing values below the detection limit with half the detection limit) is a known source of bias. Dennis Helsel's foundational work — *Nondetects and Data Analysis: Statistics for Censored Environmental Data* (Wiley, 2005) and his 2006 ES&T paper "Better Methods for Interpreting Nondetect Data" — demonstrates that DL/2:

- **Distorts variance estimates.** Even when mean estimation bias is modest, the standard deviation is systematically underestimated because the substituted values cluster artificially around a single point. This matters for your quantile regression prediction intervals.
- **Distorts correlations between parameters.** In a multi-target model, DL/2 substitution on one target (say, total phosphorus) will attenuate the observed correlation between that target and other targets (say, SSC). This directly undermines the multi-target value proposition — you are destroying the inter-parameter signal before the model can learn it.
- **Creates artifacts at the detection limit.** A spike of values at DL/2 creates a false mode in the distribution. CatBoost will learn this artifact.

That said, a nuanced finding from Antweiler & Taylor (2008, ES&T, "Evaluation of Statistical Treatments of Left-Censored Environmental Data Using Coincident Uncensored Data Sets") showed that for datasets with low censoring rates (<15-20%), the practical difference between methods can be small for estimating means. The question is: what are your censoring rates?

### Recommended approach: tiered strategy based on censoring rate

**For training data:**

1. **If censoring rate < 10% for a given parameter across your dataset:** DL/2 is acceptable for a first-pass model. The bias is small relative to other sources of error in a cross-site transfer setting. Do not let perfect be the enemy of good.

2. **If censoring rate is 10-40%:** Use **maximum likelihood estimation (MLE)** with an assumed distributional form (lognormal is standard for concentrations). In the ML context, this means modifying the loss function: for uncensored observations, use normal loss on log-transformed values; for censored observations, use the cumulative distribution function to compute the likelihood of observing a value below DL. This is essentially a Tobit model. Recent work by Quadrianto et al. (2024, *Pattern Analysis and Applications*) demonstrates that a Tobit-style loss function works with neural networks and gradient-based optimization. The same principle applies to gradient boosting: you can define a custom loss function in CatBoost.

3. **If censoring rate > 40%:** That parameter probably should not be a prediction target at that site, or you need to reformulate the problem as classification (above/below threshold) rather than regression.

**For evaluation data:**

- **Never substitute DL/2 in the test set and compute R-squared or RMSE as if those were real values.** This is a common and serious error.
- Report metrics separately for uncensored observations only.
- For censored test observations, evaluate using a probability-based metric: does the model's predicted distribution assign appropriate probability mass below the detection limit? This is essentially a censored likelihood score.
- Report the censoring rate for each parameter at each site so readers can judge how informative the metrics are.

### Practical implementation for a solo developer

The simplest defensible improvement over DL/2:

```python
# CatBoost custom objective for left-censored data (sketch)
# For censored observations: contribute log(Phi((log(DL) - mu) / sigma))
# For uncensored observations: contribute normal log-likelihood
# Where mu is the model prediction, sigma is estimated from residuals
```

However, this requires a custom loss function in CatBoost, which is nontrivial. A pragmatic middle ground:

- **Step 1 (immediate):** Document the censoring rate per parameter per site. If it is under 10% everywhere, keep DL/2 and move on. This is an honest decision, not a lazy one.
- **Step 2 (if censoring matters):** Use **Kaplan-Meier (KM) estimation via the `cenken` function in R's `NADA2` package or the `lifelines` Python package** to compute summary statistics and verify that DL/2 is not materially distorting your distributions. If KM and DL/2 give similar means and standard deviations, you have evidence that DL/2 is adequate.
- **Step 3 (for the paper):** Implement a sensitivity analysis. Train the model twice — once with DL/2, once with DL/sqrt(2) (which assumes lognormal, not uniform, distribution below DL). If results are materially identical, report that and move on. If they differ, you need the Tobit approach.

### Key references

- Helsel, D.R. (2012). *Statistics for Censored Environmental Data Using Minitab and R*, 2nd ed. Wiley.
- Helsel, D.R. (2006). Fabricating data: How substituting values for nondetects can ruin results, and what can be done. *Chemosphere*, 65(11), 2434-2439.
- Antweiler, R.C. & Taylor, H.E. (2008). Evaluation of statistical treatments of left-censored environmental data. *Environ. Sci. Technol.*, 42(10), 3732-3738.
- Shoari, N. & Dubé, J.S. (2018). Toward improved analysis of concentration data: Embracing nondetects. *Environ. Toxicol. Chem.*, 37(3), 643-656.
- Quadrianto, N. et al. (2024). A deep learning approach to censored regression. *Pattern Analysis and Applications*, 27, 37.

---

## Question 2: Multi-target prediction validation — what metrics beyond per-parameter R-squared?

### Why per-parameter R-squared is insufficient

R-squared per parameter tells you how well each target is predicted marginally. It says nothing about whether the model has learned the *joint* structure — i.e., the correlations between targets. A model that predicts each parameter independently using only shared features will achieve decent per-parameter R-squared while completely ignoring inter-parameter dependencies. You need metrics that distinguish "good multi-target model" from "five independent models stacked together."

### Recommended metrics framework

Report metrics at three levels:

#### Level 1: Marginal accuracy (per-parameter, what you already have)

- **R-squared** (coefficient of determination) — but compute on original scale, not log scale. Log-scale R-squared inflates perceived performance.
- **RMSE and MAE** on original scale — more interpretable for practitioners.
- **Median absolute percentage error (MdAPE)** — robust to outliers, intuitive.
- **Nash-Sutcliffe Efficiency (NSE)** — standard in hydrology, and reviewers will expect it. NSE = 1 - (sum of squared errors / sum of squared deviations from mean). Same as R-squared when the model is fit on the same data, but differs in cross-validation because the baseline mean is computed from training data.
- **Bias (mean error)** — critical to report. A model with low RMSE but systematic positive bias will overestimate loads, which has regulatory consequences.

#### Level 2: Joint prediction accuracy (multi-target specific)

These metrics evaluate whether the model captures inter-parameter relationships:

1. **Correlation structure preservation.** Compute the empirical correlation matrix of observed targets (e.g., cor(SSC, TP), cor(DO, temperature)) on the test set. Compute the same correlation matrix from predicted targets. Compare them. Specifically:
   - Report the element-wise difference between observed and predicted correlation matrices.
   - A formal test: the **Jennrich test** (1970) for equality of two correlation matrices. This tells you whether the predicted correlation structure is statistically distinguishable from the observed one.
   - Simpler: for each pair of targets, compute the Pearson correlation of the *residuals*. If the multi-target model has successfully captured inter-parameter dependencies, the residual correlations should be near zero. If residual correlations are large, the model is leaving joint structure on the table.

2. **Energy Score** (Gneiting & Raftery, 2007). This is the multivariate generalization of the Continuous Ranked Probability Score (CRPS). It evaluates the quality of a multivariate probabilistic forecast. If you are producing prediction intervals via quantile regression, you can generate pseudo-ensemble predictions and compute the energy score. Limitation: the energy score is more sensitive to marginal calibration than to dependence structure (Scheuerer & Hamill, 2015).

3. **Variogram Score** (Scheuerer & Hamill, 2015, *Monthly Weather Review*). This score specifically targets the dependence structure and is more sensitive than the energy score to misspecified correlations between targets. Use variogram score with p=0.5 as recommended in the literature.

#### Level 3: Ablation to prove multi-target adds value

This is the most important evaluation and the one reviewers will ask for:

- Train the same model architecture as **independent single-target models** (one CatBoost per parameter, no shared information).
- Compare joint metrics (Level 2) and marginal metrics (Level 1) against the multi-target model.
- If the multi-target model does not improve over independent models in either marginal or joint metrics, the multi-target architecture is not earning its complexity. This is a legitimate finding — report it honestly.

### Evaluating cross-site transfer specifically

Since you use leave-one-site-out CV, report all metrics **per held-out site** and show the distribution across sites (box plots, not just averages). The variance across sites is as important as the mean — it tells you how reliably the model transfers. A model with mean R-squared = 0.7 but ranging from 0.1 to 0.95 across sites is fundamentally different from one with R-squared = 0.7 +/- 0.05.

### Practical implementation

Python packages:
- `properscoring` for CRPS (univariate).
- `scoringRules` (R package) for energy score and variogram score — no mature Python equivalent exists, but the formulas are straightforward to implement. The energy score for an ensemble is: ES = E||X - y|| - 0.5 * E||X - X'|| where X, X' are independent draws from the forecast distribution and y is the observation.
- Correlation matrix comparison is trivial with numpy/scipy.

### Key references

- Gneiting, T. & Raftery, A.E. (2007). Strictly proper scoring rules, prediction, and estimation. *J. Am. Stat. Assoc.*, 102(477), 359-378.
- Scheuerer, M. & Hamill, T.M. (2015). Variogram-based proper scoring rules for probabilistic forecasts of multivariate quantities. *Mon. Weather Rev.*, 143(4), 1321-1334.
- Borchani, H. et al. (2015). A survey on multi-output regression. *WIREs Data Min. Knowl. Disc.*, 5(5), 216-233.

---

## Question 3: How to properly quantify prediction uncertainty in cross-site transfer?

### The fundamental challenge

Your setting is unusually hard for uncertainty quantification: the test site has *never been seen* by the model. This is not standard out-of-sample prediction — it is out-of-distribution prediction. The hydrological regime, geology, land use, and sensor characteristics at the test site may differ from anything in the training set. Standard prediction intervals (including your current quantile regression approach) are not guaranteed to have correct coverage in this setting.

### Assessment of current approach: quantile regression

Your current approach — CatBoost quantile regression predicting, say, the 5th and 95th percentiles — is a reasonable starting point but has specific weaknesses:

- **No coverage guarantee.** Quantile regression prediction intervals have correct coverage *on average across the training distribution*. For a site that is systematically different from training sites (e.g., a glacial-melt-dominated stream when your training is mostly rain-dominated), the intervals can be arbitrarily wrong.
- **Intervals may be too narrow for unusual sites.** If the model has never seen a site like the test site, it has no basis for wide intervals — it does not know what it does not know.
- **Crossing quantiles.** CatBoost quantile regression fits separate models for each quantile, so predicted quantiles can cross (the 95th percentile prediction may be below the 5th percentile prediction for some observations). This is a known issue.

### Recommended approach: Conformalized Quantile Regression (CQR)

The strongest practical upgrade is **Conformalized Quantile Regression (CQR)**, introduced by Romano, Patterson & Candes (2019, NeurIPS). CQR wraps quantile regression with a conformal calibration step that provides a *finite-sample coverage guarantee* under the exchangeability assumption.

**How it works:**

1. Split your data into training, calibration, and test sets.
2. Train CatBoost quantile regression on the training set (as you currently do).
3. On the calibration set, compute conformity scores: how much you'd need to expand each interval to cover the true value.
4. Take the (1-alpha) quantile of these scores.
5. Expand all test intervals by this amount.

**The catch for cross-site transfer:** CQR's coverage guarantee assumes exchangeability between calibration and test data. In leave-one-site-out CV, the test site may violate exchangeability because it is drawn from a different distribution than the calibration sites. However, empirically CQR still produces much better-calibrated intervals than raw quantile regression, even under moderate distribution shift.

**Implementation:** The `MAPIE` Python library (v1.x) provides `MapieQuantileRegressor` which implements CQR directly and wraps around any scikit-learn-compatible regressor. CatBoost is scikit-learn-compatible. This is a near-drop-in replacement for your current approach.

```python
from mapie.regression import MapieQuantileRegressor
# Wrap your CatBoost quantile model with MAPIE for CQR
```

### Addressing the distribution shift problem

For the specific case where the test site may be genuinely out-of-distribution, consider these additional strategies:

1. **Weighted conformal prediction.** If you can quantify how similar the test site is to training sites (e.g., using catchment attributes to compute a distance metric), you can weight the calibration scores by similarity. Closer calibration sites get more weight. This is distribution-shift-aware conformal prediction (Tibshirani et al., 2019, "Conformal prediction under covariate shift", *Ann. Stat.*).

2. **Site-similarity-based interval scaling.** Compute a "novelty score" for each test site — how far its catchment attributes are from the convex hull of training site attributes (e.g., using Mahalanobis distance or isolation forest anomaly score). Scale prediction intervals by this novelty score. This is heuristic but interpretable: "this site is unlike anything we've trained on, so intervals are wide."

3. **Ensemble disagreement.** If you train multiple CatBoost models (e.g., with different random seeds or subsets of features), the variance of predictions across ensemble members provides a model-based uncertainty estimate. Where ensemble members disagree, uncertainty is high. This is free if you're already doing any form of ensembling.

### What to report

- **Calibration plots.** For each nominal coverage level (50%, 80%, 90%, 95%), plot actual coverage vs. nominal coverage, stratified by site. This is the single most informative diagnostic.
- **Prediction Interval Coverage Probability (PICP):** the fraction of observations falling within the interval. Report per site.
- **Mean Prediction Interval Width (MPIW):** average width of intervals. Report per site. There is always a tradeoff — wider intervals trivially achieve better coverage.
- **Interval Score** (Gneiting & Raftery, 2007): a proper scoring rule that penalizes both miscoverage and interval width. This is the single best metric for interval quality.

### Practical recommendation for a solo developer

1. **Immediate:** Keep quantile regression but add calibration plots. Just knowing whether your intervals are miscalibrated is 80% of the value.
2. **Next step:** Implement CQR via MAPIE. This is a small code change with large statistical payoff.
3. **For the paper:** Add weighted conformal prediction using site-similarity weights, or at minimum stratify calibration results by site novelty (near vs. far from training distribution).

### Key references

- Romano, Y., Patterson, E. & Candes, E. (2019). Conformalized quantile regression. *NeurIPS 2019*.
- Tibshirani, R.J. et al. (2019). Conformal prediction under covariate shift. *Ann. Stat.*, 47(5), 2999-3028.
- MAPIE documentation: https://mapie.readthedocs.io/
- Angelopoulos, A.N. & Bates, S. (2023). Conformal prediction: A gentle introduction. *Found. Trends Mach. Learn.*, 16(4), 494-591.

---

## Question 4: Accounting for USGS grab sample sampling bias

### The nature of the bias

USGS discrete water quality samples are collected under a **targeted sampling design**, not a random or systematic design. This creates several interacting biases:

1. **Temporal access bias.** Samples are overwhelmingly collected during business hours on weekdays. Nighttime and weekend conditions — which may have different temperature, DO, and biological activity profiles — are systematically underrepresented. This matters less for SSC (which is flow-driven) but matters for DO and nutrient cycling.

2. **Flow-condition bias (the big one).** At some sites, USGS intentionally oversamples storm events to characterize sediment transport during high flows (critical for load estimation). At other sites, storms are underrepresented because field crews cannot safely access the site during floods. This creates a heterogeneous, site-specific bias: some sites have heavy-tailed sample distributions (lots of high-flow, high-SSC samples) while others have truncated distributions (missing the high end entirely).

3. **Seasonal bias.** Winter sampling is less frequent due to ice, road conditions, and field safety. Sites in Montana, Idaho, and Colorado will have sparser winter records than sites in Virginia or Kansas. Spring snowmelt, which drives the annual sediment pulse in rain-snow transition watersheds (your north Idaho sites), may be undersampled.

4. **Site-selection bias.** The 57 USGS sites in your dataset are not a random sample of US rivers. They are sites with both continuous sensors AND discrete sampling programs, which biases toward larger, more important, or better-funded watersheds.

### How this affects training

If you train a model to minimize mean squared error on this dataset, the model will optimize for the conditions that are most common *in the sample*, not conditions that are most common *in reality*. Concretely:

- At storm-oversampled sites, the model will be well-calibrated for high flows but may under-learn baseflow relationships.
- At storm-undersampled sites, the model will be well-calibrated for baseflow but will extrapolate (with unknown error) during storms.
- The cross-site model will implicitly average over these heterogeneous biases, which partially cancels out — but the cancellation is uncontrolled and may not produce correct predictions for any individual site.

### How this affects evaluation

This is actually the more insidious problem. If you evaluate on the same biased sample, your metrics reflect model performance on the *sampled* conditions, not on the *real-world* conditions the model will encounter in deployment. An R-squared of 0.85 computed on a storm-oversampled test set does not mean R-squared = 0.85 for the full range of conditions at that site.

### Recommended corrections

#### For training:

1. **Stratified weighting by flow regime.** Classify each sample into flow regimes (e.g., baseflow, rising limb, peak, falling limb) using the continuous discharge record. Compute the fraction of time the site spends in each regime vs. the fraction of samples in each regime. Weight training samples by the inverse of their overrepresentation:

   ```
   weight_i = (fraction of time in regime_k) / (fraction of samples in regime_k)
   ```

   This is a form of **inverse probability weighting (IPW)** adapted from the survey sampling literature (Horvitz & Thompson, 1952). CatBoost natively supports sample weights.

   **Practical simplification:** Rather than formal flow regime classification, bin the continuous discharge record into quantiles (e.g., quartiles) and weight samples by how over/under-represented their flow quantile is.

2. **Flow-duration weighting.** Use the flow duration curve at each site (available from the continuous discharge record). For each sample, determine what exceedance probability its discharge represents. Weight by the density of the flow duration curve at that exceedance probability. Samples from frequently occurring flows get more weight; samples from rare extremes get less (unless you specifically care about extreme events, in which case reverse this).

3. **Do NOT correct for weekday/time-of-day bias** unless you have evidence it matters for your parameters. For SSC and sediment transport, which are flow-driven, the day-of-week effect is negligible. For DO (which has a diel cycle), it could matter — but correcting for it adds complexity without clear benefit given your current scope.

#### For evaluation:

1. **Report metrics stratified by flow condition.** At minimum, report performance separately for:
   - Low flow (below median discharge)
   - Medium flow (median to 75th percentile)
   - High flow (above 75th percentile)
   - Storm events (if identifiable from the hydrograph)

   This is more informative than a single R-squared and directly reveals where the model succeeds and fails.

2. **Flow-weighted metrics for load estimation.** If the model will be used to estimate loads (concentration x discharge, integrated over time), evaluate the load estimation accuracy directly. A model that is poor at predicting storm concentrations but excellent at baseflow will produce terrible load estimates because storms dominate annual loads.

3. **Bootstrap within flow strata.** When computing confidence intervals on your performance metrics, bootstrap within flow strata to avoid the bootstrap sample reproducing the same sampling bias. Standard bootstrapping of the biased sample will produce a confidence interval on "performance as evaluated on the biased sample" — not on "performance in reality."

#### For the paper (reporting):

1. **Characterize the sampling distribution.** For each site, report:
   - Number of samples
   - Date range
   - Flow exceedance probability distribution of samples vs. the full flow record
   - Seasonal distribution (samples per month vs. uniform)

   This lets readers judge the representativeness of your results themselves.

2. **Acknowledge the limitation explicitly.** State that model performance metrics reflect performance on the sampled conditions, which overrepresent [whatever your data shows] relative to the full hydrologic regime. This is standard practice and will be expected by reviewers.

3. **Site-selection bias is acceptable to acknowledge but not correct for.** Your 57 sites are what they are. You cannot extrapolate performance to the universe of all US rivers. But you can describe the diversity of your sites (ecoregions, drainage areas, land use, climates) and argue that the diversity provides reasonable coverage.

### Practical implementation for a solo developer

**Priority 1 (do first, high impact, low effort):** Stratify your evaluation metrics by flow quantile. You already have continuous discharge data. Bin it. Report metrics per bin. This takes an hour and dramatically improves the informativeness of your evaluation.

**Priority 2 (moderate effort, solid improvement):** Implement flow-quantile sample weighting for training. CatBoost's `sample_weight` parameter makes this trivial once you compute the weights. You need:
- The continuous discharge record at each site (you have this).
- A flow-duration curve or quantile binning (simple computation).
- The weight for each sample = (fraction of record in that flow bin) / (fraction of samples in that flow bin).

**Priority 3 (for the paper):** Full characterization of sampling distribution per site, including the figure showing sample flow exceedance probabilities vs. the full flow duration curve. This figure alone will address most reviewer concerns about sampling bias.

### Key references

- Helsel, D.R. & Hirsch, R.M. (2002). *Statistical Methods in Water Resources*. USGS Techniques of Water-Resources Investigations, Book 4, Ch. A3. (The standard reference for USGS statistical methods.)
- Diggle, P.J., Menezes, R. & Su, T. (2010). Geostatistical inference under preferential sampling. *J. R. Stat. Soc. C*, 59(2), 191-232. (Foundational paper on preferential sampling bias.)
- Hestir, E.L. et al. (2024). On the impact of preferential sampling on ecological status and trend assessment. *Ecological Modelling*, 489, 110612.
- Horvitz, D.G. & Thompson, D.J. (1952). A generalization of sampling without replacement from a finite universe. *J. Am. Stat. Assoc.*, 47(260), 663-685. (The IPW estimator.)
- Roberts, D.R. et al. (2017). Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure. *Ecography*, 40(8), 913-929.

---

## Summary of Recommendations by Priority

| Priority | Action | Effort | Impact |
|----------|--------|--------|--------|
| 1 | Stratify evaluation metrics by flow quantile | 1 hour | High — reveals where model actually works |
| 2 | Add calibration plots for prediction intervals | 2 hours | High — shows if intervals are honest |
| 3 | Document censoring rates per parameter per site | 1 hour | Medium — determines if non-detect handling matters |
| 4 | Implement flow-quantile sample weights in training | 3 hours | Medium — corrects dominant sampling bias |
| 5 | Replace raw quantile regression with CQR via MAPIE | 4 hours | High — proper coverage guarantee |
| 6 | Add residual correlation analysis for multi-target | 2 hours | Medium — proves multi-target adds value |
| 7 | Implement sensitivity analysis (DL/2 vs DL/sqrt(2)) | 3 hours | Low-Medium — needed for paper, may not change results |
| 8 | Add energy/variogram scores | 4 hours | Medium — needed for a rigorous multi-target paper |

### A note on Duan's smearing estimator

The current use of log1p transform with Duan's smearing estimator for back-transformation is appropriate for the SSC prediction task. Duan (1983) provides a nonparametric bias correction that is robust to non-normality of log-scale residuals — a real advantage over the parametric Ferguson (1986) correction, which assumes normality. Keep this. However, verify that the smearing factor is computed from held-out residuals (not training residuals) when used in cross-validation, otherwise you introduce optimistic bias. If the smearing factor is computed from training-set residuals and applied to test-set predictions, the bias correction may be slightly off for sites with different error distributions. A per-site or per-flow-regime smearing factor would be more defensible if you have enough data.

---

*Review prepared by Dr. Ananya Krishnamurthy, Environmental Statistician. This review reflects my professional judgment based on 12 years of applied environmental statistics work. I have no conflicts of interest with this project.*
