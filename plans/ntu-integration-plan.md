# Phase 7: NTU Training Integration — Detailed Plan

## Context

The v9 model is trained exclusively on FNU (infrared, pCode 63680) continuous turbidity. External validation showed the model ranks NTU data correctly (Spearman 0.93) but systematically overpredicts (+66% bias). We want the model to handle NTU natively.

## Critical Finding: No Continuous NTU Exists at USGS

Per USGS TM 2004.03, turbidity reporting was split by sensor type:
- **Continuous sondes = FNU** (pCode 63680, ISO 7027, infrared) — all modern in-situ sensors
- **Discrete lab/field = NTU** (pCode 00076, EPA 180.1, white light) — grab samples only

We verified: zero continuous NTU (pCode 00076) IV data exists across 15 states and all turbidity pCodes. This is by design since 2004.

**What NTU data exists:**
- 89 of our 396 sites have discrete NTU grab samples (from hydrographer site visits)
- 260 external non-USGS sites have discrete NTU grab samples (UMRR, SRBC, etc.)
- All NTU is single readings per visit — no continuous time series, no window stats

## Architecture: Single Master Column + Categorical Flag + Alt Column

(After expert panel + Gemini red-team review)

**Existing columns (unchanged):**
- `turbidity_instant` — PRIMARY turbidity reading (FNU or NTU depending on sensor_type)
- `turbidity_max_1hr` — max in 1hr window (NaN for NTU rows — no continuous record)
- `turbidity_std_1hr` — std in 1hr window (NaN for NTU rows)
- Monotone constraint stays on `turbidity_instant` and `turbidity_max_1hr`

**New columns (2):**
- `sensor_type` — categorical: 'FNU' or 'NTU'
- `turbidity_instant_alt` — the OTHER sensor's reading at same sample time (NaN if only one)

**Row types:**
1. **Existing FNU-SSC rows (35,209):** sensor_type='FNU', turbidity_instant=continuous FNU, window stats populated, turbidity_instant_alt=NaN (unless NTU discrete reading exists at same timestamp)
2. **New NTU-SSC rows:** sensor_type='NTU', turbidity_instant=discrete NTU, window stats=NaN, turbidity_instant_alt=continuous FNU reading at same time (if available)
3. **At 89 dual sites where SSC + NTU + FNU all coincide:** TWO ROWS per sample:
   - Row A: sensor_type='FNU', turbidity_instant=FNU, turbidity_instant_alt=NTU (window stats from FNU)
   - Row B: sensor_type='NTU', turbidity_instant=NTU, turbidity_instant_alt=FNU (window stats=NaN)
   Both link to same lab SSC value.

## Phase 7A: Paired NTU Data at 89 Dual-Sensor Sites

### Step 1: Download discrete NTU data (pCode 00076)
For each of the 89 sites, download discrete NTU samples from WQP.
- Use same pattern as `download_discrete_turbidity.py` but with pCode 00076
- Filter to NTU units, Sample-Routine activity type
- Parse timestamps to UTC
- Save to `data/discrete/{site}_turbidity_ntu.parquet`
- Use RDB format / batch queries for efficiency

### Step 2: Pair NTU with SSC
For each NTU discrete sample, find the matching SSC lab sample:
- Match by site_id + date (same-day visit by hydrographer)
- The hydrographer collects NTU field reading AND SSC bottle at the same visit
- This gives NTU-SSC pairs

### Step 3: Add FNU context to NTU-SSC pairs
For each NTU-SSC pair, find the continuous FNU reading at the same timestamp:
- Use existing FNU continuous data in `data/continuous/{site}/`
- Same ±15 min alignment as our FNU-SSC pairing
- This gives: NTU grab sample + SSC lab value + FNU continuous reading = the FNU-NTU-SSC triplet
- `turbidity_instant` = NTU, `turbidity_instant_alt` = FNU

