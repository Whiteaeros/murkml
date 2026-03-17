# Chen — Strategic Review of Phase Plan (Post-Audit)

**Date:** 2026-03-16

---

## 1. Is the Phase Progression Still Right?

Mostly yes, with one important reordering. The sequence Baselines (Phase 2) → Expand Parameters (Phase 3) → LSTM (Phase 4) → Package (Phase 5) → Publish (Phase 6) is sound in principle, but after what the audit revealed, the priorities within that sequence need to shift.

**What the audit changes:** You have 17K samples across 57 sites, which is already past every Phase 1 decision gate. But the timezone bug means ~20-40% of those samples will be lost on reassembly, and the leakage issues mean your current R²=0.67 is probably 0.55-0.62 in reality. The good news: you already have enough data. The bad news: you have never seen honest numbers. Until Round 1A+1B of the fix plan completes and you get a clean baseline, everything downstream is speculative.

**My recommendation:** The phase plan is right, but Phase 3 (expand parameters) should be deferred until AFTER Phase 5 (package + release). The reason is simple: turbidity-to-SSC with 57 sites, honest metrics, SHAP, and prediction intervals is already a publishable, useful product. Adding conductance-to-TDS and multi-sensor-to-nitrate makes the paper stronger but delays the release by 2-3 months for marginal credibility gain. You are a solo developer graduating mid-2026. Ship the SSC model, publish the dataset, then expand parameters in v0.2.

**Revised order:** Fix Plan → Phase 2 (honest baselines) → Phase 2.5 (analysis) → Phase 5 (package v0.1) → Phase 6 (publish) → Phase 3 (expand) → Phase 4 (LSTM, if justified).

## 2. Are the Decision Gates Still Valid?

The Phase 1 gates (feasibility, data volume) are already passed. The remaining gates:

- **"CatBoost beats global OLS"** — still valid. If CatBoost with 30+ features cannot beat a single-variable log-log regression, either the features are garbage or the cross-site signal is too weak. But after fixing the timezone bug and adding real hydrograph/antecedent features (Fix 3+5), I expect CatBoost to beat OLS by a wider margin than before, not a narrower one. These are the features that encode actual hydrology.

- **"Lagged features help CatBoost → justifies LSTM"** — still valid, but I would strengthen it. The bar should not be "lagged features help at all" but "lagged features improve storm-period RMSE by >5%." The whole point of LSTM is temporal dynamics during events. If adding t-1hr and t-6hr turbidity to CatBoost does not meaningfully help storm predictions specifically, then LSTM is not worth the engineering cost for a solo developer.

- **"Publishable at Week 8"** — needs revision. You are past Week 8 in wall-clock time. The real gate now is: "After Round 1A+1B fixes, is cross-site CatBoost median R² > 0.55 in natural space with honest metrics?" If yes, you have a paper. If no, the dataset alone is still publishable (ESSD or Scientific Data), and the toolkit becomes a methods contribution rather than a performance one.

**Add one new gate:** After Round 1A reassembly, check sample count. If you lose >50% of samples from the timezone fix (not 20-40%), something is wrong with the fix itself, not the data. Do not proceed to model training on a dataset that dropped below 8K samples without investigating.

## 3. What Should Change About Phases 3-6

**Phase 3 (Expand Parameters):** Move to after Phase 5/6. When you do get to it, conductance-to-TDS is the right first expansion — it is near-linear and confirms the pipeline generalizes without adding methodological complexity. Skip nutrients for v0.1 entirely. Nitrate and phosphorus have non-detect rates of 10-30%, seasonal cycling, and point-source confounders that will consume months. Save them for a second paper.

**Phase 4 (LSTM):** I remain skeptical this is worth doing at all for a solo developer. The self-supervised pretraining approach is correct in theory (pretrain on millions of continuous timesteps, fine-tune on sparse grab samples), but the engineering burden is high: you need a proper dataloader for variable-length sequences across 57 sites, GPU training, hyperparameter tuning, and careful comparison. CatBoost with well-engineered temporal features (which you will have after Fix 3+5) often matches or beats LSTM on tabular data with <100K samples. My honest assessment: if the lagged-feature gate does not clear convincingly, kill Phase 4 and use that time to write the paper.

**Phase 5 (Package):** Accelerate. You already have the package structure, CI, and most of the code. After the fix plan completes and you have honest baselines, packaging is 1-2 weeks of polish, not 3. The main work items: (a) make sure `pip install murkml` actually works end-to-end with the fixed pipeline, (b) write one demo notebook with a real site, (c) upload the dataset to Zenodo with a DOI. Do not build MkDocs, do not write extensive API documentation. A working README with a quickstart is enough for v0.1.

**Phase 6 (Publish):** Reorder the publication sequence. The current plan says dataset paper first, then JOSS, then research paper. I would change this:

1. **Zenodo dataset deposit** (immediate, no peer review needed, gets a DOI, establishes priority)
2. **JOSS software paper** (requires 6 months of dev history — clock is already ticking, so submit as soon as eligible around Sept 2026)
3. **Research paper** (Environmental Modelling & Software or JAWRA — the cross-site results with SHAP and honest metrics)

Skip the standalone dataset paper unless the research paper gets rejected. A Zenodo DOI is citable and discoverable. A formal dataset paper in ESSD takes 4-6 months of review and adds little over Zenodo for your career timeline.

## 4. Fastest Path to a Publishable Result

Here is the critical path, stripped to essentials:

1. **Complete Round 1A** (data pipeline fixes: timezone, QC, alignment, features). This is the bottleneck. Budget 2 weeks.
2. **Complete Round 1B** (model fixes: early stopping, imputation, smearing, collinear features). Budget 1 week.
3. **Run honest baselines.** CatBoost LOGO, global OLS, per-site OLS. Compute all metrics including storm RMSE and load bias. Budget 3 days.
4. **SHAP analysis + results notebook.** One afternoon if the pipeline is clean.
5. **Add catchment attributes** (Fix 14 — drainage area, elevation, HUC2). This is low effort and likely bumps R² by 0.02-0.04. Budget 2 days.
6. **Write the paper.** You already have the framing from the handoff doc (Fix 29 gives you the novelty claim). Budget 2 weeks.
7. **Package and release v0.1.** Budget 1 week.

Total: ~6-7 weeks from today to a submitted paper and a released package. That puts you at early May 2026, well before graduation.

**What to cut to hit this timeline:** Skip Round 2 items 17-18 (confidence intervals, PICP) for the first submission — report them if a reviewer asks. Skip Round 3 entirely for v0.1. Skip Fix 12 (secondary sensor time coordination) — it is correct but the effect on model performance is negligible for slow-changing sensors like conductance and temperature. Skip Fix 22 (DO saturation formula) — CatBoost compensates. Do not tune hyperparameters beyond the coarse grid (3x3x3 = 27 runs, not a full Optuna sweep).

**The one thing that could derail this timeline:** If the timezone fix drops sample counts below 8K and you need to re-expand the site list or loosen alignment windows. Monitor this carefully during Round 1A.

---

**Bottom line:** The plan is good. The audit found real bugs that matter. Fix the data, get honest numbers, ship v0.1, write the paper. Do not expand scope until after you have published. You have enough data and enough sites right now — what you need is clean execution over the next 6 weeks.
