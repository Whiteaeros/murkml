"""Train final models on full training set, then validate on holdout sites.

Trains CatBoost Tier C (with categorical features) on all training data,
then assembles and predicts on the 20+ holdout validation sites.

Usage:
    python scripts/train_and_validate.py
"""

from __future__ import annotations

import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from murkml.data.align import align_samples
from murkml.data.attributes import prune_gagesii, build_feature_tiers
from murkml.data.features import engineer_features
from murkml.data.qc import filter_continuous
from murkml.evaluate.metrics import kge, r_squared, rmse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"
VAL_DIR = DATA_DIR / "validation"

CONTINUOUS_PARAMS = {
    "63680": "turbidity",
    "00095": "conductance",
    "00300": "do",
    "00400": "ph",
    "00010": "temp",
    "00060": "discharge",
}


def load_continuous_val(site_id: str, param_code: str) -> pd.DataFrame:
    """Load continuous data from validation directory."""
    cont_dir = VAL_DIR / "continuous" / site_id.replace("-", "_") / param_code
    if not cont_dir.exists():
        return pd.DataFrame()
    chunks = []
    for f in sorted(cont_dir.glob("*.parquet")):
        chunk = pd.read_parquet(f)
        if len(chunk) > 0:
            chunks.append(chunk)
    if not chunks:
        return pd.DataFrame()
    df = pd.concat(chunks, ignore_index=True)
    df = df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    return df


def assemble_validation_ssc(site_id: str) -> pd.DataFrame:
    """Assemble SSC paired dataset for a validation site."""
    # Load discrete SSC
    disc_file = VAL_DIR / "discrete" / f"{site_id.replace('-', '_')}_ssc.parquet"
    if not disc_file.exists():
        return pd.DataFrame()

    df = pd.read_parquet(disc_file)
    if "Activity_StartDate" not in df.columns or "Result_Measure" not in df.columns:
        return pd.DataFrame()

    # Parse datetime (same logic as assemble_dataset.py)
    USGS_TZ = {"EST": -5, "EDT": -4, "CST": -6, "CDT": -5, "MST": -7, "MDT": -6,
               "PST": -8, "PDT": -7, "AKST": -9, "AKDT": -8, "HST": -10, "AST": -4,
               "UTC": 0, "GMT": 0}

    if "Activity_StartTime" not in df.columns or "Activity_StartTimeZone" not in df.columns:
        return pd.DataFrame()

    df = df[df["Activity_StartTime"].notna() & (df["Activity_StartTime"] != "")].copy()
    df = df[df["Activity_StartTimeZone"].isin(USGS_TZ.keys())].copy()
    if df.empty:
        return pd.DataFrame()

    local_dt = pd.to_datetime(
        df["Activity_StartDate"].astype(str) + " " + df["Activity_StartTime"].astype(str),
        errors="coerce")
    offsets = df["Activity_StartTimeZone"].map(USGS_TZ)
    df["datetime"] = (local_dt - pd.to_timedelta(offsets, unit="h")).dt.tz_localize("UTC")
    df["ssc_value"] = pd.to_numeric(df["Result_Measure"], errors="coerce")
    df = df.dropna(subset=["datetime", "ssc_value"])
    df = df[df["ssc_value"] >= 0]
    df = df.drop_duplicates(subset=["datetime", "ssc_value"], keep="first")
    df = df.sort_values("datetime").reset_index(drop=True)

    if df.empty:
        return pd.DataFrame()

    # Load and QC turbidity
    turb = load_continuous_val(site_id, "63680")
    if turb.empty:
        return pd.DataFrame()
    turb_filtered, _ = filter_continuous(turb)
    if turb_filtered.empty:
        return pd.DataFrame()
    turb_clean = turb_filtered[["time", "value"]].copy()
    turb_clean.columns = ["datetime", "value"]

    disc_clean = df[["datetime", "ssc_value"]].copy()
    disc_clean.columns = ["datetime", "value"]

    aligned = align_samples(continuous=turb_clean, discrete=disc_clean,
                            max_gap=pd.Timedelta(minutes=15))
    if aligned.empty:
        return pd.DataFrame()

    aligned = aligned.rename(columns={
        "sensor_instant": "turbidity_instant",
        "window_mean": "turbidity_mean_1hr", "window_min": "turbidity_min_1hr",
        "window_max": "turbidity_max_1hr", "window_std": "turbidity_std_1hr",
        "window_range": "turbidity_range_1hr", "window_slope": "turbidity_slope_1hr",
    })

    # Add secondary sensors
    for pcode, pname in CONTINUOUS_PARAMS.items():
        if pcode == "63680":
            continue
        cont = load_continuous_val(site_id, pcode)
        if cont.empty:
            aligned[f"{pname}_instant"] = np.nan
            continue
        cont_filtered, _ = filter_continuous(cont)
        if cont_filtered.empty:
            aligned[f"{pname}_instant"] = np.nan
            continue
        cont_clean = cont_filtered[["time", "value"]].copy().reset_index(drop=True)
        cont_clean["time"] = pd.to_datetime(cont_clean["time"], utc=True)
        cont_clean = cont_clean.sort_values("time").reset_index(drop=True)

        instant_values = []
        for _, row in aligned.iterrows():
            anchor_time = row["sample_time"]
            time_diffs = (cont_clean["time"] - anchor_time).abs()
            min_idx = time_diffs.idxmin()
            if time_diffs.iloc[min_idx] <= pd.Timedelta(minutes=15):
                instant_values.append(cont_clean["value"].iloc[min_idx])
            else:
                instant_values.append(np.nan)
        aligned[f"{pname}_instant"] = instant_values

    aligned["site_id"] = site_id
    aligned["is_nondetect"] = False
    return aligned


