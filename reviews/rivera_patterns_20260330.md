# Dr. Marcus Rivera — Data Patterns & Next Steps Review
**Date:** 2026-03-30
**Affiliation:** USGS Water Resources Division (ret.), 20 years sediment transport & surrogate regression

---

## Summary

I've spent time with the actual data files rather than just reasoning from the briefing summaries. Several of the patterns you've documented are solid and publishable. But I found things that concern me — some that could be red flags, some that are missed opportunities. I'll walk through each question with evidence.

---

## Question 1: What other patterns should we look for?

### Pattern A: Systematic Over-Prediction Bias — This is a Problem

The model over-predicts 74.9% of the time. Mean log-space residual is +0.317 (i.e., predictions are exp(0.317) = 1.37x too high on average). This is not a minor calibration artifact — it's a fundamental bias.

Breakdown by SSC range:
| SSC Range | % Over-Predicting | Mean Log Residual |
|---|---|---|
| 0-10 mg/L | **95.2%** | +0.735 |
| 10-50 | 76.0% | +0.377 |
| 50-200 | 76.7% | +0.314 |
| 200-1000 | 67.9% | +0.117 |
| >1000 | **29.9%** | **-0.452** |

The model is trained on log-transformed SSC and learns to predict the conditional mean in log-space. But when you exponentiate back, the geometric mean is always less than the arithmetic mean for right-skewed data. What I see here is the opposite — consistent over-prediction at low-to-moderate SSC and under-prediction at extremes. This is a **regression-to-the-mean artifact** of the pooled model: it's dragged toward the population mean (~55 mg/L), which is above most individual samples but below extremes.

This matters for regulatory applications. A model that reads 95% high at low SSC will trigger false exceedance flags. A model that reads 30% low at extreme SSC will miss real violations.

**Recommendation:** Report the median bias by SSC range in the paper. This is honest and reviewers will check for it.

### Pattern B: Spatial Autocorrelation is Weak but Present

I computed pairwise error differences by distance:
| Distance | Mean Error Diff | n pairs |
|---|---|---|
| 0-50 km | **39.1%** | 57 |
| 50-100 km | 65.5% | 39 |
| 100-200 km | 61.1% | 61 |
| 200-500 km | 54.1% | 177 |
| 500-1000 km | 57.4% | 304 |
| 1000-5000 km | 55.4% | 1797 |

Sites within 50 km have notably more similar errors (39% difference vs 55% at longer distances). The Spearman correlation between distance and error difference is weak (rho=0.068, p<0.001) but statistically significant. This suggests the model captures some regional information but there's room for a spatial random effect or regional feature.

### Pattern C: Drainage Area is a Strong Error Predictor

Drainage area correlates significantly with MAPE (rho=-0.375, p=0.004). Small watersheds (<55 km2) have mean MAPE of 121%; large basins (>13,000 km2) have MAPE of 47%. This makes physical sense: large basins integrate sediment sources and smooth the turbidity-SSC relationship, while small basins have flashier, more heterogeneous responses.

**Is drainage area in the feature set?** If not, it should be. If it is, the model may not be weighting it enough.

### Pattern D: Lithology Matters in the Direction You'd Expect

From the holdout sites (n=67 with lithology data):
- Sedimentary clastic watersheds have **lower** error (rho=-0.189) — makes sense, predictable fine-grained sources
- Igneous intrusive watersheds have **higher** error (rho=+0.259) — coarse granitic sediment produces highly variable SSC/FNU ratios
- Igneous/metamorphic undifferentiated: rho=+0.384 — same story

This confirms that geology modulates the turbidity-SSC relationship through particle size distribution, and the model partially captures this but incompletely.

### Pattern E: 65% of Sensors are "Unknown" Family

23,064 of 35,209 samples (65.5%) have `sensor_family = unknown`. If sensor_family is a feature, two-thirds of the data contribute no information from it. The model is essentially building its turbidity-SSC relationship with minimal sensor metadata for most samples. This is a known problem in USGS turbidity data — the NWIS parameter codes don't always distinguish instruments well.

