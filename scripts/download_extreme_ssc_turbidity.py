"""Download continuous FNU turbidity (pCode 63680) for top extreme-SSC sites.

Sites are from data/raw/extreme_ssc_hotspots/site_summary.csv — top 20 by
n_extreme, focusing on NEW sites not already in data/continuous/.

Key decisions:
- RDB format (70% smaller than JSON)
- 2-year chunks to avoid timeouts
- 2-second rate-limit delay between requests (sequential, not parallel,
  to stay safe on a focused list of 20 sites)
- Per-request file cache under data/raw/extreme_ssc_hotspots/_cache/
- Skip sites that already have 63680 data in data/continuous/
- Resume-safe: skips chunks that already have parquet files on disk

Output:
  data/continuous/USGS_{site_id}/63680/{yr_start}_{yr_end}.parquet
  data/raw/extreme_ssc_hotspots/download_log.csv
"""

import csv
import hashlib
import logging
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SITE_SUMMARY = PROJECT_ROOT / "data" / "raw" / "extreme_ssc_hotspots" / "site_summary.csv"
CONTINUOUS_DIR = PROJECT_ROOT / "data" / "continuous"
CACHE_DIR = PROJECT_ROOT / "data" / "raw" / "extreme_ssc_hotspots" / "_cache"
LOG_PATH = PROJECT_ROOT / "data" / "raw" / "extreme_ssc_hotspots" / "download_log.csv"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
CONTINUOUS_DIR.mkdir(parents=True, exist_ok=True)

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
# Parameters
# ---------------------------------------------------------------------------
PCODE = "63680"
TOP_N = 20
RATE_LIMIT_SEC = 2          # seconds between HTTP requests
CHUNK_YEARS = 2             # year span per request
CURRENT_YEAR = datetime.now().year
RECORD_START_YEAR = 1990    # don't bother before sensors existed


def _cache_path(url: str) -> Path:
    key = hashlib.md5(url.encode()).hexdigest()
    return CACHE_DIR / f"{key}.txt"


def fetch_rdb(url: str) -> str | None:
    """Fetch URL, using local cache. Returns text or None on failure."""
    cp = _cache_path(url)
    if cp.exists() and cp.stat().st_size > 0:
        return cp.read_text(encoding="utf-8")

    for attempt in range(4):
        try:
            resp = requests.get(url, timeout=90)
            if resp.status_code == 200:
                cp.write_text(resp.text, encoding="utf-8")
                return resp.text
            elif resp.status_code == 404:
                # No data — cache empty sentinel so we don't retry
                cp.write_text("", encoding="utf-8")
                return None
            elif resp.status_code == 429:
                wait = 15 * (attempt + 1)
                logger.warning(f"Rate limited (429), sleeping {wait}s")
                time.sleep(wait)
            else:
                logger.warning(f"HTTP {resp.status_code} for {url}")
                time.sleep(5)
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request error attempt {attempt+1}: {e}")
            time.sleep(5 * (attempt + 1))
    return None


def parse_rdb(text: str) -> pd.DataFrame:
    """Parse USGS RDB tab-delimited response into DataFrame."""
    lines = []
    header = None
    skip_next = False
    for line in text.split("\n"):
        if line.startswith("#") or not line.strip():
            continue
        if header is None:
            header = line.strip().split("\t")
            skip_next = True
            continue
        if skip_next:
            skip_next = False
            continue
        parts = line.strip().split("\t")
        if len(parts) < len(header):
            parts.extend([""] * (len(header) - len(parts)))
        elif len(parts) > len(header):
            parts = parts[: len(header)]
        lines.append(parts)

    if not header or not lines:
        return pd.DataFrame()

    return pd.DataFrame(lines, columns=header)


def _parse_cd(val: str) -> tuple[str, str | None]:
    s = str(val).strip()
    if not s:
        return "Unknown", None
    approval = "Approved" if s[0] == "A" else "Provisional" if s[0] == "P" else "Unknown"
    parts = s.split(None, 1)
    qualifier = parts[1] if len(parts) > 1 else None
    return approval, qualifier


