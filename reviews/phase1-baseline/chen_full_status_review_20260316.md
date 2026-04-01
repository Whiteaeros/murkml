# Chen — Full Project Status Assessment & Strategic Review

**Date:** 2026-03-16
**Reviewer:** Dr. Sarah Chen, ML Engineering
**Scope:** Complete project health assessment — code, data, results, trajectory, publishability

---

## 0. Where This Project Actually Stands

I am going to be direct: this project is in better shape than most solo-developer academic ML projects I have reviewed, and it is in worse shape than you probably think. Both statements are true simultaneously. Let me explain.

**What is genuinely strong:**
- The data pipeline is production-quality code. Timezone handling, per-record DL/2 with guards, generalized discrete loader, 3-tier ablation — this is not prototype code, this is library code. Two rounds of 4-expert review plus a 6-expert physics panel is more scrutiny than most published tools receive.
- 57 USGS sites across 11 states with real temporal alignment is a meaningful cross-site dataset. Nobody else has built this for open-source release.
- SSC R2 = 0.80 in LOGO CV with 57 sites is a publishable result right now.
- The review/fix/verify cycle you have been running is rigorous. Every finding has been tracked, implemented, and independently verified.

**What needs honest assessment:**
- You have publishable results for 1.5 out of 4 parameters. SSC is done. TP is promising but unvalidated. Nitrate and OrthoP are negative results.
- The CatBoost model code (`baseline.py`) is functional but bare — no early stopping, no hyperparameter configuration, no sample weighting, no monotone constraints. It trains 4 models per LOGO fold (1 point estimate + 3 quantile models), which means ~228 model fits for 57 sites. That works but it is the naive implementation.
- You have zero notebooks showing end-to-end results. The `01_data_exploration.py` in notebooks/ is a script, not a reproducible demo. For publication and JOSS, you need at minimum one notebook that goes from data loading to a results figure.
- The `paper/` directory is empty.
- Prediction intervals are raw quantile regression (uncalibrated). The physics panel confirmed this undercoverage is real (~60-70% actual for nominal 80% intervals).

**Net assessment: You have a solid foundation and one strong result. The question is what to do with the next 8 weeks before graduation.**

---

## 1. Publishability Assessment

### What you need for a submittable paper

| Component | Status | Work remaining |
|---|---|---|
| Novel cross-site dataset | Done | Zenodo deposit (1 day) |
| SSC results (positive) | Done | Back-transform to natural units, report KGE (2 hrs) |
| TP results (positive, conditional) | 80% | Validation tests from my Phase 3 review (3 hrs) |
| Nitrate/OrthoP results (negative) | Done as-is | Frame as physics-limited boundary characterization |
| Ablation study (Tiers A/B/C) | Done | Already in results table |
| SHAP analysis | Not started | 1 day per parameter |
| Calibrated prediction intervals | Not started | CQR via MAPIE, 2-3 days |
| Reproducible results notebook | Not started | 1-2 days |
| Paper draft | Not started | 2-3 weeks |

**Verdict: You are 4-5 weeks from a submittable manuscript, assuming you do not add scope.**

### Target venues (in order of fit)

1. **Environmental Modelling & Software** — best fit for a cross-site ML surrogate tool. Impact factor ~5.0. Accepts software+results papers. Review time 3-6 months.
2. **Water Resources Research** — higher prestige, but reviewers will want more hydrology depth. The negative-result characterization of dissolved parameters would strengthen the submission here.
3. **JOSS (Journal of Open Source Software)** — for the software artifact itself. Requires 6+ months of development history (you have this), a substantial README, and a passing test suite. This can be submitted in parallel with the research paper.

### The honest publishability bar

Your SSC result (0.80 LOGO, 57 sites) already clears the bar. The existing literature on cross-site turbidity-SSC surrogates uses 5-15 sites and reports R2 = 0.6-0.7 (Rasmussen et al. 2009, Uhrich & Bragg 2003). You have 4x the sites and better performance. The TP result, if validated, is a second contribution that most papers in this space do not have.

What would make the paper stronger but is NOT required for publication:
- Calibrated prediction intervals (CQR)
- SHAP feature importance plots
- Flow-stratified metrics
- Comparison against published cross-site models

What IS required:
- Results in natural units (not just log-space R2)
- Per-site R2 distribution (box plot or similar)
- Clear description of the negative nitrate/OrthoP results and why they fail
- Reproducibility: either a notebook or a CLI command that regenerates the results table

---

## 2. What the Results Mean for Project Scope

### The physics ceiling is real

