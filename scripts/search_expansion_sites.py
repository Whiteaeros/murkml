"""Search for expansion training sites across 12 watershed regimes.

Queries USGS for sites with continuous turbidity in target regions,
verifies turbidity data actually exists, checks for discrete SSC/TP,
and outputs a ranked candidate list.

Usage:
    python scripts/search_expansion_sites.py
"""

from __future__ import annotations

import logging
import os
import sys
import time
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

from dataretrieval import waterdata

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"

# Existing sites to exclude (training + validation)
def get_existing_sites() -> set:
    existing = set()
    # Training sites
    for f in (DATA_DIR / "discrete").glob("*_ssc.parquet"):
        site_id = f.stem.replace("_ssc", "").replace("_", "-")
        existing.add(site_id)
    # Validation sites
    val_cont = DATA_DIR / "validation" / "continuous"
    if val_cont.exists():
        for d in val_cont.iterdir():
            if d.is_dir():
                existing.add(d.name.replace("_", "-"))
    return existing


# Target regimes with bounding boxes and search parameters
REGIMES = {
    "loess_belt": {
        "description": "Wind-deposited silt, different turbidity-SSC ratio",
        "bboxes": {
            "IA": [-96.6, 40.4, -90.1, 43.5],
            "NE_east": [-100.0, 40.0, -95.3, 43.0],
            "MO_north": [-95.8, 38.5, -91.0, 40.6],
            "IL": [-91.5, 37.0, -87.5, 42.5],
        },
        "target": 8,
    },
    "gulf_coastal_plain": {
        "description": "Sandy/clay coastal sediments, WWTP, subtropical",
        "bboxes": {
            "TX_east": [-97.0, 29.0, -93.5, 33.5],
            "LA": [-94.0, 29.0, -89.0, 33.0],
            "MS": [-91.7, 30.2, -88.1, 35.0],
            "AL_south": [-88.5, 30.2, -85.0, 33.0],
            "FL_pan": [-87.6, 29.0, -82.0, 31.0],
        },
        "target": 8,
    },
    "arid_southwest": {
        "description": "Ephemeral flow, flash floods, alkaline",
        "bboxes": {
            "AZ": [-114.8, 31.3, -109.0, 37.0],
            "NM": [-109.0, 31.3, -103.0, 37.0],
            "UT_south": [-114.0, 37.0, -109.0, 42.0],
        },
        "target": 6,
    },
    "iron_range": {
        "description": "Precambrian geology, iron-rich, mining influence",
        "bboxes": {
            "MN_north": [-95.0, 46.5, -89.5, 49.4],
            "WI_north": [-92.0, 45.0, -87.0, 47.1],
            "MI_UP": [-90.4, 45.8, -84.0, 47.5],
        },
        "target": 6,
    },
    "se_piedmont": {
        "description": "Red clay soils, blackwater streams, mixed ag/urban",
        "bboxes": {
            "NC": [-84.3, 34.0, -75.5, 36.6],
            "SC": [-83.4, 32.0, -78.5, 35.2],
            "GA": [-85.6, 31.0, -81.0, 35.0],
        },
        "target": 6,
    },
    "karst": {
        "description": "Carbonate geology, groundwater-dominated, springs",
        "bboxes": {
            "TX_edwards": [-101.0, 29.0, -97.0, 32.0],
            "TN_KY": [-87.0, 35.5, -82.0, 37.5],
            "MO_ozarks": [-94.6, 36.0, -90.0, 38.5],
            "FL_springs": [-83.5, 28.0, -80.5, 31.0],
        },
        "target": 6,
    },
    "urban_stormwater": {
        "description": "High impervious, flashy hydrology, CSO/stormwater",
        "bboxes": {
            "PA_philly": [-76.0, 39.5, -74.7, 40.5],
            "GA_atlanta": [-84.8, 33.4, -83.8, 34.2],
            "IL_chicago": [-88.5, 41.3, -87.2, 42.3],
            "MA_boston": [-71.5, 42.0, -70.5, 42.7],
        },
        "target": 6,
    },
    "new_england": {
        "description": "Glaciated, dilute, granitic/metamorphic, snowmelt",
        "bboxes": {
            "CT": [-73.7, 41.0, -71.8, 42.1],
            "MA": [-73.5, 41.2, -69.9, 42.9],
            "NH_VT": [-73.4, 42.7, -71.0, 45.3],
            "ME": [-71.1, 43.0, -67.0, 47.5],
        },
        "target": 6,
    },
    "glaciolacustrine": {
        "description": "Prairie pothole, glacial clay, seasonal wetlands",
        "bboxes": {
            "ND": [-104.0, 46.0, -96.6, 49.0],
            "SD": [-104.0, 43.0, -96.4, 46.0],
        },
        "target": 5,
    },
    "blue_ridge": {
        "description": "Forested reference, steep terrain, crystalline geology",
        "bboxes": {
            "NC_mountains": [-84.3, 35.0, -81.5, 36.6],
            "WV": [-82.6, 37.2, -77.7, 40.6],
            "VA_blue_ridge": [-81.0, 36.5, -78.5, 39.5],
        },
        "target": 5,
    },
    "cold_semiarid": {
        "description": "Grassland steppe, snowmelt-dominated, sparse veg",
        "bboxes": {
            "WY": [-111.0, 41.0, -104.0, 45.0],
            "MT_east": [-111.0, 45.0, -104.0, 49.0],
        },
        "target": 5,
    },
    "deep_south_alluvial": {
        "description": "Mississippi floodplain, high organic, subtropical ag",
        "bboxes": {
            "MS_delta": [-91.7, 32.0, -88.8, 35.0],
            "AR": [-94.6, 33.0, -89.6, 36.5],
            "LA_north": [-94.0, 31.0, -91.0, 33.0],
        },
        "target": 5,
    },
}


