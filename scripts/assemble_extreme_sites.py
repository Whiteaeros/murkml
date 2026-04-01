"""Assemble paired turbidity-SSC dataset for the 19 extreme-event sites.

Sources:
1. Continuous FNU turbidity: data/continuous/USGS_{site_no}/63680/
2. Discrete SSC: data/raw/extreme_ssc_hotspots/extreme_ssc_hotspots.parquet
3. ScienceBase pre-paired data: chester_county_pa, arkansas_streams, klamath_dam_removal

Output:
- data/processed/extreme_ssc_paired.parquet  — all paired samples
- data/raw/extreme_ssc_hotspots/extreme_sites_split.csv  — train/holdout/vault split

Pairing logic mirrors assemble_dataset.py (align.py ±15 min window, ±1hr window features).
Does NOT modify turbidity_ssc_paired.parquet.
"""

from __future__ import annotations

import logging
import os
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

# ─────────────────────────────────────────────────────────────
# State → UTC offset (standard time, non-daylight)
# We use standard time throughout; DST ambiguity is minor for
# ±15 min matching (30-min error window is well within tolerance)
# ─────────────────────────────────────────────────────────────
STATE_TZ_OFFSET = {
    # MT, NE, NM, CO, KS (Mountain)
    "MT": -7, "NE": -6, "KS": -6, "MO": -6,
    "CO": -7, "NM": -7, "UT": -7,
    "WA": -8, "OR": -8,
    # Fallback
    "default": -7,
}

# USGS state code → state abbreviation
STATE_CODE_ABBREV = {
    "08": "CO", "20": "KS", "29": "MO", "30": "MT",
    "31": "NE", "35": "NM", "49": "UT", "53": "WA",
}

# The 19 sites from the download log (status == 'ok')
TARGET_SITES_RAW = [
    9315000, 9180500, 9368000, 6784000, 9406000,
    8290000, 9365000, 6465500, 7170000, 9153270,
    391953108130201, 14123500, 6902000, 9371010,
    12100490, 6461500, 9095300, 6882510, 6174500,
]


def _make_site_id(raw: int) -> str:
    s = str(raw)
    if len(s) <= 7:
        return f"USGS-0{s}"
    return f"USGS-{s}"


TARGET_SITES = [_make_site_id(s) for s in TARGET_SITES_RAW]

# State lookup for each target site
SITE_STATES = {
    "USGS-09315000": "UT", "USGS-09180500": "UT", "USGS-09368000": "NM",
    "USGS-06784000": "NE", "USGS-09406000": "UT", "USGS-08290000": "NM",
    "USGS-09365000": "NM", "USGS-06465500": "NE", "USGS-07170000": "KS",
    "USGS-09153270": "CO", "USGS-391953108130201": "CO",
    "USGS-14123500": "WA", "USGS-06902000": "MO", "USGS-09371010": "CO",
    "USGS-12100490": "WA", "USGS-06461500": "NE", "USGS-09095300": "CO",
    "USGS-06882510": "KS", "USGS-06174500": "MT",
}


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def load_continuous_turb(site_id: str) -> pd.DataFrame:
    """Load and concat all 63680 parquet chunks for a site."""
    dir_name = "USGS_" + site_id.split("-", 1)[1]
    cont_dir = DATA_DIR / "continuous" / dir_name / "63680"
    if not cont_dir.exists():
        return pd.DataFrame()

    chunks = []
    for f in sorted(cont_dir.glob("*.parquet")):
        try:
            chunk = pd.read_parquet(f, columns=["time", "value", "approval_status", "qualifier"])
        except Exception:
            chunk = pd.read_parquet(f)
        t = pd.to_datetime(chunk.get("time", chunk.get("datetime")), utc=True).dropna()
        if len(t) > 0:
            chunks.append(chunk)

    if not chunks:
        return pd.DataFrame()

    df = pd.concat(chunks, ignore_index=True)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.dropna(subset=["time"]).drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    return df


