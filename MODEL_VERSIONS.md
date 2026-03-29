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
| #5-bimodal-slope | — | — | — | — | — | Unimodal (dip p=0.98, BIC favors 1-comp). Mean=0.93, std=0.21. HUC2 weakly associated (chi2 p=0.0006) but no continuous attr correlates. | 2026-03-28 |
| #6-residual-norm | — | — | — | — | — | NOT normal: skew=2.0, kurtosis=13.8, 2% beyond 3-std (7x normal). Right-skewed + heavy-tailed. Need Student-t or skew-normal prior, not Gaussian. | 2026-03-28 |

---

## Task 8: Individual Prediction Error Distribution (v4-boxcox, 32,003 predictions)

### Overall Error Quantiles

| Quantile | Absolute Error (mg/L) | Percentage Error |
|---|---|---|
| 25th | 8.1 | 28.7% |
| 50th (median) | 29.1 | 63.6% |
| 75th | 125.5 | 125.3% |
| 90th | 367.3 | 251.6% |
| 95th | 679.9 | 386.5% |
| Mean | 181.6 | 137.5% |

### Error Stratified by SSC Level

| SSC Level | n | Med Abs Err (mg/L) | Mean Abs Err | 90th Abs Err | Med Pct Err | Mean Pct Err |
|---|---|---|---|---|---|---|
| Low (<50 mg/L) | 15,602 | 9.1 | 23.2 | 43.7 | 86.1% | 202.1% |
| Medium (50–500) | 12,184 | 77.9 | 131.0 | 293.9 | 54.0% | 85.0% |
| High (500–5000) | 4,066 | 403.4 | 619.3 | 1,443.6 | 42.1% | 48.8% |
| Extreme (>5000) | 151 | 5,556.3 | 8,846.8 | 16,128.4 | 83.6% | 73.3% |

### Heteroscedasticity

**Yes, strongly heteroscedastic.** Absolute error grows ~600x from Low to Extreme SSC (median 9→5,556 mg/L). Percentage error shrinks from Low to High (86%→42% median) but reverses at Extreme (84%) — model completely underpredicts extreme events. The model is proportionally best in the 500–5000 mg/L range (42% median pct error) and worst at low SSC where small absolute errors look huge as percentages.

### Worst Single Predictions

- **Worst absolute:** USGS-12170300 — true 70,000 mg/L, predicted 997 mg/L (error: 69,003 mg/L, 98.6%). A lahar/volcanic sediment event the model cannot capture.
- **Worst percentage:** USGS-02336240 — true 1 mg/L, predicted 1,228 mg/L (122,704%). Model grossly overpredicted a near-zero observation.

---

## Task 10: Catastrophic Site Classification (51 sites with R²(native) < -1)

### Classification Results

| Category | Count | Description |
|---|---|---|
| **Low signal** | 17 (33%) | SSC range <100 mg/L AND mean abs error <50 mg/L. R² is bad because there's nothing to predict, but predictions aren't far off in absolute terms. |
| **Mixed** | 27 (53%) | Intermediate — some signal, moderate errors. |
| **Genuinely wrong** | 7 (14%) | Mean abs error >200 mg/L OR error >2x SSC range. Model is making large, substantive mistakes. |

### Low Signal Examples (R² is misleading — errors are small)

| Site | R²(native) | SSC Range (mg/L) | Mean Abs Error (mg/L) | n |
|---|---|---|---|---|
| USGS-09013500 | -21.9 | 2.5 | 3.5 | 20 |
| USGS-05536356 | -2.5 | 9.0 | 4.3 | 20 |
| USGS-04249000 | -13.0 | 26.5 | 9.3 | 148 |
| USGS-14181500 | -34.6 | 37.0 | 41.5 | 20 |

These sites have near-constant SSC. A 3–41 mg/L average error is operationally acceptable; R² is just the wrong metric for flat signals.

### Genuinely Wrong Examples (model fails substantively)

