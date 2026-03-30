# Phase 4 Diagnostic Observations (2026-03-30)

## 4.1 Disaggregated Metrics — Key Findings

### Overall: Pooled R²=0.665, MAPE=57.7%, within-2x=62.2%, bias=-3.0%

### By Collection Method
| Method | n | R² | MAPE | within-2x | bias |
|---|---|---|---|---|---|
| auto_point | 1,925 | 0.377 | 57.3% | 62.0% | -5.6% |
| depth_integrated | 2,065 | 0.548 | 56.9% | 62.8% | +0.9% |
| grab | 609 | 0.288 | 67.4% | 57.8% | -0.7% |
| unknown | 1,248 | 0.873 | 55.8% | 63.8% | -2.7% |

**Observation:** "Unknown" has the best R². These are the 13 unresolvable sites from the method resolution. Either they happen to be easy sites, or the "unknown" categorical value is acting as a useful signal (the model learned "unknown = behaves like X"). This needs investigation — if we resolve them, performance might actually drop for those sites.

### By HUC2 Region (selected)
| Region | Sites | Samples | R² | MAPE | bias |
|---|---|---|---|---|---|
| HUC06 Tennessee | 1 | 128 | 0.910 | 17.9% | -11.5% |
| HUC11 Arkansas-White-Red | 4 | 247 | 0.825 | 46.5% | +1.6% |
| HUC13 Rio Grande | 1 | 16 | 0.824 | 21.1% | -18.1% |
| HUC19 Alaska | 1 | 21 | -10.522 | 205.4% | +262.3% |
| HUC20 Hawaii | 1 | 112 | -0.629 | 147.7% | +106.0% |
| HUC08 Lower Mississippi | 2 | 137 | -0.153 | 47.9% | +41.4% |

**Observation:** Alaska (+262% bias) and Hawaii (+106% bias) are catastrophic. The model massively overpredicts SSC. These are geologically and climatically unique environments (glacial flour, volcanic soils) that the continental training set doesn't represent. Single-site regions make the numbers extremely volatile.

### By SSC Variability (per-site std quartile)
| Tier | n | R² | MAPE | bias |
|---|---|---|---|---|
| Q1 low-var | 1,018 | 0.094 | 65.4% | +33.0% |
| Q2 medium | 1,501 | 0.139 | 62.4% | +30.9% |
| Q3 high | 1,665 | 0.518 | 50.9% | +18.7% |
| Q4 extreme | 1,659 | 0.644 | 56.6% | -15.4% |

**Observation:** The model works well when there's something to predict (Q3-Q4: high variability = R²>0.5) and fails when SSC is nearly constant (Q1: low variability = R²~0.09, +33% bias). Low-variability sites are noise, not signal — the model would be better off predicting the site mean. This is a fundamental limitation of R² as a metric for flat signals.

### By Turbidity Level
| Turbidity | n | R² | MAPE | within-2x | bias |
|---|---|---|---|---|---|
| <10 FNU | 1,807 | 0.138 | 77.6% | 50.4% | -8.7% |
| 10-50 FNU | 2,048 | 0.442 | 58.1% | 61.8% | -19.1% |
| 50-200 FNU | 1,271 | 0.205 | 48.8% | 72.9% | -1.6% |
| 200-1000 FNU | 665 | 0.348 | 39.1% | 75.9% | +4.4% |
| >1000 FNU | 43 | 0.805 | 43.6% | 60.5% | -1.3% |

**Observation:** Model is proportionally most accurate at HIGH turbidity (MAPE 39-44%, within-2x 60-76%). Worst at LOW turbidity (MAPE 78%, within-2x 50%). This makes sense — at low turbidity, other factors (dissolved organic matter, algae, fine clays) contribute to the FNU reading but don't carry SSC. The model can't distinguish turbidity-from-sediment vs turbidity-from-other-stuff at low levels.

### By SSC Level
| SSC Level | n | R² | MAPE | bias |
|---|---|---|---|---|
| Low <50 mg/L | 2,742 | -52.4 | 92.9% | +121.2% |
| Med 50-500 | 2,285 | -1.85 | 47.2% | +41.8% |
| High 500-5K | 802 | -0.12 | 35.3% | -18.1% |
| Extreme >5K | 18 | -0.77 | 59.1% | -46.9% |

