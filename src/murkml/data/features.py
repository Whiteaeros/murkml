"""Feature engineering for water quality surrogate modeling.

Computes hydrograph position, antecedent conditions, cross-sensor features,
and seasonality from aligned sensor data. These features were identified as
critical by domain expert review.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def add_hydrograph_features(
    df: pd.DataFrame,
    discharge_col: str = "discharge_instant",
    time_col: str = "sample_time",
    site_col: str = "site_id",
    continuous_dir: str | None = None,
) -> pd.DataFrame:
    """Add hydrograph position + antecedent features from continuous discharge.

    Fix 3: dQ/dt must come from continuous discharge record, NOT diff() on
    sporadic grab samples (which are days/weeks apart — garbage).
    Fix 5: Antecedent features require 7-30 day discharge history.
    Combined per Rivera/Chen: share one continuous-discharge loading function.

    Hydrograph features:
    - discharge_slope_2hr: slope of Q over ±2hr window from continuous record
    - rising_limb: binary from discharge_slope_2hr > 0

    Antecedent features:
    - Q_7day_mean: mean discharge over prior 7 days
    - Q_30day_mean: mean discharge over prior 30 days
    - Q_ratio_7d: current Q / Q_7day_mean
    """
    from pathlib import Path

    df = df.copy()

    if discharge_col not in df.columns or site_col not in df.columns:
        logger.warning(f"No {discharge_col} or {site_col} — skipping hydrograph features")
        df["discharge_slope_2hr"] = np.nan
        df["rising_limb"] = np.nan
        df["Q_7day_mean"] = np.nan
        df["Q_30day_mean"] = np.nan
        df["Q_ratio_7d"] = np.nan
        return df

    if continuous_dir is None:
        continuous_dir = Path(__file__).parent.parent.parent.parent / "data" / "continuous"
    else:
        continuous_dir = Path(continuous_dir)

    # Process each site separately
    results = []
    for site_id, group in df.groupby(site_col):
        group = group.copy()

        # Load continuous discharge for this site
        q_dir = continuous_dir / site_id.replace("-", "_") / "00060"
        q_continuous = None
        if q_dir.exists():
            chunks = []
            for f in sorted(q_dir.glob("*.parquet")):
                chunk = pd.read_parquet(f)
                if len(chunk) > 0:
                    chunks.append(chunk)
            if chunks:
                q_continuous = pd.concat(chunks, ignore_index=True)
                q_continuous = q_continuous.drop_duplicates(subset=["time"]).sort_values("time")
                q_continuous["time"] = pd.to_datetime(q_continuous["time"], utc=True)
                q_continuous["value"] = pd.to_numeric(q_continuous["value"], errors="coerce")
                q_continuous = q_continuous.dropna(subset=["time", "value"])

        if q_continuous is None or len(q_continuous) < 10:
            # No continuous discharge — fill with NaN
            group["discharge_slope_2hr"] = np.nan
            group["rising_limb"] = np.nan
            group["Q_7day_mean"] = np.nan
            group["Q_30day_mean"] = np.nan
            group["Q_ratio_7d"] = np.nan
            results.append(group)
            continue

        q_times = q_continuous["time"].values
        q_values = q_continuous["value"].values

        slopes = []
        q7_means = []
        q30_means = []
        q_ratios = []

        for _, row in group.iterrows():
            t = row[time_col]
            if pd.isna(t):
                slopes.append(np.nan)
                q7_means.append(np.nan)
                q30_means.append(np.nan)
                q_ratios.append(np.nan)
                continue

            t_np = np.datetime64(t)

            # ±2hr window for slope
            window_2hr = (np.abs(q_times - t_np) <= np.timedelta64(2, "h"))
            if window_2hr.sum() >= 2:
                w_vals = q_values[window_2hr]
                w_times = q_times[window_2hr]
                t_seconds = (w_times - w_times[0]).astype("timedelta64[s]").astype(float)
                if t_seconds[-1] > 0:
                    slope = np.polyfit(t_seconds, w_vals, 1)[0]
                else:
                    slope = 0.0
                slopes.append(slope)
            else:
                slopes.append(np.nan)

            # 7-day lookback for antecedent mean
            window_7d = (q_times >= t_np - np.timedelta64(7, "D")) & (q_times <= t_np)
            if window_7d.sum() > 0:
                q7 = q_values[window_7d].mean()
                q7_means.append(q7)
            else:
                q7_means.append(np.nan)

            # 30-day lookback for antecedent mean
            window_30d = (q_times >= t_np - np.timedelta64(30, "D")) & (q_times <= t_np)
            if window_30d.sum() > 0:
                q30 = q_values[window_30d].mean()
                q30_means.append(q30)
            else:
                q30_means.append(np.nan)

            # Q ratio
            q_current = row.get(discharge_col, np.nan)
            q7_val = q7_means[-1]
            if pd.notna(q_current) and pd.notna(q7_val) and q7_val > 0:
                q_ratios.append(q_current / q7_val)
            else:
                q_ratios.append(np.nan)

        group["discharge_slope_2hr"] = slopes
        group["rising_limb"] = (np.array(slopes) > 0).astype(float)
        group.loc[pd.isna(group["discharge_slope_2hr"]), "rising_limb"] = np.nan
        group["Q_7day_mean"] = q7_means
        group["Q_30day_mean"] = q30_means
        group["Q_ratio_7d"] = q_ratios

        results.append(group)

    if results:
        return pd.concat(results, ignore_index=True)
    return df


def add_cross_sensor_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add cross-sensor interaction features.

    Features:
    - turb_Q_ratio: turbidity / discharge (sediment source signal)
    - DO_sat_departure: DO departure from temperature-based saturation
    - SC_turb_interaction: conductance * turbidity (surface runoff dilution)
    """
    df = df.copy()

    # Turbidity / discharge ratio
    if "turbidity_instant" in df.columns and "discharge_instant" in df.columns:
        Q = df["discharge_instant"].replace(0, np.nan)
        df["turb_Q_ratio"] = df["turbidity_instant"] / Q

    # DO departure from saturation
    if "do_instant" in df.columns and "temp_instant" in df.columns:
        # Simplified DO saturation as function of temperature (mg/L)
        do_sat = 14.6 - 0.4 * df["temp_instant"]
        df["DO_sat_departure"] = df["do_instant"] - do_sat

    # Conductance * turbidity interaction
    if "conductance_instant" in df.columns and "turbidity_instant" in df.columns:
        df["SC_turb_interaction"] = df["conductance_instant"] * df["turbidity_instant"]

    return df


def add_seasonality(df: pd.DataFrame, time_col: str = "sample_time") -> pd.DataFrame:
    """Add sin/cos encoded day-of-year for seasonality.

    Uses sin/cos encoding instead of raw DOY so the model doesn't need
    hundreds of splits to learn a smooth seasonal cycle.
    """
    df = df.copy()

    if time_col in df.columns:
        doy = pd.to_datetime(df[time_col]).dt.dayofyear
        df["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
        df["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)

    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all feature engineering steps.

    This is the main entry point for feature engineering.
    Applies in order: hydrograph+antecedent (from continuous), cross-sensor, seasonality.

    Fix 3+5: Hydrograph and antecedent features now computed from continuous
    discharge record, not from diff() on sporadic grab samples.
    """
    df = add_hydrograph_features(df)  # Now includes antecedent features
    df = add_cross_sensor_features(df)
    df = add_seasonality(df)

    # Remove old garbage features if they somehow exist
    for col in ["dQ_dt"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    return df
