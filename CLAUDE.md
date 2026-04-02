# CLAUDE.md

## What This Project Is

`murkml` predicts suspended sediment concentration (SSC) in rivers using turbidity sensors and machine learning. The core innovation is **cross-site generalization**: one model trained on 254 USGS sites that works at new sites it's never seen, optionally improved with a handful of local grab samples via Bayesian shrinkage adaptation.

**Owner:** Kaleb — water science student, graduating mid-2026. Not on a deadline. Exploring what's possible, with eventual commercial product and paper goals.

## Current State (2026-04-01)

**Current model: v11 (BEST — supersedes v10)**
- CatBoost, 260 training sites, 23,624 samples, 72 features (137 in tier, 65 dropped)
- Box-Cox lambda=0.2, **Plain boosting** (not Ordered), 485 trees
- BCF_mean=1.297 (for loads), BCF_median=0.975 (for individual predictions)
- Trained in 47 minutes (vs ~3 hrs for Ordered boosting — same quality, 1/4 the time)
- Dataset expanded: 36,341 total samples, 405 sites (was 35,074/396 in v10)
  - 10 new extreme-event sites from NWIS hotspots + ScienceBase
  - New vault: USGS-09153270 (Cement Creek CO, 329 samples, max 121,000 mg/L)
  - New holdout: USGS-06902000 (MO), USGS-07170000 (KS)
- Samples >=1000 mg/L: 2,549 (7.0%), >=5000: 312 (0.9%), max=121,000 mg/L
- Split: 291 train / 78 holdout / 37 vault

**v11 Holdout (78 sites, bcf_median):**
- MedSiteR²=0.402, MAPE=40.1%, Within-2x=70.0%, Spearman=0.907, Log-NSE=0.804, Bias=-36.6%

**v11 Adaptation:**
- N=10 random: MedSiteR²=0.493, MAPE=34.6%, Within-2x=76.5%
- N=10 temporal: MedSiteR²=0.389, MAPE=38.6%
- N=10 seasonal: MedSiteR²=0.431, MAPE=40.1%

**v11 Extreme metrics:**
- Top 1% underprediction: -25% (improved from -28% v10, -37% original)
- Top 5%: Within-2x=71.5%

**v11 Disaggregated:**
- Carbonate: R²=0.807, Volcanic: R²=0.195
- Depth-integrated: R²=0.321, Auto-point: R²=0.238
- SSC <50: R²=-60.6 (overpredicts), >5K: R²=-3.4 (underpredicts)

**OLS benchmark: CatBoost beats at every N** (N=2 temporal delta=+0.93)

**v11 Bootstrap CIs (95%, site-level blocking):** MedSiteR²=0.402 [0.358, 0.440], N=10 random: 0.493 [0.440, 0.547], KGE: 0.186 [0.078, 0.406], Spearman: 0.874 [0.836, 0.899]

**v10 superseded.** v10 was first honest model (254 sites, 22,995 samples). See MODEL_VERSIONS.md.
**NOTE:** v9 was contaminated — trained on 357 sites including 76 holdout + 36 vault. All v9 numbers are invalid.

**Bayesian site adaptation (the killer feature):**
- Student-t shrinkage (k=15, df=4), staged: intercept-only N<10, slope+intercept N>=10
- CatBoost beats OLS at every N (N=2 temporal: R²=0.36 vs OLS R²=-0.56)
- External NTU data: Spearman=0.927 zero-shot on foreign sensors/networks
- Global post-processing calibration tested (8 methods) — fundamental tradeoff: fixing low-SSC overprediction worsens high-SSC underprediction. No global fix possible.
- Gemini consensus: frame model as ranking engine (Spearman=0.907), geology dictates scale, Bayesian adaptation is the calibrator.

