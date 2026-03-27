"""Head-to-head comparison: our CatBoost global model vs USGS OLS per-site regression.

For each holdout site, with the same N calibration samples, compare:
- USGS approach: log10(SSC) = a + b*log10(Turbidity), fit per-site
- Our approach: CatBoost global model + 2-param log-space correction

Identifies where each method wins and what site characteristics predict it.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import linregress, spearmanr

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
DATA_DIR = PROJECT_ROOT / "data"


def main():
    from murkml.data.attributes import load_streamcat_attrs

    paired = pd.read_parquet(DATA_DIR / "processed" / "turbidity_ssc_paired.parquet")
    split = pd.read_parquet(DATA_DIR / "train_holdout_split.parquet")
    holdout_ids = set(split[split["role"] == "holdout"]["site_id"])
    holdout = paired[paired["site_id"].isin(holdout_ids)].copy()
    holdout = holdout.dropna(subset=["turbidity_instant", "lab_value"])
    holdout = holdout[(holdout["turbidity_instant"] > 0) & (holdout["lab_value"] > 0)]

    pred = pd.read_parquet(DATA_DIR / "results" / "prediction_intervals.parquet")
    ws = load_streamcat_attrs(DATA_DIR)
    basic = pd.read_parquet(DATA_DIR / "site_attributes.parquet")

    N = 10
    N_TRIALS = 50
    rng = np.random.default_rng(42)

    site_results = []

    for site_id in sorted(holdout["site_id"].unique()):
        site_paired = holdout[holdout["site_id"] == site_id].reset_index(drop=True)
        site_pred = pred[pred["site_id"] == site_id].reset_index(drop=True)
        n = len(site_paired)

        if N >= n - 2 or n < 12 or len(site_pred) != n:
            continue

        usgs_r2s, ours_r2s = [], []
        usgs_slopes, ours_slopes = [], []
        usgs_rmses, ours_rmses = [], []

        for trial in range(N_TRIALS):
            cal_idx = rng.choice(n, N, replace=False)
            test_idx = np.setdiff1d(np.arange(n), cal_idx)
            ssc_true = site_paired.iloc[test_idx]["lab_value"].values

            # --- USGS OLS ---
            try:
                cal_p = site_paired.iloc[cal_idx]
                test_p = site_paired.iloc[test_idx]
                lt_cal = np.log10(cal_p["turbidity_instant"].values)
                ls_cal = np.log10(cal_p["lab_value"].values)
                b_u, a_u, _, _, _ = linregress(lt_cal, ls_cal)
                lt_test = np.log10(test_p["turbidity_instant"].values)
                ssc_usgs = 10 ** (a_u + b_u * lt_test)
                resid = ls_cal - (a_u + b_u * lt_cal)
                ssc_usgs *= np.mean(10**resid)

                ss_res = np.sum((ssc_true - ssc_usgs) ** 2)
                ss_tot = np.sum((ssc_true - np.mean(ssc_true)) ** 2)
                r2_u = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
                try:
                    sl_u, _, _, _, _ = linregress(ssc_true, ssc_usgs)
                except ValueError:
                    sl_u = np.nan
                usgs_r2s.append(r2_u)
                usgs_slopes.append(sl_u)
                usgs_rmses.append(np.sqrt(np.mean((ssc_true - ssc_usgs) ** 2)))
            except Exception:
                continue

            # --- Our method ---
            try:
                cal_o = site_pred.iloc[cal_idx]
                test_o = site_pred.iloc[test_idx]
                a_o, b_o, _, _, _ = linregress(cal_o["y_pred_log"].values, cal_o["y_true_log"].values)
                a_o = np.clip(a_o, 0.1, 10.0)
                corr_log = a_o * test_o["y_pred_log"].values + b_o
                ssc_ours = np.clip(np.expm1(corr_log), 0, None)
                cal_corr = np.clip(np.expm1(a_o * cal_o["y_pred_log"].values + b_o), 1e-6, None)
                bcf = np.clip(np.mean(cal_o["y_true_native_mgL"].values) / np.mean(cal_corr), 0.1, 10.0)
                ssc_ours *= bcf

                ssc_true_o = test_o["y_true_native_mgL"].values
                ss_res = np.sum((ssc_true_o - ssc_ours) ** 2)
                ss_tot = np.sum((ssc_true_o - np.mean(ssc_true_o)) ** 2)
                r2_o = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
                try:
                    sl_o, _, _, _, _ = linregress(ssc_true_o, ssc_ours)
                except ValueError:
                    sl_o = np.nan
                ours_r2s.append(r2_o)
                ours_slopes.append(sl_o)
                ours_rmses.append(np.sqrt(np.mean((ssc_true_o - ssc_ours) ** 2)))
            except Exception:
                continue

        if len(usgs_r2s) < 10 or len(ours_r2s) < 10:
            continue

        attrs = {"site_id": site_id, "n_samples": n}
        ws_row = ws[ws["site_id"] == site_id]
        basic_row = basic[basic["site_id"] == site_id]
        for col in ["forest_pct", "agriculture_pct", "developed_pct", "sand_pct",
                     "clay_pct", "drainage_area_km2", "precip_mean_mm",
                     "baseflow_index", "slope_pct", "soil_permeability"]:
            if not ws_row.empty and col in ws_row.columns:
                v = ws_row[col].values[0]
                attrs[col] = float(v) if pd.notna(v) else np.nan
            elif not basic_row.empty and col in basic_row.columns:
                v = basic_row[col].values[0]
                attrs[col] = float(v) if pd.notna(v) else np.nan
            else:
                attrs[col] = np.nan
        if not basic_row.empty:
            attrs["huc2"] = str(basic_row["huc2"].values[0])

        attrs["usgs_r2"] = np.nanmedian(usgs_r2s)
        attrs["ours_r2"] = np.nanmedian(ours_r2s)
        attrs["usgs_slope"] = np.nanmedian(usgs_slopes)
        attrs["ours_slope"] = np.nanmedian(ours_slopes)
        attrs["usgs_rmse"] = np.nanmedian(usgs_rmses)
        attrs["ours_rmse"] = np.nanmedian(ours_rmses)
        attrs["r2_advantage"] = attrs["ours_r2"] - attrs["usgs_r2"]
        attrs["rmse_advantage"] = attrs["usgs_rmse"] - attrs["ours_rmse"]
        site_results.append(attrs)

    df = pd.DataFrame(site_results).sort_values("r2_advantage")

    print(f"Compared {len(df)} holdout sites at N={N}")
    print(f"Our method wins on R²: {(df['r2_advantage'] > 0).sum()} sites")
    print(f"USGS OLS wins on R²: {(df['r2_advantage'] < 0).sum()} sites")
    print(f"Tied (within 0.01): {((df['r2_advantage'].abs() < 0.01)).sum()} sites")
    print(f"Median R² advantage: {df['r2_advantage'].median():+.3f}")
    print()

    print("=" * 110)
    print("SITES WHERE USGS OLS BEATS OUR MODEL")
    print("=" * 110)
    losers = df[df["r2_advantage"] < -0.01].sort_values("r2_advantage")
    for _, r in losers.iterrows():
        dev = r.get("developed_pct", np.nan)
        sand = r.get("sand_pct", np.nan)
        drain = r.get("drainage_area_km2", np.nan)
        forest = r.get("forest_pct", np.nan)
        ag = r.get("agriculture_pct", np.nan)
        huc = r.get("huc2", "?")
        print(f"  {r['site_id']:25s}  USGS={r['usgs_r2']:+.3f}  Ours={r['ours_r2']:+.3f}  "
              f"gap={r['r2_advantage']:+.3f}  n={int(r['n_samples'])}  "
              f"forest={forest:.0f}%  ag={ag:.0f}%  dev={dev:.0f}%  "
              f"sand={sand:.0f}%  drain={drain:.0f}km²  HUC={huc}")

    print()
    print("=" * 110)
    print("SITES WHERE OUR MODEL EXCELS (top 15)")
    print("=" * 110)
    winners = df[df["r2_advantage"] > 0.01].sort_values("r2_advantage", ascending=False).head(15)
    for _, r in winners.iterrows():
        dev = r.get("developed_pct", np.nan)
        sand = r.get("sand_pct", np.nan)
        drain = r.get("drainage_area_km2", np.nan)
        forest = r.get("forest_pct", np.nan)
        ag = r.get("agriculture_pct", np.nan)
        huc = r.get("huc2", "?")
        print(f"  {r['site_id']:25s}  USGS={r['usgs_r2']:+.3f}  Ours={r['ours_r2']:+.3f}  "
              f"gap={r['r2_advantage']:+.3f}  n={int(r['n_samples'])}  "
              f"forest={forest:.0f}%  ag={ag:.0f}%  dev={dev:.0f}%  "
              f"sand={sand:.0f}%  drain={drain:.0f}km²  HUC={huc}")

    print()
    print("=" * 110)
    print("WHAT PREDICTS WHERE EACH METHOD WINS?")
    print("(Positive rho = our model favored)")
    print("=" * 110)
    for col in ["forest_pct", "agriculture_pct", "developed_pct", "sand_pct",
                "clay_pct", "drainage_area_km2", "precip_mean_mm",
                "baseflow_index", "slope_pct", "soil_permeability", "n_samples"]:
        valid = df.dropna(subset=[col, "r2_advantage"])
        if len(valid) > 5:
            rho, p = spearmanr(valid[col], valid["r2_advantage"])
            sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
            direction = "our model better" if rho > 0 else "USGS better"
            print(f"  {col:25s}: rho={rho:+.3f}  p={p:.4f}  {sig:3s}  (higher {col} = {direction})")

    # Save
    out = DATA_DIR / "results" / "usgs_comparison.parquet"
    df.to_parquet(out, index=False)
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
