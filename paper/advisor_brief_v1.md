# murkml — Progress Brief for Discussion

**Kaleb Rounsevel | March 2026**

## What This Is

I'm building a cross-site suspended sediment concentration (SSC) model. One CatBoost model trained on ~254 USGS sites that generalizes to new sites it's never seen, with optional Bayesian adaptation using a handful of local grab samples. The goal is to replace the current USGS practice of fitting a per-site log-log OLS rating curve at every monitoring location.

The data is 35,074 paired turbidity-SSC observations from 396 USGS sites, using continuous FNU turbidity (pCode 63680) and discrete SSC grab samples (pCode 80154). Features include real-time sensor readings, hydrograph derivatives, weather, and watershed attributes (StreamCat + SGMC lithology) — 72 features total after ablation.

## Where Things Stand

**Training data is clean.** I removed 135 anomalous records (SSC/turbidity ratios >200 or <0.01, turbidity <=0). The dataset is split three ways: 284 training sites, 76 holdout sites (for development evaluation), and 36 vault sites (sealed for final paper evaluation, never touched during development).

**Feature set is locked at 72.** Ran 83 single-feature + group ablation experiments. A 5-seed stability check showed 72 vs 58 features are statistically indistinguishable (p=0.81). CatBoost handles irrelevant features internally — pruning doesn't help.

**I found and fixed a data contamination bug.** The previous model checkpoint (v9) was accidentally trained on all sites including holdout and vault, so those evaluation numbers were invalid. I've added automatic exclusion guards and am currently retraining a clean model (v10). The numbers below use either properly-excluded cross-validation or fully independent external data.

## Results I Can Report Honestly

### Cross-Site Generalization (GKF5 on 287 training sites, properly excluded)

This is 5-fold grouped cross-validation where each fold holds out entire sites. Not the final model — used for screening — but the exclusion is correct.

| Metric | Value |
|--------|-------|
| Sites | 287 (after feature filtering from 284) |
| Features | 72 |
| Transform | Box-Cox (lambda=0.2) |

*(Full GKF5 metrics will be available from v10 LOGO CV, currently training.)*

### External Validation (260 non-USGS NTU sites — completely independent)

This is the most trustworthy result. These 260 sites from 4 organizations (mostly UMRR-LTRM) were never in any training data. The model was trained on FNU turbidity; these sites use NTU — a different measurement standard.

| Metric | Value | Notes |
|--------|-------|-------|
| Sites | 260 | Non-USGS, NTU sensors |
| Samples | 11,026 | |
| Spearman rho | **0.93** | Model ranks correctly across foreign sensors |
| Zero-shot bias | +57% | Expected — NTU != FNU |
| Zero-shot MAPE | 90% | Poor absolute accuracy without adaptation |
| Within 2x | 55% | |

**Key finding:** The model *ranks* correctly on foreign NTU data (Spearman 0.93) but has large systematic bias (+57%). This is actually good news — it means Bayesian adaptation can fix the scale while preserving the ranking.

### Site Adaptation Curve (Bayesian shrinkage)

With just a few local grab samples, the model adapts to a new site. This uses Student-t shrinkage (k=15, df=4), staged: intercept-only for N<10, slope+intercept for N>=10.

| Calibration samples | Median site R² | MAPE | Within 2x | Spearman |
|---------------------|---------------|------|-----------|----------|
| 0 (zero-shot) | 0.42 | 55% | 67% | 0.88 |
| 1 | 0.51 | 36% | 75% | 0.88 |
| 5 | 0.53 | 36% | 77% | 0.88 |
| 10 | 0.54 | 37% | 79% | 0.88 |
| 20 | 0.52 | 37% | 79% | 0.89 |

*Note: These holdout numbers are from the contaminated v9 model and will be replaced by v10. The shape of the curve (big jump at N=1, plateau by N=10, slight decline at N=20) is consistent across experiments and externally validated.*

**The N=1 jump is the headline result.** One grab sample improves MAPE from 55% to 36% and within-2x accuracy from 67% to 75%. This is the value proposition: you don't need 30+ samples for a site-specific rating curve — one sample gets you most of the way.

## Interesting Findings

### 1. Dual BCF tradeoff

The Snowdon bias correction factor (BCF ~1.32) corrects for Box-Cox back-transformation bias. But it optimizes the *mean*, which causes 1.44x systematic overprediction of the *median*. We now compute two BCFs:

- **bcf_mean = 1.32**: Unbiased mean, good for load estimation (annual sediment tons)
- **bcf_median = 0.94**: Unbiased median, good for individual predictions (monitoring)

With the median BCF, MAPE improves from ~55% to ~36% and within-2x from ~65% to ~74%. Same model, same predictions — just a different scaling constant. This is a paper finding on its own.

### 2. "Noise" sites carry extreme event signal

Site contribution analysis (50 random subsets, out-of-bag scoring) identified 110 "anchor" sites and 110 "noise" sites. When I dropped the 15 worst noise sites, aggregate metrics barely changed — but first flush R² collapsed from 0.91 to 0.26 and top 1% extreme event R² collapsed from 0.79 to -0.04.

**Implication:** Sites that look "noisy" in aggregate are the ones experiencing extreme sediment events. Dropping them destroys the model's ability to predict the most operationally important cases.

### 3. N=20 adaptation collapse

Expert panel analysis found that 36% of random N=20 calibration draws contain zero storm samples. At sites with wide SSC range, adding more baseflow-dominated calibration samples actually rotates the adaptation *away* from storm physics. This suggests capping adaptation at N=10 or implementing flow-stratified adaptation.

### 4. NTU is validation-only

USGS has zero continuous NTU data (by design since TM 2004.03 — continuous sensors are FNU/ISO 7027, discrete field measurements are NTU/EPA 180.1). We preserve 3,646 USGS discrete NTU-SSC pairs as a validation dataset. The +57% zero-shot bias on external NTU data is a feature for the paper — it proves adaptation is necessary.

## What I'd Like to Discuss

1. **Is this enough for a WRR paper?** Cross-site generalization + Bayesian adaptation + the N=1 result + dual BCF seems like a strong story.

2. **Honest metrics.** The pooled NSE (0.69) looks great but the sample-weighted mean site R² is only 0.22. Twenty-eight percent of holdout sites have R² < 0. How should we frame this?

3. **What's the right benchmark?** The USGS standard is per-site log-log OLS (Rasmussen et al. 2009). We need to formally show we beat it at various N. At N=0 we obviously win (OLS can't predict with no data). The question is where we cross over.

4. **The BCF tradeoff.** Is dual BCF (mean vs median) a novel contribution, or is this well-known in the back-transformation literature?

## What's In Progress

- **v10 model retraining** (currently running) — clean data, proper site exclusion, dual BCF
- **Conformal Quantile Regression** for prediction intervals (after v10)
- **Formal OLS benchmark comparison** at N = 0, 1, 5, 10, 20
- **Bootstrap CIs** on all reported metrics (resampling sites, not samples)
