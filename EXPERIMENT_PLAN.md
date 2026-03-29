# Experiment Plan — 2026-03-29

## Goal
Understand what's driving per-site performance variation and find the best model configuration. Each experiment is independent, results committed immediately after each.

## Process Rules
1. After EVERY experiment: add result row to RESULTS table below, commit model + results to git
2. Before starting any experiment: re-read this plan to check what's done and what's next
3. No changing the plan mid-experiment without discussing first
4. Every model saved with versioned name: `ssc_C_{experiment_label}.cbm`
5. All evaluation uses per-site AND per-sample metrics, not just one aggregate number

## Quick Reference
- Quick model train + holdout eval: ~3 minutes
- GKF5 cross-validation: ~3 minutes
- Full LOGO CV: ~3.5 hours (only run on final winner)

## Baseline (murkml-4-boxcox)
- R²(native) LOGO CV median: 0.290 (mean: -1.075)
- R²(native) holdout (76 sites): 0.472
- R²(native) pooled: 0.211
- Per-site distribution: 15% excellent, 20% good, 22% fair, 11% poor, 18% bad, 15% catastrophic

---

## Experiment A: Collection Method Split & Grouping

**Question:** Do different collection methods have fundamentally different turbidity-SSC relationships that one model can't learn?

**Sub-experiments (7 models):**

| Label | Training data | Hypothesis | Drop collection_method feature? |
|---|---|---|---|
| A1-auto_point | auto_point samples only (~12,600) | ISCO-only relationship | Yes (constant) |
| A2-depth_integrated | depth_integrated samples only (~11,700) | Gold standard method only | Yes (constant) |
| A3-grab | grab samples only (~4,500) | Manual grab only | Yes (constant) |
| A4-auto+depth | auto_point + depth_integrated (~24,300) | Professional methods combined | No (2 categories) |
| A5-auto+grab | auto_point + grab (~17,100) | Point samples vs integrated | No (2 categories) |
| A6-depth+grab | depth_integrated + grab (~16,200) | Manual collection methods | No (2 categories) |
| A7-known_only | auto+depth+grab, exclude unknown (~28,900) | Remove unknown noise | No (3 categories) |

**Hypotheses for groupings:**
- A4: Tests "professional methods vs amateur/unknown"
- A5: Tests "point sample vs integrated" — both grab from one depth
- A6: Tests "manual vs automated collection"

**Evaluation:**
- All models evaluated on ALL 76 holdout sites (not just matching method)
- Report per-site R² distribution AND per-sample error distribution for each model
- Breakdown: how does each model perform on auto_point holdout samples vs depth_integrated vs unknown?
- This shows where each model works AND where it fails

**Success criteria:** If any split/grouped model beats v4 (holdout R²=0.472) by >0.05, collection method split is worth pursuing. If A7 (known only) beats v4, "unknown" samples are hurting training.

**Status:** NOT STARTED
**Result:** _pending_

---

## Experiment B: Exclude Low-Quality Sites

**Question:** Are noisy/catastrophic sites poisoning the model for the good sites?

**Sub-experiments:**

| Label | Training data | Selection method | Defensible for paper? |
|---|---|---|---|
| B1-no_catastrophic | Remove 51 sites with v4 LOGO R² < -1 | Outcome-based | No (circular) |
| B2-no_negative | Remove 112 sites with v4 LOGO R² < 0 | Outcome-based | No (circular) |
| B3-no_lowvar | Remove sites with SSC std below data-driven threshold | Characteristic-based | Yes |

**B3 threshold determination:**
- Before running B3, plot per-site R² vs SSC std to find the natural elbow
- Justify threshold with physics: minimum SSC variability needed for turbidity signal to exceed sensor noise (~2 FNU measurement uncertainty)
- Report results stratified by SSC variability quartiles regardless of threshold choice

**Circularity note:** B1 and B2 use v4's LOGO CV R² to select which sites to exclude, then retrain. This is scientifically indefensible — we're using the model's own failures to select its training data. Run them as comparison, but B3 is the version we'd report.

**Evaluation:**
- Holdout R² on same 76 sites (per-site and per-sample)
- Also check: do the excluded sites perform better or worse in the new model's holdout? (Validates whether exclusion helps the excluded sites too)

**Success criteria:** If B3 improves holdout R² by >0.03, site selection matters. If B1 and B3 give similar results, the selection method doesn't matter much.

**Status:** NOT STARTED
**Result:** _pending_

---

## Experiment C: Flow-Stratified Metrics

**Question:** Is the model good at baseflow and bad at storms, or bad everywhere?

**Step 1 — Analysis only (no retraining):**

