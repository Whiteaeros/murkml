# Dr. Elena Vasquez — Hydrogeochemist Review
## Physics & Design Panel, Phase 1 Independent Review
**Date:** 2026-03-16

---

## Question 1: Which water quality parameters should be in the "full suite"?

I recommend a tiered approach: a **core tier** (high confidence, implement first) and an **extension tier** (add after the core is validated). I explicitly exclude several parameters that will tempt you but should be avoided.

### Core Tier (Implement These)

#### 1. Suspended Sediment Concentration (SSC)
**Why it belongs:** Already your proof of concept. Regulatory importance for 303(d) listings, TMDL allocations, and aquatic habitat assessments. Turbidity is the primary continuous surrogate, with discharge as a secondary predictor during sensor gaps.

**What controls it:** Erosion intensity (rainfall erosivity x soil erodibility), channel bed/bank mobilization at high flows, upstream land disturbance. Fundamentally transport-limited in most systems — supply is essentially infinite from the landscape, and discharge governs delivery. During storms, grain size distribution shifts toward coarser material, which is why the turbidity-SSC relationship exhibits hysteresis (Landers & Sturm, 2013, Water Resources Research).

**Cross-site generalization prospect:** MODERATE. The turbidity-SSC relationship varies by grain size distribution and mineralogy across sites. However, catchment attributes (geology, land use, drainage area) provide strong priors. With 57 sites across diverse geologies, this is tractable.

**USGS data availability:** Excellent. SSC (parameter code 80154) is the most widely available discrete sediment measurement at continuous monitoring sites.

#### 2. Total Dissolved Solids (TDS)
**Why it belongs:** Near-linear relationship with specific conductance makes this the easiest parameter to predict. Regulatory importance for drinking water (EPA secondary MCL of 500 mg/L), irrigation suitability, and aquatic life standards.

**What controls it:** Mineral weathering of bedrock and soils, evapotranspiration concentration, anthropogenic inputs (road salt, agriculture, wastewater). TDS is dominated by major ions: Ca2+, Mg2+, Na+, K+, HCO3-, SO42-, Cl-, SiO2. The relationship TDS = k * SC holds well within a given water type, where k ranges from 0.55 to 0.75 depending on ionic composition (Hem, 1985, USGS Water-Supply Paper 2254). The factor is lower (~0.55) for calcium-bicarbonate waters and higher (~0.70-0.75) for sodium-chloride or sulfate-dominated waters.

**Cross-site generalization prospect:** HIGH. The conductance-TDS relationship is well-behaved. The site-specific k factor can be estimated from geology (carbonate vs. silicate vs. evaporite terrain). This is arguably the easiest extension from SSC.

**USGS data availability:** Good. TDS (parameter code 70300) and residue on evaporation at 180C (parameter code 70300) are widely measured in discrete samples.

#### 3. Dissolved Oxygen (DO)
**Why it belongs:** Aquatic life criteria are built around DO. Nearly every state has numeric DO standards (typically 5-6 mg/L minimum for cold-water fisheries, 4-5 mg/L for warm-water). Already measured continuously, so the "prediction" here is really about DO deficit — the departure from saturation — which encodes biological oxygen demand information.

**What controls it:** Two regimes:
- **Physical:** Solubility is thermodynamically constrained by temperature and pressure. The Benson & Krause (1984) equation in Limnology and Oceanography gives DO saturation as a function of T and atmospheric pressure. This is an exact, universal relationship — valid 0-40C, freshwater to 40 PSU. USGS adopted this in their DOTABLES program (USGS Technical Memorandum 2011.03).
- **Biological/chemical:** DO deficit below saturation reflects oxygen demand from organic matter decomposition (BOD), sediment oxygen demand, and nutrient-driven eutrophication, minus reaeration. The deficit is kinetically controlled and site-dependent.

