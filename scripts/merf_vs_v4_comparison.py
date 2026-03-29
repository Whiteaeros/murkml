"""Head-to-head MERF vs v4 comparison using identical evaluation pipeline."""
import sys
import warnings
import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.special import boxcox1p
from scipy.stats import linregress
from catboost import CatBoostRegressor, Pool
from merf import MERF

warnings.filterwarnings("ignore")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from murkml.data.attributes import build_feature_tiers, load_streamcat_attrs
from murkml.evaluate.metrics import snowdon_bcf, safe_inv_boxcox1p

DATA_DIR = PROJECT_ROOT / "data"
LMBDA = 0.2


def inv_transform(y):
    return np.clip(safe_inv_boxcox1p(y, LMBDA), 0, None)


def compute_site_metrics(y_true, y_pred):
    if len(y_true) < 3:
        return {"r2_native": np.nan}
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - y_true.mean()) ** 2)
    r2 = 1 - ss_res / max(ss_tot, 1e-10)
    return {"r2_native": float(r2)}


def run_adaptation_curve(predictions, label):
    """Run identical adaptation logic as site_adaptation.py."""
    N_VALUES = [0, 1, 2, 3, 5, 10, 20]
    rng = np.random.default_rng(42)
    n_trials = 50

    print(f"\n{'=' * 70}")
    print(f"{label} ADAPTATION CURVE")
    print(f"{'=' * 70}")

    for N in N_VALUES:
        all_site_r2s = []

        for site_id in predictions["site_id"].unique():
            site_data = predictions[predictions["site_id"] == site_id].reset_index(drop=True)
            n_samples = len(site_data)

            if N == 0:
                m = compute_site_metrics(
                    site_data["y_true_native"].values,
                    site_data["y_pred_native"].values,
                )
                if not np.isnan(m["r2_native"]):
                    all_site_r2s.append(m["r2_native"])
                continue

            if N >= n_samples - 2:
                continue

            trial_r2s = []
            for trial in range(n_trials):
                cal_idx = rng.choice(n_samples, N, replace=False)
                test_idx = np.setdiff1d(np.arange(n_samples), cal_idx)

                cal = site_data.iloc[cal_idx]
                test = site_data.iloc[test_idx]

                if N == 1:
                    a = 1.0
                    b = float(cal["y_true_log"].values[0] - cal["y_pred_log"].values[0])
                else:
                    try:
                        a, b, _, _, _ = linregress(
                            cal["y_pred_log"].values, cal["y_true_log"].values
                        )
                        a = np.clip(a, 0.1, 10.0)
                    except Exception:
                        a, b = 1.0, 0.0

                corrected_log = a * test["y_pred_log"].values + b
                corrected_native = inv_transform(corrected_log)

                cal_corrected = inv_transform(a * cal["y_pred_log"].values + b)
                cal_corrected = np.clip(cal_corrected, 1e-6, None)
                cal_bcf = np.mean(cal["y_true_native"].values) / np.mean(cal_corrected)
                cal_bcf = np.clip(cal_bcf, 0.1, 10.0)
                corrected_native *= cal_bcf

                m = compute_site_metrics(test["y_true_native"].values, corrected_native)
                if not np.isnan(m["r2_native"]):
                    trial_r2s.append(m["r2_native"])

            if trial_r2s:
                all_site_r2s.append(np.median(trial_r2s))

        if all_site_r2s:
            med = np.median(all_site_r2s)
            q25 = np.percentile(all_site_r2s, 25)
            q75 = np.percentile(all_site_r2s, 75)
            print(f"  N={N:>2d}:  {len(all_site_r2s)} sites,  median R2={med:.3f}  [{q25:.3f} - {q75:.3f}]")


