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


def load_discrete(site_id: str) -> pd.DataFrame:
    """Load discrete SSC samples for a site, parse datetime and value."""
    cache_file = DATA_DIR / "discrete" / f"{site_id.replace('-', '_')}_ssc.parquet"
    if not cache_file.exists():
        return pd.DataFrame()

    df = pd.read_parquet(cache_file)

    # Parse datetime from Activity_StartDate + Activity_StartTime
    if "Activity_StartDate" in df.columns:
        time_str = df.get("Activity_StartTime", pd.Series(["12:00:00"] * len(df)))
        time_str = time_str.fillna("12:00:00")
        tz_str = df.get("Activity_StartTimeZone", pd.Series(["UTC"] * len(df)))

        df["datetime"] = pd.to_datetime(
            df["Activity_StartDate"].astype(str) + " " + time_str.astype(str),
            errors="coerce",
            utc=True,
        )

    # Parse SSC value
    if "Result_Measure" in df.columns:
        df["ssc_value"] = pd.to_numeric(df["Result_Measure"], errors="coerce")

    # Check for non-detects
    if "Result_ResultDetectionCondition" in df.columns:
        non_detect_mask = df["Result_ResultDetectionCondition"] == "Not Detected"
        n_nondetect = non_detect_mask.sum()
        if n_nondetect > 0:
            logger.info(f"  {n_nondetect} non-detects in SSC (keeping detection limit as value)")

    # Filter to valid rows
    valid = df.dropna(subset=["datetime", "ssc_value"]).copy()
    valid = valid[valid["ssc_value"] > 0]  # SSC must be positive
    valid = valid.sort_values("datetime").reset_index(drop=True)

    return valid[["datetime", "ssc_value"]]


def load_continuous(site_id: str, param_code: str) -> pd.DataFrame:
    """Load all cached continuous data for a site+param, concat chunks."""
    cont_dir = DATA_DIR / "continuous" / site_id.replace("-", "_") / param_code
    if not cont_dir.exists():
        return pd.DataFrame()

    chunks = []
    for f in sorted(cont_dir.glob("*.parquet")):
        chunk = pd.read_parquet(f)
        if len(chunk) > 0:
            chunks.append(chunk)

    if not chunks:
        return pd.DataFrame()

    df = pd.concat(chunks, ignore_index=True)
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

    disc_clean = discrete[["datetime", "ssc_value"]].copy()
    disc_clean.columns = ["datetime", "value"]

    aligned = align_samples(
        continuous=turb_clean,
        discrete=disc_clean,
        max_gap=pd.Timedelta(minutes=30),  # Slightly relaxed from ±15 to ±30
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

        # Match each aligned sample to nearest continuous reading
        cont_clean = cont_filtered[["time", "value"]].copy().reset_index(drop=True)
        cont_clean["time"] = pd.to_datetime(cont_clean["time"], utc=True)
        cont_clean = cont_clean.sort_values("time").reset_index(drop=True)

        instant_values = []
        for _, row in aligned.iterrows():
            sample_time = row["sample_time"]
            time_diffs = (cont_clean["time"] - sample_time).abs()
            min_idx = time_diffs.idxmin()
            if time_diffs.iloc[min_idx] <= pd.Timedelta(minutes=30):
                instant_values.append(cont_clean["value"].iloc[min_idx])
            else:
                instant_values.append(np.nan)

        aligned[f"{pname}_instant"] = instant_values

    # Add site ID
    aligned["site_id"] = site_id

    logger.info(f"  Aligned: {len(aligned)} samples with sensor data")
    return aligned


def main():
    import warnings
    warnings.filterwarnings("ignore")

    # Load site catalog
    catalog = pd.read_parquet(DATA_DIR / "site_catalog.parquet")
    logger.info(f"Site catalog: {len(catalog)} sites")

    # Check which sites have downloaded data
    disc_dir = DATA_DIR / "discrete"
    available_sites = []
    if disc_dir.exists():
        for f in disc_dir.glob("*_ssc.parquet"):
            site_id = f.stem.replace("_ssc", "").replace("_", "-")
            available_sites.append(site_id)
    logger.info(f"Sites with downloaded data: {len(available_sites)}")

    # Process each site
    all_aligned = []
    for site_id in available_sites:
        try:
            aligned = align_site(site_id)
            if not aligned.empty:
                all_aligned.append(aligned)
        except Exception as e:
            logger.error(f"  Error processing {site_id}: {e}")
            continue

    if not all_aligned:
        logger.error("No aligned data produced!")
        sys.exit(1)

    # Combine all sites
    dataset = pd.concat(all_aligned, ignore_index=True)

    # Add log-transformed target
    dataset["ssc_log1p"] = np.log1p(dataset["lab_value"])

    # Apply feature engineering
    dataset = engineer_features(dataset)

    # Save
    output_path = DATA_DIR / "processed" / "turbidity_ssc_paired.parquet"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_parquet(output_path, index=False)

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info(f"Dataset assembled: {output_path}")
    logger.info(f"Total samples: {len(dataset)}")
    logger.info(f"Sites: {dataset['site_id'].nunique()}")
    logger.info(f"States: {catalog[catalog['site_id'].isin(dataset['site_id'].unique())]['state'].unique()}")
    logger.info(f"SSC range: {dataset['lab_value'].min():.0f} - {dataset['lab_value'].max():.0f} mg/L")
    logger.info(f"Columns: {list(dataset.columns)}")

    # Per-site summary
    logger.info(f"\nPer-site summary:")
    for site_id, group in dataset.groupby("site_id"):
        logger.info(
            f"  {site_id}: {len(group)} samples, "
            f"SSC {group['lab_value'].min():.0f}-{group['lab_value'].max():.0f} mg/L"
        )


if __name__ == "__main__":
    main()
