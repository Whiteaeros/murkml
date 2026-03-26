# murkml Data Pipeline

How raw USGS data becomes an ML-ready dataset. Read this before running anything.

---

## Overview

```
Download  -->  QC  -->  Align  -->  Features  -->  Attributes  -->  Train
```

Each step has a script. They run in order. Skipping a step will break the next one.

---

## Step 1: Download Raw Data

**Scripts:** `download_data.py`, `download_diverse.py`, `download_expansion_sites.py`, `download_discrete_params.py`

**What it does:**
- Pulls continuous sensor data (15-min interval) from USGS waterdata API
- Pulls discrete lab samples (grab samples, irregular timing) from the same API
- Stores everything locally so we never re-download

**Continuous sensors pulled (per site):**

| Parameter | pcode | Stored as |
|-----------|-------|-----------|
| Turbidity (FNU) | 63680 | `data/continuous/{site_id}/63680/*.parquet` |
| Specific conductance | 00095 | `data/continuous/{site_id}/00095/*.parquet` |
| Dissolved oxygen | 00300 | `data/continuous/{site_id}/00300/*.parquet` |
| pH | 00400 | `data/continuous/{site_id}/00400/*.parquet` |
| Temperature | 00010 | `data/continuous/{site_id}/00010/*.parquet` |
| Discharge | 00060 | `data/continuous/{site_id}/00060/*.parquet` |

Continuous data is chunked into 3-year windows because the API has row limits.

**Discrete lab samples pulled (per site):**

| Parameter | pcode | Stored as |
|-----------|-------|-----------|
| Suspended sediment (SSC) | 80154 | `data/discrete/{site_id}_ssc.parquet` |
| Total phosphorus | 00665 | `data/discrete/{site_id}_total_phosphorus.parquet` |
| Nitrate+nitrite | 00631 | `data/discrete/{site_id}_nitrate_nitrite.parquet` |
| Orthophosphate | 00671 | `data/discrete/{site_id}_orthophosphate.parquet` |

**Rate limits:** USGS allows 1000 requests/hour with an API token (`API_USGS_PAT` env var). Scripts track remaining requests and pause if needed.

**How to verify:** Check `data/continuous/` has a folder per site, and `data/discrete/` has parquet files per site+parameter. Currently ~124 site folders.

---

## Step 2: Quality Control (QC)

**Code:** `src/murkml/data/qc.py` (called automatically during assembly)

**What it does to continuous sensor data:**
- Keeps only USGS "Approved" data (drops Provisional)
- Removes records flagged with bad qualifiers: Ice, Equipment malfunction (Eqp), Backwater (Bkw), Maintenance (Mnt), estimated (e)
- **Ice buffer (IMPLEMENTED 2026-03-24):** Extends Ice exclusion by 48 hours after the flag ends (bottom ice releases trapped sediment when it melts — sensor reads are unreliable)
- **Maintenance buffer (IMPLEMENTED 2026-03-24):** Extends Maintenance exclusion by 4 hours (freshly cleaned sensors have step discontinuities)
- Keeps Flood (Fld) flagged data — those are the storm events we care most about
- **Raises `ValueError` on missing expected columns** instead of silently skipping (hardened 2026-03-24)

**USGS qualifier format note (2026-03-24 fix):** The USGS API returns qualifier values as array-like strings, e.g., `"['ICE' 'EQUIP']"`, NOT as simple strings like `"Ice"`. The QC code now parses this format correctly. Prior to the fix, qualifier matching was silently failing — no Ice/Equip/Maint records were ever being excluded.

**What it does to discrete lab samples:**
- Drops samples with no timestamp (does NOT default to noon — that would create false alignment)
- Drops samples with unrecognized timezones
- Converts all timestamps to UTC using USGS timezone codes
- Handles non-detects: substitutes detection limit / 2 (standard DL/2 method)
- Keeps SSC = 0 (valid measurement, log1p handles it)
- Deduplicates samples with identical timestamp + value

**Why this matters:** Raw USGS data includes ice-affected readings, equipment glitches, and provisional estimates. Training on bad data teaches the model bad relationships. The QC step is the difference between R² = 0.6 and R² = 0.8.

---

## Step 3: Temporal Overlap Audit

**Script:** `check_temporal_overlap.py`

**What it does:** For each site and each discrete parameter, counts how many lab samples fall within the continuous turbidity sensor record period. A site might have 200 TP samples total, but if the turbidity sensor wasn't installed until 2018, only 40 of those samples are usable.

**Output:** `data/temporal_overlap_audit.parquet` — a table of site_id, param_name, n_total, n_pairable

**Why this matters:** The assembly step uses this audit to decide which sites have enough pairable samples (default threshold: 20). Without this step, the assembler doesn't know which sites to include for TP, nitrate, etc.

**When to run:** After downloading new sites, before assembling TP/nutrient datasets. The SSC assembler doesn't use this file (it checks directly), but the multi-param assembler does.

---

## Step 4: Align Discrete Samples to Continuous Sensors

