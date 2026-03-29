"""
Compute % of each watershed covered by each GENERALIZED_LITH category
from the USGS SGMC geodatabase.

Strategy: Load SGMC with spatial index, process one basin at a time,
use spatial index for fast candidate selection, compute intersection areas.
"""

import geopandas as gpd
import pandas as pd
import numpy as np
import time
import warnings
import os
import sys

warnings.filterwarnings("ignore", category=UserWarning)

# Paths
GDB_PATH = "data/sgmc/USGS_SGMC_Geodatabase/USGS_StateGeologicMapCompilation_ver1.1.gdb"
BASINS_PATH = "data/sgmc/watershed_basins.parquet"
OUTPUT_PATH = "data/sgmc/watershed_lithology_pct.parquet"
CHECKPOINT_PATH = "data/sgmc/_lithology_checkpoint.parquet"

# Skip basins larger than this (km2) - likely bad delineations
MAX_BASIN_AREA_KM2 = 200_000

SGMC_CRS = "ESRI:102039"  # Albers Equal Area


def load_sgmc():
    """Load SGMC geology layer with only needed columns."""
    print("Loading SGMC geology layer...")
    t0 = time.time()
    sgmc = gpd.read_file(
        GDB_PATH,
        layer="SGMC_Geology",
        columns=["GENERALIZED_LITH"],
    )
    print(f"  Loaded {len(sgmc)} polygons in {time.time()-t0:.0f}s")
    print(f"  CRS: {sgmc.crs}")
    # Build spatial index (auto-built by geopandas but let's be explicit)
    _ = sgmc.sindex
    return sgmc


def process_basin(basin_geom, sgmc, basin_area_m2):
    """Compute lithology percentages for one basin polygon."""
    # Get candidate SGMC polygons via spatial index
    candidates_idx = list(sgmc.sindex.query(basin_geom, predicate="intersects"))
    if not candidates_idx:
        return {}

    candidates = sgmc.iloc[candidates_idx]

    # Compute intersection areas
    results = {}
    for idx, row in candidates.iterrows():
        try:
            intersection = basin_geom.intersection(row.geometry)
            if intersection.is_empty:
                continue
            area = intersection.area
            lith = row["GENERALIZED_LITH"]
            if lith in results:
                results[lith] += area
            else:
                results[lith] = area
        except Exception:
            continue

    # Convert to percentages
    total = sum(results.values())
    if total == 0:
        return {}
    # Use basin_area_m2 as denominator for more accurate %
    # but if intersections exceed basin area (due to projection), use total
    denom = max(basin_area_m2, total)
    return {k: (v / denom) * 100 for k, v in results.items()}


def main():
    # Load basins and reproject to SGMC CRS
    print("Loading basins...")
    basins = gpd.read_parquet(BASINS_PATH)
    basins_albers = basins.to_crs(SGMC_CRS)
    basins_albers["area_m2"] = basins_albers.area

    # Filter out oversized basins
    area_km2 = basins_albers["area_m2"] / 1e6
    oversized = area_km2 > MAX_BASIN_AREA_KM2
    n_oversized = oversized.sum()
    print(f"Skipping {n_oversized} basins > {MAX_BASIN_AREA_KM2} km2")
    basins_work = basins_albers[~oversized].copy()
    print(f"Processing {len(basins_work)} basins")

    # Check for checkpoint
    done_sites = set()
    results_list = []
    if os.path.exists(CHECKPOINT_PATH):
        checkpoint = pd.read_parquet(CHECKPOINT_PATH)
        done_sites = set(checkpoint["site_id"].tolist())
        results_list = checkpoint.to_dict("records")
        print(f"Resuming from checkpoint: {len(done_sites)} already done")

    # Load SGMC
    sgmc = load_sgmc()

    # Process each basin
    n_total = len(basins_work)
    n_success = len(done_sites)
    n_fail = 0
    t_start = time.time()

    for i, (site_id, row) in enumerate(basins_work.iterrows()):
        if site_id in done_sites:
            continue

        try:
            pcts = process_basin(row.geometry, sgmc, row["area_m2"])
            if pcts:
                record = {"site_id": site_id}
                record.update(pcts)
                results_list.append(record)
                n_success += 1
            else:
                n_fail += 1
        except Exception as e:
            n_fail += 1
            if n_fail <= 5:
                print(f"  FAIL {site_id}: {e}")

        # Progress
        done = i + 1
        if done % 10 == 0 or done == n_total:
            elapsed = time.time() - t_start
            rate = done / elapsed if elapsed > 0 else 0
            eta = (n_total - done) / rate if rate > 0 else 0
            print(
                f"  [{done}/{n_total}] success={n_success} fail={n_fail} "
                f"rate={rate:.1f}/s ETA={eta:.0f}s",
                flush=True,
            )

        # Save checkpoint every 50
        if done % 50 == 0:
            df_ckpt = pd.DataFrame(results_list)
            df_ckpt.to_parquet(CHECKPOINT_PATH)

    # Build final DataFrame
    df = pd.DataFrame(results_list)

    # Get all lithology columns (everything except site_id)
    lith_cols = [c for c in df.columns if c != "site_id"]
    df[lith_cols] = df[lith_cols].fillna(0)

    # Sort columns
    lith_cols.sort()
    df = df[["site_id"] + lith_cols]

    df.to_parquet(OUTPUT_PATH, index=False)
    print(f"\nSaved {len(df)} sites to {OUTPUT_PATH}")
    print(f"  {len(lith_cols)} lithology categories")
    print(f"  Success: {n_success}, Failed: {n_fail}, Skipped oversized: {n_oversized}")

    # Clean up checkpoint
    if os.path.exists(CHECKPOINT_PATH):
        os.remove(CHECKPOINT_PATH)

    return df


if __name__ == "__main__":
    main()
