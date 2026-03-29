# murkml Model Version History

## Naming Convention

Format: `murkml-{version}-{descriptor}`

- **Version**: Sequential number (1, 2, 3...)
- **Descriptor**: Short tag for what changed

Each entry records: training config, dataset, performance, and what changed from the previous version. This is the single source of truth for "which model had which numbers."

---

## Version History

### murkml-1-initial
- **Date:** 2026-03-24
- **Training sites:** 102 (pre-expansion, GAGES-II bug present)
- **Samples:** ~5,000
- **Features:** 99
- **Transform:** log1p
- **CV:** LOGO
- **R²(log):** 0.721
- **R²(native):** 0.295
- **Holdout R²:** Not evaluated
- **Notes:** First working model. GAGES-II attributes were silently destroyed by prune_gagesii() bug — all watershed features were zeros/NaN. Model was effectively sensor-only despite having 99 "features."

### murkml-2-pruned
- **Date:** 2026-03-27
- **Training sites:** 243 (266 total, 23 holdout)
- **Samples:** 12,253
- **Features:** 37 (after ablation from 102 → 62 → 37)
- **Transform:** log1p
- **CV:** LOGO (233 folds)
- **R²(log):** 0.725
- **R²(native):** 0.361
- **Holdout split:** data/train_holdout_split.parquet (266-site version, now overwritten)
- **Notes:** Feature reduction improved native R² from 0.295 to 0.361. Expert panel converged on 37 features. Bug fixes applied (dedup key, precip leakage, weather tz, QC codes). Linear interpolation for turbidity alignment. Collection method and sensor calibration features added.

### murkml-2-holdout
- **Date:** 2026-03-27
- **Same model as murkml-2-pruned, evaluated on holdout sites**
- **Holdout sites:** ~23 sites (from 266-site split)
- **Zero-shot R²(native):** 0.699
- **Zero-shot slope:** 0.719
- **Site adaptation (5 samples):** R² improved significantly
- **Notes:** The famous zero-shot number. BUT: holdout split is lost (overwritten when dataset expanded to 396 sites). Cannot reproduce this exact evaluation. Holdout set was small (~23 sites). May not be comparable to v4-holdout (76 sites).

### murkml-3-expanded
- **Date:** 2026-03-28 morning
- **Training sites:** 346 (383 total)
- **Samples:** 14,632
- **Features:** 37
- **Transform:** log1p
- **CV:** LOGO
- **R²(log):** 0.735
- **R²(native):** 0.154
- **Notes:** Added 117 sites via QC approval code fix. Log R² improved but native R² collapsed catastrophically. "Smoking Gun" analysis proved original 243 sites also degraded (0.361 → 0.189) — model structure changed, not just dilution from new sites. Triggered the transform/loss function investigation.

### murkml-4-boxcox (current)
- **Date:** 2026-03-28/29
- **Training sites:** 357 (396 total, 76 holdout) — fewer than 383 because 39 sites lack StreamCat
- **Samples:** 32,046
- **Features:** 44 (41 numeric + 3 categorical)
- **Transform:** Box-Cox lambda=0.2
- **Monotone:** ON (turbidity_instant, turbidity_max_1hr)
- **CV:** LOGO (357 folds)
- **R²(log):** 0.718
- **R²(native):** 0.290
- **KGE:** 0.767
- **Alpha:** 0.882
- **RMSE:** 165.6 mg/L
- **Bias:** 19.4%
- **BCF:** 1.364 (Snowdon)
- **Trees:** median 344
- **Holdout split:** data/train_holdout_split.parquet (396-site version, 320 train / 76 holdout)
- **Saved model:** data/results/models/ssc_C_sensor_basic_watershed.cbm (487 trees, lambda=0.2 confirmed)
- **Notes:** Box-Cox 0.2 chosen from 24-experiment transform sweep. Raw SSC ruled out. KGE eval_metric tested (no improvement). Lambda confirmed via fine sweep at 0.18-0.20.

### murkml-4-holdout
- **Date:** 2026-03-29
- **Same model as murkml-4-boxcox, evaluated on 76 holdout sites**
- **Holdout sites:** 76 (from 396-site split)
- **Holdout samples:** 5,847
- **Zero-shot R²(native):** 0.472
- **Zero-shot KGE:** 0.454
- **Zero-shot slope:** 0.578
- **Site adaptation (10 samples):** R²=0.457 (barely recovers to zero-shot level)
- **Site adaptation (20 samples):** R²=0.487
- **Notes:** Adaptation with <10 samples HURTS performance (correction overfits). 2-parameter linear correction in Box-Cox space is too aggressive with few samples. Panel recommends shrinkage estimator. Temporal adaptation even worse (seasonal bias in first-N samples).

