#!/usr/bin/env python
"""Site Contribution Analysis — Out-of-Bag Random Subset Scoring.

Identifies which training sites help the model generalize (anchors) vs
which inject noise (anti-anchors). Uses out-of-bag evaluation: train on
100 random sites, predict the other 184. Score = mean(R²_with) - mean(R²_without).

Usage:
    python scripts/site_contribution_analysis.py
    python scripts/site_contribution_analysis.py --n-subsets 50 --subset-size 100
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool
from scipy.special import boxcox1p
from sklearn.model_selection import GroupShuffleSplit

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = DATA_DIR / "results" / "site_contribution"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from murkml.data.attributes import build_feature_tiers, load_streamcat_attrs
from murkml.evaluate.metrics import safe_inv_boxcox1p

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)


def load_training_data(drop_features: list[str]) -> tuple[pd.DataFrame, list[str], list[str], list[int]]:
    """Load Tier C training data with features, excluding vault + validation."""
    paired = pd.read_parquet(DATA_DIR / "processed" / "turbidity_ssc_paired.parquet")
    basic_attrs = pd.read_parquet(DATA_DIR / "site_attributes.parquet")
    watershed_attrs = load_streamcat_attrs(DATA_DIR)

    # Merge SGMC
    sgmc_path = DATA_DIR / "sgmc" / "sgmc_features_for_model.parquet"
    if sgmc_path.exists() and watershed_attrs is not None:
        sgmc = pd.read_parquet(sgmc_path)
        watershed_attrs = watershed_attrs.merge(sgmc, on="site_id", how="left")

    # Exclude vault + validation
    split_path = DATA_DIR / "train_holdout_vault_split.parquet"
    if split_path.exists():
        split = pd.read_parquet(split_path)
        train_sites = split[split["role"] == "training"]["site_id"]
    else:
        split = pd.read_parquet(DATA_DIR / "train_holdout_split.parquet")
        train_sites = split[split["role"] == "training"]["site_id"]

    assembled = paired[paired["site_id"].isin(train_sites)]
    tiers = build_feature_tiers(assembled, basic_attrs, watershed_attrs)

    if "C_sensor_basic_watershed" not in tiers:
        raise ValueError("Tier C not available")

    tier_data = tiers["C_sensor_basic_watershed"]["data"]
    feature_cols = tiers["C_sensor_basic_watershed"]["feature_cols"]

    # Apply drop list
    feature_cols = [c for c in feature_cols if c not in drop_features]

    cat_cols = [c for c in feature_cols if tier_data[c].dtype == "object" or tier_data[c].dtype.name == "category"]
    num_cols = [c for c in feature_cols if c not in cat_cols]
    cat_indices = [feature_cols.index(c) for c in cat_cols]

    return tier_data, feature_cols, num_cols, cat_indices


def train_and_evaluate_oob(
    tier_data: pd.DataFrame,
    feature_cols: list[str],
    num_cols: list[str],
    cat_indices: list[int],
    train_site_ids: list[str],
    test_site_ids: list[str],
    lmbda: float = 0.2,
) -> dict:
    """Train on train_site_ids, predict on test_site_ids. Return per-site R²."""
    train_mask = tier_data["site_id"].isin(train_site_ids)
    test_mask = tier_data["site_id"].isin(test_site_ids)

    train_data = tier_data[train_mask]
    test_data = tier_data[test_mask]

    if len(train_data) < 50 or len(test_data) < 50:
        return {}

    X_train = train_data[feature_cols].copy()
    X_test = test_data[feature_cols].copy()
    y_train_raw = train_data["lab_value"].values
    y_test_raw = test_data["lab_value"].values

    y_train = boxcox1p(y_train_raw, lmbda)

    # Fill NaN
    train_median = X_train[num_cols].median()
    X_train[num_cols] = X_train[num_cols].fillna(train_median)
    X_test[num_cols] = X_test[num_cols].fillna(train_median)

    # Validation split for early stopping
    sites_train = train_data["site_id"].values
    gss = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=42)
    sub_train_idx, val_idx = next(gss.split(X_train, y_train, groups=sites_train))

    train_pool = Pool(X_train.iloc[sub_train_idx], y_train[sub_train_idx], cat_features=cat_indices)
    val_pool = Pool(X_train.iloc[val_idx], y_train[val_idx], cat_features=cat_indices)

    # Monotone constraints
    mono = {}
    for col in ["turbidity_instant", "turbidity_max_1hr"]:
        if col in feature_cols:
            mono[feature_cols.index(col)] = 1

    model = CatBoostRegressor(
        iterations=500, learning_rate=0.05, depth=6, l2_leaf_reg=3,
        random_seed=42, verbose=0, thread_count=6,
        early_stopping_rounds=50,
        monotone_constraints=mono if mono else None,
    )
    model.fit(train_pool, eval_set=val_pool)

    # Predict on test sites
    test_pool = Pool(X_test, cat_features=cat_indices)
    y_pred_ms = model.predict(test_pool)

    # BCF from training predictions
    full_train_pool = Pool(X_train, cat_features=cat_indices)
    y_train_pred_ms = model.predict(full_train_pool)
    native_true = y_train_raw
    native_pred = safe_inv_boxcox1p(y_train_pred_ms, lmbda)
    native_pred = np.clip(native_pred, 1e-6, None)
    bcf = float(np.clip(np.mean(native_true) / np.mean(native_pred), 0.5, 5.0))

    # Back-transform test predictions
    y_pred_native = safe_inv_boxcox1p(y_pred_ms, lmbda) * bcf
    y_pred_native = np.clip(y_pred_native, 0, None)

    # Per-site R² on test sites
    test_site_col = test_data["site_id"].values
    per_site_r2 = {}
    for site_id in test_site_ids:
        mask = test_site_col == site_id
        if mask.sum() < 2:
            continue
        yt = y_test_raw[mask]
        yp = y_pred_native[mask]
        ss_tot = np.sum((yt - yt.mean()) ** 2)
        if ss_tot > 1e-10:
            per_site_r2[site_id] = float(1 - np.sum((yt - yp) ** 2) / ss_tot)

    return per_site_r2


def main():
    parser = argparse.ArgumentParser(description="Site Contribution Analysis")
    parser.add_argument("--n-subsets", type=int, default=50)
    parser.add_argument("--subset-size", type=int, default=100)
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Load drop list
    with open(DATA_DIR / "optimized_drop_list.txt") as f:
        drop_features = [x.strip() for x in f.read().split(",") if x.strip()]

    logger.info("Loading training data...")
    tier_data, feature_cols, num_cols, cat_indices = load_training_data(drop_features)

    all_sites = sorted(tier_data["site_id"].unique())
    n_sites = len(all_sites)
    logger.info(f"Training sites in Tier C: {n_sites}")
    logger.info(f"Features: {len(feature_cols)}")
    logger.info(f"Subsets: {args.n_subsets}, size: {args.subset_size}")

    # Get site metadata for stratification
    site_meta = tier_data.groupby("site_id").agg(
        n_samples=("lab_value", "count"),
        huc2=("site_id", "first"),  # placeholder, get from attrs
    ).reset_index()

    # Site HUC2 from attributes
    try:
        attrs = pd.read_parquet(DATA_DIR / "site_attributes.parquet")
        huc_map = dict(zip(attrs["site_id"], attrs.get("huc2", pd.Series(dtype=str))))
        site_meta["huc2"] = site_meta["site_id"].map(huc_map).fillna("unknown")
    except Exception:
        site_meta["huc2"] = "unknown"

    # Run subsets
    all_subset_results = []  # List of {subset_idx, train_sites, oob_med_r2, per_site_r2}
    t0 = time.time()

    for i in range(args.n_subsets):
        rng = np.random.default_rng(seed=1000 + i)

        # Stratified sample: proportional by HUC2
        train_sites = []
        sites_by_huc = {}
        for site in all_sites:
            huc = site_meta.loc[site_meta["site_id"] == site, "huc2"].values
            h = huc[0] if len(huc) > 0 else "unknown"
            sites_by_huc.setdefault(h, []).append(site)

        for huc, huc_sites in sites_by_huc.items():
            n_pick = max(1, round(args.subset_size * len(huc_sites) / n_sites))
            n_pick = min(n_pick, len(huc_sites))
            picked = rng.choice(huc_sites, size=n_pick, replace=False)
            train_sites.extend(picked)

        # Trim to exact size
        if len(train_sites) > args.subset_size:
            train_sites = list(rng.choice(train_sites, size=args.subset_size, replace=False))
        train_set = set(train_sites)
        test_sites = [s for s in all_sites if s not in train_set]

        logger.info(f"[{i+1}/{args.n_subsets}] Train: {len(train_sites)}, Test: {len(test_sites)}")

        per_site_r2 = train_and_evaluate_oob(
            tier_data, feature_cols, num_cols, cat_indices,
            train_sites, test_sites, lmbda=0.2,
        )

        if per_site_r2:
            oob_values = list(per_site_r2.values())
            med_r2 = float(np.nanmedian(oob_values))
            logger.info(f"  OOB MedSiteR²={med_r2:.4f} ({len(per_site_r2)} test sites)")

            all_subset_results.append({
                "subset_idx": i,
                "train_sites": train_sites,
                "test_sites": test_sites,
                "oob_med_r2": med_r2,
                "per_site_r2": per_site_r2,
            })
        else:
            logger.warning(f"  Failed — insufficient data")

    elapsed = time.time() - t0
    logger.info(f"\nCompleted {len(all_subset_results)} subsets in {elapsed:.0f}s")

    # Score each site: continuous marginal contribution
    logger.info("\nScoring sites...")
    site_scores = {}
    for site_id in all_sites:
        r2_with = []  # OOB MedR² of subsets that included this site
        r2_without = []  # OOB MedR² of subsets that excluded this site

        for result in all_subset_results:
            if site_id in result["train_sites"]:
                r2_with.append(result["oob_med_r2"])
            else:
                r2_without.append(result["oob_med_r2"])

        n_with = len(r2_with)
        n_without = len(r2_without)
        mean_with = float(np.mean(r2_with)) if r2_with else np.nan
        mean_without = float(np.mean(r2_without)) if r2_without else np.nan
        score = mean_with - mean_without if (r2_with and r2_without) else np.nan

        site_scores[site_id] = {
            "site_id": site_id,
            "n_with": n_with,
            "n_without": n_without,
            "mean_r2_with": mean_with,
            "mean_r2_without": mean_without,
            "anchor_score": score,
        }

    scores_df = pd.DataFrame(site_scores.values())

    # Merge site characteristics
    site_stats = tier_data.groupby("site_id").agg(
        n_samples=("lab_value", "count"),
        mean_ssc=("lab_value", "mean"),
        std_ssc=("lab_value", "std"),
    ).reset_index()
    scores_df = scores_df.merge(site_stats, on="site_id", how="left")

    try:
        scores_df = scores_df.merge(
            site_meta[["site_id", "huc2"]].drop_duplicates("site_id"),
            on="site_id", how="left",
        )
    except Exception:
        pass

    # Sort by anchor score
    scores_df = scores_df.sort_values("anchor_score", ascending=False)

    # Save
    scores_df.to_csv(RESULTS_DIR / "site_scores.csv", index=False)

    # Summary
    logger.info(f"\n{'='*70}")
    logger.info(f"SITE CONTRIBUTION ANALYSIS")
    logger.info(f"{'='*70}")
    logger.info(f"Sites scored: {len(scores_df)}")
    logger.info(f"Subsets: {len(all_subset_results)}")
    logger.info(f"Mean appearances per site: {scores_df['n_with'].mean():.1f}")

    valid = scores_df.dropna(subset=["anchor_score"])
    logger.info(f"\nAnchor score distribution:")
    logger.info(f"  Mean: {valid['anchor_score'].mean():.4f}")
    logger.info(f"  Std:  {valid['anchor_score'].std():.4f}")
    logger.info(f"  Min:  {valid['anchor_score'].min():.4f}")
    logger.info(f"  Max:  {valid['anchor_score'].max():.4f}")

    n_pos = (valid["anchor_score"] > 0.005).sum()
    n_neg = (valid["anchor_score"] < -0.005).sum()
    n_neutral = len(valid) - n_pos - n_neg
    logger.info(f"\n  Anchors (score > +0.005): {n_pos}")
    logger.info(f"  Neutral (±0.005):         {n_neutral}")
    logger.info(f"  Noise (score < -0.005):   {n_neg}")

    logger.info(f"\nTop 15 anchors:")
    logger.info(f"  {'Site':<25s} {'Score':>8s} {'n_with':>6s} {'n_samples':>9s} {'mean_ssc':>9s}")
    for _, r in valid.head(15).iterrows():
        logger.info(f"  {r['site_id']:<25s} {r['anchor_score']:>+8.4f} {r['n_with']:>6.0f} {r.get('n_samples',0):>9.0f} {r.get('mean_ssc',0):>9.1f}")

    logger.info(f"\nBottom 15 noise sites:")
    for _, r in valid.tail(15).iterrows():
        logger.info(f"  {r['site_id']:<25s} {r['anchor_score']:>+8.4f} {r['n_with']:>6.0f} {r.get('n_samples',0):>9.0f} {r.get('mean_ssc',0):>9.1f}")

    # Save subset results for reproducibility
    subset_summary = []
    for result in all_subset_results:
        subset_summary.append({
            "subset_idx": result["subset_idx"],
            "n_train": len(result["train_sites"]),
            "n_test": len(result["test_sites"]),
            "oob_med_r2": result["oob_med_r2"],
        })
    pd.DataFrame(subset_summary).to_csv(RESULTS_DIR / "subset_results.csv", index=False)

    logger.info(f"\nSaved to {RESULTS_DIR}/")
    logger.info(f"{'='*70}")


if __name__ == "__main__":
    main()
