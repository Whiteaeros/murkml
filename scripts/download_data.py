"""Download continuous sensor + discrete sample data for paired sites.

This script fetches all available data for selected sites from the USGS API.
Downloads are cached as Parquet files so the script is resume-safe.

Usage:
    python scripts/download_data.py [--n-sites 20] [--years 10]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dataretrieval import waterdata

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Continuous parameters to fetch for every site
CONTINUOUS_PARAMS = {
    "63680": "turbidity_fnu",
    "00095": "conductance",
    "00300": "do",
    "00400": "ph",
    "00010": "temp",
    "00060": "discharge",
}

DATA_DIR = Path(__file__).parent.parent / "data"


def select_sites(n_sites: int = 20) -> pd.DataFrame:
    """Select top N sites by SSC sample count from site catalog."""
    catalog_path = DATA_DIR / "site_catalog.parquet"
    if not catalog_path.exists():
        logger.error(f"Site catalog not found at {catalog_path}")
        logger.error("Run site discovery first.")
        sys.exit(1)

    df = pd.read_parquet(catalog_path)
    # Balance across states: take proportional from each
    selected = []
    for state, group in df.groupby("state"):
        n_from_state = max(1, round(n_sites * len(group) / len(df)))
        top = group.nlargest(n_from_state, "n_ssc_samples")
        selected.append(top)

    result = pd.concat(selected).nlargest(n_sites, "n_ssc_samples")
    logger.info(f"Selected {len(result)} sites:")
    for _, row in result.iterrows():
        logger.info(f"  {row['site_id']} ({row['state']}): {row['n_ssc_samples']} SSC samples")

    return result


def fetch_discrete_for_site(site_id: str) -> pd.DataFrame:
    """Fetch all discrete SSC samples for a site. Cache as Parquet."""
    cache_dir = DATA_DIR / "discrete"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{site_id.replace('-', '_')}_ssc.parquet"

    if cache_file.exists():
        logger.info(f"  [cache] Discrete SSC for {site_id}")
        return pd.read_parquet(cache_file)

    try:
        df, _ = waterdata.get_samples(
            monitoringLocationIdentifier=site_id,
            usgsPCode="80154",
        )
        if df is not None and len(df) > 0:
            df.to_parquet(cache_file)
            logger.info(f"  Fetched {len(df)} SSC samples for {site_id}")
            return df
    except Exception as e:
        logger.error(f"  Failed discrete fetch for {site_id}: {e}")

    return pd.DataFrame()


def fetch_continuous_for_site(
    site_id: str,
    param_code: str,
    param_name: str,
    n_years: int = 10,
) -> pd.DataFrame:
    """Fetch continuous data for a site+param in 3-year chunks. Cache per year."""
    cache_dir = DATA_DIR / "continuous" / site_id.replace("-", "_") / param_code
    cache_dir.mkdir(parents=True, exist_ok=True)

    end_year = 2025
    start_year = end_year - n_years

    all_chunks = []
    for year in range(start_year, end_year + 1, 3):
        chunk_end = min(year + 3, end_year + 1)
        cache_file = cache_dir / f"{year}_{chunk_end}.parquet"

        if cache_file.exists():
            chunk = pd.read_parquet(cache_file)
            if len(chunk) > 0:
                all_chunks.append(chunk)
            continue

        time_range = f"{year}-01-01/{chunk_end}-01-01"
        try:
            df, _ = waterdata.get_continuous(
                monitoring_location_id=site_id,
                parameter_code=param_code,
                time=time_range,
            )
            if df is not None and len(df) > 0:
                df.to_parquet(cache_file)
                all_chunks.append(df)
                logger.info(
                    f"  {param_name}: {len(df)} records ({year}-{chunk_end})"
                )
            else:
                # Save empty file to avoid re-fetching
                pd.DataFrame().to_parquet(cache_file)
        except Exception as e:
            logger.warning(f"  {param_name} {year}-{chunk_end}: {e}")
            # Save empty to avoid retrying failed chunks
            pd.DataFrame().to_parquet(cache_file)

        time.sleep(0.5)  # Respectful API delay

    if all_chunks:
        return pd.concat(all_chunks, ignore_index=True)
    return pd.DataFrame()


def main():
    parser = argparse.ArgumentParser(description="Download USGS water data")
    parser.add_argument("--n-sites", type=int, default=20, help="Number of sites")
    parser.add_argument("--years", type=int, default=10, help="Years of data")
    args = parser.parse_args()

    import warnings
    warnings.filterwarnings("ignore")

    logger.info(f"Downloading data for {args.n_sites} sites, {args.years} years each")

    sites = select_sites(args.n_sites)
    total_sites = len(sites)

    for i, (_, site_row) in enumerate(sites.iterrows()):
        site_id = site_row["site_id"]
        logger.info(f"\n[{i+1}/{total_sites}] {site_id} ({site_row['state']})")

        # Fetch discrete SSC
        fetch_discrete_for_site(site_id)

        # Fetch all continuous parameters
        for pcode, pname in CONTINUOUS_PARAMS.items():
            fetch_continuous_for_site(site_id, pcode, pname, n_years=args.years)

    logger.info("\nDownload complete!")

    # Summary
    disc_dir = DATA_DIR / "discrete"
    cont_dir = DATA_DIR / "continuous"
    n_disc = len(list(disc_dir.glob("*.parquet"))) if disc_dir.exists() else 0
    n_cont = len(list(cont_dir.rglob("*.parquet"))) if cont_dir.exists() else 0
    logger.info(f"Discrete files: {n_disc}")
    logger.info(f"Continuous files: {n_cont}")


if __name__ == "__main__":
    main()
