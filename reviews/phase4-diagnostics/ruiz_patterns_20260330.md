# Dr. Catherine Ruiz -- Data Patterns Review (Updated with Data Analysis)
## 2026-03-30 | Sediment Transport Perspective

I read the panel briefing, then computed everything myself from the raw data files. Every number cited below comes from my own analysis of turbidity_ssc_paired.parquet (35,209 samples), v9_final_per_reading.parquet (5,847 holdout predictions), site_turb_ssc_params.parquet (304 sites), and watershed_lithology_pct.parquet (355 sites). Where I disagree with the briefing, I say so and show why.

---

## Question 1: What other patterns should we look for?

### 1a. Broken power laws are widespread and systematic

I split each site's log(turb)-log(SSC) rating curve at its median turbidity and fit separate slopes to the low and high halves. Across 219 sites with 30+ samples:

| Regime | Mean slope | Std |
|--------|-----------|-----|
| Low turbidity | 0.821 | -- |
| High turbidity | 0.896 | -- |
| Paired t-test | t = 1.96 | p = 0.051 |

50.2% of sites steepen at high turbidity (slope difference > 0.1) and 32.4% flatten. The most extreme cases show slope differences exceeding 1.5:

- USGS-12510500: low slope = -0.20, high slope = 1.38 (steepens dramatically)
- USGS-034336392: low slope = 1.51, high slope = -0.04 (saturates completely)
- USGS-02203900: low slope = 2.64, high slope = 1.15 (flattens under load)

The physical mechanism is clear: at low flows, fine clay and dissolved organic matter dominate the turbidity signal -- you get lots of light scattering per unit mass. At high flows, coarser particles are entrained that add mass without proportional optical scattering, steepening the power law. Sites that flatten at high turbidity likely have sensor saturation or a finite coarse sediment supply that caps SSC while turbidity keeps climbing.

**This is a publishable finding.** The standard practice of fitting a single power law to the turbidity-SSC relationship misrepresents at least half the sites in this dataset.

### 1b. Between-site ratio variance dwarfs within-site variance

I computed the SSC/turbidity ratio (SSC / max(turbidity, 1 FNU)) for every sample and calculated the coefficient of variation both across and within sites:

- Between-site CV of mean ratio: **4.37**
- Average within-site CV: **1.35**

This 3.2x ratio tells you the fundamental truth about this problem: what geology, land use, and channel morphology put into the water matters more than what any individual storm does. This is why a pooled model without site information has a hard ceiling, and why even a crude site-adaptation mechanism shows large improvements.

### 1c. Rising-limb samples carry 16% more sediment per unit turbidity

| Hydrograph position | Median SSC/turb ratio | n |
|---------------------|----------------------|---|
| Rising limb | 2.05 | 8,448 |
| Falling/baseflow | 1.76 | 8,979 |

The rising limb entrains fresh, unsorted bed and bank material including coarse fractions. The falling limb is dominated by fines that remained in suspension after the coarse fraction deposited. This is textbook sediment transport physics, and the data confirms it cleanly. The model should be using rising_limb more aggressively -- if it is not already a top feature, investigate why.

### 1d. Summer has the highest SSC/turbidity ratio

| Season | Median ratio | n |
|--------|-------------|---|
| Winter | 1.73 | 7,701 |
| Spring | 1.79 | 10,898 |
| Summer | **1.94** | 8,433 |
| Fall | 1.82 | 8,177 |

Summer convective storms hit dry, unconsolidated surfaces and mobilize coarse material in flashy, short-duration events. Winter and spring rain-on-snow or prolonged frontal events produce more dilute, fine-sediment-dominated flows. This 12% seasonal swing is real and physically meaningful.

### 1e. Discharge quintile analysis shows a U-shaped ratio pattern

| Discharge quintile | Range (cfs) | Median ratio |
|-------------------|-------------|-------------|
| Q1 (lowest) | 0-20 | 1.82 |
| Q2 | 20-95 | 2.00 |
| Q3 | 95-384 | 1.89 |
| Q4 | 384-2119 | 1.89 |
| Q5 (highest) | 2119-100000 | 2.09 |

