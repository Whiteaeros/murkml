# Zero-Regression Refactor: murkml Training Pipeline

## Context

The murkml codebase has been iterated through 11+ model versions with 84 scripts. Critical configuration (feature lists, drop lists) is scattered and inconsistent. The same bug (final model not respecting feature drops) was documented on 2026-03-28 and rediscovered on 2026-04-05. RESULTS_LOG has been wrong about feature counts — every prior agent reported v11 had 72 features when it actually had 137. We need a full structural refactor, but we CANNOT introduce silent regressions — this is a scientific pipeline where a dropped row or misaligned timestamp silently degrades model physics.

## The Problem That Triggered This

`train_tiered.py` (the only active training script) never loads `data/optimized_drop_list.txt`. Every older script in the project does. Result: v10 and v11 trained on 137 features instead of the curated 72. Additionally, `train_tiered.py` has duplicated feature selection logic — one path for CV, one for final model saving — and they diverge. This class of bug is architectural: it cannot be patched, only eliminated by removing the duplication.

## Strategy: 4-Phase Zero-Regression Migration

No "big bang" rewrite. Build new pipeline alongside old. Prove equivalence at every step. Only then replace.

---

## Phase 0: Pin Environment and Measure Reproducibility

### Step 0a: Freeze environment

```bash
pip freeze > data/golden_master/requirements_golden_master.txt
python --version > data/golden_master/python_version.txt
```

All golden master and validation scripts assert at startup:
```python
import catboost
assert catboost.__version__ == pinned_version, f"CatBoost version mismatch"
```

### Step 0b: Measure reproducibility delta

`scripts/measure_reproducibility.py` runs the surrogate model generation TWICE into temp directories, computes the maximum absolute difference between the two prediction sets, and writes `measured_reproducibility_delta` to `data/golden_master/manifest.json`. This happens BEFORE the canonical golden master run.

**Critical:** Both `measure_reproducibility.py` and `generate_golden_master.py` must call the SAME `_build_surrogate()` function (shared module or imported from the same file). The surrogate config (depth, iterations, thread_count, seed, stratified site selection) must NOT be duplicated across scripts — any drift means the measurement validates a different surrogate than the one the golden master actually uses.

Validation uses `atol = max(1e-10, 10 * delta)`. The 1e-10 floor protects against imperfect environment pinning (transitive dependency bumps, etc.), NOT BLAS parallelism (which thread_count=1 eliminates). With thread_count=1 and pinned seed, CatBoost's tree-building is sequential and deterministic at the bit level. If someone hits delta > 1e-10, investigate environment drift (library version mismatch), not BLAS noise.

### Step 0c: Generate canonical golden master

Only after reproducibility is measured, run `generate_golden_master.py` to produce the canonical artifacts.

**Critical: the golden master must instrument the ACTUAL legacy code, not reimplement it.**

Strategy: Use a wrapper script with `runpy.run_path()` to inject the interceptor before `train_tiered.py` executes. `PYTHONSTARTUP` does NOT work for non-interactive script execution (Python ignores it outside REPLs).

```python
# scripts/golden_master_wrapper.py
import golden_master_interceptor  # patches CatBoostRegressor.fit()
# Verify the patch is active BEFORE running legacy code
from catboost import CatBoostRegressor
assert CatBoostRegressor.fit is golden_master_interceptor.patched_fit, "Interceptor patch not active!"
import runpy
runpy.run_path("scripts/train_tiered.py", run_name="__main__")
```

The interceptor patches `CatBoostRegressor.fit()` to:
- Dump the training matrix (X, y, feature names) to disk for the FIRST fold, 3-5 deterministically-chosen middle folds, the LAST fold, and the final model (not all 261 calls — avoids disk explosion while catching mid-fold bugs)
- Hash X at the `.fit()` boundary for ALL calls (cheap in-memory op with `del` + `gc.collect()` after each hash to prevent OOM)
- Log `observed_fit_call_count` to the golden master manifest (used as expected value in future runs, not hardcoded)
- Post-run assertion: `assert call_count > 0` (catches interceptor bypass if legacy uses private training methods)

After the run completes, the golden master script reads the dumped matrices from disk.

Do NOT reimplement data loading. Do NOT use `sys.settrace`. The `runpy` approach is read-only for the legacy file and auditable.

The wrapper MUST assert CWD is the project root before calling `run_path()` (bare relative paths in legacy code resolve against CWD).

### Step 0d: Capture legacy lineage (NO legacy modification)

`train_tiered.py` doesn't emit lineage. The interceptor (Step 0c) captures the training matrix at `.fit()` boundaries. For earlier pipeline stages (post-load, post-split, post-merge), the golden master wrapper captures intermediate DataFrames by intercepting the data loading functions that `train_tiered.py` calls (e.g., `pd.read_parquet`, `build_feature_tiers`, the SGMC merge). The interceptor dumps these to temp files; `generate_golden_master.py` then computes lineage (shape, row counts, key hashes, per-feature non-null counts) from the snapshots.

**No exceptions to the "don't touch legacy files" rule.** All instrumentation is via monkey-patching in the wrapper's process, never modifying the legacy source.

---

## Phase 1: The Golden Master (Characterization Tests)

### What to capture

