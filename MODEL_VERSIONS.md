# murkml Model Version History

## Naming Convention

Format: `murkml-{version}-{descriptor}`

- **Version**: Sequential number (1, 2, 3...)
- **Descriptor**: Short tag for what changed

Each entry records: training config, dataset, performance, and what changed from the previous version. This is the single source of truth for "which model had which numbers."

---

## Version History

### murkml-1-initial
- **Date:** 2026-03-24
- **Training sites:** 102 (pre-expansion, GAGES-II bug present)
- **Samples:** ~5,000
- **Features:** 99
- **Transform:** log1p
- **CV:** LOGO
- **R²(log):** 0.721
- **R²(native):** 0.295
- **Holdout R²:** Not evaluated
- **Notes:** First working model. GAGES-II attributes were silently destroyed by prune_gagesii() bug — all watershed features were zeros/NaN. Model was effectively sensor-only despite having 99 "features."

### murkml-2-pruned
- **Date:** 2026-03-27
- **Training sites:** 243 (266 total, 23 holdout)
- **Samples:** 12,253
- **Features:** 37 (after ablation from 102 → 62 → 37)
- **Transform:** log1p
- **CV:** LOGO (233 folds)
- **R²(log):** 0.725
- **R²(native):** 0.361
- **Holdout split:** data/train_holdout_split.parquet (266-site version, now overwritten)
- **Notes:** Feature reduction improved native R² from 0.295 to 0.361. Expert panel converged on 37 features. Bug fixes applied (dedup key, precip leakage, weather tz, QC codes). Linear interpolation for turbidity alignment. Collection method and sensor calibration features added.

### murkml-2-holdout
- **Date:** 2026-03-27
- **Same model as murkml-2-pruned, evaluated on holdout sites**
- **Holdout sites:** ~23 sites (from 266-site split)
- **Zero-shot R²(native):** 0.699
- **Zero-shot slope:** 0.719
- **Site adaptation (5 samples):** R² improved significantly
- **Notes:** The famous zero-shot number. BUT: holdout split is lost (overwritten when dataset expanded to 396 sites). Cannot reproduce this exact evaluation. Holdout set was small (~23 sites). May not be comparable to v4-holdout (76 sites).

### murkml-3-expanded
- **Date:** 2026-03-28 morning
- **Training sites:** 346 (383 total)
- **Samples:** 14,632
- **Features:** 37
- **Transform:** log1p
- **CV:** LOGO
- **R²(log):** 0.735
- **R²(native):** 0.154
- **Notes:** Added 117 sites via QC approval code fix. Log R² improved but native R² collapsed catastrophically. "Smoking Gun" analysis proved original 243 sites also degraded (0.361 → 0.189) — model structure changed, not just dilution from new sites. Triggered the transform/loss function investigation.

### murkml-4-boxcox (current)
- **Date:** 2026-03-28/29
- **Training sites:** 357 (396 total, 76 holdout) — fewer than 383 because 39 sites lack StreamCat
- **Samples:** 32,046
- **Features:** 44 (41 numeric + 3 categorical)
- **Transform:** Box-Cox lambda=0.2
- **Monotone:** ON (turbidity_instant, turbidity_max_1hr)
- **CV:** LOGO (357 folds)
- **R²(log):** 0.718
- **R²(native):** 0.290
- **KGE:** 0.767
- **Alpha:** 0.882
- **RMSE:** 165.6 mg/L
- **Bias:** 19.4%
- **BCF:** 1.364 (Snowdon)
- **Trees:** median 344
- **Holdout split:** data/train_holdout_split.parquet (396-site version, 320 train / 76 holdout)
- **Saved model:** data/results/models/ssc_C_sensor_basic_watershed.cbm (487 trees, lambda=0.2 confirmed)
- **Notes:** Box-Cox 0.2 chosen from 24-experiment transform sweep. Raw SSC ruled out. KGE eval_metric tested (no improvement). Lambda confirmed via fine sweep at 0.18-0.20.

### murkml-4-holdout
- **Date:** 2026-03-29
- **Same model as murkml-4-boxcox, evaluated on 76 holdout sites**
- **Holdout sites:** 76 (from 396-site split)
- **Holdout samples:** 5,847
- **Zero-shot R²(native):** 0.472
- **Zero-shot KGE:** 0.454
- **Zero-shot slope:** 0.578
- **Site adaptation (10 samples):** R²=0.457 (barely recovers to zero-shot level)
- **Site adaptation (20 samples):** R²=0.487
- **Notes:** Adaptation with <10 samples HURTS performance (correction overfits). 2-parameter linear correction in Box-Cox space is too aggressive with few samples. Panel recommends shrinkage estimator. Temporal adaptation even worse (seasonal bias in first-N samples).

---

## Key Comparisons

### Why murkml-2-holdout (0.699) and murkml-4-holdout (0.472) are NOT directly comparable:
1. Different holdout sites (23 vs 76 sites)
2. Different holdout split (266-site split vs 396-site split)
3. Different training data (12K vs 32K samples, 243 vs 357 training sites)
4. Different transform (log1p vs Box-Cox 0.2)
5. Different feature count (37 vs 44)
6. Old holdout split is lost — cannot re-run v2 on the new holdout

### To make a fair comparison, need:
- Run log1p model on same 396-site dataset with same 76-site holdout
- OR: run Box-Cox model on 266-site dataset (if it can be reconstructed)

---

## What Changed Between Versions

| From → To | What changed | Effect on R²(native) |
|---|---|---|
| v1 → v2 | Fixed GAGES-II bug, 102→37 features, 102→266 sites | 0.295 → 0.361 (+0.066) |
| v2 → v3 | Added 117 sites (QC fix), same features | 0.361 → 0.154 (-0.207) COLLAPSE |
| v3 → v4 | Box-Cox 0.2, more samples (discrete turb), 37→44 features | 0.154 → 0.290 (+0.136) |
