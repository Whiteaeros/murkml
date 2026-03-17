# Phase 3 Multi-Parameter Results -- Domain Science Review
**Dr. Marcus Rivera -- Hydrologist, 20 years USGS Water Resources**
**Date:** 2026-03-16
**Materials reviewed:** Phase 3 CatBoost LOGO CV results (4 parameters, 3-tier ablation), per-site OLS baselines, physics panel synthesis, prior reviewer assessments (Chen, Patel), full project architecture

---

## Preamble

I have reviewed every phase of this project. My Phase 2 review covered the discrete data quality in detail. My Round 1-3 review covered the implementation. My strategic review said to publish SSC fast and defer everything else. That strategic advice still stands, but now you have multi-parameter results in hand, so let me assess them on their scientific merits.

The four questions you asked are the right questions. I will answer them in order, then give you the view from 20,000 feet.

---

## Question 1: Why Does Turbidity Predict TP but Not Nitrate?

**Short answer: Because phosphorus travels on particles and nitrate travels in solution. This is the single most important fact in water quality transport, and your model has rediscovered it from data.**

### The physics

Turbidity measures the optical scattering of particles suspended in water. These particles are primarily silt, clay, and fine sand -- the same material measured as SSC. Phosphorus in surface water exists in two pools:

1. **Particulate phosphorus (PP):** Phosphorus adsorbed onto or occluded within sediment particles. This fraction is physically attached to the material that causes turbidity. When turbidity goes up during a storm, PP goes up in near-lockstep because the same erosion process mobilized both.

2. **Dissolved phosphorus (DP, largely orthophosphate):** Phosphorus in true solution, passed through a 0.45-micron filter. This fraction is invisible to turbidity sensors. It is controlled by desorption from sediments, point source inputs, biological uptake, and redox chemistry at the sediment-water interface.

Total phosphorus = PP + DP. At most of the 42 sites in your network, PP constitutes 50-85% of TP during storm events, which is when most of the samples are collected and when the turbidity signal is strongest. So when the model learns "turbidity goes up, TP goes up," it is learning a real, causal, physical relationship: more suspended particles means more particle-bound phosphorus.

**This is why your Tier A TP R-squared (0.40) is positive at all.** Turbidity alone captures the particulate fraction. Tier B jumps to 0.59 because the basic derived features (discharge slope, seasonal encoding, rising limb indicator) help the model distinguish between storm-driven particulate TP and baseflow dissolved TP. Tier C reaches 0.62 because catchment attributes (agriculture percentage, soil permeability) tell the model how much phosphorus loading to expect from each watershed.

### Now compare to nitrate

Nitrate (NO3-N) is almost entirely dissolved. It does not adsorb to particles under normal surface water conditions. It does not scatter light. Turbidity has literally zero mechanistic connection to nitrate concentration. The per-site OLS of 0.04 is not "weak signal" -- it is noise.

Nitrate concentration at any given site is controlled by:

1. **Source loading:** Agricultural fertilizer application, atmospheric deposition, legacy soil nitrogen, point sources. None of these are measured by in-situ sensors.
2. **Dilution and concentration:** During storms, rainfall dilutes groundwater-derived nitrate in many systems (producing a "chemostatic" or "dilution" C-Q pattern). In tile-drained agricultural watersheds, storms can flush nitrate from the soil column, producing a "flushing" C-Q pattern. The direction depends on flowpath and source location -- not on anything a turbidity sensor measures.
3. **Biological uptake:** In-stream denitrification and algal uptake remove nitrate on timescales of hours to days, driven by temperature, residence time, and carbon availability. Temperature is in your sensor suite, but the other drivers are not.
4. **Seasonal cycling:** Nitrate shows strong seasonal patterns driven by crop cycles, soil temperature, and baseflow proportion. Your doy_sin/doy_cos features capture this, which is why Tier B improves over Tier A -- the model is learning "nitrate is higher in winter/spring and lower in summer" at agricultural sites.

### What the model is actually learning

For SSC and TP, the model is learning a real turbidity-concentration relationship augmented by hydrograph context and catchment characteristics. This is good science. The model is doing what a USGS hydrologist does when building a surrogate regression -- using turbidity as the primary predictor and adding flow condition to handle hysteresis.