The highest ratios occur at both low flows (Q2) and very high flows (Q5). At Q2, you have slightly elevated turbidity from local disturbance entraining coarse material from the bed. At Q5, you are mobilizing the full bed and bank sediment population. The middle ranges are dominated by fine washload. This nonlinear relationship complicates any simple turbidity-to-SSC mapping.

### 1f. ISCO burst hysteresis is measurable but noisy

I analyzed 119 burst events where I could identify a turbidity peak with at least 3 samples on each limb:

| Direction | Count | Percentage |
|-----------|-------|-----------|
| Clockwise (HI > 0.1) | 47 | 39.5% |
| Counter-clockwise (HI < -0.1) | 29 | 24.4% |
| Linear (\|HI\| < 0.1) | 43 | 36.1% |

The median hysteresis index is +0.048 (slight clockwise tendency). The Wilcoxon test for rising vs falling ratio is not significant (p = 0.13), meaning the aggregate signal is weak, but individual sites show consistent patterns:

- **Consistent clockwise sites** (proximal sediment source): USGS-16274100 (HI = 0.33, n=3), USGS-16247100 (HI = 0.29, n=3), USGS-14179000 (HI = 0.16, n=7)
- **Consistent counter-clockwise sites** (distal source): USGS-01589000 (HI = -0.90, n=3), USGS-16210500 (HI = -0.34, n=3)

Hysteresis index does not significantly correlate with storm size (rho = 0.13 vs peak turbidity, p = 0.15). This suggests the dominant sediment pathway is a site property, not an event property -- consistent with the between-site variance dominance in pattern 1b.

### 1g. Extreme-ratio sites reveal data quality issues

USGS-01362330 has a mean SSC/turb ratio of **455**. Examining the raw data: 51 samples, with many turbidity readings pinned at 0.2 FNU (the sensor reporting floor). The actual SSC at those readings is 0.5-6 mg/L, so the real ratio at baseflow is reasonable. But a few high-SSC readings at moderate turbidity inflate the mean catastrophically. This site has a sensor floor problem, not a sediment transport anomaly.

USGS-12186000 (ratio = 48) is 68% auto_point samples with SSC up to 12,200 mg/L. This is likely a glacial stream where coarse glacial flour dominates -- very high mass-per-scatter, which is the physical definition of coarse suspended sediment.

**57 readings have turbidity exactly 0 with median SSC = 2 mg/L and max SSC = 265 mg/L.** The 265 mg/L at zero turbidity is physically impossible for mineral sediment. These are sensor failures or sample contamination.

---

## Question 2: Why does adaptation hurt extremes at N=20?

I ran a Monte Carlo simulation: drawing 20 random samples from each site with 40+ observations (100 draws per site):

- **36% of 20-sample draws contain zero storm samples** (turbidity > 200 FNU)
- Only 40% of draws contain 3+ storm samples
- The typical site has 67.3% of its data below 50 FNU and only 5.8% above 200 FNU

The mechanism: at N=20, the calibration set is overwhelmingly baseflow -- fine particles, DOM, algae contaminating the turbidity signal. The Bayesian adaptation learns to shift predictions toward the lower SSC/turb ratio that characterizes these conditions. Then a storm arrives. The sediment population switches completely -- coarser particles, higher ratio, different optical properties. The adapted model fights the storm signal because it was trained on baseflow physics.

This is the **sediment population switching problem**. It is not a statistical artifact. During baseflow, "turbidity" is partly not sediment at all (DOM, algae). During storms, it is mostly real mineral sediment. These are two distinct optical regimes sharing one sensor.

### My recommended fixes (in order of preference):

1. **Minimum storm count guard.** If the calibration set contains fewer than 2 samples above the 75th percentile of the site's turbidity range, do not apply adaptation to predictions in that range -- fall back to the pooled model. Simple, conservative, easy to implement and explain.

