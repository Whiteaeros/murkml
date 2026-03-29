"""v8: Custom MERF EM loop around CatBoost WITH native categorical features.

The MERF package can't pass categorical features to the underlying model.
GPBoost uses LightGBM which underperforms CatBoost on this dataset.
Solution: implement the EM loop ourselves around CatBoost, keeping native categoricals.

Architecture:
  y = f(X) + b_i[0] + b_i[1] * turbidity_instant + e
  - f(X) is CatBoost with all 44 features including 3 categorical
  - b_i is per-site [intercept, slope] drawn from N(0, D)
  - e ~ N(0, sigma^2)

EM algorithm:
  E-step: y* = y - Z @ b_hat  (subtract random effects)
  M-step: fit CatBoost on (X, y*), then update b_hat, D, sigma^2

Usage:
    python scripts/train_catboost_merf_v8.py
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


def load_data():
    """Load and prepare data exactly like v4 pipeline."""
    assembled = pd.read_parquet(DATA_DIR / "processed" / "turbidity_ssc_paired.parquet")
    basic = pd.read_parquet(DATA_DIR / "site_attributes.parquet")
    ws = load_streamcat_attrs(DATA_DIR)
    assembled["ssc_log1p"] = boxcox1p(assembled["lab_value"].values, LMBDA)

    tiers = build_feature_tiers(assembled, basic, ws)
    tier_data = tiers["C_sensor_basic_watershed"]["data"]
    feature_cols = tiers["C_sensor_basic_watershed"]["feature_cols"]

    drop_file = DATA_DIR / "optimized_drop_list.txt"
    if drop_file.exists():
        drop_list = set(open(drop_file).read().strip().split(","))
    else:
        drop_list = set()

    EXCLUDE = {
        "site_id", "sample_time", "lab_value", "match_gap_seconds", "window_count",
        "is_nondetect", "hydro_event", "ssc_log1p", "ssc_value",
        "total_phosphorus_log1p", "nitrate_nitrite_log1p",
        "orthophosphate_log1p", "tds_evaporative_log1p",
    }
    available = [
        c for c in feature_cols
        if c in tier_data.columns and c not in EXCLUDE and c not in drop_list
    ]
    num_cols = [
        c for c in available
        if tier_data[c].dtype in [np.float64, np.float32, np.int64, np.int32, float, int]
    ]
    cat_cols = [
        c for c in available
        if tier_data[c].dtype == object
    ]
    all_cols = num_cols + cat_cols

    split = pd.read_parquet(DATA_DIR / "train_holdout_split.parquet")
    holdout_ids = set(split[split["role"] == "holdout"]["site_id"])
    train_ids = set(split[split["role"] == "training"]["site_id"])

    train_data = tier_data[tier_data["site_id"].isin(train_ids)].copy()
    holdout_data = tier_data[tier_data["site_id"].isin(holdout_ids)].copy()

    return train_data, holdout_data, all_cols, num_cols, cat_cols


def prepare_features(df, all_cols, num_cols, cat_cols, train_medians=None):
    """Prepare feature matrix."""
    X = df[all_cols].copy()
    for c in cat_cols:
        X[c] = X[c].fillna("missing").astype(str)
    if train_medians is None:
        train_medians = {}
        for c in num_cols:
            med = float(X[c].median())
            train_medians[c] = med
            X[c] = X[c].fillna(med)
    else:
        for c in num_cols:
            X[c] = X[c].fillna(train_medians.get(c, 0.0))
    return X, train_medians


class CatBoostMERF:
    """Mixed-effects model with CatBoost fixed effects and per-site random effects.

    Implements the MERF EM algorithm directly around CatBoost, preserving
    native categorical feature support.

    Random effects: b_i = [intercept_i, slope_i] for each site i.
    Z matrix: [1, turbidity_instant] for each sample.
    """

    def __init__(self, max_em_iterations=10, catboost_params=None, cat_features=None):
        self.max_em_iterations = max_em_iterations
        self.catboost_params = catboost_params or {}
        self.cat_features = cat_features or []

        # Learned parameters
        self.fe_model = None
        self.b_hat = None       # DataFrame: index=site_id, columns=[0, 1]
        self.D_hat = None       # 2x2 covariance of random effects
        self.sigma2_hat = None  # residual variance
        self.gll_history = []

    def _build_Z(self, X, turbidity_col="turbidity_instant"):
        """Build random effects design matrix [1, turbidity]."""
        n = len(X)
        Z = np.ones((n, 2))
        Z[:, 1] = X[turbidity_col].values
        return Z

    def fit(self, X, y, sites, X_val=None, y_val=None, sites_val=None):
        """Fit using EM algorithm.

        Parameters
        ----------
        X : DataFrame with all features (including categoricals)
        y : array of target values (Box-Cox transformed)
        sites : array of site IDs
        X_val, y_val, sites_val : optional validation data
        """
        n_obs = len(y)
        Z = self._build_Z(X)
        q = Z.shape[1]  # 2 (intercept + slope)

        # Unique sites
        unique_sites = pd.Series(sites).unique()
        n_clusters = len(unique_sites)

        # Precompute per-cluster indices
        site_series = pd.Series(sites)
        indices_by_site = {}
        Z_by_site = {}
        y_by_site = {}
        n_by_site = {}
        I_by_site = {}

        for sid in unique_sites:
            mask = (site_series == sid).values
            indices_by_site[sid] = mask
            Z_by_site[sid] = Z[mask]
            y_by_site[sid] = y[mask]
            n_by_site[sid] = mask.sum()
            I_by_site[sid] = np.eye(mask.sum())

        # Initialize
        b_hat = pd.DataFrame(np.zeros((n_clusters, q)), index=unique_sites)
        sigma2_hat = 1.0
        D_hat = np.eye(q)

        cat_idx = [i for i, c in enumerate(X.columns) if c in self.cat_features]

        for iteration in range(1, self.max_em_iterations + 1):
            logger.info(f"EM iteration {iteration}/{self.max_em_iterations}")

            # ---- E-step: subtract random effects to get y* ----
            y_star = y.copy()
            for sid in unique_sites:
                mask = indices_by_site[sid]
                Z_i = Z_by_site[sid]
                b_i = b_hat.loc[sid].values
                y_star[mask] -= Z_i @ b_i

            # ---- M-step part 1: fit CatBoost on (X, y*) ----
            train_pool = Pool(X, y_star, cat_features=cat_idx)

            # For EM iterations < final, use fewer trees for speed
            params = self.catboost_params.copy()
            if iteration < self.max_em_iterations:
                params["iterations"] = min(params.get("iterations", 500), 300)

            if X_val is not None:
                val_pool = Pool(X_val, y_val, cat_features=cat_idx)
                model = CatBoostRegressor(**params)
                model.fit(train_pool, eval_set=val_pool)
            else:
                model = CatBoostRegressor(**params)
                model.fit(train_pool)

            f_hat = model.predict(train_pool)

            # ---- M-step part 2: update random effects ----
            sigma2_sum = 0
            D_sum = np.zeros((q, q))

            for sid in unique_sites:
                mask = indices_by_site[sid]
                y_i = y_by_site[sid]
                Z_i = Z_by_site[sid]
                n_i = n_by_site[sid]
                I_i = I_by_site[sid]
                f_hat_i = f_hat[mask]

                V_i = Z_i @ D_hat @ Z_i.T + sigma2_hat * I_i
                V_inv_i = np.linalg.pinv(V_i)

                # Update b_hat for this site
                b_i = D_hat @ Z_i.T @ V_inv_i @ (y_i - f_hat_i)
                b_hat.loc[sid] = b_i

                # Accumulate for sigma2 and D updates
                eps_i = y_i - f_hat_i - Z_i @ b_i
                sigma2_sum += eps_i @ eps_i + sigma2_hat * (n_i - sigma2_hat * np.trace(V_inv_i))
                D_sum += np.outer(b_i, b_i) + (D_hat - D_hat @ Z_i.T @ V_inv_i @ Z_i @ D_hat)

            sigma2_hat = max(sigma2_sum / n_obs, 1e-6)
            D_hat = D_sum / n_clusters

            # ---- Compute generalized log-likelihood ----
            gll = 0
            for sid in unique_sites:
                mask = indices_by_site[sid]
                y_i = y_by_site[sid]
                Z_i = Z_by_site[sid]
                I_i = I_by_site[sid]
                f_hat_i = f_hat[mask]
                R_i = sigma2_hat * I_i
                b_i = b_hat.loc[sid].values

                _, logdet_D = np.linalg.slogdet(D_hat)
                _, logdet_R = np.linalg.slogdet(R_i)

                resid = y_i - f_hat_i - Z_i @ b_i
                gll += (
                    resid @ np.linalg.pinv(R_i) @ resid
                    + b_i @ np.linalg.pinv(D_hat) @ b_i
                    + logdet_D + logdet_R
                )
            self.gll_history.append(gll)
            logger.info(f"  GLL = {gll:.1f}, sigma2 = {sigma2_hat:.4f}, "
                        f"D diag = [{D_hat[0,0]:.4f}, {D_hat[1,1]:.6f}]")

            # Check convergence
            if len(self.gll_history) > 1:
                rel_change = abs(gll - self.gll_history[-2]) / abs(self.gll_history[-2])
                if rel_change < 1e-4:
                    logger.info(f"  Converged (rel change = {rel_change:.2e})")
                    break

        self.fe_model = model
        self.b_hat = b_hat
        self.D_hat = D_hat
        self.sigma2_hat = sigma2_hat

        logger.info(f"Final: {model.tree_count_} trees, "
                    f"sigma2={sigma2_hat:.4f}, D={np.diag(D_hat)}")
        logger.info(f"Random intercept std: {np.sqrt(D_hat[0,0]):.4f}")
        logger.info(f"Random slope std: {np.sqrt(D_hat[1,1]):.6f}")

        return self

    def predict(self, X, sites, cat_idx=None):
        """Predict with fixed effects + random effects for known sites.

        For unknown sites, only fixed effects are used (b_i = 0).
        """
        if cat_idx is None:
            cat_idx = [i for i, c in enumerate(X.columns) if c in self.cat_features]
        pool = Pool(X, cat_features=cat_idx)
        y_hat = self.fe_model.predict(pool)

        Z = self._build_Z(X)
        known_sites = set(self.b_hat.index)

        for sid in pd.Series(sites).unique():
            if sid in known_sites:
                mask = (pd.Series(sites) == sid).values
                b_i = self.b_hat.loc[sid].values
                y_hat[mask] += Z[mask] @ b_i

        return y_hat


def evaluate_predictions(predictions, label):
    """Compute per-site and pooled metrics."""
    site_metrics = []
    for site_id in predictions["site_id"].unique():
        site = predictions[predictions["site_id"] == site_id]
        if len(site) < 3:
            continue
        y_true = site["y_true_native"].values
        y_pred = site["y_pred_native"].values

        ss_res = np.sum((y_true - y_pred) ** 2)
        ss_tot = np.sum((y_true - y_true.mean()) ** 2)
        r2 = 1 - ss_res / max(ss_tot, 1e-10)

        nonzero = y_true > 0
        if nonzero.sum() > 0:
            ape = np.abs(y_pred[nonzero] - y_true[nonzero]) / y_true[nonzero]
            mape = float(np.median(ape) * 100)
            ratio = y_pred[nonzero] / y_true[nonzero]
            f2 = float(np.mean((ratio >= 0.5) & (ratio <= 2.0)))
        else:
            mape, f2 = np.nan, np.nan

        site_metrics.append({
            "site_id": site_id, "n": len(site),
            "r2_native": r2, "mape_pct": mape, "frac_within_2x": f2,
        })

    sm = pd.DataFrame(site_metrics)

    y_true_all = predictions["y_true_native"].values
    y_pred_all = predictions["y_pred_native"].values
    ss_res = np.sum((y_true_all - y_pred_all) ** 2)
    ss_tot = np.sum((y_true_all - y_true_all.mean()) ** 2)
    pooled_r2 = 1 - ss_res / max(ss_tot, 1e-10)

    print(f"\n{'=' * 70}")
    print(f"  {label} RESULTS")
    print(f"{'=' * 70}")
    print(f"  Sites evaluated: {len(sm)}")
    print(f"  Holdout samples: {len(predictions)}")
    print(f"  Median per-site R2: {sm['r2_native'].median():.3f}")
    print(f"  Mean per-site R2:   {sm['r2_native'].mean():.3f}")
    print(f"  Pooled R2:          {pooled_r2:.3f}")
    print(f"  Median MAPE:        {sm['mape_pct'].median():.1f}%")
    print(f"  Median within 2x:   {sm['frac_within_2x'].median():.1%}")
    print(f"  25th pct R2:        {sm['r2_native'].quantile(0.25):.3f}")
    print(f"  75th pct R2:        {sm['r2_native'].quantile(0.75):.3f}")
    print(f"{'=' * 70}\n")

    return sm, pooled_r2


def run_adaptation_curve(predictions, label):
    """Run site adaptation curve."""
    from scipy.stats import linregress
    N_VALUES = [0, 1, 2, 3, 5, 10, 20]
    rng = np.random.default_rng(42)
    n_trials = 50

    print(f"\n{label} ADAPTATION CURVE:")
    results = {}

    for N in N_VALUES:
        all_site_r2s = []
        for site_id in predictions["site_id"].unique():
            site_data = predictions[predictions["site_id"] == site_id].reset_index(drop=True)
            n_samples = len(site_data)
            if n_samples < 3:
                continue

            if N == 0:
                y_t = site_data["y_true_native"].values
                y_p = site_data["y_pred_native"].values
                ss_res = np.sum((y_t - y_p) ** 2)
                ss_tot = np.sum((y_t - y_t.mean()) ** 2)
                r2 = 1 - ss_res / max(ss_tot, 1e-10)
                all_site_r2s.append(r2)
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

                y_t = test["y_true_native"].values
                ss_res = np.sum((y_t - corrected_native) ** 2)
                ss_tot = np.sum((y_t - y_t.mean()) ** 2)
                r2 = 1 - ss_res / max(ss_tot, 1e-10)
                trial_r2s.append(r2)

            if trial_r2s:
                all_site_r2s.append(np.median(trial_r2s))

        if all_site_r2s:
            med = np.median(all_site_r2s)
            q25 = np.percentile(all_site_r2s, 25)
            q75 = np.percentile(all_site_r2s, 75)
            print(f"  N={N:>2d}:  {len(all_site_r2s)} sites,  median R2={med:.3f}  [{q25:.3f} - {q75:.3f}]")
            results[N] = {"median_r2": med, "q25": q25, "q75": q75, "n_sites": len(all_site_r2s)}

    return results


def main():
    logger.info("Loading data...")
    train_data, holdout_data, all_cols, num_cols, cat_cols = load_data()
    logger.info(f"Train: {train_data.site_id.nunique()} sites, {len(train_data)} samples")
    logger.info(f"Holdout: {holdout_data.site_id.nunique()} sites, {len(holdout_data)} samples")

    # Prepare training data
    clean = train_data.dropna(subset=["ssc_log1p"]).copy()
    y = clean["ssc_log1p"].values
    sites = clean["site_id"].values
    X, train_medians = prepare_features(clean, all_cols, num_cols, cat_cols)

    cat_idx = [i for i, c in enumerate(all_cols) if c in cat_cols]

    # Train/val split for CatBoost early stopping
    from sklearn.model_selection import GroupShuffleSplit
    gss = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=42)
    train_idx, val_idx = next(gss.split(X, y, groups=sites))

    X_val = X.iloc[val_idx]
    y_val = y[val_idx]

    # Monotone constraints
    mono = {}
    for i, c in enumerate(all_cols):
        if c in {"turbidity_instant", "turbidity_max_1hr"}:
            mono[i] = 1

    catboost_params = {
        "iterations": 500,
        "learning_rate": 0.05,
        "depth": 6,
        "l2_leaf_reg": 3,
        "random_seed": 42,
        "verbose": 0,
        "early_stopping_rounds": 50,
        "thread_count": 12,
        "boosting_type": "Ordered",
        "monotone_constraints": mono,
    }

    # Train CatBoost-MERF
    logger.info("Training CatBoost-MERF...")
    merf = CatBoostMERF(
        max_em_iterations=10,
        catboost_params=catboost_params,
        cat_features=cat_cols,
    )
    merf.fit(X, y, sites, X_val=X_val, y_val=y_val, sites_val=sites[val_idx])

    # Save CatBoost model component
    model_path = MODEL_DIR / "ssc_C_v8_merf_cat.cbm"
    merf.fe_model.save_model(str(model_path))
    logger.info(f"Saved fixed-effects model to {model_path}")

    # ---- Holdout predictions (zero-shot: no random effects for new sites) ----
    logger.info("Generating holdout predictions...")
    h = holdout_data.copy()
    X_h, _ = prepare_features(h, all_cols, num_cols, cat_cols, train_medians)

    # Zero-shot: only fixed effects (holdout sites are unknown)
    pool_h = Pool(X_h, cat_features=cat_idx)
    pred_bc = merf.fe_model.predict(pool_h)
    pred_native = inv_transform(pred_bc)

    # BCF from training
    pool_train = Pool(X, cat_features=cat_idx)
    # Use fixed effects only for BCF (consistent with holdout eval)
    train_pred_fe = merf.fe_model.predict(pool_train)
    bcf = snowdon_bcf(clean["lab_value"].values, inv_transform(train_pred_fe))
    pred_native *= bcf
    logger.info(f"BCF (fixed effects only): {bcf:.4f}")

    # Also compute BCF with random effects for completeness
    train_pred_full = merf.predict(X, sites, cat_idx)
    bcf_full = snowdon_bcf(clean["lab_value"].values, inv_transform(train_pred_full))
    logger.info(f"BCF (with random effects): {bcf_full:.4f}")

    predictions = pd.DataFrame({
        "site_id": h["site_id"].values,
        "sample_time": h["sample_time"].values if "sample_time" in h.columns else np.nan,
        "y_true_log": boxcox1p(h["lab_value"].values, LMBDA),
        "y_pred_log": pred_bc,
        "y_true_native": h["lab_value"].values,
        "y_pred_native": pred_native,
    })

    # Evaluate
    sm, pooled_r2 = evaluate_predictions(predictions, "CatBoost-MERF v8")
    adapt_results = run_adaptation_curve(predictions, "CatBoost-MERF v8")

    # Save metadata
    meta = {
        "schema_version": 2,
        "param": "ssc",
        "tier": "C_sensor_basic_watershed",
        "transform_type": "boxcox",
        "transform_lmbda": LMBDA,
        "feature_cols": all_cols,
        "cat_cols": cat_cols,
        "cat_indices": cat_idx,
        "train_median": train_medians,
        "n_trees": merf.fe_model.tree_count_,
        "bcf": bcf,
        "bcf_method": "snowdon",
        "architecture": "catboost_merf_em",
        "em_iterations": len(merf.gll_history),
        "random_effects": "site_id intercept + turbidity_instant slope",
        "sigma2_hat": float(merf.sigma2_hat),
        "D_hat": merf.D_hat.tolist(),
        "monotone_constraints": True,
    }
    meta_path = MODEL_DIR / "ssc_C_v8_merf_cat_meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    # Save predictions
    pred_path = DATA_DIR / "results" / "holdout_predictions_v8_merf_cat.parquet"
    predictions.to_parquet(pred_path)
    logger.info(f"Saved predictions to {pred_path}")

    # Comparison
    print("\n" + "=" * 70)
    print("  COMPARISON TO BASELINES")
    print("=" * 70)
    print(f"  v4 baseline (CatBoost):       holdout median R2 = 0.472")
    print(f"  v6 MERF (no categoricals):    holdout median R2 = 0.417")
    print(f"  v8 CatBoost-MERF (w/ cats):   holdout median R2 = {sm['r2_native'].median():.3f}")
    delta = sm['r2_native'].median() - 0.472
    print(f"  Delta vs v4: {delta:+.3f}  {'BETTER' if delta > 0 else 'WORSE'}")
    print("=" * 70)


if __name__ == "__main__":
    main()
