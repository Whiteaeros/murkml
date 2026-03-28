"""Assemble ML-ready dataset from downloaded continuous + discrete data.

For each site:
1. Load discrete SSC samples
2. Load all continuous sensor data
3. Apply QC filtering
4. Align each grab sample with continuous sensor window
5. Compute features (hydrograph position, antecedent, cross-sensor, seasonality)
6. Combine all sites into one dataset

Output: data/processed/turbidity_ssc_paired.parquet
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from murkml.data.align import align_samples, FEATURE_WINDOW
from murkml.data.features import engineer_features
from murkml.data.qc import filter_continuous
from murkml.provenance import start_run, log_step, log_file, end_run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"

CONTINUOUS_PARAMS = {
    "63680": "turbidity",
    "00095": "conductance",
    "00300": "do",
    "00400": "ph",
    "00010": "temp",
    "00060": "discharge",
}


    # --- USGS timezone abbreviation → UTC offset (hours) ---
USGS_TZ_OFFSETS = {
    "EST": -5, "EDT": -4,
    "CST": -6, "CDT": -5,
    "MST": -7, "MDT": -6,
    "PST": -8, "PDT": -7,
    "AKST": -9, "AKDT": -8,
    "HST": -10, "AST": -4,
    "UTC": 0, "GMT": 0,
}


def load_discrete(site_id: str) -> pd.DataFrame:
    """Load discrete SSC samples for a site, parse datetime and value.

    Fix 1: Convert local timestamps to UTC using Activity_StartTimeZone.
    Fix 6: Drop rows with missing time or timezone (no noon default).
    Fix 11: Handle non-detects with DL/2 substitution; keep SSC=0.
    Fix 18: Deduplicate samples.
    """
    cache_file = DATA_DIR / "discrete" / f"{site_id.replace('-', '_')}_ssc.parquet"
    if not cache_file.exists():
        return pd.DataFrame()

    df = pd.read_parquet(cache_file)
    n_original = len(df)

    # Handle WQP batch format column names (different from per-site format)
    col_renames = {
        "ActivityStartDate": "Activity_StartDate",
        "ActivityStartTime/Time": "Activity_StartTime",
        "ActivityStartTime/TimeZoneCode": "Activity_StartTimeZone",
        "ResultMeasureValue": "Result_Measure",
        "ResultDetectionConditionText": "Result_ResultDetectionCondition",
        "DetectionQuantitationLimitMeasure/MeasureValue": "DetectionQuantitationLimitMeasure_MeasureValue",
    }
    df = df.rename(columns={k: v for k, v in col_renames.items() if k in df.columns})

    # --- FIX 1+6: Timezone-aware datetime parsing ---
    if "Activity_StartDate" not in df.columns:
        return pd.DataFrame()

    # Drop rows with missing time (Fix 6: do NOT default to noon)
    if "Activity_StartTime" not in df.columns:
        logger.warning(f"  {site_id}: No Activity_StartTime column — skipping site")
        return pd.DataFrame()

    time_null_mask = df["Activity_StartTime"].isna() | (df["Activity_StartTime"] == "")
    n_null_time = time_null_mask.sum()
    if n_null_time > 0:
        logger.info(f"  Dropped {n_null_time} samples with null time")
    df = df[~time_null_mask].copy()

    # Drop rows with missing or unrecognized timezone (Fix 1)
    if "Activity_StartTimeZone" not in df.columns:
        logger.warning(f"  {site_id}: No timezone column — skipping site")
        return pd.DataFrame()

    tz_col = df["Activity_StartTimeZone"].fillna("")
    unrecognized = ~tz_col.isin(USGS_TZ_OFFSETS.keys())
    n_bad_tz = unrecognized.sum()
    if n_bad_tz > 0:
        bad_vals = tz_col[unrecognized].value_counts().to_dict()
        logger.warning(f"  Dropped {n_bad_tz} samples with unrecognized timezone: {bad_vals}")
    df = df[~unrecognized].copy()

    if df.empty:
        return pd.DataFrame()

    # Parse local datetime then convert to UTC using timezone offset
    local_dt = pd.to_datetime(
        df["Activity_StartDate"].astype(str) + " " + df["Activity_StartTime"].astype(str),
        errors="coerce",
    )
    offsets = df["Activity_StartTimeZone"].map(USGS_TZ_OFFSETS)
    # Subtract offset to convert to UTC: CST=-6, so local - (-6hr) = local + 6hr = UTC
    utc_dt = local_dt - pd.to_timedelta(offsets, unit="h")
    df["datetime"] = utc_dt.dt.tz_localize("UTC")

    # --- Parse SSC value ---
    if "Result_Measure" in df.columns:
        df["ssc_value"] = pd.to_numeric(df["Result_Measure"], errors="coerce")
    else:
        return pd.DataFrame()

    # --- FIX 11: Non-detect handling (DL/2 substitution) ---
    df["is_nondetect"] = False
    if "Result_ResultDetectionCondition" in df.columns:
        non_detect_mask = df["Result_ResultDetectionCondition"] == "Not Detected"
        n_nondetect = non_detect_mask.sum()
        if n_nondetect > 0:
            # Try detection limit from dedicated column first, fall back to Result_Measure
            dl_col = None
            for col_name in ["DetectionQuantitationLimitMeasure_MeasureValue",
                             "Result_DetectionQuantitationLimitMeasure"]:
                if col_name in df.columns:
                    dl_col = col_name
                    break

            if dl_col is not None:
                dl_values = pd.to_numeric(df.loc[non_detect_mask, dl_col], errors="coerce")
                dl_values = dl_values.fillna(df.loc[non_detect_mask, "ssc_value"])
            else:
                dl_values = df.loc[non_detect_mask, "ssc_value"]

            # Where DL is still missing, use conservative 1 mg/L
            dl_values = dl_values.fillna(1.0)
            df.loc[non_detect_mask, "ssc_value"] = dl_values / 2.0
            df.loc[non_detect_mask, "is_nondetect"] = True
            logger.info(f"  {n_nondetect} non-detects → DL/2 substitution")

    # --- Collection method classification (before filtering so it carries through) ---
    equip_col = None
    for candidate in ["SampleCollectionEquipmentName", "SampleCollectionEquipment"]:
        if candidate in df.columns:
            equip_col = candidate
            break

    def _classify_equipment(equip_str):
        if not isinstance(equip_str, str):
            return "unknown"
        e = equip_str.lower()
        if "automatic" in e or "peristaltic" in e or "submersible" in e:
            return "auto_point"
        if any(k in e for k in ["dh-", "dh ", "d-7", "d-9", "p-6", "us d", "us p",
                                 "equal width", "equal discharge", "multiple vertical",
                                 "bag sampler"]):
            return "depth_integrated"
        if any(k in e for k in ["grab", "open-mouth", "van dorn", "kemmerer",
                                 "weighted-bottle", "weighted bottle"]):
            return "grab"
        return "unknown"

    if equip_col is not None:
        df["collection_method"] = df[equip_col].apply(_classify_equipment)
    else:
        df["collection_method"] = "unknown"

    # --- Filter to valid rows ---
    valid = df.dropna(subset=["datetime", "ssc_value"]).copy()
    valid = valid[valid["ssc_value"] >= 0]  # Fix 11: keep SSC=0 (log1p handles it)

    # --- FIX 18: Deduplicate ---
    n_before_dedup = len(valid)
    valid = valid.drop_duplicates(
        subset=["datetime", "ssc_value"], keep="first"
    )
    n_dupes = n_before_dedup - len(valid)
    if n_dupes > 0:
        logger.info(f"  Removed {n_dupes} duplicate samples")

    valid = valid.sort_values("datetime").reset_index(drop=True)
    n_final = len(valid)
    logger.info(f"  {n_original} raw → {n_final} valid samples "
                f"({n_original - n_final} dropped: {n_null_time} null time, "
                f"{n_bad_tz} bad tz, {n_dupes} dupes)")

    return valid[["datetime", "ssc_value", "is_nondetect", "collection_method"]]


_CONTINUOUS_COLS = ["time", "value", "approval_status", "qualifier"]

def load_continuous(site_id: str, param_code: str) -> pd.DataFrame:
    """Load all cached continuous data for a site+param, concat chunks."""
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
    # Ensure all timestamps are tz-aware UTC (gap-fill files may differ from originals)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    return df


def align_site(site_id: str) -> pd.DataFrame:
    """Full alignment pipeline for one site.

    1. Load discrete SSC
    2. Load continuous turbidity (required) + all other params
    3. QC filter continuous data
    4. For each grab sample, find matching sensor window
    5. Build feature row
    """
    logger.info(f"Processing {site_id}")

    # Load discrete
    discrete = load_discrete(site_id)
    if discrete.empty:
        logger.warning(f"  No discrete data for {site_id}")
        return pd.DataFrame()
    logger.info(f"  {len(discrete)} SSC samples")

    # Load continuous turbidity (required)
    turb = load_continuous(site_id, "63680")
    if turb.empty:
        logger.warning(f"  No continuous turbidity for {site_id}")
        return pd.DataFrame()

    # QC filter turbidity
    turb_filtered, qc_stats = filter_continuous(turb)
    logger.info(f"  Turbidity QC: {qc_stats.get('pct_retained', '?')}% retained")

    # Align SSC samples with turbidity
    turb_clean = turb_filtered[["time", "value"]].copy()
    turb_clean.columns = ["datetime", "value"]

    # Keep is_nondetect and collection_method for later
    # Use merge_asof after alignment to map back by timestamp
    discrete_meta = discrete[["datetime", "is_nondetect", "collection_method"]].copy()
    discrete_meta["datetime"] = pd.to_datetime(discrete_meta["datetime"], utc=True)
    discrete_meta = discrete_meta.sort_values("datetime").drop_duplicates("datetime", keep="first")

    disc_clean = discrete[["datetime", "ssc_value"]].copy()
    disc_clean.columns = ["datetime", "value"]

    aligned = align_samples(
        continuous=turb_clean,
        discrete=disc_clean,
        max_gap=pd.Timedelta(minutes=15),  # Fix 6: tightened from ±30 to ±15 (Rasmussen 2009 standard)
    )

    if aligned.empty:
        logger.warning(f"  No aligned samples for {site_id}")
        return pd.DataFrame()

    # Rename columns to be specific
    aligned = aligned.rename(columns={
        "sensor_instant": "turbidity_instant",
        "window_mean": "turbidity_mean_1hr",
        "window_min": "turbidity_min_1hr",
        "window_max": "turbidity_max_1hr",
        "window_std": "turbidity_std_1hr",
        "window_range": "turbidity_range_1hr",
        "window_slope": "turbidity_slope_1hr",
    })

    # Add other continuous parameters as instantaneous values
    for pcode, pname in CONTINUOUS_PARAMS.items():
        if pcode == "63680":  # Already have turbidity
            continue

        cont = load_continuous(site_id, pcode)
        if cont.empty:
            aligned[f"{pname}_instant"] = np.nan
            continue

        # QC filter
        cont_filtered, _ = filter_continuous(cont)
        if cont_filtered.empty:
            aligned[f"{pname}_instant"] = np.nan
            continue

        # Interpolate each aligned sample between flanking continuous readings
        # Fix 12: Anchor to turbidity match time, not grab sample time
        # Fix 6: Use ±15 min window (consistent with primary alignment)
        cont_clean = cont_filtered[["time", "value"]].copy().reset_index(drop=True)
        cont_clean["time"] = pd.to_datetime(cont_clean["time"], utc=True)
        cont_clean = cont_clean.sort_values("time").reset_index(drop=True)

        from murkml.data.align import _interpolate_at_times
        c_times = cont_clean["time"].values
        c_vals = cont_clean["value"].astype(float).values
        s_times = pd.to_datetime(aligned["sample_time"], utc=True).values
        max_gap_ns = pd.Timedelta(minutes=15).value

        interp_vals, _, _ = _interpolate_at_times(c_times, c_vals, s_times, max_gap_ns)
        aligned[f"{pname}_instant"] = interp_vals

    # Add is_nondetect and collection_method via merge on timestamp
    aligned["sample_time"] = pd.to_datetime(aligned["sample_time"], utc=True)
    aligned = pd.merge_asof(
        aligned.sort_values("sample_time"),
        discrete_meta.rename(columns={"datetime": "sample_time"}),
        on="sample_time",
        direction="nearest",
        tolerance=pd.Timedelta(seconds=1),
    )
    if "is_nondetect" not in aligned.columns:
        aligned["is_nondetect"] = False
    if "collection_method" not in aligned.columns:
        aligned["collection_method"] = "unknown"
    aligned["is_nondetect"] = aligned["is_nondetect"].fillna(False)
    aligned["collection_method"] = aligned["collection_method"].fillna("unknown")

    # Add site ID
    aligned["site_id"] = site_id

    logger.info(f"  Aligned: {len(aligned)} samples with sensor data")
    return aligned


def main():
    import warnings
    warnings.filterwarnings("ignore")

    start_run("assemble_ssc")

    # Load qualified site list (preferred) or fall back to site catalog
    qualified_path = DATA_DIR / "qualified_sites.parquet"
    catalog_path = DATA_DIR / "site_catalog.parquet"
    if qualified_path.exists():
        catalog = pd.read_parquet(qualified_path)
        log_file(qualified_path, role="input")
        logger.info(f"Qualified sites: {len(catalog)} sites")
    elif catalog_path.exists():
        catalog = pd.read_parquet(catalog_path)
        log_file(catalog_path, role="input")
        logger.info(f"Site catalog (legacy): {len(catalog)} sites")
    else:
        logger.error("No site list found (qualified_sites.parquet or site_catalog.parquet)")
        sys.exit(1)

    # Check which qualified sites have downloaded discrete + continuous data
    disc_dir = DATA_DIR / "discrete"
    cont_dir = DATA_DIR / "continuous"
    qualified_ids = set(catalog["site_id"].tolist())

    available_sites = []
    if disc_dir.exists():
        for f in disc_dir.glob("*_ssc.parquet"):
            site_id = f.stem.replace("_ssc", "").replace("_", "-")
            if site_id in qualified_ids:
                available_sites.append(site_id)
    logger.info(f"Qualified sites with discrete data: {len(available_sites)} / {len(qualified_ids)}")

    # Process each site in parallel with progress logging
    import time as _time
    from joblib import Parallel, delayed

    def _safe_align(site_id, idx, total):
        t0 = _time.time()
        try:
            result = align_site(site_id)
            elapsed = _time.time() - t0
            if elapsed > 30:
                logger.warning(f"  SLOW: {site_id} took {elapsed:.1f}s")
            return result
        except Exception as e:
            logger.error(f"  FAILED: {site_id}: {e}")
            import traceback
            traceback.print_exc()
            return pd.DataFrame()

    n_total = len(available_sites)
    logger.info(f"Assembling {n_total} sites with 8 parallel workers...")

    results = Parallel(n_jobs=8, backend="loky", verbose=10)(
        delayed(_safe_align)(sid, i, n_total) for i, sid in enumerate(available_sites)
    )
    all_aligned = [r for r in results if not r.empty]
    logger.info(f"Assembly complete: {len(all_aligned)}/{n_total} sites produced paired data")
    for r in all_aligned:
        log_step("align_site", site_id=r["site_id"].iloc[0], rows_out=len(r))

    if not all_aligned:
        logger.error("No aligned data produced!")
        sys.exit(1)

    # Combine all sites (Tier 1: continuous turbidity pairs)
    dataset = pd.concat(all_aligned, ignore_index=True)
    dataset["turb_source"] = "continuous"
    n_continuous = len(dataset)
    logger.info(f"Tier 1 (continuous turbidity): {n_continuous} samples")

    # --- Tier 2/3: Add discrete turbidity pairs (SSC + portable turbidity, no continuous) ---
    disc_turb_dir = DATA_DIR / "discrete"
    USGS_TZ_OFFSETS_LOCAL = {
        "EST": -5, "EDT": -4, "CST": -6, "CDT": -5,
        "MST": -7, "MDT": -6, "PST": -8, "PDT": -7,
        "AKST": -9, "AKDT": -8, "HST": -10, "AST": -4,
        "UTC": 0, "GMT": 0,
    }

    discrete_pairs = []
    existing_pairs = set()
    # Build lookup of (site_id, sample_time) already in dataset
    # Use int64 nanoseconds for reliable comparison (avoids T-vs-space string format bug)
    for _, row in dataset.iterrows():
        t_ns = int(pd.Timestamp(row["sample_time"]).value) if pd.notna(row["sample_time"]) else 0
        existing_pairs.add((row["site_id"], t_ns))

    for site_id in available_sites:
        site_u = site_id.replace("-", "_")
        turb_file = disc_turb_dir / f"{site_u}_turbidity.parquet"

        if not turb_file.exists():
            continue

        turb = pd.read_parquet(turb_file)
        if turb.empty or "datetime" not in turb.columns or "turbidity_value" not in turb.columns:
            continue

        # Use load_discrete() for proper non-detect handling + collection_method (Bug B + C fix)
        ssc_parsed = load_discrete(site_id)
        if ssc_parsed.empty:
            continue

        turb["datetime"] = pd.to_datetime(turb["datetime"], utc=True)
        turb_times = turb["datetime"].values
        turb_vals = turb["turbidity_value"].values.astype(float)

        # Match SSC to discrete turbidity within ±60 min
        tolerance_ns = pd.Timedelta(minutes=60).value
        for _, ssc_row in ssc_parsed.iterrows():
            t = ssc_row["datetime"]
            t_ns = int(pd.Timestamp(t).value) if pd.notna(t) else 0
            key = (site_id, t_ns)
            if key in existing_pairs:
                continue  # Already paired with continuous data

            t_np = np.datetime64(t)
            diffs = np.abs((turb_times - t_np).astype(np.int64))
            if len(diffs) == 0:
                continue
            min_idx = diffs.argmin()
            if diffs[min_idx] <= tolerance_ns:
                pair = {
                    "sample_time": t,
                    "lab_value": float(ssc_row["ssc_value"]),
                    "turbidity_instant": float(turb_vals[min_idx]),
                    "match_gap_seconds": float(diffs[min_idx] / 1e9),
                    "site_id": site_id,
                    "is_nondetect": bool(ssc_row["is_nondetect"]),
                    "collection_method": str(ssc_row.get("collection_method", "unknown")),
                    "turb_source": "discrete",
                    # Window features are NaN for discrete-only pairs
                    "turbidity_mean_1hr": np.nan,
                    "turbidity_max_1hr": np.nan,
                    "turbidity_min_1hr": np.nan,
                    "turbidity_std_1hr": np.nan,
                    "turbidity_range_1hr": np.nan,
                    "turbidity_slope_1hr": np.nan,
                    "window_count": 0,
                }
                discrete_pairs.append(pair)
                existing_pairs.add(key)

    if discrete_pairs:
        disc_df = pd.DataFrame(discrete_pairs)
        logger.info(f"Tier 2/3 (discrete turbidity): {len(disc_df)} samples from {disc_df['site_id'].nunique()} sites")
        dataset = pd.concat([dataset, disc_df], ignore_index=True)
    else:
        logger.info("Tier 2/3: No discrete turbidity pairs found")

    logger.info(f"Combined: {len(dataset)} total samples ({n_continuous} continuous + {len(discrete_pairs)} discrete)")

    # --- Add sensor calibration features ---
    cal_path = DATA_DIR / "processed" / "sensor_calibration.parquet"
    cal_summary_path = DATA_DIR / "processed" / "sensor_calibration_summary.parquet"

    if cal_path.exists() and cal_summary_path.exists():
        cal = pd.read_parquet(cal_path)
        cal_summary = pd.read_parquet(cal_summary_path)
        logger.info(f"Sensor calibration: {len(cal)} pairs from {cal['site_id'].nunique()} sites")

        # For each sample, compute: sensor_offset (median of last 3 visits), days_since_cleaning, sensor_family
        dataset["sensor_offset"] = np.nan
        dataset["days_since_last_visit"] = np.nan
        dataset["sensor_family"] = "unknown"

        for site_id in dataset["site_id"].unique():
            site_cal = cal[cal["site_id"] == site_id].sort_values("visit_time")
            if site_cal.empty:
                continue

            site_mask = dataset["site_id"] == site_id
            site_data = dataset.loc[site_mask]
            cal_times = site_cal["visit_time"].values
            cal_offsets = site_cal["offset"].values
            cal_families = site_cal["sensor_family"].values

            for idx, row in site_data.iterrows():
                t = pd.Timestamp(row["sample_time"])
                if pd.isna(t):
                    continue

                t_np = np.datetime64(t)

                # Find calibration visits before this sample
                before_mask = cal_times <= t_np

                # For discrete-source rows, exclude the current visit to avoid self-reference (Bug D fix)
                if row.get("turb_source") == "discrete":
                    # Exclude visits within 5 min of this sample (same field visit)
                    not_self = np.abs((cal_times - t_np).astype(np.int64)) > 300_000_000_000  # 5 min in ns
                    before_mask = before_mask & not_self

                if before_mask.sum() > 0:
                    # Use MOST RECENT offset, not median (Dr. Medina: cleaning resets corrupt median)
                    dataset.at[idx, "sensor_offset"] = float(cal_offsets[before_mask][-1])

                    last_visit = cal_times[before_mask][-1]
                    days = (t_np - last_visit) / np.timedelta64(1, "D")
                    dataset.at[idx, "days_since_last_visit"] = float(days)

                    dataset.at[idx, "sensor_family"] = str(cal_families[before_mask][-1])

        n_with_cal = dataset["sensor_offset"].notna().sum()
        logger.info(f"Sensor calibration features applied: {n_with_cal}/{len(dataset)} samples have calibration data")
    else:
        dataset["sensor_offset"] = np.nan
        dataset["days_since_last_visit"] = np.nan
        dataset["sensor_family"] = "unknown"
        logger.info("No sensor calibration data found — features set to NaN/unknown")

    # Add log-transformed target
    dataset["ssc_log1p"] = np.log1p(dataset["lab_value"])

    # Apply feature engineering
    dataset = engineer_features(dataset)

    # Save
    output_path = DATA_DIR / "processed" / "turbidity_ssc_paired.parquet"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_parquet(output_path, index=False)
    log_file(output_path, role="output")

    log_step("assemble_complete",
             n_sites=int(dataset["site_id"].nunique()),
             n_samples=len(dataset),
             n_features=len([c for c in dataset.columns if c not in {"site_id", "sample_time", "lab_value", "ssc_log1p", "is_nondetect"}]))

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info(f"Dataset assembled: {output_path}")
    logger.info(f"Total samples: {len(dataset)}")
    logger.info(f"Sites: {dataset['site_id'].nunique()}")
    if "state" in catalog.columns:
        logger.info(f"States: {catalog[catalog['site_id'].isin(dataset['site_id'].unique())]['state'].unique()}")
    logger.info(f"SSC range: {dataset['lab_value'].min():.0f} - {dataset['lab_value'].max():.0f} mg/L")
    logger.info(f"Columns: {list(dataset.columns)}")

    end_run()

    # Per-site summary
    logger.info(f"\nPer-site summary:")
    for site_id, group in dataset.groupby("site_id"):
        logger.info(
            f"  {site_id}: {len(group)} samples, "
            f"SSC {group['lab_value'].min():.0f}-{group['lab_value'].max():.0f} mg/L"
        )


if __name__ == "__main__":
    main()
