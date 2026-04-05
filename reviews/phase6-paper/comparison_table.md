# Formal Comparison Table — Phase 2 Expert Team

**Date:** 2026-04-02

## Cross-Site SSC and Water Quality Models

| Attribute | **murkml v11 (this work)** | **Song et al. 2024** | **Zhi et al. 2024** | **Kratzert et al. 2019** |
|---|---|---|---|---|
| **Target variable** | SSC (mg/L) | SSC (mg/L) | Multiple WQ (DO, conductance, etc.) | Streamflow (not WQ) |
| **Primary input** | Continuous turbidity (FNU) | Discharge + meteorology | Discharge + meteorology | Precipitation + temperature |
| **Architecture** | CatBoost (gradient boosting) | LSTM (recurrent neural net) | Transformer / deep learning | LSTM |
| **Training sites** | 260 USGS | 377 USGS | ~500 | 531 CAMELS |
| **Holdout sites** | 78 (truly unseen) | Ungauged prediction at all sites | Variable by parameter | PUB at ungauged basins |
| **Temporal inputs** | Instantaneous + 1hr/7d/30d windows | Full hydrograph sequences | Full sequences | Full daily sequences |
| **Static attributes** | 72 active (geology, land cover, soils, method) | Watershed attributes (CAMELS-style) | Watershed attributes | Watershed attributes (CAMELS) |
| **Primary metric** | MedSiteR2 = 0.40 (zero-shot) | Median R2 = 0.55 (gauged sites) | Varies by parameter | NSE > 0.73 median (streamflow) |
| **Ranking metric** | Per-site Spearman = 0.875 | Not reported | Not reported | Not applicable |
| **Per-site failure rate** | 24% sites R2 < 0 | Not reported per-site | Not reported per-site | Not reported per-site |
| **Adapted performance** | MedSiteR2 = 0.49 (N=10 random) | N/A (fully trained per-site) | N/A | N/A |
| **Load validation** | 3 sites vs USGS 80155 (2.6% at Brandywine) | None | None | None |
| **External validation** | 260 NTU sites (Spearman = 0.927) | None reported | Limited | CAMELS splits |
| **Uncertainty quantification** | Empirical conformal (90.6% coverage) | None reported | None reported | None reported |
| **Interpretability** | SHAP feature importance | Limited (LSTM black-box) | Limited | Limited |
| **Missing data handling** | Native (CatBoost) | Requires imputation | Requires imputation | Requires imputation |
| **Categorical features** | Native (collection method rank 3) | Not applicable | Not applicable | Not applicable |
| **Publication venue** | WRR (target) | WRR | Nature Water | HESS |

---

## Key Comparisons

### murkml vs Song et al. 2024

**Complementary, not competing.** Song et al. predict SSC from discharge at sites without turbidity sensors. murkml predicts SSC from turbidity at sites with sensors but without calibrated regressions. The methods address different parts of the 4,000-site monitoring network.

**Performance:** Song et al. median R2 = 0.55 at gauged sites (with site-specific data in training) vs murkml MedSiteR2 = 0.40 at truly ungauged sites. Direct comparison is confounded by:
- Song uses site-specific training data (the LSTM sees data from the target site); murkml does not.
- Song's R2 = 0.55 includes discharge-only predictions where turbidity is unavailable; murkml's 0.40 includes turbidity-available predictions where discharge-only would perform worse.
- Song does not report per-site failure rates; murkml honestly reports 24% R2 < 0.
- murkml's Spearman = 0.875 per-site is not directly comparable to Song's R2 (different metrics).

**The turbidity advantage:** murkml's value proposition is event-scale: turbidity captures hysteresis that discharge cannot. The storm-event load comparison (1.4-3.5x lower median error than OLS) is evidence Song et al. cannot match without turbidity input. This should be framed as "turbidity adds event-scale information inaccessible to discharge-only models."

### murkml vs Zhi et al. 2024

**Different physics.** Zhi et al. focus primarily on dissolved species (DO, conductance-based parameters) where the surrogate relationship is dissolution chemistry. murkml targets particulate transport where the surrogate relationship is optical scattering. They share methodology (cross-site ML with watershed attributes) but the underlying physics is fundamentally different.

**Relevance:** Cite as evidence of the general paradigm (cross-site ML for water quality) but do not attempt direct metric comparison. Note that murkml attempted to extend to dissolved parameters (TP, nitrate) and failed, which correctly bounds the approach to particle-mediated parameters.

### murkml vs Kratzert et al. 2019

**Analogous framework, different application.** Kratzert showed that LSTMs can learn catchment-specific hydrologic "fingerprints" from static attributes + forcing sequences, enabling PUB (prediction in ungauged basins). murkml does the analogous thing for the turbidity-SSC relationship: watershed attributes encode the site-specific optical-gravimetric conversion.

**Architecture choice:** Kratzert's success with LSTMs raises the question of why murkml uses CatBoost instead. The answer: (a) CatBoost natively handles categorical features (collection method is SHAP rank 3); (b) CatBoost natively handles missing values (79% of sites missing pH); (c) SHAP provides interpretability that LSTM cannot match; (d) CatBoost enables the extensive ablation program (450x faster GKF5 mode) that produced the 72-feature set. LSTM is acknowledged as future work.

### murkml vs Per-Site Turbidity-SSC OLS (Rasmussen et al. 2009)

**The natural baseline.** The standard operational approach is per-site log(SSC) ~ log(Turb) regression with 30-100 calibration samples. This achieves median R2 = 0.78-0.90 (Uhrich & Bragg, 2003). murkml's zero-shot MedSiteR2 = 0.40 is substantially lower. The comparison that matters is:

| Method | Samples Required | MedSiteR2 |
|--------|-----------------|-----------|
| Per-site Turb-SSC OLS | 30-100 | 0.78-0.90 |
| murkml zero-shot | 0 | 0.40 |
| murkml + 10 samples | 10 | 0.49 |
| murkml + 30 samples | 30 | 0.48 |
| Per-site OLS (N=10) | 10 | 0.37 (CatBoost OLS comparison) |
| Per-site OLS (N=2) | 2 | -0.56 (catastrophic) |

**The value proposition:** murkml is not better than a fully calibrated per-site regression. It is better than having no regression at all (the situation at most turbidity sites), and better than OLS at low N (the situation when you are starting a new monitoring program).

**Missing comparison (noted by Osei):** The paper compares to per-site OLS(discharge), not per-site OLS(turbidity). A per-site log(SSC) ~ log(Turb) regression with the same N samples used in the adaptation experiments would be the fairest baseline. This comparison is missing and should be added if feasible.

---

## Summary Statement for Paper

The following paragraph is recommended for the Discussion:

> Direct comparison with prior cross-site SSC models is limited by input data differences. Song et al. (2024) achieve median R2 = 0.55 using LSTM with discharge and watershed attributes at sites with some training data; our zero-shot MedSiteR2 = 0.40 at truly unseen sites is lower in absolute terms but the models address different segments of the monitoring network. No prior cross-site model uses continuous turbidity or validates against operational sediment load records. Our model is complementary to discharge-only approaches: it fills the gap at the estimated 3,600 USGS turbidity sites lacking calibrated SSC regressions, while discharge-only models serve sites without turbidity sensors entirely.

---

*Prepared 2026-04-02 by the Phase 2 Expert Team.*
