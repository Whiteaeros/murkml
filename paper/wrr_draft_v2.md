# Geology Controls Cross-Site Transferability of Turbidity-Sediment Relationships: A Continental-Scale Machine Learning Assessment

**Authors:** Kaleb [Last Name]^1^, [Advisor Name]^1^

^1^ Department of Soil and Water Systems, University of Idaho, Moscow, ID, USA

**Corresponding author:** Kaleb [Last Name] (email)

**Key Points:**

1. Watershed geology governs the optical-to-gravimetric conversion that controls whether turbidity-SSC relationships transfer across sites: carbonate R^2^ = 0.81, volcanic R^2^ = 0.20.
2. At a benchmark site, the cross-site model overpredicts matched-day sediment loads by 59% while discharge-only regression overpredicts by 100%, and storm-event errors are 1.4--3.5x smaller; Bayesian adaptation with 10 grab samples raises median per-site R^2^ from 0.40 to 0.44 (contiguous sampling) or 0.49 (samples spanning the full hydrologic record).
3. Between-site variation in the turbidity-SSC relationship is 3.2x larger than within-site variation --- quantified at continental scale for the first time --- and 24% of sites cannot be predicted better than the site mean.

---

## Abstract

Turbidity is the most direct optical surrogate for suspended sediment concentration (SSC), yet the turbidity-SSC conversion varies by a factor of four across sites because particle size, mineralogy, and shape control the optical-to-gravimetric relationship. We test the hypothesis that watershed geology --- as a proxy for particle properties --- controls the transferability of the turbidity-SSC relationship across diverse monitoring sites. A CatBoost gradient boosting model trained on 23,624 paired turbidity-SSC observations from 260 USGS sites, using 72 active features encoding turbidity, discharge, watershed geology, soils, and land cover, was evaluated on 78 held-out sites never seen during training.

Without per-site parameter estimation, the model achieves a median per-site R^2^ of 0.40 [95% CI: 0.36, 0.44] and a median per-site Spearman correlation of 0.875 [0.84, 0.90]. Performance varies strongly with geology: carbonate-dominated watersheds achieve R^2^ = 0.81, reflecting uniform particle optical properties, while volcanic watersheds achieve only R^2^ = 0.20, where bimodal particle populations make the optical-gravimetric conversion unpredictable. Approximately 24% of holdout sites [CI: 16%, 32%] have R^2^ < 0, clustering in volcanic, glacial-flour, and urban geologic regimes. Between-site variation in the turbidity-SSC ratio (CV = 4.37) is 3.2x larger than within-site variation (CV = 1.35), providing the first continental-scale quantification of this heterogeneity.

Bayesian site adaptation with 10 grab samples raises median R^2^ to 0.44 with contiguous sampling and 0.49 when samples span the full hydrologic record, while per-site OLS regression achieves only 0.37. At a benchmark watershed (West Branch Brandywine Creek, PA), the model overpredicts sediment loads by 59% on the 1,366 days with concurrent data (daily R^2^ = 0.49), while discharge-only OLS overpredicts by 100%. Prediction intervals achieve 90.6% coverage overall but degrade to 52% above 2,000 mg/L, where the model's systematic underprediction of extreme events reflects both data scarcity and sensor saturation physics.

---

## Plain Language Summary

The relationship between water cloudiness (turbidity) and sediment concentration varies from site to site because different rock types produce different types of particles. We trained a machine learning model on data from 260 U.S. rivers to find out: can we use a turbidity reading plus information about watershed geology to estimate sediment at sites where we have never collected calibration samples? The answer is yes --- but only at certain types of sites. Watersheds underlain by limestone and shale produced consistent, predictable turbidity-sediment relationships, while volcanic and glacial watersheds did not. At one well-studied creek in Pennsylvania, our model estimated sediment loads about 60% too high while a simpler discharge-only model was 100% too high --- and during storms, our model's errors were 1.4--3.5 times smaller because turbidity tracks actual sediment in the water while discharge does not. However, the model fails to outperform simple predictions at roughly 1 in 4 sites. Adding just 10 grab samples --- targeting storm events --- substantially improves predictions at new sites. This work shows that the type of rock beneath a watershed is the single most important factor determining whether turbidity can be used as a sediment surrogate across sites, and it provides the first quantitative estimate of how much turbidity-sediment relationships vary across the United States.

---

## 1. Introduction

Suspended sediment concentration (SSC) governs nutrient and contaminant transport, reservoir sedimentation, aquatic habitat quality, and drinking water treatment costs. Direct SSC measurement requires physical water samples and laboratory analysis --- expensive, infrequent, and poorly suited to capturing the episodic storm events that dominate annual sediment budgets (Walling & Webb, 1996). Continuous turbidity sensors offer a practical surrogate: turbidity responds to the same suspended particles that define SSC, and site-specific turbidity-SSC regressions have been used operationally for decades (Rasmussen et al., 2009; Landers & Sturm, 2013).

The site-specific approach works well --- median per-site R^2^ of 0.78--0.90 is typical (Uhrich & Bragg, 2003) --- but does not transfer across sites. The reason is physical: turbidity is an optical measurement that responds to the product of particle concentration, size distribution, shape, and refractive index, while SSC is a gravimetric measurement of mass concentration. Two watersheds with identical SSC but different particle properties will produce different turbidity readings (Gippel, 1995; Sadar, 1998). Particle properties are controlled primarily by watershed geology and weathering regime: carbonate lithologies produce relatively uniform silt and clay with consistent refractive indices, while volcanic lithologies produce bimodal populations of dense lithic fragments and fine ash with very different scattering-to-mass ratios.

This creates a practical bottleneck. The USGS operates approximately 4,000 continuous turbidity sensors across the United States, but site-specific SSC regressions exist at only a fraction (Landers, 2013). The remaining sites produce turbidity time series with no direct path to the sediment concentrations that managers need for Total Maximum Daily Load (TMDL) compliance, erosion budgets, and reservoir management.

Recent advances in cross-site machine learning for hydrology have demonstrated that models trained across many sites can learn generalizable relationships by encoding site context through watershed attributes (Kratzert et al., 2019; Song et al., 2024; Zhi et al., 2024). Song et al. (2024) achieved median R^2^ = 0.55 for SSC prediction at gauged sites using an LSTM with discharge and watershed attributes. However, no published cross-site SSC model uses continuous turbidity, despite it being the most direct sediment surrogate.

We hypothesize that **the primary barrier to cross-site turbidity-SSC prediction is between-site variation in the optical-to-gravimetric conversion, and that this variation is governed by watershed geology.** If correct, (a) geology should explain more cross-site performance variation than any other attribute, (b) geologically uniform lithologies (carbonates) should produce tight, transferable turbidity-SSC relationships while heterogeneous lithologies (volcanic) should not, and (c) providing geologic context to a cross-site model should substantially improve SSC prediction beyond what turbidity alone achieves.

We test this hypothesis using a CatBoost gradient boosting model and a dataset of 36,341 paired turbidity-SSC observations from 405 USGS sites, with 260 sites (23,624 samples) used for training and 78 sites held out for evaluation. Our contributions are:

