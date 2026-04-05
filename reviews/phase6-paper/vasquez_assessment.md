# UQ Assessment: murkml v11 for WRR Submission

**Reviewer:** Dr. Elena Vasquez, Uncertainty Quantification Specialist
**Date:** 2026-04-02
**Scope:** Empirical conformal intervals, Bayesian site adaptation, dual BCF, bootstrap CIs, CQR failure analysis

---

## 1. Overall UQ Assessment

**Verdict: Conditionally publishable, with required revisions.**

The UQ story has laudable breadth -- five distinct components (conformal intervals, Bayesian adaptation, dual BCF, bootstrap CIs, CQR failure) -- which is more UQ machinery than most WRR papers attempt. The honesty about the CQR failure and the 52% extreme-SSC coverage is commendable and distinguishes this from papers that quietly sweep tail failures under the rug.

However, the UQ is **marginal-coverage only** (pooled across sites), not conditional on any operationally relevant covariate except predicted SSC bin. The paper makes no claim about per-site coverage, per-geology coverage, or per-event coverage, which is fine as long as this limitation is explicitly stated. The 90.6% overall coverage is encouraging but it hides a fatal tail problem that could mislead users who need the intervals most (during extreme events).

The Bayesian adaptation framework is the strongest UQ component -- principled, well-motivated, and demonstrably superior to OLS. The dual BCF is the weakest -- it walks a fine line between methodologically defensible and ad hoc metric optimization.

**Bottom line:** With the revisions below, this is publishable in WRR. Without them, a UQ-aware reviewer will flag the conformal intervals as misleadingly reassuring and the BCF as inadequately justified.

---

## 2. Empirical Conformal Intervals Critique

### 2.1 Is the Mondrian approach appropriate?

Yes, conditionally. Mondrian conformal prediction (Vovk et al., 2005) is the correct framework when you expect heteroscedastic nonconformity scores, which SSC residuals clearly exhibit (median absolute error ranges from 5.5 mg/L at low SSC to 1,102 mg/L at extreme SSC -- a 200x range). Binning by predicted SSC magnitude is the natural Mondrian partition for this problem.

**However**, the implementation is not standard conformal prediction -- it is empirical quantile intervals on residuals, which only provides finite-sample validity guarantees under the exchangeability assumption. The paper calls this "empirical conformal prediction intervals using a Mondrian approach," which is technically correct but may overstate the theoretical guarantees. True split conformal prediction provides coverage guarantees for any distribution under exchangeability. What is implemented here -- computing the 5th and 95th percentiles of residuals within bins -- provides asymptotic coverage but not the finite-sample guarantee that makes conformal prediction theoretically distinctive.

**Recommendation:** Either (a) implement true split conformal (use the (1-alpha)(1+1/n)-th quantile of nonconformity scores, not the alpha/2 percentile of residuals), or (b) be explicit that this is "empirical residual-based prediction intervals with Mondrian binning" rather than conformal prediction per se. The distinction matters for reviewers familiar with the conformal literature. At n=252 calibration samples in the 2000+ bin, the finite-sample correction would shift the quantile noticeably.

### 2.2 Coverage: Marginal or Conditional?

The 90.6% overall coverage is **marginal coverage pooled across sites and conditions.** This is explicitly not conditional coverage in any meaningful sense. The Mondrian bins provide a coarse form of conditional coverage (conditional on predicted SSC bin), but:

- **Per-bin coverage at 90% nominal:** 92%, 91%, 89%, 91%, 52%. The first four bins are well-calibrated. The 2000+ bin at 52% is a catastrophic failure of conditional coverage.
- The 80% intervals tell the same story but worse: 76%, 79%, 76%, 83%, 35% at 2000+. The 35% number means the 80% intervals contain only one-third of extreme observations.
- **Per-site coverage is unreported.** Some sites may have 100% coverage (intervals too wide) and others 50% (intervals too narrow). Without per-site coverage statistics, the 90.6% is an average that may not apply to any individual site.

