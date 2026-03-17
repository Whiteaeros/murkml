# Chen — Phase 2 Data Download Review

**Date:** 2026-03-16
**Scope:** Multi-parameter discrete data + catchment attributes readiness for LOGO CV
**Verdict:** Data looks workable. Several design decisions need resolving before you write training code. One critical issue, two important, rest minor.

---

## 1. Sample Size Adequacy for LOGO CV (34 sites, all 4 params)

**Severity: IMPORTANT**

34 folds is borderline. Here is my reasoning:

LOGO CV produces one performance estimate per fold. The standard error of the mean R² across k folds is approximately `sd(R²) / sqrt(k)`. For cross-site hydrology models, inter-site R² variance is typically high (sd ~ 0.15-0.25 because some sites are easy and some are pathological). With 34 folds and sd=0.20, your SE on mean R² is 0.20/sqrt(34) = 0.034. That means your 95% CI on mean R² is roughly +/-0.07. You can distinguish "good" (R²=0.65) from "bad" (R²=0.45), but you cannot distinguish "good" (0.65) from "decent" (0.58). For a paper, that is acceptable. For product claims, it is thin.

**The real problem is not the fold count — it is the per-fold sample count heterogeneity.** If fold i has 20 test samples and fold j has 1000, the per-fold R² estimates have wildly different precision. A site with 20 samples can swing R² by 0.2 from a single outlier. You need to:

1. **Report sample-weighted metrics alongside unweighted.** Unweighted = each site matters equally (fairness). Weighted = reflects actual prediction quality on the pool. Both matter.
2. **Set a minimum test-set size per fold.** I would drop sites with <30 samples from evaluation (not from training — they can still contribute to training folds). Report them separately as "insufficient data for reliable evaluation."
3. **Bootstrap confidence intervals on LOGO metrics.** Resample the fold-level results with replacement, 1000 times. This gives you honest CIs that account for the skewed fold sizes.

**My minimum for LOGO:** 25 folds for exploratory modeling, 40+ for publication-quality claims. 34 is in the gray zone. You can publish with 34 if you are transparent about CIs and do not over-claim precision. For individual parameters where you have more sites (TP: 50, nitrate: 48), run the full set — do not artificially restrict to 34.

---

## 2. GAGES-II Coverage Gap (37/57 matched, 20 missing)

**Severity: CRITICAL**

This is the most consequential design decision in the whole Phase 2 plan. Let me evaluate all three options honestly.

### Option (a): Impute missing sites with medians

**Risk: High. Do not do this.**

Median imputation of 44 catchment features for 20/57 sites (35% of your data) is not imputation — it is fiction. CatBoost will learn that these 20 sites all look identical on catchment features, which is false. Worse, if the missing sites are systematically different from the matched sites (they probably are — GAGES-II covers established, well-studied watersheds, so your 20 missing sites are likely smaller, newer, or oddball basins), you are introducing a bias that correlates with your target variable. This is a textbook case of Missing Not At Random (MNAR).

Even with CatBoost's native missing-value handling (which routes NaN to the best split), 44 features all simultaneously NaN for 35% of sites will create a de facto binary split: "GAGES-II site vs. not-GAGES-II site." The model will learn the split but the feature importance will be garbage.

### Option (b): Two model variants (with/without catchment features)

**Risk: Medium. Methodologically honest but operationally messy.**

You train Model A on all 57 sites using only sensor features, and Model B on 37 sites using sensor + catchment features. This is clean — no imputation, no data fabrication. But it creates two problems:
- You cannot compare Model A vs Model B on the same test set because they use different site pools. The 37-site pool is a biased subsample.
- For the paper, you need to explain why you have two models, which raises reviewer eyebrows.

If you go this route, the correct comparison is: run Model A on the 37-site subset only (not all 57), then compare to Model B on the same 37 sites. This isolates the effect of catchment features. Report the 57-site Model A results separately as a "broader validation."

### Option (c): Evaluate catchment features only on 37-site subset

**Risk: Low. This is the correct approach.**

Train and evaluate the catchment-augmented model on 37 sites only. Report the sensor-only model on all 57 sites. This gives you:
- An honest comparison of "do catchment features help?" on the same 37 sites (LOGO on 37 with vs. without catchment features)
- A broader generalization claim on 57 sites with the sensor-only model
- No imputation artifacts

