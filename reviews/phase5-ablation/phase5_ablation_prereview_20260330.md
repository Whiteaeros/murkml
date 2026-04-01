# Phase 5 Ablation Script Pre-Run Review

**Date:** 2026-03-30
**Reviewed by:** Claude Opus 4.6
**Files reviewed:**
- `C:\Users\kaleb\.claude\plans\phase5-informed-ablation.md`
- `scripts/phase5_ablation.py`
- `scripts/train_tiered.py` (CLI args, SGMC merge, drop-features logic, output format)
- `data/results/models/ssc_C_sensor_basic_watershed_meta.json`
- `data/optimized_drop_list.txt`
- `data/sgmc/sgmc_features_for_model.parquet`

---

## CRITICAL BUGS (will crash the run)

### BUG 1: Python path validation fails on Windows

**Location:** `phase5_ablation.py` line 34 + line 270

The script sets:
```python
PYTHON = str(PROJECT_ROOT / ".venv" / "Scripts" / "python")
```

Then validates:
```python
assert Path(PYTHON).exists(), f"Python not found: {PYTHON}"
```

On Windows, `Path(".venv/Scripts/python").exists()` returns **False** because the actual file is `python.exe`. The `subprocess.run()` call would work fine (Windows CreateProcess auto-appends `.exe`), but the **assertion on line 270 kills the script before it ever gets there**.

Verified empirically:
```
>>> Path('.venv/Scripts/python').exists()    # False
>>> Path('.venv/Scripts/python.exe').exists() # True
>>> subprocess.run(['.venv/Scripts/python', '--version'])  # Works (CreateProcess magic)
```

**Fix:** Change line 34:
```python
# Before
PYTHON = str(PROJECT_ROOT / ".venv" / "Scripts" / "python")

# After
PYTHON = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")
```

**Severity:** BLOCKER. Script exits immediately on startup.

---

## SIGNIFICANT ISSUES (won't crash but will produce wrong/confusing results)

### ISSUE 2: Baseline will NOT reproduce v4 numbers

The current v4 model (`ssc_C_sensor_basic_watershed_meta.json`) was trained with **44 features and zero SGMC features**. No SGMC columns appear in `feature_cols`.

However, `train_tiered.py` now auto-merges SGMC features at line 952-958:
```python
if sgmc_path.exists() and watershed_attrs is not None:
    sgmc = pd.read_parquet(sgmc_path)
    watershed_attrs = watershed_attrs.merge(sgmc, on="site_id", how="left")
```

This means the baseline experiment (`phase5_baseline`) will train with **72 features** (44 original + 28 SGMC), not the 44 that produced v4. The baseline numbers will differ from v4.

**This is actually correct behavior** -- the ablation is screening the 72-feature model, not reproducing v4. But you should be aware:
- The "baseline" in `phase5_ablation_screen.parquet` is the 72-feature model, not v4
- Delta metrics are relative to this 72-feature baseline
- To compare final results back to v4, you'll need a separate comparison (Step 8 in the plan covers this)

**Action:** No code change needed, but label this clearly. Consider logging a warning like "Baseline includes 28 SGMC features not in v4 meta" so you don't confuse yourself later.

### ISSUE 3: Plan says "9 candidates" but lists 10; code has 10

The plan header at line 90 says "9 previously dropped physics-plausible features" but then lists 10 items (numbered 1-10, ending with `water_table_depth`). The code's `REINTRODUCE_CANDIDATES` list correctly has all 10. Total experiments = 1 baseline + 72 drop + 10 reintroduce = **83**, not the 82 implied by "72 + 9 + 1".

**Action:** Fix the plan text if you care about accuracy. Code is correct.

### ISSUE 4: `--parallel` flag is a no-op

The `--parallel` argument is declared at line 246 and used only for the time estimate at line 330. The actual execution loop (line 344) is purely sequential. The docstring at line 11 says `--parallel 2 # run 2 experiments at a time`, which is misleading.

Running 83 experiments sequentially at ~4 min each = **~5.5 hours**. With `--parallel 2` the user would expect ~2.75 hours but would still get 5.5 hours.

**Action:** Either implement parallelism (use `concurrent.futures.ProcessPoolExecutor`) or remove the `--parallel` flag and update the docstring to avoid confusion. For an overnight run, sequential is fine -- just don't promise parallelism.

### ISSUE 5: SGMC feature names in the plan don't match actual column names

The plan (line 74) references `sgmc_metamorphic_undiff` as an example SGMC feature. The actual column names use full words:
- `sgmc_metamorphic_undifferentiated` (not `sgmc_metamorphic_undiff`)
- `sgmc_igneous_metamorphic_undifferentiated`
- etc.

This is only a plan documentation issue -- the code reads names from the parquet file directly, so it uses the correct names. But if anyone manually edits the drop list referencing plan names, they'd get the wrong feature names.

**Action:** No code change needed. Plan text is just shorthand.

---

## VERIFIED CORRECT

### Check 2: Feature list correctness -- PASS

The `--drop-features` flag in `train_tiered.py` operates on the **full Tier C feature set** (all columns available after merging sensor + basic + StreamCat + SGMC), not on the meta's stored `feature_cols`. At line 681-685:
```python
if drop_features:
    all_available = [c for c in all_available if c not in drop_features]
```

