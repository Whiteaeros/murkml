# Training Diversity Analysis -- Is This a Site Coverage Problem?
**Reviewer:** Dr. Marcus Rivera, USGS (ret.), 20 years Water Resources Division
**Date:** 2026-03-17
**Prompted by:** Kaleb's question on whether external validation failures are primarily a training diversity problem

---

## Short Answer

Kaleb, you are mostly right, and your instinct is good. But "mostly" is doing important work in that sentence. Let me break it down.

---

## 1. Is This Primarily a Training Diversity Problem?

**For SSC: Yes, about 80% of the problem is missing watershed types.**

Look at your training pool. Your 269 candidate sites come from 11 states:

| State | Candidate sites | Dominant landscape |
|-------|----------------|-------------------|
| California | 60 | Mediterranean, Sierra Nevada, Central Valley |
| Oregon | 40 | Pacific maritime, volcanic Cascades |
| Kansas | 33 | Great Plains, prairie |
| Virginia | 31 | Piedmont, Coastal Plain, Appalachian |
| Colorado | 27 | Rocky Mountain, high-altitude arid |
| Indiana | 22 | Midwest glacial till, agricultural |
| Maryland | 20 | Piedmont, Chesapeake tributaries |
| Montana | 14 | Northern Rockies, plains |
| Ohio | 12 | Glaciated Midwest |
| Idaho | 6 | Mountain West |
| Kentucky | 4 | Appalachian/Interior Low Plateau |

Now look at what is completely absent:

- **Loess belt** (Iowa, Nebraska, Missouri, Illinois, western Indiana) -- zero sites. This is a massive sediment-producing region with a fundamentally different turbidity-SSC relationship due to coarse silt particles. Your Iowa River failure (R-squared=-0.50) is 100% predictable from this gap.
- **Iron Range / Canadian Shield geology** (Minnesota, Wisconsin, Michigan Upper Peninsula) -- zero sites. The St. Louis River TP failure (R-squared=-0.54) maps directly to this.
- **Arid Southwest** (Arizona, New Mexico, Utah, West Texas) -- zero sites. The San Juan River catastrophe (R-squared=-8.13) is what happens when a model trained on humid-region SSC concentrations (typically 10-2,000 mg/L) encounters arid-regime concentrations (routinely 10,000-100,000+ mg/L during flash floods).
- **Gulf Coastal Plain** (Texas coast, Louisiana, Mississippi, Alabama, Florida) -- zero sites. The E Fork San Jacinto failure (R-squared=0.55 SSC, R-squared=-2.02 TP) reflects sandy coastal plain soils with low P-enrichment and heavy WWTP influence.
- **Southeast Piedmont/Coastal Plain** (Carolinas, Georgia interior, Florida) -- zero sites with the right characteristics. Your GA site performed OK for SSC (0.61) but failed for TP (-2.06).

These are not exotic landscapes. The loess belt alone accounts for roughly 15-20% of US agricultural land. The Gulf Coastal Plain covers Texas to Florida. The arid West covers a third of the continental US by area. You have built a model on humid-eastern, Pacific-maritime, and Great Plains sites and are surprised it fails outside those domains. You should not be surprised. This is exactly what the bias looks like.

**For TP: It is about 50% diversity and 50% missing information.**

Adding more sites will help TP at particulate-P-dominant locations in new geographies. But the dissolved-P failures (CT, FL) and the WWTP failures (TX) will NOT be fixed by more training sites alone, because the model lacks a feature that captures dissolved vs. particulate P fraction. Chen is right about this. More sites help, but they are not sufficient for TP the way they are for SSC.

---

## 2. If We Added 20-30 Sites Covering the Missing Regimes, Would the Model Learn Them?

**For SSC: Yes, with high confidence for most regimes. CatBoost can learn different turbidity-SSC slopes if you give it examples.**

