"""Download all data for external validation sites.

Downloads continuous sensor data and discrete lab data for sites in new states
that weren't part of the training set. These serve as a true external holdout.

Usage:
    python scripts/download_validation_sites.py
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd

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
VAL_DIR = DATA_DIR / "validation"

# Validation sites — new states not in training set
# Selected: have continuous turbidity + ≥20 discrete TP samples
VALIDATION_SITES = [
    # === Batch 1 (already downloaded) ===
    # Texas (3 sites — 2 have turbidity)
    "USGS-08068000",   # Spring Creek near Spring, TX — 211 TP, 213 SSC, TURB CONFIRMED
    "USGS-08070200",   # E Fork San Jacinto R nr New Caney, TX — 281 TP, 194 SSC, TURB CONFIRMED
    "USGS-08116650",   # Brazos R nr Rosharon, TX — 376 TP, 319 SSC (no turbidity)
    # Washington (3 sites — 2 have turbidity)
    "USGS-12113390",   # Duwamish R at Tukwila, WA — 116 TP, 289 SSC, TURB CONFIRMED
    "USGS-12101500",   # Puyallup R at Puyallup, WA — 211 TP, 280 SSC (no turbidity)
    "USGS-12090400",   # Nisqually R near McKenna, WA — 33 TP, 30 SSC, TURB CONFIRMED
    # North Carolina (2 sites — no turbidity)
    "USGS-02089500",   # Neuse R at Kinston, NC — 652 TP, 668 SSC (no turbidity)
    "USGS-02096960",   # Haw R near Bynum, NC — 147 TP, 191 SSC (no turbidity)
    # Pennsylvania (3 sites — 1 has turbidity)
    "USGS-01474500",   # Schuylkill R at Philadelphia, PA — 246 TP, 105 SSC, TURB CONFIRMED
    "USGS-03049625",   # Allegheny R at New Kensington, PA — 225 TP, 191 SSC (no turbidity)
    "USGS-03015500",   # Brokenstraw Cr at Youngsville, PA — 137 TP, 42 SSC (no turbidity)
    # Minnesota (3 sites — 2 have turbidity)
    "USGS-04024000",   # St. Louis R at Scanlon, MN — 418 TP, 385 SSC, TURB CONFIRMED
    "USGS-05082500",   # Red R of the North at Grand Forks, ND — 385 TP, 244 SSC, TURB CONFIRMED
    "USGS-05311000",   # Minnesota R at Montevideo, MN — 100 TP, 61 SSC (no turbidity)
    # === Batch 2 (turbidity pre-verified) ===
    # New York (2 sites)
    "USGS-01362370",   # Esopus Creek at Mount Marion, NY — 177 TP, 611 SSC, TURB CONFIRMED
    "USGS-04213500",   # Cattaraugus Creek at Gowanda, NY — 502 TP, 451 SSC, TURB CONFIRMED
    # Georgia (2 sites)
    "USGS-02336030",   # N Fork Peachtree Creek at Atlanta, GA — 227 TP, 220 SSC, TURB CONFIRMED
    "USGS-02207135",   # Yellow R at GA 124 nr Lithonia, GA — 83 TP, 90 SSC, TURB CONFIRMED
    # Iowa (1 site)
    "USGS-05447500",   # Iowa R at Iowa City, IA — 295 TP, 116 SSC, TURB CONFIRMED
    # Florida (1 site)
    "USGS-02292900",   # Caloosahatchee R at S-79 nr Olga, FL — 138 TP, 2 SSC, TURB CONFIRMED
]

# Continuous parameters to download
CONTINUOUS_PARAMS = {
    "63680": "turbidity",
    "00095": "conductance",
    "00300": "do",
    "00400": "ph",
    "00010": "temp",
    "00060": "discharge",
}

# Discrete parameters to download
DISCRETE_PARAMS = {
    "80154": "ssc",
    "00665": "total_phosphorus",
    "00631": "nitrate_nitrite",
    "70300": "tds_evaporative",
    "00671": "orthophosphate",
}


def get_site_date_range(site_id: str, param_code: str) -> tuple:
    """Get actual date range from time series metadata."""
    try:
        ts, _ = waterdata.get_time_series_metadata(
            monitoring_location_id=site_id,
            parameter_code=param_code,
        )
        if ts is not None and len(ts) > 0:
            begin = pd.to_datetime(ts["begin"].iloc[0])
            end = pd.to_datetime(ts["end"].iloc[0])
            if pd.notna(begin) and pd.notna(end):
                return begin.year, end.year + 1
    except Exception:
        pass
    return None, None


def download_continuous(site_id: str, param_code: str, param_name: str,
                         delay: float = 2.0, max_retries: int = 3):
    """Download continuous data in 3-year chunks."""
    site_stem = site_id.replace("-", "_")
    cache_dir = VAL_DIR / "continuous" / site_stem / param_code
    cache_dir.mkdir(parents=True, exist_ok=True)

    start_year, end_year = get_site_date_range(site_id, param_code)
    if not start_year:
        end_year = 2027
        start_year = end_year - 15

    total_records = 0
    for year in range(start_year, end_year + 1, 3):
        chunk_end = min(year + 3, end_year + 1)
        cache_file = cache_dir / f"{year}_{chunk_end}.parquet"

        if cache_file.exists():
            chunk = pd.read_parquet(cache_file)
            total_records += len(chunk)
            continue

        time_range = f"{year}-01-01/{chunk_end}-01-01"
        for attempt in range(max_retries):
            try:
                df, _ = waterdata.get_continuous(
                    monitoring_location_id=site_id,
                    parameter_code=param_code,
                    time=time_range,
                )
                if df is not None and len(df) > 0:
                    df.to_parquet(cache_file)
                    total_records += len(df)
                else:
                    pd.DataFrame().to_parquet(cache_file)
                break
            except Exception as e:
                if "429" in str(e):
                    time.sleep(2 ** attempt * 30)
                else:
                    break
        time.sleep(delay)

    if total_records > 0:
        logger.info(f"    {param_name}: {total_records} records")
    return total_records


def download_discrete(site_id: str, pcode: str, param_name: str,
                       max_retries: int = 3):
    """Download discrete samples for a parameter."""
    site_stem = site_id.replace("-", "_")
    cache_dir = VAL_DIR / "discrete"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{site_stem}_{param_name}.parquet"

    if cache_file.exists():
        df = pd.read_parquet(cache_file)
        if len(df) > 0:
            logger.info(f"    [cache] {param_name}: {len(df)} samples")
            return len(df)
        return 0

    for attempt in range(max_retries):
        try:
            df, _ = waterdata.get_samples(
                monitoringLocationIdentifier=site_id,
                usgsPCode=pcode,
            )
            if df is not None and len(df) > 0:
                df.to_parquet(cache_file)
                logger.info(f"    {param_name}: {len(df)} samples")
                return len(df)
            return 0
        except Exception as e:
            if "429" in str(e):
                time.sleep(2 ** attempt * 15)
            else:
                logger.warning(f"    {param_name} error: {e}")
                return 0
    return 0


def main():
    if os.getenv("API_USGS_PAT"):
        logger.info("USGS API token found")
    else:
        logger.warning("No API_USGS_PAT — will be rate-limited!")

    logger.info(f"Downloading data for {len(VALIDATION_SITES)} external validation sites")
    logger.info(f"States: TX, WA, NC, PA, MN (not in training set)")

    summary = []
    for i, site_id in enumerate(VALIDATION_SITES):
        logger.info(f"\n[{i+1}/{len(VALIDATION_SITES)}] {site_id}")

        site_data = {"site_id": site_id}

        # Download all continuous parameters
        for pcode, pname in CONTINUOUS_PARAMS.items():
            n = download_continuous(site_id, pcode, pname)
            site_data[f"cont_{pname}"] = n

        # Download all discrete parameters
        for pcode, pname in DISCRETE_PARAMS.items():
            n = download_discrete(site_id, pcode, pname)
            site_data[f"disc_{pname}"] = n
            time.sleep(1.5)

        summary.append(site_data)

    # Summary
    df = pd.DataFrame(summary)
    df.to_parquet(VAL_DIR / "validation_site_summary.parquet", index=False)

    logger.info(f"\n{'='*60}")
    logger.info("VALIDATION SITE DOWNLOAD SUMMARY")
    logger.info(f"{'='*60}")
    for _, row in df.iterrows():
        turb = row.get("cont_turbidity", 0)
        tp = row.get("disc_total_phosphorus", 0)
        ssc = row.get("disc_ssc", 0)
        logger.info(f"  {row['site_id']}: turb={turb}, TP={tp}, SSC={ssc}")


if __name__ == "__main__":
    main()
