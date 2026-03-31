# NTU Integration Plan Review
**Reviewer:** Dr. Ananya Krishnamurthy
**Date:** 2026-03-30
**Document under review:** `ntu-integration-plan.md` (Phase 7)

---

## 1. Parallel FNU/NTU Column Approach: Statistical Soundness

The parallel-column design is the correct architecture for this problem. It is preferable to a categorical sensor-type flag for exactly the reasons stated in the plan: dual-sensor sites provide direct paired observations that let the model learn the FNU-NTU mapping conditioned on watershed covariates, without duplicating rows or introducing artificial group structure.

**CatBoost NaN handling specifics.** CatBoost routes missing values to a dedicated "missing" branch at each split node. The model learns whether NaN should go left or right independently for every split. This means:

- FNU-only rows (NTU=NaN): The model ignores NTU columns entirely for these rows. Equivalent to the current v9 behavior. No degradation expected.
- NTU-only rows (FNU=NaN): The model routes through NTU-learned branches. Good.
- Dual-sensor rows: The model can split on either or both. This is where the FNU-NTU calibration transfer is learned.

**The concern I would raise:** With 89 dual-sensor sites out of ~396+, the dual-sensor rows are a small fraction of the total training data. CatBoost will primarily learn FNU trees (because most rows have FNU populated), and the NTU branches will be learned from a much smaller pool. The effective sample size for NTU-specific splits is limited to the rows at those 89 sites where NTU is populated, plus whatever NTU-only sites are added in Phase 7B.

**Recommendation:** After Phase 7A, report the number of rows that actually have NTU populated (not just the 89 site count). If the NTU-populated row count is below ~500, the model may not have enough signal to learn reliable NTU branches, and Phase 7B becomes not optional but essential.

**Interaction features are a hidden landmine.** The current `features.py` computes `turb_Q_ratio`, `SC_turb_interaction`, `log_turbidity_instant`, `turb_saturated`, and `turb_below_detection` all from the column `turbidity_instant`. After the rename, these derived features must be computed from whichever turbidity source is available. This is not a simple rename -- it is a logic fork:

```
turb_Q_ratio = turbidity_instant_fnu / Q   (when FNU available)
             = turbidity_instant_ntu / Q   (when NTU available)
             = ???                          (when both available)
```

For dual-sensor rows where both are populated, you need a decision rule: use FNU? Use NTU? Average? The plan does not address this. My recommendation: for derived features, prefer FNU when available (maintains continuity with v9), fall back to NTU. Create a single "effective turbidity" column used only for derived feature computation, but do NOT include it as a direct model feature (that would leak the sensor-type distinction back into a single column and defeat the purpose of the parallel design).

---

## 2. Breaking Column Rename Risks

The rename `turbidity_instant` to `turbidity_instant_fnu` touches at minimum:

| Location | Impact |
|---|---|
| `assemble_dataset.py` line ~289 | Column creation during alignment |
| `assemble_dataset.py` line ~481 | Manual alignment fallback path |
| `features.py` `_MINIMAL_FEATURES` set | Feature whitelist |
| `features.py` `_build_monotone_constraints()` | Monotone feature set |
| `features.py` `add_cross_sensor_features()` | `turb_Q_ratio`, `SC_turb_interaction` |
| `features.py` `engineer_features()` | `log_turbidity_instant`, `turb_saturated`, `turb_below_detection` |
| `data/optimized_drop_list.txt` | Contains `log_turbidity_instant`, `turb_saturated`, `turbidity_mean_1hr`, `turbidity_min_1hr`, `turbidity_range_1hr`, `turbidity_slope_1hr` |
| `train_tiered.py` | Monotone constraint builder |
| `evaluate_model.py` | Holdout data loading |
| `validate_external.py` line ~135 | Maps external turb to `turbidity_instant` |
| `phase4_diagnostics.py` | Turbidity references |
| `phase5_ablation.py` | Feature references |
| All experiment scripts (a, b, d, e, d_redo) | Hardcoded feature names |
| `notebooks/01_data_exploration.py` | EDA references |
| Saved model `meta.json` | Feature name lists |
| Any cached/serialized datasets | Column names baked in |

**Risk assessment:** This is a high-risk refactor. A single missed reference will cause a silent failure where a NaN column is used instead of the real data (exactly the prune_gagesii failure mode documented in CLAUDE.md). The model would train on all-NaN turbidity for affected rows and produce garbage without any error.

**Mitigation (required):**
1. Do the rename as a standalone commit with zero functional changes. Run the full test suite and a v9-reproduction check (train, get identical metrics) before proceeding with any NTU work.
2. Add a validation gate in the training script: assert that the fraction of NaN in `turbidity_instant_fnu` matches expectations (should be ~0% for current FNU-only dataset, rising to a known fraction after NTU-only rows are added).
3. Grep the entire codebase for the old name. Every hit must be resolved. The plan lists 7 files; I count at least 14 that need changes.

