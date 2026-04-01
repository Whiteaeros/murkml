# Site Diversity Expansion Plan: 35 Recommended Sites Across 8 Diversity Dimensions

**Authors:** Dr. Elena Vasquez (Hydrogeochemist) & Dr. Marcus Rivera (Hydrologist)
**Date:** 2026-03-17
**Purpose:** Design a maximally diverse set of 30-40 USGS monitoring sites to fill gaps in murkml's training set for SSC/TP prediction from continuous turbidity
**Current training set:** 57 sites across 11 states (KS, IN, CA, CO, OR, VA, MD, MT, OH, ID, KY)

---

## Executive Summary

The current 57-site training set covers roughly 5 of 25 EPA Level II ecoregions in the continental US, with heavy overrepresentation of Pacific maritime, Mediterranean California, and Great Plains prairie systems. We identify **35 recommended site-regions** organized across 8 diversity dimensions, targeting the most consequential gaps for model generalization. If all 35 sites yield adequate data, the expanded training set would cover approximately 16 of 25 Level II ecoregions and span the full range of US sediment transport regimes.

### Priority Summary

| Priority | Gap | Sites | Expected Impact |
|----------|-----|-------|-----------------|
| 1 | Loess belt (silt-dominated) | 6 | Fixes worst SSC failure mode |
| 2 | Gulf Coastal Plain (sandy, WWTP) | 5 | Opens Gulf Coast geography |
| 3 | Arid Southwest (extreme SSC, ephemeral) | 4 | Opens western third of CONUS |
| 4 | Iron Range / Canadian Shield | 3 | Fixes anomalous TP geochemistry |
| 5 | Southeast Piedmont / Coastal Plain | 3 | Opens SE US corridor |
| 6 | Karst / carbonate springs | 3 | Addresses groundwater-dominated systems |
| 7 | Urban stormwater / impervious | 3 | Addresses human influence gradient |
| 8 | Additional unique regimes | 8 | Fills remaining ecoregion and chemistry gaps |
| **Total** | | **35** | |

---

## Ecoregion Gap Analysis

### EPA Level II Ecoregions: Current Coverage Assessment

The continental US contains approximately 25 EPA Level II ecoregions. The current 11-state training set covers the following:

**Well-covered (>=5 training sites):**
- 9.2 — Temperate Prairies (KS, IN, OH)
- 10.1 — Columbia Plateau / Great Basin (OR, ID, CA)
- 11.1 — Mediterranean California (CA)
- 6.2 — Western Cordillera (CO, MT, ID, OR)
- 8.3 — Southeastern USA Plains (VA, MD, KY partially)

**Partially covered (1-4 training sites):**
- 8.1 — Mixed Wood Plains (OH marginally)
- 8.4 — Ozark/Ouachita-Appalachian Forests (KY marginally)
- 6.5 — Middle Rockies (MT, ID)

**Completely absent from training set:**
- 9.3 — West-Central Semi-Arid Prairies (ND, SD, MT western)
- 9.4 — South-Central Semi-Arid Prairies (TX panhandle, OK, western KS)
- 10.2 — Cold Deserts (UT, NV, southern ID, eastern OR)
- 10.1 — Warm Deserts (AZ, NM, W TX)
- 12.1 — Southern Semi-Arid Highlands (AZ, NM montane)
- 8.5 — Mississippi Alluvial & SE Coastal Plains (MS, LA, AL, FL, coastal TX)
- 15.4 — Everglades (S FL)
- 5.3 — Northern Forests / Laurentian Mixed Forest (MN, WI, MI)
- 8.1 — Mixed Wood Plains / New England (CT, MA, NH, VT, ME)
- 9.2 — Temperate Prairies / Loess subregion (IA, NE, IL, MO)
- 7.1 — Marine West Coast Forests (WA, coastal OR -- partially covered by OR)
- 3.1 — Arctic/Subarctic (excluded -- Alaska)

**Critical observation:** The absent ecoregions collectively cover over 60% of CONUS land area. The training set is concentrated in a west-coast-to-midwest corridor with a Chesapeake appendage.

---

## DIMENSION 1: Geology and Sediment Type

### Gap 1A: Loess Belt -- Silt-Dominated Systems (PRIORITY 1)

**The problem:** Loess (wind-deposited silt, 20-50 micron modal size) has a fundamentally different turbidity-SSC relationship than clay-dominated systems. Loess particles are large enough that their light-scattering efficiency per unit mass is lower than clay. Result: high SSC at moderate turbidity. The model, trained on clay-rich sites, systematically underpredicts SSC in loess systems. This is confirmed by the Iowa River failure (R-squared = -0.50).

**Recommended sites (6):**

