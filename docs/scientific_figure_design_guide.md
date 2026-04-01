# Scientific Figure Design Guide for Hydrology / ML Papers

*Compiled 2026-03-31 for the murkml WRR paper and related publications.*

---

## Table of Contents

1. [Journal Requirements (AGU / WRR)](#1-journal-requirements-agu--wrr)
2. [Color and Accessibility](#2-color-and-accessibility)
3. [Layout and Typography](#3-layout-and-typography)
4. [Static Figure Best Practices](#4-static-figure-best-practices)
5. [Interactive Dashboard Patterns](#5-interactive-dashboard-patterns)
6. [Python Tooling Recommendations](#6-python-tooling-recommendations)
7. [Example Gallery](#7-example-gallery-descriptions-of-excellent-published-figures)

---

## 1. Journal Requirements (AGU / WRR)

Water Resources Research is published by AGU (American Geophysical Union) through Wiley. All AGU journals share the same graphics standards.

### Figure Dimensions

| Type | Width | Notes |
|------|-------|-------|
| Single-column | 50-85 mm (2.0-3.35 in) | Most common for simple plots |
| 1.5-column | 105-130 mm | Good for multi-panel with shared axis |
| Full-width (2-column) | 105-170 mm (4.13-6.69 in) | Max for complex multi-panel |
| Maximum height | 228 mm (8.98 in) | Hard limit |

### Resolution

- **Vector formats preferred:** EPS, PDF (choose "Press Quality")
- **Raster minimum:** 300 ppi at final print size
- **Raster maximum:** 600 ppi (larger files get rejected)
- **Recommended approach:** Use vector (PDF/EPS) for line art and charts; use TIFF/PNG at 300-600 ppi only for photographs or raster data (satellite imagery, heatmaps)

### Font Requirements

- **Allowed fonts:** Arial, Helvetica, Times, Symbol
- **Body text in figures:** 8 pt at final print size
- **Subscript/superscript:** 6 pt at final print size
- **Fonts must be:** embedded, outlined, or converted to curves in EPS/PDF
- **Consistency:** Same font family across all figures in the manuscript

### Color Mode

- **RGB** for both vector and raster graphics (AGU handles CMYK conversion)
- Avoid colors that rely solely on red-green distinction

### File Formats (Accepted)

- EPS (vector, fonts outlined/embedded)
- PDF (vector, "Press Quality" export)
- TIFF (raster, LZW compression OK)
- PNG (raster, for initial submission)
- JPEG (raster, only for photographs -- lossy compression degrades line art)

### Submission Protocol

- **Initial submission:** Figures inline with text and captions in a single Word/PDF file
- **Revision/acceptance:** Separate high-resolution figure files
- **Naming:** `fig01.eps`, `fig02.pdf`, etc.
- **Publication units:** 1 figure = 1 PU; total manuscript limit is 25 PU (500 words or 1 display element each)

### Accessibility Requirements

AGU strongly encourages:
- Figures accessible to people with color vision deficiency
- Alternative text descriptions for figures
- Patterns or markers in addition to color to distinguish data series

**Key reference:** [AGU Text & Graphics Requirements](https://www.agu.org/publications/authors/journals/text-graphics-requirements)

---

## 2. Color and Accessibility

### The Golden Rule

Never rely on color alone to convey information. Always pair color with shape, pattern, line style, or direct labeling.

### Recommended Colorblind-Safe Palettes

#### Okabe-Ito (Categorical -- the gold standard)

Recommended by Nature Methods. Works for all common forms of color vision deficiency.

| Color | Hex | Use Case |
|-------|-----|----------|
| Orange | `#E69F00` | Primary accent |
| Sky Blue | `#56B4E9` | Secondary accent |
| Bluish Green | `#009E73` | Tertiary |
| Yellow | `#F0E442` | Caution: low contrast on white backgrounds |
| Blue | `#0072B2` | Strong, safe for all CVD types |
| Vermillion | `#D55E00` | High-contrast warm |
| Reddish Purple | `#CC79A7` | Distinct from blue and green |
| Black | `#000000` | Reference / baseline |

**Usage note:** For a 3-color scheme, use Blue `#0072B2`, Vermillion `#D55E00`, and Bluish Green `#009E73`. For 2 colors, Blue + Vermillion provides maximum contrast.

#### Paul Tol's Schemes (Comprehensive)

Paul Tol provides qualitative, diverging, and sequential schemes all designed for colorblind safety. Key schemes:

**Bright (qualitative, up to 7 colors):**
`#4477AA`, `#EE6677`, `#228833`, `#CCBB44`, `#66CCEE`, `#AA3377`, `#BBBBBB`

**Vibrant (qualitative, up to 7 colors):**
`#EE7733`, `#0077BB`, `#33BBEE`, `#EE3377`, `#CC3311`, `#009988`, `#BBBBBB`

**Muted (qualitative, up to 10 colors):**
`#CC6677`, `#332288`, `#DDCC77`, `#117733`, `#88CCEE`, `#882255`, `#44AA99`, `#999933`, `#AA4499`, `#DDDDDD`

**Reference:** [Paul Tol's Colour Schemes](https://personal.sron.nl/~pault/) (Technical Note issue 3.2, 2021)

#### Sequential / Continuous Colormaps

| Colormap | Source | Best For | Python Access |
|----------|--------|----------|---------------|
| **viridis** | matplotlib built-in | Default sequential | `cmap='viridis'` |
| **batlow** | Fabio Crameri | "Scientific rainbow" -- perceptually uniform | `import cmcrameri.cm as cmc; cmap=cmc.batlow` |
| **cividis** | matplotlib built-in | CVD-safe sequential | `cmap='cividis'` |
| **YlOrBr** | ColorBrewer | Warm sequential (precipitation, concentration) | `cmap='YlOrBr'` |
| **roma** | Fabio Crameri | Diverging (blue-white-red alternative) | `cmap=cmc.roma` |
| **vik** | Fabio Crameri | Diverging (blue-white-red) | `cmap=cmc.vik` |

**Install Crameri colormaps:** `pip install cmcrameri`

#### What NOT to Use

- **jet / rainbow:** Not perceptually uniform, creates false features, terrible in grayscale
- **Red-green only:** Indistinguishable for ~8% of males
- **Pure red + pure green:** Even with luminance differences, avoid this pair
- **High-saturation neon colors:** Look unprofessional, hard to print

### Testing Tools

- **Color Oracle** (desktop app): Simulates CVD in real-time on your screen
- **Coblis** (web): Upload image, see CVD simulations
- **Viz Palette** (web): Test palette distinctiveness
- **matplotlib:** `from colorspacious import cspace_converter` for programmatic checks

---

## 3. Layout and Typography

### Multi-Panel Figure Design

**Panel labeling conventions:**
- Use **(a)**, **(b)**, **(c)** or **a**, **b**, **c** -- bold, uppercase or lowercase per journal style
- Place labels in the **upper-left corner** of each panel
- Keep labels **outside** the plot area when possible, or in a consistent inset position
- Size: same as axis label text (8 pt at final size for AGU)

**Layout principles:**
- Read left-to-right, top-to-bottom (Z-pattern)
- Keep horizontal and vertical spacing equal between panels
- Align axes across rows/columns when comparing related data
- Share axes when panels show the same variable range
- Use `gridspec` or `subfigures` in matplotlib for precise control

**Spacing:**
- Panels should never touch -- maintain at least 3-5 mm gap
- Use `plt.subplots_adjust()` or `constrained_layout=True`

### Typography Rules

| Element | Size (at final print) | Font |
|---------|----------------------|------|
| Axis labels | 8-10 pt | Arial or Helvetica (sans-serif for AGU) |
| Tick labels | 7-8 pt | Same family |
| Panel labels | 8-10 pt, **bold** | Same family |
| Legend text | 7-8 pt | Same family |
| Annotations | 7-8 pt | Same family |
| Figure caption | Set by journal (not in figure file) | -- |

**Critical sizing test:** Export your figure at the final column width (e.g., 85 mm for single-column). Open the PDF at 100% zoom. If you cannot comfortably read every label, the text is too small.

### Tufte's Principles (Applied)

Edward Tufte's core principles, adapted for hydrology papers:

1. **Maximize data-ink ratio:** Remove gridlines (or make them very light), remove chart borders, remove redundant axis labels. Every pixel should convey data.
2. **Eliminate chartjunk:** No 3D effects, no gradient fills, no decorative elements. Moire patterns in bar fills are chartjunk.
3. **Show the data:** Use scatter plots over bar charts when showing distributions. Show individual data points alongside summary statistics.
4. **Small multiples:** When comparing across sites/conditions, use identical mini-plots in a grid rather than overlaying everything on one busy plot.
5. **Graphical integrity:** Axis scales must not mislead. Start y-axes at zero for bar charts. Use consistent scales across compared panels. Label directly on lines/points rather than using separate legends when practical.

---

## 4. Static Figure Best Practices

### Figures Every ML-Hydrology Paper Needs

#### 1. Observed vs. Predicted Scatter Plot

**What makes it good:**
- 1:1 reference line (dashed black, not fitted regression line)
- Log-log scale for streamflow/SSC (spans orders of magnitude)
- Point density coloring or hexbin for large N (avoid overplotting)
- Performance metrics annotated in corner: NSE, KGE, R^2, RMSE, PBIAS
- Separate panels or colors for training vs. test data
- If site-specific: small multiples by site

**Common mistakes:**
- Using linear scale when data spans 3+ orders of magnitude
- Fitting and showing regression line instead of 1:1 line
- Not showing point density when N > 1000
- Omitting units on axes

#### 2. Time Series with Prediction Intervals

**What makes it good:**
- Observed as thin black line or dots
- Predicted as colored line
- Prediction intervals as shaded bands (use graded bands: 50%, 80%, 95%)
- Darker shading for narrower intervals
- Zoom insets for event periods
- Precipitation/discharge on secondary y-axis (inverted for precip)

**Shading approach for CQR intervals:**
```
95% band: alpha=0.15
80% band: alpha=0.25
50% band: alpha=0.35
Median prediction: solid line, alpha=0.9
```

#### 3. Residual Diagnostic Plots

**What makes it good:**
- Residuals vs. predicted (should be random scatter around zero)
- Residuals vs. time (check for temporal autocorrelation)
- Q-Q plot of residuals (check normality assumption)
- Histogram of residuals with normal curve overlay
- Annotate heteroscedasticity or systematic patterns

#### 4. Feature Importance / SHAP Plot

**What makes it good:**
- Horizontal bar chart (easier to read feature names)
- Sorted by importance (largest at top)
- Error bars from cross-validation or bootstrapping
- SHAP beeswarm plot for interaction effects
- Group correlated features or note collinearity

#### 5. Spatial Performance Map

**What makes it good:**
- Map showing site locations colored by performance metric
- Consistent color scale with meaningful breakpoints
- Basemap with watershed boundaries, rivers
- Inset showing study area location in larger context
- Symbol size can encode a second variable (e.g., sample size)

#### 6. Flow Duration Curve / Exceedance Plot

**What makes it good:**
- Log y-axis for discharge
- Observed and simulated curves overlaid
- Shaded confidence bands
- Annotated flow regime zones (high flow, mid, low flow)

### Uncertainty Visualization Best Practices

From Claus Wilke's *Fundamentals of Data Visualization*:

- **Error bars:** Best for comparing multiple point estimates. Always specify what they represent (SD, SE, CI).
- **Graded confidence bands:** Use 2-3 nested bands (e.g., 50% and 95%) with decreasing opacity. This reduces "deterministic construal error" -- viewers treating a single band edge as a hard boundary.
- **Quantile dotplots:** For communicating probability to non-expert audiences. Use 20-100 dots.
- **Never use confidence strips alone** (continuous shading without boundaries) -- they are difficult to read quantitatively.

---

## 5. Interactive Dashboard Patterns

### When to Use Interactive vs. Static

| Use Case | Format |
|----------|--------|
| Journal submission | Static (PDF/EPS/TIFF) |
| Supplementary material | Interactive HTML (self-contained) |
| Conference presentation | Interactive (Plotly/Dash) |
| Stakeholder communication | Interactive dashboard |
| Thesis defense | Both |
| GitHub/project documentation | Interactive HTML |

### Plotly for Interactive Scientific Figures

**Strengths:**
- Hover tooltips showing exact values, site IDs, dates
- Zoom/pan for exploring dense time series
- Toggle traces on/off via legend clicks
- Export to self-contained HTML files
- Also exports to static PNG/SVG/PDF

**Key code patterns:**

```python
import plotly.graph_objects as go

# Observed vs predicted with hover info
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=observed, y=predicted,
    mode='markers',
    marker=dict(size=4, color=metric_values, colorscale='Viridis',
                colorbar=dict(title='KGE')),
    text=site_ids,  # hover text
    hovertemplate='Site: %{text}<br>Obs: %{x:.2f}<br>Pred: %{y:.2f}<extra></extra>'
))
fig.add_trace(go.Scatter(x=[0,max_val], y=[0,max_val],
    mode='lines', line=dict(dash='dash', color='black'), name='1:1'))
fig.update_layout(
    xaxis_title='Observed SSC (mg/L)',
    yaxis_title='Predicted SSC (mg/L)',
    xaxis_type='log', yaxis_type='log',
    template='plotly_white',
    font=dict(family='Arial', size=12)
)
fig.write_html('obs_vs_pred.html')  # self-contained
fig.write_image('obs_vs_pred.pdf', width=170*3.78, height=120*3.78)  # mm to px at 96 dpi
```

### Dash for Full Dashboards

**When Dash makes sense:**
- Multi-page exploration of model results across sites
- Real-time data monitoring (e.g., USGS data feeds)
- Stakeholder tools with dropdowns, sliders, date pickers
- Portfolio demos for job applications

**Architecture pattern:**
```
app.py
|-- layout (sidebar + main content)
|   |-- Dropdown: select site
|   |-- DateRangePicker: select period
|   |-- Tabs: time series | scatter | spatial | diagnostics
|-- callbacks
    |-- update_timeseries(site, dates)
    |-- update_scatter(site, dates)
    |-- update_map(metric)
```

### Observable Framework

**When to consider it:**
- You want a static site (no server) with interactive plots
- Markdown-based authoring with embedded JavaScript visualizations
- Built-in DuckDB support for querying large datasets in-browser
- Good for research group websites and open-science dashboards
- Steeper learning curve than Dash if you are Python-first

---

## 6. Python Tooling Recommendations

### Recommended Stack

```
matplotlib          # Foundation -- full control, publication vector output
seaborn             # Statistical plots (violin, box, heatmap, pair plots)
plotly              # Interactive figures, HTML export
scienceplots        # Pre-built journal styles for matplotlib
cmcrameri           # Crameri perceptually uniform colormaps
adjustText          # Auto-position text labels to avoid overlap
cartopy / geopandas # Spatial maps
```

### SciencePlots Setup

```bash
pip install SciencePlots
# Requires LaTeX installed (texlive-full on Linux, MiKTeX on Windows)
# For no-LaTeX fallback: plt.style.use(['science', 'no-latex'])
```

```python
import matplotlib.pyplot as plt
import scienceplots

# AGU/WRR style (serif, appropriate sizing)
plt.style.use(['science'])

# IEEE style (single-column, B&W safe)
plt.style.use(['science', 'ieee'])

# Nature style (sans-serif)
plt.style.use(['science', 'nature'])

# Colorblind-safe color cycle
plt.style.use(['science', 'bright'])
```

### Publication-Quality matplotlib Settings

For manual control without SciencePlots:

```python
import matplotlib.pyplot as plt
import matplotlib as mpl

# -- Core settings for WRR figures --
plt.rcParams.update({
    # Figure
    'figure.figsize': (3.35, 2.5),        # single-column in inches (85mm)
    'figure.dpi': 300,
    'savefig.dpi': 600,
    'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.02,

    # Font
    'font.family': 'sans-serif',
    'font.sans-serif': ['Arial', 'Helvetica'],
    'font.size': 8,                        # base font size
    'axes.titlesize': 9,
    'axes.labelsize': 8,
    'xtick.labelsize': 7,
    'ytick.labelsize': 7,
    'legend.fontsize': 7,

    # Lines and markers
    'lines.linewidth': 1.0,
    'lines.markersize': 3,

    # Axes
    'axes.linewidth': 0.6,
    'axes.spines.top': False,
    'axes.spines.right': False,            # Tufte: remove non-data ink

    # Ticks
    'xtick.major.width': 0.6,
    'ytick.major.width': 0.6,
    'xtick.major.size': 3,
    'ytick.major.size': 3,
    'xtick.direction': 'in',
    'ytick.direction': 'in',

    # Grid (subtle or off)
    'axes.grid': False,

    # Legend
    'legend.frameon': False,

    # Math text
    'mathtext.fontset': 'dejavusans',

    # Save
    'savefig.format': 'pdf',
})
```

### Seaborn for Statistical Figures

```python
import seaborn as sns

# Set seaborn context for publication
sns.set_context("paper", font_scale=1.0)
sns.set_style("ticks")  # clean axes, no grid

# Correlation heatmap (half-matrix)
import numpy as np
mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
sns.heatmap(corr_matrix, mask=mask, cmap='RdBu_r',
            vmin=-1, vmax=1, center=0,
            annot=True, fmt='.2f', annot_kws={'size': 6},
            linewidths=0.5, square=True,
            cbar_kws={'shrink': 0.8, 'label': 'Correlation'})
```

### Saving Figures Correctly

```python
# Vector (preferred for line art, charts)
fig.savefig('fig01.pdf', dpi=600, bbox_inches='tight', pad_inches=0.02)
fig.savefig('fig01.eps', dpi=600, bbox_inches='tight', pad_inches=0.02)

# Raster (for photos, satellite imagery, dense heatmaps)
fig.savefig('fig01.tiff', dpi=600, bbox_inches='tight', pil_kwargs={'compression': 'tiff_lzw'})
fig.savefig('fig01.png', dpi=600, bbox_inches='tight')

# NEVER save charts as JPEG -- lossy compression creates artifacts on line art
```

### Useful Utility Functions

```python
def set_size(width_mm, height_mm=None, aspect=0.75):
    """Convert mm to inches for matplotlib figsize."""
    w = width_mm / 25.4
    h = (height_mm / 25.4) if height_mm else w * aspect
    return (w, h)

# Usage:
fig, ax = plt.subplots(figsize=set_size(85))    # single-column
fig, ax = plt.subplots(figsize=set_size(170))   # full-width

def annotate_metrics(ax, metrics_dict, loc='upper left', fontsize=7):
    """Add performance metrics text box to axes."""
    text = '\n'.join(f'{k} = {v:.3f}' for k, v in metrics_dict.items())
    props = dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8, edgecolor='gray')
    anchors = {
        'upper left': (0.03, 0.97, 'top', 'left'),
        'upper right': (0.97, 0.97, 'top', 'right'),
        'lower right': (0.97, 0.03, 'bottom', 'right'),
    }
    x, y, va, ha = anchors[loc]
    ax.text(x, y, text, transform=ax.transAxes, fontsize=fontsize,
            verticalalignment=va, horizontalalignment=ha, bbox=props, family='monospace')
```

---

## 7. Example Gallery (Descriptions of Excellent Published Figures)

### A. Observed vs. Predicted with Density Coloring

**What it shows:** Log-log scatter of observed vs. simulated daily streamflow for 500+ CAMELS basins.

**What makes it excellent:**
- Hexbin density coloring (viridis) prevents overplotting while showing data distribution
- Crisp 1:1 line with KGE, NSE, and PBIAS annotated in a clean text box
- Marginal histograms on both axes showing the distributions
- Separate panels for calibration and validation periods
- Consistent axis ranges and tick marks across panels

**Seen in:** Kratzert et al. (2019) WRR -- LSTM rainfall-runoff modeling

### B. Multi-Site Small Multiples Time Series

**What it shows:** 9-panel grid, each panel showing 1 year of observed + predicted hydrograph for a different catchment.

**What makes it excellent:**
- Inverted precipitation bars on top (standard hydrology convention)
- Thin black line for observed, colored line for predicted
- Shaded 90% prediction interval (light blue, alpha ~0.2)
- Shared x-axis (time), independent y-axes (discharge varies by site)
- Site name and NSE annotated in each panel corner
- Clean, minimal axes -- no gridlines, no chart borders

**Seen in:** Feng et al. (2020) HESS -- differentiable hydrology models

### C. SHAP Summary Beeswarm

**What it shows:** Feature importance with direction of effect for an XGBoost water quality model.

**What makes it excellent:**
- Horizontal orientation (feature names readable)
- Color encodes feature value (low=blue, high=red using a diverging colormap)
- Each dot is one sample -- shows distribution, not just mean
- Features sorted by mean absolute SHAP value
- Clear x-axis label: "SHAP value (impact on model output)"
- Compact: communicates feature importance + direction + nonlinearity in one panel

### D. Spatial Performance Map

**What it shows:** CONUS map with gauge locations colored by site-level KGE.

**What makes it excellent:**
- Basemap with state boundaries and major rivers (subtle gray)
- Diverging colormap centered on KGE=0 (red=poor, white=neutral, blue=good)
- Circle size proportional to record length
- Inset histogram of KGE distribution
- Clean projection (Albers equal-area for CONUS)
- No unnecessary legend box -- colorbar integrated along bottom

### E. Flow Duration Curve Comparison

**What it shows:** Exceedance probability vs. discharge for observed and 3 model variants.

**What makes it excellent:**
- Log y-axis (standard for FDC)
- Observed as thick black line, models as distinct colored lines (Okabe-Ito palette)
- Shaded region showing where models bracket observations
- Vertical dashed lines delineating flow regimes (Q10, Q50, Q90)
- Regime labels annotated ("High flows", "Mid-range", "Low flows")
- Direct labeling on lines instead of separate legend

### F. Taylor Diagram

**What it shows:** Multi-model comparison on a single polar plot encoding correlation, RMSE, and standard deviation.

**What makes it excellent:**
- Compact representation of 3 metrics simultaneously
- Reference point (observed) clearly marked
- Each model variant as a distinct marker
- Concentric RMSE arcs and radial correlation lines
- Standard deviation on the radial axis
- Enables at-a-glance comparison of 10+ model configurations

### G. Prediction Interval Reliability Diagram

**What it shows:** Nominal coverage (x-axis) vs. observed coverage (y-axis) for CQR prediction intervals.

**What makes it excellent:**
- 1:1 diagonal = perfectly calibrated intervals
- Points for each quantile level (5%, 10%, ..., 95%)
- Shaded acceptable region around diagonal
- Separate lines/markers for different model variants or site groups
- Communicates interval reliability without requiring domain expertise

---

## Quick-Reference Checklist

Before submitting any figure, verify:

- [ ] Text readable at final print size (8 pt minimum for AGU)
- [ ] Colorblind-safe palette used (test with Color Oracle)
- [ ] Figure understandable in grayscale (or uses markers/patterns)
- [ ] No chartjunk: no 3D effects, no gradient fills, no unnecessary gridlines
- [ ] Consistent fonts, sizes, and styles across all figures
- [ ] Panel labels (a, b, c) in upper-left, bold, consistent size
- [ ] Axes labeled with units
- [ ] 1:1 line (not regression line) on obs vs. pred plots
- [ ] Performance metrics annotated on relevant panels
- [ ] Uncertainty shown as graded bands, not single-line boundaries
- [ ] Resolution >= 300 ppi for raster, vector preferred for line art
- [ ] File format: PDF or EPS for charts, TIFF for raster imagery
- [ ] Figure communicates ONE main idea (split if overcrowded)
- [ ] Axes scales appropriate (log for data spanning orders of magnitude)
- [ ] Caption written (not embedded in figure file)

---

## Sources

### Journal Guidelines
- [AGU Text & Graphics Requirements](https://www.agu.org/publications/authors/journals/text-graphics-requirements)
- [AGU Submission Checklists](https://www.agu.org/publications/authors/journals/submission-checklists)
- [Water Resources Research (Wiley)](https://agupubs.onlinelibrary.wiley.com/journal/19447973)

### Color and Accessibility
- [Okabe-Ito Palette Hex Codes (ConceptViz)](https://conceptviz.app/blog/scientific-color-palette-for-research-papers-and-posters)
- [Paul Tol's Colour Schemes](https://personal.sron.nl/~pault/)
- [Fabio Crameri Scientific Colour Maps](https://www.fabiocrameri.ch/colourmaps/)
- [cmcrameri Python Package](https://pypi.org/project/cmcrameri/)
- [Choosing Color Palettes (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7040535/)
- [NKI Guidelines for Colorblind-Friendly Figures](https://www.nki.nl/about-us/responsible-research/guidelines-color-blind-friendly-figures/)
- [ColorBrewer 2.0](https://colorbrewer2.org)

### Layout and Design
- [Multi-Panel Figure Layouts Guide (Catalin Iliescu)](https://cataliniliescu.ro/a-complete-guide-to-multi-panel-scientific-figure-layouts-avoid-reviewer-rejection/)
- [Tufte's Principles (The Double Think)](https://thedoublethink.com/tuftes-principles-for-visualizing-quantitative-information/)
- [7 Common Figure Design Mistakes (Mind the Graph)](https://mindthegraph.com/blog/research-figure-design-mistakes-and-fixes/)
- [Visualizing Uncertainty (Claus Wilke)](https://clauswilke.com/dataviz/visualizing-uncertainty.html)
- [Multi-Panel Figures (Claus Wilke)](https://clauswilke.com/dataviz/multi-panel-figures.html)

### Python Tools
- [SciencePlots (GitHub)](https://github.com/garrettj403/SciencePlots)
- [Publication-Quality Plots with Matplotlib (Bastian Bloessl)](https://www.bastibl.net/publication-quality-plots/)
- [Publication-Quality Figures (F. Schuch)](https://www.fschuch.com/en/blog/2025/07/05/publication-quality-plots-in-python-with-matplotlib/)
- [matplotlib for Papers (Jean-Baptiste Mouret)](https://github.com/jbmouret/matplotlib_for_papers)
- [Tips for Academic Figures (Allan Chain)](https://allanchain.github.io/blog/post/mpl-paper-tips/)

### Interactive Visualization
- [Plotly Python Documentation](https://plotly.com/python/)
- [Dash Documentation](https://dash.plotly.com/)
- [Observable Framework (GitHub)](https://github.com/observablehq/framework)
- [Plotly Interactive HTML Export](https://plotly.com/python/interactive-html-export/)

### Hydrology Visualization
- [Visualising Hydrologic Data (Tony Ladson)](https://tonyladson.wordpress.com/2018/12/02/visualising-hydrologic-data/)
- [Visualization in Water Resources Management (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S1364815222001025)
- [USGS Data Science for Water Resources](https://www.usgs.gov/mission-areas/water-resources/science/data-science-water-resources)
