"""Download all data for expansion training sites.

Reads verified sites from expansion_candidates.parquet and downloads
continuous sensor data + discrete lab data for each.

Saves to the MAIN data directory (not validation/) since these are training sites.

Usage:
    python scripts/download_expansion_sites.py
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

import warnings
warnings.filterwarnings("ignore")

from dataretrieval import waterdata

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"

CONTINUOUS_PARAMS = {
    "63680": "turbidity",
    "00095": "conductance",
    "00300": "do",
    "00400": "ph",
    "00010": "temp",
    "00060": "discharge",
}

DISCRETE_PARAMS = {
    "80154": "ssc",
    "00665": "total_phosphorus",
    "00631": "nitrate_nitrite",
    "70300": "tds_evaporative",
    "00671": "orthophosphate",
}


def get_site_date_range(site_id, param_code):
    try:
        ts, _ = waterdata.get_time_series_metadata(
            monitoring_location_id=site_id, parameter_code=param_code,
        )
        if ts is not None and len(ts) > 0:
            begin = pd.to_datetime(ts["begin"].iloc[0])
            end = pd.to_datetime(ts["end"].iloc[0])
            if pd.notna(begin) and pd.notna(end):
                return begin.year, end.year + 1
    except Exception:
        pass
    return None, None


def download_continuous(site_id, param_code, param_name, delay=2.0, max_retries=3):
    site_stem = site_id.replace("-", "_")
    cache_dir = DATA_DIR / "continuous" / site_stem / param_code
    cache_dir.mkdir(parents=True, exist_ok=True)

    start_year, end_year = get_site_date_range(site_id, param_code)
    if not start_year:
        end_year = 2027
        start_year = end_year - 15

    total = 0
    for year in range(start_year, end_year + 1, 3):
        chunk_end = min(year + 3, end_year + 1)
        cache_file = cache_dir / f"{year}_{chunk_end}.parquet"
        if cache_file.exists():
            chunk = pd.read_parquet(cache_file)
            total += len(chunk)
            continue

        for attempt in range(max_retries):
            try:
                df, _ = waterdata.get_continuous(
                    monitoring_location_id=site_id,
                    parameter_code=param_code,
                    time=f"{year}-01-01/{chunk_end}-01-01",
                )
                if df is not None and len(df) > 0:
                    df.to_parquet(cache_file)
                    total += len(df)
                else:
                    pd.DataFrame().to_parquet(cache_file)
                break
            except Exception as e:
                if "429" in str(e):
                    time.sleep(2 ** attempt * 30)
                else:
                    break
        time.sleep(delay)

    if total > 0:
        logger.info(f"    {param_name}: {total} records")
    return total


def download_discrete(site_id, pcode, param_name, max_retries=3):
    site_stem = site_id.replace("-", "_")
    cache_dir = DATA_DIR / "discrete"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{site_stem}_{param_name}.parquet"

    if cache_file.exists():
        df = pd.read_parquet(cache_file)
        if len(df) > 0:
            return len(df)
        return 0

    for attempt in range(max_retries):
        try:
            df, _ = waterdata.get_samples(
                monitoringLocationIdentifier=site_id, usgsPCode=pcode,
            )
            if df is not None and len(df) > 0:
                df.to_parquet(cache_file)
                logger.info(f"    {param_name}: {len(df)} samples")
                return len(df)
            return 0
        except Exception as e:
            if "429" in str(e):
                time.sleep(2 ** attempt * 15)
            else:
                return 0
    return 0


def main():
    if os.getenv("API_USGS_PAT"):
        logger.info("USGS API token found")
    else:
        logger.warning("No API_USGS_PAT!")

    candidates = pd.read_parquet(DATA_DIR / "expansion_candidates.parquet")
    logger.info(f"Downloading data for {len(candidates)} expansion sites")

    for i, (_, row) in enumerate(candidates.iterrows()):
        site_id = row["site_id"]
        regime = row["regime"]
        logger.info(f"\n[{i+1}/{len(candidates)}] {site_id} ({regime})")

        for pcode, pname in CONTINUOUS_PARAMS.items():
            download_continuous(site_id, pcode, pname)

        for pcode, pname in DISCRETE_PARAMS.items():
            download_discrete(site_id, pcode, pname)
            time.sleep(1)

    logger.info(f"\nDone! Downloaded data for {len(candidates)} expansion sites.")


if __name__ == "__main__":
    main()
