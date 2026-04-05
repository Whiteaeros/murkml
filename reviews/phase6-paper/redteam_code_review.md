# Red-Team Code Review: Phase 6 Scripts

**Reviewer:** Claude (red-team audit)  
**Date:** 2026-04-02  
**Scope:** evaluate_model.py partition flag, prior_sensitivity.py, hp_sensitivity_sweep.py, model integrity, vault evaluation output

---

## 1. evaluate_model.py -- Partition Flag

### 1.1 Partition filter: PASS
The `--partition` argument (line 1061-1063) is correctly wired through. `load_holdout_data()` receives it at line 1114 and uses it to filter the split file at line 119:
```python
holdout_ids = set(split[split["role"] == partition]["site_id"])
```
This correctly reads from `train_holdout_vault_split.parquet` (3-way split) when it exists, falling back to the 2-way split. The filter is applied before any feature merging, so vault sites get the same feature pipeline as holdout sites. No issues found.

### 1.2 MIN_HOLDOUT assertions: PASS (with note)
Lines 152-160 handle vault correctly:
- `MIN_HOLDOUT_SITES` (20) is applied to BOTH partitions -- vault has 37 sites, so this passes.
- `MIN_HOLDOUT_SAMPLES` (500) is relaxed to 100 for vault partition. Vault has 4054 samples, so this easily passes.

