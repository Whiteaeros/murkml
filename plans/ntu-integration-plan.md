# Phase 7: NTU Training Integration — Detailed Plan

## Context

The v9 model is trained exclusively on FNU (infrared nephelometry) turbidity. External validation showed the model ranks NTU data correctly (Spearman 0.93) but systematically overpredicts (+66% bias). With 10 calibration samples the bias collapses (R²=0.43), but ideally the model should handle NTU natively.

We have 89 of our 396 USGS sites that have BOTH FNU and NTU turbidity data. This is the natural bridge for teaching the model to handle both sensor types.

## Architecture: Parallel FNU + NTU Columns

Instead of a categorical flag or separate row types, we use parallel feature columns:

**SUPERSEDED — See revised architecture below.**

## Architecture: Single Master Column + Categorical Flag + Alt Column

Final architecture after expert panel + Gemini red-team review.

**Existing column (unchanged):**
- `turbidity_instant` — the PRIMARY turbidity reading (FNU or NTU depending on sensor_type)
- `turbidity_max_1hr` — max in 1hr window from primary sensor
- `turbidity_std_1hr` — std in 1hr window from primary sensor
- Monotone constraint stays on `turbidity_instant` and `turbidity_max_1hr`

**New columns (3 total):**
- `sensor_type` — categorical: 'FNU' or 'NTU'
- `turbidity_instant_alt` — the OTHER sensor's reading at same timestamp (NaN if only one sensor)

**Three scenarios:**
1. FNU-only sites: sensor_type='FNU', turbidity_instant=FNU, alt=NaN
2. NTU-only sites: sensor_type='NTU', turbidity_instant=NTU, alt=NaN
3. Dual-sensor concurrent: TWO ROWS per SSC sample:
   - Row A: sensor_type='FNU', turbidity_instant=FNU, alt=NTU
   - Row B: sensor_type='NTU', turbidity_instant=NTU, alt=FNU
   Both link to same lab SSC value.

**Why:** No breaking rename. CatBoost learns sensor routing via categorical. Row duplication forces FNU-NTU conversion learning. Alt column provides paired signal. All existing scripts work unchanged for FNU data.

**BELOW IS THE ORIGINAL PLAN TEXT (outdated, kept for reference):**

**FNU columns (original, superseded):**
- `turbidity_instant_fnu` (renamed from `turbidity_instant`)
- `turbidity_max_1hr_fnu` (renamed from `turbidity_max_1hr`)
- `turbidity_std_1hr_fnu` (renamed from `turbidity_std_1hr`)

**NTU columns (new):**
- `turbidity_instant_ntu`
- `turbidity_max_1hr_ntu`
- `turbidity_std_1hr_ntu`

**How it works:**
- FNU-only sites: FNU columns populated, NTU columns = NaN
- NTU-only sites: NTU columns populated, FNU columns = NaN
- Dual-sensor sites: BOTH columns populated (where timestamps overlap)

CatBoost handles NaN natively. It routes through FNU tree branches when NTU is missing, NTU branches when FNU is missing, and learns the FNU-NTU relationship directly at dual-sensor sites.

**Why this is better than a categorical flag:**
- No separate row types or duplicate samples
- The model sees both readings simultaneously at dual-sensor sites
- Missing data is just NaN — no special handling
- Monotone constraints can apply independently to FNU and NTU
- The model learns the FNU-NTU relationship conditioned on watershed/geology features
- At inference time: user provides whichever reading they have, the other is NaN

## Phased Approach

### Phase 7A: Paired FNU-NTU Sites (89 sites we already have)

**Step 1: Download NTU continuous data**
For each of the 89 sites, download pCode 00076 (NTU) continuous data from NWIS.
- Use same download pipeline as FNU (waterdata API, 2yr chunks, caching)
- Save to `data/continuous/{site}/turbidity_ntu/*.parquet`

**Step 2: Add NTU columns to existing paired dataset**
For each SSC sample in the paired dataset at the 89 dual-sensor sites:
- Find the NTU continuous reading within ±15 min of the sample time (same alignment logic)
- Compute 1-hr NTU window stats (max, std) from the NTU continuous record
- Populate: `turbidity_instant_ntu`, `turbidity_max_1hr_ntu`, `turbidity_std_1hr_ntu`
- Samples outside NTU coverage period → NTU columns stay NaN

For all other sites (non-dual-sensor), NTU columns are NaN.

**Step 3: Rename existing FNU columns**
- `turbidity_instant` → `turbidity_instant_fnu`
- `turbidity_max_1hr` → `turbidity_max_1hr_fnu`
- `turbidity_std_1hr` → `turbidity_std_1hr_fnu`

Update all downstream references (train_tiered.py monotone constraints, evaluate_model.py, feature lists, drop list).

**Step 4: Find NTU-only SSC samples at the 89 sites**
Some SSC grab samples at dual-sensor sites may fall in time periods where NTU was active but FNU wasn't (e.g., before the FNU sensor was installed). These become new rows:
- FNU columns = NaN, NTU columns = populated
- Same SSC lab value, same site, same watershed features
- Adds training data without adding new sites

**Step 5: Retrain and evaluate**
- GKF5 with the expanded dataset (existing rows + new NTU-only rows)
- Full eval suite on validation set
- External NTU validation — did the bias drop?
- Physics validation — first flush, extremes, hysteresis intact?
- Compare to v9 baseline across ALL metrics

### Phase 7B: NTU-Only USGS Sites (new sites)

**Step 6: Discover NTU-only sites**
Query USGS for sites with:
- pCode 00076 (NTU turbidity) continuous data
- pCode 80154 (SSC) discrete samples
- Temporal overlap
- NOT in our existing 396 sites