---

## Key Comparisons

### Why murkml-2-holdout (0.699) and murkml-4-holdout (0.472) are NOT directly comparable:
1. Different holdout sites (23 vs 76 sites)
2. Different holdout split (266-site split vs 396-site split)
3. Different training data (12K vs 32K samples, 243 vs 357 training sites)
4. Different transform (log1p vs Box-Cox 0.2)
5. Different feature count (37 vs 44)
6. Old holdout split is lost — cannot re-run v2 on the new holdout

### To make a fair comparison, need:
- Run log1p model on same 396-site dataset with same 76-site holdout — DONE (v5)

---

### murkml-5-log1p-396sites
- **Date:** 2026-03-29
- **Purpose:** Fair comparison with v4 — same data, different transform
- **Training sites:** 357 (same as v4)
- **Samples:** 32,046 (same as v4)
- **Features:** 44 (same as v4, but NO monotone — log1p + monotone hurts)
- **Transform:** log1p
- **Holdout R²(native):** 0.460
- **Saved model:** data/results/models/ssc_C_v5_log1p_396sites.cbm
- **Notes:** Essentially identical to v4 (0.472 vs 0.460). Proved the v2→v4 holdout drop (0.699→0.472) is from data expansion + different holdout split, NOT the transform choice.

### murkml-6-merf-fe
- **Date:** 2026-03-29
- **Purpose:** MERF mixed-effects — test if per-site random effects improve generalization
- **Training sites:** 287 (fewer — MERF uses different tier pipeline)
- **Samples:** 26,515
- **Features:** 41 numeric only (MERF can't handle categoricals — lost collection_method, turb_source, sensor_family)
- **Transform:** Box-Cox 0.2
- **Architecture:** MERF (10 EM iterations) with CatBoost fixed effects + per-site random intercept + random slope on turbidity
- **Holdout R²(native):** 0.417 (via site_adaptation.py)
- **Saved model:** data/results/models/ssc_C_v6_merf_fe.cbm (fixed-effects component only)
- **Notes:** Worse than v4 (0.417 vs 0.472) because losing categoricals (especially collection_method, SHAP rank 3) costs more than the random-effects training benefit gains. MERF concept is sound but needs categorical support.

---

## Experiment Results (2026-03-29)

### Experiment A: Collection Method Split (7 models)
Specialist models trained on single collection methods are WORSE than v4 on their own domain:
- auto_point specialist: 0.215 vs v4's 0.377 on auto_point data
- depth_integrated specialist: 0.389 vs v4's 0.548 on depth_integrated data
- grab specialist: 0.111 vs v4's 0.282 on grab data

Splitting loses training data without gaining specialization. v4 handles collection_method well as a feature.

### Experiment B: Exclude Low-Quality Sites (3 models)
Removing bad sites improves pooled R² (cosmetic) but hurts per-site R² (real):
- B1 (no catastrophic): pooled 0.312 (+0.101) but med site 0.273 (-0.017)
- B3 (no low-var): pooled 0.324 (+0.113) but med site 0.236 (-0.054)

### Experiment C: Flow-Stratified Metrics
Not a flow-specific problem. MAPE actually best at storms (48.2%) vs baseflow (74.5%). Site heterogeneity dominates at all flow levels.

### Experiment D: Site Count Impact
Quality-tiered: sweet spot at ~194-256 sites (known methods, ≥20 samples). 96 best sites = best pooled but worst per-site.

Random selection (5 seeds): per-site R² variance is huge (std 0.064-0.089). More sites helps slightly, reduces variance, but site heterogeneity dominates.

### Experiment E: MERF
On identical pipeline (site_adaptation.py): v4 wins 0.472 vs MERF 0.417. MERF lost categorical features. MERF concept promising if categoricals can be added.

---

## What Changed Between Versions

| From → To | What changed | Effect on R²(native) |
|---|---|---|
| v1 → v2 | Fixed GAGES-II bug, 102→37 features, 102→266 sites | 0.295 → 0.361 (+0.066) |
| v2 → v3 | Added 117 sites (QC fix), same features | 0.361 → 0.154 (-0.207) COLLAPSE |
| v3 → v4 | Box-Cox 0.2, more samples (discrete turb), 37→44 features | 0.154 → 0.290 (+0.136) |
| v4 → v5 | Same data, log1p instead of Box-Cox | 0.290 → ~same (transform doesn't matter) |
| v4 → v6 | MERF architecture, lost categoricals | Holdout: 0.472 → 0.417 (-0.055) |

---

## Results Table

**This is the single source of truth for all experiment results. Updated via `/record-experiment` skill.**

| Label | Holdout R² | Med Site R² | Pooled R² | MAPE | Within 2x | Key Finding | Date |
|---|---|---|---|---|---|---|---|
| v1-initial | — | — | — | — | — | Broken GAGES-II, 99 features | 2026-03-24 |
| v2-pruned | 0.699 | — | — | — | — | 37 features, 266 sites (old holdout, 23 sites) | 2026-03-27 |
| v3-expanded | — | — | — | — | — | Native R² collapsed 0.361→0.154 | 2026-03-28 |
| **v4-boxcox** | **0.472** | **0.290** | **0.211** | — | — | **Current best. Box-Cox 0.2, monotone, 44 features** | 2026-03-29 |
| v5-log1p | 0.460 | — | — | — | — | Transform doesn't matter (0.460 vs 0.472) | 2026-03-29 |
| v6-merf-fe | 0.417 | 0.357 | 0.290 | 57.2% | 60.3% | MERF loses to v4 — lost categoricals | 2026-03-29 |
| A1-auto_point | — | 0.146 | 0.296 | 75.3% | 51.9% | Specialist worse than v4 on own domain | 2026-03-29 |
| A2-depth_integrated | — | 0.308 | 0.203 | 57.6% | 59.4% | Best per-site among splits | 2026-03-29 |
| A3-grab | — | 0.222 | 0.175 | 49.2% | 63.6% | Best MAPE among pure splits | 2026-03-29 |
| A4-auto+depth | — | 0.204 | 0.294 | 66.2% | 55.8% | No improvement | 2026-03-29 |
| A5-auto+grab | — | 0.121 | 0.295 | 76.0% | 51.4% | Worst per-site | 2026-03-29 |
| A6-depth+grab | — | 0.377 | 0.203 | 45.8% | 65.5% | Best MAPE and within-2x overall | 2026-03-29 |
| A7-known_only | — | 0.318 | 0.279 | 53.4% | 64.0% | Excluding unknown doesn't help | 2026-03-29 |
| B1-no_catastrophic | — | 0.273 | 0.312 | 58.0% | 60.4% | Cosmetic: pooled up, per-site down | 2026-03-29 |
| B2-no_negative | — | 0.128 | 0.282 | 57.6% | 61.4% | Too aggressive — per-site much worse | 2026-03-29 |
| B3-no_lowvar | — | 0.236 | 0.324 | 59.6% | 59.2% | Best pooled, per-site worse | 2026-03-29 |
| D1-highest (96) | — | 0.158 | 0.386 | 62.1% | — | Best pooled, worst per-site | 2026-03-29 |
| D2-good (194) | — | 0.293 | 0.315 | 56.5% | — | Sweet spot for per-site | 2026-03-29 |
| D3-moderate (256) | — | 0.294 | 0.311 | 57.2% | — | Nearly = D2 | 2026-03-29 |
| D4-all (287) | — | 0.266 | 0.319 | 54.3% | — | Adding low-quality hurts per-site | 2026-03-29 |
| D5-continuous (109) | — | 0.165 | 0.224 | 77.6% | — | Too few sites | 2026-03-29 |
| D-rand-100 (5 seeds) | — | 0.205±0.083 | 0.281±0.031 | — | — | High variance per-site | 2026-03-29 |
| D-rand-150 (5 seeds) | — | 0.226±0.089 | 0.286±0.016 | — | — | High variance per-site | 2026-03-29 |
| D-rand-200 (5 seeds) | — | 0.191±0.071 | 0.316±0.025 | — | — | Pooled improving | 2026-03-29 |
| D-rand-250 (5 seeds) | — | 0.275±0.064 | 0.305±0.021 | — | — | Best random per-site | 2026-03-29 |
| C-flow (analysis) | — | — | — | — | — | Not a flow problem; MAPE best at storms | 2026-03-29 |
