"""Fetch USGS water data via the dataretrieval package.

Uses the NEW waterdata module (not deprecated nwis module).
All data is cached as Parquet files for resume-safe incremental downloads.

Key functions:
    discover_sites() — find sites with paired continuous + discrete data
    fetch_continuous() — pull 15-min sensor data with retry/validation
    fetch_discrete() — pull grab sample lab results
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# USGS parameter codes
PARAMS = {
    "turbidity_fnu": "63680",
    "conductance": "00095",
    "do": "00300",
    "ph": "00400",
    "temp": "00010",
    "discharge": "00060",
    "ssc": "80154",
    "tss": "00530",  # Do NOT mix with SSC
}

# Default continuous parameters to fetch for every site
DEFAULT_CONTINUOUS_PARAMS = ["63680", "00095", "00300", "00400", "00010", "00060"]

# 3-year max per API call for continuous data
MAX_YEARS_PER_CALL = 3


def discover_sites(
    parameter_code: str = "63680",
    states: list[str] | None = None,
    min_years: int = 2,
) -> pd.DataFrame:
    """Find USGS sites that have time-series data for a given parameter.

    Uses waterdata.get_time_series_metadata() — NOT get_monitoring_locations()
    which has no parameter filter.

    Args:
        parameter_code: USGS parameter code (default: 63680 = turbidity FNU).
        states: List of state NAMES to search. If None, searches all states.
            Must be full names like "Kansas", not codes like "KS".
        min_years: Minimum years of record to include.

    Returns:
        DataFrame with time series metadata including monitoring_location_id.
    """
    from dataretrieval import waterdata

    # API requires full state names, not codes
    all_states = states or [
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

    results = []
    for state in all_states:
        try:
            df, _ = waterdata.get_time_series_metadata(
                parameter_code=parameter_code,
                state_name=state,
            )
            if df is not None and len(df) > 0:
                results.append(df)
                logger.info(f"Found {len(df)} time series in {state}")
        except Exception as e:
            logger.warning(f"Failed to query {state}: {e}")
            continue

    if not results:
        logger.warning("No sites found!")
        return pd.DataFrame()

    combined = pd.concat(results, ignore_index=True)
    logger.info(f"Total: {len(combined)} time series across {len(all_states)} states")
    return combined


def find_paired_sites(
    continuous_param: str = "63680",
    discrete_param: str = "80154",
    states: list[str] | None = None,
    min_discrete_samples: int = 30,
) -> pd.DataFrame:
    """Find sites that have BOTH continuous sensor data AND discrete lab samples.

    This is the core site discovery function. It:
    1. Finds sites with continuous turbidity via get_time_series_metadata()
    2. For each, checks if discrete SSC samples exist via get_samples()
    3. Filters to sites with >= min_discrete_samples

    Args:
        continuous_param: Parameter code for continuous sensor (default: turbidity FNU).
        discrete_param: Parameter code for discrete lab samples (default: SSC).
        states: States to search. None = all states.
        min_discrete_samples: Minimum discrete samples required.

    Returns:
        DataFrame with site metadata and sample counts.
    """
    from dataretrieval import waterdata

    # Step 1: Find sites with continuous data
    continuous_sites = discover_sites(
        parameter_code=continuous_param,
        states=states,
    )

    if continuous_sites.empty:
        return pd.DataFrame()

    # Extract unique site IDs
    if "monitoring_location_id" in continuous_sites.columns:
        site_ids = continuous_sites["monitoring_location_id"].unique()
    else:
        logger.warning("Unexpected column names in time series metadata")
        return pd.DataFrame()

    logger.info(f"Checking {len(site_ids)} sites for discrete {discrete_param} samples...")

    # Step 2: Check each site for discrete samples (no pagination — one site at a time)
    paired = []
    for i, site_id in enumerate(site_ids):
        if i % 50 == 0 and i > 0:
            logger.info(f"  Checked {i}/{len(site_ids)} sites...")

        try:
            samples, _ = waterdata.get_samples(
                monitoringLocationIdentifier=site_id,
                usgsPCode=discrete_param,
            )
            if samples is not None and len(samples) >= min_discrete_samples:
                paired.append({
                    "site_id": site_id,
                    "n_discrete_samples": len(samples),
                })
        except Exception:
            continue

    if not paired:
        logger.warning("No paired sites found!")
        return pd.DataFrame()

    paired_df = pd.DataFrame(paired)

    # Merge with continuous site metadata
    result = paired_df.merge(
        continuous_sites.drop_duplicates(subset=["monitoring_location_id"]),
        left_on="site_id",
        right_on="monitoring_location_id",
        how="left",
    )

    logger.info(
        f"Found {len(result)} sites with continuous {continuous_param} "
        f"AND >= {min_discrete_samples} discrete {discrete_param} samples"
    )
    return result


def fetch_continuous(
    site_id: str,
    parameter_code: str,
    start_date: str,
    end_date: str,
    cache_dir: Path | str = "data/continuous",
    max_retries: int = 3,
) -> pd.DataFrame:
    """Fetch continuous (instantaneous value) data for a site+parameter.

    Handles the 3-year-max API limit by chunking, caches results as Parquet,
    and validates record counts to catch silent pagination failures.

    Args:
        site_id: USGS site ID with prefix (e.g., "USGS-07144100").
        parameter_code: USGS parameter code.
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        cache_dir: Directory for cached Parquet files.
        max_retries: Max retries per chunk on failure.

    Returns:
        DataFrame with datetime index (UTC) and value column.
    """
    from dataretrieval import waterdata

    cache_dir = Path(cache_dir)
    site_dir = cache_dir / site_id.replace(":", "_") / parameter_code
    site_dir.mkdir(parents=True, exist_ok=True)

    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)

    chunks = []
    current = start
    while current < end:
        chunk_end = min(current + pd.DateOffset(years=MAX_YEARS_PER_CALL), end)
        year_label = f"{current.year}_{chunk_end.year}"
        cache_file = site_dir / f"{year_label}.parquet"

        if cache_file.exists():
            logger.debug(f"Cache hit: {cache_file}")
            chunk_df = pd.read_parquet(cache_file)
        else:
            # API uses ISO 8601 interval format for time parameter
            time_range = (
                f"{current.strftime('%Y-%m-%d')}/{chunk_end.strftime('%Y-%m-%d')}"
            )
            chunk_df = _fetch_with_retry(
                waterdata.get_continuous,
                monitoring_location_id=site_id,
                parameter_code=parameter_code,
                time=time_range,
                max_retries=max_retries,
            )
            if chunk_df is not None and len(chunk_df) > 0:
                chunk_df.to_parquet(cache_file)
                logger.info(
                    f"Fetched {len(chunk_df)} records for {site_id}/{parameter_code} "
                    f"({current.date()} to {chunk_end.date()})"
                )
            else:
                logger.warning(
                    f"No data for {site_id}/{parameter_code} "
                    f"({current.date()} to {chunk_end.date()})"
                )

        if chunk_df is not None and len(chunk_df) > 0:
            chunks.append(chunk_df)

        current = chunk_end

    if not chunks:
        return pd.DataFrame()

    result = pd.concat(chunks, ignore_index=True)
    return result


def fetch_discrete(
    site_id: str,
    parameter_code: str = "80154",
    cache_dir: Path | str = "data/discrete",
) -> pd.DataFrame:
    """Fetch discrete (grab sample) lab results for a site.

    No pagination in this endpoint — queries one site at a time.
    SSC (80154) only for MVP. Do NOT mix with TSS (00530).

    Args:
        site_id: USGS site ID with prefix (e.g., "USGS-07144100").
        parameter_code: USGS parameter code (default: SSC).
        cache_dir: Cache directory.

    Returns:
        DataFrame with sample timestamps, values, and metadata.
    """
    from dataretrieval import waterdata

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{site_id.replace(':', '_')}_{parameter_code}.parquet"

    if cache_file.exists():
        logger.debug(f"Cache hit: {cache_file}")
        return pd.read_parquet(cache_file)

    try:
        df, _ = waterdata.get_samples(
            monitoringLocationIdentifier=site_id,
            usgsPCode=parameter_code,
        )
    except Exception as e:
        logger.error(f"Failed to fetch discrete data for {site_id}: {e}")
        return pd.DataFrame()

    if df is not None and len(df) > 0:
        df.to_parquet(cache_file)
        logger.info(f"Fetched {len(df)} discrete samples for {site_id}/{parameter_code}")

    return df if df is not None else pd.DataFrame()


def _fetch_with_retry(func, max_retries: int = 3, **kwargs) -> pd.DataFrame | None:
    """Call a dataretrieval function with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            df, _ = func(**kwargs)
            return df
        except Exception as e:
            wait = 2 ** attempt * 5
            logger.warning(
                f"Attempt {attempt + 1}/{max_retries} failed: {e}. "
                f"Retrying in {wait}s..."
            )
            time.sleep(wait)
    logger.error(f"All {max_retries} attempts failed for {kwargs}")
    return None
