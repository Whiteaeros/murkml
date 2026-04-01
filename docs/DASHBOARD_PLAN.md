# murkml Dashboard Implementation Plan

*Marcus Reyes — dashboard architecture, 2026-03-31*

---

## 1. Framework Recommendation

### Top 3 Candidates

#### Option A: Observable Framework
- **What it is:** Static site generator by Mike Bostock (creator of D3). Markdown pages with embedded JavaScript. DuckDB-WASM queries parquet files directly in the browser. Python data loaders run at build time.
- **Parquet support:** Native. DuckDB-WASM reads parquet files client-side with SQL. This is its killer feature.
- **Static site / GitHub Pages:** Yes, generates a static `dist/` folder. Works on GitHub Pages with minor base-path config.
- **Static export for papers:** No built-in PNG/SVG export from the dashboard itself. You'd generate paper figures separately with matplotlib (which you need to do anyway for WRR).
- **Maintenance burden:** Low once built. No server, no Python runtime in production. Markdown files with JS snippets.
- **Load speed:** Excellent. DuckDB-WASM binary is ~5MB initial load, but subsequent queries are instant. Pages load in 1-3 seconds after first visit.
- **Mobile/tablet:** Good. Responsive by default. Observable Plot (the charting library) handles resize.
- **Learning curve:** STEEP if you don't know JavaScript. You're writing Observable Plot / D3 code, not Python. Data loaders can be Python, but all visualization is JS.
- **Claude Code compatibility:** Moderate. Claude can write Observable Plot code, but iteration is slower than Python because you can't run it inline — you need `npm run dev` in a terminal.

**Honest assessment:** This would produce the most impressive, fastest dashboard. But you'd be learning JavaScript visualization from scratch while also writing a paper. The DuckDB-WASM + parquet story is unbeatable for performance. If you had 3 months and no paper deadline, I'd pick this without hesitation.

#### Option B: Quarto Dashboard + Plotly
- **What it is:** Quarto (the academic publishing tool you may already know) has a dashboard layout mode. Write `.qmd` files with Python code cells. Plotly figures render as interactive HTML widgets. Static graphics from matplotlib also embed.
- **Parquet support:** Via Python (pandas/polars) at render time. No client-side parquet queries.
- **Static site / GitHub Pages:** Yes. `quarto render` produces a static HTML site. No server needed for Plotly widgets.
- **Static export for papers:** EXCELLENT. The same `.qmd` document can render to both dashboard HTML and paper-quality PDF/SVG via matplotlib. This is the only framework where your paper figures and dashboard figures share source code.
- **Maintenance burden:** Low-medium. Quarto is well-maintained (Posit/RStudio backs it). But Quarto versions sometimes break things, and the dashboard layout system is newer (v1.4+) with occasional rough edges.
- **Load speed:** Medium. Each page bundles all its Plotly JSON inline. With 5,829 readings and 76 sites, individual pages will be 2-8MB. Acceptable, but not as snappy as Observable.
- **Mobile/tablet:** Decent. Quarto dashboards are responsive, but complex multi-panel Plotly figures can be cramped on phones.
- **Learning curve:** LOW if you know Python. You're writing Python in code cells. Plotly syntax is well-documented. Quarto layout uses YAML headers.
- **Claude Code compatibility:** EXCELLENT. Claude can write Python Plotly code, run it, see the output, iterate. The feedback loop is tight.

**Honest assessment:** The pragmatic choice. You already need matplotlib for paper figures. Quarto lets you put Plotly interactive versions of those same figures into a dashboard with minimal extra work. The "dual export" story (paper PDF + interactive dashboard from the same source) is genuinely valuable for a solo researcher. It won't win design awards, but it will be done.

#### Option C: Evidence.dev
- **What it is:** "BI as code." SQL + Markdown. DuckDB backend queries parquet at build time, ships pre-computed results. Beautiful default charts.
- **Parquet support:** Native via DuckDB.
- **Static site / GitHub Pages:** Yes.
- **Static export for papers:** No. Not designed for scientific publication at all. No matplotlib integration.
- **Maintenance burden:** Low.
- **Load speed:** Excellent.
- **Learning curve:** Low-medium. SQL + Markdown. But charting is limited to Evidence's built-in components — no Plotly, no custom D3.
- **Claude Code compatibility:** Good for SQL, but you can't customize visualizations enough for scientific figures.

