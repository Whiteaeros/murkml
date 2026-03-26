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

    # --- Primary match: nearest continuous reading within ±max_gap ---
    merged = pd.merge_asof(
        discrete.rename(columns={discrete_time_col: "_sample_time", discrete_value_col: "_lab_value"}),
        continuous.rename(columns={continuous_time_col: "_cont_time", continuous_value_col: "_cont_value"}),
        left_on="_sample_time",
        right_on="_cont_time",
        direction="nearest",
        tolerance=max_gap,
    )

    # Drop unmatched samples
    matched = merged[merged["_cont_time"].notna()].copy()
    n_matched = len(matched)
    n_missed = len(discrete) - n_matched

    if n_matched == 0:
        logger.info(
            f"Aligned 0 samples, {n_missed} missed "
            f"(no sensor data within {max_gap})"
        )
        return pd.DataFrame()

    matched["match_gap_seconds"] = (
        (matched["_sample_time"] - matched["_cont_time"]).abs().dt.total_seconds()
    )

    # --- Window features: ±1hr stats using searchsorted ---
    cont_times = continuous[continuous_time_col].values  # sorted numpy datetime64
    cont_values = continuous[continuous_value_col].values
    sample_times = matched["_sample_time"].values

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
        "sample_time": matched["_sample_time"].values,
        "lab_value": matched["_lab_value"].values,
        "sensor_instant": matched["_cont_value"].values,
        "match_gap_seconds": matched["match_gap_seconds"].values,
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
