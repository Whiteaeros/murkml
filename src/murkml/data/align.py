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

    # Sort continuous by time for efficient lookup
    continuous = continuous.sort_values(continuous_time_col).reset_index(drop=True)

    results = []
    n_matched = 0
    n_missed = 0

    for _, sample in discrete.iterrows():
        sample_time = sample[discrete_time_col]
        lab_value = sample[discrete_value_col]

        # Find nearest continuous reading (primary match)
        time_diffs = (continuous[continuous_time_col] - sample_time).abs()
        nearest_idx = time_diffs.idxmin()
        nearest_gap = time_diffs.loc[nearest_idx]

        if nearest_gap > max_gap:
            n_missed += 1
            continue

        sensor_instant = continuous.loc[nearest_idx, continuous_value_col]

        # Extract ±1hr feature window
        window_mask = (
            (continuous[continuous_time_col] >= sample_time - FEATURE_WINDOW)
            & (continuous[continuous_time_col] <= sample_time + FEATURE_WINDOW)
        )
        window = continuous.loc[window_mask, continuous_value_col]

        # Compute window features
        row = {
            "sample_time": sample_time,
            "lab_value": lab_value,
            "sensor_instant": sensor_instant,
            "match_gap_seconds": nearest_gap.total_seconds(),
        }

        if len(window) > 0:
            row["window_mean"] = window.mean()
            row["window_min"] = window.min()
            row["window_max"] = window.max()
            row["window_std"] = window.std() if len(window) > 1 else 0.0
            row["window_range"] = window.max() - window.min()
            row["window_count"] = len(window)

            # Slope: linear regression of value over time in window
            if len(window) >= 2:
                window_times = continuous.loc[window_mask, continuous_time_col]
                t_seconds = (window_times - window_times.iloc[0]).dt.total_seconds().values
                values = window.values
                if t_seconds[-1] > 0:
                    slope = np.polyfit(t_seconds, values, 1)[0]
                    row["window_slope"] = slope
                else:
                    row["window_slope"] = 0.0
            else:
                row["window_slope"] = 0.0
        else:
            for feat in ["window_mean", "window_min", "window_max", "window_std",
                         "window_range", "window_count", "window_slope"]:
                row[feat] = np.nan

        results.append(row)
        n_matched += 1

    logger.info(
        f"Aligned {n_matched} samples, {n_missed} missed "
        f"(no sensor data within {max_gap})"
    )

    if not results:
        return pd.DataFrame()

    return pd.DataFrame(results)
