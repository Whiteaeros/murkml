# Patel -- Phase 2 Data Download Review

**Reviewer:** Ravi Patel (Critical Reviewer / Research Software Engineer)
**Date:** 2026-03-16
**Materials reviewed:** Phase 2 download logs, scripts (`scan_parameters.py`, `download_discrete_params.py`, `analyze_new_params.py`, `download_gagesii.py`, `fill_attributes_nldi.py`), output data files, DATA_DOWNLOAD_PLAN.md, Krishnamurthy censoring thresholds

---

## Summary Verdict

The decision gate passes (34 sites with all 4 params, threshold was 30). The discrete downloads themselves are clean -- 182 calls, 0 failures. But there are **three issues that will silently degrade model quality if not addressed before Phase 3**, and two of them have no plan to be addressed. I am flagging them by severity.

---

## Finding 1: The NLDI Gap Leaves 35% of Sites With Toy-Level Catchment Attributes

**Severity: HIGH -- will directly affect cross-site transfer model quality**

The plan said GAGES-II covers most sites, NLDI fills gaps, HyRiver is the final fallback. Here is what actually happened:

- GAGES-II matched 37/57 sites. Fine.
- NLDI returned COMIDs but the characteristics endpoint returned non-JSON (the `fill_attributes_nldi.py` script fell through to `source: "none"` for the unmatched sites). The API is broken.
- HyRiver was never attempted.
- StreamCat was never attempted (needed COMIDs from NLDI, which technically were retrieved but never used).

**Result:** 20 sites have only drainage area, elevation, and HUC code from NWIS. That is 3 attributes versus 44 for the GAGES-II sites. In a leave-one-site-out CV setup where catchment attributes are features, these 20 sites will either:

1. Have NaN for 41 features (CatBoost handles NaN natively but this is not "handling" -- it is "guessing"), or
2. Be excluded, dropping your site count from 57 to 37.

Neither option is acknowledged in the current plan. The DATA_DOWNLOAD_PLAN.md lists Tier 3 (HyRiver) and Tier 4 (StreamCat bulk CSVs) as fallbacks, but nobody executed them. They are sitting there as aspirational bullet points.

**Concrete options remaining (in order of effort):**

1. **StreamCat bulk CSVs from GitHub.** You have COMIDs from NLDI. StreamCat publishes CSV files organized by metric category on their GitHub repo. Download the relevant CSVs, join by COMID. Does not require a working API. Effort: 2-3 hours. This is the most pragmatic path.

2. **NLCD + SSURGO direct download.** The National Land Cover Database and SSURGO soils are available as bulk downloads or WMS services. For 20 sites with known coordinates, you can extract catchment polygons from NHDPlus (using the COMIDs you already have) and do a zonal summary. Effort: 4-6 hours, requires geopandas/rasterio.

3. **Accept the gap and document it.** Run the model two ways: (a) all 57 sites with only the 3 common attributes as static features, (b) 37 GAGES-II sites with full 44 attributes. Compare. If catchment attributes do not materially improve cross-site transfer, the gap does not matter. If they do, you need options 1 or 2.

**My recommendation:** Option 3 first (it takes one training run and tells you whether this matters), then option 1 if it does. Do not proceed to Phase 3 without at least running the ablation, because if catchment attributes matter a lot, you will wish you had 57 complete sites rather than 37.

---

## Finding 2: The Orthophosphate Censoring Decision Is a Deferred Problem Disguised as a Decision

**Severity: MEDIUM -- will affect ortho-P model quality and TP >= ortho-P constraint**

The Krishnamurthy threshold was explicit: DL/2 is defensible below 10%. Ortho-P averages 9.8% with 12 sites above 10%. The decision was "borderline, DL/2 for now."

"For now" is not a decision. It is a deferral without a trigger. When will "now" become "later"? The answer, based on 15 years of watching research projects, is: never, unless someone writes down a concrete condition.

**The specific risk:** Ortho-P is not just another prediction target. It feeds the TP >= ortho-P physics constraint (Vasquez panel, Tier 2). If ortho-P values are biased low by DL/2 substitution at high-censoring sites, the constraint becomes easier to satisfy than it should be, which means it provides less useful regularization. You are weakening your own physics layer.

**What needs to happen:**

