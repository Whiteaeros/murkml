# NTU Integration Plan Review -- USGS Sensor Operations Assessment
**Reviewer:** Dr. Marcus Rivera, USGS Water Resources Division (ret.), 20 years
**Date:** 2026-03-30
**Materials reviewed:** `ntu-integration-plan.md` (Phase 7), `PHASE4_OBSERVATIONS.md` (external validation results), `validate_external.py`, prior Rivera reviews (external validation, expansion plan)
**Scope:** Operational viability of the parallel FNU/NTU column architecture, dual-sensor site overlap expectations, NTU data quality, geographic distribution, and missed risks

---

## 1. Is the Parallel FNU/NTU Column Approach Sound?

**Yes. This is the correct architecture. It is superior to every alternative I can think of.**

Let me explain why by walking through what the alternatives are and why they fail.

**Alternative A: Categorical flag (sensor_type = "FNU" or "NTU").** This was the earlier idea noted in PHASE4_OBSERVATIONS.md. The problem is that it creates duplicate row structures and forces the model to learn a global FNU-NTU offset, which does not exist. The FNU-NTU divergence depends on particle characteristics -- color, shape, size distribution, organic content -- all of which vary by site and by event. A single categorical flag cannot capture this. CatBoost would try to learn an average offset, which would be wrong everywhere.

**Alternative B: Convert NTU to FNU using a regression.** This is what most published studies do, and it is wrong for cross-site work. Every NTU-to-FNU conversion equation I have seen in the literature (Anderson 2005, Rasmussen et al. 2009 appendix) was derived at specific sites with specific water chemistry. There is no universal NTU-to-FNU conversion. Applying a site-specific conversion to a cross-site model introduces systematic error that varies by geology and sediment type -- exactly the kind of error that CatBoost cannot diagnose or correct.

**Alternative C: Parallel columns with NaN.** This is what the plan proposes, and it is correct because:

1. At dual-sensor sites, CatBoost sees both readings simultaneously and learns the site-conditioned relationship between FNU and NTU as a function of watershed attributes. This is the conversion equation, but learned from the data, conditioned on geology and land use. That is fundamentally better than any static regression.

2. At single-sensor sites, the missing column is NaN, and CatBoost routes through whichever branch has data. No imputation, no synthetic values, no information leakage.

3. At inference time, the user provides whichever measurement they have. This is operationally clean -- no conversion step, no lookup table, no assumptions about the user's sensor.

**One operational concern:** The column renaming from `turbidity_instant` to `turbidity_instant_fnu` is a breaking change that touches every script, the drop list, monotone constraints, meta.json, and any saved model artifacts. The plan acknowledges this but underestimates the blast radius. Every downstream consumer of the model -- any inference script, any API endpoint, any notebook that loads model predictions -- will break if it expects `turbidity_instant`. I would recommend adding a compatibility shim or alias layer rather than a hard rename, at least during the transition. Version the feature schema (v9 = old names, v10 = new names) and have the inference code detect which schema it is working with.

---

## 2. The 89 Dual-Sensor Sites: How Much Temporal Overlap?

**This is the most important uncertainty in the entire plan, and the plan correctly flags it in the risks section but does not quantify it. Let me give you my best estimate from 20 years of watching USGS sensor deployments.**

### The USGS NTU-to-FNU transition history

The USGS began transitioning from NTU (white-light nephelometry, typically Hach 2100 or similar bench/field instruments) to FNU (infrared nephelometry, typically YSI EXO or Hydrolab DS5) as the standard for continuous in-situ monitoring starting around 2004-2007, accelerating after the publication of USGS Techniques and Methods 1-D3 (Anderson 2005, updated Wagner et al. 2006). By 2010-2012, most new continuous turbidity deployments were FNU. By 2015, NTU continuous sensors were being phased out at the majority of active supergages.

This means the typical deployment history at a dual-sensor site looks like one of three patterns:

