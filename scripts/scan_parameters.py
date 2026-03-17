"""Scan all 57 assembled sites for discrete lab data availability.

Queries USGS API for Total Phosphorus, Nitrate+Nitrite, TDS, and Orthophosphate
at each site. Builds an availability matrix showing sample counts per site per parameter.

Usage:
    python scripts/scan_parameters.py
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd

# Add project root to path
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

# Parameters to scan (from physics panel / Vasquez)
PARAMS = {
    "00665": "total_phosphorus",
    "00631": "nitrate_nitrite",
    "70300": "tds_evaporative",
    "00671": "orthophosphate",
}

# Minimum samples to consider a site viable
MIN_SAMPLES = 10


def get_assembled_sites() -> list[str]:
    """Get the 57 sites that passed assembly QC."""
    assembled = pd.read_parquet(DATA_DIR / "processed" / "turbidity_ssc_paired.parquet")
    sites = sorted(assembled["site_id"].unique())
    return sites


def scan_site_parameter(site_id: str, pcode: str, max_retries: int = 3) -> int:
    """Query sample count for a site+parameter. Returns count or -1 on failure."""
    for attempt in range(max_retries):
        try:
            df, _ = waterdata.get_samples(
                monitoringLocationIdentifier=site_id,
                usgsPCode=pcode,
            )
            if df is not None and len(df) > 0:
                return len(df)
            return 0
        except Exception as e:
            if "429" in str(e):
                wait = 2 ** attempt * 15
                logger.warning(f"  Rate limited on {site_id}/{pcode}, retry in {wait}s")
                time.sleep(wait)
            else:
                logger.warning(f"  Error {site_id}/{pcode}: {e}")
                if attempt == max_retries - 1:
                    return -1
                time.sleep(5)
    return -1


def main():
    if os.getenv("API_USGS_PAT"):
        logger.info("USGS API token found")
    else:
        logger.warning("No API_USGS_PAT — will be rate-limited!")

    sites = get_assembled_sites()
    logger.info(f"Scanning {len(sites)} sites for {len(PARAMS)} parameters")
    logger.info(f"Parameters: {PARAMS}")

    # Resume support: check for existing scan progress
    progress_file = DATA_DIR / "parameter_scan_progress.parquet"
    if progress_file.exists():
        results = pd.read_parquet(progress_file).to_dict("records")
        done = {(r["site_id"], r["pcode"]) for r in results}
        logger.info(f"Resuming — {len(done)} site/param combos already scanned")
    else:
        results = []
        done = set()

    total = len(sites) * len(PARAMS)
    completed = len(done)

    for i, site_id in enumerate(sites):
        for pcode, pname in PARAMS.items():
            if (site_id, pcode) in done:
                continue

            completed += 1
            logger.info(f"[{completed}/{total}] {site_id} — {pname} ({pcode})")

            count = scan_site_parameter(site_id, pcode)
            results.append({
                "site_id": site_id,
                "pcode": pcode,
                "param_name": pname,
                "n_samples": count,
            })

            # Save progress every 10 queries
            if len(results) % 10 == 0:
                pd.DataFrame(results).to_parquet(progress_file)

            time.sleep(1.5)  # Rate limit: ~1 req/sec with overhead

    # Save final results
    df = pd.DataFrame(results)
    df.to_parquet(progress_file)

    # Build availability matrix (pivot: sites x params)
    matrix = df.pivot(index="site_id", columns="param_name", values="n_samples")
    matrix.to_parquet(DATA_DIR / "site_parameter_matrix.parquet")

    # Summary
    logger.info("\n=== PARAMETER AVAILABILITY SUMMARY ===")
    for pcode, pname in PARAMS.items():
        param_df = df[df["pcode"] == pcode]
        n_viable = (param_df["n_samples"] >= MIN_SAMPLES).sum()
        n_any = (param_df["n_samples"] > 0).sum()
        total_samples = param_df["n_samples"].clip(lower=0).sum()
        logger.info(f"{pname:25s}: {n_viable} sites (≥{MIN_SAMPLES} samples), "
                     f"{n_any} sites (any data), {total_samples} total samples")

    # Sites with ALL parameters
    viable = matrix.copy()
    viable[viable < MIN_SAMPLES] = 0
    all_params = (viable > 0).all(axis=1).sum()
    logger.info(f"\nSites with ALL 4 new params (≥{MIN_SAMPLES} each): {all_params}")

    # Sites with at least SSC + one new param
    at_least_one = (viable > 0).any(axis=1).sum()
    logger.info(f"Sites with ≥1 new param (≥{MIN_SAMPLES}): {at_least_one}")


if __name__ == "__main__":
    main()
