# Dr. Catherine Ruiz — Data Patterns Review
## 2026-03-30

**Background:** 15 years sediment transport research. Fluvial geomorphology, particle mobilization thresholds, in-situ monitoring of suspended sediment dynamics. I think about what moves the grains.

---

## Question 1: What other patterns should we look for?

### Hysteresis classification — the single biggest untapped signal

You have 213 site-days with 10+ samples. That is a gold mine you are sitting on and barely using. Every one of those site-days contains a clockwise or counterclockwise hysteresis loop in turbidity-discharge space. Clockwise hysteresis means the sediment source is proximal (channel bed, banks, near-channel hillslopes) — supply gets exhausted before the discharge peak. Counterclockwise means the source is distal (upland, tributary, headwater) — sediment arrives after the peak. This is not decorative. It tells you the dominant sediment delivery mechanism at each site.

**What to test:**
- For each ISCO burst day, compute the hysteresis index (e.g., Lawler et al. 2006 or Zuecco et al. 2016 method). Classify as CW, CCW, figure-eight, or complex.
- Correlate hysteresis class with model residuals. I predict CCW sites have systematically different SSC/turbidity ratios because the sediment arriving late is finer (long travel distance = coarse fraction dropped en route).
- Check if hysteresis class correlates with your watershed features — drainage area, slope, percent impervious. If it does, you have a physically interpretable feature that could improve the model.

### Rising vs. falling limb performance

Related to hysteresis but testable across all sites, not just ISCO bursts. For any sample, determine whether discharge was rising or falling at the time of collection (compare to the preceding and following hourly Q values). The turbidity-SSC relationship is fundamentally different on the rising limb (fresh erosion, coarse unsorted material, high SSC/turbidity ratio) versus the falling limb (fines settling out of the receding flow, lower ratio). If your model does not know which limb it is on, it is flying partially blind.

### Particle size as the hidden variable

The SSC/turbidity ratio is a proxy for particle size distribution. High ratio = coarse-dominated (sand scatters less light per unit mass). Low ratio = fine-dominated (clays and silts scatter efficiently). Your collection method differences (auto_point ratio 2.10 vs grab 1.56) are almost certainly a particle size effect — ISCO intakes near the bed capture more of the coarse bedload-adjacent suspended fraction. But particle size also varies by:
- Season (spring snowmelt mobilizes different size fractions than summer thunderstorms)
- Geology (sandstone watersheds vs. clay-rich glacial till)
- Antecedent conditions (long dry period = available fines on surface)

**Test:** Regress the SSC/turbidity ratio against your lithology features, drainage area, and season. If lithology predicts the ratio, that is a physically meaningful finding worth a paragraph in the paper.

### Antecedent moisture and sediment supply

You have discharge time series. Compute antecedent flow metrics: mean Q over the preceding 7, 14, 30 days. Also compute days-since-last-event (where "event" = Q exceeding some threshold like 2x median). After a long dry spell, the first flush carries disproportionate sediment (the "first flush effect"). After repeated storms, supply gets depleted and SSC per unit Q drops. This is fundamental sediment transport physics and it is testable with your existing data.

### Spatial autocorrelation of residuals

Plot your model residuals on a map. If neighboring sites have similar residual signs, the model is missing a spatially structured process — likely geology, land use, or regional hydroclimatic regime. Compute Moran's I on the residuals. If it is significant, you have evidence that adding spatial features (or a spatial random effect) would help.

---

## Question 2: Adaptation hurting extremes at N=20

This is entirely expected from a sediment transport perspective, and I can tell you exactly what is happening physically.

### The physical mechanism

Your calibration samples at N=20 are dominated by routine conditions because that is when samples get collected. The Bayesian update learns a site-specific bias correction tuned to the baseflow turbidity-SSC relationship — which is dominated by fine particles, organic matter, and dissolved color interference. Then a storm arrives. The sediment population changes completely: coarser particles mobilized from the bed and banks, higher concentrations, different optical properties. The adaptation, trained on baseflow, actively fights against the storm signal.

This is the **sediment population switching problem**. It is not a statistical artifact. During baseflow, your turbidity signal is contaminated by DOM and algae — the "turbidity" is partly not sediment at all. During storms, the signal is mostly real suspended mineral sediment. These are two fundamentally different physical regimes sharing one sensor.

### What I would do

**Flow-stratified adaptation is the correct physical answer.** The turbidity-SSC relationship genuinely changes with flow regime. Two options:

1. **Two-tier adaptation.** Define a flow threshold (e.g., Q > 2x median = "event"). Maintain separate bias corrections for event vs. non-event conditions. This respects the physics: you are allowing the model to learn that the site has different sediment populations under different hydraulic conditions.

2. **Weight calibration samples by representativeness.** If you must use a single adaptation, upweight storm samples in the Bayesian update. The extreme events carry more information about the sediment transport relationship you actually care about.

3. **Cap adaptation magnitude.** If the shift learned from N=20 normal-condition samples exceeds some threshold (e.g., 30% adjustment), attenuate it for predictions above the 90th percentile of the calibration turbidity range. This is crude but would prevent the collapse you see.

