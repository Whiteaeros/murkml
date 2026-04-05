"""Leave-One-Group-Out cross-validation for CatBoost. Pure functions.

Handles fold splitting, per-fold NaN imputation, training, OOF prediction,
and per-fold metric computation. Matches legacy train_tiered.py behavior.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool
from sklearn.model_selection import GroupShuffleSplit, LeaveOneGroupOut

from murkml.config import ModelConfig
from murkml.evaluate.metrics import (
    kge,
    native_space_metrics,
    r_squared,
    safe_inv_boxcox1p,
    snowdon_bcf,
)
from murkml.training.model import build_catboost_params, compute_monotone_constraints

logger = logging.getLogger(__name__)


def _train_one_fold(
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    X_test: pd.DataFrame,
    y_test: np.ndarray,
    cat_indices: list[int],
    numeric_cols: list[str],
    params: dict[str, Any],
    sites_train: np.ndarray,
    lab_values_train: np.ndarray | None = None,
    lab_values_test: np.ndarray | None = None,
    transform_lmbda: float = 0.2,
) -> tuple[dict, list[dict]] | tuple[None, list]:
    """Train one CV fold, return (fold_metrics, sample_records).

    Matches legacy _train_one_fold behavior:
    - Skips folds with <5 test samples
    - Per-fold median imputation of numeric NaN (train median applied to both)
    - GroupShuffleSplit internal validation split for early stopping
    - BCF computation in native space
    - Per-fold metrics (R², KGE, native-space)
    """
    if len(y_test) < 5:
        return None, []

    test_site = "unknown"  # Will be set by caller

    # Per-fold NaN imputation (CRITICAL — matches legacy lines 366-370)
    X_train = X_train.copy()
    X_test = X_test.copy()
    num_cols_present = [c for c in numeric_cols if c in X_train.columns]
    train_median = X_train[num_cols_present].median()
    X_train[num_cols_present] = X_train[num_cols_present].fillna(train_median)
    X_test[num_cols_present] = X_test[num_cols_present].fillna(train_median)

    # Internal validation split for early stopping
    if len(np.unique(sites_train)) > 2:
        gss = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=42)
        sub_train_idx, val_idx = next(gss.split(X_train, y_train, groups=sites_train))
    else:
        n = len(X_train)
        n_val = max(1, int(n * 0.15))
        rng = np.random.RandomState(42)
        perm = rng.permutation(n)
        sub_train_idx, val_idx = perm[n_val:], perm[:n_val]

    train_pool = Pool(
        X_train.iloc[sub_train_idx], y_train[sub_train_idx],
        cat_features=cat_indices,
    )
    val_pool = Pool(
        X_train.iloc[val_idx], y_train[val_idx],
        cat_features=cat_indices,
    )
    test_pool = Pool(X_test, cat_features=cat_indices)

    model = CatBoostRegressor(**params)
    model.fit(train_pool, eval_set=val_pool)

    y_pred = model.predict(test_pool)

    # BCF computation (native space, matching legacy lines 436-454)
    y_train_pred = model.predict(
        Pool(X_train.iloc[sub_train_idx], cat_features=cat_indices)
    )
    if lab_values_train is not None:
        train_native_true = lab_values_train[sub_train_idx]
        train_native_pred = safe_inv_boxcox1p(y_train_pred, transform_lmbda)
        bcf = float(snowdon_bcf(train_native_true, train_native_pred))
    else:
        bcf = 1.0

    # KGE with decomposition
    kge_result = kge(y_test, y_pred, return_components=True)

    # Native-space metrics
    native = native_space_metrics(
        y_test, y_pred, smearing_factor=bcf,
        transform="boxcox", lmbda=transform_lmbda,
    )

    fold_metric = {
        "r2_log": float(r_squared(y_test, y_pred)),
        "kge_log": float(kge_result["kge"]),
        "kge_r": float(kge_result["kge_r"]),
        "kge_alpha": float(kge_result["kge_alpha"]),
        "kge_beta": float(kge_result["kge_beta"]),
        "r2_native": float(native["r2_native"]),
        "rmse_native_mgL": float(native["rmse_native_mgL"]),
        "pbias_native": float(native["pbias_native"]),
        "smearing_factor": bcf,
        "n_test": len(y_test),
        "fold_lmbda": transform_lmbda,
        "n_trees": model.tree_count_,
    }

    # Per-sample records for downstream analysis
    y_true_native = lab_values_test if lab_values_test is not None else safe_inv_boxcox1p(y_test, transform_lmbda)
    y_pred_native = safe_inv_boxcox1p(y_pred, transform_lmbda) * bcf

    sample_records = []
    for i in range(len(y_test)):
        sample_records.append({
            "y_true_log": float(y_test[i]),
            "y_pred_log": float(y_pred[i]),
            "y_true_native_mgL": float(y_true_native[i]),
            "y_pred_native_mgL": float(y_pred_native[i]),
        })

    return fold_metric, sample_records


def run_logo_cv(
    X: pd.DataFrame,
    y: np.ndarray,
    sites: np.ndarray,
    cat_indices: list[int],
    config: ModelConfig,
    feature_names: list[str],
    lab_values: np.ndarray | None = None,
    thread_count: int | None = None,
    n_jobs: int = 1,
) -> dict[str, Any]:
    """Run Leave-One-Group-Out cross-validation.

    Returns dict with oof_predictions, fold_assignments, fold_metrics, sample_records.
    """
    monotone = compute_monotone_constraints(feature_names, config)
    if thread_count is None:
        cpu = os.cpu_count() or 12
        thread_count = max(1, cpu // n_jobs)
    params = build_catboost_params(config, thread_count, monotone)

    # Identify numeric columns for NaN imputation
    cat_set = set(config.features.categoricals)
    numeric_cols = [f for f in feature_names if f not in cat_set]

    logo = LeaveOneGroupOut()
    unique_sites = np.unique(sites)
    n_folds = len(unique_sites)
    logger.info(f"LOGO CV: {n_folds} folds, {len(X)} samples, {len(feature_names)} features, "
                f"thread_count={thread_count}, n_jobs={n_jobs}")

    oof_preds = np.full(len(y), np.nan)
    fold_assignments = {}
    fold_metrics_list = []
    all_sample_records = []

    if n_jobs > 1:
        from joblib import Parallel, delayed

        def _run_fold(fold_idx, train_idx, test_idx):
            site = sites[test_idx[0]]
            lv_train = lab_values[train_idx] if lab_values is not None else None
            lv_test = lab_values[test_idx] if lab_values is not None else None
            metric, records = _train_one_fold(
                X.iloc[train_idx], y[train_idx],
                X.iloc[test_idx], y[test_idx],
                cat_indices, numeric_cols, params,
                sites_train=sites[train_idx],
                lab_values_train=lv_train,
                lab_values_test=lv_test,
                transform_lmbda=config.transform.lmbda,
            )
            return fold_idx, test_idx, metric, records, site

        results = Parallel(n_jobs=n_jobs, backend="loky", verbose=10)(
            delayed(_run_fold)(fold_idx, train_idx, test_idx)
            for fold_idx, (train_idx, test_idx) in enumerate(logo.split(X, y, groups=sites))
        )

        for fold_idx, test_idx, metric, records, site in results:
            fold_assignments[fold_idx] = site
            if metric is not None:
                oof_preds[test_idx] = metric.pop("_preds", oof_preds[test_idx])
                # Reconstruct preds from records
                for i, idx in enumerate(test_idx):
                    if i < len(records):
                        oof_preds[idx] = records[i]["y_pred_log"]
                metric["site_id"] = site
                fold_metrics_list.append(metric)
                for r in records:
                    r["site_id"] = site
                all_sample_records.extend(records)
    else:
        # Sequential execution with progress logging
        for fold_idx, (train_idx, test_idx) in enumerate(logo.split(X, y, groups=sites)):
            site = sites[test_idx[0]]
            fold_assignments[fold_idx] = site

            if fold_idx % 20 == 0 or fold_idx == n_folds - 1:
                logger.info(f"  Fold {fold_idx}/{n_folds} (site={site}, n_test={len(test_idx)})")

            lv_train = lab_values[train_idx] if lab_values is not None else None
            lv_test = lab_values[test_idx] if lab_values is not None else None
            metric, records = _train_one_fold(
                X.iloc[train_idx], y[train_idx],
                X.iloc[test_idx], y[test_idx],
                cat_indices, numeric_cols, params,
                sites_train=sites[train_idx],
                lab_values_train=lv_train,
                lab_values_test=lv_test,
                transform_lmbda=config.transform.lmbda,
            )
            if metric is not None:
                for i, idx in enumerate(test_idx):
                    if i < len(records):
                        oof_preds[idx] = records[i]["y_pred_log"]
                metric["site_id"] = site
                fold_metrics_list.append(metric)
                for r in records:
                    r["site_id"] = site
                all_sample_records.extend(records)

    n_predicted = np.isfinite(oof_preds).sum()
    logger.info(f"LOGO CV complete: {n_predicted}/{len(y)} predicted, "
                f"{len(fold_metrics_list)} folds with metrics")

    return {
        "oof_predictions": oof_preds,
        "fold_assignments": fold_assignments,
        "fold_metrics": fold_metrics_list,
        "sample_records": all_sample_records,
        "sites": sites,
    }
