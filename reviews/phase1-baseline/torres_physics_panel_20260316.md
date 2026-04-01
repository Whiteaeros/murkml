# Maria Torres — Regulatory & Practitioner Review
## murkml Physics & Design Panel, 2026-03-16

**Reviewer background:** 25 years in water quality management. Field technician, state monitoring program coordinator, EPA Region 10 TMDL specialist. Currently consulting for small water districts and watershed councils in the Pacific Northwest. Written or reviewed over 100 TMDL documents.

**Documents reviewed:** PRODUCT_VISION.md, physics_panel_plan.md

---

## Question 1: Which water quality parameters drive the most regulatory decisions in the United States?

### Ranking by regulatory action volume

Based on EPA's National Water Quality Inventory reports, ATTAINS data, and my direct experience writing and reviewing TMDLs, here is how parameters rank by the volume of regulatory decisions they trigger:

**Tier 1 — High-volume drivers of 303(d) listings and TMDLs:**

1. **Pathogens (E. coli, enterococci, fecal coliform)** — The single largest cause of impairment nationally for rivers and streams. Drives recreational use impairments in virtually every state. ~23% of assessed river miles exceed enterococci thresholds (EPA 305(b) Report to Congress, 2017). However, the product vision explicitly excludes E. coli, and I agree with that decision for this tool — pathogen sources are primarily point-source or land-use driven, and the relationship to continuous sensor surrogates is weak.

