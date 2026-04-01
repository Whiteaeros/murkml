# NTU Integration Findings (2026-03-30)

## The Decision: Do NOT integrate NTU into training. Use for validation only.

Unanimous expert panel (Rivera, Krishnamurthy, Ruiz) + Gemini red-team all agree.

## Why

### The Data Reality
- USGS has ZERO continuous NTU sensor data. Per TM 2004.03 (2004): continuous = FNU (pCode 63680, ISO 7027 infrared), discrete lab/field = NTU (pCode 00076, EPA 180.1 white light). By design.
- 89 of our 396 sites have discrete NTU grab samples (1976-2005). All started FNU continuous in 2006+.
- **Zero temporal overlap** between NTU and FNU eras at any site.
- 3,646 NTU-SSC same-day pairs at 67 sites. No FNU continuous available at those timestamps.

### Why Not Train On It
1. **Total confounding:** sensor_type is perfectly confounded with era. The model can't distinguish "NTU physics" from "1980s watershed conditions." A reviewer would flag this immediately.
2. **3/6 turbidity features NaN:** No continuous record = no window stats (max_1hr, std_1hr). Dilutes the signal from complete FNU rows.
3. **Temporal bias:** 1976-2005 had different land use, climate, sampling methods, and possibly different SSC lab procedures than 2006+.
4. **Marginal benefit:** Would reduce external NTU bias from +66% to maybe +45%. Not a real fix.
5. **Bayesian adaptation already works:** 10 calibration samples achieves R²=0.43 on foreign NTU data. This is the correct path.

## What We Have for Validation
- 3,646 USGS NTU-SSC pairs (67 sites, 1976-2005)
- 7,474 raw NTU discrete samples (89 sites) — saved at `data/discrete_ntu_raw_89sites.parquet`
- 260 external non-USGS NTU sites (11K samples, UMRR/SRBC/GLEC/UMC/MDNR/CEDEN)
- All preserved for adaptation curve characterization, not training

## Paper Framing (from Gemini + panel)

### The +66% Bias is a Feature, Not a Bug
- The model systematically overpredicts SSC when given NTU input because NTU reads higher than FNU for the same water (white light absorbed by DOM/tannins)
- This is an optical hardware reality, not a model error
- The bias is physically explainable and predictable

### The "Time Travel" OOD Test
- Validating with 1976-2005 NTU data isn't just a cross-sensor test — it's a cross-DECADE test
- Modern watershed features (StreamCat 2016 land cover, SGMC geology) predicting 1983 sediment
- Proves temporal out-of-distribution generalization
- Makes the Bayesian adaptation look twice as powerful

### R²=0.43 on NTU is the Floor
- The model is missing its high-frequency features (window stats are NaN for all NTU)
- It's also missing hysteresis context (discrete grab samples don't capture rising vs falling limb)
- A hypothetical continuous NTU sensor would give the model more features and likely better performance
- 0.43 is what you get with just `turbidity_instant` and watershed features

### The Adaptation Narrative
- Zero-shot on foreign sensors: Spearman 0.93 (correct ranking), +66% bias (wrong scale)
- 10 calibration samples: R²=0.43, bias drops to +40%
- This proves the adaptation architecture is necessary for real-world deployment
- "A model that exhibits a known, physically explainable zero-shot bias which is elegantly corrected by Bayesian adaptation is a bulletproof, high-impact narrative" — Gemini

## Future Considerations

### NTU→FNU Bridge Model (Gemini suggestion)
- A small preprocessing model trained on the 3,646 NTU-SSC pairs
- Maps NTU readings to FNU-equivalents before feeding to the main model
- Not part of the main CatBoost model — an optional front-end for legacy data users
- Could be as simple as quantile regression

### Lab Method Drift (Gemini flag)
- Did USGS change SSC lab methods between 1980s and 2020s? (oven temperatures, filter types)
- If the target variable itself shifted, that's another reason the historical data is incompatible
- Worth investigating for the paper's methods section

### Revisit Conditions
- Only revisit NTU training integration if concurrent FNU-NTU data becomes available
- State agencies or international networks with dual-sensor installations would provide the bridge
- Without concurrent data, the era confounding is insoluble

## USGS Turbidity Parameter Reference

| Code | Unit | Method | Use |
|---|---|---|---|
| 63680 | FNU | ISO 7027 (infrared, 90°) | Continuous sondes (all modern USGS) |
| 00076 | NTU | EPA 180.1 (white light) | Discrete lab/field samples |
| 63675 | FNRU | ISO 7027 (ratio) | Some older sensor models |
| 63676 | NTRU | Nephelometric ratio | Ratio-based sensors |

Reference: USGS OWQ Technical Memorandum 2004.03