Here is my reasoning. Your model already demonstrates it can learn regime-specific behavior:
- It handles glacial clay (NY, MN/ND: R-squared 0.90) differently from volcanic sediment (WA: R-squared 0.87) differently from iron-range mixed sediment (MN St. Louis: R-squared 0.79).
- The GAGES-II catchment attributes (clay_pct, sand_pct, geology class, ecoregion) give the model the information it needs to adjust the turbidity-SSC slope by site type.

So if you add 5 loess-belt sites, the model can learn "when silt_pct > 50% and clay_pct < 20% in an ecoregion tagged as Western Corn Belt Plains, the turbidity-SSC slope is steeper (more SSC per unit turbidity)." The information pathway exists. You just need the training examples.

**The one regime I am less confident about: arid extreme-SSC.** The San Juan River regularly carries SSC above 50,000 mg/L. Your training distribution probably tops out around 5,000-10,000 mg/L. CatBoost, like all tree-based models, cannot extrapolate beyond its training range. You would need arid-regime sites in the training set, AND those sites would need to include high-concentration events. If the USGS sites in Arizona and New Mexico only have grab samples from baseflow conditions, the model still will not learn the extreme-event behavior. You need sites with event sampling.

**For TP at new regimes (not dissolved-P): Yes.** Iron-range sites have anomalous P-enrichment ratios. If you add 3-4 iron-range sites, the model can learn that iron-bearing geology means more P per unit turbidity. The GAGES-II geology classification should capture this if it distinguishes iron formations, though you should verify the coding.

**For TP at dissolved-P or WWTP sites: No, not from more sites alone.** You need a new feature (conductance-turbidity ratio, urban land use fraction, NPDES discharge density) to give the model information about the dissolved P pathway. More sites will improve the model's ability to recognize "I should not try to predict TP here," but they will not make the predictions accurate.

---

## 3. How Many Sites Do We Need? Is There a Sweet Spot?

This is the practical question. Here is how I think about it.

**The USGS operates roughly 9,000 streamgages, of which maybe 1,500-2,000 have continuous turbidity sensors, and of those maybe 400-600 have co-located discrete SSC data adequate for surrogate regression.** Song et al. (2024) used 377 training sites and achieved median R-squared=0.55 without turbidity. You used 57 with turbidity and got R-squared=0.79.

The issue is not the total number of sites -- it is the coverage of distinct watershed types. I would frame it as a stratified sampling problem.

### Major US Watershed Types for SSC Modeling

Here are the regimes I would want represented, with a minimum site count for each:

| Regime | Example states | Current coverage | Sites needed |
|--------|---------------|-----------------|-------------|
| Glacial clay / till | OH, IN, NY, MN, WI | Good (OH, IN, NY in training) | 0 new |
| Great Plains prairie | KS | Good (33 candidates) | 0 new |
| Pacific maritime | OR, WA | Good (40 candidates) | 0 new |
| Mediterranean California | CA | Good (60 candidates) | 0 new |
| Rocky Mountain | CO, MT, ID | Good (47 candidates) | 0 new |
| Appalachian/Piedmont | VA, MD, KY | Good (55 candidates) | 0 new |
| **Loess belt** | IA, NE, MO, IL | **Zero** | **4-6** |
| **Iron Range / Canadian Shield** | MN (Mesabi), WI, MI UP | **Zero** | **2-3** |
| **Arid Southwest** | AZ, NM, UT, W. TX | **Zero** | **4-5** |
| **Gulf Coastal Plain** | TX coast, LA, MS, AL, FL | **Zero** | **4-5** |
| **Southeast Piedmont** | NC, SC, GA | **Minimal (1 GA site)** | **2-3** |
| **Glaciolacustrine / Red River type** | MN/ND, MB | **Zero in training** | **2-3** |
| **WWTP-influenced urban** | Any suburban reach | **Unknown** | **3-4** |
| **Karst / carbonate** | central TX, KY, TN, FL | **Maybe KY?** | **2-3** |