### Pattern F: 391 Samples Have Extreme SSC/Turbidity Ratios (>50 or <0.01)

These are spread across 77 sites and include clearly erroneous data:
- USGS-01362330: SSC = 18,800 mg/L with turbidity = 0.2 FNU — this is a data entry error or mismatched timestamp
- USGS-02336240: Six samples on 2003-10-26 with SSC < 2 and turbidity 170-720 — sensor was reading something that wasn't sediment (likely algal bloom or dissolved organics)
- USGS-02203603: SSC 1,960 with turbidity 1.1 — bedload-dominated event where turbidity sensor missed the coarse fraction

All of these are in training, not holdout. They are teaching the model incorrect relationships.

---

## Question 2: Adaptation Hurting Extremes at N=20

### Root Cause Analysis

I confirmed the pattern and dug deeper. The key finding:

**SSC range is the strongest predictor of adaptation degradation** (rho=-0.541, p<0.001 between SSC range and delta-R2 at N=20). Sites with a wide SSC range get hurt the most.

Additionally, **sites that already have good zero-shot R2 get hurt** (rho=-0.534, p<0.001). Sites with base R2 > 0.5 see an average delta of -0.032 at N=20, while sites with base R2 <= 0.5 see +0.474.

This is textbook **adaptation overfitting to the mode**. When you calibrate with 20 samples, you're most likely drawing from the baseflow distribution (which has more mass). The adaptation adjusts the intercept/slope to minimize error on those 20 samples, which means it shifts the curve down for sites where storms produce SSC:FNU ratios much higher than baseflow. The extremes get compressed.

At N=50, it gets worse: 21 sites degraded vs 16 improved.

### Recommendation: Flow-Stratified Adaptation

Yes, absolutely. The standard approach in USGS surrogate regression is to develop separate regressions for different flow regimes (Rasmussen et al., 2009). For adaptation:

1. **Split calibration samples by discharge percentile** — e.g., Q < median vs Q >= median
2. **Apply separate adaptation factors** to each regime
3. At prediction time, route through the appropriate adaptation based on current discharge

A simpler alternative: **cap adaptation at N=10** for operational use. The data show that N=5-10 improves normal-condition R2 without degrading extremes, while N=20 causes collapse.

A third option: **weight calibration samples inversely to their frequency in the calibration set**. If you draw 18 baseflow and 2 storm samples, upweight the storm samples so they have equal influence on the adaptation.

---

## Question 3: Additional Validation Tests for Paper-Readiness

### Must-Have (a WRR reviewer will demand these):

1. **Comparison to simple OLS log-log regression per site.** For each holdout site, fit log(SSC) = a + b*log(FNU) on the calibration samples and compare R2. If the pooled ML model can't beat a site-specific OLS with 10-20 calibration samples, the value proposition collapses. (I see you have v4_ols_comparison files — make sure these are prominently reported.)

2. **Residual diagnostics.** Plot residuals vs predicted, residuals vs turbidity, residuals vs discharge. Check for heteroscedasticity patterns. The 75% over-prediction rate needs to be visible and explained.

3. **Temporal split validation.** You have data from 2003-2023. Train on pre-2015, test on post-2015. This tests whether the model generalizes to future conditions, not just unseen sites. The per-site file has `r2_temporal_at_*` columns — report these prominently.

4. **Leave-one-HUC-out.** Your LOGO is leave-one-site-out. But nearby sites share geology, climate, land use. A WRR reviewer will ask: does the model work in a region it's never seen? Leave out all HUC2=17 (Pacific NW), retrain, and test.

5. **Report KGE alongside NSE.** You have KGE in the per-site results (85% of sites KGE > 0, 50% > 0.5). This is a better metric for hydrological models and reviewers will want to see it.

### Should-Have:

6. **Prediction intervals.** Any operational user needs uncertainty bounds. Even if just bootstrap or quantile regression, you need to show that the model knows when it's uncertain.

7. **Sensitivity to turbidity sensor type.** The discrete vs continuous split (27% discrete) means the model is mixing field readings with installed sensors. Discrete turbidity is a single grab measurement; continuous is a 15-min average from an installed probe. These have different precision characteristics.

