"""Evaluation metrics for water quality surrogate models.

Includes standard metrics (R2, RMSE) and hydrology-specific metrics
(KGE, load bias, storm-period RMSE, prediction interval coverage).
"""

from __future__ import annotations

import numpy as np


def r_squared(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Coefficient of determination (R2)."""
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - y_true.mean()) ** 2)
    return 1 - ss_res / max(ss_tot, 1e-10)


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Root mean squared error."""
    return np.sqrt(np.mean((y_true - y_pred) ** 2))


def kge(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Kling-Gupta Efficiency.

    Replacing NSE as the hydrology standard. Decomposes into:
    - r: correlation
    - alpha: variability ratio (std_pred / std_obs)
    - beta: bias ratio (mean_pred / mean_obs)

    KGE = 1 - sqrt((r-1)^2 + (alpha-1)^2 + (beta-1)^2)
    """
    r = np.corrcoef(y_true, y_pred)[0, 1] if len(y_true) > 1 else 0.0
    alpha = np.std(y_pred) / max(np.std(y_true), 1e-10)
    beta = np.mean(y_pred) / max(np.mean(y_true), 1e-10)
    return 1 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2)


def percent_bias(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Percent bias: positive = overprediction, negative = underprediction."""
    return 100 * np.sum(y_pred - y_true) / max(np.sum(y_true), 1e-10)


def load_bias(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    discharge: np.ndarray,
) -> float:
    """Load bias: % error in total load (concentration * discharge).

    Slight underprediction at peak flow = massive load error.
    """
    load_true = np.sum(y_true * discharge)
    load_pred = np.sum(y_pred * discharge)
    return 100 * (load_pred - load_true) / max(load_true, 1e-10)


def storm_rmse(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    discharge: np.ndarray,
    threshold_quantile: float = 0.9,
) -> float:
    """RMSE conditioned on high-flow events (above discharge percentile).

    This is where 90% of sediment load occurs and where model
    performance matters most.
    """
    threshold = np.quantile(discharge, threshold_quantile)
    mask = discharge >= threshold
    if mask.sum() == 0:
        return np.nan
    return rmse(y_true[mask], y_pred[mask])


def prediction_interval_coverage(
    y_true: np.ndarray,
    y_lower: np.ndarray,
    y_upper: np.ndarray,
) -> float:
    """Prediction Interval Coverage Probability (PICP).

    Fraction of observations falling within the prediction interval.
    A well-calibrated 90% interval should cover ~90% of observations.
    """
    covered = np.sum((y_true >= y_lower) & (y_true <= y_upper))
    return covered / max(len(y_true), 1)


def compute_all_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    discharge: np.ndarray | None = None,
    y_lower: np.ndarray | None = None,
    y_upper: np.ndarray | None = None,
) -> dict:
    """Compute all evaluation metrics.

    Returns a dict with all metric values.
    """
    results = {
        "r2": r_squared(y_true, y_pred),
        "rmse": rmse(y_true, y_pred),
        "kge": kge(y_true, y_pred),
        "percent_bias": percent_bias(y_true, y_pred),
        "n_samples": len(y_true),
    }

    if discharge is not None:
        results["load_bias"] = load_bias(y_true, y_pred, discharge)
        results["storm_rmse_q90"] = storm_rmse(y_true, y_pred, discharge, 0.9)

    if y_lower is not None and y_upper is not None:
        results["picp_90"] = prediction_interval_coverage(y_true, y_lower, y_upper)

    return results
