# Phase 5 Ablation Review — Dr. Catherine Ruiz
## Sediment Transport Physics Assessment

**Date:** 2026-03-30
**Reviewer:** Dr. Catherine Ruiz, sediment transport researcher (15 yr experience in erosion mechanics, particle size distributions, sediment rating curves, hysteresis dynamics, and optical scattering physics for suspended sediment monitoring)

**Material reviewed:** PANEL_BRIEFING_ABLATION_20260330.md, previous Phase 4 observations

---

## 1. Why turb_Q_ratio Is the Most Important Feature

The turb_Q_ratio (turbidity divided by discharge) is the single most important feature, with a -0.102 drop in median per-site R-squared when removed. This is not suspicious. It is physically the most informative quantity you could construct from available measurements.

Here is what it captures:

**Sediment supply vs. transport capacity separation.** Discharge (Q) is a proxy for the stream's transport capacity — its ability to carry sediment. Turbidity is a proxy for the sediment actually in suspension. The ratio turb/Q therefore isolates the *supply signal* from the *transport signal*. A high turb/Q means the stream is carrying more sediment per unit transport capacity than expected — this happens during supply-rich conditions (first flush, bank collapse, hillslope erosion pulses). A low turb/Q means the stream has excess transport capacity relative to available sediment — this happens during supply-limited conditions (armored bed, post-event exhaustion, clear-water dam releases).

**Why this matters for SSC prediction:** The turbidity-SSC relationship is not fixed. It shifts depending on the particle population in suspension, and the particle population depends on which sources are active, which depends on the balance between supply and transport capacity. By encoding turb/Q, you give the model a lever to adjust the turbidity-SSC conversion factor based on the hydrologic regime at the moment of measurement. Without it, the model must use turbidity alone and cannot distinguish between "high turbidity because lots of fine clay is suspended" (moderate SSC) and "high turbidity because a bank just collapsed and coarse silt is being entrained" (high SSC).

**Specific physical processes turb_Q_ratio encodes:**

1. **Hysteresis state.** On the rising limb, turb/Q is high (sediment supply exceeds steady-state). On the falling limb, turb/Q is low (supply exhausted, transport capacity still elevated). This is exactly the clockwise hysteresis information I discussed in my Phase 4 review.

2. **Sediment exhaustion.** During a prolonged event, turb/Q declines as available sediment depletes. The model can learn that declining turb/Q implies the particle population is shifting toward finer, harder-to-mobilize material — which has a different scattering efficiency.

3. **Regulated vs. natural flow.** Below dams, Q can be very high with near-zero turbidity (clear-water releases), giving turb/Q near zero. During natural floods, turb/Q is elevated. The ratio inherently separates these regimes.

4. **Baseflow vs. stormflow discrimination.** During baseflow, both turbidity and Q are low, but their ratio reflects whether the low turbidity is "clean baseflow" (low ratio) or "mild but sediment-rich groundwater" (higher ratio). This distinction matters for SSC prediction at low concentrations.

**Is it leaking information?** No. turb_Q_ratio does not contain SSC information directly. It contains information about the *hydrologic and geomorphic state of the watershed at the moment of measurement*, which is exactly what a physically informed sediment transport model needs. If anything, this feature should have been in the model from the beginning. It is essentially a simplified version of the sediment rating curve residual — the deviation of the current sediment state from the long-term turbidity-discharge relationship.

One caveat: if turb_Q_ratio is computed from the same turbidity measurement used as the primary predictor, there is a mathematical coupling (turbidity appears in both numerator and as a standalone feature). This is not information leakage per se, but it means the model could use the ratio as a nonlinear transformation of turbidity divided by discharge, which effectively gives CatBoost a pre-computed interaction term. This is fine — it is giving the model a physically meaningful nonlinear feature that trees would otherwise have to approximate through multiple splits.

---

## 2. Why Dropping Weather Destroys First Flush and Extreme Events

This is the most important finding in the ablation study. The numbers are stark:

- First flush R-squared: 0.394 to 0.305 (a 23% relative decline)
- Top 1% R-squared: 0.109 to 0.005 (effectively zero — the model becomes useless for extremes)
- Yet median R-squared improves from 0.285 to 0.347

The aggregate improvement is a trap. Here is the sediment transport physics behind the catastrophic extreme-event failure:

### 2a. What precipitation features carry that discharge alone cannot

Discharge is an *integrated* signal. By the time water reaches the stream gauge, precipitation has been filtered through infiltration, soil storage, overland flow routing, and channel routing. This integration smooths out the information about *how* and *when* precipitation arrived, which is exactly what controls sediment mobilization.

**Rainfall intensity vs. total volume.** A 50mm storm that falls in 1 hour produces radically different erosion than 50mm over 3 days. Both may produce similar peak discharge at a downstream gauge (depending on basin size), but the intense storm mobilizes orders of magnitude more sediment because:
- Raindrop kinetic energy scales with intensity, and raindrop impact is the primary detachment mechanism for surface erosion
- Infiltration-excess overland flow (Hortonian flow) occurs only when rainfall intensity exceeds infiltration capacity
- Sheet wash and rill erosion scale nonlinearly with flow depth, which scales with rainfall intensity

The precipitation features (precip_48h, precip_7d, precip_30d) are imperfect proxies for intensity but they encode *temporal structure* of water input that discharge has already lost.

### 2b. Why first flush specifically needs antecedent precipitation

The first flush signal depends on knowing that there has been a dry antecedent period followed by a wet event. The flush_intensity feature partially captures this, but flush_intensity is derived from the discharge hydrograph, which has already lost the precipitation timing information. Consider two scenarios:

- **Scenario A:** 30 dry days, then a 20mm rainfall event. The 30 days of dryness allowed sediment to accumulate. The 20mm event mobilizes this stored sediment. True first flush — high SSC/turb ratio.
- **Scenario B:** Frequent small rains over 30 days totaling 60mm, then a 20mm event. The frequent rains kept sediment sources active and partially depleted. The 20mm event encounters less available sediment. Not a true first flush — moderate SSC/turb ratio.

These two scenarios might produce similar flush_intensity values (both show a discharge rise after a period of low flow), but precip_30d distinguishes them. Without precip_30d, the model cannot tell if the rising limb is mobilizing stored sediment or just transporting steady-state sediment supply.

### 2c. Why extreme events specifically need weather features

Extreme SSC events (top 1%) are almost exclusively driven by extreme precipitation — high-intensity rainfall that generates widespread erosion across all source areas simultaneously. The discharge hydrograph records the *hydraulic response* to this precipitation, but it does not record:

1. **The spatial extent of rainfall.** A localized thunderstorm and a frontal system can produce similar peak Q, but the frontal system activates erosion across the entire watershed while the thunderstorm activates only one sub-basin. The sediment load from the frontal system is much higher. Multi-day precipitation totals (precip_7d) are a crude proxy for spatial extent of rainfall coverage.

2. **Antecedent moisture state.** Wet antecedent conditions (high precip_30d) mean soil is at or near saturation, infiltration capacity is reduced, and a larger fraction of new precipitation becomes runoff. This amplifies both discharge AND sediment production relative to the same rainfall on dry soil. But the amplification is disproportionate — sediment production increases faster than discharge because saturated soils are mechanically weaker and overland flow depth increases.

