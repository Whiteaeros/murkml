"""Error analysis: which sites does the SSC model fail on and why?

Computes per-site metrics for holdout predictions, merges with watershed
attributes, and identifies correlates of model performance.

Usage:
    python scripts/error_analysis.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from murkml.data.attributes import load_streamcat_attrs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = DATA_DIR / "results"

MIN_SAMPLES = 5  # flag sites with fewer than this


# ── per-site metrics ────────────────────────────────────────────────────
def _r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - y_true.mean()) ** 2)
    if ss_tot == 0:
        return np.nan
    return 1 - ss_res / ss_tot


def _kge(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    if y_true.std() == 0 or y_pred.std() == 0:
        return np.nan
    r = np.corrcoef(y_true, y_pred)[0, 1]
    alpha = y_pred.std() / y_true.std()
    beta = y_pred.mean() / y_true.mean() if y_true.mean() != 0 else np.nan
    if np.isnan(r) or np.isnan(beta):
        return np.nan
    return 1 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2)


def compute_site_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Compute R², slope, RMSE, KGE, bias for each site in native mg/L."""
    rows = []
    for site_id, grp in df.groupby("site_id"):
        yt = grp["y_true_native_mgL"].values
        yp = grp["y_pred_native_mgL"].values
        n = len(yt)
        r2 = _r2(yt, yp)
        rmse = np.sqrt(np.mean((yt - yp) ** 2))
        bias = np.mean(yp - yt)
        kge = _kge(yt, yp)

        # OLS slope (pred vs true)
        if yt.std() > 0:
            slope = np.polyfit(yt, yp, 1)[0]
        else:
            slope = np.nan

        rows.append(
            {
                "site_id": site_id,
                "n_samples": n,
                "r2": r2,
                "slope": slope,
                "rmse_mgL": rmse,
                "kge": kge,
                "bias_mgL": bias,
                "low_sample_flag": n < MIN_SAMPLES,
            }
        )
    return pd.DataFrame(rows)


# ── attribute correlation ───────────────────────────────────────────────
ATTR_COLS_OF_INTEREST = [
    "drainage_area_km2",
    "precip_mean_mm",
    "temp_mean_c",
    "elevation_m",
    "forest_pct",
    "agriculture_pct",
    "developed_pct",
    "wetland_pct",
    "clay_pct",
    "sand_pct",
    "baseflow_index",
    "slope_pct",
    "dam_density",
    "pop_density",
    "fertilizer_rate",
    "soil_permeability",
]


def spearman_correlations(
    merged: pd.DataFrame, metric: str = "r2"
) -> pd.DataFrame:
    """Spearman rank correlations between site attributes and a metric."""
    results = []
    for col in ATTR_COLS_OF_INTEREST:
        if col not in merged.columns:
            continue
        valid = merged[[col, metric]].dropna()
        if len(valid) < 5:
            continue
        rho, pval = stats.spearmanr(valid[col], valid[metric])
        results.append({"attribute": col, "rho": rho, "p_value": pval})
    out = pd.DataFrame(results).sort_values("p_value")
    return out


