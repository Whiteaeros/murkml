"""Batch download USGS data using multi-site API calls.

Uses dataretrieval.nwis.get_iv() for continuous data and
dataretrieval.wqp.get_results() for discrete samples.

Multi-site requests are 100x faster than per-site API calls:
- 50 sites × 6 params × 1 year = ~75 seconds (one API call)
- Same via per-site API = ~300 calls, rate-limited, hours

Usage:
    python scripts/download_batch.py
    python scripts/download_batch.py --batch-size 30 --start-year 2010
    python scripts/download_batch.py --discrete-only
    python scripts/download_batch.py --continuous-only
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


def download_continuous_batch(
    site_numbers: list[str],
    start_year: int,
    end_year: int,
    batch_size: int = 30,
    years_per_call: int = 3,
):
    """Download continuous IV data in multi-site batches.

    Args:
        site_numbers: USGS site numbers (without 'USGS-' prefix)
        start_year: First year to download
        end_year: Last year to download
        batch_size: Sites per API call (30-50 works well)
        years_per_call: Years per time chunk (3 is safe)
    """
    import dataretrieval.nwis as nwis

    cache_dir = DATA_DIR / "continuous_batch"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Split sites into batches
    batches = [site_numbers[i:i + batch_size]
               for i in range(0, len(site_numbers), batch_size)]

    # Split years into chunks
    year_ranges = []
    y = start_year
    while y < end_year:
        y_end = min(y + years_per_call, end_year)
        year_ranges.append((y, y_end))
        y = y_end

    total_calls = len(batches) * len(year_ranges)
    logger.info(f"Continuous download: {len(site_numbers)} sites in {len(batches)} batches, "
                f"{len(year_ranges)} year chunks = {total_calls} API calls")

    call_count = 0
    total_rows = 0

    for batch_idx, batch in enumerate(batches):
        batch_start = time.time()
        batch_rows = 0

        for yr_start, yr_end in year_ranges:
            cache_file = cache_dir / f"batch_{batch_idx:04d}_{yr_start}_{yr_end}.parquet"

            if cache_file.exists():
                existing = pd.read_parquet(cache_file)
                batch_rows += len(existing)
                call_count += 1
                continue

            call_count += 1
            logger.info(f"  [{call_count}/{total_calls}] Batch {batch_idx+1}/{len(batches)}, "
                        f"{yr_start}-{yr_end} ({len(batch)} sites)")

            for attempt in range(3):
                try:
                    df, _ = nwis.get_iv(
                        sites=batch,
                        parameterCd=CONTINUOUS_PARAMS,
                        start=f"{yr_start}-01-01",
                        end=f"{yr_end}-01-01",
                    )

                    if df is not None and len(df) > 0:
                        # Reset multi-index to columns for parquet storage
                        df = df.reset_index()
                        df.to_parquet(cache_file, index=False)
                        batch_rows += len(df)
                        logger.info(f"    {len(df)} rows")
                    else:
                        # Save empty marker
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

            # Brief pause between calls to be respectful
            time.sleep(2)

        batch_elapsed = time.time() - batch_start
        total_rows += batch_rows
        logger.info(f"  Batch {batch_idx+1} done: {batch_rows} rows in {batch_elapsed:.0f}s "
                    f"(total: {total_rows:,} rows)")

    logger.info(f"\nContinuous download complete: {total_rows:,} total rows")
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


def merge_continuous_batches():
    """Merge batch parquet files into per-site cache files.

    Converts from batch format to the per-site format expected by
    the rest of the pipeline (data/continuous/{site_id}/{param}/{year}.parquet).

    Handles duplicate sensor columns by picking the primary sensor
    (plain parameter code column) or the first alternate.
    """
    batch_dir = DATA_DIR / "continuous_batch"
    cont_dir = DATA_DIR / "continuous"

    if not batch_dir.exists():
        logger.warning("No batch directory found")
        return

    batch_files = sorted(batch_dir.glob("batch_*.parquet"))
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

                param_data["datetime"] = pd.to_datetime(param_data["datetime"])
                param_data["year"] = param_data["datetime"].dt.year

                for year, year_df in param_data.groupby("year"):
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
    parser.add_argument("--start-year", type=int, default=2006,
                        help="Start year for continuous data")
    parser.add_argument("--end-year", type=int, default=2026,
                        help="End year for continuous data")
    parser.add_argument("--continuous-only", action="store_true")
    parser.add_argument("--discrete-only", action="store_true")
    parser.add_argument("--skip-merge", action="store_true",
                        help="Skip merging batches into per-site files")
    args = parser.parse_args()

    # Load discovered sites
    sites_path = DATA_DIR / "all_discovered_sites.parquet"
    if not sites_path.exists():
        logger.error(f"No discovered sites at {sites_path}. Run discovery first.")
        return

    sites_df = pd.read_parquet(sites_path)
    site_ids = sites_df["site_id"].tolist()  # USGS-XXXXXXXX format
    site_numbers = [s.replace("USGS-", "") for s in site_ids]

    logger.info(f"Sites: {len(site_ids)}")
    log_step("start", n_sites=len(site_ids), start_year=args.start_year,
             end_year=args.end_year)

    # Download continuous
    if not args.discrete_only:
        logger.info(f"\n{'='*60}")
        logger.info("CONTINUOUS DATA (nwis.get_iv batch)")
        logger.info(f"{'='*60}")
        n_cont = download_continuous_batch(
            site_numbers,
            start_year=args.start_year,
            end_year=args.end_year,
            batch_size=args.batch_size,
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
    if not args.skip_merge:
        logger.info(f"\n{'='*60}")
        logger.info("MERGING BATCHES INTO PER-SITE FILES")
        logger.info(f"{'='*60}")
        if not args.discrete_only:
            merge_continuous_batches()
        if not args.continuous_only:
            merge_discrete_batches()

    end_run()
    logger.info("\nDone.")


if __name__ == "__main__":
    main()
