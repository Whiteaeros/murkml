# Critical Findings Report — Phase 2 Expert Team

**Date:** 2026-04-02
**Team:** Whitfield, Liu, Osei, Vasquez, Kowalski, Tanaka

Findings ranked by severity. Each includes what is wrong, the impact on the paper, and the action required.

---

## SEVERITY 1: BLOCKING (must fix before submission)

### 1.1 Abstract Overclaim: N=2 Adaptation (Osei, Liu, Vasquez)

**What:** The abstract states "Adding as few as two grab samples for Bayesian site adaptation raises median R2 to 0.49." The data shows N=2 random MedSiteR2 = 0.413, not 0.49. N=10 random reaches 0.493.

**Impact:** A reviewer who checks Table 5 against the abstract will immediately lose trust.

**Action:** Change to "as few as 10 grab samples" or accurately report N=2 improvement (+0.01). Effort: 5 minutes.

### 1.2 Pooled Spearman (0.907) as Headline Metric (all 6 reviewers)

**What:** The abstract, Key Points, and conclusions all report pooled Spearman rho = 0.907. The per-site median Spearman is 0.875 [95% CI: 0.836, 0.899]. The pooled point estimate (0.907) falls ABOVE the bootstrap CI upper bound for the per-site metric (0.899). Pooled Spearman is inflated by between-site SSC gradient.

**Impact:** A statistically aware reviewer will immediately flag this discrepancy. The paper looks like it is hiding the per-site number.

**Action:** Use per-site median Spearman (0.875) as the primary ranking metric throughout. Report pooled (0.907) as secondary with explanation of why it differs. Effort: 30 minutes.

### 1.3 Brandywine 2.6% Without Daily Context (Whitfield, Osei, Tanaka)

**What:** The headline claims 2.6% total load match, but daily metrics show R2 = 0.49, pbias = +59.4% (on the 1,366 days with matched data), and median daily error of 12,743%. The 2.6% total match arises from error cancellation over the full integration period. The total loads (42,059 vs 41,007 tons) cover different day windows (v11 has continuous turbidity for 2,549 days; the 80155 record has data on specific days).

**Impact:** Potentially fatal if a reviewer finds the JSON shows total_load_ratio = 1.594 for matched days but the paper says 1.03 for total loads. The discrepancy is real (different time windows) but unexplained.

**Action:** (a) Report the total load (42,059 vs 41,007 tons, ratio 1.03) alongside the daily pbias (+59.4% on matched days). (b) Explain that the total includes all days with turbidity data (2,549), while the daily comparison uses the 1,366-day overlap. (c) Note explicitly that error cancellation contributes to the favorable total. Effort: 1 hour.

### 1.4 Moran's I Not Conducted (all 6 reviewers)

**What:** Spatial autocorrelation of holdout site residuals has not been tested. The paper acknowledges this in Section 6.4 but a WRR reviewer will demand it or reject.

**Impact:** If Moran's I is significant, the effective number of independent sites is smaller than 78, and the bootstrap CIs are too narrow. If not significant, it removes a major attack vector.

**Action:** Compute Moran's I with inverse-distance weight matrix (100 km cutoff) on site-level mean residuals. Report statistic and p-value. If significant, note as limitation and discuss CI width implications. Effort: 2-4 hours (code + interpretation).

### 1.5 Feature Count Confusion: 137 vs 72 (Osei, Tanaka, Kowalski)

**What:** The abstract, Section 3.2, and Table 1 all say 137 features. The model uses 72 active features after ablation. Table 1 has a footnote, but it is buried and readers will be confused.

**Impact:** Reviewers will think the model has 137 features and question overfitting. When they discover 65 were dropped, they will wonder which features are actually in the model.

**Action:** (a) Change all prominent references to "72 active features (selected from 137 candidates through systematic ablation)." (b) Table 1 should mark active vs dropped features. (c) Appendix B should list the ablation methodology and dropped features. Effort: 1 hour.

### 1.6 Vault Must Be Opened (Liu)

**What:** The vault (36 sites) exists specifically to provide an unbiased test. The holdout was evaluated across 7+ model versions (v4-v11), making it a development set, not a true test set. Without the vault, the holdout metrics are optimistic by an unknown amount.

**Impact:** A savvy reviewer will note that the holdout was used iteratively and question whether reported metrics are inflated.

**Action:** Open the vault exactly once. Report all metrics. If vault performance is within the holdout CI, this is strong evidence. If outside, explain the discrepancy. Effort: 2 hours (run evaluation, write up).

---

## SEVERITY 2: HIGH (will weaken the paper if not addressed)

### 2.1 "30% of Sites R2 < 0" is Actually ~24% (Osei, Liu)

**What:** The paper says "30% of holdout sites have R2 < 0." Bootstrap point estimate of frac_R2_gt_0 = 0.757, meaning ~24.3% have R2 < 0. The 95% CI is [0.681, 0.837], so 30% is within the CI but is not the point estimate.

**Action:** Use the actual number: "approximately 24% of holdout sites [95% CI: 16-32%] have R2 < 0." Effort: 15 minutes.

### 2.2 "Without Any Site-Specific Calibration" Language (Whitfield, Tanaka)

**What:** The BCF_mean = 1.297 is a global bias correction estimated from training data. While not per-site, it is a form of calibration.

**Action:** Replace "without any site-specific calibration" with "without per-site parameter estimation" throughout. Effort: 15 minutes.

### 2.3 Storm Event "2-4x Smaller Median Error" Claim (Whitfield, Osei)

