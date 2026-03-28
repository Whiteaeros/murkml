"""Fast gap-fill download using direct RDB requests + 8 concurrent workers.

Based on Gemini's advice: one site per request, RDB format (70% smaller),
8 workers to saturate the 120 req/min rate limit, exponential backoff on errors.

Usage:
    python scripts/download_gap_fill_fast.py
"""

import io
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Thread-safe progress tracking
_lock = Lock()
_stats = {"calls": 0, "rows": 0, "skipped": 0, "errors": 0}


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
            skip_next = True  # Next line is the format descriptor
            continue
        if skip_next:
            skip_next = False
            continue
        parts = line.strip().split("\t")
        # Pad or truncate to match header length
        if len(parts) < len(header):
            parts.extend([""] * (len(header) - len(parts)))
        elif len(parts) > len(header):
            parts = parts[:len(header)]
        lines.append(parts)

    if not header or not lines:
        return pd.DataFrame()

    df = pd.DataFrame(lines, columns=header)
    return df


def fetch_site_chunk(site_no: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Download one site's turbidity for a date range via RDB format."""
    url = (
        f"https://waterservices.usgs.gov/nwis/iv/"
        f"?format=rdb&sites={site_no}&parameterCd=63680"
        f"&startDT={start_date}&endDT={end_date}"
    )

    for attempt in range(4):
        try:
            resp = requests.get(url, timeout=90)
            if resp.status_code == 200:
                df = parse_rdb(resp.text)
                if df.empty:
                    return pd.DataFrame()

                # Find the turbidity value column (contains "63680" in name)
                turb_col = None
                qual_col = None
                for col in df.columns:
                    if "63680" in col and "_cd" not in col:
                        turb_col = col
                    elif "63680" in col and "_cd" in col:
                        qual_col = col

                if turb_col is None:
                    return pd.DataFrame()

                # Build output in expected format
                out = pd.DataFrame()
                out["time"] = pd.to_datetime(df["datetime"], errors="coerce", utc=True)
                out["value"] = pd.to_numeric(df[turb_col], errors="coerce")

                # Parse approval status AND qualifier from RDB _cd column
                # RDB codes are compound: "A" (approved), "A e" (approved+estimated),
                # "P Ice" (provisional+ice), "A [4]" (approved+remark)
                if qual_col and qual_col in df.columns:
                    raw_cd = df[qual_col].fillna("")

                    def _parse_cd(val):
                        s = str(val).strip()
                        if not s:
                            return "Unknown", None
                        # First character is approval: A=Approved, P=Provisional
                        approval = "Approved" if s[0] == "A" else "Provisional" if s[0] == "P" else "Unknown"
                        # Everything after the first token is the qualifier
                        parts = s.split(None, 1)
                        qualifier = parts[1] if len(parts) > 1 else None
                        return approval, qualifier

                    parsed = raw_cd.apply(_parse_cd)
                    out["approval_status"] = parsed.apply(lambda x: x[0])
                    out["qualifier"] = parsed.apply(lambda x: x[1])
                else:
                    out["approval_status"] = "Unknown"
                    out["qualifier"] = None

                out = out.dropna(subset=["time", "value"])
                return out

            elif resp.status_code == 429:
                time.sleep(10 * (attempt + 1))
            else:
                time.sleep(5)
        except requests.exceptions.RequestException:
            time.sleep(5 * (attempt + 1))

    return pd.DataFrame()  # Failed after retries


def process_site(site_no: str, gaps: list[tuple[int, int]], output_dir: Path) -> int:
    """Download all gap chunks for one site. Returns total rows saved."""
    site_id = f"USGS_{site_no}"
    site_dir = output_dir / site_id / "63680"
    site_dir.mkdir(parents=True, exist_ok=True)
    total_rows = 0

    for yr_start, yr_end in gaps:
        out_file = site_dir / f"gap_fill_{yr_start}_{yr_end}.parquet"
        if out_file.exists() and out_file.stat().st_size > 0:
            with _lock:
                _stats["skipped"] += 1
            continue

        start_date = f"{yr_start}-01-01"
        end_date = f"{yr_end}-12-31"
        df = fetch_site_chunk(site_no, start_date, end_date)

        with _lock:
            _stats["calls"] += 1

        if not df.empty:
            df.to_parquet(out_file, index=False)
            total_rows += len(df)
        else:
            # Write empty file to mark as attempted
            pd.DataFrame(columns=["time", "value", "approval_status", "qualifier"]).to_parquet(out_file, index=False)

    return total_rows


def main():
    # Load gap analysis
    gaps_df = pd.read_parquet(DATA_DIR / "download_gaps.parquet")

    # Build per-site download plan from gap analysis
    # For each site, determine what year ranges to download
    site_plans = {}
    for _, row in gaps_df.iterrows():
        site_id = row["site_id"]
        site_no = site_id.replace("USGS-", "")

        outside = row.get("ssc_outside_turb", 0)
        if pd.isna(outside) or outside <= 0:
            continue

        dl_start = row.get("download_start_year")
        dl_end = row.get("download_end_year")
        turb_start = row.get("turb_start")
        turb_end = row.get("turb_end")

        if pd.isna(dl_start) or pd.isna(dl_end):
            continue

        dl_start = int(dl_start)
        dl_end = int(dl_end)

        # Parse existing turbidity year range
        try:
            turb_yr_start = pd.Timestamp(turb_start).year if pd.notna(turb_start) else None
            turb_yr_end = pd.Timestamp(turb_end).year if pd.notna(turb_end) else None
        except Exception:
            turb_yr_start = turb_yr_end = None

        # Generate 2-year chunks, skipping years already covered
        chunks = []
        for yr in range(dl_start, dl_end + 1, 2):
            yr_end = min(yr + 1, dl_end)
            if turb_yr_start and turb_yr_end:
                if yr >= turb_yr_start and yr_end <= turb_yr_end:
                    continue
            chunks.append((yr, yr_end))

        if chunks:
            site_plans[site_no] = chunks

    total_chunks = sum(len(v) for v in site_plans.values())
    logger.info(f"Download plan: {len(site_plans)} sites, {total_chunks} chunks, 8 workers")

    t0 = time.time()

    # Process sites in parallel (8 workers, one site at a time per Gemini's advice)
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(process_site, site_no, chunks, DATA_DIR / "continuous"): site_no
            for site_no, chunks in site_plans.items()
        }

        done = 0
        for future in as_completed(futures):
            site_no = futures[future]
            try:
                rows = future.result()
                done += 1
                if done % 20 == 0:
                    elapsed = time.time() - t0
                    logger.info(
                        f"  [{done}/{len(site_plans)}] {_stats['calls']} calls, "
                        f"{_stats['rows'] + rows:,} rows, {_stats['skipped']} skipped, "
                        f"{elapsed/60:.1f} min"
                    )
                with _lock:
                    _stats["rows"] += rows
            except Exception as e:
                with _lock:
                    _stats["errors"] += 1
                logger.error(f"  Site {site_no} failed: {e}")

    elapsed = time.time() - t0
    logger.info(f"\nDone in {elapsed/60:.1f} min")
    logger.info(f"  {_stats['rows']:,} rows saved")
    logger.info(f"  {_stats['calls']} API calls, {_stats['skipped']} skipped, {_stats['errors']} errors")


if __name__ == "__main__":
    main()