**Pattern A: Sequential replacement (most common, ~60-70% of dual-sensor sites).** The site had an NTU continuous sensor from roughly 2002-2010, which was replaced by an FNU sensor from 2010 onward. There may be a brief overlap period of weeks to months during the transition when both sensors were deployed for comparison purposes. These sites will have minimal true concurrent data -- maybe a few hundred paired 15-minute readings during the overlap window, but in your SSC-paired dataset, the number of SSC grab samples that fall within that narrow overlap window will be tiny. Possibly zero at many sites. Possibly 1-5 at others.

**Pattern B: Extended co-deployment for research purposes (~15-20%).** Some USGS Water Science Centers, particularly in Kansas (the Rasmussen group was very thorough about this), Oregon, and Minnesota, ran parallel NTU and FNU sensors for 1-3 years specifically to develop local conversion equations. These sites will have substantial overlap, potentially hundreds of concurrent readings, and a reasonable number of SSC grab samples with both turbidity readings available. These are the gold mines for Phase 7A.

**Pattern C: NTU bench measurement alongside FNU continuous (~15-20%).** At some sites, the "NTU" record in NWIS is not from a continuous in-situ sensor but from periodic bench-top measurements (Hach 2100P or similar) taken during site visits. These are discrete measurements, not continuous records, and they will appear as pCode 00076 in NWIS but with a different time-series type code (not "uv"). If you are querying for continuous ("uv") NTU data, you should not encounter these, but verify that you are filtering correctly. If bench NTU data leaks in, you will have sporadic NTU readings (monthly frequency) rather than 15-minute data, and the 1-hr window stats will be meaningless.

### My estimate for the 89 sites

Of the 89 dual-sensor sites:
- **~55-60 sites** will have sequential NTU-then-FNU deployment with minimal overlap. At these sites, you will get NTU-only SSC pairs from the pre-FNU era and FNU-only SSC pairs from the post-FNU era, but very few (0-5) SSC samples with both columns populated.
- **~15-18 sites** will have meaningful concurrent deployment (Pattern B), giving you 10-50 SSC samples with both FNU and NTU populated.
- **~12-16 sites** may be Pattern C or other edge cases that need manual review.

**The practical consequence:** The plan assumes dual-sensor sites will teach CatBoost the FNU-NTU relationship "conditioned on watershed/geology features." This learning requires rows where BOTH columns are populated. If only 15-18 sites have substantial concurrent data, and each has 10-50 relevant SSC samples, you are looking at maybe 150-900 rows with both columns filled -- out of your total training set of thousands. That is enough for CatBoost to learn something, but the FNU-NTU relationship will be learned from a narrow slice of your training data, concentrated in a few states (Kansas, Oregon, Minnesota most likely).

**What to do about this:** Before downloading anything, run a quick query for each of the 89 sites to determine the period of record for pCode 00076 (NTU continuous) and pCode 63680 (FNU continuous). Compute the overlap in days. Any site with less than 90 days of overlap is Pattern A and will contribute almost no concurrent rows. This triage step takes an hour and will tell you exactly how much dual-sensor data you actually have.

### Step 4 is where the real value lies

The plan's Step 4 -- finding NTU-only SSC samples at the dual-sensor sites from the pre-FNU era -- is actually the most valuable part of Phase 7A. At the ~55-60 Pattern A sites, you will not get concurrent data, but you WILL get SSC grab samples from the NTU era that were never usable before. These are new training rows with NTU populated and FNU = NaN. They expand your training set, add temporal diversity (older samples, different flow conditions), and teach the model to predict SSC from NTU at sites where it already knows the watershed characteristics from FNU-era data. This is clever and I endorse it strongly.

---

## 3. NTU Data Quality vs. FNU

This is an area where 20 years of field experience gives me a lot to say. The short version: NTU data is noisier, has more artifacts, and has specific failure modes that FNU data does not.

### Sensor physics differences

**NTU (white-light nephelometry, ISO 7027 notwithstanding):** Uses a broadband white-light source (tungsten lamp) and measures scattered light at 90 degrees. The white-light spectrum interacts with particle color, meaning that dark-colored particles (organic matter, iron-stained clay, dark volcanic sediment) produce a weaker scattering signal per unit mass than light-colored particles. This introduces a particle-color bias that varies by geology.