This means:
- Drop experiments: `base_drop_list (65) + [one_feature]` = 66 drops from ~137 total = 71 active features. Correct.
- Reintroduce experiments: `base_drop_list minus one` = 64 drops from ~137 total = 73 active features. Correct.
- Baseline: `base_drop_list (65)` drops from ~137 = 72 active features. Correct.

### Check 3: SGMC feature names exist in merged data -- PASS

SGMC features are merged into `watershed_attrs` at line 956 of `train_tiered.py`. The merge is `on="site_id", how="left"`, so SGMC column names appear verbatim in the Tier C data. The ablation script reads SGMC names from the parquet file (`get_sgmc_features()`), so names always match.

Verified: 28 SGMC features, no overlap with the 44 meta features, no overlap with the 65 drop list features.

### Check 4: Drop list mechanics -- PASS

- **Drop experiments:** `base_drop_list + [feat]` correctly adds one feature to the drop list. Since the 44 meta features are NOT on the base drop list (verified), adding one of them to the list will cause it to be dropped.
- **Reintroduce experiments:** `[f for f in base_drop_list if f != feat]` correctly removes one feature. All 10 candidates are confirmed present in the drop list.
- Both produce the right `--drop-features` comma-separated string via `",".join(drop_features)`.

### Check 6: Output parsing -- PASS (with caveat)

The `parse_train_output()` function parses stderr from `train_tiered.py`. The actual output format (line 1044-1049) is:
```
    R²(log)=0.815  KGE(log)=0.890  alpha=1.020  |  R²(mg/L)=0.370  RMSE(mg/L)=567.1  Bias=-2.3%  BCF=1.364
```

The parser correctly handles:
- The Unicode `²` character (checks both `\u00b2` and literal `²`)
- The `|` delimiter (splits on `|` then on whitespace)
- The `%` suffix on Bias (strips with `rstrip("%")`)
- The `Trees per fold: median=X, min=X, max=X` line

Verified that `subprocess.run(..., text=True)` preserves the Unicode `²` character on this Windows system.

### Check 7: Resume logic -- PASS

On startup, the script:
1. Loads existing parquet at line 198-201
2. Builds `completed_labels` set at line 321
3. Filters remaining experiments at line 322: `[e for e in experiments if e["label"] not in completed_labels]`
4. Numbering accounts for completed: `n_done = len(completed_labels)` at line 345

If the script crashes after 40 experiments, re-running starts at #41. The label-based matching is correct since labels are deterministic (`"drop_{feature_name}"` or `"add_{feature_name}"`).

### Check 9: Atomic writes on Windows -- PASS

`shutil.move()` from `.tmp` to `.parquet` on the same drive works correctly on Windows, including the overwrite case. Verified empirically on this system.

### Check 8: Lock file staleness -- ACCEPTABLE

The 6-hour stale lock timeout provides a 30-minute margin over the estimated 5.5-hour runtime (sequential). If using `--parallel 2` (which currently doesn't work anyway), the runtime would be ~2.75 hours, giving a huge margin. The lock is adequate.

One minor concern: the lock check at line 220-228 has a TOCTOU race (check-then-write), but since this is a single-user machine, it's not a practical concern.

---

## MINOR ISSUES

### MINOR 1: Feature count logging may confuse

At line 277, the script logs `Current model features: 44` and at line 278 `SGMC features: 28`, then at line 282 `Total features to screen: 72`. But it then also screens the baseline, making total experiments 73 (72 + baseline) before adding reintroduce. The "72" is the number of drop-one experiments, not total experiments. This is fine but could be clearer.

### MINOR 2: Error message truncation

At line 168, failed experiment errors are truncated to 2000 chars: `result.stderr[-2000:]`. At line 354, the warning further truncates to 200 chars. For debugging a failure, the full stderr is only saved in the parquet (2000 chars). If a failure is caused by an import error or data issue, 2000 chars should be enough, but consider saving the full stderr for the first failure.

### MINOR 3: No disk space check

83 experiments, each saving an incrementally larger parquet file (plus a .tmp file during writes). The parquet will be tiny (83 rows), so this is not a real concern. But the train_tiered.py subprocess may consume memory/temp space. Not a practical issue.

---

## SUMMARY OF REQUIRED FIXES

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | **BLOCKER** | `Path(".venv/Scripts/python").exists()` returns False on Windows | Change line 34 to `".venv" / "Scripts" / "python.exe"` |
| 2 | Note | Baseline differs from v4 (includes SGMC) | No code fix; just be aware |
| 3 | Low | Plan says 9 candidates, code has 10 | Fix plan text |
| 4 | Medium | `--parallel` flag is a no-op | Remove flag or implement; update docstring |

**After fixing Bug 1, the script should run correctly overnight.** The core logic (drop list manipulation, output parsing, resume, atomic writes, lock file) is all sound.

### Recommended command to start the run:

```bash
cd c:\Users\kaleb\Documents\murkml
.venv\Scripts\python.exe scripts\phase5_ablation.py --mode both 2>&1 | tee data/results/phase5_ablation.log
```

Using `tee` captures the full log in case you need to debug later. Estimated runtime: ~5.5 hours sequential.
