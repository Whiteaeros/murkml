"""Check temporal overlap between discrete lab samples and continuous sensor data.

For each site+parameter, determines how many discrete samples fall within
the continuous turbidity sensor record period. This gives the REAL usable
sample count (vs. total samples which may predate sensor installation).

Usage:
    python scripts/check_temporal_overlap.py
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from murkml.provenance import start_run, log_step, log_file, end_run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"

# USGS timezone offset map (same as assemble_dataset.py)
USGS_TZ_OFFSETS = {
    "EST": -5, "EDT": -4, "CST": -6, "CDT": -5,
    "MST": -7, "MDT": -6, "PST": -8, "PDT": -7,
    "AKST": -9, "AKDT": -8, "HST": -10, "AST": -4,
    "UTC": 0, "GMT": 0,
}

PARAMS = {
    "total_phosphorus": "00665",
    "nitrate_nitrite": "00631",
    "tds_evaporative": "70300",
    "orthophosphate": "00671",
    "ssc": "80154",
}


def get_continuous_date_range(site_id: str) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """Get the min/max timestamp range of continuous turbidity data for a site."""
    site_dir = site_id.replace("-", "_")
    turb_dir = DATA_DIR / "continuous" / site_dir / "63680"
    if not turb_dir.exists():
        return None, None

    min_t, max_t = None, None
    for f in turb_dir.glob("*.parquet"):
        try:
            df = pd.read_parquet(f)
            if len(df) == 0:
                continue
            if "time" in df.columns:
                ts = pd.to_datetime(df["time"], utc=True)
            elif "datetime" in df.columns:
                ts = pd.to_datetime(df["datetime"], utc=True)
            else:
                continue
            chunk_min = ts.min()
            chunk_max = ts.max()
            if min_t is None or chunk_min < min_t:
                min_t = chunk_min
            if max_t is None or chunk_max > max_t:
                max_t = chunk_max
        except Exception:
            continue

    return min_t, max_t


def parse_discrete_timestamps(df: pd.DataFrame) -> pd.Series:
    """Parse discrete sample timestamps to UTC, same logic as assemble_dataset.py."""
    df = df.copy()
    # Combine date + time
    date_col = "Activity_StartDate"
    time_col = "Activity_StartTime"
    tz_col = "Activity_StartTimeZone"

    if date_col not in df.columns:
        return pd.Series(dtype="datetime64[ns, UTC]")

    # Drop rows missing date or time
    mask = df[date_col].notna()
    if time_col in df.columns:
        mask &= df[time_col].notna()
    df = df[mask]

    if len(df) == 0:
        return pd.Series(dtype="datetime64[ns, UTC]")

    # Parse local datetime
    if time_col in df.columns:
        dt_str = df[date_col].astype(str) + " " + df[time_col].astype(str)
    else:
        dt_str = df[date_col].astype(str)

    local_dt = pd.to_datetime(dt_str, errors="coerce")
    valid = local_dt.notna()
    local_dt = local_dt[valid]
    df = df[valid]

    if len(df) == 0:
        return pd.Series(dtype="datetime64[ns, UTC]")

    # Convert to UTC using timezone offsets
    if tz_col in df.columns:
        offsets = df[tz_col].map(USGS_TZ_OFFSETS)
        has_offset = offsets.notna()
        local_dt = local_dt[has_offset]
        offsets = offsets[has_offset]
        utc_dt = local_dt - pd.to_timedelta(offsets, unit="h")
        return utc_dt.dt.tz_localize("UTC")
    else:
        # Assume UTC if no timezone info
        return local_dt.dt.tz_localize("UTC")


def main():
    start_run("check_temporal_overlap")

    # Get all assembled sites
    assembled = pd.read_parquet(DATA_DIR / "processed" / "turbidity_ssc_paired.parquet")
    log_file(DATA_DIR / "processed" / "turbidity_ssc_paired.parquet", role="input")
    sites = sorted(assembled["site_id"].unique())
    logger.info(f"Checking temporal overlap for {len(sites)} sites, {len(PARAMS)} parameters")

    results = []

    for i, site_id in enumerate(sites):
        # Get continuous turbidity date range (once per site)
        cont_start, cont_end = get_continuous_date_range(site_id)
        if cont_start is None:
            logger.warning(f"  {site_id}: no continuous turbidity data")
            for param_name in PARAMS:
                results.append({
                    "site_id": site_id,
                    "param_name": param_name,
                    "n_total_discrete": 0,
                    "n_pairable": 0,
                    "continuous_start": None,
                    "continuous_end": None,
                })
            continue

        for param_name, pcode in PARAMS.items():
            # Load discrete file
            site_stem = site_id.replace("-", "_")
            disc_file = DATA_DIR / "discrete" / f"{site_stem}_{param_name}.parquet"
            if not disc_file.exists():
                results.append({
                    "site_id": site_id,
                    "param_name": param_name,
                    "n_total_discrete": 0,
                    "n_pairable": 0,
                    "continuous_start": str(cont_start),
                    "continuous_end": str(cont_end),
                })
                continue

            disc_df = pd.read_parquet(disc_file)
            n_total = len(disc_df)

            # Parse timestamps
            disc_times = parse_discrete_timestamps(disc_df)
            n_with_time = len(disc_times)

            # Count samples within continuous period
            if len(disc_times) > 0:
                in_range = (disc_times >= cont_start) & (disc_times <= cont_end)
                n_pairable = in_range.sum()
            else:
                n_pairable = 0

            results.append({
                "site_id": site_id,
                "param_name": param_name,
                "n_total_discrete": n_total,
                "n_parseable_time": n_with_time,
                "n_pairable": int(n_pairable),
                "continuous_start": str(cont_start),
                "continuous_end": str(cont_end),
            })

        if (i + 1) % 10 == 0:
            logger.info(f"  Processed {i+1}/{len(sites)} sites")

    df = pd.DataFrame(results)
    out_path = DATA_DIR / "temporal_overlap_audit.parquet"
    df.to_parquet(out_path, index=False)
    log_file(out_path, role="output")
    log_step("overlap_audit_complete", n_sites=len(sites), n_params=len(PARAMS),
             n_results=len(results))
    logger.info(f"\nSaved: {out_path}")

    # Summary per parameter
    logger.info("\n" + "=" * 70)
    logger.info("TEMPORAL OVERLAP SUMMARY")
    logger.info("=" * 70)

    for param_name in PARAMS:
        subset = df[df["param_name"] == param_name]
        has_data = subset[subset["n_total_discrete"] > 0]
        has_pairable = subset[subset["n_pairable"] > 0]

        total_discrete = has_data["n_total_discrete"].sum()
        total_pairable = has_pairable["n_pairable"].sum()
        pct = (total_pairable / total_discrete * 100) if total_discrete > 0 else 0

        # Sites with enough pairable samples for modeling (≥20)
        sites_ge20 = (subset["n_pairable"] >= 20).sum()
        sites_ge10 = (subset["n_pairable"] >= 10).sum()

        logger.info(f"\n{param_name}:")
        logger.info(f"  Sites with any data: {len(has_data)}")
        logger.info(f"  Sites with pairable samples: {len(has_pairable)}")
        logger.info(f"  Sites with ≥10 pairable: {sites_ge10}")
        logger.info(f"  Sites with ≥20 pairable: {sites_ge20}")
        logger.info(f"  Total discrete: {total_discrete}, Pairable: {total_pairable} ({pct:.0f}%)")

    # Decision gate check
    logger.info("\n" + "=" * 70)
    logger.info("DECISION GATE: ≥30 sites with ≥3 params AND ≥20 pairable samples each?")
    logger.info("=" * 70)

    # For each site, count how many NEW params have ≥20 pairable
    new_params = [p for p in PARAMS if p != "ssc"]
    site_param_counts = {}
    for site_id in sites:
        count = 0
        for param_name in new_params:
            row = df[(df["site_id"] == site_id) & (df["param_name"] == param_name)]
            if len(row) > 0 and row.iloc[0]["n_pairable"] >= 20:
                count += 1
        site_param_counts[site_id] = count

    for threshold in [1, 2, 3, 4]:
        n_sites = sum(1 for v in site_param_counts.values() if v >= threshold)
        logger.info(f"  Sites with ≥{threshold} new params (≥20 pairable): {n_sites}")

    end_run()


if __name__ == "__main__":
    main()
