#!/usr/bin/env python
"""OLS log-log turbidity-SSC benchmark for comparison against CatBoost.

Implements the standard USGS per-site regression (Rasmussen et al. 2009):
    log(SSC+1) = a + b * log(Turbidity+1)

This is the 2-parameter baseline that any ML model must beat to justify
its complexity. Runs on the same holdout sites with the same split logic
as evaluate_model.py for fair comparison.

Usage:
    .venv/Scripts/python.exe scripts/ols_benchmark.py \
      --output-dir data/results/evaluations/ols_benchmark
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

import warnings
import numpy as np
import pandas as pd
from numpy.polynomial.polynomial import polyfit
from scipy.stats import spearmanr as _spearmanr

warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*overflow.*")
warnings.filterwarnings("ignore", message=".*constant.*correlation.*")

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
DATA_DIR = PROJECT_ROOT / "data"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (must match evaluate_model.py)
# ---------------------------------------------------------------------------
EXPECTED_HOLDOUT_SITES = 76
EXPECTED_HOLDOUT_SAMPLES = 5829
ADAPTATION_NS = [0, 1, 2, 3, 5, 10, 20, 30, 50]
N_TRIALS = 50
SEED = 42
SPLIT_MODES = ["random", "temporal"]


# ---------------------------------------------------------------------------
# Data loading (simplified — only needs turbidity + SSC, no model features)
# ---------------------------------------------------------------------------

def load_holdout_data() -> pd.DataFrame:
    """Load holdout paired data with turbidity and SSC."""
    logger.info("Loading holdout data...")

    paired = pd.read_parquet(DATA_DIR / "processed" / "turbidity_ssc_paired.parquet")
    logger.info(f"  Paired data: {len(paired)} samples, {paired['site_id'].nunique()} sites")

    split_path = DATA_DIR / "train_holdout_vault_split.parquet"
    if not split_path.exists():
        split_path = DATA_DIR / "train_holdout_split.parquet"
    split = pd.read_parquet(split_path)
    holdout_ids = set(split[split["role"] == "holdout"]["site_id"])

    holdout = paired[paired["site_id"].isin(holdout_ids)].copy()
    n_sites = holdout["site_id"].nunique()
    n_samples = len(holdout)

    assert n_sites == EXPECTED_HOLDOUT_SITES, (
        f"Expected {EXPECTED_HOLDOUT_SITES} holdout sites, got {n_sites}"
    )
    assert n_samples == EXPECTED_HOLDOUT_SAMPLES, (
        f"Expected {EXPECTED_HOLDOUT_SAMPLES} holdout samples, got {n_samples}"
    )
    logger.info(f"  VERIFIED: {n_sites} sites, {n_samples} samples")

    # Sort by site and time for temporal splits
    if "sample_time" in holdout.columns:
        holdout = holdout.sort_values(["site_id", "sample_time", "lab_value"])

    return holdout


# ---------------------------------------------------------------------------
# OLS log-log prediction
# ---------------------------------------------------------------------------

def ols_loglog_predict(
    cal_turb: np.ndarray,
    cal_ssc: np.ndarray,
    test_turb: np.ndarray,
) -> np.ndarray:
    """Fit log(SSC+1) = a + b*log(Turbidity+1) on calibration, predict on test.

    Uses +1 offset (same as log1p) to handle zero values safely.
    Applies Duan's smearing BCF for back-transformation bias correction.
    """
    log_cal_turb = np.log1p(np.clip(cal_turb, 0, None))
    log_cal_ssc = np.log1p(np.clip(cal_ssc, 0, None))

    n_cal = len(cal_turb)

    if n_cal == 0:
        return np.full(len(test_turb), np.nan)

    if n_cal == 1:
        # With 1 sample, use simple ratio (can't fit a line)
        if cal_turb[0] > 0:
            ratio = cal_ssc[0] / cal_turb[0]
            pred = np.clip(test_turb, 0, None) * ratio
        else:
            pred = np.full(len(test_turb), cal_ssc[0])
        return np.clip(pred, 0, None)

    # Check for zero-variance turbidity
    if np.std(log_cal_turb) < 1e-10:
        # All turbidity values are the same — predict mean SSC
        return np.full(len(test_turb), np.mean(cal_ssc))

    # Fit OLS: log(SSC+1) = intercept + slope * log(Turb+1)
    coeffs = polyfit(log_cal_turb, log_cal_ssc, 1)  # [intercept, slope]
    intercept, slope = float(coeffs[0]), float(coeffs[1])

    # Duan's smearing estimator for back-transformation bias
    residuals = log_cal_ssc - (intercept + slope * log_cal_turb)
    duan_bcf = float(np.mean(np.exp(residuals)))
    # Sanity-bound the BCF
    duan_bcf = np.clip(duan_bcf, 0.5, 5.0)

    # Predict
    log_test_turb = np.log1p(np.clip(test_turb, 0, None))
    log_pred_ssc = intercept + slope * log_test_turb

    # Clamp log-space predictions to prevent overflow on back-transform
    # log1p(1e7) ~ 16.1, so 20 is extremely generous
    log_pred_ssc = np.clip(log_pred_ssc, 0, 20)

    # Back-transform: expm1 to invert log1p, then apply Duan BCF
    pred_ssc = np.expm1(log_pred_ssc) * duan_bcf
    return np.clip(pred_ssc, 0, None)


# ---------------------------------------------------------------------------
# Metrics (copied from evaluate_model.py for standalone use)
# ---------------------------------------------------------------------------

def compute_site_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Compute standard metrics for a single site."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    n = len(y_true)
    nan_result = {
        "r2": np.nan, "log_nse": np.nan, "rmse": np.nan,
        "mape_pct": np.nan, "frac_within_2x": np.nan,
        "spearman_rho": np.nan, "bias_pct": np.nan, "n": n,
    }
    if n < 2:
        return nan_result

    # R² (NSE)
    ss_tot = np.sum((y_true - y_true.mean()) ** 2)
    ss_res = np.sum((y_true - y_pred) ** 2)
    r2 = float(1 - ss_res / ss_tot) if ss_tot > 1e-10 else np.nan

    # Log-NSE
    pos = (y_true > 0) & (y_pred > 0)
    if pos.sum() >= 2:
        log_true = np.log(y_true[pos])
        log_pred = np.log(y_pred[pos])
        ss_res_log = np.sum((log_true - log_pred) ** 2)
        ss_tot_log = np.sum((log_true - log_true.mean()) ** 2)
        log_nse = float(1 - ss_res_log / ss_tot_log) if ss_tot_log > 1e-10 else np.nan
    else:
        log_nse = np.nan

    # RMSE
    rmse_val = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))

    # MAPE (median, skip zeros)
    nonzero = y_true > 0
    if nonzero.sum() > 0:
        pct_err = np.abs(y_true[nonzero] - y_pred[nonzero]) / y_true[nonzero] * 100
        mape = float(np.median(pct_err))
    else:
        mape = np.nan

    # Fraction within 2x
    ratios = np.where(y_true > 0, y_pred / y_true, np.nan)
    valid_ratios = ratios[~np.isnan(ratios)]
    frac_2x = float(np.mean((valid_ratios >= 0.5) & (valid_ratios <= 2.0))) if len(valid_ratios) > 0 else np.nan

    # Spearman
    try:
        rho, _ = _spearmanr(y_true, y_pred)
        spearman = float(rho)
    except Exception:
        spearman = np.nan

    # Bias %
    mean_true = np.mean(y_true)
    bias_pct = float((np.mean(y_pred) - mean_true) / mean_true * 100) if mean_true > 0 else np.nan

    return {
        "r2": r2, "log_nse": log_nse, "rmse": rmse_val,
        "mape_pct": mape, "frac_within_2x": frac_2x,
        "spearman_rho": spearman, "bias_pct": bias_pct, "n": n,
    }


# ---------------------------------------------------------------------------
# Split logic (must match evaluate_model.py exactly)
# ---------------------------------------------------------------------------

def get_cal_test_split(
    n_site: int,
    n_cal: int,
    mode: str,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (cal_idx, test_idx) for a given split mode."""
    if n_cal >= n_site:
        return np.arange(n_site), np.array([], dtype=int)

    if mode == "random":
        cal_idx = rng.choice(n_site, size=n_cal, replace=False)
    elif mode == "temporal":
        cal_idx = np.arange(n_cal)
    else:
        raise ValueError(f"Unknown split mode: {mode!r}")

    test_idx = np.setdiff1d(np.arange(n_site), cal_idx)
    return cal_idx, test_idx


