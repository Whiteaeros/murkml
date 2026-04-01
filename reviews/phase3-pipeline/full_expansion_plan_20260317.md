# Full Site Expansion Plan: 57 to ~137 Sites Across 12 Watershed Regimes

**Authors:** Dr. Elena Vasquez (Hydrogeochemist) & Dr. Marcus Rivera (Hydrologist, ret.)
**Date:** 2026-03-17
**Purpose:** Operational plan for scaling murkml training set from 57 sites (11 states) to ~137 sites (~23 states) with 5-8 sites per major watershed regime, enabling robust LOGO-CV across all US sediment transport regimes
**Builds on:** `site_diversity_plan_20260317.md` (35-site conceptual plan) and `rivera_training_diversity_20260317.md` (regime gap analysis)

---

## Executive Summary

This plan specifies **82 new site targets** across 12 watershed regimes, targeting states with confirmed or high-probability USGS continuous turbidity monitoring (parameter code 63680) and co-located discrete SSC (80154) or TP (00665) samples. We estimate 65-72 of these 82 targets will yield viable training sites (n >= 50 paired samples), with the remainder becoming external validation targets.

**Key principle:** We are over-targeting by ~15% to account for sites that will fail data adequacy checks. If all 82 targets yield data, prioritize by regime balance rather than including all of them.

### Regime-Level Summary

| # | Regime | New Sites | Target States | Data Confidence | Priority |
|---|--------|-----------|---------------|-----------------|----------|
| 1 | Loess Belt | 8 | IA, NE, MO, IL | High | 1 |
| 2 | Gulf Coastal Plain | 7 | TX, LA, FL, AL | Medium-High | 2 |
| 3 | Arid/Semi-Arid Southwest | 6 | NM, AZ, UT, NV | Medium-Low | 3 |
| 4 | Southeast Piedmont/Coastal Plain | 7 | NC, SC, GA | Medium-High | 4 |
| 5 | Karst/Carbonate | 6 | TX, TN, KY, FL, MO/AR | Medium | 5 |
| 6 | Iron Range/Canadian Shield | 5 | MN, WI, MI | Medium | 6 |
| 7 | Urban Stormwater | 6 | PA, WA, TX, GA, OH, MN | High | 7 |
| 8 | New England/Northeast | 6 | CT, NY, NH, MA, VT | Medium-High | 8 |
| 9 | Northern Great Plains/Prairie Pothole | 6 | ND, SD, MT-east, NE-west | Medium | 9 |
| 10 | Deep South/Lower Mississippi | 6 | AR, MS, LA, TN-west | Medium-Low | 10 |
| 11 | Pacific Coast/Cascade (supplement) | 4 | WA | High | 11 |
| 12 | Cold Semi-Arid/Steppe | 5 | WY, MT-east, SD-west | Medium-Low | 12 |
| | **TOTAL** | **82** | **~23 states** | | |

**Expected yield after data adequacy filtering:** 65-72 viable training sites + 10-17 validation-only sites.

---

## How to Use This Plan

For each regime below, run the following `dataretrieval` query sequence:

```python
import dataretrieval.nwis as nwis

# Step 1: Find sites with continuous turbidity in target state
site_info, _ = nwis.get_info(
    stateCd=STATE_CODE,
    parameterCd="63680",       # Turbidity, FNU
    siteType="ST",             # Streams only
    siteStatus="all",
    hasDataTypeCd="uv"         # Unit values = continuous
)

# Step 2: For each candidate, count discrete SSC samples
ssc_data, _ = nwis.get_qwdata(
    sites=SITE_ID,
    parameterCd="80154",       # SSC
    begin_date="2000-01-01"
)
n_ssc = len(ssc_data)

# Step 3: Count discrete TP samples
tp_data, _ = nwis.get_qwdata(
    sites=SITE_ID,
    parameterCd="00665",       # TP
    begin_date="2000-01-01"
)
n_tp = len(tp_data)

# Step 4: Check GAGES-II membership
# Cross-reference site_no against GAGES-II site list
```

**Minimum thresholds:**
- Training: n_ssc >= 50 AND turbidity record >= 2 years AND period overlap
- Validation: n_ssc >= 20 AND turbidity record >= 1 year
- Discard: n_ssc < 20 or no continuous turbidity

---

## REGIME 1: Loess Belt

### Why This Regime Needs Representation

Loess (wind-deposited silt, 20-50 micron modal particle size) has a fundamentally different turbidity-SSC relationship than clay-dominated systems. Silt particles scatter light less efficiently per unit mass than clay particles, producing a steeper turbidity-to-SSC slope (more SSC per FNU). The current training set's Iowa River failure (R-squared = -0.50) is a direct consequence of this gap. The loess belt covers one of the most intensively farmed regions in the US (western Corn Belt), making it a high-priority commercial target for murkml.

**Physical distinctiveness:**
- Particle size distribution dominated by coarse silt (20-50 um) rather than clay (<2 um)
- Turbidity-SSC slope is 2-3x steeper than clay systems
- Extremely high sediment yields from intensive row-crop agriculture
- Seasonally frozen ground creates spring runoff pulses
- Tile drainage modifies hydrology (subsurface flow paths carry dissolved nutrients but not sediment)

### Target States and Search Strategy

| State | Target Region | Why | Expected Sites with Turbidity | SSC/TP Data Likely? |
|-------|--------------|-----|-------------------------------|---------------------|
| **IA** | Iowa River, Cedar River, Des Moines River basins | Core loess belt, USGS Central Midwest WSC has heavy turbidity investment since 2010; confirmed on NRTWQ (nrtwq.usgs.gov/ia/) | 10-15 sites | **SSC: High** -- USGS IA has active SSC sampling program. **TP: High** -- nutrient monitoring driven by Gulf hypoxia concerns |
| **NE** | Platte River (Louisville, Ashland), Salt Creek, Elkhorn River | Nebraska loess with more sand fraction; USGS NE WSC operates continuous WQ monitoring network (confirmed on usgs.gov) | 5-10 sites | **SSC: High** -- USGS NE sediment monitoring for Platte River Recovery Program. **TP: Medium** |
| **MO** | Missouri River at Hermann/Boonville, Grand River, Chariton River | Missouri River mainstem carries integrated loess signal from entire basin; MO sites confirmed in NRTWQ with published turbidity-SSC/TP surrogate models (USGS SIR 2024-5097) | 5-8 sites | **SSC: High** -- Long sediment record on MO River. **TP: High** -- surrogate TP models published |
| **IL** | Illinois River at Valley City/Havana, Sangamon River | Glacial till + loess mixture, most intensively farmed landscape in US | 3-5 sites | **SSC: Medium-High** -- USGS IL WSC has some turbidity; less investment than IA/NE. **TP: High** |

**Total sites to query:** 8 (select 2-3 from IA, 2 from NE, 2 from MO, 1-2 from IL)

**Site selection preferences within regime:**
- At least one Missouri River mainstem site (large river, >100,000 km2 drainage)
- At least two Iowa headwater/mid-size tributaries (<5,000 km2)
- At least one Platte River site (braided sand-silt bed, distinct from Iowa clay-silt)
- Mix of tile-drained (IA, IL) and non-tile-drained (NE, MO) watersheds

