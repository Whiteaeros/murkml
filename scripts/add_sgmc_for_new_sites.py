"""
Compute SGMC watershed lithology for 9 new extreme-event sites and
append to data/sgmc/sgmc_features_for_model.parquet.

Uses the same watershed-overlay approach as compute_watershed_lithology.py:
1. Fetch upstream basins from NLDI
2. Reproject to SGMC Albers Equal Area CRS
3. Compute area-weighted GENERALIZED_LITH percentages
4. Map lithology names to sgmc_* column naming convention
5. Append to sgmc_features_for_model.parquet
"""

import json
import time
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from pynhd import NLDI
from shapely.errors import GEOSException

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

ROOT = Path(__file__).resolve().parent.parent
SGMC_GDB = ROOT / "data" / "sgmc" / "USGS_SGMC_Geodatabase" / "USGS_StateGeologicMapCompilation_ver1.1.gdb"
BASINS_CACHE = ROOT / "data" / "sgmc" / "watershed_basins.parquet"
SGMC_MODEL_FEATURES = ROOT / "data" / "sgmc" / "sgmc_features_for_model.parquet"

# The 9 real new sites (USGS-14803000 is a duplicate of 01480300 and is excluded)
NEW_SITES = [
    "USGS-01472157",
    "USGS-01480300",
    "USGS-06882510",
    "USGS-06902000",
    "USGS-07170000",
    "USGS-09153270",
    "USGS-09365000",
    "USGS-09368000",
    "USGS-12100490",
]


def fetch_basins_for_sites(site_ids: list[str]) -> gpd.GeoDataFrame:
    """Fetch upstream watershed basins from NLDI for the given sites, updating cache."""
    nldi = NLDI()

    # Load existing cache
    if BASINS_CACHE.exists():
        cached = gpd.read_parquet(BASINS_CACHE)
        cached_ids = set(cached.index.tolist())
        print(f"  Loaded {len(cached_ids)} basins from cache")
    else:
        cached = None
        cached_ids = set()

    to_fetch = [s for s in site_ids if s not in cached_ids]
    print(f"  Need to fetch {len(to_fetch)} new basins: {to_fetch}")

    new_basins = []
    for site_id in to_fetch:
        print(f"  Fetching basin for {site_id}...", end=" ", flush=True)
        t0 = time.time()
        try:
            result = nldi.get_basins(site_id)
            result.index.name = "site_id"
            new_basins.append(result)
            print(f"ok ({time.time()-t0:.1f}s)")
        except Exception as e:
            print(f"FAILED: {e}")

    if new_basins:
        all_new = pd.concat(new_basins)
        if cached is not None:
            combined = pd.concat([cached, all_new])
            combined = combined[~combined.index.duplicated(keep="last")]
        else:
            combined = all_new
        combined.to_parquet(BASINS_CACHE)
        print(f"  Updated cache: {len(combined)} total basins")
        return combined
    else:
        return cached


def compute_lithology_for_basin(site_id: str, basin_geom, sgmc_gdb: str) -> dict | None:
    """Load SGMC polygons within basin bbox and compute area-weighted lithology fractions."""
    if basin_geom is None or basin_geom.is_empty:
        print(f"  {site_id}: empty basin geometry")
        return None

    bounds = basin_geom.bounds  # (minx, miny, maxx, maxy)
    buf = 1000  # 1km buffer in metres
    bbox = (bounds[0] - buf, bounds[1] - buf, bounds[2] + buf, bounds[3] + buf)

    try:
        sgmc = gpd.read_file(
            sgmc_gdb,
            layer="SGMC_Geology",
            columns=["GENERALIZED_LITH"],
            bbox=bbox,
            engine="pyogrio",
        )
    except Exception as e:
        print(f"  {site_id}: SGMC read error: {e}")
        return None

    if len(sgmc) == 0:
        print(f"  {site_id}: no SGMC polygons in bbox")
        return None

    try:
        intersections = sgmc.intersection(basin_geom)
    except GEOSException:
        try:
            basin_geom = basin_geom.buffer(0)
            intersections = sgmc.intersection(basin_geom)
        except GEOSException as e:
            print(f"  {site_id}: geometry error: {e}")
            return None

    areas = intersections.area
    sgmc = sgmc.copy()
    sgmc["intersect_area"] = areas.values
    sgmc = sgmc[sgmc["intersect_area"] > 0]

    if len(sgmc) == 0:
        print(f"  {site_id}: no intersecting areas")
        return None

    lith_areas = sgmc.groupby("GENERALIZED_LITH")["intersect_area"].sum()
    total_area = lith_areas.sum()
    if total_area <= 0:
        return None

    result = (lith_areas / total_area * 100).to_dict()
    result["site_id"] = site_id
    return result


