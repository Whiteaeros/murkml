"""
Deep SHAP analysis for the v11 model.

Computes four SHAP products — all saved to data/results/shap_deep/:
  1. holdout_shap_values.parquet     — SHAP for all 6,026 holdout readings
  2. holdout_feature_values.parquet  — Matching feature values (same row order)
  3. holdout_shap_metadata.parquet   — site_id, sample_time, y_true, y_pred per row
  4. interaction_values.parquet      — SHAP interaction matrix (2,000-sample subset)
  5. per_site_shap.parquet           — Mean |SHAP| per feature per holdout site
  6. failure_site_shap.parquet       — Mean |SHAP| for sites with R² < 0

Usage:
    python scripts/compute_shap_deep.py [--n-interaction 2000] [--n-jobs 12]

Runtime estimates (i9-13900K, 24 cores):
    - Holdout SHAP values: ~5-15 min (6,026 samples, TreeExplainer)
    - Interaction values:  ~30-60 min (2,000 samples, TreeExplainer interactions)
    - Per-site + failure:  seconds (aggregation only)
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MODEL_PATH = DATA_DIR / "results" / "models" / "ssc_C_sensor_basic_watershed_v11_extreme_expanded.cbm"
META_PATH = DATA_DIR / "results" / "models" / "ssc_C_sensor_basic_watershed_v11_extreme_expanded_meta.json"
EVAL_DIR = DATA_DIR / "results" / "evaluations"
OUTPUT_DIR = DATA_DIR / "results" / "shap_deep"

PAIRED_PATH = DATA_DIR / "processed" / "turbidity_ssc_paired.parquet"
SPLIT_PATH = DATA_DIR / "train_holdout_vault_split.parquet"
STREAMCAT_DIR = DATA_DIR / "streamcat"
SGMC_PATH = DATA_DIR / "sgmc" / "sgmc_features_for_model.parquet"
SITE_ATTRS_PATH = DATA_DIR / "site_attributes.parquet"
DROP_LIST_PATH = DATA_DIR / "optimized_drop_list.txt"

PER_SITE_PATH = EVAL_DIR / "v11_extreme_eval_per_site.parquet"


def load_model():
    """Load v11 CatBoost model and metadata."""
    print(f"Loading model from {MODEL_PATH}")
    model = CatBoostRegressor()
    model.load_model(str(MODEL_PATH))
    with open(META_PATH) as f:
        meta = json.load(f)
    feature_cols = meta["feature_cols"]
    print(f"  {len(feature_cols)} features")
    return model, feature_cols, meta


def build_holdout_features(feature_cols: list[str], meta: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reconstruct the full 137-feature matrix for holdout samples.

    Mirrors the evaluate_model.py pipeline EXACTLY: direct merges of basic attrs,
    StreamCat, and SGMC onto paired data. No re-engineering — paired.parquet already
    contains all engineered features.

    Returns (X_holdout, metadata_df) where rows are aligned.
    """
    import sys
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from murkml.data.attributes import load_streamcat_attrs

    cat_cols = meta.get("cat_cols", [])
    train_medians = meta.get("train_median", {})

    print("Building holdout feature matrix...")

    # 1. Load paired data (already has engineered features)
    paired = pd.read_parquet(PAIRED_PATH)
    print(f"  Paired data: {len(paired)} rows")

    # 2. Filter to holdout sites
    split = pd.read_parquet(SPLIT_PATH)
    holdout_sites = split[split["role"] == "holdout"]["site_id"].tolist()
    holdout = paired[paired["site_id"].isin(holdout_sites)].copy()
    print(f"  Holdout samples: {len(holdout)}")

    # 3. Merge basic site attributes (same as evaluate_model.py)
    if SITE_ATTRS_PATH.exists():
        basic = pd.read_parquet(SITE_ATTRS_PATH)
        overlap_basic = set(basic.columns) & set(holdout.columns) - {"site_id"}
        basic_clean = basic.drop(columns=list(overlap_basic))
        holdout = holdout.merge(basic_clean, on="site_id", how="left")
        print(f"  After basic merge: {len(holdout)} samples")

    # 4. Merge StreamCat
    streamcat = load_streamcat_attrs(DATA_DIR)
    overlap_sc = set(streamcat.columns) & set(holdout.columns) - {"site_id"}
    streamcat_clean = streamcat.drop(columns=list(overlap_sc))
    holdout = holdout.merge(streamcat_clean, on="site_id", how="left")
    print(f"  After StreamCat merge: {len(holdout)} samples")

    # 5. Merge SGMC lithology
    if SGMC_PATH.exists():
        sgmc = pd.read_parquet(SGMC_PATH)
        overlap_sgmc = set(sgmc.columns) & set(holdout.columns) - {"site_id"}
        sgmc_clean = sgmc.drop(columns=list(overlap_sgmc))
        holdout = holdout.merge(sgmc_clean, on="site_id", how="left")
        print(f"  After SGMC merge: {len(holdout)} samples")

    # 6. Compute derived features (same as evaluate_model.py)
    if "drainage_area_km2" in holdout.columns and "log_drainage_area" not in holdout.columns:
        holdout["log_drainage_area"] = np.log1p(holdout["drainage_area_km2"].clip(lower=0))

    # Keep metadata before subsetting to feature columns
    meta_cols = ["site_id", "sample_time", "lab_value"]
    metadata = holdout[meta_cols].copy() if all(c in holdout.columns for c in meta_cols) else holdout[["site_id"]].copy()

    # Subset to exactly the model's feature columns
    missing = [c for c in feature_cols if c not in holdout.columns]
    if missing:
        print(f"  WARNING: {len(missing)} features missing, filling with NaN: {missing[:5]}...")
        for c in missing:
            holdout[c] = np.nan

    X = holdout[feature_cols].copy()

    # Handle categoricals and fill missing values same way as evaluate_model.py
    for col in feature_cols:
        if col in cat_cols:
            X[col] = X[col].fillna("missing").astype(str)
        elif col in train_medians and X[col].isna().any():
            X[col] = X[col].fillna(train_medians[col])

    # Convert string columns to category for CatBoost/SHAP
    for col in X.columns:
        if X[col].dtype == object:
            X[col] = X[col].astype("category")

    print(f"  Feature matrix: {X.shape}")
    return X, metadata


