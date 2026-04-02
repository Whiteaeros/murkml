# murkml Decision Log

Every significant design choice and experiment, with results and reasoning.

---

## 1. Target Transform

### Box-Cox lambda=0.2 -- KEPT (winner from 24-experiment sweep)

| Config | R2(native) | BCF | Notes |
|--------|-----------|-----|-------|
| **Box-Cox 0.2 + monotone** | **0.241** | 1.351 | Winner |
| Box-Cox 0.3 + monotone | 0.238 | 1.292 | Close second |
| log1p + monotone OFF | 0.236 | 1.463 | Third |
| log1p + monotone ON | 0.217 | 1.711 | Monotone hurts log1p |
| Box-Cox MLE + monotone | 0.195 | 1.675 | MLE picks near 0 |
| Raw SSC (all configs) | <=0.012 | - | Definitively ruled out |

Fine lambda sweep confirmed peak at 0.18-0.20 (0.15=0.221, 0.18=0.240, **0.20=0.241**, 0.22=0.224, 0.25=0.228).

**Critical finding:** Monotone x transform interaction. Monotone HELPS Box-Cox (+0.060 R2_native) but HURTS log1p (-0.019). log1p over-compresses, making monotone redundant.

### v5 Fair Transform Comparison
- Ran log1p on same 396 sites / same holdout to isolate transform from data expansion.
- Box-Cox 0.2 holdout R2=0.472 vs log1p holdout R2=0.460. Nearly identical.
- The v2-to-v4 holdout drop (0.699 to 0.472) was from data expansion + harder holdout, NOT transform.

### log1p, sqrt, none transforms -- DROPPED
- log1p: BCF inflated to 1.71, over-compresses extremes
- sqrt: equivalent to Box-Cox 0.5, worse than 0.2
- none: R2 < 0.012, complete failure

---

## 2. Loss Function / Eval Metric

### KGE as eval_metric -- DROPPED (no improvement)
- R2(native)=0.241 vs RMSE baseline 0.241. Same performance, just fewer trees (426 vs 497).
- Expert consensus: KGE cannot be CatBoost training loss (batch-level, numerically unstable). Alpha=0.84 is structural.

### Sqrt sample weights -- DROPPED (destructive)
- R2(log) collapsed 0.718 to 0.528, trees collapsed 281 to 86.
- Weights flatten the gradient landscape.

### Linear sample weights -- DROPPED (catastrophic)
- R2(native)=0.004, 17 trees.

---

## 3. BCF Method

### Snowdon BCF -- KEPT
- Ratio-based, transform-agnostic. Correct for Box-Cox.
- Duan assumes log-normal residuals (only valid for log transforms).

### Dual BCF (mean + median) -- KEPT

| BCF | NSE | MAPE | Within-2x | Median pred/obs |
|-----|-----|------|-----------|----------------|
| bcf_mean=1.32 (Snowdon) | 0.692 | 55.6% | 65.4% | 1.44x |
| bcf_median=0.94 | 0.611 | **36.0%** | **73.8%** | 1.00x |

Same model, different scaling constant. bcf_mean for load estimation, bcf_median for monitoring. All three expert reviewers independently confirmed the 1.44x overprediction (75% of predictions too high, Wilcoxon p=6.2e-166).

### Binned BCF -- DROPPED
- Per-quartile BCF: R2 0.216 to 0.210. Did not help.
- Problem is in predictions (transform compression), not back-transformation.

---

## 4. Feature Additions

### EPA StreamCat (69 features) -- KEPT
- Tier C R2(log)=0.710, R2(native)=0.363, RMSE=111 mg/L. Significant improvement over Tier B.
- Replaces broken GAGES-II. 370/413 sites covered.
- Tier comparison statistically significant: B vs C native R2 improvement p<0.01, median +0.07.

### SGMC Lithology (28 features) -- KEPT
- Net flat on aggregate (dR2_native=-0.007) but 5 categories significant at p<0.05.
- Expert panel unanimous: keep for subgroup effects. Metamorphic rocks produce higher slopes (~1.05-1.13); carbonate/sedimentary produce lower (~0.76-0.87).
- 5-seed stability: 72 vs 58 features statistically indistinguishable (p=0.81). CatBoost handles noise.

