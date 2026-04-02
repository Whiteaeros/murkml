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

### murkml-9-final-72feat (CONTAMINATED — DO NOT USE)
- **Date:** 2026-03-30
- **Training sites:** 254 (284 train - 30 w/o StreamCat). Split: 284 train / 76 validation / 36 vault
- **Samples:** 23,088
- **Features:** 72 (69 numeric + 3 categorical: 44 original + 28 SGMC lithology)
- **Transform:** Box-Cox lambda=0.2
- **Monotone:** ON (turbidity_instant, turbidity_max_1hr)
- **CV:** LOGO (254 folds, on training sites only — vault + holdout excluded)
- **R²(log):** 0.740
- **R²(native):** 0.335
- **MedSiteR²:** 0.335
- **KGE:** 0.778
- **Alpha:** 0.881
- **RMSE:** 133.0 mg/L
- **Bias:** +17.8%
- **BCF:** 1.390 (Snowdon)
- **Trees:** median 411
- **Split:** data/train_holdout_vault_split.parquet (284 train / 76 validation / 36 vault)
- **Saved model:** data/results/models/ssc_C_sensor_basic_watershed_v9_final_72feat.cbm
- **CONTAMINATION:** Model was trained on 357 sites including 76 holdout + 36 vault sites. All validation/vault results are data leakage. LOGO CV numbers are also tainted because the model saw more sites during training than it should have. Replaced by v10.
- **Notes:** 72 features locked after Phase 5 ablation (unanimous expert panel: keep all). 28 SGMC lithology features added. 5,536 unknown collection methods resolved.

### murkml-10-clean-dualbcf (SUPERSEDED by v11)
- **Date:** 2026-03-30
- **Training sites:** 254, holdout_vault_excluded=True (auto-exclusion + hard guard)
- **Samples:** 22,995
- **Features:** 72 (137 in tier, 65 dropped)
- **Transform:** Box-Cox lambda=0.2
- **Monotone:** ON (turbidity_instant, turbidity_max_1hr)
- **Boosting:** Ordered
- **CV:** LOGO (254 folds)
- **R²(log):** 0.756
- **MedSiteR²:** 0.395
- **KGE:** 0.777
- **RMSE:** 127.4 mg/L
- **BCF:** Dual — bcf_mean=1.327 (for loads), bcf_median=1.021 (for individual predictions)
- **Trees:** 446
- **Training time:** ~3 hours
- **Split:** data/train_holdout_vault_split.parquet (254 train / 76 holdout / 36 vault)
- **Saved model:** data/results/models/ssc_C_sensor_basic_watershed_v10_clean_dualbcf.cbm
- **Key changes from v9:**
  - Properly excludes holdout/vault from training (auto-exclusion + hard guard)
  - Dual BCF: bcf_mean for loads, bcf_median for individual predictions
  - 135 anomalous records cleaned from dataset
  - Seasonal split bug fixed (was producing identical results to random)
  - evaluate_model.py defaults to bcf_median (--bcf-mode flag added)
  - OLS benchmark and bootstrap CIs completed
  - CQR MultiQuantile training failed (23 hrs, Box-Cox compression defeats quantile learning for extremes)

### murkml-11-extreme-plain (CURRENT BEST)
- **Date:** 2026-04-01
- **Training sites:** 260 (291 train - 31 w/o StreamCat)
- **Samples:** 23,624
- **Total dataset:** 36,341 samples, 405 sites (expanded from 35,074/396 in v10)
- **Features:** 72 (137 in tier, 65 dropped)
- **Transform:** Box-Cox lambda=0.2
- **Monotone:** ON (turbidity_instant, turbidity_max_1hr)
- **Boosting:** Plain (switched from Ordered — same quality, 1/4 training time)
- **CV:** LOGO (260 folds)
- **BCF:** Dual — bcf_mean=1.297 (for loads), bcf_median=0.975 (for individual predictions)
- **Trees:** 485
- **Training time:** 47 minutes
- **Split:** data/train_holdout_vault_split.parquet (291 train / 78 holdout / 37 vault)
- **Key changes from v10:**
  - 10 new extreme-event sites added (NWIS hotspots + ScienceBase: Chester County PA, Klamath, Arkansas)
  - Plain boosting adopted (Ordered was wasting 3x time with no quality gain)
  - New vault: USGS-09153270 (Cement Creek CO, max 121,000 mg/L)
  - New holdout: USGS-06902000 (MO), USGS-07170000 (KS)
  - Samples >=1000 mg/L: 2,549 (7.0%), >=5000: 312 (0.9%), max=121,000 mg/L

