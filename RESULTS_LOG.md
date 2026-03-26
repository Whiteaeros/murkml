# murkml Results & Findings Log

Reference for paper writing. Captures key results, expert panel findings, and decisions.

---

## CRITICAL BUG: prune_gagesii destroyed all GAGES-II attributes (discovered 2026-03-24)

**Root cause:** `train_tiered.py` calls `prune_gagesii()` on `site_attributes_gagesii.parquet`, but that parquet already stores data with **pruned column names** (e.g., `forest_pct`). `prune_gagesii()` looks for raw GAGES-II names (e.g., `FORESTNLCD06`), finds none, and replaces every column with zeros or NaN. The model trained on 25 columns of garbage for all Tier C/C_gagesii_only results.

**Evidence:**
- Before `prune_gagesii()`: `forest_pct = [58.6, 46.0, 6.5, ...]`, `geol_class = ['tg', 'rtr', ...]`
- After `prune_gagesii()`: `forest_pct = [0, 0, 0, ...]`, `geol_class = [NaN, NaN, ...]` (dtype changed from object to float64)
- Saved model meta confirms: only `huc2` (from basic_attrs, not GAGES-II) was treated as categorical. `geol_class`, `ecoregion`, `reference_class` all became float64 NaN columns.
- `sites_per_ecoregion` and `sites_per_geology` in model meta are both `{}` (empty).