**Honest assessment:** Evidence is built for business dashboards, not science. The chart types are too limited. You can't do hexbin log-log scatter, SHAP beeswarms, or CQR ribbon plots with Evidence's built-in components. Disqualified.

#### Honorable Mentions (and why they lose)

- **Plotly Dash:** Requires a running Python server. Can't host on GitHub Pages (without hacks like Render/Railway free tier). Overkill for static data. I've built 6 Dash apps for scientists and 4 of them are dead because the server stopped.
- **Streamlit:** Same server problem. Streamlit Cloud free tier is unreliable. Not a static site.
- **Panel/HoloViews:** Can convert to WASM via `panel convert`, but the resulting bundles are 20MB+ and slow to load. The WASM conversion is still experimental. I've had it break on complex layouts.
- **Raw Plotly HTML files:** One self-contained HTML per figure works, but you lose navigation, shared filtering, and the "dashboard" experience. Fine for supplementary material, not for a companion site.
- **Jupyter Book / MyST:** Academic-focused but the dashboard layout story is weak. Better for narrative documents than exploratory dashboards.

### My Pick: Quarto Dashboard + Plotly (Option B)

**Reasoning:**

1. **You're writing a WRR paper.** The paper figures MUST be matplotlib/PDF. With Quarto, the same Python code that generates your paper figures can also produce Plotly interactive versions for the dashboard. One codebase, two outputs.

2. **You're a solo Python developer.** Observable Framework would require learning JavaScript visualization. That's a week of your time you don't have. Quarto lets you stay in Python.

3. **Claude Code can iterate on it.** I can write a Plotly figure, you can run `quarto preview`, see it, tell me what's wrong, and I can fix it. That loop doesn't work as well with Observable.

4. **GitHub Pages deployment is trivial.** `quarto render` → push `_site/` → done.

5. **Maintenance is near-zero.** Static HTML files. If Quarto disappears tomorrow, the rendered site still works.

6. **The data is small enough.** 76 holdout sites, 5,829 readings, 11K external samples. Plotly handles this without breaking a sweat. You don't need DuckDB-WASM's query engine for datasets this size.

**The one thing Observable does better:** If you want the site-level personality cards (NEW-P3) with instant filtering across 254 sites, Observable's client-side SQL would be smoother. But that's a dashboard-only figure and can be simplified or cut.

---

## 2. Architecture

### Data Flow

```
[parquet/JSON files in data/results/]
        │
        ▼  (build time: quarto render)
[Python code cells in .qmd files]
  - pandas reads parquet
  - computes any derived metrics
  - generates Plotly figures (interactive)
  - generates matplotlib figures (static, for paper export)
        │
        ▼
[_site/ directory — static HTML + JS + CSS]
        │
        ▼  (deploy: git push to gh-pages branch)
[GitHub Pages serves static files]
```

### Key Design Decisions

1. **All data processing happens at build time.** No client-side data loading. Plotly figures embed their data as JSON in the HTML. This means pages are self-contained and work offline.

2. **Shared Python module for figure generation.** A `_scripts/figures.py` module contains functions like `make_obs_vs_pred()`, `make_adaptation_curve()`, etc. Each function returns BOTH a Plotly figure and a matplotlib figure. The `.qmd` files call these functions.

3. **Paper figures are a separate render target.** `scripts/generate_paper_figures.py` imports the same functions but saves matplotlib output as PDF/SVG at WRR dimensions. The dashboard shows the Plotly versions.

4. **Data is pre-processed into a single `dashboard_data/` directory** at build time by a prep script. This avoids the dashboard code reaching into the raw data pipeline.

### File Structure

```
dashboard/
├── _quarto.yml              # Site config, navigation, theme
├── _scripts/
│   ├── figures.py           # Shared figure-generation functions
│   ├── data_prep.py         # Reads parquets, builds dashboard data
│   └── style.py             # Okabe-Ito palette, WRR rcParams, shared config
├── index.qmd                # Landing page — hero figure + key metrics
├── performance.qmd          # Model performance deep-dive
├── adaptation.qmd           # Bayesian adaptation story
├── sites.qmd                # Per-site explorer
├── external.qmd             # External NTU validation
├── diagnostics.qmd          # Physics, residuals, SHAP
├── supplement.qmd           # Supplementary figures (all of them)
├── about.qmd                # Methods summary, data sources, links
├── custom.scss              # Theme overrides
└── dashboard_data/          # Pre-processed data (git-ignored, built by prep script)
    ├── per_site.parquet
    ├── per_reading.parquet
    ├── external.parquet
    ├── ols_benchmark.parquet
    ├── shap_importance.parquet
    ├── site_metadata.json   # lat/lon, HUC, n_samples — needs to be built
    ├── adaptation_curves.json
    ├── physics_validation.json
    ├── bootstrap_ci.json
    └── disaggregated.parquet
```