**Note:** The `MIN_HOLDOUT_SITES` threshold name is slightly misleading when used for vault (it's a holdout-named constant applied to vault), but functionally correct. Not a bug, just a naming nit.

### 1.3 Output JSON partition label: PASS
Line 936 dynamically labels the partition:
```python
"partition": args.partition,
```
And lines 945-946 use f-strings to create partition-specific keys:
```python
f"{args.partition}_sites": int(readings["site_id"].nunique()),
f"{args.partition}_samples": len(readings),
```
Confirmed in the vault output: `"partition": "vault"`, `"vault_sites": 37`, `"vault_samples": 4054`. Correct.

### 1.4 Risk of model/training data modification: PASS
- The model is loaded read-only (`model.load_model()` at line 1103), never saved back.
- No `model.fit()` or `model.save_model()` calls exist anywhere in the script.
- The training data is never loaded; only the partition (holdout/vault) data is loaded.
- `predict_holdout()` creates a new result DataFrame from predictions; the input holdout DataFrame is not written back.

### 1.5 Log messages: PASS
Line 1088 correctly logs `args.partition`. Line 121 uses `partition.title()` for the filter log line. All accurate.

### 1.6 Minor observations (non-blocking)
- Line 288: `corrected_ms = a * y_pred_ms + b` in `adapt_old_2param` applies the correction to ALL samples (not just test), then indexes into test at line 299. This is harmless (the cal indices are never used downstream from the full-array result), but wasteful. Not a bug.

---

## 2. prior_sensitivity.py -- CRITICAL BUG

### 2.1 JSON path mismatch: BUG (CRITICAL)

**Line 49:**
```python
curves = s.get("adaptation_curves", {}).get("random", {})
```

**Actual JSON structure (from vault eval and all evaluate_model.py outputs):**
```json
{
  "adaptation": {
    "random": {
      "curve": {
        "10": { "median_r2": 0.483, ... }
      }
    }
  }
}
```

The correct path should be:
```python
curves = s.get("adaptation", {}).get("random", {}).get("curve", {})
```

The key `"adaptation_curves"` does not exist in any summary JSON produced by `evaluate_model.py`. The `.get()` silently returns `{}`, so `n10` becomes `{}`, and `med_r2` becomes `"?"` for every single experiment. **All 9 sensitivity experiments will run to completion but report `"?"` for every result.** The final JSON output will contain `{"med_site_r2_n10": "?"}` for all grid points.

### 2.2 Metric key mismatch: BUG (CRITICAL, same root cause)

**Line 51:**
```python
med_r2 = n10.get("median_site_r2", "?")
```

The actual key in the summary JSON is `"median_r2"`, not `"median_site_r2"`. Even if the path in 2.1 were fixed, this would still return `"?"`.

**Fix for both:** Replace lines 49-51 with:
```python
curves = s.get("adaptation", {}).get("random", {}).get("curve", {})
n10 = curves.get("10", {})
med_r2 = n10.get("median_r2", "?")
```

### 2.3 Risk of model modification: PASS
The script only calls `evaluate_model.py` via subprocess. It never loads the model directly. The MODEL and META paths are passed as `--model` and `--meta` arguments to evaluate_model.py, which loads them read-only (verified above).

### 2.4 Label uniqueness: PASS
Labels follow the pattern `v11_sens_k{k}_df{df}` (line 24). Since (k, df) pairs are unique in the GRID, all 9 labels are distinct: `v11_sens_k10_df2`, `v11_sens_k10_df4`, ..., `v11_sens_k20_df8`.

---

## 3. hp_sensitivity_sweep.py -- Quick Check

### 3.1 Correctness: PASS
- Uses `--skip-save-model` flag (line 119), so no model files are written. Good.
- Uses `--skip-ridge` (line 118) to skip the Ridge baseline, appropriate for HP sensitivity.
- Regex parsing (lines 63-104) looks for standard metric patterns. The regexes use `R..` to match R-squared with any unicode encoding of the superscript 2. Reasonable.
- All experiments use GKF5 cross-validation (line 115), matching v11 methodology.
- Results are saved to `hp_sensitivity_sweep.json` (line 223), not overwriting any model file.

### 3.2 Potential issue: Regex collision (LOW)
Line 101: `re.search(r"(?:BCF|[Ss]mearing)\s*[=:]\s*([-\d.]+)", line)` -- if a line contains both "BCF" and "Smearing", only the last match wins due to the loop structure. This is acceptable since only the final parsed value is kept, and these should appear on separate lines.

### 3.3 Risk of model modification: PASS
The `--skip-save-model` flag prevents any model file writes. The script uses `--label hp_{label}` prefix which further separates these from production outputs.

---

## 4. Model File Integrity

### 4.1 Model .cbm file: PASS
`git status` shows "nothing to commit, working tree clean". The model file `ssc_C_sensor_basic_watershed_v11_extreme_expanded.cbm` was last modified in commit `0bb9ffb` ("v11 model + evaluation: expanded extreme data, Plain boosting"). No uncommitted changes exist.

### 4.2 Model meta JSON: PASS
Same status -- no modifications since commit `0bb9ffb`. Clean working tree.

---

## 5. Vault Evaluation Output (v11_vault_eval_summary.json)

### 5.1 Partition label: PASS
`"partition": "vault"` -- correct.

### 5.2 Site/sample counts: PASS
- `"vault_sites": 37` -- matches the 37 sites visible in the adaptation curves (n_sites = 37 at N=0 through N=10 for all modes).
- `"vault_samples": 4054` -- consistent with baselines where `"n": 4054`.

### 5.3 Adaptation curve structure: PASS
All three split modes present (random, temporal, seasonal). Each has entries for N = 0, 1, 2, 3, 5, 10, 20, 30, 50. The n_sites correctly decreases at higher N values (sites with fewer samples drop out), e.g., random N=20 has 33 sites, N=50 has 23 sites.

### 5.4 Zero-shot sanity check: PASS
- Spearman rho = 0.920 (strong rank correlation, consistent with a well-trained model)
- Pooled NSE = 0.151 (low, expected for vault sites the model has never seen)
- Bias = -66.4% (large negative bias, expected -- model underpredicts on unseen sites)
- Median per-site R2 = 0.365 (reasonable zero-shot on held-out sites)

### 5.5 Data observation: n_sites at N=0 is identical across all modes
At N=0 (zero calibration samples), all three modes correctly show n_sites=37 with identical metrics. This is correct because zero-shot performance is independent of split mode.

---

## Summary

| Item | Status | Severity |
|------|--------|----------|
| evaluate_model.py partition filter | PASS | -- |
| evaluate_model.py assertions for vault | PASS | -- |
| evaluate_model.py output JSON labels | PASS | -- |
| evaluate_model.py no model mutation | PASS | -- |
| evaluate_model.py log messages | PASS | -- |
| **prior_sensitivity.py JSON path** | **BUG** | **CRITICAL** |
| **prior_sensitivity.py metric key name** | **BUG** | **CRITICAL** |
| prior_sensitivity.py no model mutation | PASS | -- |
| prior_sensitivity.py label uniqueness | PASS | -- |
| hp_sensitivity_sweep.py correctness | PASS | -- |
| hp_sensitivity_sweep.py no model mutation | PASS | -- |
| Model .cbm file integrity | PASS | -- |
| Model meta.json integrity | PASS | -- |
| Vault eval partition label | PASS | -- |
| Vault eval site/sample counts | PASS | -- |

**Action required:** Fix prior_sensitivity.py lines 49-51 before running the sensitivity grid. Without the fix, all 9 experiments will silently produce `"?"` for every metric, wasting hours of compute.
