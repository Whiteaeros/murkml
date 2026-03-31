# Site Contribution Analysis — Detailed Plan

## Context

We want to know which of our 284 training sites help the model generalize and which ones hurt. The previous anchor analysis (50 sites beat 287) was invalidated by Gemini because it used holdout performance to select training data = data leakage.

This analysis uses ONLY training data (GKF5 CV) for site scoring. The 76 validation sites and 36 vault sites are never involved in any way.

## Data Bleed Prevention

### What we must NOT do:
1. **Never evaluate subset models on validation or vault sites during selection.** If we pick "good" training sites based on how they improve holdout performance, we're leaking holdout information into training data selection.
2. **Never use the vault sites at all.** They remain sealed.
3. **Never let a site appear in both the training subset AND the evaluation metric.** GKF5 handles this — each site's predictions come from a fold where it was held out.
4. **Never use external validation data for site selection.** External data is for final reporting only.

### What we CAN do:
- Score sites by how they affect GKF5 median per-site R² on the TRAINING data
- Each GKF5 fold holds out ~20% of training sites — predictions for every training site come from a model that didn't see that site
- This is clean: the evaluation metric (per-site R² from out-of-fold predictions) never uses data the model trained on

## Method: Out-of-Bag Random Subset Scoring

### The Key Insight (Gemini review)

GKF5 on a subset measures whether the subset's sites are EASY TO PREDICT, not whether they HELP predict other sites. A subset of 100 clean, linear sites will score high on GKF5 without teaching the model anything about complex rivers.

The correct approach: **out-of-bag evaluation.** Train on 100 sites, predict the OTHER 184 sites that were excluded. The only way a subset scores high is if its 100 sites teach the model physics that transfers to 184 unseen rivers.

### Step 1: Generate 50 random subsets (stratified)

For each of 50 seeds:
- Sample 100 sites from the 284 training sites
- Stratify by HUC2 region (proportional representation)
- Stratify by collection method (proportional)
- Record which sites are in each subset

**Why 100?** Gives 100 train / 184 test per subset. Enough training data for a functional model, enough test data for stable metrics.

**Why 50 subsets?** Each site appears ~18 times (100/284 × 50). With continuous scoring, 18 appearances is enough for a stable estimate. 20 subsets would give only ~7 appearances — too quantized.

**Why stratified?** Prevents accidental geographic or methodological bias in subsets.

### Step 2: Train and evaluate each subset (50 out-of-bag runs)

For each subset:
1. Train ONE CatBoost model on the 100 subset sites (with early stopping via GroupShuffleSplit validation, same as _save_quick_model)
2. Predict on ALL 184 EXCLUDED training sites using that model
3. Compute MedSiteR² on the 184 excluded sites — this is the subset's score
4. Also compute per-site R² for each of the 184 excluded sites
5. Save the model and per-site predictions

**This is NOT GKF5.** It's a single train + predict, much faster (~30s per subset vs ~2 min for GKF5). Total: 50 × 30s = ~25 min.

**Data bleed check:** The 100 training sites never appear in the evaluation. The 184 evaluation sites were never in that model's training data. The 76 validation + 36 vault sites are excluded from everything. Clean.

### Step 3: Score each site (continuous marginal contribution)

For each of the 284 training sites, compute:

**Score_i = mean(R²_with_i) - mean(R²_without_i)**

Where:
- R²_with_i = average out-of-bag MedSiteR² across all subsets that INCLUDED site i
- R²_without_i = average out-of-bag MedSiteR² across all subsets that EXCLUDED site i

If Score_i is positive: the model empirically performs better on unseen rivers when site i is in training. Site i teaches generalizable physics.

If Score_i is negative: site i injects noise that hurts predictions on unseen rivers.

**Why continuous, not binary win/lose?** Binary scoring on ~18 appearances is too quantized (win rates like 8/18=0.44 vs 10/18=0.56 look different but aren't). Continuous scoring uses the actual R² values, capturing magnitude not just direction.

### Step 4: Analyze site characteristics

For each site, we already have:
- SGMC lithology (dominant rock type)
- Collection method (auto_point, depth_integrated, grab, unknown)
- HUC2 region
- SSC variability (std)
- Sample count
- Sensor family
- Per-site turbidity-SSC slope

Correlate anchor score with these characteristics:
- Do noise sites cluster in specific geologies?
- Do noise sites have specific collection methods?
- Do noise sites have unusual SSC/turbidity relationships?
- Do noise sites have very few samples?

### Step 5: Validate anchor identification

Train TWO additional models on the TRAINING data only:
1. **Anchor model:** Train on top 50 anchor sites (highest scores)
2. **Anti-anchor model:** Train on bottom 50 noise sites (lowest scores)

Run GKF5 on both. Compare MedSiteR² to the full 284-site model.

**Also run the full evaluation suite (evaluate_model.py) on the validation set for these two models.** This is the ONE time we use validation for anchor analysis — but only AFTER selection is complete (selection used GKF5 only). The validation evaluation is for REPORTING, not for SELECTING.

### Step 6: Disaggregated analysis of anchor vs noise models

Using the full eval suite results from Step 5:
- Compare anchor model vs full model on each subgroup (geology, collection method, HUC2, etc.)
- Compare first flush, extreme event, hysteresis performance
- Identify: do anchor sites teach specific physics that noise sites dilute?

## Compute Budget

| Step | Experiments | Time each | Total |
|---|---|---|---|
| 2: Train 50 subsets (out-of-bag) | 50 single trains | ~30s | ~25 min |
| 5: Anchor + anti-anchor models | 2 trains + 2 full evals | ~3 min | ~6 min |
| **Total** | | | **~31 min** |

## Output Files

| File | Contents |
|---|---|
| data/results/site_contribution/subset_results.parquet | Per-subset GKF5 metrics |
| data/results/site_contribution/site_scores.csv | Per-site anchor scores, characteristics |
| data/results/site_contribution/anchor_model_eval/ | Full eval of anchor-50 model |
| data/results/site_contribution/noise_model_eval/ | Full eval of anti-anchor model |

## What This Tells Us

1. **Which sites to prioritize for data quality review** — noise sites may have data issues
2. **Whether site selection can improve the model** — if anchor-50 beats full-284 on GKF5
3. **What makes a site "anchor"** — physical characteristics that predict site usefulness
4. **Whether future data collection should be targeted** — collect at anchor-like sites, not random
5. **For the paper** — "the model benefits most from sites with X characteristics"

## What This Does NOT Tell Us

- This does NOT mean we should train the final model on only anchor sites. Site diversity matters for generalization (Experiment D proved ~200 sites is the sweet spot).
- The anchor scores are relative to the current feature set and model architecture. Different features might produce different anchors.
- Anchor analysis on 20 subsets has inherent variance — sites with few appearances (appeared in only 2-3 subsets) have unreliable scores.
