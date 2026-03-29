"""v8: Post-hoc Bayesian shrinkage random effects on top of v4 CatBoost.

Instead of MERF EM loop (which corrupts fixed effects for zero-shot), this:
1. Keeps v4 CatBoost model untouched (best zero-shot)
2. Learns population-level RE variance (D, sigma2) from v4 training residuals
3. For new-site adaptation, uses Bayesian shrinkage estimator instead of
   naive linear correction

The shrinkage estimator:
  b_hat = D @ Z' @ (Z @ D @ Z' + sigma2 * I)^{-1} @ residuals

With few calibration samples, estimates shrink toward 0. With many, approaches OLS.
This should fix "adaptation hurts with <10 samples" problem.

Uses site_adaptation.py data loading for apples-to-apples comparison.

Usage:
    python scripts/train_posthoc_re_v8.py
"""
from __future__ import annotations

import json
import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import boxcox1p
from scipy.stats import linregress
from catboost import CatBoostRegressor, Pool

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from murkml.data.attributes import build_feature_tiers, load_streamcat_attrs
from murkml.evaluate.metrics import snowdon_bcf, safe_inv_boxcox1p

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"
MODEL_DIR = DATA_DIR / "results" / "models"
LMBDA = 0.2


def inv_transform(y):
    return np.clip(safe_inv_boxcox1p(y, LMBDA), 0, None)


def load_holdout_predictions_via_site_adaptation():
    """Load holdout predictions using site_adaptation.py's exact data path."""
    from murkml.data.attributes import load_streamcat_attrs

    # Load model + meta (same as site_adaptation.py)
    model = CatBoostRegressor()
    model.load_model(str(MODEL_DIR / "ssc_C_sensor_basic_watershed.cbm"))
    with open(MODEL_DIR / "ssc_C_sensor_basic_watershed_meta.json") as f:
        meta = json.load(f)

    feature_cols = meta["feature_cols"]
    cat_cols = meta["cat_cols"]
    num_cols = [c for c in feature_cols if c not in cat_cols]
    train_median = meta.get("train_median", {})
    bcf = meta["bcf"]

    # Load paired data + split (same as site_adaptation.py)
    paired = pd.read_parquet(DATA_DIR / "processed" / "turbidity_ssc_paired.parquet")
    split = pd.read_parquet(DATA_DIR / "train_holdout_split.parquet")

    holdout_ids = set(split[split["role"] == "holdout"]["site_id"])
    train_ids = set(split[split["role"] == "training"]["site_id"])

    # ---- HOLDOUT predictions (same merge path as site_adaptation.py) ----
    holdout_raw = paired[paired["site_id"].isin(holdout_ids)].copy()
    train_raw = paired[paired["site_id"].isin(train_ids)].copy()

    ws_attrs = load_streamcat_attrs(DATA_DIR)
    basic_attrs = pd.read_parquet(DATA_DIR / "site_attributes.parquet")

    def merge_attrs(df):
        basic_cols_available = [c for c in basic_attrs.columns if c != "site_id"]
        df = df.merge(
            basic_attrs[["site_id"] + basic_cols_available].drop_duplicates("site_id"),
            on="site_id", how="left",
        )
        ws_cols = set(ws_attrs.columns) - {"site_id"}
        for col in ["drainage_area_km2", "huc2", "slope_pct"]:
            if col in df.columns and col in ws_cols:
                df = df.drop(columns=[col])
        df = df.merge(ws_attrs, on="site_id", how="left")
        return df

    holdout_data = merge_attrs(holdout_raw)
    train_data = merge_attrs(train_raw)

    def prep_and_predict(data, label):
        for c in feature_cols:
            if c not in data.columns:
                data[c] = np.nan
        X = data[feature_cols].copy()
        for col in num_cols:
            if col in train_median:
                X[col] = X[col].fillna(train_median[col])
        for col in cat_cols:
            X[col] = X[col].fillna("missing").astype(str)
        cat_indices = [feature_cols.index(c) for c in cat_cols]
        pool = Pool(X, cat_features=cat_indices)
        y_pred_log = model.predict(pool)

        native_vals = data["lab_value"].values
        result = pd.DataFrame({
            "site_id": data["site_id"].values,
            "y_true_log": boxcox1p(native_vals, LMBDA),
            "y_pred_log": y_pred_log,
            "y_true_native": native_vals,
            "y_pred_native": inv_transform(y_pred_log),  # no BCF yet, like site_adaptation.py
            "turbidity_instant": X["turbidity_instant"].values,
        })
        logger.info(f"{label}: {result.site_id.nunique()} sites, {len(result)} samples")
        return result

    holdout_preds = prep_and_predict(holdout_data, "Holdout")
    train_preds = prep_and_predict(train_data, "Training")

    return holdout_preds, train_preds, meta


