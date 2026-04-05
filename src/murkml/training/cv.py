"""Leave-One-Group-Out cross-validation for CatBoost. Pure functions.

Handles fold splitting, per-fold training, OOF prediction aggregation.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool
from sklearn.model_selection import GroupShuffleSplit, LeaveOneGroupOut

from murkml.config import ModelConfig
from murkml.training.model import build_catboost_params, compute_monotone_constraints

logger = logging.getLogger(__name__)


def _train_one_fold(
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    X_test: pd.DataFrame,
    y_test: np.ndarray,
    cat_indices: list[int],
    params: dict[str, Any],
    val_fraction: float = 0.15,
    sites_train: np.ndarray | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Train one CV fold and return test predictions + fold metrics.

    Pure function: no side effects, no file I/O.
    """
    # Internal validation split for early stopping
    if sites_train is not None and len(np.unique(sites_train)) > 2:
        gss = GroupShuffleSplit(n_splits=1, test_size=val_fraction, random_state=params.get("random_seed", 42))
        sub_train_idx, val_idx = next(gss.split(X_train, y_train, groups=sites_train))
    else:
        # Not enough groups for group split — use random
        n = len(X_train)
        n_val = max(1, int(n * val_fraction))
        rng = np.random.RandomState(params.get("random_seed", 42))
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

    model = CatBoostRegressor(**params)
    model.fit(train_pool, eval_set=val_pool)

    test_pool = Pool(X_test, cat_features=cat_indices)
    preds = model.predict(test_pool)

    fold_info = {
        "n_trees": model.tree_count_,
        "n_train": len(sub_train_idx),
        "n_val": len(val_idx),
        "n_test": len(X_test),
    }

    return preds, fold_info


def run_logo_cv(
    X: pd.DataFrame,
    y: np.ndarray,
    sites: np.ndarray,
    cat_indices: list[int],
    config: ModelConfig,
    feature_names: list[str],
    thread_count: int = 1,
    n_jobs: int = 1,
) -> dict[str, Any]:
    """Run Leave-One-Group-Out cross-validation.

    Returns dict with oof_predictions, fold_assignments, fold_metrics.

    For surrogate validation: use thread_count=1, n_jobs=1 for determinism.
    For production: use thread_count=5, n_jobs=6 for speed.
    """
    monotone = compute_monotone_constraints(feature_names, config)
    params = build_catboost_params(config, thread_count, monotone)

    logo = LeaveOneGroupOut()
    unique_sites = np.unique(sites)
    n_folds = len(unique_sites)
    logger.info(f"LOGO CV: {n_folds} folds, {len(X)} samples, {len(feature_names)} features")

    oof_preds = np.full(len(y), np.nan)
    fold_assignments = {}
    fold_metrics = []

    if n_jobs > 1:
        # Parallel execution (production)
        from joblib import Parallel, delayed

        def _run_fold(fold_idx, train_idx, test_idx):
            site = sites[test_idx[0]]
            sites_train = sites[train_idx]
            preds, info = _train_one_fold(
                X.iloc[train_idx], y[train_idx],
                X.iloc[test_idx], y[test_idx],
                cat_indices, params,
                sites_train=sites_train,
            )
            return fold_idx, test_idx, preds, info, site

        results = Parallel(n_jobs=n_jobs, backend="loky")(
            delayed(_run_fold)(fold_idx, train_idx, test_idx)
            for fold_idx, (train_idx, test_idx) in enumerate(logo.split(X, y, groups=sites))
        )

        for fold_idx, test_idx, preds, info, site in results:
            oof_preds[test_idx] = preds
            fold_assignments[fold_idx] = site
            fold_metrics.append(info)
    else:
        # Sequential execution (surrogate validation — deterministic)
        for fold_idx, (train_idx, test_idx) in enumerate(logo.split(X, y, groups=sites)):
            site = sites[test_idx[0]]
            fold_assignments[fold_idx] = site
            sites_train = sites[train_idx]

            preds, info = _train_one_fold(
                X.iloc[train_idx], y[train_idx],
                X.iloc[test_idx], y[test_idx],
                cat_indices, params,
                sites_train=sites_train,
            )
            oof_preds[test_idx] = preds
            fold_metrics.append(info)

    n_predicted = np.isfinite(oof_preds).sum()
    logger.info(f"LOGO CV complete: {n_predicted}/{len(y)} samples predicted, {n_folds} folds")

    return {
        "oof_predictions": oof_preds,
        "fold_assignments": fold_assignments,
        "fold_metrics": fold_metrics,
        "sites": sites,
    }
