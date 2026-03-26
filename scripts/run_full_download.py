"""Orchestrator: Discover sites → StreamCat → Weather → USGS data download.

This is the "go to bed" script. It runs the full download pipeline:

Phase 1: DISCOVER — Find all USGS sites with paired turbidity + SSC data (fast, ~30 min)
Phase 2: STREAMCAT — Download watershed attributes for all sites (fast, ~2 hr)
Phase 3: WEATHER — Download GridMET daily precip/temp for all sites (fast, ~1.5 hr)
Phase 4: USGS DATA — Download continuous + discrete data for NEW sites (slow, overnight)

Each phase is resume-safe. If the script is interrupted, re-run it and it picks up
where it left off.

Usage:
    python scripts/run_full_download.py [--min-samples 15] [--skip-discovery]
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Load .env file if it exists (for API_USGS_PAT)
env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

import warnings
warnings.filterwarnings("ignore")

from dataretrieval import waterdata
from murkml.provenance import start_run, log_step, log_file, end_run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"
PYTHON = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")

CONTINUOUS_PARAMS = {
    "63680": "turbidity",
    "00095": "conductance",
    "00300": "do",
    "00400": "ph",
    "00010": "temp",
    "00060": "discharge",
}

DISCRETE_PARAMS = {
    "80154": "ssc",
    "00665": "total_phosphorus",
    "00631": "nitrate_nitrite",
    "00671": "orthophosphate",
}


# ============================================================
# PHASE 1: DISCOVER ALL VIABLE SITES
# ============================================================

def discover_all_sites(min_samples: int = 15) -> pd.DataFrame:
    """Find all USGS sites with continuous turbidity AND discrete SSC.

    Searches all 50 states. Caches results to avoid re-querying.
    """
    cache_path = DATA_DIR / "all_discovered_sites.parquet"
    if cache_path.exists():
        cached = pd.read_parquet(cache_path)
        logger.info(f"Discovery cache exists: {len(cached)} sites")
        return cached

    logger.info(f"\n{'='*60}")
    logger.info("PHASE 1: SITE DISCOVERY")
    logger.info(f"{'='*60}")
    logger.info(f"Finding all USGS sites with turbidity + ≥{min_samples} SSC samples...")

    # Step 1: Find all sites with continuous turbidity
    logger.info("Step 1: Querying turbidity time series metadata (all states)...")
    all_states = [
        "Alabama", "Alaska", "Arizona", "Arkansas", "California",
        "Colorado", "Connecticut", "Delaware", "Florida", "Georgia",
        "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa",
        "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland",
        "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri",
        "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey",
        "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
        "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
        "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
        "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
    ]

    turb_sites = set()
    for state in all_states:
        try:
            df, _ = waterdata.get_time_series_metadata(
                parameter_code="63680",
                state_name=state,
            )
            if df is not None and len(df) > 0:
                sites = df["monitoring_location_id"].unique()
                usgs_sites = [s for s in sites if str(s).startswith("USGS")]
                turb_sites.update(usgs_sites)
                if usgs_sites:
                    logger.info(f"  {state}: {len(usgs_sites)} turbidity sites")
        except Exception as e:
            logger.warning(f"  {state}: {e}")
        time.sleep(1)

    logger.info(f"Total turbidity sites found: {len(turb_sites)}")

    # Step 2: Check each for discrete SSC samples
    logger.info(f"\nStep 2: Checking {len(turb_sites)} sites for SSC samples...")

    # Load any existing progress
    progress_path = DATA_DIR / "discovery_progress.parquet"
    if progress_path.exists():
        progress = pd.read_parquet(progress_path)
        checked = set(progress["site_id"])
        logger.info(f"  Resuming: {len(checked)} already checked")
    else:
        progress = pd.DataFrame(columns=["site_id", "n_ssc", "state"])
        checked = set()

    sites_to_check = sorted(turb_sites - checked)
    new_records = []

    for i, site_id in enumerate(sites_to_check):
        if (i + 1) % 25 == 0:
            logger.info(f"  [{i+1}/{len(sites_to_check)}] checking SSC...")
            # Save progress periodically
            if new_records:
                progress = pd.concat([progress, pd.DataFrame(new_records)], ignore_index=True)
                progress.to_parquet(progress_path, index=False)
                new_records = []

        try:
            samples, _ = waterdata.get_samples(
                monitoringLocationIdentifier=site_id,
                usgsPCode="80154",
            )
            n_ssc = len(samples) if samples is not None else 0
        except Exception:
            n_ssc = 0

        # Extract state from site ID or leave blank
        new_records.append({
            "site_id": site_id,
            "n_ssc": n_ssc,
        })
        time.sleep(1.5)  # Respectful delay for USGS API

    # Final save
    if new_records:
        progress = pd.concat([progress, pd.DataFrame(new_records)], ignore_index=True)
        progress.to_parquet(progress_path, index=False)

    # Filter to viable sites
    viable = progress[progress["n_ssc"] >= min_samples].copy()
    viable = viable.sort_values("n_ssc", ascending=False).reset_index(drop=True)

    logger.info(f"\nDiscovery complete:")
    logger.info(f"  Total turbidity sites: {len(turb_sites)}")
    logger.info(f"  Sites with ≥{min_samples} SSC samples: {len(viable)}")
    logger.info(f"  Total SSC samples across viable sites: {viable['n_ssc'].sum()}")

    # Save final list
    viable.to_parquet(cache_path, index=False)
    log_file(cache_path, role="output")
    return viable


# ============================================================
# PHASE 4: DOWNLOAD USGS DATA FOR NEW SITES
# ============================================================

def get_already_downloaded_sites() -> set:
    """Find sites that already have continuous data cached."""
    cont_dir = DATA_DIR / "continuous"
    if not cont_dir.exists():
        return set()
    downloaded = set()
    for site_dir in cont_dir.iterdir():
        if site_dir.is_dir():
            # Convert dir name back to site ID: USGS_01491000 -> USGS-01491000
            site_id = site_dir.name.replace("_", "-")
            # Check if it actually has turbidity data
            turb_dir = site_dir / "63680"
            if turb_dir.exists() and any(turb_dir.glob("*.parquet")):
                downloaded.add(site_id)
    return downloaded


def get_site_date_range(site_id: str, param_code: str):
    """Query the actual date range for a site+param from time series metadata."""
    try:
        ts, _ = waterdata.get_time_series_metadata(
            monitoring_location_id=site_id, parameter_code=param_code,
        )
        if ts is not None and len(ts) > 0:
            begin = pd.to_datetime(ts["begin"].iloc[0])
            end = pd.to_datetime(ts["end"].iloc[0])
            if pd.notna(begin) and pd.notna(end):
                return begin.year, end.year + 1
    except Exception:
        pass
    return None, None


def download_continuous_for_site(site_id: str, delay: float = 2.5, max_retries: int = 3):
    """Download all continuous parameters for a site."""
    site_stem = site_id.replace("-", "_")
    total_records = 0

    for pcode, pname in CONTINUOUS_PARAMS.items():
        cache_dir = DATA_DIR / "continuous" / site_stem / pcode
        cache_dir.mkdir(parents=True, exist_ok=True)

        start_year, end_year = get_site_date_range(site_id, pcode)
        if not start_year:
            end_year = 2027
            start_year = end_year - 15

        for year in range(start_year, end_year + 1, 3):
            chunk_end = min(year + 3, end_year + 1)
            cache_file = cache_dir / f"{year}_{chunk_end}.parquet"
            if cache_file.exists():
                total_records += len(pd.read_parquet(cache_file))
                continue

            for attempt in range(max_retries):
                try:
                    df, _ = waterdata.get_continuous(
                        monitoring_location_id=site_id,
                        parameter_code=pcode,
                        time=f"{year}-01-01/{chunk_end}-01-01",
                    )
                    if df is not None and len(df) > 0:
                        df.to_parquet(cache_file)
                        total_records += len(df)
                    else:
                        pd.DataFrame().to_parquet(cache_file)
                    break
                except Exception as e:
                    if "429" in str(e):
                        wait = min(2 ** attempt * 30, 90)  # Cap at 90s
                        logger.warning(f"    Rate limited on {pname} {year}-{chunk_end}, "
                                       f"retry {attempt+1}/{max_retries} in {wait}s")
                        time.sleep(wait)
                    else:
                        logger.debug(f"    {pname} {year}-{chunk_end}: {e}")
                        break  # Non-rate-limit error, skip chunk (leave uncached for retry)
            time.sleep(delay)

    return total_records


def download_discrete_for_site(site_id: str, max_retries: int = 3):
    """Download all discrete parameters for a site."""
    site_stem = site_id.replace("-", "_")
    cache_dir = DATA_DIR / "discrete"
    cache_dir.mkdir(parents=True, exist_ok=True)
    total = 0

    for pcode, pname in DISCRETE_PARAMS.items():
        cache_file = cache_dir / f"{site_stem}_{pname}.parquet"
        if cache_file.exists():
            df = pd.read_parquet(cache_file)
            total += len(df)
            continue

        for attempt in range(max_retries):
            try:
                df, _ = waterdata.get_samples(
                    monitoringLocationIdentifier=site_id,
                    usgsPCode=pcode,
                )
                if df is not None and len(df) > 0:
                    df.to_parquet(cache_file)
                    total += len(df)
                else:
                    pd.DataFrame().to_parquet(cache_file)
                break
            except Exception as e:
                if "429" in str(e):
                    wait = min(2 ** attempt * 15, 60)  # Cap at 60s
                    logger.warning(f"    Rate limited on {pname}, retry {attempt+1}/{max_retries} in {wait}s")
                    time.sleep(wait)
                else:
                    break
        time.sleep(1)

    return total


def download_usgs_data(sites: pd.DataFrame, delay: float = 2.5):
    """Download continuous + discrete data for sites that don't have it yet."""
    already = get_already_downloaded_sites()
    new_sites = [s for s in sites["site_id"] if s not in already]

    logger.info(f"\n{'='*60}")
    logger.info("PHASE 4: USGS DATA DOWNLOAD")
    logger.info(f"{'='*60}")
    logger.info(f"Total sites: {len(sites)}")
    logger.info(f"Already downloaded: {len(already)}")
    logger.info(f"New to download: {len(new_sites)}")

    if not new_sites:
        logger.info("All sites already cached!")
        return

    n_downloaded = 0
    n_errors = 0
    failed_sites = []
    total_start = time.time()

    for i, site_id in enumerate(new_sites):
        logger.info(f"\n[{i+1}/{len(new_sites)}] {site_id}")
        site_start = time.time()

        try:
            # Discrete first (faster, one API call per param)
            n_disc = download_discrete_for_site(site_id)
            logger.info(f"  Discrete: {n_disc} samples")

            # Continuous (slow, multiple year chunks per param)
            # Each chunk retries 3x then moves on — failed chunks stay uncached
            # so the next run picks them up automatically
            n_cont = download_continuous_for_site(site_id, delay=delay)
            logger.info(f"  Continuous: {n_cont} records")

            elapsed = time.time() - site_start
            logger.info(f"  Done in {elapsed:.0f}s")
            n_downloaded += 1

            log_step("download_site", site_id=site_id,
                     n_discrete=n_disc, n_continuous=n_cont,
                     elapsed_sec=round(elapsed))

        except Exception as e:
            logger.error(f"  FAILED: {e}")
            failed_sites.append(site_id)
            n_errors += 1
            # Don't skip — the cached chunks are still good.
            # Just log it and continue to the next site.

        # Progress summary every 10 sites
        if (i + 1) % 10 == 0:
            pct = (i + 1) / len(new_sites) * 100
            total_elapsed = (time.time() - total_start) / 60
            rate = (i + 1) / total_elapsed if total_elapsed > 0 else 0
            remaining = (len(new_sites) - i - 1) / rate if rate > 0 else 0
            logger.info(
                f"\n  --- Progress: {i+1}/{len(new_sites)} ({pct:.0f}%) | "
                f"{n_downloaded} ok, {n_errors} errors | "
                f"{total_elapsed:.0f}min elapsed, ~{remaining:.0f}min remaining ---"
            )

    if failed_sites:
        logger.warning(f"\n{len(failed_sites)} sites had errors (partial data may exist):")
        for s in failed_sites:
            logger.warning(f"  {s}")
        logger.info("Re-run this script to retry failed chunks (resume-safe).")


