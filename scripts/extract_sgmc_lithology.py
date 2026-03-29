"""Extract SGMC bedrock lithology for each site via point-in-polygon lookup.

Reads site coordinates, projects to SGMC CRS (Albers Equal Area),
does spatial join against SGMC_Geology polygons, and saves per-site lithology.

Then correlates lithology with turbidity-SSC slope to test whether
bedrock type predicts the turb-SSC relationship.

Usage:
    python scripts/extract_sgmc_lithology.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import stats
from shapely.geometry import Point

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SGMC_GDB = DATA_DIR / "sgmc" / "USGS_SGMC_Geodatabase" / "USGS_StateGeologicMapCompilation_ver1.1.gdb"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_sites() -> gpd.GeoDataFrame:
    """Load site coordinates and create GeoDataFrame in SGMC CRS."""
    attrs = pd.read_parquet(DATA_DIR / "site_attributes.parquet")
    logger.info(f"Loaded {len(attrs)} sites from site_attributes.parquet")

    # Filter to sites with coordinates
    attrs = attrs.dropna(subset=["latitude", "longitude"])
    logger.info(f"  {len(attrs)} sites with coordinates")

    # Create GeoDataFrame in WGS84 (EPSG:4269 = NAD83, close enough to WGS84 for this)
    geometry = [Point(lon, lat) for lon, lat in zip(attrs["longitude"], attrs["latitude"])]
    sites_gdf = gpd.GeoDataFrame(attrs, geometry=geometry, crs="EPSG:4269")

    # Reproject to SGMC CRS (Albers Equal Area USGS version = ESRI:102039)
    # Read CRS from the actual geodatabase to ensure exact match
    import pyogrio
    info = pyogrio.read_info(str(SGMC_GDB), layer="SGMC_Geology")
    sgmc_crs = info["crs"]
    sites_gdf = sites_gdf.to_crs(sgmc_crs)
    logger.info(f"  Reprojected to SGMC CRS")

    return sites_gdf


def extract_lithology(sites_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Do point-in-polygon join of sites against SGMC_Geology.

    Uses bbox filter to avoid loading the entire national dataset.
    """
    # Get bounding box of all sites (with buffer)
    bounds = sites_gdf.total_bounds  # (minx, miny, maxx, maxy)
    buffer = 50000  # 50 km buffer in meters (Albers)
    bbox = (
        bounds[0] - buffer,
        bounds[1] - buffer,
        bounds[2] + buffer,
        bounds[3] + buffer,
    )
    logger.info(f"Site bbox (Albers): {bounds}")
    logger.info(f"Loading SGMC polygons within buffered bbox...")

    # Read SGMC with spatial filter - only columns we need
    cols_to_read = [
        "STATE", "UNIT_NAME", "MAJOR1", "MAJOR2", "MAJOR3",
        "GENERALIZED_LITH", "AGE_MIN", "AGE_MAX",
    ]
    sgmc = gpd.read_file(
        str(SGMC_GDB),
        layer="SGMC_Geology",
        bbox=bbox,
        columns=cols_to_read,
    )
    logger.info(f"  Loaded {len(sgmc)} SGMC polygons within bbox")

    # Spatial join: for each site point, find the polygon it falls within
    result = gpd.sjoin(sites_gdf, sgmc, how="left", predicate="within")
    logger.info(f"  Spatial join: {result['GENERALIZED_LITH'].notna().sum()}/{len(result)} sites matched")

    # Handle duplicates (site falling on polygon boundary → multiple matches)
    # Keep the first match (they should be the same or very similar)
    if result.index.duplicated().any():
        n_dup = result.index.duplicated().sum()
        logger.warning(f"  {n_dup} duplicate matches, keeping first")
        result = result[~result.index.duplicated(keep="first")]

    return result