**Cross-site generalization prospect:** HIGH for saturation prediction (pure thermodynamics). MODERATE for deficit prediction (requires understanding of organic loading and reaeration, which vary by site). The ML model should predict DO deficit (= DOsat - DOobserved) rather than raw DO, using temperature to compute DOsat analytically.

**USGS data availability:** Excellent. Continuous DO sensors at nearly all 57 sites. Discrete DO measurements also common.

#### 4. Nitrate + Nitrite as N (NO3+NO2-N)
**Why it belongs:** Nitrate is the most common groundwater contaminant in the US, drives eutrophication in receiving waters, has an MCL of 10 mg/L, and is increasingly measured by continuous UV-absorbance sensors (USGS parameter code 99133 for continuous nitrate). It has strong multi-sensor signal: temperature, conductance, discharge, and DO all carry information about nitrate cycling.

**What controls it:** Agricultural fertilizer application, atmospheric deposition, biological nitrogen fixation, and point sources (wastewater). In-stream cycling involves nitrification (NH4+ to NO3-, aerobic, temperature-dependent) and denitrification (NO3- to N2, anaerobic, temperature-dependent). Seasonal patterns are strong: high nitrate in winter/spring (low biological uptake, high discharge flushing) and low in summer (biological uptake, denitrification). The C-Q relationship for nitrate is typically chemostatic in agricultural watersheds (transport-limited from legacy soil stores) but chemodynamic in forested/mixed watersheds (Moatar et al., 2017, Water Resources Research).

**Cross-site generalization prospect:** MODERATE. Strong seasonal and hydrological signals are transferable. But point sources, tile drainage, and legacy nitrogen stores create site-specific baselines that require catchment attributes (land use, specifically % agricultural) as features. The fact that 71% of catchments show biological mediation of nitrate at low flows (Moatar et al., 2017) means summer predictions will be harder than winter.

**USGS data availability:** Good. Nitrate+nitrite (parameter code 00631) is one of the most commonly analyzed nutrients in USGS discrete sampling. Continuous nitrate sensors are expanding rapidly.

#### 5. Total Phosphorus (TP)
**Why it belongs:** The nutrient driving eutrophication in most US freshwater systems. 303(d) listings for phosphorus are extremely common. Strong physical coupling to sediment — particulate P typically represents 60-90% of TP during storm events, making SSC a powerful predictor of TP.

**What controls it:** Two distinct pools:
- **Particulate P (PP):** Sorbed to sediment particles, especially fine clays and iron/aluminum oxides. Controlled by erosion and sediment transport — essentially co-varies with SSC. Sorption capacity varies with grain size: ~116 ug/g for fine silt down to ~50 ug/g for sand (these values are site-dependent based on mineralogy and P saturation of soils).
- **Dissolved P (DP, orthophosphate):** Controlled by desorption equilibria, point sources (wastewater effluent is typically 1-5 mg/L TP), and biological uptake. Less predictable from sensors alone.

**Cross-site generalization prospect:** MODERATE-HIGH for TP during high-flow events (dominated by particulate P, tightly coupled to SSC/turbidity). LOW-MODERATE for TP during baseflow (dominated by dissolved P from point sources and groundwater, highly site-specific). The model should learn to weight SSC/turbidity heavily during storms and rely more on conductance and catchment attributes during baseflow.

**USGS data availability:** Good. Total phosphorus (parameter code 00665) is widely measured. Orthophosphate (00671) is also common.

### Extension Tier (Add After Core Validation)

#### 6. Specific Conductance (SC) — as a predicted parameter at ungauged sites
SC is already a continuous sensor input, but predicting it at sites WITHOUT sensors (from catchment attributes, discharge, and season) would enable the model to bootstrap TDS predictions anywhere. This is feasible because SC is strongly controlled by geology, dilution at high flows, and evapoconcentration at low flows.

#### 7. pH
pH is continuously measured, but predicting it at ungauged sites requires understanding the carbonate buffering system, which is geology-dependent but reasonably predictable from alkalinity and pCO2. I discuss why this is harder than it looks in Question 3.