def fetch_chunk(site_no: str, yr_start: int, yr_end: int) -> pd.DataFrame:
    """Download one 2-year chunk of turbidity for a site. Returns tidy DataFrame."""
    url = (
        f"https://waterservices.usgs.gov/nwis/iv/"
        f"?format=rdb&sites={site_no}&parameterCd={PCODE}"
        f"&startDT={yr_start}-01-01&endDT={yr_end}-12-31"
    )
    text = fetch_rdb(url)
    if not text or not text.strip():
        return pd.DataFrame()

    raw = parse_rdb(text)
    if raw.empty:
        return pd.DataFrame()

    # Identify turbidity value column and qualifier column
    turb_col = None
    qual_col = None
    for col in raw.columns:
        if PCODE in col and "_cd" not in col:
            turb_col = col
        elif PCODE in col and "_cd" in col:
            qual_col = col

    if turb_col is None:
        return pd.DataFrame()

    out = pd.DataFrame()
    out["time"] = pd.to_datetime(raw["datetime"], errors="coerce", utc=True)
    out["value"] = pd.to_numeric(raw[turb_col], errors="coerce")

    if qual_col and qual_col in raw.columns:
        parsed = raw[qual_col].fillna("").apply(_parse_cd)
        out["approval_status"] = parsed.apply(lambda x: x[0])
        out["qualifier"] = parsed.apply(lambda x: x[1])
    else:
        out["approval_status"] = "Unknown"
        out["qualifier"] = None

    out = out.dropna(subset=["time", "value"])
    return out


def site_has_data(site_no: str) -> bool:
    """Return True if any 63680 parquets already exist for this site."""
    site_dir = CONTINUOUS_DIR / f"USGS_{site_no}" / PCODE
    if not site_dir.exists():
        return False
    parquets = list(site_dir.glob("*.parquet"))
    # A site "has data" if there's at least one non-trivial parquet
    return any(p.stat().st_size > 200 for p in parquets)


def get_period_of_record(site_no: str) -> tuple[int, int]:
    """Query USGS site service for the period of record for pcode 63680.
    Falls back to (RECORD_START_YEAR, CURRENT_YEAR) if unavailable.
    """
    url = (
        f"https://waterservices.usgs.gov/nwis/site/"
        f"?format=rdb&sites={site_no}&seriesCatalogOutput=true"
        f"&parameterCd={PCODE}&outputDataTypeCd=iv"
    )
    text = fetch_rdb(url)
    if not text:
        return RECORD_START_YEAR, CURRENT_YEAR

    for line in text.split("\n"):
        if line.startswith("#") or not line.strip():
            continue
        # Header lines, skip 2 (header + format)
        pass

    # Parse the RDB properly
    raw = parse_rdb(text)
    if raw.empty:
        return RECORD_START_YEAR, CURRENT_YEAR

    # Look for begin_date / end_date columns
    begin_col = next((c for c in raw.columns if "begin" in c.lower()), None)
    end_col = next((c for c in raw.columns if "end" in c.lower()), None)

    if begin_col and end_col and len(raw) > 0:
        try:
            begin_yr = pd.to_datetime(raw[begin_col].iloc[0], errors="coerce").year
            end_yr = pd.to_datetime(raw[end_col].iloc[0], errors="coerce").year
            if pd.notna(begin_yr) and pd.notna(end_yr):
                return max(int(begin_yr), RECORD_START_YEAR), min(int(end_yr) + 1, CURRENT_YEAR + 1)
        except Exception:
            pass

    return RECORD_START_YEAR, CURRENT_YEAR


def download_site(site_no: str) -> dict:
    """Download all turbidity chunks for one site. Returns stats dict."""
    logger.info(f"  Starting {site_no} — querying period of record...")
    time.sleep(RATE_LIMIT_SEC)

    por_start, por_end = get_period_of_record(site_no)
    logger.info(f"  {site_no}: period {por_start}–{por_end}")

    site_dir = CONTINUOUS_DIR / f"USGS_{site_no}" / PCODE
    site_dir.mkdir(parents=True, exist_ok=True)

    total_rows = 0
    chunks_downloaded = 0
    chunks_skipped = 0
    chunks_empty = 0

    for yr in range(por_start, por_end + 1, CHUNK_YEARS):
        yr_end = min(yr + CHUNK_YEARS - 1, por_end)
        out_file = site_dir / f"{yr}_{yr_end}.parquet"

        if out_file.exists() and out_file.stat().st_size > 200:
            chunks_skipped += 1
            continue

        time.sleep(RATE_LIMIT_SEC)
        df = fetch_chunk(site_no, yr, yr_end)

        if not df.empty:
            df.to_parquet(out_file, index=False)
            total_rows += len(df)
            chunks_downloaded += 1
            logger.info(f"    {site_no} {yr}-{yr_end}: {len(df):,} rows")
        else:
            # Write empty sentinel so we don't re-attempt
            pd.DataFrame(
                columns=["time", "value", "approval_status", "qualifier"]
            ).to_parquet(out_file, index=False)
            chunks_empty += 1
            logger.info(f"    {site_no} {yr}-{yr_end}: no data")

    return {
        "site_no": site_no,
        "por_start": por_start,
        "por_end": por_end,
        "total_rows": total_rows,
        "chunks_downloaded": chunks_downloaded,
        "chunks_skipped": chunks_skipped,
        "chunks_empty": chunks_empty,
        "status": "ok" if (total_rows > 0 or chunks_skipped > 0) else "no_data",
    }


