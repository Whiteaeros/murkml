#!/usr/bin/env python
"""Download and prepare external validation data from WQP non-USGS providers.

Uses wqp.get_results() with characteristicName (legacy CSV format) — same
approach as download_batch.py and download_discrete_turbidity.py but querying
by organization instead of siteid.

Fetches paired turbidity + SSC grab samples from external monitoring networks,
pairs them by site + date, and saves as a validation dataset.

Usage:
    python scripts/download_external_validation.py
    python scripts/download_external_validation.py --orgs UMRR_LTRM,42SRBCWQ_WQX
    python scripts/download_external_validation.py --skip-download  # just pair cached data
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
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "external_validation" / "cache"
OUTPUT_DIR = DATA_DIR / "external_validation"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)


# Organizations with both SSC and turbidity (from WQP cross-reference)
DEFAULT_ORGS = [
    ("UMRR_LTRM", "Upper Mississippi River Restoration"),
    ("AZDEQ_SW", "Arizona DEQ Surface Water"),
    ("42SRBCWQ_WQX", "Susquehanna River Basin Commission"),
    ("GLEC", "Great Lakes Environmental Center"),
    ("UMC", "University of Missouri Columbia"),
    ("TCEQMAIN", "Texas Commission on Environmental Quality"),
    ("WIDNR_WQX", "Wisconsin DNR"),
    ("MDNR", "Missouri DNR"),
    ("CBP_WQX", "Chesapeake Bay Program"),
    ("CEDEN", "California Environmental Data Exchange"),
]


def download_characteristic(org_id: str, char_name: str, cache_path: Path,
                            max_retries: int = 3) -> pd.DataFrame | None:
    """Download WQP results for one org + characteristic, with caching and retries."""
    from dataretrieval import wqp

    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        logger.info(f"    Cached: {len(df)} rows")
        return df if len(df) > 0 else None

    for attempt in range(max_retries):
        try:
            df, _ = wqp.get_results(
                organization=org_id,
                characteristicName=char_name,
            )
            if df is not None and len(df) > 0:
                df.to_parquet(cache_path, index=False)
                logger.info(f"    Downloaded: {len(df)} rows")
                return df
            else:
                pd.DataFrame().to_parquet(cache_path)
                logger.info(f"    0 rows")
                return None
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "503" in err_str:
                wait = 2 ** attempt * 15
                logger.warning(f"    Rate limited, waiting {wait}s")
                time.sleep(wait)
            elif attempt < max_retries - 1:
                logger.warning(f"    Error: {e}, retrying in 5s...")
                time.sleep(5)
            else:
                logger.error(f"    Failed after {max_retries} attempts: {e}")
                return None
    return None


def download_site_metadata(org_id: str, cache_path: Path) -> pd.DataFrame | None:
    """Download site metadata (coordinates, HUC) for one organization."""
    from dataretrieval import wqp

    if cache_path.exists():
        return pd.read_parquet(cache_path)

    try:
        sites, _ = wqp.what_sites(
            organization=org_id,
            characteristicName="Suspended Sediment Concentration (SSC)",
        )
        if sites is not None and len(sites) > 0:
            sites.to_parquet(cache_path, index=False)
            return sites
    except Exception as e:
        logger.warning(f"  Could not get site metadata for {org_id}: {e}")
    return None


def pair_turb_ssc(ssc_df: pd.DataFrame, turb_df: pd.DataFrame, org_id: str) -> pd.DataFrame:
    """Pair turbidity and SSC by site + date (same-day samples)."""
    # Parse SSC
    ssc = ssc_df[["MonitoringLocationIdentifier", "ActivityStartDate",
                   "ActivityStartTime/Time", "ResultMeasureValue",
                   "ResultMeasure/MeasureUnitCode"]].copy()
    ssc.columns = ["site_id", "date", "time", "ssc_value", "ssc_unit"]
    ssc["ssc_value"] = pd.to_numeric(ssc["ssc_value"], errors="coerce")
    ssc = ssc.dropna(subset=["ssc_value"])
    ssc = ssc[ssc["ssc_value"] > 0]

    # Parse turbidity
    turb = turb_df[["MonitoringLocationIdentifier", "ActivityStartDate",
                     "ActivityStartTime/Time", "ResultMeasureValue",
                     "ResultMeasure/MeasureUnitCode"]].copy()
    turb.columns = ["site_id", "date", "time", "turb_value", "turb_unit"]
    turb["turb_value"] = pd.to_numeric(turb["turb_value"], errors="coerce")
    turb = turb.dropna(subset=["turb_value"])
    turb = turb[turb["turb_value"] > 0]

    # Pair by site + date (same-day)
    paired = ssc.merge(turb, on=["site_id", "date"], how="inner", suffixes=("_ssc", "_turb"))

    if len(paired) == 0:
        return pd.DataFrame()

    # If multiple readings on same day, take median turbidity and first SSC
    paired = paired.groupby(["site_id", "date"]).agg(
        ssc_value=("ssc_value", "first"),
        ssc_unit=("ssc_unit", "first"),
        turb_value=("turb_value", "median"),
        turb_unit=("turb_unit", "first"),
    ).reset_index()

    paired["org_id"] = org_id
    return paired


def main():
    parser = argparse.ArgumentParser(description="Download external validation data")
    parser.add_argument("--orgs", type=str, default=None,
                        help="Comma-separated org IDs (default: all 10)")
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip download, just pair cached data")
    parser.add_argument("--min-samples", type=int, default=5,
                        help="Minimum samples per site (default: 5)")
    args = parser.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.orgs:
        org_ids = args.orgs.split(",")
        orgs = [(oid, oid) for oid in org_ids]
    else:
        orgs = DEFAULT_ORGS

    all_paired = []
    all_sites_meta = []

    for org_id, org_name in orgs:
        logger.info(f"\n{'='*50}")
        logger.info(f"Organization: {org_id} ({org_name})")
        logger.info(f"{'='*50}")

        # Download SSC
        ssc_cache = CACHE_DIR / f"{org_id}_ssc.parquet"
        logger.info(f"  SSC data:")
        ssc_df = download_characteristic(org_id, "Suspended Sediment Concentration (SSC)",
                                          ssc_cache) if not args.skip_download else (
            pd.read_parquet(ssc_cache) if ssc_cache.exists() else None)

        # Download turbidity
        turb_cache = CACHE_DIR / f"{org_id}_turb.parquet"
        logger.info(f"  Turbidity data:")
        turb_df = download_characteristic(org_id, "Turbidity",
                                           turb_cache) if not args.skip_download else (
            pd.read_parquet(turb_cache) if turb_cache.exists() else None)

        if ssc_df is None or turb_df is None:
            logger.warning(f"  Skipping {org_id} — missing data")
            continue

        # Download site metadata
        meta_cache = CACHE_DIR / f"{org_id}_sites.parquet"
        logger.info(f"  Site metadata:")
        sites_meta = download_site_metadata(org_id, meta_cache)
        if sites_meta is not None:
            all_sites_meta.append(sites_meta)

        # Pair turbidity + SSC
        logger.info(f"  Pairing...")
        paired = pair_turb_ssc(ssc_df, turb_df, org_id)
        if len(paired) > 0:
            logger.info(f"  Paired: {len(paired)} samples at {paired['site_id'].nunique()} sites")
            all_paired.append(paired)
        else:
            logger.warning(f"  No same-day pairs found")

        # Rate limiting between orgs
        time.sleep(2)

    if not all_paired:
        logger.error("No paired data from any organization!")
        return

    # Combine all
    combined = pd.concat(all_paired, ignore_index=True)
    logger.info(f"\n{'='*50}")
    logger.info(f"COMBINED: {len(combined)} samples, {combined['site_id'].nunique()} sites")

    # Add coordinates from site metadata
    if all_sites_meta:
        meta = pd.concat(all_sites_meta, ignore_index=True)
        meta = meta[["MonitoringLocationIdentifier", "LatitudeMeasure",
                      "LongitudeMeasure", "HUCEightDigitCode"]].copy()
        meta.columns = ["site_id", "latitude", "longitude", "huc8"]
        meta["latitude"] = pd.to_numeric(meta["latitude"], errors="coerce")
        meta["longitude"] = pd.to_numeric(meta["longitude"], errors="coerce")
        meta["huc2"] = meta["huc8"].astype(str).str[:2]
        meta = meta.drop_duplicates("site_id")
        combined = combined.merge(meta, on="site_id", how="left")

    # Summary by org
    logger.info(f"\n=== SUMMARY BY ORGANIZATION ===")
    for org_id in combined["org_id"].unique():
        sub = combined[combined["org_id"] == org_id]
        turb_units = sub["turb_unit"].value_counts().to_dict()
        logger.info(f"  {org_id:20s}: {sub['site_id'].nunique():4d} sites, "
                    f"{len(sub):6d} samples, turb_units={turb_units}")

    # Turbidity unit breakdown
    logger.info(f"\n=== TURBIDITY UNITS ===")
    logger.info(combined["turb_unit"].value_counts().to_string())

    # Filter to sites with enough samples
    site_counts = combined.groupby("site_id").size()
    good_sites = site_counts[site_counts >= args.min_samples].index
    filtered = combined[combined["site_id"].isin(good_sites)]
    logger.info(f"\nAfter filtering to {args.min_samples}+ samples/site: "
                f"{len(filtered)} samples, {filtered['site_id'].nunique()} sites")

    # Save
    combined.to_parquet(OUTPUT_DIR / "all_paired_external.parquet", index=False)
    filtered.to_parquet(OUTPUT_DIR / "filtered_external.parquet", index=False)
    logger.info(f"\nSaved to {OUTPUT_DIR}/")
    logger.info(f"  all_paired_external.parquet: {len(combined)} samples, {combined['site_id'].nunique()} sites")
    logger.info(f"  filtered_external.parquet: {len(filtered)} samples, {filtered['site_id'].nunique()} sites")


if __name__ == "__main__":
    main()
