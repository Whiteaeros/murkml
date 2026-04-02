"""
Shared visual style for murkml dashboard and paper figures.
Okabe-Ito colorblind-safe palette, WRR-compatible sizing.
"""

# Okabe-Ito categorical palette (colorblind-safe)
COLORS = {
    "orange": "#E69F00",
    "sky_blue": "#56B4E9",
    "green": "#009E73",
    "yellow": "#F0E442",
    "blue": "#0072B2",
    "vermillion": "#D55E00",
    "purple": "#CC79A7",
    "gray": "#999999",
}

# Semantic color assignments
MODEL_COLOR = COLORS["orange"]      # model predictions always this color
OBS_COLOR = "#333333"               # observed data always dark gray
REF_COLOR = "#CCCCCC"               # reference lines light gray
GOOD_COLOR = COLORS["blue"]         # good performance
BAD_COLOR = COLORS["vermillion"]    # bad performance
BREAKTHROUGH_COLOR = COLORS["orange"]

# Shared density colorscale for 2D histograms
DENSITY_COLORSCALE = [
    [0.0, "rgba(255,255,255,0)"],
    [0.02, "#deebf7"],
    [0.15, COLORS["sky_blue"]],
    [0.5, COLORS["blue"]],
    [1.0, COLORS["vermillion"]],
]

# Method comparison colors
BAYESIAN_COLOR = COLORS["blue"]
OLS_COLOR = COLORS["vermillion"]
OLD_2PARAM_COLOR = COLORS["gray"]

# Split mode colors
RANDOM_COLOR = COLORS["sky_blue"]
TEMPORAL_COLOR = COLORS["vermillion"]
SEASONAL_COLOR = COLORS["green"]

# Organization colors for external validation
ORG_COLORS = {
    "UMRR": COLORS["blue"],
    "SRBC": COLORS["orange"],
    "GLEC": COLORS["green"],
    "UMC": COLORS["purple"],
    "MDNR": COLORS["sky_blue"],
    "CEDEN": COLORS["yellow"],
}

# Plotly layout defaults
PLOTLY_LAYOUT = dict(
    font=dict(family="Source Sans Pro, Helvetica, Arial, sans-serif", size=13),
    plot_bgcolor="white",
    paper_bgcolor="white",
    margin=dict(l=60, r=30, t=80, b=60),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="left",
        x=0.0,
        bgcolor="rgba(255,255,255,0.9)",
        font=dict(size=11),
    ),
    xaxis=dict(
        showgrid=True,
        gridcolor="#EEEEEE",
        gridwidth=1,
        zeroline=False,
    ),
    yaxis=dict(
        showgrid=True,
        gridcolor="#EEEEEE",
        gridwidth=1,
        zeroline=False,
    ),
)

# WRR paper figure dimensions (mm -> inches)
WRR_SINGLE_COL = 84 / 25.4   # 3.31 inches
WRR_FULL_WIDTH = 174 / 25.4  # 6.85 inches
WRR_MAX_HEIGHT = 228 / 25.4  # 8.98 inches

# Matplotlib rcParams for paper figures
MPL_RCPARAMS = {
    "font.family": "sans-serif",
    "font.sans-serif": ["Source Sans Pro", "Helvetica", "Arial"],
    "font.size": 8,
    "axes.labelsize": 9,
    "axes.titlesize": 10,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "axes.linewidth": 0.5,
    "xtick.major.width": 0.5,
    "ytick.major.width": 0.5,
    "lines.linewidth": 1.0,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linewidth": 0.5,
}


def apply_plotly_style(fig):
    """Apply consistent style to a Plotly figure."""
    fig.update_layout(**PLOTLY_LAYOUT)
    return fig


def apply_mpl_style():
    """Apply WRR-compatible matplotlib style. Call once at script start."""
    import matplotlib.pyplot as plt
    plt.rcParams.update(MPL_RCPARAMS)
