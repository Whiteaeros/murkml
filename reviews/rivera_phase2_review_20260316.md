# Phase 2 Discrete Data Review — Dr. Marcus Rivera
**Date:** 2026-03-16
**Scope:** Review of Phase 2 nutrient/TDS discrete data downloads for 57 USGS sites
**Data examined:** Download logs, parquet column structures, method identifiers, censoring patterns, detection limits

---

## 1. Parameter Code Verification

### Findings

| pcode | Expected | Confirmed Characteristic in Data | Sample Fraction | Verdict |
|-------|----------|----------------------------------|-----------------|---------|
| 00665 | Total Phosphorus | "Phosphorus" | **Unfiltered** | CORRECT — unfiltered = total P, not dissolved |
| 00631 | Nitrate+Nitrite as N | "Inorganic nitrogen (nitrate and nitrite)" | Filtered | CORRECT — filtered, as N basis, not total N |
| 70300 | TDS by evaporation | "Total dissolved solids" | Filtered | CORRECT — ROE (residue on evaporation) method confirmed |
| 00671 | Orthophosphate as P | "Orthophosphate" | Filtered | CORRECT — filtered, as P basis |

**All four parameter codes are pulling exactly what you want.** The sample fraction field is the key discriminator:
- 00665 returns **Unfiltered** (total P, includes particulate-bound P). Good. If it said "Filtered" you'd have dissolved P, which is a different parameter (00666).
- 00631 returns **Filtered** — this is correct for nitrate+nitrite as N. The unfiltered equivalent would be total nitrogen (00600/62854), which you explicitly do not want.

### Gotchas to be aware of

**[IMPORTANT] Units:** All data comes back in mg/L, which is correct and consistent. However, I see `None` values in `Result_MeasureUnit` on censored records. When `Result_ResultDetectionCondition = "Not Detected"`, the Result_Measure is often null and so is the unit. Your DL/2 substitution logic needs to pull the unit from the detection limit column, not the result column, for these records.

**[MINOR] TP method speciation:** pcode 00665 is "Phosphorus, water, unfiltered" — it's reported "as P." Some older literature reports phosphorus as PO4. All USGS NWIS data for 00665 is consistently as P, so no conversion needed, but if you ever merge with state agency data from WQP, check the `Result_MethodSpeciation` field.

**[MINOR] Ortho-P vs TP constraint:** The physics panel noted TP >= ortho-P must hold. In the data, TP is unfiltered and ortho-P is filtered — so this constraint should hold naturally. However, analytical variability at low concentrations can produce apparent violations. Flag but don't discard these; they're measurement noise, not data errors.

---

## 2. Sample Count Sanity Check — Duplicates

### Findings

**[MINOR] Duplicates are not a significant problem in this dataset.**

I checked the Activity_ActivityIdentifier field (the unique sample event ID from WQP) across multiple sites. Results:
- USGS-01491000 TP: 1,077 rows, 1,077 unique activity IDs, 1,077 unique date+time combos
- USGS-04193500 TP: 4,168 rows, all with unique activity IDs, zero same-timestamp duplicates
- Across the first 30 files checked: only 1 file (an SSC file, not a Phase 2 file) had a single duplicate activity ID

This is consistent with how the new USGS Samples API works — it returns one row per result, and since you queried by single pcode, there's no multi-parameter row expansion.

**However**, there are two dedup scenarios to handle during preprocessing:

1. **QA replicates:** Some sample events are QA/QC splits (Activity_TypeCode = "Sample - Routine, regular" vs "Quality Control Sample - Field Replicate"). I didn't find these in the spot checks, but they exist in longer records. Standard practice: keep the primary, drop the QC replicate. Or average them — either way, document it.

2. **Same-day samples at different times:** A site might have a morning and afternoon sample on the same day, both legitimate. These are NOT duplicates. Your temporal alignment will correctly pair each one with its own continuous reading. Do not dedup by date alone.

**Bottom line:** Your reported counts (30,637 TP, 28,309 nitrate, etc.) are likely accurate to within 1-2% of the true usable sample count. Dedup will shave off very little.

---

## 3. The 80.5% Censored Nitrate Site

### Identification

The site is **USGS-11501000, Sprague River near Chiloquin, Oregon.** Detection limit: 0.04 mg/L.

### Assessment

**[IMPORTANT] This is a real environmental signal, not a data quality problem.**

The Sprague River is a spring-fed system in the upper Klamath Basin. Spring-dominated streams in volcanic terrain routinely have ambient nitrate below 0.05 mg/L. The 33 detected samples average 0.154 mg/L with a max of 0.907 — those are the storm pulses and seasonal peaks. The 136 non-detects are baseflow conditions where nitrate is genuinely below 0.04 mg/L.