| Parameter | Per-site OLS R2 | Cross-site R2 | Gap | Interpretation |
|---|---|---|---|---|
| SSC | 0.81 | 0.80 | 0.01 | Cross-site nearly matches site-specific. Signal is in turbidity-SSC covariance, which transfers. |
| TP | 0.60 | 0.62 | -0.02 | Cross-site may exceed site-specific. Multi-feature captures both particulate and dissolved P. |
| Nitrate | 0.04 | -0.72 | 0.76 | No site-level signal to transfer. Dissolved, biologically controlled. |
| OrthoP | 0.06 | -0.55 | 0.61 | Same as nitrate. Dissolved, controlled by redox/biology/point sources. |

The pattern is unambiguous: **particle-associated parameters (SSC, TP) are learnable cross-site; dissolved parameters (nitrate, OrthoP) are not.** This is a physics result, not a modeling failure. The turbidity sensor measures light scattering by particles. If the analyte is a particle or bound to particles, turbidity has signal. If the analyte is dissolved, turbidity is noise.

This means the product scope needs revision. The PRODUCT_VISION.md describes predicting "a full suite of water quality parameters." The honest version is: **murkml can predict particle-associated water quality parameters cross-site. Dissolved parameters require site-specific calibration data or a fundamentally different approach (e.g., SC-based models for TDS, which is why the SC-TDS linear validation is still worth doing).**

### Recommended scope for v0.1

**Include:**
- SSC (primary, validated)
- TP (secondary, pending validation)
- TDS via SC-linear (tertiary, near-trivial to add, demonstrates pipeline generality)

**Report as negative results:**
- Nitrate (characterized, physics-limited)
- OrthoP (characterized, physics-limited)

**Defer:**
- Two-stage nitrate model (interesting research, not v0.1 material)
- Dissolved oxygen (needs different approach — physics-first, not surrogate)
- Prediction chains (SSC->TP ablation is worth 1 day but is an incremental improvement, not a priority)

---

## 3. Are the Remaining Planned Steps the Right Priorities?

Let me evaluate each planned step against the publication timeline.

### Prediction chain ablation (SSC -> TP)
**Priority: LOW for publication, MEDIUM for the product story.**

The physics panel confirmed that particulate P tracks SSC, so feeding SSC predictions into the TP model is mechanistically motivated. But the TP model already achieves R2 = 0.62 without the chain. The chain might add 0.02-0.03 R2. That is a nice result for a supplementary table but it does not change the paper's conclusions.

**Do this only if:** the TP validation confirms the result AND you have time after writing the paper. Budget: 1 day.

### Physics constraints Tier 1 (monotone constraints, output clipping, DO sat feature)
**Priority: MEDIUM, but mostly already done or not applicable.**

- Monotone constraints in CatBoost: trivial to add (one parameter). But which constraints? The physics panel said NOT to enforce turbidity-SSC monotonicity globally (grain size varies). So what monotone constraints are left? `discharge -> SSC` (positive) is plausible but not universal (dilution at extreme flows). `temperature -> DO_saturation` (negative) is well-established but you are not predicting DO in v0.1. **For SSC and TP, there are no safe global monotone constraints to enforce.** Skip this.
- Output clipping (non-negative): already enforced by log-transform + expm1 back-transform. Anything in log-space back-transforms to non-negative. This is done.
- DO saturation feature: already implemented in `features.py` as `DO_sat_departure`. The simplified formula (14.6 - 0.4*T) is a reasonable approximation. Upgrading to Benson & Krause 1984 would be more accurate but the improvement is marginal for a feature that CatBoost uses as a split predictor, not a physical equation. **Skip the upgrade for v0.1.**

**Net: Tier 1 physics constraints are either already done or not applicable to the v0.1 parameter set. Move on.**

### TDS SC-linear validation
**Priority: MEDIUM-HIGH.**

This is the lowest-effort way to add a third parameter to the paper. SC->TDS is near-linear (R2 > 0.95 per-site). The cross-site question is: does the proportionality constant k vary enough across geologies to prevent cross-site prediction? If you can show cross-site SC->TDS works even with variable k, that is a third positive result. If it does not work cross-site (because k varies too much), that is another characterized negative result that informs the product scope.

**Budget: 1 day.** You already have the TDS data loaded for 16 sites. Run a simple LOGO OLS: TDS = k * SC. Report per-site k values and cross-site R2. This does not require CatBoost — a linear model suffices and is more interpretable.

### CQR for calibrated prediction intervals (MAPIE)
**Priority: HIGH for publication quality, but can be post-submission.**

Raw quantile regression intervals undercover by ~20 percentage points (the physics panel and Krishnamurthy both flagged this). CQR via MAPIE is a near-drop-in upgrade. However, prediction intervals are not the core claim of the paper. The core claim is "cross-site surrogates work for particle-associated parameters." Calibrated intervals make the paper better but are not required for submission.

