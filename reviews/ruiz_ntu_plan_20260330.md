# NTU Integration Plan Review — Dr. Catherine Ruiz
## Sediment Transport & Particle-Light Scattering Physics Perspective

**Date:** 2026-03-30
**Reviewer:** Dr. Catherine Ruiz, sediment transport researcher (15 yr experience in erosion mechanics, particle size distributions, sediment rating curves, hysteresis dynamics, and optical scattering physics for suspended sediment monitoring)

**Material reviewed:** `ntu-integration-plan.md` (Phase 7), `PHASE4_OBSERVATIONS.md`, `train_tiered.py` monotone constraint implementation, external validation results

---

## 1. Is the Parallel Column Approach Physically Sound?

**Yes, with caveats.** This is the correct architecture and it is superior to both the categorical flag approach and any external conversion factor approach. Here is why.

The FNU-NTU relationship is not a universal constant. It depends on the optical properties of the suspended particle population, which are controlled by:

- **Particle size distribution.** Mie scattering theory tells us that the angular distribution of scattered light depends on the size parameter (ratio of particle circumference to wavelength). FNU uses 860 nm infrared; NTU uses broadband white light centered around 400-600 nm. A 10-micron clay particle has a size parameter of ~37 at 860 nm but ~52-79 across the visible spectrum. These land in different regimes of the Mie scattering function, producing different angular intensities at the 90-degree detector.
- **Particle color and absorption.** Infrared at 860 nm is minimally absorbed by most mineral particles, so FNU is close to a pure scattering measurement. White light at 400-600 nm is strongly absorbed by iron oxides, organic coatings, and dark minerals (magnetite, ilmenite, hornblende). NTU therefore couples scattering AND absorption, making it sensitive to mineralogy in ways FNU is not.
- **Dissolved organic matter.** Humic and fulvic acids absorb blue and UV light strongly but are nearly transparent at 860 nm. In DOM-rich waters (forested catchments, wetlands), NTU will read high relative to FNU even at zero SSC.

The plan correctly identifies that this relationship "varies by site/geology" and proposes to let CatBoost learn it conditioned on watershed features. This is the right instinct. The watershed features (lithology, percent fines, drainage area, land cover) are proxies for the particle population characteristics that drive the FNU-NTU divergence. At dual-sensor sites, the model sees simultaneous FNU and NTU readings for the same water with the same SSC, alongside watershed descriptors. CatBoost can learn that granite watersheds with coarse, light-colored sediment have FNU/NTU ratios near 1.0, while iron-rich clay watersheds have ratios of 0.7-0.8.

**The 89 dual-sensor sites are the linchpin.** If they are geographically and geologically diverse, this approach works. If they cluster in one region or one lithology type, the model will learn one version of the FNU-NTU relationship and extrapolate poorly to others. Before proceeding, I would want to see the HUC2 distribution and dominant lithology classes of those 89 sites compared to the full 396-site set.

**Concern: temporal non-overlap at dual-sensor sites.** The plan acknowledges this risk but does not quantify it. If USGS installed FNU sensors to replace NTU sensors (which is the common upgrade path since the ISO 7027 transition), then at most sites the FNU and NTU records will NOT overlap. You may find that "dual-sensor" means "NTU from 2005-2015, FNU from 2015-present" with little or no concurrent operation. The number of rows where both columns are populated could be far smaller than expected. Check this before committing to the architecture. If concurrent overlap is sparse, the model cannot learn the conditional FNU-NTU relationship directly — it can only learn them as separate predictors that both correlate with SSC, which is weaker.

---

## 2. FNU-NTU Divergence: Where, How Much, and Why

The commonly cited "diverge above 400" threshold is a simplification. The divergence is not a single threshold — it is concentration-dependent, particle-dependent, and nonlinear.

### Concentration regimes

**Below ~40 FNU/NTU:** FNU and NTU are essentially interchangeable. Both operate in the single-scattering regime where Beer-Lambert-type attenuation is negligible. Ratios are typically 0.95-1.05.

**40-400 FNU/NTU:** Divergence begins and grows. Multiple scattering starts affecting the measurements differently because the two wavelengths have different extinction coefficients. Typical FNU/NTU ratios range from 0.85-1.15 depending on the particle population. The divergence is smooth but geology-dependent within this range.

**Above 400 FNU/NTU:** Divergence accelerates. Multiple scattering dominates, and the different wavelengths experience different optical depths. FNU typically reads 10-40% higher than NTU for the same water sample because infrared light penetrates farther through the suspension before being scattered back to the detector. The exact ratio depends strongly on particle size and color.