2. **Nutrients (total phosphorus, total nitrogen, nitrate)** — Second largest driver. ~40% of assessed rivers, 51% of lakes list nutrients as a cause of impairment (EPA, Impaired Waters and Nutrients). Drives TMDLs in every state. Phosphorus is the controlling nutrient in most freshwater systems; nitrogen in estuarine/coastal. States are increasingly adopting numeric nutrient criteria (e.g., Oregon's TP criteria of 0.07 mg/L for Willamette tributaries). This is directly in murkml's scope and is the highest-value regulatory target.

3. **Sediment / turbidity / siltation** — Third largest cause of impairment for rivers and streams. ~15% of stream miles assessed as poor due to excess streambed sediments. Drives aquatic life use impairments. This is murkml's current proof-of-concept (SSC), and the regulatory demand is real. Every sediment TMDL I have written needs continuous load estimates.

4. **Temperature** — A major driver in the Pacific Northwest and other salmonid regions. Oregon, Washington, and Idaho all have numeric temperature criteria tied to fish use designations (e.g., Oregon OAR 340-041-0028: 16.0 deg C for core cold water habitat, 18.0 deg C for salmon/trout rearing). Temperature is already a continuous sensor parameter at USGS sites, so murkml does not need to predict it — but it is a critical input feature and a co-stressor the model should account for.

5. **Dissolved oxygen** — Fourth or fifth nationally. States have numeric DO criteria (e.g., Idaho IDAPA 58.01.02: cold water aquatic life minimum 6.0 mg/L; Oregon: 8.0 mg/L for cold water, 6.5 mg/L for cool water). DO impairments are often nutrient-driven (eutrophication). Like temperature, DO is already measured continuously at most USGS sites, but predicting it at ungauged sites has real value.

**Tier 2 — Important but lower volume or harder to predict:**

6. **Total dissolved solids / conductance** — Drives impairments in arid West, mining-affected areas, and irrigation return flow regions. Near-linear relationship with specific conductance makes it an easy win for the model. Regulatory standards vary by state (e.g., Colorado has site-specific TDS standards; Idaho has a secondary standard of 500 mg/L).

7. **pH** — Measured continuously, but pH impairments are usually driven by other stressors (mining, algal photosynthesis/respiration). Predicting pH at ungauged sites is possible but the regulatory demand for modeled pH is lower.

8. **Metals (mercury, copper, zinc, etc.)** — Mercury in fish tissue is a massive driver of fish consumption advisories. Dissolved metals drive aquatic life impairments near mining sites. However, metals are highly site-specific (geology, hardness-dependent criteria) and the cross-site transfer learning approach will struggle with them. I would not recommend including metals in the first release.

### My recommendation for murkml's parameter suite (regulatory priority order):

| Priority | Parameter | Regulatory driver | Cross-site feasibility |
|----------|-----------|-------------------|----------------------|
| 1 | **SSC** (current) | Sediment TMDLs, aquatic life | Good — already working |
| 2 | **Total phosphorus** | Nutrient TMDLs, 303(d) listings | Good — binds to sediment, strong turbidity signal |
| 3 | **Nitrate+nitrite** | Nutrient TMDLs, drinking water (MCL 10 mg/L) | Moderate — seasonal, flow-dependent |
| 4 | **Dissolved oxygen** | Aquatic life use, TMDLs | Good — well-understood physics |
| 5 | **TDS** | Irrigation, drinking water, mining TMDLs | High — near-linear with conductance |

This aligns well with the working list in PRODUCT_VISION.md. Total nitrogen would be a valuable addition eventually, but nitrate+nitrite is the more commonly measured fraction and has better USGS data availability.

---

## Question 2: What precision does a screening-level tool need vs. a compliance-level tool?

This is the most important question for murkml's positioning, so I will be blunt.

### The two tiers of use

**Screening-level use** — "Is this waterbody likely impaired? Should we collect more data here? What is the approximate pollutant load for planning purposes?" This is what watershed councils, state 303(d) listing programs, and TMDL planners actually need most of the time.

**Compliance-level use** — "Does this discharge violate its NPDES permit limit? Does this waterbody meet its water quality standard?" This requires laboratory-grade data with full QA/QC documentation, chain of custody, and method-specific detection limits. An ML model will not be accepted for compliance decisions in the current regulatory framework. Period.

### Precision requirements by parameter

| Parameter | Screening-level tolerance | Compliance-level requirement | Notes |
|-----------|--------------------------|------------------------------|-------|
| **SSC** | +/- 50% of actual, bias < 25% | Lab method (ASTM D3977), +/- 15% RPD | USGS surrogate regressions routinely have RPD of 30-50% and are accepted for load estimation. murkml should aim for comparable performance. |
| **Total phosphorus** | +/- 40-50% for load estimation; correct order of magnitude for screening | Lab method (EPA 365.1), detection limit 0.01 mg/L, +/- 15% RPD | States compare annual or seasonal means to criteria. Getting the right bin (above/below 0.07 mg/L) matters more than exact concentration. |
| **Nitrate+nitrite** | +/- 30% for trend detection; correct seasonal pattern | Lab method (EPA 353.2), detection limit 0.01 mg/L | For drinking water MCL (10 mg/L NO3-N), the screening question is "are we close to 10?" not "are we at 9.2 vs 9.8?" |
| **Dissolved oxygen** | +/- 0.5 mg/L | Sensor (luminescent DO probe), +/- 0.2 mg/L | DO has well-understood physics. The model should be able to get within 0.5 mg/L at gauged-equivalent sites. At ungauged sites, getting the diurnal range direction right matters. |
| **TDS** | +/- 20% (the conductance-TDS relationship is tight) | Lab method (EPA 160.1), +/- 10% | This should be murkml's easiest target. If the model cannot get TDS within 20% at sites with conductance data, something is wrong. |

### Key insight for murkml

**The USGS surrogate regression program provides the benchmark.** USGS publishes model archive summaries for every surrogate regression they deploy (turbidity-to-SSC, turbidity-to-TP, etc.). These are site-specific OLS regressions with R-squared values typically in the 0.6-0.9 range. They are accepted by state agencies for load estimation and TMDL development. If murkml can match or beat USGS site-specific surrogate R-squared values in a cross-site transfer setting, that is a publishable and practically useful result.

Do not try to compete with lab data. Compete with "what would a USGS hydrologist estimate with a site-specific regression?"

For the cross-site transfer case (predicting at a site with no calibration data), wider uncertainty intervals are expected. An honest +/- 100% interval that captures the true value is more useful than a tight interval that misses.

---

## Question 3: What output format do state agencies and watershed councils actually need?

Having worked on both sides — writing TMDLs and reviewing them for EPA — here is what people actually use:

### What TMDL developers need

1. **Daily loads (mass/time)** — This is the core TMDL unit. A TMDL is literally expressed as: `TMDL = WLA + LA + MOS` where all terms are in mass per day (e.g., kg/day of sediment, kg/day of TP). EPA guidance recommends all TMDLs include a daily time increment (EPA, "Options for the Expression of Daily Loads in TMDLs," 2007). To compute daily loads, the model output needs to be:
   - **Instantaneous concentration** (mg/L or similar) at some time step
   - **Paired with discharge** (which USGS provides)
   - Multiplied: Load = Concentration x Discharge x unit conversion factor

   murkml should output concentration time series, not loads. The user computes loads from concentration x flow. This keeps the model's job clean.

2. **Seasonal and annual summary statistics** — States compare monitoring data to criteria using various statistical summaries:
   - Oregon: 30-day mean for DO, 7-day average of daily maxima for temperature
   - Idaho: instantaneous minimum for DO
   - EPA nutrient criteria guidance: seasonal geometric means or medians for TP and TN

   The model should provide time series at a sub-daily resolution (15-minute or hourly) so users can compute whatever summary statistic their state requires. Do NOT bake in a specific averaging period.

3. **Exceedance probability** — "What fraction of the time does this site exceed the water quality standard?" This is the 303(d) listing question. If the model provides concentration + uncertainty intervals, the user can compute: P(concentration > standard) at each time step. This is extremely valuable for screening-level 303(d) assessments. murkml's uncertainty quantification directly enables this.

### What watershed councils need

Watershed councils are typically less technical. They need:

1. **Maps and summaries** — "Where in our watershed are the problem areas?" A tool that produces estimated concentrations at multiple points along a river network, visualized on a map, would be immediately useful.

2. **Before/after comparison capability** — "Did our restoration project reduce sediment loads?" This requires consistent methodology over time, which a standardized model provides.

3. **Annual load estimates** — For grant applications and effectiveness monitoring reports.

### Recommended output format for murkml v1

At minimum:
- **Concentration time series** at the temporal resolution of the input data (15-min if continuous sensors, daily if daily discharge only)
- **Prediction intervals** (upper/lower bounds) at each time step — this is non-negotiable for regulatory credibility
- **Metadata**: what inputs were used, how many calibration samples, model version

Do NOT output:
- Loads (let the user multiply by Q)
- Compliance determinations (that is a regulatory judgment, not a model output)
- Letter grades or color-coded "good/bad" labels (regulators hate when models make their decisions for them)

---

## Question 4: What would make a state agency hydrologist actually USE this tool vs. dismiss it?

This is where I will be the most direct, because I have watched dozens of tools get proposed to state agencies and get ignored. Here are the trust barriers, ranked from most to least critical:

### Barrier 1: "I can't see how it works"

The single biggest trust barrier for ML tools in regulatory settings is the black box problem. State hydrologists (my former colleagues) do not trust what they cannot explain to their supervisor, to EPA reviewers, or to a judge in a citizen lawsuit. Every TMDL is a legally defensible document. If a stakeholder challenges the loading analysis and the state's answer is "the machine learning model said so," the TMDL gets thrown out.

**What murkml must do:**
- For every prediction, show which input features contributed most and in what direction. CatBoost has built-in SHAP support — use it.
- Publish the training data and model weights. Open source is necessary but not sufficient; the data must also be available.
- Provide per-site model diagnostics: at each of the 57 training sites, what was the observed vs. predicted? Where did the model succeed and fail? A state hydrologist will look for sites similar to theirs and evaluate performance there.

### Barrier 2: "How do I know the uncertainty is real?"

State agencies have been burned by models that report tight confidence intervals and then miss wildly on out-of-sample data. murkml's honest uncertainty approach is its best feature from a regulatory perspective — but only if the intervals are demonstrably well-calibrated.

**What murkml must do:**
- Report calibration plots: of all predictions where the model said "90% confidence interval," what fraction actually contained the true value? If the answer is 90% (+/- a few percent), the model is well-calibrated and trustworthy. If it is 60%, the intervals are useless.
- Use the leave-one-site-out evaluation to show this. That is exactly the right validation approach for cross-site transfer.

### Barrier 3: "Who reviewed this?"

State agency staff follow USGS methods because USGS has institutional credibility built over 100+ years. An undergraduate's Python package does not have that credibility. This is not a technical problem; it is a social one.

**What murkml must do:**
- Get the method published in a peer-reviewed journal (the plan already includes this — good).
- Get at least one established USGS or academic researcher to endorse or co-author. A name that state hydrologists recognize on the paper is worth more than any technical feature.
- Present at a practitioners' conference: National Water Quality Monitoring Council, or a regional AWRA conference. State agency staff attend these.
- Start with USGS data and USGS methods vocabulary. Calling it "surrogate regression using gradient boosting with cross-site transfer" speaks the language. Calling it "AI water quality prediction" triggers skepticism.

### Barrier 4: "Does it work in MY watershed?"

Cross-site generalization is the hardest sell. Every state hydrologist believes their watershed is unique (and they are partly right). The 57-site, 11-state dataset helps, but the response will be: "None of those sites are in my watershed."

**What murkml must do:**
- Report performance stratified by watershed characteristics: ecoregion, geology type, drainage area, land use. A state hydrologist in agricultural Indiana can look at the model's performance at similar agricultural sites. A hydrologist in mountainous Idaho can look at similar mountain sites.
- Be explicit about where the model works poorly. If it fails at sites with unusual geology or extreme land use, say so. Honesty about limitations builds more trust than inflated claims.
- Make it easy to add local calibration data. If a user has 20 grab samples from their site, the model should be able to incorporate those and tighten its predictions. This bridges the gap between "generic cross-site model" and "my site-specific regression."

### Barrier 5: "I don't have time to learn a new tool"

State agency hydrologists are overworked and understaffed. If the tool requires Python expertise, command-line operations, or debugging dependency conflicts, it will not be adopted.

**What murkml must do (eventually, not v1):**
- Provide a simple interface: input a site ID, get a report. The current design as a Python library is appropriate for v1 (targeting researchers and technical users), but long-term adoption by practitioners requires a web interface or at minimum a well-documented CLI.
- Output results in formats that integrate with existing workflows: CSV files that can be opened in Excel, or direct compatibility with EPA's ATTAINS data format.

### Summary: The adoption path

The realistic adoption path for murkml in regulatory settings is:

1. **Researchers and USGS cooperators** use it first (v1 target — Python library)
2. **A peer-reviewed paper** validates the method and gets cited
3. **A state agency pilot project** uses it for a screening-level 303(d) assessment or TMDL scoping study (not for compliance)
4. **Word of mouth** among the small community of state water quality modelers
5. **Eventually**, incorporation into EPA guidance as an acceptable screening method (this takes 5-10 years minimum)

Do not try to skip steps. The tool's first regulatory use will be screening, not compliance. Design for that.

---

## Summary of Key Recommendations

1. **Parameter suite is well-chosen.** SSC, TP, nitrate, DO, and TDS cover the top regulatory drivers that are feasible for cross-site ML. Do not add metals or pathogens.

2. **Position as a screening tool, not a compliance tool.** The precision bar for screening (~30-50% for loads, correct order of magnitude for concentrations) is achievable. Compliance precision is not.

3. **Benchmark against USGS site-specific surrogate regressions.** That is the standard state agencies already trust. Matching their R-squared in a cross-site setting is a strong result.

4. **Output concentration time series with prediction intervals.** Let users compute loads and summary statistics. Never output compliance determinations.

5. **Uncertainty calibration is the killer feature.** Well-calibrated prediction intervals are what separates this from every other ML water quality paper. Demonstrate calibration rigorously in the leave-one-site-out evaluation.

6. **Explainability is non-negotiable for regulatory adoption.** Feature importance, per-site diagnostics, and stratified performance reporting are required, not optional.

7. **Get the paper published and get a recognized name on it.** Social credibility matters as much as technical performance in regulatory settings.

---

## Sources

- [EPA National Water Quality Inventory Report to Congress](https://www.epa.gov/waterdata/national-water-quality-inventory-report-congress)
- [EPA Impaired Waters and Nutrients](https://www.epa.gov/tmdl/impaired-waters-and-nutrients)
- [EPA Overview of TMDLs](https://www.epa.gov/tmdl/overview-total-maximum-daily-loads-tmdls)
- [EPA Options for Expression of Daily Loads in TMDLs](https://www.epa.gov/sites/default/files/2015-07/documents/2007_06_26_tmdl_draft_daily_loads_tech.pdf)
- [Oregon DEQ Water Quality Standards — Conventional Parameters](https://www.oregon.gov/deq/wq/pages/wqstandards-conventional-parameters.aspx)
- [Oregon Turbidity Standard OAR 340-041-0036](https://oregon.public.law/rules/oar_340-041-0036)
- [Idaho Water Quality Standards IDAPA 58.01.02](https://www.epa.gov/sites/default/files/2014-12/documents/idwqs.pdf)
- [USGS Super Gage Network](https://www.usgs.gov/centers/oki-water/science/super-gage-network)
- [USGS Surrogate Analysis and Index Developer (SAID) Tool](https://pubs.usgs.gov/publication/ofr20151177)
- [USGS Continuous Water Quality Monitoring and Regression (SIR 2006-5241)](https://pubs.usgs.gov/sir/2006/5241/pdf/sir2006-5241.pdf)
- [Identifying Trustworthiness Challenges in Deep Learning Models for Continental-Scale Water Quality Prediction](https://arxiv.org/html/2503.09947v2)
- [EPA Water Quality Standards Handbook](https://www.epa.gov/wqs-tech/water-quality-standards-handbook)
- [EPA ATTAINS Impairment Cause Descriptions](https://www.epa.gov/system/files/documents/2022-04/34parentattainsdescriptions.pdf)