### Data Prep Script

A `_scripts/data_prep.py` script runs before `quarto render` and:
1. Copies relevant parquets from `data/results/evaluations/` into `dashboard_data/`
2. Fetches site lat/lon from NWIS (or a cached lookup) for map figures
3. Merges per-site metrics with location data
4. Computes any derived columns needed by multiple figures
5. Writes a compact `site_metadata.json` with everything the map and site explorer need

This keeps the dashboard decoupled from the training pipeline.

---

## 3. Page Layout and Navigation

### Navigation Structure

```
[murkml] ─── Overview | Performance | Adaptation | Sites | External | Diagnostics | Supplement | About
```

Seven pages plus landing. Sidebar navigation on desktop, hamburger on mobile. Quarto handles this natively.

### Page Descriptions

#### Landing Page (`index.qmd`)
**Hero experience:** The first thing anyone sees is three numbers in value boxes:
- **254** training sites
- **0.41** median site R² (zero-shot)
- **0.49** median site R² (N=10 adapted)

Below that: the hero figure (NEW-P1) — three panels showing the gap, the model, and the adaptation. This is a static image (matplotlib, pre-rendered) because it's a composite figure that needs precise layout control.

Below the hero: a 2-sentence description of what murkml does, a link to the paper, and a "Start exploring" button pointing to the Performance page.

**Design principle:** Someone landing on this page should understand the project in 10 seconds.

#### Performance (`performance.qmd`)
Core model evaluation. Four figure sections:
1. Obs vs Pred (Fig 1) — interactive hexbin/scatter, log-log, hover shows site ID
2. Pooled vs Per-Site (Fig 19) — the "aggregate metrics lie" figure
3. Disaggregated Heatmap (Fig 4) — by collection method, SSC range, hydrology regime
4. CatBoost vs OLS (Fig 6) — site-by-site scatter at multiple N values

Each figure has a one-sentence caption and expandable "Details" accordion with full interpretation.