| Site | R²(native) | SSC Range (mg/L) | Mean Abs Error (mg/L) | n | Collection | Sensor |
|---|---|---|---|---|---|---|
| USGS-432004118453400 | -4.0 | 1,546 | 607.5 | 51 | grab | unknown |
| USGS-01478185 | -2.0 | 1,046 | 472.5 | 22 | depth_integrated | unknown |
| USGS-06893820 | -1.5 | 2,109 | 272.1 | 142 | unknown | ysi_6series |
| USGS-07048600 | -2.5 | 899 | 263.7 | 16 | depth_integrated | unknown |
| USGS-11336685 | -45.9 | 41 | 84.6 | 6 | unknown | unknown |
| USGS-11336680 | -44.8 | 30 | 70.9 | 5 | unknown | unknown |

### What genuinely wrong sites have in common

1. **Unknown metadata:** 4/7 have unknown collection method, 5/7 have unknown sensor — the model's categorical features can't help differentiate them.
2. **Highly skewed SSC:** Most have SSC skew >1.0 (heavy right tail). The model predicts near the median but misses the extremes.
3. **Unusual turbidity-SSC ratios:** USGS-07048600 has turb/SSC ratio of 2.74 (turbidity much higher than SSC), while USGS-06893820 and USGS-05406479 have ratios of 0.47 (SSC much higher than turbidity). These abnormal ratios suggest site-specific sediment properties the global model can't capture.
4. **Last two (11336685, 11336680) are tiny-n sites** (5–6 samples) in Sacramento Delta with small SSC range but errors >2x the range — too few samples for reliable assessment.

---

## Task 9: Instrument Model Differences Within FNU (pCode 63680)

### turb_source Feature Analysis

**turb_source is NOT zero-SHAP.** Actual mean |SHAP| = 0.008 (rank 29 of 44). Low but nonzero.

- **Values:** "continuous" (25,789 samples, 73%) and "discrete" (9,420 samples, 27%)
- **169 sites** are 100% continuous; **227 sites** have both continuous and discrete turbidity measurements
- turb_source varies WITHIN sites (not just between), so CatBoost CAN split on it
- **SSC/turbidity ratio differs:** continuous median 1.91, discrete median 1.68 — discrete turbidity has systematically lower SSC-per-FNU
- **Confounded with collection_method:** turb_source and collection_method are correlated (discrete turbidity often paired with depth-integrated sampling). collection_method (SHAP=0.113, rank 4) likely absorbs most of the signal turb_source could provide.

### Instrument Identification from NWIS

Queried all 396 sites via NWIS IV JSON API `methodDescription` field for pCode 63680:

- **148 sites (37%)** have some text in method description
- **84 sites (21%)** have identifiable instrument models
- **248 sites (63%)** have blank method descriptions — instrument unknown

| Instrument | Sites | Median log-log slope | IQR | Median R² |
|---|---|---|---|---|
| FTS DTS-12 | 15 | 0.947 | 0.840–1.024 | 0.684 |
| YSI EXO | 16 | 0.919 | 0.684–1.074 | 0.804 |
| YSI 6136 | 13 | 0.883 | 0.786–1.079 | 0.754 |
| YSI 6-series | 7 | 0.659 | 0.656–0.708 | 0.639 |
| YSI (other) | 6 | 0.652 | 0.534–0.927 | 0.558 |
| Observator NEP5000 | 2 | 0.953 | — | 0.793 |

**No statistically significant difference between instruments** (Kruskal-Wallis H=6.33, p=0.18; ANOVA F=1.49, p=0.22). The YSI 6-series group has a noticeably lower slope (0.659) but with only 7 sites, cannot reject chance.

### Conclusions

