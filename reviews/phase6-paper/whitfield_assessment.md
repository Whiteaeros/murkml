# Whitfield Assessment — murkml v11 / WRR Draft Review

**Reviewer:** Dr. Sarah Whitfield, Fluvial Geomorphologist
**Affiliation:** USGS Sediment Transport Program (20 years)
**Date:** 2026-04-02
**Reviewed:** v11 model results, DECISION_LOG, RESULTS_LOG, wrr_draft_v1.md, load comparison data, bootstrap CIs, hyperparameter sensitivity sweep, SHAP/feature importance documentation

---

## 1. Overall Assessment

This is a genuinely novel contribution to sediment monitoring science. No one has built a cross-site turbidity-SSC model at this scale (405 sites, continental coverage) and validated it against the USGS 80155 published sediment record. The paper fills a real operational gap: thousands of turbidity sensors produce data that cannot currently be converted to SSC without per-site calibration. The Brandywine load result is striking and, if it holds up under scrutiny, is a headline finding for the practitioner community.

**Scientific merit: Strong.** The project asks the right question, uses the right data, and is brutally honest about its limitations (30% of sites R^2 < 0, the site heterogeneity problem, CQR failure). This honesty will serve the paper well at WRR, where reviewers are allergic to overstated ML claims.

**Paper readiness: 70%.** The draft is well-structured and the methods are solid, but there are gaps in the load comparison that a WRR reviewer will catch, some overstated claims that need hedging, and several strong results that are buried or missing from the current draft.

**Verdict: Publishable with revisions.** The core contribution --- turbidity as primary input to a cross-site model, validated against 80155 --- is sound. The revisions needed are primarily analytical completeness and honest framing, not fundamental methodological changes.

---

## 2. Sediment Transport Physics Critique

### 2.1 Turbidity-SSC Relationship Characterization

**Mostly correct, with one significant gap.** The paper correctly identifies the core physics: turbidity is an optical measurement that responds to particle concentration, size distribution, shape, and refractive index. The statement that "the turbidity-SSC relationship depends on particle size, mineralogy, and organic content" (Section 1) is accurate and well-cited.

However, the paper does not adequately discuss **the nonlinearity of the turbidity-SSC relationship at high concentrations.** Above roughly 1,000-2,000 FNU, many optical sensors saturate or enter a nonlinear regime where increasing SSC actually decreases the backscatter signal (sensor saturation). The model includes a `turb_saturated` flag (turbidity > 3,000 FNU), which is good, but the paper should explicitly discuss why the top-1% underprediction (-25%) is partly a sensor physics problem, not just a data scarcity problem. The sensor literally cannot see the sediment at extreme concentrations.

The between-site CV of 4.37 vs within-site CV of 1.35 is an excellent finding. In my experience calibrating dozens of these regressions, the between-site variation is the dominant challenge, and this is the first time I have seen it quantified at continental scale. **This number alone justifies the paper.**

### 2.2 Grain-Size / Mineralogy Confound

**Addressed but not fully resolved.** The geology-dependent performance breakdown (carbonate R^2 = 0.81 vs volcanic R^2 = 0.20) is physically correct and well-explained in Section 5.2. Carbonate-derived sediment tends to be relatively uniform in size and refractive index (calcite silt), producing a tight turbidity-SSC relationship. Volcanic lithologies produce bimodal particle populations --- fine ash and coarse lithic fragments --- with very different optical-to-mass ratios, which explains the poor R^2.

What is missing: **the paper does not discuss clay mineralogy as a confound.** Smectite (montmorillonite) clays have dramatically different light-scattering properties per unit mass than kaolinite or illite, due to their platy morphology and high surface area. Two watersheds with identical SSC and particle size but different clay minerals will produce different turbidity readings. This is a known limitation of all optical SSC estimation (Gippel, 1995) and should be acknowledged explicitly.

The SHAP analysis showing SGMC sedimentary-chemical at rank 10 suggests the model is learning some of this mineralogy signal indirectly through lithology. This is a strength worth emphasizing.

### 2.3 Hysteresis Argument for Load Estimation

**Sound and well-supported.** The argument that turbidity captures event-scale hysteresis --- rising-limb SSC/turbidity ratio 16% higher than falling limb, 39.5% clockwise loops --- is physically correct and is the strongest mechanistic argument for why turbidity-informed models beat discharge-only models for load estimation.

