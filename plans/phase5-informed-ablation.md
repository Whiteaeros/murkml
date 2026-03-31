# Phase 5: Informed Ablation — Detailed Plan

## Context

The model currently has 44 features (from the v4 meta.json) plus 28 SGMC lithology features merged at runtime = 72 total features in Tier C after dropping 65 from the optimized drop list. Phase 4 diagnostics revealed where the model works and fails. Now we use that information to make smart feature decisions — keep features that help difficult subgroups, drop features that add noise, and re-test previously dropped features that might help specific phenomena.

## Why Informed Ablation

Previous ablation (102→62→37→44) used aggregate R²(log) and R²(native) only. This missed critical subgroup effects:
- `rising_limb` looked "harmful" in log-space but was critical for native-space hysteresis
- SGMC features showed net flat on aggregate but might help metamorphic/volcanic sites specifically
- 7 features were added post-ablation without formal testing

Phase 4 gives us disaggregated diagnostics to evaluate features by their impact on:
- Extreme events (top 1-5% turbidity) — currently underpredicted by 37%
- Low SSC (<50 mg/L) — currently overpredicted by 121%
- Specific geologies (volcanic sites are hardest)
- Collection method subgroups
- First flush events
- Rising vs falling limb (hysteresis)

## Infrastructure

**Training:** `ablation_matrix.py` → calls `train_tiered.py` as subprocess with `--drop-features`
- GKF5 mode: ~4 min per experiment with 12 jobs
- Produces: R²(log), R²(native), KGE, alpha, RMSE, bias, BCF, trees

**Evaluation:** `evaluate_model.py` — the canonical evaluation script
- Requires a saved model (.cbm + _meta.json)
- Produces: 3 split modes, all metrics, baselines, bootstrap CIs, disaggregated diagnostics, external validation
- Takes ~1 min per model

**Problem:** GKF5 training doesn't save models by default (`--skip-save-model`). For disaggregated evaluation, we need the model. Two options:
- Option A: Run GKF5 without `--skip-save-model` for each ablation (saves model, takes same time, uses disk)
- Option B: Run GKF5 for aggregate screening, then only run full evaluate_model.py on promising candidates
- **Use Option B** — screen with aggregate GKF5 first, deep-evaluate only the features that matter

## Execution Plan

### Step 1: Establish the Baseline (1 run, ~5 min)

Train the current 72-feature model (44 original + 28 SGMC) with GKF5 AND save the model:

```bash
DROP_LIST=$(cat data/optimized_drop_list.txt)
.venv/Scripts/python scripts/train_tiered.py \
  --param ssc --tier C --cv-mode gkf5 --transform boxcox --boxcox-lambda 0.2 \
  --n-jobs 12 --label phase5_baseline --drop-features "$DROP_LIST"
```

Then run full evaluation:
```bash
.venv/Scripts/python scripts/evaluate_model.py \
  --model data/results/models/ssc_C_sensor_basic_watershed.cbm \
  --meta data/results/models/ssc_C_sensor_basic_watershed_meta.json \
  --label phase5_baseline --n-trials 50
```

This gives us baseline disaggregated metrics for every subgroup.

**Key files:**
- Model: `data/results/models/ssc_C_sensor_basic_watershed.cbm` (existing v4)
- Meta: `data/results/models/ssc_C_sensor_basic_watershed_meta.json`
- Drop list: `data/optimized_drop_list.txt` (65 features)
- SGMC: `data/sgmc/sgmc_features_for_model.parquet` (28 features, auto-merged)

### Step 2: Screen All 72 Features with GKF5 (72 runs, ~5 hrs)

For each of the 72 features currently in the model, drop it and run GKF5. This is the aggregate screening pass.

**The 72 features:**
- 41 numeric from v4: turbidity_instant, turbidity_max_1hr, turbidity_std_1hr, conductance_instant, temp_instant, sensor_offset, days_since_last_visit, discharge_slope_2hr, rising_limb, Q_7day_mean, turb_Q_ratio, DO_sat_departure, doy_sin, doy_cos, precip_48h, precip_7d, precip_30d, turb_below_detection, flush_intensity, longitude, drainage_area_km2, forest_pct, agriculture_pct, developed_pct, pct_carbonate_resid, pct_alluvial_coastal, pct_eolian_coarse, pct_eolian_fine, pct_colluvial_sediment, geo_fe2o3, clay_pct, sand_pct, soil_organic_matter, elevation_m, baseflow_index, wetness_index, dam_storage_density, wwtp_all_density, wwtp_minor_density, fertilizer_rate, nitrogen_surplus
- 3 categorical from v4: collection_method, turb_source, sensor_family
- 28 SGMC: sgmc_metamorphic_undiff, sgmc_metamorphic_amphibolite, ..., sgmc_water

For each: `DROP_LIST + ",feature_name"` → compare R²(log), R²(native), KGE, RMSE, bias to baseline.

**Output:** `data/results/phase5_ablation_screen.parquet` — one row per feature with delta metrics.

