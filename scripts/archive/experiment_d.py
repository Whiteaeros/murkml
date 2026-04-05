"""Experiment D: Site Count & Data Quality Impact.

Tests whether adding more (potentially noisier) sites helps or hurts.
Quality-tiered scaling curve with 5 random seeds per tier.
"""
import sys
import warnings
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import boxcox1p
from sklearn.model_selection import GroupShuffleSplit
from catboost import CatBoostRegressor, Pool

warnings.filterwarnings("ignore")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from murkml.data.attributes import build_feature_tiers, load_streamcat_attrs
from murkml.evaluate.metrics import snowdon_bcf, safe_inv_boxcox1p

DATA_DIR = PROJECT_ROOT / "data"
LMBDA = 0.2


def prepare_data():
    assembled = pd.read_parquet(DATA_DIR / "processed" / "turbidity_ssc_paired.parquet")
    basic_attrs = pd.read_parquet(DATA_DIR / "site_attributes.parquet")
    ws_attrs = load_streamcat_attrs(DATA_DIR)
    assembled["ssc_log1p"] = boxcox1p(assembled["lab_value"].values, LMBDA)

    tiers = build_feature_tiers(assembled, basic_attrs, ws_attrs)
    tier_data = tiers["C_sensor_basic_watershed"]["data"]
    feature_cols = tiers["C_sensor_basic_watershed"]["feature_cols"]

    drop_list = set(open(DATA_DIR / "optimized_drop_list.txt").read().strip().split(","))
    EXCLUDE = {
        "site_id", "sample_time", "lab_value", "match_gap_seconds", "window_count",
        "is_nondetect", "hydro_event", "ssc_log1p", "ssc_value",
        "total_phosphorus_log1p", "nitrate_nitrite_log1p",
        "orthophosphate_log1p", "tds_evaporative_log1p",
    }
    available = [c for c in feature_cols if c in tier_data.columns and c not in EXCLUDE and c not in drop_list]
    num_cols = [c for c in available if tier_data[c].dtype in [np.float64, np.float32, np.int64, np.int32, float, int]]
    cat_cols = [c for c in available if tier_data[c].dtype == object]

    split = pd.read_parquet(DATA_DIR / "train_holdout_split.parquet")
    holdout_ids = set(split[split["role"] == "holdout"]["site_id"])
    train_ids = set(split[split["role"] == "training"]["site_id"])

    holdout_data = tier_data[tier_data["site_id"].isin(holdout_ids)].copy()
    train_data = tier_data[tier_data["site_id"].isin(train_ids)].copy()

    return train_data, holdout_data, num_cols, cat_cols


