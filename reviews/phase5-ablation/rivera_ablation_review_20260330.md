# Phase 5 Ablation Review -- Dr. Marcus Rivera

**Date:** 2026-03-30
**Reviewer:** Dr. Marcus Rivera (ret. USGS Water Resources Division, 20 years sediment transport & surrogate regression)
**Document reviewed:** PANEL_BRIEFING_ABLATION_20260330.md + gemini_ablation_review.md (full data)
**Scope:** Ablation results, proposed group tests, 8 panel questions, external validation, weather features, feature finalization criteria

---

## 1. Reaction to Ablation Results

### What surprises me

**The GKF5 vs holdout discrepancy is the most important finding in this entire document.** Features that look neutral or even harmful on cross-validated training data turn out to be critical for holdout generalization. This is not a bug -- it is the signature of features that help the model generalize to *unseen sites* rather than fit *seen sites* better. GKF5 uses GroupKFold by site, so it should capture this. The fact that it does not means your 5 folds are not diverse enough -- 357 sites split 5 ways gives ~71 sites per fold, but if the folds are not balanced by geology, climate zone, and turbidity range, you can get folds that are too similar to each other. I would want to see the fold composition before trusting GKF5 for any feature selection decision.

**turb_Q_ratio at -0.102 dMedR2 on holdout vs +0.004 on GKF5 is extraordinary.** That is the single most important feature for generalization while being invisible to cross-validation. More on this below.

**pct_eolian_fine at +0.056 when dropped is a large positive signal.** Dropping one feature improves median site R2 by 5.6 percentage points. That is not noise -- something about this feature is actively confusing the model on holdout sites. My guess: eolian fine deposits have a very skewed geographic distribution (concentrated in the Great Plains and Columbia Plateau), so the model learns a split that works for training sites in those regions but fails to transfer. This is a classic curse of rare-but-informative features in tree models.

**The early stopping bug catch was critical.** The fact that initial ablation showed catastrophic collapse on *every* feature drop, and a red-team review traced it to 500-iteration no-early-stopping memorization -- that is exactly the kind of silent methodological error that invalidates entire papers. Good catch. But it also tells me you need to be suspicious of every model comparison that was run before this fix. Were the group ablation results (legacy geology, human land, weather) run with the corrected pipeline? I assume yes, but confirm.

### What concerns me

**The weather group result is the most dangerous finding in this briefing.** Dropping weather improves median R2 by +0.062 but destroys first flush R2 by -0.089 and extreme event R2 from 0.109 to 0.005. If you had only looked at median R2, you would have dropped weather and shipped a model that is useless for the events that produce 80% of annual sediment load. This is not hypothetical -- I have seen published models that optimized median metrics and completely missed storm transport. The disaggregated diagnostics saved you here. Never trust aggregate metrics alone.

**28 SGMC features is too many for 396 sites.** Many of these lithology subtypes occur in fewer than 10 training sites. The model is learning site-specific quirks disguised as geology. The fact that 6 of the top 12 "drop helps" features are SGMC confirms this. You need aggressive pruning of rare SGMC categories or aggregation into parent types.

**The underprediction bias persists.** Baseline shows -37.6% underprediction at extreme events. The weather group was the only thing partially mitigating this (dropping weather worsens underprediction to only -31.8% ... wait, that actually improves it). Let me re-read. The briefing says dropping weather changes underprediction from -37.6% to -31.8%, which is a reduction in magnitude. But it also destroys Top 1% R2 from 0.109 to 0.005. So the model without weather underpredicts less on average but explains almost zero variance in the extremes. That means it is just predicting a flat value near the median for extreme events. This is worse, not better, even though the bias number looks better.

---

## 2. Evaluation of Proposed Group Ablation Tests (A-D)

### Test A (SGMC subgroups): Yes, this is the right approach.
A5 and A6 are the critical experiments. If dropping all 28 SGMC and keeping old StreamCat geology performs similarly or better on holdout, you have your answer -- SGMC is overfitting. A1-A4 are informative but secondary. I would add:
- **A7: Keep only the 3-5 SGMC features that individually help on holdout** (unconsolidated_sedimentary_undiff, igneous_volcanic, metamorphic_volcanic, and maybe 1-2 others). This is a targeted pruning that preserves the useful geology signal while removing noise.

### Test B (combined drop of individually harmful features): Essential.
This is the most important test in the batch. If you drop all 12 individually-harmful features simultaneously and get a compound improvement anywhere close to the sum of individual improvements (+0.306 if fully additive), you have a much leaner model. If the compound effect is much smaller (say +0.05), then the individual ablation results are interacting and you cannot trust greedy single-feature selection. **Run this test first. It determines whether the rest of the ablation strategy is valid.**