**My recommendation:** implement CQR after the first draft is written but before submission. If you are running out of time, submit without it and add it during revision (reviewers will likely ask for it, which gives you a natural revision task). Budget: 2-3 days.

### Flow-weighted sampling for storm bias correction
**Priority: LOW for publication.**

Krishnamurthy flagged this correctly — grab samples oversample baseflow and undersample storms at most sites. Inverse-probability weighting by flow quantile is the right fix. But implementing it correctly requires computing the flow distribution at each site, determining sampling weights, and verifying that weighted metrics differ meaningfully from unweighted. This is a multi-day effort that adds a paragraph to the methods section.

**Skip for v0.1.** Report both unweighted metrics (current) and flow-stratified metrics (high-flow vs. low-flow R2) as a diagnostic. This addresses the concern without requiring weighted training.

### Hyperparameter search
**Priority: LOW.**

Your current CatBoost config (1000 iterations, lr=0.1, depth=6) is reasonable. Hyperparameter tuning on 57-site LOGO CV is expensive (57 folds x N configurations) and rarely changes R2 by more than 0.02 for CatBoost on tabular data. A 3x3 grid (depth=[4,6,8], lr=[0.05,0.1,0.15]) is sufficient if you want to show robustness. A full Optuna sweep is overkill.

**One thing that IS worth adding:** early stopping. Your current code trains for exactly 1000 iterations regardless of convergence. Add `eval_set=(X_val, y_val)` with a small holdout from the training fold (10% random split), `early_stopping_rounds=50`. This prevents overfitting on small training folds and speeds up training. Budget: 30 minutes.

### SHAP analysis per parameter
**Priority: HIGH for publication.**

Reviewers will ask "what is the model using?" SHAP beeswarm plots for SSC and TP answer this definitively. For SSC, you expect turbidity to dominate (confirming the physics). For TP, the interesting question is whether conductance and discharge features contribute alongside turbidity — this would validate the multi-sensor advantage.

**Budget: 1 day.** SHAP on CatBoost is fast. One beeswarm per parameter + one dependence plot for the most important feature.

---

## 4. What You Should Actually Do Next (Prioritized)

Here is my recommended sequence for the next 5 weeks, targeting a submittable paper by late April 2026.

### Week 1: Validate and finalize results

1. **TP validation** (the four tests from my Phase 3 review Section 1). This is the single most important task. If TP holds up, your paper has two positive results and a stronger story. If it does not, you have one positive result and you adjust the framing. (3 hours)

2. **SSC natural-unit metrics.** Back-transform predictions with Duan's smearing, compute KGE and RMSE in mg/L. Report per-site R2 distribution as a box plot. (2 hours)

3. **Add early stopping to CatBoost.** Trivial code change, prevents overfitting on small folds. Re-run all tiers for all parameters. If results change by more than 0.02, investigate. (2 hours + compute time)

4. **SC-TDS linear validation.** 16 sites, simple LOGO OLS. Report k values by site and cross-site R2. (4 hours)

### Week 2: Analysis and figures

5. **SHAP analysis for SSC and TP.** Beeswarm plots, top-feature dependence plots. (1 day)

6. **Results notebook.** One Jupyter notebook that loads data, trains LOGO CV, produces the main results table and figures. This serves as both a reproducibility artifact and the JOSS demo. (1-2 days)

7. **Flow-stratified metrics.** Split test predictions into high-flow (>Q75) and low-flow (<Q25). Report R2 by flow condition. Do not implement weighted training. (3 hours)

### Weeks 3-4: Paper draft

8. **Write the paper.** The structure writes itself:
   - Introduction: site-specific surrogates are the norm; cross-site generalization is the gap
   - Data: 57 USGS sites, sensor+discrete pairing, GAGES-II catchment attributes
   - Methods: CatBoost LOGO CV, 3-tier ablation, log-transform + Duan's smearing
   - Results: SSC (strong positive), TP (positive, exceeds per-site OLS), nitrate/OrthoP (negative, physics-limited), TDS (linear validation)
   - Discussion: particle-associated vs. dissolved boundary, implications for monitoring network design
   - The negative results ARE the discussion section. Frame them as characterizing the learnability boundary.

### Week 5: Polish and submit

9. **CQR prediction intervals** if time permits. Otherwise, flag as future work.
10. **Zenodo dataset deposit.** Upload assembled dataset with DOI.
11. **Package polish.** Ensure `pip install murkml[all]` works. Write one CLI command that reproduces the results table.
12. **Submit to Environmental Modelling & Software.**

