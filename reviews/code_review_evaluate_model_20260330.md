# Code Review: `scripts/evaluate_model.py`

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-30
**File:** `scripts/evaluate_model.py` (1136 lines)
**Scope:** Full review covering correctness, edge cases, data flow, subprocess integration, performance, and output consistency.

---

## Issues Found (ranked by severity)

### CRITICAL

#### 1. NSE is NOT identical to R-squared for your formulation — mismatch in `compute_site_metrics` vs `r_squared()`

The docstring and code claim NSE and R-squared are identical (`1 - SS_res/SS_tot`), and this is true for the formula used. However, there is a subtle inconsistency: the local `compute_site_metrics` function checks `ss_tot < 1e-10` and returns `np.nan` when it is too small (line 437-438), but then calls `r_squared()` from `metrics.py` which uses `max(ss_tot, 1e-10)` — meaning `r_squared()` will return a huge positive number (approaching 1.0) instead of NaN when `ss_tot` is near zero.

If all true values at a site are nearly identical, `compute_site_metrics` will correctly return NaN, but `r_squared()` would return approximately `1 - ss_res / 1e-10` which could be a very large negative number. The guard in `compute_site_metrics` protects against this, but the inconsistency is confusing and fragile — if anyone calls `r_squared()` directly elsewhere for a constant-y site, they get garbage.

**Impact:** Low in this script (the guard catches it), but a latent API bug.
**Fix:** Make `r_squared()` in `metrics.py` also return NaN when `ss_tot < 1e-10`, or document this mismatch.

---

### HIGH

#### 2. Seasonal month-neighbor calculation has an off-by-one bug for December

Lines 530-531:
```python
neighbors = [(peak_month - 2) % 12 + 1, (peak_month - 1) % 12 + 1,
             peak_month, peak_month % 12 + 1]
```

This is a 4-month window (peak +/- 1, plus an extra month 2-before). But the intent stated in the comment is "plus/minus 1 month." The window is actually asymmetric: it includes the month **two before** the peak but only **one after**. For `peak_month=1` (January):
- `(1-2) % 12 + 1 = 11 + 1 = 12` (December) -- correct
- `(1-1) % 12 + 1 = 0 + 1 = 1` (January) -- this is the peak itself, duplicated
- `1` (January again)
- `1 % 12 + 1 = 2` (February)

So for January the window is {12, 1, 2} (3 unique months). For `peak_month=12`:
- `(12-2) % 12 + 1 = 10 + 1 = 11`
- `(12-1) % 12 + 1 = 11 + 1 = 12`
- `12`
- `12 % 12 + 1 = 1`

Window is {11, 12, 1} (3 unique months). This is actually a 3-month symmetric window, not the 4-month asymmetric one it appears to be — the first element `(peak_month - 2) % 12 + 1` adds the month 2-before, but for most months, the second entry `(peak_month - 1) % 12 + 1` is just 1 month before the peak, so you get a 4-unique-month window for months 3-12 but a 3-month window for January. This inconsistency across months could bias seasonal splits.

**Fix:** Decide on a consistent window (e.g., exactly +/- 1 month = 3 months). Replace with:
```python
neighbors = {(peak_month - 2) % 12 + 1, peak_month, peak_month % 12 + 1}
```

#### 3. Temporal mode is NOT truly deterministic across data changes

Line 523: `cal_idx = np.arange(n_cal)` relies on the data being pre-sorted by `sample_time` (line 745). However, if two samples at the same site have identical `sample_time` values, `sort_values` uses the original row order, which depends on upstream merge order. This makes the split non-deterministic across data rebuilds. The sort should include a tiebreaker:

```python
readings = readings.sort_values(["site_id", "sample_time", "y_true_native"])
```

**Impact:** May silently produce different adaptation curves if data pipeline is re-run.

#### 4. `adapt_old_2param` applies correction to ALL indices before slicing `test_idx`

Line 268: `corrected_ms = a * y_pred_ms + b` — this applies the correction to the full array `y_pred_ms` (all samples at the site), not just `test_idx`. Then line 279 slices `corrected_ms[test_idx]`. This is functionally correct but wasteful. More importantly, the per-trial BCF on lines 271-275 computes `cal_corrected_native = inverse_transform(corrected_ms[cal_idx], ...)` which uses the corrected predictions at calibration indices — this is correct (you want to see how well the correction works on cal data to compute BCF).

However, this means the calibration samples inform both the linear correction AND the BCF, which is double-dipping. The BCF is essentially overfitting to the calibration set. For the Bayesian method this is partially mitigated by shrinkage, but for `old_2param` it is not.