The continuous interpolation approach is actually WORSE for extremes: 19.4% coverage at 2000+ (vs. 52% binned). This is because the continuous knots extrapolate poorly beyond the last knot at 2066 mg/L.

### 2.3 The 52% Problem

This is the single most important UQ finding in the paper and it needs more treatment than a parenthetical. At >2000 mg/L:

- n_holdout = 31 samples (tiny)
- n_calibration = 252 samples (marginal)
- Coverage = 52% at 90% nominal
- Interval width = 8,304 mg/L median -- already enormous, yet still insufficient

The root causes are: (1) the residual distribution in this bin is extremely heavy-tailed and skewed, so the 5th/95th percentiles of calibration residuals do not bound the holdout residuals; (2) 252 calibration samples is insufficient to estimate the 95th percentile of a heavy-tailed distribution; (3) the model has a systematic -25% underprediction bias at extreme SSC that shifts the entire residual distribution, so intervals centered on biased predictions cannot achieve nominal coverage.

**Recommendation:** This needs its own paragraph in the Results or Discussion, not just a parenthetical in Section 4.8. The paper should explicitly state: "Prediction intervals for SSC > 2000 mg/L should not be used for decision-making without additional site-specific validation."

### 2.4 How does this compare to what CQR would have provided?

CQR (Romano et al., 2019) would have provided three advantages: (1) adaptive interval widths learned from the data rather than fixed per-bin offsets; (2) conditional coverage guarantees (asymptotic) at each prediction; (3) no need for arbitrary bin boundaries. The failure of CQR is real and well-diagnosed -- Box-Cox compression prevents Q95 from reaching extreme native-space values -- but it means the paper is stuck with a strictly inferior UQ method. This should be framed honestly: the empirical conformal approach is a fallback, not a first choice.

### 2.5 Violated Assumptions

1. **Exchangeability between calibration (LOGO CV) and holdout:** LOGO CV predictions are out-of-fold but still come from models that saw ~97% of the same training sites. Holdout sites are truly unseen. The nonconformity score distribution at holdout sites may be systematically different (wider) than at LOGO CV sites. The 90.6% coverage suggests this gap is small, but it is not zero.

2. **Stationarity:** The paper acknowledges temporal non-stationarity (Section 6.3) but does not discuss its implications for the conformal intervals specifically. If the turbidity-SSC relationship drifts over time, intervals calibrated on historical data will under-cover future predictions.

3. **Independence within bins:** Residuals within the same bin at the same site are temporally autocorrelated (lag-1 up to 0.69). This means the effective calibration sample size is smaller than n_calibration, and the percentile estimates are less precise than they appear.

---

## 3. Bayesian Site Adaptation Critique

### 3.1 Prior Selection: k=15, df=4

The Student-t prior with k=15 and df=4 is motivated by the heavy-tailed residual distribution (skewness=2.0, kurtosis=13.8). This is a good qualitative motivation. However:

- **k=15 is the shrinkage strength.** At N=2, the effective shrinkage is N/(N+k_eff) where k_eff = k * w_t. With w_t near 1 for typical residuals, this gives 2/(2+15) = 11.8% trust in the data. At N=10, it is 10/(10+15) = 40%. This seems reasonable but I see no formal sensitivity analysis.
- **df=4 for the Student-t influence function** controls how much extreme sites are downweighted. With df=4, the influence function is (4+1)/(4+z^2) = 5/(4+z^2). At z=2 (moderately extreme), w_t = 0.625. At z=4 (very extreme), w_t = 0.25. This provides moderate robustness without being as aggressive as Cauchy (df=1).
- **No sensitivity analysis is reported.** How sensitive is the adaptation curve to k=10 vs k=15 vs k=20? To df=2 vs df=4 vs df=8? The current values may be optimal, but without a sweep, a reviewer can reasonably ask whether they were tuned on the holdout set.

