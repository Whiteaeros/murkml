"""Generate a data pipeline flowchart for the murkml project.

Produces: data_pipeline_flowchart.png in the project root.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = PROJECT_ROOT / "data_pipeline_flowchart.png"

# ── Colour palette ──────────────────────────────────────────────────
C_SOURCE  = "#3B82F6"   # blue   – external data sources
C_PROC    = "#22C55E"   # green  – processing steps
C_FEAT    = "#F59E0B"   # orange – feature tiers
C_MODEL   = "#EF4444"   # red    – model training
C_OUTPUT  = "#8B5CF6"   # purple – outputs
C_BG      = "#F8FAFC"   # near-white background
C_TEXT    = "#1E293B"   # dark text

# Lighter fills (pastel versions)
C_SOURCE_FILL = "#DBEAFE"
C_PROC_FILL   = "#DCFCE7"
C_FEAT_FILL   = "#FEF3C7"
C_MODEL_FILL  = "#FEE2E2"
C_OUTPUT_FILL = "#EDE9FE"


def draw_box(ax, x, y, w, h, label, border_color, fill_color,
             fontsize=8.5, bold=False, text_color=C_TEXT):
    """Draw a rounded rectangle with centred text."""
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.12",
        facecolor=fill_color,
        edgecolor=border_color,
        linewidth=1.8,
        zorder=3,
    )
    ax.add_patch(box)
    weight = "bold" if bold else "normal"
    ax.text(
        x + w / 2, y + h / 2, label,
        ha="center", va="center",
        fontsize=fontsize, fontweight=weight,
        color=text_color, zorder=4,
        wrap=True,
    )
    return box


def draw_arrow(ax, x1, y1, x2, y2, color="#94A3B8", lw=1.4):
    """Draw a curved arrow between two points."""
    arrow = FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle="->,head_width=6,head_length=5",
        connectionstyle="arc3,rad=0.0",
        color=color, linewidth=lw, zorder=2,
    )
    ax.add_patch(arrow)


def draw_arrow_curved(ax, x1, y1, x2, y2, color="#94A3B8", lw=1.4, rad=0.15):
    arrow = FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle="->,head_width=6,head_length=5",
        connectionstyle=f"arc3,rad={rad}",
        color=color, linewidth=lw, zorder=2,
    )
    ax.add_patch(arrow)


def main():
    fig, ax = plt.subplots(figsize=(18, 12))
    fig.patch.set_facecolor(C_BG)
    ax.set_facecolor(C_BG)
    ax.set_xlim(0, 18)
    ax.set_ylim(0, 12)
    ax.axis("off")

    # Title
    ax.text(9, 11.55, "murkml  Data Pipeline",
            ha="center", va="center", fontsize=20, fontweight="bold",
            color=C_TEXT, family="sans-serif")
    ax.text(9, 11.2, "USGS sensor + lab data  \u2192  multi-target water-quality estimation",
            ha="center", va="center", fontsize=11, color="#64748B")

    # ── Column positions ────────────────────────────────────────────
    # Col 1: Data sources    x ~ 0.5 – 4.5
    # Col 2: Processing      x ~ 5.5 – 9.5
    # Col 3: Feature tiers   x ~ 10.5 – 14
    # Col 4: Model+Output    x ~ 14.5 – 17.5

    bw = 3.8   # box width (sources)
    bh = 0.65  # box height
    pw = 3.5   # processing box width
    fw = 3.2   # feature/tier box width
    mw = 3.0   # model/output box width

    # ── COLUMN 1: External Data Sources ─────────────────────────────
    sx = 0.5
    col1_header_y = 10.4
    ax.text(sx + bw / 2, col1_header_y, "EXTERNAL DATA SOURCES",
            ha="center", va="center", fontsize=10, fontweight="bold",
            color=C_SOURCE)

    sources = [
        ("USGS NWIS API\nContinuous sensors (15-min)\nTurbidity, Cond, DO, pH, Temp, Q", 9.4),
        ("USGS NWIS API\nDiscrete lab samples\nSSC, TP, Nitrate, OrthoP", 8.4),
        ("USGS ScienceBase\nGAGES-II catchment attributes\n9,067 sites \u00b7 576 attributes", 7.4),
        ("USGS NLDI\nBasin boundaries +\nwatershed characteristics", 6.4),
        ("MRLC\nNLCD land cover raster", 5.55),
    ]
    for label, y in sources:
        draw_box(ax, sx, y, bw, bh, label, C_SOURCE, C_SOURCE_FILL, fontsize=7.5)

    # ── COLUMN 2: Processing Steps ──────────────────────────────────
    px = 5.5
    col2_header_y = 10.4
    ax.text(px + pw / 2, col2_header_y, "PROCESSING STEPS",
            ha="center", va="center", fontsize=10, fontweight="bold",
            color="#16A34A")

    procs = [
        ("QC Filtering\nApproval status, qualifier codes\nIce +48h / Maintenance +4h buffers", 9.4),
        ("Temporal Alignment\n\u00b115 min matching of grab\nsamples to sensor readings", 8.4),
        ("Feature Engineering\nHydrograph position, cross-sensor\nratios, seasonality (sin/cos)", 7.4),
        ("Attribute Pruning\n576 \u2192 25 GAGES-II features", 6.55),
        ("NLCD Processing\nRaster \u2192 land cover %", 5.75),
        ("Attribute Merging\nGAGES-II + NLCD + NLDI\n\u2192 unified site attributes", 4.85),
    ]
    for label, y in procs:
        h = bh if "\n" in label and label.count("\n") <= 1 else bh
        draw_box(ax, px, y, pw, bh, label, C_PROC, C_PROC_FILL, fontsize=7.5)

    # ── COLUMN 3: Feature Tiers ─────────────────────────────────────
    fx = 10.5
    col3_header_y = 10.4
    ax.text(fx + fw / 2, col3_header_y, "FEATURE TIERS",
            ha="center", va="center", fontsize=10, fontweight="bold",
            color="#D97706")

    tiers = [
        ("Tier A: Sensor Only\n22 features\n(turbidity stats, Q, cond, DO,\npH, temp + engineered)", 9.1, 0.95),
        ("Tier B: + Basic Attributes\n24 features\n(+ lat, lon, drainage area,\nelevation)", 7.8, 0.95),
        ("Tier C: + Watershed Attrs\n49 features (4 categorical)\n(+ geology, land cover, soils,\nclimate, hydrology)", 6.5, 0.95),
    ]
    for label, y, h in tiers:
        draw_box(ax, fx, y, fw, h, label, C_FEAT, C_FEAT_FILL, fontsize=7.5)

    # ── COLUMN 4: Model Training ────────────────────────────────────
    mx = 14.5
    col4_header_y = 10.4
    ax.text(mx + mw / 2, col4_header_y, "MODEL & OUTPUTS",
            ha="center", va="center", fontsize=10, fontweight="bold",
            color=C_MODEL)

    # Model box
    draw_box(ax, mx, 8.7, mw, 1.0,
             "CatBoost\nLOGO Cross-Validation\n(leave-one-site-out)\nPer-site R\u00b2, KGE, RMSE",
             C_MODEL, C_MODEL_FILL, fontsize=8)

    # Output boxes
    outputs = [
        ("SSC Predictions\n(mg/L)", 7.5),
        ("TP Predictions\n(mg/L)", 6.7),
        ("Nitrate / OrthoP\n(characterized negatives)", 5.9),
    ]
    for label, y in outputs:
        draw_box(ax, mx, y, mw, 0.6, label, C_OUTPUT, C_OUTPUT_FILL, fontsize=8)

    # ── ARROWS: Sources \u2192 Processing ───────────────────────────────
    # Continuous sensors -> QC
    draw_arrow(ax, sx + bw, 9.4 + bh / 2, px, 9.4 + bh / 2, color=C_SOURCE)
    # Discrete samples -> Temporal Alignment
    draw_arrow(ax, sx + bw, 8.4 + bh / 2, px, 8.4 + bh / 2, color=C_SOURCE)
    # GAGES-II -> Attribute Pruning
    draw_arrow(ax, sx + bw, 7.4 + bh / 2, px, 6.55 + bh / 2, color=C_SOURCE)
    # NLDI -> Attribute Merging
    draw_arrow(ax, sx + bw, 6.4 + bh / 2, px, 4.85 + bh / 2, color=C_SOURCE)
    # NLCD -> NLCD Processing
    draw_arrow(ax, sx + bw, 5.55 + bh / 2, px, 5.75 + bh / 2, color=C_SOURCE)

    # ── ARROWS: Processing internal flow ────────────────────────────
    # QC -> Temporal Alignment
    draw_arrow(ax, px + pw / 2, 9.4, px + pw / 2, 8.4 + bh, color="#16A34A")
    # Temporal Alignment -> Feature Engineering
    draw_arrow(ax, px + pw / 2, 8.4, px + pw / 2, 7.4 + bh, color="#16A34A")
    # Attribute Pruning -> Attribute Merging
    draw_arrow(ax, px + pw / 2, 6.55, px + pw / 2, 4.85 + bh, color="#16A34A")
    # NLCD Processing -> Attribute Merging
    draw_arrow(ax, px + pw / 2 + 0.3, 5.75, px + pw / 2 + 0.3, 4.85 + bh, color="#16A34A")

    # ── ARROWS: Processing \u2192 Feature Tiers ────────────────────────
    # Feature Engineering -> Tier A
    draw_arrow(ax, px + pw, 7.4 + bh / 2, fx, 9.1 + 0.95 / 2, color="#16A34A")
    # Feature Engineering -> Tier B
    draw_arrow(ax, px + pw, 7.4 + bh / 2, fx, 7.8 + 0.95 / 2, color="#16A34A")
    # Attribute Merging -> Tier B
    draw_arrow(ax, px + pw, 4.85 + bh / 2, fx, 7.8 + 0.95 / 2, color="#16A34A")
    # Feature Engineering + Merging -> Tier C
    draw_arrow(ax, px + pw, 4.85 + bh / 2, fx, 6.5 + 0.95 / 2, color="#16A34A")

    # ── ARROWS: Feature Tiers \u2192 Model ───────────────────────────────
    draw_arrow(ax, fx + fw, 9.1 + 0.95 / 2, mx, 8.7 + 1.0 / 2 + 0.2, color="#D97706")
    draw_arrow(ax, fx + fw, 7.8 + 0.95 / 2, mx, 8.7 + 1.0 / 2, color="#D97706")
    draw_arrow(ax, fx + fw, 6.5 + 0.95 / 2, mx, 8.7 + 1.0 / 2 - 0.2, color="#D97706")

    # ── ARROWS: Model \u2192 Outputs ─────────────────────────────────────
    draw_arrow(ax, mx + mw / 2, 8.7, mx + mw / 2, 7.5 + 0.6, color=C_MODEL)
    draw_arrow(ax, mx + mw / 2 - 0.2, 7.5, mx + mw / 2 - 0.2, 6.7 + 0.6, color=C_OUTPUT)
    draw_arrow(ax, mx + mw / 2 + 0.2, 6.7, mx + mw / 2 + 0.2, 5.9 + 0.6, color=C_OUTPUT)

    # ── Legend ──────────────────────────────────────────────────────
    legend_items = [
        (C_SOURCE_FILL, C_SOURCE, "External Data Source"),
        (C_PROC_FILL, C_PROC, "Processing Step"),
        (C_FEAT_FILL, C_FEAT, "Feature Tier"),
        (C_MODEL_FILL, C_MODEL, "Model Training"),
        (C_OUTPUT_FILL, C_OUTPUT, "Prediction Output"),
    ]
    lx, ly = 0.5, 4.0
    for i, (fill, border, label) in enumerate(legend_items):
        yy = ly - i * 0.45
        draw_box(ax, lx, yy, 0.4, 0.3, "", border, fill, fontsize=7)
        ax.text(lx + 0.55, yy + 0.15, label, va="center", fontsize=8.5,
                color=C_TEXT)

    # ── Key stats annotation ────────────────────────────────────────
    stats_text = (
        "Key numbers\n"
        "\u2022 ~124 USGS sites\n"
        "\u2022 \u00b115 min alignment window\n"
        "\u2022 Ice buffer: +48 h\n"
        "\u2022 Maint. buffer: +4 h\n"
        "\u2022 576 \u2192 25 GAGES-II attrs\n"
        "\u2022 DL/2 for non-detects\n"
        "\u2022 CatBoost, 500 iter max"
    )
    ax.text(5.5, 3.5, stats_text, fontsize=7.5, color="#475569",
            va="top", ha="left", family="monospace",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#F1F5F9",
                      edgecolor="#CBD5E1", linewidth=1))

    plt.tight_layout(pad=0.5)
    fig.savefig(str(OUTPUT), dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    print(f"Saved flowchart to {OUTPUT}")
    plt.close(fig)


if __name__ == "__main__":
    main()