def compute_holdout_shap(model, X: pd.DataFrame):
    """Compute SHAP values for all holdout samples using TreeExplainer."""
    print(f"\nComputing SHAP values for {len(X)} holdout samples...")
    t0 = time.time()

    import shap
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X)

    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.0f}s ({elapsed/60:.1f} min)")

    return pd.DataFrame(shap_values, columns=X.columns, index=X.index)


def compute_interaction_values(model, X: pd.DataFrame, n_samples: int = 2000):
    """Compute SHAP interaction values on a subsample."""
    print(f"\nComputing SHAP interaction values for {n_samples} samples...")
    print("  (This is the slow one — expect 30-60 min)")

    rng = np.random.RandomState(42)
    idx = rng.choice(len(X), size=min(n_samples, len(X)), replace=False)
    idx.sort()
    X_sub = X.iloc[idx]

    t0 = time.time()
    import shap
    explainer = shap.TreeExplainer(model)
    interaction = explainer.shap_interaction_values(X_sub)
    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.0f}s ({elapsed/60:.1f} min)")

    # interaction shape: (n_samples, n_features, n_features)
    # Save as flattened: mean absolute interaction per feature pair
    n_feat = len(X_sub.columns)
    feat_names = list(X_sub.columns)

    # Mean |interaction| across samples
    mean_abs_interact = np.abs(interaction).mean(axis=0)  # (n_feat, n_feat)

    interact_df = pd.DataFrame(mean_abs_interact, index=feat_names, columns=feat_names)

    return interact_df, idx


def compute_per_site_shap(shap_df: pd.DataFrame, metadata: pd.DataFrame):
    """Aggregate mean |SHAP| per feature per holdout site."""
    print("\nComputing per-site SHAP profiles...")
    merged = shap_df.copy()
    merged["site_id"] = metadata["site_id"].values

    per_site = merged.groupby("site_id").apply(
        lambda g: g.abs().mean(),
        include_groups=False,
    )
    print(f"  {len(per_site)} sites, {per_site.shape[1]} features")
    return per_site