**FNU (infrared nephelometry, ISO 7027 compliant):** Uses a near-infrared LED (~860 nm) and measures at 90 degrees. At this wavelength, particle color has much less effect on scattering intensity, so FNU is closer to a "pure" particle-concentration measurement. This is why the USGS standardized on FNU -- it is more physically interpretable.

### Specific quality issues to expect with NTU data

1. **Biofouling and lamp degradation.** White-light sources degrade over time (tungsten lamp aging), causing a slow downward drift in readings. The USGS QC protocol requires lamp checks, but older NTU records (pre-2010) were less rigorously maintained. FNU sensors with LED sources are more stable. Expect more baseline drift in NTU records, especially in warm-water systems where biofouling is aggressive.

2. **Color interference.** At sites with high dissolved organic carbon (DOC) -- wetland-influenced streams, blackwater rivers in the Southeast, tannin-stained waters -- NTU readings will be elevated relative to the true particle concentration because dissolved color absorbs and scatters white light. FNU at 860 nm is nearly immune to this. If you add NTU-only sites from the Southeast or Upper Midwest (wetland-influenced), the NTU readings will carry a DOC signal that the model may incorrectly learn as "sediment." This is a real risk of model confusion.

3. **Dynamic range and saturation.** Older NTU sensors (especially bench-top units deployed in continuous mode) had lower dynamic ranges than modern FNU sensors. Saturation was common above 1000-1500 NTU. The plan's existing observation that "NTU and FNU diverge above ~400" is partly a saturation artifact, partly a genuine optical physics difference. For SSC prediction, saturation means the highest-SSC events (floods) will have clipped NTU readings while FNU records the true turbidity signal. The model needs to understand that a NTU reading of 1200 might mean 1200 or might mean "1200+, sensor saturated."

4. **Reporting units confusion.** Some NWIS records store NTU data under pCode 00076, but the actual measurement may be NTRU (nephelometric turbidity ratio units) or JTU (Jackson turbidity units) from very old records. NWIS has had unit standardization issues with turbidity. For records pre-2005, verify the method code in the NWIS metadata to confirm the measurement is actually nephelometric NTU and not something else.

5. **Approval status.** USGS data goes through a review process: provisional (P), approved (A), or estimated (E). Older NTU continuous records may have long stretches of provisional or estimated data that never went through the full quality-assurance process described in Wagner et al. (2006). FNU records from the 2012+ era generally have better QA status because the protocols were more mature. Filter for approval status or at minimum flag it.

### Recommendation

Add a data quality screen for NTU records before integration:
- Require approval status "A" where available
- Flag records with extended flatlines (>24 hrs at identical value = probable sensor failure)
- Flag records where NTU > 1000 continuously for >1 hr (probable saturation)
- For the dual-sensor overlap periods, compute FNU/NTU ratios and flag any site where the ratio is not reasonably stable (coefficient of variation > 0.5 across events) -- this suggests the NTU sensor was malfunctioning

---

## 4. NTU-Only Sites: Geographic Concentration

This is where my knowledge of the USGS network is directly relevant. The question is: where did USGS operate NTU continuous sensors but never upgrade to FNU? And where do non-USGS organizations still use NTU?

### USGS NTU-only sites

Sites that had NTU but were never upgraded to FNU typically fall into two categories:

1. **Sites that were decommissioned before the FNU transition.** Budget cuts, particularly in the 2008-2013 sequestration era, forced many Water Science Centers to reduce monitoring networks. Sites that were operating NTU sensors and got cut never received FNU upgrades. These are concentrated in:
   - **HUC2 Region 05 (Ohio River basin):** Ohio, Indiana, West Virginia had extensive NTU networks in the 2000s that were thinned significantly. Many Ohio River tributary sites have NTU records from 2002-2008 and nothing after.
   - **HUC2 Region 07 (Upper Mississippi):** Iowa, Minnesota, Wisconsin had NTU sites on smaller tributaries that were consolidated into fewer, better-instrumented FNU supergages on mainstem rivers.
   - **HUC2 Region 10 (Missouri):** Kansas, Nebraska, South Dakota had NTU monitoring on agricultural streams that was partially discontinued.
   - **HUC2 Region 03 (South Atlantic-Gulf):** Georgia, Alabama, Florida had NTU monitoring for some coastal plain streams that was reduced.