class PostHocRandomEffects:
    """Bayesian shrinkage random effects from pre-trained model residuals."""

    def __init__(self):
        self.D = None
        self.sigma2 = None
        self.b_hat = {}

    def fit_from_residuals(self, residuals, turb_values, sites):
        """Estimate D and sigma2 from model residuals.

        Uses intercept-only random effects (slope adds noise, converges to ~0
        in the MERF experiments).
        """
        q = 1  # intercept only
        unique_sites = pd.Series(sites).unique()
        n_clusters = len(unique_sites)

        # Per-site mean residual (= OLS intercept estimate)
        site_means = {}
        site_counts = {}
        for sid in unique_sites:
            mask = (sites == sid)
            r_i = residuals[mask]
            site_means[sid] = np.mean(r_i)
            site_counts[sid] = len(r_i)

        # Estimate D (variance of random intercepts)
        means_array = np.array(list(site_means.values()))
        # Method of moments: Var(b_hat_OLS) = D + sigma2/n_i
        # Use pooled within-site variance as sigma2 estimate first
        total_within = 0
        total_n = 0
        for sid in unique_sites:
            mask = (sites == sid)
            r_i = residuals[mask]
            if len(r_i) > 1:
                total_within += np.sum((r_i - np.mean(r_i)) ** 2)
                total_n += len(r_i) - 1
        self.sigma2 = max(total_within / max(total_n, 1), 1e-6)

        # D = Var(site_means) - E[sigma2/n_i]
        var_means = np.var(means_array)
        avg_var_correction = self.sigma2 * np.mean([1.0 / max(n, 1) for n in site_counts.values()])
        self.D = np.array([[max(var_means - avg_var_correction, 1e-6)]])

        # Compute shrinkage estimates for training sites
        for sid in unique_sites:
            mask = (sites == sid)
            r_i = residuals[mask]
            n_i = len(r_i)
            # Shrinkage factor: D / (D + sigma2/n_i)
            shrinkage = self.D[0, 0] / (self.D[0, 0] + self.sigma2 / n_i)
            self.b_hat[sid] = np.array([shrinkage * np.mean(r_i)])

        logger.info(f"Post-hoc RE fit: {n_clusters} sites")
        logger.info(f"  sigma2 = {self.sigma2:.4f} (within-site variance)")
        logger.info(f"  D = {self.D[0,0]:.4f} (between-site intercept variance)")
        logger.info(f"  RE std = {np.sqrt(self.D[0,0]):.4f}")
        logger.info(f"  Mean |shrunk intercept|: {np.mean([abs(b[0]) for b in self.b_hat.values()]):.4f}")

        # Shrinkage analysis
        shrink_1 = self.D[0, 0] / (self.D[0, 0] + self.sigma2 / 1)
        shrink_3 = self.D[0, 0] / (self.D[0, 0] + self.sigma2 / 3)
        shrink_5 = self.D[0, 0] / (self.D[0, 0] + self.sigma2 / 5)
        shrink_10 = self.D[0, 0] / (self.D[0, 0] + self.sigma2 / 10)
        shrink_20 = self.D[0, 0] / (self.D[0, 0] + self.sigma2 / 20)
        logger.info(f"  Shrinkage factors: N=1: {shrink_1:.3f}, N=3: {shrink_3:.3f}, "
                    f"N=5: {shrink_5:.3f}, N=10: {shrink_10:.3f}, N=20: {shrink_20:.3f}")

    def estimate_for_new_site(self, residuals):
        """Estimate random intercept for a new site given calibration residuals.

        Uses Bayesian shrinkage: b_hat = (D / (D + sigma2/n)) * mean(residuals)
        """
        n = len(residuals)
        if n == 0:
            return 0.0
        shrinkage = self.D[0, 0] / (self.D[0, 0] + self.sigma2 / n)
        return shrinkage * np.mean(residuals)


def compute_site_r2(y_true, y_pred):
    if len(y_true) < 3:
        return np.nan
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - y_true.mean()) ** 2)
    return 1 - ss_res / max(ss_tot, 1e-10)


