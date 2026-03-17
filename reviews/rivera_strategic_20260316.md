# Strategic Review: murkml Phase Plan
**Dr. Marcus Rivera — Hydrologist / Water Quality Scientist**
**Date:** 2026-03-16

---

## 1. Is the Phase Progression Right?

The overall arc — baselines, expand parameters, LSTM, package, publish — is sound in principle. But the audit changed things. The plan was written assuming a working data pipeline. You do not have one. Fixes 1, 3, 5, and 6 together mean you are essentially rebuilding the assembly layer. That is not a "fix round" — that is finishing Phase 1.

The phase progression should be:

1. **Finish the data pipeline** (what the audit fix plan calls Round 1A). This is Phase 1 completion, not a patch.
2. **Get honest baselines** (Round 1B + Round 2). This is Phase 2.
3. **Publish what you have.** This is where I diverge from the plan.
4. **Then** consider parameter expansion and LSTM.

The current plan has Phase 3 (expand to conductance, nitrate, phosphorus) at weeks 9-11 and Phase 4 (LSTM) at weeks 12-16. You are graduating mid-2026. That is roughly 3 months from now. You cannot afford to touch Phase 3 or 4 before you have a shipped v0.1.0 and a submitted paper. Period.

## 2. Are the Decision Gates Valid?

Mostly yes, with revisions:

- **Week 1 feasibility gate (60% match rate):** Still valid but needs re-evaluation post-timezone-fix. Chen estimated 20-40% sample loss. If you drop below 40% match rate, you have a problem. Set the revised gate at 45% post-fix.
- **Week 4 data gate (15 sites, 500 pairs, 4 ecoregions):** Still valid. You have 57 sites and 17K pairs. Even losing 30% you are well above threshold.
- **Week 7 value gate (CatBoost beats global OLS):** Still valid. The honest R-squared will drop. If CatBoost does not beat global OLS after the fixes, you need to ask hard questions about whether the feature engineering is adding anything or the data is too heterogeneous.
- **Week 7 temporal gate (lagged features help CatBoost):** Still valid as the LSTM go/no-go.
- **Week 8 publishability check:** This is the most important gate. I would move it UP. After Round 1B gives you honest numbers, stop and assess. If median LOGO R-squared is above 0.55 with proper features, you have a publishable result RIGHT NOW. The dataset alone is publishable.

**New gate I would add:** After the timezone fix and re-assembly, check whether the corrected temporal alignment actually changes which sites perform well vs. poorly. If the same sites fail before and after the fix, the timezone bug was corrupting individual predictions but not the overall model structure. If the ranking of sites changes substantially, your prior SHAP analysis is also invalid.

## 3. What Should Change About Phases 3-6?

**Phase 3 (Expand Parameters): Defer entirely.** Do not touch conductance-to-TDS or nutrient prediction before v0.1.0 ships and a paper is submitted. The plan says "only after Phase 2 results are solid" — good — but the temptation to keep improving before publishing is the single biggest risk to this project. Turbidity-to-SSC across 57 sites with proper features and honest evaluation is already a contribution. Conductance-to-TDS is trivially linear and adds nothing to the science. Nutrients require non-detect handling at scale (10-30% censored data) and multi-sensor feature engineering that will consume months.

**Phase 4 (LSTM): Probably skip.** Here is why. You have 17K paired samples across 57 sites. After the fixes, maybe 10-12K. That is roughly 200 samples per site on average, but the distribution is skewed — some sites have 500+, many have 30-50. LSTM self-supervised pretraining on the continuous record is clever and could work, but it is a research project in itself. CatBoost with proper hydrograph features (discharge slope, time since peak, antecedent conditions) will capture 80% of the temporal dynamics that LSTM would learn, without the complexity. The lagged-features test at the end of Phase 2 is the right gate. My prediction: lagged features will help modestly (0.01-0.03 R-squared improvement), not enough to justify LSTM development before graduation.

**Phase 5 (Package and Release): Move this up.** The moment you have honest baselines with the audit fixes applied, package and release v0.1.0. Do not wait for parameter expansion or LSTM. The plan already says this under v0.1.0 scope, but the phase numbering buries it at weeks 17-19. It should be weeks 10-12 at the latest.

**Phase 6 (Publication): Start the dataset paper NOW.** You have 57 sites, 17K samples (pre-fix), 11 states. The compiled, QC-filtered, temporally aligned cross-site turbidity-SSC dataset does not exist in the literature. Write the data descriptor (ESSD or Scientific Data format) in parallel with the bug fixes. The dataset paper and the JOSS software paper can be submitted within weeks of each other. The research paper (model results) comes third and can be submitted after graduation if needed.

## 4. Fastest Path to a Result USGS Hydrologists Would Respect

USGS hydrologists care about three things: (a) did you handle the data correctly, (b) do you evaluate on storm events, and (c) do your features make physical sense.

Here is the shortest credible path:

1. **Fix the data pipeline (Round 1A).** Timezone, alignment, QC, antecedent features. No shortcuts. If the data is wrong, nothing else matters. The USGS NRTWQ group will check your alignment methodology first.

2. **Get honest baselines with storm-stratified metrics (Round 1B + Round 2, compressed).** Report R-squared, RMSE, and KGE stratified by flow regime: baseflow (below Q25), moderate (Q25-Q75), elevated (Q75-Q90), storm (above Q90). Report sample counts per stratum. Report load bias. This is what USGS cares about — can your model estimate sediment loads during the events that move 90% of the material?

3. **Compare directly to published USGS site-specific regressions.** You already planned this. Make it the centerpiece. At the 10-15 sites where USGS has published turbidity-SSC regressions, show your cross-site model vs. their per-site OLS. You will lose at most sites — that is fine. The value is that your model produces a prediction at the other 42+ sites where no regression exists. Frame it that way.

4. **Show the SHAP makes physical sense.** Turbidity should dominate. Discharge slope and antecedent conditions should matter for storm events. If SHAP shows the model relying on artifacts (time-of-day, site index leaking through categorical encoding), fix it before publishing. USGS reviewers will look at this.

5. **Ship v0.1.0 and submit the dataset paper.** Everything else (LSTM, nutrients, web UI) is Phase 2 of your career, not Phase 2 of this project.

**Timeline estimate from today:**
- Weeks 1-3: Data pipeline fixes + re-assembly + tests
- Weeks 4-5: Model fixes + honest baselines + storm metrics
- Week 6: SHAP analysis, comparison to USGS regressions, ablation studies
- Weeks 7-8: Package v0.1.0, write dataset paper, draft JOSS paper
- Weeks 9-10: Submit dataset paper, submit JOSS, email USGS contacts

That gets you two submitted papers before graduation with a shipped open-source tool. That is the win condition.

---

**Bottom line:** The audit revealed that you are still in Phase 1, not Phase 2. Accept that. Fix the data, get honest numbers, publish immediately. The plan's later phases are fine as a roadmap for post-graduation work, but they should not delay shipping what you have. A correct, well-evaluated turbidity-to-SSC cross-site model with 57 sites and proper storm-event metrics would be the first of its kind as an open tool. That is enough.