**Specific candidate sites to check first:**
- USGS-05454500 Iowa River at Iowa City, IA (confirmed turbidity, was external validation site -- now move to training)
- USGS-05464500 Cedar River at Cedar Rapids, IA
- USGS-05481650 Des Moines River near Saylorville, IA
- USGS-06805500 Platte River at Louisville, NE (confirmed turbidity via NE WSC)
- USGS-06803555 Salt Creek at Greenwood, NE
- USGS-06934500 Missouri River at Hermann, MO (confirmed SSC surrogate model)
- USGS-06906800 Lamine River near Otterville, MO
- USGS-05586100 Illinois River at Valley City, IL

---

## REGIME 2: Gulf Coastal Plain

### Why This Regime Needs Representation

The Gulf Coastal Plain from east Texas to Florida panhandle has sandy/clayey coastal sediments, heavy wastewater treatment plant (WWTP) influence in urbanizing areas, subtropical climate with year-round precipitation, and high organic matter from swamp/wetland drainage. The turbidity-SSC relationship differs because: (1) sandy sediment has even lower light-scattering efficiency than silt, (2) organic particles (detritus, algae) register on turbidity sensors without corresponding mineral SSC, and (3) WWTP effluent creates a decoupled TP-turbidity relationship at baseflow.

The East Fork San Jacinto failure (SSC R-squared = 0.55, TP R-squared = -2.02) demonstrates this gap. The Gulf Coast is also a massive commercial market (Houston, New Orleans, Tampa metro areas).

**Physical distinctiveness:**
- Sandy soils with low clay content (Coastal Plain sands)
- High organic content from subtropical vegetation and wetland drainage
- WWTP-dominated baseflow in urban/suburban streams
- Flat terrain, slow flow, depositional environment
- Year-round warm temperatures accelerate biological turbidity contributions
- Phosphorus geochemistry differs: low P-enrichment in sandy soils, high dissolved P from WWTPs

### Target States and Search Strategy

| State | Target Region | Why | Expected Sites | SSC/TP Data |
|-------|--------------|-----|----------------|-------------|
| **TX** | Houston metro (San Jacinto, Spring Creek, Buffalo Bayou), Brazos River lower basin | USGS TX WSC confirmed turbidity-SSC surrogate regression models for Lake Houston tributaries (published USGS SIR for W Fork San Jacinto and Spring Creek, 2005-2009 data). Multiple studies confirm paired data exists | 8-12 sites | **SSC: High** -- Published surrogate models confirm paired data exists. **TP: High** -- Nutrient monitoring for Lake Houston water supply |
| **LA** | Atchafalaya River, Vermilion/Mermentau basins, Amite River | Louisiana delta plain; USGS Lower Mississippi-Gulf WSC covers LA; Atchafalaya is major monitoring site | 2-4 sites | **SSC: Medium** -- LA turbidity monitoring sparser than TX; focus on Atchafalaya. **TP: Medium** |
| **FL** | Peace River (Arcadia), Hillsborough River, Alafia River | Florida phosphate mining district; Peace River is well-monitored for phosphate industry concerns | 3-5 sites | **SSC: Medium-High** -- FL WSC monitors Peace River area. **TP: High** -- Phosphate mining means P is primary concern |
| **AL** | Tombigbee River, Alabama River tributaries, Mobile Bay tributaries | Southeastern Coastal Plain transition from red clay to sandy; USGS Lower MS-Gulf WSC | 2-3 sites | **SSC: Medium** -- AL has less turbidity investment than TX/FL. **TP: Medium** |

**Total sites to query:** 7 (select 3 from TX, 1-2 from LA, 2 from FL, 1 from AL)

**Site selection preferences:**
- At least one Houston-area suburban stream (WWTP influence)
- At least one large Gulf Coast river (Brazos or Atchafalaya, >10,000 km2)
- At least one Florida phosphate-district stream (unique P geochemistry)
- At least one blackwater/organic-rich stream (LA or FL)
- Mix of sandy vs. clayey Coastal Plain sub-types

**Specific candidate sites:**
- USGS-08068500 Spring Creek near Spring, TX (confirmed turbidity + SSC surrogate model)
- USGS-08070200 East Fork San Jacinto near New Caney, TX (confirmed -- was external validation, move to training)
- USGS-08068090 West Fork San Jacinto River (confirmed surrogate model published)
- USGS-08116650 Brazos River near Rosharon, TX
- USGS-07381495 Atchafalaya River at Butte La Rose, LA
- USGS-02296750 Peace River at Arcadia, FL
- USGS-02301500 Alafia River at Lithia, FL
- USGS-02469762 Tombigbee River below Coffeeville Lock and Dam, AL

---

## REGIME 3: Arid/Semi-Arid Southwest

### Why This Regime Needs Representation

The arid West covers roughly one-third of CONUS by area. Streams here routinely carry SSC exceeding 10,000-100,000 mg/L during flash floods -- one to two orders of magnitude above the training set's range. Ephemeral/intermittent flow, monsoon-driven hydrology, and sandstone/shale geology produce sediment dynamics fundamentally unlike anything in the humid-region training set. The San Juan River failure (R-squared = -8.13) is the model's worst performance and maps directly to this gap.

**Physical distinctiveness:**
- Extreme SSC concentrations (10,000-100,000+ mg/L during events vs. 10-2,000 mg/L in humid regions)
- Ephemeral and intermittent flow regimes
- Dual hydrologic drivers: snowmelt (spring) + monsoon (summer)
- Alkaline water chemistry (pH > 8), high conductance (>1,000 uS/cm in many systems)
- Sandstone/shale/evaporite geology produces different sediment mineralogy
- Very sparse discrete sampling (remote locations, dangerous flash flood access)

**CRITICAL WARNING:** Arid sites are the highest-risk targets in this plan. Continuous turbidity sensors are sparse, discrete SSC sampling during high-flow events is rare (dangerous conditions), and many sites have very short records. Expect only 3-4 of 6 targets to yield training-quality data. The remainder become validation targets.

### Target States and Search Strategy

| State | Target Region | Why | Expected Sites | SSC/TP Data |
|-------|--------------|-----|----------------|-------------|
| **NM** | Rio Grande at Otowi Bridge/Albuquerque, Rio Puerco, Rio Chama | Rio Grande at Otowi has one of the longest continuous monitoring records in the Southwest; NRTWQ coverage confirmed for AZ (likely NM via same WSC) | 3-5 sites | **SSC: Medium-High** -- Rio Grande has long USGS sediment record; check for continuous turbidity sensor specifically. **TP: Medium** |
| **AZ** | Salt River near Roosevelt, Verde River, Gila River | Desert mountain transition, monsoon flash floods; AZ WSC confirmed to operate reservoir/stream monitoring with turbidity; NRTWQ covers AZ | 2-4 sites | **SSC: Medium** -- AZ has turbidity at some sites but sparse discrete SSC during events. **TP: Low** |
| **UT** | Green River at Green River, San Rafael River, Price River | Colorado Plateau sandstone; coal-country streams with high SSC | 2-3 sites | **SSC: Medium** -- Check for turbidity at established USGS streamgages. **TP: Low** |
| **NV** | Humboldt River, Truckee River | Great Basin interior drainage, alkaline/saline; NRTWQ covers NV | 1-2 sites | **SSC: Low** -- NV has minimal turbidity monitoring; long shot. **TP: Low** |

