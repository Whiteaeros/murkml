"""Re-ablation on the 62-feature set + confounding pair tests.

Runs 4 experiments in parallel (each with 2 internal GKF5 workers = 8 threads total).
"""

import subprocess
import json
import time
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
python = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")

# Features to drop from the full 102 to get our 62-feature set
BASE_DROP = set(
    "pct_coastal_coarse,geol_class,pct_saline_lake,geo_cao,temp_at_sample,"
    "pct_siliciclastic,pct_glacial_till_coarse,turbidity_min_1hr,SC_turb_interaction,"
    "compressive_strength,slope_pct,huc2,pct_glacial_lake_coarse,pct_glacial_till_loam,"
    "runoff_mean,water_table_depth,geo_al2o3,turbidity_mean_1hr,turbidity_range_1hr,"
    "pct_water_geology,rock_nitrogen,temp_mean_c,precip_mean_mm,log_turbidity_instant,"
    "shrub_pct,coalmine_density,pct_extrusive_volcanic,geo_sio2,geo_k2o,"
    "wwtp_major_density,septic_density,pct_nonite_resid,pct_hydric,"
    "pct_alkaline_intrusive,road_density,ag_drainage_pct,pct_glacial_till_clay,"
    "dam_density,soil_rock_depth,mine_density".split(",")
)

# All 62 remaining features to test individually
REMAINING = [
    "turbidity_instant", "turbidity_max_1hr", "turbidity_std_1hr",
    "turbidity_slope_1hr", "log_drainage_area", "turb_saturated",
    "conductance_instant", "discharge_instant", "discharge_slope_2hr",
    "rising_limb", "do_instant", "ph_instant", "temp_instant",
    "DO_sat_departure", "Q_7day_mean", "Q_30day_mean", "Q_ratio_7d",
    "turb_Q_ratio", "precip_24h", "precip_48h", "precip_7d",
    "days_since_rain", "doy_sin", "doy_cos",
    "latitude", "longitude", "elevation_m", "drainage_area_km2",
    "forest_pct", "agriculture_pct", "developed_pct", "wetland_pct",
    "grass_pct", "clay_pct", "sand_pct",
    "soil_erodibility", "soil_permeability", "soil_organic_matter",
    "hydraulic_conductivity", "baseflow_index", "wetness_index",
    "hydrologic_connectivity", "dam_storage_density",
    "nitrogen_surplus", "fertilizer_rate", "manure_rate", "bio_n_fixation",
    "geo_na2o", "geo_fe2o3", "geo_mgo",
    "pct_eolian_fine", "pct_eolian_coarse", "pct_colluvial_sediment",
    "pct_alluvial_coastal", "pct_carbonate_resid", "pct_glacial_lake_fine",
    "pop_density", "npdes_density", "wwtp_all_density", "wwtp_minor_density",
    "superfund_density",
]

# Confounding pairs to test
PAIRS = [
    ("ph+do", ["ph_instant", "do_instant"]),
    ("ph+do+DOsat+temp", ["ph_instant", "do_instant", "DO_sat_departure", "temp_instant"]),
    ("Q_inst+slope+rising", ["discharge_instant", "discharge_slope_2hr", "rising_limb"]),
    ("nutrients4", ["nitrogen_surplus", "manure_rate", "fertilizer_rate", "bio_n_fixation"]),
    ("geo3", ["latitude", "longitude", "elevation_m"]),
    ("precip_timing", ["precip_24h", "days_since_rain"]),
    ("all_wastewater", ["npdes_density", "wwtp_all_density", "wwtp_minor_density"]),
    ("clay+sand", ["clay_pct", "sand_pct"]),
    ("eolian_both", ["pct_eolian_fine", "pct_eolian_coarse"]),
]


