# Statistical Assessment of murkml v11 for WRR Submission

**Reviewer:** Dr. Marcus Liu, ML Statistician (spatial cross-validation, transfer learning, environmental model evaluation)
**Date:** 2026-04-02
**Model reviewed:** CatBoost v11 (260 sites, 23,624 samples, 72 features, Box-Cox 0.2)

---

## 1. Overall Statistical Assessment

**Verdict: Conditionally publishable.** The statistical methodology is above average for a hydrology paper and below average for a machine learning paper. The project has several genuine strengths --- honest reporting of failure rates, proper LOGO CV, the dual-BCF framework, and the site-level bootstrap --- but also some structural weaknesses that must be addressed before WRR submission.

The core scientific finding is sound: continuous turbidity enables meaningful cross-site SSC transfer (Spearman = 0.907), site heterogeneity is the dominant error source (between/within CV ratio = 3.2x), and Bayesian adaptation with minimal samples closes most of the gap. This is a real contribution.

However, the statistical presentation suffers from three systemic issues:

1. **Multiple testing and implicit holdout overfitting.** The holdout set was evaluated dozens of times across v4-v11 development (acknowledged via the vault creation, but the vault has not been opened). The reported holdout metrics are not truly prospective. The paper must frame them as development-set metrics, not as a primary test.

2. **Effective sample size ambiguity.** The paper conflates N=260 (sites) with N=23,624 (observations) in different contexts. The independent unit is the site. All inferential claims must be based on N=78 holdout sites, not 6,026 holdout observations.

3. **Incomplete spatial dependence accounting.** The bootstrap uses site-level blocking (correct), but nearby sites share geology, climate, and sensor deployment patterns. Without Moran's I or a variogram on site-level residuals, the CI widths are optimistic. The paper acknowledges this (Section 6.4) but still reports CIs without qualification in the abstract.

---

## 2. Cross-Validation Strategy Critique

### LOGO CV: Appropriate but not sufficient

LOGO CV is the correct choice for this problem --- it ensures complete spatial separation between train and test. The GKF5 approximation for ablation is reasonable (450x speedup, comparable rankings). However:

**The GKF5-vs-holdout disagreement is a red flag.** Features that are neutral under GKF5 are critical on holdout (e.g., `turb_Q_ratio`: GKF5 neutral, holdout delta = -0.10). This means GKF5 is not a reliable proxy for holdout generalization. The feature decisions were made on GKF5, but the final evaluation is on holdout. This is not wrong, but the paper should acknowledge that the feature set was optimized under GKF5 and that holdout results are partially out-of-distribution with respect to the selection procedure.

**Possible explanation:** GKF5 with only 5 groups has much less site diversity per fold than full LOGO. Features that help with rare site types (the 10% of sites where turb_Q_ratio matters) get averaged away in 5-fold but become visible when you test on 78 diverse holdout sites. This is actually an argument for LOGO over GKF5 for final feature decisions.

### The 260/78/36 split

**Defensible but not ideal.** The 77% train / 19% holdout / 9% vault proportions are reasonable. The stratification by HUC-2 and median SSC is good. But:

- 78 holdout sites give a bootstrap standard error on MedSiteR2 of approximately sqrt(Var(R2_i)/78) ~ 0.02-0.04, which matches the reported CI width [0.358, 0.440]. This is adequate for the primary claim.
- 36 vault sites is small. The vault CI will be very wide. If the vault result is substantially different from holdout, the paper has a credibility problem. If it is similar, it adds modest confirmation. The vault must be opened before submission; holding it forever defeats its purpose.

### Approved-only training bias

This is a serious confound that the paper correctly identifies but underweights. "Approved" data is biased toward:
- Older time periods (approval lag is months to years)
- Lower-flow conditions (extreme events stay provisional longer because they require more hydrographer review)
- Better-maintained sensors (sites with QC problems stay provisional indefinitely)

This means the training data systematically underrepresents the extreme events the model most needs to learn. The -25% top-1% underprediction is almost certainly partly caused by this. The paper should quantify: what fraction of SSC > 5,000 mg/L samples are Approved vs. Provisional in the NWIS universe?

---

## 3. Metrics and Evaluation Critique

### Metric suite: Strong