**Above ~1,000 NTU / ~1,500 FNU:** Both sensors approach saturation, but at different rates and for different physical reasons. FNU saturates later because IR has lower extinction. The ratio becomes unstable and sensor-specific.

### Geology dependence

This is the critical point the plan should address more explicitly. The FNU/NTU ratio is NOT a smooth function of concentration alone. It depends on:

- **Clay mineralogy.** Kaolinite (white, plate-shaped) gives ratios near 1.0. Montmorillonite (swelling, high surface area) gives ratios of 0.9-1.0. Iron-stained clays (laterite, ferricrete weathering products) give ratios of 0.7-0.9 because the iron absorbs visible light (NTU wavelengths) but not IR (FNU wavelengths), making NTU read artificially high relative to FNU for the same scattering.
- **Organic vs mineral sediment.** Organic-rich suspensions (peaty, humic waters) can have FNU/NTU ratios of 0.5-0.7 because the organic matter absorbs visible light strongly.
- **Sand fraction.** Coarse particles in the measurement volume create stochastic spikes in both signals, but the spike magnitude differs by wavelength. This adds noise rather than bias.

**The relationship is smooth within a site but discontinuous between sites.** For a given watershed, as concentration increases, the FNU/NTU ratio traces a predictable curve. But two different watersheds at the same concentration can have very different ratios. This is exactly what the parallel column + watershed features approach should capture, IF the dual-sensor sites sample enough of this geological diversity.

---

## 3. Monotone Constraints on NTU

**Monotonicity is valid for NTU-SSC, but with a weaker physical basis than FNU-SSC.**

For FNU, the monotone constraint (higher turbidity implies higher SSC) is grounded in ISO 7027 nephelometry physics. The 860 nm IR source minimizes absorption effects, making the 90-degree scattering signal a relatively clean proxy for particle concentration. The monotone relationship can break at very high concentrations (sensor saturation) and at very low concentrations (DOM interference), but across the working range it is physically robust.

For NTU, the same directional relationship holds — more particles produce more scattered light at 90 degrees — but the tighter coupling between scattering and absorption at visible wavelengths introduces more pathways for the monotone relationship to bend:

1. **Color-driven NTU inflation.** If a site has episodic DOM pulses (leaf litter decomposition, wetland drainage), NTU can spike without any sediment increase. The monotone constraint would force the model to predict higher SSC, which is wrong. FNU is far less susceptible to this.
2. **Particle color shifts during events.** If fine, dark particles arrive first (surface wash of organic-rich topsoil) followed by lighter mineral particles from bank erosion, NTU can decrease even as SSC increases because the dark particles absorb rather than scatter. This is uncommon but physically real.
3. **Biofouling.** NTU sensors in the field, especially older ones, are more affected by biofilm growth on the optical window. This produces a slow upward drift in NTU unrelated to SSC. Over weeks, the monotone assumption holds (higher reading = probably more particles), but within a drift episode the turbidity values are corrupted.

**My recommendation:** Apply the monotone constraint to `turbidity_instant_ntu` and `turbidity_max_1hr_ntu` (same as FNU), but monitor the training diagnostics for NTU-specific fold degradation. If any cross-validation fold shows the NTU monotone constraint reducing performance, consider whether the constraint should be relaxed for NTU. I would NOT pre-emptively remove it — the constraint is correct in the dominant case — but be prepared to revisit.

---

## 4. Particle Physics Effects When Mixing FNU and NTU Data

Beyond the FNU/NTU ratio issues already discussed, there are several mixing effects to watch for:

### 4a. Systematic bias in SSC-turbidity slopes

FNU-based SSC-turbidity regressions at a given site typically have slopes (mg/L per FNU) of 0.8-3.0, with the variation driven by particle size. NTU-based regressions at other sites have slopes of 1.0-5.0. These ranges overlap substantially but are NOT drawn from the same distribution. If the model learns one "average" slope for turbidity features and applies it to both FNU and NTU inputs, it will systematically under- or over-predict depending on which input type it receives. The parallel column approach avoids this by learning separate feature importances for FNU and NTU. Good.

### 4b. Different noise characteristics

FNU sensors (typically Hach TU5300, YSI EXO2 with IR probe) have lower noise floors (~0.3 FNU) and better precision at low concentrations than many NTU sensors (especially older Hach 2100 series with noise floors of ~1-2 NTU). The 1-hour window statistics (max, std) will therefore have different statistical distributions for NTU vs FNU even in identical water. `turbidity_std_1hr_ntu` will be systematically higher than `turbidity_std_1hr_fnu` for the same conditions. The model needs enough dual-sensor data to learn that NTU std of 5 is "normal low-variability" while FNU std of 5 is "moderate variability."