### Step 4: Annotate existing FNU-SSC pairs with NTU
For existing FNU-SSC paired rows at the 89 sites:
- Find if a discrete NTU reading exists within ±1 hour of the SSC sample
- If yes: populate `turbidity_instant_alt` = NTU value
- This enriches existing rows without adding new ones

### Step 5: Create row-duplicated training data
At timestamps where FNU + NTU + SSC all exist:
- Row A: sensor_type='FNU', turbidity_instant=FNU, alt=NTU, window stats from FNU
- Row B: sensor_type='NTU', turbidity_instant=NTU, alt=FNU, window stats=NaN
- Both link to same SSC

### Step 6: Add sensor_type to ALL existing rows
All current 35,209 rows get `sensor_type='FNU'` and `turbidity_instant_alt=NaN` (unless Step 4 found an NTU match).

### Step 7: Retrain and evaluate
- GKF5 with expanded dataset
- Full eval suite on validation set
- External NTU validation — did the bias drop?
- Physics validation — first flush, extremes, hysteresis intact?
- Compare to v9 baseline across ALL metrics

## Phase 7B: Discover NTU-Only SSC Sites

Sites that have discrete NTU + discrete SSC but NO continuous FNU. These are typically older sites pre-dating FNU standardization.

### Step 8: Query WQP for sites with both NTU and SSC
- characteristicName='Turbidity' with NTU units + characteristicName='Suspended Sediment Concentration'
- Provider: NWIS (USGS)
- Exclude our existing 396 sites
- Check geographic and SSC range distribution

### Step 9: Quality check and selection
- Minimum sample count (≥10 paired NTU-SSC)
- Geographic diversity (prioritize underrepresented HUC2 regions)
- SSC range diversity
- Reserve ~20 as NTU vault

### Step 10: Download and assemble
- Download NTU + SSC discrete data for new sites
- Pair by same-day visit
- No FNU continuous data available → turbidity_instant_alt=NaN, window stats=NaN
- Add watershed features (StreamCat + SGMC)

## Phase 7C: External NTU Sites (non-USGS)

Already downloaded 11K samples from 260 non-USGS sites.

### Step 11: Integrate external NTU
- These are discrete grab-sample NTU — same as Phase 7B rows
- sensor_type='NTU', window stats=NaN, turbidity_instant_alt=NaN
- Add watershed features via spatial matching
- Cap at 20% of NTU training rows (Krishnamurthy recommendation)
- Keep UMRR entirely out of training as clean NTU validation (Rivera recommendation)

### Step 12: Final retrain and full eval suite

## Data Bleed Prevention

- 76 FNU validation sites: add sensor_type='FNU' but NO NTU data. Historical benchmark unchanged.
- 36 FNU vault sites: sealed. No changes.
- ~20 NTU vault sites: selected in Step 9, sealed immediately.
- UMRR (9,625 samples): reserved for external NTU validation, not training.
- Site contribution analysis should be re-run after NTU integration.

## New Features

| Feature | Type | Description |
|---|---|---|
| `sensor_type` | categorical | 'FNU' or 'NTU' |
| `turbidity_instant_alt` | numeric | Other sensor's reading (NaN if unavailable) |

## Infrastructure Changes

| File | Change |
|---|---|
| `scripts/assemble_dataset.py` | Add sensor_type column, NTU pairing path |
| `scripts/download_discrete_ntu.py` | NEW — download pCode 00076 discrete NTU |
| `scripts/train_tiered.py` | sensor_type as new categorical |
| `scripts/evaluate_model.py` | Handle sensor_type in holdout loading |
| `data/optimized_drop_list.txt` | No changes needed (no renames) |

## Compute Budget

| Step | Time |
|---|---|
| Download NTU discrete for 89 sites | ~15 min (batch WQP query) |
| Pair NTU-SSC + FNU alignment | ~10 min |
| GKF5 retrain | ~3-5 min |
| Full eval suite | ~2 min |
| Discover NTU-only sites (7B) | ~30 min |
| Download + assemble new sites | ~1-2 hrs |
| Final LOGO CV | ~2-3 hrs |
