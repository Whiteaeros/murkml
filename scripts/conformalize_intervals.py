"""Conformal Quantile Regression (CQR) for murkml prediction intervals.

Uses LOGO CV out-of-fold quantile predictions to calibrate prediction intervals
with distribution-free coverage guarantees (Romano et al. 2019, NeurIPS).

All conformalization is done in Box-Cox space (lambda=0.2). Interval endpoints
are back-transformed to native mg/L only at the final step. This preserves
coverage probability because Box-Cox is a monotone transform.

Usage:
    python scripts/conformalize_intervals.py
    python scripts/conformalize_intervals.py --alpha 0.10  # 90% intervals (default)
    python scripts/conformalize_intervals.py --alpha 0.05  # 95% intervals
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from math import ceil
from pathlib import Path

import numpy as np
import pandas as pd

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
RESULTS_DIR = DATA_DIR / "results"


def load_logo_quantile_predictions() -> pd.DataFrame:
    """Load LOGO CV out-of-fold predictions with quantile columns."""
    path = RESULTS_DIR / "logo_predictions_ssc_C_sensor_basic_watershed.parquet"
    df = pd.read_parquet(path)
    logger.info(f"Loaded LOGO predictions: {len(df)} rows, {df['site_id'].nunique()} sites")

    # Verify quantile columns exist
    required = ["q05_ms", "q95_ms"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"Missing quantile columns: {missing}. "
            "Was the model trained with --quantile flag?"
        )
    return df


def compute_conformity_scores(
    df: pd.DataFrame,
    alpha_lo_col: str = "q05_ms",
    alpha_hi_col: str = "q95_ms",
    y_true_col: str = "y_true_log",
) -> np.ndarray:
    """Compute CQR conformity scores in Box-Cox space.

    Score_i = max(q_lo_i - y_i, y_i - q_hi_i)
    Positive when y falls outside the interval, zero/negative when inside.

    Per Romano et al. 2019, Section 2.2.
    """
    q_lo = df[alpha_lo_col].values
    q_hi = df[alpha_hi_col].values
    y_true = df[y_true_col].values

    scores = np.maximum(q_lo - y_true, y_true - q_hi)
    logger.info(
        f"Conformity scores: median={np.median(scores):.4f}, "
        f"mean={np.mean(scores):.4f}, "
        f"frac_inside={np.mean(scores <= 0):.3f} "
        f"(raw coverage before adjustment)"
    )
    return scores


def compute_q_hat(scores: np.ndarray, alpha: float) -> float:
    """Compute the conformal adjustment threshold Q_hat.

    Q_hat is the ceil((n+1)(1-alpha))/(n+1) quantile of conformity scores.
    Adding Q_hat to upper bound and subtracting from lower bound guarantees
    marginal coverage >= 1-alpha.

    Per Romano et al. 2019, Equation (6).
    """
    n = len(scores)
    # The exact finite-sample quantile level
    quantile_level = ceil((n + 1) * (1 - alpha)) / n
    quantile_level = min(quantile_level, 1.0)  # cap at 1.0

    q_hat = float(np.quantile(scores, quantile_level))
    logger.info(
        f"Q_hat (alpha={alpha}): {q_hat:.4f} "
        f"(quantile level={quantile_level:.6f}, n={n})"
    )
    return q_hat


def conformalize_and_evaluate(
    df: pd.DataFrame,
    q_hat: float,
    alpha: float,
    lmbda: float = 0.2,
    alpha_lo_col: str = "q05_ms",
    alpha_hi_col: str = "q95_ms",
) -> dict:
    """Apply conformal adjustment and evaluate coverage.

    1. Adjust interval in Box-Cox space: [q_lo - Q_hat, q_hi + Q_hat]
    2. Back-transform endpoints to native mg/L
    3. Compute coverage and interval width metrics
    """
    q_lo_bc = df[alpha_lo_col].values - q_hat
    q_hi_bc = df[alpha_hi_col].values + q_hat
    y_true_bc = df["y_true_log"].values

    # Coverage in Box-Cox space (should match native-space coverage)
    coverage_bc = np.mean((y_true_bc >= q_lo_bc) & (y_true_bc <= q_hi_bc))

    # Back-transform to native mg/L (BCF=1.0 — quantile bounds, not means)
    lower_native = np.clip(safe_inv_boxcox1p(q_lo_bc, lmbda), 0, None)
    upper_native = safe_inv_boxcox1p(q_hi_bc, lmbda)
    y_true_native = df["y_true_native_mgL"].values

    # Coverage in native space
    coverage_native = np.mean(
        (y_true_native >= lower_native) & (y_true_native <= upper_native)
    )

    # Interval width
    width_native = upper_native - lower_native
    width_ratio = width_native / np.clip(y_true_native, 1e-6, None)

    results = {
        "alpha": alpha,
        "target_coverage": 1 - alpha,
        "q_hat": q_hat,
        "coverage_bc_space": float(coverage_bc),
        "coverage_native_space": float(coverage_native),
        "n_samples": len(df),
        "n_sites": df["site_id"].nunique(),
        "median_width_native_mgL": float(np.median(width_native)),
        "mean_width_native_mgL": float(np.mean(width_native)),
        "median_width_ratio": float(np.median(width_ratio)),
        "mean_width_ratio": float(np.mean(width_ratio)),
        "frac_zero_width": float(np.mean(width_native < 0.01)),
    }

    logger.info(
        f"Coverage: {coverage_native:.3f} (target {1-alpha:.2f}) | "
        f"Median width: {np.median(width_native):.1f} mg/L | "
        f"Median width ratio: {np.median(width_ratio):.2f}x"
    )

    return results, lower_native, upper_native


def conditional_coverage(
    df: pd.DataFrame,
    lower: np.ndarray,
    upper: np.ndarray,
    group_col: str,
) -> dict:
    """Compute coverage within subgroups (Mondrian-style diagnostic)."""
    y_true = df["y_true_native_mgL"].values
    inside = (y_true >= lower) & (y_true <= upper)

    groups = df[group_col].values
    result = {}
    for g in sorted(set(groups)):
        if pd.isna(g):
            continue
        mask = groups == g
        n = mask.sum()
        if n < 10:
            continue
        cov = float(np.mean(inside[mask]))
        result[str(g)] = {"coverage": cov, "n": int(n)}

    return result


def main():
    parser = argparse.ArgumentParser(description="CQR conformalization for murkml")
    parser.add_argument("--alpha", type=float, default=0.10,
                        help="Miscoverage rate (0.10 = 90%% intervals, 0.05 = 95%%)")
    parser.add_argument("--lmbda", type=float, default=0.2,
                        help="Box-Cox lambda")
    parser.add_argument("--output-dir", type=str,
                        default=str(RESULTS_DIR / "evaluations" / "cqr_intervals"))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Load LOGO CV quantile predictions
    df = load_logo_quantile_predictions()

    # Determine which quantile columns to use for the requested alpha
    # For alpha=0.10 (90% interval): use q05 and q95
    # For alpha=0.05 (95% interval): use q05 and q95 (same bounds, different conformal adjustment)
    alpha_lo_col = "q05_ms"
    alpha_hi_col = "q95_ms"
    logger.info(f"Using bounds: {alpha_lo_col} and {alpha_hi_col}")

    # Step 2: Compute conformity scores in Box-Cox space
    scores = compute_conformity_scores(df, alpha_lo_col, alpha_hi_col)

    # Step 3: Compute Q_hat (conformal adjustment threshold)
    q_hat = compute_q_hat(scores, args.alpha)

    # Step 4: Apply adjustment and evaluate on the same LOGO data
    # (This is the calibration set — coverage should be >= 1-alpha by construction)
    logger.info("\n--- LOGO CV (calibration set) ---")
    cal_results, cal_lower, cal_upper = conformalize_and_evaluate(
        df, q_hat, args.alpha, args.lmbda, alpha_lo_col, alpha_hi_col
    )

    # Step 5: Conditional coverage by SSC tier
    df["ssc_tier"] = pd.cut(
        df["y_true_native_mgL"],
        bins=[0, 50, 500, 5000, 1e6],
        labels=["Low <50", "Med 50-500", "High 500-5K", "Extreme >5K"],
    )
    cond_ssc = conditional_coverage(df, cal_lower, cal_upper, "ssc_tier")
    logger.info("Conditional coverage by SSC tier:")
    for tier, stats in cond_ssc.items():
        logger.info(f"  {tier}: {stats['coverage']:.3f} (n={stats['n']})")

    # Step 6: Save results
    summary = {
        "method": "CQR (Romano et al. 2019)",
        "conformity_score": "max(q_lo - y, y - q_hi) in Box-Cox space",
        "back_transform": f"inv_boxcox(endpoints, lambda={args.lmbda})",
        "bcf_applied": "1.0 (no BCF for quantile bounds)",
        "calibration": cal_results,
        "conditional_coverage_ssc_tier": cond_ssc,
    }

    with open(output_dir / "cqr_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    # Save per-sample intervals
    df["lower_native_mgL"] = cal_lower
    df["upper_native_mgL"] = cal_upper
    df["width_native_mgL"] = cal_upper - cal_lower
    df.to_parquet(output_dir / "cqr_per_sample.parquet", index=False)

    logger.info(f"\nSaved to {output_dir}/")
    logger.info(f"  cqr_summary.json — coverage metrics and Q_hat")
    logger.info(f"  cqr_per_sample.parquet — per-sample intervals")

    # Print summary
    print(f"\n{'='*60}")
    print(f"CQR SUMMARY (alpha={args.alpha}, {(1-args.alpha)*100:.0f}% intervals)")
    print(f"{'='*60}")
    print(f"Q_hat (conformal adjustment): {q_hat:.4f} (Box-Cox units)")
    print(f"Coverage (LOGO calibration):  {cal_results['coverage_native_space']:.3f}")
    print(f"Median interval width:        {cal_results['median_width_native_mgL']:.1f} mg/L")
    print(f"Median width ratio:           {cal_results['median_width_ratio']:.2f}x true value")
    print(f"Samples: {cal_results['n_samples']}, Sites: {cal_results['n_sites']}")
    print(f"\nConditional coverage by SSC tier:")
    for tier, stats in cond_ssc.items():
        flag = " !!!" if stats["coverage"] < (1 - args.alpha - 0.05) else ""
        print(f"  {tier:15s}: {stats['coverage']:.3f} (n={stats['n']}){flag}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