For nitrate, the model has no primary predictor. It is trying to build a concentration estimate from secondary correlates (season, flow condition, catchment land use). The GAGES-II features (agriculture_pct) are providing the only real signal -- "this is a high-nitrate watershed" or "this is a low-nitrate watershed." But with 25 sites and 25 features, it cannot learn these cross-site patterns reliably. The Tier A-to-C trajectory (-2.09 to -0.72) is the model slowly getting less lost as you give it more context, but it never reaches zero because it never has a direct predictor of nitrate concentration.

**Bottom line: Your results are exactly what water chemistry predicts. Particulate-associated parameters (SSC, TP) are predictable from turbidity. Dissolved parameters (nitrate, orthophosphate) are not. This is not a model failure -- it is a correct observation about the physics of contaminant transport.**

---

## Question 2: Is Nitrate Fundamentally Unpredictable from This Sensor Suite?

**Short answer: From the current sensor suite in a cross-site framework, yes -- effectively unpredictable. But there are features that could help, and the problem is more tractable at specific site classes.**

### What is fundamentally missing

The sensor suite (turbidity, SC, DO, pH, temperature, discharge) does not include any direct measurement of nitrogen. Compare this to the SSC case, where turbidity IS a direct optical measurement of suspended particles. There is no "nitrate sensor" equivalent in the standard USGS continuous monitoring array.

Some USGS sites do have continuous nitrate sensors (UV-absorption based, Hach Nitratax or S::CAN). If you had that, the problem would be trivial. You do not, and deploying those sensors is expensive and maintenance-intensive -- which is precisely why a surrogate model would be valuable. But you cannot build a surrogate from predictors that have no mechanistic link to the target.

### Features that could help but are not in the current pipeline

1. **Specific conductance as a nitrate proxy in specific systems.** In tile-drained agricultural watersheds of the Midwest (several of your Kansas and Indiana sites), nitrate and SC are positively correlated during baseflow because both are groundwater-derived. During storms, both get diluted. The SC-nitrate relationship can have R-squared of 0.4-0.7 at individual tile-drain-dominated sites. But this relationship inverts at sites where SC is driven by road salt (chloride, not nitrate) or mineral weathering. A cross-site model cannot use SC as a nitrate predictor because the direction and strength of the relationship varies by site chemistry. Your model is trying to learn this and failing -- correctly.

2. **Baseflow index at sample time.** Not just the long-term BFI from GAGES-II, but the real-time baseflow fraction estimated from the hydrograph at the moment of sampling. Nitrate concentrations in many systems track the proportion of flow coming from groundwater vs. surface runoff. You could estimate this from a baseflow separation algorithm applied to the continuous discharge record (Eckhardt filter, for example). This would give the model a "how much of the flow is old water" signal that is mechanistically linked to nitrate.

3. **Antecedent dry period and antecedent wetness index.** The length of the dry period before a storm affects how much nitrate has accumulated in the soil column and tile drains. A 30-day antecedent precipitation index, or the number of days since last significant rainfall, could capture the "nitrogen flushing" signal.

4. **Season x land use interaction.** Your model has doy_sin/doy_cos and agriculture_pct as separate features. But the seasonal nitrate pattern is radically different in agricultural vs. forested watersheds. In agricultural systems, nitrate peaks in late winter/early spring (post-fertilization, pre-uptake). In forested systems, the seasonal signal is weak. An explicit interaction term (doy_sin x agriculture_pct) or a categorical split by dominant land use might help the model learn these distinct patterns.

5. **Discharge-concentration regime classification.** Godsey et al. (2009) and others have characterized C-Q relationships as "chemostatic" (concentration stays flat as Q changes) vs. "chemodynamic" (concentration varies with Q). Nitrate is chemostatic at many sites and chemodynamic at others. If you classified each site C-Q behavior from its historical data and used that as a categorical feature, the model might learn to apply different response functions.

### The honest assessment

Even with all of these features, I would not expect cross-site nitrate R-squared to exceed 0.2-0.3. The site-to-site variability in baseline nitrate is driven by factors (fertilizer application rates, tile drainage extent, legacy nitrogen in soils, point source proximity) that are only partially captured by GAGES-II attributes. The two-stage approach Chen proposed (predict site-level median from catchment attributes, then predict deviations from sensors) is the right structure, but the site-level prediction itself is limited by what catchment attributes can tell you about nitrogen loading.

