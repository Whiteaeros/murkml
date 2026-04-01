# Strategic Data Engineering Review: murkml Pipeline Readiness

**Reviewer:** Dr. Jenna Okafor — Data Engineering Specialist
**Date:** 2026-03-16
**Scope:** Pipeline robustness for Phases 3-6, missing infrastructure, reproducibility, and top priority improvement.

---

## 1. Is the pipeline robust enough for Phases 3-6?

**No. The current pipeline will not survive scope expansion.**

The pipeline works for the current 57-site, single-parameter (turbidity-SSC) case because every shortcut is invisible at this scale. Expanding to conductance-TDS, multi-sensor nutrient prediction, more sites, or LSTM training will expose structural problems:

**Phase 3 (new parameters):** The assembly script (`assemble_dataset.py`) hardcodes turbidity-SSC assumptions throughout. The `align_site()` function treats turbidity as the required primary sensor (line 209), the output parquet has column names like `turbidity_instant`, and `engineer_features()` assumes a single target variable. Adding conductance-TDS means either duplicating the entire assembly script or refactoring it into a parameter-agnostic pipeline. Right now there is no abstraction for "surrogate pair" -- the concept of (predictor sensor, target analyte) is baked into variable names and control flow rather than being a configurable entity.

**Phase 4 (LSTM):** The alignment module produces one row per grab sample -- a tabular format. LSTM training needs fixed-length time series windows from continuous data, aligned to grab sample timestamps. The current pipeline has no mechanism to emit a sequence of sensor readings per sample. This is a fundamentally different output shape and will require a parallel data path or a major refactor of `align.py`.

**Phase 3-4 (more sites):** The O(N*M) brute-force alignment in `align.py` (line 73-84) iterates over every discrete sample and scans the entire continuous record each time. At 57 sites and 17K samples this is tolerable. At 200+ sites or with 15-minute continuous records spanning 20 years per site, it will be painfully slow. Fix 23 (`pd.merge_asof`) is listed as minor but becomes a blocker at scale.

**Phase 5-6 (release/publication):** The feature engineering function `add_hydrograph_features()` re-reads continuous discharge parquet files from disk for every call (lines 67-78 of `features.py`). During assembly, the same discharge data was already loaded in `align_site()`. This means the same multi-GB data gets deserialized twice per site. For a published tool where users run the pipeline on their own data, this is a poor experience.

## 2. What infrastructure is missing?

**Configuration management.** There is no config file, no CLI argument parsing for the assembly script, and no way to change parameters (alignment window, QC thresholds, target analyte) without editing source code. The `CONTINUOUS_PARAMS` dict is duplicated in `assemble_dataset.py` and `download_diverse.py`. Before Phase 3, you need a single config source (YAML or dataclass) that defines the surrogate pair, QC bounds per parameter, and pipeline settings.

**Data versioning and lineage.** There is no record of which API calls produced the cached parquet files, when they were downloaded, what dataretrieval version was used, or what QC filters were applied. The download scripts cache aggressively (good for not re-downloading) but store no metadata. If you re-run assembly after fixing the timezone bug, there is no way to prove the output dataset differs from the previous one only because of the code change and not because upstream data changed. At minimum, write a `data/manifest.json` after each assembly run recording: git commit hash, assembly timestamp, per-site sample counts, and the hash of the output parquet.

**Pipeline orchestration.** The three-step workflow (download -> assemble -> train) is three separate scripts with no dependency tracking. There is nothing preventing someone from training on a stale dataset after changing the assembly logic. A simple Makefile or a `dvc.yaml` (DVC is free, lightweight, and designed for exactly this) would make the dependency chain explicit.

**Parameter-specific QC.** The `filter_continuous()` function applies a single generous bound (-0.01 to 100,000) regardless of which parameter it is filtering. The fix plan (Fix 8) specifies per-parameter bounds (turbidity 0-10K, discharge >= 0, DO 0-25, etc.) but the current implementation has no way to receive or dispatch on parameter identity. Before Phase 3 adds conductance and DO as primary predictors, this function needs a parameter argument.

