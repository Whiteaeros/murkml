# Phase 4 Diagnostic Review — Dr. Marcus Rivera

**Date:** 2026-03-30
**Reviewer:** Dr. Marcus Rivera (ret. USGS Water Resources Division, 20 years sediment transport & surrogate regression)
**Document reviewed:** PHASE4_OBSERVATIONS.md
**Model version:** murkml-4-boxcox (holdout evaluation)

---

## Overall Assessment

I'll say this up front: the diagnostic work here is better than what I see in most published surrogate-regression papers. The disaggregation by geology, collection method, turbidity band, SSC band, and hydrologic condition is exactly what reviewers should demand and almost never get. The fact that you did it voluntarily tells me you're taking the science seriously. That said, the numbers tell a complicated story, and some of what I see would keep me up at night if this were going operational.

---

## What Stands Out

### The Good

**Geology matters and you proved it.** R² of 0.884 on undifferentiated sedimentary vs 0.326 on volcanic is the kind of result that makes physical sense. Volcanic watersheds produce fine ash-derived clays and amorphous silica that scatter light differently per unit mass. Carbonate terrain produces coarser, denser particles where turbidity tracks mass more linearly. The fact that your model captures this distinction through watershed features rather than explicit calibration is genuinely impressive.

**Hysteresis detection is working.** Rising limb R²=0.535 vs falling limb R²=0.648 — the spread is real and the direction is correct. In my experience building per-site models, I never had a hysteresis feature because I never had enough samples on the rising limb of any given event at any given site. The cross-site approach gives you something single-site OLS fundamentally cannot.

**First flush performance is surprisingly good.** R²=0.864 on flush events, better than the overall model. That's backwards from what I'd expect. Usually first flush is where models blow up because the sediment supply is decoupled from the turbidity signal — you get massive SSC spikes from channel scour that overwhelm whatever the turbidity sensor reads. The fact that your engineered features (`flush_intensity`, `precip_30d`) are capturing this is a strong signal that the feature engineering is doing real work, not just adding noise.

**The >1000 FNU performance (R²=0.805) is remarkable** for a cross-site model. At those turbidity levels, you're in a regime where most per-site OLS models are extrapolating beyond their calibration range. Having 43 samples from multiple sites in that range gives you something the traditional approach lacks entirely.

### The Bad

**Pooled R²=0.665 with MAPE=57.7% is not operational-grade.** Let me be blunt: if someone brought me a per-site model with 58% MAPE, I'd send them back to collect more samples. For a cross-site zero-shot model, it's a proof of concept. For operational deployment, it's not there yet. The within-2x of 62.2% means nearly 4 in 10 predictions are off by more than a factor of 2. That's not tight enough for regulatory reporting, load calculations, or permit compliance.

**The low-SSC overprediction (+121% bias) is a serious problem.** I know the absolute errors are small (median ~10 mg/L), but this matters enormously for water quality applications. If a stream's actual SSC is 15 mg/L and you report 33 mg/L, you've just told a water manager they have a sediment problem they don't have. In TMDL contexts, that kind of systematic overprediction at baseflow concentrations inflates load estimates, because baseflow accounts for a huge fraction of total time even though it's a small fraction of total load. You'd be systematically overestimating annual sediment loads by a significant margin for any watershed that spends most of its time at low SSC.

**The compression problem at the extremes (-47% bias at >5000 mg/L) is equally dangerous in the other direction.** If the model underpredicts by half during the events that move 80% of annual sediment, your load estimates are garbage on the other end too. The low-end overprediction and high-end underprediction are two faces of the same coin: the model regresses toward the grand mean. Tree-based models do this by construction — they can only predict values within the range of their training leaf averages, and those averages get pulled toward the center.