def main():
    # Load data
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
    all_cols = num_cols + cat_cols

    split = pd.read_parquet(DATA_DIR / "train_holdout_split.parquet")
    holdout_ids = set(split[split["role"] == "holdout"]["site_id"])
    train_ids = set(split[split["role"] == "training"]["site_id"])

    train_data = tier_data[tier_data["site_id"].isin(train_ids)].copy()
    holdout_data = tier_data[tier_data["site_id"].isin(holdout_ids)].copy()

    print(f"Train: {train_data.site_id.nunique()} sites, {len(train_data)} samples")
    print(f"Holdout: {holdout_data.site_id.nunique()} sites, {len(holdout_data)} samples")

    # ============================================================
    # V4 BASELINE: CatBoost with categoricals
    # ============================================================
    print("\n--- Training v4 baseline (CatBoost, all features) ---")
    clean = train_data.dropna(subset=["ssc_log1p"]).copy()
    y = clean["ssc_log1p"].values
    sites = clean["site_id"].values
    X = clean[all_cols].copy()
    for c in cat_cols:
        X[c] = X[c].fillna("missing").astype(str)
    for c in all_cols:
        if c not in cat_cols:
            X[c] = X[c].fillna(X[c].median())

    cat_idx = [i for i, c in enumerate(all_cols) if c in cat_cols]

    from sklearn.model_selection import GroupShuffleSplit
    gss = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=42)
    train_idx, val_idx = next(gss.split(X, y, groups=sites))

    train_pool = Pool(X.iloc[train_idx], y[train_idx], cat_features=cat_idx)
    val_pool = Pool(X.iloc[val_idx], y[val_idx], cat_features=cat_idx)

    mono = {}
    for i, c in enumerate(all_cols):
        if c in {"turbidity_instant", "turbidity_max_1hr"}:
            mono[i] = 1

    v4_model = CatBoostRegressor(
        iterations=500, learning_rate=0.05, depth=6,
        l2_leaf_reg=3, random_seed=42, verbose=0,
        early_stopping_rounds=50, thread_count=12,
        boosting_type="Ordered", monotone_constraints=mono,
    )
    v4_model.fit(train_pool, eval_set=val_pool)
    print(f"v4: {v4_model.tree_count_} trees")

    # v4 holdout predictions
    h = holdout_data.copy()
    X_h = h[all_cols].copy()
    for c in cat_cols:
        X_h[c] = X_h[c].fillna("missing").astype(str)
    tm = {c: float(X.iloc[train_idx][c].median()) for c in all_cols if c not in cat_cols}
    for c in all_cols:
        if c not in cat_cols and c in tm:
            X_h[c] = X_h[c].fillna(tm[c])

    h_pool = Pool(X_h, cat_features=cat_idx)
    v4_pred_bc = v4_model.predict(h_pool)
    v4_pred_native = inv_transform(v4_pred_bc)
    v4_bcf = snowdon_bcf(
        clean["lab_value"].values[train_idx],
        safe_inv_boxcox1p(v4_model.predict(train_pool), LMBDA),
    )
    v4_pred_native *= v4_bcf
    print(f"v4 BCF: {v4_bcf:.4f}")

    v4_predictions = pd.DataFrame({
        "site_id": h["site_id"].values,
        "sample_time": h["sample_time"].values if "sample_time" in h.columns else np.nan,
        "y_true_log": boxcox1p(h["lab_value"].values, LMBDA),
        "y_pred_log": v4_pred_bc,
        "y_true_native": h["lab_value"].values,
        "y_pred_native": v4_pred_native,
    })

    # ============================================================
    # MERF: CatBoost with random effects (numeric features only)
    # ============================================================
    print("\n--- Training MERF (CatBoost + random effects, numeric only) ---")
    X_merf = clean[num_cols].copy()
    for c in num_cols:
        X_merf[c] = X_merf[c].fillna(X_merf[c].median())

    Z = np.ones((len(X_merf), 2))
    Z[:, 1] = X_merf["turbidity_instant"].values
    clusters = pd.Series(sites)

    cb = CatBoostRegressor(
        iterations=500, learning_rate=0.05, depth=6,
        l2_leaf_reg=3, random_seed=42, verbose=0,
        early_stopping_rounds=50, thread_count=12,
    )
    mrf = MERF(fixed_effects_model=cb, max_iterations=10)
    mrf.fit(X_merf, Z, clusters, y)
    print("MERF trained")

    # MERF holdout predictions (no random effects for new sites)
    X_h_merf = h[num_cols].copy()
    for c in num_cols:
        X_h_merf[c] = X_h_merf[c].fillna(tm.get(c, 0))

    Z_h = np.ones((len(X_h_merf), 2))
    Z_h[:, 1] = X_h_merf["turbidity_instant"].values
    h_clusters = pd.Series(h["site_id"].values)

    merf_pred_bc = mrf.predict(X_h_merf, Z_h, h_clusters)
    merf_pred_native = inv_transform(merf_pred_bc)
    merf_bcf = snowdon_bcf(
        clean["lab_value"].values,
        safe_inv_boxcox1p(mrf.predict(X_merf, Z, clusters), LMBDA),
    )
    merf_pred_native *= merf_bcf
    print(f"MERF BCF: {merf_bcf:.4f}")

    merf_predictions = pd.DataFrame({
        "site_id": h["site_id"].values,
        "sample_time": h["sample_time"].values if "sample_time" in h.columns else np.nan,
        "y_true_log": boxcox1p(h["lab_value"].values, LMBDA),
        "y_pred_log": merf_pred_bc,
        "y_true_native": h["lab_value"].values,
        "y_pred_native": merf_pred_native,
    })

    # ============================================================
    # Run identical adaptation curves
    # ============================================================
    run_adaptation_curve(v4_predictions, "V4 BASELINE")
    run_adaptation_curve(merf_predictions, "MERF")


if __name__ == "__main__":
    main()
