# Okafor Round 1-3 Review: Dedup, HUC02, Type Safety, Integration

**Reviewer:** Dr. Jenna Okafor (data engineering)
**Date:** 2026-03-16
**Files reviewed:**
- `src/murkml/data/qc.py` (lines 123-268 -- new functions)
- `src/murkml/data/discrete.py` (new file)
- `src/murkml/data/attributes.py` (new file)
- `scripts/download_gagesii.py` (HUC02 fix, lines 238-249)

---

## 1. Dedup Logic (`deduplicate_discrete`)

### BUG [SEVERITY: HIGH] -- Three-or-more rows with mixed values and NaNs

`group[value_col].nunique()` by default **excludes NaN** from the count. Consider three rows at the same datetime:

| value |
|-------|
| 150.0 |
| NaN   |
| 150.0 |

`nunique()` returns 1 (only sees 150.0), so this hits the "all values agree" branch and keeps `group.iloc[[0]]` -- which could be the 150.0 row, or the NaN row depending on original sort order. If `iloc[0]` happens to be the NaN row, you silently keep NaN and discard the real measurement.

**Fix:** Before the `nunique()` check, drop NaN values from the group (or at least from the value comparison):

```python
non_null = group.dropna(subset=[value_col])
if non_null.empty:
    kept.append(group.iloc[[0]])  # all NaN, keep one
elif non_null[value_col].nunique() <= 1:
    kept.append(non_null.iloc[[0]])  # agree -- keep first non-null
    stats["n_exact_dupes"] += len(group) - 1
else:
    # conflict resolution (existing USGS-preference logic)
    ...
```

### BUG [SEVERITY: MEDIUM] -- `Org_Identifier` column present but all-NaN

When `org_col in group.columns` is True but every value is NaN, this line:
```python
usgs_mask = group[org_col].astype(str).str.contains("USGS", case=False, na=False)
```
produces all False (because `na=False`). So `usgs_mask.any()` is False, and it falls through to `kept.append(group.iloc[[0]])`. This is **correct behavior** -- first-row fallback is reasonable when org is unknown. No bug here, but the logging doesn't distinguish "no org info" from "org present but non-USGS." Consider a debug log line for traceability.

### OBSERVATION [SEVERITY: LOW] -- Three rows, two conflicting non-NaN values

Example: datetime has rows with values [100, 200, 100]. `nunique()` returns 2, so conflict branch fires. The USGS-preference logic picks one row. This works correctly, but the `n_conflicts_resolved` counter increments by 1 regardless of how many rows were dropped. The stat is "number of conflict groups", not "number of rows dropped in conflicts." This is fine semantically, but document it or rename to `n_conflict_groups`.

### OBSERVATION [SEVERITY: LOW] -- `groupby` on datetime with timezone

If `datetime_col` contains tz-aware timestamps, `groupby` works correctly in modern pandas (>= 1.4). No issue here, just noting that this was validated.

---

## 2. HUC02 Fix (`download_gagesii.py`, lines 238-248)

### BUG [SEVERITY: HIGH] -- `.dropna().astype(int)` produces a shorter Series, then assignment silently misaligns

The chain:
```python
gagesii["HUC02"] = (
    gagesii["HUC02"]
    .dropna()           # <-- returns Series with FEWER rows
    .astype(int)
    .astype(str)
    .str.zfill(2)
)
```

When you assign a shorter Series back to `gagesii["HUC02"]`, pandas aligns on index. Rows that were NaN get set back to NaN because their index isn't in the right-hand Series. So the non-NaN rows are correctly converted, and the NaN rows stay NaN. **This actually works by accident due to pandas index alignment.**

However, the next line is suspect:
```python
gagesii["HUC02"] = gagesii["HUC02"].where(gagesii["HUC02"].notna(), None)
```

This replaces NaN with `None`. In a pandas Series, `None` in a string column is stored as `NaN` anyway (object dtype). This line is a no-op. It does not cause a crash, but it's dead code that suggests the author was uncertain about the behavior. Not harmful, but misleading.