### Weather (precip_48h, precip_7d, precip_30d, flush_intensity) -- KEPT
- +0.008 R2(log). Provides first-flush and antecedent condition context.
- Dropping weather destroys extreme event performance despite improving median.
- precip_7d alone sufficient (precip_48h and precip_30d redundant when precip_7d present).

### Longitude -- KEPT (latitude DROPPED)
- Expert panel 2-1: longitude captures maritime-continental gradient (physics).
- Lat+lon together memorize geography (site fingerprint). Dropping lat+lon+elev together: dR2_native=+0.086.

### Collection method -- KEPT
- SHAP rank 3-5. depth_integrated data inherently better quality.
- 5,536 unknown methods resolved via WQP metadata (88% of unknowns fixed, 218/231 sites resolved).
- 30/51 catastrophic sites had unknown method (59%) — resolution helps worst sites most.

### GAGES-II -- DROPPED
- prune_gagesii() bug destroyed all values silently (called on already-pruned data, produced zeros/NaN). Replaced by StreamCat.

### Categorical features (ecoregion, geology, huc2) -- KEPT
- Silently dropped in early versions due to a dtype bug. Fixing them improved Tier C R2(log) from 0.75 to 0.79.

---

## 5. Feature Removals

### 102 to 72 features (multi-phase ablation) -- KEPT at 72

Harmful features removed (all metrics improve when dropped):
- days_since_rain, manure_rate, do_instant, bio_n_fixation
- geo_na2o, geo_mgo, discharge_instant
- pct_glacial_lake_fine (+0.082 R2_native when dropped — helps log, destroys native)
- latitude (memorization risk)
- 30+ others from group-level and single-feature ablation

Key insight from ablation: **native-space effects 10-100x larger than log-space**. Features that look "helpful" in log-space can destroy native-space performance (e.g., rising_limb: +0.002 log, -0.075 native).

**KNOWN LIMITATION — Two ablation rounds used different standards:**
- **Round 1** (102→62→37, `reablation_62.py`): Sorted and verdicted by **R²(log) only**. R²(native) and KGE were captured but not used for decisions. This round produced the bulk of the drop list.
- **Round 2** (Phase 5, 83 experiments, `phase5_ablation.py`): Used R²(log), KGE, R²(native), RMSE, bias, and MedSiteR² — but still only **aggregate GKF5 metrics**. No disaggregated evaluation (physics, geology, collection method, extreme events).
- **Neither round used disaggregated metrics for feature decisions.** The 65 features on `optimized_drop_list.txt` were dropped before disaggregated evaluation existed. Some may matter for specific subgroups (extremes, first flush, specific geologies). The expert panel locked at 72 partly to stop this problem from getting worse, but never re-evaluated the already-dropped features.
- **Action item (post-v10):** Selectively re-test dropped features using disaggregated evaluation — especially event-dynamic features (turbidity_slope_1hr, turbidity_range_1hr, Q_30day_mean, days_since_rain) and interaction features (turb_Q_ratio, SC_turb_interaction) that might matter for extreme events or specific geologies even if aggregate metrics said "drop."

### Most impactful features in v9 (Phase 5 drop-one GKF5 screening):

| Feature dropped | dR2(native) | Role |
|----------------|-------------|------|
| turbidity_instant | -0.049 | Primary predictor |
| pct_alluvial_coastal | -0.028 | Geology |
| sgmc_sed_iron_formation | -0.026 | Geology |
| sgmc_igneous_intrusive | -0.022 | Geology |
| conductance_instant | -0.019 | Water chemistry proxy |

On holdout (from early-stopped models), turb_Q_ratio was the single most impactful feature (-0.10 holdout delta).

### Round 3 Group Ablation (GKF5, vault/holdout excluded)
- Compound drop of 12 harmful: +0.012 MedSiteR2
- Drop all SGMC: -0.007 (keep)
- Drop old geology: -0.004 (keep)
- Aggressive D2 subset: -0.024 (too aggressive)
- Final expert panel overruled individual drops: keep all 72.

---

## 6. Model Architecture

### CatBoost -- KEPT (production model)
- depth=6, lr=0.05, l2_reg=3, 500 iter max, early stopping, ordered boosting.
- Native categorical handling critical for collection_method (SHAP rank 3).
- No formal hyperparameter sweep on final config (expert panel recommended but deferred).

### Ridge linear -- BASELINE only
- Much worse than CatBoost under same LOGO CV. Used as comparison.