**Recommendation:** Run a 3x3 sensitivity grid (k in {10, 15, 20}, df in {2, 4, 8}) on the holdout set and report the range of MedSiteR2 values. If the range is narrow (say, <0.02), state that the adaptation is robust to prior choice. If it is wide, acknowledge that the prior was selected for the reported dataset and may need re-tuning. This is a one-afternoon experiment.

### 3.2 Staged Adaptation (Intercept-Only N<10, Slope+Intercept N>=10)

This is a sensible heuristic. With N<10, there is insufficient data to estimate both a slope and intercept without massive overfitting. The intercept-only correction at small N is equivalent to a location shift in transformed space, which is the most parsimonious correction available.

The N=10 threshold is somewhat arbitrary. Why not N=8 or N=12? I suspect it does not matter much, but the paper should either justify it (e.g., "we tested thresholds of 5, 10, and 15 and found <0.01 R2 difference") or acknowledge it as a design choice.

The slope shrinkage uses slope_k=10 (different from intercept k=15). This asymmetry is not explained. Why is the slope prior tighter than the intercept prior?

### 3.3 Bayesian vs OLS at N=2: Remarkable or Expected?

The N=2 result (R2 = 0.485 vs -0.012) is both remarkable and expected:

- **Expected** because OLS with 2 points is a perfect fit with zero residual degrees of freedom. Any out-of-sample prediction from a 2-point OLS regression is pure extrapolation. The -0.012 R2 actually implies OLS barely hurts, which is unusual -- in most cases, 2-point OLS produces R2 << 0.
- **Remarkable** because the Bayesian shrinkage essentially says "with 2 points, trust the global model 89% and the site correction 11%." The fact that this 11% correction provides any improvement at all (0.485 vs 0.401 zero-shot) means even 2 samples contain useful site-specific information, and the shrinkage prior correctly prevents overfitting to it.

This is a publishable finding. Frame it as: "The Bayesian prior prevents the catastrophic failure of OLS at small N while still extracting the small amount of site-specific signal available from 2 samples."

### 3.4 Does the Shrinkage Prior Need Sensitivity Analysis?

Yes, as noted in 3.1. The prior parameters (k, df, slope_k, bcf_k_mult) are hyperparameters of the adaptation method. The paper reports results at a single setting. For WRR, this is borderline -- the adaptation curve is the paper's main operational contribution, and it rests on four hyperparameters whose sensitivity is unexplored.

At minimum, report what happens if k is doubled or halved. If the adaptation curve barely changes, this is a strong result that demonstrates robustness. If it changes substantially, the paper must acknowledge that the adaptation hyperparameters were tuned and may not generalize.

---

## 4. Bias Correction (Dual BCF) Critique

### 4.1 Snowdon vs. Duan

Snowdon (1991) ratio-based BCF is the correct choice for Box-Cox transformations. Duan's smearing estimator assumes log-normal residuals and is only exact for log transforms. Since lambda=0.2 is neither log (lambda=0) nor identity (lambda=1), Snowdon's nonparametric ratio approach is more defensible. The paper correctly identifies this in the Decision Log. The Methods section (3.3) should cite this reasoning explicitly.

### 4.2 Dual BCF: Defensible or Gaming?

This is the most methodologically questionable decision in the UQ framework. Using two different BCFs for two different purposes (BCF_mean=1.297 for loads, BCF_median=0.975 for individual predictions) is:

**Defensible if framed as:** "Back-transformation from a compressed space introduces systematic positive bias. For load estimation, this bias is desirable (preserving mass balance). For individual prediction accuracy, this bias inflates errors. We report results under both correction factors and recommend BCF_mean for load applications and BCF_median for monitoring applications."

**Not defensible if framed as:** "We found two BCFs and we report the one that makes each use case look best." The paper's current framing in Section 3.3 is closer to the defensible version, but it needs to be crystal clear that all holdout metrics are computed under a single, pre-specified BCF (bcf_median for individual metrics, bcf_mean for load comparisons), and that this choice was made before looking at holdout results.