Option 1 is the publishable one. It is physically defensible and solves the actual problem.

### Why this matters for the paper

A reviewer in sediment transport will immediately ask about storm performance. If you report N=20 adaptation with that extreme R^2 collapse, it looks like the model fails exactly when it matters most. You need to either fix it or frame it very carefully — showing that you understand the mechanism and that N=5 or N=10 avoids the problem.

---

## Question 3: Validation tests for paper-readiness

### What a WRR reviewer will demand

**A. Performance stratified by dominant sediment source.**
Your 179 transport-limited vs 3 supply-limited split is a start but too crude. Classify sites by dominant lithology (from your watershed features) and report performance separately. Sandstone-dominated watersheds produce different sediment than glacial-till watersheds. If performance varies by geology, a reviewer will want to know.

**B. Discharge-stratified error analysis.**
Not just "extreme vs normal" but a proper flow-duration curve analysis. Report errors at Q10, Q50, Q90. The community cares about sediment loads, and loads are dominated by the high-flow tail. If your model is accurate at Q50 but has 60% error at Q10, your load estimates will be garbage regardless of your pooled metrics.

**C. Sediment load comparison.**
Pick 10-20 sites with enough data. Compute annual suspended sediment load from (a) observed SSC x Q, (b) model-predicted SSC x Q. Report the percent difference. Loads integrate all the errors over time. A model can have decent R^2 but systematically underestimate peaks and still get loads wrong by 50%. This is the test that matters for any practical application.

**D. Comparison to site-specific rating curves.**
At each site, fit a simple log(SSC) = a + b*log(Q) rating curve using the same calibration data available to your model. Show that your model beats this baseline. If it does not beat a two-parameter rating curve at a given site, the 72-feature model is not adding value there. Report how many sites the model wins vs loses.

**E. Residual analysis by collection method.**
You have shown the SSC/turbidity ratio varies by method. Show the model residuals stratified by method. If auto_point samples have systematically positive residuals (model underpredicts because ISCO captures coarser near-bed particles), that is a known physical bias you should report and discuss.

**F. Independence of test sites.**
If your training and test sites share the same river basins, spatial leakage is a concern. Show a map. Report performance for test sites that are in entirely different HUC-4 basins from any training site.

---

## Question 4: Red flags

### Red flag 1: The 3 supply-limited sites

Only 3 out of 254 sites show supply limitation? That is suspiciously low. Many headwater streams, especially in the western US, are genuinely supply-limited — sediment availability controls transport, not hydraulic capacity. I suspect this finding is an artifact of your detection method. If you are using the overall SSC-Q correlation, a site can be supply-limited during summer (exhausted bank sediment) but transport-limited during spring melt, and the net correlation looks positive. You need to check this seasonally.

If you truly have almost no supply-limited sites, say so explicitly and explain why — probably because the USGS monitoring network is biased toward larger, transport-limited rivers. This is a legitimate sampling bias worth acknowledging.

### Red flag 2: "All rho > 0.3" for turbidity-SSC

This is reported as reassuring but it should not be. A rho of 0.3 means turbidity explains roughly 9% of SSC variance. That is a site where your model's primary input is nearly useless. How many sites have rho < 0.5? These sites are where DOM, algae, color, and instrument differences are dominating the turbidity signal. They deserve special scrutiny — either flag them as low-confidence or explain what other features are compensating.

### Red flag 3: Collection method as confound

The auto_point / depth_integrated split correlates with time of day, day of week, flow condition, SSC magnitude, AND SSC/turbidity ratio. This is a massive confound. Your model's apparently good storm performance may partly reflect the fact that storm samples come from ISCO samplers which have a systematically different SSC/turbidity relationship. If you trained on depth_integrated and predicted auto_point (or vice versa), would performance collapse?

**Test this.** Train on depth_integrated only, predict auto_point only, and vice versa. If there is a large asymmetry, collection method is a confound the model has learned to exploit rather than a signal it has learned to generalize from.

### Red flag 4: External NTU zero-shot NSE = 0.152

This is very low. I know NTU vs FNU is a different measurement, but physically they are both measuring light scattering by particles. NSE of 0.15 means the model barely beats predicting the mean. The jump to 0.43 at N=10 shows adaptation is doing heavy lifting. Be honest about this in the paper — the zero-shot transferability is limited, and adaptation is essential, not optional.

---

## Question 5: Figures for the paper

### Must-include (publishable findings)

1. **Extreme vs normal performance as a function of adaptation N.** This is your most interesting finding. The crossover where adaptation helps normal conditions but destroys extreme performance is physically meaningful and novel. Show it as a line plot: x-axis = N, two lines for extreme R^2 and normal R^2. A reviewer will remember this figure.

2. **SSC/turbidity ratio by collection method with physical interpretation.** Bar chart or violin plot. Annotate with the particle size / intake position explanation. This is a contribution to the monitoring community — people know ISCO and depth-integrated give different results, but quantifying the ratio difference across 35,000 samples is useful.