# ── reporting ───────────────────────────────────────────────────────────
def print_report(merged: pd.DataFrame, corr: pd.DataFrame) -> None:
    print("\n" + "=" * 60)
    print("=== ERROR ANALYSIS ===")
    print("=" * 60)

    # per-region
    print("\nPer-region performance (HUC2):")
    if "huc2" in merged.columns:
        region = (
            merged.groupby("huc2")
            .agg(
                n_sites=("r2", "count"),
                median_r2=("r2", "median"),
                median_kge=("kge", "median"),
                median_rmse=("rmse_mgL", "median"),
            )
            .sort_values("median_r2", ascending=False)
        )
        for huc, row in region.iterrows():
            print(
                f"  Region {huc}: {int(row['n_sites'])} sites, "
                f"median R²={row['median_r2']:.3f}, "
                f"median KGE={row['median_kge']:.3f}, "
                f"median RMSE={row['median_rmse']:.1f} mg/L"
            )
    else:
        print("  (huc2 column not available)")

    # correlations
    print("\nTop correlates with model R² (Spearman):")
    for _, row in corr.head(15).iterrows():
        sig = "*" if row["p_value"] < 0.05 else ""
        print(
            f"  {row['attribute']:25s}: rho={row['rho']:+.3f}, "
            f"p={row['p_value']:.4f}{sig}"
        )

    # best / worst
    reliable = merged[~merged["low_sample_flag"]].copy()
    if len(reliable) == 0:
        reliable = merged.copy()

    top10 = reliable.nlargest(10, "r2")
    bot10 = reliable.nsmallest(10, "r2")

    def _site_line(row: pd.Series) -> str:
        parts = [f"R²={row['r2']:.3f}"]
        parts.append(f"KGE={row['kge']:.3f}")
        parts.append(f"n={int(row['n_samples'])}")
        if "drainage_area_km2" in row.index and pd.notna(
            row.get("drainage_area_km2")
        ):
            parts.append(f"drain={row['drainage_area_km2']:.0f}km²")
        for lc in ["forest_pct", "agriculture_pct", "developed_pct"]:
            if lc in row.index and pd.notna(row.get(lc)):
                short = lc.replace("_pct", "")
                parts.append(f"{short}={row[lc]:.0f}%")
        if "huc2" in row.index and pd.notna(row.get("huc2")):
            parts.append(f"region={row['huc2']}")
        return ", ".join(parts)

    print(f"\n10 Best sites (of {len(reliable)} with >={MIN_SAMPLES} samples):")
    for _, row in top10.iterrows():
        print(f"  {row['site_id']}: {_site_line(row)}")

    print(f"\n10 Worst sites (of {len(reliable)} with >={MIN_SAMPLES} samples):")
    for _, row in bot10.iterrows():
        print(f"  {row['site_id']}: {_site_line(row)}")

    # low-sample warning
    low = merged[merged["low_sample_flag"]]
    if len(low) > 0:
        print(f"\nWarning: {len(low)} sites have <{MIN_SAMPLES} samples "
              f"(metrics unreliable):")
        for _, row in low.iterrows():
            print(f"  {row['site_id']}: n={int(row['n_samples'])}, R²={row['r2']:.3f}")

    print()


# ── main ────────────────────────────────────────────────────────────────
def main() -> None:
    # 1. Load predictions
    preds_path = RESULTS_DIR / "prediction_intervals.parquet"
    preds = pd.read_parquet(preds_path)
    logger.info("Loaded %d predictions for %d sites", len(preds), preds["site_id"].nunique())

    # 2. Compute per-site metrics
    site_metrics = compute_site_metrics(preds)
    logger.info(
        "Per-site R² — median=%.3f, mean=%.3f, min=%.3f, max=%.3f",
        site_metrics["r2"].median(),
        site_metrics["r2"].mean(),
        site_metrics["r2"].min(),
        site_metrics["r2"].max(),
    )

    # 3. Load site attributes
    basic_attrs = pd.read_parquet(DATA_DIR / "site_attributes.parquet")
    streamcat = load_streamcat_attrs(DATA_DIR)

    # Merge StreamCat first (it has more columns), then fill gaps from basic
    attrs = streamcat.copy()
    # basic_attrs may have columns not in StreamCat (altitude_ft, latitude, longitude)
    extra_cols = [c for c in basic_attrs.columns if c not in attrs.columns or c == "site_id"]
    if len(extra_cols) > 1:  # more than just site_id
        attrs = attrs.merge(
            basic_attrs[extra_cols], on="site_id", how="outer"
        )

    # 4. Merge metrics with attributes
    merged = site_metrics.merge(attrs, on="site_id", how="left")
    logger.info(
        "Merged: %d sites, %d have StreamCat attributes",
        len(merged),
        merged["precip_mean_mm"].notna().sum(),
    )

    # 5. Correlations
    corr = spearman_correlations(merged, metric="r2")

    # 6. Report
    print_report(merged, corr)

    # 7. Save
    out_path = RESULTS_DIR / "error_analysis.parquet"
    merged.to_parquet(out_path, index=False)
    logger.info("Saved error analysis to %s", out_path)


if __name__ == "__main__":
    main()
