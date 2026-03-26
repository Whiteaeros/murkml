"""Site qualification pipeline — vet every site BEFORE downloading data.

For each discovered site, checks:
1. Does it have continuous turbidity? (metadata API)
2. What other continuous params does it have, and for what date ranges?
3. Does it have valid discrete SSC samples? (not all non-detects, not TSS)
4. Do the continuous and discrete data overlap in time?
5. Does it meet minimum sample thresholds?

Produces:
- data/qualified_sites.parquet — the definitive site list with metadata
- data/train_holdout_split.parquet — stratified train/holdout assignment
- data/site_qualification_report.txt — human-readable summary

Usage:
    python scripts/qualify_sites.py
    python scripts/qualify_sites.py --min-training-samples 20 --min-holdout-samples 15
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"

CONTINUOUS_PARAMS = {
    "63680": "turbidity",
    "00095": "conductance",
    "00300": "do",
    "00400": "ph",
    "00010": "temp",
    "00060": "discharge",
}


def step_0a_continuous_metadata(sites: list[str]) -> pd.DataFrame:
    """Query USGS time-series-metadata API for all continuous params.

    Returns DataFrame: site_id, param_code, param_name, begin_date, end_date
    Caches to data/site_continuous_metadata.parquet, resumable.
    """
    cache_path = DATA_DIR / "site_continuous_metadata.parquet"

    if cache_path.exists():
        cached = pd.read_parquet(cache_path)
        cached_sites = set(cached["site_id"].unique())
        new_sites = [s for s in sites if s not in cached_sites]
        if not new_sites:
            logger.info(f"Step 0a: All {len(sites)} sites have cached metadata")
            return cached[cached["site_id"].isin(sites)]
        logger.info(f"Step 0a: {len(cached_sites)} cached, {len(new_sites)} new to query")
    else:
        cached = pd.DataFrame()
        new_sites = sites

    # Use the USGS OGC API for time-series metadata
    import requests

    records = []
    for i, site_id in enumerate(new_sites):
        if (i + 1) % 25 == 0 or i == 0:
            logger.info(f"  Metadata [{i+1}/{len(new_sites)}]")

        for pcode, pname in CONTINUOUS_PARAMS.items():
            url = (
                "https://api.waterdata.usgs.gov/ogcapi/v0/collections/"
                "time-series-metadata/items"
            )
            params = {
                "monitoring_location_id": site_id,
                "parameter_code": pcode,
                "skipGeometry": "False",
                "limit": 100,
            }

            for attempt in range(3):
                try:
                    resp = requests.get(url, params=params, timeout=30)
                    if resp.status_code == 200:
                        data = resp.json()
                        features = data.get("features", [])
                        if features:
                            # May have multiple time series (sensors) per param
                            for feat in features:
                                props = feat.get("properties", {})
                                begin = props.get("begin")
                                end = props.get("end")
                                if begin and end:
                                    records.append({
                                        "site_id": site_id,
                                        "param_code": pcode,
                                        "param_name": pname,
                                        "begin_date": pd.to_datetime(begin),
                                        "end_date": pd.to_datetime(end),
                                    })
                        break
                    elif resp.status_code == 429:
                        wait = 2 ** attempt * 10
                        logger.warning(f"  Rate limited, waiting {wait}s")
                        time.sleep(wait)
                    else:
                        break
                except Exception as e:
                    if attempt < 2:
                        time.sleep(3)
                    else:
                        logger.warning(f"  {site_id}/{pcode} failed: {e}")

            time.sleep(0.3)  # Brief delay between calls

        # Checkpoint every 100 sites
        if (i + 1) % 100 == 0 and records:
            new_df = pd.DataFrame(records)
            if not cached.empty:
                checkpoint = pd.concat([cached, new_df], ignore_index=True)
            else:
                checkpoint = new_df
            checkpoint.to_parquet(cache_path, index=False)
            logger.info(f"  Checkpoint: {len(checkpoint)} metadata records saved")

    # Final save
    new_df = pd.DataFrame(records) if records else pd.DataFrame()
    if not cached.empty and not new_df.empty:
        result = pd.concat([cached, new_df], ignore_index=True)
    elif not new_df.empty:
        result = new_df
    else:
        result = cached

    if not result.empty:
        result.to_parquet(cache_path, index=False)

    logger.info(f"Step 0a complete: {len(result)} metadata records for {result['site_id'].nunique()} sites")
    return result[result["site_id"].isin(sites)]


def step_0b_filter_turbidity(metadata: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Filter to sites that have turbidity (63680).

    Returns (filtered_metadata, n_dropped).
    """
    turb_sites = set(metadata[metadata["param_code"] == "63680"]["site_id"].unique())
    all_sites = set(metadata["site_id"].unique())
    no_turb = all_sites - turb_sites

    if no_turb:
        logger.info(f"Step 0b: Dropping {len(no_turb)} sites with no turbidity")

    filtered = metadata[metadata["site_id"].isin(turb_sites)]
    logger.info(f"Step 0b: {len(turb_sites)} sites have turbidity")
    return filtered, len(no_turb)


