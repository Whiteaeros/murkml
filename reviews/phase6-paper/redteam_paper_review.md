# Red-Team Paper Review: wrr_draft_v2.md

**Date:** 2026-04-02
**Reviewed against:** v11_extreme_eval_summary.json, v11_bootstrap_ci_results.json, v11_vault_eval_per_site.parquet

---

## CRITICAL ISSUES (must fix before submission)

### 1. Ferron Creek numbers are internally inconsistent

- **Table 4** says CatBoost ratio = **0.72** (5,792 / 8,049 = 0.720, i.e., 28% underprediction).
- **Section 4.6 text** (line 253) says "The 25% underprediction (ratio 0.75)" -- both the ratio AND the percentage contradict the table.
- **Conclusions** (line 383) say "underpredicts by 28%" -- matches the table but contradicts Section 4.6 text.
- **Fix:** Make text match the table. Either the table is wrong or the text is. If the table is authoritative, Section 4.6 should say "28% underprediction (ratio 0.72)".

### 2. Valley Creek load overprediction is wrong in text

- **Table 4** says CatBoost ratio = **2.39** (7,447 / 3,120), which is 139% overprediction.
- **Section 4.6 text** (line 255) says "total load overprediction of 55%."
- **Fix:** Change "55%" to "139%" or verify the table is wrong.

### 3. Vault site count: 36 vs 37

- **Section 2.5** says "vault (36 sites)."
- **Figure 1 caption** says "vault (36, squares)."
- **Section 6.5 vault table** says "Vault (37 sites)."
- **v11_vault_eval_per_site.parquet** contains 37 sites.
- **Fix:** All should say 37 (or 36 if one was dropped). Currently the paper contradicts itself.

### 4. Holdout "Frac R2 > 0" is reported differently in two places

- **Table 1 / Section 4.1** (line 163): Frac R2 > 0 = **75.7%** [68.1%, 83.7%]. Matches bootstrap (0.7568).
- **Section 6.5 vault comparison table** (line 363): Holdout Frac R2 > 0 = **71.8%**.
- These should be the same holdout result. The 4-point discrepancy (75.7% vs 71.8%) is material. One of these is wrong, or they use different R2 definitions.
- **Fix:** Reconcile. If the vault evaluation used NSE (which can differ from R2 at the site level), note that explicitly. Otherwise one number must be corrected.

### 5. Conclusions contain a duplicate Ferron Creek sentence (line 383)

> "At Ferron Creek, a snowmelt-driven Utah site, the model achieves daily R^2^ = 0.76 and underpredicts by 28%. At Ferron Creek (Utah), a completely different geomorphic setting, the model achieves daily R^2^ = 0.76, demonstrating genuine cross-geologic transfer."

This says essentially the same thing twice with slightly different framing. Delete one.

### 6. Introduction overstates training data

- **Introduction** (line 45): "trained on 36,341 paired turbidity-SSC observations from 405 USGS sites"
- **Abstract** (line 19): "trained on 23,624 paired turbidity-SSC observations from 260 USGS sites"
- 36,341 / 405 is the total dataset, not training data. The abstract is correct. The introduction is misleading -- it implies all 405 sites were used for training.
- **Fix:** Change the intro to say "using a dataset of 36,341 observations from 405 sites" or "trained on 23,624 observations from 260 sites."

---

## MODERATE ISSUES (should fix)

### 7. Site count arithmetic is unexplained

- Section 2.1: 413 identified, 405 after QC.
- Section 2.5: 260 + 78 + 36(or 37) = 374 (or 375).
- 405 - 375 = 30 sites are unaccounted for. Were they dropped because they lacked StreamCat coverage (Section 2.4 notes only 370/413 have StreamCat)? The paper never explains where these 30 sites went. A reviewer will notice this arithmetic gap.
- **Fix:** Add a sentence in Section 2.4 or 2.5 explaining how many sites were dropped for missing watershed attributes.

### 8. MAPE is computed differently in Table 1 vs Section 6.5 vault table

- **Table 1** reports MAPE = 40.1%, which matches the **pooled** MAPE from eval_summary (40.07%).
- **Section 6.5 vault comparison table** reports Holdout MAPE = 39.6%, which matches the **median per-site** MAPE from the adaptation curve (39.63%).
- The bootstrap CI for MedSiteMAPE is actually 53.8% [47.5%, 65.7%] -- neither table reports this.
- Reporting two different aggregations of the same metric as "MAPE" without qualification is confusing. A reviewer will try to reconcile these numbers and fail.
- **Fix:** Label clearly as "Pooled MAPE" vs "Median per-site MAPE" in each table.