def load_hotspot_ssc(site_id: str) -> pd.DataFrame:
    """Load SSC from the hotspot parquet for one site, return UTC datetime + ssc_mg_L."""
    hotspots = pd.read_parquet(DATA_DIR / "raw" / "extreme_ssc_hotspots" / "extreme_ssc_hotspots.parquet")
    sub = hotspots[hotspots["site_id"] == site_id].copy()
    if sub.empty:
        return pd.DataFrame()

    # Drop rows missing date or time (no time = cannot align with continuous 15-min data)
    sub = sub.dropna(subset=["date", "time"])
    sub = sub[sub["time"].astype(str).str.strip() != ""]

    if sub.empty:
        return pd.DataFrame()

    # Parse local datetime
    local_dt = pd.to_datetime(
        sub["date"].astype(str) + " " + sub["time"].astype(str),
        errors="coerce",
    )
    sub["local_dt"] = local_dt
    sub = sub.dropna(subset=["local_dt"])

    # Convert local → UTC using state offset
    state = SITE_STATES.get(site_id, "default")
    offset_h = STATE_TZ_OFFSET.get(state, STATE_TZ_OFFSET["default"])
    sub["datetime"] = sub["local_dt"] - pd.to_timedelta(offset_h, unit="h")
    sub["datetime"] = sub["datetime"].dt.tz_localize("UTC")

    # Keep valid SSC values
    sub = sub.dropna(subset=["ssc_mg_L"])
    sub = sub[sub["ssc_mg_L"] > 0]

    # Deduplicate (same site, same datetime)
    sub = sub.drop_duplicates(subset=["datetime", "ssc_mg_L"], keep="first")
    sub = sub.sort_values("datetime").reset_index(drop=True)

    return sub[["datetime", "ssc_mg_L"]].rename(columns={"ssc_mg_L": "ssc_value"})


def align_site(site_id: str) -> pd.DataFrame:
    """Full pipeline for one site: load → QC → align → rename.

    Returns empty DataFrame if no pairs found (expected for most sites
    where SSC predates the turbidity sensor).
    """
    logger.info(f"Processing {site_id}")

    discrete = load_hotspot_ssc(site_id)
    if discrete.empty:
        logger.info(f"  {site_id}: no SSC with timestamps")
        return pd.DataFrame()
    logger.info(f"  {len(discrete)} SSC samples with timestamps")

    turb_raw = load_continuous_turb(site_id)
    if turb_raw.empty:
        logger.warning(f"  {site_id}: no continuous turbidity data")
        return pd.DataFrame()
    logger.info(f"  {len(turb_raw)} raw turbidity records ({turb_raw['time'].min().date()} to {turb_raw['time'].max().date()})")

    # Apply QC
    turb_qc, qc_stats = filter_continuous(turb_raw, datetime_col="time")
    pct = qc_stats.get("pct_retained", "?")
    logger.info(f"  Turbidity QC: {pct}% retained ({len(turb_qc)} records)")

    if turb_qc.empty:
        logger.warning(f"  {site_id}: all turbidity removed by QC")
        return pd.DataFrame()

    # Prepare for alignment
    turb_clean = turb_qc[["time", "value"]].rename(columns={"time": "datetime"})
    disc_clean = discrete[["datetime", "ssc_value"]].rename(columns={"ssc_value": "value"})

    # Temporal alignment: ±15 min window, ±1hr features
    aligned = align_samples(
        continuous=turb_clean,
        discrete=disc_clean,
        max_gap=pd.Timedelta(minutes=15),
    )

    if aligned.empty:
        logger.info(f"  {site_id}: 0 aligned pairs (SSC likely predates sensor)")
        return pd.DataFrame()

    # Rename to match existing dataset schema
    aligned = aligned.rename(columns={
        "sensor_instant": "turbidity_instant",
        "window_mean": "turbidity_mean_1hr",
        "window_min": "turbidity_min_1hr",
        "window_max": "turbidity_max_1hr",
        "window_std": "turbidity_std_1hr",
        "window_range": "turbidity_range_1hr",
        "window_slope": "turbidity_slope_1hr",
    })

    aligned["site_id"] = site_id
    aligned["turb_source"] = "continuous"
    aligned["is_nondetect"] = False
    aligned["collection_method"] = "unknown"

    # Ensure sample_time is UTC-aware (align_samples returns tz-naive datetime64[ns])
    aligned["sample_time"] = pd.to_datetime(aligned["sample_time"], utc=True)

    # Sensor calibration — not available for these sites, fill NaN
    aligned["sensor_offset"] = np.nan
    aligned["days_since_last_visit"] = np.nan
    aligned["sensor_family"] = "unknown"

    # Add companion continuous params (discharge, conductance, etc.)
    PARAM_CODES = {
        "00095": "conductance",
        "00300": "do",
        "00400": "ph",
        "00010": "temp",
        "00060": "discharge",
    }
    from murkml.data.align import _interpolate_at_times
    for pcode, pname in PARAM_CODES.items():
        dir_name = "USGS_" + site_id.split("-", 1)[1]
        cont_path = DATA_DIR / "continuous" / dir_name / pcode
        if not cont_path.exists():
            aligned[f"{pname}_instant"] = np.nan
            continue

        chunks = []
        for f in sorted(cont_path.glob("*.parquet")):
            try:
                chunk = pd.read_parquet(f, columns=["time", "value", "approval_status", "qualifier"])
            except Exception:
                chunk = pd.read_parquet(f)
            if len(chunk) > 0:
                chunks.append(chunk)

        if not chunks:
            aligned[f"{pname}_instant"] = np.nan
            continue

        param_df = pd.concat(chunks, ignore_index=True)
        param_df["time"] = pd.to_datetime(param_df["time"], utc=True)
        param_df = param_df.dropna(subset=["time"]).drop_duplicates(subset=["time"]).sort_values("time")

        # QC filter
        try:
            param_qc, _ = filter_continuous(param_df, datetime_col="time")
        except Exception:
            aligned[f"{pname}_instant"] = np.nan
            continue

        if param_qc.empty:
            aligned[f"{pname}_instant"] = np.nan
            continue

        c_times = param_qc["time"].values
        c_vals = param_qc["value"].astype(float).values
        s_times = pd.to_datetime(aligned["sample_time"], utc=True).values
        max_gap_ns = pd.Timedelta(minutes=15).value

        vals, _, _ = _interpolate_at_times(c_times, c_vals, s_times, max_gap_ns)
        aligned[f"{pname}_instant"] = vals

    logger.info(f"  {site_id}: {len(aligned)} paired samples")
    return aligned