# Exact mapping from SGMC GENERALIZED_LITH values to sgmc_* column names
# Derived from watershed_lithology_pct.parquet raw columns vs sgmc_features_for_model.parquet
LITH_NAME_TO_COL = {
    "Igneous and Metamorphic, undifferentiated": "sgmc_igneous_metamorphic_undifferentiated",
    "Igneous and Sedimentary, undifferentiated": "sgmc_igneous_sedimentary_undifferentiated",
    "Igneous, intrusive": "sgmc_igneous_intrusive",
    "Igneous, undifferentiated": "sgmc_igneous_undifferentiated",
    "Igneous, volcanic": "sgmc_igneous_volcanic",
    "Melange": "sgmc_melange",
    "Metamorphic and Sedimentary, undifferentiated": "sgmc_metamorphic_sedimentary_undifferentiated",
    "Metamorphic, amphibolite": "sgmc_metamorphic_amphibolite",
    "Metamorphic, carbonate": "sgmc_metamorphic_carbonate",
    "Metamorphic, gneiss": "sgmc_metamorphic_gneiss",
    "Metamorphic, granulite": "sgmc_metamorphic_granulite",
    "Metamorphic, intrusive": "sgmc_metamorphic_intrusive",
    "Metamorphic, other": "sgmc_metamorphic_other",
    "Metamorphic, schist": "sgmc_metamorphic_schist",
    "Metamorphic, sedimentary": "sgmc_metamorphic_sedimentary",
    "Metamorphic, sedimentary clastic": "sgmc_metamorphic_sedimentary_clastic",
    "Metamorphic, serpentinite": "sgmc_metamorphic_serpentinite",
    "Metamorphic, undifferentiated": "sgmc_metamorphic_undifferentiated",
    "Metamorphic, volcanic": "sgmc_metamorphic_volcanic",
    "Sedimentary, carbonate": "sgmc_sedimentary_carbonate",
    "Sedimentary, chemical": "sgmc_sedimentary_chemical",
    "Sedimentary, clastic": "sgmc_sedimentary_clastic",
    "Sedimentary, iron formation, undifferentiated": "sgmc_sedimentary_iron_formation_undifferentiated",
    "Sedimentary, undifferentiated": "sgmc_sedimentary_undifferentiated",
    "Tectonite, undifferentiated": "sgmc_tectonite_undifferentiated",
    "Unconsolidated and Sedimentary, undifferentiated": "sgmc_unconsolidated_sedimentary_undifferentiated",
    "Unconsolidated, undifferentiated": "sgmc_unconsolidated_undifferentiated",
    "Water": "sgmc_water",
}


def lith_name_to_col(lith: str) -> str | None:
    """Convert SGMC GENERALIZED_LITH value to sgmc_* column name.

    Returns None if the lithology name is not in the known mapping.
    """
    return LITH_NAME_TO_COL.get(lith, None)