3. **Map of model residuals.** Color-coded by sign and magnitude. If there is spatial structure, show it. If there is not, that is also a finding worth showing (model generalizes spatially).

4. **Sediment load comparison** (once you compute it). Observed vs predicted annual loads, 1:1 line. This is the figure practitioners will look at first.

5. **Hysteresis examples from ISCO data** (if you analyze it). Two or three representative site-days showing CW and CCW loops with model predictions overlaid. This demonstrates the model captures intra-event dynamics. Visually compelling and physically rich.

### Nice to have

6. **Flow-duration error curve.** MAPE as a function of flow exceedance percentile. Shows where the model is reliable.

7. **Seasonal SSC pattern with model predictions.** Monthly boxplots, observed vs predicted. Demonstrates the model captures the freeze-thaw / snowmelt cycle.

### Do NOT include

- The time-of-day pattern as a standalone figure. It is a sampling artifact, not a finding. Mention it in text as context for the collection method discussion.
- The weekend/weekday pattern. Same reason. Interesting for understanding the data but not a scientific result.

---

## Question 6: What are you missing?

### A. Bedload is the elephant not in the room

Your model predicts suspended sediment concentration. But total sediment transport includes bedload, which turbidity sensors cannot see at all. In coarse-bedded streams (gravel, cobble — common in your north Idaho watersheds), bedload can be 10-60% of total transport during high flows. Your model will systematically underestimate total sediment transport in these systems. You do not need to solve this, but you need to acknowledge it. A sediment transport reviewer will bring it up.

### B. Flocculation in fine-sediment systems

In watersheds with high clay content, suspended particles flocculate — they clump into larger aggregates that settle faster and scatter light differently than their constituent particles. The turbidity-SSC relationship changes with ionic strength (which your conductance feature partially captures) and with turbulence intensity. If your conductance anti-correlation with turbidity is doing real work in the model, part of that may be a flocculation signal: high conductance = high ionic strength = more flocculation = larger effective particles = different optical response. This is testable — check if the conductance feature matters more in clay-rich watersheds.

### C. Sensor fouling and biofouling

Turbidity sensors in the field accumulate biofilms, especially in summer. This causes positive drift — turbidity reads high even when the water is clear. Your seasonal pattern (summer trough) might partly mask a fouling signal. Sites with cleaning schedules vs. neglected sensors will have different error patterns. You probably cannot get cleaning schedule metadata, but you could look for characteristic fouling signatures: slow upward drift in turbidity over weeks, punctuated by sudden drops (when the sensor gets cleaned or a storm scours the lens).

### D. Freeze artifacts

In cold-climate sites (you have these in Idaho, Montana, the upper Midwest), ice formation on or near turbidity sensors creates catastrophic readings — spikes to maximum range or sudden drops to zero. These are not sediment. If you have not already filtered for water temperature < 0 C, you may have ice artifacts in your training data contaminating the cold-season relationship.

### E. The grain size gap

The fundamental limitation of turbidity-based SSC estimation is that turbidity responds to particle surface area while SSC is particle mass. A given mass of clay has orders of magnitude more surface area than the same mass of sand. Without grain size information, you are estimating mass from an area-weighted signal. Your lithology and soil features are proxies for grain size distribution, but they are static — they do not change with flow conditions when the mobilized size fraction shifts. This is the hard physics ceiling on your model's accuracy. Name it. A reviewer who studies sediment transport will respect you more for acknowledging the fundamental limitation than for claiming higher accuracy.

### F. Channel morphology and sampling representativeness

Depth-integrated samples attempt to capture the full vertical profile, but ISCO point samples capture one location. In a river cross-section, SSC varies enormously with depth (Rouse profile — coarse particles concentrated near the bed, fines more uniform). Your auto_point vs depth_integrated ratio difference (2.10 vs 1.71) is partly a Rouse profile effect. But the Rouse profile shape depends on shear velocity, particle settling velocity, and flow depth — all of which change with discharge. This means the collection method bias is not constant; it varies with flow. If your model treats it as a static feature, it is missing this interaction.

**Test:** Within auto_point samples only, does the SSC/turbidity ratio increase with discharge? It should, because higher discharge means stronger vertical mixing, bringing coarser particles up to the ISCO intake depth. If you see this, it is a real physical signal worth reporting.

---

## Summary of priorities

Ranked by impact on paper quality:

1. Compute sediment loads and compare observed vs predicted. Non-negotiable for a sediment transport paper.
2. Analyze the hysteresis in your ISCO burst data. You have the data. Use it.
3. Test collection method as confound (cross-method prediction test).
4. Implement flow-stratified adaptation to fix the extreme-event collapse.
5. Discharge-stratified error analysis (Q10/Q50/Q90).
6. Acknowledge bedload, grain size limitation, and sensor artifacts in the discussion.

The model is solid for what it is. The physics are working in the right direction — conductance as a baseflow indicator, lithology features capturing source material, adaptation capturing site-specific calibration. But the paper needs to show you understand WHY these features work, not just THAT they work. That is what separates a methods paper from a contribution to sediment transport science.

— C. Ruiz