### GPBoost (LightGBM + random effects) -- DROPPED
- Holdout R2=0.145 (MODEL_VERSIONS says 0.145; one commit says 0.158 — evaluation path discrepancy).
- LightGBM trees too weak on this data. Mixed-effects framework is correct but base learner matters.

### MERF with CatBoost -- DROPPED
- Zero-shot holdout R2=0.417 (from site_adaptation.py eval path). Pooled R2=0.290, median site R2=0.357 (from direct LOGO eval).
- Lost categoricals (MERF requires numeric). collection_method SHAP rank 3 — losing it costs too much.

### Custom CatBoost-MERF EM loop -- DROPPED
- Holdout R2=0.144. EM loop corrupts fixed effects (training on y* = y - Zb makes the tree learn a different function). BCF inflated to 1.88.

### Two-stage slope prediction -- DROPPED
- Tried predicting per-site turb-SSC slopes from watershed features, then using predicted slopes.
- CV R2=-0.21. Watershed features cannot predict slopes.
- Site heterogeneity too high for this approach.

### Post-hoc Bayesian shrinkage -- KEPT (the breakthrough)
- Keep CatBoost untouched + post-hoc Bayesian adaptation from residuals.
- Fixes catastrophic small-N collapse. Principled shrinkage: N=1 trusts 10.7% of correction, N=20 trusts 70.5%.

### Multi-parameter models (TP, nitrate, orthophosphate) -- DROPPED
- SSC Tier C R2(log)=0.80; TP R2=0.62 (42 sites, collapsed to 0.08 at 72 sites); Nitrate R2=-0.72; OrthoP R2=-1.31.
- Dissolved species not predictable from turbidity. Only SSC remains.

---

## 7. Adaptation Method

### Old 2-parameter linear correction -- REPLACED
- N=1-5 HURTS (overfit). N=2: R2=-0.012 (catastrophic). No shrinkage.

### Bayesian Student-t shrinkage (k=15, df=4) -- KEPT

*Numbers from canonical site_adaptation_bayesian_summary.json (200 MC trials, 76 holdout sites):*

| N cal | Old 2-param R2 | Bayesian R2 | Delta |
|-------|---------------|------------|-------|
| 0 | 0.472 | 0.472 | 0 |
| 2 | -0.012 | 0.485 | **+0.497** |
| 5 | 0.388 | 0.463 | +0.076 |
| 10 | 0.487 | 0.504 | +0.016 |
| 20 | 0.487 | 0.509 | +0.022 |

Staged: intercept-only N<10, slope+intercept N>=10. Per-trial BCF shrunk toward 1.0.
Bayesian wins at EVERY N in EVERY split mode (random, temporal, seasonal). Temporal N=2: Bayesian +0.488 vs OLS -0.709 (delta +1.197).

### N=20 adaptation collapse -- IDENTIFIED
- 36% of N=20 draws contain zero storm samples (Monte Carlo by Ruiz).
- Baseflow-dominated calibration rotates relationship away from storm physics.
- Cap adaptation reporting at N=10.

---

## 8. Data Decisions

### NTU in training -- REJECTED (validation only)
- 89 USGS dual-sensor sites identified. 3,646 NTU-SSC pairs found.
- Zero temporal overlap: NTU=1976-2005, FNU=2006+. Sensor type perfectly confounded with era.
- No continuous NTU exists at USGS (by design since TM 2004.03 — continuous=FNU, discrete=NTU).
- Bayesian adaptation R2=0.43 at N=10 on foreign NTU is the correct path.
- Unanimous panel + Gemini.

### Data cleaning (135 records removed) -- KEPT
- Removed: SSC/turb ratio >200 or <0.01, turb<=0, SSC<=0.
- Includes obvious errors (SSC=70,000 at turb=260). Dataset: 35,209 to 35,074.
- Expert panels found 391-430 anomalous records; conservative threshold removed 135.

### Dropping noise sites -- REJECTED (critical finding)
- Dropping 15 worst noise sites: first flush R2 collapsed 0.905 to 0.264, extreme R2 collapsed 0.793 to -0.043. *(Note: absolute values from contaminated v9 holdout; the relative collapse is still valid.)*
- "Noise" sites carry extreme event signal. NEVER drop based on aggregate metrics.

### Collection method split training -- DROPPED
- Trained 7 specialist models (one per method). Every specialist worse than unified v4 on its own domain.
- depth_integrated is better data, but model knows this via the feature (SHAP rank 3). Splitting just loses sample count.