**Observation:** R² is negative at EVERY SSC level when computed within-tier. This is expected and not alarming — R² within a narrow band is almost always negative because the model's errors are larger than the within-band variance. The MAPE tells the real story: 35% at high SSC (good), 93% at low SSC (terrible, but absolute errors are small — median 10 mg/L). The model systematically OVERPREDICTS low SSC (+121% bias) and UNDERPREDICTS extreme SSC (-47% bias). This is the compression problem.

### By Dominant Watershed Geology
| Geology | n | R² | MAPE | bias |
|---|---|---|---|---|
| Sedimentary, carbonate | 836 | 0.823 | 52.3% | +15.2% |
| Sedimentary, undifferentiated | 274 | 0.884 | 45.0% | -9.2% |
| Metamorphic, gneiss | 244 | 0.577 | 52.8% | +11.1% |
| Igneous, volcanic | 786 | 0.326 | 45.7% | -12.5% |
| Unconsolidated | 402 | 0.545 | 72.9% | +15.4% |

**Observation:** Carbonate and undifferentiated sedimentary sites are easiest (R²>0.8). Volcanic and unconsolidated sites are harder. This aligns with the SGMC analysis — geology genuinely affects the turbidity-SSC relationship.

---

## 4.2 Physics-Based Validation

### First Flush
- **Events identified:** 1,071 of 5,847 samples (18%)
- **Detection method:** precip_30d in bottom 25% AND flush_intensity in top 75%
- **SSC/turbidity ratio:** Flush 2.21, Normal 2.07 (1.07x elevation) — physics confirmed
- **Model performance:** R²=0.864 on flush events (better than normal R²=0.487)
- **Median bias:** +6.9 mg/L (slight overprediction)
- **Conclusion:** Model handles first flush well. The `flush_intensity` and `precip_30d` features are working.

### Hysteresis (Rising vs Falling Limb)
- **Rising limb samples:** 1,969 (34%)
- **Falling limb samples:** 3,878 (66%)
- **SSC/turbidity ratio:** Rising 2.03, Falling 1.84 — clockwise hysteresis confirmed
- **Model captures it:** Yes (predicted ratios move in correct direction)
- **Model accuracy:** Rising R²=0.535, Falling R²=0.648 — rising limb is harder
- **Conclusion:** The `rising_limb` feature is doing its job. Hysteresis is real and modeled.

### Extreme Events
- **Top 1% threshold:** 856 FNU (59 samples)
- **Top 5% threshold:** 410 FNU (303 samples)
- **Model R² on top 1%:** 0.788 (better than overall 0.665!)
- **Systematic underprediction:** -37% at top 1%, -26% at top 5%
- **Max turbidity in holdout:** 2,480 FNU (no samples above 4,000 FNU)
- **Conclusion:** Model ranks extreme events correctly but compresses the magnitude by ~37%. This is the heavy-tail / sensor-saturation problem. Turbidity sensors typically max out at 1,000-4,000 FNU — above that, the input flatlines while SSC keeps climbing. To improve extreme event prediction, we would need auxiliary data (discharge surge, rainfall intensity) to extrapolate beyond sensor ceiling. **This is a Paper 2 topic.**

### Snowmelt
- **Spring samples:** 1,606 (27%)
- **SSC/turbidity ratio:** Spring 2.26, Other 2.02 — OPPOSITE of snowmelt expectation
- **Spring R²:** 0.421 (worse than other seasons R²=0.700)
- **Conclusion:** Spring in this holdout set means storms and agricultural runoff, not snowmelt. Only 1 site above 50°N latitude. Need high-latitude sites to properly test snowmelt dynamics. Current holdout is biased toward temperate/subtropical US.

### Regulated Flow
- **Status:** Could not test — all holdout sites have dam_storage_density > 0
- **Conclusion:** Need to rethink the threshold. Maybe use dam_storage_density == 0 vs > median, or use GAGES-II reference/non-reference classification.

---

## Holdout Set Composition & Limitations

### What we have
- 76 sites, 5,847 samples, 19 HUC2 regions
- Latitude range: 21.4°N (Hawaii) to 59.2°N (Alaska)
- SSC range: 2 to 21,700 mg/L
- Turbidity range: 0 to 2,480 FNU
- Median 48 samples per site