Take existing v4 LOGO CV predictions (32,003 samples). For each sample, classify by **per-site** discharge quantile (not global — each site's discharge is relative to its own range):
- Low flow: bottom 25% of discharge at that site
- Mid flow: middle 50%
- High flow: top 25%
- Storm events: top 10%

Compute per-regime: R²(native), RMSE, MAPE, fraction-within-2x.

If a site lacks discharge data, exclude it from this analysis. Count how many sites are excluded.

**Step 2 — Conditional retraining (only if Step 1 shows a pattern):**

Three approaches, all tested:

| Label | Method | What it tests |
|---|---|---|
| C1-flow_regime_feature | Add "flow_regime" categorical (low/mid/high/storm) as a feature | Model can split on flow condition |
| C2-weighted_highflow | All samples, 3x weight on top 25% discharge | Emphasize storms without losing baseflow |
| C3-separate_flow_models | Train separate models for high-flow (top 25%) and low-flow (bottom 25%) samples | Completely separate relationships by flow regime |

**Success criteria:**
- Step 1: If high-flow R² is below 0.1 while low-flow R² is above 0.5, the model has a storm problem
- Step 2: If any of C1/C2/C3 improves high-flow R² without destroying low-flow R², that's the fix
- C3 specifically: if the separate high-flow model beats the general model on storm events, flow regime fundamentally changes the turbidity-SSC relationship (not just scaling)

**Status:** NOT STARTED
**Result:** _pending_

---

## Experiment D: Site Count & Data Quality Impact

**Question:** Does adding more (potentially noisier) sites help or hurt?

**Approach: Quality-tiered scaling curve**

| Label | Selection criteria | Expected sites | What it tests |
|---|---|---|---|
| D1-highest_quality | ≥50 samples AND known method AND SSC std > 100 | ~80-120 | Best data only |
| D2-good_quality | ≥20 samples AND known method | ~150-200 | Good data |
| D3-moderate_quality | ≥10 samples | ~280-320 | Most sites |
| D4-all | All 357 training sites | 357 | Current model |
| D5-continuous_only | turb_source = 100% continuous | ~200-250 | No discrete turbidity pairs |

**Randomness handling:** D1, D2, D3 — run 5 times each with different random seeds (stratified sampling by SSC variability + collection method + median SSC level to maintain representative distribution across runs). D4 and D5 are deterministic (no randomness). Total: 17 model trains.

**Stratification for random subsets:** When sampling sites for D1-D3, maintain proportional representation across:
- SSC variability (std): binned into low/medium/high thirds
- Collection method: auto_point dominant / depth_integrated dominant / unknown dominant / mixed
- Median SSC level: binned into low/medium/high thirds

This ensures each random subset is a miniature version of the full dataset, not accidentally biased toward one site type.

**Evaluation:** Holdout R² on same 76 sites. Report mean ± std across the 5 seeds for D1-D3.

**Success criteria:**
- If R² increases D1→D4: more data helps even when noisy
- If D1 or D2 beats D4: we have too many noisy sites, be selective
- If D5 beats D4: discrete turbidity pairs are hurting
- If std across 5 seeds is >0.05: results are unstable, site selection matters a lot

**Status:** NOT STARTED
**Result:** _pending_

---

## Experiment E: MERF (Mixed-Effects Random Forest)

**Question:** Does adding per-site random effects with proper shrinkage fix the site adaptation problem?

**Implementation:**
1. Check MERF package compatibility with CatBoost (sklearn wrapper). Fallback: LightGBM or manual EM loop.
2. Fixed effects: CatBoost with current 44 features (general turbidity-SSC relationship)
3. Random effects: per-site random intercept + random slope on turbidity (2 parameters per site)
4. Grouping variable: site_id only (not site_id + collection_method — too sparse)
5. New sites automatically get zero random effects (pure fixed-effect prediction = zero-shot)
6. Site adaptation: estimate new site's random effects from N grab samples via Bayesian update with shrinkage

**Evaluation:**
- GKF5 cross-validation R²(native)
- Holdout R² at 0, 1, 5, 10, 20 calibration samples
- Compare adaptation curve to v4 (does 1-5 sample adaptation still hurt?)
- Per-site R² distribution — does MERF reduce the catastrophic tail?

**Success criteria:**
- Adaptation curve is monotonically increasing (more samples = always better)
- Holdout R² at 5 samples exceeds 0.55
- Fewer than 10% of sites have R² < -1 (vs current 15%)

**Status:** NOT STARTED
**Result:** _pending_

---

## Execution Order

1. **C-Step1** — flow-stratified analysis, no retraining, ~2 minutes
2. **A** — collection method split, 7 model trains, ~15 minutes
3. **B** — exclude sites, 3 model trains, ~10 minutes
4. **D** — site count, 17 model trains, ~35 minutes
5. **C-Step2** — conditional flow retraining, ~5 minutes (if needed)
6. **E** — MERF implementation + evaluation, ~1-2 hours

Total estimated: ~2-3 hours

After each experiment: update this file with results, commit to git.

---

## Results Table

| Experiment | Label | Holdout R² | Per-site R² median | Notes | Date |
|---|---|---|---|---|---|
| Baseline | v4-boxcox | 0.472 | 0.290 (LOGO) | Current model | 2026-03-29 |
| _pending_ | | | | | |

---

## Decision Framework

After all experiments:
- Best configuration from A-D becomes the base model
- If E (MERF) improves on that, it becomes the production architecture
- Winner gets full LOGO CV for final reportable numbers
- All decisions documented here with reasoning