### 3-way split (284/76/36) -- KEPT
- Created after Krishnamurthy identified that 47+ ablation experiments on 76 holdout sites constitutes implicit overfitting.
- Vault: one-shot, never touched. Validation: tainted by development (historical reference only). Training: clean.

### Extreme data expansion (2026-04-01) -- KEPT
- **Sources:** (1) NWIS hotspots — queried NWIS for sites with SSC >10,000 mg/L; identified 19 sites, added 10 new extreme-event sites. (2) ScienceBase — Chester County PA, Klamath basin OR/CA, Arkansas River CO. (3) STN (Short-Term Network) — USGS flood event data.
- **New vault site:** USGS-09153270 (Cement Creek CO): 329 samples, max 121,000 mg/L — sealed as final exam site.
- **New holdout sites:** USGS-06902000 (Missouri R), USGS-07170000 (Kansas R).
- **Dataset after expansion:** 36,341 samples, 405 sites (was 35,074/396). Samples >=1000 mg/L: 2,549 (7.0%), >=5000: 312 (0.9%).
- **Extreme metric improvement:** Top 1% underprediction: -25% (from -28% in v10, -37% original).
- **Idaho/Palouse finding:** Uses acoustic backscatter (ADCP), not optical turbidity. No FNU data exists for this region. murkml's FNU-based model cannot be applied there.
- **WEPP integration:** Recorded as future investigation (advisor's area of work). Possible paths: WEPP outputs as features, murkml as WEPP emulator, hybrid event correction. Post-paper-2.

### Data expansion 266 to 396 sites -- KEPT
- Native R2 collapsed (0.361 to 0.154) but that was a loss function problem (log1p), not data quality.
- Triggered the transform investigation that led to Box-Cox.
- QC approval code mismatch ("A" vs "Approved") had wrongly rejected 139 sites.

### Site count sweet spot (~200)
- 194 good-quality sites: best per-site R2=0.293.
- 256 moderate: R2=0.294 (nearly identical).
- 287 all: R2=0.266 (slight degradation).
- 96 highest quality: R2=0.158 (not enough diversity).
- Pooled R2 and per-site R2 always tell opposite stories at every scale.

---

## 9. Training Strategy

### Monotone constraints -- KEPT (for Box-Cox only)
- +0.003 R2(log), all metrics consistent. Physics correct (turb up -> SSC up).
- HURTS with log1p (over-compression makes constraint redundant).

### Early stopping -- MANDATORY
- Without it: fake "flatline collapse" in ablation (Gemini caught this — 38 features all showed identical -0.22 drop).
- GroupShuffleSplit validation + early_stopping_rounds=50.

### Ordered boosting -- REPLACED by Plain boosting (v11)
- CatBoost's ordered boosting mode reduces overfitting in principle, but empirical comparison shows Plain boosting produces identical quality on this dataset.
- v11 trained in 47 minutes with Plain boosting vs ~3 hours with Ordered boosting. Quality unchanged.
- **Decision:** Use Plain boosting going forward. Ordered is wasteful here.

---

## 10. Evaluation Methodology

### Full eval suite -- MANDATORY (no exceptions)
- All split modes (random, temporal, seasonal), all metrics, disaggregated, physics, external.
- Lesson learned: "YOU'RE NOT LOOKING AT THE DISAGGREGATED STATISTICS."

### Key metric findings
- Pooled NSE=0.692 is misleading. Sample-weighted mean site R2=0.224.
- 28% of holdout sites have R2 < 0. Pooled and per-site metrics tell OPPOSITE stories.
- Holdout SSC/turb ratio systematically harder than training (2.17 vs 1.74, +25%).

### Conformal prediction intervals -- KEPT (empirical, not CQR)
- 95% coverage=96.1%, 90% coverage=91.7%. Well-calibrated.
- Median 90% interval width: 227 mg/L.

### CQR MultiQuantile -- FAILED, DROPPED (2026-04-01)
- **What:** Trained CatBoost MultiQuantile model (quantiles 0.05/0.50/0.95) under LOGO CV for conformalized quantile regression (Romano et al. 2019).
- **Training time:** 23 hours.
- **Result:** Conditional coverage disaster. Box-Cox lambda=0.2 compresses extreme values — Q95 in Box-Cox space back-transforms to values far below the true 95th percentile in SSC space. The compression prevents the quantile model from learning intervals that reach extreme SSC values (>5,000 mg/L).
- **Verdict:** CQR MultiQuantile is fundamentally incompatible with heavy-tailed SSC data under Box-Cox compression. Fall back to empirical conformal intervals using point predictions + conformity scores.

### USGS OLS head-to-head comparison -- KEPT
- At N=10 calibration: CatBoost wins 30/46 sites, OLS wins 16/46.
- agriculture_pct predicts where OLS wins (rho=-0.48, p=0.001). Simple ag sites don't need ML; complex/urban sites benefit.

### Catastrophic site classification
- 51 sites with LOGO R2 < -1. Only 7/51 genuinely wrong. 17 are low-signal (small SSC range, errors small in mg/L, R2 misleading). 27 mixed.
- R2 alone is misleading for flat sites.

### Instrument model differences -- NO EFFECT
- Kruskal-Wallis p=0.18 across sensor models. Only 21% of sites have identifiable instruments.
- turb_source SHAP=0.008 (low). No action needed.

---

## 11. External Validation

### 14-state SSC validation (early, pre-Box-Cox)
- 20 sites across 14 unseen states. Median R2=0.61, R2=0.79 with 50+ samples.
- Best: NY 0.90, MN 0.90, WA 0.87. Fails at arid (AZ) and small-sample sites.
- First evidence of cross-state transfer. Beats Song et al. 2024 PUB R2=0.55 (377 sites, no turbidity).

### 260 non-USGS NTU sites (v9) -- strongest evidence
- 11,026 samples from UMRR, SRBC, GLEC, UMC, MDNR, CEDEN. All NTU sensors.
- Zero-shot: Spearman=0.93, +57% bias, MAPE=90%, within-2x=55%.
- N=10 adaptation: R2=0.501 (matches USGS holdout). N=20: R2=0.554.
- Cross-network, cross-sensor, cross-decade generalization proven.
- UMRR (9,625 samples): Spearman=0.94, within-2x=61%. UMC (636 samples): Spearman=0.72, within-2x=2% (very low SSC sites, model way overpredicts).

---

## 12. Physics Findings (from diagnostics)

- **First flush:** ~~R2=0.864~~ **CONTAMINATED (v9 trained on holdout sites).** Honest v11 first-flush R²=0.285 (1,434 events), bias=-52%. The 0.864/0.907 was a train-set metric. v11 MAPE (45.9%) and within-2x (65.3%) are actually better than v9's (53.8%, 64.5%) despite much lower R², because v11's bcf_median reduces scatter.
- **Hysteresis:** 39.5% clockwise (proximal source), 24.4% CCW (distal), 36.1% linear across 119 ISCO events. Rising limb SSC/turb ratio 16% higher than falling.
- **Extreme events:** Top 1% R2=0.788 but -37% underprediction. Particle size shift at high SSC (coarse sediment adds mass without changing scattering).
- **Low-SSC overprediction:** 2.45x overprediction below 10 mg/L. Sensor contamination (DOM, algae) — not model failure.
- **Seasonal:** Spring R2=0.421 vs other seasons R2=0.700. Summer highest SSC/turb ratio (1.94 vs winter 1.73).
- **Power law slopes:** Median 0.952 (near linear), range 0.29-1.55. 50% steepen at high turbidity, 32% flatten. Geology predicts slope.
- **Sediment exhaustion:** 35% of burst events show declining ratio (classic supply exhaustion), 31% show increasing (new source mobilization).
- **Residuals strongly non-normal:** skew=2.0, kurtosis=13.8, 2% beyond 3-std (7x normal rate). This is WHY Student-t prior was chosen over Gaussian.
- **Error by SSC range:** Median abs error 9 mg/L at low SSC, 5,556 mg/L at extreme. Pct error best at 500-5000 mg/L (42%). Heteroscedastic.
- **Spatial autocorrelation:** Sites within 50km have 39% error difference vs 55% at distance (weak but present).
- **Residual autocorrelation:** Lag-1 up to 0.69 at individual sites. Effective sample sizes smaller than reported.
- **Drainage area predicts error:** rho=-0.375, p=0.004. Small basins 121% MAPE vs large 47%.
- **Missing features:** 79% missing pH, 78% missing DO, 68% missing conductance.
- **Burst pseudo-replicates:** 6.8% of samples within 5 minutes of another at same site.
- **Between-site variation 3.2x larger than within-site** (ratio CV 4.37 vs 1.35). Confirms site adaptation is the right approach.

---

## 13. Bugs That Changed the Project

| Bug | Impact | Fix |
|-----|--------|-----|
| prune_gagesii() double-pruning | ALL Tier C results invalid (trained on zeros) | Replaced with StreamCat |
| Timezone off by 5-8 hours | Alignment between sensor + grab samples wrong | Fixed; R2(log) improved 0.63 to 0.75 |
| Categorical features silently dropped | ecoregion, geology, huc2 not in model | Fixed dtype bug; R2(log) 0.75 to 0.79 |
| QC "A" vs "Approved" mismatch | 139 sites wrongly rejected | Normalized approval codes |
| hash() non-deterministic | Adaptation not reproducible | hashlib.md5() |
| Final model --boxcox-lambda ignored | Saved model used MLE lambda (-0.049) not 0.2 | Fixed lambda passthrough |
| Ablation without early stopping | Fake flatline collapse (38 features identical -0.22) | early_stopping_rounds=50 |
| Final model ignores --exclude-sites | v9 trained on holdout+vault (357 sites) | Auto-exclusion + hard guard |
| Model file overwriting | Lost model versions | Versioned names + git |
| Precip temporal leakage (Mar 28) | precip_24h/48h used future data | Added .shift(1) for strict antecedent *(Added 2026-03-31, from git forensics and expert review audit)* |
| Dedup key int64 mismatch (Mar 28) | Nanoseconds format mismatch causing phantom duplicates | Fixed key format *(Added 2026-03-31, from git forensics and expert review audit)* |
| Weather timezone strip (Mar 28) | Timezone not stripped before date comparison (distinct from Mar 16 discrete-sample tz bug) | Strip timezone before comparison *(Added 2026-03-31, from git forensics and expert review audit)* |
| QC vectorization bug (Mar 16) | Qualifier matching silently skipped ALL filtering — no QC was applied | Fixed vectorized matching *(Added 2026-03-31, from git forensics and expert review audit)* |
| Early-stop leakage (Mar 16) | Test data included in validation set during early stopping | Fixed split logic *(Added 2026-03-31, from git forensics and expert review audit)* |
| Seasonal split bug (Mar 31) | Seasonal split produced identical results to random split | Fixed split implementation *(Added 2026-03-31, from git forensics and expert review audit)* |
| BCF selection bug (Mar 31) | Wrong BCF applied in some evaluation paths | Fixed BCF dispatch *(Added 2026-03-31, from git forensics and expert review audit)* |
| Quantile column name bug (Mar 31) | q05 vs q05_ms mismatch silently skipped coverage stats | Fixed column naming *(Added 2026-03-31, from git forensics and expert review audit)* |
| Dedup policy divergence (Mar 31) | assemble_dataset.py uses old drop_duplicates while qc.py has new deduplicate_discrete() — new logic is unreachable dead code | Unresolved *(Added 2026-03-31, from git forensics and expert review audit)* |

---

## 14. Model Version Progression

| Version | Sites | Features | Transform | Best metric | What changed |
|---------|-------|----------|-----------|-------------|-------------|
| POC | 3 | ~10 | log1p | Per-site OLS R2=0.92 | Pipeline proof of concept |
| 17-site | 17 | ~20 | log1p | LOGO R2(log)=0.84 | First cross-site result |
| 57-site | 57 | ~30 | log1p | LOGO R2(log)=0.75 | Post-audit baseline (timezone fix) |
| v1 | 102 | 99 | log1p | R2(log)=0.721 | Expanded (GAGES-II broken — sensor-only in practice) |
| v2 | 243 | 37 | log1p | R2(nat)=0.361 | StreamCat, ablation, feature curation |
| v3 | 346 | 37 | log1p | R2(nat)=0.154 | Data expansion collapsed native R2 |
| v4 | 357 | 44 | Box-Cox 0.2 | Holdout=0.472 | Transform fix + monotone |
| v5 | 357 | 44 | log1p | Holdout=0.460 | Fair comparison (transform barely matters) |
| v6 | 287 | 41 | Box-Cox 0.2 | Holdout=0.417 | MERF (lost categoricals) |
| v8-gpb | 287 | 44 | Box-Cox 0.2 | Holdout=0.145 | GPBoost (too weak) |
| v8-merf | 287 | 44 | Box-Cox 0.2 | Holdout=0.144 | EM loop (corrupts FE) |
| v8-post | 357 | 44 | Box-Cox 0.2 | N=3 R2=0.485 | Post-hoc Bayesian (BREAKTHROUGH) |
| **v9** | **254** | **72** | **Box-Cox 0.2** | **MedSiteR2=0.486** | **SGMC, 3-way split, locked** |
| v9* | 357 | 72 | Box-Cox 0.2 | *(contaminated)* | v9 was trained on holdout+vault — all evals invalid |
| v10 | 254 | 72 | Box-Cox 0.2 | MedSiteR2=0.393, Spearman=0.873 | Clean data, dual BCF, proper exclusion (SUPERSEDED by v11) |
| **v11** | **260** | **72** | **Box-Cox 0.2** | **MedSiteR2=0.402, Spearman=0.907** | **Plain boosting, extreme data expansion, 485 trees (CURRENT BEST)** |

---

## 15. The Meta-Finding

**Site heterogeneity is THE problem.** No architecture change, feature engineering, data curation, or training strategy fixes cross-site variation. The between-site SSC/turb ratio CV is 4.37 vs within-site CV of 1.35 (3.2x). The only approach that works is site adaptation (Bayesian shrinkage). This is both the scientific finding and the product.

---

## 16. Investigated and Shelved

### Global post-processing calibration -- REJECTED (2026-04-01)
- **What:** Tested 8 methods to correct the systematic low-SSC overprediction and high-SSC underprediction simultaneously: (1) platt scaling, (2) isotonic regression, (3) piecewise linear correction, (4) log-space linear recalibration, (5) percentile matching, (6) quantile-based correction, (7) range-specific BCF, (8) two-parameter affine correction.
- **Result:** Fundamental tradeoff — fixing low-SSC overprediction worsens high-SSC underprediction (and vice versa). No global post-processing method can resolve both failure modes simultaneously.
- **Gemini consensus:** Don't do global calibration. Frame the model as a ranking engine (Spearman=0.907). Geology dictates scale (carbonate R²=0.807 vs volcanic R²=0.195). Bayesian site adaptation is the calibrator — it addresses scale per-site, which is the right level of granularity.
- **Verdict:** No global calibration. Dual BCF (median for predictions, mean for loads) is sufficient.

### Q90 quantile extreme-event specialist model -- SHELVED
- **What:** CatBoost with Quantile:alpha=0.90 loss as a second model for extreme events.
- **Red team verdict (Tanaka):** Shifts all predictions up uniformly (~40-60%), not selectively at extremes. Previous weight-scheme failures (tree collapse) are evidence that features lack extreme-event information — Q90 can't create information that isn't there. Evaluation metrics (R², RMSE) become meaningless for quantile predictions. Bayesian adaptation breaks (designed for mean residuals, not 90%-negative-by-design residuals). 149 extreme samples across 45 sites (~3/site) is insufficient for conditional quantile learning.
- **Verdict:** Shelved. The real fix is better features (event dynamics) or physics-based model integration, not a loss function change.

### WEPP integration -- FUTURE INVESTIGATION
- **What:** Combine murkml (data-driven ML) with WEPP (Water Erosion Prediction Project), a physically-based erosion model. Advisor's area of work.
- **Why:** Extreme underprediction is likely a feature deficiency — ML model lacks event-dynamic physics that WEPP simulates (hillslope sediment generation, runoff-erosion coupling).
- **Possible approaches:** WEPP outputs as CatBoost features, murkml as fast WEPP emulator, hybrid event magnitude correction.
- **Timeline:** Paper 2 or 3. Discuss with advisor first.

---

## 17. Scientific Discoveries (for paper)

*(Added 2026-03-31, from git forensics and expert review audit)*

1. **Dissolved vs. particulate boundary**: Particle-associated parameters (SSC R²=0.80, TP R²=0.62) transfer cross-site. Dissolved parameters (Nitrate R²=-0.72, OrthoP R²=-1.31) do not. Per-site OLS ceilings of 0.04 (nitrate) and 0.06 (orthoP) confirm this is a physics limit, not modeling failure. This is the primary paper finding.

2. **Nobody uses turbidity in large-scale ML models**: All published cross-site SSC/WQ models (Kratzert, Zhi, Song et al.) use hydromet + watershed attributes only. murkml's use of continuous turbidity is its primary competitive advantage.

3. **Song et al. 2024 is the primary benchmark**: 377 USGS sites, LSTM, PUB test median R²=0.55 (no turbidity). murkml R²=0.80 is +0.25 better. Most directly comparable published result.

4. **"Death of OLS" finding**: CatBoost with 1-parameter Bayesian adaptation using 2 grab samples (R²=0.48) outperforms USGS standard OLS using 50 grab samples (R²=0.40).

5. **Iowa River SSC/TP divergence**: SSC fails (R²=-0.50) while TP succeeds (R²=0.69) at the same loess-dominated site. Turbidity tracks the fine, P-bearing fraction better than total mass in loess systems (Jones et al. 2024). Publishable finding.

6. **GKF5 vs holdout disagreement**: Features neutral on GKF5 CV are critical for holdout generalization. turb_Q_ratio: +0.004 GKF5 vs -0.102 holdout. GKF5 folds lack sufficient geology/climate diversity. Major methodological finding.

7. **Collection method gap quantified**: Auto-point R²=0.377 vs depth-integrated R²=0.548 — a 0.17 gap reflecting vertical concentration gradients. Most operational sensors are fixed-point, meaning the model works worst on the most common deployment.

8. **Geology results match scattering theory**: Carbonate R²=0.823 (uniform optical properties), volcanic R²=0.326 (bimodal particles), unconsolidated R²=0.545.

---

## 18. Strategic Decisions

*(Added 2026-03-31, from git forensics and expert review audit)*

1. **"Stop improving, start writing" consensus (Mar 16-17)**: All 4 reviewers (Chen, Patel, Rivera, Okafor) independently recommended pulling publication forward. Patel: "A submitted R² of 0.80 is infinitely more valuable than an unsubmitted 0.83." Patel also noted: 36 review documents totaling ~40,000 words for ~2,000 lines of Python — marginal value of additional internal review is now zero.

2. **Three-paper publication strategy**: (1) Zenodo dataset deposit, (2) JOSS software paper (after 6-month review clock), (3) WRR research paper. Venue ranking: WRR first (values negative results), EMS second (software focus), HESS third.

3. **Paper framing**: "What transfers and what does not" — the particulate/dissolved boundary as the main finding. Negative results ARE the discussion section.

4. **Three-tier product output**: Screening Grade (zero-shot, widest CIs), Monitoring Grade (10+ calibration samples, medium CIs), Publication Grade (30+ samples matching USGS standards, tightest CIs).

5. **Physics panel 5-parameter suite (Mar 16)**: Confirmed SSC, TP, Nitrate+Nitrite, DO, TDS as the parameter suite. Excluded E. coli, metals, alkalinity, individual ions, BOD/COD. Species-level decisions: SSC never TSS (Gray et al. 2000), Nitrate+Nitrite not Total Nitrogen, TP primary / OrthoP secondary.

6. **Geographic bias in training set**: CA (60), OR (40), KS (33) = nearly 50% of candidates. Zero coverage of loess belt, iron range, arid Southwest, Gulf Coastal Plain, SE Piedmont. 35-site targeted gap-fill plan was designed (Vasquez & Rivera) but not yet executed.

7. **Torres regulatory positioning**: murkml is a screening tool, NOT compliance tool. Specific precision thresholds for each parameter. Trust barriers ranked: (1) black box, (2) uncalibrated uncertainty, (3) no institutional credibility, (4) "my watershed" skepticism, (5) tool complexity.

8. **Temporal stationarity testing missing**: No split-by-time validation, no year-over-year bias trends, no change-point detection, no sensor drift analysis. Required for operational deployment claims.

9. **Okafor's infrastructure gap analysis**: No config file, no data versioning/lineage, no pipeline orchestration (Makefile/DVC), no parameter-specific QC dispatch, no dataset manifest.

---

## 19. Project Inception (backfilled)

*(Added 2026-03-31, from git forensics and expert review audit)*

**Kansas Feasibility Test (Mar 15)**: 5 Kansas sites, 2,362 SSC samples, 92.6% match rate at ±15min alignment window. This test validated that the core concept — aligning discrete grab samples with continuous turbidity sensors — was feasible at scale. The high match rate proved the project was viable before any modeling began.

**17-site Cross-Site Transfer Proof (Mar 16)**: First evidence that a single CatBoost model (LOGO R²=0.84) could predict SSC across sites it had never seen. This was the publishable result that justified the entire project direction.
