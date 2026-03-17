# Chen — Phase 3 Multi-Parameter Results Review

**Date:** 2026-03-16
**Scope:** Tiered training results for SSC, TP, Nitrate, OrthoP using CatBoost LOGO CV
**Prior review:** chen_phase2_review_20260316.md (feature pruning, GAGES-II strategy, site-set advice)

---

## Executive Summary

SSC is solved. TP is a genuine win and potentially publishable on its own. Nitrate and OrthoP are not viable as cross-site models with this feature set — but for different reasons, which matters for what you do next.

I have four sections below corresponding to the four review tasks, then a prioritized action list.

---

## 1. TP Tier C (0.62) Exceeding Per-Site OLS (0.60) — Real or Artifact?

This is the most interesting result in the table. A cross-site model beating per-site OLS means that information from other sites is compensating for noise in individual site regressions. This is plausible, not miraculous, for the following reasons:

**Why it could be real:**

- Per-site OLS with only turbidity as a predictor is a weak baseline. Many TP sites have <50 samples. With one predictor and small n, OLS is noisy. A cross-site CatBoost with 22 sensor features + 25 catchment features, trained on pooled data from 25 sites, has access to patterns that a single-site OLS cannot learn: seasonal TP dynamics captured by doy_sin/doy_cos, hysteresis via rising_limb and discharge_slope_2hr, and catchment-level TP loading via agriculture_pct and soil_permeability.
- TP has stronger mechanistic coupling to multiple sensor features than SSC does. Particulate P tracks turbidity (like SSC), but dissolved P tracks conductance and discharge regime. A multi-feature model captures both pathways; single-predictor OLS cannot.

**Why you should be suspicious:**

- The margin is only 0.02 in median R2. With 25 LOGO folds, this is within noise. You need to verify significance.
- Tier C restricts to 25 GAGES-II sites (down from 42). If the 17 dropped sites are disproportionately "hard" sites (low per-site R2), you are comparing Tier C on an easier subset to per-site OLS on the full 42. This would be an apples-to-oranges artifact.

**Validation I want to see (do all four):**

1. **Same-site comparison.** Recompute per-site OLS R2 on only the 25 GAGES-II sites. If per-site OLS on those 25 sites is already 0.65+, then Tier C at 0.62 is not actually beating it — the apparent win was from comparing different site pools.

2. **Paired sign test.** For each of the 25 sites, compute (Tier C site R2) - (per-site OLS site R2). Count how many sites have positive vs. negative differences. If it is 15:10, the median could be noise. If it is 20:5, the effect is robust. Report the p-value from a Wilcoxon signed-rank test on the paired differences.

3. **Examine the winning sites.** Which specific sites does Tier C beat per-site OLS on? If they are the low-sample-count sites (< 40 samples), the story is clear: cross-site learning is regularizing what per-site OLS cannot estimate well. This is a legitimate and publishable finding. If the winning sites are high-sample-count sites, something else is going on and you should investigate further.

4. **Tier B vs. per-site OLS on the full 42 sites.** Tier B (0.59) is already close to per-site OLS (0.60) on a larger site pool. If Tier B also beats per-site OLS on a paired test, the story is stronger because it does not depend on the GAGES-II subset.

**Bottom line:** The result is plausible and, if confirmed by the paired test, is genuinely significant for the paper. "Cross-site surrogate model matches or exceeds per-site calibration for TP" is a strong claim that practitioners care about. But you must rule out the site-pool artifact first.

---

## 2. OrthoP Tier C Overfitting (-0.55 to -1.31)

This is textbook. 25 sites, 47 features (22 sensor + 25 GAGES-II). The model has nearly 2 features per LOGO fold. CatBoost is fitting catchment-level noise.

### Diagnosis

The key indicator: Tier B (-0.55) is substantially better than Tier C (-1.31). This means the 25 GAGES-II features are net-harmful. They are not just unhelpful — they are actively destroying generalization. This happens when the model learns site-identifying patterns from catchment features (each site has a unique combination of GAGES-II values), which is equivalent to memorizing site identity. In LOGO CV, this is maximally penalized because the test site's catchment profile was never seen in training.

### Fixes (in order of priority)

**Option 1: Use Tier B and stop.** OrthoP at R2 = -0.55 is still a failed model by any standard. No amount of feature engineering will save it if the underlying signal is not there. The per-site OLS ceiling is 0.06, meaning turbidity alone explains essentially zero OrthoP variance even within individual sites. You cannot build a cross-site model for a relationship that does not exist at the site level.

