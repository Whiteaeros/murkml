"""v8: GPBoost mixed-effects gradient boosting with native categorical support.

GPBoost = LightGBM + Gaussian process / grouped random effects, trained jointly
(not EM like MERF). This keeps all 44 features including categoricals (collection_method,
turb_source, sensor_family) which MERF had to drop.

Architecture:
  y = f(X) + b_i + c_i * turbidity + e
  where f(X) is a LightGBM tree ensemble (fixed effects),
  b_i is a per-site random intercept,
  c_i is a per-site random slope on turbidity_instant,
  e ~ N(0, sigma^2)

Usage:
    python scripts/train_gpboost_v8.py
    python scripts/train_gpboost_v8.py --anchor  # use top-96 anchor sites for fixed effects
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import boxcox1p

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

    # Apply same drop list as v4
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

    # Train/holdout split
    split = pd.read_parquet(DATA_DIR / "train_holdout_split.parquet")
    holdout_ids = set(split[split["role"] == "holdout"]["site_id"])
    train_ids = set(split[split["role"] == "training"]["site_id"])

    train_data = tier_data[tier_data["site_id"].isin(train_ids)].copy()
    holdout_data = tier_data[tier_data["site_id"].isin(holdout_ids)].copy()

    return train_data, holdout_data, all_cols, num_cols, cat_cols


def prepare_features(df, all_cols, num_cols, cat_cols, train_medians=None):
    """Prepare feature matrix. Returns X, medians dict."""
    X = df[all_cols].copy()

    # Fill categoricals
    for c in cat_cols:
        X[c] = X[c].fillna("missing").astype("category")

    # Fill numerics
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


def train_gpboost(
    train_data, all_cols, num_cols, cat_cols, anchor_ids=None, label="v8"
):
    """Train GPBoost model with site-level random effects.

    Parameters
    ----------
    anchor_ids : set or None
        If provided, train fixed effects on these sites only, but estimate
        random effects from all training sites.
    """
    import gpboost as gpb

    clean = train_data.dropna(subset=["ssc_log1p"]).copy()
    y = clean["ssc_log1p"].values
    sites = clean["site_id"].values

    X, train_medians = prepare_features(clean, all_cols, num_cols, cat_cols)

    # Identify categorical feature indices for GPBoost/LightGBM
    cat_feature_names = cat_cols  # GPBoost accepts column names

    logger.info(f"Training data: {len(clean)} samples, {pd.Series(sites).nunique()} sites")
    logger.info(f"Features: {len(all_cols)} ({len(num_cols)} numeric + {len(cat_cols)} categorical)")
    logger.info(f"Categorical features: {cat_cols}")

    # ---- GPModel: site-level random intercept + random slope on turbidity ----
    # group_data = site_id for each sample (random intercept)
    # group_rand_coef_data = turbidity_instant (random slope)
    group_data = pd.Series(sites).values
    turb_values = X["turbidity_instant"].values.reshape(-1, 1)

    gp_model = gpb.GPModel(
        group_data=group_data,
        group_rand_coef_data=turb_values,
        ind_effect_group_rand_coef=[1],  # same grouping variable for slope
        likelihood="gaussian",
    )

    # ---- Train/val split for early stopping (site-aware) ----
    from sklearn.model_selection import GroupShuffleSplit
    gss = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=42)
    train_idx, val_idx = next(gss.split(X, y, groups=sites))

    # If anchor mode: train fixed effects on anchor subset only,
    # but the random effects model sees all sites
    if anchor_ids is not None:
        anchor_mask = pd.Series(sites).isin(anchor_ids).values
        # For the tree training, we still use the GroupShuffleSplit but filter
        # Actually GPBoost trains jointly, so we filter to anchor sites for the
        # training set and use the rest for validation
        anchor_in_train = anchor_mask & np.isin(np.arange(len(sites)), train_idx)
        non_anchor_in_train = ~anchor_mask & np.isin(np.arange(len(sites)), train_idx)

        # Use anchor sites for training, non-anchor for validation
        train_idx = np.where(anchor_in_train)[0]
        val_idx_new = np.where(non_anchor_in_train)[0]
        if len(val_idx_new) > 0:
            val_idx = val_idx_new
        logger.info(f"Anchor mode: {len(train_idx)} anchor samples, {len(val_idx)} val samples")

    # Create datasets
    data_train = gpb.Dataset(
        data=X.iloc[train_idx],
        label=y[train_idx],
        categorical_feature=cat_feature_names,
    )
    data_val = gpb.Dataset(
        data=X.iloc[val_idx],
        label=y[val_idx],
        categorical_feature=cat_feature_names,
        reference=data_train,
    )

    # GPModel for training subset
    gp_model_train = gpb.GPModel(
        group_data=sites[train_idx],
        group_rand_coef_data=turb_values[train_idx],
        ind_effect_group_rand_coef=[1],
        likelihood="gaussian",
    )
    gp_model_train.set_prediction_data(
        group_data_pred=sites[val_idx],
        group_rand_coef_data_pred=turb_values[val_idx],
    )

    # ---- LightGBM parameters (similar to v4 CatBoost settings) ----
    params = {
        "objective": "regression_l2",
        "learning_rate": 0.05,
        "max_depth": 6,
        "num_leaves": 63,          # 2^6 - 1
        "min_data_in_leaf": 20,
        "lambda_l2": 3.0,          # L2 regularization (like CatBoost l2_leaf_reg)
        "feature_fraction": 0.8,
        "bagging_freq": 0,
        "verbose": -1,
        "num_threads": 12,
        "seed": 42,
        "monotone_constraints": [
            1 if c == "turbidity_instant" else
            1 if c == "turbidity_max_1hr" else
            0
            for c in all_cols
        ],
    }

    logger.info("Training GPBoost...")
    bst = gpb.train(
        params=params,
        train_set=data_train,
        gp_model=gp_model_train,
        num_boost_round=1000,
        valid_sets=[data_val],
        callbacks=[gpb.early_stopping(50), gpb.print_evaluation(100)],
    )

    n_trees = bst.num_trees()
    logger.info(f"GPBoost trained: {n_trees} trees")

    # ---- Re-fit GPModel on ALL training data for final random effects ----
    logger.info("Re-fitting random effects on full training data...")
    gp_model_full = gpb.GPModel(
        group_data=sites,
        group_rand_coef_data=turb_values,
        ind_effect_group_rand_coef=[1],
        likelihood="gaussian",
    )
    data_full = gpb.Dataset(
        data=X,
        label=y,
        categorical_feature=cat_feature_names,
    )
    bst_full = gpb.train(
        params=params,
        train_set=data_full,
        gp_model=gp_model_full,
        num_boost_round=n_trees,  # use same number of trees
    )
    logger.info("Full model trained.")

    # Compute BCF
    pred_train = bst_full.predict(
        data=X,
        group_data_pred=sites,
        group_rand_coef_data_pred=turb_values,
        pred_latent=False,
    )
    pred_train_native = inv_transform(pred_train["response_mean"])
    bcf = snowdon_bcf(clean["lab_value"].values, pred_train_native)
    logger.info(f"BCF: {bcf:.4f}")

    return bst_full, gp_model_full, train_medians, bcf, n_trees


def predict_holdout(bst, holdout_data, all_cols, num_cols, cat_cols, train_medians, bcf):
    """Generate holdout predictions (zero-shot: no random effects for new sites)."""
    h = holdout_data.copy()
    X_h, _ = prepare_features(h, all_cols, num_cols, cat_cols, train_medians)

    sites_h = h["site_id"].values
    turb_h = X_h["turbidity_instant"].values.reshape(-1, 1)

    # For holdout (new sites), GPBoost uses fixed effects only (no random effects)
    # We achieve this by predicting without group_data_pred
    pred = bst.predict(
        data=X_h,
        group_data_pred=sites_h,
        group_rand_coef_data_pred=turb_h,
        pred_latent=False,
    )
    pred_bc = pred["response_mean"]
    pred_native = inv_transform(pred_bc) * bcf

    predictions = pd.DataFrame({
        "site_id": h["site_id"].values,
        "sample_time": h["sample_time"].values if "sample_time" in h.columns else np.nan,
        "y_true_log": boxcox1p(h["lab_value"].values, LMBDA),
        "y_pred_log": pred_bc,
        "y_true_native": h["lab_value"].values,
        "y_pred_native": pred_native,
    })

    return predictions


def evaluate_predictions(predictions, label):
    """Compute per-site and pooled metrics, print summary."""
    from scipy.stats import linregress

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
            "site_id": site_id,
            "n": len(site),
            "r2_native": r2,
            "mape_pct": mape,
            "frac_within_2x": f2,
        })

    sm = pd.DataFrame(site_metrics)

    # Pooled metrics
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
    print(f"  Median per-site R²: {sm['r2_native'].median():.3f}")
    print(f"  Mean per-site R²:   {sm['r2_native'].mean():.3f}")
    print(f"  Pooled R²:          {pooled_r2:.3f}")
    print(f"  Median MAPE:        {sm['mape_pct'].median():.1f}%")
    print(f"  Median within 2x:   {sm['frac_within_2x'].median():.1%}")
    print(f"  25th pct R²:        {sm['r2_native'].quantile(0.25):.3f}")
    print(f"  75th pct R²:        {sm['r2_native'].quantile(0.75):.3f}")
    print(f"{'=' * 70}\n")

    return sm, pooled_r2


def run_adaptation_curve(predictions, label):
    """Run site adaptation curve (identical to site_adaptation.py logic)."""
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


def save_model_and_meta(bst, all_cols, cat_cols, train_medians, bcf, n_trees, suffix="v8_gpboost"):
    """Save GPBoost model and metadata."""
    model_path = MODEL_DIR / f"ssc_C_{suffix}.json"
    meta_path = MODEL_DIR / f"ssc_C_{suffix}_meta.json"

    bst.save_model(str(model_path))
    logger.info(f"Saved model to {model_path}")

    meta = {
        "schema_version": 2,
        "param": "ssc",
        "tier": "C_sensor_basic_watershed",
        "transform_type": "boxcox",
        "transform_lmbda": LMBDA,
        "feature_cols": all_cols,
        "cat_cols": cat_cols,
        "train_median": train_medians,
        "n_trees": n_trees,
        "bcf": bcf,
        "bcf_method": "snowdon",
        "architecture": "gpboost_mixed_effects",
        "random_effects": "site_id intercept + turbidity_instant slope",
        "monotone_constraints": {
            "turbidity_instant": 1,
            "turbidity_max_1hr": 1,
        },
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    logger.info(f"Saved metadata to {meta_path}")

    return model_path, meta_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--anchor", action="store_true", help="Use anchor sites for fixed effects")
    args = parser.parse_args()

    # Load data
    logger.info("Loading data...")
    train_data, holdout_data, all_cols, num_cols, cat_cols = load_data()
    logger.info(f"Train: {train_data.site_id.nunique()} sites, {len(train_data)} samples")
    logger.info(f"Holdout: {holdout_data.site_id.nunique()} sites, {len(holdout_data)} samples")
    logger.info(f"Features: {len(all_cols)} ({len(num_cols)} num + {len(cat_cols)} cat)")

    # Anchor site selection
    anchor_ids = None
    suffix = "v8_gpboost"
    if args.anchor:
        scores_path = DATA_DIR / "results" / "anchor_site_scores.csv"
        if scores_path.exists():
            scores = pd.read_csv(scores_path)
            anchor_ids = set(scores.nlargest(96, "anchor_score")["site_id"])
            suffix = "v8_gpboost_anchor96"
            logger.info(f"Using {len(anchor_ids)} anchor sites for fixed effects")
        else:
            logger.warning("No anchor scores file found, training on all sites")

    # Train
    bst, gp_model, train_medians, bcf, n_trees = train_gpboost(
        train_data, all_cols, num_cols, cat_cols, anchor_ids=anchor_ids
    )

    # Predict holdout
    logger.info("Generating holdout predictions...")
    predictions = predict_holdout(
        bst, holdout_data, all_cols, num_cols, cat_cols, train_medians, bcf
    )

    # Evaluate
    site_metrics, pooled_r2 = evaluate_predictions(predictions, f"GPBoost {suffix}")

    # Adaptation curve
    adapt_results = run_adaptation_curve(predictions, f"GPBoost {suffix}")

    # Save
    save_model_and_meta(bst, all_cols, cat_cols, train_medians, bcf, n_trees, suffix)

    # Save predictions for further analysis
    pred_path = DATA_DIR / "results" / f"holdout_predictions_{suffix}.parquet"
    predictions.to_parquet(pred_path)
    logger.info(f"Saved predictions to {pred_path}")

    # Print comparison summary
    print("\n" + "=" * 70)
    print("  COMPARISON TO BASELINES")
    print("=" * 70)
    print(f"  v4 baseline (CatBoost):     holdout median R² = 0.472")
    print(f"  v6 MERF (no categoricals):  holdout median R² = 0.417")
    print(f"  v8 GPBoost ({suffix}):  holdout median R² = {site_metrics['r2_native'].median():.3f}")
    print(f"  {'BETTER' if site_metrics['r2_native'].median() > 0.472 else 'WORSE'} than v4 baseline")
    print("=" * 70)


if __name__ == "__main__":
    main()