**The "unknown" collection method anomaly (R²=0.873) is a red flag, not a mystery.** I'd bet money those 13 sites happen to be high-variability sites in well-behaved geologies. Check their SSC standard deviations and dominant geology. If they cluster in Q3-Q4 variability and sedimentary geology, you have your answer — it's site selection, not a modeling artifact. But you need to verify this, because if the model is using "unknown" as a learned shortcut, you have a feature leakage problem that will bite you the moment you deploy on a new site where you DO know the collection method.

---

## Specific Numbers That Concern Me

1. **Auto-point R²=0.377 vs depth-integrated R²=0.548.** This 0.17 gap is real physics. Point samples miss the vertical concentration gradient — coarser particles settle toward the bed, so a point sample at the sensor intake systematically undersamples the high-SSC fraction. The model can't fully correct for this because it doesn't know the vertical profile. This matters for your deployment story: most operational turbidity sensors are fixed-point installations, and your model works worst on that exact collection method.

2. **HUC19 Alaska: R²=-10.5, bias=+262%.** One site, 21 samples, and the model is predicting 3.6x the actual SSC. This is almost certainly a glacial flour site. Glacial flour is extremely fine (silt/clay), stays in suspension forever, and scatters light efficiently. You get very high turbidity per unit mass, so the turbidity-to-SSC conversion factor is much lower than for continental sediment. The model has never seen this and has no way to learn it from 357 continental training sites. Exclude Alaska and Hawaii from your reported metrics or report them separately. They are not the same population.

3. **Q1 low-variability sites: R²=0.094, bias=+33%.** An R² of 0.094 means the model explains less than 10% of the variance. The site mean would do nearly as well. For these sites, murkml is adding noise, not signal. You need to either: (a) detect these sites automatically and fall back to site-mean prediction, or (b) set a minimum-variability threshold below which the model declines to predict. Operationally, a model that knows when it doesn't know is far more valuable than one that always gives an answer.

4. **<10 FNU turbidity band: within-2x = 50.4%.** Coin flip accuracy. At low turbidity, the relationship between FNU readings and suspended sediment mass is genuinely weak — dissolved organic carbon, algae, fine colloids, and instrument noise all contribute to the turbidity signal. This is not fixable with better modeling. It's a sensor limitation. If turbidity is <10 FNU, you're probably better off with a grab-sample program than a surrogate model.

5. **Site adaptation with 10 samples only reaches R²=0.457** (barely matching zero-shot 0.472). That adaptation curve is deeply disappointing compared to the v2 numbers. Something changed structurally between v2 and v4 that hurt the adaptation pathway. The note about 2-parameter linear correction overfitting with few samples is correct — you need shrinkage, or better yet, a Bayesian update that blends the global prediction with local evidence proportional to local sample size.

---

## Physics-Based Tests That Are Missing

1. **Particle size distribution effects.** You have geology as a proxy, but you should test the model against sites where you know the dominant particle size (D50). USGS bed-material data (parameter codes 80164, 80165) exists for many sites. The turbidity-SSC slope is fundamentally controlled by particle size: fine clay gives high turbidity per unit mass, coarse sand gives almost none. If your model fails systematically on fine-sediment vs coarse-sediment sites, that tells you the geology proxy isn't enough.

2. **Diurnal cycling.** In rivers with significant algal productivity (eutrophic lowland rivers), turbidity has a diurnal signal from algal growth/die-off that has nothing to do with SSC. Test whether the model's residuals show diurnal patterns at sites with known algal issues. The `hour_sin`/`hour_cos` features should capture some of this, but only if the pattern is consistent across sites.

3. **Post-fire watersheds.** Burned watersheds produce SSC that's 10-100x normal for the same turbidity because the sediment is fine ash with different optical properties. Do any of your training or holdout sites have wildfire history? If not, this is a critical deployment gap for western US applications.

4. **Bank erosion vs upland erosion.** Rising-limb sediment is typically bank-derived (coarse, local), while falling-limb sediment is upland-derived (fine, distal). The model captures the timing difference through `rising_limb` but not the particle-size difference. This matters because bank erosion produces SSC with a fundamentally different turbidity relationship than sheet erosion.

