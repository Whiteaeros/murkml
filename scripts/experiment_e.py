"""Experiment E: MERF (Mixed-Effects Random Forest) with CatBoost.

Tests whether per-site random effects with proper shrinkage fix the
site adaptation problem and improve cross-site predictions.
"""
import sys
import warnings
import time
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import boxcox1p
from sklearn.model_selection import GroupShuffleSplit
from catboost import CatBoostRegressor
from merf import MERF

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


def compute_metrics(y_true, y_pred):
    """Compute R², MAPE, within-2x on native space."""
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - y_true.mean()) ** 2)
    r2 = 1 - ss_res / max(ss_tot, 1e-10)

    nz = y_true > 0
    if nz.sum() > 0:
        ape = np.abs(y_pred[nz] - y_true[nz]) / y_true[nz]
        mape = np.median(ape) * 100
        ratio = y_pred[nz] / y_true[nz]
        f2 = np.mean((ratio >= 0.5) & (ratio <= 2.0))
    else:
        mape, f2 = np.nan, np.nan

    return {"r2": r2, "mape_pct": mape, "frac_within_2x": f2}


def main():
    train_data, holdout_data, num_cols, cat_cols = prepare_data()
    target_col = "ssc_log1p"

    # MERF can't handle categoricals directly — one-hot encode them
    # But first, let's try with numeric-only features for simplicity
    cols = list(num_cols)  # numeric only for MERF
    print(f"Using {len(cols)} numeric features (MERF doesn't handle categoricals natively)")

    # Prepare training data
    clean = train_data.dropna(subset=[target_col]).copy()
    y = clean[target_col].values
    sites = clean["site_id"].values
    X = clean[cols].copy()
    for c in cols:
        X[c] = X[c].fillna(X[c].median())

    # Z matrix: random intercept + random slope on turbidity_instant
    turb_col_idx = cols.index("turbidity_instant") if "turbidity_instant" in cols else 0
    Z = np.ones((len(X), 2))
    Z[:, 1] = X["turbidity_instant"].values

    clusters = pd.Series(sites)

    print(f"Training data: {len(X)} samples, {clusters.nunique()} sites")
    print(f"Z matrix: intercept + slope on turbidity_instant")

    # Train MERF
    cb = CatBoostRegressor(
        iterations=500, learning_rate=0.05, depth=6,
        l2_leaf_reg=3, random_seed=42, verbose=0,
        early_stopping_rounds=50, thread_count=12,
    )

    mrf = MERF(fixed_effects_model=cb, max_iterations=10)
    print("\nTraining MERF (10 EM iterations)...")
    t0 = time.time()
    mrf.fit(X, Z, clusters, y)
    elapsed = time.time() - t0
    print(f"MERF training: {elapsed:.0f}s")

    # Analyze random effects
    b = mrf.trained_b
    print(f"\nRandom effects for {len(b)} sites:")
    intercepts = [b[k][0] for k in b]
    slopes = [b[k][1] for k in b]
    print(f"  Intercept: mean={np.mean(intercepts):.4f}, std={np.std(intercepts):.4f}")
    print(f"  Slope:     mean={np.mean(slopes):.6f}, std={np.std(slopes):.6f}")

    # Predict on training data (with random effects)
    train_pred_bc = mrf.predict(X, Z, clusters)
    train_pred_native = np.clip(safe_inv_boxcox1p(train_pred_bc, LMBDA), 0, None)
    train_true_native = clean["lab_value"].values
    bcf = snowdon_bcf(train_true_native, train_pred_native)
    train_pred_native *= bcf
    print(f"\nBCF (Snowdon): {bcf:.4f}")

    train_metrics = compute_metrics(train_true_native, train_pred_native)
    print(f"Training R²(native): {train_metrics['r2']:.3f}")

    # Predict on holdout (NO random effects — new sites)
    h = holdout_data.copy()
    X_h = h[cols].copy()
    train_median = {c: float(X[c].median()) for c in cols}
    for c in cols:
        X_h[c] = X_h[c].fillna(train_median[c])

    Z_h = np.ones((len(X_h), 2))
    Z_h[:, 1] = X_h["turbidity_instant"].values
    h_clusters = pd.Series(h["site_id"].values)

    h_pred_bc = mrf.predict(X_h, Z_h, h_clusters)
    h_pred_native = np.clip(safe_inv_boxcox1p(h_pred_bc, LMBDA), 0, None) * bcf
    h_true_native = h["lab_value"].values

    # Pooled holdout metrics
    pooled = compute_metrics(h_true_native, h_pred_native)
    print(f"\nHoldout (zero-shot, no random effects):")
    print(f"  Pooled R²(native): {pooled['r2']:.3f}")
    print(f"  MAPE: {pooled['mape_pct']:.1f}%")
    print(f"  Within 2x: {pooled['frac_within_2x']:.1%}")

    # Per-site holdout metrics
    site_r2s = []
    for sid in h["site_id"].unique():
        mask = h["site_id"].values == sid
        yt = h_true_native[mask]
        yp = h_pred_native[mask]
        if len(yt) >= 5 and yt.std() > 0:
            sr = 1 - np.sum((yt - yp) ** 2) / max(np.sum((yt - yt.mean()) ** 2), 1e-10)
            site_r2s.append(sr)

    print(f"  Median site R²: {np.median(site_r2s):.3f}")
    print(f"  % negative: {100 * np.mean(np.array(site_r2s) < 0):.0f}%")

    # Site adaptation simulation
    # For each holdout site: use N samples to estimate random effects, predict rest
    print("\n" + "=" * 70)
    print("MERF SITE ADAPTATION CURVE")
    print("=" * 70)

    N_VALUES = [0, 1, 2, 3, 5, 10, 20]
    rng = np.random.default_rng(42)

    for N in N_VALUES:
        if N == 0:
            # Already computed above
            print(f"  N={N:>2d}: R²={pooled['r2']:.3f}, MAPE={pooled['mape_pct']:.1f}%, Within2x={pooled['frac_within_2x']:.1%}")
            continue

        site_results = []
        for sid in h["site_id"].unique():
            mask = h["site_id"].values == sid
            site_X = X_h[mask].copy()
            site_Z = Z_h[mask]
            site_y = clean_y = boxcox1p(h_true_native[mask], LMBDA)
            n_site = mask.sum()

            if N >= n_site - 2:
                continue

            # Random split: N for calibration, rest for test
            trial_r2s = []
            for trial in range(min(20, 50)):
                cal_idx = rng.choice(n_site, N, replace=False)
                test_idx = np.setdiff1d(np.arange(n_site), cal_idx)

                # Estimate random effects from calibration samples
                # Use the MERF's trained fixed effects + estimate b_i from cal data
                cal_X = site_X.iloc[cal_idx]
                cal_Z = site_Z[cal_idx]
                cal_y_bc = site_y[cal_idx]

                # Fixed effect prediction on cal
                fe_pred_cal = mrf.fe_model.predict(cal_X)
                residuals = cal_y_bc - fe_pred_cal

                # Estimate random effect: b_i = (Z'Z + D^-1)^-1 Z' residuals
                # Simplified: use OLS on residuals = Z @ b
                try:
                    from numpy.linalg import lstsq
                    b_i, _, _, _ = lstsq(cal_Z, residuals, rcond=None)
                    # Shrinkage: blend toward zero based on N
                    shrinkage = N / (N + 10)  # k=10 regularization
                    b_i = b_i * shrinkage
                except Exception:
                    b_i = np.zeros(2)

                # Predict test samples with estimated random effects
                test_X = site_X.iloc[test_idx]
                test_Z = site_Z[test_idx]
                fe_pred_test = mrf.fe_model.predict(test_X)
                pred_bc = fe_pred_test + test_Z @ b_i
                pred_native = np.clip(safe_inv_boxcox1p(pred_bc, LMBDA), 0, None) * bcf
                true_native = h_true_native[mask][test_idx]

                if len(true_native) >= 3 and true_native.std() > 0:
                    sr = 1 - np.sum((true_native - pred_native) ** 2) / max(np.sum((true_native - true_native.mean()) ** 2), 1e-10)
                    trial_r2s.append(sr)

            if trial_r2s:
                site_results.append(np.median(trial_r2s))

        if site_results:
            arr = np.array(site_results)
            median_r2 = np.median(arr)
            print(f"  N={N:>2d}: median site R²={median_r2:.3f} ({len(arr)} sites), % negative={100*(arr<0).mean():.0f}%")

    print("\n" + "=" * 70)
    print("COMPARISON: MERF vs v4 baseline")
    print("=" * 70)
    print(f"{'Metric':30s} {'v4-baseline':>12s} {'MERF':>12s}")
    print("-" * 55)
    print(f"{'Holdout pooled R²':30s} {'0.211':>12s} {pooled['r2']:>12.3f}")
    print(f"{'Holdout median site R²':30s} {'0.290':>12s} {np.median(site_r2s):>12.3f}")
    print(f"{'MAPE':30s} {'---':>12s} {pooled['mape_pct']:>12.1f}%")
    print(f"{'Within 2x':30s} {'---':>12s} {pooled['frac_within_2x']*100:>11.1f}%")


if __name__ == "__main__":
    main()