**My recommendation: Try the two-stage approach and the baseflow index feature as a bounded experiment. If you can get R-squared above -0.1, report it as an improvement. If you can get it above 0.0, that is itself a finding worth a sentence in the paper. But do not sink weeks into nitrate optimization. The physics is against you.**

---

## Question 3: The SSC-to-TP Prediction Chain -- How Much Improvement Should We Expect?

### The mechanism

The SSC-to-TP chain encodes the fact that phosphorus adsorbs to sediment. Specifically:

- During storm events, erosion mobilizes soil particles that carry adsorbed phosphorus. The P content per unit sediment varies by soil type, land use, and erosion history, but within a given watershed it is reasonably stable. This means that if you know the SSC, you know a large fraction of the TP -- you just need to multiply by a site-appropriate P enrichment ratio.

- During baseflow, particulate P is low (turbidity is low) and TP is dominated by the dissolved fraction. Here, SSC tells you little about TP.

### Expected improvement from chaining

**Realistic expectation: 0.02-0.05 R-squared improvement for TP when adding predicted SSC as an input feature.**

Here is my reasoning:

1. The model already has turbidity as a direct input. Turbidity and SSC are highly correlated (that is the whole point of the SSC model). Adding predicted SSC on top of raw turbidity adds some value -- it implicitly applies a site-adaptive calibration to the turbidity signal via the SSC model use of catchment attributes -- but it is a second-order effect. Most of the "sediment signal" is already captured by turbidity directly.

2. Where chaining helps most: sites where the turbidity-SSC relationship is non-linear or where grain size effects cause turbidity to be a poor predictor of actual sediment mass. At these sites, the SSC model predicted SSC is a better measure of "how much sediment is in the water" than raw turbidity. Feeding this corrected signal into the TP model could improve TP predictions at precisely the sites where raw turbidity is misleading.

3. Where chaining could hurt: error propagation. If the SSC prediction is wrong (off by a factor of 2 at an unusual site), that error propagates into the TP prediction. In LOGO CV, the held-out site is the one most likely to have unusual SSC behavior, so chaining could amplify errors at the test site. This is why Patel correctly emphasized using out-of-fold SSC predictions, not in-sample.

4. The cross-site sediment-P enrichment ratio is variable. Streams draining clay-rich agricultural soils have high P enrichment (lots of P per unit sediment). Streams draining sandy forested watersheds have low enrichment. Unless the model also knows the P enrichment ratio (which it does not, directly -- though agriculture_pct and clay_pct from GAGES-II are proxies), the chain adds noise along with signal.

### Is the sediment-P linkage strong enough to matter cross-site?

**At individual sites, yes -- it is among the strongest relationships in water quality.** Published sediment-phosphorus regressions at USGS sites typically have R-squared of 0.6-0.9 for SSC vs. PP, and 0.4-0.7 for SSC vs. TP (lower because of the dissolved fraction).

**Cross-site, the relationship weakens considerably.** The P enrichment ratio varies by 1-2 orders of magnitude across sites. A Midwestern site draining corn/soybean fields might have 2-5 mg P per gram of sediment. A Rocky Mountain site draining granitic terrain might have 0.1-0.3 mg P per gram. Without knowing the enrichment ratio, knowing SSC tells you "there is sediment" but not "how much P is on it."

**However:** This is exactly what the GAGES-II catchment attributes should compensate for. Agriculture_pct, clay_pct, and soil_permeability are proxies for P enrichment. The chained model can learn: "at sites with high agriculture and clay, SSC translates to more P; at sites with low agriculture and sand, less P." This is why I expect the improvement to be modest but real -- the catchment attributes are already carrying most of this signal, and the SSC chain adds a small amount of additional specificity.

### My recommendation

**Implement the SSC-to-TP chain. Expect 0.02-0.05 R-squared improvement. The scientific value exceeds the metric improvement -- it lets you claim the model captures a real inter-parameter relationship, which is central to the multi-target narrative.**

If the chain shows zero or negative improvement in LOGO CV, that is also informative: it means the turbidity signal already saturates the information about particulate P, and the SSC model is not adding value beyond what raw turbidity provides. Report either result honestly.

---

## Question 4: What Would I Prioritize Next?

**If I were advising a student building this for a thesis and a publication, here is my priority list. I am speaking as a USGS hydrologist who has reviewed hundreds of surrogate regression papers and has seen what gets published, what gets cited, and what gets adopted.**