**Parallelization:** Can run multiple GKF5 experiments simultaneously. With 12 cores per run and 24 total cores, run 2 at a time. 72 features / 2 parallel = 36 sequential runs × ~4 min = ~2.5 hrs.

**Script:** Modify `ablation_matrix.py` or write `scripts/phase5_ablation.py` that:
1. Reads the current feature list from the model meta
2. For each feature, runs GKF5 with that feature added to the drop list
3. Parses metrics, saves incrementally to parquet (crash-safe)
4. Prints summary table sorted by impact

### Step 3: Screen Re-introduced Features (9 runs, ~40 min)

For each of the 9 previously dropped physics-plausible features, REMOVE it from the drop list and run GKF5. This tests whether adding it back helps.

**The 9 candidates:**
1. `ph_instant` — was "very helpful" in original ablation; carbonate/non-carbonate geology
2. `discharge_instant` — raw discharge for extreme event detection
3. `precip_24h` — shorter window for first-flush timing
4. `temp_at_sample` — temperature affects sediment transport + snowmelt
5. `temp_mean_c` — mean climate temperature
6. `slope_pct` — watershed steepness drives erosion
7. `soil_erodibility` — how easily soil erodes
8. `do_instant` — dissolved oxygen tracks flow conditions
9. `soil_permeability` — runoff vs infiltration partitioning
10. `water_table_depth` — shallow = faster runoff

For each: `DROP_LIST minus "feature_name"` → compare to baseline.

**Output:** Appended to same `phase5_ablation_screen.parquet`.

### Step 4: Identify Candidates for Deep Evaluation (analysis, ~10 min)

From the screening results, identify:
- **Clearly harmful** (R²_native drops >0.005 when present): mark for dropping
- **Clearly helpful** (R²_native improves >0.005 when present): mark for keeping
- **Ambiguous** (delta within ±0.005): these need disaggregated evaluation

Expect ~10-20 ambiguous features that need the deep evaluation.

### Step 5: Deep Disaggregated Evaluation of Ambiguous Features (~10-20 runs, ~2 hrs)

For each ambiguous feature, train a model WITH and WITHOUT it (GKF5 with model save), then run the full `evaluate_model.py` on each. Compare disaggregated metrics:

For each ambiguous feature, check:
- Does it help extreme events (top 5% turbidity)? → compare MAPE/bias at high turb
- Does it help first flush events? → compare flush vs normal R²
- Does it help specific geologies? → compare by dominant lithology
- Does it help specific collection methods? → compare by method
- Does the SHAP direction match physics?

**Decision rule:**
- If a feature helps ANY important subgroup by >0.03 R² without hurting others by >0.02: KEEP
- If a feature hurts the worst-performing subgroups: DROP regardless of aggregate
- If a feature is a wash everywhere: DROP (simpler model is better)

### Step 6: Expert Panel Review (3 agents)

Give the panel:
- Full ablation screening table (72 + 9 features, aggregate deltas)
- Deep evaluation results for ambiguous features (disaggregated deltas)
- SHAP direction analysis for kept features

Panel decides the final feature set. Same experts: Rivera (operations), Krishnamurthy (statistics), Ruiz (physics).

### Step 7: Retrain Final Model

Train the winning feature set with:
- GKF5 first for quick validation
- Then full LOGO CV for reportable numbers (only if GKF5 looks good)
- Save model with versioned name (e.g., `ssc_C_v9_ablated.cbm`)
- Run full evaluate_model.py (all modes, all diagnostics, external validation)

### Step 8: Compare to v4

Side-by-side comparison:
- v4 (72 features) vs v9 (N features) across all metrics and all subgroups
- Did we improve the weak spots (low SSC, volcanic sites, extreme events)?
- Did we maintain the strong spots (first flush, hysteresis, carbonate sites)?
- Update MODEL_VERSIONS.md, EXPERIMENT_PLAN.md

## Compute Budget

| Step | Runs | Time/run | Total | Parallel |
|---|---|---|---|---|
| 1. Baseline | 1 + eval | 5 + 1 min | 6 min | — |
| 2. Screen 72 features | 72 | 4 min | 288 min | 2 parallel → 144 min |
| 3. Screen 9 re-introduced | 9 | 4 min | 36 min | 2 parallel → 18 min |
| 4. Analysis | — | — | 10 min | — |
| 5. Deep eval (~15) | 30 (with/without) + evals | 5 min | 150 min | 2 parallel → 75 min |
| 6. Panel | 3 agents | — | ~10 min | parallel |
| 7. Retrain final | 1 GKF5 + 1 LOGO + eval | 5 + 210 + 1 min | 216 min | — |
| **Total** | | | **~8 hrs** | **~4.5 hrs with parallelism** |

Most of the time is Step 7 (LOGO CV). Steps 2-3 screening is the bulk of the parallelizable work.

## Key Files

