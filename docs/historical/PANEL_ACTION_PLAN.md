# Panel Action Plan — 2026-03-29

Derived from expert panel deliberation. Items numbered to match the panel briefing discussion.

---

## 1. 1-Parameter Bayesian Site Adaptation

**What:** Replace the broken 2-parameter linear correction (slope + intercept) with a single additive bias correction in Box-Cox space using Bayesian shrinkage.

**How:**
- Prior: delta ~ N(0, 0.360²), derived from MERF intercept random effect variance
- For N calibration samples: compute mean residual (observed_bc - predicted_bc), then shrink toward zero
- Posterior delta = (N / (N + k)) * mean_residual, where k is the shrinkage constant (start with k = 5, tune empirically)
- At N=0: delta = 0 (pure zero-shot, no change)
- At N=1: delta = (1/6) * residual (mostly trust the global model)
- At N=20: delta = (20/25) * mean_residual (mostly trust the data)

**Evaluation:** Run on same 76 holdout sites with N=0,1,2,3,5,10,20. Success = monotonically non-decreasing curve.

**Estimated time:** 2-3 hours implementation + testing

---

## 3. SGMC Geology Investigation

**What:** Download SGMC (State Geologic Map Compilation) detailed lithology and test if it predicts the turbidity-SSC slope better than StreamCat's aggregated geology.

**How:**
- Download SGMC geodatabase from USGS (doi:10.5066/F7WH2N65)
- Spatial join: for each of our 396 sites, extract the bedrock lithology class at that point. Watershed boundaries need to be utilized to give percentages of lithology
- Also compute: % of upstream watershed in each lithology class (if catchment polygons available)
- Correlate lithology with per-site log-log slope (we have these in site_turb_ssc_params.parquet)
- If Spearman rho > 0.15 for any lithology feature, add to model and test with GKF5

**Estimated time:** Half day (download + spatial join + correlation analysis)

---

## 4. Audit "Unknown" Collection Method Sites

**What:** 37% of catastrophic sites have collection_method = "unknown." Try to recover the actual method from other metadata fields.

**How:**
- For each "unknown" site, query NWIS for the site description and equipment metadata
- Check WQP fields: SampleCollectionMethod/MethodName, ActivityTypeCode, MonitoringLocationTypeName
- Check if the site has ISCO autosampler mentioned in site documentation
- If method can be inferred, update collection_method in the paired dataset
- Re-evaluate: do formerly-catastrophic sites improve when their method is known?

**Estimated time:** 3-4 hours (query + manual review for ambiguous cases)

---

## 5. Check if MERF Slope Random Effect is Bimodal

**What:** The per-site turbidity-SSC slope has std=0.179. If the distribution has two humps (e.g., fine-sediment sites vs coarse-sediment sites), a mixture model with 2-3 types would outperform a single global model.

**How:**
- Load per-site slopes from site_turb_ssc_params.parquet (already computed, 304 sites)
- Plot histogram and kernel density estimate
- Run Hartigan's dip test for unimodality
- If bimodal: fit a 2-component Gaussian mixture, label each site as type A or type B
- Check if the types correlate with any site characteristic (geology, collection method, HUC2)

**Estimated time:** 30 minutes (pure analysis, no retraining)

---

## 6. Verify Residual Normality in Box-Cox Space

**What:** Confidence intervals assume residuals are approximately normal. If they're skewed or heavy-tailed in Box-Cox space, our uncertainty estimates will be wrong.

**How:**
- Load LOGO CV predictions (32,003 samples)
- Compute residuals in Box-Cox space: residual = y_true_bc - y_pred_bc
- Plot histogram, QQ plot
- Run Shapiro-Wilk or Anderson-Darling test
- If non-normal: identify the shape (skewed? heavy-tailed? bimodal?) and assess impact on confidence intervals
- If heavy-tailed: consider using quantile regression or CQR (MAPIE) for proper intervals

**Estimated time:** 30 minutes (pure analysis)

---

## 7. Temporal Non-Stationarity Check

**What:** Test whether the turbidity-SSC relationship drifts over time at individual sites. Important for knowing whether a deployed model needs periodic recalibration.

**How:**
- For each training site with 20+ samples: sort by time, train on first 80%, predict last 20%
- Compare temporal-split R² to random-split R² at the same sites
- If temporal R² is significantly lower: the relationship is drifting
- Identify which sites drift most and check for causes (land use change, sensor replacement, dam operations)

