"""Find USGS sites with extreme SSC (>1000 mg/L) paired with continuous FNU turbidity.

Strategy:
  1. Query NWIS qw (water quality) for discrete SSC samples (pCode 80154) by state
  2. Filter for samples >1000 mg/L
  3. Check which sites also have continuous FNU (pCode 63680) via site service
  4. Exclude sites already in our dataset (unless they have more extreme samples)
  5. Download site metadata and save results

Uses RDB format for all bulk queries per project convention.
"""

import io
import json
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "raw" / "extreme_ssc_hotspots"
CACHE_DIR = OUTPUT_DIR / "_cache"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Target states grouped by hydrologic regime
STATE_GROUPS = {
    "Pacific NW rain-on-snow": ["WA", "ID", "MT", "OR"],
    "Loess/Missouri basin": ["MO", "IA", "NE", "KS"],
    "Desert flash floods": ["AZ", "NM", "UT", "CO"],
    "Gulf Coast hurricanes": ["LA", "TX", "MS"],
    # Bonus: known high-SSC regions
    "Northern Plains": ["ND", "SD", "WY", "MN"],
    "Appalachian/Mid-Atlantic": ["PA", "WV", "VA", "NC"],
}

ALL_STATES = []
for states in STATE_GROUPS.values():
    ALL_STATES.extend(states)


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


def fetch_with_retry(url: str, timeout: int = 120, max_retries: int = 3) -> str | None:
    """Fetch URL with retry and backoff. Returns response text or None."""
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code == 429:
                wait = 15 * (attempt + 1)
                log.warning(f"Rate limited, waiting {wait}s...")
                time.sleep(wait)
            elif resp.status_code == 400:
                log.warning(f"Bad request (400) for URL (truncated): ...{url[-80:]}")
                return None
            else:
                log.warning(f"HTTP {resp.status_code} for {url[:100]}..., retry {attempt+1}")
                time.sleep(5 * (attempt + 1))
        except requests.exceptions.RequestException as e:
            log.warning(f"Request error: {e}, retry {attempt+1}")
            time.sleep(5 * (attempt + 1))
    return None


# ── Step 1: Find sites with discrete SSC samples ──────────────────────────

def discover_ssc_sites_by_state(state: str) -> pd.DataFrame:
    """Query NWIS water quality results for SSC (80154) in a state.

    Uses the NWIS qw results endpoint in RDB format.
    Returns DataFrame with site_no, sample_dt, result_va (SSC value).
    """
    cache_file = CACHE_DIR / f"ssc_results_{state}.parquet"
    if cache_file.exists():
        log.info(f"  [cache hit] {state} SSC results")
        return pd.read_parquet(cache_file)

    # Use waterqualitydata.us WQP which is more reliable for bulk qw queries
    # NWIS qwdata endpoint is being retired; WQP is the replacement
    url = (
        f"https://www.waterqualitydata.us/data/Result/search?"
        f"statecode=US%3A{_state_fips(state)}"
        f"&pCode=80154"
        f"&mimeType=csv"
        f"&zip=no"
        f"&dataProfile=narrowResult"
        f"&providers=NWIS"
    )

    log.info(f"  Querying WQP for SSC in {state}...")
    text = fetch_with_retry(url, timeout=180)
    if text is None:
        log.error(f"  Failed to fetch SSC for {state}")
        return pd.DataFrame()

    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, low_memory=False)
    except Exception as e:
        log.error(f"  Parse error for {state}: {e}")
        return pd.DataFrame()

    if df.empty:
        log.info(f"  No SSC results for {state}")
        return pd.DataFrame()

    # Extract what we need
    # WQP narrowResult columns: MonitoringLocationIdentifier, ActivityStartDate,
    # ActivityStartTime/Time, ResultMeasureValue, etc.
    col_map = {}
    for c in df.columns:
        cl = c.lower().replace(" ", "").replace("/", "")
            # Find key columns
        if "monitoringlocationidentifier" in cl:
            col_map["site_id"] = c
        elif "activitystartdate" in cl and "time" not in cl:
            col_map["date"] = c
        elif "activitystarttime" in cl and "time" in cl and "zone" not in cl:
            col_map["time"] = c
        elif "resultmeasurevalue" in cl or ("resultmeasure" in cl and "value" in cl):
            col_map["value"] = c

    if "site_id" not in col_map or "value" not in col_map:
        log.warning(f"  Missing columns for {state}. Available: {list(df.columns)[:10]}")
        return pd.DataFrame()

    out = pd.DataFrame()
    out["site_id"] = df[col_map["site_id"]]
    out["date"] = df.get(col_map.get("date", ""), "")
    out["time"] = df.get(col_map.get("time", ""), "")
    out["ssc_mg_L"] = pd.to_numeric(df[col_map["value"]], errors="coerce")
    out["state"] = state

    # Filter to USGS sites only
    out = out[out["site_id"].str.startswith("USGS-")].copy()
    out = out.dropna(subset=["ssc_mg_L"])
    out = out[out["ssc_mg_L"] > 0]  # Remove non-detects / zeros

    if not out.empty:
        out.to_parquet(cache_file, index=False)

    log.info(f"  {state}: {len(out)} SSC samples from {out['site_id'].nunique()} sites")
    return out


