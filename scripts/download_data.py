"""Download continuous sensor + discrete sample data for paired sites.

This script fetches all available data for selected sites from the USGS API.
Downloads are cached as Parquet files so the script is resume-safe.

IMPORTANT: Set the API_USGS_PAT environment variable with your free USGS API
token before running. Without it, you'll be rate-limited after ~50 requests.
Get a token at: https://api.waterdata.usgs.gov/

Usage:
    python scripts/download_data.py [--n-sites 20] [--years 10] [--delay 3]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from murkml.provenance import start_run, log_step, log_file, end_run

# Load .env file if it exists (for API_USGS_PAT)
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

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


def fetch_discrete_for_site(site_id: str, max_retries: int = 3) -> pd.DataFrame:
    """Fetch all discrete SSC samples for a site. Cache as Parquet.

    Retries with exponential backoff on 429 (Too Many Requests) errors.
    """
    cache_dir = DATA_DIR / "discrete"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{site_id.replace('-', '_')}_ssc.parquet"

    if cache_file.exists():
        logger.info(f"  [cache] Discrete SSC for {site_id}")
        return pd.read_parquet(cache_file)

    for attempt in range(max_retries):
        try:
            df, _ = waterdata.get_samples(
                monitoringLocationIdentifier=site_id,
                usgsPCode="80154",
            )
            if df is not None and len(df) > 0:
                df.to_parquet(cache_file)
                logger.info(f"  Fetched {len(df)} SSC samples for {site_id}")
                return df
            return pd.DataFrame()
        except Exception as e:
            wait = 2 ** attempt * 10  # 10s, 20s, 40s
            if "429" in str(e):
                logger.warning(
                    f"  Rate limited fetching discrete for {site_id}, "
                    f"retry {attempt + 1}/{max_retries} in {wait}s"
                )
            else:
                logger.error(f"  Failed discrete fetch for {site_id}: {e}")
                if attempt == max_retries - 1:
                    return pd.DataFrame()
            time.sleep(wait)

    return pd.DataFrame()


def get_site_date_range(site_id: str, param_code: str) -> tuple:
    """Query the actual date range for a site+param from time series metadata.

    Returns (start_year, end_year) or (None, None) if unavailable.
    """
    try:
        ts, _ = waterdata.get_time_series_metadata(
            monitoring_location_id=site_id,
            parameter_code=param_code,
        )
        if ts is not None and len(ts) > 0:
            begin = pd.to_datetime(ts["begin"].iloc[0])
            end = pd.to_datetime(ts["end"].iloc[0])
            if pd.notna(begin) and pd.notna(end):
                return begin.year, end.year + 1
    except Exception:
        pass
    return None, None


def fetch_continuous_for_site(
    site_id: str,
    param_code: str,
    param_name: str,
    n_years: int = 10,
    delay: float = 3.0,
    max_retries: int = 3,
) -> pd.DataFrame:
    """Fetch continuous data for a site+param in 3-year chunks. Cache per year.

    Queries the site's actual data availability period rather than using a
    fixed window. Only caches non-empty results. Rate-limit errors (429)
    trigger retries with exponential backoff, NOT empty cache files.
    """
    cache_dir = DATA_DIR / "continuous" / site_id.replace("-", "_") / param_code
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Query actual date range for this site+param
    meta_start, meta_end = get_site_date_range(site_id, param_code)
    if meta_start and meta_end:
        start_year = meta_start
        end_year = meta_end
        logger.info(f"  {param_name}: metadata says {start_year}-{end_year}")
    else:
        # Fallback: try a broad window
        end_year = 2027
        start_year = end_year - n_years
        logger.info(f"  {param_name}: no metadata dates, trying {start_year}-{end_year}")

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
        success = False

        for attempt in range(max_retries):
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
                    # Genuinely no data for this period — cache empty to skip next time
                    pd.DataFrame().to_parquet(cache_file)
                    logger.debug(f"  {param_name}: no data ({year}-{chunk_end})")
                success = True
                break
            except Exception as e:
                err_str = str(e)
                if "429" in err_str:
                    wait = 2 ** attempt * 30  # 30s, 60s, 120s
                    logger.warning(
                        f"  Rate limited on {param_name} ({year}-{chunk_end}), "
                        f"retry {attempt+1}/{max_retries} in {wait}s..."
                    )
                    time.sleep(wait)
                else:
                    logger.warning(f"  {param_name} {year}-{chunk_end}: {e}")
                    break  # Non-rate-limit error, don't retry

        if not success:
            # Do NOT cache — leave uncached so next run retries
            logger.error(
                f"  FAILED {param_name} ({year}-{chunk_end}) after {max_retries} attempts"
            )

        time.sleep(delay)  # Respectful delay between ALL requests

    if all_chunks:
        return pd.concat(all_chunks, ignore_index=True)
    return pd.DataFrame()


def main():
    parser = argparse.ArgumentParser(description="Download USGS water data")
    parser.add_argument("--n-sites", type=int, default=20, help="Number of sites")
    parser.add_argument("--years", type=int, default=10, help="Years of data")
    parser.add_argument("--delay", type=float, default=3.0, help="Seconds between API calls")
    args = parser.parse_args()

    import warnings
    warnings.filterwarnings("ignore")

    # Check for API token
    if os.getenv("API_USGS_PAT"):
        logger.info("USGS API token found")
    else:
        logger.warning(
            "No API_USGS_PAT token set! You WILL be rate-limited. "
            "Get a free token at https://api.waterdata.usgs.gov/ "
            "and add it to .env file or set as environment variable."
        )

    logger.info(f"Downloading data for {args.n_sites} sites, {args.years} years each")
    start_run("download_data")

    sites = select_sites(args.n_sites)
    total_sites = len(sites)

    for i, (_, site_row) in enumerate(sites.iterrows()):
        site_id = site_row["site_id"]
        logger.info(f"\n[{i+1}/{total_sites}] {site_id} ({site_row['state']})")

        # Fetch discrete SSC
        fetch_discrete_for_site(site_id)

        # Fetch all continuous parameters
        for pcode, pname in CONTINUOUS_PARAMS.items():
            fetch_continuous_for_site(
                site_id, pcode, pname, n_years=args.years, delay=args.delay,
            )

    logger.info("\nDownload complete!")

    # Summary
    disc_dir = DATA_DIR / "discrete"
    cont_dir = DATA_DIR / "continuous"
    n_disc = len(list(disc_dir.glob("*.parquet"))) if disc_dir.exists() else 0
    n_cont = len(list(cont_dir.rglob("*.parquet"))) if cont_dir.exists() else 0
    logger.info(f"Discrete files: {n_disc}")
    logger.info(f"Continuous files: {n_cont}")

    log_step("download_complete", n_sites=total_sites,
             n_discrete_files=n_disc, n_continuous_files=n_cont)
    end_run()


if __name__ == "__main__":
    main()