**The real risk:** If `HUC02` contains non-integer floats (e.g., due to data corruption producing 1.5), `.astype(int)` will silently truncate to 1. This is unlikely for HUC codes but worth a guard:

```python
raw = gagesii["HUC02"].dropna()
assert (raw == raw.astype(int)).all(), "HUC02 has non-integer float values"
```

### OBSERVATION [SEVERITY: LOW] -- Double dtype conversion in `attributes.py`

In `build_feature_tiers` (lines 165-166, 191-192):
```python
tier_b_data["huc2"] = tier_b_data["huc2"].astype(str).str.zfill(2)
```

If `huc2` is already a zero-padded string from the GAGES-II parquet, `astype(str)` on a NaN produces the literal string `"nan"`, then `zfill(2)` keeps it as `"nan"`. This means NaN HUC values become the string `"nan"` in the tier datasets. That **will** poison any downstream groupby or encoding.

**Fix:** Guard against NaN before converting:
```python
if "huc2" in tier_b_data.columns:
    huc = tier_b_data["huc2"]
    tier_b_data["huc2"] = huc.where(huc.isna(), huc.astype(str).str.zfill(2))
```

Or convert only non-null:
```python
mask = tier_b_data["huc2"].notna()
tier_b_data.loc[mask, "huc2"] = tier_b_data.loc[mask, "huc2"].astype(int).astype(str).str.zfill(2)
```

---

## 3. Type Safety in `attributes.py`

### BUG [SEVERITY: MEDIUM] -- `_safe_col` with `default=None` produces object Series, breaks arithmetic

When a GAGES-II column is missing, `_safe_col` returns:
```python
pd.Series(None, index=df.index)
```

This creates a Series of `None` (object dtype). When used in arithmetic like:
```python
out["other_landcover_pct"] = (
    100.0 - out["forest_pct"] - out["agriculture_pct"] - out["developed_pct"]
).clip(lower=0)
```

This line is safe because `forest_pct`, `agriculture_pct`, and `developed_pct` all use `default=0`, so they are numeric. The `None` default is only used for `geol_class`, `reference_class`, and `ecoregion` -- categorical columns that are never used in arithmetic. **No bug in current usage.**

However, this is fragile. If anyone later writes:
```python
out["some_ratio"] = _safe_col(df, "COL_A", None) / _safe_col(df, "COL_B", None)
```
they get a TypeError. The `_safe_col` contract should be documented: use `np.nan` for numeric columns, `None` only for categoricals.

### OBSERVATION [SEVERITY: LOW] -- `temp_range_c` with NaN operands

```python
out["temp_range_c"] = (
    _safe_col(df, "T_MAX_BASIN", np.nan) - _safe_col(df, "T_MIN_BASIN", np.nan)
)
```

If one column exists and the other doesn't, you get `value - NaN = NaN` for every row, which silently wipes out the range column. This is correct (missing data should propagate NaN), but if only one of the pair is absent in practice, you lose a feature that was half-available. Log a warning when this happens. Same applies to `relief_m`.

---

## 4. Integration Risk: `discrete.py` vs `assemble_dataset.py`

### BUG [SEVERITY: HIGH] -- Old dedup logic in `assemble_dataset.py` is weaker; switchover will change row counts

The old `load_discrete()` in `assemble_dataset.py` (line 154) deduplicates on `(datetime, ssc_value)` pairs:
```python
valid = valid.drop_duplicates(subset=["datetime", "ssc_value"], keep="first")
```

The new `deduplicate_discrete()` deduplicates on `datetime` alone, then resolves value conflicts. This means:

- **Old behavior:** Two rows with same datetime but different SSC values are both kept (different `(datetime, value)` tuples).
- **New behavior:** Two rows with same datetime but different SSC values -- only one is kept (USGS-preferred).

When you swap in the new loader, you will lose rows that the old loader kept. This is **intentionally better behavior** (the old code had a bug -- keeping conflicting measurements at the same timestamp creates nonsensical training data). But it means:

1. The output parquet row count will change.
2. Any cached model performance baselines computed with the old data are invalidated.
3. The downstream `align_samples()` function won't be affected structurally (it handles any number of discrete rows), but reproducibility breaks.

