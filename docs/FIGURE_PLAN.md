# murkml Figure Plan

Master list of proposed figures, expert reviews, consensus, and visual design guidelines.
Generated 2026-03-31 from 3 independent expert reviews + design research.

**Companion file:** [scientific_figure_design_guide.md](scientific_figure_design_guide.md) — detailed WRR specs, color palettes, Python templates.

---

## Expert Panel

| Expert | Background | Perspective |
|--------|-----------|-------------|
| **Dr. Catherine Marsh** | 32yr WRR reviewer, sediment transport, Colorado State | "What will a hydrology reviewer demand?" |
| **Dr. Amir Tehrani** | ML evaluation, DeepMind/NCAR, NeurIPS + WRR | "What will survive rigorous statistical review?" |
| **Priya Sato** | Data viz designer, NASA Goddard / The Pudding | "What will be understood, shared, and beautiful?" |

---

## Consensus: Final Figure List

### Main Text (10 figures)

| Priority | ID | Name | Marsh | Tehrani | Sato | Notes |
|----------|----|------|-------|---------|------|-------|
| 1 | **NEW-P1** | Hero Figure (3-panel composite) | — | — | Proposed | Graphical abstract. The gap / the model / the adaptation. |
| 2 | **19** | Aggregate vs Per-Site R2 | #3 | Cut (rhetorical) | #2 | **DISAGREEMENT** — Tehrani says rhetorical, Marsh+Sato say essential. Keep but use neutral title. | KEEP IT
| 3 | **2** | Adaptation Curve + site trajectories | #2 | #2 | #3 | All 3 agree. Add individual site lines (Tehrani), temporal split panel, N=1-5 inset (absorbs Fig 27). |
| 4 | **NEW-A** | Study Area + Site Map | #1 | — | — | Marsh: "disqualifying without it." Two panels: locations + performance. |
| 5 | **1** | Observed vs Predicted (log-log) | #5 | #4 | #12 | All agree. Hexbin density (Sato), holdout only (Marsh), log-log with marginal densities. |
| 6 | **6** | CatBoost vs OLS Head-to-Head | #6 | #5 | #10 | All agree. Site-by-site scatter at N=10, above diagonal = CatBoost wins. |
| 7 | **4** | Disaggregated Performance Heatmap | #8 | #9 | — | Marsh+Tehrani agree. Sato suggests dot plot instead of heatmap. Use CIs (Tehrani). | I would like to compare the two. 
| 8 | **NEW-P4** | Physics Wall (annotated error landscape) | — | — | #4 | Replaces Figs 8+22. SSC on x-axis, pct error on y-axis, 35K points with running median, 3 annotated physics zones. |
| 9 | **7** | External NTU Validation | #11 | #6 | #7 | All agree. Zero-shot vs N=10, by organization. Be honest about -46% bias and UMC failure. |
| 10 | **12** | Bayesian Shrinkage Visualization | #9 | #11 | #6 | All agree. 3-4 sites at N=2,5,10 showing zero-shot / raw local / shrunk. |

### Supplementary (12 figures)