**Total new sites needed: approximately 23-32.**

So your estimate of 20-30 is right in the range. That would bring you to roughly 80-90 training sites, which I think is the sweet spot for this problem. Here is why:

- **Diminishing returns set in around 100-150 sites** for CatBoost on tabular data with ~25-50 features. You are fitting maybe 500-1,000 trees, and each split needs to see enough variation in the feature space. With 80-90 sites covering 12-14 distinct regimes and 3-5 sites per regime, you have enough for the model to learn regime-specific behavior through the catchment attributes.
- **Going beyond 150 sites does not help much** unless you are also adding new feature types. Song et al. used 377 sites without turbidity. You could match their site count, but you would be adding diminishing-value sites in already-covered regimes. Better to add 30 well-chosen sites than 300 random ones.
- **The practical constraint is discrete sample availability**, not site count. Each new site needs at least 50-100 paired turbidity-SSC samples to be useful for training. Many USGS sites with turbidity sensors have fewer than 30 discrete SSC samples. You will likely screen 100+ candidate sites to find 25-30 with adequate data.

---

## 4. Is the Current Training Set Overrepresented in Certain Regions?

**Yes. Badly.**

From your 269-site candidate pool:
- California: 60 sites (22%)
- Oregon: 40 sites (15%)
- Kansas: 33 sites (12%)

These three states account for nearly half your candidate pool. Even after filtering to 57 training sites, I would guess California, Oregon, and Kansas still contribute 25-30 of those 57 sites. That means the model has seen dozens of Central Valley agricultural sites, dozens of Cascade/Coast Range forest sites, and dozens of Great Plains prairie sites -- but zero loess, zero arid, zero Gulf Coast, zero iron range.

**This is the classic USGS monitoring bias.** California, Oregon, and Kansas have aggressive state water quality monitoring programs that co-fund USGS turbidity networks. The USGS Sediment Data Program historically concentrated monitoring in the Pacific Northwest and the High Plains. Virginia and Maryland are well-represented because of the Chesapeake Bay Program, which funded intensive tributary monitoring. Indiana and Ohio are covered because of Great Lakes tributary monitoring.

States without strong co-funding partnerships with USGS -- Louisiana, Mississippi, Alabama, Arizona, New Mexico -- have fewer turbidity-equipped sites with adequate discrete sampling. This is not a scientific decision about where monitoring is needed; it is a budget artifact.

**The overrepresentation matters for the model.** CatBoost builds trees by finding splits that reduce loss across the training data. If 40% of your training samples come from Pacific/Mediterranean sites, the tree structure will be optimized for those conditions. The model can still learn other regimes from catchment attributes, but it will invest fewer splits (less model capacity) on regimes with fewer training examples. Adding 25-30 sites from underrepresented regimes will rebalance this.

**One specific concern about California overrepresentation:** Many of your California sites appear to be in the Sacramento-San Joaquin Delta system (the 114xx series site numbers). These sites share hydrology, sediment sources, and water management operations. Having 15-20 sites from the same watershed system inflates site count without adding independent information. For training purposes, the Sacramento-San Joaquin Delta sites function more like 3-4 independent "super-sites" than 15-20 independent observations. Be aware of this when interpreting LOGO CV results -- leaving out one Delta site still leaves 14 similar sites in training, which defeats the purpose of leave-one-out.

---

## 5. Most Efficient Strategy: Targeted Gap-Filling vs. Wide Net

**Targeted gap-filling, no question.** Here is my specific priority list.

### Priority 1: Loess Belt (Highest Impact, Easiest to Find)

**Why:** The Iowa River failure is your most scientifically interesting result and your most fixable gap. Loess belt sites have a well-documented, physically understood departure from the clay-dominated turbidity-SSC relationship. Adding these sites would (a) fix the model's worst SSC failure mode, and (b) give you a publishable story about how the model learns grain-size-dependent turbidity-SSC slopes.