3. **Snowmelt augmentation.** In rain-on-snow events (critical for Kaleb's north Idaho context), antecedent precipitation as snow sets up a snowpack that rainfall then melts. The combined runoff from rainfall + snowmelt produces extreme discharge events with sediment loads that reflect the rainfall erosivity but are amplified by the additional water volume from snowmelt. Without precipitation features, the model cannot distinguish a rain-on-snow event (high sediment) from a pure snowmelt event (low sediment) — both may produce similar discharge.

**The median R-squared improvement (+0.062) when dropping weather is a classic variance-bias tradeoff.** Weather features add noise for routine events (where the hydrograph already contains enough information) but are essential for the tail events where the hydrograph alone is ambiguous. Since routine events dominate the dataset, the aggregate metric improves when you remove the noisy-for-most-events features. But the events where weather features matter — first flush and extremes — are precisely the events that practitioners care about most for flood hazard, infrastructure design, and water quality compliance.

**My strong recommendation: keep all three precipitation features.** The median R-squared penalty is acceptable. Extreme event prediction is the competitive differentiator for this tool.

---

## 3. Why Human Infrastructure Features Help Extreme Event Prediction

Dropping the human land+infrastructure block (8 features including agriculture_pct, developed_pct, dam_storage_density, wwtp_all_density, etc.) causes extreme event underprediction to worsen from -37.6% to -53.5%. This is a 42% relative increase in extreme-event bias. Here is the physics:

### 3a. Dam storage density

Dams fundamentally alter the sediment regime in ways that matter most during extreme events:

- **Sediment trapping.** Large reservoirs trap 80-99% of incoming bedload and a substantial fraction of suspended load. This means that watersheds with high dam_storage_density have lower sediment delivery ratios — for a given discharge, less sediment reaches the downstream gauge. Without this feature, the model overpredicts SSC below dams during normal flow and mischaracterizes the extreme-event response.

- **Flow attenuation.** Dams attenuate flood peaks. A natural watershed might produce a sharp flood peak with extreme SSC, while a dammed watershed produces a lower, broader peak with less extreme SSC for the same rainfall input. The model needs to know about dams to correctly interpret what a given discharge means for sediment transport.

- **Clear-water erosion below dams.** Sediment-starved water released from dams is "hungry" — it has excess transport capacity and actively erodes the channel bed and banks downstream. During extreme releases, this hungry-water effect can produce high SSC that comes entirely from local channel erosion rather than watershed-scale sediment delivery. This is a fundamentally different SSC-generation mechanism, and the model needs dam_storage_density to distinguish it.

- **Dam spill events.** During extreme floods that exceed dam capacity, spillway releases can mobilize reservoir sediment deposits. These events produce anomalously high SSC that cannot be predicted from the hydrograph alone — you need to know that a dam exists and approximately how large its storage capacity is.

### 3b. Developed percentage

Urban/developed land surfaces produce extreme SSC events through mechanisms that are physically distinct from natural watersheds:

- **Impervious surface runoff.** Developed areas generate runoff immediately upon rainfall with no infiltration lag. This produces flashy hydrographs with rapid sediment mobilization. The time between rainfall onset and peak SSC is much shorter than in natural watersheds.

- **Construction sediment.** Active construction sites can produce sediment yields 10-100x higher than undisturbed land. During extreme rainfall, unprotected construction sites deliver massive sediment pulses. Developed_pct is a proxy for the probability that construction activity is present in the watershed.

- **Stormwater infrastructure.** Urban drainage systems concentrate runoff and deliver it directly to streams at high velocity, causing localized bank erosion and channel incision. During extreme events, combined sewer overflows add additional suspended material.

- **Road sediment.** Unpaved roads and road cut-slopes are chronic sediment sources that activate disproportionately during extreme rainfall. Road density correlates with developed_pct.

Without developed_pct and dam_storage_density, the model treats all watersheds as having the same rainfall-to-SSC transfer function during extreme events. This is physically wrong. A 100-year rainfall on a forested, unregulated watershed produces a very different extreme SSC event than the same rainfall on an urbanized, heavily dammed watershed. The infrastructure features encode this distinction.

---

## 4. SGMC Lithology Features: Which Rock Types Should Matter

The single-feature ablation shows that three SGMC features are individually important:

- sgmc_unconsolidated_sedimentary_undiff (-0.102): most important SGMC feature
- sgmc_igneous_volcanic (-0.041)
- sgmc_metamorphic_volcanic (-0.039)

And several are harmful:

- sgmc_melange (+0.055)
- sgmc_metamorphic_sedimentary_undiff (+0.043)
- sgmc_metamorphic_carbonate (+0.020)

Here is the particle physics behind what should and should not matter:

### 4a. Why unconsolidated sedimentary is critically important

"Unconsolidated sedimentary undifferentiated" covers alluvium, glacial drift, loess, and other loose surface deposits. This is the single most important lithologic control on turbidity-SSC relationships because:

- These materials are the *primary sediment source* in most watersheds. You do not erode bedrock during a rainfall event — you erode the unconsolidated surface mantle. The percentage of watershed underlain by unconsolidated material directly predicts sediment availability.
- Unconsolidated sediments have highly variable particle size distributions depending on their depositional origin (glacial till is poorly sorted, loess is well-sorted silt, alluvium varies by position). This variability produces highly variable turbidity-SSC relationships.
- The model needs this feature to distinguish "sediment-rich" watersheds (high unconsolidated fraction, abundant source material, high and variable SSC) from "sediment-poor" watersheds (mostly bedrock, thin soils, limited and consistent SSC).

### 4b. Why igneous volcanic matters

As I discussed in my Phase 4 review, volcanic lithology produces the most optically problematic sediment. Dark mafic minerals (basalt, andesite) absorb light rather than scattering it, producing less turbidity per unit SSC mass. Volcanic glass and pumice are the opposite — low density, high scattering. The bimodal optical behavior means the turbidity-SSC relationship in volcanic watersheds is highly unpredictable without knowing the specific volcanic lithology present.

The model needs sgmc_igneous_volcanic to adjust its turbidity-to-SSC conversion for these optically anomalous particles. Removing it forces the model to apply a "generic" conversion to sites where the physics are fundamentally different.

### 4c. Why metamorphic volcanic matters

Metamorphic rocks derived from volcanic protoliths (metabasalt, greenstone, metarhyolite) retain some of the optical properties of their parent material but with additional variability from metamorphic mineral assemblages (chlorite, epidote, actinolite). These are dark-colored, moderately dense minerals that scatter light differently from both sedimentary and unmetamorphosed volcanic particles.

### 4d. Why melange and metamorphic-sedimentary are harmful

These are grab-bag categories that lump physically dissimilar lithologies:

- **Melange** is a tectonic mixture of blocks of different rock types in a sheared matrix. The particle population from a melange watershed is inherently heterogeneous and unpredictable — you might get serpentinite fragments (dark, dense, fibrous), chert (light, hard, angular), basalt blocks, and shale matrix, all in the same watershed. No single adjustment to the turbidity-SSC relationship can account for this variability. The feature adds noise without predictive power.

- **Metamorphic-sedimentary undifferentiated** lumps slate, phyllite, schist, quartzite, marble, and hornfels — rocks with completely different mineralogies, particle shapes, and optical properties. It is too coarse a category to carry useful physical information.

### 4e. Which SGMC features SHOULD be most useful (prediction)

Based on particle-light scattering physics, the most useful lithologic distinctions for turbidity-SSC prediction would be:

1. **Felsic vs. mafic igneous** — controls particle albedo (light vs. dark minerals), which is the primary driver of turbidity-per-unit-mass variability
2. **Unconsolidated** (already confirmed important) — controls sediment availability
3. **Carbonate** — produces distinctive, consistent turbidity-SSC relationships (as I discussed in Phase 4)
4. **High-clay metamorphic** (slate, phyllite) vs. **high-quartz metamorphic** (quartzite, gneiss) — controls particle shape (platy vs. equant) and size distribution

The current SGMC categories partially capture these distinctions but imperfectly. The "undifferentiated" suffix on many categories means they are lumping the very distinctions that matter physically.

---

## 5. Evaluation of Proposed Group Ablation Tests (A-D)

### Test A: SGMC Subgroups — Mostly well designed

A1-A4 (drop by parent rock class) are physically meaningful groupings. Each parent class produces sediment with broadly similar particle properties, so testing them separately makes sense.

A5 (drop ALL SGMC, keep StreamCat) and A6 (drop StreamCat, keep SGMC) are the critical comparison. My prediction: A6 will outperform A5 because the SGMC lithologic classification is more geologically specific than the StreamCat generalized geology. StreamCat geology is derived from state geologic maps that use variable classification schemes, while SGMC imposes a uniform national lithologic framework.

**One addition I would make to Test A:** A7 — keep only the 3 individually important SGMC features (unconsolidated_sedimentary_undiff, igneous_volcanic, metamorphic_volcanic) plus carbonate (which is physically important even if it did not show up as individually significant — it may be correlated with other features that are compensating). This is a physics-informed minimal SGMC set.

### Test B: Combined drop of harmful features — Essential but be cautious

Dropping all 12 individually harmful features simultaneously is the right experiment. However, I predict the compound benefit will be LESS than the sum of individual benefits. Here is why: some of these features are correlated, and dropping one may have partially captured the benefit of dropping another. When you drop both, you only count the benefit once.

More importantly, check whether any of the 12 harmful features become helpful in the context of a reduced feature set. Feature importance is not independent — it depends on what other features are available. Removing a harmful feature might expose a different feature's importance.

### Test C: Precipitation decomposition — Good but add a physics-based grouping

C1-C3 test all pairwise combinations, which is correct. My physics-based prediction:

- **precip_48h** captures event-scale rainfall — the current storm. This is most relevant for real-time SSC during an active event.
- **precip_7d** captures synoptic-scale moisture patterns. This is relevant for soil saturation state and multi-event sequences.
- **precip_30d** captures antecedent moisture conditions and seasonal dryness/wetness. This is the first-flush indicator.

For first flush preservation, precip_30d is essential. For extreme event preservation, precip_48h is essential (it encodes the current storm). I predict C3 (keep 48h + 7d, drop only 30d) will harm first flush but preserve extremes, while C1 (keep only 7d) will be the best single-feature compromise.

**Additional test I would add:** C4 — replace all three precipitation features with a single derived feature: "antecedent precipitation index" (API), which is an exponentially decaying weighted sum of past precipitation. This is a standard hydrologic variable that captures the information content of all three timescales in one number. If C4 performs comparably to the full 3-feature set, you have a more parsimonious model with the same physics.

### Test D: Old geology vs. SGMC replacement — Well designed

D1 and D2 are the right tests. D2 (keep only 5 helpful SGMC) is the one I would prioritize because it tests whether a physics-informed selection of lithologic features outperforms a comprehensive-but-noisy set.

**My prediction:** D2 will be the best performer because it retains the lithologic information that actually matters for particle-light scattering physics while eliminating the grab-bag categories that add noise.

---

## 6. Answers to the 8 Panel Questions

### Q1: Are these the right group ablation tests?

They are a good start but incomplete. Missing tests:

- **Categorical features group test.** collection_method, sensor_family, and turb_source together encode measurement methodology, not watershed physics. Test dropping all three simultaneously. If performance drops substantially, the model is partly learning sensor-specific biases rather than physical relationships. This is important for understanding transferability.

- **Engineered features group test.** turb_Q_ratio, flush_intensity, and turb_below_detection are all derived features. Test dropping all three to understand how much of the model's skill comes from feature engineering vs. raw measurements.

- **Interaction between weather and human infrastructure.** The briefing shows that both weather and infrastructure help extreme events. Test dropping BOTH simultaneously. If the combined drop is worse than additive, these feature groups are complementary (each captures different aspects of extreme-event physics). If it is approximately additive, they are redundant.

### Q2: Should we keep ALL weather features despite the median R-squared penalty?

Yes. Unequivocally yes. I addressed this in detail in Section 2. The median R-squared penalty is acceptable because:

1. Extreme event prediction is the highest-value use case for this tool. Anyone can estimate SSC during baseflow — the hard problem is extremes.
2. First flush prediction is physically important for water quality compliance monitoring, which is a primary commercial application.
3. The median R-squared penalty (+0.062 = 22% relative improvement) will mislead users into thinking the model is better, when in fact it has become useless for the events they care about.

If the team is uncomfortable with the aggregate penalty, explore Test C (precipitation decomposition) to find the minimum precipitation feature set that preserves extreme-event skill.

### Q3: How to weigh the human infrastructure tradeoff?

The infrastructure block causes a modest median R-squared penalty (-0.022 = 8% relative decline) but prevents a massive worsening of extreme event bias (-37.6% to -53.5%). This is not even close — keep the infrastructure features.

The median R-squared penalty occurs because infrastructure features add complexity (more splits, more opportunities for overfitting) on routine events where they are not needed. At moderate SSC, the turbidity signal is sufficient and infrastructure context is irrelevant. But at extreme SSC, the turbidity sensor is saturated or the sediment source has shifted, and the model needs infrastructure context to adjust its predictions.

A possible middle ground: explore using infrastructure features only as interaction terms (e.g., dam_storage_density * turb_Q_ratio) rather than as standalone features. This would allow the model to use infrastructure information only when the hydrologic state suggests it is relevant (e.g., during high-flow events), reducing the noise contribution during routine conditions.

### Q4: Is turb_Q_ratio importance suspicious?

No. See Section 1 for the detailed physics argument. turb_Q_ratio is the single most physically informative feature you could construct from available measurements. Its dominance is expected, not suspicious.

The only concern I would investigate is the mathematical coupling between turb_Q_ratio and the standalone turbidity feature. Test whether the model uses turb_Q_ratio primarily as a nonlinear transformation of turbidity (in which case it is a feature engineering convenience, not physics) or whether it genuinely leverages the Q-normalization (in which case it is encoding supply-transport separation). You can test this by examining partial dependence plots: if PDP(turb_Q_ratio) looks like 1/Q, the ratio is just inverting discharge. If it has its own distinctive shape independent of both turbidity and Q, it is carrying unique physical information.

### Q5: Should we test keeping ONLY the 5 helpful SGMC features?

Yes. This is my recommended Test A7 (see Section 5). The 5 individually helpful SGMC features are the ones whose lithologic categories map onto physically meaningful particle-scattering distinctions. The remaining 23 are either grab-bag categories (melange, undifferentiated) or redundant with other features.

However, I would add pct_carbonate to the "keep" list even if it was not individually significant, because carbonate lithology has well-documented and distinctive effects on sediment optical properties. It may not show up as individually important because its information overlaps with other features (StreamCat geology, possibly specific conductance through dissolved carbonate), but it should be retained on physical grounds.

### Q6: Should we accept that re-introduced features (do_instant, ph_instant, etc.) failed?

Not yet. My Phase 4 review specifically identified dissolved oxygen and pH as potential proxies for non-sediment turbidity sources (algal interference, DOM). They failed as *standalone* features, but that does not mean they fail as *interaction terms*.

Test: create do_instant * turbidity and ph_instant * turbidity interaction features. The hypothesis is that at low turbidity, DO and pH help distinguish sediment-turbidity from biological-turbidity. At high turbidity, they are irrelevant. An interaction term captures this conditional relevance.

If they still fail as interactions, accept the result and move on. The failure would mean that the optical distinction between sediment and biological turbidity is too subtle for the available sensor precision.

### Q7: What other group ablation tests would you run?

In addition to those listed in Q1:

- **Flow regime features.** Test dropping all discharge-derived features (Q-based features, baseflow_index) to isolate how much the model depends on turbidity alone vs. turbidity-in-context-of-flow. This directly tests whether site adaptation can compensate for flow context.

- **Geographic features.** If latitude/longitude or any geographic identifiers are in the feature set, drop them. The model should work from physical properties, not location. If dropping geography hurts, there is unmodeled spatial structure (likely regional differences in measurement practices or unrepresented lithologic gradients).

- **Leave-one-feature-category-out.** Drop ALL engineered features, ALL weather features, ALL SGMC features, ALL watershed characteristics, and ALL categorical features — each as a separate test. This gives you a feature-category-level importance ranking that is more informative than individual feature ablation for deciding where to invest future feature engineering effort.

### Q8: When to stop ablating and declare the feature set final?

From a sediment transport perspective, the feature set is "final" when:

1. **Every remaining feature has a physical justification.** You should be able to explain, in terms of erosion mechanics, sediment transport, or optical scattering physics, why each feature helps predict SSC from turbidity. If you cannot articulate the mechanism, the feature is likely fitting noise.

2. **Removing any remaining feature degrades performance on the diagnostic subsets that matter** (first flush, extreme events, low-SSC, high-SSC, each geology class). Aggregate metrics are insufficient — you need disaggregated stability.

3. **Adding physically motivated features no longer helps.** When you have exhausted the set of features that encode known physical mechanisms (supply-transport separation, antecedent conditions, lithologic particle properties, measurement methodology, infrastructure modification) and none of the untested features improve disaggregated diagnostics, you have reached the information frontier for available data.

4. **The harmful features are removed and the benefit is confirmed in compound.** Test B must be completed and the compound benefit verified before declaring the feature set final.

In practice, I would say: complete Tests A7, B, C, and D2. If the results are consistent with single-feature predictions (no surprises), declare the feature set final. If there are surprises (compound effects that differ substantially from individual effects), you need one more round of investigation.

---

## 7. Physical Processes We Have Not Tested

Building on my Phase 4 recommendations, several processes remain untested and are directly relevant to the ablation results:

### 7a. Particle size distribution proxy

The single biggest gap in the feature set is the absence of any proxy for in-situ particle size distribution. The turbidity-SSC relationship depends more on particle size than any other factor. Two potential proxies:

- **Turbidity-to-specific-conductance ratio.** Specific conductance tracks dissolved load. During events dominated by surface erosion (fine particles), both turbidity and SC rise. During events dominated by bank erosion (coarse particles), turbidity rises but SC may not. The ratio could distinguish these regimes.

- **Acoustic backscatter (where available).** Acoustic sensors respond differently to particle size than optical sensors. The ratio of optical turbidity to acoustic backscatter encodes particle size information. This is available at a subset of USGS sites and would be extremely valuable if it can be incorporated.

### 7b. Sediment connectivity

Sediment delivery from hillslopes to channels depends on connectivity — whether there is a continuous transport pathway. Features like riparian buffer width, wetland percentage, and distance from sediment source to channel are all controls on connectivity. The current feature set does not include any connectivity proxy. The StreamCat "pct_wetland" or similar might partially capture this.

### 7c. Channel slope and stream power

The product of discharge and channel slope is stream power — the energy available for sediment transport. Currently, the model has discharge but not slope at the sampling location. Adding reach-level slope (available from NHDPlus) would allow the model to distinguish high-gradient mountain streams (where extreme events produce coarse, poorly sorted sediment) from low-gradient lowland rivers (where extreme events produce fine, well-sorted sediment).

### 7d. Freeze-thaw cycling

For Kaleb's north Idaho context specifically, freeze-thaw disaggregation of soil aggregates is a critical seasonal sediment source control. A cumulative freeze-thaw cycle count (from daily temperature data) would capture the seasonal build-up of available fine sediment that drives spring erosion. This might partially explain why dropping weather hurts spring performance.

### 7e. Wildfire history

I raised this in Phase 4 and it remains untested. Post-fire watersheds have fundamentally altered turbidity-SSC relationships for 2-5 years after fire. A binary "recent fire in watershed" flag from MTBS data could explain substantial residual variance at affected sites.

---

## 8. Physics-Based Argument for the Optimal Feature Set

Yes, there is a principled physics-based argument for the minimum feature set. The turbidity-SSC relationship is governed by three categories of physical controls, each of which requires specific features:

### Category 1: Optical scattering properties of the particle population
**Controls:** What particles are in the water, what they look like optically.
**Required features:** Lithologic composition (SGMC key types), watershed land cover (source material), season (biological interference).
**Current coverage:** Partially covered by SGMC and land use features.

### Category 2: Hydrologic regime and sediment supply state
**Controls:** How much sediment is available and how much energy is moving it.
**Required features:** turb_Q_ratio (supply-transport balance), flush_intensity (event position), precipitation features (antecedent conditions and current storm), baseflow_index (groundwater contribution).
**Current coverage:** Well covered.

### Category 3: Measurement context
**Controls:** How the turbidity and SSC measurements were made.
**Required features:** sensor_family (optical sensor type), collection_method (SSC sampling protocol), turb_source (data provenance), turb_below_detection (censoring).
**Current coverage:** Well covered.

### Category 4: Infrastructure modification
**Controls:** How human activity alters natural sediment dynamics.
**Required features:** dam_storage_density (flow regulation and sediment trapping), developed_pct (impervious surface and construction), agriculture_pct (tillage erosion).
**Current coverage:** Covered.

The **optimal feature set** includes the minimum number of features needed to represent all four categories, where each feature encodes a physically distinct mechanism. Based on the ablation results, my proposed optimal set would be:

**Core (remove any of these and something breaks):**
- turb_Q_ratio — supply-transport separation
- flush_intensity — event-scale sediment dynamics
- precip_48h — current storm energy
- precip_30d — antecedent moisture and first flush
- collection_method — SSC measurement methodology
- sensor_family — turbidity sensor type
- turb_source — data provenance
- temp_instant — viscosity and seasonal biology proxy
- turb_below_detection — censoring information
- sgmc_unconsolidated_sedimentary_undiff — sediment availability
- sgmc_igneous_volcanic — optically anomalous particle populations
- sgmc_metamorphic_volcanic — optically anomalous particle populations
- developed_pct — urban modification
- dam_storage_density — flow regulation

**Retain pending confirmation (likely helpful but needs compound testing):**
- precip_7d — synoptic moisture patterns
- 2-3 additional SGMC features (carbonate, sedimentary carbonate, igneous plutonic)
- agriculture_pct — tillage erosion source

**Drop (physically uninformative or grab-bag categories):**
- All 12 individually harmful features
- Remaining SGMC categories that are undifferentiated mixtures (melange, metamorphic_sedimentary_undiff, etc.)
- Any StreamCat geology features that are redundant with SGMC

This gives a feature set of approximately 17-20 features that is physically interpretable, where every feature maps to a specific mechanism in the turbidity-SSC relationship. This is a much more defensible model for publication than 72 features, many of which are noise.

---

## Summary Assessment

The Phase 5 ablation results are physically coherent and reveal important truths about the model:

1. **turb_Q_ratio dominance is physically correct.** It encodes the supply-transport balance, which is the primary control on how the turbidity-SSC conversion factor varies in time.

2. **Weather features are non-negotiable for extreme events.** The aggregate metric improvement from dropping weather is a statistical trap. Do not fall for it. The events where weather matters are the events that determine whether this tool is useful or useless.

3. **Infrastructure features encode real physics.** Dams and urban development fundamentally alter sediment dynamics in ways that matter most during extremes. Keep them.

4. **Many SGMC features are noise.** The undifferentiated and mixture categories lump physically dissimilar lithologies. Keep the 3-5 that map onto real particle-scattering distinctions; drop the rest.

5. **The path to the final feature set runs through compound testing (Tests A7, B, C, D2) and physically motivated feature engineering (particle size proxy, channel slope, freeze-thaw index).** Do not finalize the feature set based on single-feature ablation alone — compound interactions can surprise you.

The model is learning real sediment transport physics. The ablation results confirm this because the features that matter are the features that *should* matter based on decades of sediment transport research. This is the strongest evidence yet that murkml is not just curve-fitting — it is capturing mechanistic relationships between watershed properties, hydrologic state, and the turbidity-SSC transfer function.

---

*Dr. Catherine Ruiz*
*Sediment Transport & Erosion Mechanics*
