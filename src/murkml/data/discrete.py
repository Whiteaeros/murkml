"""Parameter-agnostic discrete sample loader.

Loads discrete lab data for any USGS parameter, handling:
- Timezone conversion (local → UTC)
- Non-detect DL/2 substitution (per-record detection limits)
- Contamination exclusion
- Deduplication with conflict resolution
- High-censoring site filtering

Supports SSC, TP, nitrate+nitrite, TDS, orthophosphate, and any future parameter.

MVP parameters: SSC, TP, nitrate+nitrite, orthophosphate (4 core).
TDS dropped from MVP — only 16 sites with ≥20 pairable samples (most TDS
samples predate continuous sensors). TDS will be evaluated separately as a
SC-linear validation target since SC→TDS is near-linear (R²>0.95).

CENSORING ACCOUNTABILITY (Patel review requirement):
    Orthophosphate (9.8% avg censoring, 12 sites >10%):
        Phase 4 MUST run sensitivity analysis comparing:
        1. DL/2 substitution (current)
        2. DL/sqrt(2) substitution
        3. Site exclusion at 10% threshold vs 50%
        Trigger: if orthoP model R² < 0.5 or prediction intervals are
        wider than other nutrient parameters, censoring is the first
        suspect. Training script supports --censoring-method flag.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from murkml.data.qc import deduplicate_discrete, exclude_contamination

logger = logging.getLogger(__name__)

# USGS timezone abbreviation → UTC offset (hours)
USGS_TZ_OFFSETS = {
    "EST": -5, "EDT": -4,
    "CST": -6, "CDT": -5,
    "MST": -7, "MDT": -6,
    "PST": -8, "PDT": -7,
    "AKST": -9, "AKDT": -8,
    "HST": -10, "AST": -4,
    "UTC": 0, "GMT": 0,
}

# Detection limit column candidates (tried in order)
DL_COLUMNS = [
    "DetectionLimit_MeasureA",
    "DetectionQuantitationLimitMeasure_MeasureValue",
    "Result_DetectionQuantitationLimitMeasure",
]


def load_discrete_param(
    site_id: str,
    param_name: str,
    data_dir: Path,
    value_col_out: str = "value",
    default_dl: float | None = None,
    include_hydro_event: bool = True,
) -> pd.DataFrame:
    """Load discrete lab samples for any parameter at a site.

    Args:
        site_id: USGS site identifier (e.g., "USGS-01491000").
        param_name: Parameter name matching file suffix (e.g., "ssc", "total_phosphorus").
        data_dir: Path to data directory containing discrete/ subdirectory.
        value_col_out: Name for the output value column.
        default_dl: Default detection limit when DL is missing (mg/L).
            If None, uses parameter-specific defaults (SSC=1.0, nutrients=0.01).
        include_hydro_event: Whether to preserve Activity_HydrologicEvent column.

    Returns:
        DataFrame with columns: [datetime, {value_col_out}, is_nondetect]
        plus optionally [hydro_event].
        Empty DataFrame if no valid data.
    """
    site_stem = site_id.replace("-", "_")
    cache_file = data_dir / "discrete" / f"{site_stem}_{param_name}.parquet"
    if not cache_file.exists():
        return pd.DataFrame()

    df = pd.read_parquet(cache_file)
    n_original = len(df)

    if df.empty:
        return pd.DataFrame()

    # --- Exclude contamination-flagged records ---
    df, n_contam = exclude_contamination(df)

    # --- Timezone-aware datetime parsing ---
    if "Activity_StartDate" not in df.columns:
        return pd.DataFrame()

    if "Activity_StartTime" not in df.columns:
        logger.warning(f"  {site_id}/{param_name}: No Activity_StartTime — skipping")
        return pd.DataFrame()

    # Drop missing time
    time_null = df["Activity_StartTime"].isna() | (df["Activity_StartTime"] == "")
    n_null_time = time_null.sum()
    df = df[~time_null].copy()

    # Drop missing/unrecognized timezone
    if "Activity_StartTimeZone" not in df.columns:
        logger.warning(f"  {site_id}/{param_name}: No timezone column — skipping")
        return pd.DataFrame()

    tz_col = df["Activity_StartTimeZone"].fillna("")
    unrecognized = ~tz_col.isin(USGS_TZ_OFFSETS.keys())
    n_bad_tz = unrecognized.sum()
    df = df[~unrecognized].copy()

    if df.empty:
        return pd.DataFrame()

    # Convert local → UTC
    local_dt = pd.to_datetime(
        df["Activity_StartDate"].astype(str) + " " + df["Activity_StartTime"].astype(str),
        errors="coerce",
    )
    offsets = df["Activity_StartTimeZone"].map(USGS_TZ_OFFSETS)
    utc_dt = local_dt - pd.to_timedelta(offsets, unit="h")
    df["datetime"] = utc_dt.dt.tz_localize("UTC")

    # --- Parse value ---
    if "Result_Measure" not in df.columns:
        return pd.DataFrame()

    df[value_col_out] = pd.to_numeric(df["Result_Measure"], errors="coerce")

    # --- Parameter-specific default detection limits ---
    # Rivera: default_dl=1.0 is 20-250x too high for nutrients
    if default_dl is None:
        _PARAM_DEFAULTS = {
            "ssc": 1.0,
            "total_phosphorus": 0.01,
            "nitrate_nitrite": 0.04,
            "tds_evaporative": 5.0,
            "orthophosphate": 0.005,
        }
        default_dl = _PARAM_DEFAULTS.get(param_name, 0.01)

    # --- Non-detect handling: per-record DL/2 substitution ---
    df["is_nondetect"] = False
    if "Result_ResultDetectionCondition" in df.columns:
        nd_mask = (
            df["Result_ResultDetectionCondition"]
            .astype(str)
            .str.lower()
            .str.contains("not detect", na=False)
        )
        n_nondetect = nd_mask.sum()
        if n_nondetect > 0:
            # Find detection limit column (per-record)
            # Rivera fix: check notna().any() — don't break on all-NaN columns
            dl_values = pd.Series(np.nan, index=df.index)
            for dl_col in DL_COLUMNS:
                if dl_col in df.columns:
                    candidate = pd.to_numeric(
                        df.loc[nd_mask, dl_col], errors="coerce"
                    ).reindex(df.index)
                    if candidate.notna().any():
                        dl_values = candidate
                        break

            # Fill remaining NaN DLs from the result value itself
            dl_values = dl_values.fillna(
                pd.to_numeric(df["Result_Measure"], errors="coerce")
            )
            # Chen fix: guard against DL=0 producing DL/2=0
            dl_values = dl_values.where(dl_values > 0, default_dl)
            # Last resort: use parameter-specific default
            dl_values = dl_values.fillna(default_dl)

            df.loc[nd_mask, value_col_out] = dl_values[nd_mask] / 2.0
            df.loc[nd_mask, "is_nondetect"] = True
            logger.info(f"  {n_nondetect} non-detects → DL/2 (per-record DL)")

    # --- Preserve hydrologic event ---
    hydro_col = None
    if include_hydro_event and "Activity_HydrologicEvent" in df.columns:
        df["hydro_event"] = df["Activity_HydrologicEvent"].fillna("Unknown")
        hydro_col = "hydro_event"

    # --- Filter to valid rows ---
    valid = df.dropna(subset=["datetime", value_col_out]).copy()
    valid = valid[valid[value_col_out] >= 0]

    # --- Deduplicate with conflict resolution ---
    valid, dedup_stats = deduplicate_discrete(
        valid, datetime_col="datetime", value_col=value_col_out
    )

    valid = valid.sort_values("datetime").reset_index(drop=True)
    n_final = len(valid)

    logger.info(
        f"  {site_id}/{param_name}: {n_original} raw → {n_final} valid "
        f"(dropped: {n_null_time} null time, {n_bad_tz} bad tz, "
        f"{n_contam} contam, {dedup_stats.get('n_removed', 0)} dupes)"
    )

    out_cols = ["datetime", value_col_out, "is_nondetect"]
    if hydro_col:
        out_cols.append(hydro_col)
    return valid[out_cols]


def load_ssc(site_id: str, data_dir: Path) -> pd.DataFrame:
    """Load discrete SSC samples — backward-compatible wrapper.

    Returns DataFrame with [datetime, ssc_value, is_nondetect].
    """
    df = load_discrete_param(
        site_id=site_id,
        param_name="ssc",
        data_dir=data_dir,
        value_col_out="ssc_value",
        default_dl=1.0,  # SSC: 1 mg/L is appropriate
        include_hydro_event=False,
    )
    return df
