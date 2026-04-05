# Analysis Gap List — Phase 2 Expert Team

**Date:** 2026-04-02

Each gap includes: what it is, why it matters, estimated effort, and whether it is blocking or nice-to-have.

---

## BLOCKING (paper cannot be submitted without these)

### 1. Moran's I on Site-Level Residuals
**What:** Compute spatial autocorrelation statistic (Moran's I) using a distance-based weight matrix (inverse-distance, 100 km cutoff) on the mean per-site residual (or per-site R2) for the 78 holdout sites.
**Why:** Every WRR reviewer will ask about spatial dependence. If holdout sites near training sites systematically have smaller errors, the bootstrap CIs are too narrow and the MedSiteR2 is optimistic. The informal finding (39% vs 55% error at <50 km vs >50 km) suggests weak spatial correlation exists.
**Effort:** 2-4 hours. PySAL or scipy.spatial with existing site coordinates and per-site residuals.
**Deliverable:** Moran's I statistic, p-value, and 2-3 sentences in Limitations.

### 2. Open the Vault (36 Sites)
**What:** Run the full v11 evaluation pipeline on the 36 vault sites exactly once. Report all primary metrics (MedSiteR2, MedSiteSpearman, MAPE, within-2x, fraction R2>0).
**Why:** The holdout was used across v4-v11 development. The vault is the only uncontaminated test set. If vault results are within the holdout CI, the paper is much stronger. If they differ, the paper must explain why.
**Effort:** 2 hours (evaluation script already exists; write-up needed).
**Deliverable:** One table in main text or supplement. Brief discussion paragraph.

### 3. Reconcile Brandywine Load Numbers
**What:** Document exactly: (a) how many days the total load (42,059 tons) covers, (b) how many of those days have concurrent 80155 data, (c) the total load for matched-day-only comparison, (d) explain why the daily total_load_ratio (1.594) differs from the period total ratio (1.03).
**Why:** The discrepancy between 2.6% total match and 59.4% daily pbias is the single most likely rejection trigger. A reviewer who finds the JSON will see 1.594 and conclude the paper is misleading.
**Effort:** 4-6 hours (data analysis, clear documentation).
**Deliverable:** Revised load comparison section with transparent day-coverage accounting.

---

## HIGH PRIORITY (significantly strengthen the paper)

### 4. Per-Site R2 Distribution Histogram
**What:** Histogram of the 78 holdout site R2 values, with vertical lines at R2=0 and R2=0.5, and annotations showing the fraction in each region.
**Why:** The disaggregated per-site distribution is the backbone of the transferability story. Reviewers need to see the bimodal shape (many sites near R2=0.5-0.8, a cluster below 0, a few extremely negative).
**Effort:** 1-2 hours.
**Deliverable:** Main-text figure.

### 5. Bayesian Prior Sensitivity Grid
**What:** 3x3 grid: k in {10, 15, 20}, df in {2, 4, 8}. Report N=10 random MedSiteR2 for each combination.
**Why:** k=15 and df=4 were hand-tuned. Without sensitivity analysis, a reviewer can argue the adaptation results are fragile.
**Effort:** 4-6 hours (9 runs of 50 MC trials each on 78 holdout sites).
**Deliverable:** Appendix table. One sentence in main text: "Adaptation results are robust to prior specification (MedSiteR2 range < X across the sensitivity grid)."

### 6. Quantify Baseflow Fraction in Temporal First-10
**What:** For each holdout site, compute: what fraction of the first 10 chronological samples are above the site's median SSC? How many are from storm events?
**Why:** Diagnoses the temporal adaptation collapse (N=10 temporal R2 = 0.389 < zero-shot 0.401). The paper asserts "disproportionately baseflow" but does not quantify.
**Effort:** 2-3 hours.
**Deliverable:** Numbers for discussion subsection. Expected finding: ~80% of first-10 samples are below-median SSC.

### 7. Effective Sample Size Discussion
**What:** Report: (a) number of unique sampling events per site after burst deduplication (6.8% are bursts), (b) median samples per site with range, (c) estimated effective N per site using lag-1 autocorrelation.
**Why:** The paper uses "23,624 samples" and "260 sites" interchangeably. The independent unit for cross-site claims is the site (N=260/78), not the observation. Within-site autocorrelation up to 0.69 means effective per-site N is 30-50% of nominal.
**Effort:** 2 hours.
**Deliverable:** Paragraph in Methods. Table in supplement.

### 8. Tier A/B/C Comparison in Results
**What:** Report the Tier A (sensor-only), B (+ basic attributes), C (+ watershed) comparison with holdout metrics.
**Why:** Key evidence that the model uses watershed context, not just turbidity. Without it, a reviewer can argue the model is a fancy turbidity regression.
**Effort:** 1 hour (results exist in RESULTS_LOG; need formatting).
**Deliverable:** One table in Results section.

---

## MEDIUM PRIORITY (desirable for a strong paper)

### 9. Per-Geology Turbidity-SSC Slope Distributions
**What:** Plot per-site log(SSC) vs log(turbidity) slopes colored by geology class.
**Why:** Directly shows WHY carbonate sites work (tight slope distribution) and volcanic sites don't (wide). This is the most physically informative figure for the hypothesis.
**Effort:** 4-6 hours.
**Deliverable:** Main-text figure.

### 10. Year-by-Year Brandywine Load Comparison
**What:** Complete the annual load data (currently mostly NaN) at Brandywine.
**Why:** If year-to-year errors of 50%+ cancel to produce 2.6% total, that must be documented. Currently only 2010 and 2011 have v11 annual data.
**Effort:** 4-8 hours (may require rerunning load calculation for specific years).
**Deliverable:** Table or figure showing annual loads.

### 11. Seasonal Disaggregation Table
**What:** Report R2, MAPE, within-2x by season (Spring vs rest). Already in RESULTS_LOG (Spring R2 = 0.421, other = 0.700).
**Why:** Supports the particle size story (snowmelt vs rainfall).
**Effort:** 1 hour.
**Deliverable:** Row in disaggregated results table.

### 12. Drainage Area Effect
**What:** Report rho = -0.375, p = 0.004 between log(drainage area) and MAPE. Show small basins at 121% MAPE vs large at 47%.
**Why:** Operationally critical for users deciding if the model applies to their sites.
**Effort:** 1 hour.
**Deliverable:** Paragraph in Discussion.

### 13. Per-Site Conformal Coverage Histogram
**What:** For each of the 78 holdout sites, compute the fraction of predictions within the 90% interval. Plot histogram.
**Why:** The aggregate 90.6% may hide sites with 50% coverage and others with 100%.
**Effort:** 2-3 hours.
**Deliverable:** Supplementary figure.

### 14. Learning Curve by Training Set Size
**What:** Train on 50, 100, 150, 200, 260 sites. Report holdout MedSiteR2 at each.
**Why:** Determines whether more training sites would help and at what point saturation occurs.
**Effort:** 8-12 hours (5 retraining runs).
**Deliverable:** Supplementary figure.

---

## LOW PRIORITY (future work or supplement)

### 15. Formal Predictability Model
Per-site R2 ~ f(geology, drainage_area, collection_method). Quantifies how much performance variation is explained by observable attributes.

### 16. Temporal Train-Test Split
Train on pre-2015, test on post-2015 at the same sites. Addresses stationarity.

### 17. Threshold Exceedance Classification Metrics
Precision/recall for SSC > 100, > 500, > 1000 mg/L.

### 18. Degraded-Sensor Fallback Performance
Set turbidity to NaN and evaluate on the same holdout. Quantifies discharge-only mode.

### 19. Comparison with WRTDS/LOADEST
Modern load estimation baselines beyond simple OLS.

### 20. Coverage by Geology Class
Evaluate conformal intervals separately for carbonate, sedimentary, and volcanic sites.

---

**Estimated total effort for blocking items:** 10-16 hours
**Estimated total effort through high priority:** 25-35 hours
**Estimated total effort through medium priority:** 50-65 hours

*Prepared 2026-04-02 by the Phase 2 Expert Team.*