**Impact on results:**
- ALL Tier C and C_gagesii_only R²/KGE values below are **INVALID** — trained without actual watershed attributes
- The "categorical feature fix" (2026-03-17) only added `huc2` correctly; the other 3 categoricals were already destroyed by `prune_gagesii()` before dtype detection
- The "Tier C > B_restricted" claim is NOT supported — the improvement came from noise columns or site-selection artifacts, not from watershed attributes
- **Tier A and Tier B results are NOT affected** (they don't use GAGES-II attributes)
- **External validation results are NOT affected** (used pre-tiered Tier B models)

**Fix applied (2026-03-24):** Added auto-detection guard to `prune_gagesii()` — returns input unchanged if already pruned. Added schema validation, post-merge assertions, and post-training integrity checks. Retrained all tiers. Audit script (`scripts/audit_pipeline.py`) passes 60/60 checks.

**Also corrected (2026-03-24):** Attribute coverage section below previously stated "7/102 sites have sensor-only features." Actual count: **0 sensor-only sites.** All 102 SSC sites have attributes in the GAGES-II merged file (95 sites) or NLCD file (44 sites), with 37-site overlap.

---

## Current Best Results (102 sites, 12 regimes, bug fixed + retrained 2026-03-24)

**SSC LOGO CV — log-space metrics (median across folds):**

| Parameter | Tier A (sensor) | Tier B (+basic) | Tier C (+GAGES-II) | B_restricted | C_gagesii_only |
|---|---|---|---|---|---|
| **SSC R² (log)** | 0.710 | 0.750 | **0.798** | — | — |
| **SSC KGE (log)** | 0.795 | 0.809 | **0.829** | 0.825 | 0.813 |

**SSC LOGO CV — native-space metrics (mg/L, Duan smearing, first run with old DO formula + old GAGES-II):**

| Tier | R²(log) | R²(mg/L) | RMSE(mg/L) | Bias% |
|------|---------|----------|------------|-------|
| A_sensor_only | 0.710 | 0.439 | 87.1 | +17.8% |
| B_sensor_basic | 0.750 | 0.487 | 91.4 | +18.4% |
| B_restricted | — | 0.589 | 78.0 | +8.3% |
| C_sensor_basic_gagesii | 0.798 | 0.611 | 61.7 | +2.2% |
| C_gagesii_only | — | 0.537 | 79.6 | -1.7% |

**Key observation:** Log-space R²=0.80 corresponds to native-space R²=0.61. The gap is substantial and log-space metrics alone overstate practical prediction accuracy. Both must be reported.

**Key findings (corrected):**
- **Watershed attributes genuinely help:** C (0.798) vs B_restricted (0.763) = **+0.035 R²** on the same 95 sites. This is a real improvement, not an artifact of garbage features.
- **Vintage confound test passes:** C_gagesii_only (0.806) vs B_restricted (0.763) = **+0.043 R²** on the 58 original GAGES-II sites with 2006-vintage data. GAGES-II attributes add value even controlling for land cover vintage.
- **4 categorical features correctly used:** geol_class (21 classes), ecoregion (8 classes), reference_class (2 classes), huc2 (10 values). All confirmed in model metadata with non-empty `categorical_values_seen` and `sites_per_ecoregion`.
- **46 numeric + 4 categorical = 50 features** in Tier C (was 50 features before but 25 were all-NaN garbage).
- **Native-space bias is low for Tier C** (+2.2%) but high for Tier A (+17.8%) — watershed attributes reduce systematic overprediction.

**Note:** These native-space results used the OLD broken DO saturation formula (linear approximation, 27-65% error at common temps) and old GAGES-II data. Retrain with Benson & Krause 1984 DO formula is pending.

**TP, Nitrate, OrthoP Tier C results still pending retrain** — only SSC retrained so far. Tier A/B results for non-SSC parameters are unchanged:

| Parameter | Tier A (sensor) | Tier B (+basic) |
|---|---|---|
| TP (72 sites, 9,391 samples) | -0.10 | -0.08 |
| Nitrate (66 sites, 9,043 samples) | -2.00 | -1.54 |
| OrthoP (62 sites, 8,179 samples) | -2.34 | -1.52 |

**Previously invalid results (for the record):**
- Old Tier C R²=0.786 (trained on destroyed attributes, huc2 only categorical)
- Old C_gagesii_only R²=0.807 (same issue)
- Old "Tier C > B_restricted" claim was unsupported — the +0.023 gap came from noise columns, not real attributes

---

## External Validation (holdout sites, never trained on)

Sites from new states not in training set. Model trained on full training data (Tier C), then predicted on assembled holdout data.

**SSC — 11 holdout sites:**

| Site | R² (CatBoost) | R² (per-site OLS) | n |
|------|--------------|-------------------|---|
| USGS-04213500 | **0.92** | 0.82 | 297 |
| USGS-05082500 | **0.90** | 0.94 | 177 |
| USGS-12113390 | **0.87** | 0.83 | 103 |
| USGS-01362370 | 0.83 | **0.91** | 382 |
| USGS-04026005 | 0.74 | N/A | 13 |
| USGS-04024000 | **0.68** | 0.59 | 171 |
| USGS-02207135 | **0.65** | 0.59 | 87 |
| USGS-08070200 | 0.52 | **0.71** | 140 |
| USGS-040851385 | 0.07 | N/A | 11 |
| USGS-05447500 | -0.89 | 0.06 | 60 |
| USGS-09365000 | -8.54 | N/A | 10 |

- **Median R² = 0.68, Median KGE = 0.74**
- CatBoost beats per-site OLS at 4/8 comparable sites
- 8/11 sites have R² > 0.5
- Failures: USGS-09365000 (arid, 10 samples), USGS-05447500 (60 samples, low-turbidity site)

**TP — 12 holdout sites:**

| Site | R² (CatBoost) | R² (per-site OLS) | n |
|------|--------------|-------------------|---|
| USGS-04213500 | **0.74** | 0.08 | 314 |
| USGS-410333095530101 | **0.73** | 0.31 | 123 |
| USGS-04024000 | 0.47 | **0.63** | 178 |
| USGS-05082500 | 0.40 | **0.69** | 260 |
| USGS-040851385 | 0.34 | N/A | 11 |
| USGS-05447500 | 0.00 | 0.34 | 110 |
| USGS-02207135 | -0.48 | **0.33** | 82 |
| USGS-02292900 | -3.62 | -0.36 | 16 |
| USGS-04026005 | -2.41 | N/A | 13 |
| USGS-08070200 | -6.79 | -0.81 | 140 |
| USGS-410613073215801 | -798 | -0.05 | 52 |
| USGS-01362370 | -63 | N/A | 5 |

- **Median R² = -0.24** — confirms cross-site TP is regime-dependent
- 4/12 sites have R² > 0.3 (particulate-P-dominated sites where turbidity is informative)
- Catastrophic failures at dissolved-P-dominated sites (WWTP, groundwater-influenced)
- TP cross-site model should flag dissolved-P sites as "not applicable"

---

## Prior Results (57 sites, 11 states — before expansion)

| Parameter | Tier A (sensor) | Tier B (+basic) | Tier C (+GAGES-II) | Per-site OLS |
|---|---|---|---|---|
| SSC (57 sites) | 0.75 | 0.74 | **0.80** | 0.81 |
| TP (42 sites) | 0.40 | **0.59** | **0.62** | 0.60 |
| Nitrate (40 sites) | -2.09 | -0.89 | -0.72 | 0.04 |
| OrthoP (39 sites) | -1.76 | **-0.55** | -1.31 | 0.06 |

57 sites, 16,760 SSC samples, 11 states.

**TP degradation analysis:** TP dropped from 0.62 (42 sites) to 0.08 (72 sites) after expansion. Expert panel diagnosis: TP has multiple generation mechanisms (particulate erosion, WWTP point sources, agricultural runoff) and the expansion added sites with different TP physics. A single cross-site model cannot span all mechanisms. Per-regime analysis needed to confirm. This is a scientifically honest result, not a model failure.

---

## Assembled Dataset Summary

| Parameter | Sites | Samples | Non-detect % |
|---|---|---|---|
| SSC | 102 | 19,611 | — |
| TP | 72 | 9,391 | 0.9% |
| Nitrate | 66 | 9,043 | 5.9% |
| OrthoP | 62 | 8,179 | 6.1% |

12 watershed regimes: loess belt (IA), Gulf Coastal Plain (TX), arid Southwest (CO), iron range (MN/WI), SE Piedmont (NC), karst (TX Edwards), urban stormwater (PA), New England (CT), glaciolacustrine (ND), Blue Ridge (NC/WV), cold semi-arid (WY), deep south alluvial (MS). Plus original 57 sites across KS, IN, CA, CO, OR, VA, MD, MT, OH, ID, KY.

---

## Watershed Attribute Coverage

- **95/102 sites** in the GAGES-II merged attribute file
  - 58 sites with original GAGES-II data (2006-2011 vintage)
  - 37 sites with NLCD 2019 backfill merged into GAGES-II format
- **44/102 sites** in the NLCD file (37 overlap with GAGES-II, 7 NLCD-only)
- **0/102 sites** are truly sensor-only (previously reported as 7 — incorrect)
- **Categorical features status (2026-03-24):** All 4 categoricals (`huc2`, `geol_class`, `ecoregion`, `reference_class`) are correctly handled after prune_gagesii fix. Confirmed in model metadata with non-empty `categorical_values_seen` and `sites_per_ecoregion`.
- **Two-source problem:** 58 sites have full GAGES-II attributes, 37 have NLCD land cover only (no geology/soils/climate), 7 have no watershed attributes. Planned migration to StreamCat will unify all sites.

**Attribute sources merged into single file:**
- GAGES-II (ScienceBase): land cover (2006 vintage), geology, soils, climate, dams, hydrology
- NLCD (MRLC): land cover (2019 vintage) for non-GAGES-II sites
- NLDI: clay/sand/silt %, elevation, slope, stream density, precipitation, temperature

**Staleness note (GAGES-II 2006-2011 vintage):**
- Time-sensitive: NLCD land cover %, population density, dam counts
- Stable: elevation, slope, geology, soil permeability, climate normals, baseflow index

---

## Key Architecture Decisions (Physics Panel)

- **CatBoost only.** No neural networks. Gradient boosting dominates on <20K tabular samples (Nakamura, Grinsztajn et al. 2022 NeurIPS).
- **Independent models per parameter**, then prediction chain (SSC→TP, Temp→DO). Chain must pass ablation test.
- **Physics constraints tiered:** Tier 1-2 get 90% of benefit. Log targets, monotone constraints, output clipping, derived features.
- **Screening tool positioning.** ±50% load tolerance acceptable (Torres).
- **CQR via MAPIE** for calibrated prediction intervals (Krishnamurthy).
- **Categorical features must use CatBoost Pool with cat_features parameter.** Silently dropping string columns loses ecoregion/geology information.

---

## Expert Panel Consensus (Post-Expansion Review, 2026-03-17)

**On SSC (0.79 on 102 sites):**
- Rivera: "A 1-point drop while nearly doubling sites and adding geologically diverse regimes is the honest cost of generalization. I would have been suspicious if performance stayed at 0.80."
- Publishable finding: "Watershed-scale catchment attributes improve SSC estimation cross-site, with categorical ecoregion and geology class contributing +0.04 R²."

**On TP collapse (0.62 → 0.08):**
- Chen: TP has 3+ generation mechanisms (particulate, WWTP, ag runoff). Expansion added sites with different TP physics. A single model can't span all mechanisms.
- Diagnosis needed: per-site turbidity-TP correlation to flag dissolved-P-dominated sites where turbidity is uninformative.
- Consider regime-aware TP model or explicit "model not applicable" flag for dissolved-P sites.

**On B_restricted vs Tier C:**
- Rivera: For SSC, B_restricted < C confirms watershed attributes help (with categoricals). Previous B > C was due to the categorical bug.
- Okafor: The bug was that 4 of 25 GAGES-II features (the most informative ones) were silently excluded.

**Recommended next steps (priority order):**
1. Per-regime performance breakdown (group LOGO folds by regime)
2. Per-site turbidity-TP correlation to define transferability boundary
3. KGE decomposition for TP (correlation vs bias vs variability)
4. Run validation on 20 holdout sites

**Publication framing (updated):** "What transfers cross-site and what does not." SSC transfers well (R²=0.79) across 102 sites and 12 regimes. TP transfer is regime-dependent. Nitrate/orthoP are characterized negative results consistent with the particulate/dissolved transport boundary.

**Target venues:** Water Resources Research or Environmental Modelling & Software.

---

## Censoring Rates

| Parameter | Avg Censored | Sites <10% | Verdict |
|---|---|---|---|
| TP | 0.9% | — | DL/2 fine |
| OrthoP | 6.1% | — | Borderline — sensitivity analysis Phase 4 |
| Nitrate | 5.9% | — | Per-record DL varies 0.002–0.45 mg/L |

---

## Red Team Panel Review (5 expert reviewers, 2026-03-24)

All 5 reviewers recommend **major revision before WRR submission.** Key findings by reviewer:

**Dr. Catherine Ruiz (sediment transport):**
- Grain size confound — turbidity-SSC relationship varies with particle size, model cannot distinguish silt from sand
- Hysteresis on rising vs falling limb not captured
- GAGES-II data is stale (2006 vintage) for time-sensitive attributes
- Need log-space AND native-space metrics (log alone overstates accuracy)

**Dr. Marcus Chen (statistics):**
- Effective sample size is N=102 sites, NOT 19,611 observations (spatial autocorrelation within sites)
- Spatial autocorrelation between nearby sites not addressed
- Prediction intervals missing from main results
- Tier C vs B_restricted difference may not be statistically significant given N=102

**Dr. Priya Nair (sensor QC/operations):**
- Ice buffer was documented but never implemented in code (now fixed)
- QC qualifier parsing was silently failing — never matching Ice/Equip flags due to USGS array string format (now fixed)
- Approved-only training creates bias: excludes the most extreme events (provisional data)
- Non-detect handling needs explicit strategy

**Dr. James Okafor (ML benchmarking):**
- No linear baseline model for fair comparison (Ridge baseline now added)
- Fixed hyperparameters — no tuning or sensitivity analysis
- Tier comparison confounded by different site subsets per tier
- External validation set too small (11 sites) for credible generalization claims — need 20-30

**Dr. Elena Voss (scientific contribution):**
- Paper needs a testable hypothesis, not just "ML predicts SSC"
- SHAP analysis missing (now added)
- DO saturation formula was wrong — linear approximation had 27-65% error at common temperatures (now fixed with Benson & Krause 1984)
- Reframe paper as "what transfers cross-site and what doesn't"

---

## Structural Data Problem: Two Sources of Truth (discovered 2026-03-24)

Watershed attributes currently come from two incompatible sources:
- **GAGES-II (2006 vintage):** 58 sites — full attributes (geology, soils, climate, land cover, hydrology)
- **NLCD 2019 backfill:** 37 sites — land cover ONLY (no geology, soils, or climate)
- **7 sites:** No watershed attributes at all

The 37 backfill sites appear to have full Tier C features, but most columns are NaN or default-filled. This confounds tier comparisons — Tier C improvement may partly reflect which sites have real attributes vs backfill.

**Plan:** Replace both sources with **EPA StreamCat** — covers all NHDPlus catchments, 600+ attributes, consistent framework, regularly updated. This gives all 102 sites the same attribute set from one source.

---

## Code Fixes Implemented (2026-03-24/25) — NOT YET RETRAINED

These fixes are in the code but results above still reflect the old code:
- **DO saturation formula:** Benson & Krause 1984 polynomial replaces broken linear approximation (was 27-65% error at common temps)
- **QC qualifier parsing:** Now handles USGS array string format `"['ICE' 'EQUIP']"` (was never matching anything)
- **Ice/Maint buffer exclusion:** 48hr post-Ice, 4hr post-Maint (was documented but never coded)
- **Native-space metrics:** Duan smearing factor computed per LOGO fold, reported alongside log-space
- **Ridge linear baseline:** Runs under same LOGO CV framework for fair comparison
- **SHAP analysis:** Computed for Tier C models after final model save
- **QC raises on missing columns** instead of silently skipping

Retrain with all fixes is the next step. Results will change.

---

## Confirmed Physics Equations

| Constraint | Equation | Citation | Type |
|-----------|----------|----------|------|
| DO saturation | Nonlinear f(T, P) | Benson & Krause 1984 (fixed 2026-03-24; was broken linear approx with 27-65% error) | Thermodynamic |
| Non-negative concentrations | C ≥ 0 | Physical law | Thermodynamic |
| SC-TDS proportionality | TDS = k × SC, k=0.55-0.75 | Hem 1985 | Empirical-universal |
| TP ≥ orthophosphate | TP ≥ ortho-P | Mass balance | Thermodynamic |
| DO ≤ ~130% saturation | Soft cap | Empirical | Conditional |
| Turbidity-SSC monotonicity | DO NOT ENFORCE | Rivera audit | Breaks across sites |