# State FIPS codes for WQP queries
_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08",
    "CT": "09", "DE": "10", "FL": "12", "GA": "13", "HI": "15", "ID": "16",
    "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21", "LA": "22",
    "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28",
    "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34",
    "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39", "OK": "40",
    "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46", "TN": "47",
    "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53", "WV": "54",
    "WI": "55", "WY": "56",
}


def _state_fips(state: str) -> str:
    return _FIPS[state.upper()]


# ── Step 2: Check for continuous FNU turbidity ─────────────────────────────

def check_sites_have_fnu(site_numbers: list[str]) -> set[str]:
    """Check which sites have continuous FNU turbidity (63680) via site service.

    Takes site numbers (without USGS- prefix), returns set of those with FNU.
    Queries in batches of 100.
    """
    cache_file = CACHE_DIR / "sites_with_fnu.json"
    if cache_file.exists():
        with open(cache_file) as f:
            cached = set(json.load(f))
        # Only query sites not in cache
        unchecked = [s for s in site_numbers if s not in cached and f"NO_{s}" not in cached]
        if not unchecked:
            return cached & set(site_numbers)
        fnu_sites = cached
    else:
        unchecked = site_numbers
        fnu_sites = set()

    no_fnu = set()
    batch_size = 100
    for i in range(0, len(unchecked), batch_size):
        batch = unchecked[i : i + batch_size]
        sites_str = ",".join(batch)
        url = (
            f"https://waterservices.usgs.gov/nwis/site/"
            f"?format=rdb&sites={sites_str}"
            f"&parameterCd=63680"
            f"&siteStatus=all"
            f"&hasDataTypeCd=iv"
        )
        text = fetch_with_retry(url, timeout=60)
        if text:
            df = parse_rdb(text)
            if not df.empty and "site_no" in df.columns:
                found = set(df["site_no"].unique())
                fnu_sites.update(found)
                no_fnu.update(set(batch) - found)
            else:
                no_fnu.update(batch)
        else:
            log.warning(f"  Site service failed for batch starting at index {i}")
            # Don't mark as no_fnu, just skip

        time.sleep(2)  # Be nice to the API
        if (i // batch_size) % 5 == 4:
            log.info(f"  Checked {i + len(batch)}/{len(unchecked)} sites for FNU...")

    # Update cache
    all_cached = fnu_sites | {f"NO_{s}" for s in no_fnu}
    with open(cache_file, "w") as f:
        json.dump(sorted(all_cached), f)

    result = fnu_sites & set(site_numbers)
    log.info(f"  {len(result)}/{len(site_numbers)} sites have continuous FNU turbidity")
    return result


# ── Step 3: Get site metadata ──────────────────────────────────────────────

def get_site_metadata(site_numbers: list[str]) -> pd.DataFrame:
    """Fetch lat, lon, drainage area for sites via NWIS site service."""
    cache_file = CACHE_DIR / "site_metadata.parquet"
    if cache_file.exists():
        existing = pd.read_parquet(cache_file)
        existing_sites = set(existing["site_no"])
        needed = [s for s in site_numbers if s not in existing_sites]
        if not needed:
            return existing[existing["site_no"].isin(site_numbers)]
    else:
        existing = pd.DataFrame()
        needed = site_numbers

    all_meta = []
    batch_size = 100
    for i in range(0, len(needed), batch_size):
        batch = needed[i : i + batch_size]
        sites_str = ",".join(batch)
        url = (
            f"https://waterservices.usgs.gov/nwis/site/"
            f"?format=rdb&sites={sites_str}"
            f"&siteOutput=expanded"
            f"&siteStatus=all"
        )
        text = fetch_with_retry(url, timeout=60)
        if text:
            df = parse_rdb(text)
            if not df.empty:
                all_meta.append(df)
        time.sleep(2)

    if all_meta:
        meta = pd.concat(all_meta, ignore_index=True)
        cols_want = {
            "site_no": "site_no",
            "station_nm": "station_name",
            "dec_lat_va": "latitude",
            "dec_long_va": "longitude",
            "drain_area_va": "drainage_area_sqmi",
            "state_cd": "state_code",
            "huc_cd": "huc",
        }
        available = {k: v for k, v in cols_want.items() if k in meta.columns}
        meta = meta[list(available.keys())].rename(columns=available)
        for col in ["latitude", "longitude", "drainage_area_sqmi"]:
            if col in meta.columns:
                meta[col] = pd.to_numeric(meta[col], errors="coerce")

        if not existing.empty:
            meta = pd.concat([existing, meta], ignore_index=True).drop_duplicates(
                subset=["site_no"]
            )
        meta.to_parquet(cache_file, index=False)
    else:
        meta = existing

    return meta[meta["site_no"].isin(site_numbers)] if not meta.empty else pd.DataFrame()


# ── Main pipeline ──────────────────────────────────────────────────────────

def main():
    log.info("=== Extreme SSC Site Discovery ===")

    # Load existing sites
    paired_file = DATA_DIR / "processed" / "turbidity_ssc_paired.parquet"
    if paired_file.exists():
        existing_df = pd.read_parquet(paired_file, columns=["site_id", "ssc_log1p"])
        existing_sites = set(existing_df["site_id"].unique())
        existing_ssc = np.expm1(existing_df["ssc_log1p"])
        existing_extreme_counts = (
            existing_df.assign(ssc=existing_ssc)
            .groupby("site_id")["ssc"]
            .apply(lambda x: (x > 1000).sum())
            .to_dict()
        )
        log.info(f"Existing dataset: {len(existing_sites)} sites, {(existing_ssc > 1000).sum()} samples >1000 mg/L")
    else:
        existing_sites = set()
        existing_extreme_counts = {}

    # Step 1: Discover SSC samples from all target states
    log.info("\n── Step 1: Discovering SSC samples by state ──")
    all_ssc = []
    for group_name, states in STATE_GROUPS.items():
        log.info(f"\n{group_name}:")
        for state in states:
            df = discover_ssc_sites_by_state(state)
            if not df.empty:
                all_ssc.append(df)
            time.sleep(2)  # Be nice between state queries

    if not all_ssc:
        log.error("No SSC data retrieved from any state!")
        return

    ssc_all = pd.concat(all_ssc, ignore_index=True)
    log.info(f"\nTotal SSC samples: {len(ssc_all)} from {ssc_all['site_id'].nunique()} sites")

    # Filter for extreme values
    ssc_extreme = ssc_all[ssc_all["ssc_mg_L"] >= 1000].copy()
    log.info(f"Samples >= 1000 mg/L: {len(ssc_extreme)} from {ssc_extreme['site_id'].nunique()} sites")
    log.info(f"Samples >= 5000 mg/L: {(ssc_extreme['ssc_mg_L'] >= 5000).sum()}")
    log.info(f"Samples >= 10000 mg/L: {(ssc_extreme['ssc_mg_L'] >= 10000).sum()}")

    # Get unique site numbers (strip USGS- prefix for API calls)
    extreme_site_ids = ssc_extreme["site_id"].unique()
    site_numbers = [s.replace("USGS-", "") for s in extreme_site_ids]

    # Step 2: Check which have continuous FNU
    log.info("\n── Step 2: Checking for continuous FNU turbidity ──")
    fnu_sites = check_sites_have_fnu(site_numbers)
    log.info(f"Sites with both extreme SSC AND continuous FNU: {len(fnu_sites)}")

    # Filter to sites with FNU
    fnu_site_ids = {f"USGS-{s}" for s in fnu_sites}
    ssc_with_fnu = ssc_extreme[ssc_extreme["site_id"].isin(fnu_site_ids)].copy()

    if ssc_with_fnu.empty:
        log.warning("No sites found with both extreme SSC and continuous FNU!")
        # Still save all SSC results for reference
        ssc_extreme.to_parquet(OUTPUT_DIR / "all_extreme_ssc_no_fnu_filter.parquet", index=False)
        return

    # Step 3: Identify new opportunities
    log.info("\n── Step 3: Comparing with existing dataset ──")
    new_sites = fnu_site_ids - existing_sites
    existing_with_more = set()
    for sid in fnu_site_ids & existing_sites:
        new_extreme = (ssc_with_fnu[ssc_with_fnu["site_id"] == sid]["ssc_mg_L"] >= 1000).sum()
        old_extreme = existing_extreme_counts.get(sid, 0)
        if new_extreme > old_extreme:
            existing_with_more.add(sid)

    log.info(f"Completely new sites (not in dataset): {len(new_sites)}")
    log.info(f"Existing sites with potentially more extreme samples: {len(existing_with_more)}")

    # Step 4: Get metadata
    log.info("\n── Step 4: Fetching site metadata ──")
    target_site_numbers = [s.replace("USGS-", "") for s in fnu_site_ids]
    meta = get_site_metadata(target_site_numbers)

    # Merge everything
    result = ssc_with_fnu.merge(
        meta.rename(columns={"site_no": "site_no_clean"}),
        left_on=ssc_with_fnu["site_id"].str.replace("USGS-", ""),
        right_on="site_no_clean",
        how="left",
    )

    # Clean up
    result = result.drop(columns=["key_0", "site_no_clean"], errors="ignore")
    result["is_new_site"] = result["site_id"].isin(new_sites)

    # Save results
    output_file = OUTPUT_DIR / "extreme_ssc_hotspots.parquet"
    result.to_parquet(output_file, index=False)
    log.info(f"\nSaved {len(result)} extreme SSC samples to {output_file}")

    # Also save as CSV for easy inspection
    csv_file = OUTPUT_DIR / "extreme_ssc_hotspots.csv"
    result.to_csv(csv_file, index=False)

    # Save site summary
    summary = (
        result.groupby(["site_id", "state", "is_new_site"])
        .agg(
            n_extreme=("ssc_mg_L", "count"),
            max_ssc=("ssc_mg_L", "max"),
            median_ssc=("ssc_mg_L", "median"),
            latitude=("latitude", "first"),
            longitude=("longitude", "first"),
            drainage_area=("drainage_area_sqmi", "first"),
        )
        .reset_index()
        .sort_values("max_ssc", ascending=False)
    )
    summary_file = OUTPUT_DIR / "site_summary.csv"
    summary.to_csv(summary_file, index=False)

    # Print summary
    log.info("\n" + "=" * 60)
    log.info("SUMMARY")
    log.info("=" * 60)
    log.info(f"Total extreme SSC samples (>=1000) with FNU: {len(result)}")
    log.info(f"  >= 5000 mg/L: {(result['ssc_mg_L'] >= 5000).sum()}")
    log.info(f"  >= 10000 mg/L: {(result['ssc_mg_L'] >= 10000).sum()}")
    log.info(f"Sites with extreme SSC + FNU: {result['site_id'].nunique()}")
    log.info(f"  New sites: {len(new_sites)}")
    log.info(f"  Existing sites with more extremes: {len(existing_with_more)}")
    log.info(f"\nTop 15 sites by max SSC:")
    for _, row in summary.head(15).iterrows():
        flag = " [NEW]" if row["is_new_site"] else ""
        log.info(
            f"  {row['site_id']}: max={row['max_ssc']:.0f} mg/L, "
            f"n={row['n_extreme']:.0f}, state={row['state']}{flag}"
        )

    log.info(f"\nBy state:")
    state_summary = result.groupby("state").agg(
        n_samples=("ssc_mg_L", "count"),
        n_sites=("site_id", "nunique"),
        max_ssc=("ssc_mg_L", "max"),
    )
    for state, row in state_summary.sort_values("n_samples", ascending=False).iterrows():
        log.info(f"  {state}: {row['n_samples']} samples, {row['n_sites']} sites, max={row['max_ssc']:.0f} mg/L")

    # Save query log
    log_file = OUTPUT_DIR / "query_log.txt"
    with open(log_file, "w") as f:
        f.write(f"Extreme SSC Discovery Run\n")
        f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"States queried: {ALL_STATES}\n")
        f.write(f"Total SSC samples found: {len(ssc_all)}\n")
        f.write(f"Extreme (>=1000): {len(ssc_extreme)} from {ssc_extreme['site_id'].nunique()} sites\n")
        f.write(f"With FNU: {len(result)} from {result['site_id'].nunique()} sites\n")
        f.write(f"New sites: {len(new_sites)}\n")
        f.write(f"Output: {output_file}\n")


if __name__ == "__main__":
    main()