**Scripts:** `assemble_dataset.py` (SSC), `assemble_multi_param.py` (TP, nitrate, orthoP)

**What it does:** This is the core step. For each discrete lab sample:

1. Find the closest continuous turbidity reading within +/- 15 minutes
2. If no match within 15 min, discard the sample (per Rasmussen 2009 standard)
3. For matched samples, compute a 1-hour window around the match time:
   - Turbidity: instant, mean, min, max, std, range, slope
4. For each other continuous sensor (conductance, DO, pH, temp, discharge):
   - Find the nearest reading within +/- 15 min of the same match time
   - Store as instantaneous value (NaN if no reading available)

**Output:**
- `data/processed/turbidity_ssc_paired.parquet` — SSC dataset
- `data/processed/total_phosphorus_paired.parquet` — TP dataset
- `data/processed/nitrate_nitrite_paired.parquet`
- `data/processed/orthophosphate_paired.parquet`

Each row = one lab sample matched to its sensor context. Columns include the lab value, all sensor readings, site_id, timestamp, and non-detect flag.

**The 15-minute rule:** If a technician collected a water sample at 10:30 AM but the turbidity sensor's nearest reading is 10:52 AM, that's a 22-minute gap. The river could have changed. We throw that sample out. This is strict but prevents training on mismatched pairs.

---

## Step 5: Feature Engineering

**Code:** `src/murkml/data/features.py` (called automatically during assembly)

**Features added:**
- **Hydrograph position:** Rate of change in discharge and turbidity over 1hr, 6hr, 24hr windows — tells the model whether the river is on a rising limb, peak, or falling limb
- **Cross-sensor ratios:** Turbidity/discharge ratio, turbidity/conductance ratio — these capture whether sediment is supply-limited or transport-limited
- **DO saturation departure:** Uses Benson & Krause (1984) nonlinear polynomial for DO saturation as a function of temperature and pressure. **(Fixed 2026-03-24 — was using a broken linear approximation `14.6 - 0.4*T` with 27-65% error at common stream temperatures. Never use a linear DO saturation formula.)**
- **Seasonality:** Sin/cos encoded day-of-year and hour-of-day — captures snowmelt timing, diurnal biological cycles
- **Log transforms:** log1p of the target variable (SSC, TP, etc.) — water quality values are log-normally distributed

---

## Step 6: Watershed Attributes (GAGES-II)

**Script:** `download_gagesii.py`

**What it does:** Downloads the GAGES-II dataset from USGS ScienceBase — a massive table of catchment characteristics for 9,067 US stream gauges. Attributes include:

- **Geology:** % limestone, % sandstone, karst fraction
- **Land cover:** % forest, % agriculture, % urban, % wetland
- **Soils:** Permeability, clay content, depth to bedrock
- **Climate:** Mean precipitation, mean temperature, aridity index
- **Topography:** Drainage area, mean slope, mean elevation
- **Hydrology:** Base flow index, runoff ratio

**Output:**
- `data/site_attributes_gagesii_full.parquet` — all 9,067 sites, all ~270 raw attributes (column names like `FORESTNLCD06`, `GEOL_HUNT_DOM_CODE`)
- `data/site_attributes_gagesii.parquet` — subset matched to our training sites, **already pruned** (column names like `forest_pct`, `geol_class`)

**CRITICAL: Column name formats differ between these files.** The `_full` file has raw GAGES-II column names. The non-full file has already-pruned column names. `prune_gagesii()` expects raw names. **Do NOT call `prune_gagesii()` on `site_attributes_gagesii.parquet`** — it will silently destroy all data by looking for columns that don't exist and replacing them with zeros/NaN. (Bug discovered 2026-03-24.)

**Matching:** GAGES-II uses plain station numbers (e.g., "01491000"). Our site IDs use "USGS-01491000". The script handles this conversion and zero-padding.

**Sites not in GAGES-II:** Some newer or non-standard sites won't match. The `fill_landcover_nlcd.py` script pulls NLCD 2019 land cover via pygeohydro as a fallback (37 sites filled this way).

**Two-source-of-truth problem (identified 2026-03-24):** The current attribute setup has a structural flaw:
- 58 sites have full GAGES-II data (geology, soils, climate, land cover — but 2006 vintage)
- 37 sites have NLCD 2019 backfill — land cover ONLY (no geology, soils, or climate attributes)
- 7 sites have no watershed attributes at all

This means Tier C models train on inconsistent feature sets across sites. The 37 backfill sites have NaN/default values for most GAGES-II columns, confounding tier comparisons.

**Planned fix: Migrate to EPA StreamCat.** StreamCat covers all NHDPlus catchments with 600+ attributes from a single consistent framework, regularly updated. This will give all 102 sites the same attribute set from one source. Requires COMID lookup via NLDI first.

---

## Step 7: Build Feature Tiers

**Code:** `src/murkml/data/attributes.py`

Three tiers used for ablation testing:

