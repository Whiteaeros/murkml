"""Catchment attribute processing for murkml.

Handles watershed attribute loading, 3-tier ablation setup, and attribute merging.

Supports two attribute sources:
    StreamCat (preferred, 2019 vintage):
        - 768+ sites, ~83 static features after dropping time-varying columns
        - Already uses internal column names (forest_pct, clay_pct, etc.)
        - Loaded via load_streamcat_attrs()

    GAGES-II (legacy, 2006-2011 vintage):
        - 58 sites, ~20 pruned features
        - Loaded via prune_gagesii() (kept for backward compatibility)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def prune_gagesii(df: pd.DataFrame) -> pd.DataFrame:
    """Prune GAGES-II attributes from ~576 to ~20-25 key features.

    Merges correlated groups to reduce dimensionality for 37-site models.
    Chen review: 44 features is too many for 37 sites. Target 20-25.

    IMPORTANT: This function expects RAW GAGES-II column names (e.g., FORESTNLCD06,
    GEOL_HUNT_DOM_CODE). If the input already has pruned names (e.g., forest_pct,
    geol_class), it returns the input unchanged.

    Args:
        df: GAGES-II matched attributes DataFrame (must have 'site_id' column).

    Returns:
        DataFrame with pruned/merged feature columns + site_id.
    """
    # Guard: detect already-pruned input (bug discovered 2026-03-24)
    if "forest_pct" in df.columns and "FORESTNLCD06" not in df.columns:
        logger.warning(
            "prune_gagesii: input already has pruned column names "
            f"({len(df.columns)} cols, {len(df)} rows). Returning as-is."
        )
        return df

    # Guard: verify enough expected raw columns exist
    expected_raw_cols = [
        "FORESTNLCD06", "CROPSNLCD06", "DEVNLCD06", "GEOL_HUNT_DOM_CODE",
        "CLAYAVE", "SANDAVE", "PERMAVE", "PPTAVG_BASIN", "T_AVG_BASIN",
        "ELEV_MEAN_M_BASIN", "SLOPE_PCT", "BFI_AVE", "CLASS", "AGGECOREGION",
    ]
    n_found = sum(1 for c in expected_raw_cols if c in df.columns)
    if n_found < len(expected_raw_cols) * 0.5:
        raise ValueError(
            f"prune_gagesii: only {n_found}/{len(expected_raw_cols)} expected raw "
            f"GAGES-II columns found. Input may have wrong column names. "
            f"Expected columns like FORESTNLCD06, got: {list(df.columns[:5])}..."
        )

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


def load_streamcat_attrs(data_dir: Path) -> pd.DataFrame:
    """Load StreamCat watershed attributes, dropping time-varying and all-null columns.

    StreamCat has ~159 columns total. After dropping all-null columns and
    time-varying columns (those with a 4-digit year in the name), ~83 static
    features remain.

    CatBoost handles NaN natively, so missing values are NOT filled.

    Args:
        data_dir: Path to data/ directory containing site_attributes_streamcat.parquet.

    Returns:
        DataFrame with site_id + static feature columns.
    """
    path = Path(data_dir) / "site_attributes_streamcat.parquet"
    df = pd.read_parquet(path)
    n_cols_raw = len(df.columns)

    # Drop columns that are entirely null
    all_null_cols = [c for c in df.columns if df[c].isna().all()]
    if all_null_cols:
        logger.info(f"StreamCat: dropping {len(all_null_cols)} all-null columns: {all_null_cols}")
        df = df.drop(columns=all_null_cols)

    # Drop time-varying columns (contain a 4-digit year in the name)
    year_pattern = re.compile(r"\d{4}")
    time_varying_cols = [c for c in df.columns if c != "site_id" and year_pattern.search(c)]
    if time_varying_cols:
        logger.info(f"StreamCat: dropping {len(time_varying_cols)} time-varying columns")
        df = df.drop(columns=time_varying_cols)

    # Ensure geol_class is categorical (dtype=object) if present
    if "geol_class" in df.columns:
        df["geol_class"] = df["geol_class"].astype(object)

    # Deduplicate by site_id — keep first occurrence per site
    # (StreamCat parquet may have one row per site repeated across assembled samples)
    if df["site_id"].duplicated().any():
        df = df.drop_duplicates(subset=["site_id"], keep="first")

    n_features = len(df.columns) - 1  # exclude site_id
    logger.info(
        f"StreamCat: {n_cols_raw} → {n_features} static features, "
        f"{len(df)} sites"
    )
    return df


def validate_gagesii_schema(df: pd.DataFrame, expected_format: str = "pruned") -> None:
    """Validate that a GAGES-II DataFrame has the expected column name format.

    Args:
        df: DataFrame to validate.
        expected_format: "pruned" (forest_pct, geol_class) or "raw" (FORESTNLCD06).

    Raises:
        ValueError: If column names don't match expected format.
    """
    if expected_format == "pruned":
        if "forest_pct" not in df.columns:
            raise ValueError(
                f"Expected pruned GAGES-II format (forest_pct, geol_class, ...) "
                f"but got columns: {list(df.columns[:5])}..."
            )
        if "FORESTNLCD06" in df.columns:
            raise ValueError(
                "DataFrame has raw GAGES-II column names but expected pruned format."
            )
        # Verify categorical columns are string dtype
        for cat_col in ["geol_class", "ecoregion", "reference_class"]:
            if cat_col in df.columns:
                non_null = df[cat_col].dropna()
                if len(non_null) > 0 and non_null.dtype != object:
                    raise ValueError(
                        f"Column {cat_col} should be dtype=object (string) but is "
                        f"{non_null.dtype}. Categorical columns were likely destroyed."
                    )
    elif expected_format == "raw":
        if "FORESTNLCD06" not in df.columns:
            raise ValueError(
                f"Expected raw GAGES-II format (FORESTNLCD06, GEOL_HUNT_DOM_CODE, ...) "
                f"but got columns: {list(df.columns[:5])}..."
            )
    else:
        raise ValueError(f"Unknown format: {expected_format}. Use 'pruned' or 'raw'.")


def _assert_merge_integrity(
    result: pd.DataFrame,
    expected_rows: int,
    label: str,
    check_cols: list[str] | None = None,
) -> None:
    """Post-merge sanity check. Warns on row count changes and all-NaN columns."""
    if len(result) != expected_rows:
        logger.warning(
            f"Merge '{label}': row count changed {expected_rows} → {len(result)}. "
            f"Possible duplicate site_ids in attribute file."
        )
    if check_cols:
        for col in check_cols:
            if col in result.columns and result[col].isna().all():
                logger.warning(
                    f"Merge '{label}': column '{col}' is entirely NaN after merge."
                )


def get_gagesii_original_sites(data_dir: Path) -> set[str]:
    """Return site_ids with genuine GAGES-II attributes (not NLCD backfill).

    Computes: sites in merged gagesii file MINUS sites in nlcd backfill file.
    """
    gagesii_path = data_dir / "site_attributes_gagesii.parquet"
    nlcd_path = data_dir / "site_attributes_nlcd.parquet"

    if not gagesii_path.exists():
        return set()

    gagesii_sites = set(pd.read_parquet(gagesii_path, columns=["site_id"])["site_id"])

    if nlcd_path.exists():
        nlcd_df = pd.read_parquet(nlcd_path)
        # Only count sites that actually got NLCD data (have forest_pct)
        if "forest_pct" in nlcd_df.columns:
            nlcd_sites = set(nlcd_df.dropna(subset=["forest_pct"])["site_id"])
        else:
            nlcd_sites = set()
    else:
        nlcd_sites = set()

    return gagesii_sites - nlcd_sites


def build_feature_tiers(
    assembled_df: pd.DataFrame,
    basic_attrs: pd.DataFrame,
    watershed_attrs: pd.DataFrame | None = None,
) -> dict[str, dict]:
    """Build feature tiers for ablation study.

    Tier A (all sites): Sensor-only features
    Tier B (all sites): Sensor + basic attributes (drainage area, elevation, HUC)
    Tier C (watershed-attr sites): Sensor + basic + watershed attributes
        (StreamCat or GAGES-II — both use site_id + feature columns)

    Args:
        assembled_df: Paired sensor+discrete dataset with site_id column.
        basic_attrs: Basic site attributes (drainage area, elevation, HUC) for all sites.
        watershed_attrs: Watershed attributes (from load_streamcat_attrs or prune_gagesii).
            Must have site_id column + feature columns. Optional.

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

    # --- Tier C: Sensor + basic + watershed attributes ---
    if watershed_attrs is not None and not watershed_attrs.empty:
        ws_sites = set(watershed_attrs["site_id"])
        tier_c_base = assembled_df[assembled_df["site_id"].isin(ws_sites)].copy()

        if basic_cols_to_add:
            n_before = len(tier_c_base)
            tier_c_base = tier_c_base.merge(
                basic_attrs[["site_id"] + basic_cols_to_add],
                on="site_id",
                how="left",
            )
            _assert_merge_integrity(tier_c_base, n_before, "Tier C basic attrs")

        ws_feature_cols = [c for c in watershed_attrs.columns if c != "site_id"]
        n_before = len(tier_c_base)
        tier_c_data = tier_c_base.merge(watershed_attrs, on="site_id", how="left")
        _assert_merge_integrity(
            tier_c_data, n_before, "Tier C watershed",
            check_cols=["forest_pct", "clay_pct", "precip_mean_mm"],
        )

        # Okafor fix: guard HUC2 NaN
        if "huc2" in tier_c_data.columns:
            mask = tier_c_data["huc2"].notna()
            tier_c_data.loc[mask, "huc2"] = (
                tier_c_data.loc[mask, "huc2"].astype(int).astype(str).str.zfill(2)
            )

        tiers["C_sensor_basic_watershed"] = {
            "data": tier_c_data,
            "sites": sorted(tier_c_data["site_id"].unique()),
            "feature_cols": sensor_cols + basic_cols_to_add + ws_feature_cols,
            "description": f"Sensor + basic + watershed ({len(ws_sites)} sites)",
        }

    # Summary
    for name, tier in tiers.items():
        logger.info(
            f"Tier {name}: {len(tier['sites'])} sites, "
            f"{len(tier['feature_cols'])} features, "
            f"{len(tier['data'])} samples"
        )

    return tiers
