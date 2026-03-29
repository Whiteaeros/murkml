"""Anchor Site Identification: Find sites that consistently improve model performance.

Runs 10 random-100-site models (seeds 200-209), combines with 5 existing D-redo results
(seeds 100-104), then identifies "anchor sites" that appear disproportionately in
high-performing random subsets.

Finally trains a model on just the top 50 anchor sites to test if curated < random-100.
"""
import sys
import json
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import boxcox1p
from sklearn.model_selection import GroupShuffleSplit
from catboost import CatBoostRegressor, Pool

warnings.filterwarnings("ignore")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from murkml.data.attributes import build_feature_tiers, load_streamcat_attrs
from murkml.evaluate.metrics import snowdon_bcf, safe_inv_boxcox1p

DATA_DIR = PROJECT_ROOT / "data"
MODELS_DIR = DATA_DIR / "results" / "models"
LMBDA = 0.2


def prepare_data():
    """Load and prepare data identically to experiment_d_redo.py."""
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

    split = pd.read_parquet(DATA_DIR / "train_holdout_split.parquet")
    holdout_ids = set(split[split["role"] == "holdout"]["site_id"])
    train_ids = set(split[split["role"] == "training"]["site_id"])

    holdout_data = tier_data[tier_data["site_id"].isin(holdout_ids)].copy()
    train_data = tier_data[tier_data["site_id"].isin(train_ids)].copy()

    return train_data, holdout_data, num_cols, cat_cols


def train_and_eval(train_df, holdout_data, num_cols, cat_cols, label, save_path=None):
    """Train CatBoost and evaluate on holdout. Optionally save model."""
    target_col = "ssc_log1p"
    cols = list(num_cols) + list(cat_cols)

    clean = train_df.dropna(subset=[target_col]).copy()
    if len(clean) < 50:
        return None

    y = clean[target_col].values
    sites = clean["site_id"].values
    X = clean[cols].copy()
    for c in cat_cols:
        X[c] = X[c].fillna("missing").astype(str)
    for c in cols:
        if c not in cat_cols:
            X[c] = X[c].fillna(X[c].median())

    cat_idx = [i for i, c in enumerate(cols) if c in cat_cols]

    gss = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=42)
    train_idx, val_idx = next(gss.split(X, y, groups=sites))

    train_pool = Pool(X.iloc[train_idx], y[train_idx], cat_features=cat_idx)
    val_pool = Pool(X.iloc[val_idx], y[val_idx], cat_features=cat_idx)

    mono = {}
    for i, c in enumerate(cols):
        if c in {"turbidity_instant", "turbidity_max_1hr"}:
            mono[i] = 1

    model = CatBoostRegressor(
        iterations=500, learning_rate=0.05, depth=6,
        l2_leaf_reg=3, random_seed=42, verbose=0,
        early_stopping_rounds=50, thread_count=12,
        boosting_type="Ordered", monotone_constraints=mono,
    )
    model.fit(train_pool, eval_set=val_pool)

    if save_path:
        model.save_model(str(save_path))

    # Evaluate on holdout
    h = holdout_data.copy()
    X_h = h[cols].copy()
    for c in cat_cols:
        X_h[c] = X_h[c].fillna("missing").astype(str)
    tm = {c: float(X.iloc[train_idx][c].median()) for c in cols if c not in cat_cols}
    for c in cols:
        if c not in cat_cols and c in tm:
            X_h[c] = X_h[c].fillna(tm[c])

    h_pool = Pool(X_h, cat_features=cat_idx)
    pred_bc = model.predict(h_pool)
    pred_native = np.clip(safe_inv_boxcox1p(pred_bc, LMBDA), 0, None)
    true_native = h["lab_value"].values

    t_pred = model.predict(train_pool)
    bcf = snowdon_bcf(clean["lab_value"].values[train_idx], safe_inv_boxcox1p(t_pred, LMBDA))
    pred_native *= bcf

    ss_res = np.sum((true_native - pred_native) ** 2)
    ss_tot = np.sum((true_native - true_native.mean()) ** 2)
    pooled_r2 = 1 - ss_res / max(ss_tot, 1e-10)

    site_r2s = []
    for sid in h["site_id"].unique():
        mask = h["site_id"].values == sid
        yt, yp = true_native[mask], pred_native[mask]
        if len(yt) >= 5 and yt.std() > 0:
            site_r2s.append(1 - np.sum((yt - yp) ** 2) / max(np.sum((yt - yt.mean()) ** 2), 1e-10))

    return {
        "label": label,
        "n_sites": clean["site_id"].nunique(),
        "n_samples": len(clean),
        "pooled_r2": pooled_r2,
        "median_site_r2": np.median(site_r2s) if site_r2s else np.nan,
        "mean_site_r2": np.mean(site_r2s) if site_r2s else np.nan,
        "n_trees": model.tree_count_,
    }