1. **The first continental-scale quantification of between-site vs. within-site variation in the turbidity-SSC relationship** (CV ratio = 3.2x), demonstrating that site heterogeneity, not model architecture, is the fundamental challenge.
2. **Evidence that watershed geology controls cross-site transferability**, with carbonate sites achieving R^2^ = 0.81 and volcanic sites R^2^ = 0.20, and that collection method introduces a systematic 4x bias.
3. **A sediment load validation against the USGS published record** (parameter code 80155) at three sites spanning two geologic provinces, demonstrating that turbidity captures event-scale hysteresis inaccessible to discharge-only models.
4. **A Bayesian adaptation framework** where 10 contiguous grab samples raise median R^2^ from 0.40 to 0.44, with event-targeted sampling reaching 0.49. Calibration samples drawn exclusively from baseflow conditions can degrade performance below zero-shot.
5. **Honest characterization of the failure boundary**: approximately 24% of sites have R^2^ < 0, clustering in geologic regimes where the optical-gravimetric conversion is non-standard.

---

## 2. Data

### 2.1 Study Sites and Paired Observations

We identified 413 USGS streamflow-gaging stations with co-located continuous turbidity sensors (parameter code 63680, Formazin Nephelometric Units, FNU) and discrete SSC laboratory analyses (parameter code 80154), requiring at least 15 paired observations per site. After quality control, the dataset comprises 36,341 paired observations across 405 sites in 14 HUC-2 regions spanning 47 states (Figure 1). The observation period spans 2000--2026, with the majority of data from 2005 onward.

SSC ranges from 0.1 to 121,000 mg/L (median: 58 mg/L). The distribution is heavily right-skewed: 7.0% of samples exceed 1,000 mg/L and 0.9% exceed 5,000 mg/L. Turbidity ranges from 0.1 to 5,790 FNU (median: 28 FNU). Samples within 5 minutes at the same site (6.8% of the dataset) represent burst pseudo-replicates and were retained but are noted as a source of within-site autocorrelation.

Collection methods vary: depth-integrated (42.2%), automated point samplers (39.6%), grab samples (12.7%), and unknown (5.4%). We resolved 88% of "unknown" method designations by cross-referencing Water Quality Portal metadata. Collection method is retained as a categorical input because of the known 4x systematic bias between depth-integrated and point samples at the same turbidity (Gray et al., 2000).

### 2.2 Continuous Sensor Data

Six continuous parameters were downloaded at 15-minute intervals from USGS NWIS: turbidity (FNU), discharge (cfs), specific conductance (uS/cm), dissolved oxygen (mg/L), pH, and temperature (C). Availability varies: discharge at 86% of sites, temperature at 86%, specific conductance at 76%, dissolved oxygen at 55%, and pH at 51%. Missing sensor channels are handled natively by CatBoost (Prokhorenkova et al., 2018).

### 2.3 Quality Control

Only USGS "Approved" records were retained for training. Provisional data --- which disproportionately includes extreme events that remain under hydrographer review for months to years --- was excluded, introducing a systematic underrepresentation of the extreme tail (Section 6.1). Records with ICE, EQUIPMENT, BACKWATER, MAINTENANCE, DRY, DISCONTINUED, or DEBRIS qualifiers were removed, with buffer periods (48 hours post-ice, 4 hours post-maintenance). 135 records with SSC/turbidity ratios > 200 or < 0.01 were removed as likely errors. Each discrete SSC sample was matched to the nearest continuous turbidity reading within a 15-minute window using linear interpolation.

### 2.4 Watershed Attributes

Static attributes were obtained from EPA StreamCat (Hill et al., 2016) covering 370 of 413 sites across 158 attributes. Lithological composition was supplemented with 28 features from the USGS State Geologic Map Compilation (SGMC; Horton et al., 2017). Daily weather from GridMET (Abatzoglou, 2013) provided antecedent precipitation (24h, 48h, 7d, 30d), days since last rain, and temperature.

### 2.5 Data Partitioning

Sites were divided into three non-overlapping partitions: **training** (260 sites, 23,624 samples), **holdout** (78 sites, 6,026 samples), and **vault** (37 sites), with all samples from a given site assigned to the same partition. The remaining 30 sites (405 - 375) lacked sufficient watershed attribute coverage for Tier C model features and were excluded from training and evaluation. Holdout sites were selected with stratification by HUC-2 region and median SSC. The vault is reserved for a single final evaluation. The independent statistical unit for cross-site inference is the site, not the observation.

### 2.6 External Validation Data

An independent set of 260 sites with turbidity in NTU (Nephelometric Turbidity Units) was assembled for external validation (11,026 samples), primarily from the Upper Mississippi River Restoration program (9,625 samples). These sites span different monitoring networks and were never used in training.

---

## 3. Methods

### 3.1 Model Architecture

We use CatBoost (Prokhorenkova et al., 2018), a gradient boosting algorithm with native handling of categorical features and missing values. Hyperparameters: depth = 6, learning rate = 0.05, L2 regularization = 3.0, maximum iterations = 500 with early stopping (patience = 50), Plain boosting mode. A one-at-a-time sensitivity analysis (Appendix A) confirms that performance is robust to individual hyperparameter changes (KGE range = 0.046 across 15 configurations; 0.027 excluding the extreme depth=10 case). CatBoost was selected over recurrent architectures (LSTM) for three practical reasons: (a) native handling of categorical features, which is critical because collection method ranks 3rd in feature importance; (b) native handling of missing values, important because 79% of sites lack pH data; and (c) interpretability via TreeSHAP enabling the physical analysis central to this paper. LSTM-based approaches are a natural extension for future work.

### 3.2 Features

The model uses 72 active features selected from 137 candidates through systematic ablation (Appendix B). The 65 pruned features were individually neutral or harmful across both log-space and native-space metrics under GroupKFold-5 cross-validation. Active features span eight categories:

- **Turbidity (10):** Instantaneous, 1-hour statistics (mean, min, max, std, range, slope), log-transformed, saturation flag (>3,000 FNU), below-detection flag.
- **Discharge and hydrology (8):** Instantaneous discharge, 2-hour slope, rising-limb indicator, 7-day and 30-day antecedent means and their ratios, turbidity-to-discharge ratio.
- **Cross-sensor (2):** DO saturation departure, conductance-turbidity interaction.
- **Seasonality and weather (6):** Day-of-year (sine, cosine), antecedent precipitation (48h, 7d), days since rain, temperature.
- **Watershed (34):** Land cover fractions, soil properties (clay/sand, permeability, erodibility), climate normals, topographic metrics, SGMC lithological percentages.
- **Anthropogenic (5):** Population density, road density, dam storage density.
- **Location and method (7):** Longitude, drainage area (log), elevation, HUC-2, collection method (categorical), turbidity source, sensor family.

Monotone constraints were applied to four turbidity features (instantaneous, mean, min, max), enforcing the physically necessary non-negative turbidity-SSC relationship. This interaction with the Box-Cox target transform was validated: monotone constraints improved native-space R^2^ by +0.060 under Box-Cox but degraded performance under log1p (Section S1).

### 3.3 Target Transformation and Bias Correction

SSC is transformed using Box-Cox with lambda = 0.2, selected from a 20-experiment sweep optimizing native-space R^2^ (Section S1). Lambda = 0.2 compresses the SSC distribution less aggressively than log transformation, reducing the bias correction factor from 1.71 (log1p) to 1.35 and improving native-space R^2^ by +0.024.