The project's metric suite is genuinely good --- MedSiteR2, Spearman, MAPE, within-2x, KGE, disaggregated by geology/method/SSC range, per-site R2 distribution, baselines (global mean, site mean, OLS). This is more thorough than 95% of published ML hydrology papers. The decision to lead with MedSiteR2 and Spearman rather than pooled NSE is correct and should be highlighted as a methodological contribution.

### Bootstrap CIs: Mostly valid, with caveats

The bootstrap procedure (1,000 resamples, site-level blocking) is appropriate for the primary inference. However:

**Bug in bootstrap code (line 115-122 of bootstrap_v11_ci.py):** When the same site is drawn multiple times in a bootstrap sample, the code uses `np.unique(sampled_sites)` to compute per-site metrics. This means a site drawn 3 times counts the same as a site drawn once for MedSiteR2. This is actually correct for the median (it does not matter how many times a site appears --- its R2 is the same), but it means the bootstrap is not resampling the site-level metric distribution in the standard way. The effective bootstrap sample size is smaller than 78 because many draws are deduplicated. This makes CIs slightly conservative, which is the right direction to err.

**Spatial dependence issue:** If sites A and B are 10km apart in the same watershed and share similar geology, their residuals are correlated. Drawing both in a bootstrap sample double-counts the same information. The 39% vs. 55% spatial autocorrelation finding (sites within 50km vs. farther) suggests weak but real spatial dependence. This does not invalidate the bootstrap, but it means the true CIs are wider than reported. The standard approach would be a block bootstrap with spatial blocks, but the spatial structure may be too irregular for clean blocking. At minimum, the paper should report the Moran's I of site-level residuals and note that CIs are conditional on spatial independence.

**The Spearman CI is suspicious.** The point estimate is 0.907 (pooled across all holdout readings), but the bootstrap CI for MedSiteSpearman is [0.836, 0.899]. The pooled Spearman is ABOVE the upper CI for the median per-site Spearman. This is not a contradiction (pooled != median of per-site), but the paper reports both without clearly distinguishing them. The abstract says "Spearman rho = 0.907" --- this is the pooled number, not the per-site median (0.875). The paper must clarify which is which and use them consistently.

### Sensitivity sweep interpretation

The claim that "KGE range of 0.027" proves stability is weak. This is a one-at-a-time (OAT) sensitivity analysis, which misses interactions. Depth and learning rate could interact nonlinearly. A 0.027 range on KGE corresponds to roughly 3-4% of KGE scale, which is indeed small, but the claim would be stronger with:
- A 2D grid over depth x learning rate (the two most sensitive parameters)
- A statement about what KGE difference is "practically significant" for this problem
- Comparison to the holdout metric variance: if the bootstrap CI width on KGE is 0.33 (pooled KGE CI [0.078, 0.406]), then a 0.027 sensitivity range is well within noise

As stated, the sensitivity sweep supports "the model is not catastrophically sensitive to hyperparameters" but not "the hyperparameters are optimal."

### Effective sample size

**This must be explicitly discussed.** The paper says "23,624 samples" and "260 sites" in the same breath. The effective sample size for cross-site generalization claims is N=260 (training sites) or N=78 (holdout sites). The 23,624 is the total observation count, which is relevant for within-site learning but not for the cross-site transfer claim.

Furthermore, the 6.8% burst pseudo-replicates (samples within 5 minutes of each other at the same site) and lag-1 autocorrelation up to 0.69 mean the effective observation count is substantially less than 23,624 even for within-site learning. The paper should report:
- Number of independent sampling events (after deduplication of bursts)
- Effective N per site accounting for temporal autocorrelation (e.g., using the Bayley-Hammersley estimator)
- Number of storm events per site (operationally, storm events are the independent information units for SSC)

---

## 4. Adaptation Framework Critique

### Bayesian Student-t shrinkage (k=15, df=4)

**This is the most principled part of the methodology**, and also the most ad hoc.

**What is principled:**
- Student-t prior correctly accounts for heavy-tailed residuals (skew=2.0, kurtosis=13.8). A Gaussian prior would over-shrink legitimate outlier sites.
- Staged adaptation (intercept-only for N<10, slope+intercept for N>=10) correctly avoids estimating two parameters from too few data points.
- MAD-based robust scale estimation is correct for heavy tails.
- Per-trial BCF shrinkage toward 1.0 is conservative and sensible.