| # | State | Region | What it represents | Gap filled | Turbidity data confidence |
|---|-------|--------|--------------------|-----------|--------------------------|
| 1 | IA | Iowa River basin (Iowa City area) | Loess hills, intensive corn/soy, coarse-silt sediment | Loess-SSC slope, Western Corn Belt Plains ecoregion | **High** -- USGS has turbidity at multiple Iowa River sites; MN/IA/MO Water Science Center invested heavily in turbidity since ~2010 |
| 2 | IA | Cedar River or Des Moines River | Second Iowa loess drainage, different tributary | Replication within loess regime for model to learn consistent pattern | **High** -- Multiple USGS gages with WQ monitoring |
| 3 | NE | Platte River (Louisville or Ashland area) | Nebraska loess, mixed sand/silt bed, wide braided channel | Sand-silt mixed regime, different from Iowa clay-silt; Great Plains/loess transition | **High** -- USGS Nebraska WSC operates continuous turbidity at Platte sites |
| 4 | MO | Missouri River at Hermann or Boonville | Major river carrying loess-derived sediment from entire Missouri basin; high SSC, heavy silt load | Large-river loess transport, different hydraulics than headwater Iowa streams | **High** -- USGS has long sediment record on Missouri mainstem; turbidity sensors installed at multiple MO River sites |
| 5 | IL | Illinois River at Valley City or Havana | Illinois River drains central IL glacial/loess terrain; receives agricultural runoff from most intensively farmed landscape in US | Glacial till + loess mixture, different from pure loess; extremely high nutrient loads (TP) | **Medium-High** -- USGS Illinois WSC has turbidity at some Illinois River sites; check NRTWQ |
| 6 | NE/IA | Missouri River tributary (e.g., Boyer River, Nishnabotna River) | Small to mid-size stream in deep loess hills of western Iowa / eastern Nebraska | Headwater-scale loess response, flashier hydrology than mainstem Missouri | **Medium** -- Smaller tributaries less likely to have continuous turbidity; check USGS and state networks |

**Why 6 sites:** The loess belt is not monolithic. Iowa loess differs from Nebraska loess (more sand). The Missouri mainstem carries a composite signal. The model needs multiple examples to learn that "high silt percentage + Western Corn Belt ecoregion = steeper turbidity-SSC slope" through the GAGES-II features.

### Gap 1B: Crystalline / Igneous Bedrock -- Low-Nutrient, Dilute Systems

**The problem:** Granitic and gneissic watersheds produce minimal weathering-derived nutrients and very low sediment loads. Turbidity is naturally very low, and SSC events are driven by episodic surface erosion rather than chronic sediment supply. The model has limited exposure to these dilute, nutrient-poor systems.

**Recommended sites (included in Dimension 8 -- Additional Unique Regimes):**

| # | State | Region | What it represents |
|---|-------|--------|--------------------|
| 28 | NH/VT | Upper Connecticut River or Merrimack tributaries | Crystalline bedrock, glaciated, low-nutrient, forested New England |
| 29 | GA/NC | Blue Ridge mountain headwaters | Crystalline Appalachian, steep gradient, reference-quality |

### Gap 1C: Volcanic Ash and Glacial Flour

**Current coverage:** OR and WA (Cascades) partially cover volcanic sediment. But glacial flour (rock flour from active glaciation) is absent.

**Note:** Glacial flour is primarily an Alaska and possibly MT/WA glacier-fed stream issue. For CONUS, the Cascades volcanic sites in OR provide partial coverage. One site in WA Cascades glacier-fed streams would add this dimension (included in Dimension 8).

---

## DIMENSION 2: Gulf Coastal Plain -- Sandy, Low-P, WWTP-Influenced (PRIORITY 2)

**The problem:** The Gulf Coastal Plain from Texas to Florida has sandy soils, low phosphorus enrichment ratios, heavy wastewater influence in urbanizing areas, and high organic matter from swamp/wetland drainage. The current training set has zero exposure to this vast region.

**Recommended sites (5):**

| # | State | Region | What it represents | Gap filled | Turbidity data confidence |
|---|-------|--------|--------------------|-----------|--------------------------|
| 7 | TX | East Fork San Jacinto River or Spring Creek (Houston metro) | Gulf Coastal Plain, suburban, WWTP-influenced, sandy sediment | Sandy coastal plain + WWTP influence; TP failure diagnosis | **High** -- USGS Texas WSC has active turbidity monitoring in Houston-area watersheds; confirmed by external validation data |
| 8 | TX | Brazos River (Richmond/Rosharon area) | Major Gulf Coast river, agricultural + urban mix, blackland prairie to coastal plain transition | Large-river coastal plain transport, different from small suburban streams | **Medium-High** -- Brazos is heavily monitored by USGS; check for continuous turbidity vs. discrete-only |
| 9 | LA | Atchafalaya River / Vermilion River or Mermentau basin | Louisiana delta plain, extremely flat, organic-rich water, swamp/marsh drainage | High-DOC, organic turbidity, subtropical wetland influence | **Medium** -- Louisiana turbidity monitoring is sparser than TX; Atchafalaya more likely to have data than smaller bayou systems |
| 10 | FL | Peace River at Arcadia or upstream | Florida phosphate mining district, naturally high P, sandy/karst hybrid | Phosphate-mining influence on TP, sandy Florida geology; unique P-enrichment regime | **Medium-High** -- Peace River is well-monitored by USGS FL WSC due to phosphate industry concerns |
| 11 | AL/MS | Tombigbee River or Alabama River tributary | Alabama/Mississippi Coastal Plain, red clay subsoil, forested/agricultural | Southeastern Coastal Plain sediment distinct from Gulf sandy coastal | **Medium** -- Alabama WSC has some continuous WQ sites; less turbidity-specific investment than TX or FL |