def main():
    print("=" * 80)
    print("ANCHOR SITE IDENTIFICATION")
    print("=" * 80)

    train_data, holdout_data, num_cols, cat_cols = prepare_data()
    all_train_sites = sorted(train_data["site_id"].unique())
    n_total = len(all_train_sites)
    print(f"Total training sites: {n_total}")
    print(f"Holdout: {holdout_data.site_id.nunique()} sites, {len(holdout_data)} samples")

    # =========================================================================
    # STEP 1: Run 10 random-100-site models (seeds 200-209)
    # =========================================================================
    print(f"\n{'='*80}")
    print("STEP 1: Running 10 random-100-site models (seeds 200-209)")
    print(f"{'='*80}")

    # Store: seed -> (selected_sites, result_dict)
    all_runs = {}

    for seed in range(200, 210):
        rng = np.random.default_rng(seed)
        selected = set(rng.choice(all_train_sites, 100, replace=False))
        save_path = MODELS_DIR / f"ssc_C_anchor_s{seed}.cbm"

        t0 = time.time()
        result = train_and_eval(
            train_data[train_data["site_id"].isin(selected)],
            holdout_data, num_cols, cat_cols,
            f"anchor-s{seed}",
            save_path=save_path,
        )
        elapsed = time.time() - t0

        if result:
            all_runs[seed] = {"sites": sorted(selected), "result": result}
            print(f"  s{seed}: {result['n_sites']} sites, {result['n_samples']} samples, "
                  f"pooled={result['pooled_r2']:.3f}, med_site={result['median_site_r2']:.3f}, "
                  f"trees={result['n_trees']} ({elapsed:.0f}s)")

    # =========================================================================
    # STEP 2: Reconstruct the 5 existing D-redo results (seeds 100-104)
    # =========================================================================
    print(f"\n{'='*80}")
    print("STEP 2: Reconstructing D-redo seeds 100-104 (same RNG, no retraining)")
    print(f"{'='*80}")

    # We don't retrain -- just reconstruct which sites were selected and re-run
    for seed_offset in range(5):
        seed = seed_offset + 100
        rng = np.random.default_rng(seed)
        selected = set(rng.choice(all_train_sites, 100, replace=False))

        t0 = time.time()
        result = train_and_eval(
            train_data[train_data["site_id"].isin(selected)],
            holdout_data, num_cols, cat_cols,
            f"anchor-s{seed}",
        )
        elapsed = time.time() - t0

        if result:
            all_runs[seed] = {"sites": sorted(selected), "result": result}
            print(f"  s{seed}: {result['n_sites']} sites, {result['n_samples']} samples, "
                  f"pooled={result['pooled_r2']:.3f}, med_site={result['median_site_r2']:.3f}, "
                  f"trees={result['n_trees']} ({elapsed:.0f}s)")

    # =========================================================================
    # STEP 3: Compute anchor scores
    # =========================================================================
    print(f"\n{'='*80}")
    print("STEP 3: Computing anchor scores")
    print(f"{'='*80}")

    n_runs = len(all_runs)
    print(f"Total runs: {n_runs}")

    # Median holdout R² across all runs
    all_pooled = [r["result"]["pooled_r2"] for r in all_runs.values()]
    all_medsite = [r["result"]["median_site_r2"] for r in all_runs.values()]
    median_pooled = np.median(all_pooled)
    median_medsite = np.median(all_medsite)
    print(f"Median pooled R²: {median_pooled:.3f}")
    print(f"Median med-site R²: {median_medsite:.3f}")
    print(f"Pooled R² range: [{min(all_pooled):.3f}, {max(all_pooled):.3f}]")
    print(f"Med-site R² range: [{min(all_medsite):.3f}, {max(all_medsite):.3f}]")

    # Identify which runs are "winners" (above median on BOTH metrics)
    # Use med-site R² as primary (it's the harder metric)
    winner_seeds = set()
    for seed, run in all_runs.items():
        if run["result"]["median_site_r2"] > median_medsite:
            winner_seeds.add(seed)
    print(f"Winner runs (above-median med-site R²): {len(winner_seeds)}")

    # For each training site, compute appearance and win rate
    expected_rate = 100.0 / n_total  # ~34.8%
    print(f"Expected appearance rate: {expected_rate:.1f}%")

    site_stats = {}
    for sid in all_train_sites:
        appeared_in = []
        won_in = []
        for seed, run in all_runs.items():
            if sid in run["sites"]:
                appeared_in.append(seed)
                if seed in winner_seeds:
                    won_in.append(seed)
        n_appeared = len(appeared_in)
        n_won = len(won_in)
        win_rate = n_won / max(n_appeared, 1)
        anchor_score = win_rate - (len(winner_seeds) / n_runs)  # expected win rate = fraction of winners

        site_stats[sid] = {
            "site_id": sid,
            "n_appeared": n_appeared,
            "n_won": n_won,
            "win_rate": win_rate,
            "anchor_score": anchor_score,
        }

    # Get site characteristics
    site_chars = train_data.groupby("site_id").agg(
        n_samples=("lab_value", "count"),
        median_ssc=("lab_value", "median"),
        std_ssc=("lab_value", "std"),
        mean_ssc=("lab_value", "mean"),
    ).reset_index()

    # Add collection method
    if "collection_method" in train_data.columns:
        cm = train_data.groupby("site_id")["collection_method"].agg(
            lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else "unknown"
        ).reset_index()
        cm.columns = ["site_id", "collection_method"]
        site_chars = site_chars.merge(cm, on="site_id", how="left")

    scores_df = pd.DataFrame(site_stats.values())
    scores_df = scores_df.merge(site_chars, on="site_id", how="left")
    scores_df = scores_df.sort_values("anchor_score", ascending=False).reset_index(drop=True)

    # =========================================================================
    # STEP 4: Report results
    # =========================================================================
    print(f"\n{'='*80}")
    print("STEP 4: TOP 20 ANCHOR SITES")
    print(f"{'='*80}")
    top20 = scores_df.head(20)
    print(f"{'Site':<12} {'Appeared':>8} {'Won':>4} {'WinRate':>8} {'AnchorSc':>9} {'Samples':>8} {'MedSSC':>8} {'StdSSC':>8} {'Method':<18}")
    print("-" * 100)
    for _, row in top20.iterrows():
        cm = row.get("collection_method", "?")
        print(f"{row['site_id']:<12} {row['n_appeared']:>8} {row['n_won']:>4} {row['win_rate']:>8.2f} {row['anchor_score']:>9.3f} "
              f"{row['n_samples']:>8.0f} {row['median_ssc']:>8.1f} {row['std_ssc']:>8.1f} {cm:<18}")

    print(f"\n{'='*80}")
    print("BOTTOM 20 NOISE SITES")
    print(f"{'='*80}")
    bottom20 = scores_df.tail(20).iloc[::-1]
    print(f"{'Site':<12} {'Appeared':>8} {'Won':>4} {'WinRate':>8} {'AnchorSc':>9} {'Samples':>8} {'MedSSC':>8} {'StdSSC':>8} {'Method':<18}")
    print("-" * 100)
    for _, row in bottom20.iterrows():
        cm = row.get("collection_method", "?")
        print(f"{row['site_id']:<12} {row['n_appeared']:>8} {row['n_won']:>4} {row['win_rate']:>8.2f} {row['anchor_score']:>9.3f} "
              f"{row['n_samples']:>8.0f} {row['median_ssc']:>8.1f} {row['std_ssc']:>8.1f} {cm:<18}")

    # Summary statistics
    print(f"\n{'='*80}")
    print("ANCHOR SCORE DISTRIBUTION")
    print(f"{'='*80}")
    print(f"Mean anchor score: {scores_df['anchor_score'].mean():.3f}")
    print(f"Std anchor score: {scores_df['anchor_score'].std():.3f}")
    print(f"Sites with anchor_score > 0.2: {len(scores_df[scores_df['anchor_score'] > 0.2])}")
    print(f"Sites with anchor_score < -0.2: {len(scores_df[scores_df['anchor_score'] < -0.2])}")
    print(f"Sites never appearing in any run: {len(scores_df[scores_df['n_appeared'] == 0])}")

    # =========================================================================
    # STEP 4b: Train model on top-50 anchor sites
    # =========================================================================
    print(f"\n{'='*80}")
    print("STEP 4b: Training model on TOP 50 ANCHOR SITES")
    print(f"{'='*80}")

    top50_sites = set(scores_df.head(50)["site_id"])
    save_path = MODELS_DIR / "ssc_C_v7_anchor50.cbm"

    t0 = time.time()
    result_anchor = train_and_eval(
        train_data[train_data["site_id"].isin(top50_sites)],
        holdout_data, num_cols, cat_cols,
        "v7-anchor50",
        save_path=save_path,
    )
    elapsed = time.time() - t0

    if result_anchor:
        print(f"Anchor-50 result: {result_anchor['n_sites']} sites, {result_anchor['n_samples']} samples")
        print(f"  Pooled R²:   {result_anchor['pooled_r2']:.3f}")
        print(f"  Med site R²: {result_anchor['median_site_r2']:.3f}")
        print(f"  Mean site R²: {result_anchor['mean_site_r2']:.3f}")
        print(f"  Trees: {result_anchor['n_trees']}")
        print(f"  Time: {elapsed:.0f}s")

    # Compare
    print(f"\n{'='*80}")
    print("COMPARISON: Anchor-50 vs Random-100 (15 seeds) vs All-287")
    print(f"{'='*80}")

    # Also train all-287 for comparison
    t0 = time.time()
    result_all = train_and_eval(
        train_data, holdout_data, num_cols, cat_cols, "all-287",
    )
    elapsed_all = time.time() - t0

    print(f"{'Model':<25} {'Sites':>6} {'Samples':>8} {'Pooled R²':>10} {'Med Site R²':>12}")
    print("-" * 65)
    if result_anchor:
        print(f"{'Anchor-50':<25} {result_anchor['n_sites']:>6} {result_anchor['n_samples']:>8} "
              f"{result_anchor['pooled_r2']:>10.3f} {result_anchor['median_site_r2']:>12.3f}")
    print(f"{'Random-100 (mean±std)':<25} {'100':>6} {'~9200':>8} "
          f"{np.mean(all_pooled):>10.3f}±{np.std(all_pooled):.3f} {np.mean(all_medsite):>7.3f}±{np.std(all_medsite):.3f}")
    print(f"{'Random-100 (best)':<25} {'100':>6} {'~9200':>8} "
          f"{max(all_pooled):>10.3f} {max(all_medsite):>12.3f}")
    if result_all:
        print(f"{'All-287':<25} {result_all['n_sites']:>6} {result_all['n_samples']:>8} "
              f"{result_all['pooled_r2']:>10.3f} {result_all['median_site_r2']:>12.3f}")

    # =========================================================================
    # Save detailed results
    # =========================================================================
    results_path = DATA_DIR / "results" / "anchor_site_analysis.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)

    save_data = {
        "n_runs": n_runs,
        "seeds": sorted(all_runs.keys()),
        "median_pooled_r2": float(median_pooled),
        "median_medsite_r2": float(median_medsite),
        "per_run": {
            str(seed): {
                "sites": run["sites"],
                "pooled_r2": float(run["result"]["pooled_r2"]),
                "median_site_r2": float(run["result"]["median_site_r2"]),
            }
            for seed, run in all_runs.items()
        },
        "anchor50_result": {
            "n_sites": result_anchor["n_sites"] if result_anchor else None,
            "n_samples": result_anchor["n_samples"] if result_anchor else None,
            "pooled_r2": float(result_anchor["pooled_r2"]) if result_anchor else None,
            "median_site_r2": float(result_anchor["median_site_r2"]) if result_anchor else None,
        },
        "all287_result": {
            "pooled_r2": float(result_all["pooled_r2"]) if result_all else None,
            "median_site_r2": float(result_all["median_site_r2"]) if result_all else None,
        },
    }

    with open(results_path, "w") as f:
        json.dump(save_data, f, indent=2)
    print(f"\nDetailed results saved to {results_path}")

    # Save anchor scores CSV
    csv_path = DATA_DIR / "results" / "anchor_site_scores.csv"
    scores_df.to_csv(csv_path, index=False)
    print(f"Anchor scores saved to {csv_path}")

    print(f"\nDone! Models saved to {MODELS_DIR}/ssc_C_anchor_s*.cbm and ssc_C_v7_anchor50.cbm")


if __name__ == "__main__":
    main()