**What:** Brandywine: v11 median +119% vs OLS +165% = 1.4x. Valley Creek: +169% vs +591% = 3.5x. Ferron: -39% vs +124% = 3.2x (absolute). The 2-4x claim fails at Brandywine.

**Action:** Report the range honestly: "1.4x to 3.5x smaller median event error." Effort: 15 minutes.

### 2.4 Temporal Adaptation Collapse Understated (all 6 reviewers)

**What:** Temporal N=10 MedSiteR2 = 0.389, below zero-shot (0.401). This is operationally devastating: the most realistic adaptation strategy makes the model worse. The paper mentions this in Section 4.4 but underplays it.

**Action:** Expand to a dedicated subsection. Quantify the baseflow fraction in the first 10 temporal samples. Diagnose the N=10 staging threshold as the mechanism. Issue explicit sampling recommendations. Effort: 4 hours.

### 2.5 "Publication Grade" Tier Overstated (Kowalski)

**What:** N=30 random MedSiteR2 = 0.478. N=50 random = 0.497. The adaptation curve plateaus around 0.50. Claiming "publication grade" (R2 > 0.70) is not supported.

**Action:** Remove "publication grade" tier or redefine it honestly: "At favorable sites (carbonate geology, depth-integrated), R2 may exceed 0.70; at the median site, N=30 achieves 0.48." Effort: 30 minutes.

### 2.6 Bayesian Prior Sensitivity Unanalyzed (Vasquez, Liu)

**What:** k=15 and df=4 are stated but not justified. No sensitivity analysis. These were potentially tuned on the holdout.

**Action:** Run a 3x3 grid (k in {10, 15, 20}, df in {2, 4, 8}). Report in an appendix. If MedSiteR2 range is < 0.02, state that adaptation is robust. Effort: 4-6 hours.

### 2.7 No Per-Site R2 Distribution Histogram (Liu, Osei)

**What:** The paper reports MedSiteR2 and the failure rate but never shows the full distribution. This is essential for WRR reviewers.

**Action:** Create a histogram of per-site R2 values with annotations at R2 = 0 and R2 = 0.5 thresholds. Main-text figure. Effort: 1-2 hours.

### 2.8 Missing CatBoost vs LSTM Justification (Osei, Tanaka)

**What:** Every reviewer will ask "Why not an LSTM?" The paper does not discuss model architecture choice.

**Action:** Add a paragraph in Discussion: CatBoost chosen for (a) native categorical handling (collection method SHAP rank 3), (b) native missing value handling, (c) interpretability via SHAP, (d) computational efficiency for ablation. Acknowledge LSTM as future work. Effort: 30 minutes.

### 2.9 Section 3.8 Error: Conformal Calibration Set (Vasquez)

**What:** The paper says "Residuals from the holdout set are binned" but the actual calibration set is LOGO CV predictions (23,588 samples from 244 training sites). The holdout is used for evaluation only.

**Action:** Correct Section 3.8 to specify LOGO CV as the calibration set and holdout as evaluation. Effort: 15 minutes.

---

## SEVERITY 3: MEDIUM (strengthens the paper)

### 3.1 Ferron Creek Buried Behind Brandywine (Whitfield, Tanaka)

Ferron Creek is the strongest single-site load validation (daily R2 = 0.76, Spearman = 0.96) and the only non-Pennsylvania site. It should receive equal billing.

### 3.2 Between-Site CV Ratio (3.2x) Not in Abstract (Whitfield, Tanaka)

This is one of the most important findings and should appear in Key Points and abstract.

### 3.3 Collection Method Disaggregated Metrics Missing from Main Text (Kowalski)

Auto-point R2 = 0.24 is the operational reality for most users. It must be in the main text, not buried.

### 3.4 Seasonal Disaggregation Not in Paper (Tanaka)

Spring R2 = 0.421 vs other seasons R2 = 0.700 supports the particle size story and is not reported.

### 3.5 Drainage Area Effect Not in Paper (Tanaka, Kowalski)

rho = -0.375, p = 0.004. Small basins have 121% MAPE vs large basins 47%. Operationally important.

### 3.6 Power Law Slopes Not in Paper (Tanaka, Whitfield)

Per-site slopes: median 0.952, range 0.29-1.55. 50% steepen at high turbidity, 32% flatten. Geology predicts slope. This IS the physical finding and is absent from the draft.

### 3.7 Residual Autocorrelation Not Discussed (Liu, Vasquez, Kowalski)

Lag-1 up to 0.69. Effective sample sizes are smaller than reported. CIs may be anti-conservative.

### 3.8 Conformal 52% Coverage at >2000 mg/L Needs Expansion (Vasquez, Kowalski)

Currently one sentence. Needs 3-5 sentences explaining the operational implication: intervals are unreliable exactly where they matter most.

### 3.9 Year-by-Year Load Breakdown Missing (Whitfield)

Annual data at Brandywine is mostly NaN. If the 2.6% total hides year-to-year errors of 50%+, that must be documented.

---

## SEVERITY 4: LOW (nice-to-have improvements)

- Per-site conformal coverage histogram (Vasquez)
- Coverage by geology class (Vasquez)
- Per-site turbidity-OLS baseline comparison (Osei)
- Threshold exceedance classification metrics (Kowalski)
- Degraded-sensor (no turbidity) fallback quantification (Kowalski)
- Bug history supplementary table (Liu, Whitfield)
- WRTDS/LOADEST comparison (Kowalski)

---

*Prepared 2026-04-02 by the Phase 2 Expert Team.*