**Key concern:** The Decision Log records that bcf_median was adopted after seeing that bcf_mean overpredicts 75% of individual predictions (Wilcoxon p<10^-100). This means the choice of bcf_median was informed by holdout performance, which is a form of post-hoc optimization. If the order of operations was: (1) discover bcf_mean overpredicts, (2) introduce bcf_median, (3) report holdout metrics under bcf_median, then the holdout metrics are optimistic by an unknown amount.

**Recommendation:** Acknowledge in the paper that the dual BCF approach was motivated by the observed overprediction under BCF_mean. Report holdout metrics under BOTH BCFs in a table so the reader can assess the sensitivity. This transparency is more convincing than omitting the history.

### 4.3 BCF Clamping to [0.5, 5.0]

The assertion `assert 0.5 <= bcf <= 5.0` in evaluate_model.py is a sanity check, not a statistical guarantee. For the global BCFs (1.297 and 0.975), this is never binding. For per-trial BCFs in the adaptation, the code clips to [0.1, 10.0] before shrinkage. These are reasonable guard rails but they should be documented as implementation choices, not statistical properties.

---

## 5. Bootstrap CI Critique

### 5.1 Site-Level Blocking

Site-level blocking (resampling sites, not individual observations) is the correct approach. It accounts for within-site correlation and provides CIs that reflect the variability due to site sampling, which is the dominant source of uncertainty.

**However**, it does NOT account for spatial autocorrelation between nearby sites. The Results Log notes that sites within 50 km have 39% error difference vs. 55% at greater distance, confirming weak but non-negligible spatial correlation. Under spatial correlation, site-level bootstrap CIs are too narrow because resampled "sites" are not independent draws from the site population.

**Recommendation:** Section 6.4 of the paper already acknowledges this limitation. Strengthen it: "The bootstrap CIs assume spatial independence between sites. Moran's I analysis of site residuals was not conducted; if spatial clustering is present, the reported CIs may be anti-conservative."

### 5.2 1000 Resamples

1000 resamples is standard and sufficient for 95% CI estimation on the quantities reported (medians and proportions of 78 sites). The Monte Carlo error on the CI bounds is approximately proportional to 1/sqrt(1000), which is negligible relative to the sampling variability.

### 5.3 Are the CIs Honest?

The bootstrap CIs condition on: (1) the specific model (v11), (2) the specific training data (260 sites), (3) the specific holdout site pool (78 sites), and (4) the adaptation hyperparameters (k=15, df=4). They estimate the variability of metrics under resampling of holdout sites, which answers the question: "If we drew a different random sample of 78 sites from the holdout pool, what range of metrics would we see?"

This is a useful but narrow statement. It does NOT answer: "If we deployed this model at 78 randomly chosen sites from the 4,000 USGS turbidity sites, what performance would we see?" The holdout sites were selected with HUC-2 balance and SSC stratification, which is not representative of the broader deployment population.

**Recommendation:** Add a sentence: "Bootstrap CIs reflect variability within the holdout population and do not account for potential distribution shift between the holdout sites (selected with stratification) and the broader population of operational deployment sites."

---

## 6. CQR Failure Analysis

### 6.1 Is the Diagnosis Correct?

Yes. Box-Cox lambda=0.2 transforms SSC=10,000 mg/L to y'=(10000^0.2 - 1)/0.2 = (6.31-1)/0.2 = 26.55, and SSC=100 mg/L to (100^0.2 - 1)/0.2 = (2.51-1)/0.2 = 7.56. The ratio in transformed space is 3.5x, but in native space it is 100x. The Q95 quantile in Box-Cox space back-transforms to a value that cannot span this 100x native-space range. The multi-quantile model learns Q95 in the compressed space and has no mechanism to produce intervals wide enough in native space for extreme SSC.

This is a fundamental limitation of combining nonlinear target compression with quantile regression. It is worth a brief theoretical note in the paper.

### 6.2 Could a Different CQR Approach Work?

Several alternatives exist:

1. **CQR in native space (no Box-Cox):** Train the MultiQuantile model on raw SSC. This fails because CatBoost in native space achieves R2 < 0.012 (documented in Decision Log). The quantiles would be meaningless.

2. **CQR with log transform:** Log compression is milder than Box-Cox 0.2 for extremes. However, the paper already shows log1p produces higher BCF (1.71 vs 1.35), which suggests worse calibration. Not clearly better.

3. **Post-hoc CQR on residuals:** Train a standard model, then fit a quantile regression on the residuals (possibly with features). This is the approach of Chernozhukov et al. (2010) and avoids the back-transformation problem. This is the most promising unexplored avenue.

4. **Distributional regression:** Predict parameters of a distribution (e.g., log-normal) rather than quantiles. Natural Gradient Boosting (NGBoost) or CatBoost with custom distributional loss could work. This sidesteps the back-transformation issue entirely.

**Recommendation:** Mention option 3 (residual-based CQR) as future work. Do not claim that CQR is fundamentally impossible for this problem -- the failure is specific to the combination of Box-Cox compression + full quantile regression.

### 6.3 How Should This Be Reported?

The current treatment in Sections 3.8 and 6.2 is adequate in substance but could be more precise. The paper should:

- State clearly that the CQR approach was attempted first and the empirical conformal method is a fallback
- Note that the Box-Cox + CQR incompatibility may be a general issue for any heavily right-skewed target
- Avoid implying that conformal prediction was the planned approach (it was not)

The current draft does all of this acceptably. No major revision needed here.

---

## 7. Paper-Worthy Results and Quotes

**The following UQ results MUST appear in the paper with exact numbers. These are formatted as bullets for the Phase 2 writing team.**

### Conformal Coverage

- Overall 90% conformal interval coverage on holdout: **90.6%** (6,026 readings, 78 sites)
- Per-bin 90% coverage: **92% (0-30 mg/L, n=2223), 91% (30-100, n=1414), 89% (100-500, n=1808), 91% (500-2000, n=550), 52% (>2000, n=31)**
- Interval widths at 90%: **43 mg/L (low SSC), 184 mg/L (medium), 710 mg/L (moderate-high), 2,385 mg/L (high), 8,304 mg/L (extreme)**
- CRITICAL LIMITATION: "Prediction intervals at SSC > 2000 mg/L achieve only 52% coverage at 90% nominal (n=31 holdout samples), well below the target. This reflects both the model's systematic underprediction bias at extreme concentrations and the insufficient calibration data (n=252) in this regime."
- Overall 80% coverage: **77.4%** (slightly under-covering; suggests the intervals are slightly too narrow at the 80% level)

### Bootstrap CIs

- MedSiteR2 zero-shot: **0.402 [0.358, 0.440]** (95% CI, 1000 site-level bootstrap resamples)
- Spearman zero-shot: **0.874 [0.836, 0.899]** (note: the point estimate from pooled data is 0.907; the bootstrap median of per-site Spearman is 0.874)
- Pooled log-NSE: **0.804 [0.752, 0.843]**
- Pooled KGE: **0.186 [0.078, 0.406]** (extremely wide CI -- KGE is dominated by a few high-leverage sites)
- Fraction R2 > 0: **0.757 [0.681, 0.837]** (i.e., 16-32% of sites could have R2 < 0 in any given sample)

### Bayesian Adaptation vs OLS

- N=2 temporal: Bayesian R2 = **0.485** vs OLS R2 = **-0.012** (delta = +0.497)
- N=2 temporal (from canonical summary): delta = **+1.197** (Bayesian +0.488 vs OLS -0.709)
- N=10 random: Bayesian MedSiteR2 = **0.493** [0.440, 0.547] (bootstrap 95% CI)
- Bayesian wins at ALL N in ALL split modes (random, temporal, seasonal)
- Shrinkage weight at N=1: ~**10.7%** trust in data; at N=20: ~**70.5%** trust in data

### Extreme Coverage (Honest Limitation)

