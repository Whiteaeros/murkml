"""Baseline models for cross-site water quality surrogate prediction.

Includes:
- Per-site OLS regression (USGS standard)
- Global OLS (all sites pooled)
- CatBoost with leave-one-site-out CV
- CatBoost quantile regression for prediction intervals
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import LeaveOneGroupOut

logger = logging.getLogger(__name__)


def per_site_ols(
    df: pd.DataFrame,
    feature_col: str = "sensor_instant",
    target_col: str = "lab_value",
    site_col: str = "site_id",
    log_transform: bool = True,
) -> dict:
    """Fit per-site OLS regressions (replicates USGS standard approach).

    log(SSC) = a * log(turbidity) + b

    Uses temporal splits within each site (not random) per ML reviewer.

    Returns:
        Dict mapping site_id -> {model, r2, n_samples, coefficients}.
    """
    results = {}

    for site_id, site_df in df.groupby(site_col):
        if len(site_df) < 10:
            continue

        X = site_df[feature_col].values.reshape(-1, 1)
        y = site_df[target_col].values

        if log_transform:
            # log1p handles zeros
            X = np.log1p(X)
            y = np.log1p(y)

        # Temporal split: first 70% for train, last 30% for test
        n = len(X)
        split = int(0.7 * n)
        X_train, X_test = X[:split], X[split:]
        y_train, y_test = y[:split], y[split:]

        model = LinearRegression()
        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)
        ss_res = np.sum((y_test - y_pred) ** 2)
        ss_tot = np.sum((y_test - y_test.mean()) ** 2)
        r2 = 1 - ss_res / max(ss_tot, 1e-10)

        results[site_id] = {
            "model": model,
            "r2": r2,
            "n_samples": len(site_df),
            "slope": model.coef_[0],
            "intercept": model.intercept_,
        }

    return results


def global_ols(
    df: pd.DataFrame,
    feature_cols: list[str] | None = None,
    target_col: str = "lab_value_log1p",
    site_col: str = "site_id",
) -> dict:
    """Fit a global OLS across all sites (baseline to beat).

    Returns dict with model, per-site R2 from leave-one-site-out.
    """
    if feature_cols is None:
        feature_cols = ["sensor_instant"]

    logo = LeaveOneGroupOut()
    groups = df[site_col].values
    X = df[feature_cols].values
    y = df[target_col].values

    site_results = {}
    for train_idx, test_idx in logo.split(X, y, groups):
        site = groups[test_idx[0]]
        model = LinearRegression()
        model.fit(X[train_idx], y[train_idx])
        y_pred = model.predict(X[test_idx])
        y_test = y[test_idx]

        ss_res = np.sum((y_test - y_pred) ** 2)
        ss_tot = np.sum((y_test - y_test.mean()) ** 2)
        r2 = 1 - ss_res / max(ss_tot, 1e-10)

        site_results[site] = {"r2": r2, "n_test": len(test_idx)}

    return site_results


def cross_site_catboost(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str = "lab_value_log1p",
    site_col: str = "site_id",
    quantiles: tuple[float, ...] = (0.1, 0.5, 0.9),
    random_seed: int = 42,
) -> dict:
    """Train CatBoost with leave-one-site-out cross-validation.

    Also trains quantile regression models for prediction intervals.

    Args:
        df: Feature DataFrame.
        feature_cols: List of feature column names.
        target_col: Target column (should be log1p transformed).
        site_col: Site identifier column.
        quantiles: Quantiles for prediction intervals.
        random_seed: Random seed for reproducibility.

    Returns:
        Dict with per-site results, feature importances, and trained models.
    """
    try:
        from catboost import CatBoostRegressor
    except ImportError:
        raise ImportError(
            "CatBoost is required for this model. "
            "Install with: pip install murkml[boost]"
        )

    logo = LeaveOneGroupOut()
    groups = df[site_col].values
    X = df[feature_cols].values
    y = df[target_col].values

    site_results = {}

    for train_idx, test_idx in logo.split(X, y, groups):
        site = groups[test_idx[0]]
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        # Median prediction (main model)
        model = CatBoostRegressor(
            iterations=1000,
            learning_rate=0.1,
            depth=6,
            random_seed=random_seed,
            verbose=0,
        )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        # Quantile models for prediction intervals
        quantile_preds = {}
        for q in quantiles:
            q_model = CatBoostRegressor(
                iterations=1000,
                learning_rate=0.1,
                depth=6,
                loss_function=f"Quantile:alpha={q}",
                random_seed=random_seed,
                verbose=0,
            )
            q_model.fit(X_train, y_train)
            quantile_preds[q] = q_model.predict(X_test)

        site_results[site] = {
            "y_test": y_test,
            "y_pred": y_pred,
            "quantile_preds": quantile_preds,
            "n_test": len(test_idx),
            "model": model,
        }

        logger.info(f"Site {site}: {len(test_idx)} test samples")

    return site_results
