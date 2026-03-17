"""Assemble ML-ready datasets for multiple water quality parameters.

For each target parameter (TP, nitrate, orthoP):
1. Load discrete lab data using the generalized loader
2. Filter high-censoring sites (>50%)
3. Load continuous sensor data
4. QC filter and align discrete to continuous (±15 min)
5. Add secondary sensors, hydrograph features, cross-sensor, seasonality
6. Save as data/processed/{param_name}_paired.parquet

Uses the same alignment, QC, and feature engineering as the SSC pipeline.

Usage:
    python scripts/assemble_multi_param.py                    # all MVP params
    python scripts/assemble_multi_param.py --param total_phosphorus  # one param
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from murkml.data.align import align_samples
from murkml.data.discrete import load_discrete_param
from murkml.data.features import engineer_features
from murkml.data.qc import filter_continuous, filter_high_censoring

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"

# Continuous sensor parameters (same as SSC pipeline)
CONTINUOUS_PARAMS = {
    "63680": "turbidity",
    "00095": "conductance",
    "00300": "do",
    "00400": "ph",
    "00010": "temp",
    "00060": "discharge",
}

# MVP parameters to assemble (TDS dropped — only 16 pairable sites)
MVP_PARAMS = {
    "total_phosphorus": {
        "pcode": "00665",
        "min_pairable": 20,
        "primary_sensor": "turbidity",  # P binds to sediment
    },
    "nitrate_nitrite": {
        "pcode": "00631",
        "min_pairable": 20,
        "primary_sensor": "conductance",  # nutrient signal via ionic strength
    },
    "orthophosphate": {
        "pcode": "00671",
        "min_pairable": 20,
        "primary_sensor": "turbidity",  # particulate P
    },
}


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


def get_viable_sites(param_name: str, min_pairable: int = 20) -> list[str]:
    """Get sites with enough pairable samples from the temporal overlap audit."""
    audit_path = DATA_DIR / "temporal_overlap_audit.parquet"
    if not audit_path.exists():
        logger.error("No temporal overlap audit found! Run check_temporal_overlap.py first.")
        sys.exit(1)

    audit = pd.read_parquet(audit_path)
    param_audit = audit[
        (audit["param_name"] == param_name) & (audit["n_pairable"] >= min_pairable)
    ]
    sites = sorted(param_audit["site_id"].tolist())
    logger.info(f"{param_name}: {len(sites)} sites with ≥{min_pairable} pairable samples")
    return sites


def align_site_param(
    site_id: str,
    param_name: str,
    value_col: str = "value",
) -> pd.DataFrame:
    """Align discrete samples for a parameter with continuous sensor data.

    Same logic as assemble_dataset.align_site() but parameterized.
    """
    # Load discrete
    discrete = load_discrete_param(
        site_id=site_id,
        param_name=param_name,
        data_dir=DATA_DIR,
        value_col_out=value_col,
    )
    if discrete.empty:
        logger.warning(f"  No discrete data for {site_id}/{param_name}")
        return pd.DataFrame()

    # Load continuous turbidity (required anchor for alignment)
    turb = load_continuous(site_id, "63680")
    if turb.empty:
        logger.warning(f"  No continuous turbidity for {site_id}")
        return pd.DataFrame()

    # QC filter turbidity
    turb_filtered, qc_stats = filter_continuous(turb)

    # Prepare for alignment
    turb_clean = turb_filtered[["time", "value"]].copy()
    turb_clean.columns = ["datetime", "value"]

    # Preserve non-detect flags and hydro event before alignment
    nondetect_flags = discrete.set_index("datetime")["is_nondetect"]
    hydro_events = None
    if "hydro_event" in discrete.columns:
        hydro_events = discrete.set_index("datetime")["hydro_event"]

    disc_clean = discrete[["datetime", value_col]].copy()
    disc_clean.columns = ["datetime", "value"]

    # Align
    aligned = align_samples(
        continuous=turb_clean,
        discrete=disc_clean,
        max_gap=pd.Timedelta(minutes=15),
    )

    if aligned.empty:
        logger.warning(f"  No aligned samples for {site_id}/{param_name}")
        return pd.DataFrame()

    # Rename turbidity window columns
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
        if pcode == "63680":
            continue

        cont = load_continuous(site_id, pcode)
        if cont.empty:
            aligned[f"{pname}_instant"] = np.nan
            continue

        cont_filtered, _ = filter_continuous(cont)
        if cont_filtered.empty:
            aligned[f"{pname}_instant"] = np.nan
            continue

        cont_clean = cont_filtered[["time", "value"]].copy().reset_index(drop=True)
        cont_clean["time"] = pd.to_datetime(cont_clean["time"], utc=True)
        cont_clean = cont_clean.sort_values("time").reset_index(drop=True)

        instant_values = []
        for _, row in aligned.iterrows():
            anchor_time = row["sample_time"]
            time_diffs = (cont_clean["time"] - anchor_time).abs()
            min_idx = time_diffs.idxmin()
            if time_diffs.iloc[min_idx] <= pd.Timedelta(minutes=15):
                instant_values.append(cont_clean["value"].iloc[min_idx])
            else:
                instant_values.append(np.nan)

        aligned[f"{pname}_instant"] = instant_values

    # Add is_nondetect flag
    aligned["is_nondetect"] = aligned["sample_time"].map(
        lambda t: nondetect_flags.get(t, False) if t in nondetect_flags.index else False
    )

    # Add hydro_event
    if hydro_events is not None:
        aligned["hydro_event"] = aligned["sample_time"].map(
            lambda t: hydro_events.get(t, "Not Reported")
            if t in hydro_events.index else "Not Reported"
        )

    aligned["site_id"] = site_id
    return aligned


def assemble_parameter(param_name: str, param_config: dict) -> pd.DataFrame:
    """Full assembly pipeline for one parameter."""
    logger.info(f"\n{'='*60}")
    logger.info(f"ASSEMBLING: {param_name}")
    logger.info(f"{'='*60}")

    # Get viable sites
    sites = get_viable_sites(param_name, param_config["min_pairable"])
    if not sites:
        logger.error(f"No viable sites for {param_name}")
        return pd.DataFrame()

    # Process each site
    all_aligned = []
    for i, site_id in enumerate(sites):
        logger.info(f"[{i+1}/{len(sites)}] {site_id}")
        try:
            aligned = align_site_param(site_id, param_name)
            if not aligned.empty:
                all_aligned.append(aligned)
        except Exception as e:
            logger.error(f"  Error: {e}")
            continue

    if not all_aligned:
        logger.error(f"No aligned data for {param_name}")
        return pd.DataFrame()

    # Combine
    dataset = pd.concat(all_aligned, ignore_index=True)

    # Add log-transformed target
    dataset[f"{param_name}_log1p"] = np.log1p(dataset["lab_value"])

    # Apply feature engineering (hydrograph, cross-sensor, seasonality)
    dataset = engineer_features(dataset)

    # Filter high-censoring sites from final dataset
    dataset, dropped = filter_high_censoring(
        dataset, site_col="site_id", nondetect_col="is_nondetect", threshold=0.5
    )

    # Summary
    logger.info(f"\n{param_name} assembly complete:")
    logger.info(f"  Sites: {dataset['site_id'].nunique()}")
    logger.info(f"  Samples: {len(dataset)}")
    logger.info(f"  Non-detects: {dataset['is_nondetect'].sum()} ({dataset['is_nondetect'].mean()*100:.1f}%)")
    logger.info(f"  Value range: {dataset['lab_value'].min():.4f} - {dataset['lab_value'].max():.2f}")
    if dropped:
        logger.info(f"  Dropped high-censoring sites: {dropped}")

    # Save
    output_path = DATA_DIR / "processed" / f"{param_name}_paired.parquet"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_parquet(output_path, index=False)
    logger.info(f"  Saved: {output_path}")

    return dataset


def main():
    warnings.filterwarnings("ignore")

    parser = argparse.ArgumentParser(description="Assemble multi-parameter datasets")
    parser.add_argument("--param", type=str, default=None,
                        help="Single parameter to assemble (default: all MVP)")
    args = parser.parse_args()

    if args.param:
        if args.param not in MVP_PARAMS:
            logger.error(f"Unknown parameter: {args.param}. Options: {list(MVP_PARAMS.keys())}")
            sys.exit(1)
        params = {args.param: MVP_PARAMS[args.param]}
    else:
        params = MVP_PARAMS

    results = {}
    for param_name, config in params.items():
        df = assemble_parameter(param_name, config)
        if not df.empty:
            results[param_name] = {
                "sites": df["site_id"].nunique(),
                "samples": len(df),
                "nondetect_pct": df["is_nondetect"].mean() * 100,
            }

    # Final summary
    logger.info(f"\n{'='*60}")
    logger.info("ASSEMBLY SUMMARY")
    logger.info(f"{'='*60}")
    for param_name, stats in results.items():
        logger.info(
            f"  {param_name:25s}: {stats['sites']} sites, "
            f"{stats['samples']} samples, "
            f"{stats['nondetect_pct']:.1f}% non-detect"
        )


if __name__ == "__main__":
    main()