| File | Role |
|---|---|
| `scripts/phase5_ablation.py` | NEW — automated screening runner |
| `scripts/ablation_matrix.py` | Existing — reference for subprocess pattern |
| `scripts/evaluate_model.py` | Deep evaluation with disaggregated metrics |
| `scripts/train_tiered.py` | Training with --drop-features |
| `data/optimized_drop_list.txt` | Current 65-feature drop list |
| `data/sgmc/sgmc_features_for_model.parquet` | 28 SGMC features |
| `data/results/phase5_ablation_screen.parquet` | Screening results |
| `data/results/phase5_deep_eval/` | Deep evaluation outputs |

## Decision Framework (from master plan)

For each feature, the question is NOT "does it improve average R²" but:
1. Does it improve predictions for the cases we care about most (extreme events, first flush, difficult sites)?
2. Does dropping it cause any subgroup to degrade by more than 0.05 R²?
3. Does the SHAP direction match expected physics?
4. Is the feature available at deployment time for new sites?

## Reliability Requirements

The ablation runner (`scripts/phase5_ablation.py`) MUST:

1. **Save after every experiment.** After each GKF5 run completes (success or failure), append the result row to `data/results/phase5_ablation_screen.parquet` immediately. Never accumulate results only in memory.

2. **Resume from checkpoint.** On startup, read the existing parquet file. Skip any feature labels that already have a result row. If the script crashes at feature #45 of 72, re-running starts at #46 automatically.

3. **Never silently fail.** If a training subprocess fails:
   - Log the FULL stderr (not truncated)
   - Write a result row with `status="FAILED"` and `error_msg=<the error>`
   - Continue to the next feature
   - At the end, print a summary of failures

4. **Lock file for concurrent safety.** If two instances accidentally run, the second should detect the lock and exit with a clear message. Use a simple `.lock` file in the output directory.

5. **Validate inputs before starting.** Check that:
   - The model file exists
   - The meta JSON exists and is valid
   - The drop list file exists
   - The SGMC feature file exists
   - train_tiered.py is importable / runnable
   - Print the total experiment count and estimated time before starting

6. **Atomic writes.** Write to a temp file, then rename to the final parquet path. This prevents a crash during write from corrupting the results file.

7. **Progress logging.** After each experiment, log: `[N/total] feature_name: R²_native=X.XXX (delta=±X.XXX) — Xs`

## Step 9: Site Contribution Analysis (after ablation, before final retrain)

### Context
The previous anchor analysis (50 sites beat 287 on per-site R²) used holdout performance to select training sites = data leakage (Gemini flagged). Need a clean version that never sees holdout data.

### Method: Random Subset Scoring with GKF5 CV Only

Same approach as the original anchor analysis, but score by GKF5 cross-validation performance instead of holdout R². The holdout set is never involved in site selection.

**Protocol:**
1. Generate 20 random subsets of 100 training sites each (stratified by HUC2 + collection method to maintain representativeness)
2. For each subset: train a GKF5 model, record R²(native) CV performance
3. For each of the 357 training sites: compute how many of the subsets that included it performed above-median ("win rate")
4. Anchor score = (win rate) - (expected win rate based on inclusion frequency)
5. Rank sites by anchor score: positive = site helps generalization, negative = site adds noise

**Why GKF5 not holdout:**
- GKF5 CV evaluates on held-out folds of the TRAINING data only
- No holdout sites are ever used for evaluation
- This measures "does this site help the model generalize to other training sites"
- Holdout sites remain completely sequestered for final evaluation

**Compute:** 20 subsets × ~4 min GKF5 = ~80 min. Parallelizable (2 at a time = ~40 min).

**Output:**
- `data/results/phase5_site_scores.parquet` — per-site anchor scores, win rates, appearance counts
- `data/results/phase5_site_scores_summary.json` — top 20 anchors, bottom 20 noise sites, distribution stats

**Reliability:**
- Same crash-safe approach as feature ablation — save after each subset run
- Resume from checkpoint if interrupted
- Record which random seeds were used for reproducibility

**Integration with Feature Ablation:**
- Run AFTER the feature set is finalized (Step 7)
- Use the winning feature set for all 20 subset runs
- If clear noise sites are identified, test training WITHOUT them as a final experiment
- Save anchor model with versioned name if it beats the full-site model

**Analysis:**
- Do anchor sites correlate with any site characteristic? (geology, collection method, SSC variability, HUC2)
- Do noise sites overlap with the 51 "catastrophic" sites from Task #10?
- Does the anchor model improve specific subgroups (disaggregated eval)?

### What NOT to Report
- Do NOT report anchor model performance on the 76 holdout sites as a "clean" result unless the anchor selection used zero holdout information (which it does under this protocol)
- The previous anchor-50 result (R²=0.367) is INVALIDATED due to data leakage
- New results can be reported because site selection uses GKF5 CV only

## What NOT to Do

- Don't change the training data or holdout split during ablation
- Don't change the transform (Box-Cox 0.2) or monotone constraints
- Don't bundle feature changes — one at a time
- Don't skip the deep evaluation for ambiguous features
- Don't overwrite any model files
