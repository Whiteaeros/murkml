# CLAUDE.md

## What This Project Is

`murkml` predicts suspended sediment concentration (SSC) in rivers using turbidity sensors and machine learning. The core innovation is **cross-site generalization**: one model trained on 357 USGS sites that works at new sites it's never seen, optionally improved with a handful of local grab samples via Bayesian shrinkage adaptation.

**Owner:** Kaleb — water science student, graduating mid-2026. Not on a deadline. Exploring what's possible, with eventual commercial product and paper goals.

## Current State (2026-03-30 evening)

**Current model: v9-final-72feat (BEST)**
- CatBoost, 254 training sites (284 train - 30 w/o StreamCat), 23,088 samples
- 72 features (69 numeric + 3 categorical: 44 original + 28 SGMC lithology)
- Box-Cox lambda=0.2, Snowdon BCF=1.390, monotone ON (turbidity_instant, turbidity_max_1hr)
- 3-way split: 284 train / 76 validation / 36 vault
- LOGO CV (254 folds): R²(log)=0.740, MedSiteR²=0.335, KGE=0.778
- Validation (76 sites): NSE=0.692, MedSiteR²=0.418, MAPE=55.6%
- **Vault (36 clean sites): MedSiteR²=0.486, MAPE=49.4%, Spearman=0.932**
- **External (260 NTU sites): 10 samples → R²=0.43, Spearman=0.93 zero-shot**
- Model: data/results/models/ssc_C_sensor_basic_watershed_v9_final_72feat.cbm

**Bayesian site adaptation (the killer feature):**
- Student-t shrinkage (k=15, df=4), staged: intercept-only N<10, slope+intercept N>=10
- Bayesian beats OLS at every N in every split mode
- External NTU data: 10 samples → R²=0.43 on foreign sensors/networks

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
- Site contribution analysis: 110 anchors, 110 noise, but noise sites are essential (keep all 284)

**Data state:**
- 396 total sites, 35,209 samples in paired dataset
- Collection methods: depth_integrated 15,381, auto_point 14,444, grab 4,638, unknown 746
- 28 SGMC watershed lithology features (355 sites with coverage)
- 260 external NTU validation sites (11K samples, 6 organizations)
- 65 features on drop list (`data/optimized_drop_list.txt`), always pass via `--drop-features`
- 3-way split: data/train_holdout_vault_split.parquet

**Completed phases:**
- Phase 3: Pipeline fixes (Gemini bugs, SGMC integration, collection methods, staged Bayesian)
- Phase 4: Diagnostics (disaggregated metrics, physics validation, external validation, eval refactor)
- Phase 5: Ablation (83 single-feature + group ablation + 5-seed stability → keep all 72)
- evaluate_model.py: staged Bayesian adaptation (Student-t, per-trial BCF shrunk toward 1.0)
- SGMC lithology: 28 watershed geology features integrated into train_tiered.py
- Collection methods: 5,536 unknown samples resolved via WQP metadata (unknown 6,282→746)

**What's next: Phase 4 — Diagnostic validation**
- Disaggregated metrics by collection method, geology, HUC2, SSC variability, sample count, sensor
- Physics-based validation: first flush, sediment exhaustion, hysteresis, snowmelt, extreme events
- Temporal stationarity, spatial LOO-CV, adversarial edge cases
- Then Phase 5: informed ablation using disaggregated diagnostics

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

6. TRAINING: CatBoost with Box-Cox lambda=0.2, monotone, Snowdon BCF
   Script: scripts/train_tiered.py
   Flags: --param ssc --tier C --transform boxcox --boxcox-lambda 0.2 --n-jobs 12
          --drop-features "$(cat data/optimized_drop_list.txt)"
   → data/results/models/ssc_*.cbm + *_meta.json

7. EVALUATION:
   → scripts/evaluate_model.py (canonical: holdout eval + adaptation curves, Bayesian/old_2param/ols)
   → scripts/site_adaptation_bayesian.py (Bayesian k-sweep with Student-t)
   → scripts/site_adaptation.py (older 2-param, random + temporal splits)
   → scripts/prediction_intervals.py (conformal intervals)
   → scripts/error_analysis.py (failure modes by site characteristics)
   → scripts/compare_vs_usgs.py (head-to-head vs USGS OLS)
```

## Key Files

| File | What it does |
|------|-------------|
| `scripts/train_tiered.py` | Main training. Key flags: `--cv-mode gkf5\|logo`, `--transform boxcox`, `--boxcox-lambda 0.2`, `--drop-features`, `--skip-ridge`, `--skip-save-model`, `--skip-shap`, `--n-jobs 12`, `--label`. |
| `scripts/evaluate_model.py` | Canonical holdout evaluation. Adaptation methods: bayesian (staged, Student-t), old_2param, ols. Flags: `--k 15`, `--df 4`, `--slope-k 10`, `--bcf-k-mult 3.0`. |
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
- Target: Box-Cox(SSC, lambda=0.2) with Snowdon BCF for back-transform
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

Direct HTTP to `waterservices.usgs.gov/nwis/iv/?format=rdb` is 70% smaller than JSON and much faster to parse. Use `requests.get()` with `parse_rdb()` from `scripts/download_gap_fill_fast.py`, NOT `dataretrieval.nwis.get_iv()` which downloads massive WaterML JSON blobs.

Pattern: 8 concurrent workers, one site per request, 2-year chunks, exponential backoff.
Reference implementation: `scripts/download_gap_fill_fast.py`

## Technical Notes

- **Python venv:** `.venv/Scripts/python` (Windows). UV-managed, cpython 3.12.9. **NOT base conda.**
- **Random seed:** 42 everywhere
- **Parallelization:** joblib with 12 workers (24-core i9)
- **CatBoost:** v1.2.10, Ordered boosting
- **Weather data format:** `data/weather/USGS_{site_no}/daily_weather.parquet`, cols: date, precip_mm, tmax_c, tmin_c, tmean_c