2. **Cooperative-funded sites where the cooperator did not fund the upgrade.** Many USGS continuous water quality sites are jointly funded by state agencies, municipalities, or water utilities. If the cooperator's needs were met by NTU and they did not fund an FNU upgrade, the site either stayed on NTU or was discontinued. These are scattered but tend to concentrate in states with smaller USGS programs.

### Non-USGS NTU sources (the big opportunity)

Your external validation already identified the major players:
- **UMRR LTRM (Upper Mississippi River Restoration Long-Term Resource Monitoring):** 133 sites across the Upper Mississippi main stem and major tributaries. This is **HUC2 Region 07** primarily, extending into Region 05 and 10. These are NTU grab samples, not continuous, but they represent the largest single non-USGS NTU dataset you have access to.
- **SRBC (Susquehanna River Basin Commission):** Concentrated in **HUC2 Region 02 (Mid-Atlantic)**, covering Pennsylvania and New York tributaries to the Chesapeake Bay.
- **State agency monitoring networks:** Many state environmental agencies (state DEQs, state geological surveys) still use NTU for routine monitoring. These would add sites in virtually every HUC2 region, but data quality and sampling protocols vary enormously.

### Where would USGS NTU-only sites fill gaps in your current training set?

Cross-referencing with the expansion plan I co-authored on 2026-03-17:

| HUC2 | Region | NTU-Only Sites Likely? | Fills a Gap? |
|-------|--------|----------------------|--------------|
| 02 | Mid-Atlantic | Yes (SRBC, PA DEP) | Moderate -- you have some NY/PA FNU sites already |
| 03 | South Atlantic-Gulf | Yes (old USGS, state agencies) | **High** -- you are thin on Southeast Piedmont and Coastal Plain |
| 05 | Ohio River | Yes (old USGS 2002-2010) | **High** -- you have very few Ohio basin sites |
| 07 | Upper Mississippi | Yes (UMRR, old USGS) | **High** -- loess belt is your biggest regime gap |
| 10 | Missouri | Yes (old USGS) | **High** -- you need Great Plains representation |
| 11 | Arkansas-Red-White | Moderate | **High** -- essentially no coverage currently |
| 12 | Texas-Gulf | Moderate (state data) | **High** -- Gulf Coastal Plain is underrepresented |

The bottom line: NTU-only USGS sites are most concentrated in HUC2 regions 05, 07, and 10 -- which happen to be exactly the regions where your expansion plan identified the biggest training gaps (Ohio River basin, Upper Mississippi/loess belt, Missouri basin). This is not coincidental. These regions had active USGS turbidity programs in the 2000s that were cut before the FNU transition. Recovering their NTU data is a way to fill geographic gaps that FNU-only expansion cannot fill.

---

## 5. Risks the Plan Misses

The plan's risk section is good but misses several operational and scientific risks that I would flag.

### Risk 1: The NTU "approximately equals FNU below 400" assumption is geology-dependent

The plan and the external validation both use 400 NTU/FNU as a threshold for comparability. This comes from the general literature (Anderson 2005, various manufacturer specs). But in my experience, the divergence threshold varies significantly by water type:

- **Clean clay suspensions:** NTU and FNU track closely up to 800-1000 units. The divergence is gradual.
- **Organic-rich waters (high DOC, wetland-influenced):** NTU exceeds FNU by 15-30% even at readings below 100, because white light scatters off dissolved color. The 400 threshold is too generous for these waters.
- **Dark volcanic or iron-stained sediments:** NTU reads LOWER than FNU at the same particle concentration because dark particles absorb white light. The divergence can begin below 200.

By using parallel columns rather than a conversion, you avoid this problem at dual-sensor sites. But at NTU-only sites where the model has never seen the local FNU signal, the model is learning the NTU-SSC relationship in isolation. If the NTU reading at a blackwater site is inflated by DOC, the model will learn a shallower NTU-SSC slope for that site than the true particle-based relationship. This is not catastrophic -- the model can learn different slopes for different site types -- but it means the NTU-side monotone constraint should be applied cautiously. At organic-rich sites, higher NTU does not always mean more sediment.