**The buffer period bug (Fix 10) is still a TODO.** The code comments on lines 92-97 of `qc.py` acknowledge that the Ice/Mnt buffer logic is broken -- it needs the unfiltered data to find flag boundaries, but the implementation filters first and then has no reference to the original. This is not just a missing feature; it means post-Ice sediment release events (which are real and significant in your Idaho/Montana sites) are silently included in training data.

## 3. What would break for someone reproducing results?

**Everything except `pip install`.** Specifically:

1. **No pinned dependency versions.** `pyproject.toml` specifies `pandas>=2.0` and `dataretrieval>=1.1`. The dataretrieval API changed significantly between versions (the plan documents this). A new user installing today might get a different version with different API behavior. Add a `requirements-lock.txt` or use `pip freeze` output committed to the repo.

2. **No download automation for the dataset.** The cached parquet files in `data/` are gitignored (correctly), but there is no script that reproduces them from scratch. `download_data.py` and `download_diverse.py` require manual sequencing and the site catalog has to already exist. A reproducer would need to read the scripts, understand the order, and hope the USGS API returns the same data months later (it won't -- data gets reprocessed, approval statuses change, provisional data gets approved).

3. **The dataset itself is not published.** The fix plan mentions Zenodo (Phase 5) but until then, anyone reproducing needs 4.9 GB of API calls that take 28-37 hours. Publish the assembled parquet file (the output, not the raw cache) as a release artifact or on Zenodo now, before publication. This is the single easiest thing you can do for reproducibility.

4. **No random seed propagation to data assembly.** `train_baseline.py` sets `RANDOM_SEED = 42`, but the assembly script has no seed. If pandas or numpy change their default sort stability across versions, row ordering changes, and feature values computed from windows may differ slightly. This is unlikely to matter for CatBoost but would affect LSTM training.

5. **The `sys.path.insert(0, ...)` pattern in every script.** This makes the import chain fragile and dependent on the working directory. If someone runs `python scripts/assemble_dataset.py` from a different directory, imports fail. The package should be installed in editable mode (`pip install -e .`) and scripts should use installed imports.

## 4. Single most important data engineering improvement

**Build a dataset manifest and make assembly idempotent and diffable.**

After every assembly run, write a sidecar file (`data/processed/manifest.json`) containing:
- Git commit hash of the code that produced it
- Timestamp of the run
- Per-site sample counts (before and after QC, after alignment)
- Total row count and column list
- SHA-256 hash of the output parquet
- Key pipeline parameters (alignment window, QC thresholds, timezone handling version)
- dataretrieval package version

This is one function, maybe 30 lines. It solves three problems at once:

1. **After Round 1A fixes:** You can prove the timezone fix changed sample counts by comparing manifests before and after. The audit plan expects 20-40% sample loss -- the manifest makes this verifiable instead of anecdotal.

2. **For reproducibility:** Anyone can compare their assembly output to your published manifest and know immediately if their data matches.

3. **For Phase 3 expansion:** When you add conductance-TDS as a second surrogate pair, the manifest tracks both pipelines independently, so you can verify one did not regress while building the other.

This is lower-effort than any of the critical bug fixes and provides immediate value for every subsequent change. Do it before or alongside Round 1A, not after.

---

**Bottom line:** The pipeline is sound for its current narrow scope and the audit fix plan is well-prioritized. But the plan focuses entirely on correctness (the right thing to do first) and says nothing about the infrastructure needed to scale from "one-off research script" to "reproducible, multi-parameter toolkit." Before starting Phase 3, you need: a config system, a dataset manifest, per-parameter QC dispatch, and `merge_asof` alignment. None of these are hard. All of them prevent the kind of silent breakage that wastes weeks.
