"""Compute sensor calibration features from discrete vs continuous turbidity pairs.

For each site that has BOTH discrete turbidity field measurements (from WQP)
AND continuous turbidity records (parameter 63680), this script:

1. Loads discrete turbidity samples
2. Loads and QC-filters continuous turbidity
3. Pairs each discrete sample with the interpolated continuous reading (+-15 min)
4. Computes offset (discrete - continuous) and ratio (discrete / continuous)
5. Filters out low-value pairs (continuous < 5 FNU) to avoid noise
6. Maps USGS method codes to sensor families

Outputs:
    data/processed/sensor_calibration.parquet        — per-visit pairs
    data/processed/sensor_calibration_summary.parquet — per-site summaries
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure murkml src is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from murkml.data.align import _interpolate_at_times, PRIMARY_WINDOW
from murkml.data.qc import filter_continuous
from murkml.provenance import start_run, log_step, log_file, end_run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"

# ── Timezone mapping (same as assemble_dataset.py) ──────────────────────
USGS_TZ_OFFSETS = {
    "EST": -5, "EDT": -4,
    "CST": -6, "CDT": -5,
    "MST": -7, "MDT": -6,
    "PST": -8, "PDT": -7,
    "AKST": -9, "AKDT": -8,
    "HST": -10, "AST": -4,
    "UTC": 0, "GMT": 0,
}

# ── Sensor family mapping ───────────────────────────────────────────────
# USGS method_code -> sensor family (from NWIS method code documentation)
SENSOR_FAMILY_MAP = {
    "TS213": "exo",           # YSI EXO series
    "TS087": "ysi_6series",   # YSI 6-series sonde
    "TS086": "ysi_6026",      # YSI 6026 sensor
}

# Continuous data columns (same as assemble_dataset.py)
_CONTINUOUS_COLS = ["time", "value", "approval_status", "qualifier"]

# Minimum continuous turbidity for a valid calibration pair (FNU)
MIN_CONTINUOUS_TURB = 5.0


def load_continuous(site_id: str, param_code: str = "63680") -> pd.DataFrame:
    """Load all cached continuous data for a site+param, concat chunks.

    Duplicated from assemble_dataset.py to keep this script self-contained.
    """
    cont_dir = DATA_DIR / "continuous" / site_id.replace("-", "_") / param_code
    if not cont_dir.exists():
        return pd.DataFrame()

    chunks = []
    for f in sorted(cont_dir.glob("*.parquet")):
        try:
            chunk = pd.read_parquet(f, columns=_CONTINUOUS_COLS)
        except Exception:
            chunk = pd.read_parquet(f)
        if len(chunk) > 0:
            chunks.append(chunk)

    if not chunks:
        return pd.DataFrame()

    df = pd.concat(chunks, ignore_index=True)
    df = df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    return df


def load_discrete_turbidity(site_id: str) -> pd.DataFrame:
    """Load discrete turbidity samples for a site.

    Expected file: data/discrete/{site}_turbidity.parquet
    Expected columns include WQP standard names (ActivityStartDate, etc.)
    plus ResultMeasureValue for the turbidity reading and optionally
    USGSPCode or MethodSpecificationName for method code.

    Returns DataFrame with columns:
        datetime (UTC), turb_value, method_code
    """
    fname = site_id.replace("-", "_") + "_turbidity.parquet"
    fpath = DATA_DIR / "discrete" / fname
    if not fpath.exists():
        return pd.DataFrame()

    df = pd.read_parquet(fpath)
    n_original = len(df)
    if n_original == 0:
        return pd.DataFrame()

    # ── Handle pre-parsed format (from download_discrete_turbidity.py) ──
    # Pre-parsed files have: datetime, turbidity_value, unit, method_code, method_name, equipment, activity_type
    if "datetime" in df.columns and "turbidity_value" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        df["turb_value"] = pd.to_numeric(df["turbidity_value"], errors="coerce")
        # method_code and other columns already present
    else:
        # ── Normalize raw WQP column names ─────────────────────────────
        col_renames = {
            "ActivityStartDate": "Activity_StartDate",
            "ActivityStartTime/Time": "Activity_StartTime",
            "ActivityStartTime/TimeZoneCode": "Activity_StartTimeZone",
            "ResultMeasureValue": "Result_Measure",
        }
        df = df.rename(columns={k: v for k, v in col_renames.items() if k in df.columns})

        if "Activity_StartDate" not in df.columns:
            logger.warning(f"  {site_id}: No date column — skipping")
            return pd.DataFrame()

        if "Activity_StartTime" not in df.columns:
            logger.warning(f"  {site_id}: No time column — skipping")
            return pd.DataFrame()

        time_null = df["Activity_StartTime"].isna() | (df["Activity_StartTime"] == "")
        df = df[~time_null].copy()

        if "Activity_StartTimeZone" not in df.columns:
            logger.warning(f"  {site_id}: No timezone column — skipping")
            return pd.DataFrame()

        tz_col = df["Activity_StartTimeZone"].fillna("")
        valid_tz = tz_col.isin(USGS_TZ_OFFSETS.keys())
        df = df[valid_tz].copy()

        if df.empty:
            return pd.DataFrame()

        local_dt = pd.to_datetime(
            df["Activity_StartDate"].astype(str) + " " + df["Activity_StartTime"].astype(str),
            errors="coerce",
        )
        offsets = df["Activity_StartTimeZone"].map(USGS_TZ_OFFSETS)
        utc_dt = local_dt - pd.to_timedelta(offsets, unit="h")
        df["datetime"] = utc_dt.dt.tz_localize("UTC")

        if "Result_Measure" in df.columns:
            df["turb_value"] = pd.to_numeric(df["Result_Measure"], errors="coerce")
        else:
            logger.warning(f"  {site_id}: No Result_Measure column — skipping")
            return pd.DataFrame()

    # ── Extract method code ─────────────────────────────────────────────
    # Try multiple possible column names for the USGS method code
    method_col = None
    for candidate in [
        "method_code",
        "USGSPCode",
        "ResultAnalyticalMethod/MethodIdentifier",
        "ResultAnalyticalMethodIdentifier",
        "MethodSpecificationName",
    ]:
        if candidate in df.columns:
            method_col = candidate
            break

    if method_col is not None:
        df["method_code"] = df[method_col].astype(str).str.strip()
    else:
        df["method_code"] = "unknown"

    # ── Filter & deduplicate ────────────────────────────────────────────
    valid = df.dropna(subset=["datetime", "turb_value"]).copy()
    valid = valid[valid["turb_value"] >= 0]
    valid = valid.drop_duplicates(subset=["datetime", "turb_value"], keep="first")
    valid = valid.sort_values("datetime").reset_index(drop=True)

    n_final = len(valid)
    logger.info(f"  {site_id}: {n_original} raw → {n_final} valid discrete turbidity samples")

    return valid[["datetime", "turb_value", "method_code"]]


def map_sensor_family(method_code: str) -> str:
    """Map a USGS method code to a sensor family name."""
    code = str(method_code).strip().upper()
    return SENSOR_FAMILY_MAP.get(code, "unknown")


def process_site(site_id: str) -> pd.DataFrame | None:
    """Process one site: pair discrete turbidity with continuous, compute offsets.

    Returns a DataFrame of calibration pairs, or None if insufficient data.
    """
    logger.info(f"Processing {site_id}")

    # Load discrete turbidity
    discrete = load_discrete_turbidity(site_id)
    if discrete.empty:
        logger.info(f"  {site_id}: No discrete turbidity — skipping")
        return None

    # Load continuous turbidity
    continuous = load_continuous(site_id, "63680")
    if continuous.empty:
        logger.info(f"  {site_id}: No continuous turbidity — skipping")
        return None

    # QC filter continuous data
    cont_filtered, qc_stats = filter_continuous(continuous)
    logger.info(
        f"  Continuous QC: {qc_stats.get('pct_retained', '?')}% retained "
        f"({qc_stats.get('n_after_filter', 0)} records)"
    )

    if cont_filtered.empty:
        logger.info(f"  {site_id}: No continuous data after QC — skipping")
        return None

    # Prepare arrays for _interpolate_at_times
    cont_clean = cont_filtered[["time", "value"]].copy()
    cont_clean["time"] = pd.to_datetime(cont_clean["time"], utc=True)
    cont_clean = cont_clean.sort_values("time").reset_index(drop=True)

    cont_t = cont_clean["time"].values
    cont_v = cont_clean["value"].astype(float).values

    discrete["datetime"] = pd.to_datetime(discrete["datetime"], utc=True)
    discrete = discrete.sort_values("datetime").reset_index(drop=True)
    sample_t = discrete["datetime"].values

    max_gap_ns = PRIMARY_WINDOW.value  # +-15 minutes in nanoseconds

    # Interpolate continuous values at discrete sample times
    interp_values, interp_gaps, matched_mask = _interpolate_at_times(
        cont_t, cont_v, sample_t, max_gap_ns
    )

    n_matched = matched_mask.sum()
    logger.info(
        f"  Matched {n_matched}/{len(discrete)} discrete samples "
        f"within ±15 min of continuous reading"
    )

    if n_matched == 0:
        return None

    # Build pairs DataFrame
    pairs = pd.DataFrame({
        "site_id": site_id,
        "visit_time": discrete.loc[matched_mask, "datetime"].values,
        "discrete_turb": discrete.loc[matched_mask, "turb_value"].values,
        "continuous_turb": interp_values[matched_mask],
        "match_gap_seconds": interp_gaps[matched_mask],
        "method_code": discrete.loc[matched_mask, "method_code"].values,
    })

    # Filter: continuous_turb > 5 FNU (avoid low-value noise)
    n_before_filter = len(pairs)
    pairs = pairs[pairs["continuous_turb"] > MIN_CONTINUOUS_TURB].copy()
    n_low_filtered = n_before_filter - len(pairs)
    if n_low_filtered > 0:
        logger.info(
            f"  Filtered {n_low_filtered} pairs with continuous_turb <= {MIN_CONTINUOUS_TURB} FNU"
        )

    if pairs.empty:
        logger.info(f"  {site_id}: No pairs remaining after low-value filter")
        return None

    # Compute calibration metrics
    pairs["offset"] = pairs["discrete_turb"] - pairs["continuous_turb"]
    pairs["ratio"] = pairs["discrete_turb"] / pairs["continuous_turb"]

    # Map method code to sensor family
    pairs["sensor_family"] = pairs["method_code"].apply(map_sensor_family)

    logger.info(
        f"  {site_id}: {len(pairs)} calibration pairs, "
        f"median offset={pairs['offset'].median():.1f} FNU, "
        f"sensor families: {pairs['sensor_family'].value_counts().to_dict()}"
    )

    return pairs


def compute_site_summary(calibration: pd.DataFrame) -> pd.DataFrame:
    """Compute per-site summary statistics from calibration pairs.

    Returns DataFrame with columns:
        site_id, n_visits, median_offset, std_offset, sensor_family,
        first_visit, last_visit
    """
    summaries = []
    for site_id, group in calibration.groupby("site_id"):
        summaries.append({
            "site_id": site_id,
            "n_visits": len(group),
            "median_offset": group["offset"].median(),
            "std_offset": group["offset"].std(),
            "sensor_family": group["sensor_family"].mode().iloc[0] if len(group) > 0 else "unknown",
            "first_visit": group["visit_time"].min(),
            "last_visit": group["visit_time"].max(),
        })

    return pd.DataFrame(summaries)


def discover_sites() -> list[str]:
    """Find all sites that have BOTH discrete turbidity and continuous turbidity data."""
    disc_dir = DATA_DIR / "discrete"
    cont_dir = DATA_DIR / "continuous"

    if not disc_dir.exists() or not cont_dir.exists():
        logger.error("Missing data/discrete/ or data/continuous/ directory")
        return []

    # Sites with discrete turbidity files
    discrete_sites = set()
    for f in disc_dir.glob("*_turbidity.parquet"):
        site_id = f.stem.replace("_turbidity", "").replace("_", "-")
        discrete_sites.add(site_id)

    # Sites with continuous turbidity (parameter 63680)
    continuous_sites = set()
    for d in cont_dir.iterdir():
        if d.is_dir():
            turb_dir = d / "63680"
            if turb_dir.exists() and any(turb_dir.glob("*.parquet")):
                site_id = d.name.replace("_", "-")
                continuous_sites.add(site_id)

    both = sorted(discrete_sites & continuous_sites)
    logger.info(
        f"Site discovery: {len(discrete_sites)} with discrete turb, "
        f"{len(continuous_sites)} with continuous turb, "
        f"{len(both)} with both"
    )

    return both


def main():
    import warnings
    warnings.filterwarnings("ignore")

    start_run("sensor_calibration")

    # Discover eligible sites
    sites = discover_sites()
    if not sites:
        logger.error("No sites found with both discrete and continuous turbidity data")
        logger.info(
            "Discrete turbidity files expected at: data/discrete/{site}_turbidity.parquet\n"
            "Continuous turbidity expected at: data/continuous/{site}/63680/*.parquet"
        )
        end_run()
        sys.exit(1)

    # Process each site
    all_pairs = []
    n_success = 0
    n_failed = 0

    for i, site_id in enumerate(sites):
        logger.info(f"[{i+1}/{len(sites)}] {site_id}")
        try:
            result = process_site(site_id)
            if result is not None and not result.empty:
                all_pairs.append(result)
                n_success += 1
                log_step("calibrate_site", site_id=site_id, n_pairs=len(result))
            else:
                n_failed += 1
        except Exception as e:
            logger.error(f"  FAILED {site_id}: {e}")
            import traceback
            traceback.print_exc()
            n_failed += 1

    logger.info(f"\nProcessed {len(sites)} sites: {n_success} produced data, {n_failed} skipped/failed")

    if not all_pairs:
        logger.error("No calibration pairs produced from any site!")
        end_run()
        sys.exit(1)

    # Combine all sites
    calibration = pd.concat(all_pairs, ignore_index=True)

    # Ensure visit_time is UTC
    calibration["visit_time"] = pd.to_datetime(calibration["visit_time"], utc=True)

    # Sort by site and time
    calibration = calibration.sort_values(["site_id", "visit_time"]).reset_index(drop=True)

    # ── Save per-visit calibration pairs ────────────────────────────────
    output_dir = DATA_DIR / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)

    pairs_path = output_dir / "sensor_calibration.parquet"
    calibration.to_parquet(pairs_path, index=False)
    log_file(pairs_path, role="output")
    logger.info(f"Saved {len(calibration)} calibration pairs → {pairs_path}")

    # ── Compute and save per-site summary ───────────────────────────────
    summary = compute_site_summary(calibration)
    summary_path = output_dir / "sensor_calibration_summary.parquet"
    summary.to_parquet(summary_path, index=False)
    log_file(summary_path, role="output")
    logger.info(f"Saved {len(summary)} site summaries → {summary_path}")

    # ── Print summary ───────────────────────────────────────────────────
    logger.info(f"\n{'='*60}")
    logger.info(f"Sensor Calibration Summary")
    logger.info(f"{'='*60}")
    logger.info(f"Total calibration pairs: {len(calibration)}")
    logger.info(f"Sites with calibration data: {calibration['site_id'].nunique()}")
    logger.info(f"Median offset (all): {calibration['offset'].median():.2f} FNU")
    logger.info(f"Std offset (all): {calibration['offset'].std():.2f} FNU")
    logger.info(f"Median ratio (all): {calibration['ratio'].median():.3f}")
    logger.info(f"Sensor families: {calibration['sensor_family'].value_counts().to_dict()}")
    logger.info(f"Date range: {calibration['visit_time'].min()} to {calibration['visit_time'].max()}")

    logger.info(f"\nPer-site summary (top 20 by visit count):")
    top_sites = summary.nlargest(20, "n_visits")
    for _, row in top_sites.iterrows():
        logger.info(
            f"  {row['site_id']}: {row['n_visits']} visits, "
            f"median_offset={row['median_offset']:.1f}, "
            f"std_offset={row['std_offset']:.1f}, "
            f"sensor={row['sensor_family']}"
        )

    log_step(
        "calibration_complete",
        n_sites=int(calibration["site_id"].nunique()),
        n_pairs=len(calibration),
        median_offset=float(calibration["offset"].median()),
    )
    end_run()


if __name__ == "__main__":
    main()
