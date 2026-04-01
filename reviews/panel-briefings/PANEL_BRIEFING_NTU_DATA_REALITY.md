# Expert Panel Briefing — NTU Data Reality (2026-03-30)

## The Situation

We planned to integrate NTU turbidity data to teach the model to handle both FNU and NTU sensors natively. After thorough investigation, here's what we actually found:

### What Exists
- **89 of our 396 USGS sites** have discrete NTU grab samples (pCode 00076)
- **7,443 NTU measurements** across these 89 sites, dating 1976-2005
- **3,646 NTU-SSC same-day pairs** at 67 sites (hydrographer collected both on same visit)
- **260 external non-USGS sites** with discrete NTU grab samples (11K samples, UMRR/SRBC/etc.)

### What Does NOT Exist
- **Zero continuous NTU sensor data anywhere in the USGS network.** Verified across 15 states, all turbidity parameter codes, both legacy and modern APIs.
- Per USGS TM 2004.03 (2004): continuous = FNU (pCode 63680), discrete lab/field = NTU (pCode 00076). By design since 2004.

### The Overlap Problem
- All 89 sites started FNU continuous monitoring in 2006 or later
- All NTU discrete data ends by 2005
- **Zero temporal overlap between NTU discrete and FNU continuous at any site**
- No FNU-NTU-SSC triplets are possible
- The "dual-sensor bridge" we planned (learn FNU-NTU conversion from concurrent readings) cannot be built

### What We'd Be Adding
3,646 new training rows, each with:
- `turbidity_instant` = discrete NTU reading from hydrographer's field instrument
- `sensor_type` = 'NTU' (new categorical)
- `turbidity_instant_alt` = NaN (no FNU available — different era)
- `turbidity_max_1hr`, `turbidity_std_1hr` = NaN (no continuous record)
- SSC lab value from same visit
- Same watershed features (SGMC, StreamCat) as existing rows at these sites

This is a ~16% expansion of our 23,088 training samples.

### The Question for You

Given this reality, should we:

**Option A: Proceed with integration.** Add the 3,646 NTU-SSC pairs as new training rows. The model gets more SSC samples at known sites (historical data from 1976-2005). The `sensor_type` categorical flag teaches it that NTU readings should be interpreted differently. No FNU-NTU conversion learning is possible, but the model learns the NTU-SSC relationship directly.

**Option B: Skip NTU integration for now.** The value proposition has shrunk considerably — no continuous NTU, no triplets, no conversion learning. The 3,646 samples are from a different era (pre-2005) when land use, climate, and sampling methods may have differed. Focus efforts elsewhere.

**Option C: Proceed but cautiously.** Add the data but run extensive validation to ensure it doesn't degrade FNU predictions. The historical NTU samples might introduce temporal bias (1976-2005 vs 2006-present represent different watershed conditions).

### Additional Context

- The model currently overpredicts by +66% on external NTU data (zero-shot). With 10 calibration samples, R²=0.43.
- Historical NTU samples would have NaN for ALL window stats (max_1hr, std_1hr) — same as the external NTU grab samples.
- The model's handling of NaN is native (CatBoost routes around missing features).
- Our site contribution analysis showed "noise" sites carry extreme event signal — adding historical data from the same sites might help OR hurt.
- NTU field measurements were taken with white-light instruments that are affected by water color (DOM, tannins) — this is a fundamentally different measurement than FNU at low concentrations.

### Your Questions to Answer

1. Given no FNU-NTU overlap, is the 3,646-sample expansion worth the complexity of adding `sensor_type` and `turbidity_instant_alt`?
2. The NTU data is from 1976-2005, the FNU data from 2006+. Is temporal bias a concern? Land use, climate, and sensor calibration have all changed.
3. Would adding rows where 3 of 6 turbidity features are NaN (window stats) dilute the signal the model learns from complete FNU rows?
4. For the external NTU validation (+66% bias): will adding 3,646 USGS NTU training samples actually reduce this bias, or do we need the FNU-NTU conversion relationship that we can't learn?
5. Is there a simpler path to handling NTU at inference time (e.g., just apply Bayesian adaptation with 10 samples, which already gets R²=0.43)?
6. What would you recommend?
