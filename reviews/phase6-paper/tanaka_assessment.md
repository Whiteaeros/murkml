# Tanaka Assessment: murkml WRR Paper Review

**Reviewer:** Dr. Richard Tanaka, Professor of Watershed Hydrology and Water Quality Monitoring
**Date:** 2026-04-02
**Paper:** "Cross-Site Suspended Sediment Estimation from Continuous Turbidity Using Gradient Boosting: A Continental-Scale Assessment"
**Model:** CatBoost v11, 260 training sites, 78 holdout sites, 405 total

---

## 1. Scientific Contribution Assessment

### Does this advance watershed science understanding?

Yes, but the contribution is more nuanced than the draft currently frames it. This paper makes three genuine scientific contributions:

1. **Quantifying the transferability boundary for turbidity-SSC relationships.** The CV ratio finding (between-site 4.37 vs within-site 1.35, ratio 3.2x) is, to my knowledge, the first rigorous continental-scale quantification of this heterogeneity. Practitioners have known for decades that turbidity-SSC regressions don't transfer, but nobody has put a number on *how much* they don't transfer and decomposed *why*.

2. **Demonstrating that turbidity captures event-scale information inaccessible to discharge.** The Brandywine load comparison (2.6% total error vs 67% for OLS) is compelling, and the hysteresis mechanism is well-articulated. This is not a new finding in sediment transport physics, but quantifying the advantage at a continental scale with a cross-site model is new.

3. **Establishing the adaptation effort curve.** The finding that N=10 random samples captures most of the adaptation benefit has direct management implications. The temporal vs random comparison (0.389 vs 0.493 at N=10) reveals a non-obvious operational trap.

### Is there a testable hypothesis?

The stated hypothesis --- "adding continuous turbidity as a primary input to a cross-site model will substantially improve SSC estimation over discharge-only approaches" --- is reasonable but insufficiently specific. It is trivially true (turbidity IS a sediment proxy, so adding it to a sediment model obviously helps).

**The real hypothesis should be:** *The primary barrier to cross-site turbidity-SSC prediction is between-site variation in the optical-to-gravimetric conversion, which is governed by watershed geology and particle size distribution. Given sufficient geologic context, a cross-site model can match site-specific regressions with minimal calibration.*

