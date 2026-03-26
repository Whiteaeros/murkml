"""Download watershed-averaged daily weather from GridMET for all sites.

For each site:
1. Get watershed boundary polygon from NLDI
2. Download GridMET daily precipitation and temperature
3. Spatially average over the watershed
4. Save as daily time series per site

The rolling window features (24hr, 48hr, 7day, 30day precip) are computed
during feature engineering, not here. This script just provides the daily data.

GridMET: 4km resolution, daily, 1979-present, no auth required.

Usage:
    python scripts/download_weather.py [--start-year 2000] [--end-year 2025]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from murkml.provenance import start_run, log_step, log_file, end_run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"
WEATHER_DIR = DATA_DIR / "weather"


def get_all_sites() -> list[str]:
    """Get all site IDs that need weather data."""
    sites = set()

    # Assembled datasets
    for f in (DATA_DIR / "processed").glob("*_paired.parquet"):
        df = pd.read_parquet(f, columns=["site_id"])
        sites.update(df["site_id"].unique())

    # Site catalog
    catalog_path = DATA_DIR / "site_catalog.parquet"
    if catalog_path.exists():
        df = pd.read_parquet(catalog_path)
        sites.update(df["site_id"].unique())

    # Expansion candidates
    exp_path = DATA_DIR / "expansion_candidates.parquet"
    if exp_path.exists():
        df = pd.read_parquet(exp_path)
        sites.update(df["site_id"].unique())

    # Broad discovery results
    disc_path = DATA_DIR / "all_discovered_sites.parquet"
    if disc_path.exists():
        df = pd.read_parquet(disc_path)
        sites.update(df["site_id"].unique())

    return sorted(sites)


def load_site_coordinates() -> pd.DataFrame:
    """Load cached site coordinates (lat/lon from NWIS get_info)."""
    coords_path = DATA_DIR / "site_coordinates.parquet"
    if coords_path.exists():
        return pd.read_parquet(coords_path)
    raise FileNotFoundError(
        f"Site coordinates not found at {coords_path}. "
        f"Run coordinate download first."
    )


def download_site_weather(
    site_id: str,
    lat: float,
    lon: float,
    start_year: int = 2000,
    end_year: int = 2025,
    chunk_years: int = 5,
) -> pd.DataFrame | None:
    """Download GridMET daily precip and temp at site centroid.

    Uses point query (single 4km grid cell) for reliability.
    Downloads in multi-year chunks. Caches per-site as parquet.
    """
    import pygridmet

    cache_dir = WEATHER_DIR / site_id.replace("-", "_")
    cache_dir.mkdir(parents=True, exist_ok=True)
    final_cache = cache_dir / "daily_weather.parquet"

    if final_cache.exists():
        cached = pd.read_parquet(final_cache)
        if len(cached) > 0:
            last_date = pd.to_datetime(cached["date"]).max()
            if last_date.year >= end_year - 1:
                logger.info(f"  [cache] {len(cached)} days through {last_date.date()}")
                return cached

    all_chunks = []

    for yr_start in range(start_year, end_year + 1, chunk_years):
        yr_end = min(yr_start + chunk_years - 1, end_year)
        chunk_file = cache_dir / f"{yr_start}_{yr_end}.parquet"

        if chunk_file.exists():
            chunk = pd.read_parquet(chunk_file)
            if len(chunk) > 0:
                all_chunks.append(chunk)
            continue

        dates = (f"{yr_start}-01-01", f"{yr_end}-12-31")

        # Use centroid (single grid cell at watershed center).
        # Polygon-based watershed averaging is ideal but GridMET's API
        # rejects most basin polygons even after simplification. Centroid
        # at 4km resolution is adequate for watershed-scale weather signals.
        chunk_df = None
        try:
            weather = pygridmet.get_bycoords(
                (lon, lat), dates=dates,
                variables=["pr", "tmmx", "tmmn"],
            )
            precip = weather["pr (mm)"].values
            tmax = weather["tmmx (K)"].values
            tmin = weather["tmmn (K)"].values
            time_vals = weather.index

            tmax_c = tmax - 273.15
            tmin_c = tmin - 273.15

            chunk_df = pd.DataFrame({
                "date": time_vals,
                "precip_mm": precip,
                "tmax_c": tmax_c,
                "tmin_c": tmin_c,
                "tmean_c": (tmax_c + tmin_c) / 2,
            })

        except Exception as e:
            logger.warning(f"    {yr_start}-{yr_end} FAILED: {e}")

        if chunk_df is not None and len(chunk_df) > 0:
            chunk_df.to_parquet(chunk_file, index=False)
            all_chunks.append(chunk_df)
            logger.info(f"    {yr_start}-{yr_end}: {len(chunk_df)} days")
        else:
            logger.warning(f"    {yr_start}-{yr_end}: no data")

        time.sleep(1)  # Brief delay between chunks

    if not all_chunks:
        return None

    result = pd.concat(all_chunks, ignore_index=True)
    result = result.drop_duplicates("date").sort_values("date").reset_index(drop=True)

    # Save combined
    result.to_parquet(final_cache, index=False)
    return result


def main():
    parser = argparse.ArgumentParser(description="Download watershed-averaged daily weather")
    parser.add_argument("--start-year", type=int, default=2006,
                        help="Start year (2006 covers 30-day antecedent for earliest 2007 paired samples)")
    parser.add_argument("--end-year", type=int, default=2025, help="End year")
    args = parser.parse_args()

    start_run("download_weather")
    WEATHER_DIR.mkdir(parents=True, exist_ok=True)

    sites = get_all_sites()
    logger.info(f"Sites needing weather data: {len(sites)}")
    log_step("get_sites", n_sites=len(sites))

    # Load site coordinates (pre-cached from NWIS get_info)
    coords = load_site_coordinates()
    coords_dict = dict(zip(coords["site_id"], zip(coords["latitude"], coords["longitude"])))
    logger.info(f"Loaded coordinates for {len(coords_dict)} sites")

    n_success = 0
    n_failed = 0
    n_cached = 0
    n_no_coords = 0

    for i, site_id in enumerate(sites):
        if (i + 1) % 10 == 0 or i == 0:
            logger.info(f"[{i+1}/{len(sites)}] {site_id}")

        if site_id not in coords_dict:
            n_no_coords += 1
            continue

        lat, lon = coords_dict[site_id]
        if pd.isna(lat) or pd.isna(lon):
            n_no_coords += 1
            continue

        result = download_site_weather(
            site_id, lat, lon,
            start_year=args.start_year,
            end_year=args.end_year,
        )

        if result is not None and len(result) > 0:
            n_success += 1
        else:
            n_failed += 1

        # Progress summary every 50 sites
        if (i + 1) % 50 == 0:
            logger.info(f"  --- Progress: {i+1}/{len(sites)}, {n_success} ok, "
                        f"{n_cached} cached, {n_failed} failed, {n_no_coords} no coords ---")

    logger.info(f"\n{'='*60}")
    logger.info("SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"Success: {n_success}")
    logger.info(f"Cached: {n_cached}")
    logger.info(f"Failed: {n_failed}")
    logger.info(f"Total: {n_success + n_cached + n_failed}")

    log_step("download_complete",
             n_success=n_success, n_cached=n_cached, n_failed=n_failed)
    end_run()


if __name__ == "__main__":
    main()