- Top-1% SSC underprediction bias: **-25%**
- Conformal coverage at >2000 mg/L: **52%** (90% nominal) / **35%** (80% nominal)
- Continuous interpolation even worse at >2000 mg/L: **19.4%** (90% nominal) -- do NOT use the continuous approach for extremes
- The model's primary failure mode: extreme events where particle size shifts (coarse sediment adds mass without changing scattering)

### BCF Values

- BCF_mean (Snowdon, for loads): **1.297**
- BCF_median (for individual predictions): **0.975**
- BCF_mean causes 75% of individual predictions to be overpredictions (Wilcoxon p < 10^-100)
- BCF_median removes this individual-prediction bias at the cost of slight load underestimation

---

## 8. What's Missing (UQ Perspective)

### 8.1 Per-Site Coverage Analysis (HIGH PRIORITY)

The conformal intervals are calibrated and evaluated in aggregate. There is no analysis of: "At site X, what fraction of predictions fall within the 90% interval?" Some sites may have systematically under-covered or over-covered intervals. A simple histogram of per-site 90% coverage rates (across the 78 holdout sites) would reveal whether the aggregate 90.6% is representative or hides bimodality.

### 8.2 Conditional Coverage by Geology (MEDIUM PRIORITY)

Geology is the dominant source of between-site heterogeneity (carbonate R2=0.81, volcanic R2=0.20). The conformal intervals should be evaluated separately for at least carbonate, sedimentary, and volcanic/metamorphic sites. If volcanic sites have 70% coverage at 90% nominal, this is a critical finding for practitioners in the Pacific Northwest.

### 8.3 Prediction Interval Sharpness (MEDIUM PRIORITY)

Coverage alone is insufficient -- trivially wide intervals always achieve high coverage. The paper reports interval widths, which is good, but does not compare them to any baseline. A useful comparison: what interval width would a naive "plus-or-minus 2x" rule produce, and how does the conformal interval compare? This contextualizes whether the intervals are informatively narrow or trivially wide.

### 8.4 Sensitivity Analysis for Bayesian Priors (HIGH PRIORITY)

As discussed in Section 3.1. A small grid search over k and df, reported in an appendix table, would close this gap.

### 8.5 Temporal Validation of Conformal Intervals (LOW PRIORITY)

The calibration set (LOGO CV) and holdout set span the same time period. If the model were deployed in 2027 at a site with no historical data, would the 2000-2026 intervals still achieve 90% coverage? This is unknowable without future data, but it should be flagged as a limitation.

### 8.6 Moran's I on Residuals (MEDIUM PRIORITY)

Section 6.4 acknowledges this is missing. It is a standard analysis in spatial statistics and WRR reviewers will expect it. The calculation is straightforward with the site coordinates and residuals already available.

---

## 9. What's Overstated / Understated

### Overstated

1. **"Prediction uncertainty is quantified through empirical conformal intervals achieving 90.6% coverage"** (Abstract). This statement is true but misleading because it implies uniform coverage. The 52% at >2000 mg/L means uncertainty is NOT quantified for the predictions that matter most. Suggested revision: "...achieving 90.6% overall coverage, though interval reliability degrades severely above 2000 mg/L (52% coverage)."

2. **"Residuals from the holdout set are binned by predicted SSC magnitude"** (Section 3.8). This is incorrect -- the calibration set for the intervals is the LOGO CV predictions (23,588 samples from 244 training sites), not the holdout set. The holdout set is used for evaluation. This error should be corrected.

3. The use of the term "conformal" throughout may overstate theoretical guarantees. The implementation computes empirical percentiles, not the conformal quantile adjustment (which adds 1/(n+1) to account for the new test point). This distinction matters for small-sample bins like the 2000+ bin (n=252).

### Understated

1. **The Bayesian adaptation is undersold.** The N=2 result (delta +0.497 over OLS) is one of the most compelling operational findings in the paper. It deserves a dedicated paragraph in the Discussion, not just a row in Table 5. Frame it as: "Bayesian shrinkage makes the model useful with a single field visit."