8. **Sample size sensitivity.** How does median site R2 change as you thin the training set? If you randomly drop 50% of sites, how much does performance degrade? This tells users how much more data collection would help.

---

## Question 4: Red Flags

### RED FLAG 1: 69 Samples Where SSC > 500 and Turbidity < 10

These are physically almost impossible in the same water sample at the same time. The most likely explanations:
- Mismatched timestamps (turbidity reading from a different time than the SSC sample)
- Sensor fouled or buried in sediment (reading clear water in its housing while the river is turbid)
- Bedload-dominated event (turbidity sensor in upper water column, SSC sample near bed)
- Data entry errors

The worst: USGS-01362330 with SSC = 18,800 at turbidity = 0.2. This is a ratio of 94,000:1. No natural process produces this. This is bad data that is actively harming the model.

**Action required:** Flag and remove samples with SSC:FNU ratio > 50 or < 0.01 from training. This is 391 samples across 77 sites. Re-run and compare.

### RED FLAG 2: 11 Samples Where SSC < 5 and Turbidity > 100

Same problem in reverse. Five of these are from USGS-02336240 on a single day (2003-10-26) — almost certainly a sensor malfunction (perhaps reporting in NTU while the database says FNU, or vice versa).

### RED FLAG 3: The 75% Over-Prediction Rate

A well-calibrated model should over-predict ~50% of the time. Systematic 75% over-prediction means the model has a positive bias that hasn't been corrected. At low SSC (<10 mg/L), it over-predicts 95% of the time. This is not acceptable for regulatory applications where low-SSC accuracy matters (e.g., drinking water source monitoring).

### CAUTION: 58% of Holdout Samples Have No Discharge Data

Only 41.7% of holdout predictions have discharge data. The model performs better with discharge (MAPE 99% vs 119% without). This means your reported performance is a weighted average of "with discharge" and "without discharge" cases. If the model is deployed at sites without discharge gages, performance will be worse than reported.

### CAUTION: Duplicate Timestamps

Only 4 exact duplicates found (0.01%), which is clean. But check for near-duplicates (same site, within 5 minutes) — these could be replicate samples that should be averaged, not treated as independent.

---

## Question 5: Figures for the Paper

### Tier 1 — Must Include:

1. **Observed vs Predicted scatterplot** (log-log scale, holdout data, colored by collection method). This is figure 1 in every surrogate paper. Show the 1:1 line and regression line. The offset from 1:1 will make the over-prediction bias visible.

2. **Site adaptation curve** — Median site R2 vs N_cal, showing the improvement from 0-10 and the extreme degradation at 20+. Split into two lines: one for extreme events (top 5% turbidity), one for normal. This is your most interesting finding.

3. **Error by SSC range** — Bar chart or box plot showing MAPE across SSC bins. The U-shape (highest error at both extremes of the turbidity range) is a real finding.

4. **Geographic map of holdout site performance** — Points colored by site R2 or MAPE. This shows the spatial pattern and makes reviewers comfortable that you have national coverage.

5. **SSC/FNU ratio by collection method** — Box plots showing the auto_point vs depth_integrated vs grab ratio distributions. The p90 difference (13.1 for auto_point vs 4.6 for depth_integrated) is a publishable finding about bedload representation.

### Tier 2 — Strongly Recommended:

6. **Bias by SSC range** — Show the 95% over-prediction at low SSC and 30% over-prediction at high SSC. This is honest reporting and will impress reviewers.

7. **Weekend/weekday performance split** — This is genuinely novel. The finding that the model performs better on storm events than baseflow is counterintuitive and publishable.

8. **Drainage area vs MAPE** — Shows the physical control on model performance.

### Tier 3 — Supplementary:

9. Temporal split results
10. KGE distribution across sites
11. Lithology correlation table

---

## Question 6: What Are We Missing?

### Missing Analysis 1: Hysteresis Within Storm Events