**Option 2: If you want to try harder (I am skeptical).**
- Aggressive feature selection: forward selection using only 3-5 GAGES-II features with known mechanistic links to phosphorus (agriculture_pct, soil_permeability, clay_pct). Hard-code these rather than letting the model choose.
- Increase min_data_in_leaf to 50+ and reduce num_leaves / depth. You want the model to find only the broadest patterns.
- But honestly: the per-site OLS ceiling of 0.06 is your answer. There is no turbidity-OrthoP relationship to learn.

**My recommendation:** Report OrthoP Tier B (-0.55) as a negative result. State clearly: "Orthophosphate lacks sufficient covariance with continuous sensor data for viable surrogate estimation." This is valuable information. Negative results that save practitioners from building bad models are a contribution.

### Why OrthoP fails (and SSC/TP do not)

Orthophosphate is predominantly dissolved. It does not co-vary with turbidity (which measures particles). Its concentration is controlled by biological uptake, point source loading, and redox-driven sediment release — none of which are captured by the 22 sensor features. Conductance has a weak theoretical link (dissolved ions), but the signal-to-noise ratio is too low for cross-site learning. This is a physics problem, not a modeling problem.

---

## 3. Nitrate: Lost Cause or Fixable?

### The evidence says: nearly lost cause, but one avenue remains.

**Per-site OLS ceiling: 0.04.** This is the critical number. It means that even at individual sites, turbidity explains 4% of nitrate variance. There is essentially no turbidity-nitrate relationship. This makes sense physically: nitrate is dissolved, originates from diffuse agricultural and atmospheric sources, and its concentration is controlled by denitrification, dilution, and biogeochemical cycling — processes that are invisible to turbidity sensors.

**Tier C at -0.72** is a massive improvement over Tier A (-2.09), which means catchment attributes and derived features ARE adding information. The model is learning something — it is just not learning enough. The trajectory from -2.09 to -0.72 is encouraging in slope but the intercept is still deeply negative.

### What is actually happening

Negative R2 in LOGO means the model's predictions for held-out sites are worse than predicting the global mean. This happens when inter-site variability dominates intra-site variability and the model cannot correctly place new sites on the correct level. For nitrate, site-to-site differences in baseline concentration (driven by land use, geology, legacy nitrogen) are enormous — orders of magnitude. The sensor features capture temporal dynamics (storm events, seasonal cycles), but they cannot tell you whether the site is a pristine forest stream at 0.1 mg/L or an Iowa tile drain at 15 mg/L. The GAGES-II features (agriculture_pct, etc.) should help with this, and they do (Tier C is better), but 25 features on 25 sites is too many to learn these patterns reliably.

### What could still work (one thing worth trying)

**Site-level intercept model (two-stage approach):**

1. Stage 1: Use GAGES-II features only to predict the site-level median log-nitrate. This is a 25-site regression problem with 25 features — still borderline, but you can use a simple model (ridge regression or even just agriculture_pct + baseflow_index as 2 predictors). This gives you a predicted baseline for each site.
2. Stage 2: Use sensor features to predict deviations from the predicted site-level baseline.

This separates the "where am I on the nitrate gradient?" question (catchment attributes) from the "how does nitrate vary in time at this site?" question (sensor features). The current monolithic CatBoost is trying to answer both simultaneously, which is why it fails.

**Concrete implementation:**
- For each LOGO fold, hold out site i. Fit a ridge regression on the remaining 24 sites: `median_log_nitrate ~ agriculture_pct + baseflow_index + precip_mean_mm + clay_pct + n_dams`. Predict site i's baseline.
- Compute residuals: `y_residual = log_nitrate - predicted_baseline`.
- Fit CatBoost on residuals using sensor features only.
- Final prediction = predicted_baseline + CatBoost_residual.

This is essentially a mixed-effects intuition implemented as a two-stage pipeline. It will not get you to R2 = 0.5, but it might get you from -0.72 to something near 0. Getting above zero (beating the global mean) would itself be a result worth reporting.

### What will NOT work

- More features. You are already at the limit for 25 sites.
- Neural networks. Same data, same problem.
- Prediction chains (SSC -> nitrate). There is no SSC-nitrate relationship either.
- Multi-task learning with TP. TP and nitrate do not share enough mechanism. Particulate P tracks sediment; nitrate does not.

### My recommendation

Try the two-stage approach as a one-week experiment. If it gets R2 above -0.1, report it as an exploratory result. If not, report nitrate as a negative finding alongside OrthoP. Two well-characterized negative results are just as valuable as two positive ones for the paper.

---