| Priority | ID | Name | Marsh | Tehrani | Sato | Notes |
|----------|----|------|-------|---------|------|-------|
| 11 | **3** | Per-Site R2 Distribution (CDF) | — | #1 | #2 (via 19) | Essential. CDF at N=0,5,10 with fraction<0 annotated. |
| 12 | **NEW-B** | SSC/Turbidity Joint Distribution | #4 | — | — | Marsh: "reader needs to see the data before trusting the model." |
| 13 | **5** | First Flush Event Traces | #7 (implied) | — | #9 | 3-4 holdout sites with CQR ribbons. Include one failure. |
| 14 | **15** | Site-Level Rating Curves | #7 | — | — | 6 sites spanning geology spectrum (Marsh: 12, Tehrani: 6, Sato: 6). Log-log with model overlay. |
| 15 | **16** | Slope Gallery by Lithology | — | #12 | — | Ridge plot (Sato) colored by lithology. Add slope vs watershed characteristic scatter (Marsh). |
| 16 | **NEW-C** | Box-Cox Transform Justification | #12 | — | — | 3 panels: raw, log1p, Box-Cox 0.2 distributions. |
| 17 | **26** | Adaptation Surprise Plot | — | #7 | #15 | Zero-shot R2 vs delta-R2, colored by site characteristic. Quadrant labels. |
| 18 | **NEW-G** | Load Estimation Comparison | #10 | — | — | Cumulative loads: bcf_mean vs bcf_median vs OLS for 4-6 sites. Marsh: "the practical application." |
| 19 | **13+31** | CQR Calibration + Fan Plot (combined) | #13 | #15 | #14 | Calibration diagonal + 2-3 event time series with 50/90% ribbons. |
| 20 | **38** | Temporal Stability Check | #14 | #10 | — | First-half vs second-half R2 scatter with 1:1 line. |
| 21 | **14** | Residual Structure + Q-Q Plot | — | #14 | — | Tehrani: add Q-Q panel and residuals vs time. |
| 22 | **9** | SHAP Beeswarm (top 10) | — | — | — | Standard, expected. Limit to top 10, annotate physical meaning. |

### Dashboard Only (7 figures)

| ID | Name | Source | Notes |
|----|------|--------|-------|
| **NEW-P2** | Data Journey Sankey | Sato | 860 sites narrowing to 254, interactive hover |
| **NEW-P3** | Site Personality Cards | Sato | Baseball-card style per-site navigation |
| **NEW-P5** | Before/After Animation | Sato | Dots morph from zero-shot to adapted |
| **NEW-P6** | Geography of Difficulty (bivariate choropleth) | Sato | Performance x data density on CONUS map |
| **25** | Before/After Site Gallery (static version of P5) | All | 2x2 grid: best/modest/none/degradation |
| **18** | Hysteresis Loops | All | CW/CCW/linear triptych with time-color arrows |
| **NEW-D** | Representativeness CDFs | Marsh | Training sites vs national population |

### Cut or Deferred

| ID | Name | Verdict | Why |
|----|------|---------|-----|
| 8 | Error by SSC range (box plots) | **Merged into P4** | Redundant with Physics Wall |
| 10 | Geology/method disaggregation | **Deferred** | 2/3 experts keep, but covered by Fig 4 heatmap | If there are multiple options, I'd like to see them compared. 
| 11 | Spatial map (standalone) | **Merged into NEW-A** | Study area map absorbs this |
| 17 | SSC/turb ratio heatmap | **Cut** | All 3: unreadable at 254 sites |
| 20 | Failure mode taxonomy | **Deferred** | Good concept but needs principled taxonomy (Tehrani) |
| 21 | Correlation matrix | **Cut** | All 3: use ranked bar or text instead |
| 22 | Error by SSC annotated | **Merged into P4** | Same as Fig 8 |
| 23 | Spatial error map (two panel) | **Merged into NEW-A** | Two-panel in study area figure |
| 24 | Bayesian weight curve | **Keep in methods text** | Small enough to embed; not standalone figure |Just make a figure of this please, don't do different things or it will get forgotten. 
| 27 | "Death of OLS" zoom | **Merged into Fig 2** | Inset on adaptation curve |
| 28 | 2D PDP plots | **Deferred** | Tehrani: use ALE plots instead. Sato: cut entirely |
| 29 | SHAP waterfall | **Deferred to supplement** | Marsh: "tutorial material." Sato: use horizontal bars |
| 30 | Feature contribution by regime | **Deferred to supplement** | Interesting if pattern holds, not main text |
| 32 | Interval width vs error | **Deferred to supplement** | Diagnostic, covered by Fig 13 |
| 33 | Coverage by characteristics | **Cut** | Sato: "a table, not a figure" |
| 34 | Asymmetric intervals | **Cut** | All 3: too niche |
| 35 | Interval sharpness | **Cut** | All 3: methods paper, not hydrology |
| 36 | Site clustering dendrogram | **Cut** | Marsh+Tehrani: sensitive to parameters, uninformative |
| 37 | Residual autocorrelation | **Promote to NEW-A-supp** | Tehrani: CRITICAL for CI validity. Report in text + supplement |
| 39 | Feature knockout grid | **Cut** | All 3: requires new model runs, ablation covers it |

