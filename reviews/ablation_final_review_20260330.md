# Phase 5 Ablation Final Pre-Launch Review

**Date:** 2026-03-30
**Reviewer:** Claude Opus 4.6
**Files reviewed:**
- `scripts/phase5_ablation.py`
- `scripts/train_tiered.py` (model saving, label handling, n_jobs/threading)
- `data/optimized_drop_list.txt` (65 features)
- `data/results/models/ssc_C_sensor_basic_watershed_meta.json`

**Previous failures:** 4 (python path, --skip-save-model, filename collisions, meta.json corruption)

---

## Checklist Results

### 1. PYTHON path (line 34) -- PASS

```python
PYTHON = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")
```

Verified: `c:/Users/kaleb/Documents/murkml/.venv/Scripts/python.exe` **exists on disk**.

### 2. --skip-save-model -- WARNING (not a blocker, but costs time)

`--skip-save-model` is **NOT** in the subprocess command (lines 150-162). This is correct in that models WILL be saved.

**However:** This means every experiment trains a final full-data model AND saves it, in addition to the GKF5 cross-validation. This roughly doubles the time per experiment. For 83 experiments, that is significant.

**Each experiment will save a .cbm and _meta.json** -- which is fine for data preservation, but you probably only need the CV metrics from the ablation. Consider whether you actually want 83 saved models eating time.

**Recommendation:** Add `--skip-save-model` to the command to cut runtime nearly in half. You only need the CV metrics from stderr for the ablation analysis. The parquet captures everything you need.

**If you DO add --skip-save-model:** This was failure #2 last time. The difference is that last time it was accidentally included when you DID want models. This time, you genuinely only need CV metrics, so it is the correct flag for ablation.

### 3. Unique filenames -- PASS

In `train_tiered.py` lines 1261-1264:
```python
if args.label:
    model_path = model_dir / f"{param_name}_{safe_tier}_{args.label}.cbm"
```

And lines 1371-1374:
```python
if args.label:
    meta_path = model_dir / f"{param_name}_{safe_tier}_{args.label}_meta.json"
```

The ablation script always passes `--label` with unique values like `phase5_baseline`, `drop_turbidity_instant`, `add_ph_instant`, etc. Each experiment produces:
- `ssc_C_sensor_basic_watershed_{label}.cbm`
- `ssc_C_sensor_basic_watershed_{label}_meta.json`

**No collisions possible.** Each label is derived from a unique feature name.

### 4. Experiment count -- PASS (83 confirmed)

Verified by running the actual Python logic:
- **Meta features:** 41 numeric + 3 forced categoricals = 44
- **SGMC features:** 28 (no overlap with meta)
- **Total deduplicated:** 72
- **Drop list:** 65 features
- **Reintroduce candidates in drop list:** 10/10

**Total: 1 baseline + 72 drop-one + 10 reintroduce = 83 experiments**

### 5. Atomic parquet saves -- PASS

Lines 216-218 of `phase5_ablation.py`:
```python
tmp_path = OUTPUT_PATH.with_suffix(".tmp")
combined.to_parquet(tmp_path, index=False)
shutil.move(str(tmp_path), str(OUTPUT_PATH))
```

Write-to-temp then rename. Crash-safe. Checkpoint/resume logic loads existing results and skips completed labels.

### 6. Original v4 model protection -- PASS

Original model: `ssc_C_sensor_basic_watershed.cbm`
Ablation models: `ssc_C_sensor_basic_watershed_{label}.cbm`

The label is always set (never None) in the ablation script, so the non-labeled path (`ssc_C_sensor_basic_watershed.cbm`) is **never used**. Original model is safe.

### 7. CPU utilization -- SUBOPTIMAL

Current settings in ablation command (line 159):
```python
"--n-jobs", "8",
```

In `train_tiered.py` line 936:
```python
thread_count = max(cpu_count // n_jobs, 2)
```

With `os.cpu_count()` returning 32 (logical threads) on a 24-core/32-thread machine:
- **n_jobs = 8** (parallel GKF5 folds)
- **thread_count = 32 // 8 = 4** threads per CatBoost model
- **Total threads used: 8 x 4 = 32** -- fully utilizes logical threads

