# Supplementary Materials Outline — Phase 2 Expert Team

**Date:** 2026-04-02

## Organizing Principle

Main text: the science story (hypothesis, key results, interpretation). ~8,000 words.
Supplement: methodological detail, complete tables, sensitivity analyses, and figures that support but do not drive the narrative.

---

## What Goes in the Main Text

1. **Abstract, PLS, Introduction** (as drafted)
2. **Data** (sites, observations, partitioning, external validation — keep concise)
3. **Methods** (model architecture, 72 active features with brief description, Box-Cox + BCF, LOGO CV, Bayesian adaptation summary, OLS benchmark, load comparison protocol, conformal intervals, evaluation metrics)
4. **Results:**
   - Zero-shot cross-site performance (Table: MedSiteR2, Spearman, MAPE, within-2x, baselines)
   - Per-site R2 distribution (Figure 2 — NEW)
   - Disaggregated by geology (Figure 3, table)
   - Adaptation curve (Figure 4, table)
   - CatBoost vs OLS (Figure 5, table)
   - External NTU validation (brief paragraph + key numbers)
   - Sediment load comparison (Table 6-8, Figures 6-7)
   - Prediction uncertainty (coverage summary, 52% caveat)
5. **Discussion:**
   - Hypothesis test: geology controls the optical-gravimetric conversion
   - Turbidity advantage (hysteresis argument)
   - Site heterogeneity as scientific finding
   - Collection method confound
   - Temporal adaptation warning
   - Comparison with published models
   - Why not LSTM
   - Practical deployment guidance
6. **Limitations** (Moran's I, stationarity, approved-only bias, extreme coverage, autocorrelation, clay mineralogy)
7. **Conclusions**

---

## What Goes in the Supplement

### Table S1. Complete Per-Site Metric Table
All 78 holdout sites: site_id, name, state, HUC2, dominant geology, collection method, N_samples, R2, MAPE, Spearman, within-2x, median SSC, drainage area. Sorted by R2 descending. This is the table reviewers will scrutinize.

### Table S2. Complete Feature List (137 Candidates)
All 137 candidate features with: name, category, description, units, data source, active/dropped status, SHAP rank (if active), reason for dropping (if dropped). This replaces the confusing 137 vs 72 situation.

### Table S3. Feature Ablation Summary
The systematic ablation results: feature name, delta_R2_log, delta_R2_native, combined score, decision (keep/drop).

### Table S4. Hyperparameter Sensitivity Sweep
Full 15-experiment table from Appendix A, with all metrics (KGE, alpha, bias, BCF, time).

### Table S5. Bayesian Prior Sensitivity Grid
3x3 grid of (k, df) values showing N=10 random MedSiteR2 for each combination. (AFTER the analysis is run.)

### Table S6. Adaptation Curve (Full)
All N values (0, 1, 2, 3, 5, 10, 20, 30, 50) for all 3 split modes, with all metrics (MedSiteR2, MAPE, within-2x, Spearman, KGE, bias, n_sites).

### Table S7. Load Comparison Extended Metrics
Daily metrics (R2, Spearman, pbias, RMSE) for all 3 sites, both methods, both all-days and transport-days.

### Table S8. Conformal Interval Coverage by Bin
5 SSC bins, 90% and 80% nominal: n_calibration, n_holdout, coverage, interval width (median, IQR).

### Table S9. External Validation by Network
Breakdown of the 260 NTU sites by monitoring network (UMRR, state agencies, etc.) with Spearman, MAPE, within-2x.

### Table S10. Catastrophic Site Analysis (optional)
The 51 sites with LOGO R2 < -1: how many are genuinely wrong (7), how many are low-signal (17), how many have unknown collection method (30).

### Figure S1-S8. (as listed in figures_review.md)

### Text S1. Transform Selection Details
The 20-experiment sweep (currently Section 4.1 in v1 draft). Move entirely to supplement. Keep one sentence in main text Methods.

### Text S2. Feature Importance Details
Full SHAP analysis with the three information channels discussion (currently Section 4.2 in v1 draft). Move the detailed text to supplement, keep SHAP beeswarm figure and top-5 summary in main text.

### Text S3. CQR Failure Details
Expanded discussion of why Box-Cox compression is structurally incompatible with CQR. Currently Section 6.2.

### Text S4. Dual BCF Justification
Statistical rationale for using BCF_mean for loads and BCF_median for individual predictions. Report both sets of holdout metrics.

### Text S5. Bug Disclosure Table (optional)
Table of material bugs discovered during development (prune_gagesii, v9 holdout contamination, QC vectorization), with their impact on metrics and how they were resolved. Methodological transparency.

---

## Rough Word Budget

| Section | Main Text Words | Supplement |
|---------|----------------|------------|
| Abstract + PLS | 500 | -- |
| Introduction | 800 | -- |
| Data | 800 | -- |
| Methods | 1,500 | Text S1-S5 (~3,000 words) |
| Results | 2,000 | Tables S1-S9, Figures S1-S8 |
| Discussion | 1,500 | -- |
| Limitations | 500 | -- |
| Conclusions | 400 | -- |
| **Total** | **~8,000** | **~3,000 + tables + figures** |

---

*Prepared 2026-04-02 by the Phase 2 Expert Team.*
