# Expert Panel Synthesis — Data Patterns & Next Steps (2026-03-30)

## Source: Three independent reviews (Rivera, Krishnamurthy, Ruiz)
## TWO rounds: briefing-only + data-exploring (with actual data access)
## Data-exploring versions completed — findings below supersede briefing-only

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

---

## DATA-DRIVEN FINDINGS (from agents with actual data access)

### CRITICAL: Systematic 1.42-1.44x Overprediction
- All three experts independently confirmed: median pred/obs ratio = 1.42-1.44
- 75% of ALL predictions are overpredictions (Wilcoxon p=6.2e-166)
- Worst at low SSC: 2.45x overprediction below 10 mg/L
- Reverses above 1000 mg/L: 0.72x (underprediction)
- **Root cause:** Snowdon BCF of 1.390 overcorrects, especially at low SSC
- 34 of 76 holdout sites overpredicted by 50%+, only 9 sites reasonably calibrated (ratio 0.8-1.2)

### CRITICAL: Data Quality Issues
- 391-430 records with absurd SSC/turbidity ratios (>50 or <0.01)
- SSC=70,000 at turbidity=260 (ratio 269) — almost certainly data entry error
- SSC=18,800 at turbidity=0.2 — clearly erroneous
- All in training data, actively harming model learning
- 77 sites affected

### N=20 Adaptation Collapse — Quantified
- Monte Carlo: 36% of N=20 random calibration draws contain ZERO storm samples (Ruiz)
- Driven by SSC range: sites with wide SSC range hurt by adaptation (rho=-0.541, p<0.001) (Rivera)
- Adaptation primarily rescues catastrophic sites (R² from -8 to ~0), doesn't help overpredicted sites (Krishnamurthy)

### Holdout is Systematically Harder Than Training
- Holdout SSC/turbidity ratio: 2.17 vs training 1.74 (Krishnamurthy)
- Pooled NSE=0.692 is misleading — sample-weighted mean site R² is only 0.224
- 28% of holdout sites have R² < 0, mean site R² = -0.075

### Power Law Exponents (Ruiz, 304 sites)
- Median log-log slope: 0.952 (close to linear)
- Range: 0.29 to 1.55 (huge cross-site variation)
- 50% of sites steepen at high turbidity (nonlinear), 32% flatten
- Geology predicts slope: metamorphic +0.17 (p=0.005), carbonate -0.15 (p=0.015)

### Hysteresis Analysis (Ruiz, 119 events from ISCO bursts)
- 39.5% clockwise (proximal source, exhaustion before peak)
- 24.4% counter-clockwise (distal source, sediment arrives after peak)
- 36.1% linear (no clear hysteresis)
- Rising limb SSC/turb ratio 16% higher than falling limb
- Aggregate signal weak (p=0.13) but individual sites show consistent patterns

### Sediment Exhaustion (Ruiz, burst events)
- 35% of burst events show declining SSC/turb ratio (classic supply exhaustion)
- 31% show increasing ratio (new source mobilization during event)
- Long-term ratio trends at 126/313 sites (89 increasing, 37 decreasing)
- Asymmetry (more increasing) may suggest sensor calibration drift, not real physics

### Site Characteristics Predicting Error (Rivera)
- Drainage area: rho=-0.375 (p=0.004) — small basins 2.5x worse
- 58% of holdout samples lack discharge data — performance 20% worse without it
- 65% of samples have unknown sensor_family — feature mostly uninformative
- Weak spatial autocorrelation: 30% more similar errors within 50km

### Residual Autocorrelation (Krishnamurthy)
- Lag-1 autocorrelation up to 0.69 at individual sites
- Effective sample sizes smaller than reported
- Per-site R² confidence intervals wider than assumed

### Between-Site vs Within-Site Variation (Ruiz)
- Between-site SSC/turb ratio CV = 4.37
- Within-site ratio CV = 1.35
- Site heterogeneity is 3.2x larger than event-to-event variability
- Confirms site adaptation is the right approach

## PRIORITY ACTIONS (from data-driven reviews)

1. **Fix BCF overprediction** — investigate site-specific or flow-stratified BCF
2. **Clean 391+ anomalous data records** — remove or flag SSC/turb ratio >50 or <0.01
3. **Cap adaptation at N=10** or implement flow-stratified adaptation
4. **Report honest metrics** — sample-weighted mean R²=0.224, not pooled NSE=0.692
5. **Bootstrap CIs** on all metrics
6. **Formal OLS benchmark** comparison
7. **Investigate holdout vs training ratio difference** (2.17 vs 1.74)