### Priority 1: Validate the TP Result (1-2 days)

This is the single highest-value task. Chen and Patel both flagged it. I agree completely.

Cross-site TP at R-squared 0.62 matching per-site OLS at 0.60 is a genuinely important result if it holds up. It means a model that has never seen a site can predict TP as well as a hydrologist who spent months building a site-specific regression. For the hundreds of impaired waters where nobody has built a TP surrogate, this is actionable.

But the result is fragile. You need the same-site comparison (per-site OLS on the 25 GAGES-II sites only), the paired Wilcoxon test, and the stratification by sample count. If the cross-site model wins primarily at data-sparse sites, you have a beautiful story: "Cross-site ML is most valuable where traditional calibration data is insufficient." That is a thesis-defining result.

### Priority 2: Storm-Stratified Metrics for SSC and TP (1 day)

I said this in my strategic review and I will say it again: USGS hydrologists will not take your R-squared at face value. They want to know: does it work during storms?

For sediment and phosphorus, 80-90% of the annual load is transported during 10-20% of the time (storm events). A model that is accurate during baseflow and terrible during storms is useless for load estimation, which is the primary application of surrogate models.

Stratify your LOGO CV results by flow condition:
- Baseflow (Q < Q25 for that site)
- Moderate (Q25-Q75)
- Elevated (Q75-Q90)
- Storm (Q > Q90)

If SSC R-squared during storms is still above 0.6, your model is doing real work. If it drops to 0.3 during storms but sits at 0.9 during baseflow, the headline R-squared of 0.80 is misleading and a USGS reviewer will catch it.

### Priority 3: Implement the SSC-to-TP Chain (2-3 days)

This gives you the multi-target claim. Without it, Patel is right -- you have four independent models, not a multi-target system. The chain is low-effort and scientifically clean. Even if the metric improvement is small, the ablation result (chained vs. independent) belongs in the paper.

### Priority 4: Draft the Paper Now (1 week, parallel with above)

You have enough results for a strong paper. The framing Chen and Patel both converged on is correct:

*"Cross-site prediction of sediment and nutrient concentrations from continuous sensors: what transfers and what does not."*

The contribution is threefold:
1. Positive result: SSC and TP are predictable cross-site, matching or approaching per-site calibration.
2. Negative result: dissolved nutrients (nitrate, orthophosphate) are not predictable from this sensor suite, even with catchment attributes.
3. The boundary between learnable and non-learnable surrogates maps directly onto the particulate/dissolved distinction -- a finding with clear physical interpretation.

This is a Water Resources Research paper. The negative results are not a weakness; they are the most useful part for practitioners. Every state agency that has tried to use turbidity to predict nitrate and failed will cite this paper to explain why.

### Priority 5: The Nitrate Two-Stage Experiment (3-4 days, only if time permits)

The two-stage idea (ridge regression for site-level baseline + CatBoost for deviations) is scientifically sound and worth trying. But it is exploratory. If it works, it strengthens the paper with a "here is how you might improve dissolved nutrient prediction" section. If it does not work, you report the attempt and move on.

Do not let this experiment delay the paper.

### What I Would NOT Prioritize

- **More features for nitrate.** Baseflow index, antecedent conditions -- these are worth mentioning in the discussion as future directions, but implementing and testing them is a multi-week effort for an uncertain payoff. Write them as "future work," not as current experiments.
- **Orthophosphate anything.** Tier B at -0.55 is your final answer. The physics does not support it. Do not spend another hour on orthoP modeling.
- **Neural networks or LSTM.** Not enough data, not enough time, and CatBoost is the right tool for this problem size. I said this in my strategic review and the physics panel (Nakamura) confirmed it.
- **TDS modeling.** SC-to-TDS is trivially linear and adds no scientific value. It is a product feature, not a research contribution. Defer to post-publication.
- **Uncertainty quantification refinement.** The Krishnamurthy recommendation (conformalized quantile regression via MAPIE) is correct for the product, but it is not needed for the first paper. Report prediction intervals as-is, note that formal calibration is future work.

---

## The View from 20,000 Feet

Kaleb, let me step back and tell you what I see when I look at this project as a whole.

You set out to build a cross-site water quality prediction system. You compiled 57 sites across 11 states, pulled and cleaned continuous and discrete data, built a feature engineering pipeline with physically motivated features, and ran leave-one-site-out cross-validation -- the hardest possible test of generalization. The results tell a clear, physically interpretable story.