**Impact:** Optimistic per-trial BCF estimates in `old_2param` mode. Not a bug per se, but a methodology concern worth documenting.

---

### MEDIUM

#### 5. `_aggregate_trials` drops `median_abs_error` — inconsistent with `compute_site_metrics`

`compute_site_metrics()` returns `median_abs_error` (line 487), but `_aggregate_trials()` (line 665-681) does not aggregate it. Neither does `_aggregate_curve()` (line 684). This means the adaptation curve output is missing `median_abs_error` while the zero-shot per-site output has it.

**Impact:** Incomplete metrics in adaptation results. Anyone comparing zero-shot vs adapted metrics will find `median_abs_error` missing from the adapted side.

#### 6. `adapt_bayesian` does not use the global BCF at all

The function signature accepts `bcf` (the global BCF from training) but never uses it. The adapted predictions use only the per-trial `trial_bcf` shrunk toward 1.0 (line 377). Meanwhile `adapt_none` (line 237) and `adapt_old_2param` (line 279 indirectly) do use the global BCF. This means the N=0 baseline uses global BCF, but as soon as you get 1 calibration sample, the BCF jumps to a shrinkage estimate toward 1.0 rather than toward the global BCF.

Shrinking toward 1.0 rather than toward the global BCF is a defensible choice (conservative), but it means there is a potential discontinuity between N=0 (global BCF) and N=1 (BCF shrunk hard toward 1.0). If the global BCF is, say, 1.15, and you get 1 sample that suggests BCF=1.3, the trial_bcf with k_bcf=45 would be `1.0 + (1/46)*(1.3 - 1.0) = 1.0065`, which is *worse* than the global BCF. The adaptation could actually degrade performance at small N.

**Impact:** Potential non-monotonic adaptation curve at small N values.
**Fix:** Consider shrinking toward the global BCF instead of 1.0: `trial_bcf = bcf + bcf_shrinkage * (bcf_raw - bcf)`.

#### 7. `site_mean` baseline predictor computes using holdout-only data, not true site means

Line 565: `site_mean_pred[mask] = np.mean(y_true[mask])` computes the mean SSC from the holdout data itself. This is a leave-one-out-like setup but it is not: it uses all samples including the one being predicted. This makes the site-mean baseline slightly optimistic (it sees the true value for each sample when computing the mean).

For a fair baseline, this should be a leave-one-out site mean, or at least documented that it is an in-sample site mean. Given that the purpose is just a reference baseline, this is minor.

#### 8. Bootstrap CI uses a fixed seed (42) regardless of the main seed

Line 581: `rng = np.random.default_rng(42)`. This is deterministic (good), but it means the bootstrap CIs do not change if you change `--seed`. If someone runs two experiments with different seeds to test sensitivity, the CIs will be identical even though the underlying adaptation trial results differ. This is defensible (bootstrap is just for CI estimation on whatever data you have) but worth noting.

#### 9. Subprocess error messages are truncated to 200 chars

Lines 1103, 1124: `result.stderr[-200:]`. If the subprocess fails with an important error, you only see the last 200 characters. A traceback could easily be longer than this.

**Fix:** Log at least 500-1000 chars, or log the full stderr at DEBUG level and only truncate for WARNING.

---

### LOW

#### 10. Redundant `import subprocess` at line 1091

`subprocess` is already imported at line 23 (top of file). The inner `import subprocess` on line 1091 is harmless but dead code.

#### 11. `adapt_ols_loglog` fallback when `valid.sum() == 0` returns `np.nanmedian(cal_ssc)`

Line 398: if there are zero valid (positive) calibration pairs, it falls back to `np.nanmedian(cal_ssc)`. But if all `cal_ssc` values are zero or negative, `np.nanmedian` returns 0.0, which produces an all-zeros prediction. This is technically correct behavior given the degenerate input, but it could mask data quality issues.

#### 12. `polyfit` from `numpy.polynomial.polynomial` returns `[intercept, slope]` (non-standard order)

Lines 259-261 and 404-405 correctly unpack `b, a = coeffs[0], coeffs[1]` for `numpy.polynomial.polynomial.polyfit`, which returns `[c0, c1]` = `[intercept, slope]`. This is correct, but the non-standard order compared to `np.polyfit` (which returns `[slope, intercept]`) is a maintenance trap. The comment on line 260 helps. Good.

#### 13. `_clean()` helper only handles float NaN, not numpy integers or other edge cases

