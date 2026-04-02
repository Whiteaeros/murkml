"""
Bootstrap confidence intervals for v11 holdout evaluation metrics.

Resamples SITES with replacement (sites are the independent unit — within-site
temporal autocorrelation makes sample-level bootstrap invalid). Reports 95% CIs
(2.5th / 97.5th percentiles) from 1000 iterations.

Computes:
  - Zero-shot pooled and per-site metrics
  - Adaptation curve CIs for random / temporal / seasonal splits at
    N in [0, 1, 5, 10, 20]
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
PER_SITE_PATH = ROOT / "data/results/evaluations/v11_extreme_eval_per_site.parquet"
PER_READ_PATH = ROOT / "data/results/evaluations/v11_extreme_eval_per_reading.parquet"
OUT_JSON = ROOT / "data/results/evaluations/v11_bootstrap_ci_results.json"

N_BOOT = 1000
SEED = 42
# Adaptation N values to include in curve CIs (must exist as columns in per_site)
ADAPT_NS = [0, 1, 5, 10, 20]
ADAPT_MODES = ["random", "temporal", "seasonal"]


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------
def nse(obs: np.ndarray, pred: np.ndarray) -> float:
    """Nash-Sutcliffe Efficiency."""
    if len(obs) < 2:
        return np.nan
    ss_res = np.sum((obs - pred) ** 2)
    ss_tot = np.sum((obs - np.mean(obs)) ** 2)
    if ss_tot == 0:
        return np.nan
    return 1.0 - ss_res / ss_tot


def log_nse(obs: np.ndarray, pred: np.ndarray) -> float:
    """NSE in log-space (log10). Skips non-positive values."""
    mask = (obs > 0) & (pred > 0)
    if mask.sum() < 2:
        return np.nan
    return nse(np.log10(obs[mask]), np.log10(pred[mask]))


def kge(obs: np.ndarray, pred: np.ndarray) -> float:
    """Kling-Gupta Efficiency."""
    if len(obs) < 2:
        return np.nan
    r = np.corrcoef(obs, pred)[0, 1]
    alpha = np.std(pred) / np.std(obs) if np.std(obs) > 0 else np.nan
    beta = np.mean(pred) / np.mean(obs) if np.mean(obs) > 0 else np.nan
    if np.isnan(r) or np.isnan(alpha) or np.isnan(beta):
        return np.nan
    return 1.0 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2)


def site_r2(obs: np.ndarray, pred: np.ndarray) -> float:
    """R² for a single site."""
    if len(obs) < 2:
        return np.nan
    ss_res = np.sum((obs - pred) ** 2)
    ss_tot = np.sum((obs - np.mean(obs)) ** 2)
    if ss_tot == 0:
        return np.nan
    return 1.0 - ss_res / ss_tot


def site_mape(obs: np.ndarray, pred: np.ndarray) -> float:
    """MAPE (%) for a single site."""
    mask = obs != 0
    if mask.sum() == 0:
        return np.nan
    return 100.0 * np.mean(np.abs((obs[mask] - pred[mask]) / obs[mask]))


def site_spearman(obs: np.ndarray, pred: np.ndarray) -> float:
    """Spearman rho for a single site."""
    if len(obs) < 3:
        return np.nan
    rho, _ = sp_stats.spearmanr(obs, pred)
    return rho


# ---------------------------------------------------------------------------
# Bootstrap helpers
# ---------------------------------------------------------------------------
def compute_zero_shot_metrics(sampled_sites: np.ndarray, readings_by_site: dict) -> dict:
    """Compute all zero-shot metrics for a (bootstrap) sample of site IDs."""
    # Pooled arrays: concatenate readings from all sampled sites
    obs_parts, pred_parts = [], []
    for sid in sampled_sites:
        o, p = readings_by_site[sid]
        obs_parts.append(o)
        pred_parts.append(p)
    obs_all = np.concatenate(obs_parts)
    pred_all = np.concatenate(pred_parts)

    pooled_nse = nse(obs_all, pred_all)
    pooled_log_nse = log_nse(obs_all, pred_all)
    pooled_kge = kge(obs_all, pred_all)

    # Per-site metrics (only unique sites to avoid double-counting on resampled dups)
    unique_sites = np.unique(sampled_sites)
    r2s, mapes, spearmans = [], [], []
    for sid in unique_sites:
        o, p = readings_by_site[sid]
        r2s.append(site_r2(o, p))
        mapes.append(site_mape(o, p))
        spearmans.append(site_spearman(o, p))

    r2s = np.array(r2s)
    mapes = np.array(mapes)
    spearmans = np.array(spearmans)

    r2_valid = r2s[~np.isnan(r2s)]
    mape_valid = mapes[~np.isnan(mapes)]
    spear_valid = spearmans[~np.isnan(spearmans)]

    # Sample-weighted mean R²
    weights = np.array([len(readings_by_site[sid][0]) for sid in unique_sites], dtype=float)
    r2_for_mean = np.where(np.isnan(r2s), 0.0, r2s)
    w_valid = np.where(np.isnan(r2s), 0.0, weights)
    mean_r2_weighted = (
        float(np.average(r2_for_mean, weights=w_valid)) if w_valid.sum() > 0 else np.nan
    )

    return {
        "pooled_NSE": pooled_nse,
        "pooled_logNSE": pooled_log_nse,
        "pooled_KGE": pooled_kge,
        "MedSiteR2": float(np.median(r2_valid)) if len(r2_valid) > 0 else np.nan,
        "MedSiteMAPE": float(np.median(mape_valid)) if len(mape_valid) > 0 else np.nan,
        "MedSiteSpearman": float(np.median(spear_valid)) if len(spear_valid) > 0 else np.nan,
        "MeanSiteR2_weighted": mean_r2_weighted,
        "frac_R2_gt_0": float((r2_valid > 0).mean()) if len(r2_valid) > 0 else np.nan,
        "frac_R2_gt_0.5": float((r2_valid > 0.5).mean()) if len(r2_valid) > 0 else np.nan,
    }


def compute_adapt_curve_metrics(
    sampled_sites: np.ndarray, per_site_df: pd.DataFrame, adapt_ns: list, adapt_modes: list
) -> dict:
    """
    Compute MedSiteR² for each adaptation mode × N combination.

    Uses the pre-computed per-site adaptation R² columns in per_site_df.
    Resamples from those pre-computed values — this is valid because the
    adaptation was run independently per site, so sites remain the
    independent unit.
    """
    # Build lookup: site_id -> row index in per_site_df
    unique_sites = np.unique(sampled_sites)
    sub = per_site_df[per_site_df["site_id"].isin(unique_sites)]

    results = {}
    for mode in adapt_modes:
        for n in adapt_ns:
            col = f"r2_{mode}_at_{n}"
            if col not in per_site_df.columns:
                continue
            vals = sub[col].values
            valid = vals[~np.isnan(vals)]
            key = f"{mode}_at_{n}_MedSiteR2"
            results[key] = float(np.median(valid)) if len(valid) > 0 else np.nan
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Loading v11 data...")
    per_site = pd.read_parquet(PER_SITE_PATH)
    per_read = pd.read_parquet(PER_READ_PATH)

    site_ids = per_site["site_id"].values
    n_sites = len(site_ids)
    print(f"  {n_sites} sites, {len(per_read)} readings")

    # Build dict: site_id -> (obs_array, pred_array)
    readings_by_site = {}
    for sid, grp in per_read.groupby("site_id"):
        obs = grp["y_true_native"].values.astype(np.float64)
        pred = grp["y_pred_native"].values.astype(np.float64)
        readings_by_site[sid] = (obs, pred)

    missing = [s for s in site_ids if s not in readings_by_site]
    if missing:
        print(f"  WARNING: {len(missing)} sites in per_site have no readings: {missing[:5]}")

    valid_sites = np.array([s for s in site_ids if s in readings_by_site])
    n_valid = len(valid_sites)
    print(f"  {n_valid} sites with both metrics and readings")

    # Validate adaptation columns are present
    available_adapt_cols = [
        c for c in per_site.columns if any(
            c == f"r2_{m}_at_{n}" for m in ADAPT_MODES for n in ADAPT_NS
        )
    ]
    print(f"  Adaptation columns found: {len(available_adapt_cols)}")
    missing_cols = [
        f"r2_{m}_at_{n}"
        for m in ADAPT_MODES for n in ADAPT_NS
        if f"r2_{m}_at_{n}" not in per_site.columns
    ]
    if missing_cols:
        print(f"  WARNING: missing adaptation columns: {missing_cols}")

    # ----- Point estimates (no resampling) -----
    print("\nComputing point estimates...")
    point_zs = compute_zero_shot_metrics(valid_sites, readings_by_site)
    point_adapt = compute_adapt_curve_metrics(valid_sites, per_site, ADAPT_NS, ADAPT_MODES)
    point_all = {**point_zs, **point_adapt}

    # ----- Bootstrap -----
    print(f"Running {N_BOOT} bootstrap iterations (site-level resampling)...")
    rng = np.random.default_rng(SEED)
    boot_results = {k: [] for k in point_all.keys()}

    for i in range(N_BOOT):
        if (i + 1) % 200 == 0:
            print(f"  iteration {i + 1}/{N_BOOT}")
        idx = rng.choice(n_valid, size=n_valid, replace=True)
        sampled = valid_sites[idx]

        metrics = compute_zero_shot_metrics(sampled, readings_by_site)
        adapt_metrics = compute_adapt_curve_metrics(sampled, per_site, ADAPT_NS, ADAPT_MODES)

        for k, v in {**metrics, **adapt_metrics}.items():
            boot_results[k].append(v)

    # ----- Summarize and print -----
    print()
    print("=" * 76)
    print(f"  v11 Bootstrap 95% CIs  ({N_BOOT} iterations, site-level block bootstrap)")
    print("=" * 76)

    # Zero-shot section
    print()
    print("  ZERO-SHOT METRICS")
    print(f"  {'Metric':<28s} {'Point':>10s}  {'2.5%':>10s}  {'97.5%':>10s}")
    print("  " + "-" * 66)

    output_zs = {}
    for k in point_zs.keys():
        arr = np.array(boot_results[k])
        lo = float(np.nanpercentile(arr, 2.5))
        hi = float(np.nanpercentile(arr, 97.5))
        pt = point_zs[k]
        output_zs[k] = {"point": round(pt, 4), "ci_lo": round(lo, 4), "ci_hi": round(hi, 4)}
        print(f"  {k:<28s} {pt:>10.4f}  [{lo:>10.4f}, {hi:>10.4f}]")

    # Adaptation curve section
    print()
    print("  ADAPTATION CURVE  (MedSiteR² by N calibration samples)")
    print(f"  {'Key':<35s} {'Point':>10s}  {'2.5%':>10s}  {'97.5%':>10s}")
    print("  " + "-" * 73)

    output_adapt = {}
    for mode in ADAPT_MODES:
        for n in ADAPT_NS:
            k = f"{mode}_at_{n}_MedSiteR2"
            if k not in point_adapt:
                continue
            arr = np.array(boot_results[k])
            lo = float(np.nanpercentile(arr, 2.5))
            hi = float(np.nanpercentile(arr, 97.5))
            pt = point_adapt[k]
            output_adapt[k] = {
                "point": round(pt, 4),
                "ci_lo": round(lo, 4),
                "ci_hi": round(hi, 4),
            }
            print(f"  {k:<35s} {pt:>10.4f}  [{lo:>10.4f}, {hi:>10.4f}]")

    print("=" * 76)

    # ----- Save JSON -----
    final_output = {
        "meta": {
            "model": "v11_extreme_expanded",
            "n_sites": n_valid,
            "n_readings": len(per_read),
            "n_boot": N_BOOT,
            "seed": SEED,
            "bootstrap_unit": "sites",
            "ci_level": "95%",
            "adapt_modes": ADAPT_MODES,
            "adapt_ns": ADAPT_NS,
            "source_per_site": str(PER_SITE_PATH),
            "source_per_reading": str(PER_READ_PATH),
        },
        "zero_shot": output_zs,
        "adaptation_curve": output_adapt,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(final_output, f, indent=2)
    print(f"\nSaved: {OUT_JSON}")


if __name__ == "__main__":
    main()