5. **Freeze-thaw dynamics.** In your north Idaho context specifically: spring breakup produces massive sediment pulses from bank collapse and ice-dam releases. These are neither "snowmelt" nor "first flush" — they're geomorphic events. Your holdout set has no sites that could test this.

6. **Sensor fouling detection.** Operational turbidity sensors accumulate biofilm and sediment deposits that cause drift. A fouled sensor reads high, and the model would underpredict SSC (because the "turbidity" is partly biofilm, not sediment). Test whether model residuals correlate with time-since-last-maintenance at sites where you have maintenance logs.

---

## Missing Metrics

1. **Nash-Sutcliffe Efficiency (NSE).** Yes, you must compute this. It's the standard of practice in hydrology. NSE and R² are mathematically identical for raw predictions, but when you're applying bias corrections (BCF), they diverge. Report NSE alongside R².

2. **Log-space NSE (log-NSE).** Standard for evaluating low-flow and low-concentration performance. It downweights the extreme values that dominate native-space NSE and tells you how the model performs in the regime where it spends most of its time.

3. **Percent bias decomposition.** Break total bias into: (a) mean bias (systematic offset), (b) amplitude bias (under/over-estimating the range), and (c) timing/correlation bias. The KGE components (alpha, beta, r) partially do this, but explicit decomposition helps diagnose whether the problem is "wrong level" vs "right level, wrong timing."