## 4. Single Highest-Impact Next Step

**Validate the TP result.**

Here is my reasoning:

- SSC is done. R2 = 0.80 vs. ceiling 0.81. No further work needed on SSC modeling (uncertainty quantification and deployment are separate tasks).
- TP at 0.62 exceeding per-site OLS is your paper's headline result. But it needs the validation described in Section 1 before you can claim it. This validation is 2-3 hours of work (recompute per-site OLS on 25 sites, run paired test, tabulate winning/losing sites).
- Nitrate and OrthoP are secondary stories. They strengthen the paper as characterized negative results, but the positive TP finding is what gets the paper noticed.

**Specifically, in the next session:**

1. Run the TP validation (Section 1, items 1-4). **This is the priority.** ~3 hours.
2. If TP validation confirms the result, draft the results table and key figure (predicted vs. observed TP, colored by site, with per-site OLS lines overlaid). ~2 hours.
3. Try the two-stage nitrate model (Section 3). ~4 hours. This is a side experiment. If it works, great. If not, you report the negative result and move on.
4. Do NOT spend more time on OrthoP. Tier B is your final answer for OrthoP.

---

## 5. Additional Technical Notes

### On the GAGES-II feature set (25 pruned features)

Good work on the pruning from 44 to 25 — this follows my Phase 2 recommendation. The set looks reasonable. A few notes:

- `other_landcover_pct` is a derived complement (100 - forest - agriculture - developed). If all four are included, there is perfect multicollinearity. Drop `other_landcover_pct` or drop one of the others. CatBoost handles this internally but it muddies feature importance.
- `reference_class` and `ecoregion` are categoricals. With 25 sites, ecoregion likely has categories with 1-2 sites. Check the distribution and merge rare categories as I recommended in Phase 2.
- `n_dams` and `dam_storage` are likely correlated. Check if one is sufficient.

### On the sensor feature set (22 features)

The feature engineering looks solid. `turb_Q_ratio`, `DO_sat_departure`, and `SC_turb_interaction` are physically motivated and well-chosen. The temporal features (discharge_slope_2hr, rising_limb, Q_ratio_7d) capture event dynamics appropriately.

One addition to consider for TP specifically: **turbidity x discharge interaction.** Particulate P transport is the product of concentration (tracked by turbidity) and flow (discharge). The ratio `turb_Q_ratio` captures one aspect but the raw product might capture total flux better. This is worth testing in a Tier A+ experiment.

### SSC: What "solved" means

R2 = 0.80 in log-space across 57 sites with LOGO CV is an excellent result. But before calling it done for the product:

- Report performance in original units (mg/L), not just log-space. Duan's smearing back-transform can introduce bias, especially at high concentrations. Verify that KGE in original units is acceptable (> 0.5).
- Check for systematic bias by concentration range. A model that is great at 10-1000 mg/L but terrible at 1-10 mg/L is hiding behind the log transform.
- The per-site OLS ceiling (0.81) is itself only an estimate. Some sites may have per-site OLS R2 of 0.95, others 0.50. Report the distribution, not just the median.

---

## 6. Summary Table

| Parameter | Verdict | Action |
|---|---|---|
| SSC | Solved (0.80 vs 0.81 ceiling) | Report. Move to uncertainty quantification. |
| TP | Promising, needs validation | Validate Tier C vs per-site OLS on same 25 sites (priority). |
| Nitrate | Near-lost cause, one experiment left | Try two-stage site-intercept model. Report as negative if R2 stays below -0.1. |
| OrthoP | Failed, physics-limited | Use Tier B result (-0.55). Report as negative finding. Do not pursue further. |

---

## 7. For the Paper

With these results, the paper narrative writes itself:

1. **SSC cross-site surrogates are viable** — CatBoost with sensor + catchment features matches per-site calibration. This eliminates the need for site-specific regression, which is the current practice.
2. **TP cross-site surrogates may exceed per-site calibration** — if validation holds, this is the strongest result. The mechanism is clear: multi-feature learning captures both particulate and dissolved P pathways.
3. **Dissolved parameters (nitrate, OrthoP) resist cross-site surrogate modeling** — the turbidity-concentration relationship does not exist for dissolved species. This is a physics ceiling, not a modeling failure.

Point 3 is important to frame correctly. Reviewers will ask "why not include dissolved parameters?" Your answer is: "We did. Here is why they fail. This characterization of the boundary between learnable and non-learnable surrogate relationships is itself a contribution."

---

*Review by Dr. Sarah Chen, ML Engineering*
*Reviewing: murkml Phase 3 tiered training results*
