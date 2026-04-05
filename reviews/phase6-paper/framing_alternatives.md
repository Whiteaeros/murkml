# Framing Alternatives — Phase 2 Expert Team

**Date:** 2026-04-02

Three alternative framings for the WRR paper, with pros, cons, and team consensus.

---

## Framing A: "The Transferability Boundary" (RECOMMENDED)

**Title:** Geology Controls Cross-Site Transferability of Turbidity-Sediment Relationships: A Continental-Scale Machine Learning Assessment

**Central Hypothesis:** The primary barrier to cross-site turbidity-SSC prediction is between-site variation in the optical-to-gravimetric conversion, which is governed by watershed geology and particle size distribution. Given sufficient geologic context, a cross-site model can approach site-specific regression accuracy with minimal calibration.

**Narrative Arc:** Problem (turbidity is not SSC; the conversion depends on unmeasured particle properties) -> Instrument (CatBoost as a diagnostic tool) -> Finding 1 (geology controls: carbonate R2 = 0.81, volcanic R2 = 0.20) -> Finding 2 (3.2x between-vs-within CV quantifies the transferability boundary) -> Finding 3 (24% of sites fail, and we can explain where and why) -> Finding 4 (10 grab samples close most of the gap) -> Application (load estimation proof of concept at Brandywine).

**Pros:**
- Centers the physics, not the ML. WRR reviewers want process understanding.
- The 24% failure rate becomes a finding, not a limitation.
- Naturally organizes around disaggregated results (the scientific backbone).
- The model is the instrument, not the subject; deflects "just another ML paper" criticism.
- Aligns with Tanaka's recommendation and Osei's editorial assessment.
- Title signals a science paper, attracting sediment transport and water quality reviewers rather than pure ML reviewers.

**Cons:**
- Requires per-geology slope distributions (analysis gap #9) to fully deliver.
- The Brandywine load result is the strongest hook but becomes secondary under this framing.
- Less appealing to the ML-for-hydrology audience (Kratzert, Song, Zhi readers).

**Team consensus:** 5/6 recommend (Whitfield, Osei, Tanaka, Liu, Vasquez). Kowalski prefers Framing B for operational impact but agrees Framing A is better for WRR.

---

## Framing B: "The Screening-to-Monitoring Continuum"

**Title:** From Screening to Monitoring: A Cross-Site Machine Learning Framework for Turbidity-Based Sediment Estimation at 4,000 Underserved Sites

**Central Hypothesis:** A cross-site model using continuous turbidity plus watershed context provides operationally useful sediment estimates at monitoring sites that currently lack calibrated SSC regressions, with predictable performance that can be improved through targeted grab sampling.

**Narrative Arc:** Problem (4,000 turbidity sensors without SSC regressions) -> Solution (cross-site CatBoost) -> Tier 1: Screening (zero-shot MedSiteR2 = 0.40, useful for ranking and trend detection) -> Tier 2: Monitoring (N=10 MedSiteR2 = 0.49, useful for load estimation) -> Warning (temporal adaptation fails; target storms) -> Proof of concept (Brandywine load match) -> Deployment guidance (where to use, where not to use, how to calibrate).

**Pros:**
- Directly addresses the operational gap (4,000 underserved sites).
- The adaptation curve is the central result, which is the strongest practical contribution.
- The Brandywine load comparison anchors the monitoring-grade tier.
- Appeals to state agencies, USGS stakeholders, and the monitoring community.
- The deployment guidance becomes a natural conclusion, not an afterthought.

**Cons:**
- Reads as an "engineering" or "applications" paper rather than a "science" paper. WRR reviewers may downgrade for insufficient process understanding.
- The 24% failure rate is harder to frame positively (it is a deployment limitation, not a scientific finding).
- The geology story becomes supporting evidence rather than the central finding.
- Risk of "just another ML tool" criticism from academic reviewers.
- "Publication grade" tier is not supported by the data (N=30 gives R2 = 0.48, not 0.70+), creating a credibility gap.

**Team consensus:** Kowalski's preferred framing. Others acknowledge its strengths for a follow-up applications paper (JAWRA or HESS) but consider it suboptimal for WRR.

---

## Framing C: "The Turbidity Input Innovation"

**Title:** Continuous Turbidity Enables Continental-Scale Suspended Sediment Estimation: Matching the USGS Published Record Without Site-Specific Calibration

**Central Hypothesis:** Adding continuous turbidity as a primary input to a cross-site ML model closes the gap between discharge-only models (Song et al. 2024) and site-specific regressions, because turbidity directly encodes event-scale dynamics (hysteresis, sediment exhaustion) inaccessible to discharge.

**Narrative Arc:** Problem (existing cross-site models use discharge; turbidity is the obvious missing input) -> Innovation (first cross-site model using continuous turbidity) -> Result 1 (Spearman = 0.875 per-site vs Song et al. R2 = 0.55 with discharge) -> Result 2 (Brandywine load within 2.6% without calibration) -> Result 3 (storm events 1.4-3.5x better because turbidity captures hysteresis) -> Explanation (geology controls where turbidity is sufficient vs insufficient) -> Adaptation (10 samples closes the remaining gap).

**Pros:**
- The "turbidity as input" novelty is the most defensible claim of first-ness.
- The Brandywine result leads, which is the strongest hook for attention.
- The Song et al. comparison frames the contribution clearly.
- Simple, linear narrative.

**Cons:**
- The headline is the Brandywine 2.6%, which is fragile (one site, error cancellation, daily pbias +59%).
- Positions the paper as competing with Song et al. rather than complementing them. Song et al. reviewers might be hostile.
- Undersells the geology finding and the transferability characterization.
- The "first to use turbidity" claim is technically novel but intellectually modest; per-site turbidity-SSC regressions have been used for decades. The innovation is cross-site, not turbidity per se.
- Risk of being seen as incremental ("you added an obvious feature and it helped").

**Team consensus:** Tanaka and Whitfield oppose (undersells the science). Osei notes this framing maximizes citation potential but minimizes reviewer satisfaction. Not recommended for WRR; could work for Nature Water or Environmental Science & Technology.

---

## Recommendation

**Framing A ("The Transferability Boundary") is the strongest choice for WRR.** It centers the physics, makes the failure modes into findings, and positions the model as an instrument for scientific discovery rather than a tool. The geology-controls-transferability hypothesis is testable, falsifiable, and well-supported by the disaggregated results.

**Framing B is the natural choice for a second paper** (JAWRA or HESS), focused on deployment guidance and the adaptation framework.

**Framing C works as a shorter communication** (GRL or Nature Water) if the team wants a high-visibility, focused publication on the Brandywine result.

---

*Prepared 2026-04-02 by the Phase 2 Expert Team.*
