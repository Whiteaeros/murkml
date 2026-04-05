"""Sediment load estimation: 3-way comparison (USGS 80155 vs OLS vs v11 CatBoost).

Compares daily sediment loads from:
  1. USGS 80155 — published daily sediment discharge (human-adjusted rating curves)
  2. Naive OLS — automated log(SSC) ~ log(Q), no turbidity (baseline)
  3. v11 CatBoost — turbidity-informed ML predictions

For 4 holdout sites with all three data streams:
  - USGS-01480617: W. Branch Brandywine Creek, PA (2008-2016)
  - USGS-01473169: Valley Creek, PA (2013-2016)
  - USGS-16274100: Kaneohe Stream, HI (2016-2017)
  - USGS-09327000: Ferron Creek, UT (2014-2017)

Usage:
    .venv/Scripts/python.exe scripts/sediment_load_comparison.py [--sites SITE1 SITE2 ...]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import boxcox1p

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MODEL_DIR = DATA_DIR / "results" / "models"
OUTPUT_DIR = DATA_DIR / "results" / "evaluations" / "load_comparison"
CACHE_DIR = DATA_DIR / "daily_sediment"
CONTINUOUS_DIR = DATA_DIR / "continuous"
WEATHER_DIR = DATA_DIR / "weather"
PAIRED_PATH = DATA_DIR / "processed" / "turbidity_ssc_paired.parquet"

# Conversion: cfs × mg/L → tons/day
# 1 cfs = 28.3168 L/s = 2,446,575.36 L/day
# mg/L × L/day = mg/day; / 1e6 = kg/day; / 907.185 = short tons/day
# Shortcut: 0.0027 (standard USGS factor for short tons)
LOAD_FACTOR = 0.0027

# Model config (v11)
MODEL_PATH = MODEL_DIR / "ssc_C_sensor_basic_watershed_v11_extreme_expanded.cbm"
META_PATH = MODEL_DIR / "ssc_C_sensor_basic_watershed_v11_extreme_expanded_meta.json"

# Sites with continuous turbidity + discharge + published 80155
SITES = {
    "USGS-01480617": {"name": "W Branch Brandywine Creek, PA", "start": "2008-10-01", "end": "2016-09-30"},
    "USGS-01473169": {"name": "Valley Creek, PA", "start": "2013-10-01", "end": "2016-09-30"},
    # USGS-16274100 (Kaneohe Stream, HI): EXCLUDED — turbidity starts Nov 2017,
    # after 80155 record (WY2017) ended. Zero temporal overlap.
    "USGS-09327000": {"name": "Ferron Creek, UT", "start": "2014-05-01", "end": "2017-09-30"},
}

# Minimum daily completeness: 80% of 96 fifteen-minute readings
MIN_READINGS_PER_DAY = 77


# =============================================================================
# Phase 0: Download / cache USGS 80155 daily sediment discharge
# =============================================================================

def download_80155(site_id: str, start: str, end: str) -> pd.DataFrame:
    """Download USGS daily sediment discharge (param 80155) and cache."""
    import dataretrieval.nwis as nwis

    cache_path = CACHE_DIR / f"{site_id}_80155.parquet"
    if cache_path.exists():
        log.info(f"  Loading cached 80155 for {site_id}")
        return pd.read_parquet(cache_path)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    site_num = site_id.replace("USGS-", "")
    log.info(f"  Downloading 80155 for {site_id} ({start} to {end})...")

    df, _ = nwis.get_dv(sites=site_num, parameterCd="80155", start=start, end=end)

    if df.empty:
        log.warning(f"  No 80155 data for {site_id}")
        return pd.DataFrame(columns=["date", "load_tons_day"])

    # dataretrieval returns multi-index; flatten
    df = df.reset_index()
    # Find the 80155 value column (named like '80155_Mean' or similar)
    val_col = [c for c in df.columns if "80155" in str(c)]
    if not val_col:
        log.warning(f"  No 80155 column found in {df.columns.tolist()}")
        return pd.DataFrame(columns=["date", "load_tons_day"])

    result = pd.DataFrame({
        "date": pd.to_datetime(df["datetime"]).dt.date,
        "load_tons_day": pd.to_numeric(df[val_col[0]], errors="coerce"),
    }).dropna(subset=["load_tons_day"])

    result.to_parquet(cache_path, index=False)
    log.info(f"  Cached {len(result)} days of 80155 for {site_id}")
    return result


# =============================================================================
# Phase 1: Load continuous sensor data and build 15-min grid
# =============================================================================

def load_continuous_param(site_id: str, param_code: str) -> pd.DataFrame:
    """Load all parquet chunks for one site + parameter code."""
    site_dir = site_id.replace("-", "_")
    param_dir = CONTINUOUS_DIR / site_dir / param_code
    if not param_dir.exists():
        return pd.DataFrame(columns=["time", "value"])

    chunks = []
    for f in sorted(param_dir.glob("*.parquet")):
        chunk = pd.read_parquet(f)
        if len(chunk) > 0:
            chunks.append(chunk)

    if not chunks:
        return pd.DataFrame(columns=["time", "value"])

    df = pd.concat(chunks, ignore_index=True)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["time", "value"]).drop_duplicates(subset=["time"]).sort_values("time")
    return df[["time", "value"]].reset_index(drop=True)


def build_continuous_grid(site_id: str, start: str, end: str) -> pd.DataFrame:
    """Build aligned 15-min grid of all sensor parameters.

    Returns DataFrame indexed by UTC datetime with columns:
    turbidity, conductance, do, ph, temp, discharge
    """
    PARAMS = {
        "63680": "turbidity",
        "00095": "conductance",
        "00300": "do",
        "00400": "ph",
        "00010": "temp",
        "00060": "discharge",
    }

    # Create 15-min grid
    grid_index = pd.date_range(start=start, end=end, freq="15min", tz="UTC")
    grid = pd.DataFrame(index=grid_index)

    for code, name in PARAMS.items():
        raw = load_continuous_param(site_id, code)
        if raw.empty:
            log.warning(f"  No {name} data for {site_id}")
            grid[name] = np.nan
            continue

        # Set time as index, reindex to grid, interpolate gaps up to 2hr
        raw = raw.set_index("time")
        raw = raw[~raw.index.duplicated(keep="first")]
        aligned = raw["value"].reindex(grid_index)
        # Interpolate linearly, max gap = 8 steps (2hr at 15-min)
        aligned = aligned.interpolate(method="time", limit=8)
        grid[name] = aligned

    # Track where turbidity is valid (for excluding gaps from load calc)
    grid["turbidity_valid"] = grid["turbidity"].notna()

    log.info(
        f"  Grid: {len(grid):,} timesteps, "
        f"turbidity coverage: {grid['turbidity_valid'].mean():.1%}"
    )
    return grid


# =============================================================================
# Phase 2: Vectorized rolling feature engineering
# =============================================================================

def compute_rolling_features(grid: pd.DataFrame) -> pd.DataFrame:
    """Compute time-varying features from continuous sensor data.

    Adds turbidity window stats, hydrograph features, cross-sensor interactions,
    seasonality, and derived turbidity features.
    """
    df = grid.copy()

    # --- Turbidity rolling window (±1hr = 8 steps at 15-min, centered) ---
    turb = df["turbidity"]
    win = 8
    df["turbidity_instant"] = turb
    df["turbidity_mean_1hr"] = turb.rolling(win, center=True, min_periods=1).mean()
    df["turbidity_min_1hr"] = turb.rolling(win, center=True, min_periods=1).min()
    df["turbidity_max_1hr"] = turb.rolling(win, center=True, min_periods=1).max()
    df["turbidity_std_1hr"] = turb.rolling(win, center=True, min_periods=2).std().fillna(0)
    df["turbidity_range_1hr"] = df["turbidity_max_1hr"] - df["turbidity_min_1hr"]

    # Turbidity slope via rolling linear regression with fixed weights
    # For equally-spaced data, slope = Σ(w_i * x_i) / Σ(w_i²)
    # where w_i = i - mean(i) for window indices
    _w = np.arange(win, dtype=float) - (win - 1) / 2.0
    _w_norm = _w / np.sum(_w ** 2)  # Normalized weights

    def _rolling_slope(series, weights=_w_norm):
        """Efficient rolling slope using convolution."""
        vals = series.values
        result = np.full(len(vals), np.nan)
        half = len(weights) // 2
        for i in range(half, len(vals) - half):
            window = vals[i - half: i - half + len(weights)]
            if np.all(np.isfinite(window)):
                result[i] = np.dot(weights, window)
        return pd.Series(result, index=series.index)

    df["turbidity_slope_1hr"] = _rolling_slope(turb)

    # --- Discharge features ---
    Q = df["discharge"]
    df["discharge_instant"] = Q

    # Discharge slope ±2hr (16 steps)
    _w16 = np.arange(16, dtype=float) - 7.5
    _w16_norm = _w16 / np.sum(_w16 ** 2)
    df["discharge_slope_2hr"] = _rolling_slope(Q, _w16_norm)
    df["rising_limb"] = (df["discharge_slope_2hr"] > 0).astype(float)
    df.loc[df["discharge_slope_2hr"].isna(), "rising_limb"] = np.nan

    # Antecedent discharge (backward-looking)
    df["Q_7day_mean"] = Q.rolling(672, min_periods=96).mean()    # 7d × 96/day
    df["Q_30day_mean"] = Q.rolling(2880, min_periods=96).mean()  # 30d × 96/day
    df["Q_ratio_7d"] = Q / df["Q_7day_mean"].replace(0, np.nan)

    # --- Cross-sensor interactions ---
    df["turb_Q_ratio"] = turb / Q.replace(0, np.nan)

    # DO saturation departure (Benson & Krause 1984)
    if "do" in df.columns and "temp" in df.columns:
        T = df["temp"].clip(0, 40)
        Tk = T + 273.15
        ln_sat = (
            -139.34411
            + 1.575701e5 / Tk
            - 6.642308e7 / Tk**2
            + 1.243800e10 / Tk**3
            - 8.621949e11 / Tk**4
        )
        df["DO_sat_departure"] = df["do"] - np.exp(ln_sat)
    else:
        df["DO_sat_departure"] = np.nan

    # Conductance × turbidity
    df["SC_turb_interaction"] = df.get("conductance", pd.Series(np.nan, index=df.index)) * turb

    # --- Rename raw sensor columns to match model features ---
    df["conductance_instant"] = df.get("conductance", pd.Series(np.nan, index=df.index))
    df["do_instant"] = df.get("do", pd.Series(np.nan, index=df.index))
    df["ph_instant"] = df.get("ph", pd.Series(np.nan, index=df.index))
    df["temp_instant"] = df.get("temp", pd.Series(np.nan, index=df.index))

    # --- Derived turbidity features ---
    df["log_turbidity_instant"] = np.log1p(turb.clip(lower=0))
    df["turb_saturated"] = (turb > 3000).astype(float)
    df["turb_below_detection"] = (turb <= 0.5).astype(float)

    # --- Seasonality ---
    doy = df.index.dayofyear
    df["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)

    return df


# =============================================================================
# Phase 3: Static features, weather, and full feature matrix
# =============================================================================

def attach_weather(grid: pd.DataFrame, site_id: str) -> pd.DataFrame:
    """Attach daily weather features, forward-filled onto 15-min grid."""
    df = grid.copy()
    site_dir = site_id.replace("-", "_")
    weather_file = WEATHER_DIR / site_dir / "daily_weather.parquet"

    weather_cols = ["precip_24h", "precip_48h", "precip_7d", "precip_30d",
                    "days_since_rain", "temp_at_sample"]

    if not weather_file.exists():
        log.warning(f"  No weather data for {site_id} — using train_median")
        for col in weather_cols:
            df[col] = np.nan
        return df

    weather = pd.read_parquet(weather_file)
    weather["date"] = pd.to_datetime(weather["date"])
    weather = weather.sort_values("date").reset_index(drop=True)

    # Rolling precip sums (strictly antecedent via shift)
    weather["precip_24h"] = weather["precip_mm"].shift(1).fillna(0)
    weather["precip_48h"] = weather["precip_mm"].shift(1).rolling(2, min_periods=1).sum()
    weather["precip_7d"] = weather["precip_mm"].shift(1).rolling(7, min_periods=1).sum()
    weather["precip_30d"] = weather["precip_mm"].shift(1).rolling(30, min_periods=1).sum()

    # Days since rain
    rain_days = weather["precip_mm"] > 1.0
    days_since = pd.Series(np.nan, index=weather.index)
    last_rain = -1
    for i in range(len(weather)):
        if rain_days.iloc[i]:
            last_rain = i
            days_since.iloc[i] = 0
        elif last_rain >= 0:
            days_since.iloc[i] = i - last_rain
    weather["days_since_rain"] = days_since
    weather["temp_at_sample"] = weather.get("tmean_c", pd.Series(np.nan))

    # Build date-indexed lookup
    weather_indexed = weather.set_index("date")

    # Map daily values onto 15-min grid by date
    grid_dates = df.index.tz_localize(None).normalize()
    for col in weather_cols:
        if col in weather_indexed.columns:
            daily_vals = weather_indexed[col]
            df[col] = daily_vals.reindex(grid_dates).values

    return df


def attach_static_features(grid: pd.DataFrame, site_id: str, meta: dict) -> pd.DataFrame:
    """Attach static watershed attributes and categorical features."""
    df = grid.copy()

    # Get static features from one row of the paired dataset for this site
    paired = pd.read_parquet(PAIRED_PATH)
    site_data = paired[paired["site_id"] == site_id]

    if site_data.empty:
        log.warning(f"  No paired data for {site_id} — all static features from train_median")
        return df

    # Take first row as representative (static features don't change)
    row = site_data.iloc[0]

    # All features from meta that are static (not already computed)
    computed = set(df.columns)
    for feat in meta["feature_cols"]:
        if feat not in computed and feat in row.index:
            val = row[feat]
            df[feat] = val

    # Derived features
    if "drainage_area_km2" in df.columns:
        df["log_drainage_area"] = np.log1p(pd.to_numeric(df["drainage_area_km2"], errors="coerce").clip(lower=0))
    elif "drainage_area_km2" in row.index:
        da = float(row["drainage_area_km2"]) if pd.notna(row.get("drainage_area_km2")) else 0
        df["drainage_area_km2"] = da
        df["log_drainage_area"] = np.log1p(max(da, 0))

    # Flush intensity
    if "days_since_rain" in df.columns and "precip_24h" in df.columns:
        df["flush_intensity"] = np.log1p(df["days_since_rain"].fillna(0)) * np.log1p(df["precip_24h"].fillna(0))

    # Categorical overrides for continuous prediction
    df["collection_method"] = "auto_point"
    df["turb_source"] = "continuous"
    # Use site's sensor_family if available, else "unknown"
    sf = row.get("sensor_family", "unknown")
    df["sensor_family"] = sf if pd.notna(sf) and sf != "" else "unknown"

    return df


def build_feature_matrix(site_id: str, start: str, end: str, meta: dict) -> pd.DataFrame:
    """Build complete 137-feature matrix for continuous v11 prediction.

    Returns DataFrame with time index and columns matching meta["feature_cols"].
    Also retains 'discharge' and 'turbidity_valid' for load computation.
    """
    log.info(f"  Building continuous grid...")
    grid = build_continuous_grid(site_id, start, end)

    log.info(f"  Computing rolling features...")
    grid = compute_rolling_features(grid)

    log.info(f"  Attaching weather...")
    grid = attach_weather(grid, site_id)

    log.info(f"  Attaching static features...")
    grid = attach_static_features(grid, site_id, meta)

    # Fill remaining NaN with train_median — build missing columns in bulk
    train_median = meta.get("train_median", {})
    cat_cols = set(meta.get("cat_cols", []))

    # Collect new columns to add all at once (avoids DataFrame fragmentation)
    new_cols = {}
    for feat in meta["feature_cols"]:
        if feat in cat_cols:
            if feat not in grid.columns:
                new_cols[feat] = "missing"
        else:
            if feat not in grid.columns:
                new_cols[feat] = train_median.get(feat, 0.0)

    if new_cols:
        grid = pd.concat([grid, pd.DataFrame(new_cols, index=grid.index)], axis=1)

    # Now fill NaN in existing columns
    for feat in meta["feature_cols"]:
        if feat in cat_cols:
            grid[feat] = grid[feat].fillna("missing").astype(str)
        else:
            median_val = train_median.get(feat, 0.0)
            grid[feat] = pd.to_numeric(grid[feat], errors="coerce").fillna(median_val)

    log.info(f"  Feature matrix: {len(grid):,} rows × {len(meta['feature_cols'])} features")
    return grid


# =============================================================================
# Phase 4: Predict SSC (v11 and OLS)
# =============================================================================

def predict_v11(grid: pd.DataFrame, model, meta: dict) -> pd.Series:
    """Predict SSC at every timestep using v11 CatBoost. Returns native mg/L."""
    from catboost import Pool
    from murkml.evaluate.metrics import safe_inv_boxcox1p

    feature_cols = meta["feature_cols"]
    cat_indices = meta.get("cat_indices", [])
    lmbda = meta["transform_lmbda"]
    bcf = meta["bcf_mean"]  # Use bcf_mean for load estimation (unbiased totals)

    X = grid[feature_cols].copy()

    # CatBoost needs string categoricals
    for idx in cat_indices:
        col = feature_cols[idx]
        X[col] = X[col].astype(str)

    # Predict in chunks to manage memory (50K rows at a time)
    chunk_size = 50_000
    y_pred_native = np.empty(len(X))

    for i in range(0, len(X), chunk_size):
        chunk = X.iloc[i:i + chunk_size]
        pool = Pool(chunk, cat_features=cat_indices)
        y_ms = model.predict(pool)
        y_native = safe_inv_boxcox1p(y_ms, lmbda) * bcf
        y_pred_native[i:i + len(chunk)] = np.clip(y_native, 0, 1e6)

    result = pd.Series(y_pred_native, index=grid.index, name="ssc_v11")

    # CatBoost handles NaN natively — let it predict even without turbidity.
    # The model has 137 features; turbidity is important but not the only input.
    return result


def predict_ols(discharge: pd.Series, cal_ssc: np.ndarray, cal_q: np.ndarray) -> pd.Series:
    """Predict SSC from discharge-only OLS rating curve.

    Fits log10(SSC) = a + b*log10(Q) on calibration data (discrete samples).
    This is the standard USGS sediment rating curve — Q only, no turbidity.
    """
    # Filter to valid calibration pairs
    valid = np.isfinite(cal_ssc) & np.isfinite(cal_q) & (cal_ssc > 0) & (cal_q > 0)
    cal_ssc = cal_ssc[valid]
    cal_q = cal_q[valid]

    if len(cal_ssc) < 3:
        log.warning("  OLS: fewer than 3 valid calibration pairs")
        return pd.Series(np.nan, index=discharge.index, name="ssc_ols")

    # Fit in log10 space
    log_q = np.log10(cal_q)
    log_ssc = np.log10(cal_ssc)
    coeffs = np.polyfit(log_q, log_ssc, 1)  # [slope, intercept]
    slope, intercept = coeffs

    # Predict
    log_q_pred = np.log10(discharge.clip(lower=0.01))
    log_ssc_pred = intercept + slope * log_q_pred

    # Duan's smearing BCF
    residuals = log_ssc - (intercept + slope * log_q)
    bcf_duan = np.mean(10.0 ** residuals)
    bcf_duan = np.clip(bcf_duan, 0.5, 5.0)

    ssc_pred = (10.0 ** log_ssc_pred) * bcf_duan
    ssc_pred = np.clip(ssc_pred, 0, 1e6)

    log.info(f"  OLS: slope={slope:.3f}, intercept={intercept:.3f}, "
             f"BCF_duan={bcf_duan:.3f}, n_cal={len(cal_ssc)}")

    return pd.Series(ssc_pred.values, index=discharge.index, name="ssc_ols")


# =============================================================================
# Phase 5: Load computation and aggregation
# =============================================================================

def compute_daily_loads(ssc: pd.Series, discharge: pd.Series) -> pd.Series:
    """Compute daily sediment load from 15-min SSC and discharge.

    Load rate (tons/day) = SSC (mg/L) × Q (cfs) × 0.0027
    Daily load = mean of 15-min rates (since rate is already in tons/day).
    Requires ≥80% completeness per day.
    """
    load_rate = ssc * discharge * LOAD_FACTOR
    load_rate.index = load_rate.index.tz_localize(None)  # Strip tz for groupby

    daily = load_rate.groupby(load_rate.index.date).agg(["mean", "count"])
    daily.columns = ["load_tons_day", "n_readings"]
    # Require ≥80% completeness
    daily.loc[daily["n_readings"] < MIN_READINGS_PER_DAY, "load_tons_day"] = np.nan

    result = daily["load_tons_day"]
    result.index = pd.to_datetime(result.index)
    result.index.name = "date"
    return result


def aggregate_monthly(daily: pd.Series) -> pd.Series:
    """Sum daily loads to monthly totals. Require ≥80% of days present."""
    monthly = daily.groupby(daily.index.to_period("M")).agg(["sum", "count"])
    monthly.columns = ["load_tons", "n_days"]
    days_in_month = monthly.index.map(lambda p: p.days_in_month)
    monthly.loc[monthly["n_days"] < (0.8 * days_in_month), "load_tons"] = np.nan
    return monthly["load_tons"]


def aggregate_annual(daily: pd.Series) -> pd.Series:
    """Sum daily loads to water-year totals. Require ≥80% of days present."""
    # Use water year (Oct-Sep): WY2015 = Oct 2014 through Sep 2015
    valid = daily.dropna()
    if valid.empty:
        return pd.Series(dtype=float)
    wy = valid.index.year.where(valid.index.month >= 10, valid.index.year)
    # WY label = the year containing Jan-Sep (e.g., Oct 2014 → WY 2015)
    wy = valid.index.year + (valid.index.month >= 10).astype(int)
    annual = valid.groupby(wy).agg(["sum", "count"])
    annual.columns = ["load_tons", "n_days"]
    annual.loc[annual["n_days"] < 292, "load_tons"] = np.nan  # 80% of 365
    return annual["load_tons"]


# =============================================================================
# Phase 6: Storm event detection
# =============================================================================

def detect_events(discharge: pd.Series, rise_factor: float = 1.5,
                  min_hrs: int = 6, sep_hrs: int = 24) -> list[dict]:
    """Detect storm events from continuous discharge hydrograph.

    Algorithm:
    1. Baseflow = 7-day rolling minimum
    2. Event = Q exceeds rise_factor × baseflow for ≥min_hrs
    3. Merge events separated by <sep_hrs
    4. Extend to recession (Q returns to 1.2× baseflow)
    """
    Q = discharge.dropna()
    if len(Q) < 672:  # Need at least 7 days
        return []

    # Baseflow: 7-day rolling minimum
    baseflow = Q.rolling(672, min_periods=96).min()
    threshold = baseflow * rise_factor

    # Identify above-threshold periods
    above = Q > threshold
    above = above.fillna(False)

    # Find contiguous event blocks
    events = []
    in_event = False
    event_start = None
    steps_per_hr = 4  # 15-min resolution

    for i, (t, is_above) in enumerate(above.items()):
        if is_above and not in_event:
            event_start = t
            in_event = True
        elif not is_above and in_event:
            duration_hrs = (t - event_start).total_seconds() / 3600
            if duration_hrs >= min_hrs:
                events.append({"start": event_start, "end": t})
            in_event = False

    # Close any open event at the end
    if in_event and event_start is not None:
        duration_hrs = (Q.index[-1] - event_start).total_seconds() / 3600
        if duration_hrs >= min_hrs:
            events.append({"start": event_start, "end": Q.index[-1]})

    # Merge events separated by <sep_hrs
    merged = []
    for evt in events:
        if merged and (evt["start"] - merged[-1]["end"]).total_seconds() / 3600 < sep_hrs:
            merged[-1]["end"] = evt["end"]
        else:
            merged.append(evt)

    # Extend to recession and compute stats
    result = []
    for i, evt in enumerate(merged):
        mask = (Q.index >= evt["start"]) & (Q.index <= evt["end"])
        peak_Q = Q[mask].max()
        bf = baseflow.loc[evt["start"]] if evt["start"] in baseflow.index else Q[mask].min()
        duration_hrs = (evt["end"] - evt["start"]).total_seconds() / 3600

        result.append({
            "event_id": i + 1,
            "start": evt["start"],
            "end": evt["end"],
            "peak_Q_cfs": float(peak_Q),
            "baseflow_cfs": float(bf) if pd.notna(bf) else np.nan,
            "duration_hrs": duration_hrs,
        })

    log.info(f"  Detected {len(result)} storm events")
    return result


def compute_event_loads(daily_80155: pd.Series, daily_ols: pd.Series,
                        daily_v11: pd.Series, events: list[dict]) -> pd.DataFrame:
    """Compute total load during each storm event for each method."""
    rows = []
    for evt in events:
        start_date = pd.Timestamp(evt["start"]).normalize()
        end_date = pd.Timestamp(evt["end"]).normalize() + pd.Timedelta(days=1)
        mask_fn = lambda s: s[(s.index >= start_date) & (s.index < end_date)]

        load_80155 = mask_fn(daily_80155).sum()
        load_ols = mask_fn(daily_ols).sum()
        load_v11 = mask_fn(daily_v11).sum()

        # Only compute % error if 80155 load is non-trivial (>0.1 tons)
        pct_ols = 100 * (load_ols - load_80155) / load_80155 if load_80155 > 0.1 else np.nan
        pct_v11 = 100 * (load_v11 - load_80155) / load_80155 if load_80155 > 0.1 else np.nan

        rows.append({
            **evt,
            "load_80155_tons": load_80155,
            "load_ols_tons": load_ols,
            "load_v11_tons": load_v11,
            "pct_error_ols": pct_ols,
            "pct_error_v11": pct_v11,
        })

    return pd.DataFrame(rows)


# =============================================================================
# Phase 7: Comparison metrics
# =============================================================================

def compute_metrics(ref: pd.Series, pred: pd.Series, label: str) -> dict:
    """Compute comparison metrics between reference and predicted daily loads."""
    # Align on common valid dates
    common = ref.dropna().index.intersection(pred.dropna().index)
    r = ref.loc[common].values.astype(float)
    p = pred.loc[common].values.astype(float)

    if len(r) < 5:
        return {"method": label, "n_days": len(r), "error": "insufficient_data"}

    # Standard metrics
    ss_res = np.sum((p - r) ** 2)
    ss_tot = np.sum((r - np.mean(r)) ** 2)
    r2 = 1 - ss_res / max(ss_tot, 1e-10)

    # NSE
    nse = r2  # Same formula for daily loads

    # Log-NSE (for low-flow days)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        log_r = np.log1p(np.clip(r, 0, None))
        log_p = np.log1p(np.clip(p, 0, None))
        ss_res_log = np.sum((log_p - log_r) ** 2)
        ss_tot_log = np.sum((log_r - np.mean(log_r)) ** 2)
        log_nse = 1 - ss_res_log / max(ss_tot_log, 1e-10)

    # KGE
    corr = np.corrcoef(r, p)[0, 1] if len(r) > 1 else np.nan
    alpha = np.std(p) / max(np.std(r), 1e-10)
    beta = np.mean(p) / max(np.mean(r), 1e-10)
    kge = 1 - np.sqrt((corr - 1)**2 + (alpha - 1)**2 + (beta - 1)**2)

    # Percent bias
    pbias = 100 * (np.sum(p) - np.sum(r)) / max(np.sum(r), 1e-10)

    # Total load ratio
    total_ratio = np.sum(p) / max(np.sum(r), 1e-10)

    # Median daily error
    daily_err = np.abs(p - r) / np.clip(r, 1e-3, None) * 100
    median_err = float(np.median(daily_err))

    # Spearman correlation
    from scipy.stats import spearmanr
    spearman, _ = spearmanr(r, p)

    return {
        "method": label,
        "n_days": int(len(r)),
        "r2": float(r2),
        "nse": float(nse),
        "log_nse": float(log_nse),
        "kge": float(kge),
        "spearman": float(spearman),
        "pbias_pct": float(pbias),
        "total_load_ratio": float(total_ratio),
        "rmse_tons": float(np.sqrt(np.mean((p - r) ** 2))),
        "median_daily_error_pct": median_err,
    }


# =============================================================================
# Main orchestrator
# =============================================================================

def process_site(site_id: str, site_info: dict, model, meta: dict) -> dict:
    """Run full load comparison for one site."""
    log.info(f"\n{'='*60}")
    log.info(f"Processing {site_id}: {site_info['name']}")
    log.info(f"{'='*60}")

    start, end = site_info["start"], site_info["end"]

    # --- Download 80155 ---
    log.info("Phase 0: Loading USGS 80155 daily sediment discharge")
    df_80155 = download_80155(site_id, start, end)
    if df_80155.empty:
        log.error(f"  No 80155 data — skipping {site_id}")
        return {"site_id": site_id, "error": "no_80155_data"}

    daily_80155 = df_80155.set_index("date")["load_tons_day"]
    daily_80155.index = pd.to_datetime(daily_80155.index)
    log.info(f"  80155: {len(daily_80155)} days, "
             f"{daily_80155.sum():,.0f} total tons")

    # --- Build feature matrix ---
    log.info("Phase 1-3: Building continuous feature matrix")
    grid = build_feature_matrix(site_id, start, end, meta)

    # --- v11 predictions ---
    log.info("Phase 4a: v11 CatBoost SSC predictions")
    ssc_v11 = predict_v11(grid, model, meta)
    log.info(f"  v11 SSC: median={ssc_v11.median():.1f} mg/L, "
             f"mean={ssc_v11.mean():.1f} mg/L")

    # --- OLS predictions ---
    log.info("Phase 4b: OLS discharge-only SSC predictions")
    # Get discrete SSC + Q pairs for OLS calibration
    paired = pd.read_parquet(PAIRED_PATH)
    site_paired = paired[paired["site_id"] == site_id]
    cal_ssc = site_paired["lab_value"].values
    cal_q = site_paired["discharge_instant"].values
    ssc_ols = predict_ols(grid["discharge"], cal_ssc, cal_q)

    # --- Compute daily loads ---
    log.info("Phase 5: Computing daily loads")
    daily_v11 = compute_daily_loads(ssc_v11, grid["discharge"])
    daily_ols = compute_daily_loads(ssc_ols, grid["discharge"])
    log.info(f"  v11 daily loads: {daily_v11.dropna().shape[0]} valid days, "
             f"{daily_v11.sum():,.0f} total tons")
    log.info(f"  OLS daily loads: {daily_ols.dropna().shape[0]} valid days, "
             f"{daily_ols.sum():,.0f} total tons")
    log.info(f"  80155 total: {daily_80155.sum():,.0f} tons over {len(daily_80155)} days")

    # --- Metrics at multiple scales ---
    log.info("Phase 6: Computing comparison metrics")
    results = {"site_id": site_id, "name": site_info["name"]}

    # Daily — all days
    results["daily"] = {
        "ols": compute_metrics(daily_80155, daily_ols, "OLS"),
        "v11": compute_metrics(daily_80155, daily_v11, "v11"),
    }

    # Daily — filtered to days with 80155 >= 1 ton (actual sediment transport)
    # Many 80155 days are 0.0 (hydrographer set "no measurable sediment"),
    # but turbidity-based models always predict nonzero. Filter to fair comparison.
    transport_days = daily_80155[daily_80155 >= 1.0].index
    if len(transport_days) > 10:
        d80_filt = daily_80155.loc[transport_days]
        d_ols_filt = daily_ols.reindex(transport_days)
        d_v11_filt = daily_v11.reindex(transport_days)
        results["daily_transport"] = {
            "ols": compute_metrics(d80_filt, d_ols_filt, "OLS (transport days)"),
            "v11": compute_metrics(d80_filt, d_v11_filt, "v11 (transport days)"),
            "n_transport_days": len(transport_days),
            "pct_of_total": f"{100*len(transport_days)/len(daily_80155.dropna()):.0f}%",
        }

    # Monthly — align indices, convert to numeric Series for metrics
    monthly_80155 = aggregate_monthly(daily_80155)
    monthly_ols = aggregate_monthly(daily_ols)
    monthly_v11 = aggregate_monthly(daily_v11)
    common_months = monthly_80155.dropna().index
    m80 = monthly_80155.reindex(common_months).reset_index(drop=True)
    m80.index = pd.RangeIndex(len(m80))
    results["monthly"] = {
        "ols": compute_metrics(
            m80,
            monthly_ols.reindex(common_months).reset_index(drop=True),
            "OLS"
        ),
        "v11": compute_metrics(
            m80,
            monthly_v11.reindex(common_months).reset_index(drop=True),
            "v11"
        ),
    }

    # Annual
    annual_80155 = aggregate_annual(daily_80155)
    annual_ols = aggregate_annual(daily_ols)
    annual_v11 = aggregate_annual(daily_v11)
    results["annual"] = {
        "80155_tons": annual_80155.to_dict(),
        "ols_tons": annual_ols.to_dict(),
        "v11_tons": annual_v11.to_dict(),
    }

    # --- Storm events ---
    log.info("Phase 7: Storm event detection and event loads")
    discharge_series = grid["discharge"].copy()
    discharge_series.index = discharge_series.index.tz_localize(None) if discharge_series.index.tz else discharge_series.index
    events = detect_events(discharge_series)
    if events:
        event_df = compute_event_loads(daily_80155, daily_ols, daily_v11, events)
        results["events"] = {
            "n_events": len(events),
            "median_pct_error_ols": float(event_df["pct_error_ols"].median()),
            "median_pct_error_v11": float(event_df["pct_error_v11"].median()),
            "mean_pct_error_ols": float(event_df["pct_error_ols"].mean()),
            "mean_pct_error_v11": float(event_df["pct_error_v11"].mean()),
        }

        # Save event details
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        event_df.to_parquet(OUTPUT_DIR / f"event_loads_{site_id}.parquet", index=False)
        log.info(f"  Events: n={len(events)}, "
                 f"median error OLS={event_df['pct_error_ols'].median():.1f}%, "
                 f"v11={event_df['pct_error_v11'].median():.1f}%")
    else:
        results["events"] = {"n_events": 0}

    # --- Save daily loads ---
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    daily_combined = pd.DataFrame({
        "load_80155": daily_80155,
        "load_ols": daily_ols,
        "load_v11": daily_v11,
    })
    daily_combined.to_parquet(OUTPUT_DIR / f"daily_loads_{site_id}.parquet")

    return results


def print_summary(all_results: list[dict]):
    """Print formatted comparison table."""
    print(f"\n{'='*80}")
    print("SEDIMENT LOAD COMPARISON — SUMMARY")
    print(f"{'='*80}\n")

    for res in all_results:
        if "error" in res:
            print(f"{res['site_id']}: ERROR — {res['error']}\n")
            continue

        print(f"--- {res['site_id']}: {res['name']} ---")

        # Daily metrics
        if "daily" in res:
            d_ols = res["daily"]["ols"]
            d_v11 = res["daily"]["v11"]
            print(f"  DAILY (n={d_v11.get('n_days', '?')} days):")
            print(f"    {'Metric':<22} {'OLS':>10} {'v11':>10}")
            print(f"    {'-'*42}")
            for metric in ["r2", "nse", "log_nse", "kge", "spearman", "pbias_pct",
                           "total_load_ratio", "median_daily_error_pct"]:
                v_ols = d_ols.get(metric, np.nan)
                v_v11 = d_v11.get(metric, np.nan)
                fmt = ".3f" if metric not in ["pbias_pct", "median_daily_error_pct"] else ".1f"
                print(f"    {metric:<22} {v_ols:>10{fmt}} {v_v11:>10{fmt}}")

        # Transport-day metrics
        if "daily_transport" in res:
            dt = res["daily_transport"]
            dt_ols = dt["ols"]
            dt_v11 = dt["v11"]
            print(f"\n  TRANSPORT DAYS ONLY (80155 >= 1 ton, n={dt.get('n_transport_days', '?')}, "
                  f"{dt.get('pct_of_total', '?')} of record):")
            print(f"    {'Metric':<22} {'OLS':>10} {'v11':>10}")
            print(f"    {'-'*42}")
            for metric in ["r2", "nse", "log_nse", "kge", "spearman", "pbias_pct",
                           "total_load_ratio", "median_daily_error_pct"]:
                v_ols = dt_ols.get(metric, np.nan)
                v_v11 = dt_v11.get(metric, np.nan)
                fmt = ".3f" if metric not in ["pbias_pct", "median_daily_error_pct"] else ".1f"
                print(f"    {metric:<22} {v_ols:>10{fmt}} {v_v11:>10{fmt}}")

        # Events
        if "events" in res and res["events"].get("n_events", 0) > 0:
            evt = res["events"]
            print(f"\n  STORM EVENTS (n={evt['n_events']}):")
            print(f"    Median % error — OLS: {evt['median_pct_error_ols']:.1f}%, "
                  f"v11: {evt['median_pct_error_v11']:.1f}%")
            print(f"    Mean % error   — OLS: {evt['mean_pct_error_ols']:.1f}%, "
                  f"v11: {evt['mean_pct_error_v11']:.1f}%")

        # Annual
        if "annual" in res:
            print(f"\n  ANNUAL LOADS (tons):")
            years = sorted(set(
                list(res["annual"]["80155_tons"].keys()) +
                list(res["annual"]["v11_tons"].keys())
            ))
            print(f"    {'Year':<8} {'80155':>12} {'OLS':>12} {'v11':>12}")
            for yr in years:
                v_80155 = res["annual"]["80155_tons"].get(yr, np.nan)
                v_ols = res["annual"]["ols_tons"].get(yr, np.nan)
                v_v11 = res["annual"]["v11_tons"].get(yr, np.nan)
                print(f"    {yr:<8} {v_80155:>12,.0f} {v_ols:>12,.0f} {v_v11:>12,.0f}")

        print()


def main():
    parser = argparse.ArgumentParser(description="Sediment load 3-way comparison")
    parser.add_argument("--sites", nargs="*", default=None,
                        help="Site IDs to process (default: all 4)")
    args = parser.parse_args()

    sites_to_run = {k: v for k, v in SITES.items()
                    if args.sites is None or k in args.sites}

    if not sites_to_run:
        log.error("No valid sites specified")
        sys.exit(1)

    # Load model
    log.info("Loading v11 model...")
    from catboost import CatBoostRegressor
    model = CatBoostRegressor()
    model.load_model(str(MODEL_PATH))
    with open(META_PATH) as f:
        meta = json.load(f)
    log.info(f"  Model: {MODEL_PATH.name}, {len(meta['feature_cols'])} features, "
             f"BCF_mean={meta['bcf_mean']:.4f}")

    # Process each site
    all_results = []
    for site_id, site_info in sites_to_run.items():
        result = process_site(site_id, site_info, model, meta)
        all_results.append(result)

    # Save master summary
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / "load_comparison_summary.json", "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    # Print summary table
    print_summary(all_results)

    log.info(f"\nResults saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