def compute_failure_shap(per_site_shap: pd.DataFrame):
    """Extract SHAP profiles for sites with R² < 0."""
    print("\nComputing failure-site SHAP...")
    if not PER_SITE_PATH.exists():
        print("  WARNING: per_site eval not found, skipping")
        return None

    ps = pd.read_parquet(PER_SITE_PATH)
    r2_col = "nse_native" if "nse_native" in ps.columns else "r2_random_at_0"
    failures = ps[ps[r2_col] < 0]["site_id"].tolist()
    print(f"  {len(failures)} sites with R² < 0")

    failure_shap = per_site_shap.loc[per_site_shap.index.isin(failures)]
    return failure_shap


def main():
    parser = argparse.ArgumentParser(description="Deep SHAP analysis for v11")
    parser.add_argument("--n-interaction", type=int, default=2000,
                        help="Samples for interaction values (default 2000)")
    parser.add_argument("--skip-interactions", action="store_true",
                        help="Skip the slow interaction computation")
    args = parser.parse_args()

    # Versioned output directory — never overwrite
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = OUTPUT_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {out_dir}")

    # Also create/update a 'latest' symlink-like marker
    latest_marker = OUTPUT_DIR / "LATEST"
    latest_marker.write_text(timestamp)

    model, feature_cols, meta = load_model()
    X, metadata = build_holdout_features(feature_cols, meta)

    # 1. Full holdout SHAP values
    shap_df = compute_holdout_shap(model, X)
    shap_df.to_parquet(out_dir / "holdout_shap_values.parquet")
    print(f"  Saved holdout_shap_values.parquet ({shap_df.shape})")

    # 2. Feature values (aligned)
    X.to_parquet(out_dir / "holdout_feature_values.parquet")
    print(f"  Saved holdout_feature_values.parquet ({X.shape})")

    # 3. Metadata
    # Add predictions from eval
    per_reading = pd.read_parquet(EVAL_DIR / "v11_extreme_eval_per_reading.parquet")
    if len(per_reading) == len(metadata):
        metadata["y_true_native"] = per_reading["y_true_native"].values
        metadata["y_pred_native"] = per_reading["y_pred_native"].values
    metadata.to_parquet(out_dir / "holdout_shap_metadata.parquet")
    print(f"  Saved holdout_shap_metadata.parquet ({metadata.shape})")

    # 4. Interaction values (optional, slow)
    if not args.skip_interactions:
        interact_df, interact_idx = compute_interaction_values(
            model, X, n_samples=args.n_interaction
        )
        interact_df.to_parquet(out_dir / "interaction_values.parquet")
        np.save(out_dir / "interaction_sample_indices.npy", interact_idx)
        print(f"  Saved interaction_values.parquet ({interact_df.shape})")
    else:
        print("\n  Skipping interaction values (--skip-interactions)")

    # 5. Per-site SHAP profiles
    per_site_shap = compute_per_site_shap(shap_df, metadata)
    per_site_shap.to_parquet(out_dir / "per_site_shap.parquet")
    print(f"  Saved per_site_shap.parquet ({per_site_shap.shape})")

    # 6. Failure-site SHAP
    failure_shap = compute_failure_shap(per_site_shap)
    if failure_shap is not None:
        failure_shap.to_parquet(out_dir / "failure_site_shap.parquet")
        print(f"  Saved failure_site_shap.parquet ({failure_shap.shape})")

    # Summary
    summary = {
        "timestamp": timestamp,
        "model": str(MODEL_PATH.name),
        "holdout_samples": len(X),
        "holdout_sites": int(metadata["site_id"].nunique()) if "site_id" in metadata.columns else None,
        "n_features": len(feature_cols),
        "interaction_samples": args.n_interaction if not args.skip_interactions else 0,
        "failure_sites": len(failure_shap) if failure_shap is not None else 0,
    }
    with open(out_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n  Summary: {summary}")
    print(f"\nAll outputs in: {out_dir}")


if __name__ == "__main__":
    main()