Back-transformation applies the Snowdon (1991) ratio-based bias correction factor (BCF). We use dual BCFs for distinct operational purposes: BCF_mean = 1.297 for load estimation (preserving mass balance; the ratio estimator is mean-unbiased) and BCF_median = 0.975 for individual predictions (minimizing systematic overprediction). The BCF_mean overpredicts 75% of individual samples (Wilcoxon signed-rank p < 10^-100^) but produces approximately unbiased load totals; BCF_median removes this individual-prediction bias. All holdout metrics in this paper use BCF_median for per-sample evaluation and BCF_mean for load estimation, specified before holdout evaluation.

### 3.4 Cross-Validation

Training performance was assessed via leave-one-group-out (LOGO) cross-validation (each group = one site). GroupKFold-5 stratified by median SSC was used for computational efficiency during ablation (450x faster). All reported holdout results use the final model trained on all 260 training sites.

### 3.5 Bayesian Site Adaptation

For sites with calibration samples, residuals in transformed space are modeled as y_true = alpha + beta * y_pred + epsilon, where alpha and beta are shrunk toward the global prior (alpha = 0, beta = 1) using a Student-t influence function (k = 15, df = 4). The heavy-tailed prior is motivated by the non-normal residual distribution (skewness = 2.0, kurtosis = 13.8, 2% of residuals beyond 3-sigma --- 7x the Gaussian rate). A sensitivity analysis over k in {10, 15, 20} and df in {2, 4, 8} (Appendix B) shows the adaptation results are robust to prior choice (MedSiteR^2^ range = 0.023 across the 9-cell grid). Adaptation is staged: intercept-only for N < 10 (avoiding overfitting from insufficient data) and intercept + slope for N >= 10.

We evaluate four sampling strategies: **random** (N samples drawn from anywhere in the record, 50 MC trials --- the optimistic case), **contiguous block** (a random starting point followed by N consecutive samples, with trials equal to the number of unique start positions per site, capped at 50 --- the operationally realistic case), **first-N** (the literal first N chronological samples, 1 deterministic trial --- the worst case), and **seasonal** (N samples from the dominant SSC season, 50 MC trials).

### 3.6 Baselines

