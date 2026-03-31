# Expert Review: Data Patterns & Next Steps
**Dr. Ananya Krishnamurthy** | Applied Environmental Statistics | 2026-03-30

---

## Question 1: What Other Patterns Should We Look For?

Several statistically important explorations are absent from the current analysis.

**Spatial autocorrelation.** You have 254 training sites and 76 validation sites. If nearby sites share similar errors (which they almost certainly do -- watersheds in the same ecoregion will have similar lithology, land use, and sediment character), your LOGO cross-validation overstates generalization performance. Run a Moran's I on the site-level residuals. If significant (and it will be), this means your effective sample size for model evaluation is smaller than 254. A reviewer will catch this.

**Interaction between collection method and watershed characteristics.** You report method-level SSC/turbidity ratios (Pattern 6), but these ratios likely vary by particle size distribution, which varies by lithology. Is the auto_point vs depth-integrated gap larger in fine-sediment vs coarse-sediment systems? If so, the "method effect" is partially confounded with particle mineralogy and settling velocity. Decompose this.

**Sensor type heterogeneity.** Different turbidity sensors (Hach, YSI, Forest Technology Systems) have different optical geometries and wavelength responses. If sensor metadata is available in NWIS, stratify residuals by sensor model. Sensor-to-sensor variability is a well-documented source of non-comparability in turbidity data (Anderson 2005, Rasmussen et al. 2009). If you cannot stratify, at least discuss this as an uncontrolled source of variance.

**Hysteresis signatures.** Pattern 9 mentions burst sampling capturing storm hydrographs. Clockwise vs counterclockwise SSC-discharge hysteresis indicates whether sediment sources are proximal (channel) or distal (hillslope). Classify your burst-sampled storms by hysteresis direction and test whether model error differs systematically. This is a publishable sub-analysis on its own.

**Residual structure by flow regime.** Plot model residuals against discharge quantile (not just turbidity quantile). The model may behave differently on the rising vs falling limb of the hydrograph even at the same turbidity level, because SSC-turbidity relationships exhibit hysteresis. This is a different question from Pattern 3 (extreme vs normal).

**Temporal autocorrelation in residuals.** If your LOGO CV includes all samples from each held-out site, nearby-in-time samples are not independent. Report the lag-1 autocorrelation of residuals within sites. If high, your effective sample size per site is inflated, and per-site R^2 estimates have wider confidence intervals than you think.

---

## Question 2: Adaptation Hurting Extremes at N=20

This is not surprising, and I would argue it is not a bug -- it is the expected statistical behavior of Bayesian updating with an unrepresentative calibration sample.

**The cause is sample composition bias.** At N=20, most calibration samples will come from routine monitoring (weekday, depth-integrated, moderate flow). The posterior shifts toward the "typical" turbidity-SSC relationship at that site, which may differ substantially from the storm-event relationship. At N=1-10, the prior (pooled model) still dominates, so extreme-event performance is preserved.

**Flow-stratified adaptation is the obvious fix, but be careful.** If you split calibration into "storm" and "baseflow" subsets, you need enough samples in each stratum. At N=20 total, you might have only 2-3 storm samples -- too few for stable Bayesian updating. You would need N=40+ to have adequate representation in both strata, which defeats the purpose of low-N adaptation.

**My recommendation:** Cap adaptation at N=10 and report this as a finding. The story is actually strong: "site-specific calibration with as few as 5-10 paired samples improves normal-condition estimates without degrading extreme-event performance, but over-adaptation to routine samples degrades storm prediction." That is a useful, publishable, and practically important result. Practitioners need to know that more calibration data is not always better when the calibration sample is biased toward baseflow.

**If you insist on fixing N=20:** Weight calibration samples by their representativeness of the flow distribution. Upweight storm samples, downweight clustered baseflow samples. But honestly, capping at N=10 and explaining why is cleaner.

---

## Question 3: What Would Make This Paper-Ready?

A WRR reviewer will demand the following, and right now I see gaps.

**Confidence intervals on all performance metrics.** MedSiteR^2 = 0.486 means nothing without a bootstrap CI. Is it 0.486 +/- 0.02 or 0.486 +/- 0.15? With 36 vault sites, I suspect the CI is wide. Report bootstrap 95% CIs (resample sites, not samples) for every metric in every row of the performance summary table.

**Multiple testing correction on the SSC trends.** You report 125/254 sites with significant trends at p<0.05. Under the null hypothesis, you would expect ~13 false positives. 125 is clearly above chance, but you should still apply Benjamini-Hochberg FDR correction and report how many survive at q<0.10. Some of those 125 are noise.

