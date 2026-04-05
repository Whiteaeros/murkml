# Review: Temporal/Contiguous Block Adaptation Changes

**Reviewer:** Claude Opus 4.6 (automated consistency review)
**Date:** 2026-04-02
**Scope:** Consistency, framing, clarity, and completeness of the contiguous-block adaptation rewrite.

---

## 1. Consistency Issues

**PROBLEM (Methods vs Results mismatch).** Section 3.5 (line 121) still lists the old three modes: "random, temporal (first N chronological), and seasonal." Section 4.4 (line 209) lists the new three: "random, contiguous block, and seasonal." The Methods section was not updated. Fix Section 3.5 to describe all four modes (random, contiguous block, first-N temporal, seasonal) or the three that appear in the main table.

**PROBLEM (Abstract says "event-targeted" = 0.49, table says "random" = 0.493).** The abstract (line 23) claims "0.49 with event-targeted sampling." The adaptation table has no "event-targeted" column --- 0.493 is from "Random." Random sampling across the full record is not event-targeted; it is temporally dispersed. The Discussion (line 319) clarifies that deliberately targeting storms "will approach the random ideal (0.49)," implying random is a proxy for event-targeted. This conflation is misleading. Either: (a) add an actual event-targeted column to the table, or (b) change the abstract to say "0.49 with temporally dispersed (random) sampling" and explain in the Discussion why random approximates event-targeted.

**PROBLEM (Key Point 2).** Key Point 2 says "10 grab samples raises median per-site R^2^ from 0.40 to 0.49" without specifying mode. This implies a practitioner gets 0.49 with any 10 samples. It should say "0.44 with contiguous sampling (0.49 with temporally dispersed sampling)" or similar.

**OK.** The 0.440 figure is consistent across the Results table, Results text, Discussion (5.4), Deployment guidance (5.6), and Conclusions. No number errors found for this value.

**OK.** The 0.389 first-N pathology number appears only in the start-of-record paragraph and is not contradicted elsewhere.

**OK.** Vault table (Section 6.5) reports N=10 random only (0.493/0.483), which is fine --- contiguous block was not run on vault.

## 2. Framing Assessment

The reframing is **mostly honest but slightly oversells contiguous block.** The paper now says contiguous block is "the realistic case" and frames first-N as a "pathology." This is defensible IF the averaging-over-all-start-positions truly represents operational reality. But a practitioner does not get to average over all start positions --- they get exactly one start position. The averaged 0.440 is the expected value, but the variance across start positions matters and is not reported. If 25% of start positions produce performance worse than zero-shot (like first-N does), then 0.440 is an optimistic summary.

**Recommendation:** Report the interquartile range or 10th/90th percentile of contiguous-block performance across start positions. A sentence like "MedSiteR^2^ ranges from 0.39 to 0.47 across start positions (IQR), with <X%> of start positions producing performance below zero-shot" would make the reframing bulletproof.

The old claim ("temporal adaptation is worse than zero-shot") was too strong because it tested only the single worst start position (index 0). The new claim is better but hides the distribution. The truth is somewhere in between: most contiguous blocks help, some do not, and the ones that do not are baseflow-dominated.

## 3. Clarity

**The terminology is clear in Section 4.4** --- the distinction between "contiguous block (random start, N consecutive)" and "first-N (always start at index 0)" is well-explained. A reader would understand.

**But Section 3.5 breaks this** because it still uses the old "temporal" label, which readers will confuse with "contiguous block." The word "temporal" appears nowhere in the Results, creating a terminology discontinuity between Methods and Results. This needs a unified fix.

**Figure 4 caption** (line 499) handles it well: blue=random, orange=contiguous block, dashed red=first-N-only. This is the right visual strategy.

## 4. Should Both Modes Appear in the Main Table?

**Yes.** The first-N result (0.389) is important and should appear in the main adaptation table as a fourth column or a footnote row. Reasons:

1. Practitioners who start a new monitoring program and collect the first 10 samples chronologically will get first-N performance, not contiguous-block performance. This is a real deployment scenario.
2. Hiding it in a warning paragraph makes the paper look like it is downplaying an inconvenient result.
3. WRR reviewers will ask where the old temporal column went if they saw a preprint.

Add a column or footnote: "First-N (index 0 start): 0.389 at N=10. See text for explanation."

## 5. Other Number Issues

- The 0.05 gap cited in lines 221 and 315 (contiguous vs random) is actually 0.053 (0.493 - 0.440). Rounding to 0.05 is fine but should be "~0.05" for precision.
- Line 233 references "first-N" OLS at N=2 as -0.56 but gives no contiguous-block OLS comparison. This is fine --- OLS results are less important at N=2.
- The Conclusions (line 389) say "10 contiguous grab samples raises median R^2^ to 0.44" --- consistent.
- Deployment guidance (line 333) says "0.44 with contiguous sampling, 0.49 with event-targeted sampling" --- same abstract problem: "event-targeted" is not a mode in the table.

## Summary of Required Fixes

| Priority | Issue | Location |
|----------|-------|----------|
| HIGH | Methods (3.5) still describes old "temporal" mode, not contiguous block | Line 121 |
| HIGH | "Event-targeted" in abstract/deployment/KP2 has no table column; conflated with "random" | Lines 12, 23, 333 |
| MEDIUM | Add first-N results to main table (column or footnote) | Table 3 |
| MEDIUM | Report variance of contiguous-block across start positions | Section 4.4 |
| LOW | "0.05 gap" is actually 0.053; use "~0.05" | Lines 221, 315 |
