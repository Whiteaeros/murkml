# Expert Panel Briefing — Data Patterns & Next Steps (2026-03-30)

## Context

The v9 model is checkpointed. 72 features, vault MedSiteR²=0.486, external NTU R²=0.43 at N=10. Feature set is locked. Site contribution analysis complete. NTU integration decided (validation only). We're now in the exploration and paper-preparation phase.

We've uncovered several interesting patterns in the data. We want your help finding MORE patterns we haven't thought of, and identifying what else we should test or report before considering the model "finished."

## Patterns We've Found

### 1. Time-of-Day is Really Collection Method
- Night (midnight-5am): 85% auto_point (ISCO storm samplers), median SSC 133-206 mg/L, error 60-67%
- Afternoon (1-5pm): 80% depth_integrated (hydrographers working business hours), median SSC 28-38 mg/L, error 56-62%
- The model's 6 AM accuracy peak (46% error) isn't about the hour — it's about the transition between storm capture and routine sampling

### 2. Weekend vs Weekday
- Weekend: mostly auto_point storm captures, median SSC 107-124, error 45-52%
- Weekday: mostly depth_integrated routine, median SSC 40-44, error 57-59%
- The model performs BETTER on storm events than calm conditions

### 3. Extreme Events are Easier than Normal Conditions
- Top 5% turbidity (>410 FNU): R²=0.722, MAPE=39.6%
- Normal (<410 FNU): R²=0.403, MAPE=56.5%
- During storms, turbidity→SSC signal is strong and clear
- During baseflow, DOM/algae/colloids contaminate the turbidity signal

### 4. Adaptation HURTS Extremes at High N
| N_cal | Extreme R² | Normal R² |
|---|---|---|
| 0 | 0.722 | 0.403 |
| 1 | 0.722 | 0.404 |
| 5 | 0.723 | 0.408 |
| 10 | 0.722 | 0.410 |
| 20 | **0.295** | 0.404 |

At N=20, extreme R² collapses from 0.722 to 0.295. The Bayesian adaptation optimizes for normal conditions (which dominate the calibration samples) and overcorrects storm events.

### 5. SSC Trends Over Time
- 125 of 254 training sites show significant SSC trends (p<0.05)
- 56 increasing, 69 decreasing
- Strongest increase: USGS-12187500 (Pacific NW, rho=0.852)
- Strongest decrease: USGS-372525121584701 (rho=-0.791)

### 6. SSC/Turbidity Ratio by Collection Method
| Method | Median Ratio | n |
|---|---|---|
| auto_point | 2.10 | 14,444 |
| depth_integrated | 1.71 | 15,381 |
| grab | 1.56 | 4,638 |
| unknown | 1.75 | 746 |

Auto_point (ISCO near-bed) reads 35% more SSC per unit turbidity than grab (surface).

### 7. Almost All Sites are Transport-Limited
- 179 sites: more discharge = more SSC (transport-limited)
- 3 sites: more discharge = less SSC (supply-limited)
- No sites have truly broken turbidity-SSC relationships (all rho > 0.3)

### 8. Conductance is Anti-Correlated with Turbidity
- Overall rho = -0.171
- Storms: high turbidity + low conductance (rainwater dilution)
- Baseflow: low turbidity + high conductance (mineral-rich groundwater)

### 9. ISCO Burst Sampling
- 213 site-days have 10+ samples (max 66 in one day)
- These capture full storm hydrographs within hours
- Rich data for hysteresis and sediment exhaustion dynamics

### 10. Seasonal SSC
- Winter/spring peak: Jan 76 mg/L, May 79 mg/L
- Summer/fall trough: Aug-Oct ~35 mg/L
- Freeze-thaw + spring storms vs summer baseflow

## Model Performance Summary

| Dataset | Pooled NSE | MedSiteR² | MAPE | Spearman |
|---|---|---|---|---|
| LOGO CV (254 training) | — | 0.335 | — | — |
| Validation (76 sites) | 0.692 | 0.418 | 55.6% | 0.920 |
| Vault (36 clean sites) | 0.164 | 0.486 | 49.4% | 0.932 |
| External NTU zero-shot | 0.152 | — | 90% | 0.929 |
| External NTU N=10 | — | 0.430 | 45% | 0.931 |

## What We Want From You

1. **What other patterns should we look for in this data?** Think about things we haven't explored: spatial autocorrelation, sensor drift signatures, multivariate interactions, data quality indicators, etc.

2. **The adaptation hurting extremes at N=20 is concerning.** What causes this? Should we use flow-stratified adaptation? How would you fix this?

3. **What additional validation tests would make this model "paper-ready"?** What would a WRR reviewer demand that we haven't done?

4. **Are there any red flags in the patterns we've found?** Anything that suggests a bug, data quality issue, or methodological concern?

5. **What figures should be in the paper?** Which of these patterns are publishable findings vs background noise?

6. **What are we missing?** What haven't we thought about?
