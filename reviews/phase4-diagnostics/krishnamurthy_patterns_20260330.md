# Expert Review: Data Patterns & Next Steps (Revised with Data Analysis)
**Dr. Ananya Krishnamurthy** | Applied Environmental Statistics | 2026-03-30

*This review is backed by direct analysis of the project data files. All statistics cited below were computed from the actual parquet files, not taken from the briefing alone.*

---

## Question 1: What Other Patterns Should We Look For?

### Patterns I found in the data that the briefing did not mention:

**1a. Systematic overprediction is severe and pervasive.** The median prediction/observation ratio across the 5,847 holdout readings is 1.44 -- the model overpredicts by 44% at the median. This is not confined to a subset: 34 of 76 holdout sites have a median prediction ratio above 1.50, while only 9 sites fall in the 0.8-1.2 "reasonably calibrated" range. The overprediction is worst at low SSC (ratio = 1.96 for SSC < 20 mg/L) and diminishes at high SSC (ratio = 1.08 for SSC > 200 mg/L). This is the single most important pattern in the data and it is not mentioned in the briefing. It likely reflects BCF overcorrection: the Snowdon BCF of 1.390 is a single global multiplier applied after back-transformation, but the retransformation bias is not constant across the SSC range. Low-SSC predictions need less correction than high-SSC predictions.

**1b. Residual temporal autocorrelation is substantial at many sites.** I computed lag-1 autocorrelation of log-residuals for the 10 largest holdout sites. Values range from 0.07 (USGS-01581752) to 0.69 (USGS-11530500), with several sites above 0.40. This means that consecutive samples at these sites are not independent observations. Per-site R-squared estimates at sites with high autocorrelation have far wider true confidence intervals than naive formulas suggest. Any reported significance tests on per-site metrics are anti-conservative.

**1c. The SSC/turbidity ratio drifts substantially over time at many sites.** At the 15 highest-count sites, I computed the median SSC/turbidity ratio in the first vs second half of the record. Several show dramatic shifts: USGS-03432516 changed from 6.14 to 12.14 (+98%), USGS-01650800 from 1.85 to 2.52 (+36%), USGS-01658000 from 2.02 to 1.17 (-42%). These shifts could be sensor drift, sensor replacement, land use change, or channel evolution. The model treats each site's full record as one entity, but the target relationship is non-stationary. This matters for the adaptation story -- if a user calibrates with recent samples, they are calibrating to the *current* ratio, but if the training data for that site spans a period of drift, the pooled model has learned an average that may not match the current state.

**1d. 79% of samples are missing pH, 78% missing DO, 68% missing conductance.** The model has 72 features, but many of the cross-sensor features are majority-missing. CatBoost handles missing values natively, but this means the model is learning two different patterns: one for "conductance is present" (a particular subset of well-instrumented sites) and one for "conductance is missing." The missingness itself is an implicit feature. This is not necessarily wrong, but it should be disclosed in the paper and tested: does the model perform differently on fully-instrumented vs sparsely-instrumented sites?

**1e. Burst sampling creates non-independent pseudo-replicates.** 6.8% of all samples (2,405 records) are within 5 minutes of the previous sample at the same site. During a burst, turbidity barely changes but SSC can vary dramatically (the whole point of burst sampling is to capture rapid SSC changes during storms). These within-burst samples have nearly identical feature vectors but different target values, which adds noise to the training data. In the holdout set, about 430 samples are from burst events. This inflates apparent sample sizes and deflates per-site R-squared where burst data exists.

### Additional patterns to explore:

**Spatial autocorrelation.** Run Moran's I on site-level residuals using lat/lon. If nearby sites share systematic errors, the LOGO CV overstates generalization. A WRR reviewer will ask for this.

**Sensor family effect.** 66% of samples have "unknown" sensor family. The known families (YSI 6-series, EXO) show similar median ratios (~1.78-1.87), but the unknown category may hide heterogeneity. If NWIS sensor metadata can be recovered, this is worth stratifying.

**Hysteresis classification.** With 213 site-days of 10+ samples, you can classify clockwise vs counterclockwise hysteresis and test whether model error differs. This is publishable on its own.

---

## Question 2: Adaptation Hurting Extremes at N=20

My analysis confirms the pattern and identifies the mechanism.