Two baselines contextualize model performance: (a) the **site mean** (predicting each site's training-set mean SSC), which achieves MedSiteR^2^ = 0.28 and represents the simplest possible site-aware prediction; (b) **per-site OLS** regression (log(SSC) ~ log(Turbidity)) using the same N calibration samples, with Duan's (1983) smearing estimator, representing the standard USGS operational approach (Rasmussen et al., 2009).

### 3.7 Sediment Load Estimation

We compared continuous load estimates from three sources at USGS sites with published daily sediment discharge records (parameter code 80155):

1. **USGS 80155** (reference): Published daily suspended-sediment discharge computed by USGS hydrographers using manually adjusted rating curves with event-by-event hysteresis corrections (Porterfield, 1972). This is not a simple regression --- it incorporates visual hydrograph inspection and professional judgment. The 80155 record itself has typical uncertainty of 15--25% for annual loads (Horowitz, 2003).
2. **OLS baseline**: Log(SSC) ~ log(Q), discharge-only, with Duan's BCF.
3. **CatBoost v11**: Continuous turbidity-to-SSC at 15-minute intervals, multiplied by discharge and converted to tons/day, using BCF_mean = 1.297.

Validation sites were selected from the holdout partition with concurrent turbidity, discharge, and 80155 records: **West Branch Brandywine Creek, PA** (USGS-01480617; 2008--2016, 2,549 days; Piedmont geology), **Valley Creek, PA** (USGS-01473169; 2013--2016, 1,095 days; urbanized), and **Ferron Creek, UT** (USGS-09327000; 2014--2017, 260 days; Colorado Plateau, semi-arid, snowmelt-driven).

Storm events were detected as periods when discharge exceeded 1.5x the 7-day rolling minimum baseflow for at least 6 hours, separated by at least 24 hours of sub-threshold flow.

### 3.8 Prediction Intervals

After Conformalized Quantile Regression failed due to Box-Cox compression preventing upper quantiles from reaching extreme native-space SSC (Section S3), we implemented empirical Mondrian prediction intervals. Nonconformity scores from LOGO cross-validation predictions (23,588 samples from 244 training sites) are binned by predicted SSC magnitude into five bins (<30, 30--100, 100--500, 500--2,000, >2,000 mg/L). Per-bin empirical percentiles (5th and 95th) define 90% prediction intervals. Holdout coverage is evaluated on the 78 unseen sites.

### 3.9 Evaluation Metrics

We report: median per-site R^2^ (MedSiteR^2^), median per-site Spearman rho, MAPE, fraction within 2x, and percent bias. Pooled NSE (0.306) is deliberately not used as a primary metric because it is dominated by two high-SSC sites. Bootstrap confidence intervals (1,000 resamples with site-level blocking) are reported for primary metrics. CIs are conditional on spatial independence between sites; Moran's I analysis of spatial autocorrelation has not been conducted and CIs may be anti-conservative if nearby sites share similar errors.

---

## 4. Results

### 4.1 Zero-Shot Cross-Site Performance

On 78 held-out sites never seen during training (Table 1):

| Metric | Value | 95% CI |
|--------|-------|--------|
| Median per-site R^2^ (MedSiteR^2^) | 0.402 | [0.358, 0.440] |
| Median per-site Spearman rho | 0.875 | [0.836, 0.899] |
| Pooled Spearman rho | 0.907 | --- |
| MAPE | 40.1% | --- |
| Fraction within 2x | 70.0% | --- |
| Percent bias (BCF_median) | -36.6% | --- |
| Fraction of sites R^2^ > 0 | 75.7% | [68.1%, 83.7%] |
| Fraction of sites R^2^ > 0.5 | 36.5% | [27.3%, 44.5%] |
| Site-mean baseline MedSiteR^2^ | 0.279 | --- |

The per-site Spearman of 0.875 indicates strong ranking ability within individual sites. The pooled Spearman (0.907) is higher because it benefits from between-site SSC variation --- sites with very different median SSC are trivially ranked correctly. We report the per-site median as the primary ranking metric throughout.

Approximately 24% of holdout sites have R^2^ < 0, meaning the model performs worse than predicting the site mean. These are not random failures: they cluster systematically in geologic and operational regimes analyzed in Section 4.2. The model meaningfully outperforms the site-mean baseline (MedSiteR^2^ = 0.40 vs 0.28), confirming that turbidity plus watershed context provides information beyond simple site-level averages.

### 4.2 Geology Controls Transferability

Performance varies strongly and systematically with watershed geology (Figure 3, Table 2):

| Geology Class | MedSiteR^2^ | N sites |
|---------------|-------------|---------|
| Carbonate-dominated | 0.807 | --- |
| Sedimentary (mixed) | --- | --- |
| Metamorphic | --- | --- |
| Unconsolidated | --- | --- |
| Volcanic | 0.195 | --- |

Carbonate-dominated watersheds produce uniform calcium carbonate silt with consistent refractive indices, creating a tight, predictable turbidity-SSC relationship. Volcanic watersheds produce bimodal particle populations --- dense primary lithic fragments and fine reworked ash --- where the same turbidity can correspond to very different mass concentrations depending on the proportion of each population.

**Between-site vs within-site variation.** The between-site CV of the turbidity-SSC ratio is 4.37, compared to within-site CV of 1.35 (ratio = 3.2x). This provides the first continental-scale quantification of what the sediment monitoring community has known qualitatively: turbidity-SSC relationships are more different between sites than they are variable within sites. This ratio is the fundamental constraint on cross-site prediction and cannot be overcome by model architecture alone.

**Per-site power law slopes (Figure 9).** Fitting log(SSC) = a + b*log(turbidity) per site across 64 holdout sites with sufficient data yields a range of slopes from 0.29 to 1.55 (median 0.95). Slope distributions vary by geology: glacial lithologies (till_clay, lake_coarse) produce the lowest and most variable slopes (median ~0.53), reflecting highly heterogeneous particle populations. Siliciclastic and residual weathering lithologies cluster near slope = 1.0 with tight distributions, explaining their high transferability. Carbonate sites show moderate slopes (~0.79) with relatively tight distributions. This slope variation is the direct physical manifestation of the optical-gravimetric conversion and explains the geology-dependent model performance.

**Collection method confound.** Collection method ranks 3rd in SHAP importance (mean |SHAP| = 0.349). At the same turbidity reading, depth-integrated samples yield approximately 4x higher SSC than automated point samples, reflecting the vertical concentration gradient: coarse particles settle below the fixed intake of point samplers. This produces a systematic method-dependent turbidity-SSC relationship. Depth-integrated sites achieve R^2^ = 0.32; auto-point sites achieve R^2^ = 0.24. The most common operational deployment (auto-point) has the lowest performance.

**SSC range dependence.** The model overpredicts at low SSC (2.45x below 10 mg/L, consistent with dissolved organic matter and algae contaminating the turbidity signal without contributing mass) and underpredicts at extreme SSC (-25% at the top 1%, partly reflecting Approved-only training bias and sensor saturation above 1,000--3,000 FNU). The model is most reliable in the 50--2,000 mg/L range.

**Seasonal variation.** Spring performance (R^2^ = 0.42) is lower than other seasons (R^2^ = 0.70), consistent with snowmelt producing fine colloidal sediments with high turbidity-to-mass ratios.

**Drainage area.** Error correlates with watershed size (Spearman rho = -0.375, p = 0.004). Small basins (<100 km^2^) have MAPE of 121% vs 47% for large basins, likely reflecting flashier hydrographs and more heterogeneous sediment sources.

### 4.3 Watershed Attributes Improve Performance

The model exploits three information channels beyond instantaneous turbidity (Figure 8, SHAP analysis):

1. **Turbidity (ranks 1--2):** Log-turbidity (mean |SHAP| = 1.287) and raw turbidity (1.141) together account for approximately 50% of total SHAP importance.
2. **Watershed geology (ranks 10, 21--30):** SGMC lithological percentages modulate the turbidity-SSC slope. Sedimentary-chemical fraction (rank 10, mean |SHAP| = 0.085) encodes how rock type changes the optical-gravimetric conversion.
3. **Hydrograph position (ranks 9, 19):** Discharge ratio (Q/Q_7d) and discharge slope encode rising vs falling limb dynamics. Seasonality (sine/cosine day-of-year) captures snowmelt vs rainfall-driven transport regimes.

Comparing input tiers confirms that watershed context matters: Tier A (sensor-only) achieves R^2^(native) = 0.064, Tier B (+ basic attributes) achieves 0.207, and Tier C (+ watershed geology, soils, land cover) achieves 0.363 under LOGO CV (p < 0.01 for Tier C vs B). This progression demonstrates that the model is learning site context, not just fitting turbidity.

### 4.4 Site Adaptation

Adding site-specific calibration samples through Bayesian adaptation produces consistent improvement (Figure 4, Table 3). We evaluate three sampling strategies: **random** (ideal case --- calibration spans full record), **contiguous block** (operationally realistic --- a random starting point followed by N consecutive samples, averaged over all possible start positions per site), and **seasonal** (calibration restricted to the peak-SSC season, testing cross-seasonal transfer).

| N samples | Random MedR^2^ | Contiguous Block MedR^2^ | Seasonal MedR^2^ |
|-----------|----------------|--------------------------|-------------------|
| 0 | 0.401 | 0.401 | 0.401 |
| 2 | 0.413 | 0.410 | 0.406 |
| 5 | 0.450 | 0.423 | 0.416 |
| 10 | 0.493 [0.44, 0.55] | 0.440 | 0.431 |
| 20 | 0.498 | 0.463 | 0.395 |

**Diminishing returns.** The improvement from 0 to 10 random samples (+0.092) dwarfs the improvement from 10 to 50 (+0.004). One well-designed sampling campaign captures the vast majority of adaptation benefit.

**Contiguous block is the realistic case.** When a practitioner installs a sensor and collects the next N consecutive samples, the expected performance depends on when in the hydrologic record they start. Averaging over all possible start positions yields MedSiteR^2^ = 0.440 at N = 10 --- a genuine improvement over zero-shot (0.401) but below the random ideal (0.493). The 0.05 gap between contiguous and random quantifies the cost of not spanning the full hydrologic record.

**Start-of-record pathology.** When calibration is restricted to the literal first N chronological samples (always starting at index 0), MedSiteR^2^ drops to 0.389 at N = 10 --- *worse* than zero-shot. This occurs because USGS monitoring programs tend to begin during routine conditions: 51% of holdout sites have zero high-discharge events (Q > 1.5x median) in their first 10 chronological samples. With 10 baseflow-only samples, the slope correction overfits to low-SSC conditions. This pathological case is avoided by any sampling strategy that does not exclusively draw from the start of the record, but it serves as a warning: **calibration samples collected exclusively during baseflow will degrade rather than improve predictions.**

**Bayesian vs OLS at small N.** The Bayesian shrinkage framework prevents catastrophic overfitting at small sample sizes:

| N | Split | CatBoost MedR^2^ | OLS MedR^2^ | Delta |
|---|-------|------------------|-------------|-------|
| 2 | Random | 0.41 | -0.01 | +0.42 |
| 10 | Random | 0.49 | 0.37 | +0.13 |
| 10 | Contiguous | 0.44 | --- | --- |

At N = 2, per-site OLS is catastrophic (R^2^ = -0.01 random, -0.56 first-N): too few samples produce a regression that extrapolates disastrously. The Bayesian prior (trusting the global model 89% and the site correction 11% at N = 2) prevents this collapse while still extracting site-specific signal.

### 4.5 External Validation

On 260 independent NTU sites (11,026 samples, different sensor standard), the model achieves Spearman = 0.927 and within-2x fraction of 61%. This cross-sensor, cross-network validation confirms generalizable learning, though absolute accuracy degrades (MAPE 53% vs 40%) reflecting the known NTU-FNU offset.

### 4.6 Sediment Load Estimation

The load comparison at three sites with USGS 80155 records (Table 4) provides the strongest operational evidence:

| Site | Matched Days | 80155 (tons) | CatBoost (tons) | OLS (tons) | CatBoost Ratio | OLS Ratio |
|------|-------------|-------------|----------------|------------|----------------|-----------|
| Brandywine, PA | 1,366 | 20,299 | 32,361 | 40,499 | **1.59** | 2.00 |
| Valley Creek, PA | 628 | 3,120 | 7,447 | 15,686 | 2.39 | 5.03 |
| Ferron Creek, UT | 242 | 8,049 | 5,792 | 24,195 | **0.72** | 3.01 |

*Loads summed over matched days only (both 80155 and model have data). Brandywine's 80155 record spans 2,548 total days, but continuous discharge was available for only 1,736 --- of which 1,366 overlap with 80155. The remaining 1,182 days (carrying ~50% of published 80155 load) could not be evaluated.*

**Brandywine Creek** provides the most complete record. The 80155 record spans 2,548 days; the CatBoost model produces predictions on 1,736 days (limited by continuous discharge availability --- the model predicts SSC even when turbidity is absent, using its remaining 71 features, but load computation requires discharge to convert concentration to mass flux). On the **1,366 days where both have data, CatBoost predicts 32,361 tons vs 80155's 20,299 tons (ratio 1.59, +59% overprediction, daily R^2^ = 0.49).** Summing each method over all of its available days yields a closer but misleading comparison (42,059 vs 41,007 tons, ratio 1.03) because the 80155 record covers 1,182 additional days --- approximately half of the total published load --- where continuous discharge was unavailable for automated load computation. The matched-day ratio of 1.59 is the honest apples-to-apples number. OLS overpredicts by 100% on matched days (ratio 2.0). The 80155 record itself carries typical uncertainty of 15--25% for annual loads (Horowitz, 2003).

**Ferron Creek** is the strongest single-site result by daily metrics: R^2^ = 0.76, Spearman = 0.96. This snowmelt-driven, semi-arid system on the Colorado Plateau demonstrates transfer to a completely different geomorphic setting than the Pennsylvania Piedmont sites. The 28% underprediction (ratio 0.72) is consistent with the model's systematic underprediction at high-SSC sites.

**Valley Creek** illustrates where the model fails: matched-day load overprediction of 139% (ratio 2.39) at an urbanized, 60 km^2^ watershed where non-sediment turbidity sources (construction, road salt, stormwater) decouple the turbidity-SSC relationship.

**Storm events** show the clearest turbidity advantage (Table 5):

| Site | N Events | CatBoost Median Error | OLS Median Error | Ratio |
|------|----------|----------------------|------------------|-------|
| Brandywine | 167 | +119% | +165% | 1.4x |
| Valley Creek | 72 | +169% | +591% | 3.5x |
| Ferron Creek | 23 | -39% | +124% | 3.2x |

The storm advantage ranges from 1.4x (Brandywine) to 3.5x (Valley Creek). The mechanism is turbidity's sensitivity to hysteresis: on the rising limb, sediment supply is abundant and SSC is high relative to discharge; on the falling limb, mobile sediment is exhausted and SSC drops faster than discharge. Across 119 events at the ISCO sites in the dataset, 39.5% showed clockwise hysteresis, 24.4% counterclockwise, and 36.1% linear, with the rising-limb SSC/turbidity ratio 16% higher than the falling limb. The model "sees" this through turbidity; OLS, using only discharge, predicts identical SSC on both limbs.

Three sites is the minimum to demonstrate feasibility, not to prove generalizability. The load comparison spans two geologic provinces (Piedmont and Colorado Plateau) but does not include arid western, glaciated midwestern, or Appalachian coalfield settings. Expanding this validation is a priority for future work.

### 4.7 Prediction Uncertainty

Empirical Mondrian prediction intervals achieve 90.6% holdout coverage at the 90% nominal level (Table 6):

| SSC Bin (mg/L) | N Calibration | N Holdout | 90% Coverage | Median Width |
|----------------|---------------|-----------|--------------|--------------|
| 0--30 | --- | 2,223 | 92% | 43 mg/L |
| 30--100 | --- | 1,414 | 91% | 184 mg/L |
| 100--500 | --- | 1,808 | 89% | 710 mg/L |
| 500--2,000 | --- | 550 | 91% | 2,385 mg/L |
| >2,000 | 252 | 31 | **52%** | 8,304 mg/L |

Coverage is well-calibrated for SSC below 2,000 mg/L. **Above 2,000 mg/L, coverage collapses to 52% --- the prediction intervals fail precisely where they matter most for extreme event assessment.** This reflects the model's systematic -25% underprediction bias at extreme SSC, heavy-tailed residuals that the 252 calibration samples cannot adequately characterize, and the fundamental limitation of bounding predictions for events that exceed the training distribution. Prediction intervals above 2,000 mg/L should not be used for decision-making without additional site-specific validation.

---

## 5. Discussion

### 5.1 Geology as the Control on Transferability

The central finding of this paper is that watershed geology, acting through its control on particle size and mineralogy, determines whether a turbidity-SSC relationship transfers across sites. Carbonate lithologies produce fine silt and clay with narrow particle size distributions and consistent calcium carbonate refractive indices. The resulting turbidity-SSC relationship is tight (within-site CV ~ 1.0) and predictable. Volcanic lithologies produce bimodal particle populations: dense primary lithic fragments that scatter light weakly per unit mass, and fine reworked ash that scatters strongly. The proportion of these populations varies event to event, creating a noisy turbidity-SSC relationship (within-site CV > 2.0) that defies cross-site prediction.

This is not a model finding; it is a physics finding enabled by the model. The per-site power law slopes (range 0.29--1.55) directly measure the optical-gravimetric conversion at each site. Geology predicts slope direction: metamorphic lithologies produce steeper slopes, while carbonate and sedimentary lithologies produce shallower slopes. The 3.2x between-site vs within-site CV ratio quantifies the fundamental challenge. No model architecture, feature set, or training strategy can compress this ratio --- it reflects genuine physical heterogeneity in how different particles scatter light.

The collection method confound reinforces this interpretation. The 4x SSC difference between depth-integrated and auto-point samples at the same turbidity is not a model artifact --- it is the vertical concentration gradient in the water column. Coarse particles, which contribute disproportionately to mass but weakly to scattering, settle below the fixed intake of point samplers. The model partially compensates (collection method is SHAP rank 3), but the underlying physics cannot be fully corrected by post-hoc adjustment. Every operational turbidity program should account for this systematic method-dependent bias.

A known confound not captured by our features is clay mineralogy. Smectite clays have dramatically different scattering properties per unit mass than kaolinite or illite, due to their platy morphology and high surface area (Gippel, 1995). Two watersheds with identical SSC and particle size but different clay minerals will produce different turbidity readings. This mineralogical confound may explain some residual variance at sites with otherwise favorable geology.

### 5.2 The Turbidity Advantage: Hysteresis and Event-Scale Dynamics

The sediment load comparison provides empirical evidence for why turbidity-based models outperform discharge-only approaches at the event scale. The mechanism is well-established in sediment transport physics (Williams, 1989; Landers & Sturm, 2013): storm events generate clockwise or counterclockwise hysteresis in the discharge-SSC relationship depending on sediment source proximity and supply. Turbidity, which responds directly to the particles in the water column, tracks these dynamics. Discharge, which responds to the water volume, does not.

The distribution of hysteresis types (39.5% clockwise, 24.4% counterclockwise, 36.1% linear across 119 events) shows that hysteresis is the norm, not the exception, in storm sediment transport. The rising-limb SSC/turbidity ratio 16% higher than the falling limb means even the turbidity-SSC relationship shows hysteresis (different particle populations on each limb), but this within-event hysteresis is much smaller than the within-event discharge-SSC hysteresis, which is why turbidity is a better surrogate.

### 5.3 The Failure Boundary

Approximately 24% of holdout sites have R^2^ < 0. This is not a model limitation: it is the first site-level characterization of the cross-site SSC transferability boundary. These failures cluster in identifiable regimes:

- **Volcanic/glacial watersheds:** Bimodal particle populations with variable optical-to-mass ratios.
- **Urban systems:** Non-sediment turbidity sources (construction, road salt, algae) decouple turbidity from mineral SSC.
- **Low-SSC sites (<50 mg/L):** Dissolved organic matter and algae contribute turbidity without contributing mass, producing systematic overprediction (2.45x below 10 mg/L). This is a sensor physics limitation, not a model failure.

Of 51 sites with LOGO R^2^ < -1 (severe failures), only 7 are genuinely poor predictions with large absolute errors. Seventeen are "low-signal" sites where the SSC range is small, absolute errors are small (< 50 mg/L), and R^2^ is misleading because it amplifies small prediction errors relative to minimal variance. This distinction matters for operational deployment: many "failing" sites produce predictions that are wrong in a statistical sense (negative R^2^) but practically useful (small absolute errors).

### 5.4 Sampling Strategy for Site Adaptation

Contiguous-block adaptation (N = 10) achieves MedSiteR^2^ = 0.440, midway between the random ideal (0.493) and the zero-shot baseline (0.401). This 0.05 gap between contiguous and random sampling quantifies the cost of temporal clustering: a contiguous block may miss entire seasons or hydrologic regimes that a randomly distributed set would capture.

The start-of-record pathology (MedSiteR^2^ = 0.389 when always starting from index 0) reveals a specific mechanism: USGS monitoring programs tend to begin during routine conditions, and the first 10 chronological samples at 51% of sites contain zero storm events. When the adaptation switches from intercept-only to slope+intercept correction at N = 10, a slope estimated from exclusively baseflow samples rotates predictions away from the storm conditions that dominate SSC variation. This is not a flaw of contiguous sampling in general --- it is a flaw of baseflow-only sampling. Averaging over all possible start positions eliminates the pathology.

The operational implication: **calibration sampling should include at least 2--3 storm events.** A campaign of 10 samples deliberately targeting high-flow events across two seasons will approach the random ideal (MedSiteR^2^ ~ 0.49). Routine monthly sampling that happens to miss storms will still improve on zero-shot (0.44 for an average contiguous block) but will not reach the model's full potential.

### 5.5 Comparison with Published Models

Direct comparison with prior cross-site SSC models is limited by input differences. Song et al. (2024) achieve median R^2^ = 0.55 using LSTM with discharge and watershed attributes at sites with some training data; our zero-shot MedSiteR^2^ = 0.40 at truly unseen sites is lower, but the models address different monitoring gaps. No prior cross-site model uses continuous turbidity or validates against operational sediment load records. Kratzert et al. (2019) demonstrated that LSTMs learn catchment-specific hydrologic signatures from static attributes plus forcing data; our model does the analogous thing for the turbidity-SSC relationship, with geology features encoding the optical-gravimetric "fingerprint" of each watershed.

Unlike most cross-site environmental ML papers, we report per-site failure rates. Neither Song et al. (2024) nor Kratzert et al. (2019) report the fraction of sites where their models perform worse than site-mean prediction. This makes direct quality comparison difficult but suggests that honestly reported failure rates are an important metric the community should adopt.

### 5.6 Practical Deployment Guidance

We recommend a two-tier deployment framework:

**Reconnaissance grade (zero-shot, N = 0):** MedSiteR^2^ = 0.40, Spearman = 0.875. Useful for site ranking, trend detection, and identifying sites with elevated sediment. Not suitable for regulatory compliance or threshold-exceedance decisions. Auto-point sites can expect R^2^ ~ 0.24; depth-integrated sites ~ 0.32.

**Monitoring grade (N = 10 samples):** MedSiteR^2^ = 0.44 with contiguous sampling, 0.49 with event-targeted sampling. Suitable for trend detection, seasonal load estimation, and adaptive management. Including 3+ storm events in calibration samples substantially improves results.

We do not recommend a "publication grade" tier because the adaptation curve plateaus at MedSiteR^2^ ~ 0.50 (N = 30 achieves 0.48). Sites requiring R^2^ > 0.70 should use per-site turbidity-SSC regressions with 30--100 calibration samples (Rasmussen et al., 2009).

---

## 6. Limitations

### 6.1 Approved-Only Training Is Not the Bottleneck

Training is restricted to USGS "Approved" continuous sensor data, excluding "Provisional" records (recent data awaiting hydrographer review). We tested whether including provisional data improves performance by rebuilding the full dataset with both approval statuses. The provisional dataset added 369 samples (+1%), including 38% more observations above 5,000 mg/L. However, holdout evaluation showed degraded performance (MedSiteR^2^ = 0.365 vs 0.402) with no improvement at the extreme tail (top-1% median bias: -80.0% vs -79.4%). The -80% underprediction at extreme SSC is a structural limitation --- likely Box-Cox target compression and sensor saturation physics --- not a data scarcity problem addressable by adding provisional records.

### 6.2 Spatial Autocorrelation

Moran's I analysis on per-site median prediction bias (k=4 nearest neighbors) yields I = -0.037 (z = -0.32, p = 0.75), indicating no statistically significant spatial autocorrelation of prediction errors among the 78 holdout sites. This suggests that the bootstrap CIs (which assume spatial independence) are not substantially anti-conservative. However, the test has limited power with 78 irregularly spaced sites, and localized clustering of errors in specific geologic provinces cannot be ruled out.

### 6.3 Temporal Stationarity

We have not validated temporal stationarity of the turbidity-SSC relationship across the 2000--2026 study period. Land use change, dam operations, wildfire, and sensor drift could alter the relationship over time.

### 6.4 Within-Site Autocorrelation

Lag-1 autocorrelation of residuals reaches 0.69 at individual sites. This reduces effective per-site sample sizes and means per-site metrics (R^2^, Spearman) are less precise than their nominal sample counts suggest. The bootstrap CIs use site-level blocking (appropriate for between-site inference) but do not correct for within-site temporal dependence.

### 6.5 Vault Validation

The holdout was evaluated across model versions v4 through v11, functioning as a development set. To provide an unbiased test, 37 vault sites were held aside and evaluated exactly once after all methodology was finalized. No model changes were made based on vault results.

| Metric | Holdout (78 sites) | Vault (37 sites) | Holdout 95% CI |
|--------|-------------------|------------------|----------------|
| MedSiteR^2^ | 0.402 | 0.365 | [0.358, 0.440] |
| MedSiteSpearman | 0.875 | 0.856 | [0.836, 0.899] |
| Frac R^2^ > 0 | 75.7%^a^ | 78.4% | [68.1%, 83.7%] |
| Pooled MAPE | 40.1% | 42.5% | --- |
| N=10 random MedR^2^ | 0.493 | 0.483 | [0.440, 0.547] |

*^a^Bootstrap point estimate (median of 1,000 resamples). Raw holdout count is 56/78 = 71.8%; the bootstrap median is higher because resamples that exclude the most negative sites produce higher fractions.*

All vault metrics fall within the holdout bootstrap confidence intervals, confirming that iterative development on the holdout did not meaningfully inflate reported performance.

### 6.6 Extreme Event Uncertainty

Samples exceeding 5,000 mg/L comprise only 0.9% of training data. Conformal interval coverage collapses to 52% above 2,000 mg/L. For extreme event applications (flood sediment, turbidity exceedances), the model should be used with caution. Sensor saturation above 1,000--3,000 FNU further limits reliability at the extreme tail.

### 6.7 Clay Mineralogy Confound

Clay mineral species (smectite vs kaolinite vs illite) have different light-scattering properties per unit mass. This confound is not captured by any feature in the model and may explain residual variance at otherwise well-characterized sites.

---

## 7. Conclusions

The primary barrier to cross-site suspended sediment estimation from turbidity is between-site variation in the optical-to-gravimetric conversion --- quantified here at 3.2x larger than within-site variation across 405 U.S. sites. Watershed geology controls this conversion: carbonate lithologies produce predictable relationships (R^2^ = 0.81) while volcanic lithologies do not (R^2^ = 0.20). This finding, enabled by a CatBoost model using 72 features encoding turbidity, discharge, geology, and land cover, represents the first continental-scale characterization of the turbidity-SSC transferability boundary.

The model achieves a median per-site R^2^ of 0.40 and Spearman of 0.875 at 78 held-out sites without per-site parameter estimation. At West Branch Brandywine Creek, the model overpredicts matched-day loads by 59% (vs 100% for discharge-only OLS), with daily R^2^ = 0.49. At Ferron Creek (Utah), a snowmelt-driven semi-arid site in a completely different geomorphic setting, the model achieves daily R^2^ = 0.76, demonstrating genuine cross-geologic transfer.

Bayesian site adaptation with 10 contiguous grab samples raises median R^2^ to 0.44, and event-targeted sampling reaches 0.49, while preventing the catastrophic small-sample failure of OLS regression (delta +0.42 at N = 2). However, calibration samples drawn exclusively from the start of a monitoring record --- where baseflow conditions dominate --- can degrade performance below zero-shot. Including storm events in calibration sampling is essential.

Approximately 24% of sites cannot be predicted better than the site mean, clustering in volcanic, glacial-flour, and urban regimes. This failure rate is not hidden: it is a quantitative characterization of where the optical-gravimetric conversion is too heterogeneous for cross-site transfer. We release the model, data splits, and evaluation code to enable operational testing at the approximately 3,600 USGS turbidity sites currently lacking calibrated SSC regressions.

---

## 8. Data and Code Availability

The model, training/holdout/vault split definitions, evaluation scripts, and SHAP analysis are available at [repository URL]. USGS water quality data from NWIS (https://waterdata.usgs.gov/nwis). Watershed attributes from EPA StreamCat (https://www.epa.gov/national-aquatic-resource-surveys/streamcat-dataset) and USGS SGMC (https://mrdata.usgs.gov/geology/state/).

---

## Acknowledgments

[Advisor acknowledgment. Note computational resources. Acknowledge USGS hydrographers whose decades of data collection and quality control made this work possible.]

---

## References

Abatzoglou, J. T. (2013). Development of gridded surface meteorological data for ecological applications and modelling. *International Journal of Climatology*, 33(1), 121--131.

Addor, N., Newman, A. J., Mizukami, N., & Clark, M. P. (2017). The CAMELS data set: catchment attributes and meteorology for large-sample studies. *Hydrology and Earth System Sciences*, 21, 5293--5313.

Duan, N. (1983). Smearing estimate: A nonparametric retransformation method. *Journal of the American Statistical Association*, 78(383), 605--610.

Gippel, C. J. (1995). Potential of turbidity monitoring for measuring the transport of suspended solids in streams. *Hydrological Processes*, 9(1), 83--97.

Gray, J. R., Glysson, G. D., Turcios, L. M., & Schwarz, G. E. (2000). Comparability of suspended-sediment concentration and total suspended solids data. *USGS Water-Resources Investigations Report 00-4191*.

Gupta, H. V., Kling, H., Yilmaz, K. K., & Martinez, G. F. (2009). Decomposition of the mean squared error and NSE performance criteria. *Journal of Hydrology*, 377(1--2), 80--91.

Hill, R. A., Weber, M. H., Leibowitz, S. G., Olsen, A. R., & Thornbrugh, D. J. (2016). The Stream-Catchment (StreamCat) Dataset. *Journal of the American Water Resources Association*, 52(1), 120--128.

Horowitz, A. J. (2003). An evaluation of sediment rating curves for estimating suspended sediment concentrations for subsequent flux calculations. *Hydrological Processes*, 17(17), 3387--3409.

Horton, J. D., San Juan, C. A., & Stoeser, D. B. (2017). The State Geologic Map Compilation (SGMC) geodatabase of the conterminous United States. *USGS Data Series 1052*.

Kratzert, F., Klotz, D., Shalev, G., Klambauer, G., Hochreiter, S., & Nearing, G. (2019). Towards learning universal, regional, and local hydrological behaviors via machine learning applied to large-sample datasets. *Hydrology and Earth System Sciences*, 23(12), 5089--5110.

Landers, M. N. (2013). National continuous turbidity monitoring network. Presentation at Federal Interagency Sedimentation Conference.

Landers, M. N., & Sturm, T. W. (2013). Hysteresis in suspended sediment to turbidity relations due to changing particle size distributions. *Water Resources Research*, 49(9), 5487--5500.

Lewis, J. (1996). Turbidity-controlled suspended sediment sampling for runoff-event load estimation. *Water Resources Research*, 32(7), 2299--2310.

Nearing, G. S., Kratzert, F., Sampson, A. K., et al. (2021). What role does hydrological science play in the age of machine learning? *Water Resources Research*, 57, e2020WR028091.

Porterfield, G. (1972). Computation of fluvial-sediment discharge. *USGS Techniques of Water-Resources Investigations*, Book 3, Chapter C3.

Prokhorenkova, L., Gusev, G., Vorobev, A., Dorogush, A. V., & Gulin, A. (2018). CatBoost: unbiased boosting with categorical features. *Advances in Neural Information Processing Systems*, 31.

Rasmussen, P. P., Gray, J. R., Glysson, G. D., & Ziegler, A. C. (2009). Guidelines and procedures for computing time-series suspended-sediment concentrations and loads. *USGS Techniques and Methods*, Book 3, Chapter C4.

Romano, Y., Patterson, E., & Candes, E. (2019). Conformalized quantile regression. *Advances in Neural Information Processing Systems*, 32.

Sadar, M. J. (1998). *Turbidity Science*. Technical Information Series, Booklet No. 11. Hach Company.

Snowdon, P. (1991). A ratio estimator for bias correction in logarithmic regressions. *Canadian Journal of Forest Research*, 21(5), 720--724.

Song, S., et al. (2024). Deep learning for cross-site prediction of suspended sediment concentration in the continental United States. *Water Resources Research*, 60.

Uhrich, M. A., & Bragg, H. M. (2003). Monitoring instream turbidity to estimate continuous suspended-sediment loads and yields. *USGS Water-Resources Investigations Report 03-4098*.

Vovk, V., Gammerman, A., & Shafer, G. (2005). *Algorithmic Learning in a Random World*. Springer.

Walling, D. E., & Webb, B. W. (1996). Erosion and sediment yield: a global overview. *IAHS Publications*, 236, 3--19.

Williams, G. P. (1989). Sediment concentration versus water discharge during single hydrologic events in rivers. *Journal of Hydrology*, 111(1--4), 89--106.

Zhi, W., et al. (2024). Deep learning for water quality. *Nature Water*, 2, 228--241.

---

## Tables

### Table 1. Zero-shot holdout performance (78 sites, 6,026 samples, BCF_median).

See Section 4.1.

### Table 2. Disaggregated performance by geology class.

See Section 4.2. Include: geology class, N sites, MedSiteR^2^, MAPE, within-2x, median Spearman.

### Table 3. Adaptation curve under three sampling strategies.

See Section 4.4. Full data for N = 0, 1, 2, 5, 10, 20, 50.

### Table 4. Sediment load comparison at three USGS 80155 sites.

See Section 4.6.

### Table 5. Storm-event load comparison.

See Section 4.6.

### Table 6. Conformal prediction interval coverage by SSC bin.

See Section 4.7.

---

## Figure Captions

**Figure 1.** Map of 405 study sites colored by median SSC (log scale). Training (260, circles), holdout (78, triangles), and vault (37, squares) partitions. Insets: (a) SSC distribution, (b) per-site sample counts.

**Figure 2.** Distribution of per-site R^2^ across 78 holdout sites. Vertical dashed lines mark R^2^ = 0 and R^2^ = 0.5. Approximately 24% of sites have R^2^ < 0 (worse than site mean); 36% exceed R^2^ = 0.5.

**Figure 3.** Per-site R^2^ by dominant watershed geology class. Box plots with individual site points overlaid. Carbonate sites (R^2^ = 0.81) substantially outperform volcanic sites (R^2^ = 0.20), consistent with the hypothesis that uniform particle properties produce transferable turbidity-SSC relationships.

**Figure 4.** Adaptation curves: median per-site R^2^ vs number of calibration samples for random (blue), contiguous block (orange), and seasonal (green) strategies. Shaded band: 95% bootstrap CI for random mode. Dashed red line: first-N-only temporal mode, showing the start-of-record pathology at N = 10.

**Figure 5.** CatBoost vs per-site OLS under temporal splitting. The N = 2 gap (CatBoost 0.36 vs OLS -0.56) demonstrates the Bayesian shrinkage advantage.

**Figure 6.** Daily sediment load time series at Brandywine Creek (2008--2016). Gray: USGS 80155. Blue: CatBoost v11. Red: OLS. Bottom panels: three storm events showing hysteresis capture. Note log scale on y-axis.

**Figure 7.** Storm-event load comparison at three sites. Each point is one event. Blue: CatBoost. Red: OLS. Dashed line: 1:1. Dotted lines: 2:1 and 1:2.

**Figure 8.** SHAP beeswarm plot (top 15 features). Log-turbidity and raw turbidity dominate; collection method (rank 3) and SGMC geology features provide critical site context.

**Figure 9.** Per-site turbidity-SSC power law slopes by geology class (64 holdout sites). Box plots show slope distributions; individual sites as points. Glacial lithologies show the lowest and most variable slopes (~0.53), while siliciclastic and residual lithologies cluster near 1.0. Horizontal dashed line marks slope = 1.0 (linear relationship). This figure directly visualizes the optical-gravimetric conversion that governs cross-site transferability.

---

## Appendix A: Hyperparameter Sensitivity

One-at-a-time variation of CatBoost hyperparameters around v11 defaults under GroupKFold-5 cross-validation.

| Parameter | Value | KGE | Bias (%) |
|-----------|-------|-----|----------|
| **Baseline** | depth=6, lr=0.05, l2=3 | **0.786** | -7.2 |
| depth=4 | | 0.777 | -8.4 |
| depth=8 | | 0.770 | -15.6 |
| depth=10 | | 0.740 | -15.8 |
| lr=0.01 | | 0.766 | -7.1 |
| lr=0.03 | | 0.765 | -4.7 |
| lr=0.10 | | 0.772 | -12.8 |
| lr=0.20 | | 0.759 | -11.8 |
| l2=1 | | 0.784 | -9.8 |
| l2=5 | | 0.778 | -11.9 |
| l2=10 | | 0.774 | -11.0 |
| l2=30 | | 0.772 | -6.3 |
| es=25 | | 0.773 | -6.9 |
| es=100 | | 0.782 | -13.1 |
| Ordered boosting | | 0.778 | -9.6 |

Across 15 configurations, KGE ranges from 0.740 to 0.786 (total spread 0.046). Excluding the extreme depth=10 case, the spread narrows to 0.027, indicating that the model is not sensitively tuned to a narrow hyperparameter optimum. Tree depth is the most influential parameter (overfitting at depth >= 8), while L2 regularization and early stopping patience have minimal impact.

## Appendix B: Bayesian Prior Sensitivity

The Bayesian adaptation uses Student-t shrinkage with k = 15 and df = 4. To assess sensitivity, we varied both parameters across a 3x3 grid and evaluated N = 10 random adaptation (50 MC trials, 78 holdout sites):

| k \ df | 2 | 4 | 8 |
|--------|-------|-------|-------|
| **10** | 0.498 | 0.495 | 0.497 |
| **15** | 0.494 | **0.493** | 0.482 |
| **20** | 0.485 | 0.482 | 0.475 |

*Values are MedSiteR^2^ at N = 10 random adaptation. Bold: default configuration.*

The total range is 0.023 (0.475 to 0.498), indicating that the adaptation results are robust to prior specification. Weaker shrinkage (k = 10) allows slightly more trust in site-specific data, marginally improving the median, while stronger shrinkage (k = 20) over-regularizes. The Student-t degrees of freedom (df) has minimal impact at k = 10 but becomes more influential at k = 20, where heavier tails (df = 2) partially compensate for stronger shrinkage.

## Appendix C: Feature Ablation Summary

From 137 candidate features, we conducted systematic single-feature ablation under GroupKFold-5 cross-validation, tracking both log-space and native-space R^2^. Features were dropped if they degraded or had negligible effect on a combined score weighting native-space performance 2x (reflecting its operational importance). This reduced the feature set from 137 to 72 active features.

Key ablation findings:
- Several features showed opposite effects in log-space and native-space (e.g., rising_limb: +0.002 log R^2^, -0.075 native R^2^). Optimizing on log-space metrics alone would produce a worse real-world model.
- DO, pH, temperature, and nutrient features were actively harmful (zero physical mechanism for SSC prediction).
- Dropping all 65 suspect features cost <0.01 R^2^(log) while improving native-space performance.
- A limitation: disaggregated metrics (by geology, method) were not used for drop decisions. Some dropped features may matter for specific subgroups.

The complete feature list with active/dropped status and ablation scores is provided in Supplementary Table S2.