### 9. Holdout Spearman: 0.875 vs 0.876

- **Table 1** says MedSiteSpearman = 0.875.
- **Section 6.5 vault table** says Holdout MedSiteSpearman = 0.876.
- Bootstrap point estimate is 0.8735.
- Minor but sloppy. The same holdout result should be the same number everywhere.
- **Fix:** Use 0.874 (which is what 0.8735 rounds to at 3 decimal places) or 0.875 consistently.

### 10. Appendix B default config is not the best in the grid

- The paper's default (k=15, df=4) yields MedSiteR2 = 0.493, but the grid shows k=10, df=2 yields 0.498.
- A reviewer may ask: "Why didn't you use the better configuration?" This isn't an error, but the paper should preemptively address it (e.g., the difference is within noise, or k=10 overfits at small N, etc.).

---

## MINOR ISSUES

### 11. Abstract says "24% ... have R2 < 0, clustering in volcanic, glacial-flour, and urban geologic regimes"

- The 24% comes from 1 - 0.757 = 24.3%. But the CI is [16%, 32%], meaning the true fraction could be as high as a third or as low as a sixth. The point estimate is fine, but the paper treats "24%" as a precise number in the abstract, key points, discussion, and conclusions without always noting the uncertainty.

### 12. No vault adaptation CIs are reported

- Section 6.5 reports vault N=10 random MedR2 = 0.483, but no CI. The holdout CI is given (0.440--0.547) but with only 37 vault sites, a vault-specific CI would be very wide. The paper claims "all vault metrics fall within the holdout bootstrap confidence intervals" -- this is technically verifiable for MedSiteR2 (0.365 is within [0.358, 0.440] -- barely, at the lower edge) and for N=10 (0.483 in [0.440, 0.547]). But vault Spearman 0.856 is outside [0.836, 0.899] -- wait, it's inside. OK. Frac R2>0: vault 78.4% is within [68.1%, 83.7%]. This claim checks out.

### 13. Figure 1 caption says "vault (36, squares)" -- should be 37

See issue 3.

### 14. BCF_mean = 1.297 vs BCF values in eval_summary

- Section 3.3 says BCF_mean = 1.297.
- Eval summary: bcf_mean_available = 1.2969. Rounds to 1.297. OK.
- Section 3.3 says BCF_median = 0.975. Eval summary: bcf_median_available = 0.9748. Rounds to 0.975. OK.

### 15. Missing: no discussion of computational cost

- WRR reviewers often want to know training time, inference time, and hardware. A single sentence would suffice.

### 16. Missing: data availability for vault sites

- Section 8 mentions releasing model and splits. The vault evaluation is a key result -- ensure vault site IDs are in the release.

### 17. Section 5.5 comparison with Song et al. is somewhat unfair

- Song et al. (2024) report R2 = 0.55 at "gauged sites" (with some training data), vs this paper's zero-shot 0.40 at truly unseen sites. The paper acknowledges this ("different monitoring gaps") but a reviewer might still flag the comparison as misleading. Consider noting that Song's gauged-site setup is analogous to the N=10 adapted result (0.49), which is closer.

---

## OVERCLAIM FLAGS

### 18. "First continental-scale quantification" (appears 4 times)

- Used for the between-site/within-site CV ratio. This is a strong claim. If any prior work has computed turbidity-SSC variability across >50 sites in the US, this claim falls. The paper should cite a quick literature check showing no prior work did this, or soften to "among the first."

### 19. Key Point 2 packs too much into one bullet

- "At a benchmark site, the cross-site model overpredicts matched-day sediment loads by 59% while discharge-only regression overpredicts by 100%, and storm-event errors are 1.4--3.5x smaller; Bayesian adaptation with 10 grab samples raises median per-site R2 from 0.40 to 0.49."
- This is two separate findings stitched together. WRR key points should be one clear claim each.

---

## SUMMARY

**Critical fixes needed:** 6 (Ferron numbers, Valley Creek percentage, vault count, R2>0 discrepancy, duplicate sentence, intro training data overstatement)

**Moderate fixes:** 4 (site arithmetic, MAPE labeling, Spearman rounding, Appendix B justification)

**Minor/style:** 8 items

The paper's core claims are well-supported by the data. The main risk is a reviewer catching the numerical inconsistencies (especially Valley Creek 55% vs 139% and Ferron 25% vs 28%), which would undermine confidence in the entire analysis.