def main():
    # -----------------------------------------------------------------------
    # Load site list and select top 20 new sites
    # -----------------------------------------------------------------------
    summary = pd.read_csv(SITE_SUMMARY)

    # Sort by n_extreme descending
    summary = summary.sort_values("n_extreme", ascending=False).reset_index(drop=True)

    # Extract numeric site_no from USGS-XXXXXX format
    summary["site_no"] = summary["site_id"].str.replace("USGS-", "", regex=False)

    # Select top 20 NEW sites (is_new_site==True preferred, but take top 20 by count regardless)
    # Per instructions: "focusing on NEW sites not already in our dataset"
    # "Already in dataset" means existing 63680 parquets exist
    summary["has_data"] = summary["site_no"].apply(site_has_data)
    new_sites = summary[~summary["has_data"]].head(TOP_N)

    if new_sites.empty:
        logger.warning("All top sites already have data — nothing to download.")
        return

    logger.info(f"Downloading turbidity for {len(new_sites)} new sites:")
    for _, row in new_sites.iterrows():
        logger.info(f"  {row['site_no']} — {row['n_extreme']} extreme samples, max SSC {row['max_ssc']}")

    # -----------------------------------------------------------------------
    # Download
    # -----------------------------------------------------------------------
    log_rows = []
    total_records = 0
    success_count = 0
    fail_count = 0

    for i, (_, row) in enumerate(new_sites.iterrows(), 1):
        site_no = row["site_no"]
        logger.info(f"\n[{i}/{len(new_sites)}] {site_no}")

        try:
            stats = download_site(site_no)
            log_rows.append({
                "site_no": site_no,
                "state": row.get("state", ""),
                "n_extreme": row["n_extreme"],
                "max_ssc": row["max_ssc"],
                "por_start": stats["por_start"],
                "por_end": stats["por_end"],
                "total_rows": stats["total_rows"],
                "chunks_downloaded": stats["chunks_downloaded"],
                "chunks_skipped": stats["chunks_skipped"],
                "chunks_empty": stats["chunks_empty"],
                "status": stats["status"],
                "downloaded_at": datetime.utcnow().isoformat(),
            })
            total_records += stats["total_rows"]
            if stats["status"] == "ok":
                success_count += 1
            else:
                fail_count += 1
        except Exception as e:
            logger.error(f"  FAILED {site_no}: {e}")
            log_rows.append({
                "site_no": site_no,
                "state": row.get("state", ""),
                "n_extreme": row["n_extreme"],
                "max_ssc": row["max_ssc"],
                "status": "error",
                "error": str(e),
                "downloaded_at": datetime.utcnow().isoformat(),
            })
            fail_count += 1

    # -----------------------------------------------------------------------
    # Save download log
    # -----------------------------------------------------------------------
    log_df = pd.DataFrame(log_rows)
    log_df.to_csv(LOG_PATH, index=False)
    logger.info(f"\nDownload log saved to {LOG_PATH}")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    logger.info("\n" + "=" * 60)
    logger.info("DOWNLOAD COMPLETE")
    logger.info(f"  Sites attempted:    {len(new_sites)}")
    logger.info(f"  Sites with data:    {success_count}")
    logger.info(f"  Sites no data:      {fail_count}")
    logger.info(f"  Total rows saved:   {total_records:,}")
    logger.info("=" * 60)

    # Print per-site summary
    print("\nPer-site results:")
    print(f"{'site_no':<25} {'rows':>10} {'status'}")
    print("-" * 50)
    for r in log_rows:
        rows = r.get("total_rows", 0) or 0
        print(f"{r['site_no']:<25} {rows:>10,}   {r['status']}")


if __name__ == "__main__":
    main()
