# murkml Product Vision

Written 2026-03-16 from conversation between Kaleb and Claude. This is the authoritative description of what we're building.

---

## What It Is

A site-adaptive, multi-target water quality estimation system. A user points at a location on a river and the model predicts a full suite of water quality parameters using whatever data is available — from a full USGS sensor array down to just a lat/lon coordinate.

This is NOT a turbidity-to-sediment regression tool. Turbidity-SSC is the proof of concept, not the product.

## How It Works

1. **User provides a location** on a river (lat/lon or site ID)
2. **Model automatically pulls** publicly available catchment attributes for that location — land cover, geology, soils, drainage area, climate, upstream characteristics
3. **User provides whatever sensor data they have** — could be 6 continuous sensors, could be just a turbidity probe, could be nothing
4. **User provides whatever grab sample data they have** — could be hundreds of lab results, could be one, could be none
5. **Model predicts the full suite** of water quality parameters with uncertainty intervals that honestly reflect how much data it has to work with

More data = tighter intervals. Less data = wider intervals. The model always produces an estimate but never lies about its confidence.

## Key Design Principles

### Graceful degradation
Missing inputs are fine. The model handles them natively (CatBoost routes around missing features). A site with 6 sensors and 200 grab samples gets tight prediction intervals. A site with just location attributes gets intervals so wide they honestly say "I don't know much."

### Multi-target because chemistry demands it
Parameters are chemically interconnected. Phosphorus binds to sediment (SSC predicts TP). Temperature controls DO saturation. Conductance reflects TDS. Nitrate cycles seasonally with biology. Predicting them independently throws away signal. The model should predict them jointly so inter-parameter relationships act as implicit constraints.

**Open question:** The exact multi-target architecture (shared backbone with multiple heads vs. prediction chain vs. something else) needs expert research before deciding. Flagged for the technical expert panel.

### Physics-guided ML — physics is the foundation, not decoration
The ML layer sits ON TOP OF a physics layer. Known, published, verified physical and empirical relationships serve as guardrails during training. The model pays a penalty for violating physics, so it naturally learns to stay within physical bounds.

**Critical rule:** Every physical constraint must be a well-established, published empirical relationship confirmed by domain experts BEFORE implementation. A wrong physics constraint is worse than no constraint — it forces the model to learn something false.

Examples of candidate constraints (need expert confirmation):
- DO saturation as f(temperature, pressure) — Benson & Krause 1984
- Conductance-TDS proportionality (geology-dependent, 0.55-0.75 range)
- Non-negative concentrations
- Mass balance
- Temperature-dependent equilibrium chemistry

Examples of relationships that are NOT universal (do NOT enforce globally):
- Turbidity-SSC monotonicity — breaks across sites due to grain size variation
- Specific C-Q relationships — vary by watershed

### Output quality is only as good as calibration data
This must be obvious to the user. The system should clearly communicate what data it's working with and how that affects confidence. A prediction from 6 sensors + 200 lab samples is fundamentally different from a prediction from just a lat/lon, and the user must understand that.

## What Parameters

The "full suite" needs to be defined by an expert panel (soil/water chemistry, hydrogeology, ML). Criteria:
- Common pollutants of concern with regulatory importance
- Sufficient USGS data to train cross-site models
- Chemically interconnected (so multi-target learning adds value)
- Not so many that complexity explodes

Current working list (needs expert review):
- Suspended sediment concentration (SSC) — proof of concept, done
- Total dissolved solids (TDS) — near-linear with conductance, easy extension
- Nitrate+nitrite — seasonal cycling, strong multi-sensor signal
- Total phosphorus — binds to sediment, strong SSC connection
- Dissolved oxygen — temperature-dependent, well-understood physics

NOT in scope: E. coli (different domain), ocean parameters, atmospheric.

## Development Phases

1. **Fix bugs in current pipeline** (in progress)
2. **Get honest SSC baseline numbers** with proper evaluation
3. **Extend to multi-parameter** — this is core to the product, not a stretch goal
4. **Implement physics-guided constraints** (after expert panel confirms relationships)
5. **Package and release v0.1.0**
6. **Publish** — dataset paper + methods paper + JOSS software paper
7. **Geospatial wrapper** — auto-lookup of catchment attributes from any lat/lon (future phase, separate from model)

## Open Questions for Expert Panels

### Technical Panel (ML + domain)
- Multi-target architecture: shared backbone vs. prediction chain vs. hybrid?
- Which physical constraints are universal enough to enforce?
- Minimum data requirements per parameter for useful predictions?

### Domain Panel (chemistry + hydrogeology)
- Which parameters should be in the "full suite"?
- Which inter-parameter relationships are well-established enough to encode?
- What empirical equations are confirmed and published for each constraint?
- Are there parameters where the chemistry is too complex or site-specific to generalize?

## What This Is NOT

- Not a per-site regression tool (USGS already does that)
- Not a forecasting tool (we predict current conditions, not future)
- Not limited to USGS sites (any river location, eventually)
- Not a sensor QC tool (that's a separate module, later)
- Not a web app (the model is a Python library; UI is a future wrapper)
