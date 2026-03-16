"""Download data for top sites from diverse states (not KS/IN).

Selects top 5 sites per new state by SSC sample count,
downloads continuous + discrete data with proper rate limiting.

Usage: python scripts/download_diverse.py
"""

import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Load .env
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

DATA_DIR = Path(__file__).parent.parent / "data"
CONTINUOUS_PARAMS = {
    "63680": "turbidity_fnu",
    "00095": "conductance",
    "00300": "do",
    "00400": "ph",
    "00010": "temp",
    "00060": "discharge",
}
DELAY = 2.5  # seconds between requests


def fetch_continuous_chunk(site_id, param_code, param_name, time_range, cache_file):
    """Fetch one 3-year chunk with retry on 429."""
    if cache_file.exists():
        df = pd.read_parquet(cache_file)
        return len(df) > 0

    for attempt in range(3):
        try:
            df, _ = waterdata.get_continuous(
                monitoring_location_id=site_id,
                parameter_code=param_code,
                time=time_range,
            )
            if df is not None and len(df) > 0:
                df.to_parquet(cache_file)
                logger.info(f"    {param_name}: {len(df)} records ({time_range})")
                return True
            else:
                pd.DataFrame().to_parquet(cache_file)
                return False
        except Exception as e:
            if "429" in str(e):
                wait = 2 ** attempt * 30
                logger.warning(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                logger.warning(f"    {param_name} {time_range}: {e}")
                return False
        time.sleep(DELAY)
    return False


def main():
    import warnings
    warnings.filterwarnings("ignore")

    if not os.getenv("API_USGS_PAT"):
        logger.error("No API_USGS_PAT token! Set it in .env")
        sys.exit(1)

    catalog = pd.read_parquet(DATA_DIR / "site_catalog.parquet")

    # Find sites we already have
    existing = set()
    disc_dir = DATA_DIR / "discrete"
    if disc_dir.exists():
        for f in disc_dir.glob("*_ssc.parquet"):
            existing.add(f.stem.replace("_ssc", "").replace("_", "-"))

    new_sites = catalog[~catalog["site_id"].isin(existing)]
    logger.info(f"New sites available: {len(new_sites)}")

    # Select top 5 per state for diversity
    selected = []
    target_states = ["California", "Colorado", "Oregon", "Virginia", "Maryland",
                     "Montana", "Ohio", "Idaho", "Kentucky"]
    for state in target_states:
        state_sites = new_sites[new_sites["state"] == state]
        top = state_sites.nlargest(5, "n_ssc_samples")
        selected.append(top)
        for _, row in top.iterrows():
            logger.info(f"  {row['site_id']} ({state}): {row['n_ssc_samples']} SSC")

    sites = pd.concat(selected)
    logger.info(f"\nDownloading {len(sites)} diverse sites")

    for i, (_, row) in enumerate(sites.iterrows()):
        site_id = row["site_id"]
        logger.info(f"\n[{i+1}/{len(sites)}] {site_id} ({row['state']})")

        # Discrete SSC
        disc_cache = disc_dir / f"{site_id.replace('-', '_')}_ssc.parquet"
        if not disc_cache.exists():
            for attempt in range(3):
                try:
                    df, _ = waterdata.get_samples(
                        monitoringLocationIdentifier=site_id,
                        usgsPCode="80154",
                    )
                    if df is not None and len(df) > 0:
                        disc_dir.mkdir(parents=True, exist_ok=True)
                        df.to_parquet(disc_cache)
                        logger.info(f"  Discrete: {len(df)} SSC samples")
                        break
                except Exception as e:
                    if "429" in str(e):
                        time.sleep(2 ** attempt * 15)
                    else:
                        logger.error(f"  Discrete failed: {e}")
                        break
            time.sleep(DELAY)

        # Continuous — query metadata for date range first
        for pcode, pname in CONTINUOUS_PARAMS.items():
            cache_dir = DATA_DIR / "continuous" / site_id.replace("-", "_") / pcode
            cache_dir.mkdir(parents=True, exist_ok=True)

            # Get date range from metadata
            try:
                ts, _ = waterdata.get_time_series_metadata(
                    monitoring_location_id=site_id,
                    parameter_code=pcode,
                )
                if ts is not None and len(ts) > 0:
                    begin = pd.to_datetime(ts["begin"].iloc[0])
                    end = pd.to_datetime(ts["end"].iloc[0])
                    if pd.notna(begin) and pd.notna(end):
                        start_year = begin.year
                        end_year = end.year + 1
                    else:
                        start_year, end_year = 2015, 2027
                else:
                    start_year, end_year = 2015, 2027
            except Exception:
                start_year, end_year = 2015, 2027

            time.sleep(1)

            # Fetch in 3-year chunks
            for year in range(start_year, end_year + 1, 3):
                chunk_end = min(year + 3, end_year + 1)
                cache_file = cache_dir / f"{year}_{chunk_end}.parquet"
                time_range = f"{year}-01-01/{chunk_end}-01-01"
                fetch_continuous_chunk(site_id, pcode, pname, time_range, cache_file)
                time.sleep(DELAY)

    logger.info("\nDiverse download complete!")
    n_disc = len(list(disc_dir.glob("*.parquet")))
    logger.info(f"Total discrete files: {n_disc}")


if __name__ == "__main__":
    main()