**Total sites to query:** 6 (select 2-3 from NM, 1-2 from AZ, 1-2 from UT, 0-1 from NV)

**Site selection preferences:**
- Prioritize sites with EVENT sampling (high-flow SSC samples), not just baseflow
- At least one Rio Grande mainstem site (best data availability in the region)
- At least one ephemeral/intermittent tributary (true arid regime)
- Accept dam-regulated sites if they have turbidity data (Salt River, Green River)
- Accept shorter records (2-3 years) if event sampling exists

**Specific candidate sites:**
- USGS-08313000 Rio Grande at Otowi Bridge, NM (best bet -- extremely well-monitored)
- USGS-08329918 Rio Grande at Albuquerque, NM
- USGS-08334000 Rio Puerco near Bernardo, NM (extreme SSC, classic arid tributary)
- USGS-09498500 Salt River near Roosevelt, AZ
- USGS-09506000 Verde River near Camp Verde, AZ
- USGS-09315000 Green River at Green River, UT

**Alternative data sources if USGS turbidity is insufficient:**
- Bureau of Reclamation HydroMet system (reservoir inflow monitoring at dam sites in AZ, NM, UT)
- USGS acoustic backscatter surrogates (some Colorado Plateau sites use ADCP backscatter for SSC)

---

## REGIME 4: Southeast Piedmont/Coastal Plain

### Why This Regime Needs Representation

The Southeast US from North Carolina through Georgia is a major population and agriculture corridor with distinct red-clay Piedmont soils (kaolinite-rich saprolite) and sandy Coastal Plain soils. The current training set has VA and MD (northern Piedmont) but nothing south of Virginia. The subtropical weathering regime produces thicker saprolite, higher kaolinite content, and different sediment-TP relationships than the northern Piedmont.

**Physical distinctiveness:**
- Deep kaolinite-rich saprolite from intense subtropical weathering
- Red clay produces characteristic turbidity-SSC signature (fine clay, high scattering)
- Coastal Plain transition creates abrupt sediment-type change within single watersheds
- Blackwater streams in Coastal Plain (high DOC, tannin-stained, low SSC)
- Rapid urbanization (Atlanta, Charlotte, Raleigh metros) creates impervious-surface influence
- Year-round warm temperatures, no freeze-thaw

### Target States and Search Strategy

| State | Target Region | Why | Expected Sites | SSC/TP Data |
|-------|--------------|-----|----------------|-------------|
| **NC** | Yadkin-Pee Dee, Neuse, Cape Fear river basins | NC has strong USGS partnership (SAWSC); Piedmont red clay + reservoir sedimentation drives monitoring; WaterQualityWatch confirms real-time turbidity in NC | 5-8 sites | **SSC: Medium-High** -- NC WSC monitors Piedmont streams for reservoir sedimentation. **TP: High** -- Nutrient monitoring for Jordan Lake, Falls Lake TMDLs |
| **SC** | Broad River, Saluda River, Congaree River | SC Piedmont, deeper weathering than NC; Congaree receives combined Piedmont + Blue Ridge sediment | 2-4 sites | **SSC: Medium** -- SC has fewer continuous turbidity sites than NC. **TP: Medium** |
| **GA** | Chattahoochee River (Atlanta metro), Altamaha tributaries, Flint River | GA Piedmont is heavily monitored (Atlanta drinking water); USGS SAWSC covers GA; Chattahoochee confirmed with turbidity data and published E. coli/turbidity regression models (USGS SIR 2012-5037) | 4-6 sites | **SSC: Medium-High** -- Chattahoochee near Atlanta is heavily studied; sediment yields documented in USGS PP 1107. **TP: Medium** |

**Total sites to query:** 7 (select 3 from NC, 1-2 from SC, 2-3 from GA)

**Site selection preferences:**
- At least two Piedmont red-clay sites (different from VA Piedmont -- warmer climate, deeper weathering)
- At least one Coastal Plain sandy site (for within-regime contrast)
- At least one blackwater stream (high DOC, tests turbidity sensor response to organic color)
- Include Atlanta metro Chattahoochee (urban Piedmont, high commercial value)
- Mix of forested reference and agricultural/urban disturbed

**Specific candidate sites:**
- USGS-02094500 Yadkin River at Yadkin College, NC
- USGS-02087580 Neuse River at Smithfield, NC
- USGS-02102500 Cape Fear River at Lillington, NC
- USGS-02169500 Congaree River at Columbia, SC
- USGS-02336000 Chattahoochee River at Atlanta, GA (confirmed monitoring)
- USGS-02350080 Flint River at GA 26, near Montezuma, GA
- USGS-02226000 Altamaha River at Doctortown, GA

---

## REGIME 5: Karst/Carbonate

### Why This Regime Needs Representation

Karst terrain produces unique hydrology: spring-fed baseflow with very low turbidity (<5 FNU), punctuated by rapid turbidity spikes during conduit-flushing events. The turbidity-SSC relationship is fundamentally different because sediment source switches between subsurface conduit sediment (mobilized by rising water tables) and surface-derived sediment (entering sinkholes). Carbonate-buffered water has high alkalinity and often high dissolved nutrients from agricultural infiltration through thin karst soils.

**Physical distinctiveness:**
- Groundwater-dominated flow with spring-fed baseflow
- Bimodal turbidity: very low (baseflow) to very high (conduit flushing)
- Carbonate dissolution produces high alkalinity, high Ca/Mg
- Losing and gaining stream reaches (flow disappears into/emerges from bedrock)
- Thin soils over limestone allow rapid infiltration of surface contaminants
- Dissolved P may dominate over particulate P

### Target States and Search Strategy

| State | Target Region | Why | Expected Sites | SSC/TP Data |
|-------|--------------|-----|----------------|-------------|
| **TX** | San Marcos River, Comal River, Guadalupe River (Edwards Aquifer springs) | Iconic spring-fed streams from Edwards Limestone; constant temperature, variable WQ during recharge | 2-3 sites | **SSC: Medium** -- TX WSC monitors these iconic springs, but continuous turbidity uncertain for very-clear-water sites. **TP: Medium** |
| **TN/KY** | Caney Fork, Elk River, Green River (Highland Rim / Nashville Basin / Mammoth Cave) | Interior Low Plateau karst, Ordovician/Mississippian limestone; existing KY sites (03290500, 03250322) may already be karst -- verify | 2-3 sites | **SSC: Medium** -- TN/KY have USGS monitoring; check if existing KY training sites are actually karst. **TP: Medium-High** -- agricultural karst with high nutrient infiltration |
| **MO/AR** | Illinois River (OK/AR border), Current River, Jacks Fork (Ozarks) | Ozark Plateau karst/dolomite, extremely clear springs, poultry-litter P enrichment; AR confirmed in NRTWQ | 1-2 sites | **SSC: Medium** -- AR NRTWQ coverage confirmed; Ozark springs monitoring exists. **TP: High** -- IL River in OK is heavily monitored due to OK/AR phosphorus disputes |
| **FL** | Ichetucknee River, Santa Fe River, Suwannee River springs | Floridan Aquifer springs, extremely clear water with periodic tannin/DOC pulses | 1 site | **SSC: Low** -- These are very clear systems; turbidity not a primary monitoring concern. **TP: Medium** |

