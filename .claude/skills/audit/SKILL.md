---
name: audit
description: Run a full data pipeline audit for the murkml project. Use when the user wants to verify data integrity, validate model results, check provenance, generate a sample funnel, or prepare audit documentation for paper submission. Also use when the user says "audit", "validate the pipeline", "check the data", or "are the results trustworthy?"
effort: high
---

# murkml Pipeline Audit

You are auditing the murkml water quality surrogate modeling pipeline. Your job is to verify that the data, models, and reported results are correct and trustworthy — suitable for publication in a peer-reviewed journal.

Run the checks below **in order**. Report results as PASS/FAIL with evidence. Do not skip checks. Do not assume anything is correct — verify it.

## Pre-audit: Read the current state

1. Read `PIPELINE.md` for the expected pipeline structure
2. Read `RESULTS_LOG.md` for the claimed results
3. Read `CLAUDE.md` for data integrity rules

## Part A: Data Integrity Checks

### A1. GAGES-II Schema Validation
- Load `data/site_attributes_gagesii.parquet` — verify it has **pruned** column names (`forest_pct`, `geol_class`, etc.), NOT raw names (`FORESTNLCD06`)
- Load `data/site_attributes_gagesii_full.parquet` — verify it has **raw** column names
- Verify `geol_class`, `ecoregion`, `reference_class` are dtype `object` (string), not float64
- Verify `forest_pct` contains real values (not all zeros, not all NaN)
- **Report:** column counts, dtypes of categoricals, sample of values

### A2. Paired Dataset Validation
For each parquet in `data/processed/` (`turbidity_ssc_paired.parquet`, `total_phosphorus_paired.parquet`, etc.):
- Count rows and unique sites. Compare to expected counts in RESULTS_LOG.md
- Verify `turbidity_instant` is never NaN (required for primary match)
- Verify `match_gap_seconds` <= 900 (15 min) for all rows
- Verify no duplicate `(site_id, sample_time)` pairs
- Verify `lab_value` > 0 for all rows (or == 0 for SSC non-detects only)
- Verify target log transform: `np.log1p(lab_value)` matches the log column exactly
- **Report:** site counts, sample counts, NaN rates per feature column

### A3. Feature Sanity Checks
- `doy_sin`, `doy_cos`: must be in [-1, +1] exactly
- `rising_limb`: must be 0 or 1 only
- `Q_ratio_7d`: should be centered roughly around 1.0 (compute median)
- `turb_Q_ratio`: should be > 0 where both turbidity and discharge are non-NaN
- No feature column should have zero variance (all identical values)
- No feature column should be 100% NaN
- **Report:** summary stats for each feature, flagged columns

### A4. Model Metadata Integrity
For each `*_meta.json` in `data/results/models/`:
- `n_sites` and `n_samples` must match actual training data
- `feature_cols` must match features in the paired parquet
- For Tier C models: `cat_cols` should list all 4 categoricals (`geol_class`, `ecoregion`, `reference_class`, `huc2`)
- `sites_per_ecoregion` and `sites_per_geology` should be non-empty for Tier C
- `feature_ranges` should have no NaN min/max values
- **Report:** per-model summary of features, categoricals, site/sample counts

### A5. Training/Holdout Contamination Check
- Load the training parquet (`turbidity_ssc_paired.parquet`)
- Load or identify the holdout site IDs from `scripts/run_external_validation.py`
- Verify **zero overlap** between training site IDs and holdout site IDs
- **Report:** training site count, holdout site count, overlap count (must be 0)

### A6. Raw Data Cache Check
- Scan `data/discrete/*.parquet` for files < 1KB (possible cached API failures)
- Scan `data/continuous/*/*/*.parquet` for files < 1KB
- **Report:** count of suspicious files, list of flagged paths

## Part B: Provenance Report

If `data/provenance/` exists and contains manifest files, generate a provenance report:

### B1. Sample Funnel Table
For each parameter (SSC, TP, nitrate, orthoP), trace the sample count at each stage:
- Raw discrete samples (count files in `data/discrete/`)
- After QC filtering
- After alignment (±15 min window)
- After feature engineering
- Final paired dataset row count

Present as a table:
```
Parameter: SSC (N sites)
Step                  | Rows In  | Rows Out | Dropped | Drop %
Raw discrete samples  |          |          |         |
  QC filter           |          |          |         |
  Alignment (±15 min) |          |          |         |
Final paired dataset  |          |          |         |
```

If manifests don't exist yet, compute what you can directly from the parquet files and note which steps can't be reconstructed without provenance logging.

### B2. File Checksums
Compute SHA-256 for all parquet files in `data/processed/` and `data/results/`. If manifest checksums exist, compare them. Flag any mismatches.

### B3. Environment Snapshot
Report: Python version, pandas version, catboost version, numpy version, OS, git commit hash, random seed (should be 42).

### B4. Data Source Summary
For each data source, report: number of sites, number of raw files, date range of data, and total file size.

### B5. Methods Section Draft
Based on the verified numbers from Parts A and B, generate a paragraph suitable for a scientific paper's Methods section. Include:
- Number of monitoring sites and geographic extent
- Data sources (USGS Water Data API, GAGES-II, NLCD)
- QC criteria applied
- Alignment window and match rate
- Final sample counts per parameter
- Model type and cross-validation strategy
- Use precise numbers from the audit, not approximations

## Part C: Summary

End with a clear summary:
```
=== MURKML PIPELINE AUDIT ===
Date: [today]
Git commit: [hash]

VALIDATION: X/Y checks passed, Z failed
[list each check with PASS/FAIL]

PROVENANCE: [complete/partial/missing]
[status of manifest files]

RECOMMENDED ACTIONS:
[list anything that needs fixing]
```

## Important Notes

- Use Python via notebook or script execution to run checks — do not eyeball parquet files
- Always load parquets with pandas and verify programmatically
- If a check fails, explain specifically what's wrong and what the expected value was
- Do not modify any data files during the audit — this is read-only
- If `$ARGUMENTS` contains "quick", skip Part B (provenance) and just run Part A (validation)