**Hash-only for upstream artifacts** (already on disk):
| Artifact | File | Capture |
|----------|------|---------|
| Paired dataset | `data/processed/turbidity_ssc_paired.parquet` | Deterministic DataFrame hash + shape + column list |
| StreamCat attributes | `data/site_attributes_streamcat.parquet` | Deterministic DataFrame hash |
| SGMC lithology | `data/sgmc/sgmc_features_for_model.parquet` | Deterministic DataFrame hash |
| Split assignments | `data/train_holdout_vault_split.parquet` | Deterministic DataFrame hash |

**Exported lightweight terminal artifacts:**
| Artifact | What | Validates |
|----------|------|-----------|
| Feature column list (ordered) | Exact ordered list passed to CatBoost `.fit()` | Feature selection logic |
| CV fold assignments | site_id per fold | Split logic |
| Surrogate holdout predictions | thread_count=1, 50 trees, depth=4, trained on full train set, predicted on holdout | `training/model.py` (final model path) |
| Surrogate CV OOF predictions | LOGO on first 10 sites only, thread_count=1, iterations=10 | `training/cv.py` (CV splitting, training, row recombination) |

**The CV surrogate is critical.** Without it, a refactored `cv.py` that scrambles fold assignments, drops a fold, or leaks data would pass validation. Running LOGO on 10-15 sites with 10 trees takes under 10 seconds and proves the splitting/recombination logic is correct.