**Total sites to query:** 6 (select 1-2 from TX, 2 from TN/KY, 1-2 from MO/AR, 0-1 from FL)

**Site selection preferences:**
- Include both spring-fed (TX Edwards, FL) and sinkhole-drained (TN/KY, MO/AR) karst types
- Verify existing KY training sites are NOT karst before adding more KY sites
- Accept sites with low turbidity baselines (model needs to learn "low turbidity = low confidence")
- Prioritize sites where conduit-flushing events have been sampled

**Specific candidate sites:**
- USGS-08170500 San Marcos River at San Marcos, TX
- USGS-08168500 Guadalupe River above Comal River, TX
- USGS-03427500 Caney Fork at Carthage, TN
- USGS-03308500 Green River at Munfordville, KY (Mammoth Cave area)
- USGS-07060710 North Sylamore Creek near Fifty Six, AR (Ozark reference)
- USGS-02322500 Santa Fe River near Fort White, FL

**Model applicability note:** Karst sites may be genuinely outside the model's valid domain. Including 3-4 karst sites in training helps the model learn "low confidence" for these conditions. If karst sites consistently degrade model performance, flag them as out-of-domain rather than forcing them into the training set.

---

## REGIME 6: Iron Range/Canadian Shield

### Why This Regime Needs Representation

Northern Minnesota, Wisconsin, and Michigan's Upper Peninsula sit on Precambrian Shield geology with anomalous water chemistry: iron-stained water (visible red/orange color), naturally acidic to neutral pH, low alkalinity, high DOC from boreal wetlands, and mining-derived metals. Iron hydroxide particles (Fe(OH)3) scatter light differently than silicate clay, potentially altering the turbidity-SSC relationship. More critically, iron-bearing minerals adsorb phosphorus differently, producing anomalous TP-turbidity relationships. The St. Louis River TP failure (R-squared = -0.54) maps directly to this gap.

**Physical distinctiveness:**
- Precambrian igneous/metamorphic bedrock (greenstone, iron formation, gneiss)
- Iron-oxide particles contribute to turbidity without corresponding to SSC
- Mining-derived sediment (taconite tailings, waste rock) has unique mineralogy
- Boreal wetland drainage produces high DOC (>10 mg/L), causing color interference with turbidity sensors
- Fe(III)-phosphate co-precipitation creates anomalous P geochemistry
- Cold continental climate, extended ice cover, spring freshet

### Target States and Search Strategy

| State | Target Region | Why | Expected Sites | SSC/TP Data |
|-------|--------------|-----|----------------|-------------|
| **MN** | St. Louis River headwaters, Embarrass River (Mesabi Range), Rainy River, Knife River | Iron range taconite mining, boreal wetland; USGS Upper Midwest WSC covers MN; NRTWQ coverage confirmed; Knife River near Two Harbors has confirmed NRTWQ surrogate model; published MN sediment/turbidity report (USGS 2007-2011) | 3-5 sites | **SSC: Medium-High** -- MN has turbidity at iron-range sites; Knife River confirmed. **TP: Medium-High** -- MN PCA and USGS monitor nutrients extensively |
| **WI** | Bad River, Nemadji River, Bois Brule River (Lake Superior basin) | Red clay terrain (glaciolacustrine clay over Precambrian bedrock); iron-rich clay erosion is a major concern in WI Lake Superior basin; USGS Great Lakes surrogate models published | 2-3 sites | **SSC: Medium-High** -- WI red clay erosion drives monitoring investment. **TP: Medium** |
| **MI** | Sturgeon River, Ontonagon River, Tahquamenon River (Upper Peninsula) | Canadian Shield / Keweenawan geology, copper-mining legacy, boreal forest | 1-2 sites | **SSC: Medium-Low** -- MI UP sites are remote, USGS coverage thinner. **TP: Low-Medium** |

**Total sites to query:** 5 (select 2-3 from MN, 1-2 from WI, 0-1 from MI)

**Site selection preferences:**
- At least one active-mining-influenced site (Mesabi Range)
- At least one non-mining Precambrian site (reference for natural iron geochemistry)
- At least one red-clay glaciolacustrine site (WI Bad River or Nemadji)
- Sites where iron chemistry data (dissolved Fe) is available as a bonus

**Specific candidate sites:**
- USGS-04024000 St. Louis River at Scanlon, MN (was external validation -- move to training)
- USGS-04015330 Knife River near Two Harbors, MN (NRTWQ confirmed with surrogate model)
- USGS-04010500 Pigeon River at Middle Falls, MN
- USGS-04027000 Bad River near Odanah, WI
- USGS-04025500 Bois Brule River near Brule, WI

---

## REGIME 7: Urban Stormwater

### Why This Regime Needs Representation

Urban watersheds with high impervious cover (>20-30%) have fundamentally different sediment transport: rapid hydrograph response, "first flush" of accumulated particles from impervious surfaces, construction sediment, road sand/salt, and tire/brake particle contribution to turbidity. The turbidity-SSC relationship is often weaker because biogenic and anthropogenic particles (rubber, plastic, organic debris) register on turbidity sensors without corresponding mineral SSC. Including urban sites is essential for murkml's commercial viability -- municipalities and stormwater utilities are primary customers.

**Physical distinctiveness:**
- High impervious surface coverage (>20-30%) drives flashy hydrology
- First-flush phenomenon: high turbidity/SSC at storm onset, rapid decline
- Mixed particle types: mineral sediment + construction debris + organic matter + anthropogenic particles
- Road salt influence on winter conductance (northern cities)
- Combined sewer overflow (CSO) events mix sewage with stormwater
- Decoupled TP-turbidity relationship at baseflow (WWTP effluent)

### Target States and Search Strategy

