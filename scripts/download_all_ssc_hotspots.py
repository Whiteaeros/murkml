"""Download ALL discrete SSC samples (pCode 80154) for the 19 extreme-SSC hotspot sites.

These are the sites where we already have continuous FNU turbidity in
data/continuous/USGS_{site_id}/63680/. The earlier pipeline only grabbed
samples >1000 mg/L. This script fetches the full distribution — baseflow,
moderate, and extreme — so the model sees complete site behavior.

Site IDs come from data/raw/extreme_ssc_hotspots/site_summary.csv
(format: USGS-XXXXXXXX), cross-referenced against download_log.csv to
confirm turbidity was downloaded (status == ok).

Output:
  data/raw/extreme_ssc_hotspots/all_ssc_samples.parquet
    columns: site_id, datetime, ssc_mg_L, activity_id, collection_method,
             medium, detection_condition, detection_limit, units
  data/raw/extreme_ssc_hotspots/all_ssc_samples_report.csv  (per-site summary)
  Per-site cache in data/raw/extreme_ssc_hotspots/_cache/all_ssc_{site_key}.parquet

Rate limit: 2-second delay between API calls.
Resume-safe: per-site cache skips completed sites.

Column mapping from waterdata.get_samples() fullphyschem profile:
  datetime  <- Activity_StartDate + Activity_StartTime + Activity_StartTimeZone
  ssc_mg_L  <- Result_Measure (filtered to USGSpcode == '80154')
  units     <- Result_MeasureUnit
  activity_id   <- Activity_ActivityIdentifier
  collection_method <- SampleCollectionMethod_Identifier
  medium    <- Activity_Media
  detection_condition <- Result_ResultDetectionCondition
  detection_limit <- DetectionLimit_MeasureA
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd
from dataretrieval import waterdata

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
HOTSPOT_DIR = PROJECT_ROOT / "data" / "raw" / "extreme_ssc_hotspots"
SITE_SUMMARY = HOTSPOT_DIR / "site_summary.csv"
CONTINUOUS_DIR = PROJECT_ROOT / "data" / "continuous"
CACHE_DIR = HOTSPOT_DIR / "_cache"
LOG_CSV = HOTSPOT_DIR / "download_log.csv"
OUTPUT_PARQUET = HOTSPOT_DIR / "all_ssc_samples.parquet"
OUTPUT_REPORT = HOTSPOT_DIR / "all_ssc_samples_report.csv"

CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RATE_LIMIT_SEC = 2
PCODE_SSC = "80154"
MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# Site list helpers
# ---------------------------------------------------------------------------
def _site_key(site_id: str) -> str:
    """Convert 'USGS-09315000' -> '09315000' for use as a cache key."""
    return site_id.replace("USGS-", "")


def get_hotspot_sites() -> list[str]:
    """Return USGS-XXXXXXXX site_id list for sites that had turbidity downloaded.

    Cross-references site_summary.csv (which has proper zero-padded IDs) with
    download_log.csv to confirm status == ok and turbidity data was retrieved.
    """
    # download_log has bare integers (no leading zeros, no USGS- prefix)
    log = pd.read_csv(LOG_CSV)
    ok_log = log[log["status"] == "ok"]["site_no"].astype(str).tolist()

    # site_summary has USGS-XXXXXXXX format
    summary = pd.read_csv(SITE_SUMMARY)

    # Build a lookup: numeric core -> full site_id
    # For standard 8-digit sites: '9315000' -> '09315000' (zero-pad to 8)
    # For long IDs (391953108130201): match as-is
    def pad_or_keep(s: str) -> str:
        return s.zfill(8) if len(s) <= 8 else s

    ok_padded = {pad_or_keep(s) for s in ok_log}

    # site_summary site_id = 'USGS-XXXXXXXX'
    result = []
    for _, row in summary.iterrows():
        full_id = row["site_id"]  # e.g. 'USGS-09315000'
        numeric = full_id.replace("USGS-", "")
        if numeric in ok_padded:
            result.append(full_id)

    logger.info(f"Found {len(result)} matching sites in site_summary with ok turbidity download")
    for s in result:
        logger.info(f"  {s}")
    return result


# ---------------------------------------------------------------------------
# Continuous data date range helper
# ---------------------------------------------------------------------------
def get_continuous_period(site_id: str) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """Return (min_ts, max_ts) from the continuous 63680 parquet files for this site.

    The continuous parquets from download_extreme_ssc_turbidity.py use a 'time'
    column (not 'datetime'). Fall back to 'datetime' or the index for older files.
    """
    # continuous dir uses underscores: USGS_09315000
    dir_name = site_id.replace("-", "_")
    cont_dir = CONTINUOUS_DIR / dir_name / "63680"
    if not cont_dir.exists():
        return None, None

    all_min, all_max = [], []
    for f in cont_dir.glob("*.parquet"):
        try:
            df = pd.read_parquet(f)
            if len(df) == 0:
                continue
            # Try 'time' first (format used by download_extreme_ssc_turbidity.py),
            # then 'datetime', then the index
            for col in ("time", "datetime"):
                if col in df.columns:
                    ts = pd.to_datetime(df[col], utc=True, errors="coerce").dropna()
                    if len(ts) > 0:
                        all_min.append(ts.min())
                        all_max.append(ts.max())
                    break
            else:
                ts = pd.to_datetime(df.index, utc=True, errors="coerce")
                ts = ts[ts.notna()]
                if len(ts) > 0:
                    all_min.append(ts.min())
                    all_max.append(ts.max())
        except Exception:
            pass

    if not all_min:
        return None, None
    return min(all_min), max(all_max)


# ---------------------------------------------------------------------------
# Discrete SSC fetcher with cache
# ---------------------------------------------------------------------------
def fetch_all_ssc(site_id: str) -> pd.DataFrame:
    """Fetch all discrete SSC samples for one site. Cache result as parquet.

    Cache key uses the numeric part of the site_id (e.g. '09315000').
    Returns raw DataFrame from API, or empty DataFrame on failure.
    """
    key = _site_key(site_id)
    cache_file = CACHE_DIR / f"all_ssc_{key}.parquet"

    if cache_file.exists():
        df = pd.read_parquet(cache_file)
        logger.info(f"  [cache] {site_id}: {len(df)} rows")
        return df

    logger.info(f"  Querying {site_id} ...")

    for attempt in range(MAX_RETRIES):
        try:
            df, _meta = waterdata.get_samples(
                monitoringLocationIdentifier=site_id,
                usgsPCode=PCODE_SSC,
                activityMediaName="Water",
            )
            if df is None or len(df) == 0:
                logger.info(f"  {site_id}: API returned no samples")
                pd.DataFrame().to_parquet(cache_file)
                return pd.DataFrame()

            logger.info(f"  {site_id}: {len(df)} raw rows")
            df.to_parquet(cache_file)
            return df

        except Exception as exc:
            wait = 2 ** attempt * 10  # 10s, 20s, 40s
            msg = str(exc)
            if "429" in msg:
                logger.warning(f"  Rate-limited on {site_id}, retry {attempt+1}/{MAX_RETRIES} in {wait}s")
                time.sleep(wait)
            else:
                logger.error(f"  Error fetching {site_id} (attempt {attempt+1}): {exc}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(5)
                else:
                    return pd.DataFrame()

    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Column normalisation
# ---------------------------------------------------------------------------
def normalise(df: pd.DataFrame, site_id: str) -> pd.DataFrame:
    """Extract and rename columns from fullphyschem profile to standard schema.

    Column mapping (fullphyschem profile from waterdata.get_samples):
      Activity_StartDate       + Activity_StartTime + Activity_StartTimeZone -> datetime
      Result_Measure                                                          -> ssc_mg_L
      Result_MeasureUnit                                                      -> units
      Activity_ActivityIdentifier                                             -> activity_id
      SampleCollectionMethod_Identifier                                       -> collection_method
      Activity_Media                                                          -> medium
      Result_ResultDetectionCondition                                         -> detection_condition
      DetectionLimit_MeasureA                                                 -> detection_limit
    """
    if df is None or len(df) == 0:
        return pd.DataFrame()

    cols = df.columns.tolist()

    # --- Build datetime ---
    if "Activity_StartDate" in cols:
        date_str = df["Activity_StartDate"].astype(str)
        if "Activity_StartTime" in cols:
            time_str = df["Activity_StartTime"].fillna("00:00:00").astype(str)
            combined = date_str + " " + time_str
        else:
            combined = date_str

        if "Activity_StartTimeZone" in cols:
            tz_str = df["Activity_StartTimeZone"].fillna("UTC").astype(str)
            # Most USGS samples are MST/MDT/PST/CDT — coerce to UTC
            # pd.to_datetime with utc=True handles ISO8601 tz-aware strings;
            # for bare dates we force UTC after parsing
            dt = pd.to_datetime(combined, errors="coerce")
            # Attempt tz conversion where timezone codes are present
            # Simple approach: parse without tz, flag as UTC (USGS reports are in local time
            # but we don't need sub-day precision for discrete samples)
            dt = dt.dt.tz_localize("UTC", ambiguous="NaT", nonexistent="NaT")
        else:
            dt = pd.to_datetime(combined, errors="coerce").dt.tz_localize("UTC", ambiguous="NaT", nonexistent="NaT")
    else:
        logger.warning(f"  {site_id}: no Activity_StartDate column — skipping")
        return pd.DataFrame()

    # --- SSC value ---
    if "Result_Measure" not in cols:
        logger.warning(f"  {site_id}: no Result_Measure column — skipping")
        return pd.DataFrame()
    ssc = pd.to_numeric(df["Result_Measure"], errors="coerce")

    # --- Assemble ---
    out = pd.DataFrame({
        "site_id": site_id,
        "datetime": dt,
        "ssc_mg_L": ssc,
    })

    # Optional metadata
    for out_col, src_col in [
        ("activity_id", "Activity_ActivityIdentifier"),
        ("collection_method", "SampleCollectionMethod_Identifier"),
        ("medium", "Activity_Media"),
        ("detection_condition", "Result_ResultDetectionCondition"),
        ("detection_limit", "DetectionLimit_MeasureA"),
        ("units", "Result_MeasureUnit"),
    ]:
        out[out_col] = df[src_col].values if src_col in cols else None

    # Drop rows with no value or no timestamp
    before = len(out)
    out = out.dropna(subset=["datetime", "ssc_mg_L"]).reset_index(drop=True)
    if before - len(out) > 0:
        logger.debug(f"  {site_id}: dropped {before - len(out)} rows with null datetime or SSC")

    return out


# ---------------------------------------------------------------------------
# Overlap counter
# ---------------------------------------------------------------------------
def count_overlap(norm_df: pd.DataFrame, site_id: str) -> int:
    """Count how many discrete SSC samples fall within the continuous FNU window."""
    t_min, t_max = get_continuous_period(site_id)
    if t_min is None or len(norm_df) == 0:
        return 0
    dt = norm_df["datetime"]
    return int(((dt >= t_min) & (dt <= t_max)).sum())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    logger.info("=== Download ALL discrete SSC for extreme-SSC hotspot sites ===")

    sites = get_hotspot_sites()
    if not sites:
        logger.error("No sites found — check site_summary.csv and download_log.csv")
        return

    all_frames: list[pd.DataFrame] = []
    report_rows: list[dict] = []

    for i, site_id in enumerate(sites):
        logger.info(f"\n[{i+1}/{len(sites)}] {site_id}")

        raw_df = fetch_all_ssc(site_id)
        time.sleep(RATE_LIMIT_SEC)

        norm_df = normalise(raw_df, site_id)

        if len(norm_df) == 0:
            logger.info(f"  {site_id}: 0 usable samples after normalisation")
            report_rows.append({
                "site_id": site_id,
                "n_total": 0,
                "ssc_min": None,
                "ssc_max": None,
                "ssc_median": None,
                "n_overlap_with_turbidity": 0,
            })
            continue

        all_frames.append(norm_df)

        n = len(norm_df)
        ssc_min = norm_df["ssc_mg_L"].min()
        ssc_max = norm_df["ssc_mg_L"].max()
        ssc_med = norm_df["ssc_mg_L"].median()
        n_overlap = count_overlap(norm_df, site_id)

        logger.info(
            f"  {site_id}: {n} samples  "
            f"SSC [{ssc_min:.0f}, {ssc_max:.0f}] mg/L  "
            f"median={ssc_med:.0f}  "
            f"overlap_with_turbidity={n_overlap}"
        )

        report_rows.append({
            "site_id": site_id,
            "n_total": n,
            "ssc_min": ssc_min,
            "ssc_max": ssc_max,
            "ssc_median": ssc_med,
            "n_overlap_with_turbidity": n_overlap,
        })

    # -----------------------------------------------------------------------
    # Save combined parquet
    # -----------------------------------------------------------------------
    if not all_frames:
        logger.error("No usable samples from any site — output not written")
        report_df = pd.DataFrame(report_rows)
        report_df.to_csv(OUTPUT_REPORT, index=False)
        logger.info(f"Report saved to {OUTPUT_REPORT}")
        return

    combined = pd.concat(all_frames, ignore_index=True)
    combined.to_parquet(OUTPUT_PARQUET, index=False)
    logger.info(f"\nSaved {len(combined)} total rows -> {OUTPUT_PARQUET}")

    # -----------------------------------------------------------------------
    # Print per-site summary
    # -----------------------------------------------------------------------
    report_df = pd.DataFrame(report_rows)
    report_df.to_csv(OUTPUT_REPORT, index=False)
    logger.info(f"Report saved to {OUTPUT_REPORT}")

    logger.info("\n=== Per-site summary ===")
    for _, row in report_df.iterrows():
        if row["n_total"] == 0:
            logger.info(f"  {row['site_id']:30s}  n=0")
        else:
            logger.info(
                f"  {row['site_id']:30s}  "
                f"n={int(row['n_total']):5d}  "
                f"SSC=[{row['ssc_min']:.0f},{row['ssc_max']:.0f}]  "
                f"median={row['ssc_median']:.0f}  "
                f"overlap={int(row['n_overlap_with_turbidity'])}"
            )

    n_with_data = (report_df["n_total"] > 0).sum()
    n_with_overlap = (report_df["n_overlap_with_turbidity"] > 0).sum()
    logger.info(f"\nTotal samples: {len(combined)}")
    logger.info(f"Sites with SSC data: {n_with_data}/{len(sites)}")
    logger.info(f"Sites with turbidity overlap: {n_with_overlap}/{len(sites)}")


if __name__ == "__main__":
    main()
