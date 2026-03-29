"""Experiment D Redo: Pure random site selection with 5 seeds.

Tests whether more data helps, controlling for randomness.
100, 150, 200, 250 random sites, 5 seeds each, plus all sites.
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
    basic = pd.read_parquet(DATA_DIR / "site_attributes.parquet")
    ws = load_streamcat_attrs(DATA_DIR)
    assembled["ssc_log1p"] = boxcox1p(assembled["lab_value"].values, LMBDA)

    tiers = build_feature_tiers(assembled, basic, ws)
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
    tm = {c: float(X.iloc[train_idx][c].median()) for c in cols if c not in cat_cols}
    for c in cols:
        if c not in cat_cols and c in tm:
            X_h[c] = X_h[c].fillna(tm[c])

    h_pool = Pool(X_h, cat_features=cat_idx)
    pred_bc = model.predict(h_pool)
    pred_native = np.clip(safe_inv_boxcox1p(pred_bc, LMBDA), 0, None)
    true_native = h["lab_value"].values

    t_pred = model.predict(train_pool)
    bcf = snowdon_bcf(clean["lab_value"].values[train_idx], safe_inv_boxcox1p(t_pred, LMBDA))
    pred_native *= bcf

    ss_res = np.sum((true_native - pred_native) ** 2)
    ss_tot = np.sum((true_native - true_native.mean()) ** 2)
    pooled_r2 = 1 - ss_res / max(ss_tot, 1e-10)

    site_r2s = []
    for sid in h["site_id"].unique():
        mask = h["site_id"].values == sid
        yt, yp = true_native[mask], pred_native[mask]
        if len(yt) >= 5 and yt.std() > 0:
            site_r2s.append(1 - np.sum((yt - yp) ** 2) / max(np.sum((yt - yt.mean()) ** 2), 1e-10))

    return {
        "label": label,
        "n_sites": clean["site_id"].nunique(),
        "n_samples": len(clean),
        "pooled_r2": pooled_r2,
        "median_site_r2": np.median(site_r2s) if site_r2s else np.nan,
    }


def main():
    train_data, holdout_data, num_cols, cat_cols = prepare_data()
    all_train_sites = list(train_data["site_id"].unique())
    print(f"Total training sites: {len(all_train_sites)}")
    print(f"Holdout: {holdout_data.site_id.nunique()} sites, {len(holdout_data)} samples")

    print("\n" + "=" * 80)
    print("EXPERIMENT D-REDO: RANDOM SITE SELECTION (5 seeds each)")
    print("=" * 80)

    summary = {}

    for n_sites in [100, 150, 200, 250]:
        pooled_list = []
        medsite_list = []
        for seed in range(5):
            rng = np.random.default_rng(seed + 100)  # offset to avoid any overlap
            selected = set(rng.choice(all_train_sites, n_sites, replace=False))
            t0 = time.time()
            result = train_and_eval(
                train_data[train_data["site_id"].isin(selected)],
                holdout_data, num_cols, cat_cols,
                f"D-rand-{n_sites}-s{seed}",
            )
            elapsed = time.time() - t0
            if result:
                pooled_list.append(result["pooled_r2"])
                medsite_list.append(result["median_site_r2"])
                print(f"  {result['label']}: {result['n_sites']} sites, {result['n_samples']} samples, "
                      f"pooled={result['pooled_r2']:.3f}, med_site={result['median_site_r2']:.3f} ({elapsed:.0f}s)")

        if pooled_list:
            summary[n_sites] = {
                "pooled_mean": np.mean(pooled_list),
                "pooled_std": np.std(pooled_list),
                "medsite_mean": np.mean(medsite_list),
                "medsite_std": np.std(medsite_list),
            }
            print(f"  >>> n={n_sites}: pooled R2 = {np.mean(pooled_list):.3f} +/- {np.std(pooled_list):.3f}, "
                  f"med site R2 = {np.mean(medsite_list):.3f} +/- {np.std(medsite_list):.3f}")
        print()

    # All sites (deterministic)
    t0 = time.time()
    result_all = train_and_eval(train_data, holdout_data, num_cols, cat_cols, "D-all")
    elapsed = time.time() - t0
    print(f"D-all: {result_all['n_sites']} sites, pooled={result_all['pooled_r2']:.3f}, "
          f"med_site={result_all['median_site_r2']:.3f} ({elapsed:.0f}s)")

    print("\n" + "=" * 80)
    print("SUMMARY: Does more random data help?")
    print("=" * 80)
    print(f"{'N sites':>8s}  {'Pooled R2 (mean +/- std)':>28s}  {'Med Site R2 (mean +/- std)':>30s}")
    print("-" * 70)
    for n_sites in [100, 150, 200, 250]:
        if n_sites in summary:
            s = summary[n_sites]
            print(f"{n_sites:>8d}  {s['pooled_mean']:>10.3f} +/- {s['pooled_std']:.3f}          "
                  f"{s['medsite_mean']:>10.3f} +/- {s['medsite_std']:.3f}")
    print(f"{'all':>8s}  {result_all['pooled_r2']:>10.3f}                        "
          f"{result_all['median_site_r2']:>10.3f}")


if __name__ == "__main__":
    main()