The downside: 37 folds instead of 57. But for the specific question "do GAGES-II features add predictive value in LOGO," 37 folds is adequate.

**My recommendation: Option (c), with one addition.** For the 20 non-GAGES-II sites, retrieve what you can from NLDI (even partial — drainage area, elevation, a few land cover metrics). Create a "basic attributes" feature set (5-8 features) that is available for ALL 57 sites, and a "full attributes" feature set (44 features) for the 37 GAGES-II sites. Run three models:
1. Sensor-only, 57 sites
2. Sensor + basic attributes, 57 sites
3. Sensor + full GAGES-II attributes, 37 sites

This gives you a clean ablation ladder.

**Action item on the NLDI degradation:** The fact that NLDI is returning non-JSON is a problem. File it, try again in a week. If it stays broken, use the drainage area + elevation + HUC already in your site catalog as the "basic attributes" set. Do not block on it.

---

## 3. Feature Selection: The 44 GAGES-II Columns

**Severity: IMPORTANT**

### Redundant features (remove or merge)

With only 37 sites, you have a features-to-sites ratio of 44:37. That is dangerously high even for CatBoost. Some specific problems:

1. **NLCD land cover (8 columns: FOREST, CROPS, PASTURE, DEV, PLANT, WATER, SNOWICE, BARREN, SHRUB):** These sum to ~100%. They are perfectly multicollinear. CatBoost can handle this technically, but with 37 sites, having 8+ near-collinear features means the model can split on any of them interchangeably, which destroys SHAP interpretability. **Reduce to 3-4:** FOREST, CROPS+PASTURE (combine as "agriculture"), DEV, and let the remainder be implicit. Or use PCA on the land cover block and keep 2-3 components.

2. **Temperature trio (T_AVG, T_MAX, T_MIN):** Highly correlated. Keep T_AVG and T_MAX-T_MIN (range, which captures continentality). Drop T_MIN.

3. **Hydrologic soil groups (HGA, HGB, HGC, HGD):** Sum to ~100%, same collinearity issue as NLCD. Reduce to HGA + HGD (the extremes — well-drained vs. poorly-drained). Or encode as a single weighted index: `soil_index = 1*HGA + 2*HGB + 3*HGC + 4*HGD`.

4. **Elevation trio (ELEV_MEAN, ELEV_MIN, ELEV_MAX):** Keep MEAN and RELIEF = MAX - MIN. Drop the individual min/max.

5. **Dam features (NDAMS_2009, MAJ_NDAMS_2009, STOR_NOR_2009):** Three dam metrics for 37 sites. Most sites probably have 0 dams, creating near-zero-variance features. Check the distribution. If >60% of values are zero, reduce to a single binary "has_major_dam" or keep only STOR_NOR_2009 (storage is more physically meaningful than count).

### After pruning, target ~20-25 features.

That gives you a 25:37 ratio, which is still high but manageable with CatBoost's regularization. With 44 features on 37 sites, you are basically fitting one parameter per site, which is overfitting by definition in LOGO (each test fold is one site).

### Missing features worth adding

- **DRAIN_SQKM** — you already have this in site_catalog. Make sure it is in the feature set. Drainage area is the single most important catchment predictor for sediment and nutrients.
- **Population density or urban intensity** — if NPDES_MAJ_DENS is your only anthropogenic feature, you are underweighted on point sources. Check if GAGES-II has a population density column.
- **Tile drainage or agricultural management index** — important for nitrate in Midwest agricultural watersheds. GAGES-II may not have this. Flag for future.

### CLASS and AGGECOREGION

These are categorical. CLASS is the GAGES-II hydrologic disturbance classification (Ref/Non-ref). AGGECOREGION is a nominal ecoregion label. CatBoost handles categoricals natively, which is fine, but:
- CLASS has only 2 levels — include it, it is cheap.
- AGGECOREGION may have 10+ levels. With 37 sites, some levels will have 1-2 sites. CatBoost will overfit to rare categories. Either merge rare categories (group all ecoregions with <3 sites into "Other") or encode as a hierarchical feature (Omernik Level I instead of Level II).

---

## 4. Per-Parameter Site Sets vs. 34-Site Intersection

**Severity: IMPORTANT**