#### Adaptation (`adaptation.qmd`)
The Bayesian adaptation story. Three figure sections:
1. Adaptation Curve (Fig 2) — with individual site trajectories, temporal panel, N=1-5 inset
2. Bayesian Shrinkage Visualization (Fig 12) — 3-4 sites at N=2,5,10
3. Bayesian Weight Curve (Fig 24) — the shrinkage weight as a function of N (Kaleb's note: "just make a figure of this")
4. Adaptation Surprise Plot (Fig 26) — zero-shot vs delta-R² colored by characteristic

Interactive feature: dropdown to select split mode (random / temporal / seasonal) updates the adaptation curve.

#### Sites (`sites.qmd`)
Per-site explorer. This replaces the "Site Personality Cards" (NEW-P3) with something more practical:
1. CONUS map (NEW-A right panel) — sites colored by zero-shot R², click a site to select it
2. Selected site detail panel:
   - Obs vs pred scatter for that site
   - Adaptation trajectory (R² vs N)
   - Key metrics table
   - Rating curve overlay (Fig 15 — for selected site)
3. Site ranking table — sortable by any metric, searchable by site ID

This is the most interactive page. Plotly's click events + Quarto's OJS integration can handle the map-to-detail linking. If that proves too complex, fall back to a simple dropdown selector.

#### External (`external.qmd`)
External NTU validation. Two figure sections:
1. External scatter — observed vs predicted, colored by organization (Fig 7)
2. By-organization breakdown — small multiples or faceted scatter showing each org's performance
3. Honest disclosure of -46% bias and UMC failure

#### Diagnostics (`diagnostics.qmd`)
Physics and model internals. Five figure sections:
1. Physics Wall (NEW-P4) — SSC vs pct error with annotated zones
2. SHAP Beeswarm (Fig 9) — top 10 features
3. Residual Structure + Q-Q (Fig 14)
4. Temporal Stability (Fig 38) — first-half vs second-half R²
5. Box-Cox Transform Justification (NEW-C) — 3-panel distribution comparison

#### Supplement (`supplement.qmd`)
All supplementary figures in one scrollable page:
1. Per-Site R² CDF (Fig 3)
2. SSC/Turbidity Joint Distribution (NEW-B)
3. First Flush Event Traces (Fig 5) — will gain CQR ribbons later
4. Site-Level Rating Curves (Fig 15) — 6-site grid
5. Slope Gallery by Lithology (Fig 16)
6. CQR Calibration + Fan (Fig 13+31) — placeholder until CQR model finishes
7. Load Estimation (NEW-G) — placeholder until data exists
8. Before/After Site Gallery (Fig 25)
9. Hysteresis Loops (Fig 18)
10. Representativeness CDFs (NEW-D)

#### About (`about.qmd`)
- Project description and methodology summary
- Data sources and attribution (USGS, WQP, StreamCat, SGMC)
- Link to GitHub repo
- Link to paper (when published)
- Contact information
- Data Journey Sankey (NEW-P2) — how 860 discovered sites narrow to 254 training sites

---

## 4. Figure-by-Figure Implementation

### Legend
- **Library:** What renders the interactive version
- **Paper:** What renders the static paper version
- **Complexity:** Trivial (< 30 min) / Moderate (1-2 hrs) / Complex (2-4 hrs)

### Main Text Figures

| # | Figure | Library | Paper | Interactive Features | Data Source | Complexity |
|---|--------|---------|-------|---------------------|-------------|------------|
| NEW-P1 | Hero Figure (3-panel composite) | matplotlib static embedded as image | matplotlib | None — this is a composed static figure | Multiple JSONs | **Complex** — composite layout with precise alignment |
| 19 | Pooled vs Per-Site R² | Plotly | matplotlib | Hover shows metric values; toggle between weighted/median | `per_site.parquet`, `eval_summary.json` | **Moderate** |
| 2 | Adaptation Curve + trajectories | Plotly | matplotlib | Dropdown: split mode; hover shows site ID on trajectories; toggleable CI bands | `eval_summary.json`, `per_site.parquet` | **Complex** — many overlaid traces, inset panel |
| NEW-A | Study Area + Site Map | Plotly (scattermapbox) or Plotly (scattergeo) | matplotlib + cartopy | Hover shows site ID, n_samples, R²; click opens site detail; color = performance | `site_metadata.json` (needs lat/lon) | **Complex** — requires site location data build step |
| 1 | Obs vs Pred (log-log) | Plotly | matplotlib | Hover shows site ID, true/pred values; hexbin density coloring; toggle holdout/all | `per_reading.parquet` | **Moderate** |
| 6 | CatBoost vs OLS Head-to-Head | Plotly | matplotlib | Dropdown: N value (1,2,3,5,10,20); hover shows site ID; diagonal reference | `per_site.parquet`, `ols_benchmark_per_site.parquet` | **Moderate** |
| 4 | Disaggregated Performance Heatmap | Plotly heatmap | matplotlib (+ seaborn dot plot alternative) | Hover shows CI; toggle heatmap/dot-plot view (per Kaleb's note to compare both) | `disaggregated_metrics.parquet` | **Moderate** |
| NEW-P4 | Physics Wall | Plotly | matplotlib | Hover shows site ID and sample details; brush to select region; annotation boxes for 3 physics zones | `per_reading.parquet` | **Complex** — 5,829 points with running median + annotations |
| 7 | External NTU Validation | Plotly | matplotlib | Color by organization; hover shows org, site, values; toggle zero-shot vs adapted | `external_predictions.parquet` | **Moderate** |
| 12 | Bayesian Shrinkage | Plotly | matplotlib | Dropdown: select site; slider: N value; shows prior → posterior evolution | `eval_summary.json` + adaptation detail data | **Complex** — requires per-site adaptation trace data |

### Supplementary Figures

| # | Figure | Library | Paper | Interactive Features | Data Source | Complexity |
|---|--------|---------|-------|---------------------|-------------|------------|
| 3 | Per-Site R² CDF | Plotly | matplotlib | Toggle N=0,5,10 lines; hover shows exact percentile | `per_site.parquet` | **Trivial** |
| NEW-B | SSC/Turb Joint Distribution | Plotly (heatmap or hexbin) | matplotlib | Hover shows bin count; log-log axes | `per_reading.parquet` (or raw paired data) | **Moderate** |
| 5 | First Flush Event Traces | Plotly | matplotlib | Select event from dropdown; time series with CQR ribbons (when available) | `per_reading.parquet` + time series data | **Complex** — needs event detection + time alignment |
| 15 | Site-Level Rating Curves | Plotly (small multiples via subplots) | matplotlib | 6 sites; hover shows sample details; model overlay line | Site-level data from `per_reading.parquet` | **Moderate** |
| 16 | Slope Gallery by Lithology | Plotly (violin/ridge) | matplotlib | Color by lithology group; hover shows site count | `per_site.parquet` + attribute data | **Moderate** |
| NEW-C | Box-Cox Justification | Plotly (3 histograms) | matplotlib | Toggle between raw/log1p/Box-Cox; overlay normal curve | `per_reading.parquet` | **Trivial** |
| 26 | Adaptation Surprise Plot | Plotly scatter | matplotlib | Color by site characteristic dropdown; quadrant labels; hover shows site ID | `per_site.parquet` | **Moderate** |
| NEW-G | Load Estimation | Plotly | matplotlib | Select site; cumulative load curves: bcf_mean vs bcf_median vs OLS | **DEFERRED** — data doesn't exist yet | **Moderate** (when data arrives) |
| 13+31 | CQR Calibration + Fan | Plotly | matplotlib | Calibration diagonal + event ribbons | **DEFERRED** — CQR model still training | **Moderate** (when data arrives) |
| 38 | Temporal Stability | Plotly scatter | matplotlib | Hover shows site ID; 1:1 reference line | Needs first/second half split — derive from `per_reading.parquet` | **Moderate** |
| 14 | Residual Structure + Q-Q | Plotly (subplots) | matplotlib | Hover shows outlier site IDs; Q-Q with confidence envelope | `per_reading.parquet` | **Moderate** |
| 9 | SHAP Beeswarm (top 10) | Plotly (horizontal strip) | matplotlib + shap library | Hover shows feature value + SHAP value; limit to top 10 | `shap_values_*.parquet`, `shap_importance_*.parquet` | **Moderate** |
| NEW-TA | Effective Sample Size | Plotly | matplotlib | Histogram of lag-1 autocorrelation + effective N ratio | Needs computation from time series data | **Moderate** |

### Dashboard-Only Figures

| # | Figure | Library | Interactive Features | Data Source | Complexity |
|---|--------|---------|---------------------|-------------|------------|
| NEW-P2 | Data Journey Sankey | Plotly Sankey | Hover shows count at each stage | Hard-coded counts from pipeline | **Trivial** |
| NEW-P3 | Site Personality Cards | Plotly + HTML cards | Click site on map → card appears with key metrics + mini-plots | `per_site.parquet`, `site_metadata.json` | **Complex** — replaced by Sites page explorer |
| NEW-P5 | Before/After Animation | Plotly animation | Play button morphs dots from zero-shot to N=10 | `per_site.parquet` | **Moderate** |
| NEW-P6 | Geography of Difficulty | Plotly scattergeo with bivariate color | Hover shows site details; legend for 2D color encoding | `per_site.parquet`, `site_metadata.json` | **Complex** |
| 25 | Before/After Site Gallery | Plotly subplots | 2x2 grid: best/modest/none/degradation examples | `per_site.parquet`, `per_reading.parquet` | **Moderate** |
| 18 | Hysteresis Loops | Plotly with time-color | CW/CCW/linear triptych; time encoded as color gradient | `per_reading.parquet` + event selection | **Complex** |
| NEW-D | Representativeness CDFs | Plotly | Toggle: training vs national for each variable | Site attributes + national distribution data | **Moderate** |

### Figures That Change Form for the Dashboard

Some paper figures should work DIFFERENTLY in the dashboard than on paper. My recommendations:

1. **Fig 1 (Obs vs Pred):** Paper uses hexbin for density. Dashboard should use Plotly scatter with opacity=0.3 + hover, because the whole point of making it interactive is to identify which sites/samples are outliers. At 5,829 points, Plotly handles this fine.

2. **Fig 2 (Adaptation Curve):** Paper shows one panel per split mode. Dashboard should use a dropdown to switch between them, saving vertical space and enabling comparison.

3. **Fig 4 (Disaggregated Heatmap):** Kaleb's note says compare heatmap vs dot plot. In the dashboard, offer BOTH via a toggle button. For the paper, pick whichever the advisor prefers.

4. **Fig 19 (Pooled vs Per-Site):** Paper is a static paired comparison. Dashboard version should let you toggle between median/weighted/mean aggregation to really drive home how much the metric choice matters.

5. **NEW-P4 (Physics Wall):** Paper annotates 3 zones with text boxes. Dashboard should make those zones clickable — clicking a zone filters to show only those points, with a table listing the sites contributing to that zone.

6. **Fig 7 (External):** Paper shows all orgs in one panel. Dashboard should use faceted small multiples (one panel per org) because Plotly's hover makes the dense scatter readable.

---

## 5. Static Export Workflow

### The Dual-Output Strategy

Every figure has two rendering paths:

```
figures.py::make_adaptation_curve(data)
  ├── returns plotly.graph_objects.Figure   → used by .qmd for dashboard
  └── returns matplotlib.figure.Figure     → used by generate_paper_figures.py
```

In practice, some figures are better written separately for each target (the layout constraints are too different). But the DATA PROCESSING should always be shared.

### Paper Figure Generation Script

```
scripts/generate_paper_figures.py
  - Imports shared data loading from _scripts/data_prep.py
  - Imports shared palette/style from _scripts/style.py
  - Generates all paper figures as PDF + PNG at WRR dimensions
  - Saves to figures/paper/fig01.pdf, fig02.pdf, etc.
  - Uses scienceplots + custom rcParams from the design guide
  - Runs independently of Quarto — no dashboard needed to make paper figures
```

### Export Specifications

| Target | Format | DPI | Dimensions |
|--------|--------|-----|------------|
| WRR single-column | PDF (vector) | 600 | 85mm wide |
| WRR full-width | PDF (vector) | 600 | 170mm wide |
| WRR raster fallback | PNG | 600 | Same widths |
| Dashboard | Plotly HTML (inline) | N/A | Responsive |
| README / GitHub | PNG | 300 | 800px wide |

### Font Stack

Paper figures: Arial 8pt base (per AGU requirements).
Dashboard: Source Sans Pro via Google Fonts, falling back to Arial.

---

## 6. Deployment

### GitHub Pages Setup

1. Create `dashboard/` directory in the murkml repo (or a separate `murkml-dashboard` repo — I'd recommend separate to keep the data pipeline repo clean).

2. Quarto config (`_quarto.yml`):
```yaml
project:
  type: website
  output-dir: _site

website:
  title: "murkml — Cross-Site SSC Prediction"
  navbar:
    left:
      - href: index.qmd
        text: Overview
      - performance.qmd
      - adaptation.qmd
      - sites.qmd
      - external.qmd
      - diagnostics.qmd
      - supplement.qmd
      - about.qmd
  page-footer:
    center: "murkml — Kaleb [Last Name] — University of Idaho"

format:
  html:
    theme:
      light: [cosmo, custom.scss]
    toc: true
    code-fold: true
    code-tools: false
```

3. GitHub Actions workflow (`.github/workflows/dashboard.yml`):
```yaml
on:
  push:
    branches: [main]
    paths: ['dashboard/**']

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - uses: quarto-dev/quarto-actions/setup@v2
      - run: pip install pandas plotly matplotlib seaborn scienceplots kaleido
      - run: cd dashboard && python _scripts/data_prep.py
      - run: cd dashboard && quarto render
      - uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: dashboard/_site
```

4. Enable GitHub Pages → Source: `gh-pages` branch.

**Result:** Push to `dashboard/` on `main` → GitHub Actions builds → site updates in ~3 minutes.

### Alternative: Manual Deploy

If GitHub Actions is too much setup initially:
```bash
cd dashboard
python _scripts/data_prep.py
quarto render
# Copy _site/ contents to a gh-pages branch, or use `quarto publish gh-pages`
```

Quarto has a built-in `quarto publish gh-pages` command that handles the branch management.

---

## 7. Build Sequence

### Phase 0: Scaffolding (1 Claude session, ~30 min)
- [ ] Create `dashboard/` directory structure
- [ ] Write `_quarto.yml` with navigation
- [ ] Write `_scripts/style.py` with Okabe-Ito palette + shared config
- [ ] Write `_scripts/data_prep.py` to copy/transform data
- [ ] Write `index.qmd` with value boxes and placeholder text
- [ ] Verify `quarto preview` works

### Phase 1: Core Paper Figures (2-3 Claude sessions)
Priority order matches FIGURE_PLAN.md Phase 1:
- [ ] Fig 2: Adaptation curve (the most important figure)
- [ ] Fig 19: Pooled vs per-site performance
- [ ] NEW-P4: Physics Wall
- [ ] Fig 1: Obs vs pred hexbin/scatter
- [ ] Wire these into `performance.qmd` and `adaptation.qmd`

Each figure = one function in `figures.py` returning Plotly + matplotlib.

### Phase 2: Supporting Figures (2-3 Claude sessions)
- [ ] Fig 6: CatBoost vs OLS
- [ ] Fig 4: Disaggregated heatmap (both versions per Kaleb's request)
- [ ] Fig 7: External NTU validation
- [ ] Fig 12: Bayesian shrinkage
- [ ] NEW-A: Study area map (requires site lat/lon data — build the lookup first)
- [ ] Wire into remaining pages

### Phase 3: Site Explorer (1-2 Claude sessions)
- [ ] Build site metadata JSON with lat/lon
- [ ] CONUS map with Plotly scattergeo
- [ ] Site detail panel with per-site obs vs pred
- [ ] Sortable/searchable site table

### Phase 4: Supplementary + Dashboard-Only (2-3 Claude sessions)
- [ ] All supplement figures (Fig 3, 5, 15, 16, NEW-B, NEW-C, etc.)
- [ ] Dashboard-only figures (Sankey, animation, hysteresis)
- [ ] CQR figures (when data arrives)
- [ ] Load estimation (when data arrives)

### Phase 5: Polish + Deploy (1 Claude session)
- [ ] Custom SCSS theme
- [ ] Mobile testing
- [ ] GitHub Pages deployment
- [ ] Paper figure export script
- [ ] README for the dashboard directory

### Estimated Total: 8-12 Claude sessions

Each session can produce 2-4 figures depending on complexity. The scaffolding and first 5 figures are achievable in 2 sessions. The site explorer is the most complex single feature and may take a dedicated session.

---

## 8. Risks and Tradeoffs

### Things That Could Go Wrong

1. **Site lat/lon data doesn't exist in a convenient form.** The qualified_sites.parquet has no coordinates. You'll need to either:
   - Query NWIS for lat/lon for all 396 sites (one API call, trivial)
   - Or use the external_predictions.parquet which has lat/lon for external sites, and build a separate lookup for USGS sites
   - **Mitigation:** Add lat/lon lookup to `data_prep.py`. Cache the result. This is a 15-minute task.

2. **Plotly figure size bloats page load.** The per_reading.parquet has 5,829 rows. Embedded as Plotly JSON, that's ~2MB per figure. If multiple figures on one page each embed the full dataset, pages could hit 10MB+.
   - **Mitigation:** Pre-aggregate where possible. The Physics Wall doesn't need all 5,829 points — a random subsample of 2,000 with the running median looks identical. The hexbin/density encoding for Fig 1 compresses naturally.

3. **Quarto dashboard layout doesn't support the interactive map → detail linking** you want for the Sites page.
   - **Mitigation:** Use Quarto's OJS (Observable JavaScript) cells for this one page. Quarto supports mixing Python and OJS cells. The map click → detail update pattern is a natural fit for OJS reactive programming. This is the ONE place where Observable's paradigm is worth the complexity.
   - **Fallback:** Simple dropdown to select a site. Less impressive but works in 20 minutes.

4. **The hero figure (NEW-P1) is a composite nightmare.** Three-panel composites with precise alignment are hard in any framework. Plotly can't do it well. Matplotlib can, but the result is static.
   - **Mitigation:** Render the hero as a static matplotlib PNG at 2x resolution, embed as an image. The hero figure is a "gateway" — it doesn't need to be interactive. Interactivity lives on the deeper pages.

5. **CQR and load estimation data doesn't exist yet.** Several planned figures depend on models still training.
   - **Mitigation:** Build placeholder pages with "Coming soon — CQR model training in progress" boxes. The figure functions will be ready; they just need data piped in later.

6. **SHAP beeswarm in Plotly is ugly.** Plotly doesn't have a native beeswarm. You'd need to manually jitter points or use a violin-like layout.
   - **Mitigation:** Use the SHAP library's matplotlib output for the paper figure. For the dashboard, use a Plotly horizontal strip plot with jitter, limited to top 10 features. It won't look like the classic SHAP beeswarm, but with hover tooltips showing feature values, it's actually MORE informative.

### Acceptable Shortcuts

- **Skip the Before/After Animation (NEW-P5)** unless everything else is done. Plotly animations are finnicky and add little analytical value. A static before/after comparison (Fig 25) communicates the same thing.
- **Skip the Geography of Difficulty bivariate choropleth (NEW-P6).** Bivariate color encoding is notoriously hard to read. The regular site map colored by R² (NEW-A) is more useful. If you want to show data density, use marker size.
- **Skip the Representativeness CDFs (NEW-D)** initially. It's useful for reviewers but not for the landing experience.
- **The Sankey (NEW-P2) is trivial and fun.** Build it. It takes 15 minutes and people love it.

### Over-Engineering Warnings

- **Don't build a custom theme.** Quarto's `cosmo` theme with minor SCSS overrides is fine. Custom themes eat days.
- **Don't try to make every figure cross-filter with every other figure.** That's a Dash/Panel pattern. In Quarto, each figure is independent. That's fine. People don't need global cross-filtering for a paper companion.
- **Don't pre-optimize for mobile.** If it works on desktop and is readable on a tablet, that's enough. Nobody is analyzing SHAP beeswarms on their phone.
- **Don't build a search/filter system for 254 sites.** A sorted table with browser Ctrl+F is sufficient. If you find yourself building a search index, stop.

---

## 9. Dissenting Notes (Things I'd Do Differently Than the Figure Plan)

I read the full figure plan and expert panel discussion. A few places where the dashboard context changes my opinion:

1. **Fig 19 title:** The experts debated "aggregate metrics are misleading" vs neutral. For the DASHBOARD, use the editorial title. Dashboards are storytelling tools, not journal articles. Save the neutral title for the paper.

2. **Fig 4 heatmap vs dot plot:** Kaleb wants to compare both. In the dashboard, use a toggle button. For the paper, I'd go with the dot plot — heatmaps at this granularity (59 rows) are harder to read than dots with error bars, and Sato is right about that.

3. **Fig 15 — 6 vs 12 sites:** For the dashboard, show ALL holdout sites with rating curves, accessible via the site explorer dropdown. The "how many sites" debate only matters for the paper's supplementary figure. The dashboard has no page budget.

4. **Hysteresis loops (Fig 18):** In the dashboard, these should be animated — show time progressing along the loop with a moving dot. The static triptych with color-coded time arrows is a paper compromise. Animation is what makes this figure click for non-experts.

5. **Fig 24 (Bayesian weight curve):** Kaleb's note says "just make a figure." Agreed. In the dashboard, this should be on the Adaptation page with a brief caption explaining what shrinkage weight means. It's a simple line plot: N on x-axis, weight on y-axis. Trivial to implement, important for understanding.

6. **Moran's I / Variogram (NEW-H):** Kaleb asked "What is this?" — it's a spatial autocorrelation test. For the dashboard, skip it entirely. It matters for the paper's statistical rigor but adds nothing to the interactive exploration experience. If a reviewer demands it, it goes in the supplement as a static figure.

---

## Appendix: Quarto + Plotly Quick Reference

For Claude Code sessions building the dashboard, here's the minimal pattern:

````markdown
---
title: "Performance"
format: dashboard
---

```{python}
#| label: setup
#| include: false
import pandas as pd
import plotly.graph_objects as go
from _scripts.figures import make_obs_vs_pred
from _scripts.data_prep import load_dashboard_data

data = load_dashboard_data()
```

## Row {height="60%"}

### Observed vs Predicted {width="60%"}

```{python}
#| label: fig-obs-pred
fig = make_obs_vs_pred(data['per_reading'])
fig.show()
```

### Key Metrics {width="40%"}

```{python}
#| label: metrics-box
#| component: valuebox
dict(
    title="Median Site R²",
    value="0.41",
    color="primary"
)
```
````

This is the actual syntax. No Dash callbacks, no server, no deployment infrastructure. Just Python in markdown.