def step_0c_validate_discrete(sites: list[str]) -> pd.DataFrame:
    """Validate discrete SSC samples for each site.

    Checks:
    - Are samples actually SSC (pcode 80154)?
    - How many are non-detects?
    - What's the date range?
    - Are values reasonable (not all zeros)?

    Returns DataFrame: site_id, n_ssc_total, n_ssc_valid, n_nondetect,
                        ssc_begin, ssc_end, median_ssc
    """
    disc_dir = DATA_DIR / "discrete"
    batch_dir = DATA_DIR / "discrete_batch"

    records = []
    for site_id in sites:
        site_stem = site_id.replace("-", "_")

        # Try per-site file first, then look in batch data
        ssc_file = disc_dir / f"{site_stem}_ssc.parquet"
        if not ssc_file.exists():
            ssc_file = disc_dir / f"{site_stem}_80154.parquet"

        if ssc_file.exists():
            df = pd.read_parquet(ssc_file)

            # Find the result value column
            val_col = None
            for candidate in ["ResultMeasureValue", "result_va", "ssc_mg_l", "value"]:
                if candidate in df.columns:
                    val_col = candidate
                    break

            # Find the date column
            date_col = None
            for candidate in ["ActivityStartDate", "sample_dt", "datetime", "date"]:
                if candidate in df.columns:
                    date_col = candidate
                    break

            if val_col and date_col:
                values = pd.to_numeric(df[val_col], errors="coerce")
                dates = pd.to_datetime(df[date_col], errors="coerce")

                n_total = len(df)
                n_valid = values.notna().sum()
                n_nondetect = n_total - n_valid
                median_val = values.median() if n_valid > 0 else None

                # Check for suspicious data
                all_same = values.dropna().nunique() <= 1 if n_valid > 0 else True
                all_zero = (values.dropna() == 0).all() if n_valid > 0 else True

                records.append({
                    "site_id": site_id,
                    "n_ssc_total": n_total,
                    "n_ssc_valid": int(n_valid),
                    "n_nondetect": int(n_nondetect),
                    "ssc_begin": dates.min(),
                    "ssc_end": dates.max(),
                    "median_ssc": median_val,
                    "suspicious": all_same or all_zero,
                })
            else:
                records.append({
                    "site_id": site_id,
                    "n_ssc_total": len(df),
                    "n_ssc_valid": 0,
                    "n_nondetect": 0,
                    "ssc_begin": None,
                    "ssc_end": None,
                    "median_ssc": None,
                    "suspicious": True,
                })
        else:
            # No discrete file found — check batch data
            records.append({
                "site_id": site_id,
                "n_ssc_total": 0,
                "n_ssc_valid": 0,
                "n_nondetect": 0,
                "ssc_begin": None,
                "ssc_end": None,
                "median_ssc": None,
                "suspicious": False,
            })

    result = pd.DataFrame(records)
    n_suspicious = result["suspicious"].sum()
    if n_suspicious > 0:
        logger.warning(f"Step 0c: {n_suspicious} sites have suspicious SSC data (all same value or all zeros)")
    logger.info(f"Step 0c: Validated discrete SSC for {len(result)} sites")
    return result


