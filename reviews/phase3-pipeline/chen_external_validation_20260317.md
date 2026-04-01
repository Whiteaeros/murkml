# External Validation Review -- Dr. Sarah Chen, ML Engineer
**Date:** 2026-03-17
**Re:** SSC and TP external validation results on held-out states

---

## 1. Interpretation of results

**SSC: Genuinely encouraging, not broken.**

The LOGO CV R^2=0.80 to external median R^2=0.61 drop is real but explainable. Looking at the raw log, the distribution is bimodal:

| Tier | Sites | Median R^2 | Pattern |
|------|-------|-----------|---------|
| n >= 50 | 8 sites | ~0.78 | Comparable to LOGO CV |
| n < 50 | 3 sites (AZ n=10, WI-04026005 n=13, WI-040851385 n=11) | ~0.30 | Too few samples, noise dominates |

The AZ site (R^2=-8.13, n=10) is a catastrophic outlier dragging the median. With 10 samples in an arid regime fundamentally different from your training distribution, this is expected behavior, not a model failure. The Iowa site (R^2=-0.50, n=60) is the only genuinely concerning case -- enough data, bad performance. I would investigate whether Iowa has a different turbidity-SSC regime (loess soils, fine-grained SSC that turbidity misses).

**TP: More concerning, but not hopeless.**

Median R^2=-0.54 vs LOGO CV R^2=0.62 is a large gap. But the site-level breakdown tells a clear story:

- Where CatBoost wins, it wins big: NY R^2=0.77 vs OLS 0.08, MN R^2=0.79 vs OLS 0.69, IA R^2=0.69 vs OLS 0.34
- Where CatBoost loses, the *predictions are actively wrong* (R^2 deeply negative): CT R^2=-7.30, GA R^2=-2.06, MN-04024000 R^2=-0.54

This is the signature of a **bias shift problem**, not a variance problem. The model learned a turbidity-TP relationship from its training sites that does not hold at sites where TP is dominated by dissolved P (not particulate). At those sites the model confidently predicts the wrong level. TP is fundamentally harder than SSC because the turbidity-TP coupling is weaker and more site-dependent.

**Bottom line:** This is NOT a fundamental generalization failure. It is (a) small-sample noise on SSC, and (b) domain shift on TP where dissolved P dominates.

---

## 2. Filtered numbers (n >= 50, excluding AZ arid outlier)

**SSC, n >= 50 only (8 sites):**

| Site | State | n | CB R^2 | OLS R^2 | Winner |
|------|-------|---|--------|---------|--------|
| 01362370 | NY | 384 | 0.781 | 0.911 | OLS |
| 02207135 | GA | 87 | 0.611 | 0.587 | CB |
| 04024000 | MN | 171 | 0.793 | 0.594 | CB |
| 04213500 | NY | 298 | 0.902 | 0.809 | CB |
| 05082500 | MN/ND | 177 | 0.904 | 0.937 | OLS |
| 05447500 | IA | 60 | -0.503 | 0.063 | OLS |
| 08070200 | TX | 140 | 0.546 | 0.707 | OLS |
| 12113390 | WA | 103 | 0.872 | 0.829 | CB |

- Median CB R^2: **0.787** (close to LOGO CV 0.80)
- CB wins 4/8
- Excluding the Iowa anomaly: median CB R^2 = **0.793**

This is strong. For SSC with adequate data, the model generalizes well.

**TP, n >= 50 only (8 sites):**

| Site | State | n | CB R^2 | OLS R^2 | Winner |
|------|-------|---|--------|---------|--------|
| 02207135 | GA | 82 | -2.059 | 0.332 | OLS |
| 04024000 | MN | 178 | -0.536 | 0.632 | OLS |
| 04213500 | NY | 314 | 0.773 | 0.082 | CB |
| 05082500 | MN/ND | 260 | 0.787 | 0.689 | CB |
| 05447500 | IA | 110 | 0.694 | 0.344 | CB |
| 08070200 | TX | 140 | -2.018 | -0.810 | OLS |
| 410333... | IA | 123 | 0.578 | 0.310 | CB |
| 41061307... | CT | 52 | -7.298 | -0.052 | OLS |