### Risk 2: Temporal bias from the NTU era vs. the FNU era

NTU records are predominantly from 2000-2012. FNU records are predominantly from 2010-present. These two eras have different hydrologic characteristics:

- The 2000-2012 period includes the extreme drought of 2000-2003 in the West and Southeast, and the 2008 flood season in the Upper Midwest.
- The 2012-present period includes the 2012 drought, the 2016-2019 wet period in the Upper Midwest, and increasing precipitation intensity linked to climate trends.

If NTU-only sites contribute training data exclusively from the earlier period, and FNU sites contribute data from the later period, the model may conflate sensor type with climatic conditions. At dual-sensor Pattern A sites (sequential replacement), this conflation is direct: the same site has NTU data from dry years and FNU data from wet years. The model could attribute the SSC differences to the sensor type rather than to the different hydrologic conditions.

**Mitigation:** For dual-sensor sites, compare the discharge distributions during the NTU era vs. the FNU era. If they are significantly different (Kolmogorov-Smirnov test on log-Q), flag the site. This does not mean you exclude it, but it means you should not rely heavily on those sites for learning the FNU-NTU relationship.

### Risk 3: Phase 7C external NTU data lacks continuous records

The plan acknowledges this: external NTU sites (UMRR, SRBC, etc.) have grab-sample turbidity only, meaning `turbidity_instant_ntu` is populated but the 1-hr window stats (`turbidity_max_1hr_ntu`, `turbidity_std_1hr_ntu`) are NaN. This makes those rows less informative than USGS continuous-sensor rows.

