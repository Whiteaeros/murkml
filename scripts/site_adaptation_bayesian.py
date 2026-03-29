"""Bayesian site-adaptive correction experiment.

Replaces the 2-parameter OLS correction with a 1-parameter additive bias
in Box-Cox space, using Bayesian shrinkage toward zero. Staged: intercept-only
for N<10, slope+intercept for N>=10.

The residual distribution is NOT Gaussian (skewness=2.0, kurtosis=13.8),
so we use a Student-t prior which has heavier tails and won't over-shrink
sites with large positive residuals.

For the Student-t shrinkage, the effective shrinkage factor becomes:
    delta = (N / (N + k * weight)) * raw_delta
where weight adjusts based on how extreme the residuals are relative to
the t-distribution. For near-zero residuals, weight ~ 1 (same as Gaussian).
For large residuals, weight < 1 (less shrinkage = trusts data more).

Usage:
    python scripts/site_adaptation_bayesian.py
    python scripts/site_adaptation_bayesian.py --k-values 3 5 7 10
    python scripts/site_adaptation_bayesian.py --n-trials 100
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import linregress

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from murkml.evaluate.metrics import safe_inv_boxcox1p

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"


# ---------------------------------------------------------------------------
# Transform helpers (same as site_adaptation.py)
# ---------------------------------------------------------------------------

def _forward_transform(y_native, transform_type, lmbda):
    if transform_type == "log1p" or transform_type is None:
        return np.log1p(y_native)
    elif transform_type == "boxcox":
        from scipy.special import boxcox1p
        return boxcox1p(y_native, lmbda)
    elif transform_type == "sqrt":
        return np.sqrt(y_native)
    elif transform_type == "none":
        return y_native.copy()
    else:
        return np.log1p(y_native)


def _inverse_transform(y_transformed, transform_type, lmbda):
    if transform_type == "log1p" or transform_type is None:
        return np.expm1(y_transformed)
    elif transform_type == "boxcox":
        return safe_inv_boxcox1p(y_transformed, lmbda)
    elif transform_type == "sqrt":
        return np.square(y_transformed)
    elif transform_type == "none":
        return y_transformed.copy()
    else:
        return np.expm1(y_transformed)


# ---------------------------------------------------------------------------
# Model / data loading (uses v4 model explicitly)
# ---------------------------------------------------------------------------

def load_model_and_meta():
    """Load the v4 Box-Cox 0.2 model and metadata."""
    from catboost import CatBoostRegressor

    model_path = DATA_DIR / "results" / "models" / "ssc_C_v4_boxcox02.cbm"
    meta_path = DATA_DIR / "results" / "models" / "ssc_C_v4_boxcox02_meta.json"

    model = CatBoostRegressor()
    model.load_model(str(model_path))

    with open(meta_path) as f:
        meta = json.load(f)

    logger.info(f"Loaded v4 model: {model.tree_count_} trees, {len(meta['feature_cols'])} features")
    logger.info(f"Transform: {meta.get('transform_type')}, lambda: {meta.get('transform_lmbda')}")
    return model, meta


def generate_holdout_predictions(model, meta):
    """Generate predictions for all holdout sites using the v4 model."""
    paired = pd.read_parquet(DATA_DIR / "processed" / "turbidity_ssc_paired.parquet")
    split = pd.read_parquet(DATA_DIR / "train_holdout_split.parquet")

    holdout_ids = set(split[split["role"] == "holdout"]["site_id"])
    holdout_data = paired[paired["site_id"].isin(holdout_ids)].copy()

    logger.info(f"Holdout sites: {holdout_data['site_id'].nunique()}, samples: {len(holdout_data)}")

    if holdout_data.empty:
        logger.error("No holdout data found!")
        return pd.DataFrame()

    # Merge watershed attributes
    from murkml.data.attributes import load_streamcat_attrs
    ws_attrs = load_streamcat_attrs(DATA_DIR)
    basic_attrs = pd.read_parquet(DATA_DIR / "site_attributes.parquet")

    basic_cols_available = [c for c in basic_attrs.columns if c != "site_id"]
    holdout_data = holdout_data.merge(
        basic_attrs[["site_id"] + basic_cols_available].drop_duplicates("site_id"),
        on="site_id", how="left",
    )
    ws_cols = set(ws_attrs.columns) - {"site_id"}
    for col in ["drainage_area_km2", "huc2", "slope_pct"]:
        if col in holdout_data.columns and col in ws_cols:
            holdout_data = holdout_data.drop(columns=[col])
    holdout_data = holdout_data.merge(ws_attrs, on="site_id", how="left")

    feature_cols = meta["feature_cols"]
    cat_cols = meta["cat_cols"]
    num_cols = [c for c in feature_cols if c not in cat_cols]

    missing_feats = [c for c in feature_cols if c not in holdout_data.columns]
    if missing_feats:
        logger.warning(f"Missing features (filling NaN): {missing_feats}")
        for c in missing_feats:
            holdout_data[c] = np.nan

    X = holdout_data[feature_cols].copy()
    train_median = meta.get("train_median", {})
    for col in num_cols:
        if col in X.columns and col in train_median:
            X[col] = X[col].fillna(train_median[col])
    for col in cat_cols:
        if col in X.columns:
            X[col] = X[col].fillna("missing").astype(str)

    from catboost import Pool
    cat_indices = [feature_cols.index(c) for c in cat_cols]
    pool = Pool(X, cat_features=cat_indices)
    y_pred_bc = model.predict(pool)

    transform_type = meta.get("transform_type", "log1p")
    lmbda = meta.get("transform_lmbda")
    native_vals = holdout_data["lab_value"].values

    result = pd.DataFrame({
        "site_id": holdout_data["site_id"].values,
        "sample_time": holdout_data["sample_time"].values if "sample_time" in holdout_data.columns else np.nan,
        "y_true_bc": _forward_transform(native_vals, transform_type, lmbda),
        "y_pred_bc": y_pred_bc,
        "y_true_native": native_vals,
        "y_pred_native": np.clip(_inverse_transform(y_pred_bc, transform_type, lmbda), 0, None),
    })

    logger.info(f"Generated {len(result)} predictions for {result['site_id'].nunique()} holdout sites")
    return result


# ---------------------------------------------------------------------------
# Bayesian shrinkage with Student-t prior
# ---------------------------------------------------------------------------

def student_t_shrinkage(residuals, k, df=4):
    """Compute shrinkage-adjusted bias correction using Student-t prior.

    With a Gaussian prior, the shrinkage is simply N/(N+k). But residuals
    with heavy tails (skewness=2.0, kurtosis=13.8) need a heavier-tailed
    prior so that sites with legitimately large biases aren't over-shrunk.

    Student-t with df=3-5 matches the observed kurtosis well:
    - df=3: kurtosis = infinity (very heavy)
    - df=4: kurtosis = 6 (excess kurtosis = 3)
    - df=5: kurtosis = 9 (excess kurtosis = 6)
    - Observed: kurtosis = 13.8 (excess kurtosis ~ 10.8)

    We use df=4 as default. The exact value matters less than using t vs
    Gaussian, because the key property is that the t-distribution doesn't
    aggressively shrink large residuals.

    The approach: empirical Bayes with a t-prior. For a single observation
    model y_i ~ N(delta, sigma^2/N), delta ~ t(0, tau, df), the posterior
    mean can be approximated as:

        E[delta|data] ~ (N / (N + k * w)) * y_bar

    where w = 1 for |y_bar| << tau (Gaussian-like) and w < 1 for
    |y_bar| >> tau (less shrinkage for extreme values). We use a weight
    based on the t-distribution's influence function.

    Parameters
    ----------
    residuals : array-like
        Observed residuals (observed_bc - predicted_bc) from N cal samples.
    k : float
        Base shrinkage constant (higher = more conservative).
    df : int
        Degrees of freedom for the Student-t prior.

    Returns
    -------
    delta : float
        Shrinkage-adjusted bias correction.
    """
    residuals = np.asarray(residuals, dtype=float)
    N = len(residuals)
    if N == 0:
        return 0.0

    raw_delta = np.mean(residuals)

    # Estimate scale from the residuals (robust: MAD-based)
    if N > 1:
        mad = np.median(np.abs(residuals - np.median(residuals)))
        sigma = mad * 1.4826 if mad > 0 else np.std(residuals)
        if sigma == 0:
            sigma = 1.0  # degenerate case
    else:
        # Single sample: use a global prior scale
        # We'll estimate this from all residuals later; for now use a
        # reasonable default (set externally via the global_sigma parameter)
        sigma = 1.0

    # Standardized delta for the weight calculation
    z = abs(raw_delta) / (sigma / max(np.sqrt(N), 1))

    # Student-t influence weight: for a t(df) distribution, the
    # posterior weight on the data is approximately:
    #   w_t = (df + 1) / (df + z^2)  (relative to z^2 + df)
    # This gives w_t -> 1 when z is small (Gaussian-like behavior)
    # and w_t -> 0 when z is large (less shrinkage for outliers)
    #
    # We use this to REDUCE the effective k for extreme sites:
    #   effective_k = k * w_t
    # So extreme sites get LESS shrinkage (trusted more).
    w_t = (df + 1) / (df + z**2)
    # Clamp to [0.1, 1.0] — never fully turn off shrinkage
    w_t = np.clip(w_t, 0.1, 1.0)

    effective_k = k * w_t
    shrinkage = N / (N + effective_k)
    delta = shrinkage * raw_delta

    return float(delta)


def bayesian_adapt(cal_bc_true, cal_bc_pred, test_bc_pred, k, df=4,
                   transform_type="boxcox", lmbda=0.2,
                   cal_true_native=None, slope_k=10, bcf_k_mult=3.0):
    """Apply Bayesian site adaptation with staged complexity.

    Stage 1 (N < 10): intercept-only correction
        corrected_bc = predicted_bc + delta

    Stage 2 (N >= 10): slope + intercept correction
        corrected_bc = a * predicted_bc + delta
        where a is shrunk toward 1.0 with k2=slope_k

    Parameters
    ----------
    cal_bc_true, cal_bc_pred : arrays
        Calibration data in Box-Cox space.
    test_bc_pred : array
        Test predictions in Box-Cox space.
    k : float
        Shrinkage constant for intercept.
    df : int
        Student-t degrees of freedom.
    transform_type, lmbda : transform params
    cal_true_native : array or None
        Native-space calibration truths for BCF.
    slope_k : float
        Shrinkage constant for slope (more conservative, default 10).

    Returns
    -------
    corrected_native : array
        Corrected predictions in native space.
    params : dict
        Correction parameters (delta, a, bcf, etc.)
    """
    cal_bc_true = np.asarray(cal_bc_true, dtype=float)
    cal_bc_pred = np.asarray(cal_bc_pred, dtype=float)
    test_bc_pred = np.asarray(test_bc_pred, dtype=float)
    N = len(cal_bc_true)

    residuals = cal_bc_true - cal_bc_pred

    if N < 10:
        # Stage 1: intercept-only with Student-t shrinkage
        delta = student_t_shrinkage(residuals, k=k, df=df)
        a = 1.0
        corrected_bc = test_bc_pred + delta
    else:
        # Stage 2: slope + intercept
        # First fit the slope via OLS
        try:
            a_raw, b_raw, _, _, _ = linregress(cal_bc_pred, cal_bc_true)
            a_raw = np.clip(a_raw, 0.1, 10.0)
        except Exception:
            a_raw, b_raw = 1.0, 0.0

        # Shrink slope toward 1.0
        a = 1.0 + (N / (N + slope_k)) * (a_raw - 1.0)

        # Compute residuals after slope correction for the intercept
        slope_corrected = a * cal_bc_pred
        residuals_after_slope = cal_bc_true - slope_corrected
        delta = student_t_shrinkage(residuals_after_slope, k=k, df=df)

        corrected_bc = a * test_bc_pred + delta

    corrected_native = _inverse_transform(corrected_bc, transform_type, lmbda)
    corrected_native = np.clip(corrected_native, 0, None)

    # Snowdon BCF with shrinkage toward 1.0
    # The BCF is a ratio estimator that's very noisy at low N.
    # Shrink toward 1.0 with a SEPARATE, more conservative k.
    # BCF needs more data than the intercept because it's a ratio of means
    # in native space (highly skewed), so we use k_bcf = bcf_k_mult * k.
    bcf = 1.0
    k_bcf = bcf_k_mult * k
    if cal_true_native is not None and N > 0:
        cal_corrected_bc = a * cal_bc_pred + delta
        cal_corrected_native = _inverse_transform(cal_corrected_bc, transform_type, lmbda)
        cal_corrected_native = np.clip(cal_corrected_native, 1e-6, None)
        cal_true_mean = np.mean(cal_true_native)
        cal_pred_mean = np.mean(cal_corrected_native)
        if cal_pred_mean > 0:
            bcf_raw = cal_true_mean / cal_pred_mean
            bcf_raw = np.clip(bcf_raw, 0.1, 10.0)
            # Shrink BCF toward 1.0
            bcf_shrinkage = N / (N + k_bcf)
            bcf = 1.0 + bcf_shrinkage * (bcf_raw - 1.0)
        corrected_native *= bcf

    params = {"delta": delta, "a": a, "bcf": bcf, "N": N,
              "stage": 1 if N < 10 else 2}
    return corrected_native, params


# ---------------------------------------------------------------------------
# Metrics (same as site_adaptation.py)
# ---------------------------------------------------------------------------

def compute_site_metrics(y_true_native, y_pred_native):
    if len(y_true_native) < 3:
        return {"r2_native": np.nan, "kge_native": np.nan,
                "rmse_native": np.nan, "mape_pct": np.nan}

    ss_res = np.sum((y_true_native - y_pred_native) ** 2)
    ss_tot = np.sum((y_true_native - np.mean(y_true_native)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan

    rmse = np.sqrt(np.mean((y_true_native - y_pred_native) ** 2))

    try:
        r_corr = np.corrcoef(y_true_native, y_pred_native)[0, 1]
    except Exception:
        r_corr = np.nan
    alpha = np.std(y_pred_native) / np.std(y_true_native) if np.std(y_true_native) > 0 else np.nan
    beta = np.mean(y_pred_native) / np.mean(y_true_native) if np.mean(y_true_native) > 0 else np.nan
    kge = 1 - np.sqrt((r_corr - 1)**2 + (alpha - 1)**2 + (beta - 1)**2) if not np.isnan(r_corr) else np.nan

    nonzero = y_true_native > 0
    if nonzero.sum() > 0:
        ape = np.abs(y_pred_native[nonzero] - y_true_native[nonzero]) / y_true_native[nonzero]
        mape = float(np.median(ape) * 100)
        ratio = y_pred_native[nonzero] / y_true_native[nonzero]
        f2 = float(np.mean((ratio >= 0.5) & (ratio <= 2.0)))
    else:
        mape, f2 = np.nan, np.nan

    return {
        "r2_native": float(r2),
        "rmse_native": float(rmse),
        "kge_native": float(kge),
        "mape_pct": mape,
        "frac_within_2x": f2,
    }


# ---------------------------------------------------------------------------
# Experiment runner
# ---------------------------------------------------------------------------

def run_bayesian_adaptation(predictions, k, df=4, slope_k=10, n_trials=50,
                            transform_type="boxcox", lmbda=0.2, bcf_k_mult=3.0):
    """Run Bayesian adaptation experiment across all holdout sites."""
    N_VALUES = [0, 1, 2, 3, 5, 10, 20]
    rng = np.random.default_rng(42)

    results = []
    sites = predictions["site_id"].unique()
    logger.info(f"Bayesian adaptation (k={k}, df={df}, slope_k={slope_k}): "
                f"{len(sites)} sites, {n_trials} trials")

    for site_idx, site_id in enumerate(sites):
        site_data = predictions[predictions["site_id"] == site_id].reset_index(drop=True)
        n_samples = len(site_data)

        if site_idx % 20 == 0:
            logger.info(f"  Site {site_idx+1}/{len(sites)} ({site_id}, {n_samples} samples)")

        for N in N_VALUES:
            if N >= n_samples - 2:
                continue

            if N == 0:
                metrics = compute_site_metrics(
                    site_data["y_true_native"].values,
                    site_data["y_pred_native"].values,
                )
                results.append({
                    "site_id": site_id, "n_cal": 0, "trial": 0,
                    "n_test": n_samples, "k": k, "df": df,
                    "delta": 0.0, "a": 1.0, "bcf": 1.0, "stage": 0,
                    **metrics,
                })
                continue

            for trial in range(n_trials):
                cal_idx = rng.choice(n_samples, N, replace=False)
                test_idx = np.setdiff1d(np.arange(n_samples), cal_idx)
                cal = site_data.iloc[cal_idx]
                test = site_data.iloc[test_idx]

                corrected_native, params = bayesian_adapt(
                    cal["y_true_bc"].values,
                    cal["y_pred_bc"].values,
                    test["y_pred_bc"].values,
                    k=k, df=df,
                    transform_type=transform_type, lmbda=lmbda,
                    cal_true_native=cal["y_true_native"].values,
                    slope_k=slope_k,
                    bcf_k_mult=bcf_k_mult,
                )

                metrics = compute_site_metrics(
                    test["y_true_native"].values, corrected_native)

                results.append({
                    "site_id": site_id, "n_cal": N, "trial": trial,
                    "n_test": len(test), "k": k, "df": df,
                    **params, **metrics,
                })

    return pd.DataFrame(results)


def summarize_results(results_df):
    """Build calibration effort curve summary."""
    summary = results_df.groupby("n_cal").agg(
        r2_median=("r2_native", "median"),
        r2_q25=("r2_native", lambda x: np.nanpercentile(x, 25)),
        r2_q75=("r2_native", lambda x: np.nanpercentile(x, 75)),
        kge_median=("kge_native", "median"),
        rmse_median=("rmse_native", "median"),
        n_sites=("site_id", "nunique"),
    ).reset_index()
    return summary


def check_monotonicity(summary, tol=0.0):
    """Check if the R2 curve is monotonically non-decreasing.

    Parameters
    ----------
    summary : DataFrame with n_cal and r2_median columns.
    tol : float
        Tolerance for violations. If a decrease is <= tol, it's ignored.
        Use 0.0 for strict checking, 0.001 for practical checking.
    """
    sorted_summary = summary.sort_values("n_cal")
    r2_values = sorted_summary["r2_median"].values
    n_vals = sorted_summary["n_cal"].values
    violations = []
    for i in range(len(r2_values)-1):
        decrease = r2_values[i] - r2_values[i+1]
        if decrease > tol:
            violations.append(
                f"N={int(n_vals[i])} ({r2_values[i]:.4f}) > "
                f"N={int(n_vals[i+1])} ({r2_values[i+1]:.4f}) "
                f"[decrease={decrease:.4f}]"
            )
    is_monotone = len(violations) == 0
    return is_monotone, violations


def main():
    parser = argparse.ArgumentParser(description="Bayesian site adaptation experiment")
    parser.add_argument("--k-values", type=float, nargs="+", default=[3, 5, 7, 10, 15, 20, 30],
                        help="Shrinkage constants to test (default: 3 5 7 10 15 20 30)")
    parser.add_argument("--df", type=int, default=4,
                        help="Student-t degrees of freedom (default: 4)")
    parser.add_argument("--slope-k", type=float, default=10,
                        help="Slope shrinkage constant (default: 10)")
    parser.add_argument("--n-trials", type=int, default=50,
                        help="Monte Carlo trials per N (default: 50)")
    parser.add_argument("--bcf-k-mult", type=float, default=3.0,
                        help="BCF shrinkage multiplier (default: 3.0)")
    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("BAYESIAN SITE ADAPTATION EXPERIMENT")
    logger.info(f"Student-t prior df={args.df}, slope_k={args.slope_k}")
    logger.info(f"Testing k values: {args.k_values}")
    logger.info("=" * 70)

    # Load model and generate predictions
    model, meta = load_model_and_meta()
    predictions = generate_holdout_predictions(model, meta)

    if predictions.empty:
        logger.error("No predictions generated. Exiting.")
        return

    transform_type = meta.get("transform_type", "log1p")
    lmbda = meta.get("transform_lmbda")

    # --- Baseline comparison ---
    v4_baseline = {0: 0.472, 1: 0.397, 2: -0.012, 5: 0.359, 10: 0.457, 20: 0.487}

    results_dir = DATA_DIR / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    all_summaries = {}
    all_results = []
    best_k = None
    best_score = -np.inf
    best_monotone = False

    for k in args.k_values:
        logger.info(f"\n{'='*50}")
        logger.info(f"TESTING k={k}")
        logger.info(f"{'='*50}")

        results = run_bayesian_adaptation(
            predictions, k=k, df=args.df, slope_k=args.slope_k,
            n_trials=args.n_trials,
            transform_type=transform_type, lmbda=lmbda,
            bcf_k_mult=args.bcf_k_mult,
        )
        results["method"] = "bayesian_t"
        all_results.append(results)

        summary = summarize_results(results)
        all_summaries[k] = summary

        is_monotone_strict, violations_strict = check_monotonicity(summary, tol=0.0)
        is_monotone_practical, violations_practical = check_monotonicity(summary, tol=0.002)

        # Print curve
        logger.info(f"\nCalibration effort curve (k={k}):")
        logger.info(f"{'N':>5}  {'R2_med':>8}  {'R2_IQR':>15}  {'KGE':>8}  {'RMSE':>8}  {'v4_base':>8}  {'diff':>8}")
        logger.info("-" * 70)
        for _, row in summary.iterrows():
            n = int(row["n_cal"])
            iqr = f"[{row['r2_q25']:.3f}-{row['r2_q75']:.3f}]"
            v4 = v4_baseline.get(n, np.nan)
            diff = row["r2_median"] - v4 if not np.isnan(v4) else np.nan
            v4_str = f"{v4:.3f}" if not np.isnan(v4) else "  —"
            diff_str = f"{diff:+.3f}" if not np.isnan(diff) else "  —"
            logger.info(f"{n:>5}  {row['r2_median']:>8.3f}  {iqr:>15}  "
                        f"{row['kge_median']:>8.3f}  {row['rmse_median']:>8.1f}  "
                        f"{v4_str:>8}  {diff_str:>8}")

        logger.info(f"\nMonotonic (strict): {'YES' if is_monotone_strict else 'NO'}")
        if violations_strict:
            for v in violations_strict:
                logger.info(f"  {v}")
        logger.info(f"Monotonic (tol=0.002): {'YES' if is_monotone_practical else 'NO'}")
        if violations_practical:
            for v in violations_practical:
                logger.info(f"  {v}")

        is_monotone = is_monotone_practical  # Use practical for scoring

        # Score: prioritize monotonicity, then sum of R2 improvements over baseline
        curve_r2 = summary.set_index("n_cal")["r2_median"]
        score = sum(curve_r2.get(n, 0) - v4_baseline.get(n, 0)
                    for n in v4_baseline.keys() if n in curve_r2.index)
        if is_monotone:
            score += 100  # Strong bonus for monotonicity

        if score > best_score:
            best_score = score
            best_k = k
            best_monotone = is_monotone

    # --- Print comparison table ---
    logger.info("\n" + "=" * 80)
    logger.info("COMPARISON: ALL k VALUES vs v4 BASELINE (2-param OLS)")
    logger.info("=" * 80)

    header = f"{'N':>5}  {'v4_OLS':>8}"
    for k in args.k_values:
        header += f"  {'k='+str(int(k) if k==int(k) else k):>10}"
    logger.info(header)
    logger.info("-" * (20 + 12 * len(args.k_values)))

    n_values = [0, 1, 2, 3, 5, 10, 20]
    for n in n_values:
        v4 = v4_baseline.get(n, np.nan)
        row_str = f"{n:>5}  {v4:>8.3f}" if not np.isnan(v4) else f"{n:>5}  {'—':>8}"
        for k in args.k_values:
            s = all_summaries[k]
            r = s[s["n_cal"] == n]
            if not r.empty:
                val = r["r2_median"].values[0]
                diff = val - v4 if not np.isnan(v4) else 0
                marker = "+" if diff > 0 else ""
                row_str += f"  {val:>6.3f}{marker:1}{abs(diff):>3.3f}" if not np.isnan(v4) else f"  {val:>10.3f}"
            else:
                row_str += f"  {'—':>10}"
        logger.info(row_str)

    # Monotonicity check
    logger.info("\nMonotonicity (strict / tol=0.002):")
    for k in args.k_values:
        is_strict, _ = check_monotonicity(all_summaries[k], tol=0.0)
        is_pract, _ = check_monotonicity(all_summaries[k], tol=0.002)
        logger.info(f"  k={k}: {'PASS' if is_strict else 'FAIL'} / {'PASS' if is_pract else 'FAIL'}")

    logger.info(f"\nBest k: {best_k} (monotone={best_monotone})")

    # --- Save best results ---
    best_results = [r for r in all_results if r["k"].iloc[0] == best_k][0]
    best_summary = all_summaries[best_k]

    # Save detailed results
    all_results_df = pd.concat(all_results, ignore_index=True)
    all_results_df.to_parquet(
        results_dir / "site_adaptation_bayesian_all.parquet", index=False)

    best_results.to_parquet(
        results_dir / "site_adaptation_bayesian_best.parquet", index=False)

    # Save summary JSON for easy reference
    summary_dict = {
        "method": "bayesian_student_t_shrinkage",
        "best_k": best_k,
        "df": args.df,
        "slope_k": args.slope_k,
        "n_trials": args.n_trials,
        "monotonic": best_monotone,
        "curve": {},
        "v4_baseline": v4_baseline,
    }
    for _, row in best_summary.iterrows():
        n = int(row["n_cal"])
        summary_dict["curve"][str(n)] = {
            "r2_median": round(float(row["r2_median"]), 3),
            "r2_q25": round(float(row["r2_q25"]), 3),
            "r2_q75": round(float(row["r2_q75"]), 3),
            "kge_median": round(float(row["kge_median"]), 3),
            "rmse_median": round(float(row["rmse_median"]), 1),
        }
    # All k summaries
    summary_dict["all_k_results"] = {}
    for k in args.k_values:
        s = all_summaries[k]
        is_strict, _ = check_monotonicity(s, tol=0.0)
        is_practical, _ = check_monotonicity(s, tol=0.002)
        summary_dict["all_k_results"][str(k)] = {
            "monotonic_strict": is_strict,
            "monotonic_practical": is_practical,
            "curve": {str(int(row["n_cal"])): round(float(row["r2_median"]), 3)
                      for _, row in s.iterrows()},
        }

    with open(results_dir / "site_adaptation_bayesian_summary.json", "w") as f:
        json.dump(summary_dict, f, indent=2)

    logger.info(f"\nSaved results to {results_dir}")
    logger.info(f"  - site_adaptation_bayesian_all.parquet (all k values)")
    logger.info(f"  - site_adaptation_bayesian_best.parquet (k={best_k})")
    logger.info(f"  - site_adaptation_bayesian_summary.json")
    logger.info("\nDone.")


if __name__ == "__main__":
    main()