### Parameters NOT in Scope (See Question 3 for Details)
- Alkalinity (too site-specific in its relationship to other measurables)
- Individual major ions (Ca, Mg, Na, Cl, SO4) — not enough cross-site discrete data
- Total Nitrogen (analytical complexity, see Question 4)
- E. coli / pathogens (different domain entirely)
- Metals (too dependent on local geology, mining, and redox)

---

## Question 2: Which inter-parameter relationships are well-established enough to encode as physics constraints?

I classify each candidate relationship into three categories:
- **THERMODYNAMIC** — derived from equilibrium chemistry, always true within stated conditions. Safe to hardcode.
- **EMPIRICAL-UNIVERSAL** — empirically derived but confirmed across hundreds of studies and sites. Safe as soft constraints with known uncertainty bounds.
- **EMPIRICAL-CONDITIONAL** — true within certain conditions but breaks under others. Use as soft constraints with conditions, or avoid.

### Constraint 1: DO Saturation as f(Temperature, Pressure) — THERMODYNAMIC

**Classification:** THERMODYNAMIC. This is derived from Henry's Law and the thermodynamics of gas dissolution. It is exact.

**Equation:** The Benson & Krause (1984) formulation, as implemented in USGS DOTABLES:

```
ln(DO_sat) = -139.34411 + (1.575701e5 / T) - (6.642308e7 / T^2)
             + (1.243800e10 / T^3) - (8.621949e11 / T^4)
```

Where T is absolute temperature in Kelvin and DO_sat is in mg/L at 1 atm, zero salinity.

For non-standard pressure, apply:

```
DO_sat(P) = DO_sat(1atm) * P * [(1 - Pwv/P) * (1 - theta*P)] / [(1 - Pwv) * (1 - theta)]
```

Where P is barometric pressure in atm, Pwv is water vapor pressure, and theta is a temperature-dependent parameter.

**Citation:** Benson, B.B. & Krause, D., 1984. The concentration and isotopic fractionation of oxygen dissolved in freshwater and seawater in equilibrium with the atmosphere. Limnology and Oceanography, 29(3), 620-632. Adopted by USGS in Technical Memorandum 2011.03.

**When it holds:** Always, for freshwater between 0-40C and pressure 0.5-1.1 atm. This covers every USGS site in your dataset.

**When it breaks:** Never, within stated range. This is thermodynamics, not a fit.

**How to encode:** This should be a **hard architectural constraint**, not a penalty. Compute DO_sat analytically from measured temperature and station elevation (for pressure). Then the ML model predicts DO deficit (DO_sat - DO_observed), which must be non-negative (you cannot supersaturate indefinitely — but note that transient supersaturation DOES occur during algal blooms, so allow DO > DO_sat by a modest margin, say up to 120% saturation). The constraint is: predicted DO <= ~1.2 * DO_sat(T, P).

**Strength of recommendation:** IMPLEMENT THIS FIRST. It is the strongest, most defensible constraint in the entire system.

### Constraint 2: Non-negative Concentrations — THERMODYNAMIC

**Classification:** THERMODYNAMIC. Concentrations of dissolved or suspended material cannot be negative. This is definitional.

**Equation:** For all parameters: predicted value >= 0.

**When it breaks:** Never.

**How to encode:** **Hard architectural constraint.** Use a ReLU or softplus output activation. This is trivially important and should be in place from day one. CatBoost doesn't natively enforce this, but post-processing clipping or a custom loss function with a steep penalty below zero works.

**Strength of recommendation:** IMPLEMENT IMMEDIATELY. Embarrassing to produce negative concentrations.

### Constraint 3: Conductance-TDS Proportionality — EMPIRICAL-UNIVERSAL

**Classification:** EMPIRICAL-UNIVERSAL. The relationship TDS = k * SC is well-established across thousands of water samples worldwide.

**Equation:**
```
TDS = k * SC
```
Where SC is specific conductance in uS/cm at 25C, TDS is in mg/L, and k is a dimensionless factor.

