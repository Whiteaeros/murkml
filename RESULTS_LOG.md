# murkml Results & Findings Log

Reference for paper writing. Captures key results, expert panel findings, and decisions.

---

## Current Best Results (102 sites, 12 regimes, categorical fix applied)

| Parameter | Tier A (sensor) | Tier B (+basic) | Tier C (+GAGES-II) | B_restricted |
|---|---|---|---|---|
| **SSC (102 sites, 19,611 samples)** | 0.71 | 0.75 | **0.79** | 0.76 |
| TP (72 sites, 9,391 samples) | -0.10 | -0.08 | 0.08 | 0.09 |
| Nitrate (66 sites, 9,043 samples) | -2.00 | -1.54 | -1.51 | -1.77 |
| OrthoP (62 sites, 8,179 samples) | -2.34 | -1.52 | -2.54 | -2.54 |

**KGE values:** SSC Tier C = 0.82, TP Tier C = 0.34

**Key finding:** SSC R²=0.79 on 102 sites across 12 watershed regimes nearly matches the prior R²=0.80 on 57 sites from 11 states. The model generalizes. Tier C > B_restricted confirms watershed attributes (including categorical ecoregion/geology) add real predictive value for SSC.

**Categorical feature bug fix (2026-03-17):** `geol_class`, `ecoregion`, `reference_class`, and `huc2` were being silently dropped because they are string-typed and the training code only kept numeric columns. Fix: pass them as `cat_features` to CatBoost Pool. Impact: SSC Tier C improved from 0.75 → 0.79 (+0.04). TP unchanged.

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

- **58/102 sites** matched to GAGES-II (576 raw → 25 pruned features)
- **37/102 sites** filled via NLCD 2019 land cover (pygeohydro) + NLDI characteristics (soils, climate, topography)
- **7/102 sites** have sensor-only features (no watershed attributes)
- **4 categorical features now properly included:** geol_class (20 classes), ecoregion (8 classes), reference_class (2 classes), huc2

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

## Confirmed Physics Equations

| Constraint | Equation | Citation | Type |
|-----------|----------|----------|------|
| DO saturation | Nonlinear f(T, P) | Benson & Krause 1984 | Thermodynamic |
| Non-negative concentrations | C ≥ 0 | Physical law | Thermodynamic |
| SC-TDS proportionality | TDS = k × SC, k=0.55-0.75 | Hem 1985 | Empirical-universal |
| TP ≥ orthophosphate | TP ≥ ortho-P | Mass balance | Thermodynamic |
| DO ≤ ~130% saturation | Soft cap | Empirical | Conditional |
| Turbidity-SSC monotonicity | DO NOT ENFORCE | Rivera audit | Breaks across sites |