### 4c. Air bubble sensitivity

NTU sensors are more susceptible to air bubble interference than FNU sensors because small air bubbles (~50-100 micron) are strong Mie scatterers at visible wavelengths. Turbulent, aerated flow (cascades, weirs, dam tailwaters) can produce NTU readings 20-50% higher than FNU for the same water. This is not a particle physics effect but it will appear in the data and confuse the model if the dual-sensor sites include high-gradient streams.

### 4d. The external NTU data problem

The Phase 7C external data is grab-sample turbidity (bench-top instruments), not field sensors. Bench-top NTU instruments (Hach 2100Q, 2100AN) use different optical geometries than field sensors. The grab sample has been physically disturbed (shaken, transported), which changes the particle size distribution (breaks flocs, resuspends settled material). This means the "NTU" in the external data is not the same measurement as "NTU" from a USGS field sensor. The model is learning field-sensor-turbidity-to-SSC relationships, and applying bench-top-turbidity values will introduce a systematic offset. I would keep the external NTU data OUT of training until you can quantify this offset. Use it only for validation.

---

## 5. Information Lost Without Window Statistics

The plan acknowledges that external NTU data (Phase 7C) has only `turbidity_instant_ntu`, with window stats (max_1hr, std_1hr) as NaN. From a sediment transport perspective, the window statistics encode physically meaningful information:

### What max_1hr captures

The 1-hour maximum turbidity reflects the peak sediment pulse passing the sensor. In sediment transport, the peak concentration matters because:
- It indicates the maximum transport rate and thus the competence of the flow to move coarse material
- It captures event-scale hysteresis — during clockwise hysteresis, the max turbidity arrives before the max discharge
- It distinguishes between a sustained high-concentration event (max near mean) and a spike event (max >> mean)

The instant reading is a snapshot. The max tells you whether that snapshot caught the peak or the trough.

### What std_1hr captures

The 1-hour standard deviation captures the variability of the sediment signal, which is physically informative:
- **High std at moderate mean:** Slug transport. Sediment is arriving in pulses, typical of bank collapse events or bedload saltation near the sensor intake.
- **Low std at high mean:** Washload-dominated transport. Fine particles are uniformly suspended. This is the regime where turbidity is the best SSC proxy.
- **High std at low mean:** Noise-dominated. Sensor fouling, air bubbles, or biological interference. Turbidity reading is unreliable.

The std feature effectively encodes signal quality. Without it, the model cannot distinguish a clean low-turbidity reading from a noisy one.

### Quantifying the loss