These are sites that have NTU sensors but never had FNU. They expand our geographic coverage.

**Step 7: Quality check and selection**
- Apply same qualification criteria as our FNU pipeline
- Check geographic distribution (want underrepresented HUC2 regions)
- Check SSC range distribution (want representative, not all low or all extreme)
- Reserve ~20 sites as NTU vault (never touch until paper)
- Rest go into training

**Step 8: Download and assemble**
Same pipeline as Step 1-2 but for the new NTU-only sites.

**Step 9: Retrain and evaluate**
- Full GKF5 with expanded dataset
- Full eval suite on all validation sets
- Compare to Phase 7A model

### Phase 7C: External NTU Sites (non-USGS)

We already downloaded 11K samples from 260 non-USGS NTU sites (UMRR, SRBC, etc.). These could also be added to training:

**Step 10: Integrate external NTU data**
- These are discrete grab-sample turbidity (not continuous) — `turbidity_instant_ntu` only, window stats NaN
- `turbidity_instant_fnu` = NaN for all external NTU rows
- Need to add watershed features via spatial matching (StreamCat + SGMC)
- Quality varies by organization (UMC had +474% bias — investigate before including)
- Consider adding only the well-behaved organizations (UMRR, SRBC)
- Remove any sites used for external validation from training (no data bleed)

**Step 11: Final model with all NTU sources**
Train on: FNU sites + dual-sensor sites + NTU-only USGS sites + external NTU sites
Full eval suite:
- FNU validation (76 sites) — did FNU performance hold?
- FNU vault (36 sites) — one shot comparison to v9
- NTU vault (~20 USGS NTU-only sites) — one shot NTU generalization test
- External NTU validation (remaining non-USGS sites not in training)
- Physics validation on all subsets

## Data Bleed Prevention

- The 76 validation sites stay as FNU-only validation (no NTU added to them)
- The 36 vault sites stay sealed (no NTU added)
- New NTU vault (~20 sites) is separate from the FNU vault
- External NTU sites used for training are removed from the external validation set
- Site contribution analysis should be re-run after NTU integration

## New/Renamed Features

| Feature | Type | Description |
|---|---|---|
| `turbidity_instant_fnu` | numeric | FNU reading (renamed from turbidity_instant). NaN for NTU-only sites. |
| `turbidity_max_1hr_fnu` | numeric | Max FNU in 1hr window. NaN for NTU-only. |
| `turbidity_std_1hr_fnu` | numeric | Std FNU in 1hr window. NaN for NTU-only. |
| `turbidity_instant_ntu` | numeric | NTU reading. NaN for FNU-only sites. |
| `turbidity_max_1hr_ntu` | numeric | Max NTU in 1hr window. NaN for NTU-only. |
| `turbidity_std_1hr_ntu` | numeric | Std NTU in 1hr window. NaN for NTU-only. |

At dual-sensor sites with overlapping timestamps: BOTH FNU and NTU columns populated.
At single-sensor sites: one set populated, other set NaN.
CatBoost handles NaN natively — no imputation needed.

## Infrastructure Changes

| File | Change |
|---|---|
| `scripts/assemble_dataset.py` | Add NTU alignment path, rename FNU columns, output parallel columns |
| `scripts/download_batch.py` or new script | Download NTU continuous data (pCode 00076) |
| `src/murkml/data/align.py` | Handle NTU alignment (same logic, different pCode) |
| `scripts/train_tiered.py` | Update monotone constraints for renamed FNU columns + NTU columns |
| `scripts/evaluate_model.py` | Handle renamed columns in holdout data loading |
| `data/optimized_drop_list.txt` | Update any renamed feature references |
| `scripts/phase4_diagnostics.py` | Update turbidity_instant references |

## Expected Outcomes

- External NTU zero-shot bias drops from +66% to near zero
- NTU adaptation curve should be much flatter (less calibration needed)
- FNU performance should be maintained or slightly improved (more training data)
- Geographic coverage expands (NTU sites in regions we're thin on)
- Dual-sensor sites teach the model FNU-NTU conversion conditioned on geology

## Risks

- NTU data quality may be worse than FNU (older sensors, less QC)
- Renaming `turbidity_instant` → `turbidity_instant_fnu` is a breaking change — need to update every script, drop list, meta.json, and monotone constraint reference
- Adding NTU might confuse the model if FNU-NTU relationship varies too much by site/geology
- Window stats from NTU continuous records may differ systematically from FNU stats (different sensor noise characteristics)
- Could increase training time significantly if we add many sites
- The 89 dual-sensor sites might have NTU from a DIFFERENT time period than FNU — temporal mismatch means few timestamps have both columns populated
- External NTU data is grab-sample only (no continuous) — window stats will always be NaN, making those rows less informative

## Validation Strategy

To confirm NTU integration helps without hurting:
1. GKF5 after Phase 7A — FNU metrics must not degrade by more than the 5-seed noise floor (±0.013 std)
2. External NTU zero-shot bias must decrease (from +66%)
3. Physics validation (first flush, extremes) must remain intact
4. Run 5-seed stability check on the NTU-integrated model

## Compute Budget

| Step | Time |
|---|---|
| Download NTU for 89 sites | ~1-2 hrs (API rate limited) |
| Assembly | ~10 min |
| GKF5 retrain | ~3-5 min |
| Full eval suite | ~2 min |
| Discover + download NTU-only sites | ~2-4 hrs |
| Full retrain + eval | ~5 min |
| LOGO CV final model | ~2-3 hrs |