1. **turb_source is correctly coded and not broken** — it varies across 227 of 396 sites and CatBoost sees it. Its low SHAP is because collection_method captures the same signal better.
2. **Instrument model is NOT available as a clean NWIS field** — must be scraped from free-text methodDescription, which is inconsistent (blank for 63% of sites).
3. **Instrument model does NOT significantly affect the SSC-turbidity relationship** in this dataset. The within-instrument variability is larger than the between-instrument difference.
4. **No action needed for the model** — adding instrument_model as a feature would cover only 21% of sites and shows no signal. The existing sensor_family feature (YSI 6-series, EXO, etc.) already captures what's available.
| #9-instruments | — | — | — | — | — | No instrument effect (p=0.18). turb_source SHAP=0.008 not 0.000. Only 21% sites have identifiable instrument model. No action needed. | 2026-03-29 |
| #4-unknown-methods | — | — | — | — | — | 218/231 unknown sites resolved via WQP. 26/30 catastrophic unknowns fixable. 13 truly unresolvable. Most are depth_integrated. | 2026-03-29 |
| #8-error-dist | — | — | — | — | — | Median abs error 29 mg/L, median pct error 64%. Heteroscedastic: best at 500-5000 mg/L (42% pct err). Extreme events underpredicted. | 2026-03-29 |
| #10-catastrophic | — | — | — | — | — | Only 7/51 genuinely wrong. 17 are low-signal (small range, small errors). 27 mixed. R² misleading for flat sites. | 2026-03-29 |
| #3-sgmc-lithology (point) | — | — | — | — | — | Point-based: SGMC bedrock lithology DOES predict turb-SSC slope (Kruskal-Wallis p=0.0024). Metamorphic rocks (gneiss, schist, amphibolite) produce higher slopes (~1.05-1.13); carbonate/chemical sedimentary produce lower slopes (~0.76-0.87). 8 categories significant at p<0.05. Best: metamorphic undiff rho=+0.165 p=0.004; coarse-detrital rho=-0.148 p=0.010. Effect sizes modest (rho 0.12-0.17). | 2026-03-29 |
| D-rand-100 (15 seeds) | — | 0.245±0.081 | 0.264±0.035 | — | — | Extended from 5→15 seeds for anchor analysis | 2026-03-28 |
| **v7-anchor50** | — | **0.367** | 0.207 | — | — | **50 anchor sites beat random-100 mean (0.245) and all-287 (0.266) on med-site R²** | 2026-03-28 |

---

## Task 11: Anchor Site Identification (2026-03-28)

### Method
Ran 15 random-100-site model trains (seeds 100-104 from D-redo + seeds 200-209 new).
For each of 287 training sites, computed:
- **Appearances**: how many of 15 random sets included the site
- **Win rate**: fraction of appearances in above-median-performing sets (7 of 15 had med-site R² > 0.255)
- **Anchor score**: win_rate - expected_win_rate (expected ≈ 0.467 since 7/15 sets were winners)

### Key Results

| Model | Sites | Samples | Pooled R² | Med Site R² |
|---|---|---|---|---|
| Anchor-50 | 50 | 4,981 | 0.207 | **0.367** |
| Random-100 (mean±std) | 100 | ~9,200 | 0.264±0.035 | 0.245±0.081 |
| Random-100 (best of 15) | 100 | ~9,200 | 0.347 | 0.360 |
| All-287 | 287 | 26,515 | 0.319 | 0.266 |

**Anchor-50 achieves the highest median per-site R² (0.367) with only 50 sites**, beating:
- Random-100 mean by +0.122 (50% improvement)
- All-287 by +0.101 (38% improvement)
- Even the best single random-100 run (0.360)

Pooled R² is lower (0.207 vs 0.319) because fewer sites = fewer samples = less pooled coverage, but per-site generalization is what matters for site-adaptive deployment.

### Top 20 Anchor Sites (highest anchor score)

| Site | Appeared | Won | Win Rate | Anchor Score | Samples | Median SSC | Std SSC | Method |
|---|---|---|---|---|---|---|---|---|
| USGS-01480870 | 4 | 4 | 1.00 | +0.533 | 129 | 289 | 354 | auto_point |
| USGS-01645704 | 3 | 3 | 1.00 | +0.533 | 507 | 273 | 1034 | auto_point |
| USGS-09144250 | 4 | 4 | 1.00 | +0.533 | 6 | 49 | 802 | depth_integrated |
| USGS-04175120 | 4 | 4 | 1.00 | +0.533 | 20 | 18 | 97 | depth_integrated |
| USGS-08188500 | 5 | 5 | 1.00 | +0.533 | 19 | 161 | 637 | depth_integrated |
| USGS-034336392 | 3 | 3 | 1.00 | +0.533 | 232 | 102 | 240 | unknown |
| USGS-02207400 | 3 | 3 | 1.00 | +0.533 | 102 | 89 | 323 | auto_point |
| USGS-11447850 | 4 | 4 | 1.00 | +0.533 | 22 | 10 | 128 | depth_integrated |

