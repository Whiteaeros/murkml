# Strategic Review: Phase Plan (0-6) Post-Audit

**Reviewer:** Ravi Patel — Critical Reviewer
**Date:** 2026-03-16
**Scope:** Phase progression, decision gates, Phases 3-6 adjustments, path to publication

---

## 1. Is the Phase Progression Still Right?

Mostly, but the proportions are wrong. The plan allocates 16 weeks before packaging (Phases 1-4) and treats publication as a Phase 6 afterthought starting at "Month 5-8." For a solo undergrad graduating mid-2026, that is backwards.

The correct ordering is: **fix bugs, get honest numbers, write the paper, then decide if expansion is worth it.** The current plan has you expanding to conductance/TDS and nutrients (Phase 3) and building an LSTM (Phase 4) before you have published anything. That is how projects die on a hard drive.

Revised progression:
- Phase 0: Done.
- Phase 1: Done (data pipeline exists, 57 sites collected).
- **Audit remediation (Rounds 1A, 1B, 2):** This is your real Phase 2 now. The fix plan is well-ordered. Execute it.
- **Phase 2.5 (Analysis Pause):** Keep this. It is the most important week in the plan. The publishability check at Week 8 should be treated as a hard gate, not a soft suggestion.
- **Phase 5 (Package) and Phase 6 (Publish):** Pull these forward. They should follow directly after Round 2 honest numbers, before any Phase 3 or Phase 4 work.
- **Phase 3 and Phase 4:** Demote to post-publication stretch goals.

## 2. Are the Decision Gates Still Valid?

The gates at Weeks 1 and 4 are passed. The remaining gates need revision:

**Week 7 gate ("CatBoost beats global OLS"):** Still valid but reframe it. If CatBoost does not beat global OLS after the audit fixes, the problem is likely feature engineering or data quality, not the model. The audit fixes (especially Fix 3+5 hydrograph/antecedent features and Fix 14 catchment attributes) are the interventions most likely to create separation from OLS. If they do not, that is a finding worth publishing, not a failure.

**Week 7 gate ("lagged features help CatBoost -> LSTM justified"):** Still valid. I would strengthen it: unless lagged features improve median R-squared by at least 0.03, skip Phase 4 entirely. Do not chase LSTM for a marginal gain you cannot staff or maintain.

**Week 8 gate ("publishable?"):** This should not be a question. After audit remediation, 57 sites with honest CatBoost LOGO numbers, SHAP analysis, fair baseline comparison, storm-event metrics, and the compiled dataset, you have a publishable result regardless of the R-squared number. An honest R-squared of 0.55 with proper evaluation at 57 cross-site locations is more publishable than an inflated 0.67.

**Add a new gate:** After Round 1A data pipeline fixes, before Round 1B model fixes: verify you still have enough data. The plan estimates 20-40% sample loss from the timezone fix. If you drop below 8,000 samples or below 40 sites with 30+ pairs, reassess site selection before proceeding.

## 3. What Should Change About Phases 3-6

**Phase 3 (Expand Parameters):** Defer entirely until after the first paper is submitted. Conductance-to-TDS is a trivial extension that proves the pipeline generalizes -- it can be a second paper or a revision response. Nutrients are a substantially harder problem (non-detects, seasonal cycling, multiple predictors) and should not be attempted until the turbidity-SSC pipeline is published and stable.

**Phase 4 (LSTM):** This is the highest-risk, lowest-marginal-value phase. A solo developer maintaining a CatBoost pipeline and an LSTM pipeline is a maintenance burden that does not scale. If the lagged-feature gate says no, cut it cleanly. If the gate says yes, consider it a second paper, not a v0.1.0 feature.

**Phase 5 (Package):** Pull forward. The v0.1.0 scope is already correctly scoped (turbidity-SSC, CatBoost, SHAP, data pipeline). Ship this immediately after Round 2 honest numbers. Do not wait for Phase 3 or 4.

**Phase 6 (Publication):** Pull forward and reorder the publication sequence:

1. **Dataset paper first.** 57 sites, 11 states, 17K paired sensor-lab samples with proper QC, compiled into a standardized format. Submit to Earth System Science Data or Scientific Data. This is the most defensible contribution and does not depend on model performance. Write this during audit remediation.
2. **JOSS software paper second.** Requires 6-month dev history (earliest Sept 2026 per the plan). The audit fixes add to the dev history. Target October 2026 submission.
3. **Methods paper third.** Cross-site CatBoost results, SHAP analysis, comparison to USGS per-site OLS. Environmental Modelling & Software or Water Resources Research.

The novelty framing correction from the audit (Fix 29) is critical here. Do not claim "first cross-site WQ prediction." Claim "first open-source, reproducible toolkit for cross-site WQ surrogate modeling with a compiled benchmark dataset." The dataset is the novel artifact. The toolkit is the practical contribution. The model results are supporting evidence.

## 4. Faster Path to a Publishable, Credible Result

The fastest path is:

1. Execute Rounds 1A and 1B from the fix plan (data fixes, then model fixes). These are well-specified and mostly mechanical.
2. Execute Round 2 (catchment attributes, fair baselines, storm metrics, confidence intervals).
3. Write the dataset paper in parallel with Round 2. The dataset description does not depend on model results.
4. After Round 2, write up the model results. You now have two manuscripts.
5. Ship v0.1.0 to PyPI.
6. Submit dataset paper. Submit JOSS when the 6-month clock allows.

Do not touch Phase 3, Phase 4, or any feature expansion until both papers are submitted.

## 5. What I Would Cut Entirely

- **Phase 4 (LSTM/sequence models):** Cut unless the lagged-feature gate is unambiguous. A CatBoost model that works is better than an LSTM that is half-built when you graduate. The self-supervised pretraining idea is interesting but is a PhD-level effort, not a graduating-undergrad effort.
- **Fix 16 wildfire disturbance (MTBS integration):** Already deferred in the plan. Keep it deferred. A `fire_prone` boolean and a limitation paragraph in the paper is sufficient.
- **Fix 22 DO saturation formula:** CatBoost compensates. Not worth the time.
- **Fix 12 secondary sensor time coordination:** Patel (me) already deprioritized this. Slow-changing sensors (conductance, temp, pH) do not shift meaningfully over 30 minutes. The improvement is real but marginal.
- **RegressorChain for nutrients (Phase 3):** Interesting idea, wrong project stage.
- **SaaS/web UI from the revenue path:** Not before you have users of the Python package. Build demand before building infrastructure.
- **Hyperparameter search (Round 2, item 19):** A coarse grid of 27 combinations across 57 LOGO folds is computationally expensive for likely marginal gain. CatBoost defaults are reasonable. If you must, do depth and learning rate only (6 combinations), skip l2_leaf_reg.

---

## Summary

The plan is sound in structure but over-scoped for a solo undergrad on a graduation deadline. The single highest-leverage change is pulling Phase 5 (package) and Phase 6 (publish) forward to immediately follow audit remediation, and pushing Phase 3 (parameters) and Phase 4 (LSTM) to post-publication. The dataset is your most defensible contribution. Ship it first.

-- Ravi Patel