---

## 5. The Single Most Important Thing

**Validate the TP result.**

Everything else I have written above is conditional on whether TP holds up under the paired-site comparison I specified in my Phase 3 review. Here is why this one task matters more than anything else:

- If TP is real: your paper has SSC + TP as dual positive results, the cross-site-beats-per-site claim for TP is your headline finding, and the negative nitrate/OrthoP results complete the story by characterizing the physics boundary. This is a solid contribution to any of the three target venues.

- If TP is a site-pool artifact: your paper has SSC only as a positive result. Still publishable, but the framing shifts from "cross-site surrogates for multiple parameters" to "cross-site SSC surrogates with characterization of extension limits." Less exciting but honest.

Either way, you need to know. And it takes 3 hours.

---

## 6. What NOT to Do

I want to be explicit about scope traps, because solo developers near graduation are most at risk of expansion paralysis.

**Do not:**
- Attempt the two-stage nitrate model before the paper is drafted. It is interesting research but it is not v0.1.
- Build a neural network / LSTM. The physics panel and I both agree: CatBoost on tabular data with <20K samples is the right tool. LSTM is a second paper, if ever.
- Implement custom loss functions for physics constraints. Tier 1 constraints are either already done (log-transform, DO feature) or not applicable (no safe monotone constraints for SSC/TP).
- Build MkDocs documentation. README + one demo notebook is sufficient for v0.1 and JOSS.
- Optimize the prediction chain (SSC->TP) before validating standalone TP. If standalone TP is already good, the chain is incremental.
- Tune hyperparameters beyond a 3x3 grid. The marginal R2 gain does not justify the compute or the complexity in the methods section.
- Add dissolved oxygen to v0.1. DO prediction requires a physics-first approach (Benson & Krause saturation model with ML residual correction), which is a different architecture than what you have.

---

## 7. Code Quality Notes

A few specific observations from reading the source.

**`baseline.py` (lines 156-178):** The CatBoost training loop fits 4 separate models per fold (point + 3 quantile). This is correct but slow. When you implement CQR, you replace the 3 quantile models with conformal calibration on top of the point model, reducing to 1 model per fold. This is a 4x speedup that comes free with the CQR upgrade.

**`align.py` (lines 73-129):** The alignment loop iterates over discrete samples with a Python for-loop, computing time differences against the full continuous array each iteration. For 57 sites with thousands of continuous records, this is O(n*m) per site. It works but it is slow. A `merge_asof` approach would be O(n log m) and is a one-line pandas operation. Not blocking, but worth fixing when you have a spare hour.

**`features.py` (line 179):** The DO saturation formula `14.6 - 0.4 * T` is a rough linearization. The actual Benson & Krause equation is a 6th-order polynomial in 1/T. For a CatBoost feature, the linear approximation is fine — the model will learn the residual nonlinearity from the data. But document the approximation in a comment so a reviewer does not flag it as an error.

**`features.py` (line 98):** The hydrograph feature loop uses `iterrows()`, which is the slowest way to iterate a DataFrame. For 57 sites with many samples each, this adds meaningful wall-clock time. Vectorize with `np.searchsorted` for the nearest-neighbor lookup. Low priority but noticeable when running full LOGO CV.

**Test coverage:** 61 tests across 3 files is decent for an alpha package. The tests cover QC, alignment, and pipeline integration. I did not see tests for the `attributes.py` tier-building logic or the feature engineering functions. Add at least smoke tests for `prune_gagesii`, `build_feature_tiers`, and `engineer_features` before JOSS submission.

---

## 8. Summary

| Question | Answer |
|---|---|
| Where does this stand relative to publishability? | 4-5 weeks from submission. SSC is publishable now. TP needs validation. Negative results are ready to report. |
| What do the nitrate/OrthoP failures mean? | The physics ceiling for dissolved parameters. Not a modeling failure. Report as a contribution. |
| Are the planned next steps right? | Mostly no. Prediction chain, physics Tier 1, and flow weighting are all lower priority than TP validation, SHAP, and writing the paper. |
| Single most important thing? | Validate the TP result with the 4 tests I specified. 3 hours. Do it first. |

**Bottom line:** You have built something real. The data pipeline is solid, the review process has been thorough, and the SSC result is strong. The danger now is scope creep — adding features, parameters, and model variants instead of writing the paper. Every day you spend on the two-stage nitrate model or CQR or LSTM is a day you are not writing. The paper is the deliverable. Ship it.

---

*Review by Dr. Sarah Chen, ML Engineering*
*Reviewing: Full murkml project status — code, data, results, trajectory*
