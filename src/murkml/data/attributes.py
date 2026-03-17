"""Catchment attribute processing for murkml.

Handles GAGES-II feature pruning, 3-tier ablation setup, and attribute merging.

GAGES-II staleness note (2006-2011 vintage):
    Time-sensitive (use with caution for recent data):
        - NLCD land cover percentages (2006 vintage)
        - Population density, road density
        - Dam counts and storage (2009 vintage)
        - Impervious surface percentages
    Stable (geologically/climatically persistent):
        - Elevation, slope, aspect, basin morphology
        - Geology, soil properties (clay, sand, permeability)
        - Climate normals (temp, precip averages)
        - Baseflow index, stream density
        - HUC codes, drainage area
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def prune_gagesii(df: pd.DataFrame) -> pd.DataFrame:
    """Prune GAGES-II attributes from ~576 to ~20-25 key features.

    Merges correlated groups to reduce dimensionality for 37-site models.
    Chen review: 44 features is too many for 37 sites. Target 20-25.

    Args:
        df: GAGES-II matched attributes DataFrame (must have 'site_id' column).

    Returns:
        DataFrame with pruned/merged feature columns + site_id.
    """
    out = pd.DataFrame()
    out["site_id"] = df["site_id"]

    # --- Land cover (8 → 4) ---
    out["forest_pct"] = _safe_col(df, "FORESTNLCD06", 0)
    out["agriculture_pct"] = (
        _safe_col(df, "CROPSNLCD06", 0) + _safe_col(df, "PASTURENLCD06", 0)
    )
    out["developed_pct"] = _safe_col(df, "DEVNLCD06", 0)
    # other = 100 - forest - ag - developed (includes water, wetland, barren, shrub)
    out["other_landcover_pct"] = (
        100.0 - out["forest_pct"] - out["agriculture_pct"] - out["developed_pct"]
    ).clip(lower=0)

    # --- Geology ---
    out["geol_class"] = _safe_col(df, "GEOL_HUNT_DOM_CODE", None)

    # --- Soils (4 soil groups → permeability + clay) ---
    out["clay_pct"] = _safe_col(df, "CLAYAVE", np.nan)
    out["sand_pct"] = _safe_col(df, "SANDAVE", np.nan)
    out["soil_permeability"] = _safe_col(df, "PERMAVE", np.nan)
    out["water_table_depth"] = _safe_col(df, "WTDEPAVE", np.nan)

    # --- Climate (6 → 4) ---
    out["precip_mean_mm"] = _safe_col(df, "PPTAVG_BASIN", np.nan)
    out["temp_mean_c"] = _safe_col(df, "T_AVG_BASIN", np.nan)
    out["temp_range_c"] = (
        _safe_col(df, "T_MAX_BASIN", np.nan) - _safe_col(df, "T_MIN_BASIN", np.nan)
    )
    out["precip_seasonality"] = _safe_col(df, "PRECIP_SEAS_IND", np.nan)
    out["snow_pct_precip"] = _safe_col(df, "SNOW_PCT_PRECIP", np.nan)

    # --- Topography (3 → 2) ---
    out["elev_mean_m"] = _safe_col(df, "ELEV_MEAN_M_BASIN", np.nan)
    out["relief_m"] = (
        _safe_col(df, "ELEV_MAX_M_BASIN", np.nan)
        - _safe_col(df, "ELEV_MIN_M_BASIN", np.nan)
    )
    out["slope_pct"] = _safe_col(df, "SLOPE_PCT", np.nan)

    # --- Hydrology ---
    out["baseflow_index"] = _safe_col(df, "BFI_AVE", np.nan)
    out["runoff_mean"] = _safe_col(df, "RUNAVE7100", np.nan)
    out["stream_density"] = _safe_col(df, "STREAMS_KM_SQ_KM", np.nan)

    # --- Dams (3 → 2) ---
    out["n_dams"] = _safe_col(df, "NDAMS_2009", 0)
    out["dam_storage"] = _safe_col(df, "STOR_NOR_2009", 0)

    # --- Human influence ---
    out["road_density"] = _safe_col(df, "ROADS_KM_SQ_KM", np.nan)

    # --- Classification ---
    out["reference_class"] = _safe_col(df, "CLASS", None)
    out["ecoregion"] = _safe_col(df, "AGGECOREGION", None)

    n_features = len([c for c in out.columns if c != "site_id"])
    logger.info(f"Pruned GAGES-II: {len(df.columns)} → {n_features} features")

    return out


def _safe_col(df: pd.DataFrame, col: str, default):
    """Safely extract a column, returning default if missing."""
    if col in df.columns:
        return df[col]
    return pd.Series(default, index=df.index)


def build_feature_tiers(
    assembled_df: pd.DataFrame,
    basic_attrs: pd.DataFrame,
    gagesii_attrs: pd.DataFrame | None = None,
) -> dict[str, dict]:
    """Build 3-tier feature sets for ablation study.

    Tier A (all sites): Sensor-only features
    Tier B (all sites): Sensor + basic attributes (drainage area, elevation, HUC)
    Tier C (GAGES-II sites only): Sensor + basic + pruned GAGES-II

    Args:
        assembled_df: Paired sensor+discrete dataset with site_id column.
        basic_attrs: Basic site attributes (drainage area, elevation, HUC) for all sites.
        gagesii_attrs: Pruned GAGES-II attributes (from prune_gagesii). Optional.

    Returns:
        Dict mapping tier name to {"data": DataFrame, "sites": list, "feature_cols": list}.
    """
    tiers = {}

    # Identify sensor feature columns (everything except metadata and targets)
    # Chen fix: use explicit exclude set, NOT substring matching on "value"
    # (substring would exclude any sensor column containing "value")
    exclude_cols = {
        "site_id", "sample_time", "datetime", "lab_value", "match_gap_seconds",
        "window_count", "is_nondetect", "hydro_event",
        # Target columns (parameter-specific)
        "ssc_value", "ssc_log1p",
        "value", "value_log1p",
        "tp_value", "tp_log1p",
        "nitrate_value", "nitrate_log1p",
        "tds_value", "tds_log1p",
        "orthop_value", "orthop_log1p",
        "do_value", "do_log1p",
    }

    sensor_cols = [
        c for c in assembled_df.columns
        if c not in exclude_cols
    ]

    # --- Tier A: Sensor-only ---
    tiers["A_sensor_only"] = {
        "data": assembled_df.copy(),
        "sites": sorted(assembled_df["site_id"].unique()),
        "feature_cols": sensor_cols,
        "description": "Sensor features only (all sites)",
    }

    # --- Tier B: Sensor + basic attributes ---
    basic_cols_to_add = []
    if basic_attrs is not None:
        # Select useful basic columns
        for col in ["drainage_area_km2", "altitude_ft", "huc2"]:
            if col in basic_attrs.columns:
                basic_cols_to_add.append(col)

        if basic_cols_to_add:
            tier_b_data = assembled_df.merge(
                basic_attrs[["site_id"] + basic_cols_to_add],
                on="site_id",
                how="left",
            )
            # Okafor fix: guard HUC2 NaN before astype(str) to prevent "nan" literal
            if "huc2" in tier_b_data.columns:
                mask = tier_b_data["huc2"].notna()
                tier_b_data.loc[mask, "huc2"] = (
                    tier_b_data.loc[mask, "huc2"].astype(int).astype(str).str.zfill(2)
                )

            tiers["B_sensor_basic"] = {
                "data": tier_b_data,
                "sites": sorted(tier_b_data["site_id"].unique()),
                "feature_cols": sensor_cols + basic_cols_to_add,
                "description": "Sensor + basic attributes (all sites)",
            }

    # --- Tier C: Sensor + basic + GAGES-II ---
    if gagesii_attrs is not None and not gagesii_attrs.empty:
        gagesii_sites = set(gagesii_attrs["site_id"])
        tier_c_base = assembled_df[assembled_df["site_id"].isin(gagesii_sites)].copy()

        if basic_cols_to_add:
            tier_c_base = tier_c_base.merge(
                basic_attrs[["site_id"] + basic_cols_to_add],
                on="site_id",
                how="left",
            )

        gagesii_feature_cols = [c for c in gagesii_attrs.columns if c != "site_id"]
        tier_c_data = tier_c_base.merge(gagesii_attrs, on="site_id", how="left")

        # Okafor fix: guard HUC2 NaN
        if "huc2" in tier_c_data.columns:
            mask = tier_c_data["huc2"].notna()
            tier_c_data.loc[mask, "huc2"] = (
                tier_c_data.loc[mask, "huc2"].astype(int).astype(str).str.zfill(2)
            )

        tiers["C_sensor_basic_gagesii"] = {
            "data": tier_c_data,
            "sites": sorted(tier_c_data["site_id"].unique()),
            "feature_cols": sensor_cols + basic_cols_to_add + gagesii_feature_cols,
            "description": f"Sensor + basic + GAGES-II ({len(gagesii_sites)} sites)",
        }

        # Patel: Tier B-restricted to GAGES-II sites for unconfounded comparison with C
        if basic_cols_to_add:
            tier_b_restricted = tier_c_base.copy()  # already filtered to GAGES-II sites
            if "huc2" in tier_b_restricted.columns:
                mask = tier_b_restricted["huc2"].notna()
                tier_b_restricted.loc[mask, "huc2"] = (
                    tier_b_restricted.loc[mask, "huc2"].astype(int).astype(str).str.zfill(2)
                )
            tiers["B_restricted"] = {
                "data": tier_b_restricted,
                "sites": sorted(tier_b_restricted["site_id"].unique()),
                "feature_cols": sensor_cols + basic_cols_to_add,
                "description": f"Sensor + basic (restricted to {len(gagesii_sites)} GAGES-II sites)",
            }

    # Summary
    for name, tier in tiers.items():
        logger.info(
            f"Tier {name}: {len(tier['sites'])} sites, "
            f"{len(tier['feature_cols'])} features, "
            f"{len(tier['data'])} samples"
        )

    return tiers