**Formal comparison to existing methods.** You need a benchmark. The simplest is a site-specific log-log OLS regression of SSC on turbidity (the standard USGS approach via Rasmussen et al. 2009). Train it on the same calibration samples, evaluate on the same test samples. If your model does not beat site-specific OLS at N=10+, you have a problem. At N=0 (zero-shot), you have no competitor, so the comparison is: pooled model vs site-specific OLS at various N.

**Error analysis stratified by data quality flags.** NWIS data comes with qualification codes (estimated, approved, provisional). If you have not stratified errors by these flags, do so. A reviewer will wonder whether poor-quality input data is driving outlier errors.

**Geographic bias assessment.** Show a map of training sites and validation sites. If your training data is 80% USGS Region 12 (Pacific NW) and your validation includes sites from the Southeast, report performance by region. A model trained predominantly on Pacific NW rain-snow watersheds may not generalize to Piedmont clay systems.

**Formal test of the "collection method confounds time-of-day" claim.** Pattern 1 is interesting but currently anecdotal. Fit a mixed-effects model: error ~ hour + method + (1|site). If method absorbs the hour effect (hour becomes non-significant when method is included), your claim is supported. If both remain significant, the story is more complicated.

---

## Question 4: Red Flags in the Patterns

**Red flag 1: The vault NSE of 0.164 vs the validation NSE of 0.692.** This is a factor-of-4 difference. NSE is sensitive to bias, so this suggests the vault sites have systematically different mean SSC or variance than the validation set. Why? If the vault was selected to be "clean" (e.g., high data quality, consistent time series), it may also be biased toward well-monitored, low-variability sites where the turbidity-SSC signal is weaker. Investigate whether vault sites differ from validation sites in mean SSC, SSC variance, dominant collection method, or ecoregion. If they do, the vault is not a representative test -- it is a biased test, and the 0.486 MedSiteR^2 may be pessimistic or optimistic for the wrong reasons.

**Red flag 2: Only 3 supply-limited sites out of 254+.** Pattern 7 claims "almost all sites are transport-limited." This is geomorphologically implausible for a dataset spanning the continental US. Many arid and semi-arid sites exhibit supply-limited behavior. Either (a) your dataset is geographically biased toward humid transport-limited systems, (b) you are testing the wrong null hypothesis (a monotonic positive SSC-Q correlation does not prove transport limitation -- you need to test for SSC exhaustion within events), or (c) supply-limited sites were filtered out during data cleaning because they have weak turbidity-SSC relationships. Investigate which explanation applies, because a reviewer will challenge this claim.

**Red flag 3: "All rho > 0.3" in Pattern 7.** If you selected sites based on having "usable" turbidity-SSC relationships, you have introduced selection bias. Your model performance metrics only apply to sites where the turbidity-SSC relationship is already reasonably strong. This is fine and defensible, but it must be stated explicitly as a scope limitation. The model does not apply to sites where turbidity is a poor SSC proxy (e.g., DOM-dominated, algae-dominated, or colloidal systems).

**Red flag 4: The external NTU zero-shot MAPE of 90%.** This is very high. Yes, it drops to 45% at N=10, but the zero-shot performance suggests the model's transferability to NTU-reporting sensors is poor without calibration. Be cautious about claiming "zero-shot generalization" in the abstract. The honest framing is "the model requires minimal site-specific calibration (N >= 5) for practical accuracy."

---

## Question 5: Which Patterns Are Publishable Figures?

**Definitely include (these survive scrutiny):**

1. **Extreme events vs normal conditions performance split (Pattern 3).** The R^2 jump from 0.403 to 0.722 is striking and counterintuitive to many practitioners. Make a two-panel figure: scatter of predicted vs observed for top-5% turbidity and bottom-95%, with regression lines and CIs. This is your headline finding for operational relevance.

2. **Adaptation curve with the N=20 collapse (Pattern 4).** Plot MedSiteR^2 vs N for both extreme and normal conditions on the same axes. The divergence at N=20 is a cautionary result with practical implications. This is a novel contribution -- I have not seen this reported before.

3. **Collection method confounding time-of-day (Pattern 1).** A stacked bar or heatmap showing collection method proportions by hour, overlaid with model error by hour. But only after you do the formal mixed-effects test from Q3. If the formal test supports the claim, this becomes a methodological contribution about data interpretation.