def train_and_eval(train_df, holdout_data, num_cols, cat_cols, label):
    target_col = "ssc_log1p"
    cols = list(num_cols) + list(cat_cols)

    clean = train_df.dropna(subset=[target_col]).copy()
    if len(clean) < 50:
        return None

    y = clean[target_col].values
    sites = clean["site_id"].values
    X = clean[cols].copy()
    for c in cat_cols:
        X[c] = X[c].fillna("missing").astype(str)
    for c in cols:
        if c not in cat_cols:
            X[c] = X[c].fillna(X[c].median())

    cat_idx = [i for i, c in enumerate(cols) if c in cat_cols]

    gss = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=42)
    train_idx, val_idx = next(gss.split(X, y, groups=sites))

    train_pool = Pool(X.iloc[train_idx], y[train_idx], cat_features=cat_idx)
    val_pool = Pool(X.iloc[val_idx], y[val_idx], cat_features=cat_idx)

    mono = {}
    for i, c in enumerate(cols):
        if c in {"turbidity_instant", "turbidity_max_1hr"}:
            mono[i] = 1

    model = CatBoostRegressor(
        iterations=500, learning_rate=0.05, depth=6,
        l2_leaf_reg=3, random_seed=42, verbose=0,
        early_stopping_rounds=50, thread_count=12,
        boosting_type="Ordered", monotone_constraints=mono,
    )
    model.fit(train_pool, eval_set=val_pool)

    h = holdout_data.copy()
    X_h = h[cols].copy()
    for c in cat_cols:
        X_h[c] = X_h[c].fillna("missing").astype(str)
    train_median = {c: float(X.iloc[train_idx][c].median()) for c in cols if c not in cat_cols}
    for c in cols:
        if c not in cat_cols and c in train_median:
            X_h[c] = X_h[c].fillna(train_median[c])

    h_pool = Pool(X_h, cat_features=cat_idx)
    h_pred_bc = model.predict(h_pool)
    h_pred_native = np.clip(safe_inv_boxcox1p(h_pred_bc, LMBDA), 0, None)
    h_true_native = h["lab_value"].values

    t_pred = model.predict(train_pool)
    t_native_true = clean["lab_value"].values[train_idx]
    t_native_pred = safe_inv_boxcox1p(t_pred, LMBDA)
    bcf = snowdon_bcf(t_native_true, t_native_pred)
    h_pred_native *= bcf

    ss_res = np.sum((h_true_native - h_pred_native) ** 2)
    ss_tot = np.sum((h_true_native - h_true_native.mean()) ** 2)
    pooled_r2 = 1 - ss_res / max(ss_tot, 1e-10)

    site_r2s = []
    for sid in h["site_id"].unique():
        mask = h["site_id"].values == sid
        yt = h_true_native[mask]
        yp = h_pred_native[mask]
        if len(yt) >= 5 and yt.std() > 0:
            sr = 1 - np.sum((yt - yp) ** 2) / max(np.sum((yt - yt.mean()) ** 2), 1e-10)
            site_r2s.append(sr)

    median_r2 = np.median(site_r2s) if site_r2s else np.nan

    nz = h_true_native > 0
    ape = np.abs(h_pred_native[nz] - h_true_native[nz]) / h_true_native[nz]
    mape = np.median(ape) * 100
    ratio = h_pred_native[nz] / h_true_native[nz]
    f2 = np.mean((ratio >= 0.5) & (ratio <= 2.0))

    return {
        "label": label,
        "n_train_samples": len(clean),
        "n_train_sites": clean["site_id"].nunique(),
        "trees": model.tree_count_,
        "pooled_r2": pooled_r2,
        "median_site_r2": median_r2,
        "mape_pct": mape,
        "frac_within_2x": f2,
    }


def stratified_sample_sites(site_stats, n_sites, seed):
    """Sample sites maintaining distribution across SSC var, method, and SSC level."""
    rng = np.random.default_rng(seed)

    # Create strata
    site_stats = site_stats.copy()
    site_stats["ssc_std_bin"] = pd.qcut(site_stats["ssc_std"].clip(1, None), 3, labels=["low", "mid", "high"])
    site_stats["ssc_level_bin"] = pd.qcut(site_stats["median_ssc"].clip(1, None), 3, labels=["low", "mid", "high"])

    # Sample proportionally from each stratum
    sampled = []
    for (sb, lb, cm), group in site_stats.groupby(["ssc_std_bin", "ssc_level_bin", "cm_dominant"], observed=True):
        n_from_stratum = max(1, round(len(group) * n_sites / len(site_stats)))
        n_from_stratum = min(n_from_stratum, len(group))
        idx = rng.choice(len(group), n_from_stratum, replace=False)
        sampled.extend(group.iloc[idx]["site_id"].tolist())

    # Trim or pad to exact n_sites
    if len(sampled) > n_sites:
        sampled = rng.choice(sampled, n_sites, replace=False).tolist()
    return set(sampled)


