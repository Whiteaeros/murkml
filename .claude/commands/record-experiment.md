# Record Experiment Results

You MUST run this after every experiment or model training run. No exceptions.

## Steps (do ALL of them, in order):

### 1. Gather information
Ask yourself or check the output for:
- Experiment label (e.g., "A1-auto_point", "D-rand-100", "v7-merf-categoricals")
- Model file path (if a model was saved)
- Key metrics: holdout R², median per-site R², pooled R², MAPE, within-2x
- What was tested (one sentence)
- Key finding (one sentence)

### 2. Update MODEL_VERSIONS.md
Open `MODEL_VERSIONS.md` in the murkml repo. Add a row to the Results Table at the bottom:

```
| {label} | {holdout_r2} | {med_site_r2} | {pooled_r2} | {mape} | {within_2x} | {one-line finding} | {date} |
```

If a new model version was created (not just an experiment), also add a full version entry in the Version History section.

### 3. Update EXPERIMENT_PLAN.md status
If this experiment was part of the experiment plan, update its Status from "NOT STARTED" to "COMPLETE" and fill in the Result field.

### 4. Git commit
Stage and commit the updated files plus any new model .cbm files:
```
git add MODEL_VERSIONS.md EXPERIMENT_PLAN.md data/results/models/*.cbm
git commit -m "Record experiment: {label} — {one-line finding}"
```

### 5. Verify
Read back the last 5 lines of the Results Table in MODEL_VERSIONS.md to confirm the entry is there.

## CRITICAL RULES
- NEVER skip this process. If you trained a model or ran an experiment, record it.
- NEVER overwrite a model .cbm file without first saving it under a versioned name.
- If you realize you forgot to record a previous experiment, go back and record it NOW before doing anything else.