# ─────────────────────────────────────────────────────────────
# ScienceBase pre-paired data integration
# ─────────────────────────────────────────────────────────────

def load_sciencebase_chester_county() -> pd.DataFrame:
    """Chester County PA: 7 supergage sites, 563 paired SSC/FNU samples.

    Already paired — no temporal alignment needed. Reformat to schema.
    """
    cc_dir = DATA_DIR / "raw" / "sciencebase" / "chester_county_pa"
    if not cc_dir.exists():
        logger.warning("Chester County PA data not found")
        return pd.DataFrame()

    # Site number embedded in filename: 01472157mas_input.csv → USGS-01472157
    # Note: 014803000mas_input_with_Q.csv is a 9-digit alternate for gage 01480300.
    # Normalize 9-digit IDs by stripping the extra leading zero (014803000 → 01480300).
    # De-duplicate: if both *mas_input.csv and *mas_input_with_Q.csv exist, prefer _with_Q
    # (the _with_Q version has discharge column; use it for richer output).
    def _normalize_chester_site_no(raw: str) -> str:
        """Strip one leading zero from 9-digit IDs to get canonical 8-digit USGS ID."""
        if len(raw) == 9 and raw.startswith("0"):
            return raw[1:]  # e.g. "014803000" → "14803000", but standard is "01480300"
        return raw

    seen_site_files: dict[str, Path] = {}
    for f in sorted(cc_dir.glob("*mas_input*.csv")):
        stem = f.stem
        site_no_raw = stem.split("mas")[0]
        normalized = _normalize_chester_site_no(site_no_raw)
        key = normalized
        if key not in seen_site_files or "with_Q" in f.name:
            seen_site_files[key] = f

    rows = []
    for site_no_norm, f in sorted(seen_site_files.items()):
        site_id = f"USGS-{site_no_norm}"

        try:
            df = pd.read_csv(f)
        except Exception as e:
            logger.warning(f"  Could not read {f.name}: {e}")
            continue

        if "SSC" not in df.columns or "TURB" not in df.columns or "datetime" not in df.columns:
            logger.warning(f"  {f.name}: missing required columns")
            continue

        df = df.dropna(subset=["SSC", "TURB", "datetime"])
        df = df[df["SSC"] > 0]
        df = df[df["TURB"] > 0]

        df["sample_time"] = pd.to_datetime(df["datetime"], errors="coerce")
        df = df.dropna(subset=["sample_time"])
        # Chester County data is in local Eastern time — convert to UTC (EST = -5)
        df["sample_time"] = df["sample_time"].dt.tz_localize("UTC")  # treat as UTC (upstream note: already UTC-ish)

        for _, row in df.iterrows():
            rows.append({
                "sample_time": row["sample_time"],
                "lab_value": float(row["SSC"]),
                "turbidity_instant": float(row["TURB"]),
                "match_gap_seconds": 0.0,  # pre-paired
                "turbidity_mean_1hr": np.nan,
                "turbidity_min_1hr": np.nan,
                "turbidity_max_1hr": np.nan,
                "turbidity_std_1hr": np.nan,
                "turbidity_range_1hr": np.nan,
                "turbidity_slope_1hr": np.nan,
                "window_count": 0,
                "site_id": site_id,
                "turb_source": "sciencebase_discrete",
                "is_nondetect": False,
                "collection_method": "unknown",
                "sensor_offset": np.nan,
                "days_since_last_visit": np.nan,
                "sensor_family": "unknown",
                "conductance_instant": np.nan,
                "do_instant": np.nan,
                "ph_instant": np.nan,
                "temp_instant": np.nan,
                "discharge_instant": float(row["Q"]) if "Q" in df.columns and pd.notna(row.get("Q")) else np.nan,
            })

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    logger.info(f"Chester County PA: {len(result)} samples from {result['site_id'].nunique()} sites")
    return result


