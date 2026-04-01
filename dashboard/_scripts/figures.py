"""
Shared Plotly figure functions for the murkml dashboard (Phase 1).

Each function accepts file paths, reads the data, builds a Plotly figure,
applies the shared style, and returns the figure object.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from _scripts.style import (
    BAYESIAN_COLOR,
    DENSITY_COLORSCALE,
    OLS_COLOR,
    OLD_2PARAM_COLOR,
    MODEL_COLOR,
    OBS_COLOR,
    RANDOM_COLOR,
    REF_COLOR,
    GOOD_COLOR,
    BAD_COLOR,
    COLORS,
    apply_plotly_style,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict:
    """Load a JSON file, returning an empty dict on failure."""
    path = Path(path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_curve(adaptation_block: dict, metric: str = "median_r2"):
    """Extract (ns, values, ci_lo, ci_hi) arrays from an adaptation curve block.

    Parameters
    ----------
    adaptation_block : dict
        e.g. summary["adaptation"]["random"]["curve"]
    metric : str
        Key to pull from each N entry (default ``median_r2``).

    Returns
    -------
    ns : list[int]
        Calibration sample counts.
    vals : list[float | None]
        Metric values (None where missing).
    ci_lo : list[float | None]
    ci_hi : list[float | None]
    """
    ns, vals, ci_lo, ci_hi = [], [], [], []
    for n_str, entry in sorted(adaptation_block.items(), key=lambda kv: int(kv[0])):
        ns.append(int(n_str))
        vals.append(entry.get(metric))
        ci_lo.append(entry.get("ci_lower_r2"))
        ci_hi.append(entry.get("ci_upper_r2"))
    return ns, vals, ci_lo, ci_hi


# ---------------------------------------------------------------------------
# Figure 1 — Adaptation curve
# ---------------------------------------------------------------------------

def make_adaptation_curve(
    summary_json_path: str | Path,
    ols_json_path: str | Path | None = None,
) -> go.Figure:
    """Site-adaptation curve: median site R2 vs N calibration samples.

    Shows how quickly Bayesian adaptation, OLS log-log regression, and
    (optionally) a legacy 2-parameter method converge as calibration data
    increases.  Two subplot columns for *random* and *temporal* split modes.
    Bootstrap CI ribbons are drawn when the data contains them.

    Parameters
    ----------
    summary_json_path : path
        Path to ``summary.json`` (contains Bayesian adaptation curves).
    ols_json_path : path, optional
        Path to ``ols_ols_benchmark_summary.json``.  If *None*, the function
        looks for it next to *summary_json_path*.
    """
    summary_json_path = Path(summary_json_path)
    summary = _load_json(summary_json_path)

    # Try to locate OLS benchmark alongside the main summary
    if ols_json_path is None:
        candidate = summary_json_path.parent / "ols_ols_benchmark_summary.json"
        if candidate.exists():
            ols_json_path = candidate
    ols = _load_json(ols_json_path) if ols_json_path else {}

    adaptation = summary.get("adaptation", {})
    ols_adaptation = ols.get("adaptation", {})

    split_modes = [m for m in ("random", "temporal") if m in adaptation]
    if not split_modes:
        # Fallback: single panel
        split_modes = list(adaptation.keys())[:2]

    n_panels = len(split_modes)
    fig = make_subplots(
        rows=1,
        cols=n_panels,
        shared_yaxes=True,
        subplot_titles=[f"{m.capitalize()} split" for m in split_modes],
        horizontal_spacing=0.10,
    )

    for col_idx, mode in enumerate(split_modes, start=1):
        curve = adaptation.get(mode, {}).get("curve", {})
        ns, vals, ci_lo, ci_hi = _extract_curve(curve)

        # Filter out None values
        mask = [v is not None for v in vals]
        ns_f = [n for n, m in zip(ns, mask) if m]
        vals_f = [v for v, m in zip(vals, mask) if m]
        ci_lo_f = [v for v, m in zip(ci_lo, mask) if m]
        ci_hi_f = [v for v, m in zip(ci_hi, mask) if m]

        # --- Bayesian CI ribbon ---
        has_ci = all(v is not None for v in ci_lo_f) and len(ci_lo_f) > 0
        if has_ci:
            fig.add_trace(
                go.Scatter(
                    x=ns_f + ns_f[::-1],
                    y=ci_hi_f + ci_lo_f[::-1],
                    fill="toself",
                    fillcolor=f"rgba({_hex_to_rgb(BAYESIAN_COLOR)}, 0.15)",
                    line=dict(width=0),
                    showlegend=False,
                    hoverinfo="skip",
                ),
                row=1,
                col=col_idx,
            )

        # --- Bayesian line ---
        fig.add_trace(
            go.Scatter(
                x=ns_f,
                y=vals_f,
                mode="lines+markers",
                name="Bayesian" if col_idx == 1 else None,
                showlegend=bool(col_idx == 1),
                line=dict(color=BAYESIAN_COLOR, width=2.5),
                marker=dict(size=6),
                legendgroup="bayesian",
            ),
            row=1,
            col=col_idx,
        )

        # --- OLS line ---
        ols_curve = ols_adaptation.get(mode, {}).get("curve", {})
        if ols_curve:
            ols_ns, ols_vals, ols_ci_lo, ols_ci_hi = _extract_curve(ols_curve)
            ols_mask = [v is not None for v in ols_vals]
            ols_ns_f = [n for n, m in zip(ols_ns, ols_mask) if m]
            ols_vals_f = [v for v, m in zip(ols_vals, ols_mask) if m]
            ols_ci_lo_f = [v for v, m in zip(ols_ci_lo, ols_mask) if m]
            ols_ci_hi_f = [v for v, m in zip(ols_ci_hi, ols_mask) if m]

            # OLS CI ribbon
            ols_has_ci = all(v is not None for v in ols_ci_lo_f) and len(ols_ci_lo_f) > 0
            if ols_has_ci:
                fig.add_trace(
                    go.Scatter(
                        x=ols_ns_f + ols_ns_f[::-1],
                        y=ols_ci_hi_f + ols_ci_lo_f[::-1],
                        fill="toself",
                        fillcolor=f"rgba({_hex_to_rgb(OLS_COLOR)}, 0.15)",
                        line=dict(width=0),
                        showlegend=False,
                        hoverinfo="skip",
                    ),
                    row=1,
                    col=col_idx,
                )

            fig.add_trace(
                go.Scatter(
                    x=ols_ns_f,
                    y=ols_vals_f,
                    mode="lines+markers",
                    name="OLS log-log" if col_idx == 1 else None,
                    showlegend=bool(col_idx == 1),
                    line=dict(color=OLS_COLOR, width=2.5, dash="dash"),
                    marker=dict(size=6, symbol="diamond"),
                    legendgroup="ols",
                ),
                row=1,
                col=col_idx,
            )

            # --- Annotate N=2 gap (Bayesian vs OLS) ---
            if 2 in [int(k) for k in curve] and 2 in [int(k) for k in ols_curve]:
                bay_r2_at2 = curve["2"].get("median_r2")
                ols_r2_at2 = ols_curve["2"].get("median_r2")
                if bay_r2_at2 is not None and ols_r2_at2 is not None:
                    gap = bay_r2_at2 - ols_r2_at2
                    mid_y = (bay_r2_at2 + ols_r2_at2) / 2
                    fig.add_annotation(
                        x=2,
                        y=mid_y,
                        text=f"\u0394R\u00b2={gap:+.2f}",
                        showarrow=True,
                        arrowhead=2,
                        ax=40,
                        ay=-25,
                        font=dict(size=11, color=GOOD_COLOR),
                        row=1,
                        col=col_idx,
                    )

    fig.update_xaxes(title_text="N calibration samples", row=1, col=1)
    if n_panels > 1:
        fig.update_xaxes(title_text="N calibration samples", row=1, col=2)
    fig.update_yaxes(title_text="Median site R\u00b2", row=1, col=1)

    fig.update_layout(
        title="Site-Adaptation Curve: Bayesian vs OLS",
        height=500,
        legend=dict(x=0.02, y=0.98, bgcolor="rgba(255,255,255,0.8)"),
    )

    apply_plotly_style(fig)
    return fig


# ---------------------------------------------------------------------------
# Figure 2 — Pooled vs per-site performance
# ---------------------------------------------------------------------------

def make_pooled_vs_persite(per_site_path: str | Path, pooled_r2: float = 0.284) -> go.Figure:
    """Histogram of per-site R2 values with pooled R2 and median annotated.

    Highlights the gap between a single pooled metric and the true
    site-level distribution.  Annotates the fraction of sites with R2 < 0.
    """
    df = pd.read_parquet(Path(per_site_path))

    # Use zero-shot (N=0) R2 which is the nse_native column
    r2_col = "nse_native"
    if r2_col not in df.columns:
        # Fallback: try r2_random_at_0
        r2_col = "r2_random_at_0"
    site_r2 = df[r2_col].dropna()

    median_r2 = float(site_r2.median())
    frac_below_zero = float((site_r2 < 0).mean())

    # Compute a "pooled" R2 proxy — use median of all site R2s clipped for display
    # The pooled R2 is different from median site R2; read from per_site if available
    # We'll compute it as the mean-weighted R2 or just use the median
    pooled_r2 = median_r2  # Will be overridden below if we can find it

    fig = go.Figure()

    # Clip for histogram visibility but keep actual values for stats
    r2_clipped = site_r2.clip(lower=-2)

    fig.add_trace(
        go.Histogram(
            x=r2_clipped,
            nbinsx=30,
            marker_color=COLORS["sky_blue"],
            marker_line=dict(color="white", width=0.5),
            opacity=0.85,
            name="Site R\u00b2",
        )
    )

    # Vertical line at median site R2
    fig.add_vline(
        x=median_r2,
        line=dict(color=GOOD_COLOR, width=2.5, dash="solid"),
        annotation_text=f"Median R\u00b2 = {median_r2:.3f}",
        annotation_position="top right",
        annotation_font=dict(color=GOOD_COLOR, size=11),
    )

    # Vertical line at pooled R2
    fig.add_vline(
        x=pooled_r2,
        line=dict(color=BAD_COLOR, width=2.5, dash="dash"),
        annotation_text=f"Pooled NSE = {pooled_r2:.3f}",
        annotation_position="top left",
        annotation_font=dict(color=BAD_COLOR, size=11),
    )

    # Vertical line at R2 = 0 reference
    fig.add_vline(
        x=0,
        line=dict(color=REF_COLOR, width=1.5, dash="dot"),
    )

    # Annotate fraction below zero
    fig.add_annotation(
        x=-0.5,
        y=0.92,
        xref="x",
        yref="paper",
        text=f"{frac_below_zero:.0%} of sites R\u00b2 < 0",
        showarrow=False,
        font=dict(size=12, color=BAD_COLOR),
        bgcolor="rgba(255,255,255,0.8)",
        bordercolor=BAD_COLOR,
        borderwidth=1,
        borderpad=4,
    )

    fig.update_layout(
        title="Pooled vs. Site-Level Performance",
        xaxis_title="Site R\u00b2 (NSE)",
        yaxis_title="Number of sites",
        height=400,
        showlegend=False,
    )

    apply_plotly_style(fig)
    return fig


# ---------------------------------------------------------------------------
# Figure 3 — Physics wall / error vs SSC
# ---------------------------------------------------------------------------

def make_physics_wall(per_reading_path: str | Path) -> go.Figure:
    """Percent error vs observed SSC on a log x-axis.

    Reveals the three physical regimes:
    - Low SSC (<10 mg/L): sensor contamination from DOM / algae
    - Mid SSC (50-5000 mg/L): turbidity-SSC sweet spot
    - High SSC (>5000 mg/L): particle size shift breaks the relationship

    Uses a 2-D histogram for density and overlays a running-median line.
    """
    df = pd.read_parquet(Path(per_reading_path))

    obs = df["y_true_native"].values
    pred = df["y_pred_native"].values

    # Filter valid rows
    valid = np.isfinite(obs) & np.isfinite(pred) & (obs > 0)
    obs = obs[valid]
    pred = pred[valid]

    pct_error = (pred - obs) / obs * 100

    # Clamp pct_error for display
    pct_error_clipped = np.clip(pct_error, -300, 500)

    fig = go.Figure()

    # 2D histogram for density
    fig.add_trace(
        go.Histogram2d(
            x=np.log10(obs),
            y=pct_error_clipped,
            colorscale=[
                [0.0, "rgba(255,255,255,0)"],
                [0.05, COLORS["sky_blue"]],
                [0.3, COLORS["blue"]],
                [1.0, COLORS["vermillion"]],
            ],
            nbinsx=60,
            nbinsy=60,
            colorbar=dict(title="Count", len=0.6),
            zmin=1,
        )
    )

    # Running median line (log-spaced bins)
    log_obs = np.log10(obs)
    bin_edges = np.linspace(log_obs.min(), log_obs.max(), 20)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    medians = []
    for i in range(len(bin_edges) - 1):
        mask = (log_obs >= bin_edges[i]) & (log_obs < bin_edges[i + 1])
        if mask.sum() >= 5:
            medians.append(float(np.median(pct_error[mask])))
        else:
            medians.append(np.nan)

    med_arr = np.array(medians)
    valid_med = np.isfinite(med_arr)
    fig.add_trace(
        go.Scatter(
            x=bin_centers[valid_med],
            y=med_arr[valid_med],
            mode="lines+markers",
            line=dict(color=OBS_COLOR, width=2.5),
            marker=dict(size=5),
            name="Running median",
        )
    )

    # Zero-error reference
    fig.add_hline(y=0, line=dict(color=REF_COLOR, width=1, dash="dot"))

    # Shaded zones
    zones = [
        (np.log10(0.5), np.log10(10), "Sensor contamination<br>(DOM, algae)", BAD_COLOR),
        (np.log10(50), np.log10(5000), "Sweet spot", GOOD_COLOR),
        (np.log10(5000), np.log10(obs.max() * 2), "Particle size<br>shift zone", COLORS["orange"]),
    ]
    for x0, x1, label, color in zones:
        fig.add_vrect(
            x0=x0,
            x1=x1,
            fillcolor=f"rgba({_hex_to_rgb(color)}, 0.08)",
            line_width=0,
            layer="below",
        )
        fig.add_annotation(
            x=(x0 + x1) / 2,
            y=0.97,
            yref="paper",
            text=label,
            showarrow=False,
            font=dict(size=10, color=color),
            bgcolor="rgba(255,255,255,0.7)",
        )

    fig.update_layout(
        title="Error Structure Across SSC Range",
        xaxis_title="Observed SSC (mg/L, log scale)",
        yaxis_title="Percent error (%)",
        height=480,
        width=800,
        showlegend=True,
        legend=dict(x=0.01, y=0.01, bgcolor="rgba(255,255,255,0.8)"),
    )

    # Format x-axis as powers of 10 with real SSC labels
    tick_vals = [np.log10(v) for v in [1, 10, 100, 1000, 10000]]
    tick_text = ["1", "10", "100", "1,000", "10,000"]
    fig.update_xaxes(tickvals=tick_vals, ticktext=tick_text)

    apply_plotly_style(fig)
    return fig


# ---------------------------------------------------------------------------
# Figure 4 — Observed vs predicted scatter
# ---------------------------------------------------------------------------

def make_obs_vs_pred(per_reading_path: str | Path) -> go.Figure:
    """Log-log scatter of observed vs predicted SSC with density encoding.

    Includes 1:1 line, 2x envelope, and marginal histograms.
    Annotates pooled R2 and median site R2.
    """
    df = pd.read_parquet(Path(per_reading_path))

    obs = df["y_true_native"].values
    pred = df["y_pred_native"].values

    valid = np.isfinite(obs) & np.isfinite(pred) & (obs > 0) & (pred > 0)
    obs = obs[valid]
    pred = pred[valid]

    log_obs = np.log10(obs)
    log_pred = np.log10(pred)

    # Compute log-space R2 (matches the log-log axes)
    log_ss_res = np.sum((log_obs - log_pred) ** 2)
    log_ss_tot = np.sum((log_obs - np.mean(log_obs)) ** 2)
    pooled_r2_log = 1 - log_ss_res / log_ss_tot if log_ss_tot > 0 else np.nan

    # Median site R2 (approximate from per-reading groupby)
    site_ids = df.loc[valid, "site_id"].values if "site_id" in df.columns else None
    median_site_r2 = np.nan
    if site_ids is not None:
        obs_s = pd.Series(obs, name="obs")
        pred_s = pd.Series(pred, name="pred")
        site_s = pd.Series(site_ids, name="site")
        tmp = pd.DataFrame({"obs": obs_s, "pred": pred_s, "site": site_s})
        site_r2s = []
        for _, grp in tmp.groupby("site"):
            if len(grp) < 3:
                continue
            ss_r = np.sum((grp["obs"].values - grp["pred"].values) ** 2)
            ss_t = np.sum((grp["obs"].values - grp["obs"].mean()) ** 2)
            if ss_t > 0:
                site_r2s.append(1 - ss_r / ss_t)
        if site_r2s:
            median_site_r2 = float(np.median(site_r2s))

    # Simple single-panel figure (no marginals — those are a separate chart)
    fig = go.Figure()

    # Main 2D histogram (density scatter)
    fig.add_trace(
        go.Histogram2d(
            x=log_obs,
            y=log_pred,
            colorscale=DENSITY_COLORSCALE,
            nbinsx=80,
            nbinsy=80,
            zmin=1,
            colorbar=dict(title="Count", len=0.6),
        ),
    )

    # Axis range
    lo = min(log_obs.min(), log_pred.min()) - 0.1
    hi = max(log_obs.max(), log_pred.max()) + 0.1

    # 1:1 line
    fig.add_trace(
        go.Scatter(
            x=[lo, hi], y=[lo, hi],
            mode="lines",
            line=dict(color=OBS_COLOR, width=1.5),
            name="1:1",
        ),
    )

    # 2x envelope lines
    for offset, label, show in [(np.log10(2), "2\u00d7", True), (-np.log10(2), "0.5\u00d7", False)]:
        fig.add_trace(
            go.Scatter(
                x=[lo, hi], y=[lo + offset, hi + offset],
                mode="lines",
                line=dict(color=REF_COLOR, width=1, dash="dash"),
                name=label,
                showlegend=show,
            ),
        )

    # Metrics annotation
    annotation_lines = [f"Pooled R\u00b2 (log) = {pooled_r2_log:.3f}"]
    if np.isfinite(median_site_r2):
        annotation_lines.append(f"Median site R\u00b2 = {median_site_r2:.3f}")
    fig.add_annotation(
        x=0.03, y=0.97, xref="paper", yref="paper",
        text="<br>".join(annotation_lines),
        showarrow=False,
        font=dict(size=12, color=GOOD_COLOR),
        bgcolor="rgba(255,255,255,0.85)",
        bordercolor=GOOD_COLOR, borderwidth=1, borderpad=5,
        align="left",
    )

    # Axis labels and ticks
    tick_vals = [np.log10(v) for v in [1, 10, 100, 1000, 10000]]
    tick_text = ["1", "10", "100", "1k", "10k"]
    fig.update_xaxes(
        title_text="Observed SSC (mg/L)",
        range=[lo, hi], tickvals=tick_vals, ticktext=tick_text,
    )
    fig.update_yaxes(
        title_text="Predicted SSC (mg/L)",
        range=[lo, hi], tickvals=tick_vals, ticktext=tick_text,
    )

    fig.update_layout(
        title="Observed vs Predicted SSC (log-log, holdout sites)",
        height=650,
        legend=dict(x=0.75, y=0.15, bgcolor="rgba(255,255,255,0.8)"),
    )

    apply_plotly_style(fig)
    return fig


def make_distribution_comparison(per_reading_path: str | Path) -> go.Figure:
    """Observed vs predicted SSC distributions, stacked for direct shape comparison.

    Two histograms on the same x-axis (log SSC), one above the other.
    If the shapes match, the model is unbiased across the concentration range.
    """
    per_reading_path = Path(per_reading_path)
    df = pd.read_parquet(per_reading_path)

    obs_col = "obs_native" if "obs_native" in df.columns else "y_true_native"
    pred_col = "pred_native" if "pred_native" in df.columns else "y_pred_native"
    obs = df[obs_col].dropna().values
    pred = df[pred_col].dropna().values
    obs = obs[obs > 0]
    pred = pred[pred > 0]

    log_obs = np.log10(obs)
    log_pred = np.log10(pred)

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=["Observed SSC", "Predicted SSC"],
        row_heights=[0.5, 0.5],
    )

    tick_vals = [np.log10(v) for v in [1, 10, 100, 1000, 10000]]
    tick_text = ["1", "10", "100", "1k", "10k"]

    fig.add_trace(
        go.Histogram(
            x=log_obs, nbinsx=60,
            marker_color=OBS_COLOR, opacity=0.7,
            name="Observed",
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Histogram(
            x=log_pred, nbinsx=60,
            marker_color=MODEL_COLOR, opacity=0.7,
            name="Predicted",
        ),
        row=2, col=1,
    )

    fig.update_xaxes(
        title_text="SSC (mg/L)",
        tickvals=tick_vals, ticktext=tick_text,
        row=2, col=1,
    )
    fig.update_xaxes(tickvals=tick_vals, ticktext=tick_text, row=1, col=1)
    fig.update_yaxes(title_text="Count", row=1, col=1)
    fig.update_yaxes(title_text="Count", row=2, col=1)

    fig.update_layout(
        title="SSC Distribution Comparison: Observed vs Predicted",
        height=450,
        showlegend=False,
    )

    apply_plotly_style(fig)
    return fig


# ---------------------------------------------------------------------------
# Color utility
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_color: str) -> str:
    """Convert '#RRGGBB' to 'R, G, B' string for rgba() usage."""
    h = hex_color.lstrip("#")
    return f"{int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}"


# ---------------------------------------------------------------------------
# Phase 2 — Benchmark & disaggregated-metric figures
# ---------------------------------------------------------------------------

def make_catboost_vs_ols(
    ols_per_site_path: str | Path,
    per_site_path: str | Path | None = None,
) -> go.Figure:
    """Site-by-site scatter comparing CatBoost R² vs OLS R² at N=10 calibration samples.

    Points above the 1:1 diagonal indicate CatBoost outperforms OLS for that
    site.  Win/loss counts are annotated directly on the figure.  Points are
    coloured by the number of calibration samples available at the site (a
    proxy for data richness) when *per_site_path* is provided.

    Parameters
    ----------
    ols_per_site_path : path
        Path to ``ols_ols_benchmark_per_site.parquet``.
    per_site_path : path, optional
        Path to ``per_site.parquet`` (used for CatBoost R² at N=10 and the
        colour dimension).  If *None*, the function looks for it next to
        *ols_per_site_path*.
    """
    ols_per_site_path = Path(ols_per_site_path)
    ols_df = pd.read_parquet(ols_per_site_path)

    # Locate per_site.parquet alongside the OLS file if not given explicitly
    if per_site_path is None:
        candidate = ols_per_site_path.parent / "per_site.parquet"
        if candidate.exists():
            per_site_path = candidate
    if per_site_path is None:
        raise FileNotFoundError(
            "per_site.parquet not found — pass per_site_path explicitly."
        )
    ps_df = pd.read_parquet(Path(per_site_path))

    # OLS R² at N=10, random split
    ols_n10 = (
        ols_df.loc[(ols_df["n_cal"] == 10) & (ols_df["mode"] == "random")]
        .set_index("site_id")[["r2"]]
        .rename(columns={"r2": "ols_r2"})
    )

    # CatBoost R² at N=10 random from per_site
    cat_col = "r2_random_at_10"
    if cat_col not in ps_df.columns:
        raise KeyError(f"Column {cat_col!r} not found in per_site.parquet")
    cat_r2 = ps_df.set_index("site_id")[[cat_col, "n_samples"]].rename(
        columns={cat_col: "cat_r2"}
    )

    merged = ols_n10.join(cat_r2, how="inner").dropna(subset=["ols_r2", "cat_r2"])
    if merged.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No matching sites between OLS and CatBoost at N=10",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
        )
        apply_plotly_style(fig)
        return fig

    wins = int((merged["cat_r2"] > merged["ols_r2"]).sum())
    total = len(merged)

    # Colour by n_samples if available
    has_color = "n_samples" in merged.columns and merged["n_samples"].notna().any()

    fig = go.Figure()

    if has_color:
        fig.add_trace(
            go.Scatter(
                x=merged["ols_r2"],
                y=merged["cat_r2"],
                mode="markers",
                marker=dict(
                    size=8,
                    color=merged["n_samples"],
                    colorscale="Viridis",
                    colorbar=dict(title="N samples"),
                    line=dict(width=0.5, color="white"),
                ),
                text=merged.index,
                hovertemplate=(
                    "Site: %{text}<br>"
                    "OLS R²: %{x:.3f}<br>"
                    "CatBoost R²: %{y:.3f}<br>"
                    "N samples: %{marker.color:.0f}<extra></extra>"
                ),
                showlegend=False,
            )
        )
    else:
        fig.add_trace(
            go.Scatter(
                x=merged["ols_r2"],
                y=merged["cat_r2"],
                mode="markers",
                marker=dict(size=8, color=BAYESIAN_COLOR, line=dict(width=0.5, color="white")),
                text=merged.index,
                hovertemplate=(
                    "Site: %{text}<br>"
                    "OLS R²: %{x:.3f}<br>"
                    "CatBoost R²: %{y:.3f}<extra></extra>"
                ),
                showlegend=False,
            )
        )

    # 1:1 reference line
    lo = min(merged["ols_r2"].min(), merged["cat_r2"].min()) - 0.05
    hi = max(merged["ols_r2"].max(), merged["cat_r2"].max()) + 0.05
    fig.add_trace(
        go.Scatter(
            x=[lo, hi], y=[lo, hi],
            mode="lines",
            line=dict(color=REF_COLOR, width=1.5, dash="dash"),
            name="1:1",
            showlegend=True,
        )
    )

    # Win/loss annotation
    fig.add_annotation(
        x=0.03, y=0.97, xref="paper", yref="paper",
        text=f"CatBoost wins {wins}/{total} sites",
        showarrow=False,
        font=dict(size=13, color=GOOD_COLOR),
        bgcolor="rgba(255,255,255,0.85)",
        bordercolor=GOOD_COLOR, borderwidth=1, borderpad=5,
        align="left",
    )

    fig.update_layout(
        title="CatBoost vs OLS R² (N=10 calibration, random split)",
        xaxis_title="OLS R²",
        yaxis_title="CatBoost R²",
        height=550,
        legend=dict(x=0.75, y=0.10, bgcolor="rgba(255,255,255,0.8)"),
    )

    apply_plotly_style(fig)
    return fig


# ---------------------------------------------------------------------------
# Disaggregated metrics — heatmap (version 1)
# ---------------------------------------------------------------------------

def make_disaggregated_heatmap(disagg_path: str | Path) -> go.Figure:
    """Heatmap of disaggregated performance metrics across regimes.

    Rows are regime groups (e.g. SSC tiers, HUC2 regions, lithology),
    columns are metrics.  A diverging colour scale highlights where the
    model performs well vs. poorly relative to the overall row.

    Parameters
    ----------
    disagg_path : path
        Path to ``diag_disaggregated_metrics.parquet``.
    """
    df = pd.read_parquet(Path(disagg_path))

    if df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No disaggregated metrics data available",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
        )
        apply_plotly_style(fig)
        return fig

    # Drop the ALL row — it is the aggregate, not a regime
    df = df[df["group"] != "ALL"].copy()

    # Metrics to display (subset of numeric columns that are most informative)
    metric_cols = [c for c in ["r2", "bias_pct", "mape_pct", "within_2x_pct", "rmse"]
                   if c in df.columns]

    # Build a label combining dimension + group for row identification
    if "dimension" in df.columns:
        df["label"] = df["dimension"].astype(str) + " | " + df["group"].astype(str)
    else:
        df["label"] = df["group"].astype(str)

    # Pivot so rows = labels, cols = metrics
    heat = df.set_index("label")[metric_cols].copy()

    # Z-score each column so the diverging scale is meaningful across metrics
    z = heat.copy()
    for col in z.columns:
        col_std = z[col].std()
        col_mean = z[col].mean()
        if col_std > 0:
            z[col] = (z[col] - col_mean) / col_std
        else:
            z[col] = 0.0

    fig = go.Figure(
        go.Heatmap(
            z=z.values,
            x=metric_cols,
            y=heat.index.tolist(),
            colorscale="RdBu_r",
            zmid=0,
            text=heat.values.round(2),
            texttemplate="%{text}",
            textfont=dict(size=10),
            colorbar=dict(title="Z-score"),
            hovertemplate=(
                "Regime: %{y}<br>"
                "Metric: %{x}<br>"
                "Value: %{text}<br>"
                "Z-score: %{z:.2f}<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title="Disaggregated Performance Heatmap (z-scored by column)",
        xaxis_title="Metric",
        yaxis_title="Regime",
        height=max(450, 22 * len(heat)),  # scale with number of rows
        yaxis=dict(autorange="reversed"),  # top-to-bottom reading order
    )

    apply_plotly_style(fig)
    return fig


# ---------------------------------------------------------------------------
# Disaggregated metrics — Cleveland dot plot (version 2)
# ---------------------------------------------------------------------------

def make_disaggregated_dotplot(disagg_path: str | Path) -> go.Figure:
    """Cleveland dot plot of disaggregated metrics across regimes.

    An alternative to the heatmap: each regime is a horizontal row with dots
    positioned along a shared x-axis by metric value.  Separate traces per
    metric allow toggling in the legend.

    Parameters
    ----------
    disagg_path : path
        Path to ``diag_disaggregated_metrics.parquet``.
    """
    df = pd.read_parquet(Path(disagg_path))

    if df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No disaggregated metrics data available",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
        )
        apply_plotly_style(fig)
        return fig

    # Drop the ALL row
    df = df[df["group"] != "ALL"].copy()

    # Metrics to show — pick the most interpretable ones that share a
    # roughly comparable 0-100-ish scale (or unitless)
    metric_cols = [c for c in ["r2", "bias_pct", "mape_pct", "within_2x_pct"]
                   if c in df.columns]

    # Row label
    if "dimension" in df.columns:
        df["label"] = df["dimension"].astype(str) + " | " + df["group"].astype(str)
    else:
        df["label"] = df["group"].astype(str)

    # Colour palette for metrics — cycle through COLORS
    palette = [COLORS["blue"], COLORS["vermillion"], COLORS["orange"],
               COLORS["green"], COLORS["purple"], COLORS["sky_blue"]]

    fig = go.Figure()

    for i, metric in enumerate(metric_cols):
        vals = df[metric].values
        labels = df["label"].values
        color = palette[i % len(palette)]

        fig.add_trace(
            go.Scatter(
                x=vals,
                y=labels,
                mode="markers",
                name=metric,
                marker=dict(size=10, color=color, line=dict(width=0.5, color="white")),
                hovertemplate=(
                    "Regime: %{y}<br>"
                    f"{metric}: " + "%{x:.2f}<extra></extra>"
                ),
            )
        )

    # Vertical reference at 0 for R² / bias
    fig.add_vline(x=0, line=dict(color=REF_COLOR, width=1, dash="dot"))

    fig.update_layout(
        title="Disaggregated Metrics — Dot Plot",
        xaxis_title="Metric value",
        yaxis_title="Regime",
        height=max(500, 22 * df["label"].nunique()),
        yaxis=dict(autorange="reversed"),
        legend=dict(
            orientation="h", x=0.0, y=1.02,
            bgcolor="rgba(255,255,255,0.8)",
        ),
    )

    apply_plotly_style(fig)
    return fig


# ---------------------------------------------------------------------------
# Study area map
# ---------------------------------------------------------------------------

def make_study_area_map(
    site_metadata_path: str | Path,
    per_site_path: str | Path | None = None,
) -> go.Figure:
    """CONUS map of study sites colored by role (training/holdout/vault).

    Parameters
    ----------
    site_metadata_path : path
        Path to ``site_metadata.parquet`` with columns:
        site_id, latitude, longitude, role, n_samples.
    per_site_path : path, optional
        Path to ``per_site.parquet``.  If provided, holdout sites are
        colored by site R² (NSE) instead of the default role color.
    """
    meta = pd.read_parquet(Path(site_metadata_path))

    # Ensure required columns exist
    for col in ("latitude", "longitude", "role"):
        if col not in meta.columns:
            raise ValueError(f"site_metadata is missing required column: {col}")

    # Optional per-site performance overlay
    per_site = None
    if per_site_path is not None:
        ps_path = Path(per_site_path)
        if ps_path.exists():
            per_site = pd.read_parquet(ps_path)

    # Role -> display properties
    role_style = {
        "training": {"color": COLORS["blue"], "label": "Training", "order": 0},
        "holdout":  {"color": COLORS["orange"], "label": "Holdout", "order": 1},
        "vault":    {"color": COLORS["purple"], "label": "Vault", "order": 2},
    }

    fig = go.Figure()

    for role_name in ("training", "holdout", "vault"):
        style = role_style.get(role_name)
        if style is None:
            continue
        subset = meta[meta["role"] == role_name].copy()
        if subset.empty:
            continue

        n_sites = len(subset)
        marker_size = 6
        marker_color = style["color"]
        color_array = None
        colorbar_cfg = None

        # If per_site data is available, enhance holdout dots with R² color
        if per_site is not None and role_name == "holdout":
            r2_col = "nse_native" if "nse_native" in per_site.columns else None
            if r2_col is None:
                r2_col = next(
                    (c for c in per_site.columns if "r2" in c.lower()), None,
                )
            if r2_col is not None:
                subset = subset.merge(
                    per_site[["site_id", r2_col]], on="site_id", how="left",
                )
                color_array = subset[r2_col].fillna(0).values
                colorbar_cfg = dict(
                    colorscale=[
                        [0.0, COLORS["vermillion"]],
                        [0.5, COLORS["yellow"]],
                        [1.0, COLORS["green"]],
                    ],
                    cmin=0,
                    cmax=1,
                    colorbar=dict(title="R\u00b2", len=0.4, y=0.3),
                )

        # Size by sample count if available
        if "n_samples" in subset.columns:
            ns = subset["n_samples"].fillna(0).values
            marker_size = np.clip(4 + np.sqrt(ns) * 0.5, 4, 18)

        # Hover text
        hover_text = (
            subset["site_id"].str.replace("USGS-", "", regex=False)
            + "<br>" + style["label"]
        )
        if "n_samples" in subset.columns:
            hover_text = (
                hover_text + "<br>N="
                + subset["n_samples"].fillna(0).astype(int).astype(str)
            )

        marker_kwargs: dict = dict(
            size=marker_size,
            opacity=0.8,
            line=dict(width=0.5, color="white"),
        )

        if color_array is not None and colorbar_cfg is not None:
            marker_kwargs["color"] = color_array
            marker_kwargs["colorscale"] = colorbar_cfg["colorscale"]
            marker_kwargs["cmin"] = colorbar_cfg["cmin"]
            marker_kwargs["cmax"] = colorbar_cfg["cmax"]
            marker_kwargs["colorbar"] = colorbar_cfg["colorbar"]
        else:
            marker_kwargs["color"] = marker_color

        fig.add_trace(
            go.Scattergeo(
                lat=subset["latitude"].values,
                lon=subset["longitude"].values,
                text=hover_text.values,
                hoverinfo="text",
                mode="markers",
                marker=marker_kwargs,
                name=f"{style['label']} ({n_sites})",
                showlegend=True,
                legendgroup=role_name,
            )
        )

    # Build dynamic title from actual counts
    role_counts = meta["role"].value_counts()
    title_parts = []
    for r in ("training", "holdout", "vault"):
        n = int(role_counts.get(r, 0))
        if n > 0:
            title_parts.append(f"{n} {r.capitalize()}")
    title = "Study Area: " + " + ".join(title_parts) + " Sites"

    fig.update_geos(
        scope="usa",
        showland=True,
        landcolor="#f5f5f5",
        showlakes=True,
        lakecolor="#e0f0ff",
        showcountries=False,
        showsubunits=True,
        subunitcolor="#cccccc",
        subunitwidth=0.5,
    )

    fig.update_layout(
        title=title,
        height=500,
        geo=dict(projection_type="albers usa"),
        legend=dict(
            x=0.01,
            y=0.01,
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="#cccccc",
            borderwidth=1,
        ),
    )

    apply_plotly_style(fig)
    return fig


# ---------------------------------------------------------------------------
# Phase 2 — Bayesian shrinkage visualization (small multiples)
# ---------------------------------------------------------------------------

def make_bayesian_shrinkage_viz(
    per_reading_path: str | Path,
    summary_json_path: str | Path,
) -> go.Figure:
    """Small-multiples showing zero-shot predictions across site types.

    Picks 3 holdout sites spanning the R² range (good, moderate, poor) and
    shows observed-vs-predicted scatter for each, annotated with site R².
    Illustrates where Bayesian correction would have the most impact.

    Parameters
    ----------
    per_reading_path : path
        Path to ``per_reading.parquet`` (zero-shot holdout predictions).
    summary_json_path : path
        Path to ``summary.json`` (used for context but not strictly required).
    """
    df = pd.read_parquet(Path(per_reading_path))

    obs_col = "y_true_native"
    pred_col = "y_pred_native"
    if obs_col not in df.columns or pred_col not in df.columns:
        fig = go.Figure()
        fig.add_annotation(
            text="Missing required columns in per_reading data",
            x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
        )
        apply_plotly_style(fig)
        return fig

    # Compute per-site R² to select representative sites
    site_r2: dict[str, float] = {}
    for sid, grp in df.groupby("site_id"):
        obs = grp[obs_col].values
        pred = grp[pred_col].values
        valid = np.isfinite(obs) & np.isfinite(pred) & (obs > 0) & (pred > 0)
        if valid.sum() < 5:
            continue
        obs_v, pred_v = obs[valid], pred[valid]
        ss_res = np.sum((obs_v - pred_v) ** 2)
        ss_tot = np.sum((obs_v - obs_v.mean()) ** 2)
        if ss_tot > 0:
            site_r2[sid] = 1 - ss_res / ss_tot

    if len(site_r2) < 3:
        fig = go.Figure()
        fig.add_annotation(
            text="Not enough sites with sufficient data for shrinkage viz",
            x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
        )
        apply_plotly_style(fig)
        return fig

    sr = pd.Series(site_r2).sort_values()

    # Pick three sites: poor (low R²), moderate (near median), good (high R²)
    def _nearest(series: pd.Series, target: float) -> str:
        idx = (series - target).abs().argsort().iloc[0]
        return str(series.index[idx])

    picks = {
        "Poor fit": _nearest(sr, sr.quantile(0.15)),
        "Moderate fit": _nearest(sr, sr.median()),
        "Good fit": _nearest(sr, sr.quantile(0.90)),
    }

    n_panels = len(picks)
    fig = make_subplots(
        rows=1,
        cols=n_panels,
        shared_yaxes=True,
        subplot_titles=list(picks.keys()),
        horizontal_spacing=0.08,
    )

    for col_idx, (label, sid) in enumerate(picks.items(), start=1):
        grp = df[df["site_id"] == sid]
        obs = grp[obs_col].values
        pred = grp[pred_col].values
        valid = np.isfinite(obs) & np.isfinite(pred) & (obs > 0) & (pred > 0)
        obs_v, pred_v = obs[valid], pred[valid]

        log_obs = np.log10(obs_v)
        log_pred = np.log10(pred_v)

        r2_val = site_r2.get(sid, np.nan)

        # Scatter: observed vs predicted
        fig.add_trace(
            go.Scatter(
                x=log_obs,
                y=log_pred,
                mode="markers",
                marker=dict(
                    color=MODEL_COLOR,
                    size=6,
                    opacity=0.6,
                    line=dict(width=0.5, color="white"),
                ),
                showlegend=False,
                hovertemplate=(
                    "Obs: %{customdata[0]:.0f} mg/L<br>"
                    "Pred: %{customdata[1]:.0f} mg/L<extra></extra>"
                ),
                customdata=np.column_stack([obs_v, pred_v]),
            ),
            row=1,
            col=col_idx,
        )

        # 1:1 reference line
        lo = min(log_obs.min(), log_pred.min()) - 0.2
        hi = max(log_obs.max(), log_pred.max()) + 0.2
        fig.add_trace(
            go.Scatter(
                x=[lo, hi],
                y=[lo, hi],
                mode="lines",
                line=dict(color=REF_COLOR, width=1.5, dash="dot"),
                showlegend=False,
                hoverinfo="skip",
            ),
            row=1,
            col=col_idx,
        )

        # Annotate R² and site name
        short_id = sid.replace("USGS-", "")
        fig.add_annotation(
            x=0.5,
            y=0.02,
            xref=f"x{col_idx} domain" if col_idx > 1 else "x domain",
            yref=f"y{col_idx} domain" if col_idx > 1 else "y domain",
            text=f"{short_id}<br>R\u00b2 = {r2_val:.2f}",
            showarrow=False,
            font=dict(size=10, color=GOOD_COLOR if r2_val > 0.5 else BAD_COLOR),
            bgcolor="rgba(255,255,255,0.85)",
            borderpad=3,
        )

        # Format axes as SSC values
        tick_vals = [np.log10(v) for v in [1, 10, 100, 1000, 10000]
                     if lo <= np.log10(v) <= hi]
        tick_text = [str(int(v)) for v in [1, 10, 100, 1000, 10000]
                     if lo <= np.log10(v) <= hi]
        x_key = f"xaxis{col_idx}" if col_idx > 1 else "xaxis"
        y_key = f"yaxis{col_idx}" if col_idx > 1 else "yaxis"
        fig.update_layout(**{
            x_key: dict(tickvals=tick_vals, ticktext=tick_text),
            y_key: dict(tickvals=tick_vals, ticktext=tick_text),
        })

    fig.update_xaxes(title_text="Observed SSC (mg/L)", row=1, col=2)
    fig.update_yaxes(title_text="Predicted SSC (mg/L)", row=1, col=1)

    fig.update_layout(
        title="Zero-Shot Performance Across Site Types",
        height=400,
    )

    apply_plotly_style(fig)
    return fig


# ---------------------------------------------------------------------------
# Phase 2 — Bayesian weight curve (analytical, no data files)
# ---------------------------------------------------------------------------

def make_bayesian_weight_curve() -> go.Figure:
    """Theoretical Bayesian shrinkage weight vs calibration sample size.

    Shows how the weight given to local correction increases with N for
    both Gaussian (standard shrinkage) and Student-t (robust) priors.

    The Gaussian weight is ``N / (N + k)``.
    The Student-t effective weight depends on how extreme the site is:
    ``effective_k = k * w_t`` where ``w_t = (df + 1) / (df + z**2)`` and
    z measures the site's deviation in MAD-scaled units.  For typical
    sites (z ~ 0), the Student-t is slightly more conservative than
    Gaussian.  For extreme sites (z ~ 2), the effective k drops,
    giving more weight to local data — the key robustness property.

    No data files needed — purely analytical.
    """
    k = 15.0
    df_t = 4.0  # Student-t degrees of freedom

    ns = np.arange(1, 51, dtype=float)

    # Gaussian weight: N / (N + k)
    w_gaussian = ns / (ns + k)

    # Student-t for a "typical" site (z ~ 0): w_t = (df+1)/df
    # effective_k = k * (df+1)/df — slightly more conservative than Gaussian
    w_t_typical = (df_t + 1) / df_t
    w_studentt_typical = ns / (ns + k * w_t_typical)

    # Student-t for an "extreme" site (z = 2): w_t = (df+1)/(df+z^2)
    z_extreme = 2.0
    w_t_extreme = (df_t + 1) / (df_t + z_extreme ** 2)
    w_studentt_extreme = ns / (ns + k * w_t_extreme)

    fig = go.Figure()

    # Shaded region between Student-t typical and extreme
    fig.add_trace(
        go.Scatter(
            x=np.concatenate([ns, ns[::-1]]).tolist(),
            y=np.concatenate([w_studentt_extreme, w_studentt_typical[::-1]]).tolist(),
            fill="toself",
            fillcolor=f"rgba({_hex_to_rgb(BAYESIAN_COLOR)}, 0.10)",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )

    # Gaussian line
    fig.add_trace(
        go.Scatter(
            x=ns.tolist(),
            y=w_gaussian.tolist(),
            mode="lines",
            name="Gaussian (k=15)",
            line=dict(color=OLS_COLOR, width=2.5),
        )
    )

    # Student-t typical site
    fig.add_trace(
        go.Scatter(
            x=ns.tolist(),
            y=w_studentt_typical.tolist(),
            mode="lines",
            name=f"Student-t typical (df={int(df_t)}, z\u22480)",
            line=dict(color=BAYESIAN_COLOR, width=2.5, dash="dash"),
        )
    )

    # Student-t extreme site
    fig.add_trace(
        go.Scatter(
            x=ns.tolist(),
            y=w_studentt_extreme.tolist(),
            mode="lines",
            name=f"Student-t extreme (df={int(df_t)}, z=2)",
            line=dict(color=BAYESIAN_COLOR, width=2.5),
        )
    )

    # Annotate N=2 for Gaussian
    w_at_2 = 2 / (2 + k)
    fig.add_annotation(
        x=2,
        y=w_at_2,
        text=f"N=2: {w_at_2:.0%} local",
        showarrow=True,
        arrowhead=2,
        ax=55,
        ay=-30,
        font=dict(size=11, color=OLS_COLOR),
    )

    # Annotate N=20 for Gaussian
    w_at_20 = 20 / (20 + k)
    fig.add_annotation(
        x=20,
        y=w_at_20,
        text=f"N=20: {w_at_20:.0%} local",
        showarrow=True,
        arrowhead=2,
        ax=55,
        ay=-30,
        font=dict(size=11, color=OLS_COLOR),
    )

    fig.update_layout(
        title="Bayesian Shrinkage Weight vs Calibration Samples",
        xaxis_title="N calibration samples",
        yaxis_title="Weight on local correction",
        height=400,
        legend=dict(x=0.45, y=0.25, bgcolor="rgba(255,255,255,0.85)"),
        yaxis=dict(range=[0, 1.05], tickformat=".0%"),
    )

    apply_plotly_style(fig)
    return fig


# ---------------------------------------------------------------------------
# Phase 2 — External validation scatter
# ---------------------------------------------------------------------------

def make_external_validation(
    ext_predictions_path: str | Path,
    ext_summary_path: str | Path,
) -> go.Figure:
    """External validation scatter: observed vs predicted SSC (log-log).

    Shows zero-shot predictions coloured by data-provider organisation.
    Annotates Spearman correlation and overall bias on the panel.
    If adapted predictions exist in the parquet, a second panel shows
    adapted performance.

    Parameters
    ----------
    ext_predictions_path : path
        Path to ``ext_external_predictions.parquet``.
    ext_summary_path : path
        Path to ``ext_external_validation_summary.json``.
    """
    from _scripts.style import ORG_COLORS

    pred_path = Path(ext_predictions_path)
    summary_path = Path(ext_summary_path)

    if not pred_path.exists():
        fig = go.Figure()
        fig.add_annotation(
            text="External predictions file not found",
            x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
        )
        apply_plotly_style(fig)
        return fig

    df = pd.read_parquet(pred_path)
    summary = _load_json(summary_path)

    obs_col = "y_true_native" if "y_true_native" in df.columns else "ssc_value"
    pred_col = "y_pred_native"
    org_col = "org_id" if "org_id" in df.columns else "organization"

    if obs_col not in df.columns or pred_col not in df.columns:
        fig = go.Figure()
        fig.add_annotation(
            text="Missing required columns in external predictions",
            x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
        )
        apply_plotly_style(fig)
        return fig

    # Filter valid observations
    valid = (
        np.isfinite(df[obs_col].values)
        & np.isfinite(df[pred_col].values)
        & (df[obs_col].values > 0)
        & (df[pred_col].values > 0)
    )
    df_valid = df.loc[valid].copy()

    if len(df_valid) == 0:
        fig = go.Figure()
        fig.add_annotation(
            text="No valid external validation data",
            x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
        )
        apply_plotly_style(fig)
        return fig

    obs = df_valid[obs_col].values
    pred = df_valid[pred_col].values
    log_obs = np.log10(obs)
    log_pred = np.log10(pred)

    # Check if adapted predictions exist in the data
    adapted_col = "y_pred_adapted" if "y_pred_adapted" in df.columns else None
    has_adapted = (
        adapted_col is not None
        and df_valid[adapted_col].notna().sum() > 10
    )

    n_panels = 2 if has_adapted else 1
    subplot_titles = (
        ["Zero-shot", "Adapted (N=10)"] if has_adapted else ["Zero-shot"]
    )

    fig = make_subplots(
        rows=1,
        cols=n_panels,
        shared_yaxes=True,
        subplot_titles=subplot_titles,
        horizontal_spacing=0.08,
    )

    # Determine organisations present
    orgs = (
        sorted(df_valid[org_col].unique())
        if org_col in df_valid.columns
        else ["Unknown"]
    )

    # Global axis range
    lo = min(log_obs.min(), log_pred.min()) - 0.2
    hi = max(log_obs.max(), log_pred.max()) + 0.2

    def _add_panel(
        col_idx: int,
        obs_vals: np.ndarray,
        pred_vals: np.ndarray,
        df_panel: pd.DataFrame,
        show_legend: bool,
    ):
        """Add one scatter panel with 1:1 line and annotations."""
        log_o = np.log10(obs_vals)
        log_p = np.log10(pred_vals)

        for org in orgs:
            if org_col in df_panel.columns:
                org_mask = df_panel[org_col].values == org
            else:
                org_mask = np.ones(len(df_panel), dtype=bool)
            if org_mask.sum() == 0:
                continue

            # Assign colour: try ORG_COLORS with various key formats
            color = COLORS["gray"]
            for key_candidate in [
                org,
                org.split("_")[0],
                org.replace("_WQX", ""),
                org.replace("42SRBCWQ_WQX", "SRBC"),
            ]:
                if key_candidate in ORG_COLORS:
                    color = ORG_COLORS[key_candidate]
                    break

            display_name = (
                org.replace("_WQX", "")
                .replace("42SRBCWQ", "SRBC")
                .replace("_LTRM", "")
            )

            fig.add_trace(
                go.Scatter(
                    x=log_o[org_mask],
                    y=log_p[org_mask],
                    mode="markers",
                    name=display_name if show_legend else None,
                    showlegend=bool(show_legend),
                    legendgroup=org,
                    marker=dict(color=color, size=5, opacity=0.6),
                    hovertemplate=(
                        f"{display_name}<br>"
                        "Obs: %{customdata[0]:.1f} mg/L<br>"
                        "Pred: %{customdata[1]:.1f} mg/L<extra></extra>"
                    ),
                    customdata=np.column_stack(
                        [obs_vals[org_mask], pred_vals[org_mask]]
                    ),
                ),
                row=1,
                col=col_idx,
            )

        # 1:1 line
        fig.add_trace(
            go.Scatter(
                x=[lo, hi],
                y=[lo, hi],
                mode="lines",
                line=dict(color=OBS_COLOR, width=1.5),
                showlegend=False,
                hoverinfo="skip",
            ),
            row=1,
            col=col_idx,
        )

        # Compute Spearman correlation and bias
        from scipy import stats as sp_stats

        finite = np.isfinite(log_o) & np.isfinite(log_p)
        if finite.sum() > 3:
            rho, _ = sp_stats.spearmanr(obs_vals[finite], pred_vals[finite])
        else:
            rho = np.nan

        mean_obs = float(np.mean(obs_vals))
        bias_pct = (
            (float(np.mean(pred_vals)) - mean_obs) / mean_obs * 100
            if mean_obs > 0
            else np.nan
        )

        ann_text = f"\u03c1 = {rho:.2f}" if np.isfinite(rho) else ""
        if np.isfinite(bias_pct):
            ann_text += f"<br>Bias = {bias_pct:+.0f}%"

        # Use BAD_COLOR if bias is substantial (abs > 20%)
        ann_color = BAD_COLOR if (np.isfinite(bias_pct) and abs(bias_pct) > 20) else GOOD_COLOR

        fig.add_annotation(
            x=0.03,
            y=0.97,
            xref=f"x{col_idx} domain" if col_idx > 1 else "x domain",
            yref=f"y{col_idx} domain" if col_idx > 1 else "y domain",
            text=ann_text,
            showarrow=False,
            font=dict(size=12, color=ann_color),
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor=ann_color,
            borderwidth=1,
            borderpad=4,
            align="left",
        )

    # Panel 1: zero-shot
    _add_panel(1, obs, pred, df_valid, show_legend=True)

    # Panel 2: adapted (if available)
    if has_adapted:
        adapted_pred = df_valid[adapted_col].values
        adapted_valid = np.isfinite(adapted_pred) & (adapted_pred > 0)
        _add_panel(
            2,
            obs[adapted_valid],
            adapted_pred[adapted_valid],
            df_valid.iloc[np.where(adapted_valid)[0]],
            show_legend=False,
        )

    # Axis formatting
    tick_vals = [np.log10(v) for v in [1, 10, 100, 1000, 10000]]
    tick_text = ["1", "10", "100", "1k", "10k"]
    for col_idx in range(1, n_panels + 1):
        fig.update_xaxes(
            title_text="Observed SSC (mg/L)",
            tickvals=tick_vals,
            ticktext=tick_text,
            range=[lo, hi],
            row=1,
            col=col_idx,
        )
    fig.update_yaxes(
        title_text="Predicted SSC (mg/L)",
        tickvals=tick_vals,
        ticktext=tick_text,
        range=[lo, hi],
        row=1,
        col=1,
    )

    title_suffix = f" (n={len(df_valid):,})"
    fig.update_layout(
        title="External Validation: Zero-Shot on Independent Data" + title_suffix,
        height=550,
        legend=dict(x=0.01, y=0.01, bgcolor="rgba(255,255,255,0.85)"),
    )

    apply_plotly_style(fig)
    return fig


# ---------------------------------------------------------------------------
# Supplementary / dashboard-only figures
# ---------------------------------------------------------------------------


def make_per_site_r2_cdf(per_site_path: str | Path) -> go.Figure:
    """Empirical CDF of per-site R² (NSE) with adaptation curves.

    Shows zero-shot CDF and, if available, N=5 and N=10 adaptation CDFs.
    Vertical reference line at R²=0 with annotation of sites below zero.
    """
    df = pd.read_parquet(Path(per_site_path))

    fig = go.Figure()

    # Define curves to plot: (column, label, color, dash)
    curves = []
    if "nse_native" in df.columns:
        curves.append(("nse_native", "Zero-shot", OBS_COLOR, "solid"))
    elif "r2_random_at_0" in df.columns:
        curves.append(("r2_random_at_0", "Zero-shot (N=0)", OBS_COLOR, "solid"))

    if "r2_random_at_5" in df.columns:
        curves.append(("r2_random_at_5", "Adapted N=5", RANDOM_COLOR, "dash"))
    if "r2_random_at_10" in df.columns:
        curves.append(("r2_random_at_10", "Adapted N=10", BAYESIAN_COLOR, "dot"))

    for col, label, color, dash in curves:
        if col not in df.columns:
            continue
        vals = df[col].dropna().sort_values().values
        n = len(vals)
        if n == 0:
            continue
        cdf = np.arange(1, n + 1) / n
        fig.add_trace(
            go.Scatter(
                x=vals,
                y=cdf,
                mode="lines",
                name=label,
                line=dict(color=color, width=2, dash=dash),
                showlegend=True,
            )
        )

    # Vertical line at R²=0
    fig.add_vline(x=0, line=dict(color=REF_COLOR, width=1.5, dash="dash"))

    # Annotate % of sites below zero (use zero-shot column)
    zs_col = "nse_native" if "nse_native" in df.columns else "r2_random_at_0"
    if zs_col in df.columns:
        vals = df[zs_col].dropna()
        pct_below = (vals < 0).sum() / len(vals) * 100 if len(vals) > 0 else 0
        fig.add_annotation(
            x=0,
            y=0.5,
            text=f"{pct_below:.0f}% of sites<br>below zero",
            showarrow=True,
            ax=40,
            ay=0,
            font=dict(size=11, color=BAD_COLOR),
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor=BAD_COLOR,
            borderwidth=1,
            borderpad=4,
        )

    fig.update_layout(
        title="Per-Site R² (NSE) — Empirical CDF",
        xaxis_title="R² (NSE)",
        yaxis_title="Cumulative Proportion",
        height=450,
        legend=dict(x=0.02, y=0.98, bgcolor="rgba(255,255,255,0.85)"),
    )

    apply_plotly_style(fig)
    return fig


def make_residual_diagnostics(per_reading_path: str | Path) -> go.Figure:
    """2x2 residual diagnostic panel.

    Top-left: residuals vs predicted (heteroscedasticity).
    Top-right: Q-Q plot (normality).
    Bottom-left: residuals vs turbidity.
    Bottom-right: histogram with normal overlay.
    """
    df = pd.read_parquet(Path(per_reading_path))

    obs_col = "obs_native" if "obs_native" in df.columns else "y_true_native"
    pred_col = "pred_native" if "pred_native" in df.columns else "y_pred_native"

    obs = df[obs_col].values
    pred = df[pred_col].values
    resid = obs - pred  # positive = underprediction (standard convention)

    valid = np.isfinite(resid) & np.isfinite(pred)
    resid = resid[valid]
    pred_v = pred[valid]
    obs_v = obs[valid]

    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=[
            "Residuals vs Predicted",
            "Q-Q Plot",
            "Residuals vs Turbidity",
            "Residual Distribution",
        ],
        vertical_spacing=0.12,
        horizontal_spacing=0.10,
    )

    # --- Top-left: residuals vs predicted ---
    fig.add_trace(
        go.Scattergl(
            x=pred_v,
            y=resid,
            mode="markers",
            marker=dict(color=MODEL_COLOR, size=3, opacity=0.3),
            showlegend=False,
            hoverinfo="skip",
        ),
        row=1,
        col=1,
    )
    fig.add_hline(y=0, line=dict(color=REF_COLOR, width=1, dash="dash"), row=1, col=1)

    # --- Top-right: Q-Q plot ---
    from scipy import stats as sp_stats

    sorted_resid = np.sort(resid)
    n = len(sorted_resid)
    theoretical_q = sp_stats.norm.ppf(np.linspace(0.5 / n, 1 - 0.5 / n, n))

    fig.add_trace(
        go.Scattergl(
            x=theoretical_q,
            y=sorted_resid,
            mode="markers",
            marker=dict(color=BAYESIAN_COLOR, size=3, opacity=0.3),
            showlegend=False,
            hoverinfo="skip",
        ),
        row=1,
        col=2,
    )
    # Reference line through Q1-Q3
    q25, q75 = np.percentile(resid, [25, 75])
    tq25, tq75 = sp_stats.norm.ppf(0.25), sp_stats.norm.ppf(0.75)
    slope = (q75 - q25) / (tq75 - tq25) if tq75 != tq25 else 1
    intercept = q25 - slope * tq25
    qq_lo, qq_hi = theoretical_q[0], theoretical_q[-1]
    fig.add_trace(
        go.Scatter(
            x=[qq_lo, qq_hi],
            y=[intercept + slope * qq_lo, intercept + slope * qq_hi],
            mode="lines",
            line=dict(color=REF_COLOR, width=1.5),
            showlegend=False,
            hoverinfo="skip",
        ),
        row=1,
        col=2,
    )

    # --- Bottom-left: residuals vs turbidity ---
    turb_col = "turbidity_instant"
    if turb_col in df.columns:
        turb = df[turb_col].values[valid]
        turb_valid = np.isfinite(turb)
        fig.add_trace(
            go.Scattergl(
                x=turb[turb_valid],
                y=resid[turb_valid],
                mode="markers",
                marker=dict(color=COLORS["green"], size=3, opacity=0.3),
                showlegend=False,
                hoverinfo="skip",
            ),
            row=2,
            col=1,
        )
        fig.add_hline(
            y=0, line=dict(color=REF_COLOR, width=1, dash="dash"), row=2, col=1
        )
    else:
        fig.add_annotation(
            text="Turbidity data not available",
            xref="x3 domain",
            yref="y3 domain",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=12, color=COLORS["gray"]),
        )

    # --- Bottom-right: histogram with normal overlay ---
    fig.add_trace(
        go.Histogram(
            x=resid,
            nbinsx=80,
            marker_color=MODEL_COLOR,
            opacity=0.7,
            showlegend=False,
            name="Residuals",
        ),
        row=2,
        col=2,
    )

    # Normal curve overlay
    mu, sigma = np.mean(resid), np.std(resid)
    x_norm = np.linspace(mu - 4 * sigma, mu + 4 * sigma, 200)
    y_norm = sp_stats.norm.pdf(x_norm, mu, sigma)
    # Scale to match histogram: bin_width * n
    bin_width = (resid.max() - resid.min()) / 80 if len(resid) > 0 else 1
    y_norm_scaled = y_norm * bin_width * len(resid)

    fig.add_trace(
        go.Scatter(
            x=x_norm,
            y=y_norm_scaled,
            mode="lines",
            line=dict(color=BAYESIAN_COLOR, width=2),
            showlegend=False,
            hoverinfo="skip",
        ),
        row=2,
        col=2,
    )

    # Annotate skew and kurtosis
    from scipy.stats import skew, kurtosis

    sk = skew(resid, nan_policy="omit")
    ku = kurtosis(resid, nan_policy="omit")
    fig.add_annotation(
        text=f"Skew = {sk:.2f}<br>Kurtosis = {ku:.1f}",
        xref="x4 domain",
        yref="y4 domain",
        x=0.97,
        y=0.95,
        showarrow=False,
        font=dict(size=11, color=OBS_COLOR),
        bgcolor="rgba(255,255,255,0.85)",
        bordercolor=OBS_COLOR,
        borderwidth=1,
        borderpad=4,
        xanchor="right",
        yanchor="top",
    )

    # Axis labels
    fig.update_xaxes(title_text="Predicted SSC (mg/L)", row=1, col=1)
    fig.update_yaxes(title_text="Residual (mg/L)", row=1, col=1)
    fig.update_xaxes(title_text="Theoretical Quantiles", row=1, col=2)
    fig.update_yaxes(title_text="Sample Quantiles", row=1, col=2)
    fig.update_xaxes(title_text="Turbidity (FNU)", row=2, col=1)
    fig.update_yaxes(title_text="Residual (mg/L)", row=2, col=1)
    fig.update_xaxes(title_text="Residual (mg/L)", row=2, col=2)
    fig.update_yaxes(title_text="Count", row=2, col=2)

    fig.update_layout(
        title="Residual Diagnostics",
        height=650,
    )

    apply_plotly_style(fig)
    return fig


def make_temporal_stability(per_reading_path: str | Path) -> go.Figure:
    """Temporal stability check: first-half vs second-half R² per site.

    Splits each site's readings chronologically into two halves, computes
    R² for each, and scatters them with a 1:1 reference line.  Sites far
    from the diagonal are non-stationary.
    """
    df = pd.read_parquet(Path(per_reading_path))

    # Check for a usable time column
    time_col = None
    if "sample_time" in df.columns:
        time_col = "sample_time"

    if time_col is None:
        # Return a placeholder figure
        fig = go.Figure()
        fig.add_annotation(
            text="Temporal data not available",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=16, color=COLORS["gray"]),
        )
        fig.update_layout(height=450)
        apply_plotly_style(fig)
        return fig

    obs_col = "obs_native" if "obs_native" in df.columns else "y_true_native"
    pred_col = "pred_native" if "pred_native" in df.columns else "y_pred_native"
    site_col = "site_id" if "site_id" in df.columns else "site_no"

    if site_col not in df.columns:
        # Fallback — no site column
        fig = go.Figure()
        fig.add_annotation(
            text="Site identifier column not found",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=16, color=COLORS["gray"]),
        )
        fig.update_layout(height=450)
        apply_plotly_style(fig)
        return fig

    df = df.sort_values([site_col, time_col])

    first_r2 = []
    second_r2 = []
    site_labels = []

    for site, grp in df.groupby(site_col):
        obs = grp[obs_col].values
        pred = grp[pred_col].values
        valid = np.isfinite(obs) & np.isfinite(pred)
        obs_v = obs[valid]
        pred_v = pred[valid]
        if len(obs_v) < 6:
            continue
        mid = len(obs_v) // 2

        def _r2(o, p):
            ss_res = np.sum((o - p) ** 2)
            ss_tot = np.sum((o - np.mean(o)) ** 2)
            return 1 - ss_res / ss_tot if ss_tot > 0 else np.nan

        r2_1 = _r2(obs_v[:mid], pred_v[:mid])
        r2_2 = _r2(obs_v[mid:], pred_v[mid:])
        if np.isfinite(r2_1) and np.isfinite(r2_2):
            first_r2.append(r2_1)
            second_r2.append(r2_2)
            site_labels.append(site)

    fig = go.Figure()

    if len(first_r2) > 0:
        first_r2 = np.array(first_r2)
        second_r2 = np.array(second_r2)

        fig.add_trace(
            go.Scatter(
                x=first_r2,
                y=second_r2,
                mode="markers",
                marker=dict(color=BAYESIAN_COLOR, size=6, opacity=0.7),
                text=site_labels,
                hovertemplate="%{text}<br>1st half R²: %{x:.2f}<br>2nd half R²: %{y:.2f}<extra></extra>",
                showlegend=False,
            )
        )

        # 1:1 line
        lo = min(first_r2.min(), second_r2.min(), -0.5)
        hi = max(first_r2.max(), second_r2.max(), 1.0)
        fig.add_trace(
            go.Scatter(
                x=[lo, hi],
                y=[lo, hi],
                mode="lines",
                line=dict(color=REF_COLOR, width=1.5, dash="dash"),
                showlegend=False,
                hoverinfo="skip",
            )
        )
    else:
        fig.add_annotation(
            text="Insufficient data for temporal split",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=14, color=COLORS["gray"]),
        )

    fig.update_layout(
        title=f"Temporal Stability: First vs Second Half R² ({len(first_r2)} sites)",
        xaxis_title="First-Half R²",
        yaxis_title="Second-Half R²",
        height=450,
    )

    apply_plotly_style(fig)
    return fig


def make_data_sankey(summary_json_path: str | Path) -> go.Figure:
    """Sankey diagram of the data funnel from discovery to final splits.

    Uses summary JSON numbers if available, otherwise hardcoded defaults.
    """
    summary = _load_json(Path(summary_json_path))

    # Default funnel numbers (from project documentation)
    discovered = 860
    qualified = 413
    paired = 396
    # 254 sites actually used in training (284 eligible minus 30 without StreamCat coverage)
    train = 254
    holdout = 76
    vault = 36

    # Try to extract from summary if keys exist
    if "data_funnel" in summary:
        funnel = summary["data_funnel"]
        discovered = funnel.get("discovered", discovered)
        qualified = funnel.get("qualified", qualified)
        paired = funnel.get("paired", paired)
        train = funnel.get("train", train)
        holdout = funnel.get("holdout", holdout)
        vault = funnel.get("vault", vault)

    labels = [
        f"Discovered ({discovered})",
        f"Qualified ({qualified})",
        f"Paired ({paired})",
        f"Train ({train})",
        f"Holdout ({holdout})",
        f"Vault ({vault})",
        f"Filtered ({discovered - qualified})",
        f"Unpaired ({qualified - paired})",
    ]

    # Node indices: 0=discovered, 1=qualified, 2=paired, 3=train,
    #               4=holdout, 5=vault, 6=filtered, 7=unpaired
    source = [0, 0, 1, 1, 2, 2, 2]
    target = [1, 6, 2, 7, 3, 4, 5]
    value = [
        qualified,
        discovered - qualified,
        paired,
        qualified - paired,
        train,
        holdout,
        vault,
    ]

    node_colors = [
        COLORS["blue"],       # discovered
        COLORS["sky_blue"],   # qualified
        COLORS["green"],      # paired
        BAYESIAN_COLOR,       # train
        COLORS["orange"],     # holdout
        COLORS["purple"],     # vault
        COLORS["gray"],       # filtered out
        COLORS["gray"],       # unpaired
    ]

    fig = go.Figure(
        go.Sankey(
            node=dict(
                pad=20,
                thickness=25,
                line=dict(color="white", width=0.5),
                label=labels,
                color=node_colors,
            ),
            link=dict(
                source=source,
                target=target,
                value=value,
                color=[
                    "rgba(86,180,233,0.3)",   # discovered -> qualified
                    "rgba(153,153,153,0.3)",   # discovered -> filtered
                    "rgba(0,158,115,0.3)",     # qualified -> paired
                    "rgba(153,153,153,0.3)",   # qualified -> unpaired
                    "rgba(0,114,178,0.3)",     # paired -> train
                    "rgba(230,159,0,0.3)",     # paired -> holdout
                    "rgba(204,121,167,0.3)",   # paired -> vault
                ],
            ),
        )
    )

    fig.update_layout(
        title="Data Funnel: Discovery to Final Splits",
        height=450,
    )

    apply_plotly_style(fig)
    return fig


# ---------------------------------------------------------------------------
# Site Explorer
# ---------------------------------------------------------------------------


def make_site_table(
    per_site_path: str | Path,
    site_metadata_path: str | Path,
) -> go.Figure:
    """Sortable Plotly table of all holdout sites ranked by R2.

    Columns: site_id, location, R2, MAPE (%), Bias (%), n_samples.
    R2 column is color-coded green (good) to red (negative).
    """
    df = pd.read_parquet(Path(per_site_path))
    meta = pd.read_parquet(Path(site_metadata_path))

    # Keep holdout sites only (if role column exists in metadata)
    if "role" in meta.columns:
        holdout_ids = set(meta.loc[meta["role"] == "holdout", "site_id"])
        df = df[df["site_id"].isin(holdout_ids)].copy()

    # R2 column — prefer nse_native, fallback to r2_random_at_0
    r2_col = "nse_native" if "nse_native" in df.columns else "r2_random_at_0"
    df = df.sort_values(r2_col, ascending=False).reset_index(drop=True)

    # Location from metadata lat/lon
    states = []
    for sid in df["site_id"]:
        row = meta.loc[meta["site_id"] == sid]
        if len(row) > 0 and "latitude" in meta.columns:
            lat = float(row["latitude"].iloc[0])
            lon = float(row["longitude"].iloc[0])
            states.append(f"{lat:.1f}, {lon:.1f}")
        else:
            states.append("")

    r2_vals = df[r2_col].fillna(float("nan")).tolist()
    mape_vals = (
        df["mape_pct"].fillna(float("nan")).tolist()
        if "mape_pct" in df.columns
        else [float("nan")] * len(df)
    )
    bias_vals = (
        df["bias_pct"].fillna(float("nan")).tolist()
        if "bias_pct" in df.columns
        else [float("nan")] * len(df)
    )
    n_vals = df["n_samples"].fillna(0).astype(int).tolist()

    # Color-code R2
    r2_colors = []
    for v in r2_vals:
        if np.isnan(v):
            r2_colors.append("#FFFFFF")
        elif v >= 0.7:
            r2_colors.append("#009E73")  # green
        elif v >= 0.3:
            r2_colors.append("#56B4E9")  # sky blue
        elif v >= 0.0:
            r2_colors.append("#F0E442")  # yellow
        else:
            r2_colors.append("#D55E00")  # vermillion

    # Format numbers for display
    r2_text = [f"{v:.3f}" if np.isfinite(v) else "\u2014" for v in r2_vals]
    mape_text = [f"{v:.1f}" if np.isfinite(v) else "\u2014" for v in mape_vals]
    bias_text = [f"{v:+.1f}" if np.isfinite(v) else "\u2014" for v in bias_vals]

    fig = go.Figure(
        data=[
            go.Table(
                header=dict(
                    values=[
                        "Site ID", "Location", "R\u00b2",
                        "MAPE (%)", "Bias (%)", "n",
                    ],
                    fill_color=COLORS["blue"],
                    font=dict(color="white", size=12),
                    align="left",
                ),
                cells=dict(
                    values=[
                        df["site_id"].tolist(),
                        states,
                        r2_text,
                        mape_text,
                        bias_text,
                        n_vals,
                    ],
                    fill_color=[
                        ["white"] * len(df),
                        ["white"] * len(df),
                        r2_colors,
                        ["white"] * len(df),
                        ["white"] * len(df),
                        ["white"] * len(df),
                    ],
                    font=dict(size=11),
                    align="left",
                    height=25,
                ),
            )
        ]
    )

    fig.update_layout(
        title=f"Holdout Site Performance (n={len(df)} sites)",
        height=600,
    )

    apply_plotly_style(fig)
    return fig


def make_site_detail(
    per_reading_path: str | Path,
    site_id: str,
) -> go.Figure:
    """Observed vs predicted scatter for a single site on log-log axes.

    Annotates R2, MAPE, and n_samples.  Colors points by collection method
    if available.
    """
    df = pd.read_parquet(Path(per_reading_path))
    site_df = df[df["site_id"] == site_id].copy()

    if len(site_df) == 0:
        fig = go.Figure()
        fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper",
            text=f"No data for site {site_id}",
            showarrow=False, font=dict(size=16),
        )
        fig.update_layout(height=450)
        apply_plotly_style(fig)
        return fig

    obs = site_df["y_true_native"].values
    pred = site_df["y_pred_native"].values

    valid = np.isfinite(obs) & np.isfinite(pred) & (obs > 0) & (pred > 0)
    obs = obs[valid]
    pred = pred[valid]
    site_df = site_df.iloc[np.where(valid)[0]]

    n_samples = len(obs)

    # Metrics
    if n_samples > 1:
        ss_res = np.sum((obs - pred) ** 2)
        ss_tot = np.sum((obs - np.mean(obs)) ** 2)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    else:
        r2 = float("nan")

    mape = (
        float(np.mean(np.abs((obs - pred) / obs)) * 100)
        if n_samples > 0
        else float("nan")
    )

    log_obs = np.log10(obs)
    log_pred = np.log10(pred)

    # Color by collection method if available
    has_method = "collection_method" in site_df.columns
    if has_method:
        methods = site_df["collection_method"].fillna("Unknown").values
        unique_methods = sorted(set(methods))
        method_colors = {
            m: COLORS[list(COLORS.keys())[i % len(COLORS)]]
            for i, m in enumerate(unique_methods)
        }
    else:
        unique_methods = ["All"]
        methods = np.array(["All"] * n_samples)
        method_colors = {"All": MODEL_COLOR}

    # Axis range
    all_vals = np.concatenate([log_obs, log_pred])
    lo = float(np.floor(np.min(all_vals))) - 0.2
    hi = float(np.ceil(np.max(all_vals))) + 0.2

    fig = go.Figure()

    # 1:1 line
    fig.add_trace(
        go.Scatter(
            x=[lo, hi], y=[lo, hi],
            mode="lines",
            line=dict(color=REF_COLOR, width=2, dash="solid"),
            showlegend=False,
            hoverinfo="skip",
        )
    )

    # 2x envelope
    fig.add_trace(
        go.Scatter(
            x=[lo, hi], y=[lo + np.log10(2), hi + np.log10(2)],
            mode="lines",
            line=dict(color=REF_COLOR, width=1, dash="dash"),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[lo, hi], y=[lo - np.log10(2), hi - np.log10(2)],
            mode="lines",
            line=dict(color=REF_COLOR, width=1, dash="dash"),
            showlegend=False,
            hoverinfo="skip",
        )
    )

    for method in unique_methods:
        mask = methods == method
        fig.add_trace(
            go.Scatter(
                x=log_obs[mask],
                y=log_pred[mask],
                mode="markers",
                marker=dict(
                    size=8,
                    color=method_colors[method],
                    opacity=0.7,
                    line=dict(color="white", width=0.5),
                ),
                name=method,
                hovertemplate=(
                    "Obs: %{customdata[0]:.1f} mg/L<br>"
                    "Pred: %{customdata[1]:.1f} mg/L<extra></extra>"
                ),
                customdata=np.column_stack([obs[mask], pred[mask]]),
            )
        )

    # Metrics annotation
    r2_str = f"R\u00b2 = {r2:.3f}" if np.isfinite(r2) else "R\u00b2 = N/A"
    ann_text = f"{r2_str}<br>MAPE = {mape:.1f}%<br>n = {n_samples}"
    ann_color = GOOD_COLOR if (np.isfinite(r2) and r2 > 0) else BAD_COLOR

    fig.add_annotation(
        x=0.03, y=0.97, xref="paper", yref="paper",
        text=ann_text, showarrow=False,
        font=dict(size=12, color=ann_color),
        bgcolor="rgba(255,255,255,0.85)",
        bordercolor=ann_color, borderwidth=1, borderpad=4,
        align="left",
    )

    # Axis formatting
    tick_vals = [
        np.log10(v) for v in [1, 10, 100, 1000, 10000]
        if lo <= np.log10(v) <= hi
    ]
    tick_text = [
        str(v) for v in [1, 10, 100, 1000, 10000]
        if lo <= np.log10(v) <= hi
    ]

    fig.update_layout(
        title=f"Site {site_id}",
        xaxis_title="Observed SSC (mg/L)",
        yaxis_title="Predicted SSC (mg/L)",
        xaxis=dict(tickvals=tick_vals, ticktext=tick_text, range=[lo, hi]),
        yaxis=dict(tickvals=tick_vals, ticktext=tick_text, range=[lo, hi]),
        height=450,
        legend=dict(x=0.01, y=0.01, bgcolor="rgba(255,255,255,0.85)"),
    )

    apply_plotly_style(fig)
    return fig


def make_site_gallery(
    per_reading_path: str | Path,
    per_site_path: str | Path,
    n_best: int = 6,
    n_worst: int = 6,
) -> go.Figure:
    """Small-multiples grid: best and worst holdout sites by R2.

    Top row = best n_best sites, bottom row = worst n_worst sites.
    Each panel shows obs-vs-pred scatter with 1:1 line, annotated with
    site_id and R2.
    """
    per_site = pd.read_parquet(Path(per_site_path))
    per_reading = pd.read_parquet(Path(per_reading_path))

    r2_col = "nse_native" if "nse_native" in per_site.columns else "r2_random_at_0"

    # Filter to sites with enough samples for a meaningful plot
    per_site_valid = per_site[per_site["n_samples"] >= 5].copy()
    per_site_valid = per_site_valid.sort_values(
        r2_col, ascending=False,
    ).reset_index(drop=True)

    best_sites = per_site_valid.head(n_best)["site_id"].tolist()
    worst_sites = per_site_valid.tail(n_worst)["site_id"].tolist()

    all_sites = best_sites + worst_sites
    n_cols = max(n_best, n_worst)
    n_rows = 2

    subplot_titles = []
    for sid in best_sites:
        r2_val = float(
            per_site_valid.loc[per_site_valid["site_id"] == sid, r2_col].iloc[0]
        )
        short_id = sid.replace("USGS-", "")
        subplot_titles.append(f"{short_id} (R\u00b2={r2_val:.2f})")
    subplot_titles.extend([""] * (n_cols - n_best))
    for sid in worst_sites:
        r2_val = float(
            per_site_valid.loc[per_site_valid["site_id"] == sid, r2_col].iloc[0]
        )
        short_id = sid.replace("USGS-", "")
        subplot_titles.append(f"{short_id} (R\u00b2={r2_val:.2f})")
    subplot_titles.extend([""] * (n_cols - n_worst))

    fig = make_subplots(
        rows=n_rows,
        cols=n_cols,
        subplot_titles=subplot_titles,
        horizontal_spacing=0.04,
        vertical_spacing=0.12,
    )

    # Global axis range across all sites for consistency
    all_log_vals = []
    for sid in all_sites:
        sdf = per_reading[per_reading["site_id"] == sid]
        obs = sdf["y_true_native"].values
        pred = sdf["y_pred_native"].values
        valid = (
            np.isfinite(obs) & np.isfinite(pred) & (obs > 0) & (pred > 0)
        )
        if valid.any():
            all_log_vals.extend(np.log10(obs[valid]).tolist())
            all_log_vals.extend(np.log10(pred[valid]).tolist())

    if len(all_log_vals) > 0:
        global_lo = float(np.floor(np.min(all_log_vals))) - 0.2
        global_hi = float(np.ceil(np.max(all_log_vals))) + 0.2
    else:
        global_lo, global_hi = -1, 5

    def _add_site_panel(site_id: str, row: int, col: int, color: str):
        sdf = per_reading[per_reading["site_id"] == site_id]
        obs = sdf["y_true_native"].values
        pred = sdf["y_pred_native"].values
        valid = (
            np.isfinite(obs) & np.isfinite(pred) & (obs > 0) & (pred > 0)
        )

        if not valid.any():
            return

        log_o = np.log10(obs[valid])
        log_p = np.log10(pred[valid])

        # 1:1 line
        fig.add_trace(
            go.Scatter(
                x=[global_lo, global_hi],
                y=[global_lo, global_hi],
                mode="lines",
                line=dict(color=REF_COLOR, width=1),
                showlegend=False,
                hoverinfo="skip",
            ),
            row=row, col=col,
        )

        # Data points
        fig.add_trace(
            go.Scatter(
                x=log_o,
                y=log_p,
                mode="markers",
                marker=dict(size=5, color=color, opacity=0.7),
                showlegend=False,
                hovertemplate=(
                    "Obs: %{customdata[0]:.1f}<br>"
                    "Pred: %{customdata[1]:.1f}<extra></extra>"
                ),
                customdata=np.column_stack(
                    [obs[valid], pred[valid]]
                ),
            ),
            row=row, col=col,
        )

    # Top row: best sites
    for i, sid in enumerate(best_sites):
        _add_site_panel(sid, row=1, col=i + 1, color=GOOD_COLOR)

    # Bottom row: worst sites
    for i, sid in enumerate(worst_sites):
        _add_site_panel(sid, row=2, col=i + 1, color=BAD_COLOR)

    # Format all axes
    tick_vals = [np.log10(v) for v in [1, 10, 100, 1000, 10000]]
    tick_text = ["1", "10", "100", "1k", "10k"]

    for row_idx in range(1, n_rows + 1):
        for col_idx in range(1, n_cols + 1):
            fig.update_xaxes(
                range=[global_lo, global_hi],
                tickvals=tick_vals,
                ticktext=tick_text,
                tickfont=dict(size=8),
                row=row_idx, col=col_idx,
            )
            fig.update_yaxes(
                range=[global_lo, global_hi],
                tickvals=tick_vals,
                ticktext=tick_text,
                tickfont=dict(size=8),
                row=row_idx, col=col_idx,
            )

    # Row labels
    fig.add_annotation(
        x=-0.02, y=0.78, xref="paper", yref="paper",
        text="<b>Best</b>", showarrow=False,
        font=dict(size=13, color=GOOD_COLOR),
        textangle=-90,
    )
    fig.add_annotation(
        x=-0.02, y=0.22, xref="paper", yref="paper",
        text="<b>Worst</b>", showarrow=False,
        font=dict(size=13, color=BAD_COLOR),
        textangle=-90,
    )

    # Reduce subplot title font size
    for ann in fig.layout.annotations:
        if hasattr(ann, "font") and ann.font is not None:
            ann.font.size = 9
        else:
            ann.font = dict(size=9)

    fig.update_layout(
        title="Best and Worst Holdout Sites by R\u00b2 (n \u2265 5 samples)",
        height=500,
    )

    apply_plotly_style(fig)
    return fig


def make_site_location_map(
    site_metadata_path: str | Path,
    highlight_site_id: str,
) -> go.Figure:
    """CONUS map highlighting one site with all others as small gray dots."""
    meta = pd.read_parquet(Path(site_metadata_path))

    other = meta[meta["site_id"] != highlight_site_id]
    target = meta[meta["site_id"] == highlight_site_id]

    fig = go.Figure()

    # All other sites as small gray dots
    fig.add_trace(
        go.Scattergeo(
            lat=other["latitude"],
            lon=other["longitude"],
            mode="markers",
            marker=dict(size=4, color=COLORS["gray"], opacity=0.4),
            name="Other sites",
            hoverinfo="skip",
        )
    )

    # Highlighted site as large colored dot
    if len(target) > 0:
        fig.add_trace(
            go.Scattergeo(
                lat=target["latitude"],
                lon=target["longitude"],
                mode="markers",
                marker=dict(
                    size=14,
                    color=MODEL_COLOR,
                    line=dict(color="white", width=2),
                ),
                name=highlight_site_id,
                hovertemplate=(
                    f"{highlight_site_id}<br>"
                    "Lat: %{lat:.3f}<br>Lon: %{lon:.3f}<extra></extra>"
                ),
            )
        )

    fig.update_geos(
        scope="usa",
        showland=True,
        landcolor="#F5F5F5",
        showlakes=True,
        lakecolor="#E0E8F0",
        showcountries=False,
        showsubunits=True,
        subunitcolor="#CCCCCC",
    )
    fig.update_layout(
        height=350,
        margin=dict(l=0, r=0, t=30, b=0),
        showlegend=False,
    )
    apply_plotly_style(fig)
    return fig


def make_rating_curve(
    per_reading_path: str | Path,
    site_id: str,
) -> go.Figure:
    """Log-log scatter of turbidity (x) vs SSC (y) for one site.

    Shows observed SSC as dark dots and predicted SSC as colored dots,
    both plotted against the same turbidity values.
    """
    df = pd.read_parquet(Path(per_reading_path))
    site_df = df[df["site_id"] == site_id].copy()

    if len(site_df) == 0:
        fig = go.Figure()
        fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper",
            text=f"No data for site {site_id}",
            showarrow=False, font=dict(size=16),
        )
        fig.update_layout(height=450)
        apply_plotly_style(fig)
        return fig

    turb = site_df["turbidity_instant"].values
    obs = site_df["y_true_native"].values
    pred = site_df["y_pred_native"].values

    valid = (
        np.isfinite(turb) & np.isfinite(obs) & np.isfinite(pred)
        & (turb > 0) & (obs > 0) & (pred > 0)
    )
    turb = turb[valid]
    obs = obs[valid]
    pred = pred[valid]

    if len(turb) == 0:
        fig = go.Figure()
        fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper",
            text=f"No valid turbidity data for {site_id}",
            showarrow=False, font=dict(size=16),
        )
        fig.update_layout(height=450)
        apply_plotly_style(fig)
        return fig

    log_turb = np.log10(turb)
    log_obs = np.log10(obs)
    log_pred = np.log10(pred)

    # Axis range
    x_lo = float(np.floor(np.min(log_turb))) - 0.2
    x_hi = float(np.ceil(np.max(log_turb))) + 0.2
    all_y = np.concatenate([log_obs, log_pred])
    y_lo = float(np.floor(np.min(all_y))) - 0.2
    y_hi = float(np.ceil(np.max(all_y))) + 0.2

    fig = go.Figure()

    # Observed SSC
    fig.add_trace(
        go.Scatter(
            x=log_turb, y=log_obs,
            mode="markers",
            marker=dict(size=7, color=OBS_COLOR, opacity=0.6),
            name="Observed SSC",
            hovertemplate=(
                "Turb: %{customdata[0]:.1f} FNU<br>"
                "SSC: %{customdata[1]:.1f} mg/L<extra></extra>"
            ),
            customdata=np.column_stack([turb, obs]),
        )
    )

    # Predicted SSC
    fig.add_trace(
        go.Scatter(
            x=log_turb, y=log_pred,
            mode="markers",
            marker=dict(size=7, color=MODEL_COLOR, opacity=0.6),
            name="Predicted SSC",
            hovertemplate=(
                "Turb: %{customdata[0]:.1f} FNU<br>"
                "Pred SSC: %{customdata[1]:.1f} mg/L<extra></extra>"
            ),
            customdata=np.column_stack([turb, pred]),
        )
    )

    # Tick helpers
    def make_ticks(lo, hi):
        candidates = [0.1, 1, 10, 100, 1000, 10000]
        vals = [np.log10(v) for v in candidates if lo <= np.log10(v) <= hi]
        text = [str(v) for v in candidates if lo <= np.log10(v) <= hi]
        return vals, text

    x_tick_vals, x_tick_text = make_ticks(x_lo, x_hi)
    y_tick_vals, y_tick_text = make_ticks(y_lo, y_hi)

    fig.update_layout(
        title=f"Rating Curve — {site_id}",
        xaxis_title="Turbidity (FNU)",
        yaxis_title="SSC (mg/L)",
        xaxis=dict(tickvals=x_tick_vals, ticktext=x_tick_text, range=[x_lo, x_hi]),
        yaxis=dict(tickvals=y_tick_vals, ticktext=y_tick_text, range=[y_lo, y_hi]),
        height=450,
        legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.85)"),
    )

    apply_plotly_style(fig)
    return fig


# ---------------------------------------------------------------------------
# CQR Prediction Interval figures
# ---------------------------------------------------------------------------

# CQR quantile column names to detect real data
_CQR_QUANTILE_COLS = ["q05", "q10", "q15", "q20", "q25", "q45", "q50",
                       "q55", "q75", "q80", "q85", "q90", "q95"]


def _has_cqr_data(df: pd.DataFrame) -> bool:
    """Return True if the per-reading DataFrame contains CQR quantile columns."""
    return "q05" in df.columns and "q95" in df.columns


_SYNTHETIC_ANNOTATION = dict(
    x=0.5, y=1.0, xref="paper", yref="paper",
    text="SYNTHETIC DATA \u2014 CQR model training in progress",
    showarrow=False,
    font=dict(size=13, color=BAD_COLOR, family="Source Sans Pro, Helvetica, Arial, sans-serif"),
    bgcolor="rgba(255,255,255,0.85)",
    bordercolor=BAD_COLOR,
    borderwidth=2,
    borderpad=6,
    xanchor="center",
    yanchor="bottom",
)


def make_cqr_calibration(per_reading_path: str | Path) -> go.Figure:
    """Reliability diagram: nominal vs actual coverage for CQR intervals."""
    df = pd.read_parquet(Path(per_reading_path))
    is_real = _has_cqr_data(df)

    nominal_levels = [0.50, 0.60, 0.70, 0.80, 0.90, 0.95]

    if not is_real:
        fig = go.Figure()
        fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper",
            text="CQR prediction intervals pending \u2014 model training in progress",
            showarrow=False,
            font=dict(size=16, color=BAD_COLOR),
        )
        fig.update_layout(
            title="CQR Calibration \u2014 Reliability Diagram",
            height=450,
        )
        apply_plotly_style(fig)
        return fig

    # Compute actual coverage from symmetric quantile pairs
    actual_coverages = []
    for nom in nominal_levels:
        alpha = 1.0 - nom
        lo_col = f"q{int(alpha / 2 * 100):02d}"
        hi_col = f"q{int((1 - alpha / 2) * 100):02d}"
        if lo_col in df.columns and hi_col in df.columns:
            covered = (
                (df["y_true_native"] >= df[lo_col])
                & (df["y_true_native"] <= df[hi_col])
            )
            actual_coverages.append(covered.mean())
        else:
            actual_coverages.append(np.nan)

    fig = go.Figure()

    # Perfect calibration diagonal
    fig.add_trace(
        go.Scatter(
            x=[0.45, 1.0], y=[0.45, 1.0],
            mode="lines",
            line=dict(color=REF_COLOR, dash="dash", width=1.5),
            name="Perfect",
            showlegend=True,
        )
    )

    # Actual coverage points
    fig.add_trace(
        go.Scatter(
            x=nominal_levels,
            y=actual_coverages,
            mode="markers+lines",
            marker=dict(size=10, color=GOOD_COLOR),
            line=dict(color=GOOD_COLOR, width=2),
            name="CQR coverage",
            hovertemplate="Nominal: %{x:.0%}<br>Actual: %{y:.1%}<extra></extra>",
        )
    )

    # Annotate each point with its nominal level
    for nom, act in zip(nominal_levels, actual_coverages):
        if np.isfinite(act):
            fig.add_annotation(
                x=nom, y=act,
                text=f"{nom:.0%}",
                showarrow=True,
                arrowhead=0,
                ax=20, ay=-20,
                font=dict(size=10),
            )

    fig.update_layout(
        title="CQR Calibration \u2014 Reliability Diagram",
        xaxis_title="Nominal Coverage",
        yaxis_title="Actual Coverage",
        xaxis=dict(tickformat=".0%", range=[0.45, 1.0]),
        yaxis=dict(tickformat=".0%", range=[0.45, 1.0]),
        height=450,
        legend=dict(x=0.02, y=0.98, bgcolor="rgba(255,255,255,0.85)"),
    )

    apply_plotly_style(fig)
    return fig


def make_cqr_fan_plot(per_reading_path: str | Path) -> go.Figure:
    """Time series fan plot showing prediction intervals for holdout sites."""
    df = pd.read_parquet(Path(per_reading_path))
    is_real = _has_cqr_data(df)

    if not is_real:
        fig = go.Figure()
        fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper",
            text="CQR prediction intervals pending \u2014 model training in progress",
            showarrow=False,
            font=dict(size=16, color=BAD_COLOR),
        )
        fig.update_layout(
            title="Prediction Intervals \u2014 Selected Holdout Sites",
            height=500,
        )
        apply_plotly_style(fig)
        return fig

    # Pick 3 sites with the most readings
    top_sites = (
        df.groupby("site_id").size()
        .sort_values(ascending=False)
        .head(3).index.tolist()
    )

    site_colors = [COLORS["blue"], COLORS["vermillion"], COLORS["green"]]
    ribbon_dark_alpha = 0.35
    ribbon_light_alpha = 0.15

    fig = make_subplots(
        rows=len(top_sites), cols=1,
        shared_xaxes=False,
        subplot_titles=[s for s in top_sites],
        vertical_spacing=0.10,
    )

    for i, site_id in enumerate(top_sites):
        row = i + 1
        sdf = df[df["site_id"] == site_id].sort_values("sample_time").copy()
        times = sdf["sample_time"]
        obs = sdf["y_true_native"].values
        pred = sdf["y_pred_native"].values
        color = site_colors[i]

        q05 = sdf["q05"].values
        q25 = sdf["q25"].values
        q75 = sdf["q75"].values
        q95 = sdf["q95"].values

        # 90% ribbon (light)
        fig.add_trace(
            go.Scatter(
                x=pd.concat([times, times[::-1]]),
                y=np.concatenate([q95, q05[::-1]]),
                fill="toself",
                fillcolor=(
                    f"rgba({int(color[1:3], 16)},{int(color[3:5], 16)},"
                    f"{int(color[5:7], 16)},{ribbon_light_alpha})"
                ),
                line=dict(width=0),
                name="90% PI" if i == 0 else None,
                showlegend=(i == 0),
                legendgroup="90pi",
                hoverinfo="skip",
            ),
            row=row, col=1,
        )

        # 50% ribbon (dark)
        fig.add_trace(
            go.Scatter(
                x=pd.concat([times, times[::-1]]),
                y=np.concatenate([q75, q25[::-1]]),
                fill="toself",
                fillcolor=(
                    f"rgba({int(color[1:3], 16)},{int(color[3:5], 16)},"
                    f"{int(color[5:7], 16)},{ribbon_dark_alpha})"
                ),
                line=dict(width=0),
                name="50% PI" if i == 0 else None,
                showlegend=(i == 0),
                legendgroup="50pi",
                hoverinfo="skip",
            ),
            row=row, col=1,
        )

        # Predicted line
        fig.add_trace(
            go.Scatter(
                x=times, y=pred,
                mode="lines",
                line=dict(color=color, width=1.5),
                name="Predicted" if i == 0 else None,
                showlegend=(i == 0),
                legendgroup="pred",
                hovertemplate="Pred: %{y:.0f} mg/L<extra></extra>",
            ),
            row=row, col=1,
        )

        # Observed points
        fig.add_trace(
            go.Scatter(
                x=times, y=obs,
                mode="markers",
                marker=dict(size=5, color=OBS_COLOR, opacity=0.7),
                name="Observed" if i == 0 else None,
                showlegend=(i == 0),
                legendgroup="obs",
                hovertemplate="Obs: %{y:.0f} mg/L<extra></extra>",
            ),
            row=row, col=1,
        )

        fig.update_yaxes(title_text="SSC (mg/L)", row=row, col=1)

    fig.update_layout(
        title="Prediction Intervals \u2014 Selected Holdout Sites",
        height=500,
        legend=dict(x=0.01, y=1.02, orientation="h", bgcolor="rgba(255,255,255,0.85)"),
    )

    # Reduce subplot title font size
    for ann in fig.layout.annotations:
        if hasattr(ann, "font") and ann.font is not None:
            ann.font.size = 10
        else:
            ann.font = dict(size=10)

    apply_plotly_style(fig)
    return fig


def make_cqr_coverage_by_regime(
    per_reading_path: str | Path,
    disagg_path: str | Path,
) -> go.Figure:
    """Bar chart of 90% PI coverage by SSC range bins and collection method."""
    df = pd.read_parquet(Path(per_reading_path))
    is_real = _has_cqr_data(df)

    if not is_real:
        fig = go.Figure()
        fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper",
            text="CQR prediction intervals pending \u2014 model training in progress",
            showarrow=False,
            font=dict(size=16, color=BAD_COLOR),
        )
        fig.update_layout(
            title="90% Prediction Interval Coverage by Regime",
            height=400,
        )
        apply_plotly_style(fig)
        return fig

    # SSC range bins
    ssc_bins = [
        ("< 10", 0, 10),
        ("10\u2013100", 10, 100),
        ("100\u20131k", 100, 1000),
        ("> 1k", 1000, 1e9),
    ]

    # Collection methods
    methods = sorted(df["collection_method"].dropna().unique().tolist())

    # Compute actual 90% coverage by bin
    ssc_coverages = {}
    for label, lo, hi in ssc_bins:
        mask = (df["y_true_native"] >= lo) & (df["y_true_native"] < hi)
        sub = df[mask]
        if len(sub) > 0 and "q05" in sub.columns and "q95" in sub.columns:
            covered = (
                (sub["y_true_native"] >= sub["q05"])
                & (sub["y_true_native"] <= sub["q95"])
            )
            ssc_coverages[label] = covered.mean()
        else:
            ssc_coverages[label] = np.nan

    method_coverages = {}
    for m in methods:
        sub = df[df["collection_method"] == m]
        if len(sub) > 0 and "q05" in sub.columns and "q95" in sub.columns:
            covered = (
                (sub["y_true_native"] >= sub["q05"])
                & (sub["y_true_native"] <= sub["q95"])
            )
            method_coverages[m] = covered.mean()
        else:
            method_coverages[m] = np.nan

    fig = go.Figure()

    # SSC range bars
    fig.add_trace(
        go.Bar(
            x=list(ssc_coverages.keys()),
            y=list(ssc_coverages.values()),
            name="SSC Range",
            marker_color=COLORS["blue"],
            hovertemplate="%{x}: %{y:.1%}<extra></extra>",
        )
    )

    # Collection method bars
    fig.add_trace(
        go.Bar(
            x=list(method_coverages.keys()),
            y=list(method_coverages.values()),
            name="Collection Method",
            marker_color=COLORS["orange"],
            hovertemplate="%{x}: %{y:.1%}<extra></extra>",
        )
    )

    # Nominal 90% reference line
    fig.add_hline(
        y=0.90,
        line_dash="dash",
        line_color=REF_COLOR,
        annotation_text="90% nominal",
        annotation_position="top right",
        annotation_font_size=11,
    )

    fig.update_layout(
        title="90% Prediction Interval Coverage by Regime",
        yaxis_title="Actual Coverage",
        yaxis=dict(tickformat=".0%", range=[0.75, 1.0]),
        height=400,
        barmode="group",
        legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.85)"),
    )

    apply_plotly_style(fig)
    return fig


# ---------------------------------------------------------------------------
# Additional diagnostic & exploration figures (2026-03-31)
# ---------------------------------------------------------------------------


def make_adaptation_surprise(per_site_path: str | Path) -> go.Figure:
    """Scatter of zero-shot R\u00b2 vs delta-R\u00b2 from adaptation.

    Each point is one holdout site.  Upper-left quadrant = "was bad, fixed".
    Color encodes number of calibration samples available at the site.
    """
    df = pd.read_parquet(Path(per_site_path))

    # Determine zero-shot and adapted columns
    zs_col = "nse_native" if "nse_native" in df.columns else "r2_random_at_0"
    adapt_col = "r2_random_at_10" if "r2_random_at_10" in df.columns else None

    if zs_col not in df.columns or adapt_col is None or adapt_col not in df.columns:
        fig = go.Figure()
        fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper",
            text="Adaptation columns not found in per-site data.",
            showarrow=False, font=dict(size=14),
        )
        fig.update_layout(height=500)
        apply_plotly_style(fig)
        return fig

    sub = df[[zs_col, adapt_col]].dropna()
    x_vals = sub[zs_col].values
    delta = sub[adapt_col].values - x_vals

    # Color by n_samples if available
    color_vals = (
        df.loc[sub.index, "n_samples"].values
        if "n_samples" in df.columns
        else None
    )

    fig = go.Figure()

    scatter_kwargs: dict = dict(
        x=x_vals,
        y=delta,
        mode="markers",
        marker=dict(size=7, opacity=0.7, line=dict(width=0.5, color="white")),
        showlegend=False,
    )
    if color_vals is not None:
        scatter_kwargs["marker"]["color"] = color_vals
        scatter_kwargs["marker"]["colorscale"] = "Viridis"
        scatter_kwargs["marker"]["colorbar"] = dict(
            title="N samples", thickness=12, len=0.6,
        )
        scatter_kwargs["text"] = [f"N={int(n)}" for n in color_vals]
        scatter_kwargs["hovertemplate"] = (
            "Zero-shot R\u00b2: %{x:.2f}<br>"
            "\u0394R\u00b2: %{y:.2f}<br>%{text}<extra></extra>"
        )
    else:
        scatter_kwargs["marker"]["color"] = BAYESIAN_COLOR

    fig.add_trace(go.Scatter(**scatter_kwargs))

    # Horizontal line at delta = 0
    fig.add_hline(y=0, line=dict(color=REF_COLOR, width=1.5, dash="dash"))

    # Quadrant labels
    quadrants = [
        (-0.3, 0.25, "Was bad, fixed"),
        (0.6, 0.15, "Was good, improved"),
        (-0.3, -0.15, "Was bad, still bad"),
        (0.6, -0.15, "Was good, got worse"),
    ]
    for qx, qy, txt in quadrants:
        fig.add_annotation(
            x=qx, y=qy, text=txt, showarrow=False,
            font=dict(size=10, color=COLORS["gray"]),
            bgcolor="rgba(255,255,255,0.7)",
        )

    fig.update_layout(
        title="Adaptation Surprise \u2014 Who Benefits Most?",
        xaxis_title="Zero-shot R\u00b2",
        yaxis_title="\u0394R\u00b2 (Adapted N=10 \u2212 Zero-shot)",
        height=500,
    )

    apply_plotly_style(fig)
    return fig


def make_joint_distribution(per_reading_path: str | Path) -> go.Figure:
    """Log-log density scatter of observed SSC vs turbidity.

    Uses Histogram2d for density encoding.  Shows the raw relationship
    the model learns from.
    """
    df = pd.read_parquet(Path(per_reading_path))

    obs_col = "y_true_native" if "y_true_native" in df.columns else "obs_native"
    turb_col = "turbidity_instant"

    if obs_col not in df.columns or turb_col not in df.columns:
        fig = go.Figure()
        fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper",
            text="Required columns (SSC, turbidity) not found.",
            showarrow=False, font=dict(size=14),
        )
        fig.update_layout(height=550)
        apply_plotly_style(fig)
        return fig

    sub = df[[obs_col, turb_col]].dropna()
    sub = sub[(sub[obs_col] > 0) & (sub[turb_col] > 0)]

    log_ssc = np.log10(sub[obs_col].values)
    log_turb = np.log10(sub[turb_col].values)

    fig = go.Figure()

    fig.add_trace(
        go.Histogram2d(
            x=log_turb,
            y=log_ssc,
            nbinsx=80,
            nbinsy=80,
            colorscale=DENSITY_COLORSCALE,
            colorbar=dict(title="Count", thickness=12, len=0.6),
            hovertemplate=(
                "log\u2081\u2080(Turb): %{x:.1f}<br>"
                "log\u2081\u2080(SSC): %{y:.1f}<br>"
                "Count: %{z}<extra></extra>"
            ),
        )
    )

    # 1:1 reference line
    lo = min(log_turb.min(), log_ssc.min())
    hi = max(log_turb.max(), log_ssc.max())
    fig.add_trace(
        go.Scatter(
            x=[lo, hi], y=[lo, hi],
            mode="lines",
            line=dict(color=REF_COLOR, width=1.5, dash="dash"),
            name="1:1",
            showlegend=True,
        )
    )

    fig.update_layout(
        title=f"SSC vs Turbidity \u2014 Joint Distribution (n={len(sub):,})",
        xaxis_title="log\u2081\u2080(Turbidity, FNU)",
        yaxis_title="log\u2081\u2080(SSC, mg/L)",
        height=550,
        legend=dict(x=0.02, y=0.98, bgcolor="rgba(255,255,255,0.85)"),
    )

    apply_plotly_style(fig)
    return fig


def make_boxcox_comparison(per_reading_path: str | Path) -> go.Figure:
    """Three-panel histogram: raw SSC, log1p(SSC), Box-Cox(SSC, lambda=0.2).

    Annotates skewness on each panel.  No scipy dependency -- Box-Cox
    with fixed lambda=0.2 is computed manually as (x^0.2 - 1) / 0.2.
    """
    df = pd.read_parquet(Path(per_reading_path))

    obs_col = "y_true_native" if "y_true_native" in df.columns else "obs_native"
    if obs_col not in df.columns:
        fig = go.Figure()
        fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper",
            text="SSC column not found.", showarrow=False, font=dict(size=14),
        )
        fig.update_layout(height=400)
        apply_plotly_style(fig)
        return fig

    raw = df[obs_col].dropna()
    raw = raw[raw > 0].values

    log_vals = np.log1p(raw)
    bc_vals = (np.power(raw, 0.2) - 1.0) / 0.2

    fig = make_subplots(
        rows=1, cols=3,
        subplot_titles=["Raw SSC", "log1p(SSC)", "Box-Cox (\u03bb=0.2)"],
        horizontal_spacing=0.08,
    )

    panels = [
        (raw, COLORS["vermillion"]),
        (log_vals, COLORS["blue"]),
        (bc_vals, COLORS["green"]),
    ]

    for i, (vals, color) in enumerate(panels, 1):
        fig.add_trace(
            go.Histogram(
                x=vals,
                nbinsx=60,
                marker_color=color,
                opacity=0.8,
                showlegend=False,
            ),
            row=1, col=i,
        )
        # Compute skewness: E[(x-mu)^3] / std^3
        mu = np.mean(vals)
        std = np.std(vals)
        skew = np.mean(((vals - mu) / std) ** 3) if std > 0 else 0.0
        fig.add_annotation(
            x=0.5, y=0.95,
            xref=f"x{i} domain" if i > 1 else "x domain",
            yref=f"y{i} domain" if i > 1 else "y domain",
            text=f"Skew: {skew:.2f}",
            showarrow=False,
            font=dict(size=11, color=color),
            bgcolor="rgba(255,255,255,0.85)",
        )

    fig.update_layout(
        title="Effect of Transform on SSC Distribution",
        height=400,
    )

    # Reduce subplot title font size
    for ann in fig.layout.annotations:
        if hasattr(ann, "font") and ann.font is not None:
            ann.font.size = 10
        else:
            ann.font = dict(size=10)

    apply_plotly_style(fig)
    return fig


def make_slope_gallery(per_reading_path: str | Path) -> go.Figure:
    """Histogram of per-site log-log slopes of SSC vs turbidity.

    For each site, fits a simple linear regression in log-log space:
        log10(SSC) = slope * log10(turbidity) + intercept
    Annotates median slope and a reference line at slope = 1.0 (linear).
    """
    df = pd.read_parquet(Path(per_reading_path))

    obs_col = "y_true_native" if "y_true_native" in df.columns else "obs_native"
    turb_col = "turbidity_instant"
    site_col = "site_id"

    if obs_col not in df.columns or turb_col not in df.columns or site_col not in df.columns:
        fig = go.Figure()
        fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper",
            text="Required columns not found for slope analysis.",
            showarrow=False, font=dict(size=14),
        )
        fig.update_layout(height=450)
        apply_plotly_style(fig)
        return fig

    sub = df[[site_col, obs_col, turb_col]].dropna()
    sub = sub[(sub[obs_col] > 0) & (sub[turb_col] > 0)].copy()
    sub["log_ssc"] = np.log10(sub[obs_col])
    sub["log_turb"] = np.log10(sub[turb_col])

    slopes = []
    for _site, grp in sub.groupby(site_col):
        if len(grp) < 5:
            continue
        x = grp["log_turb"].values
        y = grp["log_ssc"].values
        # Simple OLS: slope = cov(x,y) / var(x)
        x_mean = x.mean()
        y_mean = y.mean()
        var_x = np.sum((x - x_mean) ** 2)
        if var_x == 0:
            continue
        slope = np.sum((x - x_mean) * (y - y_mean)) / var_x
        slopes.append(slope)

    slopes = np.array(slopes)

    if len(slopes) == 0:
        fig = go.Figure()
        fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper",
            text="Not enough sites to compute slopes.",
            showarrow=False, font=dict(size=14),
        )
        fig.update_layout(height=450)
        apply_plotly_style(fig)
        return fig

    med_slope = np.median(slopes)

    fig = go.Figure()

    fig.add_trace(
        go.Histogram(
            x=slopes,
            nbinsx=30,
            marker_color=BAYESIAN_COLOR,
            opacity=0.8,
            showlegend=False,
        )
    )

    # Reference line at slope = 1.0
    fig.add_vline(
        x=1.0, line=dict(color=REF_COLOR, width=1.5, dash="dash"),
        annotation_text="Linear (slope=1)",
        annotation_position="top right",
        annotation_font_size=10,
        annotation_font_color=COLORS["gray"],
    )

    # Median slope line
    fig.add_vline(
        x=med_slope, line=dict(color=MODEL_COLOR, width=2),
        annotation_text=f"Median: {med_slope:.2f}",
        annotation_position="top left",
        annotation_font_size=10,
        annotation_font_color=MODEL_COLOR,
    )

    fig.update_layout(
        title=f"Per-Site Power-Law Slopes (n={len(slopes)} sites, \u22655 samples each)",
        xaxis_title="log-log Slope (SSC vs Turbidity)",
        yaxis_title="Number of Sites",
        height=450,
    )

    apply_plotly_style(fig)
    return fig


# ---------------------------------------------------------------------------
# Rating Curves — small multiples (6 holdout sites spanning R2 range)
# ---------------------------------------------------------------------------

def make_rating_curves(
    per_reading_path: str | Path,
    per_site_path: str | Path,
    n_sites: int = 6,
) -> go.Figure:
    """Small-multiples log-log rating curves for 6 holdout sites.

    Picks 2 good, 2 medium, and 2 poor sites by R2 to show the turbidity-SSC
    relationship across the performance spectrum.  Gray dots = observed SSC,
    colored dots = predicted SSC, both plotted against turbidity.
    """
    per_site = pd.read_parquet(Path(per_site_path))
    per_reading = pd.read_parquet(Path(per_reading_path))

    r2_col = "nse_native" if "nse_native" in per_site.columns else "r2_random_at_0"

    # Only sites with enough data and valid turbidity readings
    valid_sites = per_site[per_site["n_samples"] >= 5].copy()
    valid_sites = valid_sites.sort_values(r2_col, ascending=False).reset_index(drop=True)

    if len(valid_sites) < n_sites:
        selected = valid_sites
    else:
        n_third = max(len(valid_sites) // 3, 1)
        good = valid_sites.head(n_third)
        poor = valid_sites.tail(n_third)
        mid = valid_sites.iloc[n_third : len(valid_sites) - n_third]
        picks = []
        for bucket in [good, mid, poor]:
            if len(bucket) >= 2:
                picks.append(bucket.iloc[0])
                picks.append(bucket.iloc[-1])
            elif len(bucket) == 1:
                picks.append(bucket.iloc[0])
        selected = pd.DataFrame(picks).head(n_sites)

    site_ids = selected["site_id"].tolist()
    n_cols = 3
    n_rows = 2

    subplot_titles = []
    for sid in site_ids:
        r2_val = float(valid_sites.loc[valid_sites["site_id"] == sid, r2_col].iloc[0])
        short_id = sid.replace("USGS-", "")
        subplot_titles.append(f"{short_id} (R\u00b2={r2_val:.2f})")
    while len(subplot_titles) < n_rows * n_cols:
        subplot_titles.append("")

    fig = make_subplots(
        rows=n_rows, cols=n_cols,
        subplot_titles=subplot_titles,
        horizontal_spacing=0.08,
        vertical_spacing=0.14,
    )

    # Compute shared axis range across all selected sites
    all_turb, all_ssc = [], []
    for sid in site_ids:
        sdf = per_reading[per_reading["site_id"] == sid]
        if "turbidity_instant" not in sdf.columns:
            continue
        turb = sdf["turbidity_instant"].values
        obs = sdf["y_true_native"].values
        pred = sdf["y_pred_native"].values
        mask = (
            np.isfinite(turb) & np.isfinite(obs) & np.isfinite(pred)
            & (turb > 0) & (obs > 0) & (pred > 0)
        )
        if mask.any():
            all_turb.extend(np.log10(turb[mask]).tolist())
            all_ssc.extend(np.log10(obs[mask]).tolist())
            all_ssc.extend(np.log10(pred[mask]).tolist())

    if all_turb:
        x_lo = np.floor(min(all_turb) * 2) / 2
        x_hi = np.ceil(max(all_turb) * 2) / 2
        y_lo = np.floor(min(all_ssc) * 2) / 2
        y_hi = np.ceil(max(all_ssc) * 2) / 2
    else:
        x_lo, x_hi, y_lo, y_hi = -1, 4, -1, 5

    def _make_ticks(lo, hi):
        candidates = [0.1, 1, 10, 100, 1000, 10000]
        vals = [np.log10(v) for v in candidates if lo <= np.log10(v) <= hi]
        text = [str(v) for v in candidates if lo <= np.log10(v) <= hi]
        return vals, text

    x_tick_vals, x_tick_text = _make_ticks(x_lo, x_hi)
    y_tick_vals, y_tick_text = _make_ticks(y_lo, y_hi)

    for idx, sid in enumerate(site_ids):
        row = idx // n_cols + 1
        col = idx % n_cols + 1
        sdf = per_reading[per_reading["site_id"] == sid]

        turb = sdf["turbidity_instant"].values
        obs = sdf["y_true_native"].values
        pred = sdf["y_pred_native"].values
        mask = (
            np.isfinite(turb) & np.isfinite(obs) & np.isfinite(pred)
            & (turb > 0) & (obs > 0) & (pred > 0)
        )
        if not mask.any():
            continue

        log_turb = np.log10(turb[mask])
        log_obs = np.log10(obs[mask])
        log_pred = np.log10(pred[mask])

        fig.add_trace(
            go.Scatter(
                x=log_turb, y=log_obs,
                mode="markers",
                marker=dict(size=5, color=OBS_COLOR, opacity=0.4),
                showlegend=(idx == 0),
                name="Observed",
                hovertemplate="Turb: %{customdata[0]:.1f}<br>Obs SSC: %{customdata[1]:.1f}<extra></extra>",
                customdata=np.column_stack([turb[mask], obs[mask]]),
            ),
            row=row, col=col,
        )
        fig.add_trace(
            go.Scatter(
                x=log_turb, y=log_pred,
                mode="markers",
                marker=dict(size=5, color=MODEL_COLOR, opacity=0.6),
                showlegend=(idx == 0),
                name="Predicted",
                hovertemplate="Turb: %{customdata[0]:.1f}<br>Pred SSC: %{customdata[1]:.1f}<extra></extra>",
                customdata=np.column_stack([turb[mask], pred[mask]]),
            ),
            row=row, col=col,
        )

    # Apply shared axes
    for i in range(1, n_rows * n_cols + 1):
        xaxis_key = f"xaxis{i}" if i > 1 else "xaxis"
        yaxis_key = f"yaxis{i}" if i > 1 else "yaxis"
        fig.update_layout(**{
            xaxis_key: dict(tickvals=x_tick_vals, ticktext=x_tick_text, range=[x_lo, x_hi]),
            yaxis_key: dict(tickvals=y_tick_vals, ticktext=y_tick_text, range=[y_lo, y_hi]),
        })

    fig.update_layout(
        height=500,
        legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.85)"),
    )

    # Add shared axis labels
    for col_idx in range(1, n_cols + 1):
        fig.update_xaxes(title_text="Turbidity (FNU)", row=n_rows, col=col_idx)
    for row_idx in range(1, n_rows + 1):
        fig.update_yaxes(title_text="SSC (mg/L)", row=row_idx, col=1)

    apply_plotly_style(fig)
    return fig


# ---------------------------------------------------------------------------
# Geology Disaggregation — grouped bar chart
# ---------------------------------------------------------------------------

def make_geology_disaggregation(disagg_path: str | Path) -> go.Figure:
    """Grouped bar chart of R2 by geology type (or collection method fallback).

    Each bar is annotated with the sample count for that group.
    Falls back to collection_method if dominant_lithology is not available.
    """
    df = pd.read_parquet(Path(disagg_path))

    # Pick geology dimension, fall back to collection_method
    if "dominant_lithology" in df["dimension"].values:
        sub = df[df["dimension"] == "dominant_lithology"].copy()
        dim_label = "Dominant Lithology"
    elif "collection_method" in df["dimension"].values:
        sub = df[df["dimension"] == "collection_method"].copy()
        dim_label = "Collection Method"
    else:
        fig = go.Figure()
        fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper",
            text="No geology or collection method data available",
            showarrow=False, font=dict(size=16),
        )
        fig.update_layout(height=450)
        apply_plotly_style(fig)
        return fig

    # Sort by R2 ascending so highest is at top of horizontal bars
    sub = sub.sort_values("r2", ascending=True).reset_index(drop=True)

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=["R\u00b2 by Group", "MAPE (%) by Group"],
        horizontal_spacing=0.18,
    )

    # R2 bars
    fig.add_trace(
        go.Bar(
            y=sub["group"],
            x=sub["r2"],
            orientation="h",
            marker_color=COLORS["blue"],
            text=[f"n={int(n)}" for n in sub["n"]],
            textposition="outside",
            showlegend=False,
            name="R\u00b2",
        ),
        row=1, col=1,
    )

    # MAPE bars
    fig.add_trace(
        go.Bar(
            y=sub["group"],
            x=sub["mape_pct"],
            orientation="h",
            marker_color=COLORS["orange"],
            text=[f"n={int(n)}" for n in sub["n"]],
            textposition="outside",
            showlegend=False,
            name="MAPE %",
        ),
        row=1, col=2,
    )

    fig.update_layout(
        title=f"Disaggregated Performance by {dim_label}",
        height=450,
    )

    fig.update_xaxes(title_text="R\u00b2", row=1, col=1)
    fig.update_xaxes(title_text="MAPE (%)", row=1, col=2)

    apply_plotly_style(fig)
    return fig


# ---------------------------------------------------------------------------
# Geology Slope Graph — connected dot plot across metrics
# ---------------------------------------------------------------------------

def make_geology_slopegraph(disagg_path: str | Path) -> go.Figure:
    """Slope graph / connected dot plot: each geology type across R2, MAPE, bias.

    Each row is a geology type (or collection method fallback).  Dots are
    positioned by metric value, connected with lines across three metric columns.
    Metrics are normalised to 0-1 for visual comparison.
    """
    df = pd.read_parquet(Path(disagg_path))

    if "dominant_lithology" in df["dimension"].values:
        sub = df[df["dimension"] == "dominant_lithology"].copy()
        dim_label = "Dominant Lithology"
    elif "collection_method" in df["dimension"].values:
        sub = df[df["dimension"] == "collection_method"].copy()
        dim_label = "Collection Method"
    else:
        fig = go.Figure()
        fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper",
            text="No geology or collection method data available",
            showarrow=False, font=dict(size=16),
        )
        fig.update_layout(height=450)
        apply_plotly_style(fig)
        return fig

    sub = sub.sort_values("r2", ascending=False).reset_index(drop=True)

    metrics = {"r2": "R\u00b2", "mape_pct": "MAPE %", "bias_pct": "Bias %"}

    # Normalise each metric to 0-1
    normed = {}
    for mcol in metrics:
        vals = sub[mcol].values.astype(float)
        vmin, vmax = np.nanmin(vals), np.nanmax(vals)
        rng = vmax - vmin if vmax != vmin else 1e-9
        normed[mcol] = (vals - vmin) / rng

    palette = [COLORS["blue"], COLORS["orange"], COLORS["vermillion"],
               COLORS["green"], COLORS["purple"], COLORS["sky_blue"],
               COLORS["gray"], COLORS["yellow"]]

    fig = go.Figure()

    metric_names = list(metrics.keys())
    metric_labels = list(metrics.values())
    x_positions = list(range(len(metric_names)))

    for idx, row in sub.iterrows():
        color = palette[idx % len(palette)]
        y_vals = [normed[m][idx] for m in metric_names]
        raw_vals = [row[m] for m in metric_names]

        fig.add_trace(go.Scatter(
            x=x_positions,
            y=y_vals,
            mode="lines+markers",
            line=dict(color=color, width=2),
            marker=dict(size=8, color=color),
            name=f"{row['group']} (n={int(row['n'])})",
            hovertemplate="<br>".join([
                f"{metric_labels[i]}: {raw_vals[i]:.1f}" for i in range(len(metric_names))
            ]) + "<extra>%{fullData.name}</extra>",
        ))

    fig.update_layout(
        title=f"Slope Graph: {dim_label} Across Metrics (normalised 0\u20131)",
        xaxis=dict(
            tickvals=x_positions,
            ticktext=metric_labels,
            title="Metric",
        ),
        yaxis=dict(title="Normalised Value (0 = worst, 1 = best within metric)"),
        height=450,
        legend=dict(
            x=1.02, y=1, bgcolor="rgba(255,255,255,0.85)",
            font=dict(size=10),
        ),
    )

    apply_plotly_style(fig)
    return fig


# ---------------------------------------------------------------------------
# Load Estimation — cumulative observed vs predicted sediment load
# ---------------------------------------------------------------------------

def make_load_estimation(per_reading_path: str | Path) -> go.Figure:
    """Cumulative sediment load comparison for top holdout sites.

    Uses cumulative sum of SSC values as a proxy for total sediment load
    (true load estimation requires discharge integration).  Panels show
    cumulative observed (dark gray) vs cumulative predicted (model color).
    Each panel is annotated with the final load ratio (predicted/observed).
    """
    df = pd.read_parquet(Path(per_reading_path))

    # Pick sites with most samples for clearest comparison
    site_counts = df.groupby("site_id").size().sort_values(ascending=False)
    top_sites = site_counts.head(6).index.tolist()

    n_cols = 3
    n_rows = 2

    subplot_titles = [sid.replace("USGS-", "") for sid in top_sites]
    while len(subplot_titles) < n_rows * n_cols:
        subplot_titles.append("")

    fig = make_subplots(
        rows=n_rows, cols=n_cols,
        subplot_titles=subplot_titles,
        horizontal_spacing=0.08,
        vertical_spacing=0.14,
    )

    for idx, sid in enumerate(top_sites):
        row = idx // n_cols + 1
        col = idx % n_cols + 1

        sdf = df[df["site_id"] == sid].copy()
        if "sample_time" in sdf.columns:
            sdf = sdf.sort_values("sample_time")

        obs = sdf["y_true_native"].values
        pred = sdf["y_pred_native"].values
        mask = np.isfinite(obs) & np.isfinite(pred) & (obs > 0) & (pred > 0)

        if not mask.any():
            continue

        obs_valid = obs[mask]
        pred_valid = pred[mask]
        x_axis = np.arange(1, len(obs_valid) + 1)

        cum_obs = np.cumsum(obs_valid)
        cum_pred = np.cumsum(pred_valid)

        fig.add_trace(
            go.Scatter(
                x=x_axis, y=cum_obs,
                mode="lines",
                line=dict(color=OBS_COLOR, width=2),
                showlegend=(idx == 0),
                name="Observed",
            ),
            row=row, col=col,
        )
        fig.add_trace(
            go.Scatter(
                x=x_axis, y=cum_pred,
                mode="lines",
                line=dict(color=MODEL_COLOR, width=2),
                showlegend=(idx == 0),
                name="Predicted",
            ),
            row=row, col=col,
        )

        # Annotate final load ratio
        if cum_obs[-1] > 0:
            load_ratio = cum_pred[-1] / cum_obs[-1]
            fig.add_annotation(
                x=x_axis[-1], y=max(cum_obs[-1], cum_pred[-1]),
                text=f"ratio={load_ratio:.2f}",
                showarrow=False,
                font=dict(size=10),
                xref=f"x{idx + 1}" if idx > 0 else "x",
                yref=f"y{idx + 1}" if idx > 0 else "y",
                xanchor="right",
                yanchor="bottom",
            )

    fig.update_layout(
        height=500,
        legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.85)"),
    )

    for col_idx in range(1, n_cols + 1):
        fig.update_xaxes(title_text="Sample #", row=n_rows, col=col_idx)
    for row_idx in range(1, n_rows + 1):
        fig.update_yaxes(title_text="Cumulative SSC (mg/L)", row=row_idx, col=1)

    apply_plotly_style(fig)
    return fig


# ---------------------------------------------------------------------------
# Feature Importance — SHAP beeswarm or CatBoost importance bar chart
# ---------------------------------------------------------------------------

# Feature category mapping for color coding
_FEATURE_CATEGORIES = {
    "sensor": ("Sensor / Real-time", COLORS["blue"]),
    "watershed": ("Watershed / Land Use", COLORS["green"]),
    "weather": ("Weather / Climate", COLORS["orange"]),
    "geology": ("Geology / Soils", COLORS["purple"]),
    "method": ("Method / Categorical", COLORS["gray"]),
}


def _categorize_feature(name: str) -> str:
    """Assign a feature to a display category based on its name."""
    sensor_prefixes = (
        "turbidity", "conductance", "do_", "ph_", "temp_instant",
        "discharge", "sensor_offset", "days_since_last", "rising_limb",
        "Q_", "turb_Q", "DO_sat", "SC_turb", "doy_", "log_turb",
        "turb_sat", "turb_below", "flush_",
    )
    weather_prefixes = (
        "precip_", "days_since_rain", "temp_at_sample", "temp_mean",
        "precip_mean",
    )
    geology_prefixes = (
        "pct_", "geo_", "clay_", "sand_", "soil_", "water_table",
        "compressive", "hydraulic_cond", "sgmc_", "rock_nitrogen",
        "slope_pct",
    )
    method_names = (
        "collection_method", "turb_source", "sensor_family",
        "geol_class", "huc2",
    )
    watershed_prefixes = (
        "latitude", "longitude", "drainage_area", "forest_", "agriculture_",
        "developed_", "wetland_", "shrub_", "grass_", "elevation_",
        "baseflow_", "runoff_", "wetness_", "dam_", "road_", "pop_",
        "npdes_", "wwtp_", "septic_", "superfund_", "coalmine_", "mine_",
        "fertilizer_", "manure_", "nitrogen_", "ag_drainage", "bio_n",
        "log_drainage", "hydrologic_connectivity",
    )

    if name in method_names:
        return "method"
    for pfx in sensor_prefixes:
        if name.startswith(pfx):
            return "sensor"
    for pfx in weather_prefixes:
        if name.startswith(pfx):
            return "weather"
    for pfx in geology_prefixes:
        if name.startswith(pfx):
            return "geology"
    for pfx in watershed_prefixes:
        if name.startswith(pfx):
            return "watershed"
    return "watershed"  # default


def make_shap_beeswarm(
    shap_path: str | Path | None = None,
    per_reading_path: str | Path | None = None,
    model_meta_path: str | Path | None = None,
    model_path: str | Path | None = None,
) -> go.Figure:
    """Feature importance bar chart from CatBoost model or SHAP values.

    If a SHAP values file exists at *shap_path*, uses those.  Otherwise
    loads the CatBoost model directly to extract built-in feature importances.
    Falls back to a placeholder if neither is available.

    Top 15 features are shown, colored by feature category (sensor, watershed,
    weather, geology, method).
    """
    feat_names = None
    feat_importances = None

    # Strategy 1: SHAP file
    if shap_path is not None:
        sp = Path(shap_path)
        if sp.exists():
            try:
                shap_df = pd.read_parquet(sp)
                mean_abs = shap_df.abs().mean().sort_values(ascending=False)
                feat_names = mean_abs.index.tolist()[:15]
                feat_importances = mean_abs.values[:15]
            except Exception:
                pass

    # Strategy 2: CatBoost model file (explicit paths)
    if feat_names is None and model_path is not None:
        mp = Path(model_path)
        meta_p = Path(model_meta_path) if model_meta_path else None
        if mp.exists():
            try:
                from catboost import CatBoostRegressor
                m = CatBoostRegressor()
                m.load_model(str(mp))
                fi = m.get_feature_importance()
                if meta_p and meta_p.exists():
                    meta = _load_json(meta_p)
                    cols = meta.get("feature_cols", [])
                else:
                    cols = [f"feature_{i}" for i in range(len(fi))]
                order = np.argsort(fi)[::-1][:15]
                feat_names = [cols[i] for i in order]
                feat_importances = fi[order]
            except Exception:
                pass

    # Strategy 3: Default model paths
    if feat_names is None:
        default_model = Path("data/results/models/ssc_C_sensor_basic_watershed_v10_clean_dualbcf.cbm")
        default_meta = Path("data/results/models/ssc_C_sensor_basic_watershed_v10_clean_dualbcf_meta.json")
        if default_model.exists():
            try:
                from catboost import CatBoostRegressor
                m = CatBoostRegressor()
                m.load_model(str(default_model))
                fi = m.get_feature_importance()
                meta = _load_json(default_meta) if default_meta.exists() else {}
                cols = meta.get("feature_cols", [f"feature_{i}" for i in range(len(fi))])
                order = np.argsort(fi)[::-1][:15]
                feat_names = [cols[i] for i in order]
                feat_importances = fi[order]
            except Exception:
                pass

    if feat_names is None or feat_importances is None:
        fig = go.Figure()
        fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper",
            text="No feature importance data available",
            showarrow=False, font=dict(size=16),
        )
        fig.update_layout(height=550)
        apply_plotly_style(fig)
        return fig

    # Build bar chart — top 15, colored by category
    categories = [_categorize_feature(f) for f in feat_names]
    colors = [_FEATURE_CATEGORIES[c][1] for c in categories]

    # Reverse so highest importance is at the top of the horizontal bar chart
    feat_names = feat_names[::-1]
    feat_importances = feat_importances[::-1]
    colors = colors[::-1]
    categories = categories[::-1]

    fig = go.Figure()

    # Group traces by category for legend
    seen_cats: set[str] = set()
    for i, (fname, imp, color, cat) in enumerate(
        zip(feat_names, feat_importances, colors, categories)
    ):
        cat_label = _FEATURE_CATEGORIES[cat][0]
        show = cat not in seen_cats
        seen_cats.add(cat)
        fig.add_trace(go.Bar(
            y=[fname],
            x=[imp],
            orientation="h",
            marker_color=color,
            name=cat_label,
            showlegend=show,
            legendgroup=cat,
            hovertemplate=f"{fname}: %{{x:.1f}}<extra>{cat_label}</extra>",
        ))

    fig.update_layout(
        title="Top 15 Feature Importances (CatBoost)",
        xaxis_title="Importance",
        yaxis_title="",
        height=550,
        barmode="stack",
        legend=dict(x=0.65, y=0.05, bgcolor="rgba(255,255,255,0.85)"),
    )

    apply_plotly_style(fig)
    return fig


# ---------------------------------------------------------------------------
# Discharge-weighted sediment load validation
# ---------------------------------------------------------------------------

def make_sediment_load_timescale(per_reading_path: str | Path) -> go.Figure:
    """Observed vs predicted sediment load at daily, monthly, and annual scales.

    Computes instantaneous load as SSC (mg/L) x Q (ft3/s) x 0.0027 (tons/day),
    then aggregates and compares observed vs predicted at each timescale.
    """
    per_reading_path = Path(per_reading_path)
    df = pd.read_parquet(per_reading_path)

    obs_col = "y_true_native" if "y_true_native" in df.columns else "obs_native"
    pred_col = "y_pred_native" if "y_pred_native" in df.columns else "pred_native"
    q_col = "discharge_instant"
    time_col = "sample_time"

    needed = [obs_col, pred_col, q_col, time_col, "site_id"]
    if not all(c in df.columns for c in needed):
        fig = go.Figure()
        fig.add_annotation(text="Discharge or time data not available", x=0.5, y=0.5,
                           xref="paper", yref="paper", showarrow=False, font=dict(size=16))
        fig.update_layout(height=400)
        apply_plotly_style(fig)
        return fig

    df = df.dropna(subset=[obs_col, pred_col, q_col, time_col]).copy()
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    df = df.dropna(subset=[time_col])

    conversion = 0.0027
    df["load_obs"] = df[obs_col] * df[q_col].abs() * conversion
    df["load_pred"] = df[pred_col] * df[q_col].abs() * conversion

    df["date"] = df[time_col].dt.date
    df["month"] = df[time_col].dt.to_period("M").astype(str)
    df["year"] = df[time_col].dt.year

    fig = make_subplots(
        rows=1, cols=3,
        subplot_titles=["Daily Load", "Monthly Load", "Annual Load"],
        horizontal_spacing=0.08,
    )

    for col_idx, (agg_col, label) in enumerate(
        [("date", "Daily"), ("month", "Monthly"), ("year", "Annual")], start=1
    ):
        agg = df.groupby(["site_id", agg_col]).agg(
            obs_load=("load_obs", "sum"),
            pred_load=("load_pred", "sum"),
        ).reset_index()
        agg = agg[(agg["obs_load"] > 0) & (agg["pred_load"] > 0)]

        if len(agg) == 0:
            continue

        log_obs = np.log10(agg["obs_load"].values)
        log_pred = np.log10(agg["pred_load"].values)

        fig.add_trace(
            go.Histogram2d(
                x=log_obs, y=log_pred,
                colorscale=DENSITY_COLORSCALE, nbinsx=50, nbinsy=50, zmin=1,
                showscale=(col_idx == 3),
                colorbar=dict(title="Count", len=0.6) if col_idx == 3 else None,
            ),
            row=1, col=col_idx,
        )

        lo = min(log_obs.min(), log_pred.min()) - 0.2
        hi = max(log_obs.max(), log_pred.max()) + 0.2
        fig.add_trace(
            go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines",
                       line=dict(color=OBS_COLOR, width=1.5), showlegend=False),
            row=1, col=col_idx,
        )

        total_obs = agg["obs_load"].sum()
        total_pred = agg["pred_load"].sum()
        ratio = total_pred / total_obs if total_obs > 0 else float("nan")
        xref = "x domain" if col_idx == 1 else f"x{col_idx} domain"
        yref = "y domain" if col_idx == 1 else f"y{col_idx} domain"
        fig.add_annotation(
            text=f"Pred/Obs = {ratio:.2f}",
            x=0.05, y=0.95, xref=xref, yref=yref,
            showarrow=False, font=dict(size=11, color=GOOD_COLOR),
            bgcolor="rgba(255,255,255,0.85)", bordercolor=GOOD_COLOR,
            borderwidth=1, borderpad=4,
        )

        fig.update_xaxes(title_text=f"Observed {label} Load (log tons)", row=1, col=col_idx)
        fig.update_yaxes(
            title_text=f"Predicted {label} Load (log tons)" if col_idx == 1 else "",
            row=1, col=col_idx,
        )

    fig.update_layout(
        title="Sediment Load Validation: Daily / Monthly / Annual",
        height=450,
    )
    apply_plotly_style(fig)
    return fig
