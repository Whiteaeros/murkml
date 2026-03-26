"""Download StreamCat watershed attributes for all sites via EPA + NLDI APIs.

Step 1: Get NHDPlus COMID for each USGS site via NLDI
Step 2: Download StreamCat metrics by COMID (geology, soils, climate, land cover, etc.)
Step 3: Download slope from Wieczorek "Select Attributes" via NLDI tot characteristics
Step 4: Save raw + mapped attributes

StreamCat API: https://api.epa.gov/StreamCat/streams/metrics
NLDI API: https://api.water.usgs.gov/nldi/linked-data/nwissite

Usage:
    python scripts/download_streamcat.py [--sites-from catalog|assembled|all]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from murkml.provenance import start_run, log_step, log_file, end_run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"
STREAMCAT_DIR = DATA_DIR / "streamcat"

NLDI_BASE = "https://api.water.usgs.gov/nldi/linked-data/nwissite"
STREAMCAT_API = "https://api.epa.gov/StreamCat/streams/metrics"

# StreamCat metrics to download, grouped by category.
# Names are the SHORT form used by the API (no Ws/Cat suffix).
# We pass aoi=ws to get watershed-level values; API appends 'ws' suffix to returned columns.
# Names verified against API name_options endpoint 2026-03-25.
STREAMCAT_METRICS = {
    # --- Static watershed characteristics ---
    "landcover_2019": [
        "pctdecid2019", "pctconif2019", "pctmxfst2019",
        "pctcrop2019", "pcthay2019",
        "pcturbhi2019", "pcturbmd2019", "pcturblo2019", "pcturbop2019",
        "pctwdwet2019", "pctshrb2019", "pctgrs2019",
        "pctice2019", "pctow2019",
    ],
    "geology": [
        "pctsilicic", "pctcarbresid", "pctnoncarbresid",
        "pctalkintruvol", "pctextruvol",
        "pctglactilloam", "pctglactilclay", "pctglactilcrs",
        "pctglaclakecrs", "pctglaclakefine",
        "pctalluvcoast", "pctcoastcrs", "pcteolcrs", "pcteolfine",
        "pctsallake", "pctwater", "pctcolluvsed", "pcthydric",
    ],
    "geochemistry": [
        "cao", "sio2", "al2o3", "fe2o3", "mgo", "k2o", "na2o",
    ],
    "soils": [
        "clay", "sand", "perm", "rckdep", "wtdep", "om", "kffact",
    ],
    "climate_normals": [
        "precip9120", "tmean9120", "tmax9120", "tmin9120",
    ],
    "topography": [
        "elev",
    ],
    "hydrology": [
        "bfi", "runoff", "wetindex",
    ],
    "physical": [
        "compstrgth", "hydrlcond",
        "bankfulldepth", "bankfullwidth",
        "conn",
    ],
    "infrastructure": [
        "damnidstor", "damdens", "rddens", "popden2010",
    ],
    "point_sources": [
        "npdesdens",
        "wwtpalldens", "wwtpmajordens", "wwtpminordens",
        "septic", "superfunddens", "coalminedens", "minedens",
    ],
    "nutrient_loading": [
        "fert", "manure", "nsurp",
        "pctagdrainage",
        "cbnf", "rockn",
    ],
    # --- Time-varying land disturbance ---
    "forest_loss": [
        f"pctfrstloss{y}" for y in range(2001, 2014)  # 2001-2013
    ],
    "burn_severity_high": [
        f"pcthighsev{y}" for y in range(2000, 2019)  # 2000-2018
    ],
    "impervious_timeseries": [
        f"pctimp{y}" for y in [2001, 2004, 2006, 2008, 2011, 2013, 2016, 2019]
    ],
    "landcover_2001": [
        "pctdecid2001", "pctconif2001", "pctmxfst2001",
        "pctcrop2001", "pcthay2001",
        "pcturbhi2001", "pcturbmd2001", "pcturblo2001", "pcturbop2001",
    ],
    # --- Time-varying nutrient application ---
    "nitrogen_ag": [
        f"n_ags_{y}" for y in range(2000, 2018)  # 2000-2017 (overlap with training data)
    ],
    "phosphorus_ag": [
        f"p_ags_{y}" for y in range(2000, 2018)  # 2000-2017
    ],
}


def get_all_sites(source: str = "all") -> list[str]:
    """Get list of USGS site IDs to fetch attributes for.

    source='catalog': sites from site_catalog.parquet
    source='assembled': sites from all assembled paired parquets
    source='all': union of catalog + assembled + expansion candidates
    """
    sites = set()

    catalog_path = DATA_DIR / "site_catalog.parquet"
    if catalog_path.exists() and source in ("catalog", "all"):
        df = pd.read_parquet(catalog_path)
        sites.update(df["site_id"].unique())

    # Assembled datasets
    if source in ("assembled", "all"):
        for f in (DATA_DIR / "processed").glob("*_paired.parquet"):
            df = pd.read_parquet(f, columns=["site_id"])
            sites.update(df["site_id"].unique())

    # Expansion candidates
    if source == "all":
        exp_path = DATA_DIR / "expansion_candidates.parquet"
        if exp_path.exists():
            df = pd.read_parquet(exp_path)
            sites.update(df["site_id"].unique())

        # Broad discovery results
        disc_path = DATA_DIR / "all_discovered_sites.parquet"
        if disc_path.exists():
            df = pd.read_parquet(disc_path)
            sites.update(df["site_id"].unique())

        # Validation sites
        val_dir = DATA_DIR / "validation" / "discrete"
        if val_dir.exists():
            for f in val_dir.glob("*.parquet"):
                site_id = f.stem.rsplit("_", 1)[0].replace("_", "-")
                sites.add(site_id)

    logger.info(f"Found {len(sites)} unique sites (source={source})")
    return sorted(sites)


def fetch_comid(site_id: str, max_retries: int = 3) -> str | None:
    """Get NHDPlus COMID for a USGS site via NLDI."""
    url = f"{NLDI_BASE}/{site_id}"
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                features = data.get("features", [])
                if features:
                    return str(features[0].get("properties", {}).get("comid", ""))
            elif resp.status_code == 429:
                wait = 2 ** attempt * 5
                logger.warning(f"  NLDI rate limited, waiting {wait}s")
                time.sleep(wait)
                continue
            elif resp.status_code == 404:
                logger.warning(f"  {site_id}: not found in NLDI")
                return None
            else:
                logger.warning(f"  {site_id}: NLDI HTTP {resp.status_code}")
                return None
        except Exception as e:
            logger.warning(f"  {site_id} COMID error: {e}")
            if attempt < max_retries - 1:
                time.sleep(3)
    return None


def fetch_huc(site_id: str) -> str | None:
    """Get HUC2 code for a site from NLDI basin lookup."""
    url = f"{NLDI_BASE}/{site_id}/basin"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            # Basin response doesn't directly give HUC, but site navigation does
            pass
    except Exception:
        pass
    # Fallback: extract from site number (first 2 digits of USGS gage number
    # don't reliably map to HUC). We'll get HUC from NLDI characteristics instead.
    return None


def get_comids_for_sites(sites: list[str]) -> pd.DataFrame:
    """Get COMIDs for all sites. Cache results."""
    cache_path = STREAMCAT_DIR / "site_comid_mapping.parquet"
    if cache_path.exists():
        cached = pd.read_parquet(cache_path)
        cached_sites = set(cached["site_id"])
        new_sites = [s for s in sites if s not in cached_sites]
        if not new_sites:
            logger.info(f"All {len(sites)} COMIDs cached")
            return cached[cached["site_id"].isin(sites)]
        logger.info(f"{len(cached_sites)} COMIDs cached, {len(new_sites)} new to fetch")
    else:
        cached = pd.DataFrame(columns=["site_id", "comid"])
        new_sites = sites

    records = []
    for i, site_id in enumerate(new_sites):
        if (i + 1) % 10 == 0 or i == 0:
            logger.info(f"  COMID lookup [{i+1}/{len(new_sites)}]")
        comid = fetch_comid(site_id)
        records.append({"site_id": site_id, "comid": comid})
        time.sleep(0.5)  # NLDI is less throttled than USGS data API

    new_df = pd.DataFrame(records)
    result = pd.concat([cached, new_df], ignore_index=True).drop_duplicates("site_id")

    # Save cache
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(cache_path, index=False)

    n_found = result["comid"].notna().sum()
    n_missing = result["comid"].isna().sum()
    logger.info(f"COMIDs: {n_found} found, {n_missing} missing")
    if n_missing > 0:
        missing = result[result["comid"].isna()]["site_id"].tolist()
        logger.warning(f"  Sites without COMID: {missing[:10]}...")

    return result[result["site_id"].isin(sites)]


def fetch_streamcat_metrics(
    comids: list[str],
    metric_names: list[str],
    max_retries: int = 3,
    batch_size: int = 100,
) -> pd.DataFrame:
    """Fetch StreamCat metrics for a list of COMIDs using batch requests.

    The StreamCat API accepts comma-separated COMIDs (up to ~100 per call).
    Multiple metric names can also be comma-separated.
    We pass aoi=ws to get watershed-level (full upstream) values.

    100 COMIDs × N metrics per call = ~3 seconds (vs 100 individual calls).
    """
    all_results = []
    metric_str = ",".join(metric_names)

    # Split COMIDs into batches
    batches = [comids[i:i + batch_size] for i in range(0, len(comids), batch_size)]

    for batch_idx, batch in enumerate(batches):
        comid_str = ",".join(str(c) for c in batch)
        logger.info(f"    StreamCat batch [{batch_idx+1}/{len(batches)}] ({len(batch)} COMIDs)")

        for attempt in range(max_retries):
            try:
                resp = requests.get(
                    STREAMCAT_API,
                    params={"comid": comid_str, "name": metric_str, "aoi": "ws"},
                    timeout=60,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items", [])
                    all_results.extend(items)
                    logger.info(f"      {len(items)} results")
                    break
                elif resp.status_code == 429:
                    wait = 2 ** attempt * 10
                    logger.warning(f"  StreamCat rate limited, waiting {wait}s")
                    time.sleep(wait)
                else:
                    logger.warning(f"  StreamCat HTTP {resp.status_code}")
                    break
            except Exception as e:
                logger.warning(f"  StreamCat error: {e}")
                if attempt < max_retries - 1:
                    time.sleep(3)

        time.sleep(1)  # Brief pause between batches

    if all_results:
        return pd.DataFrame(all_results)
    return pd.DataFrame()


def fetch_nldi_slope(site_id: str, max_retries: int = 3) -> float | None:
    """Get basin slope from NLDI total upstream characteristics (Wieczorek)."""
    url = f"{NLDI_BASE}/{site_id}/tot"
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    for item in data:
                        if item.get("characteristic_id") == "TOT_BASIN_SLOPE":
                            return float(item["characteristic_value"])
                return None
            elif resp.status_code == 429:
                time.sleep(2 ** attempt * 5)
            else:
                return None
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(3)
    return None


def get_nldi_supplementary(sites_df: pd.DataFrame) -> pd.DataFrame:
    """Fetch slope, HUC, drainage area, and IWI from NLDI tot characteristics. Cached."""
    cache_path = STREAMCAT_DIR / "nldi_supplementary.parquet"
    if cache_path.exists():
        cached = pd.read_parquet(cache_path)
        cached_sites = set(cached["site_id"])
        new_sites = [s for s in sites_df["site_id"] if s not in cached_sites]
        if not new_sites:
            logger.info("All NLDI supplementary values cached")
            return cached[cached["site_id"].isin(sites_df["site_id"])]
        logger.info(f"{len(cached_sites)} cached, {len(new_sites)} new for NLDI supplementary")
    else:
        cached = pd.DataFrame()
        new_sites = sites_df["site_id"].tolist()

    # Target characteristics from Wieczorek "Select Attributes"
    target_chars = {
        "TOT_BASIN_SLOPE": "slope_pct",
        "TOT_HUC02": "huc2",
        "TOT_BASIN_AREA": "drainage_area_km2",
        "TOT_IWI": "watershed_integrity",
        "TOT_BFI": "baseflow_index_nldi",  # backup for StreamCat BFI
    }

    records = []
    for i, site_id in enumerate(new_sites):
        if (i + 1) % 10 == 0 or i == 0:
            logger.info(f"  NLDI supplementary [{i+1}/{len(new_sites)}]")

        row = {"site_id": site_id}

        # Get HUC2 from site reachcode (first 2 digits)
        try:
            site_resp = requests.get(f"{NLDI_BASE}/{site_id}?f=json", timeout=30)
            if site_resp.status_code == 200:
                site_data = site_resp.json()
                features = site_data.get("features", [])
                if features:
                    reachcode = features[0].get("properties", {}).get("reachcode", "")
                    if reachcode and len(reachcode) >= 2:
                        row["huc2"] = reachcode[:2]
        except Exception:
            pass

        # Get slope, drainage area, etc. from tot characteristics
        url = f"{NLDI_BASE}/{site_id}/tot"
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                # Response format: {"comid": "...", "characteristics": [...]}
                chars = data.get("characteristics", [])
                if isinstance(data, list):
                    chars = data  # Fallback for old format
                for item in chars:
                    cid = item.get("characteristic_id", "")
                    val = item.get("characteristic_value")
                    if cid in target_chars and val is not None:
                        internal_name = target_chars[cid]
                        try:
                            row[internal_name] = float(val)
                        except (ValueError, TypeError):
                            pass
            elif resp.status_code == 429:
                time.sleep(10)
        except Exception as e:
            logger.warning(f"  {site_id} NLDI error: {e}")

        records.append(row)
        time.sleep(1)

        # Incremental save every 50 sites to avoid losing progress on stalls
        if (i + 1) % 50 == 0:
            partial = pd.DataFrame(records)
            if not cached.empty:
                partial = pd.concat([cached, partial], ignore_index=True).drop_duplicates("site_id")
            partial.to_parquet(cache_path, index=False)
            logger.info(f"    Saved checkpoint: {len(partial)} sites")

    new_df = pd.DataFrame(records)
    if not cached.empty:
        result = pd.concat([cached, new_df], ignore_index=True).drop_duplicates("site_id")
    else:
        result = new_df

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(cache_path, index=False)
    return result[result["site_id"].isin(sites_df["site_id"])]


def map_to_internal_schema(raw: pd.DataFrame, slopes: pd.DataFrame) -> pd.DataFrame:
    """Map StreamCat column names to murkml internal feature schema."""
    # Normalize column names to lowercase for matching
    raw.columns = [c.lower() for c in raw.columns]

    mapped = pd.DataFrame()
    mapped["comid"] = raw.get("comid")

    # WsAreaSqKm is always included in StreamCat responses
    mapped["drainage_area_km2"] = raw.get("wsareasqkm")

    # Land cover (sum NLCD sub-classes)
    mapped["forest_pct"] = (
        raw.get("pctdecid2019ws", 0).fillna(0) +
        raw.get("pctconif2019ws", 0).fillna(0) +
        raw.get("pctmxfst2019ws", 0).fillna(0)
    )
    mapped["agriculture_pct"] = (
        raw.get("pctcrop2019ws", 0).fillna(0) +
        raw.get("pcthay2019ws", 0).fillna(0)
    )
    mapped["developed_pct"] = (
        raw.get("pcturbhi2019ws", 0).fillna(0) +
        raw.get("pcturbmd2019ws", 0).fillna(0) +
        raw.get("pcturblo2019ws", 0).fillna(0) +
        raw.get("pcturbop2019ws", 0).fillna(0)
    )
    mapped["wetland_pct"] = raw.get("pctwdwet2019ws")
    mapped["shrub_pct"] = raw.get("pctshrb2019ws")
    mapped["grass_pct"] = raw.get("pctgrs2019ws")

    # Geology — continuous percentages (all Soller lithology types)
    geology_cols = {
        "pctsilicicws": "pct_siliciclastic",
        "pctcarbresidws": "pct_carbonate_resid",
        "pctnoncarbresidws": "pct_nonite_resid",
        "pctalkintruvolws": "pct_alkaline_intrusive",
        "pctextruvolws": "pct_extrusive_volcanic",
        "pctglactilloamws": "pct_glacial_till_loam",
        "pctglactilclayws": "pct_glacial_till_clay",
        "pctglactilcrsws": "pct_glacial_till_coarse",
        "pctglaclakecrsws": "pct_glacial_lake_coarse",
        "pctglaclakefinews": "pct_glacial_lake_fine",
        "pctalluvcoastws": "pct_alluvial_coastal",
        "pctcoastcrsws": "pct_coastal_coarse",
        "pcteolcrsws": "pct_eolian_coarse",
        "pcteolfinews": "pct_eolian_fine",
        "pctsallakews": "pct_saline_lake",
        "pctwaterws": "pct_water_geology",
        "pctcolluvsedws": "pct_colluvial_sediment",
        "pcthydricws": "pct_hydric",
    }
    for sc_col, internal_col in geology_cols.items():
        mapped[internal_col] = raw.get(sc_col)

    # Derive dominant geology class from percentages
    geol_pct_cols = [c for c in geology_cols.values() if c in mapped.columns]
    if geol_pct_cols:
        geol_subset = mapped[geol_pct_cols].fillna(0)
        mapped["geol_class"] = geol_subset.idxmax(axis=1).str.replace("pct_", "")
        # If all zeros (no geology data), set to NaN
        mapped.loc[geol_subset.sum(axis=1) == 0, "geol_class"] = None

    # Geochemistry
    geochem_cols = {
        "caows": "geo_cao", "sio2ws": "geo_sio2", "al2o3ws": "geo_al2o3",
        "fe2o3ws": "geo_fe2o3", "mgows": "geo_mgo", "k2ows": "geo_k2o",
        "na2ows": "geo_na2o",
    }
    for sc_col, internal_col in geochem_cols.items():
        mapped[internal_col] = raw.get(sc_col)

    # Soils (direct STATSGO matches)
    mapped["clay_pct"] = raw.get("clayws")
    mapped["sand_pct"] = raw.get("sandws")
    mapped["soil_permeability"] = raw.get("permws")
    mapped["soil_rock_depth"] = raw.get("rckdepws")
    mapped["water_table_depth"] = raw.get("wtdepws")
    mapped["soil_organic_matter"] = raw.get("omws")
    mapped["soil_erodibility"] = raw.get("kffactws")

    # Climate (1991-2020 normals)
    mapped["precip_mean_mm"] = raw.get("precip9120ws")
    mapped["temp_mean_c"] = raw.get("tmean9120ws")

    # Topography
    mapped["elevation_m"] = raw.get("elevws")

    # Hydrology
    mapped["baseflow_index"] = raw.get("bfiws")
    mapped["runoff_mean"] = raw.get("runoffws")
    mapped["wetness_index"] = raw.get("wetindexws")

    # Infrastructure — dam density stays as density (we'll convert in adapter
    # using drainage_area_km2 from NLDI which isn't available here yet)
    mapped["dam_storage_density"] = raw.get("damnidstorws")
    mapped["dam_density"] = raw.get("damdensws")
    mapped["road_density"] = raw.get("rddensws")
    mapped["pop_density"] = raw.get("popden2010ws")

    # Point sources
    mapped["npdes_density"] = raw.get("npdesdensws")
    mapped["wwtp_all_density"] = raw.get("wwtpalldensws")
    mapped["wwtp_major_density"] = raw.get("wwtpmajordensws")
    mapped["wwtp_minor_density"] = raw.get("wwtpminordensws")
    mapped["septic_density"] = raw.get("septicws")
    mapped["superfund_density"] = raw.get("superfunddensws")
    mapped["coalmine_density"] = raw.get("coalminedensws")
    mapped["mine_density"] = raw.get("minedensws")

    # Nutrient loading
    mapped["fertilizer_rate"] = raw.get("fertws")
    mapped["manure_rate"] = raw.get("manurews")
    mapped["nitrogen_surplus"] = raw.get("nsurpws")
    mapped["ag_drainage_pct"] = raw.get("pctagdrainagews")
    mapped["bio_n_fixation"] = raw.get("cbnfws")
    mapped["rock_nitrogen"] = raw.get("rocknws")

    # Physical
    mapped["compressive_strength"] = raw.get("compstrgthws")
    mapped["hydraulic_conductivity"] = raw.get("hydrlcondws")
    mapped["bankfull_depth"] = raw.get("bankfulldepthws")
    mapped["bankfull_width"] = raw.get("bankfullwidthws")
    mapped["hydrologic_connectivity"] = raw.get("connws")

    # --- Time-varying: forest loss (annual cumulative) ---
    for y in range(2001, 2014):
        col = f"pctfrstloss{y}ws"
        if col in raw.columns:
            mapped[f"forest_loss_{y}"] = raw[col]

    # --- Time-varying: high-severity burn ---
    for y in range(2000, 2019):
        col = f"pcthighsev{y}ws"
        if col in raw.columns:
            mapped[f"burn_highsev_{y}"] = raw[col]

    # --- Time-varying: impervious surface ---
    for y in [2001, 2004, 2006, 2008, 2011, 2013, 2016, 2019]:
        col = f"pctimp{y}ws"
        if col in raw.columns:
            mapped[f"impervious_{y}"] = raw[col]

    # --- Time-varying: land cover 2001 (for computing change from 2001→2019) ---
    for nlcd_type in ["pctdecid", "pctconif", "pctmxfst", "pctcrop", "pcthay",
                       "pcturbhi", "pcturbmd", "pcturblo", "pcturbop"]:
        col_2001 = f"{nlcd_type}2001ws"
        if col_2001 in raw.columns:
            mapped[f"{nlcd_type}_2001"] = raw[col_2001]

    # --- Time-varying: nitrogen and phosphorus application ---
    for y in range(2000, 2018):
        n_col = f"n_ags_{y}ws"
        p_col = f"p_ags_{y}ws"
        if n_col in raw.columns:
            mapped[f"n_ag_{y}"] = raw[n_col]
        if p_col in raw.columns:
            mapped[f"p_ag_{y}"] = raw[p_col]

    return mapped


def main():
    parser = argparse.ArgumentParser(description="Download StreamCat attributes")
    parser.add_argument("--sites-from", default="all", choices=["catalog", "assembled", "all"],
                        help="Which site list to use")
    args = parser.parse_args()

    start_run("download_streamcat")
    STREAMCAT_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Get all sites
    sites = get_all_sites(args.sites_from)
    log_step("get_sites", n_sites=len(sites), source=args.sites_from)

    # Step 2: Get COMIDs
    logger.info(f"\n{'='*60}")
    logger.info("STEP 1: COMID LOOKUP")
    logger.info(f"{'='*60}")
    comid_df = get_comids_for_sites(sites)
    valid = comid_df[comid_df["comid"].notna()]
    logger.info(f"Valid COMIDs: {len(valid)} / {len(comid_df)}")
    log_step("comid_lookup", n_valid=len(valid), n_missing=len(comid_df) - len(valid))

    if valid.empty:
        logger.error("No valid COMIDs found!")
        end_run()
        return

    # Step 3: Download StreamCat metrics
    logger.info(f"\n{'='*60}")
    logger.info("STEP 2: STREAMCAT METRICS")
    logger.info(f"{'='*60}")

    comids = valid["comid"].tolist()

    # Fetch each category separately with per-category caching
    category_cache_dir = STREAMCAT_DIR / "categories"
    category_cache_dir.mkdir(parents=True, exist_ok=True)

    for category, metric_names in STREAMCAT_METRICS.items():
        cache_file = category_cache_dir / f"{category}.parquet"
        if cache_file.exists():
            logger.info(f"  {category}: cached ({len(metric_names)} metrics)")
            continue

        logger.info(f"  Fetching {category} ({len(metric_names)} metrics)...")
        cat_df = fetch_streamcat_metrics(comids, metric_names)
        if not cat_df.empty:
            cat_df.columns = [c.lower() for c in cat_df.columns]
            cat_df.to_parquet(cache_file, index=False)
            logger.info(f"    Got {len(cat_df)} rows, {len(cat_df.columns)} cols → cached")
        else:
            logger.warning(f"    No data for {category}")
            pd.DataFrame().to_parquet(cache_file)
        log_step(f"fetch_{category}", n_metrics=len(metric_names),
                 n_rows=len(cat_df) if not cat_df.empty else 0)

    # Merge all cached categories into one DataFrame
    all_metrics = pd.DataFrame({"comid": [str(c) for c in comids]})
    for category in STREAMCAT_METRICS:
        cache_file = category_cache_dir / f"{category}.parquet"
        if cache_file.exists():
            cat_df = pd.read_parquet(cache_file)
            if len(cat_df) > 0 and "comid" in cat_df.columns:
                cat_df["comid"] = cat_df["comid"].astype(str)
                new_cols = [c for c in cat_df.columns if c not in all_metrics.columns]
                if new_cols:
                    all_metrics = all_metrics.merge(
                        cat_df[["comid"] + new_cols], on="comid", how="left"
                    )

    raw_path = STREAMCAT_DIR / "raw_metrics.parquet"
    all_metrics.to_parquet(raw_path, index=False)
    log_file(raw_path, role="output")
    logger.info(f"Raw StreamCat: {len(all_metrics)} sites, {len(all_metrics.columns)} cols")

    # Step 4: Get slope and HUC from NLDI
    logger.info(f"\n{'='*60}")
    logger.info("STEP 3: SUPPLEMENTARY FROM NLDI (slope, HUC, area, IWI)")
    logger.info(f"{'='*60}")
    nldi_supp = get_nldi_supplementary(valid)
    for col in nldi_supp.columns:
        if col != "site_id":
            n = nldi_supp[col].notna().sum()
            logger.info(f"  {col}: {n}/{len(nldi_supp)}")
    log_step("nldi_supplementary", n_sites=len(nldi_supp),
             n_slope=int(nldi_supp.get("slope_pct", pd.Series()).notna().sum()),
             n_huc=int(nldi_supp.get("huc2", pd.Series()).notna().sum()),
             n_area=int(nldi_supp.get("drainage_area_km2", pd.Series()).notna().sum()))

    # Step 5: Map to internal schema
    logger.info(f"\n{'='*60}")
    logger.info("STEP 4: MAP TO INTERNAL SCHEMA")
    logger.info(f"{'='*60}")
    mapped = map_to_internal_schema(all_metrics, nldi_supp)

    # Add site_id back (from comid mapping)
    comid_to_site = dict(zip(valid["comid"].astype(str), valid["site_id"]))
    mapped["site_id"] = mapped["comid"].astype(str).map(comid_to_site)

    # Add NLDI supplementary data (slope, HUC, drainage area, IWI)
    nldi_lookup = nldi_supp.set_index("site_id")
    for col in ["slope_pct", "huc2", "drainage_area_km2", "watershed_integrity"]:
        if col in nldi_lookup.columns:
            mapped[col] = mapped["site_id"].map(nldi_lookup[col])
        elif col not in mapped.columns:
            mapped[col] = None

    # Ecoregion: derive from StreamCat PctEco columns if available
    # (StreamCat gives % of watershed in each Level III ecoregion)
    eco_cols = [c for c in all_metrics.columns if c.lower().startswith("pcteco")]
    if eco_cols:
        eco_data = all_metrics[eco_cols].fillna(0)
        mapped["ecoregion"] = eco_data.idxmax(axis=1).str.extract(r"(\d+)")[0]
        mapped.loc[eco_data.sum(axis=1) == 0, "ecoregion"] = None
    else:
        mapped["ecoregion"] = None

    # Drop comid from final output (internal use only)
    mapped = mapped.drop(columns=["comid"], errors="ignore")

    # Move site_id to first column
    cols = ["site_id"] + [c for c in mapped.columns if c != "site_id"]
    mapped = mapped[cols]

    # Save
    output_path = DATA_DIR / "site_attributes_streamcat.parquet"
    mapped.to_parquet(output_path, index=False)
    log_file(output_path, role="output")

    logger.info(f"\n{'='*60}")
    logger.info("SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"Sites: {len(mapped)}")
    logger.info(f"Columns: {len(mapped.columns)}")
    n_complete = mapped.drop(columns=["site_id"]).notna().all(axis=1).sum()
    logger.info(f"Complete rows (all non-NaN): {n_complete}")

    # Report coverage per category
    for col in sorted(mapped.columns):
        if col == "site_id":
            continue
        n_valid = mapped[col].notna().sum()
        pct = n_valid / len(mapped) * 100
        if pct < 100:
            logger.info(f"  {col}: {n_valid}/{len(mapped)} ({pct:.0f}%)")

    log_step("save_streamcat", n_sites=len(mapped), n_cols=len(mapped.columns),
             n_complete=int(n_complete))
    end_run()


if __name__ == "__main__":
    main()