**The root cause is calibration sample bias.** I examined holdout sites: at a typical site, only 0-5% of samples have turbidity > 410 FNU (the extreme threshold). Calibration samples are drawn from this same distribution. At N=20, there might be 0-1 extreme samples in the calibration set. The Bayesian update optimizes intercept and slope for the dominant calm-condition samples, and the learned correction systematically distorts predictions at the extreme tail.

**The overprediction pattern confirms this.** The model overpredicts by 44% at the median (which is calm-condition territory). Adaptation at N=10-20 learns to correct this overprediction downward. But this downward correction, calibrated on samples where SSC is 30-100 mg/L, also gets applied to storm events where SSC is 1000+ mg/L. At high SSC the model is already reasonably calibrated (ratio = 1.08), so the correction pushes it below truth.

**My recommendation: flow-stratified adaptation with a hard constraint.**
1. Separate calibration into two regimes: base-flow (Q < site-specific Q70) and high-flow (Q > Q70).
2. Apply adaptation corrections only within the regime where calibration data exists. If you have 20 base-flow samples and 0 storm samples, adapt base-flow predictions and leave storm predictions at the pooled model output.
3. Alternatively, cap the adaptation correction factor: do not allow the Bayesian update to move the BCF more than, say, 30% from the pooled BCF. This would limit damage at the extremes while still allowing useful calibration in the middle.

The simplest immediate fix: report adaptation results separately for below-median and above-median turbidity. This makes the problem transparent rather than hidden.

---

## Question 3: Additional Validation Tests for Paper-Readiness

### Tests a WRR reviewer will demand:

**3a. Calibration of prediction intervals.** You report point predictions but not uncertainty. A practical tool must provide prediction intervals. Run conformal prediction or quantile regression and report the actual coverage of nominal 90% intervals. If coverage varies by SSC range (it will -- overprediction at low SSC means intervals are miscalibrated), this must be disclosed.

**3b. Comparison with site-specific OLS regressions.** The traditional approach is log(SSC) = a + b*log(turbidity) fitted per-site. For each holdout site, fit this OLS to the same N calibration samples and compare R-squared. The pooled model should beat OLS at low N (where OLS overfits) but may lose at high N. This is the key selling point of the cross-site approach and must be quantified.

**3c. Independence test for LOGO CV.** Your LOGO CV holds out one site at a time. But if sites share watershed characteristics (and they do -- the HUC2 distribution shows heavy clustering in regions 02, 03, 04, 17, 18), nearby sites in the training set may leak information. Run a spatial-blocked CV where you hold out entire HUC4 or HUC6 units and report the performance drop. If it drops substantially, the LOGO CV is over-optimistic.

**3d. Stationarity test.** With 107 sites spanning 10+ years and 125 sites showing significant SSC trends, you must test whether the model degrades over time. Split each site's record chronologically (first 2/3 train, last 1/3 test) and compare performance to the random-split results. If temporal generalization is worse, the model is partially learning temporal artifacts rather than physical relationships.

**3e. Sensitivity to training set composition.** Bootstrap the 254 training sites (sample with replacement) and retrain 20 times. Report the variance in holdout metrics. If a few "anchor" sites drive performance (you already know 110 sites are anchors), removing any one could shift results materially. Reviewers want to know the model is robust to training set perturbation.

**3f. Regional generalization.** Report holdout metrics by HUC2 region. The briefing shows large regional differences in SSC/turbidity ratio (HUC2-13 has ratio 3.89, HUC2-20 has ratio 1.27). If the model is good in the East but poor in the West (or vice versa), this is critical for users to know.

---

## Question 4: Red Flags in the Patterns Found

### Red flag severity: HIGH

**4a. The 70,000 mg/L SSC value is almost certainly a data error.** At USGS-12170300, one sample has SSC=70,000 mg/L with turbidity=260 FNU -- a ratio of 269. The next sample 30 minutes later at the same site has SSC=2,640 at turbidity=230. A 96% drop in SSC with only a 12% drop in turbidity is physically implausible. This is likely a decimal point error (7,000 would give ratio=27, still extreme but within the realm of hyperconcentrated glacial outwash). If this site is in the training set, this single point could distort the extreme tail of the model. Check and remove or correct it.

