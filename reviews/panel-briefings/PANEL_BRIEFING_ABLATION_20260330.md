# Expert Panel Briefing — Phase 5 Ablation Results (2026-03-30)

## What Happened Since Last Panel

### Pipeline Fixes (Phase 3)
- Fixed 3 bugs in evaluate_model.py (Gemini red-team review): hash determinism, slope-clipping, Student-t prior
- Added 28 SGMC lithology features (watershed bedrock %)
- Resolved 5,536 unknown collection methods (unknown 6,282 → 746)
- Ported staged Bayesian adaptation into canonical evaluation script

### Evaluation Script Upgrade
- Now runs 3 split modes: random (optimistic), temporal (first N predict rest), seasonal (one season cal, all test)
- Metrics: NSE, log-NSE, KGE, Spearman rho, bias, MAPE, within-2x, median abs error + bootstrap 95% CIs
- Baseline comparisons (global-mean, site-mean predictors)
- Runs OLS comparison alongside Bayesian
- Calls disaggregated diagnostics and external validation automatically

### External Validation (major result)
- Downloaded 11,026 paired turbidity-SSC samples from 6 non-USGS organizations via WQP
- 260 sites (UMRR, SRBC, GLEC, UMC, MDNR, CEDEN), mostly NTU sensors
- Bayesian adaptation on external data (NTU < 400, 113 sites):

| N cal | Random R² | Temporal R² | Seasonal R² |
|---|---|---|---|
| 0 | -0.216 | -0.216 | -0.216 |
| 2 | +0.063 | -0.007 | +0.060 |
| 5 | +0.378 | +0.299 | +0.280 |
| 10 | **+0.501** | **+0.370** | **+0.424** |
| 20 | +0.554 | +0.423 | +0.496 |

10 samples on completely foreign NTU data achieves R²=0.501 (random), matching USGS holdout performance.

### Bayesian vs OLS (all split modes, USGS holdout)
CatBoost+Bayesian wins at every N in every split mode. Temporal N=2: Bayesian +0.488 vs OLS -0.709.

---

## Phase 5 Ablation — What We Found

### The Bug We Caught
Initial holdout evaluation of ablated models showed catastrophic collapse — dropping ANY feature caused median per-site R² to plummet from 0.42 to 0.15. Gemini red-team review identified the cause: _save_quick_model trained 500 iterations with no early stopping. Without regularization, CatBoost memorized noise differently per feature set, making every model look catastrophically different on holdout.

Fix: Added GroupShuffleSplit validation + early_stopping_rounds=50. Holdout deltas became small and reasonable.

### Current Model: 72 features (44 original + 28 SGMC)
- GKF5 R²(native): 0.239
- Holdout pooled NSE: 0.368
- Holdout median per-site R²: 0.285

### Single-Feature Ablation (corrected, early-stopped)

**Top 12 most important (dropping hurts median per-site R²):**

| Feature | dMedR² | Category |
|---|---|---|
| turb_Q_ratio | -0.102 | Hydrograph |
| sgmc_unconsolidated_sedimentary_undiff | -0.102 | SGMC |
| collection_method | -0.065 | Categorical |
| flush_intensity | -0.054 | Engineered |
| sensor_family | -0.052 | Categorical |
| temp_instant | -0.045 | Sensor |
| turb_source | -0.041 | Categorical |
| sgmc_igneous_volcanic | -0.041 | SGMC |
| sgmc_metamorphic_volcanic | -0.039 | SGMC |
| developed_pct | -0.031 | Watershed |
| dam_storage_density | -0.031 | Watershed |
| turb_below_detection | -0.029 | Engineered |

**Top 12 candidates to drop (dropping helps):**

| Feature | dMedR² | Category |
|---|---|---|
| pct_eolian_fine | +0.056 | Watershed |
| sgmc_melange | +0.055 | SGMC |
| sgmc_metamorphic_sedimentary_undiff | +0.043 | SGMC |
| baseflow_index | +0.038 | Watershed |
| pct_carbonate_resid | +0.027 | SGMC |
| sgmc_metamorphic_carbonate | +0.020 | SGMC |
| geo_fe2o3 | +0.019 | Watershed |
| precip_30d | +0.012 | Weather |
| wwtp_all_density | +0.011 | Watershed |
| sgmc_unconsolidated_undiff | +0.010 | SGMC |
| fertilizer_rate | +0.008 | Watershed |
| sgmc_sedimentary_undiff | +0.007 | SGMC |

### Group Ablation Results (with full disaggregated diagnostics)

| Group Dropped | n feat | MedR² | dMedR² | FF R² | dFF R² | Top1% R² | Underpred |
|---|---|---|---|---|---|---|---|
| **Baseline** | 72 | 0.285 | — | 0.394 | — | 0.109 | -37.6% |
| Legacy geology+soil | 9 | 0.297 | +0.012 | 0.359 | -0.035 | 0.066 | -33.7% |
| Human land+infra | 8 | 0.262 | -0.022 | 0.378 | -0.016 | 0.104 | -53.5% |
| Antecedent weather | 3 | 0.347 | +0.062 | 0.305 | **-0.089** | 0.005 | -31.8% |

**Key finding:** Dropping weather improves median R² by +0.062 but destroys first flush R² (-0.089) and extreme event prediction (top 1% R²: 0.109 → 0.005). Aggregate metrics lied — weather features are essential for the events that matter most.

---

## What We Need Your Help With

### Proposed Next Ablation Tests

**Test A: SGMC subgroups**
The 28 SGMC lithology features include many correlated subtypes. Proposed groups:
- A1: Drop all metamorphic SGMC (10 features)
- A2: Drop all sedimentary SGMC (5 features)
- A3: Drop all igneous SGMC (5 features)
- A4: Drop all unconsolidated + other SGMC (5 features)
- A5: Drop ALL 28 SGMC (keep only old StreamCat geology)
- A6: Drop old StreamCat geology, keep ONLY SGMC 28

**Test B: Combined drop of individually harmful features**
Drop all 12 features where individual drop helped. Does the compound effect match the sum?

**Test C: Precipitation decomposition**
- C1: Keep only precip_7d (drop 48h and 30d)
- C2: Keep only precip_48h (drop 7d and 30d)
- C3: Keep precip_7d + precip_48h (drop only 30d)

**Test D: Old geology vs SGMC replacement**
- D1: Drop 9 old geology/soil features + keep all 28 SGMC (SGMC replaces StreamCat geology)
- D2: Drop 9 old geology/soil features + drop non-significant SGMC (keep only the 5 individually helpful ones)

### Questions for the Panel

1. Are these the right group ablation tests, or are we missing important groupings?
2. Given the group ablation results, should we keep ALL weather features despite the median R² penalty? Or is there a middle ground?
3. The human infrastructure block (agriculture_pct, developed_pct, dam_storage_density, etc.) hurts median R² but helps extreme events. How should we weigh this tradeoff?
4. Is the turb_Q_ratio importance (-0.102) suspicious? It's by far the most important feature — could it be leaking information?
5. Several SGMC features individually hurt the model (+0.02-0.05 when dropped) but the SGMC group as a whole hasn't been tested in isolation. Should we test keeping ONLY the 5 helpful SGMC features?
6. The re-introduced features (do_instant, ph_instant, etc.) all failed. Should we accept this or test them in groups?
7. What other group ablation tests would you run?
8. At what point do we stop ablating and declare the feature set final?
