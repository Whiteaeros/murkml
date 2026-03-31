# Dr. Marcus Rivera — Data Patterns Review
## 2026-03-30

**Reviewer background:** 20 years USGS Water Resources Division. Sediment transport, surrogate regression, turbidity-SSC method development. Thousands of datasets, dozens of WRR reviews.

---

## Question 1: What other patterns should we look for in this data?

There are several things I'd dig into that aren't in the briefing:

**Hysteresis classification.** You have 213 site-days with 10+ samples (Pattern 9) but I don't see any analysis of clockwise vs. counterclockwise hysteresis loops in the turbidity-SSC-discharge space. This is fundamental sediment transport physics. Clockwise hysteresis means sediment source is proximal and exhausts before the flow peak. Counterclockwise means distal sources or bank collapse on the falling limb. Your model should perform differently on these two regimes, and if it doesn't, that's a red flag that it's not learning the right thing. Classify each storm event and stratify your errors by hysteresis type.

**Spatial autocorrelation of residuals.** Are sites that are geographically close to each other making similar errors? Run a Moran's I on the site-level median residuals using the site coordinates. If there's significant spatial autocorrelation, your model is missing a regional covariate (geology, land use, sediment mineralogy) and a WRR reviewer will catch this immediately.

**Grain size distribution effects.** The SSC/turbidity ratio differences by collection method (Pattern 6) are partly about vertical grain size sorting. Auto_point samplers near the bed capture more sand, which adds mass but not much turbidity. Depth-integrated samples average over the profile. If you have any concurrent bedload or grain size data (USGS parameter codes 80154, 70331), even at a handful of sites, you should check whether the model's residuals correlate with percent sand. This is THE classic confounder in turbidity-SSC work.

**Sensor type and range effects.** Not all turbidity sensors are created equal. The Hach 2100AN and the YSI 6136 read differently on the same water sample, especially above 1000 FNU. Are you tracking which sensor model is deployed at each site? If not, at minimum check whether your errors cluster by the turbidity parameter code (63680 vs 63676 vs others). Mixing FNU, NTU, and NTRU without accounting for sensor response curves introduces systematic noise.

**Discharge-normalized SSC.** Look at SSC/Q ratios across sites. Sites with high SSC/Q have easily mobilized sediment (fine-grained, disturbed catchments). Sites with low SSC/Q are armored or supply-limited. This ratio should predict your model's error pattern. If it doesn't, something is wrong.

**First-flush vs. sustained events.** In the ISCO burst data, does the model's error change over the course of a storm event? If accuracy degrades as the event progresses, the model may be over-relying on turbidity magnitude and not capturing sediment exhaustion dynamics.

---

## Question 2: Adaptation hurting extremes at N=20

This is textbook overfitting to the wrong part of the distribution. Here's what's happening mechanistically:

When you give the Bayesian adaptation 20 calibration samples, the majority of those samples are from normal/baseflow conditions (because that's what most samples are). The adaptation shifts the site-specific parameters to minimize error on those normal samples. But the turbidity-SSC relationship during storms is physically different — it's driven by mechanical erosion and sediment mobilization, not by DOM and biofouling. By tuning to baseflow, you're rotating the regression away from the storm relationship.

**What I'd do:**

1. **Flow-stratified adaptation, yes, absolutely.** Split calibration samples into "event" (above some percentile of site-specific discharge, or above a rate-of-change threshold on turbidity) and "baseflow." Adapt separately. This is the single most important fix.

2. **Cap adaptation magnitude.** Put a prior or hard constraint on how far the adaptation can move the prediction from the zero-shot estimate. Something like: the adapted prediction can't differ from zero-shot by more than X% at turbidity values above the 90th percentile. This protects the extremes that the pooled model already handles well.

3. **Weighted adaptation loss.** Weight the calibration samples by turbidity magnitude or by SSC magnitude when computing the adaptation parameters. This prevents the baseflow samples from dominating.

4. **Show us the adaptation at N=1, 5, 10, 20 as individual curves on a turbidity-SSC scatterplot for 3-4 example sites.** I want to see the regression line rotating. If the line is flattening at high turbidity at N=20, that confirms the mechanism I described.

5. **Report performance at N=20 for extremes separately for sites where the 20 samples include at least one storm sample vs. sites where all 20 are baseflow.** I bet the collapse only happens when there are no storms in the calibration set.

The N=20 collapse from 0.722 to 0.295 is severe. That's not a subtle degradation, that's the model becoming actively harmful for flood-event estimation. If you're going to recommend this tool for operational use, you need a guardrail that prevents this. A WRR reviewer will hammer you on this.

---

## Question 3: Additional validation tests for paper-readiness

Here's what I'd demand as a reviewer, roughly in priority order:

**A. Holdout by HUC or ecoregion, not just by site.** Your LOGO-CV leaves out individual sites, but sites in the same watershed share geology, land use, and climate. If your training set includes 5 sites on the Yakima and you test on a 6th Yakima site, that's not truly independent. Do a leave-one-HUC4-out or leave-one-ecoregion-out cross-validation. If performance drops substantially, your model is memorizing regional patterns, not learning generalizable physics.

**B. Performance stratified by geology.** Show me error metrics broken out by dominant lithology (at least: igneous, sedimentary, metamorphic, unconsolidated). The turbidity-SSC relationship is fundamentally different in clay-dominated vs. sand-dominated catchments. If your model handles all of these equally well, that's a genuine contribution. If it fails on one, you need to document that limitation.

**C. Comparison with simple site-specific regressions.** At every site where you have N >= 20 samples, fit a simple log(SSC) = a + b*log(turbidity) regression and compare its performance to your model at N=0 and at N=10 adaptation. This is the baseline that every practitioner currently uses. If your model at N=0 doesn't beat the simple regression at N=20, that's fine — but you need to show where the crossover is. "How many samples does the practitioner need before the old method catches up?" That's the value proposition.

**D. Performance on rising vs. falling limb.** At the ISCO burst sites, tag each sample as rising or falling limb based on turbidity rate of change. Report metrics separately. Rising limb is always harder (sediment pulse arrives before the turbidity signal fully develops). If your model shows no difference, you should question whether it's actually resolving event dynamics or just doing static regression.

**E. Residual analysis.** Show Q-Q plots of residuals in log space, by site and pooled. Show residuals vs. predicted values. Show residuals vs. time (looking for drift). A reviewer will want to see that errors are homoscedastic in log space and don't have systematic structure.

**F. Bootstrap confidence intervals on all reported metrics.** Don't just report point estimates. Bootstrap the site-level metrics (resample sites, not individual observations) and report 95% CIs. MedSiteR² of 0.486 with a CI of [0.30, 0.65] tells a very different story than [0.45, 0.52].

**G. Detection limit and censored data handling.** How are you handling SSC values at or near the detection limit? If you have many values reported as "<1 mg/L" or similar, and you're treating them as 0 or 0.5, that contaminates your baseflow performance metrics. Document your approach.

---

## Question 4: Red flags in the patterns found

Several things concern me:

**Red flag 1: The "weekend effect" (Pattern 2) — the model performing BETTER on storms than calm conditions.** This is actually expected physics (storms produce a cleaner turbidity-SSC signal), but the fact that you frame it as a temporal pattern rather than a hydrologic regime pattern worries me. Make sure you aren't inadvertently encoding day-of-week as a feature. If hour or day-of-week is in the feature set, that's a proxy for collection method, not for hydrology. The model would learn "if it's Saturday, predict higher SSC" which is not generalizable.

**Red flag 2: Only 3 supply-limited sites out of 182 (Pattern 7).** This is suspicious. In my experience, supply limitation is common in arid watersheds, post-fire landscapes, and anywhere with reservoir regulation. Either your site selection is biased toward perennial, unregulated, humid catchments, or your method for detecting supply limitation is too coarse. Check whether you're capturing sites in the arid West, post-fire catchments, or regulated rivers. If not, you need to document this as a dataset limitation, because your model won't generalize to those settings.

**Red flag 3: The SSC trends (Pattern 5) — 125 of 254 sites showing significant trends.** Half your sites have non-stationary SSC. This means your assumption that there's a stable turbidity-SSC relationship to learn is violated at many sites. Are you checking whether the training data spans the full period of record? If a site's SSC doubled over 10 years, and you train on the early period, your predictions for the late period will be systematically biased. Run a test: at the trending sites, train on the first half and test on the second half. If error is much worse than random-split CV, you have a stationarity problem that must be disclosed.

**Red flag 4: Vault NSE of 0.164.** That's barely above zero. Yes, MedSiteR² is 0.486, which means the model works at most sites but there are a few sites where it's catastrophically wrong, pulling the pooled NSE down. Identify those sites. Are they the supply-limited sites? The ones with extreme trends? If 3-5 bad sites are destroying your NSE, you need to characterize what's different about them and report it honestly. Don't hide behind the median.

**Red flag 5: External NTU zero-shot MAPE of 90%.** That's not "validation," that's the model failing. I understand it drops to 45% at N=10, but the zero-shot NTU performance needs a frank discussion. The NTU-to-FNU conversion is not just a scaling factor — the spectral response is fundamentally different (90-degree vs. multi-angle scattering). If your model was trained on FNU, applying it zero-shot to NTU sites is like using a rating curve from one river on another. The N=10 improvement is real and valuable, but the zero-shot number shouldn't be presented as a success.

---

## Question 5: What figures should be in the paper?

**Figures that must be in the paper:**

1. **Turbidity-SSC scatterplot colored by collection method** (Pattern 6). Show the systematic offset between auto_point, depth-integrated, and grab. This is a publishable finding on its own — it quantifies a sampling bias that practitioners know intuitively but rarely see documented with n=35,000. Include the regression lines.

2. **Adaptation curve: performance vs. N** with separate lines for extreme events and normal conditions (Pattern 4). This is the most important figure in the paper. It shows the model's value proposition AND its failure mode in one plot. Mark where N=20 destroys extremes.

3. **Map of site locations colored by model performance** (MedSiteR² or site MAPE). This immediately shows spatial patterns and lets the reader assess geographic generalizability. Overlay HUC2 boundaries or ecoregions.

4. **Residual plots**: (a) predicted vs. observed in log-log space with 1:1 line, (b) residuals vs. predicted, (c) residuals vs. discharge. These are mandatory for any regression paper.

5. **Comparison with site-specific regression at various N** (see Question 3C). Bar chart or line plot showing your model's error at N=0, 5, 10, 20 vs. a simple turbidity-SSC regression at the same N. This is the figure that sells the paper.

6. **Storm event time series at 2-3 ISCO sites** showing observed SSC, model-predicted SSC, turbidity, and discharge on the same time axis. Pick one site where the model works well and one where it struggles. Nothing communicates model capability like a time series that a practitioner can look at and evaluate intuitively.

**Figures for supplement:**

- The time-of-day / day-of-week patterns (Patterns 1-2) belong in the supplement. They're interesting but they're really about sampling design, not about the model.
- Seasonal SSC pattern (Pattern 10) — supplement. It's expected and not novel.
- Conductance anti-correlation (Pattern 8) — supplement unless you can show it improves predictions.
- Feature importance plot — supplement or main text depending on space.

---

## Question 6: What are we missing?

**A. Uncertainty quantification.** You're reporting point predictions. Every operational user needs uncertainty bounds. Even if you use the quantile regression outputs you already have (I see MultiQuantile in earlier reviews), you need to validate that those uncertainty bounds have correct coverage. Do the 90% prediction intervals actually contain 90% of observations? If coverage is 70%, your uncertainty estimates are overconfident and operationally dangerous.

**B. The sand fraction problem.** Turbidity is mainly driven by fine particles (silt, clay, organics). SSC includes sand. In sand-rich rivers, two samples can have identical turbidity but wildly different SSC because of varying sand content. This is the fundamental physical limitation of ANY turbidity-SSC model, and your paper needs to confront it directly. If you have any sites with concurrent sand/fine split data, test whether your residuals correlate with sand fraction. If you don't have that data, cite Glysson et al. (2000) and Topping et al. (2011) and discuss it as a known limitation.

**C. What happens at turbidity values outside the training range?** Your training data probably maxes out somewhere. What does the model predict at 5000 FNU? 10000 FNU? Does it extrapolate sensibly or does it blow up? Extreme flood events are exactly when people need predictions most, and they'll push beyond your training envelope. Show an extrapolation test, even if it's synthetic.

**D. Sensor fouling and maintenance artifacts.** Real-world turbidity sensors drift and foul. The classic signature is a sudden drop in turbidity when the wiper cleans the sensor, or a gradual upward drift between maintenance visits. Are you filtering for these? If your training data includes fouled readings paired with manually-collected SSC samples, you're teaching the model to associate artificially high turbidity with whatever SSC happens to be present. At minimum, flag observations where turbidity is anomalously high relative to discharge and check whether they're fouling artifacts.

**E. The "is this actually better than existing USGS methods?" question.** USGS has a well-established protocol (Rasmussen et al., 2009, TM 3-C4) for developing turbidity-SSC regressions. Your paper needs a clear-eyed comparison with that approach. Not just "our model is general purpose" but a quantitative comparison: at how many sites does your zero-shot model beat a site-specific OLS regression with N=10, 20, 50 samples? That's the comparison that matters to the people who would actually use this.

**F. Multi-collinearity in your feature set.** 72 features is a lot. How many of them are correlated with each other at r > 0.9? Do you have VIF analysis? Even with tree-based models that handle collinearity gracefully in terms of prediction, high collinearity makes feature importance unstable and misleading. If you're going to discuss which features matter (and you should), you need to address this.

**G. The disconnect between pooled NSE and MedSiteR².** Vault pooled NSE is 0.164 while MedSiteR² is 0.486. That's a huge gap. It means you have outlier sites that are severely degrading the pooled metric. I said this above but I want to be very explicit: you MUST characterize those failure sites. What's different about them? Can you predict in advance which sites the model will fail on? If you can build a "model applicability" screening criterion (like: the model works when X > threshold), that's extremely useful operationally and it would significantly strengthen the paper.

**H. Reproducibility.** Are your data sources, processing steps, and model configurations documented well enough that someone else can reproduce your results? For a WRR paper, you'll need a data availability statement and ideally a public code repository. Start preparing that now.

---

## Summary of Priority Actions

The three things that would most strengthen this paper, in my professional judgment:

1. **Characterize and fix the N=20 extreme collapse** with flow-stratified adaptation. This is your biggest vulnerability.
2. **Compare against site-specific OLS at various N** (Rasmussen-style regressions). This defines your value proposition.
3. **Identify and characterize the failure sites** dragging vault NSE to 0.164. Turn a weakness into a contribution by explaining WHY the model fails where it does.

Everything else matters, but these three will determine whether the paper is accepted or desk-rejected.

---

*Dr. Marcus Rivera*
*USGS Water Resources Division (ret.)*
