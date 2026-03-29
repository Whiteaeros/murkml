# Experiment Plan — 2026-03-29

## Goal
Understand what's driving per-site performance variation and find the best model configuration. Each experiment is independent, results committed immediately after each.

## Quick Reference
- Quick model train + holdout eval: ~3 minutes
- GKF5 cross-validation: ~3 minutes
- Full LOGO CV: ~3.5 hours (only run on final winner)
- All models saved with versioned names and committed to git

---

## Experiment A: Collection Method Split & Grouping

**Question:** Do different collection methods have fundamentally different turbidity-SSC relationships that one model can't learn?

**Sub-experiments (7 models):**

| Label | Training data | What it tests |
|---|---|---|
| A1-auto_point | auto_point samples only (~12,600) | ISCO-only relationship |
| A2-depth_integrated | depth_integrated samples only (~11,700) | Gold standard method only |
| A3-grab | grab samples only (~4,500) | Manual grab only |
| A4-auto+depth | auto_point + depth_integrated (~24,300) | The two known methods combined |
| A5-auto+grab | auto_point + grab (~17,100) | Point samples combined |
| A6-depth+grab | depth_integrated + grab (~16,200) | Manual methods combined |
| A7-known_only | auto_point + depth_integrated + grab, exclude unknown (~28,900) | Everything except unknown |

**Evaluation:** Each model evaluated on holdout sites (same 76 sites) using the subset of samples matching that model's collection method. Also evaluate A7 on ALL holdout samples including unknown (does excluding unknown from training help or hurt predictions at unknown sites?).

**Success criteria:** If any split/grouped model beats the full model (v4, R²=0.472) by more than 0.05 R², the collection method split is worth pursuing.

---

## Experiment B: Exclude Catastrophic Sites

**Question:** Are the 51 catastrophic sites (R² < -1) poisoning the model for the good sites?

**Sub-experiments:**

| Label | Training data | What it tests |
|---|---|---|
| B1-no_catastrophic | Remove 51 sites with LOGO CV R² < -1 | Does removing worst sites help the rest? |
| B2-no_negative | Remove 112 sites with LOGO CV R² < 0 | Aggressive pruning — only keep sites where model works |
| B3-no_lowvar | Remove sites with SSC std < 40 mg/L | Remove by characteristic, not by R² (avoids circular logic) |

**Evaluation:** Holdout R² on the 76 holdout sites. Per-site R² distribution via GKF5.

**Success criteria:** If removing bad sites improves holdout R² by more than 0.03, site selection matters. If B3 (characteristic-based) works as well as B1 (outcome-based), we have a principled exclusion criterion.

**Important note:** B1/B2 use LOGO CV R² to select sites, which means we're using test performance to choose training data. B3 avoids this circularity by using a site characteristic (SSC variability) instead. B3 is the scientifically defensible version.

---

## Experiment C: Flow-Stratified Metrics

**Question:** Is the model good at baseflow and bad at storms, or bad everywhere?

**Step 1 (no retraining):**
Take existing v4 LOGO CV predictions (32,003 samples). For each sample, classify by discharge quantile:
- Low flow: bottom 25% of discharge at that site
- Mid flow: middle 50%
- High flow: top 25%
- Storm events: top 10%

Compute R²(native), RMSE, MAPE, and fraction-within-2x for each flow regime.

**Step 2 (conditional, only if Step 1 shows a pattern):**
If high-flow performance is much worse, train a flow-stratified model:

| Label | Training data | What it tests |
|---|---|---|
| C1-highflow_only | Only samples in top 25% discharge | Storm-specialist model |
| C2-weighted_highflow | All samples, but 3x weight on top 25% | Emphasize storms without losing baseflow |

**Success criteria:** If high-flow R² is below 0.1 while low-flow R² is above 0.5, the model has a storm problem. If C2 (weighted) improves high-flow R² without destroying low-flow R², that's the fix.

---

## Experiment D: Site Count Impact

**Question:** Did adding 130 sites from v2 to v4 help or hurt?

**The bias problem:** We can't just pick 266 random sites because we don't know which 266 were in v2 (holdout split was overwritten). And the data pipeline changed (bug fixes, new features, discrete turbidity added).

**Approach:** Instead of reconstructing v2, test the scaling curve:

| Label | Training sites | What it tests |
|---|---|---|
| D1-100sites | Random 100 of 357 training sites | Small dataset |
| D2-200sites | Random 200 of 357 training sites | Medium dataset |
| D3-all357 | All 357 training sites (= current v4) | Current model |
| D4-continuous_only | Only sites where turb_source is 100% continuous | Remove discrete turbidity pairs |

Run each 3 times with different random seeds to estimate variance.

**Evaluation:** Holdout R² on same 76 sites.

**Success criteria:** If R² increases monotonically from D1→D3, more sites helps. If D2 beats D3, we have too many noisy sites. If D4 beats D3, discrete turbidity pairs are hurting.

---

## Experiment E: MERF (Mixed-Effects Random Forest)

**Question:** Does adding per-site random effects with proper shrinkage fix the site adaptation problem?

**Implementation:**
1. `pip install merf`
2. Use CatBoost as the base estimator (fixed effects)
3. Add site_id as the grouping variable for random effects
4. MERF estimates per-site intercept + slope offset via EM algorithm
5. New sites get zero random effect (= current zero-shot behavior)
6. Sites with data get shrunk random effects

**Evaluation:**
- GKF5 cross-validation R²(native)
- Holdout R² at 0, 1, 5, 10, 20 calibration samples
- Compare adaptation curve to current (does 1-5 sample adaptation still hurt?)

**Success criteria:** If the adaptation curve is monotonically increasing (more samples = always better, never worse), MERF fixed the shrinkage problem. If holdout R² at 5 samples exceeds 0.55, this is a major improvement.

---

## Execution Order

1. **C-Step1** (flow-stratified metrics) — zero retraining, pure analysis, 2 minutes
2. **A** (collection method split) — 7 quick model trains, ~20 minutes total
3. **B** (exclude catastrophic) — 3 quick model trains, ~10 minutes
4. **D** (site count) — 12 quick model trains (4 configs × 3 seeds), ~30 minutes
5. **E** (MERF) — implementation + evaluation, ~1-2 hours

After each experiment: commit results to MODEL_VERSIONS.md and git.

## Decision Framework

After all experiments, we will have answers to:
- Should we split by collection method? (A)
- Should we exclude bad sites? (B)
- Where does the model fail by flow regime? (C)
- Does more data help? (D)
- Does MERF fix site adaptation? (E)

The winning configuration from A-D becomes the base model. If E (MERF) improves on that, it becomes the production architecture. Then and only then do we run full LOGO CV for final numbers.