---

## 3. Validation Strategy Assessment

The proposed validation is necessary but not sufficient.

**What is adequate:**
- GKF5 regression check against v9 baseline (noise floor threshold of +/-0.013)
- External NTU zero-shot bias reduction
- Physics validation (first flush, extremes, hysteresis)
- 5-seed stability

**What is missing:**

**(a) Per-sensor-type performance breakdown.** After NTU integration, report all metrics separately for: (i) FNU-only validation sites, (ii) NTU-only validation sites, (iii) dual-sensor sites split by which sensor was populated. A global metric can hide sensor-type-specific degradation.

**(b) Conditional calibration check.** The whole point is that the model learns FNU-NTU conversion conditioned on geology/watershed. Verify this by examining residuals at dual-sensor sites: do the FNU-prediction residuals and NTU-prediction residuals have different distributions? If they do, the model learned the sensor difference. If they look the same, the model may be ignoring the NTU columns.

**(c) Feature importance shift analysis.** Compare SHAP or feature importance between v9 and the NTU-integrated model. If the NTU columns have near-zero importance, the model is not actually using them, and the integration is cosmetic. If FNU column importance drops significantly, something has gone wrong with the data plumbing.

**(d) NTU-only row ablation.** After Phase 7A, train two models: one with the NTU-only rows included, one without. Compare on the NTU validation set. This isolates the contribution of the NTU-only rows from the contribution of the parallel column architecture.

**(e) Saved model reproducibility.** After the rename, load the v9 saved model and confirm it cannot make predictions (because it expects `turbidity_instant`, which no longer exists). This is not a test of the new model -- it is a test that old models are clearly incompatible, preventing accidental use of mismatched model/data versions.

---

## 4. NTU Vault Sizing and Stratification

The plan says "~20 sites" without justification. Here is how to size it properly.

**Power analysis framing.** The vault's purpose is a one-shot generalization test. You want to detect whether the NTU zero-shot bias has dropped from +66% to some acceptable level (say, less than +15%) with reasonable statistical power.

With the external NTU validation showing +66% bias across 260 sites and 11K samples, the effect size is large. For detecting a drop from +66% to +15% at alpha=0.05, power=0.80, the per-site sample count matters more than the site count for the bias estimate, but for the R-squared estimate you need site-level replication.

**Practical recommendation:** 20 sites is a reasonable floor IF each site has at least 15-20 SSC samples with paired NTU. If some NTU-only sites have only 3-5 samples, 20 sites may not give you a stable R-squared estimate. Count the total sample count across vault candidates, not just the site count.

**Stratification criteria (in priority order):**
1. **HUC2 region** -- geographic diversity is paramount. The 89 dual-sensor sites likely cluster in specific regions. NTU-only sites from Phase 7B should fill gaps.
2. **SSC range** -- ensure the vault spans the full range (below 100, 100-1000, above 1000 mg/L). An all-low-SSC vault gives an artificially optimistic R-squared.
3. **Sensor vintage** -- if metadata is available, stratify by sensor model/age. Older NTU sensors have different noise characteristics.
4. **Sample count** -- ensure no vault site has fewer than 10 SSC samples. Sites with 2-3 samples contribute noise, not signal.

**Additional rule:** The NTU vault must be sealed before you see ANY model results from Phase 7A. If you select vault sites after seeing which sites perform well/poorly, you introduce selection bias. Lock the vault membership at the data download stage, not the evaluation stage.

---

## 5. External NTU Data (Grab-Sample Only, No Window Stats)

These rows will have:
- `turbidity_instant_ntu` = populated (grab sample value)
- `turbidity_max_1hr_ntu` = NaN
- `turbidity_std_1hr_ntu` = NaN
- `turbidity_instant_fnu` = NaN
- All FNU window stats = NaN

**Assessment: Informative but lower-quality, and the missing-data pattern is confounding.**

The problem is not that window stats are missing per se -- CatBoost handles NaN. The problem is that the missingness pattern is perfectly confounded with data source. Every external NTU row has the same NaN pattern (instant-only, no windows). Every USGS continuous NTU row has a different NaN pattern (instant + windows populated). The model will learn that "NTU instant populated + NTU windows NaN" means "external grab sample" and may learn source-specific biases rather than generalizable NTU-to-SSC relationships.

**Specific risks:**
- External grab samples may have systematically different turbidity-SSC relationships than USGS continuous monitoring (different sampling protocols, different points in the water column, different hydrograph timing bias).
- The +474% bias at UMC is a red flag that data quality varies enormously across organizations.
- Without window stats, these rows carry less information per sample. They are essentially single-point turbidity readings with watershed features. The model might overweight the watershed features for these rows, learning "at this type of watershed, SSC is approximately X" rather than "at this NTU reading, SSC is approximately Y."