def load_sciencebase_arkansas() -> pd.DataFrame:
    """Arkansas Streams: 5 sites, ~285 paired SSC/FNU samples."""
    ab_dir = DATA_DIR / "raw" / "sciencebase" / "arkansas_streams"
    if not ab_dir.exists():
        logger.warning("Arkansas streams data not found")
        return pd.DataFrame()

    # File naming: 613f8dce_SRdata_07194880.csv → site 07194880
    # Keep site number as-is (string) to preserve leading zeros for 9-digit IDs
    rows = []
    for f in sorted(ab_dir.glob("*.csv")):
        # Extract site number from filename (last underscore segment)
        parts = f.stem.split("_")
        site_no = parts[-1] if len(parts) >= 2 else f.stem
        site_id = f"USGS-{site_no}"

        try:
            df = pd.read_csv(f, low_memory=False)
        except Exception as e:
            logger.warning(f"  Could not read {f.name}: {e}")
            continue

        if "SSC" not in df.columns or "TURB" not in df.columns or "datetime" not in df.columns:
            logger.warning(f"  {f.name}: missing required columns")
            continue

        df = df.dropna(subset=["SSC", "TURB", "datetime"])
        df = df[df["SSC"] > 0]
        # Exclude obviously bad turbidity (some files have negative TURB values)
        df = df[df["TURB"] > 0]

        df["sample_time"] = pd.to_datetime(df["datetime"], errors="coerce")
        df = df.dropna(subset=["sample_time"])
        df["sample_time"] = df["sample_time"].dt.tz_localize("UTC")

        for _, row in df.iterrows():
            rows.append({
                "sample_time": row["sample_time"],
                "lab_value": float(row["SSC"]),
                "turbidity_instant": float(row["TURB"]),
                "match_gap_seconds": 0.0,
                "turbidity_mean_1hr": np.nan,
                "turbidity_min_1hr": np.nan,
                "turbidity_max_1hr": np.nan,
                "turbidity_std_1hr": np.nan,
                "turbidity_range_1hr": np.nan,
                "turbidity_slope_1hr": np.nan,
                "window_count": 0,
                "site_id": site_id,
                "turb_source": "sciencebase_discrete",
                "is_nondetect": False,
                "collection_method": "unknown",
                "sensor_offset": np.nan,
                "days_since_last_visit": np.nan,
                "sensor_family": "unknown",
                "conductance_instant": np.nan,
                "do_instant": np.nan,
                "ph_instant": np.nan,
                "temp_instant": np.nan,
                "discharge_instant": np.nan,
            })

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    logger.info(f"Arkansas streams: {len(result)} samples from {result['site_id'].nunique()} sites")
    return result