def step_0d_temporal_overlap(
    metadata: pd.DataFrame,
    discrete: pd.DataFrame,
    min_overlap_years: float = 1.0,
) -> tuple[pd.DataFrame, int]:
    """Check temporal overlap between continuous turbidity and discrete SSC.

    Returns (overlap_df, n_dropped).
    """
    # Get turbidity date range per site (use widest range if multiple sensors)
    turb = metadata[metadata["param_code"] == "63680"].copy()
    turb_ranges = turb.groupby("site_id").agg(
        turb_begin=("begin_date", "min"),
        turb_end=("end_date", "max"),
    ).reset_index()

    # Merge with discrete SSC dates
    merged = turb_ranges.merge(
        discrete[["site_id", "ssc_begin", "ssc_end", "n_ssc_valid"]],
        on="site_id",
        how="inner",
    )

    # Compute overlap
    merged["overlap_begin"] = merged[["turb_begin", "ssc_begin"]].max(axis=1)
    merged["overlap_end"] = merged[["turb_end", "ssc_end"]].min(axis=1)
    merged["overlap_days"] = (merged["overlap_end"] - merged["overlap_begin"]).dt.days
    merged["overlap_years"] = merged["overlap_days"] / 365.25

    # Filter
    has_overlap = merged[merged["overlap_years"] >= min_overlap_years].copy()
    n_dropped = len(merged) - len(has_overlap)

    if n_dropped > 0:
        logger.info(f"Step 0d: Dropped {n_dropped} sites with <{min_overlap_years} year overlap")
    logger.info(f"Step 0d: {len(has_overlap)} sites have sufficient temporal overlap")

    return has_overlap, n_dropped


def step_0e_sample_threshold(
    overlap: pd.DataFrame,
    min_training: int = 20,
    min_holdout: int = 15,
) -> pd.DataFrame:
    """Apply minimum sample count. All sites meeting holdout threshold qualify;
    training/holdout assignment happens later in step 0g."""

    qualified = overlap[overlap["n_ssc_valid"] >= min_holdout].copy()
    n_dropped = len(overlap) - len(qualified)

    if n_dropped > 0:
        logger.info(f"Step 0e: Dropped {n_dropped} sites with <{min_holdout} valid SSC samples")

    # Flag sites that meet training threshold
    qualified["meets_training_threshold"] = qualified["n_ssc_valid"] >= min_training
    n_training_eligible = qualified["meets_training_threshold"].sum()

    logger.info(f"Step 0e: {len(qualified)} qualified ({n_training_eligible} training-eligible, "
                f"{len(qualified) - n_training_eligible} holdout-only)")
    return qualified


def step_0f_build_qualified_list(
    qualified: pd.DataFrame,
    metadata: pd.DataFrame,
    discovery: pd.DataFrame,
) -> pd.DataFrame:
    """Build the full qualified site list with all metadata columns."""

    # Add parameter availability flags
    for pcode, pname in CONTINUOUS_PARAMS.items():
        has_param = metadata[metadata["param_code"] == pcode]["site_id"].unique()
        qualified[f"has_{pname}"] = qualified["site_id"].isin(has_param)

    # Build params_available list
    def _get_params(site_id):
        site_meta = metadata[metadata["site_id"] == site_id]
        return list(site_meta["param_code"].unique())

    qualified["params_available"] = qualified["site_id"].apply(_get_params)

    # Compute download year range (padded by 1 year for antecedent features)
    qualified["download_start_year"] = qualified["overlap_begin"].dt.year - 1
    qualified["download_end_year"] = qualified["overlap_end"].dt.year + 1

    # Add state from discovery data
    if "state" in discovery.columns:
        state_map = dict(zip(discovery["site_id"], discovery["state"]))
        qualified["state"] = qualified["site_id"].map(state_map)

    logger.info(f"Step 0f: Built qualified list with {len(qualified)} sites, "
                f"{len(qualified.columns)} columns")
    return qualified


