# Data Download Plan — Multi-Parameter + Catchment Attributes

> **STATUS (2026-03-25): LARGELY COMPLETE.**
> Multi-parameter discrete data has been downloaded for all parameters (SSC, TP, nitrate, orthoP) across the expanded 102-site network. GAGES-II and NLCD attributes have been downloaded and merged. TDS was deprioritized. See actual results below.
>
> **What was achieved vs planned:**
> - Discrete data for TP (72 sites), nitrate (66 sites), orthoP (62 sites) — downloaded and assembled
> - GAGES-II attributes matched for 58 sites (Tier 1)
> - NLCD 2019 backfill for 37 additional sites (Tier 3 via pygeohydro)
> - NLDI characteristics pulled for gap-filling (Tier 2)
> - TDS (pcode 70300) was not pursued — SC-TDS relationship is near-linear and not a priority
> - StreamCat (Tier 4) is now the PLANNED replacement for the two-source attribute problem
>
> **Remaining:** StreamCat migration to replace GAGES-II + NLCD with a single consistent source for all 102 sites.

## Goal (original)
Download all remaining data needed for the multi-target model: discrete lab data for 4 new parameters at all 57 existing sites, plus catchment/watershed attributes.

**Rule:** Same sites for all parameters. We are building complete site profiles, not mixing data across sites.

---

## Part 1: Discrete Lab Data for New Parameters

### Parameters to pull (from Vasquez panel review)

| Parameter | USGS pcode | Why |
|-----------|-----------|-----|
| Total Phosphorus | 00665 | Largest TMDL impairment, binds to sediment |
| Nitrate+Nitrite | 00631 | Drinking water MCL, nutrient TMDLs |
| TDS (evaporative) | 70300 | Near-linear with conductance, irrigation/mining |
| Orthophosphate | 00671 | Secondary target, enforce TP >= ortho-P |

### Approach

1. **Scan all 57 sites** for each parameter — count how many discrete samples exist
2. **Download discrete data** for all site/parameter combinations that have ≥10 samples
3. **Save as** `data/discrete/{site_id}_{pcode}.parquet` (same pattern as SSC)
4. **Build a multi-parameter availability matrix** showing which sites have which parameters

### API details
- Function: `waterdata.get_samples(monitoringLocationIdentifier="USGS-XXXXXXXX", usgsPCode="00665")`
- Token: `API_USGS_PAT` env var (1000 req/hr)
- No pagination on get_samples — query one site at a time
- Rate limit: add 1-second delay between calls

### Expected outcome
- ~30-40 of 57 sites will have nutrient data (some are sediment-only)
- Sites with nutrient data will typically have hundreds of samples
- The multi-parameter model will use only the subset of sites that have ALL target parameters

---

## Part 2: Catchment/Watershed Attributes

### What we need per site
- **Land cover:** % forest, % agriculture, % urban, % impervious
- **Geology:** dominant lithology, % carbonate, % sandstone
- **Soils:** clay content, permeability, hydrologic soil group
- **Climate:** mean annual precipitation, mean annual temperature
- **Topography:** mean slope, mean elevation (elevation already downloaded)
- **Hydrology:** baseflow index, drainage area (already downloaded)

### Approach (tiered fallbacks)

**Tier 1: GAGES-II (easiest, covers most sites)**
- Download from ScienceBase: https://www.sciencebase.gov/catalog/item/631405bbd34e36012efa304a
- ~300 attributes for 9,322 USGS sites
- Static dataset (2006-2011 era) but comprehensive
- Join by station number to our site catalog
- Most of our 57 sites should be in GAGES-II

**Tier 2: NLDI characteristics (API, for sites not in GAGES-II)**
- New URL: https://api.water.usgs.gov/nldi/
- `GET /linked-data/nwissite/USGS-{siteID}/tot` for total upstream characteristics
- Limited subset of attributes but includes key ones
- Also gets COMIDs for StreamCat queries

**Tier 3: HyRiver ecosystem (if we need raster-derived attributes)**
- `pynhd` for StreamCat metrics by COMID
- `pygeohydro` for NLCD land cover + SSURGO soils
- `pydaymet` for climate grids
- Requires geopandas/GDAL — may be tricky on Windows
- Install: `pip install pynhd pygeohydro py3dep pydaymet`

**Tier 4: StreamCat bulk CSVs (fallback if API is down)**
- Download from GitHub: https://github.com/USEPA/StreamCat
- 600+ metrics per stream reach
- Need COMIDs from NLDI first

### Risk: EPA StreamCat API
StreamCat returned 503 errors in March 2026. EPA budget cuts may have degraded it.
Fallback: GAGES-II covers most of what we need. HyRiver can fill gaps.

---

## Execution Order

1. **Download GAGES-II** from ScienceBase (one-time download, ~100MB)
2. **Match GAGES-II sites** to our 57-site catalog by station number
3. **Scan all 57 sites** for nutrient/TDS discrete data availability
4. **Download discrete data** for TP, nitrate, TDS, orthophosphate
5. **Build multi-parameter availability matrix**
6. **NLDI COMID lookup** for sites not in GAGES-II
7. **Fill attribute gaps** with HyRiver if needed

Steps 1-2 and 3-5 can run in parallel (different data sources, no conflicts).

---

## Output Files

| File | Contents |
|------|----------|
| `data/discrete/{site}_{pcode}.parquet` | Discrete lab data per site per parameter |
| `data/site_parameter_matrix.parquet` | Which sites have which parameters and how many samples |
| `data/site_attributes_gagesii.parquet` | GAGES-II catchment attributes for our sites |
| `data/site_attributes.parquet` | Updated with all catchment attributes merged |