1. **Right now (10 minutes):** List the 12 sites with >10% ortho-P censoring. Check whether these sites also have high TP censoring. If TP censoring is low at the same sites, the TP >= ortho-P constraint will be fighting DL/2 artifacts.

2. **Before model training:** Run Krishnamurthy's Step 2 sensitivity analysis: train with DL/2 and with DL/sqrt(2) for ortho-P. If results differ by more than 5% in RMSE, you need the Tobit approach or you need to exclude those 12 sites from ortho-P training.

3. **Write the trigger now:** "If the DL/2 vs DL/sqrt(2) sensitivity analysis shows >5% RMSE difference for ortho-P, switch to site-level exclusion (drop ortho-P target at sites with >15% censoring) before publication." Put this in the AUDIT_FIX_PLAN.md or wherever the Phase 3 checklist lives.

**Nitrate is worse** (10.3% average, one site at 80.5%). The plan says "needs investigation" which is even vaguer than "for now." The 80.5% site should be excluded from nitrate training immediately -- that is not a borderline call. For the remaining sites, the same sensitivity analysis applies.

---

## Finding 3: Temporal Overlap With Continuous Data Has Not Been Checked

**Severity: HIGH -- the "50 sites with TP" count may be materially misleading**

The `analyze_new_params.py` script has a docstring that says it computes "Temporal overlap with continuous sensor data." The code does not implement this. The docstring is lying.

Here is why this matters: the discrete samples span decades (many USGS sites have nutrient data going back to the 1970s). The continuous sensor data -- turbidity, conductance, DO, pH, temperature -- typically starts in the 2010s. A site might have 800 TP samples, of which 750 predate the continuous sensors. That leaves 50 usable paired samples. At another site, 200 of 200 samples may fall within the sensor record.

Until someone computes the actual temporal overlap, the sample counts reported by Phase 2 are gross counts, not usable counts. The "50 sites with TP" could be "30 sites with >= 10 usable paired TP samples" or it could be "48 sites." We do not know.

**What needs to happen:**

For each site and parameter, compute:
- Date range of discrete samples
- Date range of continuous sensor data (you have this in `data/continuous/`)
- Number of discrete samples that fall within the continuous sensor date range
- Of those, number that fall within +/- 1 day of a continuous data point (accounting for gaps in the continuous record)

This is a 30-minute script. It should have been part of Phase 2. It needs to happen before Phase 3 starts, because if the usable paired counts are much smaller than the gross counts, the decision gate calculation changes. You might still pass (the threshold was 30 sites with >= 3 params), but the margin might be thinner than you think.

**Note:** The Phase 1 SSC data went through this pairing process (that is what `turbidity_ssc_paired.parquet` is). The Phase 2 data has not. The scan counted raw API returns, not paired samples.

---

## Finding 4: GAGES-II Attributes Are 15 Years Stale for Time-Sensitive Variables

**Severity: LOW-MEDIUM -- matters for some attributes, not others**

GAGES-II is based on 2006-2011 era data. For sites with records spanning 2000-2025, this means:

**Time-insensitive (use without concern):**
- Geology, lithology, percent carbonate/sandstone
- Soils (clay content, permeability, hydrologic soil group)
- Topography (slope, elevation)
- Basin area, shape, drainage density

**Time-sensitive (potentially stale):**
- Land cover (% forest, % agriculture, % urban, % impervious) -- NLCD releases every 3 years; 2006 vs 2021 land cover can differ substantially in peri-urban watersheds
- Population density -- 15 years of growth
- Dam storage / reservoir capacity -- dams built or removed since 2011
- Baseflow index -- can shift with land use change and climate

**The practical question:** How many of the 44 selected attributes are time-sensitive? I do not see a list of which 44 were selected from the 576 available. If the selection is heavy on geology and soils, the staleness does not matter. If it includes % impervious, % cropland, and population, it matters more.

**What needs to happen:**

1. Document the 44 selected attributes and tag each as time-sensitive or time-insensitive.
2. For time-sensitive attributes, consider whether NLCD 2021 data (available from MRLC) would be a better source for sites with recent data. This is a "nice to have" -- it improves rigor but probably does not change results materially for most sites.
3. At minimum, acknowledge this limitation when reporting results. "Catchment attributes are from the GAGES-II dataset (2006-2011 reference period) and may not reflect current land cover at sites with significant recent development."

