# Expert Panel Synthesis — Data Patterns & Next Steps (2026-03-30)

## Source: Three independent reviews (Rivera, Krishnamurthy, Ruiz) — briefing-only versions
## Data-exploring versions still running — will update when complete

## UNANIMOUS DEMANDS (all three flagged independently)

### 1. Hysteresis Classification on ISCO Burst Data
- 213 site-days with 10+ samples = gold mine for hysteresis analysis
- Classify each storm as clockwise (proximal source) vs counterclockwise (distal source)
- Correlate hysteresis type with model error
- Publishable sub-analysis on its own

### 2. Spatial Autocorrelation (Moran's I)
- Are nearby sites making similar errors?
- If significant: effective sample size is smaller than we think, LOGO CV overstates performance
- A WRR reviewer WILL catch this

### 3. Bootstrap Confidence Intervals on ALL Metrics
- MedSiteR²=0.486 means nothing without CIs
- Resample sites, not samples
- Non-negotiable for publication

### 4. Formal Benchmark vs Site-Specific OLS
- USGS standard: site-specific log-log OLS (Rasmussen et al. 2009)
- Compare at N=0, 5, 10, 20 calibration samples
- If we don't beat site-specific OLS at N=10+, the value proposition collapses

### 5. Investigate Vault NSE=0.164
- Much lower than validation NSE=0.692
- A few catastrophic sites are dragging it down
- Must characterize which sites and why

## KEY FINDINGS ABOUT N=20 ADAPTATION COLLAPSE

**All three agree on the mechanism:** Baseflow-dominated calibration samples rotate the relationship away from storm physics.

**Rivera:** Flow-stratified adaptation (event vs baseflow), cap adaptation magnitude at high turbidity, weighted adaptation loss
**Krishnamurthy:** Cap at N=10, report as a finding ("more calibration is not always better when biased toward baseflow")
**Ruiz:** "Sediment population switching problem" — baseflow turbidity is DOM/algae, storm turbidity is mineral sediment. Two different physical regimes sharing one sensor.

## RED FLAGS IDENTIFIED

1. **Only 3 supply-limited sites** — geomorphologically implausible. Likely seasonal effects masking detection, or geographic selection bias (Rivera, Krishnamurthy)
2. **SSC trends at 125/254 sites** — violates stationarity assumption. Need to address in paper. (Rivera)
3. **Vault NSE=0.164** — catastrophic sites not yet characterized (Rivera, Krishnamurthy)
4. **External NTU MAPE=90%** — do not frame zero-shot NTU as success (all three)
5. **Collection method as confound** — correlated with time, flow, SSC, ratio. Needs formal decomposition (Ruiz)

## RECOMMENDED PAPER FIGURES (consensus)

1. **Adaptation curve with extreme/normal split** — shows N=20 collapse on extremes
2. **Turbidity-SSC by collection method** — the 35% ratio difference is a key finding
3. **Performance map** — site locations colored by R² (shows spatial patterns)
4. **Comparison with OLS at various N** — the value proposition figure
5. **Storm time series** — example ISCO burst showing predictions tracking the hydrograph
6. **Residual diagnostics** — predicted vs observed, residuals vs turbidity level

## ADDITIONAL ANALYSES RECOMMENDED

- Grain size effects (if data available: USGS pCode 70331 percent fines)
- Discharge-normalized SSC (SSC/Q ratio across sites)
- Sensor type stratification of errors
- First-flush vs sustained event error evolution
- Temporal autocorrelation within sites (lag-1 on residuals)
- Rising vs falling limb performance (beyond the simple rising_limb binary)
- Sediment load calculations (annual tons predicted vs observed at 10-20 sites)
- FDR correction on the 125 SSC trend tests
- Prediction intervals with coverage validation
- Extrapolation behavior at unseen turbidity/SSC ranges

## WHAT WE'RE MISSING (biggest gaps)

1. **Uncertainty quantification** — no prediction intervals yet
2. **Load estimation** — the actual operational use case, never tested
3. **Sand fraction** — the classic turbidity-SSC confounder
4. **Sensor model heterogeneity** — different instruments read differently
5. **Bedload invisibility** — turbidity can't see 10-60% of total sediment transport in coarse systems
6. **Formal reproducibility** — code/data sharing preparation
