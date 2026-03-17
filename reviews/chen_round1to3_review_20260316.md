# Chen Review: Round 1-3 Implementation Fixes
**Reviewer:** Dr. Sarah Chen, ML Engineer
**Date:** 2026-03-16
**Files reviewed:** `attributes.py`, `discrete.py`, `qc.py`, `check_temporal_overlap.py`

---

## Overall Assessment

The implementation addresses the core concerns from my earlier review. The GAGES-II pruning, 3-tier ablation, and generalized discrete loader are structurally sound. I have a few targeted findings below, ranked by severity.

---

## 1. GAGES-II Feature List (25 features)

**Verdict: Acceptable with one flag.**

The 25 features are well-chosen. The merging of correlated land-cover classes (crops+pasture into `agriculture_pct`, computing `other_landcover_pct` as residual) is exactly what I'd do. The inclusion of `snow_pct_precip` and `precip_seasonality` is good -- these matter for rain-snow transition watersheds which is your deployment context.

### MINOR: Drainage area is missing from the GAGES-II prune

`drainage_area_km2` is arguably the single most important catchment attribute for any water quality transfer model. I see it appears in Tier B via `basic_attrs`, so it's not actually missing from the model -- but it's worth noting that the 25-feature GAGES-II list alone doesn't include it. This is fine as long as Tier C always stacks on top of Tier B (which it does). No action needed, just documenting.

### MINOR: `geol_class`, `reference_class`, `ecoregion` are categorical

These three features will need encoding before any tree or linear model sees them. `geol_class` from `GEOL_HUNT_DOM_CODE` can have ~15 levels; `ecoregion` from `AGGECOREGION` can have ~10. For 42 sites, one-hot encoding `geol_class` alone could add 15 columns, partially undoing your pruning.

**Recommendation:** Use ordinal encoding or target encoding for these, not one-hot. Or collapse geology to 4-5 superclasses (sedimentary, ignite, metamorphic, unconsolidated, mixed). Flag this for the modeling phase.

### OK: No obviously redundant features

`clay_pct` and `sand_pct` are moderately correlated but capture different soil hydraulics (clay = retention, sand = conductivity). Both are worth keeping. `relief_m` and `slope_pct` overlap conceptually but relief captures basin-scale gradient while slope is mean local gradient. Fine.

---

## 2. `build_feature_tiers()` -- 3-Tier Ablation

**Verdict: Correct implementation of what I recommended.**

The logic is right:
- Tier A = sensor features only, all sites
- Tier B = sensor + basic attrs (drainage area, elevation, HUC), all sites
- Tier C = sensor + basic + GAGES-II, GAGES-II sites only (subset)

This is exactly the ablation structure I asked for. It lets you answer: "Do catchment attributes help, and does the full GAGES-II suite help beyond basic attrs?"

### MEDIUM: `target_patterns` filter is fragile

```python
target_patterns = {"_log1p", "ssc_value", "value"}
```

The sensor column filter excludes any column containing `"value"` as a substring. This will accidentally exclude columns like `"max_value_24h"` or `"turbidity_value"` if they exist. The string `"value"` is too common.

**Fix:** Use exact matches or a more specific pattern. Better yet, define an explicit list of known target columns rather than pattern-matching:

```python
target_cols = {"lab_value", "ssc_value", "value", "lab_value_log1p", "ssc_value_log1p"}
```

Then filter as `c not in metadata_cols and c not in target_cols`.

### MINOR: Tier B falls through silently if `basic_attrs` is None

If `basic_attrs` is None, Tier B is simply not created and there's no log message about it. This is defensible but could confuse a downstream user who expects three tiers and gets two. Add a `logger.warning` if Tier B is skipped.

### MINOR: Tier C doesn't verify site overlap

Line 178 filters `assembled_df` to GAGES-II sites, but doesn't log a warning if few sites match. If only 10 of 42 sites have GAGES-II coverage, Tier C becomes underpowered. Add a check:

```python
if len(tier_c_base["site_id"].unique()) < 20:
    logger.warning(f"Tier C has only {n} sites — LOGO CV may be underpowered")
```

---

## 3. Temporal Overlap Results & LOGO CV Viability

### TP, Nitrate, OrthoP (41-42 sites, 8K-9K samples): SUFFICIENT

42 sites is adequate for LOGO CV. Each fold holds out 1 site and trains on 41. With 8-9K total pairable samples, the average site contributes ~200 samples. This is workable. Not luxurious, but workable.

**One caveat:** The 42 sites with >=20 pairable samples tells me there's a long tail of sites with fewer. For LOGO CV, what matters is that the held-out site has enough samples for a meaningful test-set evaluation. 20 is my minimum; I'd prefer 30+. Report the distribution (10th/25th/50th/75th percentiles of per-site sample counts) so we know if any folds are effectively noise.

### TDS (16 sites, 2,231 samples): NOT VIABLE for LOGO CV

**SEVERITY: HIGH.** 16 sites is not enough for LOGO CV. Each fold trains on 15 sites -- that's too few for any model to learn transferable patterns, especially with 25 catchment attributes. You'd be fitting noise.

**Recommendation:** Flag TDS as a stretch target. Options:
1. **Drop TDS from the MVP entirely.** Focus on SSC, TP, nitrate, orthoP (all >=41 sites).
2. **Use grouped k-fold instead of LOGO** for TDS only -- but this leaks site information, so results aren't comparable to the other parameters. I'd avoid this.
3. **Revisit after Phase 4** -- maybe relaxing the 20-sample threshold to 10 adds enough sites, but then per-site test sets are tiny.

My recommendation: **drop TDS from MVP scope.** Four parameters with solid site counts is better than five with one being unreliable.

### SSC (54 sites, 19K samples): STRONG

