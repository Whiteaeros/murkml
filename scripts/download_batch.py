"""Batch download USGS data using multi-site API calls.

Uses dataretrieval.nwis.get_iv() for continuous data and
dataretrieval.wqp.get_results() for discrete samples.

Reads qualified_sites.parquet (413 sites) and only downloads
params/years that actually exist per site.

Usage:
    python scripts/download_batch.py --continuous-only
    python scripts/download_batch.py --continuous-only --batch-size 50
    python scripts/download_batch.py --discrete-only
    python scripts/download_batch.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from murkml.provenance import start_run, log_step, log_file, end_run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"

CONTINUOUS_PARAMS = "63680,00095,00300,00400,00010,00060"
CONTINUOUS_PARAM_NAMES = {
    "63680": "turbidity", "00095": "conductance", "00300": "do",
    "00400": "ph", "00010": "temp", "00060": "discharge",
}

DISCRETE_PCODES = "80154;00665;00631;00671"
DISCRETE_PCODE_NAMES = {
    "80154": "ssc", "00665": "total_phosphorus",
    "00631": "nitrate_nitrite", "00671": "orthophosphate",
}


def _build_smart_batches(
    sites_df: pd.DataFrame,
    batch_size: int = 30,
    years_per_call: int = 2,
) -> list[dict]:
    """Sort sites by start year, batch them, use each batch's actual year range.

    Sorting by start year clusters sites with similar ranges naturally.
    Each batch uses the union (min start, max end) of its sites' ranges.
    This avoids tiny-group fragmentation while still skipping years no site needs.
    """
    df = sites_df.sort_values("download_start_year").reset_index(drop=True)

    batches = []
    for i in range(0, len(df), batch_size):
        batch_df = df.iloc[i:i + batch_size]
        site_numbers = [s.replace("USGS-", "") for s in batch_df["site_id"].tolist()]

        # Union of year ranges for this batch
        yr_start = int(batch_df["download_start_year"].min())
        yr_end = int(batch_df["download_end_year"].max())

        # Build year chunks
        year_chunks = []
        y = yr_start
        while y < yr_end:
            y_end = min(y + years_per_call, yr_end)
            year_chunks.append((y, y_end))
            y = y_end

        batches.append({
            "site_numbers": site_numbers,
            "year_chunks": year_chunks,
            "yr_range": f"{yr_start}-{yr_end}",
        })

    return batches


def download_continuous_smart(
    sites_df: pd.DataFrame,
    batch_size: int = 30,
    years_per_call: int = 2,
    call_timeout: int = 300,
    dry_run: bool = False,
):
    """Download continuous IV data using smart year-range batching.

    Only downloads years within each site's active range.
    Output goes to data/continuous_batch_v2/.

    Args:
        sites_df: qualified_sites.parquet DataFrame
        batch_size: Sites per API call (30 default, test 50)
        years_per_call: Years per time chunk (2 to avoid timeout on dense periods)
        call_timeout: Max seconds per API call before retry
        dry_run: If True, just print plan without downloading
    """
    import dataretrieval.nwis as nwis
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

    cache_dir = DATA_DIR / "continuous_batch_v2"
    cache_dir.mkdir(parents=True, exist_ok=True)

    batches = _build_smart_batches(sites_df, batch_size, years_per_call)

    # Count total API calls
    total_calls = sum(len(b["year_chunks"]) for b in batches)
    blind_calls = len(batches) * 7  # 2006-2026 = 7 chunks of 3yr

    logger.info(f"Smart download plan:")
    logger.info(f"  {len(sites_df)} sites in {len(batches)} batches")
    logger.info(f"  {total_calls} API calls (vs {blind_calls} if all 2006-2026)")
    logger.info(f"  Batch size: {batch_size}, {years_per_call}yr chunks")

    for i, b in enumerate(batches):
        logger.info(f"  Batch {i+1}: {len(b['site_numbers'])} sites, "
                    f"{b['yr_range']} ({len(b['year_chunks'])} chunks)")

    if dry_run:
        est_minutes = total_calls * 35 / 60
        logger.info(f"\nDRY RUN: Would make {total_calls} calls, ~{est_minutes:.0f} min")
        return 0

    call_count = 0
    total_rows = 0
    call_times = []

    for group_idx, group in enumerate(batches):
        site_numbers = group["site_numbers"]
        year_chunks = group["year_chunks"]

        logger.info(f"\n--- Batch {group_idx+1}/{len(batches)}: "
                    f"{len(site_numbers)} sites, {group['yr_range']} ---")

        for yr_start, yr_end in year_chunks:
            cache_file = cache_dir / f"v2_grp{group_idx:03d}_{yr_start}_{yr_end}.parquet"

            if cache_file.exists():
                existing = pd.read_parquet(cache_file)
                total_rows += len(existing)
                call_count += 1
                continue

            call_count += 1

            # ETA based on rolling average
            if call_times:
                avg_time = sum(call_times[-10:]) / len(call_times[-10:])
                remaining = (total_calls - call_count) * avg_time
                eta_str = f", ETA {remaining/60:.0f}min"
            else:
                eta_str = ""

            logger.info(f"  [{call_count}/{total_calls}] {yr_start}-{yr_end} "
                        f"({len(site_numbers)} sites{eta_str})")

            call_start = time.time()
            for attempt in range(3):
                try:
                    # Use thread-based timeout to prevent infinite hangs
                    # dataretrieval doesn't support request timeouts natively
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(
                            nwis.get_iv,
                            sites=site_numbers,
                            parameterCd=CONTINUOUS_PARAMS,
                            start=f"{yr_start}-01-01",
                            end=f"{yr_end}-01-01",
                        )
                        df, _ = future.result(timeout=call_timeout)

                    if df is not None and len(df) > 0:
                        df = df.reset_index()
                        df.to_parquet(cache_file, index=False)
                        total_rows += len(df)
                        logger.info(f"    {len(df):,} rows")
                    else:
                        pd.DataFrame().to_parquet(cache_file)
                        logger.info(f"    0 rows")
                    break

                except FuturesTimeout:
                    logger.warning(f"    Timeout ({call_timeout}s) on attempt {attempt+1}/3, retrying...")
                    time.sleep(10)
                except Exception as e:
                    err_str = str(e).lower()
                    err_type = type(e).__name__
                    if "429" in str(e) or "rate" in err_str:
                        wait = 2 ** attempt * 30
                        logger.warning(f"    Rate limited, waiting {wait}s")
                        time.sleep(wait)
                    elif attempt < 2:
                        logger.warning(f"    Error ({err_type}): {e}, retrying...")
                        time.sleep(5)
                    else:
                        logger.error(f"    FAILED after 3 attempts ({err_type}): {e}")
                        break

            call_times.append(time.time() - call_start)
            time.sleep(2)

        logger.info(f"  Batch {group_idx+1} done (total: {total_rows:,} rows)")

    logger.info(f"\nSmart download complete: {total_rows:,} total rows, "
                f"{call_count} calls in {sum(call_times)/60:.1f}min")
    return total_rows


def download_discrete_batch(
    site_ids: list[str],
    batch_size: int = 100,
):
    """Download discrete lab samples via WQP in multi-site batches.

    Args:
        site_ids: USGS site IDs WITH 'USGS-' prefix
        batch_size: Sites per WQP call (100 works well)
    """
    import dataretrieval.wqp as wqp

    cache_dir = DATA_DIR / "discrete_batch"
    cache_dir.mkdir(parents=True, exist_ok=True)

    batches = [site_ids[i:i + batch_size]
               for i in range(0, len(site_ids), batch_size)]

    logger.info(f"Discrete download: {len(site_ids)} sites in {len(batches)} batches")

    total_rows = 0

    for batch_idx, batch in enumerate(batches):
        cache_file = cache_dir / f"discrete_batch_{batch_idx:04d}.parquet"

        if cache_file.exists():
            existing = pd.read_parquet(cache_file)
            total_rows += len(existing)
            logger.info(f"  Batch {batch_idx+1}/{len(batches)}: cached ({len(existing)} rows)")
            continue

        sites_str = ";".join(batch)
        logger.info(f"  Batch {batch_idx+1}/{len(batches)}: {len(batch)} sites")

        for attempt in range(3):
            try:
                df, _ = wqp.get_results(
                    siteid=sites_str,
                    pCode=DISCRETE_PCODES,
                )

                if df is not None and len(df) > 0:
                    df.to_parquet(cache_file, index=False)
                    total_rows += len(df)
                    logger.info(f"    {len(df)} rows")
                else:
                    pd.DataFrame().to_parquet(cache_file)
                    logger.info(f"    0 rows")
                break

            except Exception as e:
                if "429" in str(e) or "rate" in str(e).lower():
                    wait = 2 ** attempt * 30
                    logger.warning(f"    Rate limited, waiting {wait}s")
                    time.sleep(wait)
                elif attempt < 2:
                    logger.warning(f"    Error: {e}, retrying...")
                    time.sleep(5)
                else:
                    logger.error(f"    FAILED after 3 attempts: {e}")
                    break

        time.sleep(2)

    logger.info(f"\nDiscrete download complete: {total_rows:,} total rows")
    return total_rows


def _find_primary_column(columns: list[str], pcode: str) -> tuple[str | None, str | None]:
    """Find the primary value and qualifier columns for a parameter code.

    NWIS batch responses can have multiple sensors per parameter, e.g.:
        63680, 63680_from dts-12, 63680_bgc project [east fender
    We pick the plain pcode column (primary sensor). If it doesn't exist,
    pick the one with the most non-null values at merge time.

    Returns (value_col, qualifier_col) or (None, None).
    """
    # Exact match is the primary sensor
    if pcode in columns:
        cd_col = f"{pcode}_cd" if f"{pcode}_cd" in columns else None
        return pcode, cd_col

    # Look for columns that start with the pcode (alternate sensors)
    candidates = [c for c in columns if c.startswith(pcode) and not c.endswith("_cd")]
    if candidates:
        # Pick the first one (they're usually ordered by priority)
        val_col = candidates[0]
        cd_col = f"{val_col}_cd" if f"{val_col}_cd" in columns else None
        return val_col, cd_col

    return None, None


def merge_continuous_batches(use_v2: bool = True):
    """Merge batch parquet files into per-site cache files.

    Converts from batch format to the per-site format expected by
    the rest of the pipeline (data/continuous/{site_id}/{param}/{year}.parquet).

    Handles duplicate sensor columns by picking the primary sensor
    (plain parameter code column) or the first alternate.
    """
    if use_v2:
        batch_dir = DATA_DIR / "continuous_batch_v2"
        glob_pattern = "v2_*.parquet"
    else:
        batch_dir = DATA_DIR / "continuous_batch"
        glob_pattern = "batch_*.parquet"
    cont_dir = DATA_DIR / "continuous"

    if not batch_dir.exists():
        logger.warning(f"No batch directory found: {batch_dir}")
        return

    batch_files = sorted(batch_dir.glob(glob_pattern))
    logger.info(f"Merging {len(batch_files)} batch files into per-site cache...")

    total_sites = set()
    for bf in batch_files:
        df = pd.read_parquet(bf)
        if len(df) == 0:
            continue

        if "site_no" not in df.columns:
            continue

        all_cols = list(df.columns)

        for site_no, site_df in df.groupby("site_no"):
            site_id = f"USGS_{site_no}"
            total_sites.add(site_id)

            site_dir = cont_dir / site_id
            site_dir.mkdir(parents=True, exist_ok=True)

            for pcode, pname in CONTINUOUS_PARAM_NAMES.items():
                val_col, cd_col = _find_primary_column(all_cols, pcode)
                if val_col is None:
                    continue

                param_dir = site_dir / pcode
                param_dir.mkdir(parents=True, exist_ok=True)

                # Build output dataframe with standard column names
                keep_cols = ["datetime", val_col]
                param_data = site_df[keep_cols].dropna(subset=[val_col]).copy()
                if len(param_data) == 0:
                    continue

                param_data = param_data.rename(columns={val_col: "value"})

                if cd_col and cd_col in site_df.columns:
                    raw_cd = site_df.loc[param_data.index, cd_col].values
                    param_data["raw_cd"] = raw_cd

                    # NWIS _cd format: "A" = Approved, "P" = Provisional,
                    # "A, e" = Approved+estimated, "A, [91]" = Approved+qualifier
                    # Parse approval status from the first character
                    def _parse_approval(val):
                        if pd.isna(val) or str(val).strip() == "":
                            return "Unknown"
                        first = str(val).strip()[0].upper()
                        if first == "A":
                            return "Approved"
                        elif first == "P":
                            return "Provisional"
                        return "Unknown"

                    def _parse_qualifier(val):
                        if pd.isna(val) or str(val).strip() == "":
                            return None
                        parts = str(val).split(",")
                        # Everything after the first part (approval) is qualifiers
                        quals = [p.strip() for p in parts[1:] if p.strip()]
                        return ", ".join(quals) if quals else None

                    param_data["approval_status"] = pd.Series(raw_cd).apply(_parse_approval).values
                    param_data["qualifier"] = pd.Series(raw_cd).apply(_parse_qualifier).values
                    param_data.drop(columns=["raw_cd"], inplace=True)
                else:
                    param_data["approval_status"] = "Unknown"
                    param_data["qualifier"] = None

                # Rename to 'time' for compatibility with assemble pipeline
                param_data = param_data.rename(columns={"datetime": "time"})
                param_data["time"] = pd.to_datetime(param_data["time"])
                param_data["year"] = param_data["time"].dt.year

                for year, year_df in param_data.groupby("year", observed=True):
                    year_end = year + 1
                    cache_file = param_dir / f"{year}_{year_end}.parquet"
                    if not cache_file.exists():
                        year_df.drop(columns=["year"]).to_parquet(cache_file, index=False)

    logger.info(f"Merged data for {len(total_sites)} sites")


def merge_discrete_batches():
    """Merge WQP batch files into per-site discrete cache files.

    WQP returns wide-format data with verbose column names. We save the
    full WQP response per site/param for downstream processing by the
    existing discrete.py loader (which already handles WQP format).
    """
    batch_dir = DATA_DIR / "discrete_batch"
    disc_dir = DATA_DIR / "discrete"
    disc_dir.mkdir(parents=True, exist_ok=True)

    if not batch_dir.exists():
        logger.warning("No discrete batch directory found")
        return

    batch_files = sorted(batch_dir.glob("discrete_batch_*.parquet"))
    logger.info(f"Merging {len(batch_files)} discrete batch files...")

    all_dfs = []
    for bf in batch_files:
        df = pd.read_parquet(bf)
        if len(df) > 0:
            all_dfs.append(df)

    if not all_dfs:
        logger.warning("No discrete data found")
        return

    combined = pd.concat(all_dfs, ignore_index=True)
    logger.info(f"Total discrete rows: {len(combined)}")

    # WQP column names
    site_col = "MonitoringLocationIdentifier"
    if site_col not in combined.columns:
        for alt in ["monitoringLocationIdentifier", "MonitoringLocationID"]:
            if alt in combined.columns:
                site_col = alt
                break
        else:
            # Save combined and let downstream handle it
            out_path = disc_dir / "all_discrete_wqp.parquet"
            combined.to_parquet(out_path, index=False)
            logger.info(f"Could not find site column. Saved raw to {out_path}")
            return

    # WQP uses USGSPCode or CharacteristicName for parameter identification
    pcode_col = None
    for candidate in ["USGSPCode", "pCode", "CharacteristicName"]:
        if candidate in combined.columns:
            pcode_col = candidate
            break

    # Map CharacteristicName to our param names if no pcode column
    char_name_map = {
        "Suspended sediment concentration (SSC)": "ssc",
        "Suspended Sediment Concentration (SSC)": "ssc",
        "Total suspended solids": "ssc",  # close enough for discovery
        "Phosphorus": "total_phosphorus",
        "Inorganic nitrogen (nitrate and nitrite)": "nitrate_nitrite",
        "Nitrate plus nitrite": "nitrate_nitrite",
        "Orthophosphate": "orthophosphate",
    }

    pcode_to_name = {
        "80154": "ssc", "00665": "total_phosphorus",
        "00631": "nitrate_nitrite", "00671": "orthophosphate",
    }

    total_sites = set()
    n_saved = 0

    for site_id_raw, site_group in combined.groupby(site_col):
        site_stem = str(site_id_raw).replace("-", "_")
        total_sites.add(site_id_raw)

        if pcode_col and pcode_col != "CharacteristicName":
            # Group by parameter code
            for pcode_val, param_group in site_group.groupby(pcode_col):
                pname = pcode_to_name.get(str(pcode_val).strip(), str(pcode_val))
                cache_file = disc_dir / f"{site_stem}_{pname}.parquet"
                if not cache_file.exists():
                    param_group.to_parquet(cache_file, index=False)
                    n_saved += 1
        elif pcode_col == "CharacteristicName":
            # Group by characteristic name and map to our param names
            for char_name, param_group in site_group.groupby(pcode_col):
                pname = char_name_map.get(str(char_name))
                if pname is None:
                    continue
                cache_file = disc_dir / f"{site_stem}_{pname}.parquet"
                if not cache_file.exists():
                    param_group.to_parquet(cache_file, index=False)
                    n_saved += 1
        else:
            # No parameter column — save everything per site
            cache_file = disc_dir / f"{site_stem}_all.parquet"
            if not cache_file.exists():
                site_group.to_parquet(cache_file, index=False)
                n_saved += 1

    logger.info(f"Saved {n_saved} files for {len(total_sites)} sites")


def main():
    start_run("download_batch")

    parser = argparse.ArgumentParser(description="Batch download USGS data")
    parser.add_argument("--batch-size", type=int, default=30,
                        help="Sites per API call for continuous (default 30)")
    parser.add_argument("--discrete-batch-size", type=int, default=100,
                        help="Sites per WQP call for discrete (default 100)")
    parser.add_argument("--continuous-only", action="store_true")
    parser.add_argument("--discrete-only", action="store_true")
    parser.add_argument("--skip-merge", action="store_true",
                        help="Skip merging batches into per-site files")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print download plan without making API calls")
    parser.add_argument("--use-old-batches", action="store_true",
                        help="Merge from old continuous_batch/ instead of v2")
    args = parser.parse_args()

    # Load QUALIFIED sites (not all discovered)
    sites_path = DATA_DIR / "qualified_sites.parquet"
    if not sites_path.exists():
        logger.error(f"No qualified sites at {sites_path}. Run qualify_sites.py first.")
        return

    sites_df = pd.read_parquet(sites_path)
    site_ids = sites_df["site_id"].tolist()

    logger.info(f"Qualified sites: {len(site_ids)}")
    logger.info(f"Year ranges: {sites_df['download_start_year'].min()}-"
                f"{sites_df['download_end_year'].max()}")
    log_step("start", n_sites=len(site_ids))

    # Download continuous (smart: per-site year ranges)
    if not args.discrete_only:
        logger.info(f"\n{'='*60}")
        logger.info("CONTINUOUS DATA — SMART DOWNLOAD (nwis.get_iv batch)")
        logger.info(f"{'='*60}")
        n_cont = download_continuous_smart(
            sites_df,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )
        log_step("continuous_complete", total_rows=n_cont)

    # Download discrete
    if not args.continuous_only:
        logger.info(f"\n{'='*60}")
        logger.info("DISCRETE DATA (WQP batch)")
        logger.info(f"{'='*60}")
        n_disc = download_discrete_batch(
            site_ids,
            batch_size=args.discrete_batch_size,
        )
        log_step("discrete_complete", total_rows=n_disc)

    # Merge into per-site format
    if not args.skip_merge and not args.dry_run:
        logger.info(f"\n{'='*60}")
        logger.info("MERGING BATCHES INTO PER-SITE FILES")
        logger.info(f"{'='*60}")
        if not args.discrete_only:
            merge_continuous_batches(use_v2=not args.use_old_batches)
        if not args.continuous_only:
            merge_discrete_batches()

    end_run()
    logger.info("\nDone.")


if __name__ == "__main__":
    main()
