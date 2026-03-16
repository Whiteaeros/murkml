"""Data Exploration: Visualize the assembled turbidity-SSC dataset.

Run after scripts/assemble_dataset.py has produced the paired dataset.
Generates plots saved to notebooks/figures/.

This is a plain Python script (not Jupyter) for reproducibility.
Can be converted to notebook with jupytext if needed.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

DATA_DIR = Path(__file__).parent.parent / "data"
FIG_DIR = Path(__file__).parent / "figures"
FIG_DIR.mkdir(exist_ok=True)


def main():
    # Load dataset
    dataset_path = DATA_DIR / "processed" / "turbidity_ssc_paired.parquet"
    if not dataset_path.exists():
        print(f"Dataset not found at {dataset_path}")
        print("Run scripts/assemble_dataset.py first.")
        sys.exit(1)

    df = pd.read_parquet(dataset_path)
    print(f"Dataset: {len(df)} samples across {df['site_id'].nunique()} sites")
    print(f"Columns: {list(df.columns)}")

    # --- Plot 1: Turbidity vs SSC by site ---
    fig, ax = plt.subplots(figsize=(10, 8))
    sites = df["site_id"].unique()
    colors = plt.cm.tab20(np.linspace(0, 1, len(sites)))

    for site, color in zip(sites, colors):
        site_df = df[df["site_id"] == site]
        ax.scatter(
            site_df["turbidity_instant"],
            site_df["lab_value"],
            alpha=0.5,
            s=15,
            color=color,
            label=site.replace("USGS-", ""),
        )

    ax.set_xlabel("Turbidity (FNU)")
    ax.set_ylabel("SSC (mg/L)")
    ax.set_title("Turbidity vs Suspended Sediment Concentration by Site")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=7, ncol=2)
    plt.tight_layout()
    fig.savefig(FIG_DIR / "turbidity_vs_ssc_by_site.png", dpi=150, bbox_inches="tight")
    print("Saved: turbidity_vs_ssc_by_site.png")
    plt.close()

    # --- Plot 2: Sample count per site ---
    fig, ax = plt.subplots(figsize=(12, 5))
    site_counts = df.groupby("site_id").size().sort_values(ascending=True)
    site_counts.plot(kind="barh", ax=ax, color="steelblue")
    ax.set_xlabel("Number of paired samples")
    ax.set_title("Paired Samples per Site")
    ax.set_yticklabels([s.replace("USGS-", "") for s in site_counts.index], fontsize=7)
    plt.tight_layout()
    fig.savefig(FIG_DIR / "samples_per_site.png", dpi=150, bbox_inches="tight")
    print("Saved: samples_per_site.png")
    plt.close()

    # --- Plot 3: SSC distribution ---
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    axes[0].hist(df["lab_value"], bins=50, color="sienna", edgecolor="black", alpha=0.7)
    axes[0].set_xlabel("SSC (mg/L)")
    axes[0].set_ylabel("Count")
    axes[0].set_title("SSC Distribution (natural scale)")

    axes[1].hist(df["ssc_log1p"], bins=50, color="teal", edgecolor="black", alpha=0.7)
    axes[1].set_xlabel("log1p(SSC)")
    axes[1].set_ylabel("Count")
    axes[1].set_title("SSC Distribution (log-transformed)")

    plt.tight_layout()
    fig.savefig(FIG_DIR / "ssc_distribution.png", dpi=150, bbox_inches="tight")
    print("Saved: ssc_distribution.png")
    plt.close()

    # --- Plot 4: Temporal coverage ---
    fig, ax = plt.subplots(figsize=(12, 6))
    for i, (site, group) in enumerate(df.groupby("site_id")):
        times = pd.to_datetime(group["sample_time"])
        ax.scatter(
            times,
            [i] * len(times),
            s=3,
            alpha=0.5,
            color="steelblue",
        )
    ax.set_yticks(range(df["site_id"].nunique()))
    ax.set_yticklabels(
        [s.replace("USGS-", "") for s in df["site_id"].unique()],
        fontsize=7,
    )
    ax.set_xlabel("Date")
    ax.set_title("Temporal Coverage of Paired Samples by Site")
    plt.tight_layout()
    fig.savefig(FIG_DIR / "temporal_coverage.png", dpi=150, bbox_inches="tight")
    print("Saved: temporal_coverage.png")
    plt.close()

    # --- Plot 5: Feature correlations ---
    feature_cols = [c for c in df.columns if c not in [
        "site_id", "sample_time", "lab_value", "ssc_log1p",
        "match_gap_seconds", "window_count",
    ] and df[c].dtype in ["float64", "float32", "int64"]]

    if len(feature_cols) > 2:
        corr = df[feature_cols + ["ssc_log1p"]].corr()["ssc_log1p"].drop("ssc_log1p")
        corr = corr.dropna().sort_values()

        fig, ax = plt.subplots(figsize=(10, max(6, len(corr) * 0.3)))
        colors = ["indianred" if v < 0 else "steelblue" for v in corr.values]
        corr.plot(kind="barh", ax=ax, color=colors)
        ax.set_xlabel("Correlation with log1p(SSC)")
        ax.set_title("Feature Correlations with Target")
        ax.axvline(x=0, color="black", linewidth=0.5)
        plt.tight_layout()
        fig.savefig(FIG_DIR / "feature_correlations.png", dpi=150, bbox_inches="tight")
        print("Saved: feature_correlations.png")
        plt.close()

    # --- Summary stats ---
    print("\n" + "=" * 60)
    print("DATASET SUMMARY")
    print("=" * 60)
    print(f"Total samples: {len(df)}")
    print(f"Sites: {df['site_id'].nunique()}")
    print(f"SSC range: {df['lab_value'].min():.0f} - {df['lab_value'].max():.0f} mg/L")
    print(f"SSC median: {df['lab_value'].median():.0f} mg/L")
    print(f"Turbidity range: {df['turbidity_instant'].min():.1f} - {df['turbidity_instant'].max():.1f} FNU")
    print(f"Match gap median: {df['match_gap_seconds'].median():.0f} seconds")

    print(f"\nPer-site summary:")
    for site, group in df.groupby("site_id"):
        print(
            f"  {site}: n={len(group)}, "
            f"SSC={group['lab_value'].median():.0f} median, "
            f"Turb={group['turbidity_instant'].median():.1f} median"
        )

    # Feature completeness
    print(f"\nFeature completeness:")
    for col in feature_cols:
        pct = (1 - df[col].isna().mean()) * 100
        print(f"  {col}: {pct:.0f}%")


if __name__ == "__main__":
    main()