def analyze_correlations(df: pd.DataFrame) -> pd.DataFrame:
    """Compute Spearman correlation between lithology and turb-SSC slope."""
    # Load turb-SSC params
    params = pd.read_parquet(DATA_DIR / "processed" / "site_turb_ssc_params.parquet")
    logger.info(f"Loaded {len(params)} sites with turb-SSC params")

    # Merge
    merged = df.merge(params, on="site_id", how="inner")
    logger.info(f"  {len(merged)} sites with both lithology and turb-SSC params")

    # --- Analysis 1: GENERALIZED_LITH categories ---
    logger.info("\n=== GENERALIZED_LITH vs turb_ssc_slope ===")
    gen_lith_counts = merged["GENERALIZED_LITH"].value_counts()
    logger.info(f"Categories (n >= 5):")
    for cat, count in gen_lith_counts.items():
        if count >= 5:
            subset = merged[merged["GENERALIZED_LITH"] == cat]["turb_ssc_slope"]
            logger.info(f"  {cat}: n={count}, median_slope={subset.median():.3f}, "
                       f"mean={subset.mean():.3f}, std={subset.std():.3f}")

    # Kruskal-Wallis test across categories with n >= 5
    groups = []
    group_names = []
    for cat, count in gen_lith_counts.items():
        if count >= 5:
            groups.append(merged[merged["GENERALIZED_LITH"] == cat]["turb_ssc_slope"].values)
            group_names.append(cat)

    if len(groups) >= 2:
        kw_stat, kw_p = stats.kruskal(*groups)
        logger.info(f"\n  Kruskal-Wallis: H={kw_stat:.2f}, p={kw_p:.4f}")

    # --- Analysis 2: MAJOR1 rock types ---
    logger.info("\n=== MAJOR1 (specific rock type) vs turb_ssc_slope ===")
    major1_counts = merged["MAJOR1"].value_counts()
    logger.info(f"Rock types (n >= 3):")
    for rock, count in major1_counts.items():
        if count >= 3:
            subset = merged[merged["MAJOR1"] == rock]["turb_ssc_slope"]
            logger.info(f"  {rock}: n={count}, median_slope={subset.median():.3f}, "
                       f"mean={subset.mean():.3f}")

    # --- Analysis 3: One-hot encode and compute Spearman for each category ---
    logger.info("\n=== Spearman correlations (one-hot) ===")
    results_rows = []

    # GENERALIZED_LITH one-hot
    for cat in gen_lith_counts.index:
        if gen_lith_counts[cat] >= 5:
            binary = (merged["GENERALIZED_LITH"] == cat).astype(int)
            rho, p = stats.spearmanr(binary, merged["turb_ssc_slope"])
            results_rows.append({
                "feature": f"gen_lith_{cat}",
                "field": "GENERALIZED_LITH",
                "category": cat,
                "n_sites": int(gen_lith_counts[cat]),
                "spearman_rho": rho,
                "p_value": p,
                "median_slope": merged[merged["GENERALIZED_LITH"] == cat]["turb_ssc_slope"].median(),
            })

    # MAJOR1 one-hot
    for rock in major1_counts.index:
        if major1_counts[rock] >= 3:
            binary = (merged["MAJOR1"] == rock).astype(int)
            rho, p = stats.spearmanr(binary, merged["turb_ssc_slope"])
            results_rows.append({
                "feature": f"major1_{rock}",
                "field": "MAJOR1",
                "category": rock,
                "n_sites": int(major1_counts[rock]),
                "spearman_rho": rho,
                "p_value": p,
                "median_slope": merged[merged["MAJOR1"] == rock]["turb_ssc_slope"].median(),
            })

    corr_df = pd.DataFrame(results_rows).sort_values("p_value")
    logger.info("\nTop correlations by p-value:")
    for _, row in corr_df.head(20).iterrows():
        sig = "***" if row["p_value"] < 0.001 else "**" if row["p_value"] < 0.01 else "*" if row["p_value"] < 0.05 else ""
        logger.info(f"  {row['feature']:40s}  rho={row['spearman_rho']:+.3f}  p={row['p_value']:.4f}{sig}  n={row['n_sites']}")

    return corr_df


def main():
    logger.info("=" * 60)
    logger.info("SGMC BEDROCK LITHOLOGY EXTRACTION")
    logger.info("=" * 60)

    # Step 1: Load sites
    sites_gdf = load_sites()

    # Step 2: Extract lithology via spatial join
    result = extract_lithology(sites_gdf)

    # Step 3: Save per-site lithology
    output_cols = [
        "site_id", "latitude", "longitude",
        "STATE", "UNIT_NAME", "MAJOR1", "MAJOR2", "MAJOR3",
        "GENERALIZED_LITH", "AGE_MIN", "AGE_MAX",
    ]
    available_cols = [c for c in output_cols if c in result.columns]
    site_lithology = result[available_cols].copy()

    output_path = DATA_DIR / "sgmc" / "site_lithology.parquet"
    site_lithology.to_parquet(output_path, index=False)
    logger.info(f"\nSaved site lithology to {output_path}")
    logger.info(f"  {len(site_lithology)} sites, {site_lithology['GENERALIZED_LITH'].notna().sum()} with lithology")

    # Step 4: Correlation analysis
    corr_df = analyze_correlations(site_lithology)

    # Save correlation results
    corr_path = DATA_DIR / "sgmc" / "lithology_slope_correlations.parquet"
    corr_df.to_parquet(corr_path, index=False)
    logger.info(f"\nSaved correlations to {corr_path}")

    # Also save a human-readable CSV
    corr_csv = DATA_DIR / "sgmc" / "lithology_slope_correlations.csv"
    corr_df.to_csv(corr_csv, index=False, float_format="%.4f")
    logger.info(f"Saved CSV to {corr_csv}")

    # Summary statistics
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    n_sig = (corr_df["p_value"] < 0.05).sum()
    logger.info(f"Total lithology categories tested: {len(corr_df)}")
    logger.info(f"Significant at p < 0.05: {n_sig}")
    if n_sig > 0:
        logger.info("\nSignificant correlations:")
        for _, row in corr_df[corr_df["p_value"] < 0.05].iterrows():
            logger.info(f"  {row['feature']:40s}  rho={row['spearman_rho']:+.3f}  p={row['p_value']:.4f}")


if __name__ == "__main__":
    main()