**Why these 5:** They span the Gulf Coastal Plain from TX through LA to FL, covering the key sub-regimes: urban/WWTP (TX), large-river alluvial (TX Brazos), organic/wetland (LA), phosphate-mining (FL), and interior Coastal Plain (AL/MS).

---

## DIMENSION 3: Arid Southwest -- Extreme SSC, Ephemeral Flow (PRIORITY 3)

**The problem:** Arid-regime streams regularly carry SSC exceeding 10,000-100,000 mg/L during flash floods -- one to two orders of magnitude above the training set's range. Ephemeral/intermittent flow, monsoon-driven hydrology, and sandstone/shale geology produce sediment dynamics fundamentally unlike anything in the humid-region training set. The San Juan River failure (R-squared = -8.13) demonstrates total model collapse in this regime.

**Recommended sites (4):**

| # | State | Region | What it represents | Gap filled | Turbidity data confidence |
|---|-------|--------|--------------------|-----------|--------------------------|
| 12 | NM | Rio Grande at Otowi Bridge or Albuquerque | Major arid-region river, snowmelt + monsoon hydrology, volcanic/sedimentary geology | Arid large-river regime, dual hydrologic drivers; best-monitored arid site in USGS network | **High** -- Rio Grande at Otowi has one of the longest continuous monitoring records in the Southwest; check specifically for turbidity sensor |
| 13 | AZ | Salt River near Roosevelt or Verde River | Sonoran Desert/mountain transition, monsoon flash floods, dam-regulated | Desert mountain regime, extreme SSC variability, dam influence | **Medium** -- Arizona WSC monitors reservoir and stream sites; turbidity sensors present at some but not all; dam regulation complicates natural sediment signal |
| 14 | AZ/UT | Colorado River at Lees Ferry or San Juan tributary | Colorado Plateau, sandstone canyon, extreme SSC, post-dam sediment starvation | Plateau sandstone regime; high-SSC events from tributary flash floods; iconic sediment dynamics | **Medium-Low** -- Lees Ferry has long sediment record but continuous turbidity is uncertain; post-Glen Canyon Dam sediment regime is highly modified |
| 15 | NM/TX | Pecos River or Rio Grande tributary in southern NM | True semi-arid, high-salinity, intermittent flow reaches, evaporite geology | High-conductance arid regime, evaporite dissolution, saline water; tests model at chemistry extremes | **Medium** -- Pecos River has USGS gages but continuous turbidity is sparse; southern NM sites are remote |