Line 887-889: `isinstance(v, float) and np.isnan(v)` — this will NOT catch `np.float64` NaN values. In Python, `isinstance(np.float64(np.nan), float)` is `True` (numpy scalars subclass float), so this actually works. However, if any metric returns a bare `np.nan` (which is a Python float), it will also be caught. This is fine but fragile.

#### 14. `print_summary` formats `frac_within_2x` as `:.1%` (e.g., "85.3%") but the value is already 0-1

Line 967: `{pooled['frac_within_2x']:.1%}` — this is correct. Python's `%` format multiplies by 100. But line 995 uses `{m2x:>4.1f}%` — this treats the 0-1 value as a percentage directly, printing "0.8%" instead of "80%". There is an inconsistency: the zero-shot summary uses `:.1%` format (correct), but the adaptation curve table uses `:.1f%` format (wrong — will show e.g., "0.9%" instead of "90%").

**Impact:** The adaptation curve table prints nonsensical values for `within_2x`. This is a **display bug** — the underlying data is correct.
**Fix:** Change line 995 from `{m2x:>4.1f}%` to `{m2x:>5.1%}` or multiply by 100 first.

*Severity upgraded:* This is arguably **MEDIUM** since it produces misleading terminal output that could cause incorrect interpretations during development.

---

### STYLE / MINOR

#### 15. No type annotation for `run_adaptation_curve` return value

The function returns a complex nested dict. A TypedDict or dataclass would make the structure clear and prevent key typos.

#### 16. `spearmanr` imported with underscore alias but only used once

Line 43: `from scipy.stats import spearmanr as _spearmanr`. The underscore prefix suggests "private" but it is just an alias to avoid name collision. Fine, but a comment would help.

#### 17. Magic number `1e-6` in `adapt_bayesian` line 371

`cal_corrected_native = np.clip(cal_corrected_native, 1e-6, None)` — this prevents division by zero in BCF calculation. The choice of `1e-6` is reasonable for SSC (mg/L) but should be a named constant.

---

## Things Done Well

1. **Deterministic seeding with per-site hash.** The `hashlib.md5(str(site_id).encode())` approach (line 633) ensures each site gets a reproducible but different random stream. Smart.

2. **Assertion-based data validation.** The script checks expected site/sample counts, feature count mismatches, NaN in predictions, and BCF range. These are exactly the kind of guards the CLAUDE.md lesson ("fail loudly") calls for.

3. **Clean separation of concerns.** Transform helpers, adaptation methods, metrics, split logic, and output generation are all well-separated. Each function does one thing.

4. **Multiple split modes are a strength.** The temporal/seasonal/random split design directly addresses a common criticism in hydrology ML papers (optimistic random splits). This is publication-quality methodology.

5. **The Bayesian shrinkage implementation is sound.** The staged approach (intercept-only for N<10, slope+intercept for N>=10) with MAD-based robust scale estimation is well-motivated. The Student-t influence weighting prevents extreme sites from being over-shrunk while still regularizing moderate sites.

6. **BCF is applied exactly once.** The code is careful to apply BCF only in `predict_holdout` for the zero-shot path and only as `trial_bcf` in the adaptation path. No double-BCF risk.

7. **Baseline comparisons.** Including global-mean and site-mean predictors as baselines is excellent for paper-readiness. Reviewers will ask for this.

8. **Good error messages.** The assertion messages include actual vs expected values, making debugging straightforward.

---

## Summary

| Severity | Count | Key items |
|----------|-------|-----------|
| CRITICAL | 1     | `r_squared()` vs local NSE guard inconsistency (latent, mitigated) |
| HIGH     | 3     | Seasonal month window asymmetry; temporal sort tiebreaker; `old_2param` BCF double-dipping |
| MEDIUM   | 5     | Missing `median_abs_error` in aggregation; BCF shrinkage toward 1.0 vs global; site-mean baseline optimism; fixed bootstrap seed; truncated subprocess stderr; `within_2x` display bug |
| LOW      | 5     | Redundant import; OLS edge case; polyfit order trap; NaN cleaning fragility; magic number |
| STYLE    | 3     | Missing return type; alias naming; type annotations |

**Recommended priority for fixes:**
1. The `within_2x` display bug (#14) — you may be misreading your own adaptation tables right now.
2. Seasonal month window (#2) — inconsistent 3-vs-4 month windows across peak months.
3. Missing `median_abs_error` in aggregation (#5) — easy fix, adds consistency.
4. BCF shrinkage direction (#6) — investigate whether this explains any non-monotonicity in your adaptation curves.
5. Temporal sort tiebreaker (#3) — one-line fix for reproducibility insurance.