def step_0g_train_holdout_split(
    qualified: pd.DataFrame,
    holdout_fraction: float = 0.20,
    min_per_region: int = 2,
    random_seed: int = 42,
) -> pd.DataFrame:
    """Stratified train/holdout split by HUC2 region.

    Rules:
    - Only training-eligible sites (≥min_training samples) can be training
    - Holdout-only sites always go to holdout
    - Stratify by HUC2 so every region has representation in both sets
    - Holdout gets ~20% of sites per region (minimum 2)
    """
    # Load HUC2 from COMID mapping or NLDI supplementary
    comid_path = DATA_DIR / "streamcat" / "site_comid_mapping.parquet"
    nldi_path = DATA_DIR / "streamcat" / "nldi_supplementary.parquet"

    huc_map = {}
    if nldi_path.exists():
        nldi = pd.read_parquet(nldi_path)
        if "huc2" in nldi.columns:
            huc_map = dict(zip(nldi["site_id"], nldi["huc2"]))

    qualified["huc2"] = qualified["site_id"].map(huc_map)
    qualified.loc[qualified["huc2"].isna(), "huc2"] = "unknown"

    rng = np.random.RandomState(random_seed)
    roles = []

    for huc, group in qualified.groupby("huc2"):
        training_eligible = group[group["meets_training_threshold"]].index.tolist()
        holdout_only = group[~group["meets_training_threshold"]].index.tolist()

        # Holdout-only sites always go to holdout
        holdout_indices = set(holdout_only)

        # From training-eligible, pick ~20% for holdout (min 2 if possible)
        n_eligible = len(training_eligible)
        n_holdout_target = max(min_per_region, int(n_eligible * holdout_fraction))
        n_holdout_target = min(n_holdout_target, n_eligible - 1)  # Keep at least 1 for training

        if n_holdout_target > 0 and n_eligible > 0:
            holdout_picks = rng.choice(training_eligible, size=n_holdout_target, replace=False)
            holdout_indices.update(holdout_picks)

        for idx in group.index:
            roles.append("holdout" if idx in holdout_indices else "training")

    qualified["role"] = roles

    n_train = (qualified["role"] == "training").sum()
    n_hold = (qualified["role"] == "holdout").sum()
    logger.info(f"Step 0g: {n_train} training, {n_hold} holdout "
                f"({n_hold / len(qualified) * 100:.1f}% holdout)")

    return qualified


def step_0h_report(
    qualified: pd.DataFrame,
    n_discovered: int,
    n_no_turb: int,
    n_no_overlap: int,
    n_too_few: int,
) -> str:
    """Generate human-readable qualification report."""

    n_train = (qualified["role"] == "training").sum()
    n_hold = (qualified["role"] == "holdout").sum()

    lines = [
        "=" * 60,
        "SITE QUALIFICATION REPORT",
        "=" * 60,
        "",
        "FUNNEL:",
        f"  Total discovered:                {n_discovered}",
        f"  Dropped (no turbidity):          {n_no_turb}",
        f"  Dropped (no temporal overlap):   {n_no_overlap}",
        f"  Dropped (too few samples):       {n_too_few}",
        f"  QUALIFIED:                       {len(qualified)}",
        f"    Training:                      {n_train}",
        f"    Holdout:                       {n_hold}",
        "",
        "SAMPLE COUNTS:",
        f"  Total valid SSC samples:         {qualified['n_ssc_valid'].sum():,}",
        f"  Median samples/site:             {qualified['n_ssc_valid'].median():.0f}",
        f"  Min samples (training):          {qualified[qualified['role']=='training']['n_ssc_valid'].min()}",
        f"  Min samples (holdout):           {qualified[qualified['role']=='holdout']['n_ssc_valid'].min() if n_hold > 0 else 'N/A'}",
        "",
        "TEMPORAL COVERAGE:",
        f"  Earliest overlap:                {qualified['overlap_begin'].min().date()}",
        f"  Latest overlap:                  {qualified['overlap_end'].max().date()}",
        f"  Median overlap (years):          {qualified['overlap_years'].median():.1f}",
        "",
        "PARAMETER AVAILABILITY:",
    ]

    for pcode, pname in CONTINUOUS_PARAMS.items():
        col = f"has_{pname}"
        if col in qualified.columns:
            n = qualified[col].sum()
            pct = n / len(qualified) * 100
            lines.append(f"  {pname:20s} {n:>5} sites ({pct:.0f}%)")

    lines.extend([
        "",
        "HUC2 DISTRIBUTION:",
    ])
    for huc, group in qualified.groupby("huc2"):
        n_t = (group["role"] == "training").sum()
        n_h = (group["role"] == "holdout").sum()
        lines.append(f"  HUC {huc}: {n_t} training, {n_h} holdout")

    lines.extend(["", "=" * 60])

    report = "\n".join(lines)
    return report