def assemble_validation_tp(site_id: str) -> pd.DataFrame:
    """Assemble TP paired dataset for a validation site."""
    from murkml.data.discrete import load_discrete_param

    discrete = load_discrete_param(
        site_id=site_id, param_name="total_phosphorus",
        data_dir=VAL_DIR, value_col_out="value",
    )
    if discrete.empty:
        return pd.DataFrame()

    turb = load_continuous_val(site_id, "63680")
    if turb.empty:
        return pd.DataFrame()
    turb_filtered, _ = filter_continuous(turb)
    if turb_filtered.empty:
        return pd.DataFrame()
    turb_clean = turb_filtered[["time", "value"]].copy()
    turb_clean.columns = ["datetime", "value"]

    disc_clean = discrete[["datetime", "value"]].copy()
    aligned = align_samples(continuous=turb_clean, discrete=disc_clean,
                            max_gap=pd.Timedelta(minutes=15))
    if aligned.empty:
        return pd.DataFrame()

    aligned = aligned.rename(columns={
        "sensor_instant": "turbidity_instant",
        "window_mean": "turbidity_mean_1hr", "window_min": "turbidity_min_1hr",
        "window_max": "turbidity_max_1hr", "window_std": "turbidity_std_1hr",
        "window_range": "turbidity_range_1hr", "window_slope": "turbidity_slope_1hr",
    })

    for pcode, pname in CONTINUOUS_PARAMS.items():
        if pcode == "63680":
            continue
        cont = load_continuous_val(site_id, pcode)
        if cont.empty:
            aligned[f"{pname}_instant"] = np.nan
            continue
        cont_filtered, _ = filter_continuous(cont)
        if cont_filtered.empty:
            aligned[f"{pname}_instant"] = np.nan
            continue
        cont_clean = cont_filtered[["time", "value"]].copy().reset_index(drop=True)
        cont_clean["time"] = pd.to_datetime(cont_clean["time"], utc=True)
        cont_clean = cont_clean.sort_values("time").reset_index(drop=True)
        instant_values = []
        for _, row in aligned.iterrows():
            anchor_time = row["sample_time"]
            time_diffs = (cont_clean["time"] - anchor_time).abs()
            min_idx = time_diffs.idxmin()
            if time_diffs.iloc[min_idx] <= pd.Timedelta(minutes=15):
                instant_values.append(cont_clean["value"].iloc[min_idx])
            else:
                instant_values.append(np.nan)
        aligned[f"{pname}_instant"] = instant_values

    aligned["site_id"] = site_id
    aligned["is_nondetect"] = False
    return aligned