**What is ad hoc:**
- k=15 and df=4 appear to be hand-tuned, not derived from the data or from prior information. How were these values selected? Was there a sensitivity analysis on k and df? The decision log says "k=15, df=4" but not why those numbers.
- The adaptation was evaluated on the same holdout set used for all other development. The adaptation hyperparameters (k, df, staging threshold at N=10) were tuned on this holdout. This is a second layer of implicit overfitting on top of the feature selection.
- The comparison to "old 2-param" is not a fair benchmark. The old method had no shrinkage at all. A fairer comparison would be a Gaussian shrinkage prior (same framework, df=infinity) to isolate the contribution of the Student-t tails from the contribution of shrinkage itself.

### Temporal N=10 collapse

The finding that temporal adaptation at N=10 (MedSiteR2 = 0.389) is WORSE than zero-shot (0.401) is important and correctly diagnosed: early chronological samples are disproportionately baseflow. However:

- The diagnosis is qualitative ("disproportionately collected during baseflow conditions"). The paper should quantify: what fraction of the first 10 temporal samples are above the site's median SSC? What fraction are from storm events?
- The collapse does not happen at N=1 (0.414) or N=2 (0.403). It appears between N=5 (0.407) and N=10 (0.389). This is puzzling --- more data should not make things worse unless the adaptation is overfitting to a non-representative subset. The staged adaptation switches from intercept-only to slope+intercept at N=10. This is the likely culprit: with 10 baseflow-dominated samples, the slope estimate rotates the relationship away from storms.
- **Recommendation:** Test whether the collapse disappears if you keep intercept-only adaptation through N=10 for temporal splits. This would confirm the staging threshold as the cause.

### 50 Monte Carlo trials per (site, N)

This is sufficient for the median but may be insufficient for tail statistics. With 50 trials and 78 sites, the adaptation curve point estimates are stable, but the per-site adaptation variance is estimated from only 50 draws. For the CIs on the adaptation curve, this adds Monte Carlo noise on top of bootstrap noise. The paper should either:
- Report the Monte Carlo standard error of the median (should be small, ~0.01)
- Or increase to 200 trials for the final evaluation (as was done for the v10 Bayesian summary)

I note the decision log mentions "200 MC trials" for the canonical Bayesian summary but the v11 evaluation JSON shows "n_trials: 50." This discrepancy should be resolved.

### Dual-BCF approach

**Statistically justified and well-motivated.** The bcf_mean/bcf_median split correctly separates two distinct use cases (load estimation vs. individual predictions). The Wilcoxon test confirming that bcf_mean overpredicts 75% of individual observations (p < 10^-100) is decisive. This is a genuine methodological contribution --- most papers apply a single BCF and ignore the trade-off.

However, the paper should note that the bcf_median (0.975) being so close to 1.0 means the Box-Cox back-transformation is nearly unbiased for the median prediction. This is not guaranteed and may be specific to lambda=0.2. The paper should discuss whether BCF_median varies with lambda.

---

## 5. Paper-Worthy Results and Quotes

**These specific results MUST appear in the paper with exact numbers:**

### Primary performance (Section 4.3, Table 4)
- Zero-shot MedSiteR2 = 0.402 [95% CI: 0.358, 0.440] across 78 holdout sites
- Pooled Spearman rho = 0.907 (median per-site Spearman = 0.875 [0.836, 0.899])
- 75.7% of holdout sites have R2 > 0 [CI: 68.1%, 83.7%]; 36.5% have R2 > 0.5 [CI: 27.3%, 44.5%]
- MAPE = 40.1%, fraction within 2x = 70.0%
- Pooled NSE = 0.306 --- deliberately downplayed because two high-SSC sites contribute disproportionate SS_res

### The site heterogeneity finding (Section 5.2)
- Between-site turbidity-SSC CV = 4.37 vs. within-site CV = 1.35 (ratio = 3.24)
- 30% of holdout sites have R2 < 0. This is not a failure --- it is a quantitative characterization of the transferability boundary
- Carbonate R2 = 0.807 vs. Volcanic R2 = 0.195 --- geology is the primary explanatory variable for cross-site performance

### Adaptation curve (Section 4.4, Table 5)
- Random N=2: MedSiteR2 = 0.413 (vs. zero-shot 0.401)
- Random N=10: MedSiteR2 = 0.493 [CI: 0.440, 0.547] --- the operational sweet spot
- Random N=20: MedSiteR2 = 0.498 (diminishing returns after N=10)
- Temporal N=10: MedSiteR2 = 0.389 --- WORSE than zero-shot. First 10 chronological samples are baseflow-biased.
- Seasonal N=10: MedSiteR2 = 0.431 --- intermediate, suggesting seasonal stratification partially mitigates temporal bias.