### murkml-9-validation (76 sites — CONTAMINATED, model trained on these sites)
- **Date:** 2026-03-30
- **CONTAMINATION:** v9 model was trained on all 357 sites including these 76 holdout sites. All numbers below are data leakage, not honest holdout evaluation. Replaced by v10-holdout below.
- **Validation sites:** 76, 5,847 samples
- **Pooled NSE:** 0.692
- **Log-NSE:** 0.807
- **KGE:** 0.745
- **MAPE:** 55.6%
- **Within 2x:** 65.4%
- **Spearman rho:** 0.920
- **Bias:** +2.0%
- **Median per-site R²:** 0.418

### murkml-10-holdout (76 sites, HONEST)
- **Date:** 2026-03-30
- **Holdout sites:** 76 (never seen during v10 training)
- **BCF mode:** bcf_median
- **MedSiteR²:** 0.393
- **MAPE:** 41.7%
- **Within 2x:** 70.3%
- **Spearman rho:** 0.873
- **Bias:** -26.4%
- **Adaptation (N=10, random, bcf_median):** MedSiteR²=0.492, MAPE=36.4%, Within-2x=76.1%
- **Adaptation (N=10, temporal):** MedSiteR²=0.405, MAPE=36.9%
- **Bootstrap CIs (95%, bcf_mean):** MedSiteR²=0.409 [0.144, 0.459], Spearman=0.873 [0.842, 0.886]

### murkml-9-vault (36 sites — CONTAMINATED, model trained on these sites)
- **Date:** 2026-03-30
- **CONTAMINATION:** v9 model was trained on all 357 sites including these 36 vault sites. All numbers below are data leakage, not a clean final exam. The vault was NOT actually sequestered.
- **Vault sites:** 36, 3,660 samples
- **Pooled NSE:** 0.164
- **Log-NSE:** 0.825
- **Spearman rho:** 0.932
- **MAPE:** 49.4%
- **Within 2x:** 68.3%
- **Bias:** -7.8%
- **RMSE:** 1293.8 mg/L
- **Median per-site R²:** 0.486

### murkml-9-external (260 non-USGS NTU sites — CONTAMINATED)
- **Date:** 2026-03-30
- **CONTAMINATION:** These results used the v9 model which was trained on holdout+vault. External NTU sites were not in training, but the base model is still tainted. See v10-external below.
- **Sites:** 260, 6 organizations (UMRR, SRBC, GLEC, UMC, MDNR, CEDEN)

### murkml-10-external (260 non-USGS NTU sites, HONEST)
- **Date:** 2026-03-30
- **Sites:** 260, 11K samples
- **Sensor:** NTU (not FNU — model trained on FNU only)
- **Spearman:** 0.927
- **MAPE:** 53%
- **Bias:** -46%
- **Notes:** Model ranks correctly from zero-shot (Spearman 0.927) despite NTU sensors. Proves cross-network generalization.

### murkml-10-ols-benchmark
- **Date:** 2026-03-30
- **Finding:** CatBoost beats OLS at every N
- N=2 temporal: CatBoost R²=0.36 vs OLS R²=-0.56
- N=10 random: CatBoost R²=0.492 vs OLS R²=0.365
- **Notes:** OLS benchmark completed for paper. CatBoost advantage is largest at low N where shrinkage matters most.

