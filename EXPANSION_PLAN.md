# Site Expansion Plan

## Current Status (2026-03-25)

**Expansion is partially complete.** We reached **102 training sites** (up from 57), not the original target of ~137. The 102 sites span 12 watershed regimes and 19,611 SSC samples.

**Key results at 102 sites:** SSC LOGO CV R²=0.80 (log), R²=0.61 (native-space mg/L). See `RESULTS_LOG.md` for full metrics.

**Remaining work:**
- External validation has only 11 holdout sites — need 20-30 for credible generalization claims (red team finding)
- StreamCat migration will give all sites consistent watershed attributes (currently two inconsistent sources)

## Goal
Expand from 57 to ~137 training sites across 12 watershed regimes.
Validate on original 20 external sites (unchanged) + ~15-20 new holdout sites.

## Validation Philosophy
- Original 20 external validation sites are PERMANENT holdout — never trained on
- These include the v1 failure sites (IA loess, TX Gulf Coast, AZ arid, etc.)
- New training sites fill the SAME regimes as the failures
- Before/after comparison on the same failure sites proves the expansion worked
- **Red team finding (2026-03-24):** 11 holdout sites is too few. Need 20-30 sites for external validation to be credible. Prioritize expanding holdout set.

## Training Expansion (~80 new sites)

| Regime | Sites | Target States | Gap Being Filled |
|--------|-------|---------------|------------------|
| Loess belt | 6-8 | IA, NE, MO, IL | Iowa SSC failure (particle size) |
| Gulf Coastal Plain | 6-8 | TX, LA, MS, AL, FL | TX TP failure (WWTP, coastal soils) |
| Arid Southwest | 5-6 | NM, AZ, UT, west TX | AZ SSC failure (ephemeral flow) |
| Iron Range | 5-6 | northern MN, WI, MI | MN TP failure (iron geochemistry) |
| SE Piedmont | 5-6 | NC, SC, GA | GA TP failure, missing ecoregion |
| Karst/carbonate | 5-6 | TX Edwards, TN/KY, FL, MO/AR | Groundwater-dominated, unique turbidity |
| Urban stormwater | 5-6 | any major metro | WWTP/impervious influence |
| New England | 5-6 | CT, MA, NH, VT, ME | CT TP failure (dissolved-P, dilute) |
| Glaciolacustrine | 5-6 | ND, SD, MN, WI | Prairie, clay-rich, seasonal |
| Blue Ridge/Appalachian | 5-6 | NC, WV, VA, TN | Reference sites, forested |
| Cold semi-arid | 4-5 | WY, MT-east, ND-west | Grassland, snowmelt |
| Deep South alluvial | 4-5 | MS, LA, AR, western TN | Floodplain, high organic |

## Validation Holdout (~35 sites)

### Original 20 (permanent, already downloaded)
TX(2), WA(2), PA(1), MN(2), NY(2), GA(2), IA(1), FL(1), WI(2), NE(1), AL(1), TN(1), CT(1), AZ(1)

### New holdout (~15-20, different states from training when possible)
2-3 per regime in states NOT used for training in that regime.

## Execution Order

1. Search USGS for training sites → verify turbidity + discrete data
2. Download training sites (continuous + discrete, all parameters)
3. Retrain model on ~137 sites (START validation downloads in parallel)
4. Download validation holdout sites
5. Run on original 20 failures → before/after comparison
6. Run on new holdout sites → broader generalization test

## Expected Outcome
- SSC: LOGO CV should stay ~0.80 or improve — **ACHIEVED at 102 sites (R²=0.80 log, 0.61 native)**
- SSC external: Iowa, AZ, TX failures should improve significantly
- TP: Should improve at GA, MN, CT failures if regime coverage helps — **TP collapsed from 0.62 to -0.08 at 72 sites; regime-dependent, not fixable with more data alone**
- TP dissolved-P failures (FL, CT): May still struggle — this is a feature limitation, not training size

## Watershed Attribute Unification
All 102 sites will migrate to **EPA StreamCat** for consistent attributes. Currently:
- 58 sites: full GAGES-II (2006 vintage)
- 37 sites: NLCD 2019 land cover only (no geology/soils/climate)
- 7 sites: no watershed attributes

StreamCat covers all NHDPlus catchments with 600+ attributes from a single framework.