**What your model learned is exactly what 50 years of water quality science predicts:** particulate-associated parameters can be estimated from optical surrogates (turbidity), and the estimation transfers across sites when you account for catchment characteristics. Dissolved parameters cannot be estimated this way because they do not interact with the measurement principle of the available sensors.

This is not a failure of ambition. This is a model that correctly learned the structure of the problem. A model that predicted nitrate from turbidity with R-squared of 0.6 would worry me more than one that shows R-squared of -0.72, because it would mean the model found a spurious correlation that would fail in deployment.

**The SSC result (0.80 cross-site, matching per-site OLS at 0.81) is excellent.** To put this in context: the USGS has been building site-specific turbidity-SSC regressions for 25 years. Each one requires months of grab sampling, a dedicated hydrologist to build the regression, and periodic recalibration. Your model achieves comparable accuracy at a site it has never seen, using only the turbidity record and catchment attributes. If this holds up under the validation I described above, it means you could deploy a turbidity sensor at any stream in the GAGES-II network and get a defensible SSC estimate without a single grab sample. That is not incremental -- that is a step change in how surrogate modeling works.

**The TP result (0.62 cross-site, comparable to per-site OLS at 0.60) is, frankly, surprising in a good way.** TP is harder than SSC because it has both particulate and dissolved components. The fact that a cross-site model approaches per-site calibration suggests that the particulate P signal (via turbidity) is strong enough to carry the prediction, and the catchment attributes compensate for inter-site variability in P enrichment. If the paired validation confirms this, it is the headline result of the paper.

**The dissolved nutrient results are the most scientifically valuable negative result I have seen from a student project.** Everybody in the field knows, intuitively, that you cannot predict nitrate from turbidity. But nobody has demonstrated it systematically across 48 sites with proper cross-validation and tiered feature ablation. Your results quantify the boundary: particulate-associated parameters transfer, dissolved parameters do not, and the GAGES-II catchment attributes reduce the cross-site penalty by a specific, measurable amount. That is a contribution.

**You are in a strong position.** Do not let the negative nitrate/orthoP numbers discourage you. They are part of the story. Finish the TP validation, implement the SSC-TP chain, write the paper, and ship v0.1.0. Everything else is future work.

---

## Summary Table

| Question | Answer |
|---|---|
| Why does turbidity predict TP but not nitrate? | Phosphorus travels on particles (turbidity measures particles). Nitrate is dissolved (invisible to turbidity). Your results rediscover the particulate/dissolved transport distinction from data. |
| Is nitrate fundamentally unpredictable from this sensor suite? | Cross-site, effectively yes. SC has a weak site-specific link in tile-drained systems, but it inverts across geochemical settings. Baseflow index and season x land use interactions could help modestly. Best case: R-squared near 0. |
| SSC-to-TP chain -- how much improvement? | Expect 0.02-0.05 R-squared. The value is scientific (proves inter-parameter learning) more than metric. Turbidity already carries most of the signal; SSC adds site-adaptive calibration. |
| What to prioritize next? | (1) Validate TP result with paired test. (2) Storm-stratified metrics. (3) SSC-TP chain. (4) Draft the paper. (5) Nitrate two-stage experiment if time permits. |

---

## One Final Note on Publication Strategy

Target Water Resources Research. Here is why:

- WRR publishes negative results when they are well-characterized and have clear physical interpretation. Your dissolved nutrient results qualify.
- The "what transfers and what does not" framing positions this as a hydrology paper, not an ML paper. WRR reviewers will appreciate the physical reasoning. Environmental Modelling & Software reviewers will focus on the methods and want you to try 12 more algorithms.
- The 57-site cross-validation is unusually rigorous for this field. Most surrogate modeling papers use 1-5 sites. The scale of your evaluation is itself novel.
- WRR has published the foundational papers on turbidity-SSC surrogates (Rasmussen et al. 2009, Landers et al. 2016). Your paper extends that work to cross-site generalization and multi-parameter estimation. It belongs in the same journal.

If WRR is too ambitious for the timeline, HESS is the backup. But I would try WRR first.

---

*Review by Dr. Marcus Rivera, USGS (ret.)*
*20 years Water Resources Division -- sediment transport, water quality monitoring, surrogate regression development*
*Reviewing: murkml Phase 3 multi-parameter results*