**Where to look:**
- **Iowa:** USGS-05420500 (Mississippi at Clinton), USGS-05454500 (Iowa River at Iowa City -- your test site, now add it to training), USGS-06610000 (Missouri River at Omaha area sites)
- **Nebraska:** USGS-06805500 (Platte River at Louisville), USGS-06803555 (Salt Creek)
- **Missouri:** USGS-06934500 (Missouri River at Hermann)
- **Illinois:** USGS-05586100 (Illinois River at Valley City)

Target: 5-6 sites. The USGS Central Midwest Water Science Center (Iowa/Missouri) and the Nebraska Water Science Center have invested heavily in turbidity monitoring since ~2010. Several sites should have 100+ paired samples.

### Priority 2: Gulf Coastal Plain (Second Highest Impact)

**Why:** The Gulf Coast represents a huge geography (TX to FL) with fundamentally different sediment -- sandy, low P-enrichment, high organic content, WWTP-influenced. Your model has zero exposure to this.

**Where to look:**
- **Texas:** USGS-08068500 (Spring Creek at Spring, TX -- Houston suburban), USGS-08068090 (W Fork San Jacinto), USGS-08116650 (Brazos River tributaries)
- **Louisiana:** USGS-07381495 (Atchafalaya at Butte La Rose -- if they have turbidity)
- **Florida:** USGS-02296750 (Peace River at Arcadia -- phosphate mining influence), USGS-02292900 (Caloosahatchee -- your test site)
- **South Carolina:** USGS-02169500 (Congaree River at Columbia)

Target: 4-5 sites. Florida and Texas have good WQ monitoring. Louisiana is harder because few sites have continuous turbidity.

### Priority 3: Arid Southwest (High Scientific Value, Hard to Find Data)

**Why:** The arid West is a third of the US by area. Your model currently cannot say anything about it.

**Where to look:**
- **Arizona:** USGS-09402500 (Colorado River at Lees Ferry), USGS-09380000 (Colorado River at Grand Canyon -- very long SSC record but check for turbidity), USGS-09498500 (Salt River near Roosevelt)
- **New Mexico:** USGS-08313000 (Rio Grande at Otowi Bridge -- extremely well-monitored)
- **Utah:** USGS-09315000 (Green River at Green River, UT)

Target: 3-4 sites. **WARNING:** Arid sites often have short turbidity records (sensors installed recently) and sparse discrete sampling (remote locations, dangerous access during flash floods). You may find only 1-2 sites with adequate data. If so, treat them as external validation rather than training sites -- a 2-site regime is too thin for reliable training.

### Priority 4: Iron Range / Canadian Shield (Targeted TP Fix)

**Why:** Specifically to fix the St. Louis River TP failure and improve TP performance in mining-influenced geochemistry.

**Where to look:**
- **Minnesota:** USGS-04024000 (St. Louis River -- your test site), USGS-04010500 (Pigeon River), any Vermilion Range or Mesabi Range tributaries with turbidity
- **Wisconsin:** USGS-04025500 (Bois Brule River)
- **Michigan:** Upper Peninsula sites near Marquette Range

Target: 2-3 sites. These will be harder to find because iron-range monitoring often lacks continuous turbidity. The Minnesota Pollution Control Agency may have state-operated turbidity data that supplements the USGS network.

### Priority 5: Karst / Carbonate (Addresses a Blind Spot)

**Why:** Karst systems have unique turbidity behavior -- spring-fed streams can go from clear to turbid in hours during recharge events, and the turbidity-SSC relationship is driven by conduit flushing, not surface erosion.

**Where to look:**
- **Central Texas:** USGS-08170500 (San Marcos River -- spring-fed, constant flow but variable WQ)
- **Kentucky/Tennessee:** USGS-03290500 (you have KY sites; check if any are karst)
- **Florida:** USGS springs monitoring (Ichetucknee, Silver Springs)

