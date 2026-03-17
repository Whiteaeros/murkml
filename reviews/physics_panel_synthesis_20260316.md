# Physics & Design Panel Synthesis

Written 2026-03-16. All four panelists completed Phase 1 independent reviews.

---

## Parameter Selection (Vasquez + Torres)

**Core 5 parameters (confirmed by both chemistry and regulatory):**
1. SSC — proof of concept, done
2. Total Phosphorus — largest TMDL impairment category nationally, binds to sediment
3. Nitrate+Nitrite — drinking water MCL, nutrient TMDLs
4. Dissolved Oxygen — aquatic life standard, well-understood physics
5. TDS — near-linear with conductance, irrigation/mining regulatory driver

**Extension:** Specific conductance at ungauged sites, pH as secondary outputs

**Exclude:** E. coli, metals, alkalinity, individual ions, BOD/COD

**Species-level (Vasquez):**
- SSC never TSS (Gray et al. 2000)
- Nitrate+nitrite, not total nitrogen
- Total phosphorus primary, orthophosphate secondary (enforce TP >= ortho-P)
- Evaporative TDS (pcode 70300), not calculated sums

---

## Architecture (Nakamura)

- **Stay with CatBoost.** Do not switch to neural networks. Gradient boosting dominates on tabular data with <20K samples (Grinsztajn et al. 2022, NeurIPS).
- **Multi-target: independent models first, then prediction chain** (SSC->TP because phosphorus binds to sediment, Temperature->DO because temp controls saturation). NOT a shared-backbone neural network.
- **Ablation test required (Krishnamurthy):** Prove the chain beats independent models before keeping it.

---

## Physics Constraints — Tiered (Nakamura + Vasquez)

**Tier 1 (implement now, zero architecture change):**
- Log-transform targets (enforces non-negative)
- DO saturation from Benson & Krause 1984 as a derived feature
- CatBoost monotone_constraints where appropriate
- Post-hoc output clipping

**Tier 2 (moderate effort):**
- SC-TDS proportionality (k = 0.55-0.75, geology-dependent, Hem 1985) as soft penalty
- TP >= orthophosphate constraint
- SSC->TP prediction chain at high flows
- Physics-derived features (DO% saturation, log turbidity, seasonal encoding)

**Tier 3 (later, maybe never):**
- Custom loss functions
- Neural network architectures
- Mass balance enforcement

**Do NOT enforce globally:** Turbidity-SSC monotonicity (grain size varies across sites)

**90% of the physics-guided benefit comes from Tiers 1-2.**

---

## Statistical Methods (Krishnamurthy)

**Non-detects:** DL/2 substitution is defensible if censoring rates are <10%. Document censoring rates per parameter first. Run sensitivity analysis (DL/2 vs DL/sqrt(2)) before investing in custom loss functions. Never compute R-squared on substituted censored test values.

**Prediction uncertainty:** Upgrade from raw quantile regression to Conformalized Quantile Regression (CQR) via the MAPIE Python library. Near-drop-in upgrade with finite-sample coverage guarantees. Current 80% intervals are undercovering (~60-70% actual coverage).

**Sampling bias:** Dominant bias is flow-condition heterogeneity — some sites oversample storms, others undersample them. Correct with inverse-probability weighting by flow quantile (CatBoost supports sample_weight natively). Stratify all metrics by flow condition.

**Multi-target validation:** Three levels: (1) marginal accuracy per parameter, (2) joint prediction quality via residual correlation, (3) ablation comparing multi-target vs independent. The ablation is the most important — proves the design earns its complexity.

---

## Regulatory Reality (Torres)

- **Position as screening tool** — achievable tolerances: +/-50% SSC loads, +/-40-50% TP, +/-30% nitrate, +/-0.5 mg/L DO, +/-20% TDS
- **Benchmark is USGS site-specific surrogate regressions** (R-squared 0.6-0.9), not lab data
- **Output concentration time series with prediction intervals** — let users compute loads (C x Q)
- **Trust barriers (ranked):** (1) black-box opacity, (2) uncalibrated uncertainty, (3) no institutional credibility, (4) "does it work in my watershed?", (5) tool complexity
- **Adoption path:** Researchers first -> pilot with state agency -> slow practitioner diffusion

---

## Open Questions Remaining

1. Exact prediction chain order and which links add value (needs ablation testing with data)
2. Geology-dependent SC-TDS k values — how to determine per-site without manual lookup
3. Whether censoring rates for nutrients are low enough for DL/2 or need Tobit approach
4. Optimal flow-quantile weighting scheme (needs experimentation)
5. Whether orthophosphate data is available at enough sites to enforce TP >= ortho-P

---

## Confirmed Equations for Physics Layer

| Constraint | Equation | Citation | Type | Conditions |
|-----------|----------|----------|------|-----------|
| DO saturation | Complex nonlinear f(T, P) | Benson & Krause 1984 | Thermodynamic | Always valid |
| Non-negative concentrations | C >= 0 | Physical law | Thermodynamic | Always valid |
| SC-TDS proportionality | TDS = k * SC, k = 0.55-0.75 | Hem 1985 | Empirical-universal | k varies by geology |
| TP >= orthophosphate | TP >= ortho-P | Mass balance | Thermodynamic | Always valid |
| DO <= ~130% saturation | Soft cap | Empirical | Empirical-conditional | Supersaturation in productive streams |
| Turbidity-SSC monotonicity | DO NOT ENFORCE | Rivera audit | — | Breaks across sites (grain size) |
