"""Temporal alignment of continuous sensor data with discrete grab samples.

For each grab sample at time T, extracts sensor readings and computes
features from a window around T. This is the core data challenge —
pairing 15-minute sensor streams with sporadic lab measurements.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Primary match window: ±15 minutes
PRIMARY_WINDOW = pd.Timedelta(minutes=15)

# Feature window: ±1 hour
FEATURE_WINDOW = pd.Timedelta(hours=1)


def _interpolate_at_times(
    cont_t: np.ndarray, cont_v: np.ndarray,
    sample_t: np.ndarray, max_gap_ns: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized linear interpolation of continuous values at sample times.

    For each sample time, finds flanking continuous readings and interpolates.
    Falls back to nearest if only one side within tolerance. NaN if neither.

    Returns (values, gap_seconds, matched_mask).
    """
    n = len(sample_t)

    # Find indices of flanking readings for all samples at once
    idx_after = np.searchsorted(cont_t, sample_t, side="left")
    idx_before = idx_after - 1

    # Clip to valid range for safe indexing
    idx_before_safe = np.clip(idx_before, 0, len(cont_t) - 1)
    idx_after_safe = np.clip(idx_after, 0, len(cont_t) - 1)

    # Compute time gaps (in nanoseconds) to flanking readings
    gap_before = np.abs((cont_t[idx_before_safe] - sample_t).astype(np.int64))
    gap_after = np.abs((cont_t[idx_after_safe] - sample_t).astype(np.int64))

    # Mark which sides are valid (within tolerance AND within array bounds)
    has_before = (idx_before >= 0) & (gap_before <= max_gap_ns)
    has_after = (idx_after < len(cont_t)) & (gap_after <= max_gap_ns)

    # Get flanking values
    v_before = cont_v[idx_before_safe]
    v_after = cont_v[idx_after_safe]
    t_before = cont_t[idx_before_safe]
    t_after = cont_t[idx_after_safe]

    # Compute interpolation fraction
    span = (t_after - t_before).astype(np.float64)
    elapsed = (sample_t - t_before).astype(np.float64)
    # Avoid division by zero
    safe_span = np.where(span > 0, span, 1.0)
    frac = elapsed / safe_span
    frac = np.clip(frac, 0.0, 1.0)

    # Interpolated values
    interp = v_before + (v_after - v_before) * frac

    # Build result: prefer interpolation, fall back to single side
    both = has_before & has_after
    only_before = has_before & ~has_after
    only_after = ~has_before & has_after
    neither = ~has_before & ~has_after

    values = np.where(both, interp,
             np.where(only_before, v_before,
             np.where(only_after, v_after, np.nan)))

    gaps = np.where(both, np.maximum(gap_before, gap_after) / 1e9,
           np.where(only_before, gap_before / 1e9,
           np.where(only_after, gap_after / 1e9, np.nan)))

    matched = ~neither

    return values, gaps, matched