This is straightforward. **Use parameter-specific site sets for training. Use the 34-site intersection for cross-parameter comparison only.**

Here is why:

- **Training:** Each parameter model should use every available site. The TP model should train on 50 sites, not 34. You are throwing away 16 sites of TP data (and the samples at those sites) for no statistical benefit. CatBoost does not care that site X has TP but not TDS. Each model is independent.

- **Evaluation:** When you want to compare "is TP easier to predict than TDS?", you need the same test sites. Otherwise differences in R² could be due to different site pools rather than parameter difficulty. For this comparison, report results on the 34-site intersection.

- **For the paper:** Report two tables:
  - Table 1: Per-parameter LOGO results using all available sites (50/48/38/46 sites). This is your best estimate of real-world performance.
  - Table 2: Cross-parameter comparison on the 34-site intersection. This answers "which parameters are hardest to predict cross-site?"

- **For prediction chains (SSC→TP, Temp→DO):** The chain can only operate at sites where both the predictor and target exist. The 34-site intersection is the natural evaluation set for chains. But train the chain's component models on their full site sets.

**One nuance:** The sites that have TDS (38) but not TP are probably different hydrogeologically from those that have TP (50) but not TDS. This is not random missingness — it reflects what each USGS Water Science Center chose to monitor. Be aware of this in your discussion. The 34-site intersection may not be representative of the broader population of USGS sites.

---

## 5. Censoring / Non-Detect Handling

**Severity: MINOR (mostly fine, one exception)**

DL/2 substitution is adequate for censoring rates <10%. Your TP and TDS numbers are clean. But:

- **Nitrate at 10.3% average with one site at 80.5%:** That 80.5% site is useless for nitrate modeling — it is basically a flag that says "nitrate is always below detection here." Drop it from the nitrate model entirely. For the remaining sites at 10.3% average, DL/2 is borderline. I would flag this in the paper's methods and run a sensitivity analysis: compare DL/2 vs. DL/sqrt(2) vs. Kaplan-Meier imputation on the 5 sites with highest censoring rates. If R² does not change by more than 0.02, DL/2 is fine and you move on.

- **Orthophosphate at 9.8% average:** Borderline. Same recommendation — run sensitivity on the worst sites. The 12/46 sites with >10% censoring are your risk. If those 12 sites cluster in a particular ecoregion (low-phosphorus bedrock areas), the censoring is informative and DL/2 is actively wrong (it creates a false floor that does not exist). Check whether the high-censoring sites share geological characteristics.

---

## 6. Summary of Action Items

| # | Severity | Action |
|---|----------|--------|
| 1 | CRITICAL | Use Option (c) for GAGES-II: evaluate catchment features on 37-site subset only. Build 3-tier ablation (sensor-only 57, sensor+basic 57, sensor+full 37). |
| 2 | IMPORTANT | Prune GAGES-II features from 44 to ~20-25. Merge collinear land cover, soil groups, temperature, elevation. Check dam feature variance. |
| 3 | IMPORTANT | Train each parameter on its own full site set. Use 34-site intersection ONLY for cross-parameter comparison table. |
| 4 | IMPORTANT | Set minimum 30 samples per site for LOGO evaluation. Report both weighted and unweighted metrics. Bootstrap CIs on fold-level results. |
| 5 | MINOR | Drop the 80.5% censored nitrate site. Run DL/2 sensitivity analysis on top-5 censored sites per parameter. |
| 6 | MINOR | Check if high ortho-P censoring sites share geology — if yes, censoring is informative and DL/2 is biased. |
| 7 | MINOR | Merge rare AGGECOREGION categories (<3 sites → "Other"). |

---

## 7. One Thing I Want to See Before Training Starts

Before you train a single multi-parameter model, produce this diagnostic: **a sample count heatmap** (sites x parameters, colored by log(n_samples), with GAGES-II match status as a row annotation). This one plot will immediately reveal:
- Which sites are data-rich vs. data-poor
- Whether GAGES-II coverage correlates with sample richness (if it does, the 20 missing sites are probably also data-poor, and the 37-site subset is biased toward well-monitored sites)
- Whether any site is an outlier that should be investigated before it contaminates training

This takes 20 minutes to build and saves weeks of debugging mysterious model behavior later. Do it first.
