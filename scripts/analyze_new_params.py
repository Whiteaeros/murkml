"""Analyze downloaded discrete parameter data.

Computes:
1. Non-detect (censoring) rates per parameter per site
2. Summary statistics
3. Temporal overlap with continuous sensor data

Usage:
    python scripts/analyze_new_params.py
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"

PARAMS = {
    "total_phosphorus": "00665",
    "nitrate_nitrite": "00631",
    "tds_evaporative": "70300",
    "orthophosphate": "00671",
}


def load_discrete_data(param_name: str) -> dict[str, pd.DataFrame]:
    """Load all discrete files for a parameter, keyed by site_id."""
    disc_dir = DATA_DIR / "discrete"
    files = list(disc_dir.glob(f"*_{param_name}.parquet"))
    result = {}
    for f in files:
        site_id = f.name.replace(f"_{param_name}.parquet", "").replace("_", "-")
        df = pd.read_parquet(f)
        if len(df) > 0:
            result[site_id] = df
    return result


def analyze_censoring(data: dict[str, pd.DataFrame], param_name: str) -> pd.DataFrame:
    """Analyze non-detect / censoring rates.

    Uses Result_ResultDetectionCondition = 'Not Detected' as the primary indicator.
    Falls back to checking DetectionLimit_TypeA = 'Censoring Level'.
    """
    rows = []
    for site_id, df in data.items():
        n_total = len(df)
        n_nondetect = 0

        # Primary: Result_ResultDetectionCondition
        if "Result_ResultDetectionCondition" in df.columns:
            nd_mask = df["Result_ResultDetectionCondition"].astype(str).str.lower().str.contains(
                "not detect", na=False
            )
            n_nondetect = nd_mask.sum()
        # Fallback: DetectionLimit_TypeA = 'Censoring Level'
        elif "DetectionLimit_TypeA" in df.columns:
            cens_mask = df["DetectionLimit_TypeA"].astype(str).str.lower().str.contains(
                "censoring", na=False
            )
            n_nondetect = cens_mask.sum()

        # Get median detection limit for censored values
        median_dl = None
        if n_nondetect > 0 and "DetectionLimit_MeasureA" in df.columns:
            dl_vals = df.loc[
                df["Result_ResultDetectionCondition"].astype(str).str.lower().str.contains(
                    "not detect", na=False
                ) if "Result_ResultDetectionCondition" in df.columns else pd.Series(dtype=bool),
                "DetectionLimit_MeasureA"
            ]
            if len(dl_vals) > 0:
                median_dl = dl_vals.median()

        pct = (n_nondetect / n_total * 100) if n_total > 0 else 0

        rows.append({
            "site_id": site_id,
            "param_name": param_name,
            "n_samples": n_total,
            "n_nondetect": n_nondetect,
            "pct_censored": round(pct, 1),
            "median_detection_limit": median_dl,
        })

    return pd.DataFrame(rows)


def main():
    all_censoring = []

    for param_name, pcode in PARAMS.items():
        data = load_discrete_data(param_name)
        if not data:
            logger.info(f"{param_name}: no data files found")
            continue

        logger.info(f"\n{'='*60}")
        logger.info(f"{param_name.upper()} (pcode {pcode})")
        logger.info(f"{'='*60}")
        logger.info(f"Sites: {len(data)}")

        total_samples = sum(len(df) for df in data.values())
        logger.info(f"Total samples: {total_samples}")

        # Censoring analysis
        cens = analyze_censoring(data, param_name)
        all_censoring.append(cens)

        mean_pct = cens["pct_censored"].mean()
        max_pct = cens["pct_censored"].max()
        sites_over_10 = (cens["pct_censored"] > 10).sum()

        logger.info(f"Censoring: mean={mean_pct:.1f}%, max={max_pct:.1f}%")
        logger.info(f"Sites >10% censored: {sites_over_10}")

        if sites_over_10 > 0:
            high_cens = cens[cens["pct_censored"] > 10].sort_values("pct_censored", ascending=False)
            for _, row in high_cens.iterrows():
                logger.info(f"  {row['site_id']}: {row['pct_censored']:.1f}% "
                           f"({row['n_nondetect']}/{row['n_samples']})")

        # Sample column inspection (first file)
        first_site = list(data.keys())[0]
        first_df = data[first_site]
        logger.info(f"\nColumn names ({first_site}):")
        for col in first_df.columns:
            logger.info(f"  {col}")

    # Save combined censoring report
    if all_censoring:
        combined = pd.concat(all_censoring, ignore_index=True)
        combined.to_parquet(DATA_DIR / "censoring_rates.parquet", index=False)
        logger.info(f"\nSaved censoring rates: data/censoring_rates.parquet")

        # Summary table
        logger.info("\n" + "="*60)
        logger.info("CENSORING SUMMARY (Krishnamurthy threshold: DL/2 OK if <10%)")
        logger.info("="*60)
        for param_name in PARAMS:
            subset = combined[combined["param_name"] == param_name]
            if len(subset) == 0:
                continue
            mean_pct = subset["pct_censored"].mean()
            n_sites = len(subset)
            n_ok = (subset["pct_censored"] < 10).sum()
            status = "OK (DL/2)" if mean_pct < 10 else "INVESTIGATE"
            logger.info(f"  {param_name:25s}: {mean_pct:5.1f}% avg censored, "
                       f"{n_ok}/{n_sites} sites <10% — {status}")


if __name__ == "__main__":
    main()
