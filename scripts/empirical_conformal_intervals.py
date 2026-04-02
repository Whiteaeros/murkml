"""
Empirical Conformal Prediction Intervals — Mondrian approach
Bins by predicted SSC tier, computes tier-specific residual percentiles as interval bounds.

Calibration set: LOGO CV predictions from v11 model (~23k out-of-fold, truly honest)
Validation set:  v11 holdout per-reading predictions (6,026 readings)

Usage:
    .venv/Scripts/python.exe scripts/empirical_conformal_intervals.py
"""

import json
import os
import warnings

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = os.path.join(os.path.dirname(__file__), "..")
LOGO_PATH = os.path.join(
    ROOT,
    "data/results/logo_predictions_ssc_C_sensor_basic_watershed_v11_extreme_expanded.parquet",
)
HOLDOUT_PATH = os.path.join(
    ROOT,
    "data/results/evaluations/v11_extreme_eval_per_reading.parquet",
)
OUT_DIR = os.path.join(ROOT, "data/results/evaluations/empirical_conformal")
os.makedirs(OUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Bin definitions — match regime bins from calibration experiment
# ---------------------------------------------------------------------------
BIN_EDGES = [0, 30, 100, 500, 2000, np.inf]
BIN_LABELS = ["0-30", "30-100", "100-500", "500-2000", "2000+"]
UNRELIABLE_THRESHOLD = 50  # flag bins with fewer calibration samples

# ---------------------------------------------------------------------------
# Confidence levels
# ---------------------------------------------------------------------------
ALPHA_90 = 0.10  # 90% interval: [5th, 95th] percentile of residuals
ALPHA_80 = 0.20  # 80% interval: [10th, 90th] percentile of residuals


def assign_bin(pred_values: pd.Series) -> pd.Series:
    """Assign each predicted SSC value to a bin label."""
    return pd.cut(
        pred_values,
        bins=BIN_EDGES,
        labels=BIN_LABELS,
        right=False,  # [low, high)
    )


# ---------------------------------------------------------------------------
# Step 1: Load LOGO predictions as calibration set
# ---------------------------------------------------------------------------
print("=" * 70)
print("Empirical Conformal Prediction Intervals — Mondrian / SSC-tier binning")
print("=" * 70)

print(f"\n[1] Loading LOGO calibration data from:\n    {LOGO_PATH}")
logo = pd.read_parquet(LOGO_PATH)
print(f"    Rows: {len(logo):,}  |  Sites: {logo['site_id'].nunique()}")

# ---------------------------------------------------------------------------
# Step 2: Compute residuals in native (mg/L) space
# ---------------------------------------------------------------------------
print("\n[2] Computing residuals in native mg/L space")

logo["residual"] = logo["y_true_native_mgL"] - logo["y_pred_native_mgL"]
logo["abs_residual"] = logo["residual"].abs()
logo["pct_residual"] = logo["residual"] / logo["y_true_native_mgL"]

print(f"    Residual range : [{logo['residual'].min():.1f}, {logo['residual'].max():.1f}] mg/L")
print(f"    Abs resid p50  : {logo['abs_residual'].median():.1f} mg/L")
print(f"    Pct resid p50  : {logo['pct_residual'].median()*100:.1f}%")

# ---------------------------------------------------------------------------
# Step 3: Bin by PREDICTED SSC (not true — we don't have truth at inference)
# ---------------------------------------------------------------------------
print("\n[3] Binning by predicted SSC")
logo["bin"] = assign_bin(logo["y_pred_native_mgL"])

bin_counts = logo["bin"].value_counts().reindex(BIN_LABELS)
print(f"\n    {'Bin':<12} {'Count':>8}  {'Flag'}")
print(f"    {'-'*35}")
for label, count in bin_counts.items():
    flag = " *** UNRELIABLE (<50)" if count < UNRELIABLE_THRESHOLD else ""
    print(f"    {label:<12} {count:>8,}{flag}")

# ---------------------------------------------------------------------------
# Step 4: Per-bin interval bounds
# ---------------------------------------------------------------------------
print("\n[4] Computing per-bin interval bounds")


def compute_bin_bounds(group: pd.DataFrame, alpha: float) -> dict:
    """Return lower/upper offsets for a given alpha level."""
    lo_pct = alpha / 2 * 100          # e.g. 5 for alpha=0.10
    hi_pct = (1 - alpha / 2) * 100    # e.g. 95 for alpha=0.10
    lower_offset = np.percentile(group["residual"], lo_pct)
    upper_offset = np.percentile(group["residual"], hi_pct)
    # Clip: lower bound can't push prediction below 0 (handled at inference time
    # by clipping, not here — we store offsets as-is and clip during application)
    return {
        "lower_offset": float(lower_offset),
        "upper_offset": float(upper_offset),
        "n_calibration": int(len(group)),
        "median_abs_residual": float(group["abs_residual"].median()),
    }


bin_bounds_90 = {}
bin_bounds_80 = {}
grouped = logo.groupby("bin", observed=True)

for label in BIN_LABELS:
    if label not in grouped.groups:
        bin_bounds_90[label] = None
        bin_bounds_80[label] = None
        continue
    grp = grouped.get_group(label)
    bin_bounds_90[label] = compute_bin_bounds(grp, ALPHA_90)
    bin_bounds_80[label] = compute_bin_bounds(grp, ALPHA_80)

print(f"\n    90% intervals (alpha=0.10):")
print(f"    {'Bin':<12} {'N_cal':>7} {'Lower':>10} {'Upper':>10} {'Width_p50':>10}  Reliable?")
print(f"    {'-'*60}")
for label in BIN_LABELS:
    b = bin_bounds_90[label]
    if b is None:
        print(f"    {label:<12} {'NO DATA':>7}")
        continue
    width = b["upper_offset"] - b["lower_offset"]
    reliable = "yes" if b["n_calibration"] >= UNRELIABLE_THRESHOLD else "NO (< 50)"
    print(f"    {label:<12} {b['n_calibration']:>7,} {b['lower_offset']:>10.1f} {b['upper_offset']:>10.1f} {width:>10.1f}  {reliable}")

print(f"\n    80% intervals (alpha=0.20):")
print(f"    {'Bin':<12} {'N_cal':>7} {'Lower':>10} {'Upper':>10} {'Width_p50':>10}  Reliable?")
print(f"    {'-'*60}")
for label in BIN_LABELS:
    b = bin_bounds_80[label]
    if b is None:
        print(f"    {label:<12} {'NO DATA':>7}")
        continue
    width = b["upper_offset"] - b["lower_offset"]
    reliable = "yes" if b["n_calibration"] >= UNRELIABLE_THRESHOLD else "NO (< 50)"
    print(f"    {label:<12} {b['n_calibration']:>7,} {b['lower_offset']:>10.1f} {b['upper_offset']:>10.1f} {width:>10.1f}  {reliable}")


# ---------------------------------------------------------------------------
# Step 5: Validate on holdout
# ---------------------------------------------------------------------------
print(f"\n[5] Validating on holdout set")
print(f"    Loading: {HOLDOUT_PATH}")
holdout = pd.read_parquet(HOLDOUT_PATH)
print(f"    Rows: {len(holdout):,}  |  Sites: {holdout['site_id'].nunique()}")

# Bin holdout by predicted SSC
holdout["bin"] = assign_bin(holdout["y_pred_native"])
holdout["residual"] = holdout["y_true_native"] - holdout["y_pred_native"]


def apply_intervals(df: pd.DataFrame, bounds_dict: dict, alpha: float) -> pd.DataFrame:
    """Apply per-bin intervals to predictions. Returns df with added columns."""
    df = df.copy()
    df["lower_bound"] = np.nan
    df["upper_bound"] = np.nan

    for label in BIN_LABELS:
        mask = df["bin"] == label
        if mask.sum() == 0:
            continue
        b = bounds_dict.get(label)
        if b is None:
            continue
        pred = df.loc[mask, "y_pred_native"]
        lo = (pred + b["lower_offset"]).clip(lower=0.0)  # SSC >= 0
        hi = pred + b["upper_offset"]
        df.loc[mask, "lower_bound"] = lo
        df.loc[mask, "upper_bound"] = hi

    df["covered"] = (
        (df["y_true_native"] >= df["lower_bound"])
        & (df["y_true_native"] <= df["upper_bound"])
    )
    df["interval_width"] = df["upper_bound"] - df["lower_bound"]
    return df


holdout_90 = apply_intervals(holdout, bin_bounds_90, ALPHA_90)
holdout_80 = apply_intervals(holdout, bin_bounds_80, ALPHA_80)

# Helper to build coverage report
def coverage_report(df: pd.DataFrame, label: str) -> dict:
    valid = df.dropna(subset=["lower_bound", "upper_bound", "covered"])
    overall_cov = float(valid["covered"].mean())
    overall_width = float(valid["interval_width"].median())

    per_bin = {}
    for b_label in BIN_LABELS:
        grp = valid[valid["bin"] == b_label]
        if len(grp) == 0:
            per_bin[b_label] = None
            continue
        per_bin[b_label] = {
            "n_holdout": int(len(grp)),
            "coverage": float(grp["covered"].mean()),
            "median_width": float(grp["interval_width"].median()),
            "mean_width": float(grp["interval_width"].mean()),
        }

    return {
        "target_coverage": 1 - (0.10 if "90" in label else 0.20),
        "overall_coverage": overall_cov,
        "overall_median_width_mgL": overall_width,
        "per_bin": per_bin,
    }


cov_90 = coverage_report(holdout_90, "90%")
cov_80 = coverage_report(holdout_80, "80%")

def print_coverage_table(report: dict, interval_label: str):
    target = report["target_coverage"]
    print(f"\n    {interval_label}  (target coverage = {target*100:.0f}%)")
    print(f"    Overall coverage: {report['overall_coverage']*100:.1f}%  |  Median width: {report['overall_median_width_mgL']:.1f} mg/L")
    print(f"\n    {'Bin':<12} {'N_holdout':>10} {'Coverage':>10} {'Med_width':>10}")
    print(f"    {'-'*50}")
    for b_label, info in report["per_bin"].items():
        if info is None:
            print(f"    {b_label:<12} {'(no data)':>10}")
            continue
        flag = " <-- LOW" if info["coverage"] < (target - 0.05) else ""
        flag = " <-- HIGH" if info["coverage"] > (target + 0.10) else flag
        print(f"    {b_label:<12} {info['n_holdout']:>10,} {info['coverage']*100:>9.1f}% {info['median_width']:>10.1f}{flag}")


print_coverage_table(cov_90, "90% intervals")
print_coverage_table(cov_80, "80% intervals")


# ---------------------------------------------------------------------------
# Step 6: Continuous interpolated version
# ---------------------------------------------------------------------------
print("\n[6] Continuous interpolated intervals (smooth function of predicted SSC)")

N_QUANTILE_KNOTS = 20
logo_clean = logo.dropna(subset=["y_pred_native_mgL", "residual"])

# Compute knots at evenly-spaced quantiles of predicted SSC
knot_quantiles = np.linspace(0.01, 0.99, N_QUANTILE_KNOTS)
knot_preds = np.quantile(logo_clean["y_pred_native_mgL"], knot_quantiles)

lo_vals_90, hi_vals_90 = [], []
lo_vals_80, hi_vals_80 = [], []

# For each knot, use a local window of ±15 quantile points (overlapping windows)
window_half = 0.075  # ±7.5% in quantile space

for q in knot_quantiles:
    q_lo = max(0, q - window_half)
    q_hi = min(1, q + window_half)
    pred_lo = np.quantile(logo_clean["y_pred_native_mgL"], q_lo)
    pred_hi = np.quantile(logo_clean["y_pred_native_mgL"], q_hi)
    mask = (
        (logo_clean["y_pred_native_mgL"] >= pred_lo)
        & (logo_clean["y_pred_native_mgL"] <= pred_hi)
    )
    local = logo_clean.loc[mask, "residual"]
    if len(local) < 20:
        # Fall back to nearest 200 samples by predicted SSC distance
        dists = (logo_clean["y_pred_native_mgL"] - np.quantile(logo_clean["y_pred_native_mgL"], q)).abs()
        local = logo_clean.loc[dists.nsmallest(200).index, "residual"]

    lo_vals_90.append(np.percentile(local, 5))
    hi_vals_90.append(np.percentile(local, 95))
    lo_vals_80.append(np.percentile(local, 10))
    hi_vals_80.append(np.percentile(local, 90))

# Build interpolation functions (linear, clipped to training range)
def make_interp(x_knots, y_vals):
    return interp1d(x_knots, y_vals, kind="linear", bounds_error=False,
                    fill_value=(y_vals[0], y_vals[-1]))

interp_lo_90 = make_interp(knot_preds, lo_vals_90)
interp_hi_90 = make_interp(knot_preds, hi_vals_90)
interp_lo_80 = make_interp(knot_preds, lo_vals_80)
interp_hi_80 = make_interp(knot_preds, hi_vals_80)

# Validate continuous on holdout
def apply_continuous(df: pd.DataFrame, lo_fn, hi_fn) -> pd.DataFrame:
    df = df.copy()
    pred = df["y_pred_native"].values
    df["lower_bound"] = np.maximum(pred + lo_fn(pred), 0.0)
    df["upper_bound"] = pred + hi_fn(pred)
    df["covered"] = (df["y_true_native"] >= df["lower_bound"]) & (df["y_true_native"] <= df["upper_bound"])
    df["interval_width"] = df["upper_bound"] - df["lower_bound"]
    return df


cont_90 = apply_continuous(holdout, interp_lo_90, interp_hi_90)
cont_80 = apply_continuous(holdout, interp_lo_80, interp_hi_80)

print(f"\n    Continuous 90%: overall coverage = {cont_90['covered'].mean()*100:.1f}%  |  median width = {cont_90['interval_width'].median():.1f} mg/L")
print(f"    Continuous 80%: overall coverage = {cont_80['covered'].mean()*100:.1f}%  |  median width = {cont_80['interval_width'].median():.1f} mg/L")
print(f"\n    Binned    90%: overall coverage = {cov_90['overall_coverage']*100:.1f}%  |  median width = {cov_90['overall_median_width_mgL']:.1f} mg/L")
print(f"    Binned    80%: overall coverage = {cov_80['overall_coverage']*100:.1f}%  |  median width = {cov_80['overall_median_width_mgL']:.1f} mg/L")

# Per-bin coverage of continuous approach (reusing same bin column)
def cont_coverage_per_bin(df: pd.DataFrame, target: float):
    result = {}
    for label in BIN_LABELS:
        grp = df[df["bin"] == label]
        if len(grp) == 0:
            result[label] = None
            continue
        result[label] = {
            "n_holdout": int(len(grp)),
            "coverage": float(grp["covered"].mean()),
            "median_width": float(grp["interval_width"].median()),
        }
    return result

cont_cov_90_per_bin = cont_coverage_per_bin(cont_90, 0.90)
cont_cov_80_per_bin = cont_coverage_per_bin(cont_80, 0.80)

print(f"\n    Continuous per-bin (90%):")
print(f"    {'Bin':<12} {'N_holdout':>10} {'Coverage':>10} {'Med_width':>10}")
print(f"    {'-'*50}")
for b_label, info in cont_cov_90_per_bin.items():
    if info is None:
        print(f"    {b_label:<12} {'(no data)':>10}")
        continue
    print(f"    {b_label:<12} {info['n_holdout']:>10,} {info['coverage']*100:>9.1f}% {info['median_width']:>10.1f}")


# ---------------------------------------------------------------------------
# Step 7: Save results
# ---------------------------------------------------------------------------
print(f"\n[7] Saving results to {OUT_DIR}")

# Build calibration summary (bin bounds + metadata)
calibration_summary = {
    "description": "Mondrian empirical conformal intervals, calibrated on v11 LOGO CV predictions",
    "calibration_set": {
        "source": "logo_predictions_ssc_C_sensor_basic_watershed_v11_extreme_expanded.parquet",
        "n_rows": int(len(logo)),
        "n_sites": int(logo["site_id"].nunique()),
    },
    "bin_edges": [0, 30, 100, 500, 2000, "inf"],
    "bin_labels": BIN_LABELS,
    "unreliable_threshold": UNRELIABLE_THRESHOLD,
    "intervals_90pct": {
        label: {
            "lower_offset_mgL": b["lower_offset"] if b else None,
            "upper_offset_mgL": b["upper_offset"] if b else None,
            "n_calibration": b["n_calibration"] if b else 0,
            "median_abs_residual_mgL": b["median_abs_residual"] if b else None,
            "reliable": (b["n_calibration"] >= UNRELIABLE_THRESHOLD) if b else False,
        }
        for label, b in bin_bounds_90.items()
    },
    "intervals_80pct": {
        label: {
            "lower_offset_mgL": b["lower_offset"] if b else None,
            "upper_offset_mgL": b["upper_offset"] if b else None,
            "n_calibration": b["n_calibration"] if b else 0,
            "median_abs_residual_mgL": b["median_abs_residual"] if b else None,
            "reliable": (b["n_calibration"] >= UNRELIABLE_THRESHOLD) if b else False,
        }
        for label, b in bin_bounds_80.items()
    },
    "continuous_knots": {
        "n_knots": N_QUANTILE_KNOTS,
        "knot_pred_values_mgL": [float(v) for v in knot_preds],
        "lo_offsets_90": [float(v) for v in lo_vals_90],
        "hi_offsets_90": [float(v) for v in hi_vals_90],
        "lo_offsets_80": [float(v) for v in lo_vals_80],
        "hi_offsets_80": [float(v) for v in hi_vals_80],
    },
}

summary_path = os.path.join(OUT_DIR, "conformal_summary.json")
with open(summary_path, "w") as f:
    json.dump(calibration_summary, f, indent=2)
print(f"    Saved: conformal_summary.json")

# Build holdout coverage report
holdout_coverage = {
    "description": "Holdout validation of empirical conformal intervals on v11_extreme holdout set",
    "holdout_set": {
        "source": "v11_extreme_eval_per_reading.parquet",
        "n_rows": int(len(holdout)),
        "n_sites": int(holdout["site_id"].nunique()),
    },
    "binned_approach": {
        "90pct": cov_90,
        "80pct": cov_80,
    },
    "continuous_approach": {
        "90pct": {
            "overall_coverage": float(cont_90["covered"].mean()),
            "overall_median_width_mgL": float(cont_90["interval_width"].median()),
            "per_bin": cont_cov_90_per_bin,
        },
        "80pct": {
            "overall_coverage": float(cont_80["covered"].mean()),
            "overall_median_width_mgL": float(cont_80["interval_width"].median()),
            "per_bin": cont_cov_80_per_bin,
        },
    },
}

coverage_path = os.path.join(OUT_DIR, "conformal_holdout_coverage.json")
with open(coverage_path, "w") as f:
    json.dump(holdout_coverage, f, indent=2)
print(f"    Saved: conformal_holdout_coverage.json")

# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"\nCalibration set: {len(logo):,} LOGO CV predictions from {logo['site_id'].nunique()} sites")
print(f"Holdout set:     {len(holdout):,} predictions from {holdout['site_id'].nunique()} sites")
print()

print(f"{'Method':<25} {'Alpha':<8} {'Target':>8} {'Actual':>8} {'Med_Width':>12}")
print("-" * 65)
rows = [
    ("Binned (Mondrian)",   "90%", 90.0, cov_90["overall_coverage"]*100, cov_90["overall_median_width_mgL"]),
    ("Binned (Mondrian)",   "80%", 80.0, cov_80["overall_coverage"]*100, cov_80["overall_median_width_mgL"]),
    ("Continuous (smooth)", "90%", 90.0, cont_90["covered"].mean()*100,  cont_90["interval_width"].median()),
    ("Continuous (smooth)", "80%", 80.0, cont_80["covered"].mean()*100,  cont_80["interval_width"].median()),
]
for name, alpha, target, actual, width in rows:
    diff = actual - target
    flag = "  OK" if abs(diff) <= 3 else (f"  +{diff:.1f}%" if diff > 0 else f"  {diff:.1f}%")
    print(f"{name:<25} {alpha:<8} {target:>7.0f}% {actual:>7.1f}%{flag:>12}   {width:>8.1f} mg/L")

print()
print("Unreliable bins (< 50 calibration samples):")
any_unreliable = False
for label, b in bin_bounds_90.items():
    if b and b["n_calibration"] < UNRELIABLE_THRESHOLD:
        print(f"  *** Bin [{label}]: only {b['n_calibration']} calibration samples")
        any_unreliable = True
if not any_unreliable:
    print("  None — all bins have >= 50 calibration samples.")

print(f"\nOutput files:")
print(f"  {summary_path}")
print(f"  {coverage_path}")
print()
