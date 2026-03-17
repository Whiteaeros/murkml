# murkml Results & Findings Log

Reference for paper writing. Captures key results, expert panel findings, and decisions.

---

## Baseline Results (SSC-only, post-audit)

| Model | Median R² (log) | Median R² (nat) | Median KGE |
|-------|----------------|----------------|-----------|
| Per-site OLS (ceiling) | 0.81 | 0.59 | 0.51 |
| **Cross-site CatBoost** | **0.75** | **0.57** | **0.54** |
| Global OLS | 0.67 | 0.35 | 0.37 |

57 sites, 16,760 paired samples, 11 states. Cross-site CatBoost within 0.06 of per-site OLS without seeing test site.

---

## Multi-Parameter Tiered Results

| Parameter | Tier A (sensor) | Tier B (+basic) | Tier C (+GAGES-II) | Per-site OLS |
|---|---|---|---|---|
| SSC (57 sites) | 0.75 | 0.74 | **0.80** | 0.81 |
| TP (42 sites) | 0.40 | **0.59** | **0.62** | 0.60 |
| Nitrate (40 sites) | -2.09 | -0.89 | -0.72 | 0.04 |
| OrthoP (39 sites) | -1.76 | **-0.55** | -1.31 | 0.06 |

- TDS dropped from MVP: only 16 sites with ≥20 pairable samples
- Nitrate: 2 high-censoring sites dropped (USGS-11501000 80.5%, USGS-11502500)
- OrthoP: 10 contamination records excluded, Tier C overfits (46 features on 25 sites)

---

## Assembled Dataset Summary

| Parameter | Sites | Samples | Non-detect % |
|---|---|---|---|
| SSC | 57 | 16,760 | — |
| TP | 42 | 7,415 | 0.7% |
| Nitrate | 40 | 6,949 | 5.1% |
| OrthoP | 39 | 6,461 | 5.8% |

Temporal overlap: only 30% of total discrete samples are pairable with continuous sensors. Most losses from lab samples predating sensor installation.

---

## Key Architecture Decisions (Physics Panel)

- **CatBoost only.** No neural networks. Gradient boosting dominates on <20K tabular samples (Nakamura, Grinsztajn et al. 2022 NeurIPS).
- **Independent models per parameter**, then prediction chain (SSC→TP, Temp→DO). Chain must pass ablation test.
- **Physics constraints tiered:** Tier 1-2 get 90% of benefit. Log targets, monotone constraints, output clipping, derived features.
- **Screening tool positioning.** ±50% load tolerance acceptable (Torres).
- **CQR via MAPIE** for calibrated prediction intervals (Krishnamurthy).

---

## Expert Panel Strategic Consensus (Phase 3 Review)

**Publishable findings:**
- SSC R²=0.80 cross-site exceeds published baselines (5-15 sites, R²=0.6-0.7 typical)
- TP R²=0.62 cross-site, potentially exceeds per-site OLS — needs Wilcoxon validation
- Nitrate/orthoP negative results define the particulate/dissolved predictability boundary

**Publication framing:** "What transfers cross-site and what does not." Lead with SSC+TP, report nitrate/orthoP as characterized negative results.

**Rivera's domain insight:** "The model correctly learned the particulate/dissolved transport boundary that 50 years of water quality science predicts." Turbidity measures particles; nitrate is dissolved with zero mechanistic connection to optical scattering.

**Target venues:** Water Resources Research or Environmental Modelling & Software.

---

## Censoring Rates

| Parameter | Avg Censored | Sites <10% | Verdict |
|---|---|---|---|
| TP | 1.3% | 49/50 | DL/2 fine |
| TDS | 0.2% | 38/38 | DL/2 fine |
| OrthoP | 9.8% | 34/46 | Borderline — sensitivity analysis Phase 4 |
| Nitrate | 10.3% | 35/48 | Per-record DL varies 0.002–0.45 mg/L |

---

## GAGES-II Coverage

- 37/57 sites matched to GAGES-II (576 raw attributes → 25 pruned)
- 20 sites have basic attributes only (drainage area, elevation, HUC)
- NLDI characteristics endpoint down (EPA service degradation, March 2026)

**Pruned features (25):** forest_pct, agriculture_pct, developed_pct, other_landcover_pct, geol_class, clay_pct, sand_pct, soil_permeability, water_table_depth, precip_mean_mm, temp_mean_c, temp_range_c, precip_seasonality, snow_pct_precip, elev_mean_m, relief_m, slope_pct, baseflow_index, runoff_mean, stream_density, n_dams, dam_storage, road_density, reference_class, ecoregion.

**Staleness note (2006-2011 vintage):**
- Time-sensitive: NLCD land cover %, population density, dam counts
- Stable: elevation, slope, geology, soil permeability, climate normals, baseflow index

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