### Test C (precipitation decomposition): Good but incomplete.
- C1-C3 are the right experiments.
- **Add C4: Drop all precipitation features but keep discharge-based features (flush_intensity, Q_7day_mean, rising_limb).** The hypothesis is that discharge already integrates precipitation, so precip features are redundant for explaining SSC. If the model retains extreme-event skill without precip but with discharge features, you know the weather signal is coming through Q, not through rainfall directly.

### Test D (old geology vs SGMC replacement): Fine.
D1 and D2 are reasonable. D2 (keep only 5 helpful SGMC) is the one I'd bet on. But this should wait until after A5/A6/A7 tell you whether SGMC is worth keeping at all.

### What is missing

**Test E: Interaction features.** turb_Q_ratio is by far the most important feature. It is the only feature that captures the relationship between two sensor readings -- turbidity per unit discharge. You should test:
- E1: Drop turb_Q_ratio but add turbidity_instant * discharge_instant (product instead of ratio)
- E2: Drop turb_Q_ratio and DO_sat_departure (both interaction features) to see if the model can learn these interactions on its own from the raw inputs

**Test F: Categorical encoding sensitivity.** collection_method, turb_source, and sensor_family together account for -0.158 dMedR2 (sum of individual drops). These are not physical features -- they are metadata about how the data was collected. This is a red flag for a model that is supposed to generalize. Test:
- F1: Drop all three categorical metadata features simultaneously.
If the model collapses, you have a problem: the model is learning *sampling protocol effects* not *physics*. That will not transfer to new deployments where collection methods are different.

**Test G: Minimum-sample SGMC threshold.** For each SGMC feature, compute how many training sites have >1% of that lithology in their watershed. Any SGMC feature present in fewer than 20 sites should be dropped or merged with a parent category. This is not an ablation test -- it is a prior constraint that prevents overfitting by construction.

---

## 3. Answers to the 8 Panel Questions

### Q1: Are these the right group ablation tests, or are we missing important groupings?

The proposed A-D are reasonable. Missing: (1) all categorical metadata features as a group (Test F above), (2) interaction features as a group (Test E above), (3) rare-SGMC pruning by sample threshold (Test G above). Also missing: a test of the sensor hardware block (sensor_offset, days_since_last_visit, sensor_family) as a group -- these are deployment-specific features that will not be available for new sensors at new sites.

### Q2: Should we keep ALL weather features despite the median R2 penalty?

**Yes. Unambiguously yes.** The weather features cost you +0.062 on median R2 -- a metric dominated by low-variability sites where the model barely works anyway. They buy you first flush skill and extreme event skill. In sediment transport, the events that matter are the ones that move sediment, and those are the ones weather features serve. If you have to justify this to a reviewer, show the disaggregated results. Any competent hydrologist will accept the tradeoff.

However, I would investigate whether you can keep precip_48h and precip_7d while dropping precip_30d (which individually helps when dropped, +0.012 dMedR2). The 30-day window is likely too long to be causally linked to any individual sediment event -- it is more of a soil moisture proxy, and you already have that signal through baseflow_index and Q_7day_mean.

### Q3: Human infrastructure block -- how to weigh the tradeoff?

The human infrastructure block (agriculture_pct, developed_pct, dam_storage_density, etc.) hurts median R2 by -0.022 but the briefing says it helps extreme events. The underprediction goes from -37.6% to -53.5% when you drop it -- that is a massive increase in bias during the events that produce the loads. **Keep it.** These features encode information about sediment supply and transport capacity that the model cannot infer from turbidity alone. Developed watersheds have flashier hydrographs. Dams trap sediment and change the SSC-turbidity relationship downstream. Agricultural land has higher erodibility. All of this is real physics operating at scales the sensor cannot see.

### Q4: Is turb_Q_ratio importance (-0.102) suspicious? Could it leak information?

**Not leakage, but worth verifying.** turb_Q_ratio = turbidity_instant / discharge_instant. The target is SSC. Turbidity is already a direct input. The ratio turb/Q is a legitimate physical feature -- it captures sediment supply independent of transport capacity. A high turb/Q ratio means more sediment per unit flow, which typically indicates bank erosion, land disturbance, or supply-limited conditions. A low turb/Q ratio means dilution-dominated conditions.

This is NOT leakage because:
1. The ratio does not contain SSC or any derivative of SSC.
2. Both turbidity and discharge are measured before SSC is sampled.
3. The feature has clear physical interpretation in sediment transport theory.

However, I would worry about it being a proxy for *which site this is* rather than a generalizable physical signal. If certain sites consistently have high turb/Q ratios (e.g., small flashy urban streams) and the model uses that to identify site type, it is acting as a hidden site identifier. Test this by computing the within-site variance of turb_Q_ratio vs the between-site variance. If the between-site variance dominates, the feature is mostly encoding site identity. If within-site variance is substantial (meaning the ratio changes meaningfully during events at a given site), it is encoding real hydrologic dynamics.