# ---------------------------------------------------------------------------
# Bootstrap CI
# ---------------------------------------------------------------------------

def bootstrap_ci(values: list[float], n_boot: int = 1000, ci: float = 0.95) -> dict:
    """Bootstrap confidence interval for the median."""
    values = np.array([v for v in values if np.isfinite(v)])
    if len(values) < 3:
        return {"median": float(np.nanmedian(values)) if len(values) > 0 else np.nan,
                "ci_lower": np.nan, "ci_upper": np.nan}
    rng = np.random.default_rng(42)
    boot_medians = np.array([
        np.median(rng.choice(values, size=len(values), replace=True))
        for _ in range(n_boot)
    ])
    alpha = (1 - ci) / 2
    return {
        "median": float(np.median(values)),
        "ci_lower": float(np.percentile(boot_medians, alpha * 100)),
        "ci_upper": float(np.percentile(boot_medians, (1 - alpha) * 100)),
    }


# ---------------------------------------------------------------------------
# Main adaptation curve
# ---------------------------------------------------------------------------

def run_ols_adaptation_curve(holdout: pd.DataFrame) -> dict:
    """Run OLS log-log benchmark across all N values, split modes, and sites.

    Returns dict keyed by split mode with curve and per-site results.
    """
    sites = sorted(holdout["site_id"].unique())
    has_dates = "sample_time" in holdout.columns

    # Pre-build per-site arrays
    site_data = {}
    for site_id in sites:
        site_df = holdout[holdout["site_id"] == site_id]
        turb = site_df["turbidity_instant"].values.astype(float)
        ssc = site_df["lab_value"].values.astype(float)
        site_data[site_id] = {"turb": turb, "ssc": ssc, "n": len(site_df)}

    results_by_mode = {}

    for mode in SPLIT_MODES:
        logger.info(f"  Split mode: {mode}")
        curve_results = {n_val: [] for n_val in ADAPTATION_NS}
        per_site_records = []

        for site_id in sites:
            sd = site_data[site_id]
            n_site = sd["n"]
            turb = sd["turb"]
            ssc = sd["ssc"]

            for n_val in ADAPTATION_NS:
                # N=0: OLS cannot predict without calibration data
                if n_val == 0:
                    continue

                if n_val >= n_site:
                    continue

                # Temporal: 1 deterministic split. Random: N_TRIALS MC trials.
                trial_range = 1 if mode == "temporal" else N_TRIALS
                trial_metrics = []

                for trial in range(trial_range):
                    site_hash = int(hashlib.md5(str(site_id).encode()).hexdigest(), 16) % (2**31)
                    rng = np.random.default_rng(SEED + site_hash + n_val * 1000 + trial)

                    cal_idx, test_idx = get_cal_test_split(n_site, n_val, mode, rng)

                    if len(test_idx) < 2:
                        continue

                    pred = ols_loglog_predict(turb[cal_idx], ssc[cal_idx], turb[test_idx])
                    true_test = ssc[test_idx]

                    m = compute_site_metrics(true_test, pred)
                    trial_metrics.append(m)

                # Aggregate trials for this site at this N
                valid = [m for m in trial_metrics if np.isfinite(m.get("r2", np.nan))]
                if valid:
                    agg = {
                        k: float(np.nanmedian([m[k] for m in valid]))
                        for k in ["r2", "log_nse", "rmse", "mape_pct",
                                   "frac_within_2x", "spearman_rho", "bias_pct"]
                    }
                    agg["n"] = int(np.median([m["n"] for m in valid]))
                    curve_results[n_val].append(agg)

                    per_site_records.append({
                        "site_id": site_id,
                        "n_cal": n_val,
                        "mode": mode,
                        **agg,
                    })

        # Aggregate curve with bootstrap CIs
        curve_agg = {}
        for n_val in ADAPTATION_NS:
            entries = curve_results.get(n_val, [])
            if not entries:
                curve_agg[str(n_val)] = {
                    "median_r2": None, "ci_lower_r2": None, "ci_upper_r2": None,
                    "median_log_nse": None, "median_rmse": None,
                    "median_mape": None, "median_within_2x": None,
                    "median_spearman": None, "median_bias": None,
                    "n_sites": 0,
                }
                continue

            r2s = [e["r2"] for e in entries]
            ci = bootstrap_ci(r2s)
            curve_agg[str(n_val)] = {
                "median_r2": ci["median"],
                "ci_lower_r2": ci["ci_lower"],
                "ci_upper_r2": ci["ci_upper"],
                "median_log_nse": float(np.nanmedian([e["log_nse"] for e in entries])),
                "median_rmse": float(np.nanmedian([e["rmse"] for e in entries])),
                "median_mape": float(np.nanmedian([e["mape_pct"] for e in entries])),
                "median_within_2x": float(np.nanmedian([e["frac_within_2x"] for e in entries])),
                "median_spearman": float(np.nanmedian([e["spearman_rho"] for e in entries])),
                "median_bias": float(np.nanmedian([e["bias_pct"] for e in entries])),
                "n_sites": len(entries),
            }

        results_by_mode[mode] = {
            "curve": curve_agg,
            "per_site": per_site_records,
        }

    return results_by_mode


