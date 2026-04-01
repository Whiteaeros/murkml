# NTU Data Reality Review -- Post-Investigation Assessment
**Reviewer:** Dr. Marcus Rivera, USGS Water Resources Division (ret.), 20 years
**Date:** 2026-03-30
**Materials reviewed:** `PANEL_BRIEFING_NTU_DATA_REALITY.md`, prior Rivera review (`rivera_ntu_plan_20260330.md`), Phase 4 external validation results
**Scope:** Whether to integrate 3,646 discrete NTU-SSC pairs given the confirmed absence of continuous NTU sensor data anywhere in the USGS network

---

## Preamble

I want to acknowledge something directly: my prior review assumed dual-sensor concurrent data would exist in meaningful quantities. I estimated 15-18 Pattern B sites with extended co-deployment. The investigation has now confirmed that **zero continuous NTU sensor data exists in the USGS network.** All NTU data is discrete grab samples (pCode 00076). My estimate of 150-900 concurrent FNU/NTU rows was wrong -- the number is zero.

This changes the calculus substantially. The parallel-column architecture I endorsed was designed for a world where CatBoost would see both FNU and NTU readings at the same site, same timestamp, and learn the relationship conditioned on watershed features. That world does not exist. What exists is 3,646 discrete NTU readings from hydrographer visits between 1976 and 2005, each paired with an SSC lab result, with no FNU reading available at any of them.

Let me answer the six questions with this reality in mind.

---

## Question 1: Is the 3,646-sample expansion worth the complexity of adding `sensor_type` and `turbidity_instant_alt`?

**No. The complexity is no longer justified.**

In my prior review, I endorsed the parallel-column architecture (`turbidity_instant_fnu` and `turbidity_instant_ntu` as separate features) because it would allow CatBoost to learn the site-conditioned FNU-NTU relationship from concurrent readings. With zero concurrent readings, that architecture buys you nothing. Every NTU row will have FNU = NaN. Every FNU row will have NTU = NaN. The two columns are never co-populated. CatBoost cannot learn a relationship between two features that are never simultaneously present.

What you are actually proposing is simpler than it looks: add 3,646 rows where the turbidity measurement happens to come from a different instrument, slap a categorical flag on it, and hope the model figures it out.

The `turbidity_instant_alt` column (the alternate sensor reading) will be NaN in 100% of training rows. It is a dead feature. Do not add it.

The `sensor_type` categorical -- I warned against this in my prior review. A single categorical flag asks the model to learn a global NTU-vs-FNU offset, but the offset depends on particle color, size distribution, organic content, and water chemistry. It varies by site and by event. CatBoost will learn an average offset, which will be wrong everywhere.

The only architecture that makes sense for this data is the simplest one: put the NTU readings directly into `turbidity_instant` alongside the FNU readings, with no flag, no parallel column, no `turbidity_instant_alt`. Let the model treat them as turbidity measurements. The NTU values below ~400 are close enough to FNU that mixing them in is defensible. Above 400, you introduce noise, but you have very few extreme NTU values in discrete grab samples anyway -- hydrographers do not typically take grab samples during the peak of a flood.

But this simplest path has its own problems, which I address below.

---

## Question 2: Is temporal bias a concern?

**Yes. This is the primary scientific risk, and it is severe enough to give me pause.**

The NTU data spans 1976-2005. The FNU data spans 2006-present. There is zero temporal overlap at any site. This means:

1. **Land use has changed.** Urbanization, agricultural intensification, best management practice (BMP) adoption, TMDL implementation, reservoir construction, and land cover transitions have all occurred between the NTU era and the FNU era. The SSC-turbidity relationship at a given site in 1990 may differ from the relationship at the same site in 2020, not because the sensor changed, but because the watershed changed. You cannot distinguish sensor effects from watershed evolution effects.

2. **Climate has shifted.** Precipitation intensity has increased in much of the eastern US since the 1990s. The frequency of 25-year and 50-year storms has increased. Storm-driven sediment pulses in 2020 may be systematically different from those in 1990 at the same site.

3. **Sampling protocols evolved.** Pre-2005 USGS sediment sampling used depth-integrated DH-48, DH-59, and D-49 samplers with field processing that varied by Water Science Center. Post-2010 sampling increasingly uses autosamplers (ISCO) and point-integrated methods for quality-assurance purposes. The SSC lab values themselves may carry a methodological signal.

4. **The sites with NTU data are concentrated in the pre-2005 era precisely because they were decommissioned or transitioned.** As I noted in my prior review, these tend to be sites that lost funding during sequestration-era cuts (2008-2013). They may represent a biased sample of watershed types -- perhaps sites in economically depressed regions, or sites monitoring problems that were considered "solved," or sites that cooperators chose not to continue funding.

