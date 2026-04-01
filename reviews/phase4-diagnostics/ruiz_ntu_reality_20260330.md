# NTU Data Reality Review — Dr. Catherine Ruiz
## Sediment Transport & Particle-Light Scattering Physics Perspective

**Date:** 2026-03-30
**Reviewer:** Dr. Catherine Ruiz, sediment transport researcher (15 yr experience in erosion mechanics, particle size distributions, sediment rating curves, hysteresis dynamics, and optical scattering physics for suspended sediment monitoring)

**Material reviewed:** `PANEL_BRIEFING_NTU_DATA_REALITY.md`, my prior review (`ruiz_ntu_plan_20260330.md`)

---

## Preamble

I flagged temporal overlap as my #1 risk in my prior review. I wrote: *"If the 89 sites have minimal concurrent FNU+NTU data, the model cannot learn the conditional relationship."* The answer has come back as the worst case: zero overlap, not sparse overlap. Zero. The entire architecture I endorsed -- parallel columns where CatBoost learns a geology-conditioned FNU-NTU conversion from concurrent readings -- is impossible. The question is now fundamentally different from what we were evaluating before.

---

## Question 1: Is the 3,646-sample expansion worth the complexity of `sensor_type` and `turbidity_instant_alt`?

**No. The complexity is no longer justified by the physics.**

My previous endorsement of the parallel column architecture rested on one critical assumption: that the model would see simultaneous FNU and NTU readings for the same water at the same SSC, alongside watershed descriptors, and learn the conditional FNU-NTU conversion. That cannot happen with zero temporal overlap.

What you are left with is a simpler proposition: 3,646 rows where turbidity was measured with a white-light nephelometer and SSC was measured from the same grab sample. You do not need `turbidity_instant_alt` because there is no alternate reading to populate it -- it would be NaN in 100% of NTU rows and 100% of FNU rows. A column that is universally NaN within each class teaches the model nothing; CatBoost routes around it at every split and the column is dead weight.

The `sensor_type` categorical flag is the only viable encoding, and it carries less physics than the parallel column approach. It tells the model "interpret this turbidity number differently," but gives it no direct information about HOW to interpret it differently. The model must learn the NTU-SSC relationship purely from the NTU-SSC pairs themselves, with no FNU anchor. This is not worthless -- it is a separate regression learned within the same tree ensemble -- but it is a much weaker form of integration than what was originally planned.

For 3,646 rows (16% expansion) with a single categorical flag, the added complexity is minimal. But the added VALUE is also minimal, because the model already handles NTU-only inference via Bayesian adaptation. The question becomes: does static NTU training data from 1976-2005 outperform 10-sample site-specific adaptation at inference time? I doubt it.

---

## Question 2: Is temporal bias a concern?

**Yes. It is a serious concern that is under-discussed in the briefing.**

The NTU data spans 1976-2005. The FNU data spans 2006-present. These are not just different measurement eras -- they are different watershed eras.

Consider what changed between these periods at a typical USGS monitoring site in the contiguous US:

- **Land use.** The 2001 NLCD and 2019 NLCD differ substantially in many watersheds. Urban expansion, agricultural intensification, conservation reserve programs, reforestation of marginal farmland -- all of these alter sediment sourcing, particle size distributions, and the organic content of suspended material.
- **Climate.** Precipitation intensity has increased measurably across much of the eastern US since the 1990s. More intense storms mobilize coarser fractions and produce flashier sediment pulses. The SSC-turbidity relationship at a site in 2020 may have a different slope than the same site in 1985 because the particle population being mobilized has shifted.
- **Channel morphology.** Decades of urbanization, dam removal, channel restoration, riparian buffer installation, and legacy sediment remobilization have changed the channel geometry and bank materials at many monitored sites. The sediment reaching the sensor is sourced differently.
- **Sampling protocols.** Pre-2000 SSC samples were sometimes processed as TSS (total suspended solids) using methods that undercount sand-sized particles. The USGS switched to SSC method (ASTM D3977) broadly by the late 1990s, but some pre-2000 data labeled as SSC may actually be TSS. A TSS value paired with an NTU reading will produce a different apparent NTU-SSC slope than a true SSC value with the same reading.

The watershed features (StreamCat, SGMC) in your training data are static snapshots. They do not evolve with time. So the model has no way to distinguish "NTU reading of 50 at this site in 1988 when the watershed was 20% agricultural" from "FNU reading of 50 at the same site in 2020 when the watershed is 35% agricultural." Both rows share the same StreamCat features because StreamCat does not version by decade. The model will blend these eras, and any systematic shift in the SSC-turbidity relationship between eras will appear as unexplained variance.

