"""Fill land cover data for sites not in GAGES-II using NLCD via pygeohydro.

For each unmatched site:
1. Get watershed boundary from NLDI (sync requests)
2. Pull NLCD 2019 land cover raster for that watershed
3. Compute land cover percentages
4. Save as site_attributes_nlcd.parquet

Usage:
    python scripts/fill_landcover_nlcd.py
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from shapely.geometry import shape

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"

# NLCD land cover classes
NLCD_CLASSES = {
    11: "open_water", 12: "ice_snow",
    21: "developed_open", 22: "developed_low", 23: "developed_med", 24: "developed_high",
    31: "barren",
    41: "deciduous_forest", 42: "evergreen_forest", 43: "mixed_forest",
    51: "dwarf_scrub", 52: "shrub_scrub",
    71: "grassland", 72: "sedge", 73: "lichens", 74: "moss",
    81: "pasture_hay", 82: "cultivated_crops",
    90: "woody_wetland", 95: "herbaceous_wetland",
}


def get_unmatched_sites() -> list[str]:
    """Get sites not in GAGES-II."""
    assembled = pd.read_parquet(DATA_DIR / "processed" / "turbidity_ssc_paired.parquet")
    all_sites = set(assembled["site_id"].unique())

    gagesii_path = DATA_DIR / "site_attributes_gagesii.parquet"
    if gagesii_path.exists():
        gagesii = pd.read_parquet(gagesii_path)
        matched_sites = set(gagesii["site_id"])
    else:
        matched_sites = set()

    return sorted(all_sites - matched_sites)


def get_basin_geometry(site_id: str):
    """Get watershed boundary from NLDI as a shapely geometry."""
    url = f"https://api.water.usgs.gov/nldi/linked-data/nwissite/{site_id}/basin"
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200:
        return None
    geojson = resp.json()
    features = geojson.get("features", [])
    if not features:
        return None
    return shape(features[0]["geometry"])


def compute_nlcd_stats(geom) -> dict | None:
    """Pull NLCD land cover raster for a geometry and compute class percentages."""
    import geopandas as gpd
    from pygeohydro import nlcd_bygeom

    gdf = gpd.GeoDataFrame({"geometry": [geom]}, index=[0], crs="EPSG:4326")

    try:
        result = nlcd_bygeom(
            gdf,
            resolution=100,  # 100m for speed (vs 30m native)
            years={"cover": [2019]},
            region="L48",
        )
    except Exception as e:
        logger.warning(f"  NLCD API error: {e}")
        return None

    if not result or 0 not in result:
        return None

    ds = result[0]

    # Extract the cover layer
    if "cover_2019" not in ds:
        logger.warning(f"  No cover_2019 in dataset, keys: {list(ds.data_vars)}")
        return None

    cover = ds["cover_2019"].values.flatten()
    cover = cover[~np.isnan(cover)].astype(int)
    # Exclude nodata/background (class 127, 0, etc.)
    cover = cover[(cover >= 11) & (cover <= 95)]

    if len(cover) == 0:
        return None

    total = len(cover)
    stats = {}
    for code, name in NLCD_CLASSES.items():
        count = np.sum(cover == code)
        stats[f"nlcd_{name}_pct"] = float(count / total * 100)

    # Broad categories matching GAGES-II naming
    stats["forest_pct"] = (
        stats.get("nlcd_deciduous_forest_pct", 0) +
        stats.get("nlcd_evergreen_forest_pct", 0) +
        stats.get("nlcd_mixed_forest_pct", 0)
    )
    stats["agriculture_pct"] = (
        stats.get("nlcd_pasture_hay_pct", 0) +
        stats.get("nlcd_cultivated_crops_pct", 0)
    )
    stats["developed_pct"] = (
        stats.get("nlcd_developed_open_pct", 0) +
        stats.get("nlcd_developed_low_pct", 0) +
        stats.get("nlcd_developed_med_pct", 0) +
        stats.get("nlcd_developed_high_pct", 0)
    )
    stats["wetland_pct"] = (
        stats.get("nlcd_woody_wetland_pct", 0) +
        stats.get("nlcd_herbaceous_wetland_pct", 0)
    )

    return stats


def main():
    unmatched = get_unmatched_sites()
    logger.info(f"Sites needing land cover data: {len(unmatched)}")

    if not unmatched:
        logger.info("All sites have attributes!")
        return

    results = []
    for i, site_id in enumerate(unmatched):
        logger.info(f"[{i+1}/{len(unmatched)}] {site_id}")

        # Step 1: Get basin boundary
        try:
            geom = get_basin_geometry(site_id)
        except Exception as e:
            logger.warning(f"  Basin error: {e}")
            results.append({"site_id": site_id})
            continue

        if geom is None:
            logger.warning(f"  No basin geometry")
            results.append({"site_id": site_id})
            continue

        # Compute drainage area from geometry
        import geopandas as gpd
        basin_gdf = gpd.GeoDataFrame({"geometry": [geom]}, crs="EPSG:4326")
        basin_proj = basin_gdf.to_crs("EPSG:5070")  # Albers Equal Area
        drainage_area_km2 = float(basin_proj.geometry.area.iloc[0] / 1e6)

        # Step 2: Pull NLCD
        stats = compute_nlcd_stats(geom)

        if stats:
            stats["site_id"] = site_id
            stats["drainage_area_km2"] = drainage_area_km2
            results.append(stats)
            logger.info(f"  area={drainage_area_km2:.1f} km² "
                        f"forest={stats.get('forest_pct', 0):.1f}% "
                        f"ag={stats.get('agriculture_pct', 0):.1f}% "
                        f"dev={stats.get('developed_pct', 0):.1f}%")
        else:
            results.append({"site_id": site_id, "drainage_area_km2": drainage_area_km2})
            logger.warning(f"  Got basin ({drainage_area_km2:.1f} km²) but no NLCD data")

        time.sleep(2)

    df = pd.DataFrame(results)
    out_path = DATA_DIR / "site_attributes_nlcd.parquet"
    df.to_parquet(out_path, index=False)

    has_lc = df["forest_pct"].notna().sum() if "forest_pct" in df.columns else 0
    logger.info(f"\nSaved: {out_path}")
    logger.info(f"Sites with land cover data: {has_lc} of {len(unmatched)}")


if __name__ == "__main__":
    main()
