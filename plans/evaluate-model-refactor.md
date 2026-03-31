# evaluate_model.py Refactor Plan

## Context

The evaluation script needs to become the canonical, repeatable test suite for any model. Currently it only does random-split adaptation with basic metrics (R², KGE, RMSE, MAPE, within-2x). Expert panel identified missing metrics and the external validation work revealed the need for three split modes. Every model we train should go through the same battery of tests.

## What exists now (evaluate_model.py, ~814 lines)

- `forward_transform()` / `inverse_transform()` — transform helpers
- `load_holdout_data(meta)` — loads 76 holdout sites with features
- `predict_holdout(model, holdout, meta)` — generates predictions, returns DataFrame with y_true/y_pred in native + model space
- `adapt_none()` — no adaptation, just BCF
- `adapt_old_2param()` — OLS slope+intercept + per-trial BCF (Gemini fixes applied)
- `adapt_bayesian()` — staged Student-t shrinkage (ported from site_adaptation_bayesian.py)
- `adapt_ols_loglog()` — log-log OLS ignoring CatBoost
- `_student_t_shrinkage()` — helper for Bayesian
- `compute_site_metrics(y_true, y_pred)` — R², KGE, RMSE, MAPE, within-2x
- `run_adaptation_curve()` — Monte Carlo trials across N values, random split only
- `save_per_reading()` / `save_per_site()` / `save_summary()` — output files
- `print_summary()` — human-readable stdout
- `main()` — CLI entry point

## Changes needed

### 1. Upgrade `compute_site_metrics()` — add new metrics

Add to the returned dict:
- `nse` — identical to our current R² (1 - SS_res/SS_tot), just label it
- `log_nse` — same formula on log-transformed values (emphasizes low-value accuracy)
- `spearman_rho` — rank correlation (from scipy.stats.spearmanr)
- `bias_pct` — (mean_pred - mean_true) / mean_true * 100
- `median_abs_error` — np.median(|y_true - y_pred|)

Keep existing: r2, kge, rmse, mape_pct, frac_within_2x, n

**Files:** evaluate_model.py, function at line ~415
**Import needed:** `from scipy.stats import spearmanr`

### 2. Add split mode functions — new section

Create a `get_cal_test_split()` function that returns (cal_idx, test_idx) given:
- `n_site` — total samples at this site
- `n_cal` — number of calibration samples
- `mode` — "random", "temporal", "seasonal"
- `rng` — random generator (for random/seasonal modes)
- `dates` — sample dates (for temporal/seasonal modes)

Logic:
- **random:** `cal_idx = rng.choice(n_site, n_cal, replace=False)` (current behavior)
- **temporal:** `cal_idx = np.arange(n_cal)` (first N chronologically, data must be sorted by date)
- **seasonal:** Find most common month in the site's samples. Select N cal samples from within ±1 month of that peak. Test on everything else.

**Files:** evaluate_model.py, new section after adaptation methods (~line 410)

### 3. Add baseline predictor — new function

`compute_baseline_metrics(y_true_native)` — computes what you'd get from:
- **site-mean predictor:** predict mean(y_true) for every sample → R² = 0 by definition, but RMSE/MAPE/bias are the baselines to beat
- **global-mean predictor:** predict the overall mean across all sites

These go into the summary so reviewers can see "model R²=0.665 vs site-mean R²=0 vs global-mean R²=negative".

**Files:** evaluate_model.py, new function near compute_site_metrics

### 4. Add bootstrap confidence intervals — new function

`bootstrap_ci(values, n_boot=1000, ci=0.95)` — returns (lower, upper) for the metric.

Apply to the aggregated curve metrics (median R², median KGE, etc.) across sites. Each bootstrap iteration resamples sites (not samples within sites).

**Files:** evaluate_model.py, new function. Called during curve aggregation.

### 5. Modify `run_adaptation_curve()` — three split modes

Current signature adds `split_modes` parameter (default: `["random", "temporal", "seasonal"]`).

The function runs the full adaptation curve for EACH split mode and returns results keyed by mode:

```python
return {
    "random": {"curve": {...}, "per_site": {...}},
    "temporal": {"curve": {...}, "per_site": {...}},
    "seasonal": {"curve": {...}, "per_site": {...}},
}
```

Internal changes:
- Before the site loop: sort each site's data by date (needed for temporal/seasonal)
- Need `sample_time` column in the readings DataFrame (check if predict_holdout includes it)
- For each (site, N, mode): call `get_cal_test_split()` to get indices
- temporal mode: 1 deterministic split (no MC trials needed)
- random/seasonal modes: N_TRIALS MC trials as before

### 6. Update `predict_holdout()` — ensure sample_time is preserved

Check that the returned DataFrame includes `sample_time` for temporal/seasonal splits. Currently it has `sample_time` if present in the holdout data — verify this.

**Files:** evaluate_model.py line ~150-220

### 7. Update `save_summary()` — multi-mode output

The summary JSON gets restructured:
```json
{
    "zero_shot": {...metrics...},
    "baselines": {"site_mean": {...}, "global_mean": {...}},
    "adaptation": {
        "random": {"curve": {...}, "per_site": {...}},
        "temporal": {"curve": {...}, "per_site": {...}},
        "seasonal": {"curve": {...}, "per_site": {...}}
    },
    "bootstrap_ci": {...}
}
```

### 8. Update `save_per_site()` — include all modes

Per-site parquet gets adaptation columns for each mode:
- `r2_at_N_random`, `r2_at_N_temporal`, `r2_at_N_seasonal` for each N

### 9. Update `print_summary()` — show all three modes

Print three adaptation curve tables side by side (or sequentially). Include baseline comparison at the top. Show bootstrap CIs.

### 10. Update `main()` CLI — add split mode control

- `--split-modes` flag: comma-separated, default "random,temporal,seasonal"
- Allows running just one mode for quick tests: `--split-modes random`

## Execution order

1. `compute_site_metrics()` upgrade (add metrics) — no dependencies
2. `get_cal_test_split()` new function — no dependencies
3. `compute_baseline_metrics()` new function — no dependencies
4. `bootstrap_ci()` new function — no dependencies
5. `run_adaptation_curve()` refactor — depends on 1, 2
6. `predict_holdout()` sample_time check — verify only
7. `save_summary()` update — depends on 5
8. `save_per_site()` update — depends on 5
9. `print_summary()` update — depends on 5
10. `main()` CLI update — depends on all above

Steps 1-4 can be done in parallel (independent functions). Steps 5-10 are sequential.

## Verification

After refactoring:
1. Run on the v4 model: `.venv/Scripts/python scripts/evaluate_model.py --model data/results/models/ssc_C_sensor_basic_watershed.cbm --meta data/results/models/ssc_C_sensor_basic_watershed_meta.json --label v4_refactored`
2. Compare random-mode R² values to previous run (should be identical for same seed)
3. Verify temporal and seasonal modes produce different (generally lower) numbers
4. Verify bootstrap CIs are reasonable (not too wide, not zero)
5. Verify baseline metrics appear in summary
6. Verify all three output files are well-formed