### Recommendation

**Drop this site from the nitrate model, but keep it for TP and ortho-P.**

Here's my reasoning:
- A model trained on data that's 80% censored at 0.04 mg/L is learning to predict "basically zero" most of the time. That's not useful.
- DL/2 substitution (0.02 mg/L) for 80% of samples creates a massive artificial spike in the concentration distribution at a single value. This violates the distributional assumptions of most ML loss functions.
- You could use Kaplan-Meier or maximum likelihood estimation for censored data, but that's a research project unto itself, and 33 real observations isn't enough to calibrate a site-specific sensor-to-concentration relationship.

**Set a threshold:** Drop any site/parameter combination where >50% of samples are censored. For the sites with 10-50% censoring, DL/2 is acceptable as long as you:
1. Add a binary feature `is_censored` to the training data
2. Document the censoring rate per site in the model metadata

For the 35/48 sites with <10% nitrate censoring, DL/2 is unambiguously fine.

---

## 4. Method Consistency

### TP Methods Over Time

At USGS-04193500 (longest record, 1971-2026):

| Method | Period | Count | Notes |
|--------|--------|-------|-------|
| (none) | 1971-2013 | 3,615 | Legacy STORET records, method not migrated |
| CL084 | 1985-1991 | 27 | Kjeldahl digestion + colorimetry |
| KJ010 | 1991-1994 | 12 | Kjeldahl block digestion |
| KJ009 | 1994-2026 | 288 | Automated Kjeldahl |
| CL021 | 1999-2026 | 211 | EPA 365.1 equivalent |
| AKP01 | 2004-2011 | 15 | Alkaline persulfate digestion |

**[IMPORTANT] The 3,615 records with NaN method are legacy NWIS/STORET data.**

These are real USGS samples — the method metadata just wasn't migrated when the data moved to WQP format. The conducting organizations confirm they're USGS. These records span 1971-2013 and represent the bulk of the long-term record.

**Do NOT filter to specific methods.** If you restrict to only records with known methods, you'll lose ~70% of the data at long-record sites. The actual analytical methods used by USGS for total phosphorus have been reasonably comparable since the 1980s — they all involve acid digestion followed by colorimetric detection. Detection limits have improved (from ~0.01 mg/L to ~0.004 mg/L), but the measurements are comparable.

### Nitrate Methods Over Time

| Method | Period | Notes |
|--------|--------|-------|
| CL045 | 1985-1994 | Cadmium reduction |
| CL048 | 1994-2011 | Automated cadmium reduction |
| RED01 | 2011-present | Enzymatic reduction (newer, no cadmium waste) |

**[MINOR] The method transition from cadmium reduction to enzymatic reduction around 2011 is real but not a problem for your use case.** Both methods produce equivalent results in side-by-side testing. The USGS published comparison studies confirming this. Detection limits improved slightly (0.01 to ~0.004 mg/L), which could create a few extra non-detects in post-2011 data at very low-concentration sites, but this is negligible.

### Detection Limit Step Changes

**[IMPORTANT] Nitrate detection limits vary enormously across the dataset: from 0.002 to 0.45 mg/L.**

The full list I found: 0.002, 0.003, 0.004, 0.005, 0.01, 0.013, 0.016, 0.02, 0.022, 0.04, 0.05, 0.06, 0.09, 0.1, 0.12, 0.18, 0.2, 0.3, 0.45 mg/L.

A detection limit of 0.45 mg/L means any nitrate below 0.45 is reported as "Not Detected" — that's a fundamentally different measurement than a site with DL of 0.004 mg/L. When you substitute DL/2, you'd get 0.225 mg/L for one and 0.002 mg/L for the other, even though the true concentration could be identical.

**Action required:** When computing DL/2 for censored values, use the *per-record* detection limit from `DetectionLimit_MeasureA`, NOT a fixed value. The detection limit varies by method, lab, and time period. The data already has this field populated correctly for censored records.

---

## 5. Temporal Alignment Window

### Current approach: ±15 minutes for all parameters

**[IMPORTANT] The ±15 minute window is appropriate for nutrients, but the reasoning is different than for SSC.**

For SSC, the concern is that turbidity changes fast during storms and you need a tight match. For nutrients, the situation is:

- **During baseflow:** Nutrient concentrations change on timescales of hours to days. A ±15 min window is more than tight enough. You could use ±2 hours and get the same answer.
- **During storms:** Nutrient concentrations (especially TP, which binds to sediment) change on the same timescale as turbidity — minutes. Here ±15 min is exactly right.
- **For nitrate specifically:** Nitrate has a somewhat different storm response than TP. In many watersheds, nitrate shows dilution during storm peaks (rain dilutes groundwater nitrate), while TP shows concentration peaks (sediment-bound P gets mobilized). The ±15 min window handles both patterns fine.

**My recommendation: Keep ±15 minutes as the primary match window.** Do not vary by hydrologic condition. Here's why:

1. The `Activity_HydrologicCondition` field is populated for most samples (I see "Stable, normal stage," "Rising stage," "Falling stage," etc.), but it's a subjective field filled in by the field tech. It's not reliable enough to drive algorithmic decisions.
2. Widening the window during baseflow gains you very few additional matches (baseflow samples are usually collected during normal working hours when sensors are operating fine), and it introduces inconsistency in how the aligned features are computed.
3. The ±1 hour feature window already captures the slower baseflow dynamics through window_mean and window_slope.

**One exception to flag:** The `Activity_HydrologicEvent` field shows "Storm" for 392/1077 samples at one site (USGS-01491000). This is useful metadata. Consider adding `hydrologic_event` as a categorical feature in the model, but don't use it to change the alignment window.

---

## 6. TDS Coverage (38/57 sites)

### Assessment

**[MINOR] 38 sites is more than enough for SC-to-TDS modeling. In fact, this is the easiest prediction target in the entire project.**

The SC-TDS relationship is governed by basic electrochemistry: specific conductance measures the total ionic strength of the solution, and TDS (by evaporation) measures the total dissolved mass. At any given site, the relationship is:

```
TDS = a * SC + b
```

where `a` is typically 0.55-0.75 depending on dominant ion chemistry (carbonate vs sulfate vs chloride systems). The R-squared is routinely >0.95 at individual sites and >0.85 across sites.

**Why 38 sites works:**
- You don't need geographic diversity for TDS the way you do for sediment (where geology, land use, and watershed size all create unique turbidity-SSC relationships).
- What matters for TDS is *ionic chemistry diversity* — you need some carbonate-dominated sites (Midwest/karst), some sulfate-dominated (mining/arid West), and some chloride-influenced (coastal/road salt). Your 38 sites across 11 states covers this adequately.
- The 19 sites without TDS data are likely sites where nobody bothered to run the evaporative analysis because they already had SC — which tells you the same thing.

**Practical note:** Given how strong and simple the SC-TDS relationship is, TDS is more of a "prove the framework works" target than a research contribution. The value of murkml for nutrients (TP, nitrate) is much higher, because those relationships with sensor surrogates are nonlinear, site-specific, and currently require manual model building. TDS is a warm-up exercise.

---

## Summary of Action Items

| # | Severity | Issue | Action |
|---|----------|-------|--------|
| 1 | **CRITICAL** | Detection limits vary per record (0.002-0.45 mg/L for nitrate) | Use per-record `DetectionLimit_MeasureA` for DL/2 substitution, never a fixed DL |
| 2 | **IMPORTANT** | 80.5% censored nitrate at USGS-11501000 | Drop from nitrate model. Set threshold: exclude site/param combos with >50% censoring |
| 3 | **IMPORTANT** | 3,615 TP records at long-record sites have NaN method | Do NOT filter by method. These are valid legacy USGS samples with un-migrated metadata |
| 4 | **IMPORTANT** | Censored records have None in Result_MeasureUnit | Pull units from DetectionLimit_MeasureUnitA for censored records |
| 5 | **IMPORTANT** | Ortho-P has "Systematic Contamination" flags (11 records across 2 sites) | Exclude these records — they are known blank contamination, not real measurements |
| 6 | MINOR | Temporal alignment window ±15 min | Keep as-is for all parameters. Add `Activity_HydrologicEvent` as a model feature |
| 7 | MINOR | QA replicates may exist in longer records | Add dedup step: keep primary sample, drop QC replicates by Activity_TypeCode |
| 8 | MINOR | TP >= ortho-P constraint may show apparent violations at low concentrations | Flag but don't discard; add as a data quality check in preprocessing |

### Overall Assessment

The Phase 2 download is clean, complete, and well-executed. The parameter codes are correct, the sample counts are real (not inflated by duplicates), and the data structure supports all the preprocessing you need. The two critical items are (1) per-record detection limit handling and (2) the high-censoring site exclusion — both are straightforward to implement. The method consistency question is a non-issue; do not filter by method.

The 34 sites with all 4 parameters at >= 10 samples each is a strong foundation for multi-target modeling. Proceed to preprocessing and alignment.

— Dr. Marcus Rivera