The risk I would flag more strongly: **these rows are structurally different from every other row in the training set.** USGS rows have either FNU window stats or NTU window stats populated. External NTU rows have neither. CatBoost may learn to treat external-NTU rows as a distinct subpopulation and develop prediction branches that overfit to their characteristics (which include the systematic biases of each external organization's sampling protocols, sample handling, and turbidity measurement methods). The UMC +500% bias is the extreme example, but subtler biases exist in every external dataset.

**Recommendation:** Add Phase 7C data last, after 7A and 7B are validated. If 7A+7B solve the NTU bias problem adequately, you may not need 7C for training at all -- keep it purely as external validation data. Adding messy external data to training is a last resort, not a default.

### Risk 4: Monotone constraint complications

The plan mentions that monotone constraints can apply independently to FNU and NTU. True, but there is a subtlety. Currently, `turbidity_instant` has a monotone increasing constraint (more turbidity = more SSC, always). When you split into two columns:

- `turbidity_instant_fnu` should get monotone increasing. Correct.
- `turbidity_instant_ntu` should get monotone increasing. Also correct.

But what about the window stats? `turbidity_max_1hr_fnu` and `turbidity_max_1hr_ntu` should also be monotone increasing. `turbidity_std_1hr_fnu` and `turbidity_std_1hr_ntu` -- these are trickier. Higher turbidity variability within an hour suggests a changing sediment regime (rising or falling limb), which could correlate with either higher or lower SSC depending on the hysteresis direction. Are the current std features monotone-constrained? If so, doubling them for both sensor types doubles the constraint set, and any error in the constraint direction is now applied to both sensor pathways.

### Risk 5: Model complexity and overfitting with sparse dual-sensor data

You are adding 6 new features (3 NTU columns) to a model that already has a carefully tuned feature set. As I estimated above, the number of rows with both FNU and NTU populated will be small (150-900). CatBoost will see the NTU columns as "mostly NaN" features and may not invest much tree depth in learning from them unless you tune the per-feature missing-value handling. There is a risk that the NTU columns become low-importance features that add noise without improving predictions, while the model's effective capacity is diluted.

**Recommendation:** After Phase 7A training, run a feature importance analysis on the 6 turbidity columns. If the NTU columns have near-zero importance, that tells you the model is not learning from them and you need more dual-sensor training data (i.e., go directly to 7B before concluding 7A worked).

---

## 6. What I Would Do Differently

### Change 1: Triage the 89 sites before downloading anything

Run the period-of-record overlap query I described in Section 2. Classify each site as Pattern A (sequential), Pattern B (concurrent), or Pattern C (bench NTU). This takes one scripted query and an hour of processing. It tells you:
- How many sites have true concurrent data (Pattern B) -- these are the sites that teach the FNU-NTU relationship
- How many sites have sequential data (Pattern A) -- these contribute NTU-only rows via Step 4
- How many are Pattern C edge cases that need manual review

This triage determines whether Phase 7A can actually learn the FNU-NTU relationship or whether it is effectively just "add NTU-only rows to training."

### Change 2: Start with a diagnostic experiment, not a full integration

Before committing to the full pipeline changes (column renaming, infrastructure updates, etc.), run a minimal experiment:
- Take the 15-18 Pattern B sites with concurrent data
- Download their NTU records
- For SSC samples at those sites that have both FNU and NTU within 15 minutes, compute the FNU/NTU ratio
- Plot FNU/NTU ratio against: SSC, particle size proxy (if available), clay_pct, DOC proxy, geology type
- Determine whether the FNU-NTU relationship at these sites is learnable from watershed attributes

If the FNU/NTU ratio is random noise with no predictable pattern, then the parallel-column approach will not work as intended and you should consider a simpler approach (just add NTU-only rows and let the model learn NTU-SSC directly, without trying to bridge to FNU). If the ratio IS predictable from watershed features, then the full parallel-column plan is justified.

### Change 3: Separate the "add NTU-only training rows" goal from the "learn FNU-NTU conversion" goal

The plan conflates two distinct goals:
1. **Expand the training set** with NTU-only rows (FNU = NaN, NTU = populated). This is straightforward and low-risk.
2. **Teach the model the FNU-NTU relationship** via dual-sensor concurrent rows. This is ambitious and depends on having enough concurrent data.

Goal 1 is almost certainly achievable and valuable. Goal 2 is uncertain. I would pursue them as separate experiments and evaluate each independently.

### Change 4: Quality-gate the external NTU data much more aggressively

The UMC +500% bias is disqualifying for training. But even the SRBC and UMRR data need scrutiny:
- What turbidimeters did they use? (Hach 2100P, 2100Q, LaMotte? Each has different optical geometry.)
- What was their sample handling protocol? (Time from collection to measurement matters -- particles settle.)
- Were calibration records available?

For training data, I hold external organizations to the same standard I would hold a USGS cooperator: documented methods, traceable calibration, and defensible QC. If you cannot verify these for an external organization, use their data for validation only, not training.

### Change 5: Protect the external validation dataset

This is critical and the plan partially addresses it, but I want to emphasize it. The 11K external NTU samples from 260 sites are currently your only independent NTU validation dataset. The moment you put any of them into training, you lose that independence. Before moving ANY external site from validation to training, ensure you have a sealed NTU vault (the plan's ~20 USGS NTU-only sites) that has never been touched. And keep at least one full external organization (I would suggest UMRR, since it is the largest and best-documented) entirely out of training as a cross-organization validation check.

---

## Summary Assessment

The parallel FNU/NTU column architecture is the right design. It is scientifically sound and operationally clean. The phased approach is well structured. The data bleed prevention is adequate.

The main concern is the gap between what the plan assumes and what the dual-sensor data will actually deliver. The plan envisions CatBoost learning the FNU-NTU relationship from dual-sensor sites, but my experience suggests only 15-20 of the 89 sites will have meaningful concurrent data. The plan should be restructured around what will actually be available: primarily NTU-only training rows from the pre-FNU era (Step 4), with a smaller concurrent-data component.

The NTU data quality issues (color interference, lamp drift, saturation, reporting unit confusion) are real and need explicit QC screens before integration. The geographic payoff is excellent -- NTU-only sites fill exactly the regions where FNU expansion is hardest (Ohio basin, Upper Mississippi, Missouri basin, HUC2 regions 05/07/10).

The plan is executable and should proceed, with the triage and diagnostic steps I recommend as prerequisites before the full infrastructure changes.

---

*Dr. Marcus Rivera, USGS Water Resources Division (ret.)*
*20 years -- sediment transport, continuous water quality monitoring, surrogate regression development*
*Reviewing: Phase 7 NTU Integration Plan, 2026-03-30*