| State | Target Region | Why | Expected Sites | SSC/TP Data |
|-------|--------------|-----|----------------|-------------|
| **PA** | Chester County Brandywine Creek area, Schuylkill tributaries | USGS PA WSC has published turbidity-SSC surrogate regression models for Chester County (confirmed 2020 USGS publication); suburban Piedmont; PA confirmed in NRTWQ | 3-5 sites | **SSC: High** -- Confirmed by published USGS surrogate models. **TP: High** |
| **WA** | Puyallup River, Green River, Duwamish River (Seattle/Tacoma metro) | Pacific NW urban + volcanic/glacial sediment from Mt. Rainier; lahar warning monitoring ensures turbidity data; supplements existing OR sites | 2-4 sites | **SSC: High** -- Seattle-area streams heavily monitored for lahar warning and water supply. **TP: Medium-High** |
| **TX** | Houston urban tributaries (Brays Bayou, White Oak Bayou, Greens Bayou) | Pure urban stormwater in warm subtropical climate; complements Regime 2 Gulf Coast sites | 1-2 sites | **SSC: Medium-High** -- Houston stormwater monitoring for Lake Houston confirmed. **TP: Medium** |
| **GA** | Chattahoochee urban tributaries, Peachtree Creek (Atlanta) | Warm-climate urban on Piedmont red clay; complements Regime 4 SE Piedmont | 1 site | **SSC: Medium** -- Check for turbidity at Atlanta urban tributary gages. **TP: Medium** |
| **OH** | Cuyahoga River (Cleveland metro) | Glaciated Midwest urban; supplements existing OH training sites with explicitly urban signature | 0-1 sites | **SSC: Medium** -- OH already in training set; check if existing OH sites are urban. **TP: Medium** |
| **MN** | Mississippi River at St. Paul, Minnesota River at Mankato | Large river urban/agricultural combined influence; confirmed NRTWQ coverage | 0-1 sites | **SSC: Medium-High** -- MN NRTWQ confirmed. **TP: High** |

**Total sites to query:** 6 (select 2 from PA, 2 from WA, 1 from TX, 1 from GA)

**Site selection preferences:**
- At least two high-impervious (>30%) small urban watersheds (<100 km2)
- At least one large river through major metro (>1,000 km2 drainage)
- Geographic spread: include both northern (road salt) and southern (no road salt) cities
- Include at least one CSO-influenced site if available

**Specific candidate sites:**
- USGS-01480617 Brandywine Creek at Chadds Ford, PA (confirmed surrogate model)
- USGS-01480870 East Branch Brandywine Creek below Downingtown, PA
- USGS-12101500 Puyallup River at Puyallup, WA (lahar monitoring, confirmed turbidity)
- USGS-12113000 Green River near Auburn, WA
- USGS-08075000 Brays Bayou at Houston, TX
- USGS-02336300 Peachtree Creek at Atlanta, GA

---

## REGIME 8: New England/Northeast

### Why This Regime Needs Representation

New England and the northeastern US sit on glaciated crystalline bedrock (granite, gneiss, schist) producing dilute, low-nutrient water with minimal sediment supply. The turbidity-SSC relationship here is characterized by very low concentrations (baseline turbidity <5 FNU, SSC typically <50 mg/L) with episodic snowmelt and storm pulses. The model needs exposure to these dilute systems to learn "low turbidity = low SSC with low uncertainty" rather than extrapolating from high-turbidity training sites.

**Physical distinctiveness:**
- Glaciated crystalline/metamorphic bedrock (low weathering rates)
- Dilute water: low conductance (<100 uS/cm), low alkalinity, low nutrients
- Glacial till and outwash create heterogeneous surficial deposits
- Snowmelt-dominated spring hydrology with ice-jam flooding
- Dissolved P often dominates over particulate P (TP prediction challenge)
- Mixed hardwood-conifer forest, limited agriculture

### Target States and Search Strategy

| State | Target Region | Why | Expected Sites | SSC/TP Data |
|-------|--------------|-----|----------------|-------------|
| **NY** | Mohawk River, Schoharie Creek, Hudson tributaries | USGS NY WSC has published turbidity-derived SSC model archive summaries for Mohawk/Schoharie (3 sites confirmed: 01349527, 01351500, 01357500, data 2015-2020) | 3-5 sites | **SSC: High** -- Confirmed published surrogate models for Mohawk/Schoharie. **TP: Medium-High** |
| **CT** | Housatonic River, Quinnipiac River, Connecticut River tributaries | New England suburban/agricultural; Long Island Sound TMDL drives nutrient monitoring; USGS New England WSC covers CT | 2-3 sites | **SSC: Medium-High** -- CT rivers monitored for Long Island Sound nutrient loading. **TP: High** -- Dissolved-P-dominant regime, important for model calibration |
| **NH/VT** | Connecticut River upper basin, Merrimack River tributaries | Crystalline bedrock reference systems; forested, dilute, low human influence | 1-2 sites | **SSC: Medium** -- Less investment in turbidity than CT/NY; check USGS New England WSC. **TP: Medium** |
| **MA** | Blackstone River, Merrimack River at Lowell | Mixed urban/suburban New England; industrial legacy | 1-2 sites | **SSC: Medium** -- Check for continuous turbidity at established streamgages. **TP: Medium** |

**Total sites to query:** 6 (select 2-3 from NY, 1-2 from CT, 1 from NH/VT, 0-1 from MA)

**Site selection preferences:**
- At least two confirmed Mohawk River area sites (known data availability)
- At least one Long Island Sound tributary (dissolved-P regime)
- At least one forested reference headwater (crystalline bedrock, low disturbance)
- Mix of urban/suburban (CT, MA) and forested (NH, VT)

**Specific candidate sites:**
- USGS-01349527 Mohawk River above SH 30A at Fonda, NY (confirmed surrogate model)
- USGS-01351500 Schoharie Creek at Burtonsville, NY (confirmed surrogate model)
- USGS-01357500 Mohawk River at Cohoes, NY (confirmed surrogate model)
- USGS-01184000 Connecticut River at Thompsonville, CT
- USGS-01196500 Quinnipiac River at Wallingford, CT
- USGS-01078000 Merrimack River tributary, NH

---

## REGIME 9: Northern Great Plains/Prairie Pothole

### Why This Regime Needs Representation

The Northern Great Plains from the Dakotas through eastern Montana features glacial deposits over sedimentary bedrock, prairie grassland/cropland, seasonal wetland complexes (prairie potholes), and extreme continental climate. The Red River of the North (external validation R-squared = 0.90 for SSC) demonstrated good model transferability for glaciolacustrine clay, suggesting these sites can slot into training readily. However, the broader regime includes glacial till (different from glaciolacustrine clay), prairie pothole hydrology (seasonal wetland storage), and grassland sediment sources that differ from the existing KS Great Plains sites.

**Physical distinctiveness:**
- Glacial deposits: till, outwash, glaciolacustrine clay (Lake Agassiz basin)
- Prairie pothole wetlands modulate runoff (seasonal storage and release)
- Extreme continental climate: -30C winters, +35C summers, 300-500 mm annual precip
- Spring flood dominated hydrology (snowmelt + frozen ground)
- Grassland/cropland sediment: different from KS tallgrass prairie (shorter grass, less soil aggregation)
- High sodium/sulfate in some western ND/MT groundwaters

### Target States and Search Strategy