**Recommendation:**
1. Add external NTU data ONLY from organizations where the zero-shot bias is below +/-30% (UMRR and SRBC, as the plan suggests). Exclude UMC and any other high-bias organizations entirely from training.
2. Add an indicator feature: `has_window_stats` (binary, 1 if any window stat is populated, 0 otherwise). This gives the model an honest signal that grab-sample rows have less temporal context, rather than forcing it to infer this from the NaN pattern.
3. Phase 7C should be the LAST phase, and external data should be added incrementally. Train with just USGS data first (Phases 7A+7B), evaluate, then add external data and check whether it helps or hurts. If it hurts, drop it. Do not bundle external data addition with the core NTU integration.
4. Cap external NTU contribution at no more than 20% of total NTU training rows to prevent the external grab-sample pattern from dominating NTU branch learning.

---

## 6. Experimental Design Concerns

**(a) Temporal confounding at dual-sensor sites.**
The plan acknowledges this risk but underestimates it. If site X had NTU sensors from 2005-2012 and FNU sensors from 2013-present, the dual-sensor rows with both populated may be very few (only the overlap period). Worse, the NTU-only and FNU-only rows from the same site come from different time periods, meaning they experienced different hydrological conditions. The model might attribute NTU-vs-FNU differences to actual sensor differences when they are really temporal/hydrological differences. Before proceeding, compute and report the temporal overlap statistics: for each of the 89 dual-sensor sites, how many SSC samples fall in the overlap window where both NTU and FNU were active?

**(b) Monotone constraint scope.**
The current monotone constraint set is `{turbidity_instant, turbidity_mean_1hr, turbidity_min_1hr, turbidity_max_1hr}`. After the rename, you need monotone constraints on BOTH the FNU and NTU versions of these features. The physical relationship (higher turbidity implies higher SSC) holds regardless of sensor type. Verify that `_build_monotone_constraints()` is updated to include all six level-based turbidity columns (instant, mean, min, max for both FNU and NTU). If only the FNU columns are constrained, the model can learn pathological NTU splits (e.g., higher NTU predicts lower SSC in some branch).

**(c) Non-independence of evaluation.**
The plan proposes evaluating after each phase (7A, 7B, 7C). Each evaluation informs whether to proceed and how. This is a legitimate adaptive design, but it means the final model has been optimized across multiple look-at-the-data decisions. The vault (both FNU and NTU) provides the only unbiased estimate. Do not use vault results to decide whether to include Phase 7C data. The vault is a one-shot final exam, not a development tool.

**(d) Interaction between NTU integration and the drop list.**
The current `optimized_drop_list.txt` was optimized for v9 (FNU-only). It drops `log_turbidity_instant`, `turbidity_mean_1hr`, `turbidity_min_1hr`, `turbidity_range_1hr`, and `turbidity_slope_1hr`. After adding NTU columns, the optimal drop list may change. The NTU versions of dropped features might be informative (or vice versa). The drop list should be re-optimized after Phase 7A, not carried forward from v9.

**(e) Sample weighting interaction.**
If the current model uses sample weighting (the training script accepts `sample_weights`), adding NTU-only rows changes the effective weight distribution. NTU-only rows from sites with many samples could dominate. Verify that the weighting scheme (if any) still produces balanced site/region representation after NTU rows are added.

**(f) Phase ordering creates a dependency chain that is hard to debug.**
If the final model (after Phase 7C) underperforms v9 on FNU validation, it will be difficult to determine whether the cause is: the column rename, the NTU-only rows, the external grab samples, the drop list, or an interaction between them. The plan's phased approach partially addresses this, but I would add a hard gate: if Phase 7A degrades FNU performance by more than the noise floor, STOP and diagnose before proceeding. Do not assume Phase 7B will fix it.

---

## Summary of Required Actions Before Implementation

| Priority | Action |
|---|---|
| **Critical** | Rename as standalone commit; full codebase grep; reproduction test against v9 |
| **Critical** | Update `features.py` derived features (`turb_Q_ratio`, `log_turbidity`, etc.) to handle the FNU/NTU fork |
| **Critical** | Update `_build_monotone_constraints()` for all six level-based turbidity columns |
| **Critical** | Add NaN-fraction validation gate to training script |
| **High** | Compute dual-sensor temporal overlap statistics before downloading anything |
| **High** | Lock NTU vault membership before seeing any Phase 7A results |
| **High** | Re-optimize drop list after Phase 7A |
| **High** | Report per-sensor-type metrics at every evaluation checkpoint |
| **Medium** | Add `has_window_stats` indicator feature for grab-sample rows |
| **Medium** | Cap external NTU contribution at 20% of NTU training rows |
| **Medium** | Feature importance comparison (v9 vs. NTU-integrated) at every phase |
| **Low** | NTU-only row ablation (Phase 7A: with vs. without NTU-only rows) |

---

*Dr. Ananya Krishnamurthy*
*Applied Environmental Statistics*