One important nuance missing from the draft: **hysteresis is not just about sediment exhaustion.** Clockwise hysteresis (proximal source, abundant supply) and counterclockwise hysteresis (distal source, channel bed remobilization) have different physical drivers and different implications for load estimation errors. The 39.5% clockwise / 24.4% counterclockwise / 36.1% linear split across 119 events is interesting and should appear in the paper. The fact that the model handles both hysteresis directions through the turbidity signal is a more nuanced and defensible claim than simply "turbidity captures hysteresis."

### 2.4 Geology-Dependent Performance

**Physically sensible.** Carbonate R^2 = 0.81 makes sense: limestone and dolostone watersheds produce relatively uniform calcium carbonate silt with consistent optical properties. The high R^2 reflects genuine physical uniformity, not overfitting.

Volcanic R^2 = 0.20 also makes sense for the reasons discussed above. The model cannot distinguish fine volcanic ash (high surface area per unit mass, strong scattering) from coarse lithic fragments (low surface area, weak scattering) using turbidity alone.

**The auto-point vs depth-integrated performance gap** (R^2 = 0.24 vs 0.32) is also physically expected. Auto-point samplers miss the coarse fraction that settles below the intake, creating a systematic size-dependent bias. The 4x SSC difference reported in the draft (Section 5.3) is within the range I have observed in practice, though it varies enormously by stream gradient and particle size.

---

## 3. Load Comparison Critique

### 3.1 Is 3 Sites Sufficient?

**No, but it is a defensible starting point.** Three sites is the minimum to demonstrate the concept, not to prove generalizability. The paper should explicitly state this limitation. WRR reviewers will ask: "What about sites in the arid West? In the glaciated Midwest? In the Appalachian coalfields?" Three sites in two geologic provinces (Pennsylvania Piedmont and Colorado Plateau) cannot answer these questions.