2. **Turbidity-weighted adaptation.** Weight calibration samples by their turbidity rank (or log-turbidity) in the Bayesian update. This prevents the 95% baseflow samples from drowning the 5% storm signal.

3. **Conditional adaptation.** Adapt the intercept (baseline SSC level) freely, but attenuate or freeze the slope correction when predicting above the calibration set's turbidity range. The intercept captures site-specific factors (particle mineralogy, background DOM). The slope is more universal.

4. **Two-tier adaptation.** Maintain separate bias corrections for event (Q > 2x median or turb > site 75th percentile) vs non-event. Physically correct but requires enough calibration data in each tier to be useful, which is the whole problem.

For the paper, I would implement option 1, present the Monte Carlo analysis as the explanation, and show the fix resolves the extreme-event collapse.

---

## Question 3: What validation tests does this need for paper-readiness?

### MUST-HAVE (a WRR reviewer will reject without these):

**A. Address the overprediction bias.**
The model overpredicts 74.9% of holdout readings. The median predicted/true ratio is **1.42x**. By SSC level:

| True SSC range | n | Median pred/true | % overpredicted |
|---------------|---|-----------------|----------------|
| < 10 mg/L | 987 | 2.45 | 95.4% |
| 10-30 | 1,127 | 1.52 | 80.0% |
| 30-100 | 1,421 | 1.44 | 73.7% |
| 100-300 | 1,098 | 1.39 | 77.0% |
| 300-1000 | 818 | 1.13 | 63.8% |
| > 1000 | 396 | 0.72 | 30.3% |