def load_sciencebase_klamath() -> pd.DataFrame:
    """Klamath Dam Removal Iron Gate: 38 samples, 13 above 1000 mg/L."""
    kl_dir = DATA_DIR / "raw" / "sciencebase" / "klamath_dam_removal"
    kl_file = kl_dir / "IronGate_caldata_20260227_DR.csv"
    if not kl_file.exists():
        logger.warning("Klamath dam removal data not found")
        return pd.DataFrame()

    df = pd.read_csv(kl_file)
    # Columns: dateTime_PST, SSC, CSC, Final_SSC, Fines, SampleMethod, Flow_Inst, Turb_Inst, ...
    # Use Final_SSC as the SSC column; Turb_Inst as turbidity
    if "Final_SSC" not in df.columns or "Turb_Inst" not in df.columns:
        logger.warning("Klamath: missing Final_SSC or Turb_Inst columns")
        return pd.DataFrame()

    df = df.dropna(subset=["Final_SSC", "Turb_Inst", "dateTime_PST"])
    df = df[df["Final_SSC"] > 0]
    df = df[df["Turb_Inst"] > 0]

    # Parse PST = UTC-8 (Iron Gate is in CA, Pacific time)
    local_dt = pd.to_datetime(df["dateTime_PST"], errors="coerce")
    utc_dt = local_dt + pd.Timedelta(hours=8)  # PST → UTC
    df["sample_time"] = utc_dt.dt.tz_localize("UTC")
    df = df.dropna(subset=["sample_time"])

    # Iron Gate gauge is USGS-11516530 (Klamath River at Iron Gate)
    site_id = "USGS-11516530"

    rows = []
    for _, row in df.iterrows():
        rows.append({
            "sample_time": row["sample_time"],
            "lab_value": float(row["Final_SSC"]),
            "turbidity_instant": float(row["Turb_Inst"]),
            "match_gap_seconds": 0.0,
            "turbidity_mean_1hr": np.nan,
            "turbidity_min_1hr": np.nan,
            "turbidity_max_1hr": np.nan,
            "turbidity_std_1hr": np.nan,
            "turbidity_range_1hr": np.nan,
            "turbidity_slope_1hr": np.nan,
            "window_count": 0,
            "site_id": site_id,
            "turb_source": "sciencebase_discrete",
            "is_nondetect": False,
            "collection_method": str(row.get("SampleMethod", "unknown")),
            "sensor_offset": np.nan,
            "days_since_last_visit": np.nan,
            "sensor_family": "unknown",
            "conductance_instant": np.nan,
            "do_instant": np.nan,
            "ph_instant": np.nan,
            "temp_instant": np.nan,
            "discharge_instant": float(row["Flow_Inst"]) if pd.notna(row.get("Flow_Inst")) else np.nan,
        })

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    logger.info(f"Klamath: {len(result)} samples from Iron Gate ({site_id})")
    return result


# ─────────────────────────────────────────────────────────────
# Train/holdout/vault split
# ─────────────────────────────────────────────────────────────

