"""Download discrete lab data for new parameters at all viable sites.

Reads the parameter scan results (from scan_parameters.py) and downloads
actual sample data for every site/parameter combo with >= MIN_SAMPLES.

Saves as data/discrete/{site_id}_{param_name}.parquet

Usage:
    python scripts/download_discrete_params.py [--min-samples 10]
"""

from __future__ import annotations

import argparse
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

PARAMS = {
    "00665": "total_phosphorus",
    "00631": "nitrate_nitrite",
    "70300": "tds_evaporative",
    "00671": "orthophosphate",
}


def download_samples(site_id: str, pcode: str, param_name: str,
                     max_retries: int = 3) -> pd.DataFrame | None:
    """Download discrete samples for a site+parameter. Returns DataFrame or None."""
    cache_dir = DATA_DIR / "discrete"
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Use underscore format for filenames (consistent with SSC files)
    site_file = site_id.replace("-", "_")
    cache_file = cache_dir / f"{site_file}_{param_name}.parquet"

    if cache_file.exists():
        df = pd.read_parquet(cache_file)
        logger.info(f"  [cache] {site_id}/{param_name}: {len(df)} samples")
        return df

    for attempt in range(max_retries):
        try:
            df, _ = waterdata.get_samples(
                monitoringLocationIdentifier=site_id,
                usgsPCode=pcode,
            )
            if df is not None and len(df) > 0:
                df.to_parquet(cache_file)
                logger.info(f"  Downloaded {site_id}/{param_name}: {len(df)} samples")
                return df
            logger.info(f"  {site_id}/{param_name}: no data")
            return None
        except Exception as e:
            if "429" in str(e):
                wait = 2 ** attempt * 15
                logger.warning(f"  Rate limited, retry in {wait}s")
                time.sleep(wait)
            else:
                logger.warning(f"  Error: {e}")
                if attempt == max_retries - 1:
                    return None
                time.sleep(5)
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-samples", type=int, default=10)
    args = parser.parse_args()

    if os.getenv("API_USGS_PAT"):
        logger.info("USGS API token found")
    else:
        logger.warning("No API_USGS_PAT — will be rate-limited!")

    # Load scan results
    scan_file = DATA_DIR / "parameter_scan_progress.parquet"
    if not scan_file.exists():
        logger.error("No scan results found! Run scan_parameters.py first.")
        sys.exit(1)

    scan = pd.read_parquet(scan_file)
    viable = scan[scan["n_samples"] >= args.min_samples].copy()
    logger.info(f"Viable site/parameter combos (>={args.min_samples} samples): {len(viable)}")

    # Summary by parameter
    for pcode, pname in PARAMS.items():
        n = len(viable[viable["pcode"] == pcode])
        logger.info(f"  {pname}: {n} sites")

    # Download each
    total = len(viable)
    downloaded = 0
    failed = 0

    for i, (_, row) in enumerate(viable.iterrows()):
        site_id = row["site_id"]
        pcode = row["pcode"]
        pname = row["param_name"]

        logger.info(f"[{i+1}/{total}] {site_id} — {pname}")
        result = download_samples(site_id, pcode, pname)

        if result is not None:
            downloaded += 1
        else:
            failed += 1

        time.sleep(1.5)  # Rate limit

    logger.info(f"\nDone! Downloaded: {downloaded}, Failed: {failed}, Total: {total}")

    # Summary of what we have
    disc_dir = DATA_DIR / "discrete"
    for pcode, pname in PARAMS.items():
        files = list(disc_dir.glob(f"*_{pname}.parquet"))
        total_samples = 0
        for f in files:
            total_samples += len(pd.read_parquet(f))
        logger.info(f"{pname}: {len(files)} files, {total_samples} total samples")


if __name__ == "__main__":
    main()