| Tier | Features | Purpose |
|------|----------|---------|
| A | Sensor readings only (turbidity, conductance, DO, pH, temp, discharge + engineered) | Baseline — what can sensors alone tell us? |
| B | A + basic site attributes (lat, lon, drainage area, elevation) | Does location help? |
| C | B + full GAGES-II attributes (geology, land cover, soils, climate) | Does watershed context help? |

Tier C is what we train the production model on. Tiers A and B exist to prove that watershed attributes actually improve predictions (they do — roughly +0.05 R² for SSC, +0.10 for TP).

---

## Step 8: Train

**Scripts:** `train_baseline.py` (quick single-tier), `train_tiered.py` (all tiers, all params)

**Model:** CatBoost (gradient-boosted trees). Also tested Random Forest and XGBoost — CatBoost wins on our data.

**Validation:** Leave-One-Group-Out (LOGO) cross-validation, where each "group" is a site. The model is trained on N-1 sites and tested on the held-out site. This repeats for every site. Median R² across all folds is the reported metric.

**Early stopping:** 15% of training sites held out as an internal validation set to prevent overfitting (500 max iterations, stops if validation loss hasn't improved in 50 rounds).

**Ridge linear baseline (added 2026-03-24):** A Ridge regression model runs under the same LOGO CV framework for fair comparison against CatBoost. This addresses the red team finding that no linear baseline existed.

**SHAP analysis (added 2026-03-24):** SHAP TreeExplainer is computed for Tier C models after final model save, identifying which features drive predictions and enabling interpretability analysis.

**Native-space metrics (added 2026-03-24):** Duan's smearing factor is computed per LOGO fold from training residuals, then applied to back-transform log-space predictions to mg/L. Both log-space and native-space R², RMSE, and bias are reported. This is critical because log-space R²=0.80 corresponds to only R²=0.61 in native space.

**Metrics:** R² (log-space AND native-space), KGE (Kling-Gupta Efficiency), RMSE (log + native), percent bias

---

## Running the Full Pipeline

From the murkml project root, with the `.venv` activated:

```bash
# 1. Download (already done for current sites)
python scripts/download_data.py

# 2. Temporal overlap audit (needed for TP/nutrient params)
python scripts/check_temporal_overlap.py

# 3. Assemble SSC dataset
python scripts/assemble_dataset.py

# 4. Assemble TP, nitrate, orthoP datasets
python scripts/assemble_multi_param.py

# 5. Download/update GAGES-II (only need to run once)
python scripts/download_gagesii.py

# 6. Train all tiers
python scripts/train_tiered.py
```

Steps 3 and 4 include QC, alignment, and feature engineering automatically. You don't run those separately.

---

## Data Directory Layout

```
data/
  continuous/          <- 15-min sensor data, one folder per site
    USGS_01491000/
      63680/           <- turbidity parquet chunks
      00095/           <- conductance
      ...
  discrete/            <- lab samples, one file per site+param
    USGS_01491000_ssc.parquet
    USGS_01491000_total_phosphorus.parquet
    ...
  processed/           <- ML-ready aligned datasets
    turbidity_ssc_paired.parquet
    total_phosphorus_paired.parquet
    ...
  gagesii/             <- GAGES-II raw files
  site_catalog.parquet
  site_attributes.parquet            <- basic attrs (drainage area, elevation, HUC)
  site_attributes_gagesii.parquet    <- PRUNED column names (forest_pct, geol_class, etc.)
  site_attributes_gagesii_full.parquet <- RAW column names (FORESTNLCD06, GEOL_HUNT_DOM_CODE, etc.)
  site_attributes_nlcd.parquet       <- NLCD 2019 backfill for non-GAGES-II sites
  temporal_overlap_audit.parquet
  expansion_candidates.parquet
  results/             <- model outputs
```

---

## Data Integrity Rules (added 2026-03-24)

These rules exist because of a bug where `prune_gagesii()` was called on already-pruned data, silently destroying all GAGES-II attributes. The model trained on 25 columns of zeros/NaN without any error or warning.

1. **Verify column names before calling transformation functions.** If a function expects raw GAGES-II names (`FORESTNLCD06`) but the input has pruned names (`forest_pct`), it will silently produce garbage. Check the first few column names before calling any pruning/transformation step.

2. **Never trust default values from `_safe_col()` at scale.** If more than 50% of expected columns are missing, something is wrong — fail loudly instead of filling with defaults.

3. **Spot-check intermediate data products.** After any transformation, verify that output columns contain real values (not all zeros, not all NaN, correct dtypes). A 5-row `head()` check would have caught the prune_gagesii bug.

4. **Document column name formats in file names or metadata.** `site_attributes_gagesii.parquet` (pruned) and `site_attributes_gagesii_full.parquet` (raw) store the same sites with different column schemas. This must be obvious to any code that reads them.

5. **All results must have a clear provenance chain:** raw data file → processing function → feature columns → model → metrics. If you can't trace a reported R² value back to the exact input data and code path that produced it, it's not publishable.