**Estimated time:** 1-2 hours (need to implement temporal split evaluation)

---

## 8. Residual Distribution at Individual Observation Level

**What:** What does the prediction error look like for a single measurement? Is it ±50 mg/L? ±500%? Does it depend on the SSC level?

**How:**
- Load LOGO CV predictions
- Compute absolute error and percentage error for each of the 32,003 predictions
- Plot error vs true SSC (heteroscedasticity check)
- Compute error quantiles at different SSC levels (low/mid/high/storm)
- This directly answers: "how wrong could any single prediction be?"

**Estimated time:** 30 minutes (pure analysis)

---

## 9. Instrument Model Differences Within FNU

**What:** All sites use pCode 63680 (FNU infrared), but different instrument models (Hach TU5300, YSI EXO2, etc.) have different optical paths. turb_source has SHAP=0.000 which is suspicious.

**How:**
- Query NWIS for instrument metadata at our 396 sites
- Check if instrument model is available in site description or equipment fields
- If recoverable: add as a feature and test whether it explains slope variation
- Also verify that turb_source (continuous vs discrete) is coded correctly in the pipeline — SHAP=0.000 might mean it's a constant at Tier C, not that it doesn't matter

**Estimated time:** 2-3 hours (query + analysis)

---

## 10. Are Catastrophic Sites Truly Unpredictable?

**What:** Sites with R²<-1 might be genuinely unpredictable (signal too weak), or they might have small SSC ranges where even small absolute errors produce terrible R².

**How:**
- For each of the 51 catastrophic sites: compute the residual variance (how far off are predictions in absolute mg/L?)
- Compare to the site's SSC range
- A site with residuals of ±10 mg/L and SSC range of 20-40 mg/L looks catastrophic (R²<0) but the absolute error is small
- A site with residuals of ±500 mg/L is genuinely broken
- Classify catastrophic sites as "low signal" (small range, small errors) vs "genuinely wrong" (large errors)

**Estimated time:** 30 minutes (pure analysis)

---

## 11. Anchor Site Identification

**What:** Identify which training sites contribute most to holdout performance. Some sites teach the model transferable physics, others add noise.

**How (cheap empirical approach first):**
- Use the D-redo data: we have 5 random sets of 100 sites with different performance levels. run more of these sets to improve prediction. 
- For each of the 287 training sites: count how many of the high-performing random sets (top 2) it appeared in vs low-performing sets (bottom 2)
- Sites that consistently appear in winning sets are candidate anchors
- Validate with a targeted test: train on just the top 50 candidate anchors, measure holdout R²

**How (definitive but expensive):**
- Leave-one-site-out influence: for each of 287 sites, remove it from training, retrain (2 min), measure holdout R² change
- Sites where removal hurts holdout = anchors. Sites where removal helps = noise.
- 287 retrains × 2 min = ~10 hours. Could parallelize.

**Estimated time:** Cheap approach: 2 hours. Full LOO: 10 hours (can run overnight).

---

## 12. Mixed-Effects with Categoricals (MERF Done Right)

**What:** MERF showed the concept works (random effects capture site heterogeneity) but lost because it dropped categoricals. Implement the mixed-effects EM loop ourselves around standard CatBoost with full categorical support. is this method actually the best?

**How:**
- Implement the EM algorithm manually (~100 lines):
  - E-step: estimate per-site random effects (intercept + slope) from residuals
  - M-step: retrain CatBoost on data with random effects subtracted out
  - Repeat 10 iterations
- CatBoost keeps all 44 features including categoricals
- Random effects: per-site intercept + slope on turbidity_instant
- Predict new sites: random effects = 0 (same as current zero-shot)

**Estimated time:** Half day implementation + testing

---

## 13. Staged Adaptation (Intercept-Only → Full)

**What:** Use intercept-only correction for N<10 samples, switch to intercept+slope at N≥10. This is part of item #1 but worth calling out separately.