### CatBoost vs. OLS benchmark (Section 4.5)
- Temporal N=2: CatBoost R2 = 0.36, OLS R2 = -0.56 (delta = +0.93). The model's primary operational value.
- CatBoost beats OLS at every N, every split mode. The advantage is largest at low N.
- OLS with N=2 temporal is catastrophic (R2 = -0.56); CatBoost with N=2 temporal is usable (0.36). This is the Bayesian shrinkage payoff.

### Sediment load validation (Section 4.7, Tables 6-8) --- THE money result
- Brandywine Creek: 42,059 vs. 41,007 tons over 8 water years (ratio = 1.03, error = +2.6%). OLS ratio = 1.67.
- Storm-event median error: CatBoost 119-169% vs. OLS 165-591% at Brandywine/Valley Creek
- Ferron Creek: CatBoost underpredicts (-39% median storm error) while OLS overpredicts (+124%). Different failure modes at arid sites.

### Physics findings worth highlighting
- Hysteresis distribution: 39.5% clockwise, 24.4% counterclockwise, 36.1% linear (119 events). Rising limb SSC/turb ratio 16% higher than falling. This is empirical evidence for the turbidity advantage.
- Collection method bias: depth-integrated SSC ~4x higher than auto-point at same turbidity. SHAP rank 3.
- Power law slope range: 0.29-1.55 (median 0.952). 50% steepen at high turbidity, 32% flatten. Geology predicts slope direction.
- Low-SSC overprediction: 2.45x below 10 mg/L --- attributed to DOM/algae contamination of turbidity signal, not model failure

### Negative results (Section 6) --- equally valuable
- CQR failure: Box-Cox compression prevents Q95 from reaching extreme SSC. This is a structural incompatibility worth publishing because others will try the same thing.
- 52% coverage at SSC > 2,000 mg/L. The conformal intervals fail where they matter most.
- Temporal adaptation collapse at N=10. Operational recommendation: target storm events, not baseflow.
- Extreme underprediction: -25% at top 1% SSC. Honest.

### Methodological contributions
- Dual BCF: bcf_mean = 1.297 for loads, bcf_median = 0.975 for individual predictions. Different use cases require different back-transformations.
- Monotone x transform interaction: monotone constraints help Box-Cox (+0.060 R2_native) but hurt log1p (-0.019). This has implications for other environmental ML papers.
- Feature space conflict: log-space and native-space feature importance are sometimes opposite (e.g., rising_limb: +0.002 log, -0.075 native). Optimizing on log-space metrics alone produces a worse real-world model.

---

## 6. What's Missing (Statistically)

### Must-have before submission

1. **Moran's I on site-level residuals.** The spatial autocorrelation finding (39% vs. 55% error difference) is suggestive but informal. Compute Moran's I with a distance-based weight matrix (e.g., inverse-distance with 100km cutoff). Report the statistic and p-value. If significant, discuss the implications for CI widths.

2. **Per-site R2 distribution histogram.** The paper reports MedSiteR2 and the 30% < 0 fraction, but never shows the full distribution. A histogram of per-site R2 values is essential for WRR reviewers to assess model behavior across the full site population.

3. **Effective sample size calculation.** At minimum: (a) number of unique sampling events per site after burst deduplication, (b) median samples per site (and range), (c) acknowledgment that the 23,624 is not the inferential N.

4. **Vault evaluation.** The vault exists (36 sites). It must be opened exactly once, results reported, and discrepancies with holdout discussed. A vault result within the holdout CI is strong evidence. A vault result outside the CI requires explanation.

5. **Adaptation hyperparameter sensitivity.** How sensitive is the N=10 random MedSiteR2 to k and df? Even a small table (k = 5, 10, 15, 20, 30; df = 3, 4, 6, 10, infinity) would address the ad hoc concern.

### Should-have for a strong paper

6. **Variogram of site-level residuals.** Goes beyond Moran's I to characterize the spatial scale of dependence. If the range is 50-100km, it explains the 50km finding.