This is not a theoretical concern. Gray and Simoes (2008) documented that sediment rating curves at USGS sites shift on decadal timescales. You would be injecting data from an older rating curve regime into a model calibrated on the current regime.

---

## Question 3: Would adding rows with 3 of 6 turbidity features as NaN dilute the signal?

**Yes, but the dilution mechanism is more subtle than feature-level NaN handling.**

CatBoost handles NaN by routing observations with missing values to one child or the other at each split. This is well-established and not the concern. The concern is about what the model learns from the NaN pattern itself.

Your current FNU training data has the full suite: `turbidity_instant`, `turbidity_max_1hr`, `turbidity_std_1hr`, all populated. The window statistics encode physically meaningful information I detailed in my prior review -- event hysteresis, transport mode (slug vs washload), and signal quality. When these features are present, the model learns fine-grained SSC discrimination: "high instant + high std = slug transport, predict high SSC with wide uncertainty" vs. "high instant + low std = sustained washload, predict high SSC with narrow uncertainty."

The 3,646 NTU rows would have instant-only, no window stats. The model learns a separate, cruder decision path for these rows: "moderate instant NTU + NaN window stats = predict SSC from instant alone." This is a perfectly valid path, but it is a LESS INFORMATIVE path. Every NTU row trains the model on the instant-SSC relationship in isolation. Every FNU row trains the model on the full turbidity-signal-to-SSC relationship.

The risk is not that NaN rows "corrupt" the FNU splits. CatBoost's tree construction handles this correctly. The risk is that 16% of training rows are teaching a simpler relationship, which effectively downweights the signal from the richer FNU rows in the ensemble. In a 5000-tree CatBoost model, some fraction of trees will be specialized for the NaN-pattern rows, and those trees contribute nothing useful when predicting from complete FNU inputs. You are spending model capacity on a use case (NTU grab samples) that is better served by Bayesian adaptation anyway.

The dilution is probably small -- 16% is not overwhelming -- but it is nonzero and it buys you very little.

---

## Question 4: Will adding 3,646 USGS NTU training samples reduce the +66% external NTU bias?

**Probably not in a meaningful way, and here is the physics reason.**

The +66% bias on external NTU data has at least three contributing causes:

1. **The FNU-NTU measurement difference.** The model was trained on FNU, and FNU and NTU diverge in concentration- and geology-dependent ways. At moderate concentrations (the bulk of the external data), FNU/NTU ratios of 0.85-1.15 could produce 15-30% prediction bias. This explains perhaps half the observed 66%.