**Key findings from 100+ experiments:**
- Site heterogeneity is THE problem — no architecture change fixes it
- Site adaptation (Bayesian shrinkage) is the solution and the product
- Aggregate metrics lie — dropping weather improved median R² but destroyed first flush and extremes
- Feature ablation is in the noise floor — 72 vs 58 features statistically indistinguishable (p=0.81)
- CatBoost handles irrelevant features internally — no need to prune
- Low-SSC overprediction is sensor contamination (DOM, algae), not model failure
- Extreme underprediction is particle size shift, not just sensor saturation
- Model ranks correctly on foreign NTU data (Spearman 0.93) — adaptation just fixes the scale
- EVERY evaluation must use the full suite (all modes, disaggregated, physics, external)
- "Noise" training sites carry extreme event signal — dropping them destroys first flush and extreme predictions
- Site contribution analysis: 110 anchors, 110 noise, but noise sites are essential (keep all training sites)

**Data state:**
- 405 total sites, 36,341 samples in paired dataset (expanded from 396/35,074 in v10)
- 10 new extreme-event sites: NWIS hotspots (19 sites identified, 10 added), ScienceBase (Chester County PA, Klamath, Arkansas), STN flood events
- Collection methods: depth_integrated 15,381, auto_point 14,444, grab 4,638, unknown 746
- 28 SGMC watershed lithology features (355 sites with coverage)
- 260 external NTU validation sites (11K samples, 6 organizations)
- 65 features on drop list (`data/optimized_drop_list.txt`), always pass via `--drop-features`
- 3-way split: data/train_holdout_vault_split.parquet (291 train / 78 holdout / 37 vault; 135 anomalous records cleaned)
- New vault site: USGS-09153270 (Cement Creek CO, 329 samples, max 121,000 mg/L)
- New holdout sites: USGS-06902000 (MO), USGS-07170000 (KS)
- Idaho/Palouse: acoustic backscatter not optical turbidity — no FNU data exists there

**Completed phases:**
- Phase 3: Pipeline fixes (Gemini bugs, SGMC integration, collection methods, staged Bayesian)
- Phase 4: Diagnostics (disaggregated metrics, physics validation, external validation, eval refactor)
- Phase 5: Ablation (83 single-feature + group ablation + 5-seed stability → keep all 72)
- evaluate_model.py: staged Bayesian adaptation (Student-t, per-trial BCF shrunk toward 1.0)
- SGMC lithology: 28 watershed geology features integrated into train_tiered.py
- Collection methods: 5,536 unknown samples resolved via WQP metadata (unknown 6,282→746)
- CQR MultiQuantile: FAILED — Box-Cox compression prevents Q95 from reaching extreme values. Conditional coverage disaster. Fall back to empirical conformal intervals.
- Calibration experiment (8 global post-processing methods tested) — no global fix possible (fundamental tradeoff)
- Extreme data expansion: NWIS hotspots, ScienceBase, STN flood events
- Plain boosting adopted (same quality as Ordered, 1/4 the time)
- Empirical conformal prediction intervals (Mondrian, 5 predicted-SSC bins): 90% coverage achieved (90.6% holdout). Script: scripts/empirical_conformal_intervals.py. Results: data/results/evaluations/empirical_conformal/
- Log1p retest with expanded extreme data (GKF5): Box-Cox 0.2 confirmed as final transform. Log1p does NOT fix extremes (>5K bias nearly identical: log1p=-81%, box-cox=-83%).
- Dedup unified to deduplicate_discrete() from qc.py; 8 conflicting rows in v11 (0.02%)
- Predictions parquet overwrite bug fixed (label now in filename)
- v11 bootstrap CIs rerun with site-level blocking (tighter than v10 CIs)
- First-flush Spearman=0.902 confirmed on v11 holdout events