2. **The 80% interval undercoverage (77.4% vs 80% target) is not discussed.** While 90% intervals slightly over-cover (90.6%), the 80% intervals slightly under-cover. This pattern suggests the residual distribution has heavier tails than the empirical percentiles capture (the 5th/95th are more stable than the 10th/90th). This is diagnostic information that should be reported.

3. **The residual autocorrelation finding (lag-1 up to 0.69) is buried in the Physics Findings.** This has direct implications for effective sample sizes, bootstrap CIs, and conformal coverage guarantees. It deserves mention in the Limitations section.

4. **The spatial autocorrelation (39% vs 55% error difference at 50km)** and the bootstrap CI caveat are understated. The CIs may be anti-conservative by an unknown amount.

---

## 10. Specific Recommendations

### Must-Fix (Before Submission)

1. **Correct Section 3.8:** The conformal intervals are calibrated on LOGO CV predictions, not holdout residuals. This is a factual error that will confuse reviewers.

2. **Expand Section 4.8 on extreme coverage:** The 52% coverage at >2000 mg/L needs 3-5 sentences, not a parenthetical clause. State the implication: intervals above 2000 mg/L are unreliable and should be flagged as such in any operational deployment.

3. **Add the 80% coverage results** to the paper (even in a supplementary table). The 77.4% overall and the 35% at >2000 mg/L provide important calibration information.

4. **Qualify "conformal" language:** Either implement the finite-sample conformal adjustment or use "empirical Mondrian prediction intervals" instead of "conformal prediction intervals." The distinction matters for the conformal prediction community.

5. **Report BCF_mean holdout metrics alongside BCF_median** in a supplementary table. Transparency about the dual BCF choice.

### Should-Fix (Strengthens the Paper)

6. **Bayesian prior sensitivity analysis:** 3x3 grid of (k, df) values, reported in an appendix. One afternoon of computation.

7. **Per-site coverage histogram:** Distribution of per-site 90% coverage across 78 holdout sites. One line of code.

8. **Moran's I on holdout site residuals.** Standard spatial autocorrelation test. A few lines of code with PySAL.

9. **Dedicate a Discussion paragraph to the Bayesian N=2 result.** This is the paper's strongest operational selling point and it is currently buried in a table.

10. **Add a sentence on residual autocorrelation to Section 6:** "Within-site residual autocorrelation (lag-1 r up to 0.69) reduces effective sample sizes and may cause the reported per-site metrics to be less precise than the sample counts suggest."

### Nice-to-Have (Future Work)

11. **Coverage by geology class.** Are conformal intervals well-calibrated for volcanic sites? This could be a table in the supplement.

12. **Residual-based CQR as future work.** Mention that training a quantile model on the residuals (avoiding the back-transformation problem) is a promising avenue for improving conditional coverage.

13. **Proper conformal adjustment.** Replace empirical percentiles with the conformal quantile formula: use the ceil((1-alpha)(n+1))/n-th quantile rather than the (1-alpha)-th quantile. For large n this is nearly identical; for n=252 it provides a meaningful correction.

---

## Summary Table

| UQ Component | Grade | Key Issue |
|---|---|---|
| Empirical conformal intervals | B- | 52% extreme coverage is a critical honest limitation; "conformal" language slightly overstates theoretical guarantees |
| Bayesian site adaptation | A- | Well-motivated, demonstrably superior; needs prior sensitivity analysis |
| Dual BCF | C+ | Defensible in principle but post-hoc; needs transparency about decision order |
| Bootstrap CIs | B | Correct method; spatial autocorrelation caveat needed |
| CQR failure reporting | A | Honest, well-diagnosed, correctly reported |
| Overall UQ story | B | Broad and honest; marginal-only coverage is the main gap |

---

*Assessment prepared by Dr. Elena Vasquez. All recommendations are intended to strengthen the paper for WRR peer review. The overall UQ framework is sound; the issues identified are fixable within a revision cycle.*