This reframing is falsifiable (it predicts that geologic context explains the model's successes and failures), and the disaggregated results already support it. The paper should be restructured around this hypothesis.

### Does it explain WHY?

Partially. The discussion correctly identifies geology as the primary driver and sketches the optical-gravimetric mechanism. But the connection from geology -> particle size -> scattering properties -> turbidity-SSC slope is underdeveloped. The paper asserts this chain but does not demonstrate it with data. For example:

- The paper reports carbonate R^2 = 0.81 vs volcanic R^2 = 0.20, but does not show the per-site turbidity-SSC slopes in these categories or relate them to known particle size distributions.
- The SHAP analysis shows geology features matter, but does not show HOW they modulate the relationship (e.g., do they shift the intercept? The slope? Both?).
- The power law slope analysis (median 0.952, range 0.29-1.55) is mentioned in the results log but not in the paper, and it should be --- it IS the physical finding.

### Comparison to published work

- **Song et al. 2024 (LSTM, median R^2 = 0.55):** The paper frames this as a comparison but the models serve different purposes. Song predicts SSC from discharge at sites without turbidity; this paper predicts SSC from turbidity at sites with sensors. They are complementary, not competing. The draft acknowledges this in Section 5.5, which is good. The Spearman comparison (0.907 vs unspecified for Song) is valid but needs more care --- Spearman is not directly comparable to R^2.

- **Zhi et al. 2024 (deep learning WQ):** Cited but not meaningfully compared. The paper should note that Zhi focuses on dissolved species (primarily conductance-based proxies), where the physics is fundamentally different from particulate transport. Turbidity-SSC is a particle scattering problem; conductance-concentration is a dissolution problem. They share methods but not physics.

- **Kratzert et al. 2019 (LSTM hydrology):** The paper should draw the parallel more explicitly: Kratzert showed that LSTMs learn catchment-specific hydrologic signatures from forcing data + static attributes. This paper does the same thing for the turbidity-SSC relationship. The adaptation curve is analogous to Kratzert's finding that catchment attributes encode hydrologic "fingerprints."

---

## 2. Physical Story Critique

### Do the disaggregated results tell a coherent physical story?

They tell the *beginning* of a coherent story, but critical threads are left dangling.

**Geology -> particle size -> optical-gravimetric relationship:**

This is the most important physical thread and is underdeveloped. The data is there:
- Carbonate R^2 = 0.81 (uniform particle sizes, consistent mineralogy, predictable scattering)
- Volcanic R^2 = 0.20 (bimodal particles: primary volcanic fragments + reworked fine ash)
- SGMC sedimentary-chemical at SHAP rank 10
- Power law slopes: median 0.952, range 0.29-1.55 with geology predicting slope

But the paper does not explicitly connect: "Carbonate watersheds produce fine silt/clay with narrow particle size distributions and consistent refractive index. This means turbidity (a scattering measurement) maps predictably to mass concentration (SSC). Volcanic watersheds produce bimodal populations (dense lithic fragments + fine ash) where the same turbidity can correspond to very different mass concentrations depending on the proportion of each population."

This paragraph should be in the paper. It IS the physics.

**Collection method -> vertical gradient -> sampling bias:**

Well-framed in Section 5.3. The 4x difference between depth-integrated and point samples is a strong finding. But the "operational irony" framing understates the problem: this is a *confound*, not just an inconvenience. The model may be learning a collection-method-specific turbidity-SSC relationship, and when deployed at a new site, the user must know the collection method used in the model's training data for that site's geologic analogue. This should be discussed as a limitation, not just an observation.

**Hysteresis -> event-scale turbidity advantage:**

The Brandywine load comparison is the strongest evidence in the paper. The explanation (turbidity captures rising vs falling limb asymmetry that discharge cannot) is physically correct and well-known from Williams (1989) and Landers & Sturm (2013). The storm event comparison (2-4x lower median error) is convincing.

However, I am concerned about the Brandywine numbers specifically. The paper reports total loads (42,059 vs 41,007 tons, ratio 1.03) but the daily metrics tell a different story: R^2 = 0.49, median daily error of 12,743%. The daily median error is astronomical because many non-transport days have tiny predicted loads vs reported zeros. The paper acknowledges transport-day filtering, but the reader needs to understand that the impressive 2.6% total agreement masks enormous day-to-day scatter. At Brandywine, 76% of days are non-transport --- the "matching" comes partly from getting the big events approximately right, which makes the errors on small days irrelevant for total loads. This is fine physics (big events dominate annual loads) but needs more transparent discussion.

Valley Creek (total ratio 1.55) and Ferron Creek (total ratio 0.75) are less impressive but more honest demonstrations. Three sites is a thin load validation. The paper acknowledges this implicitly but should state it explicitly: "Three sites are insufficient to validate load estimation generally; these results demonstrate feasibility, not operational readiness."

**Seasonality -> snowmelt vs rainfall -> different transport mechanisms:**

This is mentioned but not developed. The results log reports Spring R^2 = 0.421 vs other seasons R^2 = 0.700 and Summer SSC/turb ratio of 1.94 vs Winter 1.73. These numbers are not in the paper. They should be. The seasonal variation in the SSC/turb ratio directly reflects the particle size mechanism: spring snowmelt mobilizes fine sediments (high turbidity per unit mass), while summer thunderstorms mobilize coarser material from hillslopes and channel banks (lower turbidity per unit mass). This supports the central geology-particle size story.

**Between-site heterogeneity (CV ratio 3.2x):**

This IS the central finding and is appropriately positioned as such. The paper does a good job explaining that 30% of sites with R^2 < 0 is honest science, not failure. The catastrophic site classification (51 sites with LOGO R^2 < -1, only 7 genuinely wrong, 17 low-signal) is strong diagnostic work that should make it into the paper or supplementary material.

---

## 3. Literature Positioning

### Papers that should be cited or discussed more prominently

1. **Landers & Sturm (2013)** --- already cited, but their particle size distribution mechanism for hysteresis is central to explaining WHY the model's geology features matter. The paper cites them for hysteresis but does not connect to the particle size story.

2. **Uhrich & Bragg (2003)** --- cited as a reference for per-site R^2 = 0.78-0.90, which is correct.

3. **Lewis (1996)** --- "Turbidity-controlled suspended sediment sampling for runoff-event load estimation" --- one of the foundational papers arguing that turbidity-based sampling captures event dynamics better than fixed-interval sampling. Supports the hysteresis argument.

4. **Glysson et al. (2001)** --- "Comparability of suspended-sediment concentration and total suspended solids data" --- relevant to the collection method confound discussion.

5. **Topping et al. (2007)** --- "Colorado River sediment transport" --- demonstrates the acoustic backscatter approach that the paper notes is used in Idaho/Palouse. Brief mention would position the model's applicability boundaries.

6. **Nearing et al. (2021)** --- "What Role Does Hydrological Science Play in the Age of Machine Learning?" --- the "explainability" framing paper. WRR reviewers will expect engagement with this perspective.

7. **Addor et al. (2017)** --- CAMELS dataset. The parallel between CAMELS for rainfall-runoff and this dataset for turbidity-SSC should be explicit.

### Is the turbidity-informed vs discharge-only framing correct?

Yes, this is the right framing. The paper correctly identifies that no prior cross-site SSC model uses continuous turbidity, and the comparison with Song et al. (2024) is the right benchmark. But the paper should be more careful about what "turbidity-informed" means: the model is turbidity-DOMINATED (top 2 features are turbidity, accounting for ~50% of SHAP importance). The watershed attributes provide site context, but turbidity is doing the heavy lifting. This is not a weakness --- it IS the physics --- but the paper should frame it as "turbidity with geologic context" rather than "turbidity plus watershed attributes."

---

## 4. Framing Assessment

### "What transfers cross-site and what does not" --- is this the right frame?

This is a good frame but not the strongest one. Here is what I would recommend:

**Strongest framing:** "The optical-gravimetric conversion: why turbidity is not SSC, and what controls the conversion across sites."

This centers the physics. The turbidity-SSC relationship is a measurement model, not a physical law. Turbidity measures optical scattering; SSC measures mass concentration. The conversion between them depends on particle size, shape, mineralogy, and organic content --- all of which are controlled by watershed geology. The model works by learning this conversion from geologic context.

**Alternative framing:** "A screening-to-monitoring continuum for turbidity-monitored sites."

This centers the operational value. The three-tier deployment framework (Section 5.4) is smart and practical, but it currently reads as an afterthought. If this were the central framing, the paper would organize around: (1) how good is zero-shot screening? (2) what controls screening accuracy? (3) how much calibration is needed to move from screening to monitoring?

**Current framing tradeoffs:** The "what transfers" framing is the most natural for WRR, which values process understanding. I would keep it but make it more specific: "What transfers is the turbidity response to sediment; what does not transfer is the mass-to-scattering conversion, which is geologically controlled."

### How should negative results be positioned?

**30% of sites R^2 < 0:** The paper handles this well. The key sentence --- "This is a scientifically honest result, not a model limitation" --- is good but could be stronger. Frame it as: "A model that claims to work everywhere is lying. We report exactly where and why the model fails, which is itself a contribution."

**TP/nitrate/orthophosphate collapse:** Not discussed in the paper draft. It should be mentioned in the Discussion or Limitations as evidence that the approach is specific to particle-mediated parameters. Dissolved species require fundamentally different surrogate relationships. This bounds the method's applicability.

**CQR failure:** Well-handled in Section 6.2. The structural explanation (Box-Cox compression prevents quantile models from reaching extreme tails) is useful for future researchers.

---

## 5. Paper-Worthy Results and Quotes

### Site heterogeneity story

- Between-site CV of SSC/turb ratio = 4.37; within-site CV = 1.35; ratio = 3.2x. This is THE finding.
- Median per-site R^2 = 0.402 [95% CI: 0.358, 0.440]; fraction R^2 > 0 = 75.7% [68.1%, 83.7%]; fraction R^2 > 0.5 = 36.5% [27.3%, 44.5%].
- 30% of holdout sites have R^2 < 0. Catastrophic site analysis: 51 sites with LOGO R^2 < -1, but only 7/51 are genuinely poor predictions; 17/51 are low-signal sites where R^2 is misleading (small SSC range, errors small in mg/L).
- Pooled NSE = 0.306 masks per-site reality. Sample-weighted mean site R^2 = 0.303. Pooled metrics tell a fundamentally different story than disaggregated metrics.
- Holdout SSC/turb ratio is systematically harder than training (2.17 vs 1.74, +25%).

### Adaptation curve (management finding)

- N=0: MedSiteR^2 = 0.401. N=10 random: MedSiteR^2 = 0.493. N=20 random: MedSiteR^2 = 0.498. Improvement from 10 to 50 = +0.004, negligible.
- The knee is at N=10 for random sampling. One field campaign captures most adaptation benefit.
- Temporal adaptation at N=10 produces MedSiteR^2 = 0.389, WORSE than zero-shot (0.401). First 10 chronological samples are baseflow-dominated and bias the adaptation.
- Bayesian adaptation fixes catastrophic small-N collapse: at N=2 temporal, Bayesian R^2 = 0.485 vs OLS R^2 = -0.56 (delta = +1.04).
- Principled shrinkage: N=1 trusts 10.7% of the site-specific correction, N=20 trusts 70.5%.

### Geology controls on transferability

- Carbonate R^2 = 0.81 (uniform silt/clay, consistent refractive index, predictable optical-gravimetric conversion).
- Volcanic R^2 = 0.20 (bimodal particle populations, variable mineralogy).
- Unconsolidated sediments: intermediate performance.
- SGMC sedimentary-chemical at SHAP rank 10 (mean |SHAP| = 0.085).
- Metamorphic rocks produce higher turbidity-SSC slopes (~1.05-1.13); carbonate/sedimentary produce lower (~0.76-0.87).
- Per-site power law slopes: median 0.952, range 0.29-1.55. 50% of sites steepen at high turbidity, 32% flatten. Geology predicts slope.
- "Watershed features cannot predict per-site turb-SSC slopes directly" (two-stage model CV R^2 = -0.21). Site heterogeneity is too high for purely attribute-based prediction. This is a key negative finding.

### Turbidity advantage over discharge

- CatBoost beats OLS at every N and every split mode.
- N=2 temporal: CatBoost R^2 = 0.36 vs OLS R^2 = -0.56 (delta +0.93). This is the model's core operational value.
- N=10 random: CatBoost R^2 = 0.49 vs OLS R^2 = 0.37 (delta +0.13).
- Brandywine total load: v11 = 42,059 tons vs USGS 80155 = 41,007 tons (ratio 1.03, 2.6% error). OLS = 68,666 tons (ratio 1.67, 67% overprediction).
- Storm event median error: Brandywine +119% (v11) vs +165% (OLS); Valley Creek +169% vs +591%; Ferron Creek -39% vs +124%.
- Ferron Creek (arid, high-sediment Utah site): v11 daily R^2 = 0.76, Spearman = 0.96. OLS daily R^2 = -3.97. Strongest single-site demonstration.
- At 46 holdout sites with N=10 samples: CatBoost wins 30, OLS wins 16. Agriculture_pct predicts where OLS wins (rho = -0.48, p = 0.001). Simple agricultural sites don't need ML; complex/urban sites do.

### External validation

- 260 NTU sites (different sensor standard), 11,026 samples: zero-shot Spearman = 0.927, within-2x = 61%.
- Cross-network, cross-sensor, cross-decade generalization. UMRR (9,625 samples) Spearman = 0.94.

### Collection method confound

- SHAP rank 3 (mean |SHAP| = 0.349). At the same turbidity, depth-integrated samples yield ~4x higher SSC than point samples.
- Depth-integrated R^2 = 0.321 (v11 holdout); auto-point R^2 = 0.238.
- 30/51 catastrophic sites had unknown collection method (59%). Resolving unknowns helps worst sites most.

### Honest limitations

- 30% of sites R^2 < 0 (zero-shot).
- Top 1% SSC underprediction: -25%.
- Extreme SSC (>2,000 mg/L) conformal coverage: only 52% (n=31 samples).
- Approved-only training excludes many extreme events (provisional data excluded).
- Temporal stationarity not validated over the 20-year study period.
- Residual autocorrelation up to 0.69 at lag-1; effective sample sizes are smaller than reported.
- Spring R^2 = 0.421 vs other seasons R^2 = 0.700. Snowmelt is harder.
- Small drainage areas: 121% MAPE vs large basins 47% (rho = -0.375, p = 0.004).
- 6.8% of samples are burst pseudo-replicates (within 5 minutes of another at same site).

---

## 6. What's Missing

### Critical scientific analyses not in the paper

1. **Per-geology turbidity-SSC slope distributions.** The paper reports aggregate R^2 by geology class but does not show the actual slopes. A figure with per-site log(SSC) vs log(turbidity) slopes colored by geology class would be the single most informative figure in the paper. It would directly show WHY carbonate sites work (tight slope distribution) and volcanic sites don't (wide slope distribution).

2. **SHAP dependence plots for geology features.** The beeswarm plot is good for overview, but a SHAP dependence plot showing how sgmc_sedimentary_chemical modulates the prediction would reveal the mechanism (does it shift the intercept? the slope? both?). This is where the "WHY" lives.

3. **Seasonal decomposition.** Spring R^2 = 0.421 vs other seasons R^2 = 0.700 is a significant finding not in the paper. This likely reflects snowmelt producing fine glacial/colloidal sediment with high turbidity-to-mass ratios, while rainfall events produce coarser material. If true, it connects to the particle size story.

4. **Residual spatial structure.** Moran's I or a variogram of site-level residuals would show whether prediction errors are spatially correlated. The results log mentions 39% error difference at <50km vs 55% at distance, but this has not been formally tested.

5. **Temporal validation.** Train on pre-2015, test on post-2015 at the same sites. This is the most basic temporal stationarity check and is entirely absent. Even a brief analysis on the three load comparison sites would strengthen the paper.

6. **Drainage area interaction.** The results log reports rho = -0.375 between drainage area and error. Small basins are harder. Why? Likely: small basins have flashier hydrographs, shorter concentration-time lags, and more heterogeneous sediment sources. This connects to the adaptation story --- small basins may need more adaptation samples.

7. **The TP/nitrate failure.** A brief mention in the Discussion explaining why the approach does not extend to dissolved species would bound the contribution and prevent over-generalization by readers.

8. **Formal test of whether geology explains performance variation.** A linear model: per-site R^2 ~ f(geology, drainage_area, collection_method) would quantify how much of the inter-site performance variation is explained by observable attributes. This is more rigorous than reporting grouped means.

---

## 7. What's Overstated / Understated

### Overstated

1. **The Brandywine 2.6% load match.** This is a remarkable result but risks misleading readers. It is one site, and the daily metrics (R^2 = 0.49, enormous median daily error) show substantial scatter. The 2.6% agreement on totals partly reflects cancelation of over- and under-predictions across 2,549 days. The paper should note this explicitly: "The 2.6% total load agreement arises from the offsetting of event-scale errors; daily prediction accuracy is substantially lower."

2. **Spearman rho = 0.907.** The paper reports this as a pooled metric (all 6,026 holdout readings concatenated). Pooled Spearman across sites is inflated by the between-site concentration gradient --- a model that simply memorized the median SSC at each site would have high pooled Spearman. The per-site median Spearman (0.875) is the more honest number and is available in the evaluation JSON. The paper should report both and emphasize the per-site number.

3. **"Without any site-specific calibration."** The abstract states this and it is technically true for the zero-shot result. But the holdout sites are drawn from the same USGS monitoring network, the same sensor technology (FNU), and the same country. "Without site-specific calibration" does not mean "at any site anywhere." The paper should note that cross-network generalization (NTU sites) degrades meaningfully (MAPE 40% -> 53%).

4. **The 137-feature count.** The paper states 137 features in the Methods but the model uses 72 after ablation. Reporting 137 overstates model complexity. State clearly: "72 active features (65 pruned through ablation; see Appendix)."

### Understated

1. **The adaptation curve finding.** The operational insight --- that 10 randomly sampled observations capture most of the adaptation benefit, but the first 10 chronological samples can actually make things worse --- is underplayed. This finding has immediate management implications: agencies should target high-flow events in initial sampling campaigns. This deserves a full paragraph and possibly a highlighted recommendation box.

2. **The -36.6% bias.** The zero-shot model systematically underpredicts by 36.6%. This is a large bias for operational use. The dual-BCF approach (bcf_mean for loads, bcf_median for individual predictions) is clever but means the model is never unbiased for both use cases simultaneously. This tension deserves more discussion.

3. **The 30% failure rate.** The paper mentions this but does not give it enough weight. In any operational deployment, a 30% probability of R^2 < 0 at a new site means the model needs a warning system. The screening tier should include an uncertainty flag based on geology and drainage area.

4. **The v9 data contamination story.** The decision log documents that v9 was trained on holdout + vault sites, producing invalid results. This is not mentioned in the paper, and it should not be --- but the fact that the current v11 holdout performance (MedSiteR^2 = 0.40) is substantially lower than the contaminated v9 numbers is a cautionary tale. The paper should note somewhere that "holdout performance is sensitive to strict data partitioning" as a methodological lesson.

5. **Residual autocorrelation.** Lag-1 autocorrelation up to 0.69 means confidence intervals are too narrow. The bootstrap CIs are site-blocked, which helps, but within-site temporal dependence is not addressed. The effective sample size may be 30-50% of the nominal count. This should be stated as a limitation.

---

## 8. Specific Recommendations

### To make this a scientifically impactful WRR paper

1. **Reframe the hypothesis** around the optical-gravimetric conversion controlled by geology. The current hypothesis is trivially true. The interesting question is: "Can watershed geology serve as a proxy for the particle properties that control the turbidity-SSC conversion?" The disaggregated results already answer this (partially yes for carbonates, no for volcanics).

2. **Add the power law slope figure.** Plot per-site turbidity-SSC slopes by geology class. This is the most physically informative figure you could add and it directly tests the hypothesis.

3. **Add seasonal disaggregation to the paper.** Spring vs non-spring R^2 differences support the particle size story and connect to snowmelt hydrology literature.

4. **Report per-site median Spearman (0.875) alongside pooled (0.907).** Be explicit about why they differ. WRR reviewers will catch the pooled inflation.

5. **Expand the Discussion of the adaptation curve.** Add a subsection on "Operational Sampling Recommendations" with specific guidance: target storm events, stratify across seasons, avoid baseflow-only campaigns. This is where the paper transitions from science to impact.

6. **Add a brief Discussion section on dissolved species failure.** One paragraph explaining why turbidity predicts SSC but not nitrate/TP would bound the contribution and demonstrate scientific maturity.

7. **Temper the Brandywine headline result.** Report both the 2.6% total load and the daily R^2 = 0.49 prominently. The reader should understand both the strength (total load) and the limitation (daily accuracy) of the same result.

8. **Add a formal "predictability" model.** Even a simple regression of per-site R^2 on geology, drainage area, and collection method would quantify how much of the performance variation is explainable. If it explains 40%, that is a finding. If it explains 10%, that is also a finding.

9. **Cite Nearing et al. (2021) and engage with the ML-in-hydrology framing.** WRR reviewers will expect this. Explicitly address: "This is not just a prediction exercise. The disaggregated results reveal which physical attributes control cross-site transferability, advancing understanding of the turbidity-SSC measurement model."

10. **State the Moran's I limitation explicitly** rather than leaving it as an unmentioned gap. If spatial autocorrelation exists, the effective number of independent sites is smaller than 78, and the CIs widen.

11. **Consider splitting the paper.** The draft tries to cover everything: model development, load validation, adaptation, uncertainty quantification, and physical interpretation. A WRR paper has ~8,000 words. You may be better served by a focused paper on "what controls cross-site turbidity-SSC transferability" with the adaptation framework as Paper 2. The load validation could anchor either paper. But if you do keep it as one paper, the Discussion needs to be much tighter --- currently it reads as a collection of findings rather than a coherent argument.

12. **Clean up the feature count discrepancy.** The paper says 137 features in Methods Section 3.2, but the model uses 72. Note 2 in Table 1 partially addresses this, but it should be more prominent. A reviewer will be confused by "137 features" in the Methods and "72 features" in the Results Log.

### Minor technical points

- The bootstrap CIs for MedSiteR^2 [0.358, 0.440] are remarkably narrow for 78 sites. Verify that bootstrap resampling is at the site level (it is, per the JSON metadata). Even so, within-site temporal dependence may be inflating precision.
- The Ferron Creek result (R^2 = 0.76, Spearman = 0.96) is suspiciously good compared to the median holdout performance. Is this a site that happens to have very uniform geology? If so, it supports the thesis but should be noted as a best-case, not a representative case.
- The abstract says "95% CI: 0.36-0.44" for MedSiteR^2 but the bootstrap JSON says [0.358, 0.440]. Report to appropriate precision.
- Section 3.2 lists latitude as a feature, but the Decision Log says latitude was dropped. Verify which is correct for v11.

---

## Summary Judgment

This is a strong paper with genuine scientific contributions. The central finding --- that between-site heterogeneity in the optical-gravimetric conversion is the fundamental barrier to cross-site sediment estimation, and that this heterogeneity is geologically controlled --- is novel, well-supported, and important. The honest reporting of the 30% failure rate and disaggregated results by geology, collection method, and SSC range distinguishes this from the vast majority of ML-in-hydrology papers, which report only pooled metrics and claim success.

The paper's primary weakness is that the physical story is told incompletely. The geology -> particle size -> scattering relationship is asserted but not demonstrated. Adding per-geology slope distributions and SHAP dependence plots would transform this from "ML model with physical interpretation" to "physical finding enabled by ML" --- and the latter is what WRR reviewers want to see.

The load comparison at Brandywine is the paper's best hook, but it needs to be presented more carefully to avoid overselling a single-site result. The adaptation curve is the paper's best management contribution and is currently underemphasized.

**Recommendation:** Major revision to strengthen the physical story and tighten the framing. The data and analysis are sufficient; the narrative needs work. With these revisions, this could be a high-impact WRR paper.

**Estimated WRR reviewer reception:** If submitted as-is, I expect one reviewer to say "this is just another ML paper" and request substantially more physical interpretation. Another will ask about temporal validation and spatial autocorrelation. A third will appreciate the honest disaggregated reporting. With the revisions above, all three should be satisfied.