**What's next:**
- Paper writing (WRR target)
- Vault one-shot (37 sites, LAST — after paper methodology finalized)
- WEPP integration: future investigation (advisor's work, post-paper)

## How the Pipeline Works

```
1. DISCOVERY: Find USGS sites with SSC samples
   → data/all_discovered_sites.parquet (860 sites)

2. QUALIFICATION: Check which sites have turbidity + temporal overlap
   → data/qualified_sites.parquet (413 sites)
   → data/train_holdout_split.parquet (320 train / 76 holdout, 396-site version)

3. DOWNLOAD: Get continuous sensor data + discrete lab samples
   → data/continuous/{site}/{param}/*.parquet (15-min sensor readings)
   → data/discrete/{site}_ssc.parquet (grab samples)
   → data/weather/{site}/daily_weather.parquet (GridMET precip+temp)

4. ASSEMBLY: Align grab samples with sensor readings (±15 min, linear interpolation)
   Script: scripts/assemble_dataset.py
   → data/processed/turbidity_ssc_paired.parquet (396 sites, 35,209 samples)

5. ATTRIBUTES: Load watershed features
   Script: src/murkml/data/attributes.py (load_streamcat_attrs, build_feature_tiers)
   + SGMC lithology merged in train_tiered.py (~line 950)
   → Tier A: sensor-only (37 features, 396 sites)
   → Tier B: + basic attrs (42 features, 396 sites)
   → Tier C: + StreamCat + SGMC (137 features pre-drop, 72 post-drop, 357 sites)

6. TRAINING: CatBoost with Box-Cox lambda=0.2, monotone, Plain boosting, Dual BCF (mean for loads, median for predictions)
   Script: scripts/train_tiered.py
   Flags: --param ssc --tier C --transform boxcox --boxcox-lambda 0.2 --n-jobs 12
          --drop-features "$(cat data/optimized_drop_list.txt)"
          --boosting-type Plain  (Ordered is slow; Plain is equivalent for this dataset)
   → data/results/models/ssc_*.cbm + *_meta.json

7. EVALUATION:
   → scripts/evaluate_model.py (canonical: holdout eval + adaptation curves, Bayesian/old_2param/ols)
   → scripts/site_adaptation_bayesian.py (Bayesian k-sweep with Student-t)
   → scripts/site_adaptation.py (older 2-param, random + temporal splits)
   → scripts/empirical_conformal_intervals.py (Mondrian conformal intervals — 5 SSC bins, 90.6% holdout coverage)
   → scripts/prediction_intervals.py (legacy conformal intervals)
   → scripts/error_analysis.py (failure modes by site characteristics)
   → scripts/compare_vs_usgs.py (head-to-head vs USGS OLS)
```

## Key Files

| File | What it does |
|------|-------------|
| `scripts/train_tiered.py` | Main training. Key flags: `--cv-mode gkf5\|logo`, `--transform boxcox`, `--boxcox-lambda 0.2`, `--drop-features`, `--skip-ridge`, `--skip-save-model`, `--skip-shap`, `--n-jobs 12`, `--label`. |
| `scripts/evaluate_model.py` | Canonical holdout evaluation. Adaptation methods: bayesian (staged, Student-t), old_2param, ols. Flags: `--k 15`, `--df 4`, `--slope-k 10`, `--bcf-k-mult 3.0`, `--bcf-mode {mean,median}` (default: median). |
| `scripts/site_adaptation_bayesian.py` | Bayesian k-sweep with Student-t shrinkage. Reference implementation. |
| `scripts/ablation_matrix.py` | Automated ablation runner. Calls train_tiered.py as subprocess. |
| `scripts/assemble_dataset.py` | Builds paired dataset from continuous + discrete data. |
| `src/murkml/data/features.py` | Feature engineering: hydrograph, cross-sensor, seasonality, weather. |
| `src/murkml/data/attributes.py` | Loads StreamCat, builds feature tiers. `load_streamcat_attrs()`, `build_feature_tiers()`. |
| `src/murkml/evaluate/metrics.py` | All metrics: R², KGE, Duan BCF, Snowdon BCF, native-space metrics. |
| `src/murkml/data/qc.py` | QC filtering: approval status, qualifier parsing, ice/maint buffers. |
| `src/murkml/data/align.py` | Temporal alignment with linear interpolation. |

## Data Rules

- SSC only (param 80154), NOT TSS (00530) — different methods
- Turbidity FNU only (param 63680), NOT NTU (00076) — diverge above 400
- Target: Box-Cox(SSC, lambda=0.2) with Dual BCF (bcf_mean=1.297 for loads, bcf_median=0.975 for individual predictions) [v11 values]
- All timestamps UTC
- DO saturation: Benson & Krause (1984) polynomial ONLY — never linear approx
- QC qualifiers come as array strings `"['ICE' 'EQUIP']"` — must parse this format
- Report metrics in BOTH log-space and native-space (mg/L) — log-space flatters the model
- **NEVER overwrite model files** — version everything, commit immediately

## Watershed Attributes

**EPA StreamCat** — 781 sites, 69 static features after filtering. Loaded by `load_streamcat_attrs()`.

**SGMC Lithology** — 355 sites, 28 watershed geology percentage features. Loaded from `data/sgmc/sgmc_features_for_model.parquet`, merged in train_tiered.py. Categories include igneous, metamorphic, sedimentary, unconsolidated rock types.

**GAGES-II is legacy** — `prune_gagesii()` exists but is dead code. Don't use it.

## Lessons Learned (Things That Bit Us)

1. `prune_gagesii()` called on already-pruned data silently destroyed all attributes. **Always verify data contains expected values before training.**
2. USGS qualifier format `"['ICE' 'EQUIP']"` caused QC to silently skip all filtering. **Check exclusion counts.**
3. Log-space R²=0.71 looks good but native slope=0.19. **Always report native-space metrics.**
4. `huc2` column contains "unknown" strings that crash `.astype(int)`. `build_feature_tiers()` handles it.
5. Python `hash()` is non-deterministic since 3.3. Use `hashlib.md5()` for reproducible seeding.
6. Aggregate ablation hides subgroup effects. `rising_limb` looked harmful in log-space but was critical for native-space. **Judge features by disaggregated impact.**
7. `dataretrieval.nwis` module is deprecated. `waterdata` module uses the OGC API.
8. Model files got overwritten multiple times. **ALWAYS version model files, commit to git immediately.**

## Documentation Map

| File | Contents | Update when... |
|------|----------|----------------|
| `CLAUDE.md` | This file — project rules and current state | Architecture changes, new data rules, model numbers change |
| `MODEL_VERSIONS.md` | Single source of truth for all models and experiment results | New model trained or experiment completed |
| `EXPERIMENT_PLAN.md` | Experiment tracking with phases 3-5 | Experiment completed or plan changes |
| `RESULTS_LOG.md` | Detailed results with analysis | New training run or evaluation |
| `CHANGELOG.md` | History of changes by date | Significant feature, fix, or data change |
| `PIPELINE.md` | Data pipeline flow | Pipeline architecture changes |

## USGS Data Download — Use RDB Format

**Always use RDB format for USGS downloads, NOT JSON/WaterML.**

**Turbidity unit split (USGS TM 2004.03):** Continuous sondes = FNU (pCode 63680, ISO 7027 infrared). Discrete lab/field = NTU (pCode 00076, EPA 180.1 white light). No continuous NTU exists in NWIS — by design since 2004.

Direct HTTP to `waterservices.usgs.gov/nwis/iv/?format=rdb` is 70% smaller than JSON and much faster to parse. Use `requests.get()` with `parse_rdb()` from `scripts/download_gap_fill_fast.py`, NOT `dataretrieval.nwis.get_iv()` which downloads massive WaterML JSON blobs.

Pattern: 8 concurrent workers, one site per request, 2-year chunks, exponential backoff.
Reference implementation: `scripts/download_gap_fill_fast.py`

## Technical Notes

- **Python venv:** `.venv/Scripts/python` (Windows). UV-managed, cpython 3.12.9. **NOT base conda.**
- **Random seed:** 42 everywhere
- **Parallelization:** joblib with 12 workers (24-core i9)
- **CatBoost:** v1.2.10, Plain boosting (switched from Ordered in v11 — same quality, 1/4 the time)
- **Weather data format:** `data/weather/USGS_{site_no}/daily_weather.parquet`, cols: date, precip_mm, tmax_c, tmin_c, tmean_c