You have 213 site-days with 10+ samples. For these ISCO burst captures, compute the clockwise vs counterclockwise hysteresis index (Williams, 1989). Sites with consistent clockwise hysteresis (SSC peaks before turbidity peaks) have nearby/easily mobilized sediment. Sites with counterclockwise hysteresis have distal sources. The model should perform differently on these two types, and this would be a novel finding for a ML paper.

### Missing Analysis 2: The Auto-Point Bedload Problem is Underexplored

Your briefing notes that auto_point reads 35% more SSC per unit turbidity than grab. But the p90 ratio is 13.1 for auto_point vs 4.2 for grab — that's 3x at the tails, not 35%. The auto_point distribution has a long right tail because ISCO samplers positioned near the streambed capture bedload events that turbidity sensors (in the water column) don't see.

This is not a bug — it's a physics problem. The model is being asked to predict total SSC from a measurement that only sees suspended load. At high transport rates, bedload can be 20-60% of total load. You should:
- Quantify what fraction of the variance in model error is explained by collection method
- Consider reporting separate performance for depth_integrated (which is the "gold standard" SSC method) vs auto_point

### Missing Analysis 3: Sensor Offset as a Drift Indicator

The `sensor_offset` column ranges from -617 to +5521 FNU, with a mean of -0.68. The extreme values (+5521!) suggest either sensor drift or calibration differences. The `days_since_last_visit` column shows 20.7% of samples are from sensors that haven't been serviced in 180+ days. In my USGS experience, turbidity sensors drift significantly after 60-90 days without cleaning. You should test whether `days_since_last_visit > 90` is associated with higher error.

### Missing Analysis 4: Retransformation Bias Correction

If the model operates in log-space (which it appears to from the `ssc_log1p` column), you need a bias correction factor (BCF) when back-transforming. The Duan (1983) smearing estimator or the Snowdon (1986) ratio estimator are standard. The systematic 75% over-prediction at low SSC suggests either the BCF is too aggressive or isn't being applied correctly. This needs investigation before publication.

### Missing Analysis 5: Comparison to National Sediment Models

How does this compare to Zhi et al.'s LSTM approach? To the USGS LOADEST models? To the simple power-law T = a*FNU^b approach that most Water Science Centers use? You need at least one external benchmark beyond "our model at N=0 vs N=10" to establish value.

### Missing Analysis 6: Temporal Stationarity

125 of 254 training sites show significant SSC trends over time. This means the turbidity-SSC relationship is non-stationary at half your sites. A model trained on 2003-2023 data may not be valid for 2025 predictions if land use, climate, or reservoir operations have shifted the relationship. You should test whether removing time-trending sites changes model performance.

---

## Quantitative Summary of Key Findings

| Finding | Metric | Value |
|---|---|---|
| Over-prediction rate (all) | % samples over-predicted | 74.9% |
| Over-prediction rate (SSC < 10) | % samples over-predicted | 95.2% |
| Under-prediction rate (SSC > 1000) | % samples under-predicted | 70.1% |
| Spatial autocorrelation (< 50 km) | Mean pairwise error diff | 39.1% vs 55.4% at 1000+ km |
| Drainage area effect | Spearman rho with MAPE | -0.375, p=0.004 |
| Anomalous training samples | Ratio > 50 or < 0.01 | 391 samples, 77 sites |
| Adaptation collapse driver | SSC range vs delta-R2 at N=20 | rho=-0.541, p<0.001 |
| Good-site adaptation harm | Base R2 > 0.5 mean delta at N=20 | -0.032 |
| Bad-site adaptation help | Base R2 <= 0.5 mean delta at N=20 | +0.474 |
| Discharge data availability (holdout) | % with Q | 41.7% |
| Unknown sensor family | % of all samples | 65.5% |

---

## Bottom Line

The model shows genuine skill for a zero-shot national pooled surrogate. The Spearman rho of 0.92 means the rank-ordering is excellent even when the magnitude is off. The adaptation curve up to N=10 is the real selling point. But the 75% over-prediction rate and the 391 anomalous training samples are problems that need to be fixed before submission. Clean the data, investigate the bias, and add the flow-stratified adaptation. Those three things will move this from "interesting ML exercise" to "tool that practitioners would actually use."

— Marcus Rivera