**Site selection for CV surrogate must be stratified, not "first 10."** If the first 10 sites are all eastern US with `collection_method=auto_point`, the surrogate will never encounter other categorical values. The golden master script must use a custom greedy sampling function (NOT sklearn's `train_test_split(stratify=)`, which only supports single-label and fails when cross-sections have <2 members). The greedy sampler:
1. Iterates through required categorical values (collection_method × sensor_family × turb_source)
2. For each uncovered value, picks the first site (sorted by site_id as STRING — lexicographic, since USGS site IDs are strings like "USGS-01234567") that satisfies it
3. Continues until all values are covered
4. Pads to 10-15 sites with additional deterministic picks if needed

This covers:
- All `collection_method` values (auto_point, depth_integrated, grab, unknown)
- All `sensor_family` values (exo, ysi_6026, ysi_6series, unknown)
- All `turb_source` values (continuous, discrete, sciencebase_discrete)
- At least one site with missing values in common features

The selected site IDs are saved as `cv_site_ids.json` for reproducibility.

**Known limitations of the surrogate CV:**
1. Guarantees every categorical VALUE appears at least once, but NOT every categorical COMBINATION. If `sensor_family=ysi_6026` only co-occurs with `turb_source=discrete` in the real data, and the sampler covers each independently via different sites, the surrogate CV never sees that combination in a held-out fold. This is inherent to small surrogate sets.
2. The surrogate validates correctness of the CV ALGORITHM on small inputs (10-15 folds), NOT correctness at production scale (260 folds). Off-by-one errors at large fold counts, memory-pressure effects, etc. would survive Phase 4.
3. **Mitigation:** After the fast surrogate passes, run a ONE-TIME "medium surrogate" (50 sites, 30 iterations, depth=6, thread_count=1) before signing off on Phase 4. Run `measure_reproducibility.py` separately for the medium surrogate (its delta may differ from the small surrogate's). This catches scale-dependent bugs and behavioral richness issues without the full 260-fold cost.

### Deterministic DataFrame hashing

Parquet file hashing is NOT deterministic (metadata, compression, pyarrow version vary). `pd.util.hash_pandas_object()` hashes underlying memory representation, NOT logical values — it breaks on:
- **Categoricals:** Different internal category ordering → different hash even if string values match
- **Float precision:** float32 vs float64 → different hash for same logical value
- **Pandas/numpy version bumps** changing memory layout

The golden master must normalize before hashing:

```python
def hash_dataframe(df: pd.DataFrame) -> str:
    """Hash LOGICAL values, not memory layout."""
    df_norm = df.copy()
    # 1. Coerce categoricals to strings (eliminates internal code ordering)
    for col in df_norm.select_dtypes(include=["category"]).columns:
        df_norm[col] = df_norm[col].astype(str)
    # 2. Coerce object/categorical columns to string with strict null token
    #    Native NaN casts to literal "nan" which could collide with a real value.
    for col in df_norm.select_dtypes(include=["object"]).columns:
        df_norm[col] = df_norm[col].fillna("__MURKML_NULL__").astype(str)
    # 3. Normalize numeric NaN: hash both values and a null mask
    #    Don't use a sentinel value (-999999) — USGS/legacy data may already contain it.
    #    Instead: fill NaN with 0.0 for the value hash, and separately hash the null mask.
    #    Round to 8 decimals (float64-safe, preserves geochemistry precision).
    for col in df_norm.select_dtypes(include=["number"]).columns:
        df_norm[f"_mask_{col}"] = df_norm[col].isna().astype("float64")
        df_norm[col] = df_norm[col].fillna(0.0).astype("float64").round(8)
    # 4. Sort columns alphabetically
    df_norm = df_norm.reindex(sorted(df_norm.columns), axis=1)
    # 5. Sort rows by deterministic keys
    if "site_id" in df_norm.columns and "sample_time" in df_norm.columns:
        df_norm = df_norm.sort_values(["site_id", "sample_time"]).reset_index(drop=True)
    else:
        df_norm = df_norm.sort_values(list(df_norm.columns)).reset_index(drop=True)
    # 6. Assert no original columns start with _mask_ (collision guard)
    assert not any(c.startswith("_mask_") for c in df.columns), \
        f"Original columns starting with _mask_ would collide with null masks"
    # 7. Hash the normalized values
    return hashlib.sha256(
        pd.util.hash_pandas_object(df_norm, index=False).values
    ).hexdigest()
```

This hashes logical data equivalence, not memory-layout equivalence.

### `generate_golden_master.py`

Outputs to `data/golden_master/`:
- `manifest.json` — deterministic hashes of all upstream DataFrames, column lists, shapes, **dtypes per column** (catches float32→float64 drift), pinned library versions, `measured_reproducibility_delta`, `observed_fit_call_count`, sort keys used for each artifact (declared explicitly, not inferred)
- `feature_cols_ordered.json` — exact ordered list of features as passed to CatBoost `.fit()`
- `fold_assignments.json` — CV fold structure (site_id per fold)
- `lineage.json` — row counts at each pipeline stage (post-load, post-split, post-feature-selection), rows dropped per stage and reason
- `surrogate_holdout_predictions.parquet` — full-train surrogate, holdout predictions
- `surrogate_cv_oof_predictions.parquet` — stratified 10-15 site LOGO, OOF predictions
- `surrogate_holdout_model.cbm` + `surrogate_cv_model.cbm` — for reproducibility
- `cv_site_ids.json` — the stratified site IDs used for CV surrogate (deterministic)
- `meta_schema_hash.json` — hash of the `_meta.json` structure with non-deterministic keys removed (timestamps, file paths, build info). Load JSON → pop volatile keys → sort remaining keys → hash serialized string.
- `meta_parsed_values.json` — the PARSED meta values (feature list, transform params, BCF, categorical indices) as read by the evaluation pipeline. Validates that training/model.py and evaluate/holdout.py agree on the meta contract.
- `ACTUAL_FEATURE_COUNT.txt` — human-readable file stating the exact feature count (e.g., "ACTUAL FEATURE COUNT: 137"). Agents must reproduce this verbatim. Prevents future agents from "correcting" the count based on stale documentation.
- `adaptation_curve_golden.parquet` — adaptation curve output from the surrogate holdout evaluation. **Pre-requisite:** verify that the legacy `evaluate_model.py` already seeds its adaptation splits. If it doesn't, adaptation curve validation must be deferred to Phase 5 (it would be a behavioral change, not a reproduction). If it does seed, use the same seed and validate with same tolerance as predictions.

### `validate_golden_master.py`

**Process isolation:** `generate_golden_master.py` and `validate_golden_master.py` are completely separate processes. The new pipeline writes its outputs to `data/shadow_master/`. The validation script then loads ONLY the lightweight prediction parquets from `data/golden_master/` and `data/shadow_master/` to compare. It never holds legacy DataFrames, new DataFrames, and CatBoost pools in memory simultaneously.

Checks:
1. Upstream DataFrame hashes unchanged (logical equivalence via normalized hashing)
2. Feature column list matches (ordered 1:1 string comparison — see CatBoost ordering note below)
3. Surrogate holdout predictions match within empirically measured tolerance (see Determinism section) — **both DataFrames sorted by (site_id, sample_time), raw `.values` arrays compared** (eliminates index mismatch from pure functions that reset indices)
4. Surrogate CV OOF predictions match within same empirical tolerance — same sort-then-extract-values protocol
5. CV fold assignments identical
6. **Lineage row counts match** — new pipeline's `lineage.json` must report identical input/output row counts and drop counts as the golden master's lineage

**Array alignment protocol:** Before any `np.testing.assert_allclose()` call, both prediction DataFrames must be:
1. Sorted by `[site_id, sample_time]` 
2. Index reset with `reset_index(drop=True)`
3. Compared via `.values` arrays (not pandas Series, which carry index metadata)

---

## Phase 2: Architectural Audit

### Current data flow

```
assemble_dataset.py → turbidity_ssc_paired.parquet

train_tiered.py reads:
    turbidity_ssc_paired.parquet
    + site_attributes_streamcat.parquet
    + sgmc_features_for_model.parquet
    + train_holdout_vault_split.parquet
    → builds feature matrices
    → LOGO CV (260 folds) + final model save

evaluate_model.py reads:
    model .cbm + _meta.json + same data files
    → holdout predictions + adaptation + diagnostics
```

### Code smells

| Smell | Where | Impact |
|-------|-------|--------|
| Duplicated feature selection | `train_tiered.py` lines 719 vs 1294 | Same bug twice |
| Monolithic scripts | train_tiered.py 1,581 lines, evaluate_model.py 1,204 lines | Exceeds AI reasoning capacity |
| Scattered config | EXCLUDE_COLS in 15+ scripts, optimized_drop_list.txt, _MINIMAL_FEATURES, _DROP_FOR_PRUNED, hardcoded hyperparams | No single source of truth |
| Hidden side effects | `build_feature_tiers()` mutates DataFrames | Invisible to callers |
| No type hints | Most functions | AI agents guess wrong |
| Implicit unit assumptions | USGS data mixes CFS/CMS, FNU/NTU, mg/L | No enforcement |
| Dead code | 18 dead scripts, dead functions | AI agents follow dead paths |

---

## Phase 3: The "AI-Friendly" Target State

### Directory structure

```
src/murkml/
    config.py              # Pydantic models that validate YAML (<200 lines)
    data/
        fetch.py           # USGS API client (existing, untouched)
        qc.py              # QC filtering (existing, untouched)
        align.py           # Temporal alignment (existing, untouched)
        features.py        # Feature engineering (existing, untouched)
        attributes.py      # StreamCat/SGMC — FROZEN during migration. NOT archived: loader.py
                           #   imports load_streamcat_attrs() from it. Dead code (prune_gagesii, 
                           #   huc2 processing) removed AFTER Phase 4 validation, not before.
        discrete.py        # Discrete sample loading (existing, untouched)
        loader.py          # NEW: unified data loading. Internally separates concerns into
                           #   individually testable functions: load_data(), apply_split(), 
                           #   select_features(). If step 2 validation fails, you know which
                           #   function to debug.
    training/
        __init__.py
        cv.py              # LOGO CV loop — pure function
        model.py           # Final model train + save + SHAP — pure function
    evaluate/
        metrics.py         # (existing, untouched)
        holdout.py         # NEW: extracted from evaluate_model.py. Contains:
                           #   - predict_holdout(): load model, predict on holdout partition
                           #   - compute_metrics(): per-site and pooled metrics
                           #   - adaptation_curve(): N-sample adaptation across split modes
                           #   Stays in evaluate_model.py (moved to scripts/evaluate.py):
                           #   - CLI parsing, output file writing, report formatting
                           #   - External NTU validation (separate concern, future module)
                           #   - Disaggregated diagnostics (calls metrics.py, stays in CLI)

config/
    features.yaml          # THE source of truth for feature lists + hyperparams

scripts/
    train.py               # Thin CLI (<200 lines)
    evaluate.py            # Thin CLI (<200 lines)
    assemble.py            # RENAME of assemble_dataset.py (untouched)
    generate_golden_master.py   # imports _build_surrogate from golden_master_utils.py
    validate_golden_master.py
    measure_reproducibility.py  # imports _build_surrogate from golden_master_utils.py
    golden_master_utils.py      # shared: _build_surrogate(), hash_dataframe(), surrogate config
    archive/               # All dead scripts + legacy train_tiered.py + legacy evaluate_model.py
```

### Pydantic: validates YAML, doesn't hardcode content

Feature lists live in `config/features.yaml`. Pydantic validates structure at runtime. Adding a feature = editing YAML, not Python source.

```yaml
# config/features.yaml
version: "v12"

# Grouped by category (for human readability + Pydantic validation)
features:
  sensor:
    - turbidity_instant
    - turbidity_mean_1hr
    # ...
  categoricals:
    - collection_method
    - turb_source
    - sensor_family

# Explicit flat ordered list — THIS is what gets passed to CatBoost .fit()
# Copied from golden master's feature_cols_ordered.json for the legacy-reproducing run.
# Eliminates dependence on YAML parse ordering.
feature_order:
  - turbidity_instant
  - turbidity_mean_1hr
  # ... (exact legacy column order)

monotone_constraints:
  - turbidity_instant
  - turbidity_mean_1hr
  - turbidity_min_1hr
  - turbidity_max_1hr

exclude_cols:
  - site_id
  - sample_time
  - lab_value
  # ...

catboost:
  depth: 6
  learning_rate: 0.05
  l2_leaf_reg: 3
  iterations: 500
  early_stopping_rounds: 50
  boosting_type: Plain
  random_seed: 42
  thread_count: 5

transform:
  type: boxcox
  lambda: 0.2

units:
  # Declarative documentation of expected units at data boundaries.
  # NOT runtime-enforced in Phase 4 (that would be a behavioral change).
  # Phase 5+ can add runtime unit validation to loader.py data ingestion.
  turbidity: FNU
  discharge: CFS
  conductance: uS/cm
  temperature: degC
  dissolved_oxygen: mg/L
  ph: standard_units
  ssc: mg/L
```

```python
# src/murkml/config.py — schema only, content from YAML

class FeatureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")  # Unknown YAML keys → fatal error
    
    # Grouped by category (human readability + validation)
    sensor: list[str]
    temporal: list[str]
    weather: list[str] = []
    site: list[str] = []
    land_cover: list[str] = []
    soils: list[str] = []
    hydrology: list[str] = []
    surficial_geology: list[str] = []
    geochemistry: list[str] = []
    anthropogenic: list[str] = []
    sgmc_lithology: list[str] = []
    categoricals: list[str] = []

    # Explicit flat ordered list — THE authoritative column order for CatBoost .fit()
    # Copied from golden master's feature_cols_ordered.json.
    # Eliminates dependence on YAML parse ordering.
    feature_order: list[str]

    def _compute_grouped_set(self) -> set[str]:
        """VALIDATION-ONLY. Called by cross-validators, never in production."""
        grouped_list = (self.sensor + self.temporal + self.weather + self.site +
                        self.land_cover + self.soils + self.hydrology +
                        self.surficial_geology + self.geochemistry +
                        self.anthropogenic + self.sgmc_lithology + self.categoricals)
        # Check for duplicates WITHIN grouped fields (not just in feature_order)
        if len(grouped_list) != len(set(grouped_list)):
            dupes = [f for f in grouped_list if grouped_list.count(f) > 1]
            raise ValueError(f"Duplicate features in grouped fields: {set(dupes)}")
        return set(grouped_list)

    @property
    def all_features(self) -> list[str]:
        """Authoritative ordered feature list for CatBoost. Uses feature_order."""
        return list(self.feature_order)

    @model_validator(mode="after")
    def feature_order_matches_groups(self):
        """feature_order and grouped fields must describe EXACTLY the same features."""
        grouped = self._compute_grouped_set()
        ordered = set(self.feature_order)
        in_groups_only = grouped - ordered
        in_order_only = ordered - grouped
        if in_groups_only or in_order_only:
            raise ValueError(
                f"feature_order and grouped fields diverge. "
                f"In groups only: {in_groups_only}. In order only: {in_order_only}."
            )
        return self

    @model_validator(mode="after")
    def no_duplicates(self):
        dupes = [f for f in self.feature_order if self.feature_order.count(f) > 1]
        if dupes:
            raise ValueError(f"Duplicate features in feature_order: {set(dupes)}")
        return self

class ModelConfig(BaseModel):
    version: str  # Used as model output directory suffix (e.g., "v12" → model saved as *_v12.cbm)
    features: FeatureConfig
    monotone_constraints: list[str]
    exclude_cols: list[str]
    catboost: CatBoostConfig
    transform: TransformConfig
    units: USGSUnits = USGSUnits()

    @model_validator(mode="after")
    def monotone_constraints_exist(self):
        """Monotone constraints must reference features that actually exist."""
        missing = set(self.monotone_constraints) - set(self.features.all_features)
        if missing:
            raise ValueError(f"Monotone constraints reference unknown features: {missing}")
        return self

    @model_validator(mode="after")
    def no_excluded_features(self):
        """No feature should also be in exclude_cols."""
        overlap = set(self.features.all_features) & set(self.exclude_cols)
        if overlap:
            raise ValueError(f"Features also in exclude_cols: {overlap}")
        return self
```

### CatBoost column ordering guarantee

CatBoost's quantization bins can be sensitive to column order. The refactored pipeline MUST pass features to `.fit()` in the exact same order as the legacy pipeline. This is enforced by:

1. `config.FeatureConfig.all_features` returns features in a deterministic order (list concatenation, not set operations)
2. Golden master captures the exact ordered feature list from the legacy pipeline
3. Validation step asserts 1:1 ordered string match between legacy and new feature lists

### Pure functions

Every data transformation: DataFrame in → DataFrame out. No mutation. No side effects.

```python
def select_features(df: pd.DataFrame, config: FeatureConfig, *, allow_missing: bool = False) -> pd.DataFrame:
    """ONE code path for feature selection. Used by both CV and final model.
    
    RAISES ValueError if any configured feature is missing, unless allow_missing=True.
    Default is strict: callers must explicitly opt into partial feature sets.
    This prevents silent training on fewer features than configured.
    """
    available = [c for c in config.all_features if c in df.columns]
    missing = sorted(set(config.all_features) - set(df.columns))
    if missing and not allow_missing:
        raise ValueError(
            f"{len(missing)} configured features missing from data: {missing[:10]}..."
        )
    if missing:
        logger.warning(f"Missing {len(missing)} features (allow_missing=True): {missing}")
    return df[available].copy()  # .copy() prevents mutation
```

**Caller contract:** `select_features()` raises by default on missing features. The public API does NOT expose `allow_missing`. A separate `_debug_select_features(df, config)` function exists for development only, clearly marked as non-production. This prevents agents from passing `allow_missing=True` in production code under time pressure.

For **inference** on real-world data where a sensor feed is offline: the column must EXIST in the DataFrame but can contain NaN (CatBoost handles NaN natively). `select_features` raises if a column is absent — the fix is to add the column filled with NaN, not to suppress the error. `loader.py` (or a future `inference.py` wrapper) must include an explicit schema-enforcement step that pads missing sensor columns with NaN before calling `select_features()`:
```python
for col in config.features.all_features:
    if col not in df.columns:
        df[col] = np.nan  # Pad missing sensor with NaN for CatBoost
```

For production training and golden master validation: the public `select_features()` always raises on missing features.

### Post-merge null-rate check

`select_features()` catches absent columns but NOT all-NaN columns (a broken merge produces the column but fills it with NaN). `loader.py` must include a post-merge check on the GLOBAL dataset BEFORE splits (not per-CV-fold, since rare features may legitimately be all-NaN in a specific fold):
```python
for col in config.features.all_features:
    if col in df.columns and df[col].isna().all():
        raise ValueError(f"Feature '{col}' is all-NaN after merge -- likely a broken join")
```
**Partial merge detection:** In addition to the all-NaN check, lineage captures per-feature non-null counts at the `post_merge` stage. This makes a 40%-match vs 95%-match visible without configuring explicit thresholds (deferred to Phase 5). The golden master records baseline non-null counts; validation asserts they match.

### Row ordering guarantee

CatBoost's categorical target statistics (Ordered TS) are computed sequentially based on row order. Different `.merge()` paths can produce different row orderings. The loader MUST enforce a deterministic sort immediately before yielding data to training:

```python
# Assert no duplicate keys before sorting (duplicates make sort non-deterministic)
assert df.duplicated(subset=["site_id", "sample_time"]).sum() == 0, \
    f"Duplicate (site_id, sample_time) rows found — non-deterministic sort order"
df = df.sort_values(["site_id", "sample_time"]).reset_index(drop=True)
```

The golden master captures this exact row-sorted state. Validation verifies row order via the hash function (which sorts by the same keys). If duplicates exist, investigate and remove them (usually join artifacts) — do NOT use `lab_value` as a tie-breaker (target leakage into row ordering biases CatBoost's Ordered TS computation).

### Data lineage

Each step logs to a fixed JSON schema:

```json
{
  "post_load":   {"rows": 36341, "cols": 45, "dropped_count": 0, "dropped_keys_hash": null},
  "post_split":  {"rows": 23624, "cols": 45, "dropped_count": 12717, "dropped_keys_hash": "abc123...", "reason": "holdout_vault_exclusion"},
  "post_merge":  {"rows": 23624, "cols": 137, "dropped_count": 0, "dropped_keys_hash": null, "per_feature_nonnull": {"forest_pct": 23600, "sgmc_melange": 1842, "...": "..."}},
  "post_select": {"rows": 23624, "cols": 137, "dropped_count": 0, "dropped_keys_hash": null, "features_selected": 137}
}
```
NOTE: The golden master captures buggy behavior (137 features, not 72). `post_select.features_selected` will be 137 for the golden master and 137 for Phase 4 validation (reproducing the bug). Phase 5 changes this to the curated ~95 features. All numbers in this example are illustrative of the golden master state.

- `dropped_keys_hash` = hash of dropped rows' key columns via `hash_dataframe(df_dropped[["site_id", "sample_time"]])` (reuses the existing hash function; avoids OOM from string concatenation on large drops)
- Not just counts — a loader that drops the same NUMBER but DIFFERENT rows would pass count-only checks

Saved as `lineage.json` alongside model artifacts. Validation checks both counts AND key-set hashes.

---

## Phase 4: The Shadow Migration Execution

### Execution order

| Step | Module | Validates | Acceptance |
|------|--------|-----------|------------|
| 0 | Pin environment + `generate_golden_master.py` | N/A | Produces manifest, lineage, both surrogates, pinned requirements |
| 1 | `config.py` + `features.yaml` | `feature_cols_ordered.json` | Ordered list match (1:1 string) |
| 2 | `loader.py` | Manifest hashes + `lineage.json` row counts AND dropped-row key-set hashes | All hashes match; row counts AND key-set hashes at each stage match |
| 3 | `training/model.py` | `surrogate_holdout_predictions.parquet` | Predictions within `max(1e-10, 10*delta)` |
| 4 | `training/cv.py` | `surrogate_cv_oof_predictions.parquet` | OOF predictions within tolerance; fold assignments match |
| 5 | `scripts/train.py` | Steps 1-4 combined | Full surrogate validation passes |
| 6 | `evaluate/holdout.py` | Surrogate holdout preds + `adaptation_curve_golden.parquet` | Zero-shot metrics match within tolerance; adaptation curve matches within tolerance (all split modes seeded with seed=42 — deterministic). If ANY adaptation metric diverges, debug BEFORE proceeding. |
| 7 | `scripts/evaluate.py` | Steps 5-6 combined | Full validation passes |
| 7b | Medium surrogate (50 sites, 30 iter) | Own reproducibility measurement | Predictions match within `max(1e-10, 10*medium_delta)` — BLOCKING gate before archive |
| 8 | Archive dead code | No import breaks | (a) `python -c "import murkml"` succeeds; (b) `python -m modulefinder scripts/train.py` and `scripts/evaluate.py` confirm no transitive imports from `archive/`; (c) `grep -r "archive" src/ scripts/ --include="*.py"` as belt-and-suspenders; (d) manually check `attributes.py` for conditional imports; (e) dry-run `assemble_dataset.py --help` to confirm assembly pipeline still works; (f) `attributes.py` dead code removed but file stays in package |

**Steps 0-8 = Phase 4 (zero-regression). Step 8b = full-scale verification. Steps 9-11 = Phase 5 (intentional change).**

### Step 8b: Full-scale verification (overnight)

After surrogate validation passes, run the refactored pipeline with FULL LOGO (260 folds, thread_count=5) using the SAME 137 features as legacy. Compare CV metrics (R², KGE, etc.) against v11's documented LOGO metrics. They won't be bitwise identical (multithreaded), but should be statistically equivalent (within bootstrap CI). This step catches:
- Scale-dependent bugs that surrogates miss
- Float accumulation differences at production scale
- Any refactor artifact not covered by surrogates

**This step separates refactor effects from feature-change effects.** If metrics diverge here, the refactor introduced a regression. If they match here but diverge in Phase 5, the feature change is the cause.

---

## Phase 5: Apply Correct Feature Set (DELIBERATE CHANGE)

This phase intentionally breaks equivalence with the golden master. It is NOT part of the zero-regression migration.

| Step | Action | Acceptance |
|------|--------|------------|
| 9 | Update `features.yaml`: change version to "v12", update feature list to curated ~95 | Pydantic validation passes; version field differs from golden master; feature count matches intent |
| 10 | Train production v12 (LOGO, thread_count=5) | See Phase 5 validation below |
| 11 | (Optional) HP re-tuning sweep | If v12 metrics regress significantly vs v11 |

**HP retuning note:** Dropping from 137 to ~95 features changes the tree structure landscape. The v11 hyperparameters (depth=6, lr=0.05, l2=3) were tuned for 137 features — they may not be optimal for 95. If v12 metrics regress significantly, a targeted HP sweep (depth 4-8, learning_rate 0.03-0.10) is warranted before concluding the feature set change was harmful. Do not conflate "wrong hyperparams for fewer features" with "wrong features."

### Phase 5 Validation (post-intentional-change)

After step 10 trains v12, the golden master is no longer valid. Phase 5 needs its own checks:
1. Regenerate `ACTUAL_FEATURE_COUNT.txt` — manually verify against intended count
2. Check `lineage.json` `post_select.features_selected` matches expected count
3. Compare all metrics vs v11 — document deltas in RESULTS_LOG
4. **Generate a NEW golden master** from the v12 model — this becomes the v12 baseline for future work
5. Output files must be named `*_v12.cbm` (not `*_v11*`) — version field drives naming
6. **Generate a NEW golden master** for v12 into `data/golden_master_v12/` (separate directory). The Phase 0 golden master in `data/golden_master/` is NEVER overwritten — it serves as the audit trail for the refactor.

**Golden master protection:** 
- `generate_golden_master.py` is FROZEN after Phase 0. It instruments legacy `train_tiered.py` via `golden_master_wrapper.py`. After archiving, this script becomes unreproducible from source — that's OK, its output is the artifact.
- `generate_golden_master_v12.py` is a NEW script for Phase 5 that instruments `scripts/train.py` directly. It writes to `data/golden_master_v12/`.
- Both scripts refuse to overwrite an existing golden master directory unless `--force` is passed.
- Between Phase 0 and Phase 5, do NOT re-run `generate_golden_master.py`.

**Residual risk (partially-broken merges):** A StreamCat join that matches 40% of rows and leaves 60% as NaN would survive Phase 4's lineage validation (correct row count, correct key hashes) AND the all-NaN check (not ALL null, just mostly null). The surrogate predictions are the backstop — CatBoost behavior on mostly-NaN feature columns differs significantly from non-NaN, so the prediction hash would change. This chain is documented, not guaranteed. A configurable null-rate threshold check is deferred to Phase 5.

**The golden master encodes the 137-feature bug intentionally.** Steps 0-8 prove the refactored pipeline reproduces that buggy behavior exactly. Step 9 then fixes the bug by changing the YAML. This separation ensures we know the refactor didn't introduce any regressions — the only change in step 9 is the feature set, and any metric delta is attributable to that single cause.

### Legacy file mutation rule

**Do NOT modify any legacy file during migration.** This includes `attributes.py`. Create new clean logic in new files (`loader.py`, `training/model.py`, etc.). Once validation passes, legacy files get moved to `scripts/archive/` in their entirety. Never mutate legacy files during a shadow migration — a half-modified legacy file breaks both the old and new paths.

### Determinism guarantees

- **Environment pinned** via `requirements_golden_master.txt` — both generation and validation MUST use identical CatBoost/numpy/pandas versions (assert at startup)
- Both surrogates: `thread_count=1`, `random_seed=42`
- Holdout surrogate: 50 trees, depth=4, full training set
- CV surrogate: 10 trees, stratified 10-15 sites (covering all categorical values), LOGO
- Tolerance: **Empirically determined.** `measure_reproducibility.py` runs the surrogate twice on the same machine, measures max delta. Validation uses `atol = max(1e-10, 10 * delta)`. Never atol=0.0 (imperfect env pinning). Stored in `manifest.json`.
- **Single-machine execution:** All phases execute on Kaleb's local machine. No cloud/CI concerns.
- Production LOGO: `thread_count=5`, NOT expected to be bitwise reproducible, NOT part of golden master
- **Generation and validation are separate processes** — the invariant is: **write all outputs to disk between scripts, load from disk in validation, never pass objects in memory.** No PID checks (easily circumvented). The file-boundary is the guarantee.
- `delta=0` from `measure_reproducibility.py` is EXPECTED and correct (thread_count=1, pinned seed, same machine). The `max(1e-10, ...)` floor exists solely for transitive dependency drift, not because variance is expected.

### Rollback criteria

If any Phase 4 step fails validation:
1. **Do NOT debug the golden master.** Assume the golden master is correct.
2. **Debug the new module.** The failure is in the refactored code.
3. **If the failure is in the tolerance** (e.g., predictions differ at 1e-9 but not 1e-8): re-run `generate_golden_master.py` twice to measure true reproducibility delta. Adjust tolerance only if empirically justified.
4. **If validation fails and the cause isn't obvious, use the diagnostic protocol:**
   - Re-run both pipelines with `--diagnostic` flag, which dumps intermediate DataFrames at each stage (post-load, post-split, post-merge, post-select, pre-fit) to `data/diagnostics/{legacy,new}/`
   - Diff column-by-column at each stage to identify the FIRST point of divergence
   - Trace the divergent operation to a specific function call
   - The diagnostic mode must be tested during Phase 0 (confirm the legacy diagnostic dump works before you need it for debugging)
5. **If you cannot identify the specific line of code that diverges after the diagnostic protocol:** Stop. Reset to legacy pipeline. Re-examine whether the golden master correctly captured the legacy behavior, or whether the module boundary is wrong.
6. **Never skip a validation step.** Never mark a step as "close enough."

---

## What NOT to Do

- Do NOT start writing refactored code before this plan is approved
- Do NOT delete or modify legacy files before shadow run proves equivalence
- Do NOT touch v11 model artifacts (immutable)
- Do NOT change data assembly pipeline (assemble_dataset.py untouched)
- Do NOT train a production model until refactor validated (step 8 complete)
- Do NOT conflate "reproducing current behavior" with "fixing feature count" — separate steps
- Do NOT hardcode feature names in Python source — they live in YAML
- Do NOT hash parquet files directly — use normalized DataFrame hashing (coerce categoricals to str, enforce float64)
- Do NOT run full LOGO CV for golden master — use stratified 10-15 site, 10-tree surrogate
- Do NOT assume a tolerance — measure it empirically by running golden master generation twice
- Do NOT run golden master generation and shadow validation in the same process — separate processes, write to disk, compare on disk
- Do NOT bump library versions between golden master generation and shadow validation

## Parallelization Strategy

The modular design enables parallel agent execution. After Phase 0 (golden master generation), several steps can be worked on simultaneously:

**Parallel batches (all agents on same hardware as Phase 0):**
1. Phase 0: Generate golden master (single agent, sequential)
2. Batch 1 (parallel): `config.py` + `features.yaml` | unit test scaffolding
3. Batch 2 (sequential): `loader.py` (imports config — must wait for Step 1)
4. Batch 3 (parallel): `training/cv.py` | `training/model.py` — both import from config + loader, so both depend on Batch 2. Build to the config interface from the start (not raw feature lists) to avoid interface swaps in Step 5.
5. Batch 4 (sequential): `scripts/train.py` + validation of steps 1-5
6. Batch 5 (parallel): `evaluate/holdout.py` | archive dead scripts
7. Batch 6 (sequential): `scripts/evaluate.py` + full validation

**Interface contract:** Each agent gets the golden master artifacts, the relevant plan section, the Pydantic schema (from Step 1), and the `loader.py` API (from Step 2). Agents in Batch 3+ must import from `config` and `loader` — no raw feature lists, no bypassing the config system.

**All execution on same local machine.** No hardware parity concerns.

## Unit Tests for Pure Functions

Each new module gets a corresponding test file in `tests/`:
- `tests/test_config.py` — validate YAML loading, cross-validators, feature_order matching
- `tests/test_loader.py` — test `load_data()`, `apply_split()`, `select_features()` individually; include an integration test that calls `load_streamcat_attrs()` in isolation, hashes its output, and compares to the golden master manifest hash (catches attributes.py side effects)
- `tests/test_cv.py` — test fold generation, OOF recombination, data leakage checks
- `tests/test_model.py` — test surrogate training produces expected output shape
- `tests/test_boundaries.py` — **AST-based linter**: asserts that `scripts/train.py` and `scripts/evaluate.py` do NOT call `pd.read_parquet()`, `yaml.safe_load()`, or define feature lists. Forces agents to use the `loader` and `config` APIs instead of reimplementing inline.

These are fast unit tests (no real data, use synthetic fixtures). The golden master is the integration test. Unit tests catch agent-generated code errors at the function level before integration.

`_debug_select_features()` lives in `tests/helpers.py`, NOT in `loader.py`. It is only importable from test files. Production code has no path to it.

## Script Inventory (the other 64 scripts)

The plan archives ~20 scripts and creates ~6 new ones. The remaining ~58 scripts fall into:
- **Data download** (~18): One-off or periodic USGS data fetching. Not part of training pipeline. Leave as-is.
- **Data assembly** (~5): `assemble_dataset.py`, `assemble_extreme_sites_fullssc.py`, etc. Not refactored in this plan. **Future refactor** should apply same golden master pattern.
- **Analysis/diagnostics** (~15): `error_analysis.py`, `bootstrap_holdout_ci.py`, `ols_benchmark.py`, etc. Reference scripts, not pipeline-critical. Leave as-is.
- **Dashboard** (~5 in `dashboard/_scripts/`): Reads eval outputs. After Phase 5, update `EVAL_PREFIX` in `data_prep.py` to point to v12 eval files, then dry-run `python dashboard/_scripts/data_prep.py` to verify no import errors from archived modules and no missing eval files.
- **Other utilities** (~15): Site qualification, gap analysis, STN queries, etc. Leave as-is.

**Protocol for agents encountering unaddressed scripts during Phase 4:** Treat as read-only reference. Do not import from them. Do not modify them. If a script appears to be part of the active pipeline, flag it for review before proceeding.

## Data Pipeline Awareness

The data assembly pipeline (`assemble_dataset.py` → `turbidity_ssc_paired.parquet`) is NOT refactored in this plan. However:
1. The golden master hashes `turbidity_ssc_paired.parquet` to detect any accidental changes
2. `loader.py` reads from the assembly pipeline's output — the interface contract is: "parquet with expected columns and dtypes"
3. A future assembly refactor should follow the same golden master pattern: snapshot the current parquet, refactor assembly, prove output matches
4. `loader.py`'s pure functions should be designed so that assembly pipeline changes (new columns, renamed columns) are caught by `select_features()` raising on missing features, not silently accepted

## Dependencies to Add

- `pydantic` — config validation
- `pyyaml` — YAML parsing

## Estimated Scope

| Component | New Lines | Legacy Lines Archived |
|-----------|-----------|----------------------|
| `config.py` | ~150 | — |
| `features.yaml` | ~120 | — |
| `loader.py` | ~150 | — |
| `training/cv.py` | ~200 | — |
| `training/model.py` | ~200 | — |
| `scripts/train.py` | ~200 | ~1,581 (train_tiered.py) |
| `scripts/evaluate.py` | ~200 | ~1,204 (evaluate_model.py) |
| Golden master scripts (generate, validate, measure_reproducibility) | ~500 | — |
| Archive move | — | ~8,000+ (18 dead scripts) |
| **Total** | ~1,720 new | ~10,785 archived |