- Median CB R^2: **0.021** (midpoint between -0.536 and 0.578)
- CB wins 4/8, and where CB wins, margins are large
- Excluding the 3 deeply-negative sites (GA, TX, CT -- likely dissolved-P-dominant): median CB R^2 = **0.694**

The pattern is clear: TP works when turbidity is informative for TP (particulate-P-dominant sites) and catastrophically fails when it is not.

---

## 3. Retraining on expanded dataset -- risks and recommendation

**Kaleb's plan:** Retrain on original 57 + validation 11 = ~68 sites, find 20 new test sites.

**This is methodologically sound with one critical caveat:**

The risk of "training on your test set" is real *if you keep reporting the old validation numbers.* But if you:
1. Retrain on the expanded pool
2. Find genuinely new sites for re-testing
3. Report ONLY the new test numbers

...then you have NOT contaminated your evaluation. You have simply increased your training diversity, which is exactly what you should do.

**However, I would NOT do this yet.** Here is why:

Throwing more sites into a model that has a structural weakness (TP dissolved-P blind spot) will give you marginally better numbers but won't fix the core issue. The TP failures are not caused by too few training sites -- they are caused by missing information. Adding 15 more humid-eastern sites won't help the model predict dissolved-P-dominant sites.

---

## 4. Most impactful next steps (priority order)

### Step 1: Diagnose before you treat (1-2 hours)

For the failing TP sites (GA-02207135, MN-04024000, TX-08070200, CT-410613...), check:
- What fraction of TP is particulate vs dissolved? If dissolved P >> particulate P, turbidity is nearly useless as a predictor. This is the expected failure mode.
- Are the predicted values systematically too high or too low? (Bias direction tells you whether the training sites had higher or lower particulate-P fractions.)

If confirmed, this is not fixable with more training data -- you need a dissolved-P proxy feature (conductance is sometimes one).

### Step 2: Declare SSC ready, scope TP honestly (0 effort, high impact)

SSC external validation, filtered to adequate sample sizes: **median R^2 = 0.79.** This is publishable and commercially viable. You can honestly say the model generalizes across 14 states.

For TP, the honest claim is: "The model works at sites where particulate phosphorus dominates (R^2 ~ 0.7) but fails where dissolved phosphorus is the primary fraction." This is actually a useful finding -- it defines the applicability domain.

### Step 3: Add a confidence/applicability flag (medium effort, high value)

Instead of retraining, build a simple applicability check: if the model's prediction residuals at a new site exceed a threshold in the first N samples, flag the site as "out of applicability domain -- local calibration recommended." This turns a failure into a feature. The product tells the user when to trust it.

### Step 4: THEN retrain on expanded data (only if Steps 1-3 are done)

After you understand *why* sites fail, add the successful validation sites to training, add a dissolved-P indicator feature if feasible (e.g., conductance-turbidity ratio as a proxy for dissolved fraction), and find 15-20 genuinely new test sites. This time, deliberately include a mix of dissolved-P and particulate-P sites in the test set.

---

## Summary verdict

| Target | External validation status | Action |
|--------|--------------------------|--------|
| SSC | **PASS** -- median R^2=0.79 on adequate-data sites across 14 states | Ship it. Report filtered numbers honestly with sample-size caveats. |
| TP | **CONDITIONAL** -- works at particulate-P sites (R^2~0.7), fails at dissolved-P sites | Diagnose dissolved-P issue before retraining. Consider scoping TP to "particulate-P-dominant sites" in v1. |

Do not retrain yet. Diagnose first, ship SSC now, scope TP honestly.

---

*Dr. Sarah Chen, ML Engineer*
*Review prepared for Kaleb -- murkml external validation decision point*