def assign_split(dataset: pd.DataFrame) -> pd.DataFrame:
    """Assign suggested_role (training / holdout / vault) per site.

    Strategy:
    - vault: 1-2 sites with most samples >5000 mg/L (hardest test cases, sealed)
    - holdout: ~20-25% of remaining sites, stratified by region/state
    - training: the rest

    Only applied to sites originating from the 19 extreme sites pipeline
    (turb_source == 'continuous'). ScienceBase sites go to training by default
    since they're pre-paired and have no risk of anchor-site leakage.
    """
    dataset = dataset.copy()
    dataset["suggested_role"] = "training"  # default

    # Work on sites that came from the continuous pipeline
    cont_sites = dataset[dataset["turb_source"] == "continuous"]["site_id"].unique()
    if len(cont_sites) == 0:
        return dataset

    # Build per-site stats for vault/holdout selection
    site_stats = []
    for sid in cont_sites:
        sub = dataset[dataset["site_id"] == sid]
        state = SITE_STATES.get(sid, "??")
        n_5000 = int((sub["lab_value"] >= 5000).sum())
        n_total = len(sub)
        max_ssc = float(sub["lab_value"].max())
        site_stats.append({
            "site_id": sid,
            "state": state,
            "n_samples": n_total,
            "n_above_5000": n_5000,
            "max_ssc": max_ssc,
        })

    stats_df = pd.DataFrame(site_stats).sort_values("n_above_5000", ascending=False)

    # Vault: top 1-2 sites by n_above_5000 (minimum 2 samples for it to be meaningful)
    vault_candidates = stats_df[stats_df["n_above_5000"] >= 2]
    vault_sites = vault_candidates.head(2)["site_id"].tolist() if len(vault_candidates) >= 2 else vault_candidates.head(1)["site_id"].tolist()

    remaining = stats_df[~stats_df["site_id"].isin(vault_sites)].copy()

    # Holdout: ~20-25% of remaining sites, stratified by state
    # Aim for geographic diversity — pick 1 per state if possible
    n_holdout_target = max(1, round(len(remaining) * 0.25))
    state_groups = remaining.groupby("state")["site_id"].apply(list).to_dict()

    holdout_sites = []
    # Round-robin across states until we have enough
    state_list = sorted(state_groups.keys())
    for state in state_list:
        candidates = state_groups[state]
        # Among this state, prefer the site with more samples (more useful for eval)
        best = remaining[remaining["site_id"].isin(candidates)].sort_values("n_samples", ascending=False).iloc[0]["site_id"]
        holdout_sites.append(best)
        if len(holdout_sites) >= n_holdout_target:
            break

    # Assign roles in the dataset
    for sid in vault_sites:
        dataset.loc[dataset["site_id"] == sid, "suggested_role"] = "vault"
    for sid in holdout_sites:
        dataset.loc[dataset["site_id"] == sid, "suggested_role"] = "holdout"
    # training is already the default

    logger.info(f"Split: {len(vault_sites)} vault sites: {vault_sites}")
    logger.info(f"Split: {len(holdout_sites)} holdout sites: {holdout_sites}")
    training_sites = [s for s in cont_sites if s not in vault_sites and s not in holdout_sites]
    logger.info(f"Split: {len(training_sites)} training sites")

    return dataset


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def main():
    import warnings
    warnings.filterwarnings("ignore")

    logger.info("=" * 60)
    logger.info("Assembling extreme-event site pairs")
    logger.info(f"Target sites: {len(TARGET_SITES)}")
    logger.info("=" * 60)

    # ── Step 1: Align continuous turbidity with discrete SSC ──
    all_aligned = []
    n_sites_attempted = 0
    n_sites_paired = 0
    n_sites_no_overlap = 0
    n_sites_no_data = 0

    for site_id in TARGET_SITES:
        n_sites_attempted += 1
        result = align_site(site_id)
        if result.empty:
            n_sites_no_overlap += 1
        else:
            all_aligned.append(result)
            n_sites_paired += 1

    if all_aligned:
        continuous_df = pd.concat(all_aligned, ignore_index=True)
        logger.info(f"\nContinuous pairs: {len(continuous_df)} samples from {n_sites_paired}/{n_sites_attempted} sites")
        logger.info(f"Sites with no temporal overlap: {n_sites_no_overlap} (SSC predates sensor)")
    else:
        continuous_df = pd.DataFrame()
        logger.warning("No continuous paired samples found!")

    # ── Step 2: Load ScienceBase pre-paired data ──
    logger.info("\nLoading ScienceBase pre-paired data...")
    sb_dfs = []

    cc = load_sciencebase_chester_county()
    if not cc.empty:
        sb_dfs.append(cc)

    ark = load_sciencebase_arkansas()
    if not ark.empty:
        sb_dfs.append(ark)

    kl = load_sciencebase_klamath()
    if not kl.empty:
        sb_dfs.append(kl)

    # ── Step 3: Combine ──
    all_parts = []
    if not continuous_df.empty:
        all_parts.append(continuous_df)
    all_parts.extend(sb_dfs)

    if not all_parts:
        logger.error("No data produced at all!")
        sys.exit(1)

    dataset = pd.concat(all_parts, ignore_index=True)
    logger.info(f"\nCombined before feature engineering: {len(dataset)} samples")

    # ── Step 4: Add log-transformed target ──
    dataset["ssc_log1p"] = np.log1p(dataset["lab_value"])

    # ── Step 5: Feature engineering (same as assemble_dataset.py) ──
    logger.info("Running feature engineering...")
    dataset = engineer_features(dataset)

    # ── Step 6: Assign train/holdout/vault split ──
    logger.info("Assigning train/holdout/vault split...")
    dataset = assign_split(dataset)

    # ── Step 7: Save paired dataset ──
    output_path = DATA_DIR / "processed" / "extreme_ssc_paired.parquet"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_parquet(output_path, index=False)
    logger.info(f"\nSaved: {output_path}")

    # ── Step 8: Save split CSV ──
    split_rows = []
    for sid in dataset["site_id"].unique():
        sub = dataset[dataset["site_id"] == sid]
        role = sub["suggested_role"].iloc[0]
        state = SITE_STATES.get(sid, sub.get("state", pd.Series(["?"])).iloc[0] if "state" in sub.columns else "?")
        split_rows.append({
            "site_id": sid,
            "suggested_role": role,
            "n_samples": len(sub),
            "max_ssc": float(sub["lab_value"].max()),
            "n_above_1000": int((sub["lab_value"] >= 1000).sum()),
            "n_above_5000": int((sub["lab_value"] >= 5000).sum()),
            "state": state,
            "turb_source": sub["turb_source"].iloc[0],
        })

    split_df = pd.DataFrame(split_rows).sort_values("suggested_role")
    split_csv = DATA_DIR / "raw" / "extreme_ssc_hotspots" / "extreme_sites_split.csv"
    split_df.to_csv(split_csv, index=False)
    logger.info(f"Saved split: {split_csv}")

    # ── Summary ──
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total samples: {len(dataset)}")
    logger.info(f"  Continuous (19 extreme sites): {(dataset['turb_source']=='continuous').sum()}")
    logger.info(f"  ScienceBase discrete: {(dataset['turb_source']=='sciencebase_discrete').sum()}")
    logger.info(f"Sites: {dataset['site_id'].nunique()}")
    logger.info(f"  Training: {(dataset['suggested_role']=='training').sum()} samples, {dataset[dataset.suggested_role=='training']['site_id'].nunique()} sites")
    logger.info(f"  Holdout:  {(dataset['suggested_role']=='holdout').sum()} samples, {dataset[dataset.suggested_role=='holdout']['site_id'].nunique()} sites")
    logger.info(f"  Vault:    {(dataset['suggested_role']=='vault').sum()} samples, {dataset[dataset.suggested_role=='vault']['site_id'].nunique()} sites")

    n_1000 = (dataset["lab_value"] >= 1000).sum()
    n_5000 = (dataset["lab_value"] >= 5000).sum()
    logger.info(f"SSC >= 1000 mg/L: {n_1000} samples ({100*n_1000/len(dataset):.1f}%)")
    logger.info(f"SSC >= 5000 mg/L: {n_5000} samples ({100*n_5000/len(dataset):.1f}%)")
    logger.info(f"SSC range: {dataset['lab_value'].min():.0f} - {dataset['lab_value'].max():.0f} mg/L")

    # Existing dataset comparison
    existing_path = DATA_DIR / "processed" / "turbidity_ssc_paired.parquet"
    if existing_path.exists():
        existing = pd.read_parquet(existing_path)
        logger.info(f"\nExisting dataset (turbidity_ssc_paired): {len(existing)} samples")
        logger.info(f"  New extreme pairs represent +{len(dataset)}/{len(existing)+len(dataset)} = {100*len(dataset)/(len(existing)+len(dataset)):.1f}% of combined pool")
        n_existing_1000 = (existing["lab_value"] >= 1000).sum()
        logger.info(f"  Existing samples >= 1000 mg/L: {n_existing_1000} ({100*n_existing_1000/len(existing):.1f}%)")
        logger.info(f"  New samples >= 1000 mg/L:      {n_1000} ({100*n_1000/len(dataset):.1f}%)")

    logger.info("\nPer-site breakdown:")
    for _, row in split_df.sort_values("n_samples", ascending=False).iterrows():
        logger.info(
            f"  {row.site_id} [{row.state}] [{row.suggested_role}]: "
            f"{row.n_samples} samples, max={row.max_ssc:.0f}, "
            f"n>=1000={row.n_above_1000}, n>=5000={row.n_above_5000}, "
            f"source={row.turb_source}"
        )

    logger.info(f"\nColumns in output: {list(dataset.columns)}")
    logger.info("Done.")


if __name__ == "__main__":
    main()