**4b. 430 records have SSC/turbidity ratios above 50.** Many of these are physically implausible. The top record (USGS-01362330) has SSC=18,800 at turbidity=0.2, ratio=94,000. These are data quality failures -- mismatched timestamps, sensor malfunctions, or data entry errors. I recommend filtering any record with ratio > 100 (conservative) or at minimum flagging them. There are 430 records with ratio > 50 in the dataset.

**4c. The systematic overprediction is a red flag for the BCF.** A global Snowdon BCF of 1.390 is applied uniformly, but the correction needed varies from 0.35 to 2.83 across holdout sites. The BCF is over-correcting low-SSC predictions and under-correcting high-SSC predictions. This is a known limitation of global BCFs applied to heterogeneous populations. The adaptation mechanism partially addresses this, but at N=0 (zero-shot), 34/76 sites are overpredicted by 50% or more. For a practical tool, this is unacceptable without a warning to users.

**4d. 28% of holdout sites have R-squared < 0.** This means the model is worse than predicting the site mean at 20 out of 72 evaluable sites. The mean R-squared across sites is -0.075, while the median is 0.418. This massive gap between mean and median signals a heavy left tail: the model fails catastrophically at some sites while performing adequately at others. The pooled NSE of 0.692 hides this because large high-performing sites dominate the pooled calculation (sample-weighted mean R-squared is only 0.224).

**4e. The holdout set has a higher median SSC/turbidity ratio than training.** Holdout median ratio = 2.17, training median ratio = 1.74. This 25% difference means the holdout sites systematically have more SSC per unit turbidity than the training sites. The model has never seen this distribution during training and is being evaluated on a harder population. This could mean the holdout results understate the model's performance on training-like sites, or it could mean the split is biased. Either way, it should be investigated and reported.

### Red flag severity: MODERATE

**4f. Temporal non-stationarity at high-count sites.** The SSC/turbidity ratio changed by +98% at USGS-03432516 and -42% at USGS-01658000 between the first and second halves of their records. If the training data includes the full temporal range, the model is learning a time-averaged relationship that may not apply to current conditions. This is not a bug but it is a limitation that should be discussed.

**4g. Collection method confounding.** At the 97 sites with both auto_point and depth_integrated samples, auto_point consistently shows higher SSC and higher ratios. But this is confounded with event type: auto_point captures storms, depth_integrated captures routine. At USGS-01364500, auto_point has median SSC=16 while depth_integrated has median SSC=266 -- the opposite of the global pattern -- likely because the depth_integrated samples at this site are storm-targeted. The method variable is a proxy for sampling intent, not just vertical position in the water column.

---

## Question 5: Which Patterns Are Publishable Figures?

### Must-include figures (6):

1. **The overprediction-by-SSC-range figure.** Show prediction/observation ratio by SSC decile. This is the most important diagnostic and demonstrates honest self-assessment. Pair it with a discussion of BCF limitations.

2. **Site-level R-squared distribution (histogram or CDF).** Show the full distribution, not just the median. The 28% of sites with R-squared < 0 must be visible. Overlay the adaptation curve (R-squared at N=0, 5, 10, 20) to show which sites are rescued by adaptation and which remain poor.

3. **Adaptation curve with extreme/normal stratification.** The N=20 extreme collapse (R-squared from 0.722 to 0.295) is a cautionary finding. Show the adaptation curves separately for above-median and below-median turbidity.

4. **Collection method and time-of-day combined figure.** The finding that "time-of-day is really collection method" is genuinely novel for this literature and worth a figure. A two-panel plot: (a) stacked bars of collection method by hour-of-day, (b) MAPE by hour-of-day with method composition annotated.

5. **SSC/turbidity ratio by collection method within the same sites.** Use the 97 dual-method sites. This is a controlled comparison that isolates the method effect from the site effect. It is publishable and practically relevant.

6. **Regional map with per-site performance.** Color-code sites by R-squared on a US map, with HUC2 boundaries. This shows where the model works and where it fails.

### Include if space allows (3):

7. SSC/turbidity ratio temporal drift at selected sites (the +98% and -42% cases).
8. Burst sampling hydrograph examples showing within-event SSC variation at nearly constant turbidity.
9. Conductance-turbidity anti-correlation scatter, annotated with base-flow vs storm-flow.

### Background noise (do not include):