2. **The bench-top vs field sensor difference.** External NTU data comes from bench-top instruments (Hach 2100Q or similar). Grab samples are physically disturbed during collection and transport -- flocs are broken, settled material resuspended, bubbles introduced. I detailed this in my prior review (Section 4d). Bench-top NTU on a shaken grab sample reads 10-30% different from field-sensor NTU on the same water in situ. The model cannot learn this offset from USGS field data because USGS NTU is also from field instruments (or hydrographer's field portable instruments used in situ).

3. **Different site populations.** The external sites (UMRR, SRBC, etc.) operate in different watersheds with different particle populations than the 396 USGS sites. Even if the turbidity measurement were identical, the SSC-turbidity slope would differ.

Adding 3,646 USGS NTU samples addresses cause #1 only partially. The model learns that NTU readings produce different SSC than FNU readings -- but it learns the USGS version of NTU, which is field-instrument NTU, not bench-top NTU. Cause #2 is untouched. Cause #3 is untouched.

To meaningfully reduce the external NTU bias, you need either: (a) bench-top NTU training data from the external sites themselves (which defeats the purpose of a general model), or (b) a site-specific adaptation mechanism that adjusts for the compound offset. You already have (b) -- Bayesian adaptation with 10 samples gets R^2 = 0.43.

I expect that adding USGS NTU training data might reduce the +66% bias to perhaps +40-50%. That is an improvement, but it does not solve the problem, and it comes with all the temporal bias and dilution costs discussed above.

---

## Question 5: Is Bayesian adaptation with 10 samples the simpler path?

**Yes. From a physics standpoint, it is not just simpler -- it is more defensible.**

Here is why site-specific adaptation is the physically correct approach for NTU inference:

The NTU-SSC relationship at a given site is controlled by the local particle population (size, color, shape, mineralogy) and the local measurement conditions (instrument type, installation, flow regime). These are site-specific factors that static watershed features approximate but cannot fully capture. A universal model trained on a mix of FNU and NTU data learns an average NTU-SSC relationship that is wrong everywhere by a site-specific amount.

Ten calibration samples from the actual site, measured with the actual instrument, in the actual water, capture the site-specific NTU-SSC slope directly. No proxy. No assumption about how geology maps to particle optics. No temporal bias from 1985 land use. The Bayesian adaptation is doing exactly what a hydrologist does when they build a site-specific sediment rating curve -- fitting a local relationship to local data.

R^2 = 0.43 from 10 samples is modest but physically reasonable for grab-sample NTU-SSC without flow as a predictor. The dominant source of unexplained variance is likely hysteresis (same NTU at different SSC on the rising vs falling limb), which 10 samples cannot resolve but 30-50 might. Improving the adaptation sample size or adding discharge as a co-predictor in the adaptation step would likely push R^2 above 0.6, which is competitive with purpose-built site-specific rating curves.

The Bayesian adaptation path also has a clean narrative for the paper: "The model natively handles FNU data. For NTU deployment sites, 10 calibration samples enable site-specific adaptation with R^2 = 0.43 (n=10), improving with additional samples." This is honest, defensible, and does not require the model to learn a dubious cross-era, cross-instrument NTU-SSC relationship from training data.

---

## Question 6: What do I recommend?

**Option B: Skip NTU integration for now.** But with specific caveats.

### The case is clear

My prior review endorsed the parallel column architecture because it promised physics-based FNU-NTU conversion learning from concurrent sensor data. That is now confirmed impossible. What remains is a 16% training expansion using data from a different measurement era (1976-2005), with a different instrument type (field NTU vs continuous FNU), missing 3 of 6 turbidity features, and with static watershed features that do not account for the land use and climate changes between eras.

The costs:
- Temporal bias from blending 1976-2005 and 2006-present SSC-turbidity relationships
- Model capacity spent on a NaN-heavy, less informative data pattern
- Complexity of sensor_type flag that encodes instrument class but not the physics of divergence
- Risk of introducing TSS-labeled-as-SSC from pre-2000 samples
- Confounding the paper's narrative (readers will rightly ask why you mixed eras)

The benefits:
- 3,646 additional SSC observations (modest, at 16%)
- Marginal reduction in external NTU bias (from +66% to perhaps +45%)
- The model "sees" NTU during training (symbolic value, limited practical value)

The benefits do not justify the costs. The Bayesian adaptation path is simpler, more defensible, and addresses the actual deployment scenario (NTU sites with a handful of calibration samples) more directly.

### What to do instead

1. **Keep the 3,646 NTU-SSC pairs as a held-out validation set.** They are valuable for testing whether the model's Bayesian adaptation works across diverse sites and historical conditions. Use them to characterize adaptation sample size curves (5, 10, 20, 50 samples) and quantify how quickly the adaptation converges.

2. **Improve the Bayesian adaptation.** If 10 samples give R^2 = 0.43, investigate whether adding discharge (or a discharge proxy like drainage area x recent precipitation) to the adaptation step improves it. The NTU-SSC relationship is strongly modulated by flow, and including flow in the adaptation captures hysteresis effects that turbidity alone cannot.

3. **Report NTU performance honestly in the paper.** Zero-shot: +66% bias. With 10-sample adaptation: R^2 = 0.43. With 30-sample adaptation: [characterize from the held-out set]. This is a strength, not a weakness -- it shows the model's adaptation capability and gives practitioners a clear protocol for deployment at NTU sites.

4. **Revisit NTU training only if concurrent FNU-NTU data becomes available.** If any monitoring network operates dual-sensor installations (some state agencies do for transition periods), that data would enable the parallel column approach as originally designed. Without concurrent data, training on NTU is injecting a different measurement from a different era and hoping the model sorts it out. It will not.

### A note on the 260 external non-USGS sites

I want to re-emphasize from my prior review: the 11,000 external samples are bench-top NTU from grab samples. This is a third measurement class distinct from both USGS field NTU and USGS continuous FNU. Do not conflate them. If any future NTU integration happens, bench-top NTU must be flagged separately or excluded from training entirely. The physical differences (floc breakage, bubble introduction, different optical geometry) are too large to ignore.

---

*Dr. Catherine Ruiz*
*Sediment Transport Research Group*