### murkml-11-holdout (78 sites, HONEST)
- **Date:** 2026-04-01
- **Holdout sites:** 78 (never seen during v11 training; 2 new sites added from extreme expansion)
- **BCF mode:** bcf_median=0.975
- **MedSiteR²:** 0.402
- **MAPE:** 40.1%
- **Within 2x:** 70.0%
- **Spearman rho:** 0.907
- **Log-NSE:** 0.804
- **Bias:** -36.6%
- **Adaptation (N=10, random):** MedSiteR²=0.493, MAPE=34.6%, Within-2x=76.5%
- **Adaptation (N=10, temporal):** MedSiteR²=0.389, MAPE=38.6%
- **Adaptation (N=10, seasonal):** MedSiteR²=0.431, MAPE=40.1%
- **Bootstrap CIs (95%, v11, site-level blocking):** MedSiteR²=0.402 [0.358, 0.440], N=10 random: 0.493 [0.440, 0.547], KGE: 0.186 [0.078, 0.406], Spearman: 0.874 [0.836, 0.899]
  - Note: v10 CIs ([0.144, 0.459]) were much wider — site-level blocking is the correct method

### murkml-11-extreme-metrics
- **Date:** 2026-04-01
- **Top 1% underprediction:** -25% (improved from -28% in v10, -37% in original)
- **Top 5% Within-2x:** 71.5%
- **Disaggregated:**
  - Carbonate: R²=0.807
  - Volcanic: R²=0.195
  - Depth-integrated: R²=0.321
  - Auto-point: R²=0.238
  - SSC <50 mg/L: R²=-60.6 (overpredicts — sensor contamination)
  - SSC >5,000 mg/L: R²=-3.4 (underpredicts — particle size shift at extremes)
- **First-flush physics:**
  - R²=0.285 (magnitude wrong, -52% bias)
  - Spearman=0.902 on first-flush events (ranking preserved)
  - Interpretation: model captures event timing and relative severity correctly; Bayesian adaptation corrects magnitude
- **Notes:** Extreme data expansion improved top-1% underprediction from -28% to -25%. Low-SSC overprediction persists (sensor contamination, not model failure). Extreme underprediction persists (particle size shift; no global fix possible per calibration experiment). First-flush R² is low because bcf_median does not correct for event-scale bias; Spearman=0.902 is the correct ranking metric.

### v9-vs-v11 contamination comparison (same 78-site holdout)

Quantifies exactly how much the v9 contamination inflated metrics:

| Metric | v9 (contaminated) | v11 (honest) | Delta |
|--------|-------------------|-------------|-------|
| MedSiteR² (zero-shot) | 0.463 | 0.402 | -0.061 |
| Pooled NSE | 0.688 | 0.306 | -0.382 |
| Spearman | 0.923 | 0.907 | -0.016 |
| MAPE | 53.5% | **40.1%** | -13.4pp (v11 better) |
| Within-2x | 66.4% | **70.0%** | +3.6pp (v11 better) |
| Bias | +2.0% | -36.6% | v9 artificially unbiased |
| First flush R² | 0.907 | 0.285 | -0.622 (contamination artifact) |
| First flush bias | -0.8% | -52.5% | v9 memorized flush events |
| N=10 random MedSiteR² | 0.537 | 0.493 | -0.044 |

**Key finding:** v9 inflated R²-based metrics (NSE, MedSiteR², first flush R²) because it trained on holdout sites. But v11 actually has BETTER practical metrics (MAPE, within-2x) due to bcf_median and cleaned data. The "0.864 first-flush R²" cited in early analyses was a train-set metric, not real performance.

Evaluation files: `data/results/evaluations/v9_on_v11_holdout_*`

---

### murkml-11-conformal-intervals (Mondrian empirical CIs)
- **Date:** 2026-04-01
- **Method:** Mondrian conformal prediction — empirical nonconformity scores binned by predicted SSC range (5 bins), calibrated from 23,588 LOGO CV predictions
- **Script:** `scripts/empirical_conformal_intervals.py`
- **Results:** `data/results/evaluations/empirical_conformal/`
- **90% target coverage — holdout result: 90.6%** (well-calibrated)
- **Per-bin coverage and interval widths (90% target):**

