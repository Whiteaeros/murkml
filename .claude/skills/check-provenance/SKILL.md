---
name: check-provenance
description: Verify that provenance tracking is being written correctly during pipeline work. Use when the user wants to make sure provenance is being maintained, after running pipeline scripts, after making code changes to the pipeline, or when the user says "check provenance", "is provenance being tracked?", or "are we logging the pipeline?"
effort: medium
---

# Provenance Compliance Check

You are verifying that the murkml pipeline's provenance tracking system is functioning correctly. Provenance means every pipeline run records what data went in, what processing happened, and what came out — with enough detail to reproduce and defend the results in a scientific paper.

## What to check

### 1. Does the provenance module exist?

Check for `src/murkml/provenance.py`. It should provide:
- `start_run(run_name)` — initializes a manifest with run_id, timestamp, git commit, environment
- `log_step(step_name, **kwargs)` — records a processing step (rows_in, rows_out, site_id, etc.)
- `log_file(path, role)` — records a file's SHA-256 checksum, row count, columns
- `end_run()` — finalizes and writes manifest to `data/provenance/`

If it doesn't exist yet, report that provenance tracking has not been implemented and refer to the plan at `C:\Users\kaleb\.claude\plans\frolicking-snacking-emerson.md` (Phase 3.8).

### 2. Are pipeline scripts instrumented?

Check each of these scripts for provenance calls (`start_run`, `log_step`, `log_file`, `end_run`):

| Script | Expected provenance calls |
|--------|--------------------------|
| `scripts/assemble_dataset.py` | start_run, log_step per site (qc, align), log_file for output parquet, end_run |
| `scripts/assemble_multi_param.py` | start_run, log_step per site per param, log_file for each output parquet, end_run |
| `scripts/train_tiered.py` | start_run, log_step per tier (data loading, training, evaluation), log_file for model + results, end_run |
| `scripts/download_data.py` | start_run, log_file for each downloaded parquet, end_run |
| `scripts/download_gagesii.py` | start_run, log_file for output parquet, end_run |

For each script, report:
- **Instrumented:** Has all expected provenance calls
- **Partial:** Has some but not all expected calls (list what's missing)
- **Not instrumented:** No provenance calls found

### 3. Are manifests being generated?

Check `data/provenance/` directory:
- Does it exist?
- How many manifest files are in it?
- When was the most recent manifest generated?
- Does the most recent manifest have a valid structure (run_id, started_at, steps, files)?

### 4. Are manifests accurate?

For the most recent manifest (if it exists):
- Pick 3 files listed in the manifest and verify their SHA-256 checksums match the current files on disk
- Pick 3 step records and verify the row counts are plausible (e.g., rows_out <= rows_in)
- Verify the git commit in the manifest matches a real commit in the repo
- Verify the environment versions are plausible

If checksums don't match, it means files were modified after the pipeline run — flag this as **STALE PROVENANCE**.

### 5. Coverage assessment

Check that the provenance system covers the full pipeline chain:

```
Download → QC → Align → Features → Attributes → Train → Evaluate
```

For each stage, is there at least one manifest that records:
- Input file(s) with checksums
- Processing parameters (window size, QC criteria, etc.)
- Output file(s) with checksums
- Row counts (in and out)

Report coverage as a percentage: "X of 7 pipeline stages have provenance coverage."

### 6. Recent work check

Look at `git log --oneline -20` for recent commits. For any commit that modified files in `scripts/` or `src/murkml/data/`:
- Was a new provenance manifest generated after that change?
- If pipeline scripts were modified, were the provenance calls updated to match?

Flag any pipeline code changes that don't have corresponding provenance updates.

## Report format

```
=== PROVENANCE COMPLIANCE CHECK ===
Date: [today]

Module:        [exists/missing]
Scripts:       [X/5 instrumented, Y/5 partial, Z/5 not instrumented]
Manifests:     [N files, most recent: DATE]
Accuracy:      [verified/stale/untested]
Coverage:      [X/7 pipeline stages]
Recent work:   [compliant/gaps found]

ISSUES:
- [list any problems found]

NEXT STEPS:
- [what needs to be done to reach full provenance coverage]
```

## Important Notes

- This check is read-only — do not modify any files
- If provenance is not yet implemented, that's expected in early phases — just report the gap clearly and point to the plan
- The goal is not perfection, it's progress — partial provenance is better than none
- If you find scripts that were recently modified without updating provenance, flag them specifically so the user can address it
