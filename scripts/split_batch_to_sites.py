"""Split continuous_batch_v2 wide-format parquet files into per-site directories.

The batch_v2 download has a wide format:
- Columns: site_no, datetime, 00010, 00010_cd, 00060, 00060_cd, 63680, 63680_cd, ...
- Multiple sensor variants per parameter: 63680, 63680_discontinued, 63680_ysi 6136, etc.
- One row = one timestamp for one site, with all parameters as columns

This script converts to the per-site format that assemble_dataset.py expects:
- data/continuous/{USGS_site_no}/{param_code}/batch_v2_*.parquet
- Columns: time, value, approval_status, qualifier

Usage:
    python scripts/split_batch_to_sites.py
    python scripts/split_batch_to_sites.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Parameters we care about (code → name for directory)
PARAM_CODES = {"63680", "00095", "00300", "00400", "00010", "00060"}


def process_batch_file(batch_file: Path, output_dir: Path, dry_run: bool = False) -> dict:
    """Process one wide-format batch parquet file into per-site/per-param files."""
    stats = {"sites": 0, "params": 0, "rows": 0, "skipped": 0}

    try:
        df = pd.read_parquet(batch_file)
    except Exception as e:
        logger.error(f"Failed to read {batch_file.name}: {e}")
        return stats

    if df.empty or "site_no" not in df.columns:
        return stats

    # Find all parameter columns (exclude _cd quality code columns)
    param_cols = {}
    for col in df.columns:
        if col in ("site_no", "datetime"):
            continue
        if col.endswith("_cd"):
            continue
        # Extract the base parameter code
        base_code = col.split("_")[0] if "_" in col else col
        if base_code in PARAM_CODES:
            if base_code not in param_cols:
                param_cols[base_code] = []
            param_cols[base_code].append(col)

    for site_no, site_df in df.groupby("site_no"):
        site_id = f"USGS_{site_no}"

        for pcode, value_cols in param_cols.items():
            # Check if site already has per-site data for this param
            site_param_dir = output_dir / site_id / pcode
            if site_param_dir.exists():
                existing_files = list(site_param_dir.glob("*.parquet"))
                # Only skip if existing files have actual data
                existing_rows = sum(len(pd.read_parquet(f)) for f in existing_files[:1]) if existing_files else 0
                if existing_rows > 0:
                    stats["skipped"] += 1
                    continue

            # Combine all sensor variants for this parameter
            # e.g., 63680, 63680_discontinued, 63680_ysi 6136 all become "value"
            chunks = []
            for vcol in value_cols:
                cd_col = f"{vcol}_cd"
                mask = site_df[vcol].notna()
                if mask.sum() == 0:
                    continue

                chunk = pd.DataFrame({
                    "time": site_df.loc[mask, "datetime"].values,
                    "value": pd.to_numeric(site_df.loc[mask, vcol], errors="coerce").values,
                    "approval_status": site_df.loc[mask, cd_col].values if cd_col in site_df.columns else None,
                    "qualifier": None,
                })
                chunks.append(chunk)

            if not chunks:
                continue

            combined = pd.concat(chunks, ignore_index=True)
            combined = combined.dropna(subset=["time", "value"])
            combined = combined.drop_duplicates(subset=["time"], keep="first")
            combined = combined.sort_values("time").reset_index(drop=True)

            if combined.empty:
                continue

            if dry_run:
                stats["sites"] += 1
                stats["params"] += 1
                stats["rows"] += len(combined)
                continue

            site_param_dir.mkdir(parents=True, exist_ok=True)
            out_path = site_param_dir / f"batch_v2_{batch_file.stem}.parquet"
            combined.to_parquet(out_path, index=False)
            stats["sites"] += 1
            stats["params"] += 1
            stats["rows"] += len(combined)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Split batch_v2 into per-site dirs")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    batch_dir = DATA_DIR / "continuous_batch_v2"
    output_dir = DATA_DIR / "continuous"

    files = sorted(batch_dir.glob("*.parquet"))
    if not files:
        logger.error("No batch files found")
        return

    logger.info(f"Processing {len(files)} batch files {'(DRY RUN)' if args.dry_run else ''}")

    total = {"sites": 0, "params": 0, "rows": 0, "skipped": 0}
    for i, f in enumerate(files):
        if (i + 1) % 20 == 0:
            logger.info(f"  {i+1}/{len(files)} files processed ({total['rows']} rows so far)")
        s = process_batch_file(f, output_dir, dry_run=args.dry_run)
        for k in total:
            total[k] += s[k]

    logger.info(f"\nDone: {total['sites']} site-param dirs, {total['rows']} rows, {total['skipped']} skipped")
    if args.dry_run:
        logger.info("(DRY RUN — no files written)")


if __name__ == "__main__":
    main()