Target: 2-3 sites. Low priority because karst may be genuinely outside the model's applicability domain (turbidity is not the right predictor in spring-fed systems). But worth having 1-2 sites to train the model to recognize "this is karst, I should have low confidence."

---

## 6. Practical Workflow for Site Selection

Here is what I would actually do, step by step:

1. **Query USGS NWIS for all sites with continuous turbidity (63680) in the target states.** Use `waterdata.get_time_series_metadata(parameter_code="63680", state_name="Iowa")` and repeat for Nebraska, Missouri, Illinois, Texas, Louisiana, Florida, South Carolina, Arizona, New Mexico, Utah, Minnesota, Wisconsin.

2. **For each site with turbidity, check for discrete SSC (80154) availability.** Count samples. Require n >= 50, ideally n >= 100.

3. **For TP expansion, also check discrete TP (00665) and orthoP (00671).** The orthoP/TP ratio at each candidate site tells you whether it is a particulate-P or dissolved-P site before you download anything.

4. **Cross-reference against GAGES-II.** If a candidate site is not in GAGES-II, you lose the catchment attributes. Since your Tier C model (with GAGES-II) outperforms Tier A and B, you want sites with GAGES-II coverage.

5. **Rank candidates by: (a) regime gap filled, (b) sample count, (c) GAGES-II availability.**

6. **Download the top 25-30 sites** and add them to training.

This is maybe 2-3 hours of scripting time using the dataretrieval API you already know, plus a day of data QC.

---

## 7. One More Thing: Sample Weighting After Expansion

Once you add 25-30 sites from new regimes, you will have an imbalanced training set: ~57 sites from the original 11 states, ~25-30 from new states. The original sites have more samples per site (many have 500-2,000+). The new sites may have 50-200 samples each.

**Do not let sample count dominate training.** If California contributes 15 sites with 1,000 samples each (15,000 samples) and the loess belt contributes 5 sites with 100 samples each (500 samples), CatBoost will optimize for California. Two options:

- **Sample weighting by site:** Give each site equal total weight, regardless of sample count. A site with 1,000 samples gets weight 1/1000 per sample; a site with 100 samples gets weight 1/100 per sample. CatBoost supports `sample_weight`.
- **Subsample to equalize:** Cap each site at N samples (e.g., 200-300), randomly sampled. Simpler, slight information loss from large sites.

I would recommend sample weighting. It preserves the event-sampling richness at well-monitored sites while preventing geographic overfit.

---

## Summary

| Question | Answer |
|----------|--------|
| Is this a training diversity problem? | For SSC: ~80% yes. For TP: ~50% yes, 50% missing features. |
| Would 20-30 targeted sites fix it? | For SSC in missing regimes: high confidence yes. For TP: partially. |
| How many total sites is the sweet spot? | 80-90 well-distributed sites (current 57 + 25-30 new). |
| Is the training set overrepresented? | Yes. CA, OR, KS together are ~50% of candidates. Sacramento Delta sites are correlated. |
| Targeted or wide net? | Targeted. Prioritize loess belt > Gulf Coast > arid West > iron range > karst. |
| Biggest practical risk? | Finding adequate data at arid and iron-range sites. Turbidity sensors are sparse there. |

Your instinct was right, Kaleb. The "weird outliers" are not weird at all -- they are common US watershed types that your training set happens to miss because of USGS monitoring network funding patterns. Add 25-30 well-chosen sites and I expect the SSC applicability domain expands from "humid East and Pacific states" to "most of CONUS except extreme arid." That is a much more compelling product and a much stronger paper.

One caveat: do the site selection and data download BEFORE retraining anything. Understand what data exists first. Some of these target regimes may not have adequate paired data, and you will need to adjust your priorities accordingly.

---

*Dr. Marcus Rivera, USGS (ret.)*
*20 years Water Resources Division -- sediment transport, water quality monitoring, surrogate regression development*
*Reviewing: murkml training diversity and site expansion strategy, 2026-03-17*