def search_regime(regime_name: str, config: dict, existing: set) -> list[dict]:
    """Search for candidate sites in a regime."""
    candidates = []

    for region, bbox in config["bboxes"].items():
        try:
            ts, _ = waterdata.get_time_series_metadata(
                parameter_code="63680", bbox=bbox,
            )
            if ts is None or len(ts) == 0:
                continue

            usgs = ts[ts["monitoring_location_id"].str.startswith("USGS-")]
            has_data = usgs[usgs["begin"].notna()]
            sites = has_data["monitoring_location_id"].unique()

            for site in sites:
                if site in existing:
                    continue
                if site in [c["site_id"] for c in candidates]:
                    continue
                candidates.append({
                    "site_id": site,
                    "regime": regime_name,
                    "region": region,
                })
        except Exception as e:
            logger.warning(f"  {region}: search error - {str(e)[:60]}")
        time.sleep(2)

    logger.info(f"  {regime_name}: {len(candidates)} candidates from {len(config['bboxes'])} regions")
    return candidates


def verify_site(site_id: str) -> dict:
    """Quick verification: turbidity data exists + check SSC/TP availability."""
    result = {"site_id": site_id, "has_turbidity": False, "n_ssc": 0, "n_tp": 0}

    # Quick turbidity check (one year)
    for year_range in ["2023-01-01/2024-01-01", "2021-01-01/2022-01-01", "2019-01-01/2020-01-01"]:
        try:
            df, _ = waterdata.get_continuous(
                monitoring_location_id=site_id,
                parameter_code="63680",
                time=year_range,
            )
            if df is not None and len(df) > 100:
                result["has_turbidity"] = True
                result["n_turb_records"] = len(df)
                break
        except Exception:
            pass
        time.sleep(1)

    if not result["has_turbidity"]:
        return result

    # Check SSC
    try:
        df, _ = waterdata.get_samples(
            monitoringLocationIdentifier=site_id, usgsPCode="80154",
        )
        result["n_ssc"] = len(df) if df is not None else 0
    except Exception:
        pass
    time.sleep(1)

    # Check TP
    try:
        df, _ = waterdata.get_samples(
            monitoringLocationIdentifier=site_id, usgsPCode="00665",
        )
        result["n_tp"] = len(df) if df is not None else 0
    except Exception:
        pass
    time.sleep(1)

    return result


def main():
    if os.getenv("API_USGS_PAT"):
        logger.info("USGS API token found")
    else:
        logger.warning("No API_USGS_PAT!")

    existing = get_existing_sites()
    logger.info(f"Existing sites to exclude: {len(existing)}")

    all_candidates = []

    # Phase 1: Search each regime
    logger.info("\n=== PHASE 1: SEARCHING REGIMES ===")
    for regime_name, config in REGIMES.items():
        logger.info(f"\n{regime_name}: {config['description']}")
        candidates = search_regime(regime_name, config, existing)
        all_candidates.extend(candidates)

    logger.info(f"\nTotal candidates found: {len(all_candidates)}")

    # Phase 2: Verify turbidity + discrete data for top candidates per regime
    logger.info("\n=== PHASE 2: VERIFYING DATA AVAILABILITY ===")
    verified = []

    for regime_name, config in REGIMES.items():
        regime_candidates = [c for c in all_candidates if c["regime"] == regime_name]
        target = config["target"]
        # Verify up to 2x target to account for failures
        to_verify = regime_candidates[:target * 3]

        logger.info(f"\n{regime_name}: verifying {len(to_verify)} of {len(regime_candidates)} candidates (target: {target})")

        regime_verified = []
        for candidate in to_verify:
            if len(regime_verified) >= target + 2:  # +2 buffer
                break

            result = verify_site(candidate["site_id"])
            if result["has_turbidity"] and (result["n_ssc"] >= 10 or result["n_tp"] >= 10):
                candidate.update(result)
                regime_verified.append(candidate)
                logger.info(f"  VERIFIED: {candidate['site_id']} ({candidate['region']}): "
                           f"SSC={result['n_ssc']}, TP={result['n_tp']}")

        verified.extend(regime_verified[:target])
        logger.info(f"  {regime_name}: {len(regime_verified)} verified, keeping {min(len(regime_verified), target)}")

    # Save results
    df = pd.DataFrame(verified)
    out_path = DATA_DIR / "expansion_candidates.parquet"
    df.to_parquet(out_path, index=False)

    logger.info(f"\n{'='*60}")
    logger.info("EXPANSION SITE SEARCH RESULTS")
    logger.info(f"{'='*60}")
    logger.info(f"Total verified sites: {len(verified)}")

    for regime_name in REGIMES:
        regime_sites = [v for v in verified if v["regime"] == regime_name]
        logger.info(f"  {regime_name:25s}: {len(regime_sites)} sites")

    logger.info(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