**What I would need to see for a fully convincing load validation:**
- At least 8-10 sites across 4+ geologic provinces
- At least one site with high sand fraction (the model's known weakness)
- At least one site with known counterclockwise hysteresis dominance
- Sites spanning 2+ orders of magnitude in drainage area
- At least one snowmelt-dominated site (different sediment generation mechanism)

**Recommendation:** Frame the load comparison as a "proof of concept at three benchmark sites" rather than a general validation. This is honest and still newsworthy. Add a sentence: "Expanding this validation to additional sites and geologic settings is a priority for future work."

### 3.2 Is the Brandywine 2.6% Result Robust or Lucky?

**Potentially lucky, and the paper must address this.** Looking at the raw data:

- Brandywine total: v11 = 42,059 tons vs 80155 = 41,007 tons (ratio 1.03)
- But the daily v11 total_load_ratio is 1.59 (59% overprediction on matched days)
- And the daily pbias is +59.4%

This means the 2.6% total match is the result of **compensating errors**: the model overpredicts on many transport days but the time coverage is different enough that the totals happen to align. The 80155 record covers 2,548 days but the model only has 1,366 overlapping days. The total load number integrates over different time windows.

Furthermore, at the daily scale, Brandywine v11 R^2 = 0.49 and Spearman = 0.76. These are decent but not extraordinary. The 2.6% total match is much better than the daily metrics would predict, which is a sign of error cancellation.

**The paper needs to:**
1. Report the total load ratio alongside the percentage match (1.03x, not just "2.6%")
2. Acknowledge that daily-scale accuracy (R^2 = 0.49) is moderate
3. Discuss how error cancellation over long integration periods can produce good total load matches even from imperfect daily predictions --- this is actually a known property of sediment load estimation (see Walling & Webb, 1996)
4. Show year-by-year or at minimum multi-year sub-period totals to test whether the match holds across different hydrologic regimes (the annual data in the JSON has many NaN values --- this is a problem)

### 3.3 Is the Comparison with 80155 Fair?

**Mostly fair, with important caveats the paper partially addresses.** The draft correctly states that 80155 is "not a simple regression --- it incorporates visual inspection of hydrographs, event-by-event adjustments, and professional judgment" (Section 3.7). This is accurate. The Porterfield method involves a hydrographer hand-drawing rating curves, adjusting for hysteresis on a storm-by-storm basis, and incorporating supplementary data (water color, turbidity observations, upstream/downstream context). It is the most labor-intensive approach to sediment load estimation that exists.

**Caveats that need more emphasis:**
1. The 80155 record itself has uncertainty, typically estimated at 15-25% for annual loads (Horowitz, 2003). The 2.6% match is within the uncertainty of the reference.
2. The 80155 record at Brandywine was produced by experienced hydrographers at the PA Water Science Center, one of the best sediment programs in the country. The match might be worse at sites with less experienced hydrographers.
3. The zero-load days in 80155 reflect hydrographer judgment that sediment transport was negligible. The model always predicts nonzero load (because it works from continuous data). This creates a systematic difference in how the two methods handle baseflow.

### 3.4 Is Transport-Day Filtering Justified?

**Yes, but it needs better justification in the paper.** The 80155 record reports zero tons on 57% of days at Brandywine (only 24% are "transport days"). These zeros are a hydrographer decision, not a measurement --- the hydrographer looked at the hydrograph and decided sediment transport was negligible. The model, working from continuous 15-minute data, always predicts some nonzero SSC and therefore some nonzero load.

Filtering to transport days is standard practice when comparing automated methods against 80155. But the paper should explain WHY: because the model and 80155 define "zero transport" differently, and including hundreds of zero-vs-nonzero comparisons inflates error metrics without being informative about the model's sediment estimation capability.

**The daily Brandywine metrics on transport days (v11 R^2 = 0.44, Spearman = 0.83) vs all days (R^2 = 0.49, Spearman = 0.76) are both useful and both should appear in the paper.**

### 3.5 Valley Creek 55% Overprediction

**Not acceptable for operational use, but scientifically informative.** Valley Creek is a small (60 km^2) urbanized watershed in suburban Philadelphia. The 55% total load overprediction (ratio 1.55x) is concerning but physically explainable:

- Urban watersheds produce highly variable turbidity from non-sediment sources (construction runoff, road salt, stormwater infrastructure)
- The model has no features encoding impervious surface connectivity or stormwater infrastructure
- Valley Creek's daily R^2 is -0.76 (negative), meaning the model is worse than predicting the mean

Looking at the load comparison JSON, Valley Creek's event median error is +169% (v11) vs +591% (OLS). So while v11 is much better than OLS, it is still substantially wrong at this site. The paper should use Valley Creek as an example of WHERE the model fails and WHY, not hide it.

**Ferron Creek** (-25% underprediction, ratio 0.75x) is actually the strongest load result besides Brandywine: daily R^2 = 0.76, Spearman = 0.96. This is a snowmelt-driven system in the Colorado Plateau --- the fact that the model handles this geomorphic context correctly is significant.

---

## 4. Paper-Worthy Results and Quotes

**These specific results MUST appear in the final paper. Format for direct reference by the writing team.**

### Headline Results
- "Spearman rho = 0.907 on 78 holdout sites (95% CI: 0.836-0.899) --- the model ranks SSC correctly across diverse sites and conditions without any site-specific calibration."
- "MedSiteR^2 = 0.40 (95% CI: 0.358-0.440) --- treats each site equally, avoids dominance by high-SSC outlier sites."
- "70% of predictions within 2x of observed, MAPE = 40.1% --- practical accuracy for screening-grade assessment."
- "Between-site turbidity-SSC ratio CV = 4.37 vs within-site CV = 1.35 (3.2x ratio) --- site heterogeneity is the fundamental challenge, quantified for the first time at continental scale."

### Adaptation Results
- "N=2 random calibration samples: MedSiteR^2 jumps from 0.40 to 0.41 (Bayesian) vs R^2 = -0.56 (OLS) --- CatBoost+Bayesian is safe at small N where OLS catastrophically overfits."
- "N=10 random: MedSiteR^2 = 0.49 (95% CI: 0.414-0.560) --- one sampling campaign captures most adaptation benefit."
- "Temporal N=10: MedSiteR^2 = 0.39 (WORSE than zero-shot) --- first 10 chronological samples are baseflow-biased. Practitioners must target storm events."
- "Marginal benefit plateaus after N=10: improvement from 10 to 50 is +0.005 MedSiteR^2 vs +0.09 from 0 to 10."

### Load Comparison Results
- "Brandywine total load: v11 = 42,059 tons vs 80155 = 41,007 tons (2.6% overprediction) over 8 water years --- matches human-adjusted Porterfield rating curves without per-site calibration."
- "OLS (discharge-only) total load at Brandywine: 68,666 tons (67% overprediction) --- turbidity information cuts the error by 25x."
- "Ferron Creek (Utah, snowmelt): v11 daily R^2 = 0.76, Spearman = 0.96. OLS daily R^2 = -3.97. Model transfers across geomorphic settings."
- "Storm events: v11 median event error is 2-4x smaller than OLS at all three sites (Brandywine +119% vs +165%; Valley Creek +169% vs +591%; Ferron Creek -39% vs +124%)."
- "Valley Creek: v11 overpredicts by 55% (ratio 1.55x) --- the model's failure mode in urbanized watersheds with non-sediment turbidity sources."

### Physics and Disaggregated Results
- "Carbonate-dominated watersheds: R^2 = 0.81. Volcanic watersheds: R^2 = 0.20. Geology explains cross-site performance variation better than any other attribute."
- "Depth-integrated samples: R^2 = 0.32. Auto-point samples: R^2 = 0.24. Collection method is SHAP rank 3 (mean |SHAP| = 0.349) --- the model knows the vertical concentration gradient matters."
- "At the same turbidity, depth-integrated samples yield 4x higher SSC than point samples --- reflecting the settling of coarse particles below the sensor intake."
- "Clockwise hysteresis: 39.5%, counterclockwise: 24.4%, linear: 36.1% across 119 ISCO events. Rising limb SSC/turbidity ratio 16% higher than falling."
- "30% of holdout sites have R^2 < 0 --- this is NOT hidden. These cluster in volcanic, glacial-flour, and urban geologic regimes where the optical-gravimetric relationship is non-standard."
- "Low-SSC overprediction: 2.45x below 10 mg/L --- consistent with DOM/algae contamination of the turbidity signal at low concentrations, not model error."
- "SSC <50 mg/L: R^2 = -60.6 (massive overprediction). SSC >5,000 mg/L: R^2 = -3.4 (underprediction). The model is a mid-range tool."
- "Residuals are strongly non-normal: skewness = 2.0, kurtosis = 13.8, 2% beyond 3-sigma (7x the normal rate). Student-t adaptation prior (df=4) is physically motivated, not just a statistical convenience."
- "Conformal prediction intervals: 90.6% coverage at 90% nominal level (bins: 92%, 91%, 89%, 91% for SSC <30 to 2,000 mg/L). BUT: 52% coverage above 2,000 mg/L --- extreme tail is not bounded."

### Model Development Results
- "Box-Cox lambda = 0.2 vs log1p: nearly identical holdout R^2 (0.472 vs 0.460), but BCF drops from 1.71 to 1.35 --- less back-transformation bias."
- "Monotone constraints HELP Box-Cox (+0.060 native R^2) but HURT log1p (-0.019) --- transform-constraint interaction matters."
- "Hyperparameter sensitivity: total KGE spread = 0.027 across 12 non-extreme configurations --- model is stable and not overtuned."
- "External NTU validation (260 sites, 11K samples, different sensor standard): Spearman = 0.927 --- cross-network, cross-sensor generalization confirmed."

### Comparative Results
- "CatBoost beats per-site OLS at EVERY calibration level N and EVERY split mode (random, temporal, seasonal). Most dramatic at N=2 temporal: CatBoost R^2 = 0.36 vs OLS R^2 = -0.56."
- "Song et al. (2024) median R^2 = 0.55 for SSC at ungauged sites using LSTM + discharge. Our Spearman = 0.907 is substantially higher --- turbidity is the missing input."
- "agriculture_pct predicts where OLS wins (rho = -0.48, p = 0.001) --- simple agricultural sites do not need ML; complex/urban sites benefit."

---

## 5. What's Missing

### 5.1 Critical Gaps

1. **Moran's I spatial autocorrelation analysis.** The paper acknowledges this gap (Section 6.4) but it needs to be done before submission. If holdout sites cluster geographically near training sites, the holdout metrics are inflated. This is a standard WRR reviewer concern and the absence will be flagged.

2. **Year-by-year load comparison at Brandywine.** The annual data in load_comparison_summary.json is almost entirely NaN. This is a serious omission. The 2.6% total match could mask year-to-year errors of 50%+ that cancel out. A WRR reviewer will demand this.

3. **Comparison with per-site turbidity-SSC regressions at the load sites.** At Brandywine and Valley Creek, USGS has published turbidity-SSC regressions (these are the basis for the 80155 record). How does v11 compare to the SITE-SPECIFIC turbidity regression at these sites? This is the natural benchmark a sediment person would ask for.

4. **Grain-size data at holdout sites.** The paper attributes cross-site variation to particle size but never directly tests this with grain-size data. USGS often publishes percent fines (parameter code 70331) or D50 at sediment sites. Even a subset analysis at sites with grain-size data would strengthen the mechanistic argument enormously.

5. **Temporal trend analysis.** Are residuals non-stationary? Does the model degrade over multi-year periods? The 2008-2016 Brandywine comparison spans nearly a decade --- is the match uniform or does it drift?

6. **Effective sample size adjustment.** The lag-1 autocorrelation of up to 0.69 at individual sites means that the stated 23,624 training samples likely overstate the effective information content by 2-4x. Bootstrap CIs are computed with site-level blocking (good), but the within-site autocorrelation still inflates CV metrics. This should be discussed.

### 5.2 Missing from Paper Draft

7. **The tier comparison (A vs B vs C).** The paper does not present the Tier A/B/C ablation showing that watershed attributes significantly improve performance (p < 0.01 for native R^2). This is key evidence that the model is learning site context, not just fitting turbidity.

8. **The dual BCF explanation.** BCF_mean = 1.297 vs BCF_median = 0.975 is discussed in Methods but the practical implication --- that 75% of individual predictions are overpredicted with BCF_mean --- should appear in the Results with the Wilcoxon test statistic (p = 6.2e-166).

9. **The OLS benchmark details.** The paper reports the OLS comparison but does not specify that OLS uses Duan's smearing estimator (it does, from the Methods), nor does it discuss WHY OLS fails so catastrophically at N=2 (no shrinkage, massive extrapolation from baseflow to storm conditions).

10. **The 51 catastrophic sites analysis.** Only 7 of 51 sites with LOGO R^2 < -1 are genuinely wrong predictions; 17 are low-signal sites where R^2 is misleading (small SSC range, small absolute errors). This is an important nuance that protects the model from the "30% of sites fail" criticism.

---

## 6. What's Overstated

### 6.1 The 2.6% Brandywine Match

As discussed in Section 3.2, the paper presents "2.6%" as the headline number, but the daily-scale accuracy (R^2 = 0.49, pbias = +59.4%) tells a different story. The total match benefits from error cancellation over the integration period. The paper should lead with the total match but immediately contextualize it with daily-scale metrics. Something like: "Over 8 water years, the total load matches within 2.6%, though daily predictions show a systematic 59% positive bias that is compensated by differences in temporal coverage."

### 6.2 "Without Any Site-Specific Calibration"

This phrase appears in the abstract and conclusions. While technically true (the model is trained cross-site), the BCF_mean = 1.297 is a global correction factor estimated from training data. If that BCF were estimated per-site, the claim of "no calibration" would be false. The paper should be precise: "without per-site parameter estimation."

### 6.3 The Spearman rho CI Discrepancy

The abstract states "Spearman rho = 0.907" but the bootstrap CI is [0.842, 0.886]. The point estimate (0.907) is ABOVE the 95% CI upper bound (0.886). This is a red flag. The 0.907 is the pooled Spearman across all holdout readings, while the bootstrap CI is computed with site-level resampling, which appropriately captures the site-level uncertainty. The pooled number is inflated by large sites. **The paper should report the median per-site Spearman (0.875) as the primary ranking metric, not the pooled 0.907.** Or at minimum, explain the discrepancy.

### 6.4 "2-4x Smaller Median Error" for Storm Events

At Brandywine, the storm event median errors are +119% (v11) vs +165% (OLS). That is 1.4x, not 2-4x. At Valley Creek, it is +169% vs +591% (3.5x). At Ferron, it is -39% vs +124% (absolute values: 39% vs 124%, so ~3x). The "2-4x" claim holds for Valley Creek and Ferron but not for Brandywine. The paper should either qualify ("2-4x at two of three sites; 1.4x at the third") or use a more precise framing.

### 6.5 MedSiteR^2 95% CI in Abstract

The abstract states "95% CI: 0.36-0.44" for MedSiteR^2. The bootstrap results show [0.358, 0.440]. This is correct but unusually narrow for a CI based on 78 sites. The paper should note that this CI is conditional on the specific holdout partition and the spatial independence assumption (Section 6.4).

---

## 7. What's Understated

### 7.1 The Ferron Creek Result

Ferron Creek is the strongest validation site by daily metrics (R^2 = 0.76, Spearman = 0.96) and the only non-Pennsylvania site. It demonstrates transfer to a completely different geomorphic setting (Colorado Plateau, snowmelt-driven, semi-arid). The paper buries this behind Brandywine. Ferron should get equal billing.

### 7.2 The Between-Site vs Within-Site Variation Ratio

"CV = 4.37 vs 1.35 (3.2x ratio)" is one of the most important numbers in the paper. It quantifies what every USGS sediment hydrographer knows intuitively --- that turbidity-SSC relationships are more different BETWEEN sites than they are variable WITHIN sites --- but I have never seen it quantified at this scale. This finding should appear in the abstract and the Key Points.

### 7.3 The Bayesian Adaptation Breakthrough at Small N

The old 2-parameter linear correction produced R^2 = -0.012 at N=2 (catastrophic). Bayesian shrinkage produces R^2 = 0.49. The delta of +0.50 is extraordinary. At N=2 temporal, the delta is +1.197 (Bayesian +0.488 vs OLS -0.709). These numbers are buried in the Decision Log but barely mentioned in the paper. The Bayesian adaptation is the key to practical deployment and deserves a prominent figure.

### 7.4 The Temporal Adaptation Warning

The finding that temporal adaptation (first N chronological samples) can be WORSE than zero-shot (MedSiteR^2 = 0.39 at N=10 vs 0.40 at N=0) is operationally critical. Practitioners who collect their first 10 grab samples during summer baseflow will make their model WORSE. This needs to be a highlighted finding with a clear recommendation: "Target high-flow events in calibration sampling."

### 7.5 The Collection Method Effect

Collection method at SHAP rank 3 (0.349) is a major finding. It means the model has learned that the same turbidity reading corresponds to dramatically different SSC depending on how the sample was collected. The 4x difference between depth-integrated and auto-point is real physics (vertical concentration gradient), and the model partially compensates. This has implications for every operational turbidity program and deserves its own subsection in Discussion.

### 7.6 The Bug History as a Methodological Lesson

The project discovered and fixed 15+ bugs, many of which silently corrupted results (prune_gagesii destroying all watershed attributes, v9 training on holdout sites, QC vectorization bug applying no filtering). The Decision Log documents these transparently. While the paper need not catalog every bug, a brief paragraph in Methods about the importance of intermediate data validation --- especially the prune_gagesii lesson where a function produced garbage output instead of raising an error --- would be a genuine service to the ML-for-hydrology community.

---

## 8. Specific Recommendations for Paper

### 8.1 Structural Changes

1. **Add a "Tier Comparison" results subsection** showing Tier A (sensor-only) vs B (+ basic attributes) vs C (+ watershed). This is critical evidence that the model uses watershed context. Without it, a reviewer could argue the model is just a fancy turbidity regression.

2. **Split the load comparison into "total" and "daily/event" subsections.** The current draft blends these scales and the 2.6% headline obscures the daily-scale reality.

3. **Add a "Where the Model Fails" subsection in Discussion.** Use the disaggregated results (volcanic R^2 = 0.20, SSC <50 R^2 = -60.6, urban sites, auto-point R^2 = 0.24) to tell a coherent story about failure modes. This transforms limitations into scientific findings.

4. **Expand Section 6 (Limitations)** to include: (a) spatial autocorrelation of holdout sites, (b) within-site temporal autocorrelation reducing effective sample sizes, (c) clay mineralogy as an unobserved confound, (d) sensor saturation at extreme turbidity.

### 8.2 Metric Reporting Changes

5. **Replace pooled Spearman (0.907) with median per-site Spearman (0.875) as the primary ranking metric**, or report both and explain why they differ. The pooled number is driven by large sites and does not represent per-site ranking accuracy.

6. **Add the site_mean baseline** (MedSiteR^2 = 0.28, from the eval summary) alongside the model's 0.40 to show that the model meaningfully outperforms the simplest possible baseline.

7. **Report the fraction of sites with R^2 > 0.5 (36.5%)** alongside the median. This tells practitioners what fraction of sites get "good" predictions vs. "any signal at all."

8. **In load comparison tables, always show the daily load ratio alongside totals.** Brandywine: total ratio = 1.03, daily pbias = +59%. Both are true and both are needed.

### 8.3 Analysis Additions Before Submission

9. **Compute Moran's I on holdout residuals.** If spatial autocorrelation is significant, note it as a limitation and consider the implications for CI width.

10. **Produce year-by-year or water-year-by-water-year load comparisons at Brandywine.** This is the most important missing analysis. If year-by-year errors cancel to produce the 2.6% total, that is still a valid finding (error cancellation is a property of load estimation), but it must be documented.

11. **Add 2-3 sentences about the conformal interval failure at SSC > 2,000 mg/L (52% coverage).** The paper mentions this but does not discuss the operational implication: for extreme event loads --- the ones practitioners care most about --- the uncertainty bounds are unreliable.

### 8.4 Framing and Language

12. **Replace "without any site-specific calibration" with "without per-site parameter estimation"** throughout. The BCF is a form of calibration, just not per-site.

13. **Add the hysteresis type breakdown (39.5/24.4/36.1%) to Section 5.1.** This makes the hysteresis argument more specific and defensible.

14. **In Key Points, replace the third bullet** ("Site-to-site variation...3.2x larger") **with the actionable finding**: "Bayesian site adaptation with 2-10 grab samples raises median R^2 from 0.40 to 0.49; the first 10 samples deliver 95% of the adaptation benefit." The 3.2x ratio is important but the adaptation curve is more actionable for practitioners.

15. **Add a "Practical Guidance" box or table** summarizing: (a) where to use the model (screening, trend detection), (b) where NOT to use it (extreme events > 5,000 mg/L, volcanic sites, regulatory compliance without site calibration), (c) how many calibration samples to collect and when (target storms, not baseflow).

16. **Acknowledge the 80155 record's own uncertainty (typically 15-25% for annual loads).** The 2.6% match at Brandywine is within the reference uncertainty. This is a strong statement but must be grounded in the literature (Horowitz, 2003; Walling & Webb, 1996).

### 8.5 References to Add

17. **Horowitz, A.J. (2003)** — "An evaluation of sediment rating curves for estimating suspended sediment concentrations for subsequent flux calculations." Provides context for 80155 uncertainty.
18. **Landers & Sturm (2013)** — already cited but should be leveraged more for the grain-size hysteresis mechanism.
19. **Topping et al. (2007)** — acoustic backscatter vs optical methods; relevant to the Idaho/Palouse finding and the sensor physics discussion.
20. **Glysson (1987)** or **Colby (1956)** — classic references for the limitations of sediment rating curves that the OLS baseline represents.

---

## Summary Table

| Aspect | Verdict | Priority |
|--------|---------|----------|
| Core contribution (cross-site turbidity-SSC model) | Strong, novel, publishable | -- |
| Brandywine 2.6% load match | Headline-worthy but needs honest contextualization | HIGH |
| 3-site load comparison | Minimum viable; frame as proof of concept | MEDIUM |
| Disaggregated performance by geology | Excellent physics; understated in draft | HIGH |
| Bayesian adaptation | Undersold; the practical deployment story | HIGH |
| Spatial autocorrelation | Missing analysis; WRR will flag | HIGH |
| Year-by-year load breakdown | Missing analysis; critical for Brandywine claim | HIGH |
| Pooled Spearman vs per-site Spearman | Overstated; CI discrepancy must be resolved | HIGH |
| Collection method effect | Understated; major practical finding | MEDIUM |
| Extreme event uncertainty | Acknowledged but needs operational language | MEDIUM |
| Bug history transparency | Commendable; brief paper mention warranted | LOW |

---

*Assessment prepared 2026-04-02. I am available for follow-up discussion on any of these points. The project is doing strong work --- the revisions I recommend are about making the paper bulletproof for WRR review, not about fundamental methodology changes.*