| State | Target Region | Why | Expected Sites | SSC/TP Data |
|-------|--------------|-----|----------------|-------------|
| **ND** | Red River of the North, James River, Souris River, Heart River | Red River is extensively monitored (confirmed NRTWQ coverage for ND); Wild Rice River SSC/bedload publication confirmed (USGS OFR 2025-1008); James River drains prairie pothole country | 3-5 sites | **SSC: High** -- Red River is one of the most intensively monitored rivers in USGS network. **TP: High** -- Nutrient monitoring for Devils Lake and Red River |
| **SD** | James River, Big Sioux River, White River | Eastern SD glacial till, western SD semi-arid badlands; transition zone | 1-3 sites | **SSC: Medium** -- SD has USGS streamgages but less turbidity investment. **TP: Medium** |
| **MT-east** | Yellowstone River, Milk River | Eastern MT prairie, semi-arid grassland; supplements existing MT mountain sites | 1-2 sites | **SSC: Medium** -- MT already in training but only mountain sites; check eastern MT gages. **TP: Low-Medium** |
| **NE-west** | Niobrara River, North Platte tributaries | Sand Hills region, unique dune-fed groundwater hydrology; very different from eastern NE loess | 0-1 sites | **SSC: Low-Medium** -- Sand Hills streams are clear and spring-fed; limited turbidity monitoring. **TP: Low** |

**Total sites to query:** 6 (select 3 from ND, 1-2 from SD, 1 from MT-east, 0-1 from NE-west)

**Site selection preferences:**
- Move Red River external validation site(s) into training (confirmed R-squared = 0.90)
- Include at least one prairie pothole-influenced stream (James River)
- Include at least one western semi-arid transition site (Heart River or White River)
- Mix of glaciolacustrine clay (Red River) and glacial till (James, Big Sioux) substrates

**Specific candidate sites:**
- USGS-05054000 Red River of the North at Fargo, ND (was external validation, move to training)
- USGS-05066500 Goose River at Hillsboro, ND
- USGS-06470000 James River near Scotland, SD
- USGS-06354000 Heart River near Mandan, ND
- USGS-06185500 Missouri River near Culbertson, MT (eastern MT prairie)
- USGS-06457500 Big Sioux River near Brookings, SD

---

## REGIME 10: Deep South/Lower Mississippi

### Why This Regime Needs Representation

The Lower Mississippi alluvial floodplain from western Tennessee through Mississippi, Louisiana, and Arkansas is one of the most important agricultural regions in the US (cotton, rice, soybeans) and has extremely distinct sediment characteristics: thick alluvial deposits, high organic content from subtropical vegetation, slow-moving turbid water, and oxbow lake/bayou hydrology. This regime is absent from training and represents a large commercial market (Mississippi Delta agriculture).

**Physical distinctiveness:**
- Thick alluvial floodplain deposits (Mississippi River depositional environment)
- High organic content from subtropical vegetation and wetland soils
- Flat terrain, low gradient, backwater flooding
- Rice/cotton/soybean agriculture with heavy water management (levees, pumps, diversions)
- Warm subtropical climate with year-round biological activity
- Very fine-grained sediment (clay and silt from upstream erosion)

### Target States and Search Strategy

| State | Target Region | Why | Expected Sites | SSC/TP Data |
|-------|--------------|-----|----------------|-------------|
| **AR** | White River, Cache River, Arkansas River, L'Anguille River | USGS NRTWQ confirmed for AR; Arkansas River carries Rocky Mountain sediment into alluvial plain; White River is important for rice agriculture water supply | 2-4 sites | **SSC: Medium** -- AR has some turbidity monitoring; less than KS or IA. **TP: Medium** |
| **MS** | Yazoo River, Big Sunflower River, Pearl River | Mississippi Delta (Yazoo Basin) is the prototypical alluvial floodplain; Pearl River drains Coastal Plain/Piedmont transition; USGS Lower MS-Gulf WSC covers this area | 1-2 sites | **SSC: Medium-Low** -- MS has limited continuous turbidity. **TP: Medium** |
| **LA** | Ouachita River, Red River tributaries, Bayou Lafourche | Northern LA is alluvial plain distinct from coastal LA (Regime 2); Red River carries different sediment than Mississippi | 1-2 sites | **SSC: Medium-Low** -- LA turbidity monitoring sparse outside Atchafalaya. **TP: Low-Medium** |
| **TN-west** | Hatchie River, Obion River, Wolf River (Memphis area) | Western TN is Mississippi alluvial plain; Hatchie River is the last unchannelized major tributary to Lower Mississippi | 1-2 sites | **SSC: Medium** -- TN WSC (part of Lower MS-Gulf WSC) monitors some WQ sites. **TP: Medium** |

**Total sites to query:** 6 (select 2 from AR, 1-2 from MS, 1 from LA, 1 from TN-west)