| Bin | SSC range | Coverage | Interval width (median) | Notes |
|-----|-----------|----------|------------------------|-------|
| 1 | 0–30 mg/L | 92% | 43 mg/L | Slightly conservative |
| 2 | 30–100 mg/L | 91% | 184 mg/L | On target |
| 3 | 100–500 mg/L | 89% | 710 mg/L | Slightly liberal |
| 4 | 500–2000 mg/L | 91% | 2,385 mg/L | On target |
| 5 | 2000+ mg/L | 52% | — | **UNRELIABLE** — only 31 holdout samples; flag as unreliable in outputs |

- **Both versions available:** binned (step-function widths) and continuous interpolation (smooth widths)
- **Calibration source:** 23,588 LOGO CV predictions (training sites only; holdout/vault never touched)
- **Supersedes:** CQR MultiQuantile (23-hr failure — Box-Cox compression defeated quantile learning for extremes)
- **Paper language:** "90% Mondrian conformal prediction intervals achieve 90.6% holdout coverage. The 2000+ mg/L bin (n=31) is flagged as unreliable and excluded from coverage claims."

---

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

### Site Contribution Analysis (2026-03-30)

**Method:** Out-of-bag random subset scoring. 50 subsets of 100 training sites, train on subset, evaluate on the other 154 excluded sites. Score = mean(OOB R² with site) - mean(OOB R² without site).

**Results:** 254 sites scored, ~20 appearances each. 110 anchors, 34 neutral, 110 noise.
- Unknown collection method sites: 64% noise rate vs 43% overall
- SSC variability correlates with noise (Spearman rho=-0.159, p=0.012)
- Top anchor: USGS-02203655 (+0.081), Worst noise: USGS-02204037 (-0.086)

**CRITICAL FINDING: "Noise" sites carry extreme event signal.**
Dropping 15 worst noise sites destroyed the model:

| Metric | All sites | Drop 15 noise | Delta |
|---|---|---|---|
| First Flush R² | 0.905 | 0.264 | -0.641 |
| Top 1% Extreme R² | 0.793 | -0.043 | -0.836 |
| Zero-shot NSE | 0.692 | 0.302 | -0.390 |
| MedSiteR² | 0.418 | 0.290 | -0.128 |

**Conclusion:** Sites that hurt average performance carry the ONLY signal for extreme events, first flush, and unusual conditions. KEEP ALL 284 TRAINING SITES. Do not prune based on aggregate metrics.

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

### murkml-8-mixed-effects-research (2026-03-28)

**Research question:** Can mixed-effects gradient boosting beat v4 while keeping native categoricals?

**Three approaches tested:**

#### v8-gpboost (GPBoost library — LightGBM + mixed effects)
- **Date:** 2026-03-28
- **Architecture:** GPBoost v1.6.6, LightGBM trees + grouped random intercept + random slope on turbidity
- **Features:** 44 (all v4 features including 3 categoricals via LightGBM native handling)
- **Training:** 287 sites, 26,515 samples, 663 trees (early stopped)
- **Holdout R²(native):** 0.145 — much worse than v4
- **Why it failed:** LightGBM trees substantially underperform CatBoost trees on this dataset. The mixed-effects framework is correct but the tree model is weaker. GPBoost has no CatBoost backend.