### Gaps and biases
- **Eastern US dominated:** 54 of 76 sites between 35-45°N latitude
- **Single-site regions:** 8 regions have only 1 site (Alaska, Hawaii, Tennessee, etc.) — one bad site dominates the regional score
- **No sensor saturation data:** Max turbidity 2,480 FNU, zero samples above 4,000 FNU
- **Few high-latitude sites:** Only 1 site above 50°N — can't test snowmelt
- **17 thin sites:** Have <20 samples — unreliable per-site statistics
- **1,248 "unknown" method samples** still in holdout (13 unresolvable sites) — suspicious R²=0.873

### Turbidity Sensor Saturation Problem
Most USGS turbidity sensors max out at 1,000-4,000 FNU. Above the sensor ceiling, the turbidity reading flatlines while SSC continues to climb. This means:
1. The model receives a clipped input during extreme events
2. It literally cannot predict extreme SSC from saturated turbidity
3. The 37% underprediction at top 1% is partly this
4. The `turb_saturated` feature (on the drop list) flags these but can't fix them
5. Auxiliary data (discharge, precip intensity, antecedent conditions) would be needed to extrapolate
6. This is a fundamental sensor limitation, not a modeling failure

---

## Site Recovery & External Validation Options

### Internal Recovery (re-run pipeline with fixes)

| Scenario | Additional Sites | Est. Samples | Confidence | Effort |
|---|---|---|---|---|
| A: Re-assemble 17 failed sites | +17 | ~952 | HIGH | Low |
| B: Re-qualify 107 rejected sites | +107 | ~5,350 | MEDIUM | High (full API re-query) |
| Current baseline | 396 | 35,209 | — | — |

- **17 sites** qualified but produced zero pairs during assembly. Pipeline fixes (timezone, dedup, QC codes) may recover them.
- **107 sites** had continuous turbidity but failed qualification (insufficient temporal overlap or too few SSC samples). Fresh metadata query might find better overlap.
- **623 sites** have no continuous turbidity — unrecoverable without new instrumentation.

### External Validation Sources (researched 2026-03-30)

**Core problem:** Truly independent paired continuous-turbidity + lab-SSC data is rare outside USGS. USGS dominates the turbidity-surrogate approach in the US.

**Tier 1 — Most actionable:**

| Source | Sites | Data Type | Access | Effort |
|---|---|---|---|---|
| WQP non-USGS providers | ~20-50? | Same API, filter providers≠USGS | Same dataretrieval API | Low |
| Susquehanna River Basin Commission (SRBC) | 60 turb + 26 SSC stations | 15-min continuous turb + discrete SSC | Contact wmrussell@srbc.gov | Medium |
| UK Littlestock Brook (UKCEH) | 3 sites | 5-min turb + lab SSC, 2017-2021 | Free CSV download | Low |
| USFS Turbidity Threshold Sampling | Unknown | Paired turb-SSC at forest experiment stations | Contact USFS PSW Research Station | Medium |

**Tier 2 — Limited:**

| Source | Issue |
|---|---|
| USDA ARS watersheds | Rich SSC but no continuous turbidity archived |
| Canada HYDAT | Thousands of SSC stations, zero turbidity |
| France/Germany national networks | Focus on discharge, not turbidity-SSC |
| Wurm River dataset (RWTH Aachen) | Paired turb-SSC 2016-2018, may have restricted access |
| State agencies (CA DWR, OR DEQ, WA Ecology, MN PCA) | Either no continuous turb, SSC done by USGS (not independent), or grab-only |

**Recommended action order:**
1. Query WQP for non-USGS providers with both turbidity (63680) and SSC (80154) — fastest, same infrastructure
2. Download UK Littlestock Brook — small but proves international generalization
3. Contact SRBC — potentially large independent dataset, same continent
4. Re-run qualification pipeline on 107+17 sites with bug fixes — recovers internal data

**Circularity warning:** Must verify any external SSC data is from LAB ANALYSIS, not estimated from turbidity. Turbidity-derived SSC would be circular validation.

**NTU vs FNU handling:**
- Most external data uses NTU (white light nephelometry), our model is trained on FNU (infrared)
- NTU ≈ FNU below ~400, diverge significantly above that (NTU reads lower for same water)
- **For validation now:** Filter to turbidity < 400 NTU where NTU ≈ FNU. Fair comparison.
- **Future (training integration):** Add NTU sites to training data with a new sensor_family category (e.g., "ntu_white_light"). Let the model learn NTU-specific turbidity-SSC relationships natively rather than applying an external conversion factor. This is cleaner because the NTU-FNU relationship depends on particle characteristics that vary by site — exactly the kind of thing CatBoost can learn from watershed features.
- **TODO:** When integrating NTU training data, add "ntu" as a sensor_family category, and potentially add a "turb_unit" feature (FNU vs NTU) as a separate categorical.