**How:**
- Integrated into the Bayesian adaptation implementation (#1)
- N<10: single delta parameter with shrinkage
- N≥10: add slope correction with its own shrinkage (prior from MERF slope std=0.179)
- N≥10 also requires samples spanning a range of turbidity values (Gutierrez: "at least 3 above the 75th percentile")

**Estimated time:** Included in #1

---

## 14. Three-Tier Product Framing

**What:** Define clear accuracy tiers so users know what to expect.

**How:**
- Screening grade (zero-shot, N=0): "Order-of-magnitude estimates. Use for ranking, screening, and identifying sites needing attention."
- Monitoring grade (N=10+ spanning conditions): "Within factor-of-2 for most conditions. Suitable for operational monitoring."
- Publication grade (N=30+ with full range): "Meets USGS surrogate model standards. Suitable for load calculations and reporting."
- Each tier has specific accuracy metrics derived from our holdout evaluation
- Implemented as a metadata field on predictions: confidence_tier = "screening" | "monitoring" | "publication"

**Estimated time:** 1-2 hours (define thresholds from data, implement tier assignment)

---

## 15. Train Physics on Best Data, Variability from All Data

**What:** Gutierrez/Morales idea — use D1's 96 highest-quality sites for the fixed effects (core physics), but include all 287 sites for random effects estimation (understanding variability).

**How:**
- This is a modification of #12 (manual MERF with categoricals)
- M-step (CatBoost training): use only D1 sites (96 highest quality)
- E-step (random effect estimation): use all 287 sites
- The fixed effects learn clean physics, the random effects capture messy reality

**Estimated time:** Included in #12, just a data selection change

---

## Execution Order — Parallel Tracks

### Phase 0: Start downloads and long-running tasks FIRST
These are network-bound or compute-bound. Start them before anything else so they run in the background.

- **#3 SGMC download** — large geodatabase download. Agent starts this immediately, then does spatial analysis while other tasks run.
  - Note: We have NHDPlus COMIDs but no watershed polygons locally. Agent must research whether point-lookup or watershed-percentage approach is better, and determine what additional data is needed.
- **#11 Anchor sites (10 more random sets)** — 10 additional random-100-site model trains (~20 min compute). Start running, analyze when done.
- **#4 Unknown methods audit** — NWIS API queries for 51+ catastrophic sites. Network-dependent, start early.

**AFTER Phase 0 tasks complete:** Run `/record-experiment` for #11 (anchor sites) and #4 (method audit). Update MODEL_VERSIONS.md. Commit all downloaded data and results.

### Phase 1: Quick analyses (parallel, ~1 hour total)
All pure analysis on existing data. Run in parallel. Results inform Phase 2.

- **Agent A: #5 + #6** — Bimodal slope check + residual normality. These are related (both about distribution shape).
- **Agent B: #8 + #10** — Individual error distribution + catastrophic site classification. These are related (both about understanding where errors are).
- **Agent C: #9** — Instrument model check. Requires NWIS metadata query + analysis of turb_source SHAP=0.000.

**AFTER Phase 1:** Run `/record-experiment` for each analysis. Update MODEL_VERSIONS.md with findings. Commit.

### Phase 2: Core implementation (depends on Phase 1 results)
- **#1 + #13: Bayesian adaptation** — depends on #5 (if bimodal, may need 2-component adaptation instead of single prior) and #6 (residual distribution shape affects shrinkage prior).
- **#12 + #15: Manual MERF with categoricals** — agent must first research whether the EM approach is the best method for mixed-effects gradient boosting, then implement the winner. Depends on #5 (bimodal check may suggest mixture model instead).

**AFTER each Phase 2 implementation:** Run `/record-experiment` for every model trained. Save models with versioned names. Update MODEL_VERSIONS.md. Commit immediately — do NOT batch commits.

### Phase 3: Integration
- **#7: Temporal stationarity** — run after core implementation to check if improved model is temporally stable.
- Combine SGMC features (#3) with winning model from Phase 2.
- Re-run adaptation curve with all improvements.

**AFTER Phase 3:** Run `/record-experiment` for every result. Final commit with complete MODEL_VERSIONS.md update.

### DATA CAPTURE RULE (applies to ALL phases)
**Every agent must, before reporting completion:**
1. Save any model files with versioned names (never overwrite)
2. Record results in MODEL_VERSIONS.md results table
3. Git add + commit with descriptive message
4. Verify the commit landed by checking git log

**No analysis or experiment is "done" until it is recorded and committed.** If an agent forgets, the first thing the next agent does is go back and record it.

### Deferred:
- #2: Paper — not now
- #14: Three-tier framing — after adaptation works
- #16: MVP packaging — not yet
- #17: User guidance — not yet
