"""Download turbidity (63680) data to fill coverage gaps identified by gap analysis.

Reads data/download_gaps.parquet and downloads turbidity for each site's
missing date ranges. Uses multi-site batching and concurrent downloads
for speed.

Output: data/continuous/USGS_{site_no}/63680/gap_fill_{start}_{end}.parquet
Format: columns [time, value, approval_status, qualifier]
        approval_status uses full words: "Approved", "Provisional", "Unknown"

Usage:
    python scripts/download_gap_fill.py
    python scripts/download_gap_fill.py --dry-run
    python scripts/download_gap_fill.py --workers 3 --batch-size 10
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from pathlib import Path
from threading import Lock

import pandas as pd
import requests.exceptions

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Load .env for API_USGS_PAT
env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(PROJECT_ROOT / "gap_fill.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"
CONT_DIR = DATA_DIR / "continuous"
PCODE = "63680"

# Thread-safe progress counters
_lock = Lock()
_progress = {"calls": 0, "rows": 0, "skipped": 0, "errors": 0, "succeeded": 0, "failed_items": []}


def _normalize_approval(raw_cd: str) -> str:
    """Convert NWIS approval codes to full words."""
    if pd.isna(raw_cd) or str(raw_cd).strip() == "":
        return "Unknown"
    first = str(raw_cd).strip()[0].upper()
    if first == "A":
        return "Approved"
    elif first == "P":
        return "Provisional"
    return "Unknown"


def _parse_qualifier(raw_cd: str) -> str | None:
    """Extract qualifier portion from NWIS _cd column."""
    if pd.isna(raw_cd) or str(raw_cd).strip() == "":
        return None
    parts = str(raw_cd).split(",")
    quals = [p.strip() for p in parts[1:] if p.strip()]
    return ", ".join(quals) if quals else None


def _find_primary_column(columns: list[str], pcode: str) -> tuple[str | None, str | None]:
    """Find the primary value and qualifier columns for a parameter code."""
    if pcode in columns:
        cd_col = f"{pcode}_cd" if f"{pcode}_cd" in columns else None
        return pcode, cd_col
    candidates = [c for c in columns if c.startswith(pcode) and not c.endswith("_cd")]
    if candidates:
        val_col = candidates[0]
        cd_col = f"{val_col}_cd" if f"{val_col}_cd" in columns else None
        return val_col, cd_col
    return None, None


def _gap_fill_exists(site_no: str, yr_start: int, yr_end: int) -> bool:
    """Check if gap_fill file already exists with data for this range."""
    site_id = f"USGS_{site_no}"
    out_file = CONT_DIR / site_id / PCODE / f"gap_fill_{yr_start}_{yr_end}.parquet"
    if out_file.exists():
        try:
            existing = pd.read_parquet(out_file)
            return len(existing) > 0
        except Exception:
            return False
    return False


def load_gaps() -> pd.DataFrame:
    """Load and filter the gap analysis to sites that need downloads."""
    path = DATA_DIR / "download_gaps.parquet"
    df = pd.read_parquet(path)
    # Only sites with intended_years > 0
    df = df[df["intended_years"] > 0].copy()
    logger.info(f"Loaded {len(df)} sites needing gap-fill downloads")
    return df


def build_work_items(
    gaps_df: pd.DataFrame,
    batch_size: int = 10,
    years_per_chunk: int = 1,
) -> list[dict]:
    """Build a flat list of work items: each is one API call (batch of sites x 1yr chunk).

    Sites sorted by start year, grouped into batches. Each batch's year range
    is the union, split into 1-year chunks. Returns flat list for concurrent dispatch.
    """
    df = gaps_df.sort_values("download_start_year").reset_index(drop=True)

    work_items = []
    batch_idx = 0
    for i in range(0, len(df), batch_size):
        batch_df = df.iloc[i:i + batch_size]
        site_numbers = [s.replace("USGS-", "") for s in batch_df["site_id"].tolist()]

        yr_start = int(batch_df["download_start_year"].min())
        yr_end = int(batch_df["download_end_year"].max())

        y = yr_start
        while y < yr_end:
            y_end = min(y + years_per_chunk, yr_end)
            work_items.append({
                "site_numbers": site_numbers,
                "yr_start": y,
                "yr_end": y_end,
                "batch_idx": batch_idx,
            })
            y = y_end

        batch_idx += 1

    return work_items


def _process_response(df: pd.DataFrame, site_numbers: list[str]) -> dict[str, pd.DataFrame]:
    """Extract per-site turbidity dataframes from a batch API response."""
    results = {}
    if df is None or len(df) == 0:
        return results

    if "site_no" not in df.columns:
        return results

    all_cols = list(df.columns)
    val_col, cd_col = _find_primary_column(all_cols, PCODE)
    if val_col is None:
        return results

    for site_no, site_df in df.groupby("site_no"):
        site_no = str(site_no)
        if site_no not in site_numbers:
            continue

        keep = site_df[["datetime", val_col]].dropna(subset=[val_col]).copy()
        if len(keep) == 0:
            continue

        keep = keep.rename(columns={val_col: "value", "datetime": "time"})
        keep["time"] = pd.to_datetime(keep["time"])

        if cd_col and cd_col in site_df.columns:
            raw_cd = site_df.loc[keep.index, cd_col].values
            keep["approval_status"] = pd.Series(raw_cd).apply(_normalize_approval).values
            keep["qualifier"] = pd.Series(raw_cd).apply(_parse_qualifier).values
        else:
            keep["approval_status"] = "Unknown"
            keep["qualifier"] = None

        keep = keep[["time", "value", "approval_status", "qualifier"]]
        results[site_no] = keep

    return results


# Network errors that warrant retry with backoff
_NETWORK_ERRORS = (
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.ConnectionError,
    requests.exceptions.ReadTimeout,
    requests.exceptions.Timeout,
    ConnectionError,
    ConnectionResetError,
    socket.timeout,
    OSError,
)

# Exponential backoff schedule: 30s, 60s, 120s, 240s
_BACKOFF_SECS = [30, 60, 120, 240]
_MAX_RETRIES = len(_BACKOFF_SECS)

# File to track completed work items for resume support
_PROGRESS_FILE = PROJECT_ROOT / "gap_fill_progress.json"
_progress_lock_file = Lock()


def _load_completed_items() -> set[str]:
    """Load the set of completed work-item keys from the progress file."""
    if _PROGRESS_FILE.exists():
        try:
            data = json.loads(_PROGRESS_FILE.read_text())
            return set(data.get("completed", []))
        except Exception:
            return set()
    return set()


def _save_completed_item(key: str) -> None:
    """Append a completed work-item key to the progress file (thread-safe)."""
    with _progress_lock_file:
        completed = _load_completed_items()
        completed.add(key)
        _PROGRESS_FILE.write_text(json.dumps({"completed": sorted(completed)}))


def _work_item_key(item: dict) -> str:
    """Unique string key for a work item."""
    sites = ",".join(sorted(item["site_numbers"]))
    return f"{sites}|{item['yr_start']}-{item['yr_end']}"


def execute_work_item(item: dict, total_items: int, call_timeout: int = 180) -> int:
    """Execute a single work item (one API call). Returns rows saved.

    Retries on network/chunked-encoding errors with exponential backoff
    (30s, 60s, 120s, 240s). On final failure, logs and returns 0
    so the rest of the download continues.
    """
    import dataretrieval.nwis as nwis

    site_numbers = item["site_numbers"]
    yr_start = item["yr_start"]
    yr_end = item["yr_end"]
    item_key = _work_item_key(item)

    # Skip if already completed in a previous run
    if item_key in _load_completed_items():
        with _lock:
            _progress["skipped"] += 1
            _progress["calls"] += 1
            n = _progress["calls"]
        return 0

    # Check which sites already have this chunk on disk
    sites_to_fetch = [sn for sn in site_numbers if not _gap_fill_exists(sn, yr_start, yr_end)]
    if not sites_to_fetch:
        _save_completed_item(item_key)
        with _lock:
            _progress["skipped"] += 1
            _progress["calls"] += 1
            n = _progress["calls"]
        return 0

    rows_saved = 0

    for attempt in range(_MAX_RETRIES):
        try:
            old_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(call_timeout)
            try:
                df, _ = nwis.get_iv(
                    sites=sites_to_fetch,
                    parameterCd=PCODE,
                    start=f"{yr_start}-01-01",
                    end=f"{yr_end}-01-01",
                )
            finally:
                socket.setdefaulttimeout(old_timeout)

            if df is not None and len(df) > 0:
                df = df.reset_index()
                per_site = _process_response(df, sites_to_fetch)

                for site_no, data in per_site.items():
                    site_id = f"USGS_{site_no}"
                    param_dir = CONT_DIR / site_id / PCODE
                    param_dir.mkdir(parents=True, exist_ok=True)
                    out_file = param_dir / f"gap_fill_{yr_start}_{yr_end}.parquet"
                    data.to_parquet(out_file, index=False)
                    rows_saved += len(data)

            # Success -- record progress
            _save_completed_item(item_key)

            with _lock:
                _progress["calls"] += 1
                _progress["rows"] += rows_saved
                _progress["succeeded"] += 1
                n = _progress["calls"]
                total_rows = _progress["rows"]
                skipped = _progress["skipped"]

            logger.info(
                f"[{n}/{total_items}] batch{item['batch_idx']:02d} "
                f"{yr_start}-{yr_end} ({len(sites_to_fetch)} sites): "
                f"{rows_saved:,} rows | cumul: {total_rows:,} rows, {skipped} skipped"
            )
            return rows_saved

        except _NETWORK_ERRORS as e:
            err_type = type(e).__name__
            wait = _BACKOFF_SECS[attempt]
            logger.warning(
                f"  {err_type} on batch{item['batch_idx']:02d} "
                f"{yr_start}-{yr_end} (attempt {attempt+1}/{_MAX_RETRIES}), "
                f"retrying in {wait}s..."
            )
            time.sleep(wait)

        except Exception as e:
            err_str = str(e).lower()
            err_type = type(e).__name__

            # Catch network-like errors that didn't match the tuple
            if any(kw in err_str for kw in ("chunked", "connection", "timeout", "broken pipe", "reset by peer")):
                wait = _BACKOFF_SECS[attempt]
                logger.warning(
                    f"  {err_type} (network-like) on batch{item['batch_idx']:02d} "
                    f"{yr_start}-{yr_end} (attempt {attempt+1}/{_MAX_RETRIES}), "
                    f"retrying in {wait}s..."
                )
                time.sleep(wait)
            elif "429" in str(e) or "rate" in err_str:
                wait = _BACKOFF_SECS[attempt] * 2  # double for rate limits
                logger.warning(
                    f"  Rate limited batch{item['batch_idx']:02d} "
                    f"{yr_start}-{yr_end}, wait {wait}s (attempt {attempt+1}/{_MAX_RETRIES})"
                )
                time.sleep(wait)
            elif attempt < _MAX_RETRIES - 1:
                wait = _BACKOFF_SECS[attempt]
                logger.warning(
                    f"  {err_type}: {e} (batch{item['batch_idx']:02d} "
                    f"{yr_start}-{yr_end}), retry {attempt+1}/{_MAX_RETRIES} in {wait}s"
                )
                time.sleep(wait)
            else:
                # Final attempt, non-retryable error
                break

    # All retries exhausted
    logger.error(
        f"  FAILED batch{item['batch_idx']:02d} {yr_start}-{yr_end} "
        f"after {_MAX_RETRIES} attempts -- skipping"
    )
    with _lock:
        _progress["calls"] += 1
        _progress["errors"] += 1
        _progress["failed_items"].append(
            f"batch{item['batch_idx']:02d} {yr_start}-{yr_end} ({len(sites_to_fetch)} sites)"
        )
    return 0


def main():
    parser = argparse.ArgumentParser(description="Download turbidity gap-fill data")
    parser.add_argument("--batch-size", type=int, default=10,
                        help="Sites per API call (default 10, keep small for reliability)")
    parser.add_argument("--years-per-chunk", type=int, default=1,
                        help="Years per API call chunk (default 1)")
    parser.add_argument("--workers", type=int, default=3,
                        help="Concurrent API calls (default 3)")
    parser.add_argument("--call-timeout", type=int, default=180,
                        help="Seconds per API call timeout (default 180)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan without downloading")
    args = parser.parse_args()

    import warnings
    warnings.filterwarnings("ignore")

    # Check for API token
    if os.getenv("API_USGS_PAT"):
        logger.info("USGS API token found")
    else:
        logger.warning(
            "No API_USGS_PAT token set! You may be rate-limited. "
            "Get a free token at https://api.waterdata.usgs.gov/"
        )

    gaps_df = load_gaps()
    if len(gaps_df) == 0:
        logger.info("No gaps to fill!")
        return

    work_items = build_work_items(gaps_df, args.batch_size, args.years_per_chunk)

    # Count pre-existing (will be skipped)
    n_existing = 0
    for item in work_items:
        all_exist = all(
            _gap_fill_exists(sn, item["yr_start"], item["yr_end"])
            for sn in item["site_numbers"]
        )
        if all_exist:
            n_existing += 1

    n_batches = max(item["batch_idx"] for item in work_items) + 1

    logger.info(f"Gap-fill download plan:")
    logger.info(f"  {len(gaps_df)} sites in {n_batches} site-batches")
    logger.info(f"  {len(work_items)} API calls ({n_existing} already cached)")
    logger.info(f"  Batch size: {args.batch_size} sites, {args.years_per_chunk}yr chunks")
    logger.info(f"  Workers: {args.workers}")

    if args.dry_run:
        est_sec_per_call = 25  # ~25s per call for 10 sites x 1yr
        est_min = (len(work_items) - n_existing) * est_sec_per_call / 60 / args.workers
        logger.info(f"\nDRY RUN: ~{len(work_items) - n_existing} new calls, "
                     f"est ~{est_min:.0f} min with {args.workers} workers")
        return

    start_time = time.time()

    # Dispatch all work items concurrently with a thread pool
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(execute_work_item, item, len(work_items), args.call_timeout): item
            for item in work_items
        }

        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                item = futures[future]
                logger.error(f"Unhandled error in batch{item['batch_idx']} "
                             f"{item['yr_start']}-{item['yr_end']}: {e}")

    elapsed = time.time() - start_time
    logger.info(f"\nGap-fill complete:")
    logger.info(f"  {_progress['rows']:,} rows saved")
    logger.info(f"  {_progress['calls']} API calls ({_progress['skipped']} skipped, "
                f"{_progress['errors']} errors)")
    logger.info(f"  Time: {elapsed/60:.1f} min")
    logger.info(f"  Output: {CONT_DIR}/USGS_*/63680/gap_fill_*.parquet")


if __name__ == "__main__":
    main()
