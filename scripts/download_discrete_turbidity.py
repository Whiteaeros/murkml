"""Download discrete turbidity calibration data (pCode 63680) from WQP.

Fetches field turbidity measurements for all 383 murkml sites in batches,
filters to FNU units and Sample-Routine activity type, converts timestamps
to UTC, and saves per-site parquet files.

Usage:
    python scripts/download_discrete_turbidity.py [--batch-size 50] [--delay 3]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
DISCRETE_DIR = DATA_DIR / "discrete"
DISCRETE_DIR.mkdir(parents=True, exist_ok=True)

# --- Timezone offsets (from assemble_dataset.py) ---
USGS_TZ_OFFSETS = {
    "EST": -5, "EDT": -4,
    "CST": -6, "CDT": -5,
    "MST": -7, "MDT": -6,
    "PST": -8, "PDT": -7,
    "AKST": -9, "AKDT": -8,
    "HST": -10, "AST": -4,
    "UTC": 0, "GMT": 0,
}

PCODE = "63680"


def get_all_sites() -> list[str]:
    """Get all 383 site IDs from the paired parquet file."""
    paired = DATA_DIR / "processed" / "turbidity_ssc_paired.parquet"
    df = pd.read_parquet(paired, columns=["site_id"])
    sites = sorted(df["site_id"].unique().tolist())
    logger.info(f"Loaded {len(sites)} sites from turbidity_ssc_paired.parquet")
    return sites


def cached_sites() -> set[str]:
    """Return set of site IDs that already have turbidity parquet files."""
    existing = set()
    for f in DISCRETE_DIR.glob("USGS_*_turbidity.parquet"):
        # USGS_01036390_turbidity.parquet -> USGS-01036390
        site_id = f.stem.replace("_turbidity", "").replace("_", "-")
        existing.add(site_id)
    return existing


def parse_to_utc(df: pd.DataFrame) -> pd.Series:
    """Parse ActivityStartDate + Time + Timezone to UTC datetime."""
    date_col = df["ActivityStartDate"].astype(str)
    time_col = df["ActivityStartTime/Time"].astype(str)

    local_dt = pd.to_datetime(date_col + " " + time_col, errors="coerce")
    offsets = df["ActivityStartTime/TimeZoneCode"].map(USGS_TZ_OFFSETS)

    # Subtract offset to convert local -> UTC (e.g., CST=-6: local - (-6h) = UTC)
    utc_dt = local_dt - pd.to_timedelta(offsets, unit="h")
    return utc_dt.dt.tz_localize("UTC")


def download_batch(sites: list[str], max_retries: int = 3) -> pd.DataFrame | None:
    """Download discrete turbidity for a batch of sites from WQP."""
    from dataretrieval import wqp

    site_str = ";".join(sites)

    for attempt in range(max_retries):
        try:
            df, _ = wqp.get_results(
                siteid=site_str,
                pCode=PCODE,
            )
            if df is not None and len(df) > 0:
                return df
            return None
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "503" in err_str:
                wait = 2 ** attempt * 15
                logger.warning(f"  Rate limited (attempt {attempt+1}), retry in {wait}s: {err_str[:100]}")
                time.sleep(wait)
            else:
                logger.warning(f"  Error (attempt {attempt+1}/{max_retries}): {err_str[:200]}")
                if attempt == max_retries - 1:
                    return None
                time.sleep(5)
    return None


def process_and_save(df: pd.DataFrame) -> dict:
    """Filter, parse, and save per-site turbidity parquet files.

    Returns dict of site_id -> n_samples saved.
    """
    results = {}

    # --- Filter: FNU units only ---
    if "ResultMeasure/MeasureUnitCode" in df.columns:
        unit_counts = df["ResultMeasure/MeasureUnitCode"].value_counts().to_dict()
        logger.info(f"  Unit distribution before filter: {unit_counts}")
        df = df[df["ResultMeasure/MeasureUnitCode"] == "FNU"].copy()
    else:
        logger.warning("  No unit column found — skipping batch")
        return results

    # --- Filter: Sample-Routine only ---
    if "ActivityTypeCode" in df.columns:
        activity_counts = df["ActivityTypeCode"].value_counts().to_dict()
        logger.info(f"  Activity types before filter: {activity_counts}")
        df = df[df["ActivityTypeCode"] == "Sample-Routine"].copy()

    if df.empty:
        return results

    # --- Drop rows with missing time or timezone ---
    time_col = "ActivityStartTime/Time"
    tz_col = "ActivityStartTime/TimeZoneCode"

    has_time = df[time_col].notna() & (df[time_col] != "")
    has_tz = df[tz_col].notna() & df[tz_col].isin(USGS_TZ_OFFSETS.keys())
    valid = has_time & has_tz
    n_dropped = (~valid).sum()
    if n_dropped > 0:
        logger.info(f"  Dropped {n_dropped} rows with missing time/timezone")
    df = df[valid].copy()

    if df.empty:
        return results

    # --- Parse datetime to UTC ---
    df["datetime"] = parse_to_utc(df)
    df = df[df["datetime"].notna()].copy()

    # --- Parse turbidity value ---
    df["turbidity_value"] = pd.to_numeric(df["ResultMeasureValue"], errors="coerce")
    df = df[df["turbidity_value"].notna()].copy()

    if df.empty:
        return results

    # --- Extract columns of interest ---
    df["unit"] = df["ResultMeasure/MeasureUnitCode"]
    df["method_code"] = df.get("ResultAnalyticalMethod/MethodIdentifier", pd.Series(dtype=str))
    df["method_name"] = df.get("ResultAnalyticalMethod/MethodName", pd.Series(dtype=str))
    df["equipment"] = df.get("SampleCollectionEquipmentName", pd.Series(dtype=str))
    df["activity_type"] = df["ActivityTypeCode"]
    df["site_id"] = df["MonitoringLocationIdentifier"]

    keep_cols = [
        "site_id", "datetime", "turbidity_value", "unit",
        "method_code", "method_name", "equipment", "activity_type",
    ]
    df = df[keep_cols].copy()

    # --- Save per site ---
    for site_id, site_df in df.groupby("site_id"):
        site_df = site_df.drop(columns=["site_id"]).sort_values("datetime").reset_index(drop=True)
        site_file = site_id.replace("-", "_")
        out_path = DISCRETE_DIR / f"{site_file}_turbidity.parquet"
        site_df.to_parquet(out_path, index=False)
        results[site_id] = len(site_df)

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=50,
                        help="Sites per WQP request (default: 50)")
    parser.add_argument("--delay", type=float, default=3.0,
                        help="Seconds between API calls (default: 3)")
    args = parser.parse_args()

    all_sites = get_all_sites()

    # Check cache
    already_done = cached_sites()
    remaining = [s for s in all_sites if s not in already_done]
    logger.info(f"Already cached: {len(already_done)}, Remaining: {len(remaining)}")

    if not remaining:
        logger.info("All sites already downloaded!")
    else:
        # Batch download
        n_batches = (len(remaining) + args.batch_size - 1) // args.batch_size
        total_saved = {}

        for i in range(n_batches):
            batch = remaining[i * args.batch_size : (i + 1) * args.batch_size]
            logger.info(f"\n[Batch {i+1}/{n_batches}] Downloading {len(batch)} sites...")

            df = download_batch(batch)
            if df is not None:
                saved = process_and_save(df)
                total_saved.update(saved)
                logger.info(f"  Saved {len(saved)} sites from this batch")
            else:
                logger.info(f"  No data returned for this batch")

            if i < n_batches - 1:
                time.sleep(args.delay)

        logger.info(f"\nNewly downloaded: {len(total_saved)} sites, "
                     f"{sum(total_saved.values())} total samples")

    # --- Final report ---
    logger.info("\n" + "=" * 60)
    logger.info("FINAL REPORT")
    logger.info("=" * 60)

    turb_files = list(DISCRETE_DIR.glob("USGS_*_turbidity.parquet"))
    total_samples = 0
    method_counts = Counter()
    equipment_counts = Counter()
    site_sample_counts = []

    for f in turb_files:
        df = pd.read_parquet(f)
        n = len(df)
        total_samples += n
        site_sample_counts.append(n)

        if "method_code" in df.columns:
            for code in df["method_code"].dropna():
                method_counts[code] += 1
        if "equipment" in df.columns:
            for eq in df["equipment"].dropna():
                equipment_counts[eq] += 1

    logger.info(f"Sites with discrete turbidity data: {len(turb_files)} / {len(all_sites)}")
    logger.info(f"Total samples: {total_samples}")

    if site_sample_counts:
        arr = np.array(site_sample_counts)
        logger.info(f"Samples per site: min={arr.min()}, median={int(np.median(arr))}, "
                     f"mean={arr.mean():.1f}, max={arr.max()}")

    logger.info(f"\nMethod code distribution:")
    for code, count in method_counts.most_common(20):
        logger.info(f"  {code}: {count}")

    logger.info(f"\nEquipment distribution:")
    for eq, count in equipment_counts.most_common(20):
        logger.info(f"  {eq}: {count}")


if __name__ == "__main__":
    main()
