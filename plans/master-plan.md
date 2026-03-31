# murkml — Master Plan (Updated 2026-03-30 evening)

## Current State: v9-final-72feat (CHECKPOINT)

**Model:** 254 training sites, 72 features, Box-Cox λ=0.2, LOGO CV MedSiteR²=0.335
**Vault:** 36 clean sites, MedSiteR²=0.486 (one shot, never repeat)
**External:** 260 NTU sites, R²=0.43 at N=10 calibration samples
**Feature set:** LOCKED at 72 (unanimous panel decision, p=0.81 no improvement from pruning)

## Environment

**Python:** `.venv/Scripts/python.exe` (UV, Python 3.12.9). NOT base conda.
**Split:** data/train_holdout_vault_split.parquet (284 train / 76 validation / 36 vault)
**Exclude:** data/exclude_sites_for_ablation.csv (112 sites: 76 validation + 36 vault)
**Training:** Always use --exclude-sites. Always run full eval suite.

## What's Done

- Phase 3: Pipeline fixes (Gemini bugs, SGMC, collection methods, staged Bayesian)
- Phase 4: Diagnostics (disaggregated, physics validation, external validation, eval refactor)
- Phase 5: Ablation (83 single + group + 5-seed stability → 72 features locked)
- v9 model trained, vault evaluated, external validated, checkpoint committed

## What's Next

### 1. Site Contribution Analysis
- 20 random subsets of 100 training sites, GKF5 scored
- Rank sites by win rate (how often they appear in above-median subsets)
- FULL EVAL SUITE on each subset model (not just aggregate metrics)
- Identify anchor sites (help generalization) vs noise sites (hurt)
- Use GKF5 CV performance only — no holdout/vault involvement in selection

### 2. Anchor Site Ablation
- Train models with/without identified anchor/noise sites
- FULL EVAL SUITE on each to understand WHY sites help or hurt
- Disaggregated analysis: do anchor sites improve specific geologies? specific HUC2 regions?
- This tells us about data quality, not model architecture

### 3. NTU Integration — DECIDED: Validation Only, Not Training
- Unanimous panel + Gemini: do NOT add NTU to training (sensor type confounded with era, zero temporal overlap)
- 3,646 USGS NTU-SSC pairs preserved as validation dataset
- 260 external NTU sites preserved for adaptation curve characterization
- Bayesian adaptation (R²=0.43 at N=10) is the correct path for NTU users
- +66% zero-shot bias is a feature for the paper (proves adaptation is necessary)
- See NTU_FINDINGS.md for full analysis and paper framing

### 4. Paper & Product (Phase 6)
- Three-tier product framing (screening/monitoring/publication grade)
- CQR uncertainty bounds (kurtosis=13.8 means Gaussian intervals lie)
- Paper 1: Cross-site SSC prediction + site adaptation
- Paper 2: Mixed-effects / physics-guided architecture
- Paper 3: Multi-parameter extension

## Key Rules

1. **EVERY model evaluation uses the full suite** — all modes, all metrics, disaggregated, physics, external
2. **NEVER overwrite model files** — versioned names, commit immediately
3. **NEVER use holdout/vault for feature decisions** — GKF5 only for selection
4. **Vault is ONE SHOT** — never touch the 36 sites again
5. **Save models with early stopping** — no 500-iteration overfit models
6. **Change one thing at a time** — isolate variables