# ---------------------------------------------------------------------------
# Comparison table
# ---------------------------------------------------------------------------

def load_catboost_results() -> dict | None:
    """Try to load the v10 CatBoost evaluation summary."""
    candidates = [
        DATA_DIR / "results" / "evaluations" / "v10_dualbcf_median_eval_summary.json",
        DATA_DIR / "results" / "evaluations" / "v10_clean_dualbcf_eval_summary.json",
    ]
    for path in candidates:
        if path.exists():
            logger.info(f"  Loading CatBoost results from {path.name}")
            with open(path) as f:
                return json.load(f)
    logger.warning("  No CatBoost v10 results found for comparison")
    return None


def print_comparison_table(ols_results: dict, catboost_summary: dict | None):
    """Print a side-by-side comparison table: OLS vs CatBoost at each N."""
    print("\n" + "=" * 90)
    print("OLS log-log vs CatBoost+Bayesian Adaptation -- Random Split")
    print("=" * 90)

    header = f"{'N':>4s}  {'OLS R2':>9s}  {'CB R2':>9s}  {'dR2':>8s}  {'OLS W2x':>8s}  {'CB W2x':>8s}  {'OLS MAPE':>9s}  {'CB MAPE':>9s}"
    print(header)
    print("-" * 90)

    ols_curve = ols_results.get("random", {}).get("curve", {})

    cb_curve = {}
    if catboost_summary:
        cb_adapt = catboost_summary.get("adaptation", {}).get("random", {}).get("curve", {})
        cb_curve = cb_adapt

    for n_val in ADAPTATION_NS:
        ols_entry = ols_curve.get(str(n_val), {})
        cb_entry = cb_curve.get(str(n_val), {})

        ols_r2 = ols_entry.get("median_r2")
        cb_r2 = cb_entry.get("median_r2")
        ols_w2x = ols_entry.get("median_within_2x")
        cb_w2x = cb_entry.get("median_within_2x")
        ols_mape = ols_entry.get("median_mape")
        cb_mape = cb_entry.get("median_mape")

        def fmt(v, pct=False):
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return "    —"
            if pct:
                return f"{v*100:7.1f}%"
            return f"{v:9.4f}"

        def fmt_mape(v):
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return "      —"
            return f"{v:8.1f}%"

        delta = ""
        if ols_r2 is not None and cb_r2 is not None and not np.isnan(ols_r2) and not np.isnan(cb_r2):
            d = cb_r2 - ols_r2
            delta = f"{d:+8.4f}"
        else:
            delta = "       —"

        print(f"{n_val:4d}  {fmt(ols_r2)}  {fmt(cb_r2)}  {delta}  {fmt(ols_w2x, True)}  {fmt(cb_w2x, True)}  {fmt_mape(ols_mape)}  {fmt_mape(cb_mape)}")

    print("-" * 90)
    print("dR2 > 0 means CatBoost is better. W2x = fraction within 2x. MAPE = median %.")
    print()

    # Also print temporal
    print("=" * 90)
    print("OLS log-log vs CatBoost+Bayesian Adaptation -- Temporal Split")
    print("=" * 90)
    print(header)
    print("-" * 90)

    ols_curve_t = ols_results.get("temporal", {}).get("curve", {})
    cb_curve_t = {}
    if catboost_summary:
        cb_curve_t = catboost_summary.get("adaptation", {}).get("temporal", {}).get("curve", {})

    for n_val in ADAPTATION_NS:
        ols_entry = ols_curve_t.get(str(n_val), {})
        cb_entry = cb_curve_t.get(str(n_val), {})

        ols_r2 = ols_entry.get("median_r2")
        cb_r2 = cb_entry.get("median_r2")
        ols_w2x = ols_entry.get("median_within_2x")
        cb_w2x = cb_entry.get("median_within_2x")
        ols_mape = ols_entry.get("median_mape")
        cb_mape = cb_entry.get("median_mape")

        def fmt(v, pct=False):
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return "    —"
            if pct:
                return f"{v*100:7.1f}%"
            return f"{v:9.4f}"

        def fmt_mape(v):
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return "      —"
            return f"{v:8.1f}%"

        delta = ""
        if ols_r2 is not None and cb_r2 is not None and not np.isnan(ols_r2) and not np.isnan(cb_r2):
            d = cb_r2 - ols_r2
            delta = f"{d:+8.4f}"
        else:
            delta = "       —"

        print(f"{n_val:4d}  {fmt(ols_r2)}  {fmt(cb_r2)}  {delta}  {fmt(ols_w2x, True)}  {fmt(cb_w2x, True)}  {fmt_mape(ols_mape)}  {fmt_mape(cb_mape)}")

    print("-" * 90)
    print("dR2 > 0 means CatBoost is better. W2x = fraction within 2x. MAPE = median %.")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="OLS log-log turbidity-SSC benchmark")
    parser.add_argument("--output-dir", type=str,
                        default="data/results/evaluations/ols_benchmark",
                        help="Output directory for results")
    args = parser.parse_args()

    output_dir = PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load data
    holdout = load_holdout_data()
    logger.info(f"Holdout: {len(holdout)} samples, {holdout['site_id'].nunique()} sites")

    # Quick data summary
    turb_col = "turbidity_instant"
    ssc_col = "lab_value"
    n_valid_turb = holdout[turb_col].notna().sum()
    n_valid_ssc = holdout[ssc_col].notna().sum()
    logger.info(f"  Valid turbidity: {n_valid_turb}/{len(holdout)}")
    logger.info(f"  Valid SSC: {n_valid_ssc}/{len(holdout)}")

    # 2. Run OLS benchmark
    logger.info("Running OLS log-log benchmark...")
    results = run_ols_adaptation_curve(holdout)

    # 3. Save summary JSON
    summary = {
        "method": "ols_loglog",
        "description": "Per-site log(SSC+1) = a + b*log(Turbidity+1) with Duan smearing BCF",
        "holdout_sites": EXPECTED_HOLDOUT_SITES,
        "holdout_samples": EXPECTED_HOLDOUT_SAMPLES,
        "n_trials": N_TRIALS,
        "seed": SEED,
        "split_modes": SPLIT_MODES,
        "adaptation_ns": ADAPTATION_NS,
        "adaptation": {
            mode: {"curve": results[mode]["curve"]}
            for mode in SPLIT_MODES
        },
    }

    summary_path = output_dir / "ols_benchmark_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    logger.info(f"Summary saved: {summary_path}")

    # 4. Save per-site parquet
    all_per_site = []
    for mode in SPLIT_MODES:
        all_per_site.extend(results[mode]["per_site"])

    if all_per_site:
        per_site_df = pd.DataFrame(all_per_site)
        per_site_path = output_dir / "ols_benchmark_per_site.parquet"
        per_site_df.to_parquet(per_site_path, index=False)
        logger.info(f"Per-site saved: {per_site_path} ({len(per_site_df)} rows)")

    # 5. Print comparison table
    catboost_summary = load_catboost_results()
    print_comparison_table(results, catboost_summary)

    logger.info("Done.")


if __name__ == "__main__":
    main()