This is the lowest-priority finding. Do not let it block progress. But do document it.

---

## Finding 5: The Download Cache Is Not Doing What You Think

**Severity: MEDIUM -- data integrity question that needs a 5-minute verification**

Here is the timeline from the logs:

| Step | Time | What happened |
|------|------|---------------|
| Scan started | 18:30 | 30 combos already done (resumed), scanned remaining 198 |
| Scan completed | 18:47 | 228 API calls total, results saved to `parameter_scan_progress.parquet` |
| Download started | 18:50 | 182 viable combos identified |
| Download completed | 18:55 | "Downloaded: 182, Failed: 0" |

Now here is the problem. The download script has file-based caching: if `data/discrete/{site}_{param}.parquet` exists, it reads from cache instead of calling the API. The download log shows **125 of 182 entries served from cache** (the `[cache]` entries) and only **57 fresh API downloads** (the `Downloaded` entries).

But the scan script does NOT write to `data/discrete/`. It only writes to `parameter_scan_progress.parquet`. So where did the 125 cached files come from?

**Two possibilities:**

1. There was a prior partial run of the download script (before the scan) that created some files. This is plausible if the Phase 2 pipeline was run iteratively.

2. The `dataretrieval` library has its own caching layer that writes files we are not tracking.

Looking at file timestamps: the cached files are timestamped 18:48-18:49, which is AFTER the scan completed (18:47) but BEFORE the download started (18:50). This is a 1-3 minute window. Something created those files.

**The actual concern:** If a prior download run was interrupted, the cached files might be truncated (partial HTTP responses saved as parquet). Parquet files are self-validating (they have a footer), so a truncated file would fail to read. The download script reads cached files with `pd.read_parquet()` -- if they were corrupt, it would throw an exception. Since the download completed without errors, the cached files are likely valid.

**Verification (5 minutes):** For 3-4 cached sites, compare the sample count in the cached parquet file against the count from the scan. If they match, the cache is good. If the cached count is lower, files may have been truncated by an earlier interrupted run.

```python
# Quick verification
import pandas as pd
scan = pd.read_parquet("data/parameter_scan_progress.parquet")
# Pick a cached site
df = pd.read_parquet("data/discrete/USGS_01491000_total_phosphorus.parquet")
scan_count = scan[(scan.site_id == "USGS-01491000") & (scan.pcode == "00665")].n_samples.values[0]
print(f"Scan count: {scan_count}, File count: {len(df)}")
```

If those match within a few percent (small differences are possible if the API returns slightly different results at different times), the data is fine. If the file count is systematically lower, re-download without cache.

**My real concern here is not corruption -- it is provenance.** When you report "182 API calls, 0 failures" in the Phase 2 results, that is misleading. You made 228 scan calls + 57 fresh download calls = 285 API calls, of which 125 downloads were served from local cache of unknown origin. The "0 failures" applies only to the 57 fresh downloads. The 125 cached files were never validated against the API.

---

## Summary Table

| # | Finding | Severity | Action Required | Blocks Phase 3? |
|---|---------|----------|----------------|-----------------|
| 1 | 20/57 sites missing catchment attributes | HIGH | Run ablation (option 3), then StreamCat if needed | Yes -- need to know if it matters |
| 2 | Ortho-P censoring hand-wave | MEDIUM | Sensitivity analysis + written trigger | No, but write the trigger now |
| 3 | No temporal overlap check | HIGH | Write the overlap script, recount usable samples | Yes -- current counts are gross, not usable |
| 4 | GAGES-II staleness | LOW-MEDIUM | Document which attributes are time-sensitive | No |
| 5 | Cache provenance unclear | MEDIUM | 5-min verification script | No, but verify before trusting counts |

**Bottom line:** The gate passes on the headline numbers, but two of the five findings (1 and 3) could change the effective site counts enough to matter. Before Phase 3, verify that the usable paired sample counts still support the gate, and decide whether 20 sites with 3 attributes is acceptable or needs remediation.

---

*Review by Ravi Patel, 2026-03-16. I reviewed the code, logs, and output files directly. Findings are based on what the data shows, not what the plan says should have happened.*