In my Phase 4 review I noted that `turbidity_std_1hr` had meaningful SHAP importance in the ablation results. The ablation showed that window stats contribute meaningfully to prediction accuracy. For Phase 7C rows where these are NaN, I expect predictions to be noisier — perhaps 10-20% higher MAPE compared to rows with window stats populated. This is tolerable if the model learns to widen its prediction intervals for these rows (which CatBoost's quantile outputs should do naturally, since NaN features increase leaf impurity).

**Practical recommendation:** Do NOT impute window statistics for the external data. NaN is the correct representation. The model should learn that "no window stats" means "lower confidence," which it will do automatically through the CatBoost NaN handling. Just make sure the evaluation separates performance for rows with vs. without window stats so you can quantify the penalty.

---

## 6. Physics-Based Concerns the Plan Misses

### 6a. Temperature-wavelength interaction

Water temperature affects the refractive index of water, which changes the scattering cross-section. The effect is small (~0.5% per degree C) but differs by wavelength. At 860 nm (FNU) the temperature sensitivity is approximately half what it is at 550 nm (NTU). Over a 0-30 C range, this creates a ~7% drift in NTU relative to FNU. If the training data spans a wide temperature range but the dual-sensor overlap is concentrated in one season, the model may learn the wrong FNU/NTU relationship for other seasons. I would add `temperature_water` as an interacting feature in splits involving both turbidity columns. It is probably already in the feature set — just confirm it is not in the drop list.

### 6b. Sensor aging and calibration drift

USGS field sensors are calibrated with formazin or StablCal standards. The FNU/NTU ratio for formazin is, by definition, 1.0. But as sensors age, the optical components degrade differently. IR LEDs (FNU) degrade slowly and predictably. White-light sources (NTU, typically tungsten or broadband LED) shift their spectral output as they age, changing the effective NTU measurement wavelength. This means the FNU/NTU ratio for a given dual-sensor site may drift over multi-year records. If you are aligning FNU and NTU data across years, be aware that the "relationship" you are learning may be partly an artifact of sensor aging.

### 6c. The plan should define a minimum concurrent overlap requirement

The plan says 89 sites have "BOTH FNU and NTU" but does not define "have." Some sites may have 6 months of NTU in 2008 and 10 years of FNU starting in 2012 with zero overlap. I would require a minimum of 50 concurrent FNU-NTU observations (within 15 minutes of each other) before counting a site as "dual-sensor" for the purpose of learning the FNU-NTU relationship. Sites with less overlap still contribute their NTU-only rows for training, but they should not be counted as teaching the model the sensor relationship.

### 6d. Floc breakage during high-energy events

At very high flows, turbulence breaks apart flocculated aggregates into their constituent primary particles. This dramatically changes the particle size distribution (many more small particles, fewer large aggregates). Small particles scatter more light per unit mass at both wavelengths, but the increase is larger at visible wavelengths (NTU) than at IR (FNU). During extreme events, the FNU/NTU ratio may shift in ways that are not captured by static watershed features. This is an inherent limitation of any approach that does not include flow energy or shear stress as a feature.

### 6e. The UMC +474% bias

The plan mentions UMC had +474% bias and flags it for investigation. From a physics perspective, a +474% bias in the model (trained on FNU) applied to NTU data is far too large to be a simple FNU/NTU ratio effect. Even the most extreme FNU/NTU divergence would produce ~30-40% bias, not 474%. This almost certainly indicates a data quality problem — either NTU values reported in wrong units (e.g., JTU or FAU rather than NTU), SSC reported in wrong units (mg/L vs g/L), or turbidity values that are actually transmission/beam attenuation rather than nephelometric. Do NOT include UMC in training without resolving the root cause. It is not a sensor physics problem that the model can learn around.

### 6f. Phase ordering is correct but the stopping criteria need physics validation

The phased approach (7A dual-sensor, 7B NTU-only USGS, 7C external) is the right order. But each phase needs a physics sanity check beyond just "FNU metrics must not degrade." Specifically:

- After 7A: Check that the model's predicted SSC at dual-sensor sites is consistent regardless of whether you feed it the FNU or NTU input (with the other as NaN). The predictions should differ (because the inputs carry different information), but they should not diverge by more than ~20% in the working range. If they diverge by 50%+, the model learned spurious FNU-NTU associations.
- After 7B: Check that the NTU-only sites have physically plausible SSC-turbidity relationships. Plot predicted SSC vs NTU for a sample of sites and verify the slopes fall in the 1.0-5.0 mg/L per NTU range expected from the literature.
- After 7C: Do NOT evaluate the external grab-sample NTU data on the same scale as the continuous sensor data. Report it separately.

---

## 7. Summary Assessment

The parallel column architecture is physically sound and is the best approach I have seen for multi-sensor turbidity models. The CatBoost NaN handling is elegant and avoids the information loss inherent in categorical flags or external conversion factors. The phased implementation is correctly ordered.

**Primary risks in order of severity:**

1. **Sparse temporal overlap at dual-sensor sites.** If the 89 sites have minimal concurrent FNU+NTU data, the model cannot learn the conditional relationship. This would reduce the approach to "two independent turbidity predictors that happen to share a model" rather than "a model that understands FNU-NTU conversion conditioned on particle characteristics." Check this first.

2. **Bench-top NTU in training (Phase 7C).** Grab-sample bench-top turbidity is a different measurement than field-sensor continuous turbidity. Including it in training without a bench-top flag or separate treatment risks confusing the model. Recommend keeping Phase 7C data as validation only, or adding a `turb_measurement_type` categorical (continuous_field vs grab_bench) if it enters training.

3. **Geological diversity of the 89 dual-sensor sites.** If they cluster in one region, the learned FNU-NTU relationship will not generalize. Map them before proceeding.

4. **NTU monotone constraint edge cases.** Valid in the dominant case but DOM-rich sites may violate it. Monitor fold-level diagnostics.

5. **Window stats absence.** Tolerable with proper NaN handling. Do not impute.

**The plan is ready to execute Phase 7A.** The dual-sensor overlap check (concern #1) should be the first thing computed — it determines whether 7A delivers the physics-based FNU-NTU learning or just additional NTU training data. Both are useful, but the plan's narrative depends on the former.

---

*Dr. Catherine Ruiz*
*Sediment Transport Research Group*