4. **SSC/turbidity ratio by method (Pattern 6).** A box plot or violin plot. The 35% difference between auto_point and grab is operationally significant and has implications for anyone building turbidity-SSC models. Pair it with a discussion of vertical sediment concentration gradients.

**Include in supplementary materials:**

5. Seasonal SSC pattern (Pattern 10). Well-known, not novel, but useful context.
6. Conductance anti-correlation (Pattern 8). Interesting but incremental. Supplement.
7. SSC trends (Pattern 5). After FDR correction, show a map of increasing/decreasing sites. Supplement unless the spatial pattern reveals something unexpected (e.g., all increasing sites are in post-wildfire areas).

**Do not include as a standalone figure:**

8. Weekend vs weekday (Pattern 2). This is redundant with the time-of-day/method analysis. Mention in text, do not figure.
9. Transport vs supply limitation (Pattern 7). Too many caveats (see Red Flag 2). Mention carefully in text with appropriate hedging.

---

## Question 6: What Are You Missing?

**Prediction intervals, not just point predictions.** Your model produces point estimates. For operational use (e.g., TMDL compliance, real-time load estimation), users need uncertainty bounds. Even if you do not build a full probabilistic model, you should at minimum report empirical prediction intervals stratified by turbidity magnitude and adaptation level (N). A model without uncertainty quantification is incomplete for regulatory applications.

**The elephant in the room: particle size distribution.** Turbidity is an optical measurement. SSC is a gravimetric measurement. The relationship between them depends on particle size, shape, color, and mineralogy. You have no direct particle size data, but you do have watershed-level geology features (lithology, percent fines, eolian fraction). Test whether your model residuals correlate with these features. If they do, your model is partially learning a particle-size proxy, which is scientifically interesting. If they do not, you are leaving signal on the table.

**Stationarity assumption.** Your SSC trends (Pattern 5) suggest the turbidity-SSC relationship is non-stationary at many sites. But your model assumes stationarity (it uses features that do not change over time, like watershed characteristics). If a site's SSC has been increasing due to land use change or wildfire, your model will systematically under-predict recent samples and over-predict old ones. Split your test data into pre-2015 and post-2015 and compare error rates. If they differ significantly, you have a non-stationarity problem that should be disclosed.

**Censored and below-detection-limit data.** Turbidity and SSC measurements below detection limits are common in low-flow conditions. How are these handled? If they are dropped, you have left-censoring bias that inflates your model's apparent accuracy on low-SSC conditions. If they are set to zero or half the detection limit, that introduces a different bias. State your approach explicitly.

**Cross-validation leakage through watershed features.** If two sites share the same HUC8 watershed, they share identical watershed-level features (land use, geology, etc.). Your LOGO CV holds out one site at a time, but the held-out site's watershed features may be identical to a training site in the same watershed. This is not a bug, but it means your LOGO performance is optimistic for truly novel watersheds. Consider a leave-one-watershed-out analysis as a robustness check.

**The gap between pooled NSE and MedSiteR^2.** Your vault has pooled NSE = 0.164 but MedSiteR^2 = 0.486. This means a few high-variance sites are dragging down the pooled metric while most sites perform reasonably. Identify those outlier sites. Are they systematically different (e.g., tidally influenced, glacial, karst)? Reporting the distribution of site-level R^2 (histogram or CDF) is more informative than either summary statistic alone.

---

## Summary of Priority Actions

Ranked by statistical importance for publication:

1. Bootstrap confidence intervals on all metrics (non-negotiable for peer review)
2. Benchmark against site-specific OLS at matched N (non-negotiable)
3. Moran's I on site-level residuals for spatial autocorrelation
4. FDR correction on SSC trend tests
5. Investigate vault vs validation site characteristics to explain NSE discrepancy
6. Mixed-effects model for time-of-day vs collection method
7. Pre-2015 vs post-2015 error comparison for stationarity
8. Leave-one-watershed-out robustness check
9. Prediction intervals or at minimum empirical uncertainty bounds
10. Identify and characterize the high-error outlier sites dragging down pooled NSE

Items 1-2 are absolute prerequisites before submitting to WRR. Items 3-6 are what a careful reviewer will ask for. Items 7-10 strengthen the paper substantially but could potentially go in a revision if time-pressed.

---

*Review prepared in the role of Dr. Ananya Krishnamurthy, applied environmental statistician. All recommendations reflect standard practices for publication in Water Resources Research or similar journals.*