def main():
    train_data, holdout_data, num_cols, cat_cols = prepare_data()
    paired = pd.read_parquet(DATA_DIR / "processed" / "turbidity_ssc_paired.parquet")

    # Compute per-site stats for stratification and filtering
    train_sites = train_data["site_id"].unique()
    site_stats = paired[paired["site_id"].isin(train_sites)].groupby("site_id").agg(
        n_samples=("lab_value", "count"),
        median_ssc=("lab_value", "median"),
        ssc_std=("lab_value", "std"),
        cm_dominant=("collection_method", lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else "unknown"),
        pct_continuous=("turb_source", lambda x: (x == "continuous").mean()),
    ).reset_index()

    # Define quality tiers
    d1_sites = set(site_stats[
        (site_stats["n_samples"] >= 50) &
        (site_stats["cm_dominant"].isin(["auto_point", "depth_integrated", "grab"])) &
        (site_stats["ssc_std"] > 100)
    ]["site_id"])

    d2_sites = set(site_stats[
        (site_stats["n_samples"] >= 20) &
        (site_stats["cm_dominant"].isin(["auto_point", "depth_integrated", "grab"]))
    ]["site_id"])

    d3_sites = set(site_stats[site_stats["n_samples"] >= 10]["site_id"])

    d4_sites = set(site_stats["site_id"])

    d5_sites = set(site_stats[site_stats["pct_continuous"] == 1.0]["site_id"])

    print(f"D1 (highest quality): {len(d1_sites)} sites")
    print(f"D2 (good quality): {len(d2_sites)} sites")
    print(f"D3 (moderate quality): {len(d3_sites)} sites")
    print(f"D4 (all): {len(d4_sites)} sites")
    print(f"D5 (continuous only): {len(d5_sites)} sites")

    results = []

    # D4 and D5: deterministic (1 run each)
    for label, site_set in [("D4-all", d4_sites), ("D5-continuous_only", d5_sites)]:
        t0 = time.time()
        data = train_data[train_data["site_id"].isin(site_set)]
        result = train_and_eval(data, holdout_data, num_cols, cat_cols, label)
        elapsed = time.time() - t0
        if result:
            results.append(result)
            print(f"\n{label} ({elapsed:.0f}s): {result['n_train_sites']} sites, "
                  f"pooled R²={result['pooled_r2']:.3f}, med site R²={result['median_site_r2']:.3f}")

    # D1, D2, D3: 5 seeds each with stratified sampling
    for tier_label, eligible_sites in [("D1-highest", d1_sites), ("D2-good", d2_sites), ("D3-moderate", d3_sites)]:
        tier_stats = site_stats[site_stats["site_id"].isin(eligible_sites)]
        tier_results = []
        for seed in range(5):
            label = f"{tier_label}_s{seed}"
            # For D1, use all eligible (may be <100). For D2/D3, sample if needed.
            if len(eligible_sites) <= 100:
                selected = eligible_sites
            else:
                selected = stratified_sample_sites(tier_stats, min(len(eligible_sites), len(eligible_sites)), seed)

            t0 = time.time()
            data = train_data[train_data["site_id"].isin(selected)]
            result = train_and_eval(data, holdout_data, num_cols, cat_cols, label)
            elapsed = time.time() - t0
            if result:
                tier_results.append(result)
                results.append(result)
                print(f"  {label} ({elapsed:.0f}s): {result['n_train_sites']} sites, "
                      f"pooled R²={result['pooled_r2']:.3f}, med site R²={result['median_site_r2']:.3f}")

        if tier_results:
            r2s = [r["pooled_r2"] for r in tier_results]
            med_r2s = [r["median_site_r2"] for r in tier_results]
            print(f"\n  {tier_label} summary (5 seeds):")
            print(f"    Pooled R²:    {np.mean(r2s):.3f} ± {np.std(r2s):.3f}")
            print(f"    Med site R²:  {np.mean(med_r2s):.3f} ± {np.std(med_r2s):.3f}")

    # Final summary
    print("\n" + "=" * 80)
    print("EXPERIMENT D SUMMARY")
    print("=" * 80)
    print(f"{'Label':20s} {'Sites':>6s} {'Samples':>8s} {'Pooled R²':>10s} {'Med Site R²':>12s} {'MAPE%':>7s}")
    print("-" * 70)
    for r in results:
        print(f"{r['label']:20s} {r['n_train_sites']:>6d} {r['n_train_samples']:>8d} "
              f"{r['pooled_r2']:>10.3f} {r['median_site_r2']:>12.3f} {r['mape_pct']:>7.1f}")


if __name__ == "__main__":
    main()
