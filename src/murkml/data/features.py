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
    continuous_discharge: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add hydrograph position features critical for sediment prediction.

    Features:
    - dQ_dt: rate of change of discharge (rising vs falling limb)
    - rising_limb: binary indicator (1 = rising, 0 = falling)
    - Q_ratio_peak: current Q / recent peak Q

    These capture the hysteresis in turbidity-SSC relationships that
    all three reviewers flagged as critical.
    """
    df = df.copy()

    if discharge_col not in df.columns:
        logger.warning(f"No {discharge_col} column — skipping hydrograph features")
        return df

    # Simple dQ/dt from the aligned data
    # For proper implementation, we need the full continuous discharge record
    # For now, use what's available in the aligned features
    df["dQ_dt"] = df[discharge_col].diff() / df[time_col].diff().dt.total_seconds()
    df["rising_limb"] = (df["dQ_dt"] > 0).astype(int)

    return df


def add_antecedent_features(
    df: pd.DataFrame,
    discharge_col: str = "discharge_instant",
) -> pd.DataFrame:
    """Add antecedent condition features.

    Features:
    - Q_7day_cumulative: 7-day cumulative discharge (wetness proxy)
    - Q_30day_cumulative: 30-day cumulative discharge (supply exhaustion)
    - days_since_high_flow: days since last Q > Q75 event

    These capture supply exhaustion / first-flush effects on 7-30 day
    timescales (domain scientist flagged 24hr as too short).
    """
    df = df.copy()
    # Placeholder — requires full continuous discharge record
    # Will be implemented when we have the data pipeline producing
    # site-level continuous data alongside aligned samples
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
    Applies in order: hydrograph, antecedent, cross-sensor, seasonality.
    """
    df = add_hydrograph_features(df)
    df = add_antecedent_features(df)
    df = add_cross_sensor_features(df)
    df = add_seasonality(df)
    return df