At the site level, 90% of sites with 10+ predictions show >60% overprediction. This is textbook retransformation bias (Jensen's inequality from working in log or sqrt space). A WRR reviewer will identify this in the first read-through. Options: Snowdon BCF, Duan smearing, quantile regression targeting the native-space median, or reporting the bias explicitly with a correction factor.

**B. Comparison with site-specific rating curves.** For every site with 30+ calibration samples, how does the pooled model compare to a simple local log(SSC) = a + b*log(turb) OLS fit? This is the baseline that matters. Report the fraction of sites where the pooled model wins.

**C. Residual analysis.** Q-Q plots, residuals vs predicted, residuals vs key features. Show the distributional assumptions hold (or explain why they don't).

**D. Nondetect handling.** 39 nondetect samples in the holdout have **519% median error** vs 55% for detected samples. These must be flagged or excluded from reported metrics. Leaving them in without comment inflates MAPE and confuses reviewers.

**E. Independence confirmation.** Confirm that ISCO burst samples from the same storm event never appear in both training and validation for a given site. Since you split by site_id, this should be fine, but state it explicitly.

### SHOULD-HAVE (strengthens the paper):

**F. Discharge-stratified error analysis.** Report errors at Q10, Q50, Q90. Sediment loads are dominated by the high-flow tail. Good Q50 performance is irrelevant if Q10 performance is poor.

**G. Sediment load comparison.** For 10-20 sites with dense temporal coverage, compute annual loads from observed vs predicted SSC and report the percent difference. This is the metric practitioners care about.

**H. Temporal hold-out test.** Train on pre-2018, test on post-2018. If the 89 sites with increasing SSC/turb ratios represent real trends (not sensor drift), temporal performance should degrade for those sites.

---

## Question 4: Red flags in the patterns

### RED FLAG 1 (CRITICAL): Systematic 1.42x overprediction

This is the most serious issue I found. It is not a few bad sites -- 90% of sites with 10+ predictions overshoot more often than not. The pattern is unmistakable: massive overprediction at low SSC (2.45x below 10 mg/L), tapering through moderate values, then reversing to underprediction above 1000 mg/L (0.72x). This is the signature of retransformation bias from a model trained in transformed space.

The median log(pred/true) = 0.348, meaning the model predicts exp(0.348) = **1.42x** the true value at the geometric median. This single number should alarm you. Every metric you have reported is affected by this bias.

**This must be fixed or prominently documented before submission.**

### RED FLAG 2 (HIGH): Nondetects poison the metrics

39 nondetect samples have 519% median error. If these are coded as the detection limit (e.g., SSC = 1 mg/L), the model will always overshoot them by a large factor. These should be censored from MAPE/R-squared calculations and reported separately.

### RED FLAG 3 (HIGH): Sensor floor readings

919 readings (2.6%) have turbidity below 1 FNU. Of these, 57 are exactly 0 FNU. While the median SSC at turb < 1 is only 2 mg/L (reasonable), there are 22 readings with turb < 1 and SSC > 50 mg/L. The extreme case is SSC = 265 at turb = 0 -- this is physically impossible for mineral sediment and represents either sensor failure or sample contamination. These readings add noise that the model cannot resolve.

### RED FLAG 4 (MEDIUM): Only 3 supply-limited sites is suspicious

179 transport-limited vs 3 supply-limited sites is an implausibly one-sided ratio. Many headwater streams, especially in the intermountain West, are genuinely supply-limited -- sediment availability constrains transport during late summer and fall. I suspect this classification uses the overall Q-SSC correlation, which averages across seasons. A site can be supply-limited in August (exhausted bank sediment) but transport-limited in April (snowmelt mobilizing everything), and the net correlation looks positive. The paper should acknowledge this is likely a sampling bias (USGS network favoring larger, transport-limited rivers) and/or an artifact of annual-scale analysis.

### RED FLAG 5 (MEDIUM): "All rho > 0.3" is not reassuring

A rho of 0.3 between turbidity and SSC means turbidity explains roughly 9% of SSC variance at that site. At those sites, the primary model input is nearly useless. How many sites have rho < 0.5? These are the sites where DOM, algae, and instrument differences dominate the turbidity signal. They deserve explicit flagging.

### CAUTION: Long-term ratio trends may be sensor artifacts

I found 126 of 313 sites with statistically significant trends in SSC/turbidity ratio over time. But 89 show increasing ratios (apparent coarsening) and only 37 show decreasing. This asymmetry is suspicious -- real geomorphic processes should not preferentially coarsen sediment at 2.4x the rate they fine it. More likely explanations: sensor technology changes (older sensors respond differently to the same particle population), drift in turbidity calibration, or changes in the USGS sampling protocol. Cross-reference with sensor_family metadata and days_since_last_visit before interpreting these as real.

---

## Question 5: Figures for the paper

### Tier 1 -- Must include:

1. **Overprediction bias diagnostic.** Predicted vs observed in native space (log-log axes), colored by SSC magnitude. Show the systematic upward displacement at low SSC and the crossover to underprediction above ~1000 mg/L. Include the 1:1 line and the empirical bias curve. This is the figure that preempts reviewer criticism -- you show you know about the bias.

2. **Broken power law figure.** A 2x3 panel showing representative sites: one that steepens at high turbidity (e.g., USGS-12510500), one that flattens (e.g., USGS-034336392), one that is linear, and annotate with the physical interpretation. Overlay the single power-law fit to demonstrate its inadequacy. This is a novel contribution.

3. **Adaptation performance vs N, stratified by regime.** The x-axis is N (0, 1, 5, 10, 20), y-axis is R-squared, with separate lines for extreme (>410 FNU) and normal (<410 FNU) conditions. Annotate the N=20 collapse with the Monte Carlo result: "36% of N=20 calibration sets contain zero storm samples."

4. **SSC/turbidity ratio by collection method.** Violin plots showing auto_point (2.10), depth_integrated (1.71), and grab (1.56). Annotate with the physical explanation (Rouse profile, ISCO intake position near bed captures coarser fraction). This quantifies a bias that practitioners know about qualitatively but have never seen at this scale.

5. **Residual map** (once you have site coordinates). Color by median signed error. If there is spatial structure, it reveals missing regional factors. If there is not, it demonstrates the model generalizes geographically.

### Tier 2 -- Should include:

6. **Geology-slope relationship.** Metamorphic-undifferentiated watersheds have steeper turbidity-SSC slopes (rho = +0.17, p = 0.005). Carbonate and clastic sedimentary watersheds have flatter slopes. Box plots of slope grouped by dominant lithology.

7. **Error by physical condition.** Multi-panel showing median percent error by: conductance quartile (48.9% at 100-300 uS/cm vs 57.7% at >600), turbidity stability (66.1% for very stable vs 49.9% for highly variable), and pH range (38.7% acidic vs 65.5% high alkaline).

8. **Hysteresis examples from ISCO burst data.** Two representative storms (one clockwise, one counter-clockwise) showing SSC and turbidity on the same time axis, with the SSC/turb ratio plotted below.

### Do NOT include:

- Time-of-day or weekend/weekday patterns. These are fully explained by the collection method confound and add nothing scientific.
- Seasonal SSC by itself (well-known). Include the seasonal ratio variation instead, which is more novel.

---

## Question 6: What are you missing?

### 6a. The overprediction bias undermines everything else you have reported

This is the single most important finding from my analysis, and I want to make sure it does not get buried in a list. **The model overpredicts 75% of holdout readings by a median factor of 1.42x.** At SSC < 10 mg/L, it overpredicts by 2.45x. This is not a minor calibration issue. Every MAPE, R-squared, and NSE value you have reported is distorted by this bias. Any load estimates derived from this model will systematically overshoot unless corrected.

MAPE itself is asymmetric under directional bias: overpredicting 100 mg/L on a 50 mg/L sample gives 200% error, while underpredicting 100 mg/L on a 200 mg/L sample gives 50% error. With 75% overprediction, your MAPE is inflated at low SSC and deflated at high SSC. Consider reporting symmetric metrics (e.g., median absolute log-ratio error) alongside MAPE.

### 6b. Particle size distribution is the fundamental missing variable

Everything in this dataset -- the broken power laws, the collection method ratio differences, the rising-limb effect, the geology correlations, the hysteresis -- traces to one variable: particle size distribution. Turbidity responds to optical cross-section (proportional to particle surface area). SSC is mass. A given mass of clay has orders of magnitude more surface area than the same mass of silt. Until you have a particle-size proxy in the feature set, the model faces a hard physics ceiling.

Possible proxies you could add without new field data:
- Percent sand from USGS parameter 70331 (if available for your sites)
- D50 estimates from the published Zenodo map
- The site's own historical SSC/turb ratio (computed from calibration data) -- effectively a learned particle-size index
- SGMC lithology fractions (you already have these, and they correlate with slope at p < 0.01 for metamorphic and sedimentary classes)

### 6c. The conductance signal deserves more investigation

Model error varies meaningfully with conductance:

| SC range | Median % error | Median SSC |
|----------|---------------|-----------|
| < 100 uS/cm | 55.8% | 115 mg/L |
| 100-300 | 48.9% | 64 |
| 300-600 | 54.0% | 41 |
| > 600 | 57.7% | 18 |

The best performance at SC 100-300 corresponds to "normal" runoff conditions. High SC (>600) indicates baseflow where turbidity is dominated by DOM, not mineral sediment -- the model struggles because the turbidity signal means something different. Very low SC (<100) indicates rapid surface runoff (fresh rainwater) where you get high SSC but the water chemistry gives the model fewer cues.

This suggests the SC_turb_interaction feature is doing real work, but may not be capturing the full nonlinearity. The model might benefit from knowing whether SC and turbidity are moving in the same direction (both rising = unusual, possible construction/disturbance) vs opposite directions (normal storm pattern).

### 6d. Sensor family effects are underexplored because 70% of the holdout is "unknown"

| Sensor family | n | Median % error |
|--------------|---|---------------|
| unknown | 4,089 | 58.0% |
| ysi_6series | 1,565 | 51.0% |
| exo | 189 | 56.2% |

The YSI 6-series outperforms by 7 percentage points, but you cannot meaningfully compare because the "unknown" bucket is enormous and heterogeneous. Different sensor families have different spectral responses, scattering geometries, and turbidity units. The 6-series uses a 90-degree detector at ~860 nm; the EXO uses a different geometry. These physical differences mean the same suspension produces different turbidity readings. If sensor_family is not already a model feature, it should be. If it is, the "unknown" category is limiting its utility.

### 6e. Turbidity stability is informative -- stable readings have the worst errors

| Turbidity 1hr variability | Median % error |
|--------------------------|---------------|
| Very stable (std < 0.5) | 66.1% |
| Stable (0.5-3) | 51.7% |
| Moderate (3-15) | 58.7% |
| Highly variable (>15) | 49.9% |

The 16 percentage-point spread between stable and variable turbidity is striking. Stable turbidity means baseflow -- the regime where DOM, algae, and biofouling contaminate the optical signal and turbidity is a poor proxy for mineral sediment. Variable turbidity means an active hydrologic event where the turbidity signal is dominated by real particle transport. **The model performs best when the physics are most straightforward (active sediment transport) and worst when the turbidity signal is ambiguous (quiescent conditions).**

This is a key finding for the paper. It explains why "extreme events are easier" and gives a physical mechanism: turbidity variability is a proxy for whether the turbidity signal is sediment-dominated.

### 6f. pH is doing something real

| pH range | n | Median % error |
|----------|---|---------------|
| Acidic (<6.5) | 46 | 38.7% |
| Neutral (6.5-7.5) | 326 | 59.3% |
| Alkaline (7.5-8.5) | 554 | 56.9% |
| High alkaline (>8.5) | 31 | 65.5% |

The 27 percentage-point spread from acidic to high alkaline is large. Acidic waters tend to be organic-poor (less DOM interference with turbidity), while high-alkaline waters are often productive, mineral-rich systems where algae and calcite precipitation confuse the turbidity sensor. This is why the ablation study found ph_instant was "very helpful" -- it is disambiguating the turbidity signal.

### 6g. Match gap is NOT a problem

I checked: rho between match_gap_seconds and prediction error is 0.007 (p = 0.61). The temporal alignment of turbidity readings to SSC samples is not introducing systematic error. This is reassuring and worth a sentence in the methods section.

### 6h. Spatial autocorrelation of residuals needs testing

I did not have site coordinates to compute Moran's I, but this is critical. If nearby sites have correlated errors, the LOGO CV is optimistic because neighboring training sites leak information about the held-out site's sediment regime. You need to either test this or argue convincingly that your site selection is geographically diverse enough that spatial leakage is minimal.

---

## Summary of Priorities

| Priority | Issue | Impact | Action |
|----------|-------|--------|--------|
| CRITICAL | 1.42x overprediction bias | All metrics distorted | Apply BCF or document prominently |
| CRITICAL | Nondetects (519% error, n=39) | Inflates reported MAPE | Censor from metrics |
| HIGH | Adaptation kills extremes at N=20 | Model fails when it matters most | Implement min-storm-count guard |
| HIGH | Broken power laws undocumented | Novel finding for the field | Include as key result with figure |
| HIGH | Turbidity stability predicts error | Explains "extremes are easier" | Report as a finding |
| MEDIUM | Sensor floor (turb=0, SSC=265) | Data quality noise | Flag/exclude turb < 0.5 FNU |
| MEDIUM | Long-term ratio trends (n=126 sites) | May be sensor drift, not real | Cross-reference with sensor metadata |
| MEDIUM | Spatial autocorrelation untested | CV may be optimistic | Compute Moran's I on site residuals |
| LOW | Particle size proxy missing | Hard physics ceiling | Discuss as fundamental limitation |
| LOW | pH effect unexplained in text | Reviewer may question | One paragraph on DOM/calcite mechanism |

---

*Dr. Catherine Ruiz*
*Sediment Transport Research, 15 years*
*All analyses performed directly on project data files. Monte Carlo: 100 draws per site, seed=42. Hysteresis: rising/falling limb SSC/turb ratio comparison with Wilcoxon test. Power law splits: OLS on log-transformed data, low vs high halves at median turbidity.*