def run_one(label, extra_drops):
    """Run one ablation experiment, return (label, metrics_dict)."""
    drop_set = BASE_DROP | set(extra_drops)
    cmd = [
        python, "scripts/train_tiered.py",
        "--param", "ssc", "--tier", "C", "--cv-mode", "gkf5",
        "--skip-ridge", "--skip-save-model", "--no-monotone",
        "--config-json", json.dumps({"boosting_type": "Plain"}),
        "--label", label,
        "--drop-features", ",".join(drop_set),
        "--n-jobs", "4",
    ]
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180,
            cwd=str(PROJECT_ROOT),
        )
        # Parse all metrics from stderr
        metrics = {"label": label}
        for line in r.stderr.split("\n"):
            if "KGE(log)=" in line:
                for part in line.split():
                    if "(log)=" in part and "KGE" not in part:
                        try:
                            metrics["r2_log"] = float(part.split("=")[1])
                        except ValueError:
                            pass
                    elif "KGE(log)=" in part:
                        try:
                            metrics["kge_log"] = float(part.split("=")[1])
                        except ValueError:
                            pass
                # Native metrics are after the |
                if "|" in line:
                    native_part = line.split("|")[1]
                    for part in native_part.split():
                        if "(mg/L)=" in part and "RMSE" not in part:
                            try:
                                metrics["r2_native"] = float(part.split("=")[1])
                            except ValueError:
                                pass
                        elif "RMSE(mg/L)=" in part:
                            try:
                                metrics["rmse_native"] = float(part.split("=")[1])
                            except ValueError:
                                pass
                        elif "Bias=" in part:
                            try:
                                metrics["bias_pct"] = float(part.split("=")[1].rstrip("%"))
                            except ValueError:
                                pass
            if "Trees per fold" in line:
                try:
                    metrics["median_trees"] = int(line.split("median=")[1].split(",")[0])
                except (ValueError, IndexError):
                    pass
        return label, metrics
    except Exception as e:
        return label, {"label": label}


def main():
    # Build task list
    tasks = [("base62", [])]
    for feat in REMAINING:
        tasks.append((f"drop_{feat}", [feat]))
    for label, feats in PAIRS:
        tasks.append((f"pair_{label}", feats))

    print(f"Running {len(tasks)} experiments with 4 parallel workers...")
    t0 = time.time()

    results = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(run_one, label, drops): label for label, drops in tasks}
        done = 0
        for future in as_completed(futures):
            label, metrics = future.result()
            results[label] = metrics
            done += 1
            if done % 10 == 0:
                print(f"  {done}/{len(tasks)} done ({time.time()-t0:.0f}s)")

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.0f}s ({elapsed/60:.1f}min)")

    base = results.get("base62", {})
    r2_base = base.get("r2_log", 0)
    r2n_base = base.get("r2_native", 0)
    kge_base = base.get("kge_log", 0)
    print(f"\nBASE (62 features): R2_log={r2_base:.4f}  R2_native={r2n_base:.4f}  KGE={kge_base:.4f}")

    # Single features sorted by log R2 impact
    print(f"\n{'=== SINGLE FEATURES (sorted by R2_log impact) ===':60s}")
    print(f"  {'feature':35s}  {'dR2log':>7s}  {'dR2nat':>7s}  {'dKGE':>7s}  verdict")
    print(f"  {'-'*75}")
    singles = [(k.replace("drop_", ""), v) for k, v in results.items() if k.startswith("drop_")]
    singles.sort(key=lambda x: x[1].get("r2_log", 999) - r2_base)
    for feat, m in singles:
        r2 = m.get("r2_log")
        r2n = m.get("r2_native")
        kge = m.get("kge_log")
        if r2 is not None:
            d_log = r2 - r2_base
            d_nat = (r2n - r2n_base) if r2n is not None else float("nan")
            d_kge = (kge - kge_base) if kge is not None else float("nan")
            if d_log > 0.002: verdict = "HARMFUL"
            elif d_log > 0.0005: verdict = "harmful"
            elif d_log > -0.0005: verdict = "neutral"
            elif d_log > -0.002: verdict = "helpful"
            else: verdict = "HELPFUL"
            print(f"  {feat:35s}  {d_log:+.4f}  {d_nat:+.4f}  {d_kge:+.4f}  [{verdict}]")
        else:
            print(f"  {feat:35s}  FAILED")

    # Confounding pairs
    print(f"\n{'=== CONFOUNDING PAIRS ===':60s}")
    print(f"  {'pair':25s}  {'dR2log':>7s}  {'dR2nat':>7s}  {'interaction':>11s}")
    for label, feats in PAIRS:
        m = results.get(f"pair_{label}", {})
        r2 = m.get("r2_log")
        r2n = m.get("r2_native")
        if r2 is not None:
            d_log = r2 - r2_base
            d_nat = (r2n - r2n_base) if r2n is not None else float("nan")
            ind_sum = sum(
                results.get(f"drop_{f}", {}).get("r2_log", r2_base) - r2_base
                for f in feats
            )
            interaction = d_log - ind_sum
            print(f"  {label:25s}  {d_log:+.4f}  {d_nat:+.4f}    {interaction:+.4f}")

    # Save full metrics
    rows = []
    for label, m in results.items():
        rows.append(m)
    df = pd.DataFrame(rows)
    out_path = PROJECT_ROOT / "data" / "results" / "ablation_62feat_reablation.parquet"
    df.to_parquet(out_path, index=False)
    print(f"\nSaved to {out_path.name} ({len(df.columns)} columns)")


if __name__ == "__main__":
    main()