def main():
    logger.info("Loading data via site_adaptation.py path...")
    holdout_preds, train_preds, meta = load_holdout_predictions_via_site_adaptation()
    bcf = meta["bcf"]

    # Fit post-hoc RE from training residuals
    residuals = train_preds["y_true_log"].values - train_preds["y_pred_log"].values
    turb_values = train_preds["turbidity_instant"].values
    sites = train_preds["site_id"].values

    re_model = PostHocRandomEffects()
    re_model.fit_from_residuals(residuals, turb_values, sites)

    # ---- Zero-shot baseline (should match v4 = 0.472) ----
    # Apply BCF like site_adaptation does
    zero_shot_r2s = []
    for site_id in holdout_preds["site_id"].unique():
        site = holdout_preds[holdout_preds["site_id"] == site_id]
        if len(site) < 3:
            continue
        # site_adaptation.py applies BCF via the correction mechanism, not globally
        # At N=0, it uses the raw predictions with BCF applied via the Snowdon factor
        # Let's just compute R2 on raw predictions (no BCF)
        y_true = site["y_true_native"].values
        y_pred = site["y_pred_native"].values  # no BCF
        r2 = compute_site_r2(y_true, y_pred)
        zero_shot_r2s.append(r2)

    print(f"\nZero-shot (no BCF): median R2 = {np.median(zero_shot_r2s):.3f}, {len(zero_shot_r2s)} sites")

    # With BCF
    zero_shot_r2s_bcf = []
    for site_id in holdout_preds["site_id"].unique():
        site = holdout_preds[holdout_preds["site_id"] == site_id]
        if len(site) < 3:
            continue
        y_true = site["y_true_native"].values
        y_pred = site["y_pred_native"].values * bcf
        r2 = compute_site_r2(y_true, y_pred)
        zero_shot_r2s_bcf.append(r2)
    print(f"Zero-shot (with BCF={bcf:.3f}): median R2 = {np.median(zero_shot_r2s_bcf):.3f}")

    # ---- Run adaptation comparison ----
    N_VALUES = [0, 1, 2, 3, 5, 10, 20]
    rng = np.random.default_rng(42)
    n_trials = 50

    print(f"\n{'='*75}")
    print(f"  ADAPTATION COMPARISON: Naive (v4) vs Bayesian Shrinkage RE")
    print(f"{'='*75}")
    print(f"{'N':>4s}  {'Naive':>8s}  {'Bayes-RE':>10s}  {'Delta':>8s}  {'n_sites':>8s}")
    print("-" * 55)

    for N in N_VALUES:
        naive_r2s = []
        bayes_r2s = []

        for site_id in holdout_preds["site_id"].unique():
            site_data = holdout_preds[holdout_preds["site_id"] == site_id].reset_index(drop=True)
            n_samples = len(site_data)
            if n_samples < 3:
                continue

            if N == 0:
                # No BCF for zero-shot (consistent with site_adaptation.py N=0 behavior)
                r2 = compute_site_r2(
                    site_data["y_true_native"].values,
                    site_data["y_pred_native"].values,
                )
                naive_r2s.append(r2)
                bayes_r2s.append(r2)
                continue

            if N >= n_samples - 2:
                continue

            naive_trials = []
            bayes_trials = []

            for trial in range(n_trials):
                cal_idx = rng.choice(n_samples, N, replace=False)
                test_idx = np.setdiff1d(np.arange(n_samples), cal_idx)
                cal = site_data.iloc[cal_idx]
                test = site_data.iloc[test_idx]

                # ---- Naive correction (same as site_adaptation.py) ----
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

                r2_naive = compute_site_r2(test["y_true_native"].values, corrected_native)
                naive_trials.append(r2_naive)

                # ---- Bayesian shrinkage RE correction ----
                # Compute residuals in Box-Cox space on calibration samples
                cal_residuals = cal["y_true_log"].values - cal["y_pred_log"].values
                b_hat = re_model.estimate_for_new_site(cal_residuals)

                # Apply intercept correction to test predictions (in Box-Cox space)
                corrected_log_re = test["y_pred_log"].values + b_hat
                corrected_native_re = inv_transform(corrected_log_re)

                # BCF estimated from calibration with RE correction
                cal_corrected_re = inv_transform(cal["y_pred_log"].values + b_hat)
                cal_corrected_re = np.clip(cal_corrected_re, 1e-6, None)
                cal_bcf_re = np.mean(cal["y_true_native"].values) / np.mean(cal_corrected_re)
                cal_bcf_re = np.clip(cal_bcf_re, 0.1, 10.0)
                corrected_native_re *= cal_bcf_re

                r2_bayes = compute_site_r2(test["y_true_native"].values, corrected_native_re)
                bayes_trials.append(r2_bayes)

            if naive_trials:
                naive_r2s.append(np.median(naive_trials))
            if bayes_trials:
                bayes_r2s.append(np.median(bayes_trials))

        if naive_r2s:
            naive_med = np.median(naive_r2s)
            bayes_med = np.median(bayes_r2s)
            delta = bayes_med - naive_med
            marker = " *" if delta > 0 else ""
            print(f"  N={N:>2d}:  {naive_med:>7.3f}   {bayes_med:>9.3f}  {delta:>+7.3f}  {len(naive_r2s):>6d}{marker}")

    print(f"\n  * = Bayesian RE better than naive correction")
    print(f"{'='*75}")

    # Save RE params
    re_params = {
        "D": re_model.D.tolist(),
        "sigma2": float(re_model.sigma2),
        "n_training_sites": len(re_model.b_hat),
        "method": "post_hoc_bayesian_shrinkage_intercept_only",
        "base_model": "ssc_C_sensor_basic_watershed.cbm",
        "bcf": bcf,
    }
    re_path = MODEL_DIR / "ssc_C_v8_posthoc_re_params.json"
    with open(re_path, "w") as f:
        json.dump(re_params, f, indent=2)
    logger.info(f"Saved RE params to {re_path}")


if __name__ == "__main__":
    main()