7. **Learning curve by training set size.** How does holdout MedSiteR2 change as you train on 50, 100, 150, 200, 260 sites? The site count sweet spot discussion (Section 8 of Decision Log) suggests saturation around 200 sites. This has direct implications for how many more sites would help.

8. **Calibration plot (reliability diagram).** For the conformal intervals: plot empirical coverage vs. nominal coverage across the probability range (not just at 90%). This is standard for uncertainty quantification papers.

9. **Temporal train-test analysis.** Are sites whose data spans more recent years (2015-2026) predicted better or worse than sites with older data (2000-2010)? This gets at the stationarity question.

10. **Formal comparison with Song et al. (2024).** The paper claims superiority based on Spearman, but the comparison is informal. At the subset of sites where both models could be evaluated, report head-to-head metrics.

---

## 7. What's Overstated

1. **"Spearman rho = 0.907" in the abstract.** This is the pooled number computed across all 6,026 holdout readings. It is dominated by sites with many observations and extreme SSC ranges. The per-site median Spearman is 0.875 [0.836, 0.899]. The abstract should use the per-site number or clearly label which it is. Using the pooled number without qualification inflates the perceived performance.

2. **"KGE range = 0.027 proves stability."** Excluding the depth=10 outlier from a sensitivity sweep and then claiming stability on the remaining points is cherry-picking. The full range is 0.046. Moreover, OAT sweeps cannot detect interactions. Say "the model shows moderate robustness to individual hyperparameter changes" --- not that it "proves stability."

3. **"The model matches the USGS published record within 2.6%."** This is true for Brandywine Creek's total load. It is not true for the other two validation sites (55% over at Valley Creek, 25% under at Ferron Creek). The abstract should say "at a benchmark site" (which it does) but the conclusion section should emphasize that the 2.6% result is the best case, not the typical case.

4. **Holdout metrics as primary test results.** The holdout was evaluated across v4, v5, v6, v8, v9, v10, and v11 development cycles, plus dozens of ablation experiments. It is a development set, not a test set. The paper correctly created a vault for this reason but has not opened it. Until the vault is evaluated, the holdout results should be framed as "held-out development set" performance, not as an unbiased generalization estimate.

5. **"Bayesian adaptation raises median R2 to 0.49."** The 95% CI on this number is [0.440, 0.547]. The improvement from 0.401 to 0.493 (delta = 0.092) has a CI that overlaps zero at the lower end (the zero-shot CI upper bound of 0.440 overlaps the N=10 CI lower bound of 0.440). The adaptation helps, but the paper should acknowledge the uncertainty in the magnitude of the improvement.

---

## 8. What's Understated

1. **The 30% failure rate is a major scientific finding.** The paper treats R2 < 0 at 30% of sites as a limitation. It is actually the most publishable result in the paper. No other cross-site environmental ML paper honestly reports per-site failure rates. Most report pooled metrics that hide these failures entirely. The paper should frame this as: "We provide the first site-level characterization of cross-site SSC transfer failure, showing that 30% of sites cannot be predicted better than the site mean." This should be in the abstract.

2. **The temporal adaptation collapse.** The finding that realistic (temporal) adaptation at N=10 performs worse than zero-shot is operationally devastating and scientifically important. It means that naive grab sampling --- the most common real-world calibration strategy --- can make predictions WORSE. This deserves a dedicated subsection, not just two sentences in Section 4.4. It should include:
   - Quantification of baseflow bias in early samples
   - Diagnosis of the N=10 staging threshold as the likely mechanism
   - Explicit recommendation: "Practitioners must include at least one storm event in calibration samples."

3. **The log-vs-native feature space conflict.** The finding that features have opposite effects in log and native space (e.g., rising_limb: +0.002 log, -0.075 native) is a methodological insight that applies to every environmental ML paper using log-transformed targets. It deserves a paragraph in Discussion.

4. **The collection method confound.** The 4x SSC difference between depth-integrated and auto-point samples at the same turbidity is enormous. This is not just a model finding --- it is a measurement science finding that has implications for turbidity-SSC relationships across the field. It should be highlighted as a standalone result.

5. **The residual non-normality.** Skew=2.0, kurtosis=13.8, 2% beyond 3-sigma (7x the Gaussian rate). This is the empirical justification for the Student-t prior and against CQR. It should be reported as a data finding, not buried in the adaptation methods.