The practical consequence: if you add 3,646 NTU-era rows to a training set dominated by FNU-era rows, and the model learns different SSC-turbidity relationships for different eras, you have no way to determine whether the difference is attributable to sensor type, watershed evolution, climate shift, or sampling protocol changes. They are fully confounded.

---

## Question 3: Would adding rows with 3 of 6 turbidity features as NaN dilute the signal?

**Yes, and this is a bigger problem than it appears at first glance.**

Your current FNU training rows have up to 6 turbidity features: `turbidity_instant`, `turbidity_max_1hr`, `turbidity_std_1hr`, and potentially their derivatives. These window statistics carry information about within-event dynamics -- rising limb vs. falling limb, flashy vs. sustained events, sensor noise vs. true variability. The model has learned to use these features in combination.

The 3,646 NTU grab samples have exactly one turbidity feature populated: the instantaneous reading. The 1-hr max, 1-hr std, and any other window statistics are NaN. These rows are structurally identical to the external NTU grab samples that your model already handles poorly (+66% bias, R^2 = 0.43 with 10 calibration samples).

When you add 3,646 rows that are missing 3 of 6 turbidity features, CatBoost does not "skip" those features -- it routes those rows through different tree branches than the complete-data rows. You are effectively training a separate sub-model for the "grab sample with no window stats" population. That sub-model has:

- 3,646 NTU rows (1976-2005, all the temporal bias I described above)
- Whatever external NTU grab samples you add
- Any FNU rows that happen to have missing window stats (rare in continuous data)

This sub-model will be dominated by the NTU-era data. Its predictions at inference time will be applied to any new input that has no window stats -- which is exactly the external NTU validation scenario. You are not teaching the model to handle NTU better; you are teaching it to predict SSC from 1976-2005 grab-sample data when it encounters grab-sample-shaped inputs.

If the 1976-2005 SSC-turbidity relationships happen to match the modern ones, this works. If they do not (and I have given you several reasons why they might not), you have trained the model to be confidently wrong on exactly the inputs where you need it most.

---

## Question 4: Will adding 3,646 USGS NTU training samples reduce the +66% external NTU bias?

**Probably not, and there is a specific reason why.**

The +66% overprediction on external NTU data means the model predicts too much SSC for a given NTU turbidity reading. There are several possible causes:

1. **The FNU-NTU divergence at moderate turbidity.** If the model learned FNU-SSC relationships where, say, FNU = 200 corresponds to SSC = 800, and an external NTU site submits NTU = 200 which actually corresponds to SSC = 500 (because NTU reads higher than FNU for organic-rich water), the model overpredicts. This is a sensor physics problem.

2. **Different sediment characteristics at external sites.** The external NTU sites (UMRR, SRBC) are in regions with different geology than most of your USGS training sites. The SSC-turbidity relationship depends on particle size and mineralogy, which are geology-dependent. The +66% bias might have nothing to do with the sensor type and everything to do with the fact that Mississippi River loess has a different scattering-to-mass ratio than Appalachian shale.

3. **Sampling protocol differences between organizations.** USGS SSC samples are analyzed by the USGS Sediment Lab in Iowa City using standardized methods (ASTM D3977, evaporation method). External organizations may use different labs, different methods (filtration vs. evaporation), different holding times. These differences can produce systematic biases in the SSC values themselves.

Adding 3,646 USGS NTU grab samples addresses cause #1 partially (the model sees NTU-SSC pairs and learns NTU is not the same as FNU) but does not address cause #2 (the external sites are still geographically different from the USGS sites) or cause #3 (the lab methods are still different). And the NTU training data is from 1976-2005, while the external validation data is modern, so the temporal confound from Question 2 applies here too.

**The FNU-NTU conversion relationship that you cannot learn is exactly what you would need to solve cause #1 cleanly.** Without it, you are relying on the model to infer the NTU-SSC relationship from historical grab samples at sites that may not represent the external validation sites geographically, temporally, or methodologically.

My honest assessment: the +66% bias will decrease somewhat (maybe to +30-40%) because the model will have seen some NTU-SSC pairs and will learn that NTU tends to produce a different SSC than FNU at the same nominal reading. But you will not eliminate it, and you may introduce new biases from the temporal and geographic confounds.

---

## Question 5: Is there a simpler path to handling NTU at inference time?

**Yes, and I believe it is the better path for where you are right now.**

The Bayesian site adaptation with 10 calibration samples already achieves R^2 = 0.43 on external NTU data. That is not good, but it is a reasonable starting point for a fundamentally difficult problem (cross-organization, cross-sensor, cross-geography prediction). Let me describe what I think the practical inference workflow should look like.

**The user has an NTU sensor and wants SSC predictions.** They provide:
1. NTU readings (continuous or discrete)
2. A handful of SSC grab samples from their site (5-20 samples across a range of conditions)