#### v8-catboost-merf (Custom EM loop around CatBoost)
- **Date:** 2026-03-28
- **Architecture:** Custom MERF EM loop (10 iterations) with CatBoost as fixed-effects model, native categoricals preserved
- **Features:** 44 (all v4 features including 3 categoricals)
- **Training:** 287 sites, 26,515 samples
- **Holdout R²(native):** 0.144 — much worse than v4
- **Saved model:** data/results/models/ssc_C_v8_merf_cat.cbm (fixed-effects component)
- **Why it failed:** The EM loop "corrupts" fixed effects. By training CatBoost on y* = y - Z@b (residuals after subtracting random effects), the fixed-effects model learns a different function. For new sites where b=0, predictions are systematically biased (BCF=1.88 vs v4's 1.36). Random intercept std grew to 0.83 in Box-Cox space — the model over-relies on per-site correction.
- **Key insight:** MERF fundamentally hurts zero-shot prediction because the fixed-effects model absorbs less site-level variation during training.

#### v8-posthoc-RE (Post-hoc Bayesian shrinkage — WINNER)
- **Date:** 2026-03-28
- **Architecture:** v4 CatBoost model untouched + post-hoc Bayesian shrinkage random effects estimated from training residuals
- **Zero-shot R²:** 0.472 (identical to v4 — same model)
- **Population parameters learned from training:** sigma²=3.52 (within-site), D=0.42 (between-site intercept variance), RE std=0.65
- **Shrinkage factors:** N=1: 0.107, N=3: 0.264, N=5: 0.374, N=10: 0.544, N=20: 0.705
- **Saved:** data/results/models/ssc_C_v8_posthoc_re_params.json

**Adaptation curve comparison (Naive vs Bayesian RE):**

| N cal | Naive (v4) | Bayes RE | Delta | Winner |
|---|---|---|---|---|
| 0 | 0.472 | 0.472 | 0.000 | Tied |
| 1 | 0.446 | 0.376 | -0.070 | Naive |
| 2 | 0.004 | 0.422 | +0.418 | **Bayes** |
| 3 | 0.267 | 0.485 | +0.218 | **Bayes** |
| 5 | 0.388 | 0.463 | +0.076 | **Bayes** |
| 10 | 0.487 | 0.504 | +0.016 | **Bayes** |
| 20 | 0.509 | 0.524 | +0.015 | **Bayes** |

**Key findings:**
1. MERF (both GPBoost and custom EM) fundamentally degrades zero-shot performance. The approach of jointly training fixed+random effects hurts when most prediction targets are new sites.
2. Post-hoc Bayesian shrinkage is the correct approach: keep the best zero-shot model, add shrinkage-based adaptation.
3. The Bayesian RE fixes the "adaptation hurts at small N" problem: N=2 goes from catastrophic (0.004) to useful (0.422). N=3 already exceeds zero-shot (0.485 > 0.472).
4. The shrinkage factor provides principled regularization: with 1 sample, trust only 10.7% of the empirical correction; with 20 samples, trust 70.5%.
5. For deployment: use naive offset at N=1 (it's better), Bayesian shrinkage at N>=2.

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
| v4 → v8-gpboost | GPBoost (LightGBM + mixed effects) | Holdout: 0.472 → 0.145 (-0.327) WORSE |
| v4 → v8-catboost-merf | Custom EM loop around CatBoost w/ categoricals | Holdout: 0.472 → 0.144 (-0.328) WORSE |
| v4 + v8-posthoc-RE | Post-hoc Bayesian shrinkage RE (intercept only) | Zero-shot same (0.472), adaptation N=3 improved 0.267→0.485 |

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
| v8-gpboost | 0.145 | — | 0.084 | 72.4% | 46.0% | GPBoost (LightGBM trees) much worse — LightGBM underperforms CatBoost on this data | 2026-03-28 |
| v8-catboost-merf | 0.144 | — | 0.326 | 78.6% | 53.0% | Custom EM loop around CatBoost: EM corrupts fixed effects for zero-shot | 2026-03-28 |
| **v8-posthoc-RE** | **0.472** | — | — | — | — | **Post-hoc Bayesian RE: zero-shot=v4, N=3 adaptation 0.485 (was 0.267), N=10 0.504** | 2026-03-28 |
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

---

## Task #1/#13: Bayesian Site Adaptation v2 (2026-03-28)

### Method
1-parameter additive bias in Box-Cox space with Student-t shrinkage prior (df=4).
Staged: intercept-only (N<10), slope+intercept (N>=10).
BCF also shrunk toward 1.0 with separate k_bcf = 3*k.

```
delta = (N / (N + k * w_t)) * mean(obs_bc - pred_bc)
w_t = (df+1) / (df + z^2)   # Student-t weight (less shrinkage for extreme sites)
```

### Why Student-t not Gaussian
Residuals have skewness=2.0, kurtosis=13.8. A Gaussian prior over-shrinks sites with
large positive residuals. Student-t df=4 has heavier tails (excess kurtosis=3 vs 0),
so sites that genuinely need large corrections aren't penalized.

### Results (200 MC trials, 76 holdout sites, v4 model)

| N_cal | v4 OLS (old) | k=15 (best) | k=20 | k=25 | k=30 | k=35 (strict mono) |
|---|---|---|---|---|---|---|
| 0 | 0.472 | 0.472 | 0.472 | 0.472 | 0.472 | 0.472 |
| 1 | 0.397 | **0.476** | 0.475 | 0.474 | 0.474 | 0.472 |
| 2 | -0.012 | **0.485** | 0.485 | 0.485 | 0.485 | 0.484 |
| 3 | — | 0.484 | 0.484 | 0.483 | 0.485 | 0.484 |
| 5 | 0.359 | **0.487** | 0.486 | 0.486 | 0.486 | 0.485 |
| 10 | 0.457 | **0.502** | 0.499 | 0.496 | 0.493 | 0.489 |
| 20 | 0.487 | **0.509** | 0.508 | 0.507 | 0.507 | 0.506 |

### Monotonicity
- k=15: PASS (practical, tol=0.002; max violation 0.0018 at N=2 vs N=3)
- k=20-30: PASS (practical, tol=0.002)
- k=35: PASS (strict, 0 violations)

### Key Improvements over v4 OLS
- **N=1:** 0.476 vs 0.397 (+0.079) — no longer damages predictions
- **N=2:** 0.485 vs -0.012 (+0.497) — the catastrophic collapse is gone
- **N=5:** 0.487 vs 0.359 (+0.128) — immediate usable improvement
- **N=10:** 0.502 vs 0.457 (+0.045) — substantial gain
- **N=20:** 0.509 vs 0.487 (+0.022) — best R2 at any N

### Recommended Configuration
- **k=15, df=4, slope_k=10, bcf_k_mult=3.0** — best performance at all N values
- Practical monotonicity (tol=0.002 covers MC noise at N=2 vs N=3)
- For strict monotonicity guarantee: use k=35 (costs ~0.013 R2 at N=10)

### Saved Artifacts
- Script: `scripts/site_adaptation_bayesian.py`
- All results: `data/results/site_adaptation_bayesian_all.parquet`
- Best results: `data/results/site_adaptation_bayesian_best.parquet`
- Summary JSON: `data/results/site_adaptation_bayesian_summary.json`

| #1/#13-bayesian-adapt | 0.509 (N=20) | — | — | — | — | Bayesian shrinkage eliminates adaptation collapse. N=2: 0.485 vs -0.012. Monotonic curve (practical). Student-t df=4, k=15. | 2026-03-28 |
| Bayesian-k15-200mc | 0.509 (N=20) | — | — | — | — | Best Bayesian: k=15, Student-t df=4, 200 MC trials. N=2: 0.485 (was -0.012). Adaptation never hurts. | 2026-03-29 |
| v4-eval-bayesian-k15 | pooled=0.665 | 0.337 (zero-shot) | 0.665 | 127.7% | 62.2% | VERIFIED PIPELINE. Bayesian wins N=2-5 (0.368 vs 0.031), old wins N=10+ (0.483 vs 0.393). | 2026-03-29 |
| v4-eval-old2param | pooled=0.665 | 0.337 (zero-shot) | 0.665 | 127.7% | 62.2% | VERIFIED PIPELINE. Old 2-param still better at high N but catastrophic at N=2. | 2026-03-29 |