**Recommendation:** When wiring `discrete.py` into `assemble_dataset.py`, log the delta explicitly:
```
INFO: Dedup policy change: old kept N rows, new keeps M rows (-K conflict pairs removed)
```

### ISSUE [SEVERITY: MEDIUM] -- `load_ssc()` wrapper drops `hydro_event` column

The backward-compatible `load_ssc()` sets `include_hydro_event=False`. The old `load_discrete()` in `assemble_dataset.py` also does not preserve `hydro_event`. So this is backward-compatible. But the `align_site()` function in `assemble_dataset.py` expects exactly `["datetime", "ssc_value", "is_nondetect"]` -- and that's what `load_ssc()` returns. No issue today.

However, when you eventually want hydro_event in the training data (it's a valuable feature for storm-event flagging), you'll need to change `assemble_dataset.py` to call `load_discrete_param()` directly. Plan for this.

### ISSUE [SEVERITY: MEDIUM] -- `load_ssc()` non-detect matching is stricter

Old code (assemble_dataset.py line 125):
```python
non_detect_mask = df["Result_ResultDetectionCondition"] == "Not Detected"
```
Exact string match.

New code (discrete.py line 133):
```python
nd_mask = df["Result_ResultDetectionCondition"].astype(str).str.lower().str.contains("not detect", na=False)
```
Substring match, case-insensitive. This catches variants like "Not detected", "NOT DETECTED", "Result Not Detected", etc.

This is better, but it means more rows will be flagged as non-detect and get DL/2 substitution. SSC values will change for those rows. Again, baseline invalidation.

### ISSUE [SEVERITY: LOW] -- Column name divergence: `Org_Identifier` assumption

`deduplicate_discrete()` defaults `org_col="Org_Identifier"`. I checked -- WQP data uses `OrganizationIdentifier` (no underscore between Org and Identifier in some schemas) or `Org_Identifier` depending on the download format. If the parquet files were downloaded via `dataretrieval`, the column name depends on the WQP profile used. Verify this matches your actual parquet schema. If it doesn't match, the dedup silently falls back to "keep first" for all conflicts -- which hides the bug.

### OBSERVATION [SEVERITY: LOW] -- Detection limit column candidates differ

Old code checks: `DetectionQuantitationLimitMeasure_MeasureValue`, then `Result_DetectionQuantitationLimitMeasure`.

New code checks: `DetectionLimit_MeasureA`, then `DetectionQuantitationLimitMeasure_MeasureValue`, then `Result_DetectionQuantitationLimitMeasure`.

The new code adds `DetectionLimit_MeasureA` as first priority. This is fine if that column exists in some WQP profiles, but if it accidentally matches a column with different semantics, the DL values will be wrong. Verify against actual parquet files.

---

## Summary Table

| # | File | Issue | Severity | Type |
|---|------|-------|----------|------|
| 1 | qc.py | `nunique()` ignores NaN; dedup can keep NaN row over real measurement | HIGH | Bug |
| 2 | download_gagesii.py | `.dropna().astype(int)` chain works by accident via index alignment; dead `.where()` line | LOW | Code smell |
| 3 | attributes.py | `astype(str)` on NaN HUC produces literal `"nan"` string; poisons groupby/encoding | HIGH | Bug |
| 4 | assemble_dataset.py | Old dedup keeps conflicting rows; new dedup drops them -- baseline invalidation on switchover | HIGH | Integration |
| 5 | qc.py | `_safe_col` with `None` default is safe today but fragile for future arithmetic | MEDIUM | Design |
| 6 | discrete.py | Non-detect matching is stricter (substring vs exact); changes DL/2 substitution set | MEDIUM | Integration |
| 7 | discrete.py | `Org_Identifier` column name may not match actual WQP parquet schema | LOW | Integration |
| 8 | discrete.py | `DetectionLimit_MeasureA` added as DL candidate -- verify against actual data | LOW | Integration |

**Must-fix before merge:** Items 1 and 3 are data-corruption risks.
**Must-address before production run:** Item 4 (log the delta, re-baseline).
**Should-fix:** Items 5 and 6 (document behavior change, add guard).