**Typical k values by water type:**
- Calcium-bicarbonate dominated (carbonate terrain): k = 0.55 - 0.60
- Mixed cation/anion: k = 0.60 - 0.65
- Sodium-chloride dominated (e.g., road salt, coastal): k = 0.65 - 0.70
- Sulfate-dominated (e.g., mining, evaporite): k = 0.70 - 0.80

**Citation:** Hem, J.D., 1985. Study and Interpretation of the Chemical Characteristics of Natural Water, 3rd ed. USGS Water-Supply Paper 2254. Also: Rusydi, A.F., 2018. Correlation between conductivity and total dissolved solid in various type of water: A review. IOP Conference Series: Earth and Environmental Science, 118, 012019.

**When it holds:** Stable ionic composition at a given site. Works well at individual sites (R2 > 0.95 typical). Works reasonably across sites with similar geology.

**When it breaks:**
- When ionic composition changes (e.g., road salt event shifts water from Ca-HCO3 to Na-Cl type, changing k mid-event)
- At very high TDS (>10,000 mg/L), the relationship becomes non-linear as ion pairing and activity coefficient effects become significant
- When significant non-ionic dissolved solids are present (silica, organic matter)

**How to encode:** **Soft penalty.** The model predicts TDS, and the loss function penalizes deviations from TDS = k * SC, where k is either a learned site-level parameter (bounded 0.50-0.85) or estimated from catchment geology. Do NOT hardcode k — let the model learn it within bounds.

**Strength of recommendation:** HIGH. This is one of the best-characterized relationships in water chemistry.

### Constraint 4: SSC-Turbidity Positive Association — EMPIRICAL-CONDITIONAL

**Classification:** EMPIRICAL-CONDITIONAL. At a single site with stable sediment characteristics, turbidity and SSC are positively correlated (more sediment = more light scattering). But the slope, intercept, and even functional form vary enormously across sites.

**Equation (per-site):**
```
SSC = a * Turbidity^b
```
Where a and b are site-specific. Typical b ranges from 0.8 to 1.5. Some sites are well-fit by linear models; others require power-law or log-log transforms. Rasmussen et al. (2009, USGS Techniques and Methods 3-C4) provide the standard methodology.

**When it holds:** Within a site, during periods of stable sediment supply and grain size distribution.

**When it breaks:**
- **Across sites:** Different mineralogy (dark minerals scatter differently than light ones), different grain size distributions (fine clay scatters more per unit mass than coarse silt/sand), and different sensor technologies (FNU vs. NTU vs. FBU) all change the relationship fundamentally.
- **Within a site during storms:** Hysteresis in the SSC-turbidity relationship occurs when grain size distributions shift between the rising and falling limb of the hydrograph (Landers & Sturm, 2013, Water Resources Research). Clockwise hysteresis indicates proximal coarse sources mobilized early; counterclockwise indicates distal fine sources arriving late.
- **Biological turbidity:** Algal blooms produce high turbidity with minimal SSC.

**How to encode:** Do NOT enforce turbidity-SSC monotonicity as a global constraint. The PRODUCT_VISION.md already correctly identifies this. Instead, use turbidity as a strong input feature and let the ML model learn site-adapted relationships. If you want a soft constraint, enforce only the weak version: "when turbidity increases by more than 50% and discharge also increases, SSC should not decrease." But honestly, even this has edge cases. Let the model learn it.