---

## Expert Panel Findings (2026-03-30)

**Panel:** Dr. Marcus Rivera (USGS hydrology, ret.), Dr. Ananya Krishnamurthy (environmental statistics), Dr. Catherine Ruiz (sediment transport). Independent reviews, no discussion phase.

**NOTE:** Panel was given stale adaptation numbers (old 2-param curve, not current Bayesian k=15). Rivera's "deeply disappointing" adaptation comment is based on wrong data. Statistical and physics insights remain valid. Full reviews in reviews/ directory.

### Key Insight: Low-SSC Overprediction is Sensor Contamination (Ruiz)
At low turbidity, the FNU reading comes from dissolved organic matter, algae, fine colloids, and air bubbles — not sediment. The model correctly learned turbidity→SSC but the input itself is contaminated. No loss function or model architecture change fixes contaminated inputs. This means low-turbidity predictions should have much wider uncertainty bounds.

### Key Insight: Extreme Underprediction is Particle Size Shift (Ruiz)
The -37% underprediction at top 1% is NOT mostly sensor saturation (only 15-25%). The dominant factor is particle size distribution shift during floods — coarse particles add mass (scales with diameter³) but barely change light scattering. Turbidity fundamentally cannot fully capture extreme SSC.

### Key Insight: Within-Tier R² Must Be Removed (Krishnamurthy)
R² within a narrow SSC band is guaranteed negative because within-band variance is small by construction. It's misleading. Replace with MAPE/MAE/conditional bias in within-tier tables.

### Key Insight: NSE ≈ R² for Our Computation (Krishnamurthy)
Our R² is computed as 1-SS_res/SS_tot, which IS Nash-Sutcliffe Efficiency. We just need to label it and add log-NSE (same formula on log-transformed values, emphasizes low-flow accuracy).

### Mandatory Additions Before Publication (all three agree)
1. NSE, log-NSE, KGE decomposition in all metric tables
2. Bootstrap 95% confidence intervals on disaggregated metrics
3. Baseline comparisons: site-mean predictor, per-site OLS power law
4. Load error ratios (integrated sediment mass over time)
5. Report Alaska/Hawaii separately from pooled metrics

### Additional Tests Recommended
- Algal interference: correlate low-turb failures with warm season + high DO (Ruiz)
- Temporal stationarity: 5-step protocol provided by Krishnamurthy
- Temperature-viscosity effects on settling rate (Ruiz)
- Wildfire structural breaks (Ruiz)
- Sediment supply limitation (Ruiz)
- dQ/dt as auxiliary feature for extreme events (Rivera)
- 7 adversarial stress tests specified by Krishnamurthy

---

## Questions for Expert Panel

1. The "unknown" collection method sites have R²=0.873 — best of any group. Is this because they're genuinely easy sites, or is the model using "unknown" as an informative signal? Should we investigate whether resolving them would hurt performance?

2. Low-SSC bias (+121%) is the worst failure mode by far. Is this because the model's loss function (RMSE on Box-Cox space) doesn't penalize low-SSC overprediction enough? Would asymmetric loss help?

3. The within-tier R² is negative at every SSC level. Is there a better metric for evaluating predictions within narrow concentration bands? Should we be using MAPE or within-2x as the primary metric instead of R²?

4. Spring SSC/turbidity ratio is higher, not lower. Is this because our holdout lacks snowmelt sites, or because spring storms genuinely produce more sediment per unit turbidity than other seasons?

5. What other physics-based phenomena should we test that we haven't thought of? (e.g., diurnal cycling, bank erosion events, algal blooms affecting turbidity)

6. The model does BETTER on extreme turbidity (>1000 FNU, R²=0.805) than low turbidity (<10 FNU, R²=0.138). Is this expected from a tree-based model? Does this suggest low-turbidity predictions should have wider uncertainty bounds?

7. For the sensor saturation problem: what auxiliary data sources could help predict SSC when turbidity is clipped? Would discharge rate-of-change, cumulative precipitation, or soil moisture help?

8. Are there standard goodness-of-fit statistics used in hydrology/sediment transport that we should be computing but aren't? (e.g., Nash-Sutcliffe, percent bias decomposition, flow-duration curve statistics)