# ============================================================
# MAIN ORCHESTRATOR
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Full download pipeline")
    parser.add_argument("--min-samples", type=int, default=15,
                        help="Min SSC samples to include a site (default 15)")
    parser.add_argument("--skip-discovery", action="store_true",
                        help="Skip Phase 1, use existing discovered sites")
    parser.add_argument("--skip-streamcat", action="store_true",
                        help="Skip Phase 2 (StreamCat attributes)")
    parser.add_argument("--skip-weather", action="store_true",
                        help="Skip Phase 3 (GridMET weather)")
    parser.add_argument("--skip-usgs", action="store_true",
                        help="Skip Phase 4 (USGS data download)")
    parser.add_argument("--delay", type=float, default=2.5,
                        help="Delay between USGS API calls (default 2.5s)")
    args = parser.parse_args()

    start_run("full_download")

    # Check for API token
    if os.getenv("API_USGS_PAT"):
        logger.info("USGS API token found")
    else:
        logger.warning(
            "No API_USGS_PAT token! USGS downloads will be rate-limited. "
            "Set it in .env or as environment variable."
        )

    # ---- PHASE 1: DISCOVER ----
    if args.skip_discovery:
        cache_path = DATA_DIR / "all_discovered_sites.parquet"
        if cache_path.exists():
            sites = pd.read_parquet(cache_path)
            logger.info(f"Using cached discovery: {len(sites)} sites")
        else:
            logger.error("No discovery cache and --skip-discovery set!")
            end_run()
            return
    else:
        sites = discover_all_sites(min_samples=args.min_samples)

    logger.info(f"\nViable sites: {len(sites)}")
    log_step("discovery_complete", n_sites=len(sites),
             total_ssc_samples=int(sites["n_ssc"].sum()))

    # ---- PHASES 2-4: RUN IN PARALLEL ----
    # StreamCat and Weather are independent of USGS data download.
    # Launch StreamCat and Weather as subprocesses, run USGS in main process.
    bg_processes = []

    if not args.skip_streamcat:
        logger.info(f"\n{'='*60}")
        logger.info("LAUNCHING: StreamCat attributes (background)")
        logger.info(f"{'='*60}")
        cmd = [PYTHON, str(PROJECT_ROOT / "scripts" / "download_streamcat.py"),
               "--sites-from", "all"]
        streamcat_log = DATA_DIR / "logs" / "streamcat_download.log"
        streamcat_log.parent.mkdir(parents=True, exist_ok=True)
        sc_logfile = open(streamcat_log, "w")
        sc_proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT),
                                   stdout=sc_logfile, stderr=subprocess.STDOUT)
        bg_processes.append(("StreamCat", sc_proc, sc_logfile, streamcat_log))
        logger.info(f"  PID {sc_proc.pid}, log: {streamcat_log}")

    if not args.skip_weather:
        logger.info(f"\n{'='*60}")
        logger.info("LAUNCHING: GridMET weather (background)")
        logger.info(f"{'='*60}")
        cmd = [PYTHON, str(PROJECT_ROOT / "scripts" / "download_weather.py"),
               "--start-year", "2006", "--end-year", "2025"]
        weather_log = DATA_DIR / "logs" / "weather_download.log"
        weather_log.parent.mkdir(parents=True, exist_ok=True)
        wx_logfile = open(weather_log, "w")
        wx_proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT),
                                   stdout=wx_logfile, stderr=subprocess.STDOUT)
        bg_processes.append(("Weather", wx_proc, wx_logfile, weather_log))
        logger.info(f"  PID {wx_proc.pid}, log: {weather_log}")

    # USGS data runs in foreground (it's the slowest and most important to monitor)
    if not args.skip_usgs:
        download_usgs_data(sites, delay=args.delay)
        log_step("usgs_download_complete")

    # Wait for background processes with timeout and monitoring
    BG_TIMEOUT = 4 * 3600  # 4 hours max per background process
    BG_CHECK_INTERVAL = 300  # Check every 5 minutes

    for name, proc, logfile, logpath in bg_processes:
        logger.info(f"Waiting for {name} (PID {proc.pid}, timeout {BG_TIMEOUT//3600}hr)...")
        elapsed = 0
        last_size = 0

        while proc.poll() is None:  # Process still running
            time.sleep(min(BG_CHECK_INTERVAL, BG_TIMEOUT - elapsed))
            elapsed += BG_CHECK_INTERVAL

            # Check log file growth as heartbeat
            try:
                current_size = logpath.stat().st_size
                if current_size > last_size:
                    growth = current_size - last_size
                    logger.info(f"  {name}: still running ({elapsed//60}min, log +{growth} bytes)")
                    last_size = current_size
                else:
                    logger.warning(f"  {name}: log hasn't grown in {BG_CHECK_INTERVAL}s — may be stalled")
            except Exception:
                pass

            if elapsed >= BG_TIMEOUT:
                logger.error(f"  {name}: TIMEOUT after {BG_TIMEOUT//3600}hr — killing")
                proc.kill()
                break

        logfile.close()
        if proc.returncode == 0:
            logger.info(f"  {name} completed successfully")
        elif proc.returncode is None or proc.returncode == -9:
            logger.error(f"  {name} was killed (timeout or stall)")
        else:
            logger.warning(f"  {name} exited with code {proc.returncode}")
        logger.info(f"  Log: {logpath}")
        log_step(f"{name.lower().replace(' ','_')}_complete",
                 returncode=proc.returncode, elapsed_min=elapsed // 60)

    # ---- SUMMARY ----
    logger.info(f"\n{'='*60}")
    logger.info("ALL DOWNLOADS COMPLETE")
    logger.info(f"{'='*60}")

    already = get_already_downloaded_sites()
    logger.info(f"Sites with continuous data: {len(already)}")

    disc_dir = DATA_DIR / "discrete"
    n_disc = len(list(disc_dir.glob("*_ssc.parquet"))) if disc_dir.exists() else 0
    logger.info(f"Sites with SSC discrete data: {n_disc}")

    sc_path = DATA_DIR / "site_attributes_streamcat.parquet"
    if sc_path.exists():
        sc = pd.read_parquet(sc_path)
        logger.info(f"StreamCat attributes: {len(sc)} sites, {len(sc.columns)} features")

    weather_dir = DATA_DIR / "weather"
    if weather_dir.exists():
        n_weather = sum(1 for d in weather_dir.iterdir()
                        if d.is_dir() and (d / "daily_weather.parquet").exists())
        logger.info(f"Weather data: {n_weather} sites")

    end_run()


if __name__ == "__main__":
    main()