**The fact that GKF5 says turb_Q_ratio is neutral (+0.004) while holdout says it is critical (-0.102) is actually reassuring** -- it means the feature's value comes from helping the model generalize to unseen sites, not from improving fit on seen sites. That is the pattern you want for a feature encoding real physics.

### Q5: Should we test keeping ONLY the 5 helpful SGMC features?

**Yes -- this is Test A7 in my recommendations above.** The 28 SGMC features include many rare lithology types that occur in a handful of sites. The model is almost certainly overfitting on these. Keep the ones that represent common, physically meaningful distinctions:
- unconsolidated_sedimentary_undiff (alluvial vs bedrock -- the most fundamental distinction for sediment transport)
- igneous_volcanic (high turbidity per unit SSC due to fine ash-derived particles)
- metamorphic_volcanic (similar optical properties)
- Maybe 1-2 others that survive the sample-size threshold test

Everything else should be dropped or merged.

### Q6: Re-introduced features (do_instant, ph_instant, etc.) all failed. Should we accept this or test in groups?

**Accept it and move on.** You tested 10 re-introductions and none helped on GKF5. The gemini review confirms do_instant was the best at +0.003, which is noise. These features were dropped for a reason in earlier phases. Re-introducing them costs you model complexity and parsimony with no demonstrated benefit. Do not test them in groups -- if none helps individually, a group test is unlikely to find synergies and adds complexity to an already large experimental matrix.

One exception: if you later substantially change the feature set (e.g., drop 15+ features from the current 72), it would be worth a quick re-screen of the top 3 candidates (do_instant, ph_instant, discharge_instant) against the new reduced model. Feature interactions change when you remove other features.

### Q7: What other group ablation tests would you run?

See Tests E, F, and G in Section 2 above. In addition:

**Test H: Site-static vs event-dynamic feature split.** Separate your features into:
- Static (do not change within a site): all watershed, SGMC, categorical, longitude
- Dynamic (change with each sample): turbidity, discharge, weather, hydrograph position, seasonality

Drop all static features and see how the model performs. If it holds up reasonably well, it means the model is primarily a turbidity-to-SSC converter that uses dynamic hydro context, and the watershed features are secondary. If it collapses, the watershed features are doing critical site-characterization work. This decomposition tells you whether the model is fundamentally a "sensor model" or a "landscape model" -- a distinction that matters for deployment messaging and for knowing where the model will fail.

### Q8: At what point do we stop ablating and declare the feature set final?

You stop when ALL of the following are true:

1. **No single remaining feature improves holdout median R2 by more than +0.02 when dropped.** You are currently far from this -- pct_eolian_fine at +0.056 is a clear signal that pruning is incomplete.

2. **The compound drop test (Test B) has been run and the interaction effects are understood.** If compound effects are non-additive, you need a second round of single-feature ablation on the reduced model.

3. **No SGMC feature with fewer than 20 training sites remains in the model.** Rare features are overfitting liabilities.

4. **The disaggregated diagnostics (first flush, Top 1%, underprediction) are stable across the remaining feature set.** Specifically: first flush R2 stays above 0.35 and Top 1% R2 stays above 0.05.

5. **External validation performance (NTU data) does not degrade by more than 0.03 R2 at N=10 compared to the current 0.501.** The external validation is the ultimate test of generalization. If your feature pruning hurts external performance, you are overfitting to the USGS holdout.

6. **You have run one final "confirmation ablation" on the candidate-final feature set** -- a single-feature ablation of every remaining feature with the final model to verify that nothing changed due to interactions with dropped features.

In my experience, you are probably 2 rounds of ablation away from a final feature set. This round to prune the clearly harmful features (Test B) and SGMC (Test A5/A6/A7), and one more round to clean up whatever emerges from the reduced model.

---

## 4. External Validation (R2=0.501 at N=10 on foreign NTU data)

This is the most important number in the entire briefing and I want to make sure you understand what it means and what it does not mean.

### What it means

**The model transfers across sensor technologies.** NTU and FNU measure turbidity using different optical geometries (90-degree nephelometry vs backscatter). The fact that 10 NTU samples are enough to adapt the model to NTU sensors and achieve R2=0.501 means the Bayesian adaptation is correcting for systematic sensor differences. This is a genuine contribution -- most published surrogate regressions are locked to a single sensor type.

**R2=0.501 at N=10 is operationally meaningful for screening.** It means: given 10 paired grab samples at a new NTU site, the model explains half the variance in SSC. That is not good enough for regulatory reporting (you need R2 > 0.8 for TMDL load estimates), but it IS good enough for:
- Identifying sites that need more monitoring
- Preliminary load screening during permit review
- Prioritizing where to deploy dedicated SSC sensors
- Providing a prior for Bayesian calibration of a future per-site model

