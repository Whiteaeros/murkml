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


def kge(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    return_components: bool = False,
) -> float | dict:
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
    composite = 1 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2)
    if return_components:
        return {"kge": composite, "kge_r": r, "kge_alpha": alpha, "kge_beta": beta}
    return composite


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


def stratified_metrics_by_flow(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    discharge: np.ndarray,
    site_ids: np.ndarray,
    quantiles: tuple[float, ...] = (0.5, 0.9),
) -> dict[str, dict]:
    """Compute metrics stratified by discharge percentile bins.

    Percentiles computed per-site (Rivera: Q90 at a desert site is 5 cfs,
    at the Missouri River it's 50,000 cfs).

    Returns dict keyed by bin label with sub-dicts of metrics + sample counts.
    """
    valid = ~np.isnan(discharge)
    y_true = np.asarray(y_true)[valid]
    y_pred = np.asarray(y_pred)[valid]
    discharge = np.asarray(discharge)[valid]
    site_ids = np.asarray(site_ids)[valid]

    # Compute per-site discharge percentiles
    bin_labels = np.empty(len(discharge), dtype=object)
    for site in np.unique(site_ids):
        mask = site_ids == site
        site_q = discharge[mask]
        thresholds = [np.quantile(site_q, q) for q in quantiles]
        for i in range(len(mask)):
            if not mask[i]:
                continue
            val = discharge[i]
            if val < thresholds[0]:
                bin_labels[i] = f"Q<{int(quantiles[0]*100)}"
            elif len(thresholds) > 1 and val < thresholds[1]:
                bin_labels[i] = f"Q{int(quantiles[0]*100)}-{int(quantiles[1]*100)}"
            else:
                bin_labels[i] = f"Q>{int(quantiles[-1]*100)}"

    results = {}
    for label in sorted(set(bin_labels)):
        mask = bin_labels == label
        n = mask.sum()
        if n < 5:
            results[label] = {"r2": np.nan, "kge": np.nan, "rmse": np.nan, "n_samples": int(n)}
            continue
        results[label] = {
            "r2": r_squared(y_true[mask], y_pred[mask]),
            "kge": kge(y_true[mask], y_pred[mask]),
            "rmse": rmse(y_true[mask], y_pred[mask]),
            "n_samples": int(n),
        }
    return results


def threshold_fractions(
    values: np.ndarray,
    thresholds: dict[str, float] | None = None,
    n_bootstrap: int = 1000,
) -> dict[str, dict]:
    """Compute fraction of values above/below thresholds with bootstrap CIs.

    Returns dict like {'r2_gt_0.5': {'fraction': 0.65, 'ci_lower': 0.48, 'ci_upper': 0.80}}.
    """
    if thresholds is None:
        thresholds = {"r2_gt_0.5": 0.5, "r2_gt_0": 0.0}

    values = np.asarray(values)
    n = len(values)
    results = {}
    rng = np.random.default_rng(42)

    for name, thresh in thresholds.items():
        if "lt" in name:
            frac = np.mean(values < thresh)
        else:
            frac = np.mean(values >= thresh)

        # Bootstrap 95% CI
        boot_fracs = []
        for _ in range(n_bootstrap):
            sample = rng.choice(values, size=n, replace=True)
            if "lt" in name:
                boot_fracs.append(np.mean(sample < thresh))
            else:
                boot_fracs.append(np.mean(sample >= thresh))

        ci_lower = np.percentile(boot_fracs, 2.5)
        ci_upper = np.percentile(boot_fracs, 97.5)

        results[name] = {"fraction": float(frac), "ci_lower": float(ci_lower), "ci_upper": float(ci_upper)}
    return results


def duan_smearing_factor(
    y_true_log: np.ndarray,
    y_pred_log: np.ndarray,
) -> float:
    """Compute Duan's (1983) smearing estimate bias correction factor.

    When predictions are made in log-space and back-transformed via exp(),
    the result estimates the conditional median, not the conditional mean.
    For right-skewed distributions (like SSC), this systematically
    underpredicts. The smearing factor corrects for this.

    BCF = mean(exp(residuals)) where residuals = y_true_log - y_pred_log

    Typical values are 1.05-1.30. Values above 2.0 suggest poor model fit
    or heavy-tailed residuals.
    """
    residuals = np.asarray(y_true_log) - np.asarray(y_pred_log)
    return float(np.mean(np.exp(residuals)))


def native_space_metrics(
    y_true_log: np.ndarray,
    y_pred_log: np.ndarray,
    smearing_factor: float = 1.0,
) -> dict:
    """Back-transform log1p predictions and compute native-space R² and RMSE (mg/L).

    If smearing_factor > 1.0, applies Duan's (1983) bias correction to
    the back-transformed predictions. Pass the factor from
    duan_smearing_factor() computed on training residuals.
    """
    y_true_native = np.expm1(np.asarray(y_true_log))
    y_pred_native = np.expm1(np.asarray(y_pred_log)) * smearing_factor
    return {
        "r2_native": r_squared(y_true_native, y_pred_native),
        "rmse_native_mgL": rmse(y_true_native, y_pred_native),
        "pbias_native": percent_bias(y_true_native, y_pred_native),
        "smearing_factor": smearing_factor,
    }


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
    kge_result = kge(y_true, y_pred, return_components=True)
    results = {
        "r2": r_squared(y_true, y_pred),
        "rmse": rmse(y_true, y_pred),
        "kge": kge_result["kge"],
        "kge_r": kge_result["kge_r"],
        "kge_alpha": kge_result["kge_alpha"],
        "kge_beta": kge_result["kge_beta"],
        "percent_bias": percent_bias(y_true, y_pred),
        "n_samples": len(y_true),
    }

    if discharge is not None:
        results["load_bias"] = load_bias(y_true, y_pred, discharge)
        results["storm_rmse_q90"] = storm_rmse(y_true, y_pred, discharge, 0.9)

    if y_lower is not None and y_upper is not None:
        results["picp_90"] = prediction_interval_coverage(y_true, y_lower, y_upper)

    return results
