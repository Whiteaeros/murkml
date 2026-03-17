"""Fill catchment attribute gaps using NLDI API for sites not in GAGES-II.

Queries the NLDI (Network Linked Data Index) for total upstream characteristics
for each unmatched site, providing a subset of the GAGES-II-equivalent attributes.

Usage:
    python scripts/fill_attributes_nldi.py
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
NLDI_BASE = "https://api.water.usgs.gov/nldi/linked-data/nwissite"


def get_unmatched_sites() -> list[str]:
    """Get sites not in GAGES-II that need NLDI attributes."""
    assembled = pd.read_parquet(DATA_DIR / "processed" / "turbidity_ssc_paired.parquet")
    all_sites = set(assembled["site_id"].unique())

    gagesii_path = DATA_DIR / "site_attributes_gagesii.parquet"
    if gagesii_path.exists():
        gagesii = pd.read_parquet(gagesii_path)
        matched_sites = set(gagesii["site_id"])
    else:
        matched_sites = set()

    unmatched = sorted(all_sites - matched_sites)
    return unmatched


def fetch_nldi_characteristics(site_id: str, char_type: str = "tot",
                                max_retries: int = 3) -> dict | None:
    """Fetch upstream characteristics for a site from NLDI.

    char_type: 'tot' (total upstream), 'div' (divergence), 'local' (local catchment)
    """
    url = f"{NLDI_BASE}/{site_id}/{char_type}"

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                # NLDI returns a list of characteristic objects
                if isinstance(data, list):
                    chars = {}
                    for item in data:
                        name = item.get("characteristic_id", "")
                        value = item.get("characteristic_value")
                        if name and value is not None:
                            try:
                                chars[name] = float(value)
                            except (ValueError, TypeError):
                                chars[name] = value
                    return chars
                return None
            elif resp.status_code == 404:
                logger.warning(f"  {site_id}: not found in NLDI")
                return None
            elif resp.status_code == 429:
                wait = 2 ** attempt * 10
                logger.warning(f"  Rate limited, retry in {wait}s")
                time.sleep(wait)
            else:
                logger.warning(f"  {site_id}: HTTP {resp.status_code}")
                return None
        except Exception as e:
            logger.warning(f"  {site_id}: {e}")
            if attempt == max_retries - 1:
                return None
            time.sleep(5)

    return None


def fetch_nldi_comid(site_id: str) -> str | None:
    """Get the NHDPlus COMID for a site from NLDI."""
    url = f"{NLDI_BASE}/{site_id}"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            # COMID is in the features
            features = data.get("features", [])
            if features:
                props = features[0].get("properties", {})
                return props.get("comid")
        return None
    except Exception as e:
        logger.warning(f"  COMID lookup failed for {site_id}: {e}")
        return None


def main():
    unmatched = get_unmatched_sites()
    logger.info(f"Sites not in GAGES-II: {len(unmatched)}")

    if not unmatched:
        logger.info("All sites covered by GAGES-II!")
        return

    results = []
    for i, site_id in enumerate(unmatched):
        logger.info(f"[{i+1}/{len(unmatched)}] {site_id}")

        # Get COMID
        comid = fetch_nldi_comid(site_id)
        logger.info(f"  COMID: {comid}")
        time.sleep(1)

        # Get total upstream characteristics
        chars = fetch_nldi_characteristics(site_id, "tot")
        if chars:
            chars["site_id"] = site_id
            chars["comid"] = comid
            chars["source"] = "nldi_tot"
            results.append(chars)
            logger.info(f"  Got {len(chars)-3} characteristics")
        else:
            # Try local catchment characteristics
            chars_local = fetch_nldi_characteristics(site_id, "local")
            if chars_local:
                chars_local["site_id"] = site_id
                chars_local["comid"] = comid
                chars_local["source"] = "nldi_local"
                results.append(chars_local)
                logger.info(f"  Got {len(chars_local)-3} local characteristics")
            else:
                logger.warning(f"  No characteristics available")
                results.append({"site_id": site_id, "comid": comid, "source": "none"})

        time.sleep(1.5)

    df = pd.DataFrame(results)
    out_path = DATA_DIR / "site_attributes_nldi.parquet"
    df.to_parquet(out_path, index=False)
    logger.info(f"\nSaved NLDI attributes: {out_path}")
    logger.info(f"Sites with data: {(df['source'] != 'none').sum()}")
    logger.info(f"Total characteristics columns: {len(df.columns)}")


if __name__ == "__main__":
    main()
