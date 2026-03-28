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

    # DO departure from saturation (Benson & Krause 1984 polynomial)
    if "do_instant" in df.columns and "temp_instant" in df.columns:
        T = df["temp_instant"].clip(0, 40)  # guard against extreme values
        # Benson & Krause 1984 equation for DO saturation at 1 atm (mg/L)
        # ln(C*) = -139.34411 + (1.575701e5/T) - (6.642308e7/T^2)
        #        + (1.2438e10/T^3) - (8.621949e11/T^4)
        # where T is in Kelvin
        Tk = T + 273.15
        ln_sat = (
            -139.34411
            + 1.575701e5 / Tk
            - 6.642308e7 / Tk**2
            + 1.243800e10 / Tk**3
            - 8.621949e11 / Tk**4
        )
        do_sat = np.exp(ln_sat)
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


def add_weather_features(
    df: pd.DataFrame,
    site_col: str = "site_id",
    time_col: str = "sample_time",
    weather_dir: str | None = None,
) -> pd.DataFrame:
    """Add antecedent precipitation and temperature features from GridMET daily data.

    For each sample, computes rolling precipitation sums and temperature at sample time
    by matching to the site's daily weather record.

    Features added:
    - precip_24h: cumulative precip in prior 24 hours (1 day)
    - precip_48h: cumulative precip in prior 48 hours (2 days)
    - precip_7d: cumulative precip in prior 7 days
    - precip_30d: cumulative precip in prior 30 days
    - days_since_rain: days since last precip > 1mm
    - temp_at_sample: daily mean temp on sample day (snowmelt proxy)

    Data source: data/weather/USGS_{site_no}/daily_weather.parquet
    Format: date (datetime64), precip_mm (float32), tmax_c, tmin_c, tmean_c (float32)
    """
    from pathlib import Path

    df = df.copy()

    if weather_dir is None:
        weather_dir = Path(__file__).parent.parent.parent.parent / "data" / "weather"
    else:
        weather_dir = Path(weather_dir)

    if not weather_dir.exists():
        logger.warning(f"Weather directory not found: {weather_dir} — skipping weather features")
        for col in ["precip_24h", "precip_48h", "precip_7d", "precip_30d",
                     "days_since_rain", "temp_at_sample"]:
            df[col] = np.nan
        return df

    # Initialize columns
    for col in ["precip_24h", "precip_48h", "precip_7d", "precip_30d",
                 "days_since_rain", "temp_at_sample"]:
        df[col] = np.nan

    n_sites_with_weather = 0
    n_sites_without = 0

    for site_id in df[site_col].unique():
        site_mask = df[site_col] == site_id
        # Convert site_id format: USGS-01036390 → USGS_01036390
        site_dir_name = site_id.replace("-", "_")
        weather_file = weather_dir / site_dir_name / "daily_weather.parquet"

        if not weather_file.exists():
            n_sites_without += 1
            continue

        weather = pd.read_parquet(weather_file)
        if weather.empty or "precip_mm" not in weather.columns:
            n_sites_without += 1
            continue

        n_sites_with_weather += 1

        # Ensure date column is datetime and sorted
        weather["date"] = pd.to_datetime(weather["date"])
        weather = weather.sort_values("date").reset_index(drop=True)

        # Precompute rolling sums on the daily weather data
        # ALL windows use .shift(1) to be strictly antecedent (prior days only)
        # This avoids temporal leakage from same-day precipitation
        weather["precip_1d"] = weather["precip_mm"].shift(1)  # yesterday's precip
        weather["precip_2d"] = weather["precip_mm"].shift(1).rolling(2, min_periods=1).sum()  # prior 2 days
        weather["precip_7d_roll"] = weather["precip_mm"].shift(1).rolling(7, min_periods=1).sum()  # prior 7 days
        weather["precip_30d_roll"] = weather["precip_mm"].shift(1).rolling(30, min_periods=1).sum()  # prior 30 days

        # Days since rain (>1mm threshold)
        rain_days = weather["precip_mm"] > 1.0
        # For each row, find how many days since last rain
        days_since = pd.Series(np.nan, index=weather.index)
        last_rain_idx = -1
        for i in range(len(weather)):
            if rain_days.iloc[i]:
                last_rain_idx = i
                days_since.iloc[i] = 0
            elif last_rain_idx >= 0:
                days_since.iloc[i] = i - last_rain_idx
        weather["days_since_rain_val"] = days_since

        # Build a date-indexed lookup for fast matching
        weather_indexed = weather.set_index("date")

        # Match each sample to its weather date
        # Strip timezone from sample times to match tz-naive weather dates
        site_times = pd.to_datetime(df.loc[site_mask, time_col])
        sample_dates = site_times.dt.tz_localize(None).dt.normalize()  # strip tz + time, keep date only

        for col_src, col_dst in [
            ("precip_1d", "precip_24h"),
            ("precip_2d", "precip_48h"),
            ("precip_7d_roll", "precip_7d"),
            ("precip_30d_roll", "precip_30d"),
            ("days_since_rain_val", "days_since_rain"),
            ("tmean_c", "temp_at_sample"),
        ]:
            if col_src not in weather_indexed.columns:
                continue
            # Use reindex to match sample dates to weather dates
            matched = weather_indexed[col_src].reindex(sample_dates.values)
            df.loc[site_mask, col_dst] = matched.values

    logger.info(
        f"Weather features: {n_sites_with_weather} sites matched, "
        f"{n_sites_without} sites without weather data"
    )

    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all feature engineering steps.

    This is the main entry point for feature engineering.
    Applies in order: hydrograph+antecedent (from continuous), cross-sensor, seasonality, weather.

    Fix 3+5: Hydrograph and antecedent features now computed from continuous
    discharge record, not from diff() on sporadic grab samples.
    """
    df = add_hydrograph_features(df)  # Now includes antecedent features
    df = add_cross_sensor_features(df)
    df = add_seasonality(df)
    df = add_weather_features(df)

    # Log-transformed features (power-law relationships are linear in log space)
    if "turbidity_instant" in df.columns:
        df["log_turbidity_instant"] = np.log1p(df["turbidity_instant"].clip(lower=0))

    # Sensor range flags
    if "turbidity_instant" in df.columns:
        df["turb_saturated"] = (df["turbidity_instant"] > 3000).astype(float)
        df["turb_below_detection"] = (df["turbidity_instant"] <= 0.5).astype(float)

    # Engineered interaction features (validated by Dr. Harrington + equation validator)
    # First flush: antecedent dryness × current precipitation
    # NaN stays NaN (don't fillna(0) — that conflates "no data" with "just rained")
    if "days_since_rain" in df.columns and "precip_24h" in df.columns:
        df["flush_intensity"] = np.log1p(df["days_since_rain"]) * np.log1p(df["precip_24h"])

    # Note: clay_sand_ratio computed in build_feature_tiers() since clay_pct/sand_pct
    # come from StreamCat attributes, not from the sensor data

    # Remove old garbage features if they somehow exist
    for col in ["dQ_dt"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    return df