**Strength of recommendation:** LOW for a cross-site constraint. HIGH as a feature importance expectation (turbidity should rank as the #1 or #2 feature for SSC prediction in SHAP analysis — if it doesn't, something is wrong).

### Constraint 5: TP-SSC Positive Coupling During High Flows — EMPIRICAL-CONDITIONAL

**Classification:** EMPIRICAL-CONDITIONAL. During storm events and high-flow conditions, particulate phosphorus dominates total phosphorus, and particulate P is physically attached to sediment particles. So TP and SSC should be positively correlated when discharge is elevated.

**Equation (approximate):**
```
PP ≈ [P_content] * SSC
```
Where [P_content] is the phosphorus content of suspended sediment in mg P per mg sediment. Typical range: 0.5 - 3.0 mg P / g sediment, depending on soil P saturation and grain size.

During baseflow: TP ≈ DP (dissolved P dominates), and the SSC-TP relationship weakens or disappears.

**When it holds:** High-flow events where particulate P dominates (typically Q > median Q, SSC > ~50 mg/L). Agricultural watersheds with high soil P.

**When it breaks:** Baseflow conditions (DP from point sources dominates TP), watersheds with low soil P saturation, and sites below wastewater treatment plants where DP is the dominant P source regardless of flow.

**How to encode:** **Conditional soft penalty.** When discharge > some threshold (e.g., 75th percentile for that site) AND SSC is elevated, penalize cases where TP prediction decreases while SSC prediction increases. Do not apply during baseflow.

**Strength of recommendation:** MODERATE. Worth including but requires the discharge-conditional logic.

### Constraint 6: Charge Balance / Electroneutrality — THERMODYNAMIC (but impractical for MVP)

**Classification:** THERMODYNAMIC. The sum of cation equivalents must equal the sum of anion equivalents in any water sample. Acceptable error is +/- 5% (Hem, 1985).

```
Sum(cation_eq) = Sum(anion_eq)
```

**Why I mention it but do NOT recommend implementing it:** This constraint requires predicting individual major ions (Ca, Mg, Na, K, HCO3, SO4, Cl), which is NOT in the core tier. If you ever extend to predicting individual ions, this becomes a powerful joint constraint. For now, file it away.

### Constraint 7: Mass Balance — THERMODYNAMIC (but requires network topology)

**Classification:** THERMODYNAMIC. At a confluence, the load (concentration * discharge) downstream must equal the sum of loads from upstream tributaries, minus in-stream losses, plus in-stream gains.

```
C_downstream * Q_downstream = C_upstream1 * Q_upstream1 + C_upstream2 * Q_upstream2 + delta
```

**Why I mention it but do NOT recommend implementing it:** This requires knowing the network topology and having predictions at multiple connected sites simultaneously. It is architecturally complex. Powerful if you build a network-aware model later, but not for the MVP.

### Summary Table: Constraints by Priority

| Constraint | Type | Encode As | Priority |
|---|---|---|---|
| Non-negative concentrations | Thermodynamic | Hard (output activation) | P0 — immediate |
| DO saturation f(T, P) | Thermodynamic | Hard (analytical calculation) | P0 — immediate |
| SC-TDS proportionality | Empirical-universal | Soft penalty, bounded k | P1 — core |
| TP-SSC coupling at high Q | Empirical-conditional | Conditional soft penalty | P2 — after validation |
| Turbidity-SSC monotonicity | Empirical-conditional | Do NOT encode globally | -- |
| Charge balance | Thermodynamic | Future (needs ion predictions) | P3 — future |
| Mass balance | Thermodynamic | Future (needs network model) | P3 — future |

---

## Question 3: Parameters that seem important but should NOT be included

### Alkalinity
Alkalinity (as CaCO3) controls the buffering capacity of water, determines the carbonate equilibrium, and governs pH stability. It seems like a natural candidate because it is widely measured and chemically important.

**Why to exclude it:** Alkalinity is primarily controlled by bedrock geology (carbonate vs. silicate terrain) and soil CO2 concentrations. The problem is that alkalinity has essentially no continuous sensor surrogate. It does not correlate strongly with conductance across diverse geologies — a calcium-bicarbonate water and a sodium-chloride water can have the same conductance but wildly different alkalinities. There is no continuous sensor signal that reliably predicts alkalinity cross-site. Within a single site, conductance is a decent proxy (because ionic composition is stable), but cross-site, it fails.

Furthermore, the carbonate system (CO2-HCO3--CO32-) equilibrium is notoriously sensitive to pH and pCO2, both of which are kinetically controlled by gas exchange and biological activity. Predicting alkalinity requires solving non-linear equilibrium equations with site-specific inputs. This is solvable in principle but adds significant complexity for a parameter that most practitioners do not need in real-time.

**Bottom line:** Leave alkalinity out of the core model. If someone needs it, they can measure it — it is a cheap and simple lab test.

### Individual Major Ions (Ca2+, Mg2+, Na+, K+, Cl-, SO42-)
These are the building blocks of TDS and conductance. Predicting them individually would be powerful for understanding weathering processes and salt loading.

**Why to exclude them:** The USGS discrete sampling record for individual ions is sparser than for SSC, nutrients, or TDS. More critically, the relationships between conductance and individual ions are entirely geology-dependent. A site on limestone (Ca-HCO3 water) has completely different ion ratios than a site draining shale (Na-SO4 water) or one receiving road salt (Na-Cl water). There is no universal sensor-to-ion relationship. You would need to essentially build a geochemical speciation model, which defeats the purpose of the ML approach.

**Exception:** Chloride in regions with road salt application might be tractable because Cl is conservative (no biological cycling) and conductance is heavily influenced by Cl in impacted streams. But this is a regional, not universal, model.

### Metals (Fe, Mn, Cu, Zn, Pb, As, etc.)
Heavy metals are important contaminants, especially near mining operations and urban areas.

**Why to exclude them:** Metal concentrations are controlled by redox chemistry, pH, complexation with organic ligands, and sorption to iron/manganese oxide surfaces. These processes are exquisitely site-dependent. Iron and manganese, for example, are soluble under reducing conditions (groundwater, hyporheic zone, stratified reservoirs) and precipitate under oxidizing conditions (surface water). Predicting dissolved metals requires knowing the local redox environment, organic carbon concentrations, and mineral surfaces — information not available from standard continuous sensors. Additionally, most USGS sites do not have routine metals data unless they are near known contamination sources, making cross-site training data sparse.

### Biological Oxygen Demand (BOD) / Chemical Oxygen Demand (COD)
BOD and COD are important for wastewater effluent compliance and reflect organic matter loading.

**Why to exclude them:** BOD is a kinetic measurement (5-day incubation), not an equilibrium concentration. It depends on the microbial community, temperature during incubation, and the nature of the organic substrate. These vary enormously across sites. COD is more standardized analytically but still reflects a complex mixture of organic and inorganic reductants. Neither has a reliable relationship to continuous sensor parameters across diverse sites. In-stream BOD is conceptually related to DO deficit, but the relationship is confounded by reaeration rate, which depends on channel morphology and turbulence.

### E. coli / Fecal Indicator Bacteria
Already excluded in the PRODUCT_VISION.md, and correctly so. Bacterial concentrations are controlled by point-source inputs (CSOs, failing septic, livestock access), die-off kinetics (UV exposure, temperature), and resuspension from bed sediments. Turbidity is sometimes correlated with E. coli during storm events (because both increase with runoff), but this is a confounded correlation, not a causal one. Cross-site generalization is essentially impossible without source-specific data.

---

## Question 4: What species-level distinctions matter?

This is critical. Getting the analyte definition wrong will poison your training data and make your model predictions uninterpretable. Here are the distinctions that matter most for this project:

### SSC vs. TSS — THIS IS NOT NEGOTIABLE

**Use SSC. Never use TSS. Never mix them.**

Gray et al. (2000, USGS Water-Resources Investigations Report 00-4191) demonstrated conclusively that SSC and TSS are not comparable for natural waters. The TSS method (APHA Standard Methods 2540D) uses a subsample from a stirred container, which systematically undermines the sand fraction due to differential settling. SSC (ASTM D3977-97) uses the entire sample volume. When sand-size material exceeds ~25% of the sample, TSS systematically underestimates true suspended sediment by 25-50% or more.

Your model trains on SSC and predicts SSC. If a user feeds in TSS data for validation, the comparison is invalid. This must be clearly documented.

USGS parameter codes: SSC = 80154. TSS = 00530. Do not pull 00530.

### Nitrate+Nitrite (NO3+NO2-N) vs. Total Nitrogen (TN) vs. Nitrate alone

**Use nitrate+nitrite as N (parameter code 00631) for the core model.**

Rationale:
- Nitrate+nitrite is the most widely measured nitrogen species in USGS discrete sampling
- Continuous UV-Vis nitrate sensors (parameter code 99133) measure nitrate+nitrite, so you have both discrete and continuous data streams
- Nitrate typically comprises 60-95% of dissolved inorganic nitrogen in oxygenated surface water, so nitrate+nitrite is functionally equivalent to DIN (dissolved inorganic nitrogen) in most rivers

**Do NOT attempt to predict Total Nitrogen (TN) in the core model.** TN = NO3+NO2-N + NH4-N + organic N. The organic nitrogen fraction is analytically complex (requires Kjeldahl digestion or alkaline persulfate digestion), has higher analytical uncertainty, and is controlled by completely different processes (biological production and decomposition of organic matter). The relationship between sensor parameters and organic N is weak and site-dependent. The USGS has published an entire report on the challenges of TN measurement (Patton & Kryskalla, 2011, USGS Open-File Report 2012-5281).

**Exception:** If you have sites where TKN (Total Kjeldahl Nitrogen) is not available but TN is, and you also have NO3+NO2-N, you could use TN - (NO3+NO2-N) as an estimate of organic-N + NH4-N. But do not make this a prediction target — it is too noisy.

Ammonia (NH4-N, parameter code 00608) could be a future extension target at sites below wastewater outfalls, but it is typically a small fraction of total N in well-oxygenated rivers and is rapidly nitrified. Leave it for later.

### Total Phosphorus (TP) vs. Dissolved Phosphorus (DP/orthophosphate)

**Predict Total Phosphorus (parameter code 00665) as the primary target.**

Rationale:
- TP is the regulatory standard. TMDL allocations and water quality criteria are expressed as TP.
- TP includes both particulate and dissolved forms, and the model has strong predictors for both: turbidity/SSC for particulate P, and conductance/baseflow indicators for dissolved P.
- The model can implicitly learn to weight SSC/turbidity during storms (when PP dominates) and other features during baseflow (when DP dominates).

**Orthophosphate as dissolved P (parameter code 00671) should be a secondary target**, not a replacement for TP:
- Ortho-P is the bioavailable fraction — ecologically important but not the regulatory metric
- Ortho-P is more challenging to predict cross-site because it is controlled by point sources and desorption equilibria, which are highly site-specific
- It adds value in the multi-target framework because the model can learn that TP >= ortho-P (a valid constraint)

**If you predict both TP and ortho-P, enforce TP >= ortho-P as a hard constraint.** This is definitional — total phosphorus includes dissolved phosphorus. Any violation means the model is producing nonsense.

### TDS: Dissolved residue vs. calculated TDS

**Use residue on evaporation at 180C (parameter code 70300) as the TDS measurement.**

Some older records calculate TDS as the sum of measured ion concentrations. These "calculated TDS" values are systematically lower than evaporative TDS because they miss volatile organics and incompletely dissolved silica. Use the evaporative measurement when available. When only calculated TDS is available, it is usable but note the systematic bias.

### Summary: Parameter Codes to Pull

| Parameter | USGS Code | Analyte Definition | Notes |
|---|---|---|---|
| SSC | 80154 | Suspended sediment concentration | NEVER use TSS (00530) |
| TDS | 70300 | Residue on evaporation at 180C | Prefer over calculated sum |
| DO | 00300 | Dissolved oxygen | Sensor + discrete both |
| NO3+NO2-N | 00631 | Nitrate+nitrite as nitrogen | NOT total nitrogen |
| TP | 00665 | Total phosphorus | Regulatory metric |
| Ortho-P | 00671 | Orthophosphate as P, dissolved | Secondary target |
| Temperature | 00010 | Water temperature | Input, not target |
| Conductance | 00095 | Specific conductance at 25C | Input, not target |
| Turbidity | 63680 | Turbidity, FNU | Input, not target |
| Discharge | 00060 | Discharge | Input, not target |
| pH | 00400 | pH | Input, not target |

---

## Final Notes for the Architecture Team

1. **Predict DO deficit, not raw DO.** Compute DO_sat analytically from temperature and elevation. The ML model predicts (DO_sat - DO_observed), which is the ecologically meaningful quantity. This transforms a thermodynamically constrained problem into a biological/kinetic one that ML is well-suited for.

2. **The SC-TDS constraint is your easiest win.** If you can show that enforcing TDS = k * SC (with learned, bounded k) reduces TDS prediction error compared to unconstrained ML, you have a clean, publishable result demonstrating the value of physics-guided ML.

3. **TP-SSC coupling is your most interesting constraint.** It is conditional (only during high flows), involves two predicted targets (TP and SSC), and captures a real geochemical process (erosion-driven particulate P transport). If this constraint improves predictions, it demonstrates that multi-target physics-guided ML captures real hydrogeochemical processes. That is a paper.

4. **Do not over-constrain.** Two hard constraints (non-negative, DO saturation cap) and one or two soft constraints (SC-TDS, conditional TP-SSC) are plenty for the MVP. Adding constraints that are wrong or too restrictive will degrade performance and be harder to debug than having no constraints at all. A wrong constraint forces the model to fit something false — this is worse than pure ML with no physics.

5. **Validate constraints before enforcing them.** Before encoding any soft constraint, verify it holds in your training data. Plot TDS vs SC for all 57 sites. If the relationship is clean (it will be), encode it. Plot TP vs SSC colored by flow regime. If the high-flow coupling is real (it will be), encode it. If a relationship does not appear in the data, do not enforce it in the model.

---

## References

- Benson, B.B. & Krause, D., 1984. The concentration and isotopic fractionation of oxygen dissolved in freshwater and seawater in equilibrium with the atmosphere. Limnology and Oceanography, 29(3), 620-632.
- Gray, J.R., Glysson, G.D., Turcios, L.M., & Schwarz, G.E., 2000. Comparability of suspended-sediment concentration and total suspended solids data. USGS Water-Resources Investigations Report 00-4191.
- Hem, J.D., 1985. Study and Interpretation of the Chemical Characteristics of Natural Water, 3rd ed. USGS Water-Supply Paper 2254.
- Landers, M.N. & Sturm, T.W., 2013. Hysteresis in suspended sediment to turbidity relations due to changing particle size distributions. Water Resources Research, 49(9), 5487-5500.
- Moatar, F., Abbott, B.W., Minaudo, C., Curie, F., & Pinay, G., 2017. Elemental properties, hydrology, and biology interact to shape concentration-discharge curves for carbon, nutrients, sediment, and major ions. Water Resources Research, 53(2), 1270-1287.
- Patton, C.J. & Kryskalla, J.R., 2011. Colorimetric determination of nitrate plus nitrite in water by enzymatic reduction, automated discrete analyzer methods. USGS Techniques and Methods 5-B8. (Also: USGS SIR 2012-5281 on TN assay methods.)
- Rasmussen, P.P., Gray, J.R., Glysson, G.D., & Ziegler, A.C., 2009. Guidelines and procedures for computing time-series suspended-sediment concentrations and loads from in-stream turbidity-sensor and streamflow data. USGS Techniques and Methods 3-C4.
- Rusydi, A.F., 2018. Correlation between conductivity and total dissolved solid in various type of water: A review. IOP Conf. Ser.: Earth Environ. Sci., 118, 012019.
- USGS Office of Water Quality Technical Memorandum 2011.03: Change to Solubility Equations for Oxygen in Water.