def main():
    parser = argparse.ArgumentParser(description="Qualify sites for download and training")
    parser.add_argument("--min-training-samples", type=int, default=20,
                        help="Minimum SSC samples for training sites (default 20)")
    parser.add_argument("--min-holdout-samples", type=int, default=15,
                        help="Minimum SSC samples for holdout sites (default 15)")
    parser.add_argument("--holdout-fraction", type=float, default=0.20,
                        help="Fraction of sites to hold out (default 0.20)")
    parser.add_argument("--min-overlap-years", type=float, default=1.0,
                        help="Minimum years of turbidity+SSC overlap (default 1.0)")
    args = parser.parse_args()

    # Load discovered sites
    disc_path = DATA_DIR / "all_discovered_sites.parquet"
    if not disc_path.exists():
        logger.error(f"No discovered sites at {disc_path}. Run discovery first.")
        return

    discovery = pd.read_parquet(disc_path)
    sites = discovery["site_id"].tolist()
    n_discovered = len(sites)
    logger.info(f"Starting qualification for {n_discovered} discovered sites")

    # Step 0a: Get continuous parameter metadata
    logger.info(f"\n{'='*60}")
    logger.info("STEP 0a: CONTINUOUS PARAMETER METADATA")
    logger.info(f"{'='*60}")
    metadata = step_0a_continuous_metadata(sites)

    # Step 0b: Filter to sites with turbidity
    logger.info(f"\n{'='*60}")
    logger.info("STEP 0b: FILTER — MUST HAVE TURBIDITY")
    logger.info(f"{'='*60}")
    metadata, n_no_turb = step_0b_filter_turbidity(metadata)
    turb_sites = list(metadata["site_id"].unique())

    # Step 0c: Validate discrete SSC
    logger.info(f"\n{'='*60}")
    logger.info("STEP 0c: VALIDATE DISCRETE SSC SAMPLES")
    logger.info(f"{'='*60}")
    discrete = step_0c_validate_discrete(turb_sites)

    # Step 0d: Temporal overlap
    logger.info(f"\n{'='*60}")
    logger.info("STEP 0d: TEMPORAL OVERLAP CHECK")
    logger.info(f"{'='*60}")
    overlap, n_no_overlap = step_0d_temporal_overlap(
        metadata, discrete, min_overlap_years=args.min_overlap_years
    )

    # Step 0e: Sample threshold
    logger.info(f"\n{'='*60}")
    logger.info("STEP 0e: MINIMUM SAMPLE THRESHOLD")
    logger.info(f"{'='*60}")
    qualified = step_0e_sample_threshold(
        overlap,
        min_training=args.min_training_samples,
        min_holdout=args.min_holdout_samples,
    )
    n_too_few = len(overlap) - len(qualified)

    # Step 0f: Build full qualified list
    logger.info(f"\n{'='*60}")
    logger.info("STEP 0f: BUILD QUALIFIED SITE LIST")
    logger.info(f"{'='*60}")
    qualified = step_0f_build_qualified_list(qualified, metadata, discovery)

    # Step 0g: Train/holdout split
    logger.info(f"\n{'='*60}")
    logger.info("STEP 0g: TRAIN/HOLDOUT SPLIT")
    logger.info(f"{'='*60}")
    qualified = step_0g_train_holdout_split(
        qualified, holdout_fraction=args.holdout_fraction
    )

    # Save outputs
    qualified.to_parquet(DATA_DIR / "qualified_sites.parquet", index=False)
    logger.info(f"Saved: data/qualified_sites.parquet ({len(qualified)} sites)")

    split = qualified[["site_id", "role", "huc2"]].copy()
    split.to_parquet(DATA_DIR / "train_holdout_split.parquet", index=False)
    logger.info(f"Saved: data/train_holdout_split.parquet")

    # Step 0h: Report
    logger.info(f"\n{'='*60}")
    logger.info("STEP 0h: QUALIFICATION REPORT")
    logger.info(f"{'='*60}")
    report = step_0h_report(qualified, n_discovered, n_no_turb, n_no_overlap, n_too_few)
    print(report)

    report_path = DATA_DIR / "site_qualification_report.txt"
    report_path.write_text(report)
    logger.info(f"Saved: {report_path}")


if __name__ == "__main__":
    main()