6. **The bug history.** The project has an extraordinary bug history --- at least 16 bugs that materially affected results, including v9 being entirely contaminated by data leakage. This is normal for a real ML project but almost never reported. A supplementary table of "bugs and their impact on reported metrics" would be a contribution to reproducibility literature. At minimum, the methods section should note that v9 was discovered to have trained on holdout data and was discarded.

---

## 9. Specific Recommendations for Paper

### Abstract and Key Points
- Replace "Spearman rho = 0.907" with "pooled Spearman rho = 0.907 (median per-site = 0.88)" or use only the per-site number.
- Add the 30% failure rate to the abstract: "30% of holdout sites have R2 < 0, clustering in volcanic and glacial-flour geologies."
- The Brandywine result is the strongest selling point; keep it prominent.

### Methods section
- Explicitly state: "The independent statistical unit is the site (N=260 training, N=78 holdout), not the observation."
- Add a table summarizing the per-site sample count distribution (min, Q1, median, Q3, max).
- Report the 6.8% burst pseudo-replicate rate and how it was handled.
- For Bayesian adaptation: state how k=15 and df=4 were chosen. If they were hand-tuned, say so honestly. If there was any sensitivity analysis, cite it.

### Results section
- Lead every table with MedSiteR2 and MedSiteSpearman. Put pooled NSE in supplementary material only.
- Add the per-site R2 histogram as a main-text figure.
- For the adaptation curve: plot all three split modes on one figure with CIs. The temporal collapse at N=10 should be visually obvious.
- For the load comparison: include daily time series at Brandywine showing storm events --- this is where the model shines and where the figures write themselves.

### Discussion section
- Dedicate a subsection to the temporal adaptation collapse and its operational implications.
- Discuss the Approved-only training bias explicitly: "Our training data systematically underrepresents extreme events that remain in Provisional status."
- Frame the 30% failure rate as a transferability boundary, not a model limitation. Compare to Song et al. (2024) and Kratzert et al. (2019): what are their per-site failure rates? (Probably unreported.)
- Add the log-vs-native feature space conflict as a methodological contribution.

### Supplementary material
- Full per-site metric table (R2, MAPE, Spearman, N_samples, geology, collection method)
- Hyperparameter sensitivity sweep (full table, already exists)
- Adaptation hyperparameter sensitivity (k, df sweep)
- Bug disclosure table

### Statistical notation
- Use "MedSiteR2" consistently (not "R2" or "median R2" interchangeably).
- Always report CIs on primary claims.
- Distinguish pooled and per-site metrics every time they appear.
- Report all summary statistics with their denominators: "MedSiteR2 = 0.402 across N=78 holdout sites."

### What to NOT include
- Do not report pooled NSE (0.306) as a primary metric. It is misleading because two sites dominate SS_res.
- Do not claim the hyperparameter sweep "proves" anything. It supports robustness, not optimality.
- Do not present the holdout as a true test set unless the vault has been opened and corroborates it.

---

## Summary of Critical Action Items (Priority Order)

| # | Action | Priority | Effort |
|---|--------|----------|--------|
| 1 | Open the vault (36 sites). Report once. | BLOCKING | Low |
| 2 | Compute Moran's I on site-level holdout residuals | BLOCKING | Low |
| 3 | Generate per-site R2 histogram figure | HIGH | Low |
| 4 | Clarify pooled vs. per-site Spearman in abstract and all tables | HIGH | Low |
| 5 | Add effective sample size discussion to Methods | HIGH | Low |
| 6 | Adaptation hyperparameter sensitivity (k, df sweep) | HIGH | Medium |
| 7 | Quantify baseflow fraction in first-10-temporal samples | HIGH | Medium |
| 8 | Resolve 50 vs. 200 MC trial discrepancy for v11 | MEDIUM | Low |
| 9 | Reframe 30% failure rate as scientific finding, not limitation | MEDIUM | Low |
| 10 | Add temporal adaptation collapse subsection to Discussion | MEDIUM | Low |

---

*Assessment complete. The project is substantially above the quality bar I typically see for a first-author student paper in WRR. The honest reporting of negative results, the multi-metric evaluation framework, and the sediment load validation are genuine strengths. The statistical weaknesses are addressable without retraining the model. The primary risk for peer review is a reviewer who notices the holdout was used across 7+ model versions and questions whether the reported performance is optimistic. Opening the vault eliminates this risk.*