- The seasonal SSC pattern (January vs August) is well-known and does not advance the literature.
- The "almost all sites are transport-limited" finding is expected for USGS sites with turbidity sensors and does not need a figure.
- Weekend vs weekday is just a restatement of the collection method pattern and should be a brief mention in the text, not a figure.

---

## Question 6: What Are We Missing?

### Critical omissions:

**6a. The BCF problem requires immediate attention.** The global Snowdon BCF of 1.390 is creating a 44% systematic overprediction at the median. This is not a subtle effect. Options: (a) compute a site-group-specific BCF (e.g., by HUC2 or by median SSC range), (b) use Duan's smearing estimator which is less sensitive to distributional assumptions, (c) estimate the BCF as a function of the predicted value rather than a constant. I would investigate option (c) first -- fit a simple curve of (observed/back-transformed-prediction) vs predicted value and use that as a variable BCF.

**6b. You are not reporting the right central metric.** The briefing leads with MedSiteR-squared = 0.486 (vault). But the median is misleading when 28% of sites have R-squared < 0 and the mean is negative. A WRR reviewer will ask for the mean, and -0.075 is damning. Report both, and spend paper space on *why* some sites fail (data quality, unusual geology, non-stationary ratio) and how the adaptation mechanism rescues them.

**6c. Data quality filtering is incomplete.** There are 430 records with SSC/turbidity ratios above 50, including physically impossible values. The top offender has a ratio of 94,000. These outliers are training the model on noise. At minimum, run a sensitivity analysis: retrain after removing records with ratio > 100 and report the change in performance. I would expect improvement, especially at the extremes.

**6d. The effective sample size problem.** You report 35,209 paired samples at 396 sites. But with 6.8% burst duplicates (near-identical features), high temporal autocorrelation at many sites, and the top 10 sites contributing 15% of data, the effective independent sample size is much smaller. This matters for: (a) statistical tests of feature importance, (b) confidence intervals on metrics, and (c) the LOGO CV which assumes site-level independence.

**6e. The Wilcoxon test is nuclear.** I ran a Wilcoxon signed-rank test comparing predictions to observations in the holdout set: W = 3,448,817, p = 6.2e-166. The model predictions are systematically different from observations. This is driven by the overprediction at low-to-moderate SSC. While this level of significance is expected given N=5,847, the direction and magnitude of the bias matter. A reviewer who runs this test will conclude the model has a first-order calibration problem.

**6f. You need a "failure mode taxonomy."** Group the 20 sites with R-squared < 0 by their failure mode: (a) low-SSC overprediction from BCF, (b) non-stationary SSC/turbidity ratio, (c) unusual geology (HUC2-13 sites with ratio 3.89), (d) data quality issues (extreme ratio outliers). Then show that adaptation rescues category (a) and (b) sites while (c) and (d) require different interventions. This turns a weakness into a scientific contribution.

**6g. The "vault" split characteristics.** The vault has higher median SSC (78 vs 51 for training) and different ratio characteristics (2.00 vs 1.74 for training). Was the vault selected to be "clean" sites with certain properties? If so, the vault metrics are not representative of general model performance and this must be stated explicitly. The vault MedSiteR-squared of 0.486 may reflect the characteristics of the vault sites, not the model's true capability.

---

## Summary of Priority Actions

| Priority | Action | Why |
|----------|--------|-----|
| 1 | Investigate and fix the BCF overprediction | 44% median bias makes the model unreliable for practitioners |
| 2 | Remove or flag records with SSC/turb ratio > 100 | Training on impossible values corrupts extreme predictions |
| 3 | Report mean AND median site R-squared | The mean is -0.075; hiding this will get the paper rejected |
| 4 | Run adaptation with flow stratification | Prevents adaptation from destroying extreme-event predictions |
| 5 | Classify and report failure modes for R-squared < 0 sites | Turns a weakness into a contribution |
| 6 | Test stationarity with temporal split | 125 sites have significant trends; reviewers will ask |
| 7 | Run spatial-blocked CV (HUC4 or HUC6) | Tests whether LOGO CV is over-optimistic |

---

*All statistics in this review were computed directly from the project data files: `turbidity_ssc_paired.parquet` (35,209 samples), `v9_final_per_reading.parquet` (5,847 holdout predictions), `v9_final_per_site.parquet` (76 holdout sites), and `site_scores.csv` (254 training sites).*