### What it does not mean

**Do not claim this is "operational-grade" for NTU sites.** R2=0.501 means the model misses half the variance. The 95% prediction interval at any given point is going to be enormous. For a regulatory submission, an inspector would reject this. For a screening tool marketed to consultants and small water districts who currently have *nothing*, it is valuable.

**The N=0 result (R2=-0.216) is a deployment risk.** Without any local calibration, the model is worse than guessing the mean. This means you CANNOT deploy murkml as a "plug and play" tool for NTU sensors -- you MUST require a minimum calibration dataset. I would set the floor at N=5 (R2=0.378 random split, 0.280 seasonal) and warn users that fewer samples produce unreliable results.

**The gap between random (0.501) and temporal (0.370) splits at N=10 tells you the adaptation is fragile.** Random split lets calibration samples span the full range of conditions. Temporal split forces calibration to be sequential -- more realistic for deployment, where you collect your first 10 samples over a few weeks or months. The 0.13 gap means the model's adaptation depends on seeing diverse conditions, which takes time. Tell users: "collect calibration samples across at least 2 seasons before trusting the adapted model."

### Deployment implication

The external validation result is strong enough to support a product claim like: "murkml provides SSC estimates at any turbidity-monitored site with as few as 10 calibration samples, across both FNU and NTU sensor types." That is a defensible statement. But add the caveat: "Performance improves with calibration samples spanning the full range of flow conditions at the site."

---

## 5. Should We Keep All Weather Features Despite the Median R2 Penalty?

I addressed this in Q2 above, but let me be more specific.

**Keep precip_48h and precip_7d. Test dropping precip_30d.**

The physical reasoning:
- **precip_48h** captures the direct rainfall-runoff connection. Sediment mobilization from hillslopes and channel banks is driven by rainfall intensity over hours to days. This is a causal feature.
- **precip_7d** captures antecedent moisture. Saturated soils produce more runoff and more erosion per unit rainfall. This is a well-established hydrologic mechanism.
- **precip_30d** is a long memory that overlaps heavily with baseflow_index and Q_7day_mean. It is more likely capturing seasonal or regional climate patterns than event-specific sediment dynamics. The holdout ablation shows dropping it improves median R2 by +0.012, which is small but consistent with it adding noise.

If Test C3 (keep 48h + 7d, drop 30d) retains the extreme-event skill of the full weather block, that is your answer. If dropping 30d hurts extreme events, keep all three.

---

## 6. What I Would Need Before Declaring the Feature Set Final

In priority order:

1. **Test B results (compound drop of 12 harmful features).** If compound improvement is >+0.05 on holdout median R2 without degrading first flush or extreme events, execute the pruning.

2. **Test A5/A6/A7 results (SGMC pruning).** I expect A7 (keep only 3-5 helpful SGMC) to be the winner. The 28-feature SGMC block is almost certainly overfitting.

3. **External validation on the pruned model.** Re-run the NTU adaptation curve after pruning. If R2 at N=10 drops below 0.45, you pruned too aggressively.

4. **Variance decomposition of turb_Q_ratio** (within-site vs between-site) to confirm it is encoding dynamics, not site identity.

5. **Sample-size audit of all remaining SGMC and watershed features.** Any feature where fewer than 20 training sites have non-trivial values (>1% for percent-type features, >0 for density features) should be flagged for removal.

6. **One final confirmation ablation** on the candidate-final reduced feature set to check for interaction effects with dropped features.

7. **Stability check:** retrain the final model 5 times with different random seeds and verify that the feature importance rankings are stable (Spearman rho > 0.85 between runs). If a feature's importance bounces around, it is not robust.

---

## Summary

The ablation work is solid. The early stopping bug catch alone justifies the effort. The key findings are:

- **The GKF5 vs holdout discrepancy is real and important.** Never use GKF5 alone for feature selection. Always validate on true holdout.
- **Weather features are essential.** The median R2 penalty is acceptable because the alternative is a model that cannot predict the events that matter.
- **SGMC needs aggressive pruning.** Keep 3-5 physically meaningful lithology features, drop the rest.
- **turb_Q_ratio is legitimate but needs the variance decomposition check.**
- **The external validation at R2=0.501 (N=10, NTU) is a strong deployment result** that supports a real product claim with appropriate caveats.
- **You are approximately 2 ablation rounds from a final feature set.** Run Test B first -- it determines whether greedy single-feature ablation is valid for this model.

---

*Dr. Marcus Rivera*
*Retired, USGS Water Resources Division*
*20 years sediment transport & surrogate regression*