The model treats NTU as if it were FNU for the initial prediction, then the Bayesian adaptation layer learns the site-specific bias (which includes the NTU-FNU offset, the local geology effect, the lab method effect, and any other systematic differences). This is exactly what site adaptation is designed to do -- absorb all the site-specific factors into a learned correction.

The advantage of this approach: it does not require the model to have learned a global NTU-SSC relationship from 1976-2005 data. It learns the local relationship from the user's own calibration data at the user's own site, with the user's own sensor and lab methods. This is more robust to all the confounds I have described.

The disadvantage: it requires calibration samples, which means the user has to collect some grab samples. But that is standard practice for any surrogate regression. No serious hydrologist would deploy a turbidity-to-SSC model at a new site without local calibration. If your users are skipping local calibration, they are doing it wrong regardless of what sensor they use.

**My recommendation on this point:** Invest in improving the Bayesian adaptation rather than the NTU training integration. Specifically:
- Characterize how R^2 improves as a function of the number of calibration samples (you have 10; what happens at 5, 15, 20, 30?)
- Determine whether the adaptation performs better when calibration samples span a range of flow conditions (not just baseflow)
- Test whether providing the sensor type (NTU vs. FNU) as a prior in the adaptation improves convergence

If the adaptation reaches R^2 > 0.7 with 15-20 calibration samples, you have a practical solution that does not require any changes to the core training pipeline.

---

## Question 6: What Would I Recommend?

**Option B, with a specific path forward.**

Skip the NTU training integration for now. The value proposition was built on the assumption that continuous NTU data existed and could teach the model the FNU-NTU relationship alongside watershed features. That assumption was wrong. What remains is 3,646 discrete grab samples from a different era, with no window statistics, no concurrent FNU readings, and full confounding between sensor type and temporal/watershed changes.

The risk-reward calculus does not favor integration:

- **Best case:** The model sees NTU-SSC pairs, learns a slightly different turbidity-SSC relationship for grab-sample-shaped inputs, and the +66% external NTU bias drops to +30-40%. But you cannot verify whether the improvement is real or is an artifact of training on a data population that now resembles the validation population structurally (both are grab samples with missing window stats).

- **Worst case:** The temporal bias from 1976-2005 data contaminates the model's understanding of SSC-turbidity relationships, degrading predictions for FNU sites. The NaN-heavy rows dilute the signal from complete FNU rows. The model becomes harder to interpret and debug. You spend engineering effort on `sensor_type` flags and column architecture that delivers marginal improvement.

- **Likely case:** Small, ambiguous improvement on NTU validation, no change on FNU validation, significant added complexity.

**What I would do instead:**

1. **Keep the 3,646 NTU-SSC pairs as a curated validation dataset.** Do not train on them. Use them to evaluate the model's zero-shot and adapted performance on USGS NTU data specifically (as opposed to external organization NTU data). This lets you separate sensor-type effects from organization/protocol effects in your +66% bias analysis.

2. **Invest in the Bayesian site adaptation pathway.** This is the operationally correct solution. Any real user with an NTU sensor will need to provide calibration samples. Make that pathway robust, well-documented, and well-validated. Characterize the adaptation curve (R^2 vs. number of calibration samples, stratified by sensor type and geology).

3. **Revisit NTU integration only if:** (a) a specific user need demands zero-shot NTU prediction without calibration samples, (b) you discover a source of concurrent FNU-NTU continuous data that I am not aware of (some state agencies or university research stations may have run side-by-side sensors), or (c) the Bayesian adaptation pathway proves insufficient even with 20+ calibration samples.

4. **Use the 260 external NTU sites (UMRR, SRBC, etc.) exclusively for validation.** These are too valuable as independent test data to put into training. They represent different organizations, different protocols, different geographies. Keep them sealed.

The 3,646 samples are not worthless. They are valuable as validation data, as a diagnostic tool for understanding the NTU bias, and as a potential future training resource if the science justifies it. But right now, the risk of contaminating a working FNU model with temporally confounded, structurally incomplete NTU data outweighs the modest benefit of a 16% training set expansion.

---

## Summary

The investigation confirmed what I should have predicted from my own experience with the USGS transition: continuous NTU data does not exist because the USGS never deployed continuous NTU sensors alongside continuous FNU sensors at scale. The transition was a replacement, not a parallel deployment. The exceptions I estimated (Pattern B sites) either do not exist in your dataset or are too sparse to matter.

Without concurrent data, the elegant parallel-column architecture collapses to a simple "add grab samples from a different era with a flag." That is not worth the engineering cost or the scientific risk. The Bayesian site adaptation pathway is the correct solution for NTU users, and the NTU grab-sample data serves the project best as validation, not training.

---

*Dr. Marcus Rivera, USGS Water Resources Division (ret.)*
*20 years -- sediment transport, continuous water quality monitoring, surrogate regression development*
*Reviewing: NTU Data Reality Briefing, 2026-03-30*
