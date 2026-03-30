#!/usr/bin/env python
"""Deterministic evaluation pipeline for murkml CatBoost models on holdout sites.

Usage:
    python scripts/evaluate_model.py \
      --model data/results/models/ssc_C_v4_boxcox02.cbm \
      --meta data/results/models/ssc_C_v4_boxcox02_meta.json \
      --label v4_test \
      --adaptation bayesian

Produces three output files:
  1. {label}_per_reading.parquet  — every holdout sample
  2. {label}_per_site.parquet     — one row per holdout site
  3. {label}_summary.json         — adaptation curve, overall metrics, parameters
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool
from scipy.special import boxcox1p

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

DATA_DIR = PROJECT_ROOT / "data"

from murkml.data.attributes import load_streamcat_attrs
from murkml.evaluate.metrics import (
    kge,
    r_squared,
    rmse,
    safe_inv_boxcox1p,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EXPECTED_HOLDOUT_SITES = 76
EXPECTED_HOLDOUT_SAMPLES = 5847
ADAPTATION_NS = [0, 1, 2, 3, 5, 10, 20, 30, 50]


# ---------------------------------------------------------------------------
# Transform helpers
# ---------------------------------------------------------------------------

def forward_transform(values: np.ndarray, transform_type: str, lmbda: float | None) -> np.ndarray:
    """Transform native-space values into model space."""
    if transform_type == "log1p":
        return np.log1p(np.clip(values, 0, None))
    elif transform_type == "boxcox":
        return boxcox1p(np.clip(values, 0, None), lmbda)
    elif transform_type == "sqrt":
        return np.sqrt(np.clip(values, 0, None))
    elif transform_type == "none":
        return values.copy()
    else:
        raise ValueError(f"Unknown transform: {transform_type!r}")


def inverse_transform(values: np.ndarray, transform_type: str, lmbda: float | None) -> np.ndarray:
    """Transform model-space values back to native space."""
    if transform_type == "log1p":
        return np.expm1(values)
    elif transform_type == "boxcox":
        return safe_inv_boxcox1p(values, lmbda)
    elif transform_type == "sqrt":
        return np.square(values)
    elif transform_type == "none":
        return values.copy()
    else:
        raise ValueError(f"Unknown transform: {transform_type!r}")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_holdout_data(meta: dict) -> pd.DataFrame:
    """Load holdout data with all features, exactly one way."""
    logger.info("Loading holdout data...")

    # 1. Load paired data
    paired = pd.read_parquet(DATA_DIR / "processed" / "turbidity_ssc_paired.parquet")
    logger.info(f"  Paired data: {len(paired)} samples, {paired['site_id'].nunique()} sites")

    # 2. Filter to holdout sites
    split = pd.read_parquet(DATA_DIR / "train_holdout_split.parquet")
    holdout_ids = set(split[split["role"] == "holdout"]["site_id"])
    holdout = paired[paired["site_id"].isin(holdout_ids)].copy()
    logger.info(f"  Holdout filter: {len(holdout)} samples, {holdout['site_id'].nunique()} sites")

    # 3. Merge basic site attributes
    basic = pd.read_parquet(DATA_DIR / "site_attributes.parquet")
    # Drop columns that already exist in holdout (except site_id)
    overlap_basic = set(basic.columns) & set(holdout.columns) - {"site_id"}
    basic_clean = basic.drop(columns=list(overlap_basic))
    holdout = holdout.merge(basic_clean, on="site_id", how="left")
    logger.info(f"  After basic merge: {len(holdout)} samples")

    # 4. Merge StreamCat
    streamcat = load_streamcat_attrs(DATA_DIR)
    overlap_sc = set(streamcat.columns) & set(holdout.columns) - {"site_id"}
    streamcat_clean = streamcat.drop(columns=list(overlap_sc))
    holdout = holdout.merge(streamcat_clean, on="site_id", how="left")
    logger.info(f"  After StreamCat merge: {len(holdout)} samples")

    # Assertions
    n_sites = holdout["site_id"].nunique()
    n_samples = len(holdout)
    assert n_sites == EXPECTED_HOLDOUT_SITES, (
        f"Expected {EXPECTED_HOLDOUT_SITES} holdout sites, got {n_sites}"
    )
    assert n_samples == EXPECTED_HOLDOUT_SAMPLES, (
        f"Expected {EXPECTED_HOLDOUT_SAMPLES} holdout samples, got {n_samples}"
    )
    logger.info(f"  VERIFIED: {n_sites} sites, {n_samples} samples")

    return holdout


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------

def predict_holdout(
    model: CatBoostRegressor,
    holdout: pd.DataFrame,
    meta: dict,
) -> pd.DataFrame:
    """Generate predictions for all holdout samples. Returns DataFrame with predictions added."""
    feature_cols = meta["feature_cols"]
    cat_cols = meta.get("cat_cols", [])
    train_medians = meta.get("train_median", {})
    transform_type = meta["transform_type"]
    lmbda = meta.get("transform_lmbda")
    bcf = meta["bcf"]

    # Validate
    assert 0.5 <= bcf <= 5.0, f"BCF {bcf} outside sanity range [0.5, 5.0]"
    assert transform_type in ("log1p", "boxcox", "sqrt", "none"), (
        f"Unknown transform: {transform_type}"
    )
    model_n_features = len(model.feature_names_) if hasattr(model, 'feature_names_') else None
    if model_n_features is not None:
        assert len(feature_cols) == model_n_features, (
            f"Feature count mismatch: meta has {len(feature_cols)}, model has {model_n_features}"
        )

    # Build feature matrix
    X = holdout[feature_cols].copy()

    # Fill missing numeric features with training medians
    for col in feature_cols:
        if col in cat_cols:
            continue
        if col in train_medians and X[col].isna().any():
            X[col] = X[col].fillna(train_medians[col])

    # Create CatBoost Pool
    cat_indices = meta.get("cat_indices", [])
    pool = Pool(X, cat_features=cat_indices)

    # Predict in model space
    y_pred_ms = model.predict(pool)
    assert not np.any(np.isnan(y_pred_ms)), "NaN in model predictions"

    # Transform true values to model space
    y_true_native = holdout["lab_value"].values
    y_true_ms = forward_transform(y_true_native, transform_type, lmbda)

    # Convert predictions to native space (BCF applied ONCE here)
    y_pred_native = inverse_transform(y_pred_ms, transform_type, lmbda) * bcf
    y_pred_native = np.clip(y_pred_native, 0, None)

    # Build result DataFrame
    result = holdout[["site_id"]].copy()
    if "sample_time" in holdout.columns:
        result["sample_time"] = holdout["sample_time"].values
    result["y_true_native"] = y_true_native
    result["y_pred_native"] = y_pred_native
    result["y_true_model_space"] = y_true_ms
    result["y_pred_model_space"] = y_pred_ms
    result["abs_error"] = np.abs(y_true_native - y_pred_native)
    result["pct_error"] = np.where(
        y_true_native > 0,
        100 * np.abs(y_true_native - y_pred_native) / y_true_native,
        np.nan,
    )

    # Carry through stratification columns
    for col in ["turbidity_instant", "discharge_instant", "collection_method"]:
        if col in holdout.columns:
            result[col] = holdout[col].values

    return result


# ---------------------------------------------------------------------------
# Adaptation methods
# ---------------------------------------------------------------------------

def adapt_none(
    y_pred_ms: np.ndarray,
    y_true_ms: np.ndarray,
    cal_idx: np.ndarray,
    test_idx: np.ndarray,
    transform_type: str,
    lmbda: float | None,
    bcf: float,
) -> np.ndarray:
    """No adaptation — just model predictions with BCF."""
    pred_native = inverse_transform(y_pred_ms[test_idx], transform_type, lmbda) * bcf
    return np.clip(pred_native, 0, None)


def adapt_old_2param(
    y_pred_ms: np.ndarray,
    y_true_ms: np.ndarray,
    cal_idx: np.ndarray,
    test_idx: np.ndarray,
    transform_type: str,
    lmbda: float | None,
    bcf: float,
) -> np.ndarray:
    """Old 2-parameter adaptation: OLS in model space + per-trial BCF."""
    cal_pred = y_pred_ms[cal_idx]
    cal_true = y_true_ms[cal_idx]

    if len(cal_idx) == 1:
        # Offset only
        a, b = 1.0, float(cal_true[0] - cal_pred[0])
    else:
        # OLS: y_true_ms = a * y_pred_ms + b
        from numpy.polynomial.polynomial import polyfit
        coeffs = polyfit(cal_pred, cal_true, 1)  # [intercept, slope]
        b, a = float(coeffs[0]), float(coeffs[1])
        a = np.clip(a, 0.1, 10.0)
        # Recalculate intercept so the line still passes through the
        # calibration centroid after slope clipping (Gemini review fix)
        b = float(np.mean(cal_true) - a * np.mean(cal_pred))

    # Apply correction in model space
    corrected_ms = a * y_pred_ms + b

    # Per-trial BCF from calibration samples
    cal_true_native = inverse_transform(cal_true, transform_type, lmbda)
    cal_corrected_native = inverse_transform(corrected_ms[cal_idx], transform_type, lmbda)
    mean_corrected = np.mean(cal_corrected_native)
    if mean_corrected > 0:
        bcf_trial = np.clip(np.mean(cal_true_native) / mean_corrected, 0.1, 10.0)
    else:
        bcf_trial = 1.0

    pred_native = inverse_transform(corrected_ms[test_idx], transform_type, lmbda) * bcf_trial
    return np.clip(pred_native, 0, None)


def _student_t_shrinkage(residuals: np.ndarray, k: float, df: float = 4) -> float:
    """Compute shrinkage-adjusted bias correction using Student-t prior.

    Uses MAD-based robust scale estimation and t-distribution influence
    weighting so that sites with legitimately large biases aren't over-shrunk.
    Ported from site_adaptation_bayesian.py.
    """
    N = len(residuals)
    if N == 0:
        return 0.0
    raw_delta = float(np.mean(residuals))

    # Robust scale estimation (MAD-based)
    if N > 1:
        mad = float(np.median(np.abs(residuals - np.median(residuals))))
        sigma = mad * 1.4826 if mad > 0 else float(np.std(residuals))
        if sigma == 0:
            sigma = 1.0
    else:
        sigma = 1.0

    z = abs(raw_delta) / (sigma / max(np.sqrt(N), 1))

    # Student-t influence weight: reduces effective k for extreme sites
    w_t = (df + 1) / (df + z**2)
    w_t = float(np.clip(w_t, 0.1, 1.0))

    effective_k = k * w_t
    delta = (N / (N + effective_k)) * raw_delta
    return float(delta)


def adapt_bayesian(
    y_pred_ms: np.ndarray,
    y_true_ms: np.ndarray,
    cal_idx: np.ndarray,
    test_idx: np.ndarray,
    transform_type: str,
    lmbda: float | None,
    bcf: float,
    k: float = 15,
    df: float = 4,
    slope_k: float = 10,
    bcf_k_mult: float = 3.0,
) -> np.ndarray:
    """Staged Bayesian shrinkage adaptation with Student-t prior.

    Stage 1 (N < 10): intercept-only correction with shrinkage
    Stage 2 (N >= 10): slope + intercept, both shrunk

    Per-trial BCF shrunk toward 1.0 (more conservative than global BCF).
    Ported from site_adaptation_bayesian.py's bayesian_adapt().
    """
    from scipy.stats import linregress

    N = len(cal_idx)
    cal_pred = y_pred_ms[cal_idx]
    cal_true = y_true_ms[cal_idx]
    residuals = cal_true - cal_pred

    if N < 10:
        # Stage 1: intercept-only with Student-t shrinkage
        delta = _student_t_shrinkage(residuals, k=k, df=df)
        a = 1.0
        corrected_ms = y_pred_ms[test_idx] + delta
    else:
        # Stage 2: slope + intercept
        try:
            a_raw, _, _, _, _ = linregress(cal_pred, cal_true)
            a_raw = float(np.clip(a_raw, 0.1, 10.0))
        except Exception:
            a_raw = 1.0
        # Shrink slope toward 1.0
        a = 1.0 + (N / (N + slope_k)) * (a_raw - 1.0)

        # Intercept from residuals after slope correction
        residuals_after_slope = cal_true - a * cal_pred
        delta = _student_t_shrinkage(residuals_after_slope, k=k, df=df)

        corrected_ms = a * y_pred_ms[test_idx] + delta

    corrected_native = inverse_transform(corrected_ms, transform_type, lmbda)
    corrected_native = np.clip(corrected_native, 0, None)

    # Per-trial BCF shrunk toward 1.0 (more conservative than global)
    k_bcf = bcf_k_mult * k
    cal_corrected_ms = a * cal_pred + delta
    cal_corrected_native = inverse_transform(cal_corrected_ms, transform_type, lmbda)
    cal_corrected_native = np.clip(cal_corrected_native, 1e-6, None)
    cal_true_native = inverse_transform(cal_true, transform_type, lmbda)
    cal_pred_mean = float(np.mean(cal_corrected_native))
    if cal_pred_mean > 0:
        bcf_raw = float(np.clip(np.mean(cal_true_native) / cal_pred_mean, 0.1, 10.0))
        bcf_shrinkage = N / (N + k_bcf)
        trial_bcf = 1.0 + bcf_shrinkage * (bcf_raw - 1.0)
    else:
        trial_bcf = 1.0
    corrected_native *= trial_bcf

    return corrected_native


def adapt_ols_loglog(
    cal_turb: np.ndarray,
    cal_ssc: np.ndarray,
    test_turb: np.ndarray,
) -> np.ndarray:
    """Log-log regression: log(SSC) = a * log(turbidity) + b. Ignores CatBoost model."""
    # Filter valid (positive) values
    valid = (cal_turb > 0) & (cal_ssc > 0)
    if valid.sum() < 2:
        # Fall back to ratio
        if valid.sum() == 1:
            ratio = cal_ssc[valid][0] / cal_turb[valid][0]
            return np.clip(test_turb * ratio, 0, None)
        return np.full(len(test_turb), np.nanmedian(cal_ssc))

    log_turb = np.log(cal_turb[valid])
    log_ssc = np.log(cal_ssc[valid])

    from numpy.polynomial.polynomial import polyfit
    coeffs = polyfit(log_turb, log_ssc, 1)  # [intercept, slope]
    b, a = float(coeffs[0]), float(coeffs[1])

    # Predict
    test_valid = test_turb > 0
    pred = np.full(len(test_turb), 0.0)
    pred[test_valid] = np.exp(a * np.log(test_turb[test_valid]) + b)
    return np.clip(pred, 0, None)


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------

def compute_site_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Compute standard metrics for a single site."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    n = len(y_true)
    if n < 2:
        return {"r2": np.nan, "kge": np.nan, "rmse": np.nan, "mape_pct": np.nan, "frac_within_2x": np.nan, "n": n}

    # Guard against zero-variance sites (R² is undefined)
    ss_tot = np.sum((y_true - y_true.mean()) ** 2)
    if ss_tot < 1e-10:
        return {"r2": np.nan, "kge": np.nan, "rmse": float(rmse(y_true, y_pred)), "mape_pct": np.nan, "frac_within_2x": np.nan, "n": n}

    r2_val = r_squared(y_true, y_pred)
    # Guard against zero-variance predictions (KGE correlation undefined)
    if np.std(y_pred) < 1e-10 or np.std(y_true) < 1e-10:
        kge_val = np.nan
    else:
        kge_val = kge(y_true, y_pred)
    rmse_val = rmse(y_true, y_pred)

    # MAPE (skip zeros)
    nonzero = y_true > 0
    if nonzero.sum() > 0:
        mape = 100 * np.mean(np.abs(y_true[nonzero] - y_pred[nonzero]) / y_true[nonzero])
    else:
        mape = np.nan

    # Fraction within 2x
    ratios = np.where(y_true > 0, y_pred / y_true, np.nan)
    valid_ratios = ratios[~np.isnan(ratios)]
    frac_2x = np.mean((valid_ratios >= 0.5) & (valid_ratios <= 2.0)) if len(valid_ratios) > 0 else np.nan

    return {"r2": r2_val, "kge": kge_val, "rmse": rmse_val, "mape_pct": mape, "frac_within_2x": frac_2x, "n": n}


# ---------------------------------------------------------------------------
# Adaptation curve
# ---------------------------------------------------------------------------

def run_adaptation_curve(
    readings: pd.DataFrame,
    meta: dict,
    method: str,
    seed: int,
    n_trials: int,
    k: float,
    df: float = 4,
    slope_k: float = 10,
    bcf_k_mult: float = 3.0,
) -> dict:
    """Run adaptation curve for all N values across all holdout sites.

    Returns:
        Dict with per-site-per-N results and aggregated curve.
    """
    transform_type = meta["transform_type"]
    lmbda = meta.get("transform_lmbda")
    bcf = meta["bcf"]

    sites = sorted(readings["site_id"].unique())
    curve_results = {n_val: [] for n_val in ADAPTATION_NS}
    per_site_adaptation = {}  # site_id -> {n -> median_r2}

    for site_id in sites:
        site_mask = readings["site_id"] == site_id
        site_data = readings[site_mask]
        n_site = len(site_data)

        y_pred_ms = site_data["y_pred_model_space"].values
        y_true_ms = site_data["y_true_model_space"].values
        y_true_native = site_data["y_true_native"].values
        turb = site_data["turbidity_instant"].values if "turbidity_instant" in site_data.columns else None

        site_adapt = {}

        for n_val in ADAPTATION_NS:
            if n_val == 0:
                # Zero-shot: use all samples
                if method == "ols":
                    # OLS has no zero-shot — skip
                    site_adapt[0] = np.nan
                    continue
                pred_native = adapt_none(y_pred_ms, y_true_ms, np.array([]), np.arange(n_site),
                                          transform_type, lmbda, bcf)
                metrics = compute_site_metrics(y_true_native, pred_native)
                curve_results[0].append(metrics)
                site_adapt[0] = metrics["r2"]
                continue

            if n_val >= n_site:
                # Not enough samples — skip
                site_adapt[n_val] = np.nan
                continue

            trial_metrics = []
            for trial in range(n_trials):
                site_hash = int(hashlib.md5(str(site_id).encode()).hexdigest(), 16) % (2**31)
                rng = np.random.default_rng(seed + site_hash + n_val * 1000 + trial)
                cal_idx = rng.choice(n_site, size=n_val, replace=False)
                test_idx = np.setdiff1d(np.arange(n_site), cal_idx)

                if len(test_idx) == 0:
                    continue

                if method == "none":
                    pred = adapt_none(y_pred_ms, y_true_ms, cal_idx, test_idx,
                                       transform_type, lmbda, bcf)
                elif method == "old_2param":
                    pred = adapt_old_2param(y_pred_ms, y_true_ms, cal_idx, test_idx,
                                             transform_type, lmbda, bcf)
                elif method == "bayesian":
                    pred = adapt_bayesian(y_pred_ms, y_true_ms, cal_idx, test_idx,
                                           transform_type, lmbda, bcf, k=k, df=df,
                                           slope_k=slope_k, bcf_k_mult=bcf_k_mult)
                elif method == "ols":
                    if turb is None:
                        continue
                    pred = adapt_ols_loglog(turb[cal_idx], y_true_native[cal_idx], turb[test_idx])
                else:
                    raise ValueError(f"Unknown adaptation method: {method}")

                true_test = y_true_native[test_idx]
                m = compute_site_metrics(true_test, pred)
                trial_metrics.append(m)

            # Filter out NaN results from tiny test sets
            valid_trials = [m for m in trial_metrics if not np.isnan(m.get("r2", np.nan))]
            if valid_trials:
                # Median across valid trials
                median_r2 = float(np.nanmedian([m["r2"] for m in valid_trials]))
                median_kge = float(np.nanmedian([m["kge"] for m in valid_trials]))
                median_rmse = float(np.nanmedian([m["rmse"] for m in valid_trials]))
                median_mape = float(np.nanmedian([m["mape_pct"] for m in valid_trials]))
                median_2x = float(np.nanmedian([m["frac_within_2x"] for m in valid_trials]))
                curve_results[n_val].append({
                    "r2": median_r2, "kge": median_kge, "rmse": median_rmse,
                    "mape_pct": median_mape, "frac_within_2x": median_2x,
                    "n": int(np.median([m["n"] for m in valid_trials])),
                })
                site_adapt[n_val] = median_r2
            else:
                site_adapt[n_val] = np.nan

        per_site_adaptation[site_id] = site_adapt

    # Aggregate curve
    agg_curve = {}
    for n_val in ADAPTATION_NS:
        entries = curve_results[n_val]
        if not entries:
            agg_curve[n_val] = {"median_r2": np.nan, "q25_r2": np.nan, "q75_r2": np.nan,
                                "median_kge": np.nan, "median_rmse": np.nan, "n_sites": 0}
            continue
        r2s = [e["r2"] for e in entries]
        kges = [e["kge"] for e in entries]
        rmses = [e["rmse"] for e in entries]
        agg_curve[n_val] = {
            "median_r2": float(np.nanmedian(r2s)),
            "q25_r2": float(np.nanpercentile(r2s, 25)),
            "q75_r2": float(np.nanpercentile(r2s, 75)),
            "median_kge": float(np.nanmedian(kges)),
            "median_rmse": float(np.nanmedian(rmses)),
            "n_sites": len(entries),
        }

    return {
        "curve": agg_curve,
        "per_site": per_site_adaptation,
    }


# ---------------------------------------------------------------------------
# Output generation
# ---------------------------------------------------------------------------

def save_per_reading(readings: pd.DataFrame, output_dir: Path, label: str) -> Path:
    """Save per-reading parquet."""
    path = output_dir / f"{label}_per_reading.parquet"
    readings.to_parquet(path, index=False)
    logger.info(f"  Per-reading: {path} ({len(readings)} rows)")
    return path


def save_per_site(
    readings: pd.DataFrame,
    adaptation: dict,
    output_dir: Path,
    label: str,
) -> Path:
    """Save per-site parquet with zero-shot metrics and adaptation R2 at each N."""
    rows = []
    for site_id, group in readings.groupby("site_id"):
        y_true = group["y_true_native"].values
        y_pred = group["y_pred_native"].values
        m = compute_site_metrics(y_true, y_pred)
        row = {
            "site_id": site_id,
            "n_samples": len(group),
            "r2_native": m["r2"],
            "rmse_native": m["rmse"],
            "mape_pct": m["mape_pct"],
            "frac_within_2x": m["frac_within_2x"],
        }
        # Add adaptation results
        site_adapt = adaptation["per_site"].get(site_id, {})
        for n_val in ADAPTATION_NS:
            row[f"r2_at_{n_val}"] = site_adapt.get(n_val, np.nan)

        rows.append(row)

    df = pd.DataFrame(rows)
    path = output_dir / f"{label}_per_site.parquet"
    df.to_parquet(path, index=False)
    logger.info(f"  Per-site: {path} ({len(df)} rows)")
    return path


def save_summary(
    readings: pd.DataFrame,
    adaptation: dict,
    meta: dict,
    args: argparse.Namespace,
    output_dir: Path,
    label: str,
) -> Path:
    """Save summary JSON."""
    # Overall zero-shot metrics (pooled)
    y_true = readings["y_true_native"].values
    y_pred = readings["y_pred_native"].values
    pooled = compute_site_metrics(y_true, y_pred)

    # Median per-site R2
    per_site_r2s = []
    for _, group in readings.groupby("site_id"):
        m = compute_site_metrics(group["y_true_native"].values, group["y_pred_native"].values)
        per_site_r2s.append(m["r2"])

    # Adaptation curve (convert int keys to strings for JSON)
    curve_json = {}
    for n_val, vals in adaptation["curve"].items():
        curve_json[str(n_val)] = {k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in vals.items()}

    summary = {
        "label": label,
        "model_path": str(args.model),
        "meta_path": str(args.meta),
        "adaptation_method": args.adaptation,
        "adaptation_params": {"k": args.k, "df": args.df, "slope_k": args.slope_k, "bcf_k_mult": args.bcf_k_mult, "n_trials": args.n_trials, "seed": args.seed},
        "holdout_sites": int(readings["site_id"].nunique()),
        "holdout_samples": len(readings),
        "zero_shot": {
            "pooled_r2": pooled["r2"],
            "pooled_kge": pooled["kge"],
            "pooled_rmse": pooled["rmse"],
            "pooled_mape_pct": pooled["mape_pct"],
            "pooled_frac_within_2x": pooled["frac_within_2x"],
            "median_per_site_r2": float(np.nanmedian(per_site_r2s)),
        },
        "adaptation_curve": curve_json,
        "transform_type": meta["transform_type"],
        "transform_lmbda": meta.get("transform_lmbda"),
        "bcf": meta["bcf"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    path = output_dir / f"{label}_summary.json"
    with open(path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    logger.info(f"  Summary: {path}")
    return path


def print_summary(readings: pd.DataFrame, adaptation: dict, method: str):
    """Print human-readable summary to stdout."""
    y_true = readings["y_true_native"].values
    y_pred = readings["y_pred_native"].values
    pooled = compute_site_metrics(y_true, y_pred)

    per_site_r2s = []
    for _, group in readings.groupby("site_id"):
        m = compute_site_metrics(group["y_true_native"].values, group["y_pred_native"].values)
        per_site_r2s.append(m["r2"])

    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"Sites: {readings['site_id'].nunique()}  |  Samples: {len(readings)}")
    print(f"\nZero-shot (no adaptation):")
    print(f"  Pooled R2:         {pooled['r2']:.4f}")
    print(f"  Pooled KGE:        {pooled['kge']:.4f}")
    print(f"  Pooled RMSE:       {pooled['rmse']:.2f} mg/L")
    print(f"  MAPE:              {pooled['mape_pct']:.1f}%")
    print(f"  Within 2x:         {pooled['frac_within_2x']:.1%}")
    print(f"  Median per-site R2: {np.nanmedian(per_site_r2s):.4f}")

    print(f"\nAdaptation curve ({method}):")
    print(f"  {'N':>4s}  {'Med R2':>8s}  {'Q25':>8s}  {'Q75':>8s}  {'Med KGE':>8s}  {'Sites':>5s}")
    for n_val in ADAPTATION_NS:
        c = adaptation["curve"].get(n_val, {})
        if not c or c.get("n_sites", 0) == 0:
            continue
        mr2 = c["median_r2"]
        q25 = c["q25_r2"]
        q75 = c["q75_r2"]
        mkge = c["median_kge"]
        ns = c["n_sites"]
        print(f"  {n_val:>4d}  {mr2:>8.4f}  {q25:>8.4f}  {q75:>8.4f}  {mkge:>8.4f}  {ns:>5d}")
    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Evaluate a CatBoost model on holdout sites.")
    parser.add_argument("--model", type=str, required=True, help="Path to .cbm model file")
    parser.add_argument("--meta", type=str, required=True, help="Path to _meta.json file")
    parser.add_argument("--label", type=str, required=True, help="Experiment label for output files")
    parser.add_argument("--adaptation", type=str, default="bayesian",
                        choices=["none", "old_2param", "bayesian", "ols"],
                        help="Adaptation method (default: bayesian)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--n-trials", type=int, default=50, help="Trials per site per N (default: 50)")
    parser.add_argument("--k", type=float, default=15, help="Bayesian shrinkage parameter (default: 15)")
    parser.add_argument("--df", type=float, default=4, help="Student-t prior degrees of freedom (default: 4)")
    parser.add_argument("--slope-k", type=float, default=10, help="Slope shrinkage constant for N>=10 (default: 10)")
    parser.add_argument("--bcf-k-mult", type=float, default=3.0, help="BCF shrinkage multiplier (default: 3.0)")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory (default: data/results/evaluations/)")
    args = parser.parse_args()

    t0 = time.time()

    # Resolve paths
    model_path = Path(args.model)
    meta_path = Path(args.meta)
    output_dir = Path(args.output_dir) if args.output_dir else DATA_DIR / "results" / "evaluations"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load meta
    with open(meta_path) as f:
        meta = json.load(f)

    logger.info(f"Model: {model_path}")
    logger.info(f"Transform: {meta['transform_type']} (lambda={meta.get('transform_lmbda')})")
    logger.info(f"BCF: {meta['bcf']:.4f} ({meta.get('bcf_method', 'unknown')})")
    logger.info(f"Features: {len(meta['feature_cols'])}")
    logger.info(f"Adaptation: {args.adaptation} (k={args.k}, df={args.df}, slope_k={args.slope_k}, bcf_k_mult={args.bcf_k_mult}, trials={args.n_trials}, seed={args.seed})")

    # Validate meta
    assert meta["transform_type"] in ("log1p", "boxcox", "sqrt", "none"), (
        f"Unknown transform: {meta['transform_type']}"
    )
    assert 0.5 <= meta["bcf"] <= 5.0, f"BCF {meta['bcf']} outside [0.5, 5.0]"

    # Load model
    model = CatBoostRegressor()
    model.load_model(str(model_path))
    logger.info(f"Model loaded: {model.tree_count_} trees")

    # Validate feature count
    n_model_features = len(model.feature_names_)
    n_meta_features = len(meta["feature_cols"])
    assert n_model_features == n_meta_features, (
        f"Feature count mismatch: model has {n_model_features}, meta has {n_meta_features}"
    )

    # Load data
    holdout = load_holdout_data(meta)

    # Generate predictions
    logger.info("Generating predictions...")
    readings = predict_holdout(model, holdout, meta)
    assert not readings["y_pred_native"].isna().any(), "NaN in native predictions"

    # Run adaptation curve
    logger.info(f"Running adaptation curve ({args.adaptation})...")
    adaptation = run_adaptation_curve(
        readings, meta, args.adaptation, args.seed, args.n_trials, args.k, args.df,
        args.slope_k, args.bcf_k_mult,
    )

    # Save outputs
    logger.info("Saving outputs...")
    save_per_reading(readings, output_dir, args.label)
    save_per_site(readings, adaptation, output_dir, args.label)
    save_summary(readings, adaptation, meta, args, output_dir, args.label)

    # Print summary
    print_summary(readings, adaptation, args.adaptation)

    elapsed = time.time() - t0
    logger.info(f"Done in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