def align_samples(
    continuous: pd.DataFrame,
    discrete: pd.DataFrame,
    continuous_time_col: str = "datetime",
    continuous_value_col: str = "value",
    discrete_time_col: str = "datetime",
    discrete_value_col: str = "value",
    max_gap: pd.Timedelta = PRIMARY_WINDOW,
) -> pd.DataFrame:
    """Match each discrete grab sample to the nearest continuous sensor reading.

    For each grab sample timestamp T:
    1. Find nearest continuous reading within ±15 min (primary match)
    2. Extract sensor readings in ±1hr window for feature computation
    3. Compute window statistics (mean, min, max, std, slope)

    Args:
        continuous: Continuous sensor data with datetime and value columns.
        discrete: Discrete grab sample data with datetime and value columns.
        continuous_time_col: Datetime column in continuous data.
        continuous_value_col: Value column in continuous data.
        discrete_time_col: Datetime column in discrete data.
        discrete_value_col: Value column in discrete data.
        max_gap: Maximum time gap for primary match.

    Returns:
        DataFrame with one row per matched grab sample, containing:
        - lab_value: the discrete measurement
        - sensor_instant: nearest continuous reading
        - window features (mean, min, max, std, slope)
        - match_gap_seconds: time difference of primary match
    """
    if continuous.empty or discrete.empty:
        logger.warning("Empty input data — cannot align")
        return pd.DataFrame()

    # Ensure datetime columns are proper timestamps in UTC
    continuous = continuous.copy()
    discrete = discrete.copy()
    continuous[continuous_time_col] = pd.to_datetime(continuous[continuous_time_col], utc=True)
    discrete[discrete_time_col] = pd.to_datetime(discrete[discrete_time_col], utc=True)

    # Sort both by time for merge_asof
    continuous = continuous.sort_values(continuous_time_col).reset_index(drop=True)
    discrete = discrete.sort_values(discrete_time_col).reset_index(drop=True)

    # --- Primary match: linear interpolation between flanking readings ---
    # Vectorized: uses searchsorted + numpy array ops instead of Python loop.
    cont_t = continuous[continuous_time_col].values  # sorted datetime64[ns]
    cont_v = continuous[continuous_value_col].values
    sample_t = discrete[discrete_time_col].values
    max_gap_ns = max_gap.value  # nanoseconds

    interp_values, interp_gaps, interp_matched = _interpolate_at_times(
        cont_t, cont_v, sample_t, max_gap_ns
    )

    # Build matched DataFrame
    disc_lab = discrete[discrete_value_col].values
    matched_mask = interp_matched
    n_matched = matched_mask.sum()
    n_missed = len(discrete) - n_matched

    if n_matched == 0:
        logger.info(
            f"Aligned 0 samples, {n_missed} missed "
            f"(no sensor data within {max_gap})"
        )
        return pd.DataFrame()

    # Filter to matched only
    m_sample_times = sample_t[matched_mask]
    m_lab_values = disc_lab[matched_mask]
    m_interp_values = interp_values[matched_mask]
    m_gaps = interp_gaps[matched_mask]

    # --- Window features: ±1hr stats using searchsorted ---
    cont_times = cont_t  # already sorted numpy datetime64
    cont_values = cont_v
    sample_times = m_sample_times

    fw_ns = FEATURE_WINDOW.value  # nanoseconds
    lo_indices = np.searchsorted(cont_times, sample_times - fw_ns, side="left")
    hi_indices = np.searchsorted(cont_times, sample_times + fw_ns, side="right")

    w_means = np.empty(n_matched)
    w_mins = np.empty(n_matched)
    w_maxs = np.empty(n_matched)
    w_stds = np.empty(n_matched)
    w_ranges = np.empty(n_matched)
    w_counts = np.empty(n_matched, dtype=int)
    w_slopes = np.empty(n_matched)

    for i in range(n_matched):
        lo, hi = lo_indices[i], hi_indices[i]
        if hi > lo:
            wv = cont_values[lo:hi]
            w_means[i] = wv.mean()
            w_mins[i] = wv.min()
            w_maxs[i] = wv.max()
            w_stds[i] = wv.std() if len(wv) > 1 else 0.0
            w_ranges[i] = wv.max() - wv.min()
            w_counts[i] = len(wv)
            if len(wv) >= 2:
                wt = cont_times[lo:hi]
                t_sec = (wt - wt[0]).astype("timedelta64[s]").astype(float)
                if t_sec[-1] > 0:
                    w_slopes[i] = np.polyfit(t_sec, wv, 1)[0]
                else:
                    w_slopes[i] = 0.0
            else:
                w_slopes[i] = 0.0
        else:
            w_means[i] = w_mins[i] = w_maxs[i] = w_stds[i] = np.nan
            w_ranges[i] = np.nan
            w_counts[i] = 0
            w_slopes[i] = np.nan

    result = pd.DataFrame({
        "sample_time": m_sample_times,
        "lab_value": m_lab_values,
        "sensor_instant": m_interp_values,
        "match_gap_seconds": m_gaps,
        "window_mean": w_means,
        "window_min": w_mins,
        "window_max": w_maxs,
        "window_std": w_stds,
        "window_range": w_ranges,
        "window_count": w_counts,
        "window_slope": w_slopes,
    })

    logger.info(
        f"Aligned {n_matched} samples, {n_missed} missed "
        f"(no sensor data within {max_gap})"
    )

    return result