---

## Disagreements Requiring Your Decision

### 1. Figure 19: "Aggregate metrics are misleading"
- **Marsh (#3):** "One of the most important figures in the paper. Challenges the reporting standard of every ML paper in hydrology."
- **Tehrani (Cut):** "The title is rhetorical. Same information is in Figure 3. Making a separate figure with an editorial title will irritate reviewers."
- **Sato (#2):** "The most powerful finding in the project. Instantly understood."
- **My recommendation:** Keep it, neutral title ("Pooled vs. Site-Level Performance"). The concept is too important to lose; the rhetoric is the problem, not the figure.
- see my edit above

### 2. Effective sample size / autocorrelation
- **Tehrani:** Calls this a "time bomb" — must be a main-text figure with corrected CIs.
- **Marsh:** Agrees it matters but says supplement is fine.
- **Sato:** Cut (report in text).
- **My recommendation:** Address in supplement with a figure showing lag-1 distribution + effective N ratios. Mention in main text. Tehrani is right that reviewers will catch it, but a full main-text figure may be overkill.
- I dont even know what this means 
### 3. Figure 15: Site-level rating curves — how many sites?
- **Marsh:** 12 sites (span geology spectrum)
- **Tehrani:** 6 max
- **Sato:** 6 (2x3 grid)
- **My recommendation:** 6 in supplement, 2-3 examples in main text within the hero figure. THIS ONE

### 4. Load estimation figure (NEW-G)
- **Marsh (#10):** "If you cannot estimate loads accurately, the model has limited value."
- **Tehrani:** Not mentioned.
- **Sato:** Not mentioned.
- **My recommendation:** Include in supplement. Marsh is right that sediment hydrologists care about loads, but it's a supporting figure, not core narrative.    I will be doing this later. It just takes time. I'm still waiting on this model to finish. 

---

## Figures Proposed by Experts (NEW)

### From Dr. Marsh (Hydrology)
| ID | Name | Verdict |
|----|------|---------|
| NEW-A | Study Area + Site Map | **Main text #4** |
| NEW-B | SSC/Turbidity Joint Distribution | **Supplement #12** |
| NEW-C | Box-Cox Transform Justification | **Supplement #16** |
| NEW-D | Representativeness CDFs | **Dashboard** |
| NEW-E | Temporal Coverage Timeline | **Deferred** (good for dashboard) |
| NEW-F | Residuals vs Omitted Covariates | **Deferred** (supplement if space) |
| NEW-G | Load Estimation Comparison | **Supplement #18** |
| NEW-H | Moran's I / Variogram | **Deferred** (text mention + supplement) |   What is this? 

### From Dr. Tehrani (ML Evaluation)
| ID | Name | Verdict |
|----|------|---------|
| NEW-TA | Effective Sample Size Disclosure | **Supplement** (see disagreement #2) |
| NEW-TB | Skill Score vs Baselines | **Incorporate into Fig 4** |
| NEW-TC | Calibration Plot (predicted vs observed quantiles) | **Incorporate into Fig 13** |
| NEW-TD | Adaptation curve with per-site trajectories | **Incorporated into Fig 2** |
| NEW-TE | Train/Holdout Distribution Comparison | **Supplement** |
| NEW-TF | R2 vs Sample Size Per Site | **Supplement** |
| NEW-TG | Weighted vs Median R2 Disclosure | **Incorporate into Fig 19/3** |
| NEW-TH | Temporal Holdout Validation | **Critical gap** — need to verify if data exists |

### From Priya Sato (Visualization)
| ID | Name | Verdict |
|----|------|---------|
| NEW-P1 | Hero Figure (3-panel composite) | **Main text #1** |
| NEW-P2 | Data Journey Sankey | **Dashboard** |
| NEW-P3 | Site Personality Cards | **Dashboard** |
| NEW-P4 | Physics Wall (annotated error landscape) | **Main text #8** |
| NEW-P5 | Before/After Animation | **Dashboard** |
| NEW-P6 | Geography of Difficulty (bivariate choropleth) | **Dashboard** |
| NEW-P7 | Residual Signature (small multiples by failure mode) | **Deferred** (replaces Fig 14 if taxonomy is principled) |

---

## Visual Design System

### Color Palette
```
Categorical (Okabe-Ito):
  #E69F00  orange
  #56B4E9  sky blue
  #009E73  bluish green
  #F0E442  yellow
  #0072B2  blue
  #D55E00  vermillion
  #CC79A7  reddish purple
  #999999  gray

Sequential: viridis (performance metrics)
Diverging: RdBu centered at 0 (R2 maps)

Consistency rule:
  Saturated color = model predictions
  Dark gray #333333 = observed data
  Light gray #CCCCCC = reference lines
```

### Typography (WRR/AGU)
- Font: Source Sans Pro or Helvetica
- Axis labels: 8-9 pt at final print size
- Tick labels: 7-8 pt
- Panel labels: 10 pt bold, top-left, outside axes
- Minimum readable: 7 pt (6 pt for sub/superscripts)

### Sizing
- WRR single column: 84 mm wide
- WRR full width: 174 mm wide
- Max height: 228 mm
- Export: Vector (PDF/SVG). Rasterize only dense scatter layers.

### Layout Rules
1. Shared axes across panels — always
2. 3-5 mm gaps between panels
3. Left = before/baseline, Right = after/improved
4. Direct label lines, minimize legends
5. One figure, one message

### Key Principles
- Test all figures with Color Oracle for accessibility
- Print at actual size before submitting
- Never use dual y-axes, 3D, pie charts, or rainbow colormaps
- 35K-point scatters must use hexbin/contour density encoding
- Log-scale axes must be clearly labeled with minor gridlines

**Full design guide:** [scientific_figure_design_guide.md](scientific_figure_design_guide.md)

---

## Generation Priority Order

**Phase 1 — Core paper figures (generate first):**
1. Fig 2 (Adaptation curve with site trajectories + temporal panel)
2. Fig 19 (Pooled vs per-site performance)
3. NEW-P4 (Physics Wall)
4. NEW-A (Study area map)
5. Fig 1 (Obs vs pred, hexbin log-log)

**Phase 2 — Supporting paper figures:**
6. Fig 6 (CatBoost vs OLS)
7. Fig 4 (Disaggregated heatmap)
8. Fig 7 (External NTU)
9. Fig 12 (Bayesian shrinkage)
10. NEW-P1 (Hero figure — composite of above)

**Phase 3 — Supplement (after CQR finishes):**
11. Fig 3 (Per-site R2 CDF)
12. Fig 13+31 (CQR calibration + fan)
13. Fig 5 (First flush traces with CQR)
14. Fig 38 (Temporal stability)
15. Fig 15 (Rating curves)
16. NEW-B (Joint distribution)
17. NEW-C (Box-Cox justification)
18. NEW-G (Load estimation)
19. Fig 26 (Adaptation surprise)
20. Fig 14 (Residuals + Q-Q)
21. Fig 9 (SHAP beeswarm)
22. NEW-TA (Effective sample size)

**Phase 4 — Dashboard:**
23-29. P2, P3, P5, P6, 25, 18, NEW-D

---

## Generation Status

| # | Figure | Status | Script | Notes |
|---|--------|--------|--------|-------|
| All | — | Not started | — | Awaiting user approval of this plan |
