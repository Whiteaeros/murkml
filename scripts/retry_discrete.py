"""Retry failed discrete sample downloads.

Checks which sites in the catalog are missing discrete data and re-fetches them.
Run this after download_data.py if some discrete fetches hit 429 errors.

Usage: python scripts/retry_discrete.py
"""

import logging
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dataretrieval import waterdata

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"


def main():
    import warnings
    warnings.filterwarnings("ignore")

    catalog = pd.read_parquet(DATA_DIR / "site_catalog.parquet")
    disc_dir = DATA_DIR / "discrete"
    disc_dir.mkdir(parents=True, exist_ok=True)

    # Find sites that have continuous data but missing discrete
    cont_dir = DATA_DIR / "continuous"
    sites_with_continuous = set()
    if cont_dir.exists():
        for d in cont_dir.iterdir():
            if d.is_dir():
                sites_with_continuous.add(d.name.replace("_", "-"))

    sites_with_discrete = set()
    for f in disc_dir.glob("*_ssc.parquet"):
        site_id = f.stem.replace("_ssc", "").replace("_", "-")
        sites_with_discrete.add(site_id)

    missing = sites_with_continuous - sites_with_discrete
    logger.info(f"Sites with continuous but missing discrete: {len(missing)}")

    for site_id in sorted(missing):
        logger.info(f"Retrying {site_id}...")
        cache_file = disc_dir / f"{site_id.replace('-', '_')}_ssc.parquet"

        for attempt in range(5):
            try:
                df, _ = waterdata.get_samples(
                    monitoringLocationIdentifier=site_id,
                    usgsPCode="80154",
                )
                if df is not None and len(df) > 0:
                    df.to_parquet(cache_file)
                    logger.info(f"  Got {len(df)} samples")
                    break
                else:
                    logger.info(f"  No samples found")
                    break
            except Exception as e:
                wait = 2 ** attempt * 15
                logger.warning(f"  Attempt {attempt+1} failed: {e}. Waiting {wait}s...")
                time.sleep(wait)

    # Final count
    n_discrete = len(list(disc_dir.glob("*_ssc.parquet")))
    logger.info(f"\nTotal discrete files: {n_discrete}")


if __name__ == "__main__":
    main()