This is your best-powered parameter. 54 LOGO folds, ~360 samples per site on average. Solid.

---

## 4. Discrete Loader (`discrete.py`)

**Verdict: Clean, well-structured.**

The generalization from SSC-only to parameter-agnostic is well done. The backward-compatible `load_ssc()` wrapper is good practice.

### MEDIUM: DL fallback chain has a subtle bug

Lines 147-152:
```python
dl_values = dl_values.fillna(
    pd.to_numeric(df["Result_Measure"], errors="coerce")
)
dl_values = dl_values.fillna(default_dl)
```

For non-detect records, `Result_Measure` is often the detection limit itself (USGS convention: report the DL as the result value when non-detect). So `dl_values.fillna(Result_Measure)` is correct in that case. But if the lab reported 0 or some other placeholder as the result for a non-detect, you'd get DL/2 = 0, which silently creates zero-valued "measurements."

**Recommendation:** Add a guard: if the filled DL value is <= 0 after the fillna chain, replace it with `default_dl`. One line:
```python
dl_values = dl_values.where(dl_values > 0, default_dl)
```

### MINOR: `n_nondetect` is defined inside a conditional but referenced in the log

The variable `n_nondetect` is only defined if `Result_ResultDetectionCondition` exists AND `n_nondetect > 0`. The log line at 156 is inside that block so it's fine, but there's no log output for the case where there are zero non-detects. Consider logging that too for auditability.

### OK: Timezone handling

The USGS timezone map and local-to-UTC conversion logic is correct. The decision to skip sites with no `Activity_StartTime` is conservative but appropriate -- discrete samples without timestamps are unusable for pairing.

---

## 5. QC Functions (`qc.py`)

### MEDIUM: Buffer period logic is a TODO placeholder

Lines 92-97 in `filter_continuous()`:
```python
# TODO: Refactor to identify flag boundaries BEFORE step 2 filtering.
stats["n_buffer_excluded"] = 0  # Placeholder until refactored
```

The Ice 48-hour and Mnt 4-hour buffers were a specific recommendation from Rivera's review. They're defined in `QUALIFIER_BUFFERS` but never actually applied. This means post-Ice sediment pulses and post-maintenance step artifacts are leaking into your training data.

**Recommendation:** This needs to be fixed before model training. The fix is straightforward: compute flag-end timestamps from the original unfiltered data *before* Step 2, then apply the buffer mask *after* Step 2. Pass the original df as a parameter or restructure the function to do buffer detection first.

### MINOR: `deduplicate_discrete` groups by datetime only, not datetime + site

Line 151:
```python
dup_mask = df.duplicated(subset=[datetime_col], keep=False)
```

If `df` contains multiple sites (which it could if called on a concatenated dataset), two samples from different sites at the same timestamp would be treated as duplicates. This is currently safe because `load_discrete_param` calls it per-site, but it's a latent bug if anyone calls `deduplicate_discrete` on a multi-site DataFrame later.

**Recommendation:** Add `site_id` to the dedup key if the column exists, or document that this function assumes single-site input.

### OK: `filter_high_censoring` and `exclude_contamination`

Both are clean and correct. The 50% censoring threshold is reasonable -- I'd personally use 40% but 50% is defensible for an MVP. The contamination keyword matching is case-insensitive and uses partial matching, which is appropriate for the messy text in USGS detection condition fields.

---

## 6. Temporal Overlap Script (`check_temporal_overlap.py`)

**Verdict: Good diagnostic tool.**

### MINOR: Decision gate threshold should be documented

The script checks ">=30 sites with >=3 params AND >=20 pairable samples each." Where do these thresholds come from? They should be in the research plan or at minimum in a comment explaining the rationale. 30 sites is the minimum I'd want for LOGO CV; 20 samples per site is the minimum for a meaningful held-out test. Document that.

### MINOR: `n_parseable_time` is only in some result rows

When `disc_file` doesn't exist, the result dict doesn't include `n_parseable_time` (line 152-159 vs 176-184). This will create NaN in that column for those rows. Not a bug per se but messy. Add `"n_parseable_time": 0` to the no-file branch.

---

## Summary of Findings

| # | Severity | File | Issue |
|---|----------|------|-------|
| 1 | **HIGH** | -- | TDS at 16 sites is not viable for LOGO CV. Drop from MVP. |
| 2 | **MEDIUM** | `attributes.py` | `target_patterns` substring match is fragile; use explicit target column set |
| 3 | **MEDIUM** | `discrete.py` | DL fallback can produce DL/2 = 0 for non-detects with zero-valued results |
| 4 | **MEDIUM** | `qc.py` | Ice/Mnt buffer periods are TODO placeholder -- not actually applied |
| 5 | MINOR | `attributes.py` | Categorical features (geol_class, ecoregion) need encoding strategy before modeling |
| 6 | MINOR | `attributes.py` | Tier B skipped silently if basic_attrs is None |
| 7 | MINOR | `attributes.py` | Tier C should warn if site count < 20 |
| 8 | MINOR | `qc.py` | `deduplicate_discrete` assumes single-site input; latent multi-site bug |
| 9 | MINOR | `check_temporal_overlap.py` | `n_parseable_time` missing from some result rows |
| 10 | MINOR | `check_temporal_overlap.py` | Decision gate thresholds should be documented with rationale |

## Recommended Action Before Model Training

1. Fix #2 (target_patterns) -- quick, prevents silent feature leakage
2. Fix #3 (DL zero guard) -- one line
3. Fix #4 (buffer periods) -- needs a small refactor but is important for data quality
4. Make the TDS decision (#1) -- I recommend dropping it

Items #5-10 can wait for the modeling phase but should be tracked.

---

*-- Dr. Sarah Chen, 2026-03-16*
