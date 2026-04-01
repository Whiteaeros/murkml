# Physics & Design Panel — Review Plan

## Context for All Panelists

Read before answering questions:
1. `C:\Users\kaleb\Documents\murkml\PRODUCT_VISION.md` — what we're building
2. `C:\Users\kaleb\Documents\Water Pressing issues research\PROJECT_HANDOFF.md` — research background, literature findings, why this opportunity exists

The project has:
- 57 USGS sites across 11 US states (KS, IN, CA, CO, OR, VA, MD, MT, OH, ID, KY)
- 16,760 paired samples (continuous sensor reading matched to lab grab sample)
- Continuous sensors: turbidity (FNU), conductance, dissolved oxygen, pH, temperature, discharge
- Discrete lab data: SSC (suspended sediment concentration) — more parameters available but not yet pulled
- CatBoost gradient boosting with leave-one-site-out cross-validation
- Physics-guided approach planned but not yet implemented
- Currently SSC-only; multi-parameter is the goal

---

## Phase 1: Independent Domain Reviews

Each expert reads the context, then answers their assigned questions. Research using web search and OpenAlex is encouraged — cite real papers and equations, don't make them up.

### Dr. Elena Vasquez (Hydrogeochemist)

**Primary questions:**
1. Which water quality parameters should be in the "full suite" for a multi-target model? Consider: regulatory importance, data availability at USGS sites, chemical interconnectedness (predicting them jointly adds value), and feasibility of cross-site generalization. For each parameter you recommend, explain WHY it belongs and what controls it.

2. Which inter-parameter relationships are well-established enough to encode as physics constraints? For each, provide: the equation or relationship, the citation, the conditions under which it holds, and the conditions under which it breaks. Be explicit about what's thermodynamic (always true) vs. empirical (true within a calibration range) vs. kinetic (site-dependent).

3. Are there parameters that seem important but should NOT be included because the chemistry is too complex or site-specific to generalize across diverse watersheds?

4. What species-level distinctions matter? (e.g., dissolved vs. particulate phosphorus, nitrate vs. total nitrogen, SSC vs. TSS)

### Dr. Kai Nakamura (Physics-Guided ML)

**Primary questions:**
1. Given the constraints identified by Vasquez, what is the best architecture for encoding them? For each type of constraint, recommend: soft penalty in loss function, hard architectural constraint (e.g., non-negative output layer), or differentiable physics module. Explain tradeoffs.

2. For the multi-target prediction problem (predicting SSC, TDS, nitrate, phosphorus, DO simultaneously): shared backbone with multiple heads, prediction chain (SSC feeds into TP model), or independent models with physics coupling? What does the literature say about which works best for correlated environmental targets?

3. How should constraint strength be set? Fixed penalty weight, learnable weight, or curriculum (start unconstrained, gradually increase constraint strength)?

4. What's the minimum viable physics-guided architecture that improves on pure CatBoost for this problem? We're a solo developer — what's the simplest thing that works?

### Maria Torres (Regulatory Practitioner)

**Primary questions:**
1. Which water quality parameters drive the most regulatory decisions (303(d) listings, TMDL allocations, permit limits) in the United States? Rank them by regulatory importance.

2. For each parameter, what precision does a screening-level tool need vs. a compliance-level tool? Express as: acceptable percent error, required detection limit, or comparison to existing methods.

3. What output format do state agencies and watershed councils actually need? Daily loads? Instantaneous concentrations? Exceedance probabilities? Seasonal averages?

4. What would make a state agency hydrologist actually USE this tool vs. dismiss it? What are the trust barriers?

### Dr. Ananya Krishnamurthy (Environmental Statistician)

**Primary questions:**
1. How should non-detects be handled in a multi-target ML model? DL/2 substitution (current approach), Kaplan-Meier, maximum likelihood estimation, or something else? Does the answer change for training data vs. evaluation?

2. For multi-target prediction validation: what metrics should we report beyond per-parameter R²? Joint prediction accuracy? Correlation structure preservation? How do we evaluate whether the model is learning real inter-parameter relationships or just predicting each independently?

3. How do we properly quantify prediction uncertainty in a cross-site transfer setting? The model has never seen the test site. Bootstrap prediction intervals? Conformal prediction? Quantile regression (current approach)?

4. USGS grab samples are NOT random samples — they're biased toward accessible conditions, dry weather, weekdays. Storm samples are overrepresented at some sites and absent at others. How should we account for this sampling bias in training and evaluation?

---

## Phase 2: Cross-Cutting Synthesis (after Phase 1)

After independent reviews, we synthesize and identify:
- Where experts agree (high confidence decisions)
- Where experts disagree (needs discussion)
- Dependencies between decisions (e.g., parameter selection affects architecture)

Then run targeted follow-up questions on the conflicts.

---

## Deliverables

Each expert saves their findings to:
`C:\Users\kaleb\Documents\murkml\reviews\{name}_physics_panel_20260316.md`

The synthesis will be written to:
`C:\Users\kaleb\Documents\murkml\reviews\physics_panel_synthesis_20260316.md`