def main():
    print("=" * 60)
    print("SGMC LITHOLOGY FOR NEW SITES")
    print("=" * 60)

    # Step 1: Fetch basins
    print("\n=== Step 1: Fetch watershed basins ===")
    basins = fetch_basins_for_sites(NEW_SITES)

    # Check which new sites got basins
    available = [s for s in NEW_SITES if s in basins.index]
    missing = [s for s in NEW_SITES if s not in basins.index]
    print(f"\nBasins available for {len(available)}/{len(NEW_SITES)} sites")
    if missing:
        print(f"  Missing: {missing}")

    if not available:
        print("ERROR: No basins available, cannot continue")
        return

    # Step 2: Reproject to SGMC CRS
    print("\n=== Step 2: Reproject to SGMC Albers ===")
    sgmc_info = pyogrio.read_info(str(SGMC_GDB), layer="SGMC_Geology")
    sgmc_crs = sgmc_info["crs"]
    basins_sub = basins.loc[available]
    basins_albers = basins_sub.to_crs(sgmc_crs)
    print(f"  Reprojected {len(basins_albers)} basins")

    # Step 3: Compute lithology per site
    print("\n=== Step 3: Compute lithology fractions ===")
    sgmc_gdb = str(SGMC_GDB)
    site_results = []

    for site_id, row in basins_albers.iterrows():
        print(f"  Processing {site_id}...", end=" ", flush=True)
        t0 = time.time()
        result = compute_lithology_for_basin(site_id, row.geometry, sgmc_gdb)
        if result is not None:
            site_results.append(result)
            liths = [k for k in result if k != "site_id"]
            print(f"ok ({time.time()-t0:.1f}s) — {len(liths)} lith types")
        else:
            # Insert zero row for this site (no lithology data)
            site_results.append({"site_id": site_id})
            print(f"no data ({time.time()-t0:.1f}s) — zero row inserted")

    # Step 4: Map to existing column schema
    print("\n=== Step 4: Build rows in model feature schema ===")

    # Load existing features to get the column list
    existing = pd.read_parquet(SGMC_MODEL_FEATURES)
    existing_cols = list(existing.columns)  # [site_id, sgmc_igneous_metamorphic_undiff, ...]
    lith_cols = [c for c in existing_cols if c != "site_id"]
    print(f"  Existing schema: {len(lith_cols)} lithology columns")

    # Build a mapping from GENERALIZED_LITH raw names → sgmc_* column names
    # First determine all raw lith names from our results
    all_raw_liths = set()
    for r in site_results:
        all_raw_liths.update(k for k in r if k != "site_id")

    print(f"  Raw GENERALIZED_LITH types found: {sorted(all_raw_liths)}")

    # Create new rows in the existing schema
    new_rows = []
    for r in site_results:
        row_dict = {"site_id": r["site_id"]}
        # Init all lith cols to 0
        for col in lith_cols:
            row_dict[col] = 0.0
        # Fill in values
        for raw_lith, pct in r.items():
            if raw_lith == "site_id":
                continue
            col_name = lith_name_to_col(raw_lith)
            if col_name is None:
                print(f"  WARNING: unknown lith type '{raw_lith}' — skipping (not in LITH_NAME_TO_COL mapping)")
                continue
            if col_name in row_dict:
                row_dict[col_name] += pct
            else:
                print(f"  WARNING: col '{col_name}' not in existing schema — skipping")
                continue
        new_rows.append(row_dict)

    new_df = pd.DataFrame(new_rows)
    # Ensure all existing columns present (fill with 0 if missing)
    for col in existing_cols:
        if col not in new_df.columns:
            new_df[col] = 0.0

    print(f"\n  New rows shape: {new_df.shape}")
    print(f"  Sites: {new_df['site_id'].tolist()}")

    # Step 5: Append to model features
    print("\n=== Step 5: Append to sgmc_features_for_model.parquet ===")
    # Remove any existing rows for these sites (shouldn't exist, but be safe)
    existing_clean = existing[~existing["site_id"].isin(NEW_SITES)]
    combined = pd.concat([existing_clean, new_df], ignore_index=True)

    # Align columns
    all_cols = list(existing.columns)
    for c in new_df.columns:
        if c not in all_cols:
            all_cols.append(c)
    combined = combined.reindex(columns=all_cols, fill_value=0.0)
    # Fix site_id column dtype
    combined["site_id"] = combined["site_id"].astype(str)

    combined.to_parquet(SGMC_MODEL_FEATURES, index=False)
    print(f"  Saved {len(combined)} rows ({len(existing_clean)} original + {len(new_df)} new)")
    print(f"  Shape: {combined.shape}")

    # Verification
    print("\n=== Verification ===")
    final = pd.read_parquet(SGMC_MODEL_FEATURES)
    print(f"  Final file: {final.shape}")
    for s in NEW_SITES:
        row = final[final["site_id"] == s]
        if len(row) > 0:
            lith_sum = row.iloc[0][lith_cols].sum()
            dominant = row.iloc[0][lith_cols].idxmax()
            print(f"  {s}: lith_sum={lith_sum:.1f}%, dominant={dominant}")
        else:
            print(f"  {s}: NOT FOUND in output!")

    print("\nDone!")


if __name__ == "__main__":
    main()
