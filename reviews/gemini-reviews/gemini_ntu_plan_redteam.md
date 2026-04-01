# Red Team Review Request: NTU Integration Plan for ML Sediment Model

## What This Is

We're expanding our CatBoost SSC prediction model (currently trained on FNU infrared turbidity) to also handle NTU (white light nephelometry) turbidity data. The model currently achieves:
- Vault (36 clean sites): MedSiteR²=0.486, MAPE=49.4%
- External NTU (260 non-USGS sites): Spearman=0.93 zero-shot, R²=0.43 with 10 calibration samples, but +66% systematic bias without calibration

We want the model to handle NTU natively so the bias disappears without requiring calibration.

## The Proposed Architecture: Parallel FNU + NTU Columns

Instead of a categorical flag (turb_unit = 'FNU' vs 'NTU') or separate training rows, we use parallel feature columns:

**FNU columns:**
- `turbidity_instant_fnu` — FNU reading (NaN if site only has NTU)
- `turbidity_max_1hr_fnu` — Max FNU in 1hr window (NaN if NTU-only)
- `turbidity_std_1hr_fnu` — Std of FNU in 1hr window (NaN if NTU-only)

**NTU columns:**
- `turbidity_instant_ntu` — NTU reading (NaN if site only has FNU)
- `turbidity_max_1hr_ntu` — Max NTU in 1hr window (NaN if NTU-only)
- `turbidity_std_1hr_ntu` — Std of NTU in 1hr window (NaN if NTU-only)

**Three scenarios per training row:**
1. FNU-only site: FNU columns populated, NTU = NaN
2. NTU-only site: NTU columns populated, FNU = NaN
3. Dual-sensor site (89 sites have both): BOTH columns populated where timestamps overlap

CatBoost handles NaN natively. The model learns to route through whichever turbidity type is available.

## Data Sources

1. **89 existing USGS sites** with both FNU (pCode 63680) and NTU (pCode 00076) — the bridge sites
2. **NTU-only USGS sites** — sites with NTU continuous + SSC samples but no FNU (to be discovered)
3. **260 external non-USGS NTU sites** — already downloaded (UMRR, SRBC, GLEC, UMC, MDNR, CEDEN)

## The Three Phases

**Phase 7A:** Add NTU columns to existing paired dataset at the 89 dual-sensor sites. Find NTU-only SSC samples at those sites (time periods before FNU was installed). Retrain, evaluate.

**Phase 7B:** Discover and add NTU-only USGS sites. Reserve ~20 as NTU vault. Retrain, evaluate.

**Phase 7C:** Add external non-USGS NTU sites to training. Final model with all NTU sources. Full eval.

## What We Want You to Check

1. **Is the parallel column architecture the right approach?** Could there be issues with CatBoost's tree-splitting behavior when one of two correlated feature sets is always NaN? Would a categorical flag (turb_unit) be simpler or more effective?

2. **The column rename is a breaking change** (turbidity_instant → turbidity_instant_fnu). Every script, drop list, monotone constraint, and meta.json must be updated. Is there a safer way to integrate NTU without renaming existing columns?

3. **Dual-sensor temporal overlap:** The 89 sites likely had NTU first, then upgraded to FNU. There may be very little temporal overlap where BOTH sensors were active simultaneously. If most dual-sensor data is sequential (NTU pre-2010, FNU post-2010), the model sees FNU and NTU at different SSC conditions at different times, not paired readings. Is this a problem?

4. **NTU diverges from FNU above ~400 NTU/FNU.** The divergence depends on particle characteristics (size, color, mineralogy). Can CatBoost learn this geology-dependent conversion from 89 bridge sites, or do we need explicit conversion features?

5. **External NTU data has no continuous record** — only grab-sample turbidity. The window stats (max_1hr_ntu, std_1hr_ntu) will always be NaN for external data. Does this create an informative missingness problem where the model learns "NaN window stats = external site" rather than the actual turbidity-SSC relationship?

6. **Monotone constraints:** We enforce SSC increases with turbidity (monotone on turbidity_instant_fnu and turbidity_max_1hr_fnu). Should the same constraint apply to NTU columns? NTU-SSC should also be monotone in theory, but the NTU-SSC relationship may be noisier.

7. **The NTU vault:** We plan to reserve ~20 NTU-only USGS sites as a clean test set. How should these be selected? Should they be geographically diverse, or should they mirror the external validation sites' characteristics?

8. **Data bleed risks:** The existing 76 validation sites and 36 vault sites are FNU-only. If any of them also have NTU data, should we add NTU columns to those rows? Or does that contaminate our historical benchmark?

9. **What would you do differently?** Is there a fundamentally better approach to multi-sensor integration that we're not considering?

## Supporting Context

### Current Model (v9)
- 72 features (69 numeric + 3 categorical)
- 254 training sites (284 - 30 without StreamCat)
- Box-Cox lambda=0.2 transform, Snowdon BCF
- 3-way split: 284 train / 76 validation / 36 vault
- Bayesian site adaptation with Student-t shrinkage (k=15, df=4)

### External NTU Validation Results (v9, zero-shot)
- Spearman rank correlation: 0.93 (excellent ranking despite wrong sensor type)
- Systematic bias: +66% (overpredicts because NTU reads lower than FNU at same SSC)
- With 10 calibration samples: R²=0.43, bias drops to +40%
- UMRR (Upper Mississippi, 9625 samples): best performer, NSE=0.40
- UMC (Missouri, 636 samples): catastrophic +474% bias — likely data quality issue

### FNU vs NTU Physics
- Both measure light scattering at 90° but different wavelengths
- FNU: infrared (860nm) — less affected by particle color
- NTU: white light (broadband) — affected by particle color, algae, dissolved organics
- Below ~400 units: roughly equivalent
- Above ~400: diverge, magnitude depends on particle mineralogy and size distribution
- USGS standard is FNU (pCode 63680); NTU (pCode 00076) is older/supplementary

### Key Finding from Site Contribution Analysis
"Noise" sites (that hurt average predictions) carry the only signal for extreme events and first flush. Dropping 15 worst noise sites collapsed First Flush R² from 0.905 to 0.264 and Top 1% Extreme R² from 0.793 to -0.043. This means we CANNOT aggressively prune NTU sites that look "bad" on aggregate metrics.

## Please be thorough. The FNU-NTU divergence is physically real and geology-dependent. A naive integration could make the model worse, not better.