### Bottom 20 Noise Sites (lowest anchor score)

| Site | Appeared | Won | Win Rate | Anchor Score | Samples | Median SSC | Std SSC | Method |
|---|---|---|---|---|---|---|---|---|
| USGS-14181500 | 5 | 0 | 0.00 | -0.467 | 20 | 14 | 8 | unknown |
| USGS-03433637 | 3 | 0 | 0.00 | -0.467 | 110 | 211 | 1330 | unknown |
| USGS-03302060 | 5 | 0 | 0.00 | -0.467 | 27 | 26 | 98 | depth_integrated |
| USGS-07126485 | 3 | 0 | 0.00 | -0.467 | 63 | 105 | 2189 | auto_point |

### Anchor Score Distribution
- 36 sites with anchor_score > +0.2 (strong anchors)
- 37 sites with anchor_score < -0.2 (strong noise)
- 2 sites never appeared in any run
- Mean anchor score: 0.005, Std: 0.218

### Pattern Observations
- **Anchors span all collection methods** — not dominated by one type
- **Anchors include both high-sample and low-sample sites** — it's not just about data volume
- **Noise sites often have unknown metadata** (unknown collection method) and extreme SSC std relative to median
- **High-variance SSC sites appear in both lists** — variance alone doesn't determine anchor status

### Saved Artifacts
- Models: `data/results/models/ssc_C_anchor_s{200-209}.cbm` (10 random-100 models)
- Anchor model: `data/results/models/ssc_C_v7_anchor50.cbm`
- Analysis JSON: `data/results/anchor_site_analysis.json`
- Scores CSV: `data/results/anchor_site_scores.csv`
- Script: `scripts/anchor_site_identification.py`
| #11-anchors | — | — | — | — | — | 50 anchor sites beat all-287 on per-site R² (0.367 vs 0.266, +38%). Anchor selection works. 36 strong anchors, 37 noise sites. | 2026-03-29 |
| v7-anchor50 | — | 0.367 | 0.207 | — | — | 50 curated anchor sites. Best per-site R² of any model. Pooled lower (fewer sites). | 2026-03-29 |
| #3-sgmc-lithology | — | — | — | — | — | Watershed-overlay (355 sites, 28 lith categories). 5 significant (p<0.05): metamorphic_undiff rho=+0.172 (higher slope), metamorphic_amphibolite rho=+0.174, sedimentary_carbonate rho=-0.150 (lower slope), sed_chemical rho=-0.138, sed_clastic rho=-0.131. Effect sizes modest. | 2026-03-28 |
| OLS-comparison | — | — | — | — | — | OLS never beats CatBoost+Bayesian at ANY N. OLS plateaus at ~0.39 (N=50). CatBoost hits 0.51 (N=20). No crossover point. | 2026-03-29 |
| Bayesian-adapt-k30 | 0.512 (N=20) | — | — | — | — | Best holdout R² ever. Monotonic curve (almost). N=2: 0.486 vs old -0.012. Student-t prior, k=30. | 2026-03-29 |
| OLS-extended-N50 | — | — | — | — | — | OLS drops from 0.407 (N=20) to 0.372 (N=50) — overfits seasonal patterns. CatBoost stays ~0.44. Gap widens with more samples. | 2026-03-29 |
| #3-sgmc-watershed | — | — | — | — | — | Watershed-level lithology: 5 significant categories. Metamorphic amphibolite rho=+0.174, carbonate rho=-0.150. Stronger than point-based. 355 sites processed. | 2026-03-29 |
| v8-catboost-merf | 0.144 zero-shot | 0.144 | 0.326 | 78.6% | 53.0% | CatBoost-MERF with categoricals. WORSE than v4. EM loop destabilizes fixed effects. | 2026-03-29 |
| v8-gpboost | 0.158 zero-shot | 0.158 | 0.084 | — | — | GPBoost native mixed-effects. Also worse. | 2026-03-29 |
| stability-check | 0.359-0.432 | — | — | — | — | Bayesian k=30, 5 seeds: std=0.003-0.013. Stable but lower than site_adapt.py numbers (different eval set: 70 vs 76 sites). | 2026-03-29 |