**Site selection preferences:**
- At least one major alluvial-plain river (Yazoo, White River)
- At least one rice-agriculture-influenced stream (Cache River, L'Anguille)
- At least one unchannelized/reference floodplain stream (Hatchie River)
- Avoid Mississippi River mainstem (too large, too complex for turbidity-SSC relationship)

**Specific candidate sites:**
- USGS-07077500 Cache River at Patterson, AR
- USGS-07074500 White River at Newport, AR
- USGS-07289000 Yazoo River at Greenwood, MS
- USGS-07364150 Ouachita River at Camden, AR
- USGS-07030050 Hatchie River at Bolivar, TN
- USGS-07032000 Wolf River at Germantown, TN (Memphis suburban)

---

## REGIME 11: Pacific Coast/Cascade (Supplement Existing OR)

### Why This Regime Needs Representation

The current training set has good Oregon coverage but lacks Washington state entirely. WA adds two critical sub-regimes: (1) glacier-fed streams from Mt. Rainier/North Cascades with glacial flour (rock flour), and (2) rain-dominated coastal streams with logging/landslide influence. Adding WA provides within-regime replication for LOGO-CV and introduces glacial-flour sediment mineralogy not present in OR volcanic sites.

**Physical distinctiveness:**
- Active glacial meltwater with rock flour (very fine mineral particles from glacial grinding)
- Rain-dominated coastal streams with extremely high precipitation (>3000 mm/yr)
- Logging-influenced watersheds with landslide-derived sediment pulses
- Volcanic soils (Cascades) produce unique sediment mineralogy
- Lahar risk monitoring ensures high-quality continuous turbidity data at key sites

### Target States and Search Strategy

| State | Target Region | Why | Expected Sites | SSC/TP Data |
|-------|--------------|-----|----------------|-------------|
| **WA** | Nisqually River, White River (Mt. Rainier glacier-fed); Nooksack River (North Cascades); Chehalis River (coastal rain-dominated) | WA WSC operates extensive turbidity monitoring for lahar warning (Mt. Rainier) and water supply | 6-10 sites | **SSC: High** -- Lahar monitoring and Puget Sound water supply drive continuous turbidity. **TP: Medium** |

**Total sites to query:** 4 (supplement, not duplicate with Regime 7 urban WA sites)

**Site selection preferences:**
- At least one glacier-fed stream (glacial flour sediment type)
- At least one coastal rain-dominated stream (logging influence)
- Avoid duplicating Regime 7 urban WA sites (assign Puyallup/Green River to Regime 7 if urban-dominated, or Regime 11 if glacier-dominated -- check GAGES-II impervious surface %)
- Include at least one volcanic-ash-influenced stream

**Specific candidate sites:**
- USGS-12082500 Nisqually River near National, WA (glacier-fed reference)
- USGS-12100000 White River near Buckley, WA (glacier-fed, high SSC from Mt. Rainier)
- USGS-12210700 Nooksack River at Ferndale, WA (North Cascades glacier + ag)
- USGS-12027500 Chehalis River near Grand Mound, WA (coastal rain-dominated)

---

## REGIME 12: Cold Semi-Arid/Steppe

### Why This Regime Needs Representation

Wyoming, eastern Montana, and the western Dakotas occupy the cold semi-arid steppe -- grassland with low precipitation (250-400 mm/yr), snowmelt-dominated hydrology, and sedimentary bedrock (shale, sandstone, coal-bearing formations). This regime differs from the Great Plains (KS) in being colder, drier, and having different geology (Cretaceous marine shale vs. Permian limestone/shale). Coal and oil development add anthropogenic sediment sources.

**Physical distinctiveness:**
- Cold semi-arid climate (shorter growing season, deeper frost penetration than KS)
- Cretaceous/Tertiary sedimentary bedrock (shale, sandstone, coal, bentonite)
- Snowmelt-dominated spring runoff with very low summer flows
- Sagebrush-grassland land cover (less soil aggregation than tallgrass prairie)
- Coal mining and oil/gas development create localized sediment disturbance
- Sodium/sulfate-rich groundwater from marine shale weathering
- Badlands topography in some areas (extreme erosion rates)

### Target States and Search Strategy

| State | Target Region | Why | Expected Sites | SSC/TP Data |
|-------|--------------|-----|----------------|-------------|
| **WY** | Wind River, Bighorn River, North Platte tributaries, Powder River | USGS WY-MT WSC STEPPE program covers energy/plains hydrology; Powder River is heavily studied for coal/CBM development | 2-3 sites | **SSC: Medium** -- WY has streamgages but continuous turbidity less common; Powder River more likely due to coal concerns. **TP: Low-Medium** |
| **MT-east** | Musselshell River, Yellowstone tributaries (Tongue River, Rosebud Creek) | Eastern MT steppe, coal/ag; Tongue River monitored for coal mining impacts | 1-2 sites | **SSC: Medium** -- Coal mine monitoring may include turbidity; check MT sites beyond existing mountain training sites. **TP: Low** |
| **SD-west** | Cheyenne River, White River, Bad River | Western SD badlands/grassland; extreme erosion in badlands topography; White River carries some of the highest SSC in the northern US | 1-2 sites | **SSC: Medium** -- Cheyenne and White River have USGS gages; check for turbidity sensors. **TP: Low** |

**Total sites to query:** 5 (select 2 from WY, 1-2 from MT-east, 1 from SD-west)

**Site selection preferences:**
- At least one Powder River or Tongue River site (coal-development influence)
- At least one high-erosion badlands tributary (White River or Bad River, SD)
- At least one snowmelt-dominated rangeland stream without energy-development influence (reference)

**Specific candidate sites:**
- USGS-06324500 Powder River at Moorhead, MT (coal country, long sediment record)
- USGS-06298000 Tongue River at Miles City, MT
- USGS-06438000 Cheyenne River near Wasta, SD
- USGS-06441500 Bad River near Fort Pierre, SD (extreme SSC from badlands)
- USGS-06235500 Wind River near Riverton, WY

---

## Cross-Cutting Diversity Targets

### Drainage Area Distribution

| Size Class | Drainage Area | Current Coverage | Expansion Target | Regimes Providing |
|-----------|--------------|-----------------|-----------------|-------------------|
| Headwater | <50 km2 | Good (PA Chester Co, small OR tributaries) | 5-8 new sites | 7 (urban), 5 (karst springs), 6 (MN headwaters) |
| Small | 50-500 km2 | Good (many existing sites) | 10-15 new sites | All regimes |
| Medium | 500-5,000 km2 | Good | 15-20 new sites | All regimes |
| Large | 5,000-50,000 km2 | Moderate | 10-15 new sites | 1 (Iowa/Illinois River), 2 (Brazos), 4 (Yadkin), 9 (James), 10 (White/Yazoo) |
| Major | >50,000 km2 | Limited | 5-8 new sites | 1 (Missouri R), 3 (Rio Grande), 9 (Red River), 12 (Yellowstone) |

### Special Site Types (Minimum Targets)

| Type | Minimum New Sites | Regimes Providing |
|------|-------------------|-------------------|
| **Dam-regulated** | 5-8 | 3 (Salt River AZ, Green River UT), 11 (WA reservoir releases), 1 (MO River) |
| **Reference/pristine** | 5-8 | 6 (boreal forest headwaters), 8 (NH/VT forested), 11 (glacier-fed reference), 5 (Ozark springs) |
| **WWTP-influenced** | 3-5 | 2 (TX suburban), 7 (PA suburban, TX urban), 4 (GA Atlanta tributaries) |
| **Mining-influenced** | 3-5 | 6 (iron range MN, copper MI), 2 (FL phosphate), 12 (coal WY/MT) |
| **Tile-drained** | 3-5 | 1 (IA, IL), 9 (SD-east) |

### Elevation Distribution

| Elevation | Expansion Target | Regimes Providing |
|-----------|-----------------|-------------------|
| Sea level to 100m | 10-15 new sites | 2 (Gulf Coast), 4 (Coastal Plain), 10 (alluvial plain) |
| 100-500m | 25-30 new sites | Most regimes |
| 500-1500m | 15-20 new sites | 1 (IA, NE), 3 (NM, UT), 12 (WY, MT) |
| 1500-2500m | 5-8 new sites | 3 (Rio Grande, AZ mountains), 12 (WY Wind River) |
| >2500m | 0-2 new sites | Existing CO sites adequate |

---

## Implementation Schedule

### Phase 1: High-Confidence States (Week 1)
**States:** IA, NE, MO, TX, PA, WA, NY, ND
**Expected yield:** 25-30 sites
**Rationale:** These states have confirmed NRTWQ coverage, published surrogate models, or known active turbidity programs.

**Query strategy:**
1. Query NWIS for all sites with `parameterCd=63680` + `hasDataTypeCd=uv` in each state
2. For each candidate, count SSC (80154) and TP (00665) discrete samples
3. Filter: n_ssc >= 50 AND turbidity record >= 2 years
4. Cross-reference against GAGES-II site list
5. Select top candidates per regime

### Phase 2: Medium-Confidence States (Week 2)
**States:** IL, NC, SC, GA, FL, AL, MN, WI, AR, CT, SD
**Expected yield:** 20-25 sites
**Rationale:** These states have USGS WQ programs but continuous turbidity coverage less certain.

**Important:** Also query `parameterCd=00076` (turbidity NTU) for these states. Some older installations report NTU rather than FNU. The data pipeline needs to detect and convert.

### Phase 3: Low-Confidence States (Week 3)
**States:** AZ, NM, UT, NV, WY, MT-east, MI, TN, KY (new sites), NH/VT, MA
**Expected yield:** 10-15 sites
**Rationale:** Continuous turbidity is sparse in these states. Sites with n_ssc = 20-49 become validation targets.

### Phase 4: Triage and Final Selection (Week 4)
1. Compile all candidates from Phases 1-3
2. Apply hard filters: n_ssc >= 50, turbidity record >= 2 years, period overlap
3. Apply regime balance: if a regime has >8 viable candidates, select best 6-8
4. Verify no regime has <3 training sites (minimum for LOGO-CV)
5. Designate n_ssc = 20-49 sites as external validation
6. Final training set target: 125-140 total sites

---

## Data Download and QC Protocol

Once sites are selected:

1. **Turbidity sensor type check:** Verify FNU (preferred, ISO 7027) vs. NTU (older). Record sensor type in metadata.

2. **Turbidity range check:** Flag sites where turbidity exceeds sensor range (typically 0-4000 FNU). Arid sites may exceed this during flash floods.

3. **SSC-turbidity temporal matching:** Discrete SSC samples must fall within +/- 30 minutes of a continuous turbidity reading.

4. **SSC concentration range:** Log min/max/median SSC. Sites with SSC >10,000 mg/L need special handling (log-transform or separate high-concentration branch).

5. **TP dissolved fraction check:** Calculate orthoP/TP ratio if orthoP (00671) available. Sites with dissolved P > 50% of TP flagged as "dissolved-P-dominant."

6. **GAGES-II attribute extraction:** For sites in GAGES-II, extract full attribute set. For sites NOT in GAGES-II, use NLDI.

---

## Expected Outcomes

### Training Set After Expansion

| Regime | Current | After | States |
|--------|---------|-------|--------|
| Great Plains agricultural | ~15 | ~15 | KS |
| Midwest glaciated | ~10 | ~10 | IN, OH |
| Pacific NW volcanic/forest | ~10 | ~14 | OR, WA |
| California Mediterranean | ~15 | ~15 | CA |
| Mountain/Rockies | ~5 | ~5 | CO, MT-west, ID |
| Mid-Atlantic Piedmont | ~5 | ~5 | VA, MD |
| Appalachian | ~2 | ~2 | KY |
| **Loess belt** | 0 | **6-8** | IA, NE, MO, IL |
| **Gulf Coastal Plain** | 0 | **5-7** | TX, LA, FL, AL |
| **Arid/Semi-Arid Southwest** | 0 | **3-5** | NM, AZ, UT |
| **Southeast Piedmont/CP** | 0 | **5-7** | NC, SC, GA |
| **Karst/Carbonate** | 0 | **4-6** | TX, TN, MO/AR, FL |
| **Iron Range/Canadian Shield** | 0 | **3-5** | MN, WI, MI |
| **Urban Stormwater** | 0 | **4-6** | PA, WA, TX, GA |
| **New England/Northeast** | 0 | **4-6** | NY, CT, NH |
| **N. Great Plains/Prairie Pothole** | 0 | **4-6** | ND, SD, MT-east |
| **Deep South/Lower Mississippi** | 0 | **3-5** | AR, MS, TN |
| **Cold Semi-Arid/Steppe** | 0 | **3-5** | WY, MT-east, SD |
| **TOTAL** | **~57** | **~125-140** | **~23 states** |

### Geographic Coverage

- **Current:** 11 states, ~40% of CONUS by area, ~5 of 25 EPA Level II ecoregions
- **After:** ~23 states, ~80% of CONUS by area, ~18 of 25 EPA Level II ecoregions
- **Remaining gaps:** Alaska, Hawaii, extreme desert interior, high-alpine (>3500m)

### Expected Model Performance

| Metric | Current | After Expansion |
|--------|---------|----------------|
| Training LOGO-CV SSC R2 | 0.79 | 0.74-0.78 (more honest with harder sites) |
| External validation SSC R2 (median) | ~0.70 | 0.75-0.82 (fewer catastrophic failures) |
| Worst-case SSC R2 | -8.13 (San Juan) | -1.0 to 0.3 (arid still challenging) |
| TP external validation R2 (median) | ~0.40 | 0.45-0.55 (improved for particulate-P) |
| Applicability domain (% CONUS streams) | ~35-40% | ~70-80% |

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Arid sites insufficient paired data | High (60%) | Medium | Accept smaller arid representation; supplement with BOR data |
| Iron Range sites lack continuous turbidity | Medium (40%) | Medium | Check MN PCA and WI DNR state networks |
| New sites degrade existing performance | Medium (30%) | High | Site-level sample weighting; stratified training |
| GAGES-II gaps for new sites | Medium (40%) | Medium | NLDI attribute extraction as backup |
| Turbidity sensor type mismatch (NTU/FNU) | High (50%) | Low | Add sensor-type detection; include as model feature |
| CA still overrepresented after expansion | Medium (30%) | Medium | Site-level sample weighting; cap per-site at 300 samples |

---

## Appendix A: NRTWQ State Coverage

**Confirmed NRTWQ states (continuous WQ with surrogate models):**
AZ, AR, CA, CO, ID, IN, IA, KS, MD, MN, MO, MT, NE, NV, ND, OR, PA

**WaterQualityWatch turbidity (real-time sensors, no surrogate models):**
NC, SC, GA, FL, TX, AL, MS, LA, TN, NY, CT, WA, WI, MI, OH, VA, WY, SD, NH, MA, VT

## Appendix B: NWIS Parameter Codes

| Parameter | Code | Description | Required? |
|-----------|------|-------------|-----------|
| Turbidity, FNU | 63680 | Formazin Nephelometric Units (ISO 7027) | Required |
| Turbidity, NTU | 00076 | Nephelometric Turbidity Units (older) | Query as backup |
| SSC | 80154 | Suspended-sediment concentration, mg/L | Required |
| TSS | 00530 | Total suspended solids, mg/L | NOT recommended |
| TP | 00665 | Total phosphorus, mg/L as P | Preferred |
| OrthoP | 00671 | Orthophosphate, dissolved, mg/L as P | Useful for dissolved-P fraction |
| Sp. Conductance | 00095 | In-situ, uS/cm | Supplemental feature |
| Streamflow | 00060 | Discharge, cfs | Required (co-located) |

## Appendix C: Site Metadata Convention

```
site_id: USGS-XXXXXXXX
state: Full state name
regime: {loess, gulf_coastal, arid_sw, se_piedmont, karst, iron_range,
         urban, new_england, n_great_plains, deep_south, pacific_cascade,
         cold_steppe}
phase: {training, validation}
n_ssc_samples: integer
n_tp_samples: integer
turbidity_unit: {FNU, NTU}
gagesii: {yes, no}
```

---

*Dr. Elena Vasquez, Hydrogeochemist -- 15 years groundwater/surface water geochemistry, USGS and academic*
*Dr. Marcus Rivera, Hydrologist (ret.) -- 20 years USGS Water Resources Division, sediment transport and surrogate regression*
*Full site expansion plan for murkml training set scaling, 2026-03-17*