But GKF5 has only **5 folds**. With `n_jobs=8`, 5 folds are dispatched to 8 workers. Three workers sit idle. After the first 5 complete, there is nothing left. This wastes 3 worker slots.

**Optimal n_jobs for GKF5 on 24-core/32-thread:**
- `n_jobs=5` (one fold per worker, no waste)
- `thread_count = 32 // 5 = 6` threads per CatBoost model
- **Total: 5 x 6 = 30 threads** (94% utilization)
- Each CatBoost model gets 50% more threads (6 vs 4), which will speed up individual fold training

Alternatively:
- `n_jobs=4` would give `thread_count=8`, but leaves 1 fold waiting for a second batch
- `n_jobs=5` is the sweet spot

**Recommendation:** Change `--n-jobs` from `8` to `5`.

### 8. Additional Issues Found

#### 8a. STALE LOCK FILE EXISTS -- BLOCKER

**`data/results/phase5_ablation.lock` exists on disk.** The script will refuse to start:
```
Another instance is running (lock file exists). Exiting.
```

The lock file is checked at line 256. It only auto-clears after 12 hours (line 229). If it was created recently, **the script will exit immediately without running anything**.

**Action required:** Delete `data/results/phase5_ablation.lock` before launching.

#### 8b. cat_cols metadata mismatch -- LOW RISK

The meta.json shows `"cat_cols": []` (empty), but the ablation script forces 3 categorical features: `collection_method`, `turb_source`, `sensor_family`. In `train_tiered.py`, these are detected by dtype (`object`) at line 671, not from the meta.json. So the training pipeline handles them correctly regardless of what meta.json says.

The ablation's `get_current_features()` adds them to the feature list, so they get drop-one experiments. This is correct behavior.

#### 8c. --parallel flag is dead code -- LOW RISK

The `--parallel` argument is parsed but never used for actual parallelism. The experiments run sequentially. The only effect is on the time estimate display. Not a bug, but don't expect `--parallel 2` to help.

#### 8d. No checkpoint parquet exists -- CLEAN START

`data/results/phase5_ablation_screen.parquet` does not exist. This will be a fresh start with no skipped experiments.

#### 8e. Disk space -- PASS

~572KB per model x 83 = ~47MB. 112GB free on C:. No concern.

#### 8f. Timeout per experiment -- NEEDS ATTENTION

The timeout is 600 seconds (10 minutes) per experiment (line 145). With GKF5 and BoxCox, each experiment should take 3-5 minutes. The timeout is adequate but not generous. If a particular feature combination causes slow convergence, it could timeout.

**Recommendation:** Consider increasing to 900 seconds to be safe.

---

## Summary of Required Actions Before Launch

| # | Action | Severity |
|---|--------|----------|
| 1 | **Delete `data/results/phase5_ablation.lock`** | BLOCKER |
| 2 | Change `--n-jobs` from `8` to `5` | Performance (saves ~20% time per experiment) |
| 3 | Consider adding `--skip-save-model` | Performance (saves ~40% total runtime) |
| 4 | Consider increasing timeout from 600 to 900 | Safety margin |

## Verdict

**With the lock file deleted: READY TO LAUNCH.**

The four previous failure modes are all fixed:
1. Python path -- correct and verified
2. --skip-save-model -- not present (models will save; or add it intentionally to save time)
3. Filename collisions -- impossible; labels are unique per feature name
4. Meta.json corruption -- each experiment writes its own uniquely-named meta.json

The script will produce 83 experiments, save results atomically after each one, and resume from checkpoint if interrupted. The original v4 model is protected.

## Optimal Settings Recommendation

```python
# In phase5_ablation.py, line 159:
"--n-jobs", "5",          # was 8; matches GKF5 fold count exactly

# Optionally add to the command list (line 160):
"--skip-save-model",      # skip final model training; saves ~40% runtime
```

With `n_jobs=5` and `--skip-save-model`:
- Estimated time: ~83 experiments x 3 min = ~4.2 hours
- Without `--skip-save-model`: ~83 x 5 min = ~6.9 hours