**Critical warning (from Rivera's earlier analysis):** Arid sites often have very short turbidity records (sensors installed recently) and sparse discrete SSC sampling (dangerous access during flash floods, remote locations). Expect that only 2 of these 4 will have adequate paired data. Sites with insufficient data should be treated as external validation targets rather than training sites.

**Alternative strategy:** If USGS turbidity data is insufficient in the Southwest, consider the Bureau of Reclamation's reservoir inflow monitoring network. Reclamation monitors sediment at several dam sites in AZ, NM, UT, and CO that may have turbidity-SSC pairs. Cross-reference with Reclamation's HydroMet system.

---

## DIMENSION 4: Iron Range / Canadian Shield / Mining-Influenced (PRIORITY 4)

**The problem:** The Precambrian Shield geology of northern Minnesota, Wisconsin, and Michigan's Upper Peninsula produces anomalous water chemistry: iron-stained water, naturally acidic to neutral pH, low alkalinity, high DOC from boreal wetlands, and mining-derived metals. Iron hydroxide particles scatter light differently than silicate clay, potentially altering the turbidity-SSC relationship. More critically, iron-bearing minerals adsorb phosphorus differently, producing anomalous TP-turbidity relationships. Confirmed by St. Louis River TP failure (R-squared = -0.54).

**Recommended sites (3):**

| # | State | Region | What it represents | Gap filled | Turbidity data confidence |
|---|-------|--------|--------------------|-----------|--------------------------|
| 16 | MN | St. Louis River headwaters or Embarrass River (Mesabi Range) | Iron range taconite mining, boreal wetland, Precambrian geology | Iron-hydroxide particles, mining sediment, anomalous P-Fe geochemistry | **Medium** -- MN PCA and USGS have some WQ monitoring in iron range; continuous turbidity uncertain; check USGS-04024000 (St. Louis at Scanlon is the external validation site -- look for upstream training sites) |
| 17 | WI | Bad River or Nemadji River (Lake Superior basin) | Red clay terrain of northern WI, glaciolacustrine clay over Precambrian bedrock | Red clay (iron-rich), high erosion rates, Lake Superior tributary; distinct from iron-range mining | **Medium-High** -- Red clay erosion is a major concern in WI Lake Superior basin; USGS WI WSC has invested in monitoring; check for continuous turbidity |
| 18 | MI | Sturgeon River or Ontonagon River (Upper Peninsula) | Canadian Shield / Keweenawan geology, copper-mining legacy, boreal forest | Legacy mining metals, Precambrian crystalline bedrock, cold boreal hydrology | **Medium-Low** -- MI UP sites are remote; USGS coverage is thinner than MN or WI; may need to rely on state data |

**Geochemistry note (Vasquez):** The iron range sites are critical not just for SSC but for understanding TP model failures. In iron-rich waters, dissolved Fe(III) co-precipitates with phosphate, creating particulate Fe-P complexes that are not captured by the turbidity-P relationship the model learned from agricultural sites. Adding these sites with explicit iron chemistry features (if available in GAGES-II or NLDI attributes) could allow the model to learn the Fe-P interaction. However, GAGES-II likely does not code iron mineralogy explicitly -- the model would need to infer it from geology class and ecoregion.

---

## DIMENSION 5: Southeast Piedmont and Atlantic Coastal Plain (PRIORITY 5)

**The problem:** The Southeast US from North Carolina through Georgia represents a major population and agriculture corridor with distinct Piedmont red-clay soils and Coastal Plain sandy soils. The current training set has VA and MD (northern extent) but nothing south of Virginia. The Piedmont red clay of the Carolinas produces different turbidity-SSC signatures than the Piedmont of Virginia (different weathering intensity due to warmer climate).

**Recommended sites (3):**

| # | State | Region | What it represents | Gap filled | Turbidity data confidence |
|---|-------|--------|--------------------|-----------|--------------------------|
| 19 | NC | Yadkin-Pee Dee River or Neuse River (Piedmont) | North Carolina Piedmont, red clay soil, tobacco/mixed agriculture, reservoir influence | SE Piedmont red clay, subtropical weathering, higher kaolinite content than VA Piedmont | **Medium-High** -- USGS NC/SC WSC has active programs; NC has good turbidity monitoring driven by reservoir sedimentation concerns |
| 20 | SC | Broad River or Saluda River (upstate SC) | South Carolina Piedmont, crystalline-to-Piedmont transition, textile/industrial legacy | Deep SE Piedmont, more intense weathering than NC, urban/industrial influence | **Medium** -- SC has fewer continuous turbidity sites than NC; check USGS SC site inventory |
| 21 | GA | Chattahoochee River (Atlanta metro) or Altamaha tributaries | Georgia Piedmont/Coastal Plain transition, major urban (Atlanta) + agricultural | Urban SE Piedmont + Coastal Plain transition in single watershed; extreme land use gradient | **Medium-High** -- Chattahoochee near Atlanta is heavily monitored (drinking water source for metro Atlanta); USGS GA WSC likely has turbidity |

---

## DIMENSION 6: Karst / Carbonate / Spring-Fed Systems (PRIORITY 6)

**The problem:** Karst terrain (limestone/dolomite dissolution) produces unique hydrology: spring-fed baseflow with very low turbidity, punctuated by rapid turbidity spikes during conduit-flushing events. The turbidity-SSC relationship in karst is fundamentally different because sediment source switches between (a) subsurface conduit sediment mobilized by rising water tables and (b) surface-derived sediment entering sinkholes. Additionally, carbonate-buffered water has high alkalinity and often high dissolved nutrients from agricultural infiltration through thin soils.

**Recommended sites (3):**

| # | State | Region | What it represents | Gap filled | Turbidity data confidence |
|---|-------|--------|--------------------|-----------|--------------------------|
| 22 | TX | San Marcos River or Comal River (Edwards Aquifer springs) | Major spring-fed streams from Edwards Limestone; constant temperature, variable WQ during recharge events | Karst spring-fed regime; groundwater-dominated flow; unique turbidity-SSC event dynamics | **Medium** -- These are iconic Texas springs; USGS TX WSC has monitoring, but continuous turbidity specifically is uncertain; TCEQ may supplement |
| 23 | TN/KY | Caney Fork or Elk River (Highland Rim / Nashville Basin) | Interior Low Plateau karst, Ordovician limestone, spring-fed with agricultural influence | Appalachian karst distinct from Edwards karst; sinkhole-to-spring sediment pathway | **Medium** -- TN and KY have USGS WQ monitoring; KY is partially in training set but check whether existing KY sites are actually karst |
| 24 | FL | Ichetucknee River, Santa Fe River, or Suwannee tributaries (north-central FL) | Florida Floridan Aquifer springs, extremely clear water with periodic tannin/DOC pulses | Subtropical karst, high-DOC influence, naturally low SSC; tests model behavior at low-turbidity extremes | **Medium** -- USGS FL WSC monitors springs; turbidity may not be continuous because these are very clear systems and turbidity is not the primary concern |

**Model applicability note:** Karst spring-fed systems may be fundamentally outside the model's valid domain because turbidity is not a reliable predictor of SSC when the sediment source is subsurface conduit flushing. Including 1-2 karst sites in training helps the model learn "low confidence" for these conditions rather than making confidently wrong predictions. If karst sites consistently degrade model performance, they should be flagged as out-of-domain rather than forced into the training set.

---

## DIMENSION 7: Urban Stormwater / Impervious Surface Systems

**The problem:** Urban watersheds with high impervious cover (>20-30%) have fundamentally different sediment transport: rapid hydrograph response, "first flush" of accumulated particles from impervious surfaces, construction sediment, road sand/salt, and tire/brake particle contribution to turbidity. The turbidity-SSC relationship in urban streams is often weaker because biogenic and anthropogenic particles (rubber, plastic, organic debris) register on turbidity sensors without corresponding to mineral SSC.

**Recommended sites (3):**

| # | State | Region | What it represents | Gap filled | Turbidity data confidence |
|---|-------|--------|--------------------|-----------|--------------------------|
| 25 | PA | Chester County tributaries (Brandywine Creek area) | Philadelphia suburban fringe, Piedmont geology + high impervious cover | Urban/suburban Piedmont; USGS PA WSC has published turbidity-SSC surrogate models here | **High** -- Confirmed by USGS publication: "Surrogate regression models for computation of time-series suspended-sediment concentrations, Chester County, Pennsylvania (2020)" |
| 26 | WA | Puyallup River or Green River (Seattle/Tacoma metro) | Pacific NW urban + volcanic sediment from Mt. Rainier glaciers; lahar risk monitoring | Urban + glacial/volcanic hybrid; unique sediment mineralogy in urban context | **High** -- Seattle-area streams are heavily monitored by USGS WA WSC for lahar warning and water supply; turbidity is a primary parameter |
| 27 | TX/GA | Urban stream in Houston or Atlanta | Pure urban stormwater signature in warm humid climate | Warm-climate urban, distinct from northern urban (no road salt, different particle sources) | **Medium** -- Both cities have USGS monitoring; Houston sites confirmed from external validation; Atlanta Chattahoochee sites likely have urban tributaries |

---

## DIMENSION 8: Additional Unique Regimes (Filling Remaining Ecoregion and Chemistry Gaps)

These 8 sites target specific gaps not covered by Priorities 1-7.

| # | State | Region | What it represents | Gap filled | Turbidity data confidence |
|---|-------|--------|--------------------|-----------|--------------------------|
| 28 | NH/VT | Upper Connecticut River or Merrimack River tributary | New England crystalline/glaciated, forested, dilute water, low nutrient | Mixed Wood Plains ecoregion; New England water chemistry; dissolved-P-dominant regime | **Medium-High** -- USGS New England WSC has active Connecticut River and tributary monitoring with turbidity at select sites |
| 29 | NC/GA | Blue Ridge headwater stream (Nantahala, Chattooga, or similar) | Southern Appalachian reference forest, crystalline bedrock, steep gradient | Reference-quality forested headwater; minimal human influence; model calibration anchor | **Medium** -- Blue Ridge streams are monitored but continuous turbidity less common in pristine headwaters |
| 30 | ND/MN | Red River of the North mainstem (Fargo or Grand Forks) | Glaciolacustrine clay plain (former Lake Agassiz), extremely flat, spring flooding | Glaciolacustrine regime distinct from glacial till; clay-dominated with extreme seasonal cycle | **High** -- Red River is one of the most intensively monitored rivers in the USGS network; confirmed R-squared=0.90 in external validation; should be in TRAINING not just validation |
| 31 | WA | Glacier-fed stream (Nisqually, White River, or Nooksack) | Active glacial meltwater, glacial flour (rock flour), highly variable turbidity | Glacial flour sediment type; extremely fine mineral particles from active glaciation; tests model at unusual particle mineralogy | **Medium-High** -- Mt. Rainier and North Cascades glacier streams monitored by USGS WA WSC |
| 32 | WY | Wind River, Bighorn River, or North Platte tributary | Wyoming high plains / intermountain basin, sagebrush steppe, rangeland | Cold semi-arid rangeland; West-Central Semi-Arid Prairies ecoregion; different from Great Plains (KS) | **Medium** -- USGS WY WSC operates streamgages but continuous turbidity is less common in WY; check Green River and Wind River sites |
| 33 | CT | Housatonic River or Quinnipiac River | New England suburban/agricultural, known dissolved-P issues, Long Island Sound tributary | Dissolved-P-dominant regime; model needs exposure to learn "TP prediction unreliable here" | **Medium-High** -- USGS New England WSC monitors turbidity at mouths of major CT rivers (confirmed from search); discrete P sampling is strong |
| 34 | OK/AR | Illinois River (OK) or Poteau River (AR) | Ozark Plateau / Ouachita Mountains, poultry-litter P enrichment, karst/shale mixed geology | Ozark ecoregion (8.4); unique P source (poultry litter) producing extreme P enrichment ratios; karst/shale sediment | **Medium** -- Illinois River in OK is heavily monitored due to OK/AR phosphorus disputes (chicken litter lawsuits); USGS has active monitoring |
| 35 | UT/NV | Humboldt River (NV) or Sevier River (UT) | Great Basin interior drainage, alkaline/saline water, desert rangeland | Cold Deserts ecoregion (10.2); interior drainage basin (no ocean outlet); high-conductance alkaline water; model exposure to extreme chemistry | **Low-Medium** -- Great Basin streams have minimal USGS turbidity monitoring; these are long shots but scientifically valuable if data exists |

---

## Cross-Reference Matrix: Which Diversity Dimensions Does Each Site Cover?

| Site # | State | Geology | Land Use | Climate | Hydrology | Ecoregion Gap | Chemistry | Sediment | Human Influence |
|--------|-------|---------|----------|---------|-----------|---------------|-----------|----------|-----------------|
| 1 | IA | Loess | Intensive ag | Humid continental | Rainfall-dominated | 9.2 (loess sub) | Moderate-high nutrients | Silt-dominated | Intensive ag |
| 2 | IA | Loess | Intensive ag | Humid continental | Rainfall-dominated | 9.2 (loess sub) | Moderate-high nutrients | Silt-dominated | Intensive ag |
| 3 | NE | Loess/alluvial | Irrigated ag | Semi-arid transition | Braided/sand-bed | 9.3 transition | Moderate | Sand-silt mix | Moderate ag |
| 4 | MO | Loess/alluvial | Mixed ag | Humid continental | Large river | 9.2 | High nutrients | Silt-dominated | Intensive ag |
| 5 | IL | Glacial till + loess | Intensive ag | Humid continental | Rainfall-dominated | 8.2 | Very high nutrients | Silt-clay mix | Intensive ag |
| 6 | NE/IA | Deep loess | Ag/rangeland | Humid continental | Flashy headwater | 9.2/9.3 | Moderate | Pure silt | Moderate ag |
| 7 | TX | Coastal plain sand | Suburban | Humid subtropical | Rainfall, WWTP baseflow | 8.5 | WWTP-influenced | Sand-clay mix | Urban + point source |
| 8 | TX | Blackland prairie/CP | Mixed ag/urban | Humid subtropical | Large river | 9.4/8.5 transition | High nutrients | Mixed | Moderate ag + urban |
| 9 | LA | Alluvial/deltaic | Forested wetland | Humid subtropical | Low-gradient, swamp | 8.5 | High DOC | Organic-rich | Low-moderate |
| 10 | FL | Sandy/karst | Phosphate mining | Humid subtropical | Spring-influenced | 8.5/15.4 | Naturally high P | Sandy | Mining |
| 11 | AL/MS | Coastal plain clay | Forest/ag | Humid subtropical | Perennial rainfall | 8.5 | Moderate | Red clay-sand | Moderate |
| 12 | NM | Volcanic/sedimentary | Rangeland | Semi-arid | Snowmelt + monsoon | 10.1/12.1 | Moderate, alkaline | Mixed volcanic | Low |
| 13 | AZ | Desert alluvial | Rangeland/desert | Arid | Monsoon flash flood | 10.1 | High conductance | Sand-gravel | Dam-regulated |
| 14 | AZ/UT | Sandstone/shale | Wildland | Arid | Ephemeral tributary | 10.1 | Very high SSC events | Sand-silt | Dam-influenced |
| 15 | NM/TX | Evaporite/limestone | Rangeland | Semi-arid | Intermittent | 10.1 | Very high conductance, saline | Mixed | Low |
| 16 | MN | Precambrian iron | Mining/boreal forest | Humid continental/subarctic | Wetland-influenced | 5.3 | Iron-stained, low alkalinity | Fe-oxide particles | Mining |
| 17 | WI | Glaciolacustrine red clay | Forest/ag | Humid continental | Lake Superior tributary | 5.3 | Moderate | Iron-rich clay | Moderate |
| 18 | MI | Precambrian crystalline | Boreal forest | Humid continental | Snowmelt-dominated | 5.3 | Dilute, low nutrient | Crystalline fines | Legacy mining |
| 19 | NC | Piedmont saprolite | Mixed ag/suburban | Humid subtropical | Perennial rainfall | 8.3 (southern) | Moderate nutrients | Red clay (kaolinite) | Moderate ag + urban |
| 20 | SC | Deep Piedmont weathering | Mixed | Humid subtropical | Perennial | 8.3 (deep south) | Moderate | Deep red clay | Mixed |
| 21 | GA | Piedmont/Coastal Plain | Urban (Atlanta) | Humid subtropical | Urban flashy | 8.3/8.5 | Urban nutrients | Red clay + sand transition | Major urban |
| 22 | TX | Edwards Limestone | Urban/rangeland | Semi-arid | Spring-fed | 9.4/12.1 | High alkalinity, carbonate | Low SSC, episodic | Karst groundwater |
| 23 | TN/KY | Ordovician limestone | Agricultural | Humid subtropical | Spring-fed + surface | 8.4 | High alkalinity | Limestone-derived | Agricultural |
| 24 | FL | Floridan Limestone | Forest/rural | Humid subtropical | Spring-fed | 8.5 | High DOC, clear water | Very low SSC | Minimal |
| 25 | PA | Piedmont | Suburban | Humid continental | Perennial | 8.1 | Urban nutrients | Mixed Piedmont | Suburban |
| 26 | WA | Volcanic/glacial | Urban | Marine west coast | Glacial/urban flashy | 7.1 | Moderate | Volcanic + glacial flour | Urban |
| 27 | TX/GA | Varied | Urban | Humid subtropical | Urban flashy | Varies | Urban nutrients, warm | Urban particles | Major urban |
| 28 | NH/VT | Crystalline/glacial | Forested | Humid continental | Snowmelt | 5.3/8.1 | Dilute, low nutrient | Glacial + crystalline | Low (reference) |
| 29 | NC/GA | Crystalline (Blue Ridge) | Forest (reference) | Humid subtropical/montane | Steep headwater | 8.4 | Very dilute | Minimal sediment | Reference |
| 30 | ND/MN | Glaciolacustrine clay | Intensive ag | Humid continental (cold) | Spring flood dominated | 9.3/9.2 | High nutrients | Pure clay | Intensive ag |
| 31 | WA | Volcanic/glacial | Forest | Marine west coast | Glacier-fed | 7.1/6.2 | Dilute, glacial | Glacial flour | Low |
| 32 | WY | Sedimentary/mixed | Rangeland | Semi-arid cold | Snowmelt-dominated | 9.3/6.5 | Low-moderate | Varied | Rangeland |
| 33 | CT | Glacial/crystalline | Suburban/ag | Humid continental | Perennial | 8.1 | Dissolved P dominant | Mixed | Suburban |
| 34 | OK/AR | Karst/shale | Poultry agriculture | Humid subtropical | Karst-influenced | 8.4 | Extreme P enrichment | Shale + karst | Poultry litter |
| 35 | UT/NV | Basin fill/volcanic | Rangeland/desert | Arid/semi-arid | Interior drainage | 10.2 | Alkaline, saline | Desert alluvial | Low |

---

## Confidence Tier Summary

### Tier A: High Confidence of Adequate USGS Turbidity + SSC Data (12 sites)
Sites: 1, 2, 3, 4, 7, 25, 26, 30 + likely 5, 8, 10, 28

These sites are in states/regions where USGS or state cooperators have invested specifically in turbidity-SSC surrogate monitoring. Expect >=100 paired samples at most of these.

### Tier B: Medium Confidence -- Data Likely Exists but Needs Verification (15 sites)
Sites: 6, 9, 11, 12, 13, 17, 19, 20, 21, 22, 23, 27, 31, 33, 34

These sites are in regions with USGS presence and known water quality programs, but continuous turbidity specifically has not been confirmed. Some may have only discrete turbidity (instantaneous measurements during site visits) rather than continuous sensor data.

### Tier C: Lower Confidence -- Data May Be Sparse or Absent (8 sites)
Sites: 14, 15, 16, 18, 24, 29, 32, 35

These are scientifically important sites in regions where continuous turbidity monitoring is sparse. For these, the strategy should be:
1. Query NWIS for pcode 63680 availability
2. If continuous turbidity is absent, check for state-operated turbidity networks
3. If still absent, designate as external validation targets (use whatever discrete data exists) rather than training sites

---

## Programmatic Site Selection Workflow

Once this plan is approved, the following programmatic workflow should be executed:

```
For each of the 35 site-regions:
  1. Query USGS NWIS: waterservices.usgs.gov/nwis/site/?stateCd=XX&parameterCd=63680
     - Filter for sites with continuous turbidity (63680) data
  2. For each candidate site with turbidity:
     a. Count discrete SSC samples (pcode 80154): require n >= 50
     b. Count discrete TP samples (pcode 00665): prefer n >= 30
     c. Check period of record overlap between turbidity and discrete samples
  3. Cross-reference against GAGES-II site list:
     - Prefer sites IN GAGES-II (catchment attributes available)
     - If not in GAGES-II, check if NLDI can provide equivalent attributes
  4. Rank candidates within each site-region by:
     a. SSC sample count (more is better)
     b. Turbidity record length (longer is better)
     c. Period of record overlap (must be concurrent)
     d. GAGES-II availability (binary bonus)
  5. Select top candidate per site-region
```

Expected yield: 25-30 of the 35 site-regions will produce at least one viable candidate. The remaining 5-10 should be designated as validation targets or deferred until data becomes available.

---

## Water Chemistry Regimes: Specific Gaps to Monitor

Beyond the geographic/geologic gaps, several water chemistry regimes are absent from the training set. For each new site added, the following chemistry characteristics should be noted and tracked:

| Chemistry Regime | Example Sites | Why It Matters for the Model |
|-----------------|---------------|------------------------------|
| **High conductance (>1000 uS/cm)** | 15 (Pecos), 35 (Great Basin), 12 (Rio Grande) | Dissolved mineral load affects optical turbidity sensor response |
| **Very low conductance (<50 uS/cm)** | 28 (NH/VT), 29 (Blue Ridge), 18 (MI UP) | Dilute water baseline behavior differs |
| **High DOC (>10 mg/L)** | 9 (LA), 24 (FL springs), 16 (MN iron range) | DOC causes color interference with turbidity sensors (absorbs light, biases readings) |
| **Naturally acidic (pH <6.5)** | 16 (iron range), 18 (MI UP mining) | Acid mine drainage dissolves iron, which re-precipitates as turbidity-causing Fe(OH)3 |
| **Very alkaline (pH >8.5)** | 22 (TX Edwards), 35 (Great Basin) | Carbonate precipitation can contribute to turbidity without SSC |
| **Dissolved-P dominant** | 33 (CT), 10 (FL), 22 (TX springs) | Model cannot predict TP from turbidity when P is dissolved; needs to learn "low confidence" signal |
| **Extreme P enrichment** | 34 (OK/AR poultry litter), 4 (MO River ag) | Very high P per unit sediment; tests upper range of model |
| **WWTP-dominated baseflow** | 7 (TX suburban), 25 (PA suburban) | Point-source P decoupled from turbidity; inverse turbidity-TP at low flow |

---

## Expected Model Improvement After Site Expansion

### SSC Predictions
- **Loess belt (sites 1-6):** Expect R-squared improvement from -0.50 to 0.60-0.75 at Iowa-type sites. The model should learn the silt-size-dependent turbidity-SSC slope through GAGES-II silt% and ecoregion features.
- **Gulf Coastal Plain (sites 7-11):** Expect improvement from 0.55 to 0.65-0.75 at Texas-type sites. Sandy sediment regime will be partially learnable.
- **Arid Southwest (sites 12-15):** Most uncertain. If adequate high-SSC event data exists, the model may achieve R-squared 0.40-0.60 at moderate-SSC arid sites. Extreme events (>50,000 mg/L) will remain out-of-domain due to extrapolation limits of tree-based models.
- **Iron Range (sites 16-18):** SSC improvement likely modest (already R-squared=0.79 at St. Louis River for SSC); the main benefit is TP improvement.

### TP Predictions
- **Iron Range sites:** TP improvement from R-squared=-0.54 to potentially 0.20-0.40 if the model can learn the Fe-P interaction through geology features.
- **Gulf Coast sites:** TP improvement uncertain -- WWTP influence may remain a failure mode unless conductance or NPDES density is added as a feature.
- **Dissolved-P sites (CT, FL):** Will NOT improve TP prediction at these sites through site expansion alone. These sites require either (a) a dissolved-P feature or (b) an explicit out-of-domain flag.

### Applicability Domain Expansion
Current domain: ~40% of CONUS by area (humid East, Pacific states, Great Plains)
After expansion: ~75-80% of CONUS by area (adds Gulf Coast, Southeast, loess belt, partial arid West)
Remaining gaps: Extreme arid (flash flood events), interior Alaska, Hawaii

---

## References and Data Sources Used

1. **GAGES-II dataset:** Falcone, J.A., 2011, GAGES-II: Geospatial Attributes of Gages for Evaluating Streamflow, version II: USGS, https://doi.org/10.3133/70046617
2. **EPA Level II Ecoregions of North America:** Commission for Environmental Cooperation, 1997 (revised 2006). Available at https://www.epa.gov/eco-research/ecoregions-north-america
3. **USGS TM 3-C4:** Rasmussen et al., 2009, Guidelines and Procedures for Computing Time-Series Suspended-Sediment Concentrations and Loads from In-Stream Turbidity-Sensor and Streamflow Data: https://pubs.usgs.gov/tm/tm3c4/
4. **Gray and Gartner, 2009:** Technological advances in suspended-sediment surrogate monitoring. Water Resources Research 45, W00D29. (196 citations)
5. **Zhi et al., 2024:** Deep learning for water quality. Nature Water 2, 228-241. (219 citations)
6. **USGS NRTWQ:** National Real-Time Water Quality program, https://nrtwq.usgs.gov/
7. **USGS Chester County PA surrogate models:** https://www.usgs.gov/data/surrogate-regression-models-computation-time-series-suspended-sediment-concentrations-chester
8. **USGS Minnesota sediment network:** Suspended-sediment concentrations, loads, total suspended solids, turbidity, and particle-size fractions for selected rivers in Minnesota, 2007-2011
9. **USGS Indiana supergages:** Comparison of turbidity sensors at USGS supergages in Indiana, SIR 2023-5077
10. **Song et al., 2024:** Referenced benchmark of 377 training sites, median R-squared=0.55 without turbidity (per Rivera external validation review)
11. **USGS Southeast Stream Quality Assessment (SESQA), 2014:** Journey et al., OFR 2015-1095 -- design and methods for SE US stream assessment across Piedmont and Appalachian regions

---

## Next Steps

1. **Kaleb runs the programmatic site query** (Section "Programmatic Site Selection Workflow" above) using the `dataretrieval` API he already has working
2. **Triage results into training vs. validation** based on data adequacy (n>=50 SSC samples = training; n=20-49 = validation; n<20 = discard)
3. **Download and QC data** for the 25-30 viable sites (~1-2 days)
4. **Add to training set with sample weighting** (Rivera's recommendation: equal site weight regardless of sample count)
5. **Retrain and evaluate** using LOGO-CV with the expanded site set
6. **Re-run external validation** at the original 11 external sites to measure improvement

---

*Dr. Elena Vasquez, Hydrogeochemist -- 15 years groundwater/surface water geochemistry, USGS and academic*
*Dr. Marcus Rivera, Hydrologist (ret.) -- 20 years USGS Water Resources Division, sediment transport and surrogate regression*
*Reviewing: murkml site diversity expansion plan, 2026-03-17*