def main():
    warnings.filterwarnings("ignore")
    from catboost import CatBoostRegressor, Pool

    # =========================================================
    # STEP 1: Train final models on full training set
    # =========================================================
    logger.info("=" * 60)
    logger.info("TRAINING FINAL MODELS")
    logger.info("=" * 60)

    # Load training data
    basic_attrs = pd.read_parquet(DATA_DIR / "site_attributes.parquet")
    gagesii_path = DATA_DIR / "site_attributes_gagesii.parquet"
    gagesii_attrs = None
    if gagesii_path.exists():
        gagesii_raw = pd.read_parquet(gagesii_path)
        gagesii_attrs = prune_gagesii(gagesii_raw)

    EXCLUDE_COLS = {
        "site_id", "sample_time", "lab_value", "match_gap_seconds", "window_count",
        "is_nondetect", "hydro_event",
        "ssc_log1p", "ssc_value", "total_phosphorus_log1p",
        "nitrate_nitrite_log1p", "orthophosphate_log1p", "tds_evaporative_log1p",
    }

    trained_models = {}

    for param_name, dataset_file, target_col in [
        ("ssc", "turbidity_ssc_paired.parquet", "ssc_log1p"),
        ("total_phosphorus", "total_phosphorus_paired.parquet", "total_phosphorus_log1p"),
    ]:
        dataset_path = DATA_DIR / "processed" / dataset_file
        if not dataset_path.exists():
            logger.warning(f"Skipping {param_name}: no dataset")
            continue

        logger.info(f"\n--- Training {param_name} ---")
        assembled = pd.read_parquet(dataset_path)

        # Add log target if missing
        if target_col not in assembled.columns:
            assembled[target_col] = np.log1p(assembled["lab_value"])

        # Build tiers — use Tier C
        tiers = build_feature_tiers(assembled, basic_attrs, gagesii_attrs)
        tier_name = "C_sensor_basic_gagesii"
        if tier_name not in tiers:
            tier_name = "B_sensor_basic"

        tier_info = tiers[tier_name]
        tier_data = tier_info["data"]
        feature_cols = tier_info["feature_cols"]

        # Separate numeric and categorical
        available = [c for c in feature_cols if c in tier_data.columns and c not in EXCLUDE_COLS]
        numeric_cols = [c for c in available if tier_data[c].dtype in [np.float64, np.float32, np.int64, np.int32, float, int]]
        cat_cols = [c for c in available if tier_data[c].dtype == object]
        all_cols = numeric_cols + cat_cols
        cat_indices = [i for i, c in enumerate(all_cols) if c in cat_cols]

        logger.info(f"  {tier_name}: {tier_data['site_id'].nunique()} sites, "
                    f"{len(tier_data)} samples, {len(numeric_cols)} numeric + {len(cat_cols)} cat features")

        # Prepare data
        clean = tier_data.dropna(subset=[target_col]).copy()
        y = clean[target_col].values
        X_df = clean[all_cols].copy()

        # Fill categoricals with "missing", numerics with median
        for c in cat_cols:
            X_df[c] = X_df[c].fillna("missing").astype(str)
        train_median = X_df[numeric_cols].median()
        X_df[numeric_cols] = X_df[numeric_cols].fillna(train_median)

        # Early stopping split
        sites = clean["site_id"].values
        gss = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=42)
        train_idx, val_idx = next(gss.split(X_df, y, groups=sites))

        train_pool = Pool(X_df.iloc[train_idx], y[train_idx], cat_features=cat_indices)
        val_pool = Pool(X_df.iloc[val_idx], y[val_idx], cat_features=cat_indices)

        model = CatBoostRegressor(
            iterations=500, learning_rate=0.05, depth=6,
            l2_leaf_reg=3, random_seed=42, verbose=0,
            early_stopping_rounds=50,
        )
        model.fit(train_pool, eval_set=val_pool)

        logger.info(f"  Trained: {model.tree_count_} trees")

        trained_models[param_name] = {
            "model": model,
            "feature_cols": all_cols,
            "cat_cols": cat_cols,
            "cat_indices": cat_indices,
            "train_median": train_median,
            "target_col": target_col,
            "target_max_native": float(np.expm1(y.max())),
        }

    # =========================================================
    # STEP 2: Assemble and predict on validation sites
    # =========================================================
    logger.info("\n" + "=" * 60)
    logger.info("EXTERNAL VALIDATION")
    logger.info("=" * 60)

    # Find validation sites
    cont_dir = VAL_DIR / "continuous"
    val_sites = []
    if cont_dir.exists():
        for site_dir in sorted(cont_dir.iterdir()):
            if site_dir.is_dir() and (site_dir / "63680").exists():
                site_id = site_dir.name.replace("_", "-")
                val_sites.append(site_id)
    logger.info(f"Validation sites with turbidity: {len(val_sites)}")

    # Load GAGES-II for validation site attributes
    gagesii_full = pd.read_parquet(DATA_DIR / "site_attributes_gagesii_full.parquet") if \
        (DATA_DIR / "site_attributes_gagesii_full.parquet").exists() else None

    all_results = []

    for param_name in ["ssc", "total_phosphorus"]:
        if param_name not in trained_models:
            continue

        tm = trained_models[param_name]
        model = tm["model"]
        feature_cols = tm["feature_cols"]
        cat_cols = tm["cat_cols"]
        cat_indices = tm["cat_indices"]
        train_median = tm["train_median"]

        logger.info(f"\n{'='*60}")
        logger.info(f"VALIDATING: {param_name}")
        logger.info(f"{'='*60}")

        for site_id in val_sites:
            # Check for discrete data
            site_stem = site_id.replace("-", "_")
            if param_name == "ssc":
                disc_file = VAL_DIR / "discrete" / f"{site_stem}_ssc.parquet"
            else:
                disc_file = VAL_DIR / "discrete" / f"{site_stem}_{param_name}.parquet"
            if not disc_file.exists():
                continue

            logger.info(f"\n  {site_id}")

            # Assemble
            try:
                if param_name == "ssc":
                    assembled = assemble_validation_ssc(site_id)
                else:
                    assembled = assemble_validation_tp(site_id)
            except Exception as e:
                logger.error(f"    Assembly error: {e}")
                continue

            if assembled.empty:
                logger.warning(f"    No aligned data")
                continue

            # Feature engineering
            assembled = engineer_features(assembled)
            assembled["ssc_log1p"] = np.log1p(assembled["lab_value"])
            if param_name == "total_phosphorus":
                assembled["total_phosphorus_log1p"] = np.log1p(assembled["lab_value"])

            # Add basic attributes
            site_attrs = basic_attrs[basic_attrs["site_id"] == site_id]
            if not site_attrs.empty:
                for col in ["drainage_area_km2", "altitude_ft", "huc2"]:
                    if col in site_attrs.columns:
                        assembled[col] = site_attrs[col].values[0]

            # Add GAGES-II attributes if available
            if gagesii_attrs is not None:
                site_gagesii = gagesii_attrs[gagesii_attrs["site_id"] == site_id]
                if not site_gagesii.empty:
                    for col in gagesii_attrs.columns:
                        if col != "site_id" and col in feature_cols:
                            assembled[col] = site_gagesii[col].values[0]

            # Prepare features
            X_df = pd.DataFrame()
            for c in feature_cols:
                if c in assembled.columns:
                    X_df[c] = assembled[c]
                elif c in cat_cols:
                    X_df[c] = "missing"
                else:
                    X_df[c] = train_median.get(c, 0)

            # Fill NaN
            for c in cat_cols:
                X_df[c] = X_df[c].fillna("missing").astype(str)
            num_cols = [c for c in feature_cols if c not in cat_cols]
            X_df[num_cols] = X_df[num_cols].fillna(train_median)

            y_true_log = np.log1p(assembled["lab_value"].values)

            if len(y_true_log) < 5:
                logger.warning(f"    Only {len(y_true_log)} samples, skipping")
                continue

            # Determine attribute source
            attr_source = "sensor_only"
            if gagesii_attrs is not None and site_id in set(gagesii_attrs["site_id"]):
                attr_source = "GAGES-II"
            elif not site_attrs.empty:
                attr_source = "basic_only"

            # Predict
            test_pool = Pool(X_df, cat_features=cat_indices)
            y_pred_log = model.predict(test_pool)

            # Output clipping in native space (Chen: clip in native, not log)
            target_max = tm.get("target_max_native", np.inf)
            y_pred_native = np.expm1(y_pred_log)
            y_pred_native = np.clip(y_pred_native, 0, target_max)
            y_pred_log = np.log1p(y_pred_native)

            cb_r2 = r_squared(y_true_log, y_pred_log)
            cb_kge = kge(y_true_log, y_pred_log)
            cb_rmse = rmse(y_true_log, y_pred_log)

            # Native-space metrics
            y_true_native = np.expm1(y_true_log)
            cb_r2_native = r_squared(y_true_native, y_pred_native)
            cb_rmse_native = rmse(y_true_native, y_pred_native)

            # Per-site OLS baseline
            ols_r2 = np.nan
            if "turbidity_instant" in assembled.columns:
                valid_ols = assembled.dropna(subset=["turbidity_instant"])
                if len(valid_ols) >= 10:
                    from sklearn.linear_model import LinearRegression
                    X_ols = np.log1p(valid_ols["turbidity_instant"].values).reshape(-1, 1)
                    y_ols = np.log1p(valid_ols["lab_value"].values)
                    n_train = int(len(valid_ols) * 0.7)
                    if n_train >= 5 and (len(valid_ols) - n_train) >= 5:
                        lr = LinearRegression().fit(X_ols[:n_train], y_ols[:n_train])
                        y_ols_pred = lr.predict(X_ols[n_train:])
                        ols_r2 = r_squared(y_ols[n_train:], y_ols_pred)

            logger.info(f"    n={len(assembled)}, CatBoost R²={cb_r2:.3f}, "
                       f"KGE={cb_kge:.3f}, OLS R²={ols_r2:.3f}, "
                       f"RMSE={cb_rmse_native:.1f} mg/L, src={attr_source}")

            all_results.append({
                "site_id": site_id,
                "param": param_name,
                "n_samples": len(assembled),
                "catboost_r2_log": cb_r2,
                "catboost_kge_log": cb_kge,
                "catboost_rmse_log": cb_rmse,
                "catboost_r2_native": cb_r2_native,
                "catboost_rmse_native_mgL": cb_rmse_native,
                "per_site_ols_r2_log": ols_r2,
                "attribute_source": attr_source,
            })

    # =========================================================
    # STEP 3: Summary
    # =========================================================
    if all_results:
        results_df = pd.DataFrame(all_results)
        out_path = DATA_DIR / "results" / "external_validation.parquet"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        results_df.to_parquet(out_path, index=False)

        logger.info(f"\n{'='*60}")
        logger.info("EXTERNAL VALIDATION SUMMARY")
        logger.info(f"{'='*60}")

        for param in ["ssc", "total_phosphorus"]:
            subset = results_df[results_df["param"] == param]
            if len(subset) == 0:
                continue
            logger.info(f"\n{param}:")
            logger.info(f"  Sites tested: {len(subset)}")
            logger.info(f"  CatBoost median R² (log): {subset['catboost_r2_log'].median():.3f}")
            logger.info(f"  CatBoost median KGE (log): {subset['catboost_kge_log'].median():.3f}")
            valid_ols = subset.dropna(subset=["per_site_ols_r2_log"])
            if len(valid_ols) > 0:
                logger.info(f"  Per-site OLS median R² (log): {valid_ols['per_site_ols_r2_log'].median():.3f}")
                logger.info(f"  CatBoost beats OLS: {(valid_ols['catboost_r2_log'] > valid_ols['per_site_ols_r2_log']).sum()}/{len(valid_ols)}")

            for _, row in subset.iterrows():
                ols_str = f"OLS={row['per_site_ols_r2_log']:.3f}" if not np.isnan(row['per_site_ols_r2_log']) else "OLS=N/A"
                logger.info(f"    {row['site_id']}: CB={row['catboost_r2_log']:.3f} "
                           f"{ols_str} n={row['n_samples']}")

        logger.info(f"\nSaved: {out_path}")
    else:
        logger.warning("No validation results produced!")


if __name__ == "__main__":
    main()
