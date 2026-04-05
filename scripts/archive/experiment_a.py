"""Experiment A: Collection Method Split & Grouping.

Tests whether different collection methods have fundamentally different
turbidity-SSC relationships that one model can't learn.
"""
import sys
import json
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
    """Load and prepare the full dataset."""
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


def train_and_eval(train_df, holdout_data, num_cols, cat_cols, label, drop_cm=False):
    """Train a quick model and evaluate on holdout."""
    target_col = "ssc_log1p"

    cols = list(num_cols) + list(cat_cols)
    this_cat = list(cat_cols)
    if drop_cm:
        cols = [c for c in cols if c != "collection_method"]
        this_cat = [c for c in this_cat if c != "collection_method"]

    clean = train_df.dropna(subset=[target_col]).copy()
    if len(clean) < 50:
        return None

    y = clean[target_col].values
    sites = clean["site_id"].values
    X = clean[cols].copy()
    for c in this_cat:
        X[c] = X[c].fillna("missing").astype(str)
    for c in cols:
        if c not in this_cat:
            X[c] = X[c].fillna(X[c].median())

    cat_idx = [i for i, c in enumerate(cols) if c in this_cat]

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

    # Predict on holdout
    h = holdout_data.copy()
    X_h = h[cols].copy()
    for c in this_cat:
        X_h[c] = X_h[c].fillna("missing").astype(str)
    train_median = {c: float(X.iloc[train_idx][c].median()) for c in cols if c not in this_cat}
    for c in cols:
        if c not in this_cat and c in train_median:
            X_h[c] = X_h[c].fillna(train_median[c])

    h_pool = Pool(X_h, cat_features=cat_idx)
    h_pred_bc = model.predict(h_pool)
    h_pred_native = np.clip(safe_inv_boxcox1p(h_pred_bc, LMBDA), 0, None)
    h_true_native = h["lab_value"].values

    # BCF
    t_pred = model.predict(train_pool)
    t_native_true = clean["lab_value"].values[train_idx]
    t_native_pred = safe_inv_boxcox1p(t_pred, LMBDA)
    bcf = snowdon_bcf(t_native_true, t_native_pred)
    h_pred_native *= bcf

    # Pooled metrics
    ss_res = np.sum((h_true_native - h_pred_native) ** 2)
    ss_tot = np.sum((h_true_native - h_true_native.mean()) ** 2)
    pooled_r2 = 1 - ss_res / max(ss_tot, 1e-10)

    # Per-site R²
    site_r2s = []
    for sid in h["site_id"].unique():
        mask = h["site_id"].values == sid
        yt = h_true_native[mask]
        yp = h_pred_native[mask]
        if len(yt) >= 5 and yt.std() > 0:
            sr = 1 - np.sum((yt - yp) ** 2) / max(np.sum((yt - yt.mean()) ** 2), 1e-10)
            site_r2s.append(sr)

    median_r2 = np.median(site_r2s) if site_r2s else np.nan

    # MAPE and within-2x
    nz = h_true_native > 0
    ape = np.abs(h_pred_native[nz] - h_true_native[nz]) / h_true_native[nz]
    mape = np.median(ape) * 100
    ratio = h_pred_native[nz] / h_true_native[nz]
    f2 = np.mean((ratio >= 0.5) & (ratio <= 2.0))

    # Per collection method breakdown
    cm_results = {}
    if "collection_method" in h.columns:
        for cm in h["collection_method"].unique():
            cm_mask = h["collection_method"].values == cm
            yt_cm = h_true_native[cm_mask]
            yp_cm = h_pred_native[cm_mask]
            if len(yt_cm) >= 5:
                cm_r2 = 1 - np.sum((yt_cm - yp_cm) ** 2) / max(np.sum((yt_cm - yt_cm.mean()) ** 2), 1e-10)
                cm_results[cm] = {"r2": cm_r2, "n": len(yt_cm)}

    # Save model
    model_dir = DATA_DIR / "results" / "models"
    model_path = model_dir / f"ssc_C_{label}.cbm"
    model.save_model(str(model_path))

    return {
        "label": label,
        "n_train_samples": len(clean),
        "n_train_sites": clean["site_id"].nunique(),
        "trees": model.tree_count_,
        "bcf": bcf,
        "pooled_r2": pooled_r2,
        "median_site_r2": median_r2,
        "mape_pct": mape,
        "frac_within_2x": f2,
        "cm_breakdown": cm_results,
    }


def main():
    train_data, holdout_data, num_cols, cat_cols = prepare_data()
    print(f"Holdout: {holdout_data.site_id.nunique()} sites, {len(holdout_data)} samples")

    experiments = [
        ("A1-auto_point", train_data[train_data["collection_method"] == "auto_point"], True),
        ("A2-depth_integrated", train_data[train_data["collection_method"] == "depth_integrated"], True),
        ("A3-grab", train_data[train_data["collection_method"] == "grab"], True),
        ("A4-auto+depth", train_data[train_data["collection_method"].isin(["auto_point", "depth_integrated"])], False),
        ("A5-auto+grab", train_data[train_data["collection_method"].isin(["auto_point", "grab"])], False),
        ("A6-depth+grab", train_data[train_data["collection_method"].isin(["depth_integrated", "grab"])], False),
        ("A7-known_only", train_data[train_data["collection_method"].isin(["auto_point", "depth_integrated", "grab"])], False),
    ]

    print("\n" + "=" * 80)
    print("EXPERIMENT A: COLLECTION METHOD SPLIT & GROUPING")
    print("=" * 80)

    results = []
    for label, data, drop_cm in experiments:
        t0 = time.time()
        result = train_and_eval(data, holdout_data, num_cols, cat_cols, label, drop_cm=drop_cm)
        elapsed = time.time() - t0
        if result is None:
            print(f"\n{label}: SKIPPED (too few samples)")
            continue
        results.append(result)
        print(f"\n{label} ({elapsed:.0f}s):")
        print(f"  Train: {result['n_train_sites']} sites, {result['n_train_samples']} samples, {result['trees']} trees")
        print(f"  Holdout pooled R²: {result['pooled_r2']:.3f}")
        print(f"  Holdout median site R²: {result['median_site_r2']:.3f}")
        print(f"  MAPE: {result['mape_pct']:.1f}%,  Within 2x: {result['frac_within_2x']:.1%}")
        print(f"  BCF: {result['bcf']:.3f}")
        if result["cm_breakdown"]:
            print(f"  By collection method:")
            for cm, vals in sorted(result["cm_breakdown"].items()):
                print(f"    {cm:20s}: R²={vals['r2']:.3f}  (n={vals['n']})")

    print("\n" + "=" * 80)
    print("SUMMARY TABLE")
    print("=" * 80)
    header = f"{'Label':25s} {'Sites':>6s} {'Samples':>8s} {'Pooled R²':>10s} {'Med Site R²':>12s} {'MAPE%':>7s} {'Within2x':>9s}"
    print(header)
    print("-" * 80)
    print(f"{'v4-baseline':25s} {'357':>6s} {'32046':>8s} {'0.211':>10s} {'0.290':>12s} {'---':>7s} {'---':>9s}")
    for r in results:
        print(f"{r['label']:25s} {r['n_train_sites']:>6d} {r['n_train_samples']:>8d} {r['pooled_r2']:>10.3f} {r['median_site_r2']:>12.3f} {r['mape_pct']:>7.1f} {r['frac_within_2x']:>9.1%}")


if __name__ == "__main__":
    main()
