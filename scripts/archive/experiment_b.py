"""Experiment B: Exclude Low-Quality Sites.

Tests whether noisy/catastrophic sites are poisoning the model.
B1: Remove sites with LOGO CV R² < -1 (outcome-based, circular)
B2: Remove sites with LOGO CV R² < 0 (outcome-based, circular)
B3: Remove sites with SSC std below threshold (characteristic-based, defensible)
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

    # Predict on holdout
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

    # BCF
    t_pred = model.predict(train_pool)
    t_native_true = clean["lab_value"].values[train_idx]
    t_native_pred = safe_inv_boxcox1p(t_pred, LMBDA)
    bcf = snowdon_bcf(t_native_true, t_native_pred)
    h_pred_native *= bcf

    # Pooled R²
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
    pct_negative = np.mean(np.array(site_r2s) < 0) * 100 if site_r2s else np.nan

    # MAPE and within-2x
    nz = h_true_native > 0
    ape = np.abs(h_pred_native[nz] - h_true_native[nz]) / h_true_native[nz]
    mape = np.median(ape) * 100
    ratio = h_pred_native[nz] / h_true_native[nz]
    f2 = np.mean((ratio >= 0.5) & (ratio <= 2.0))

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
        "pct_negative_sites": pct_negative,
        "mape_pct": mape,
        "frac_within_2x": f2,
    }


def main():
    train_data, holdout_data, num_cols, cat_cols = prepare_data()
    paired = pd.read_parquet(DATA_DIR / "processed" / "turbidity_ssc_paired.parquet")

    # Load LOGO CV results to identify bad sites
    folds = pd.read_parquet(DATA_DIR / "results" / "logo_folds_ssc_C_sensor_basic_watershed.parquet")

    # Compute per-site SSC std for B3
    site_std = paired.groupby("site_id")["lab_value"].std().reset_index()
    site_std.columns = ["site_id", "ssc_std"]

    # B3 threshold: find elbow in R² vs SSC std
    merged = folds[["site_id", "r2_native"]].merge(site_std, on="site_id", how="left")
    # Bin by SSC std quartiles
    print("=" * 70)
    print("B3 THRESHOLD DETERMINATION: R² by SSC std quartile")
    print("=" * 70)
    merged["std_quartile"] = pd.qcut(merged["ssc_std"].clip(0, None), 4, labels=["Q1_low", "Q2", "Q3", "Q4_high"])
    for q, g in merged.groupby("std_quartile", observed=True):
        print(f"  {q}: {len(g)} sites, median R²={g.r2_native.median():.3f}, SSC std range=[{g.ssc_std.min():.0f}, {g.ssc_std.max():.0f}]")

    # Use Q1 upper bound as threshold
    q1_upper = merged[merged["std_quartile"] == "Q1_low"]["ssc_std"].max()
    print(f"\nB3 threshold: SSC std < {q1_upper:.0f} mg/L")

    # Identify sites to exclude
    catastrophic_sites = set(folds[folds["r2_native"] < -1.0]["site_id"])
    negative_sites = set(folds[folds["r2_native"] < 0.0]["site_id"])
    lowvar_sites = set(site_std[site_std["ssc_std"] < q1_upper]["site_id"])

    # Only exclude from training sites
    train_ids = set(train_data["site_id"].unique())
    b1_exclude = catastrophic_sites & train_ids
    b2_exclude = negative_sites & train_ids
    b3_exclude = lowvar_sites & train_ids

    print(f"\nB1: excluding {len(b1_exclude)} catastrophic sites (R² < -1)")
    print(f"B2: excluding {len(b2_exclude)} negative sites (R² < 0)")
    print(f"B3: excluding {len(b3_exclude)} low-variability sites (SSC std < {q1_upper:.0f})")

    experiments = [
        ("B1-no_catastrophic", train_data[~train_data["site_id"].isin(b1_exclude)]),
        ("B2-no_negative", train_data[~train_data["site_id"].isin(b2_exclude)]),
        ("B3-no_lowvar", train_data[~train_data["site_id"].isin(b3_exclude)]),
    ]

    print("\n" + "=" * 80)
    print("EXPERIMENT B: EXCLUDE LOW-QUALITY SITES")
    print("=" * 80)

    results = []
    for label, data in experiments:
        t0 = time.time()
        result = train_and_eval(data, holdout_data, num_cols, cat_cols, label)
        elapsed = time.time() - t0
        if result is None:
            print(f"\n{label}: SKIPPED")
            continue
        results.append(result)
        print(f"\n{label} ({elapsed:.0f}s):")
        print(f"  Train: {result['n_train_sites']} sites, {result['n_train_samples']} samples, {result['trees']} trees")
        print(f"  Holdout pooled R²: {result['pooled_r2']:.3f}")
        print(f"  Holdout median site R²: {result['median_site_r2']:.3f}")
        print(f"  % holdout sites with negative R²: {result['pct_negative_sites']:.0f}%")
        print(f"  MAPE: {result['mape_pct']:.1f}%,  Within 2x: {result['frac_within_2x']:.1%}")

    print("\n" + "=" * 80)
    print("SUMMARY TABLE")
    print("=" * 80)
    print(f"{'Label':25s} {'Sites':>6s} {'Samples':>8s} {'Pooled R²':>10s} {'Med Site R²':>12s} {'%Neg':>6s} {'MAPE%':>7s} {'Within2x':>9s}")
    print("-" * 80)
    print(f"{'v4-baseline':25s} {'357':>6s} {'32046':>8s} {'0.211':>10s} {'0.290':>12s} {'33%':>6s} {'---':>7s} {'---':>9s}")
    for r in results:
        print(f"{r['label']:25s} {r['n_train_sites']:>6d} {r['n_train_samples']:>8d} {r['pooled_r2']:>10.3f} {r['median_site_r2']:>12.3f} {r['pct_negative_sites']:>5.0f}% {r['mape_pct']:>7.1f} {r['frac_within_2x']:>9.1%}")


if __name__ == "__main__":
    main()