4. **Volume error / load error.** If this model is ever used for sediment load estimation (and it will be — that's the primary use case for continuous SSC), you need to compute the cumulative load error over the holdout period at each site. A model with 58% MAPE can still get loads right if the errors are symmetric and random. A model with 30% MAPE can get loads catastrophically wrong if the errors are biased in one flow regime. Compute load ratios (predicted cumulative load / observed cumulative load) per site.

5. **Flow-duration weighting.** Report model accuracy as a function of flow exceedance probability. Errors at Q5 (high flow) matter 10x more for loads than errors at Q50. If your model is accurate at Q50 but biased at Q5, the load estimates are useless despite good-looking pooled metrics.

6. **Prediction interval coverage.** You mention uncertainty bounds briefly but don't report what fraction of observations fall within your predicted uncertainty intervals. The standard test: does a 90% prediction interval actually contain 90% of observations? If it contains 70%, your uncertainty is underestimated and users will make bad decisions trusting it.

7. **Spatial autocorrelation of residuals.** Are nearby holdout sites systematically biased in the same direction? If so, the model has a spatial blind spot — probably a geological or land-use gradient it's not capturing. Moran's I on the site-level residuals, or simply map the residuals and look for spatial clustering.

---

## Answers to Your 8 Questions

### Q1: The "unknown" collection method anomaly

Investigate, don't speculate. Pull those 13 sites and check: (a) their SSC standard deviation quartile, (b) their dominant geology, (c) their turbidity range. I'd bet they cluster in the "easy" quadrant — high-variability sedimentary sites. If that's the case, the R²=0.873 is site selection, not a modeling artifact, and resolving the collection method won't hurt.

If they DON'T cluster there, you have a problem: the model is using "unknown" as a free parameter. Test this directly — retrain with "unknown" remapped to the most common method (auto_point) and see if those sites' performance degrades. If it does, the categorical encoding is leaking information.

### Q2: Low-SSC bias and loss function

Yes, Box-Cox lambda=0.2 compresses low values but not as aggressively as log. The +121% bias at low SSC is partly the BCF overcorrection (Snowdon BCF of 1.364 inflates everything, and the inflation hurts most at low concentrations where the absolute values are small) and partly the tree model regressing toward the training mean.

Asymmetric loss won't fix this cleanly. What you need is a two-regime approach: separate handling for SSC < some threshold (say 50 mg/L) where the model defaults to a more conservative estimate. Or, more practically, apply the BCF only above a threshold where it's needed and use the raw (un-corrected) predictions at low SSC where the retransformation bias is the dominant error source.

### Q3: Within-tier R²

Yes, within-tier R² is almost always negative for any regression model evaluated in narrow bands. Stop reporting it within tiers. Use MAPE, median absolute error (MAE), and within-factor-of-2 as your within-tier metrics. For the overall model, R² and KGE are fine. For disaggregated evaluation, MAPE and within-2x tell the story.

### Q4: Spring SSC/turbidity ratio

It's both. Your holdout is biased toward the mid-latitude eastern US where "spring" means thunderstorms on freshly tilled agricultural fields — maximum sediment supply with maximum erosive rainfall. That gives you high SSC per unit turbidity. Actual snowmelt in northern/mountain watersheds produces the opposite: glacially-derived fine sediment and low-energy flow that gives high turbidity per unit SSC.

You cannot test snowmelt dynamics with this holdout set. You need sites above 45°N or above 2000m elevation with winter snowpack. Until you have those, any claims about snowmelt performance are unsupported.

### Q5: Other physics to test

- **Diurnal cycling** in eutrophic streams (algae confounds turbidity)
- **Post-wildfire response** (ash changes the turbidity-SSC relationship for 2-5 years)
- **Freeze-thaw bank collapse** (massive SSC spikes with moderate turbidity)
- **Construction/land disturbance** (urban/suburban sites with active earthwork)
- **Reservoir releases** (clear-water releases scour downstream, producing SSC with minimal turbidity signal)
- **Tide-influenced sites** (if any) — tidal resuspension creates a semi-diurnal SSC cycle that's predictable but not from turbidity alone

### Q6: High-turbidity vs low-turbidity performance

Yes, this is expected and it's fundamental. At high turbidity, the signal-to-noise ratio is high — turbidity IS the SSC signal, and other confounders (DOC, algae, instrument noise) are negligible in proportion. At low turbidity, the signal-to-noise ratio is terrible — a 3 FNU reading could be 5 mg/L of silt, or 1 mg/L of silt plus 2 FNU of dissolved tannins, or sensor noise. No model can resolve this from turbidity alone.

Yes, low-turbidity predictions should carry much wider uncertainty bounds. I'd go further: below 10 FNU, the model should flag predictions as "low confidence" and report a range rather than a point estimate. For many applications, knowing "SSC is probably between 5 and 50 mg/L" is more honest and more useful than a false-precision estimate of "SSC = 22 mg/L."

### Q7: Auxiliary data for sensor saturation

In order of usefulness:

1. **Discharge rate-of-change (dQ/dt).** The single best auxiliary variable for extreme SSC. When Q is rising fast and turbidity is clipped, dQ/dt tells you how extreme the event is. Available at every gaged site in real time.
2. **Cumulative event precipitation.** Total rainfall since event onset, from gridded products (Stage IV, MRMS). Tells you the total energy input driving erosion.
3. **Antecedent soil moisture.** From NLDAS or soil moisture networks. Dry antecedent conditions + intense rain = maximum sediment production. This is essentially your `flush_intensity` concept extended.
4. **Upstream turbidity.** If an upstream gage is NOT saturated, its turbidity gives you information about what's coming downstream. This is a network-level feature most people don't think about.
5. **Acoustic backscatter.** Some USGS sites have acoustic Doppler instruments that measure backscatter, which correlates with SSC independently of turbidity. But availability is limited.

Do NOT use soil moisture or precipitation as primary predictors in lieu of turbidity — they're too noisy. Use them as auxiliary features that activate only when turbidity exceeds a saturation threshold.

### Q8: Standard goodness-of-fit statistics

You need:

- **NSE and log-NSE** — non-negotiable for hydrological modeling papers
- **KGE decomposition** — you have KGE and alpha, also report beta (bias ratio) and r (correlation) separately
- **Percent bias (PBIAS)** — you're reporting bias, just make sure it matches the standard definition: 100 * sum(pred - obs) / sum(obs)
- **Volume/load error ratio** — cumulative predicted / cumulative observed per site
- **Kling-Gupta Skill Score** if you want to claim the model beats a baseline (KGSS = (KGE_model - KGE_baseline) / (1 - KGE_baseline))
- **Spearman rank correlation** alongside Pearson — tree models often rank correctly even when magnitudes are wrong. Spearman tells you about ranking skill independent of bias.

What you do NOT need and should not waste time on: AIC/BIC (not meaningful for gradient-boosted trees), RMSE alone (only meaningful relative to the range of SSC), or percent of variance explained (just use R²).

---

## What I'd Need Before Trusting This Operationally

Let me be clear about what "operationally" means: I mean a water manager using these numbers to make decisions about permit compliance, TMDL allocations, or infrastructure operations.

1. **Per-site validation on at least 5 target sites.** I want to see site-specific adaptation curves at real sites where I know the ground truth. The pooled numbers are encouraging for research but meaningless for an operator who cares about one stream. Show me that site adaptation with 20-30 grab samples gets within-2x above 80% and MAPE below 30% at specific sites. The current 10-sample adaptation barely matching zero-shot is a dealbreaker for the "easy onboarding" pitch.

2. **Load comparison against traditional per-site OLS.** At sites where USGS has published surrogate regression models, run your model and compare cumulative load estimates over the same period. If murkml gets within 20% of the per-site OLS load, that's a win. If it's off by 50%, the model is a curiosity, not a tool.

3. **Honest uncertainty quantification.** Prediction intervals that are calibrated — 90% intervals that actually contain 90% of observations. Quantile regression forests, conformal prediction, or at minimum a site-specific residual bootstrap. An operator needs to know "SSC is 150 mg/L plus or minus X" and trust that X means something.

4. **Exclusion criteria.** A clear, documented set of conditions under which the model declines to predict: turbidity < 5 FNU (noise-dominated), turbidity > sensor max (clipped input), site geology = volcanic/glacial (outside training domain), SSC variability < threshold (model adds no value). A model that knows its own limits is worth 10x one that always answers.

5. **Alaska and Hawaii removed from pooled metrics.** They're different planets geologically. Report them separately or exclude them. Including them in pooled statistics muddies the picture for the 95% of applications in the continental US where the model actually has a chance of working.

6. **The "unknown" collection method resolved or at minimum characterized.** I can't defend a model in a methods section that gets its best performance on data where we don't know how the samples were collected.

7. **Seasonal load breakdown.** Show me the model's accuracy in winter, spring (storm season), summer (low flow), and fall. If the model is accurate 9 months of the year but misses the spring flush by 40%, the annual load estimates are wrong even if the annual MAPE looks reasonable.

---

## Bottom Line

This is the strongest cross-site turbidity-SSC model I've seen attempted. The feature engineering (hysteresis, flush intensity, geology) is thoughtful and physically grounded. The diagnostics are honest and thorough — you're not hiding the ugly numbers.

But honest diagnostics also mean honest conclusions: this model is not ready for operational deployment in its current form. It's a research prototype that demonstrates cross-site modeling is feasible and that watershed features improve transferability. The path from here to an operational tool runs through better site adaptation (the current curve is flat and disappointing), honest uncertainty quantification, and targeted data expansion to fill the geological and climatic gaps in the training set.

The compression problem (overpredicting low SSC, underpredicting extreme SSC) is the central technical challenge. It's partly loss function, partly tree-model architecture, and partly sensor limitation. Solving it will require a combination of better retransformation correction (not just a single BCF), regime-dependent prediction strategies, and auxiliary data for the sensor saturation regime.

Write the paper about what the model CAN do — cross-site transferability, the role of watershed geology, hysteresis detection — and be honest about what it can't. That's a publishable and useful contribution. Don't oversell it as operational-ready, because it isn't, and reviewers who've built per-site models (people like me) will tear it apart if you claim otherwise.

---

*Dr. Marcus Rivera*
*Retired, USGS Water Resources Division*
*Review completed 2026-03-30*
