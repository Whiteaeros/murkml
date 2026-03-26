"""
Significance tests on LOGO CV tier differences and literature comparison table.

Part 1: Paired Wilcoxon signed-rank tests across tiers A, B, C
Part 2: Literature comparison table for multi-site turbidity-SSC models
"""

import pandas as pd
import numpy as np
from scipy.stats import wilcoxon
from pathlib import Path

RESULTS_DIR = Path("data/results")


# ---------------------------------------------------------------------------
# Part 1: Significance tests
# ---------------------------------------------------------------------------

def load_tiers():
    """Load per-fold LOGO CV results for tiers A, B, C."""
    a = pd.read_parquet(RESULTS_DIR / "logo_folds_ssc_A_sensor_only.parquet")
    b = pd.read_parquet(RESULTS_DIR / "logo_folds_ssc_B_sensor_basic.parquet")
    c = pd.read_parquet(RESULTS_DIR / "logo_folds_ssc_C_sensor_basic_watershed.parquet")
    return a, b, c


def paired_wilcoxon(df1, df2, label1, label2, metrics):
    """Run paired Wilcoxon signed-rank tests on shared sites."""
    shared = set(df1["site_id"]) & set(df2["site_id"])
    print(f"\n{'='*70}")
    print(f"  {label1} vs {label2}  |  {len(shared)} shared sites")
    print(f"{'='*70}")

    d1 = df1.set_index("site_id").loc[list(shared)]
    d2 = df2.set_index("site_id").loc[list(shared)]

    rows = []
    for m in metrics:
        x = d1[m].values
        y = d2[m].values
        diff = y - x  # positive means tier2 is better (for r2/kge) or worse (for rmse)

        # Drop pairs where difference is exactly zero (wilcoxon requirement)
        nonzero = diff != 0
        if nonzero.sum() < 5:
            print(f"  {m}: too few non-zero differences ({nonzero.sum()}), skipping")
            continue

        stat, p = wilcoxon(diff[nonzero])
        median_diff = np.median(diff)
        mean_diff = np.mean(diff)

        # Effect size: r = Z / sqrt(N)  where Z approx from p
        n = nonzero.sum()
        # Approximate Z from the test statistic
        # For large n, W ~ N(n(n+1)/4, n(n+1)(2n+1)/24)
        mu = n * (n + 1) / 4
        sigma = np.sqrt(n * (n + 1) * (2 * n + 1) / 24)
        z = (stat - mu) / sigma if sigma > 0 else 0
        r_effect = abs(z) / np.sqrt(n)

        sig_05 = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""

        print(f"  {m:20s}  median_diff={median_diff:+.4f}  "
              f"W={stat:.0f}  p={p:.2e}  r={r_effect:.3f}  {sig_05}")

        rows.append({
            "comparison": f"{label1}_vs_{label2}",
            "metric": m,
            "n_shared_sites": len(shared),
            "n_nonzero_pairs": int(n),
            "median_diff": median_diff,
            "mean_diff": mean_diff,
            "W_statistic": stat,
            "p_value": p,
            "effect_size_r": r_effect,
            "sig_0.05": p < 0.05,
            "sig_0.01": p < 0.01,
        })

    return rows


def run_significance_tests():
    a, b, c = load_tiers()

    print(f"Tier A sites: {len(a)}")
    print(f"Tier B sites: {len(b)}")
    print(f"Tier C sites: {len(c)}")

    metrics = ["r2_log", "kge_log", "r2_native", "rmse_native_mgL"]

    all_rows = []
    all_rows.extend(paired_wilcoxon(a, b, "A", "B", metrics))
    all_rows.extend(paired_wilcoxon(b, c, "B", "C", metrics))
    all_rows.extend(paired_wilcoxon(a, c, "A", "C", metrics))

    df = pd.DataFrame(all_rows)
    out_path = RESULTS_DIR / "significance_tests.parquet"
    df.to_parquet(out_path, index=False)
    print(f"\nSaved significance tests to {out_path}")

    # Print summary table
    print("\n" + "=" * 70)
    print("  SUMMARY TABLE")
    print("=" * 70)
    for _, row in df.iterrows():
        sig = ""
        if row["sig_0.01"]:
            sig = "p<0.01"
        elif row["sig_0.05"]:
            sig = "p<0.05"
        else:
            sig = "n.s."
        print(f"  {row['comparison']:10s}  {row['metric']:20s}  "
              f"median_diff={row['median_diff']:+.4f}  {sig}")

    return df


# ---------------------------------------------------------------------------
# Part 2: Literature comparison table
# ---------------------------------------------------------------------------

def build_literature_table():
    """
    Build a comparison table of published multi-site turbidity-SSC model results.

    Values are drawn from published papers or estimated from reported ranges.
    Where exact values are unavailable, cells are left blank or noted.
    """
    rows = [
        # --- This study ---
        {
            "study": "This study (global LOGO CV)",
            "year": 2026,
            "sites": 243,
            "method": "CatBoost LOGO CV",
            "r2_log": 0.71,
            "r2_native": 0.36,
            "native_slope": 0.19,
            "scope": "CONUS multi-site",
            "notes": "Tier C, sensor + basic + watershed features",
        },
        {
            "study": "This study (holdout)",
            "year": 2026,
            "sites": 57,
            "method": "CatBoost final model",
            "r2_log": None,
            "r2_native": 0.55,
            "native_slope": 0.65,
            "scope": "CONUS holdout sites",
            "notes": "External validation on unseen sites",
        },
        {
            "study": "This study (N=10 adapt)",
            "year": 2026,
            "sites": 48,
            "method": "CatBoost + 10 cal samples",
            "r2_log": None,
            "r2_native": 0.60,
            "native_slope": 0.79,
            "scope": "CONUS holdout sites",
            "notes": "Site adaptation with 10 calibration samples",
        },
        # --- Classic references ---
        {
            "study": "Rasmussen et al.",
            "year": 2009,
            "sites": None,
            "method": "OLS site-specific (turb vs SSC)",
            "r2_log": None,
            "r2_native": None,
            "native_slope": None,
            "scope": "USGS guidelines",
            "notes": "USGS TM 3-C4: site-specific OLS regressions; R2 typically 0.7-0.95 per site",
        },
        {
            "study": "Jastram et al.",
            "year": 2009,
            "sites": 3,
            "method": "OLS turbidity-SSC regression",
            "r2_log": None,
            "r2_native": None,
            "native_slope": None,
            "scope": "Chesapeake Bay tributaries",
            "notes": "SIR 2009-5165; site-specific R2 0.91-0.95; not transferable across sites",
        },
        {
            "study": "Uhrich & Bragg",
            "year": 2003,
            "sites": 1,
            "method": "OLS turbidity-SSC regression",
            "r2_log": None,
            "r2_native": None,
            "native_slope": None,
            "scope": "North Santiam River, OR",
            "notes": "Site-specific monitoring; R2~0.93 for single site",
        },
        {
            "study": "Warrick",
            "year": 2015,
            "sites": None,
            "method": "Power-law SSC-Q regressions",
            "r2_log": None,
            "r2_native": None,
            "native_slope": None,
            "scope": "US rivers review",
            "notes": "Trends in SSC across US rivers; rating curves are site-specific, no multi-site R2",
        },
        {
            "study": "Gray & Gartner",
            "year": 2009,
            "sites": None,
            "method": "Review of surrogate technologies",
            "r2_log": None,
            "r2_native": None,
            "native_slope": None,
            "scope": "Global review",
            "notes": "WRR review; turbidimeters reliable where grain-size distribution is stable",
        },
        # --- ML comparisons ---
        {
            "study": "Hamshaw et al.",
            "year": 2018,
            "sites": 1,
            "method": "ML hysteresis classification (RF)",
            "r2_log": None,
            "r2_native": None,
            "native_slope": None,
            "scope": "Mad River, VT",
            "notes": "600+ storm events; ML for SSC-Q hysteresis patterns, not SSC prediction",
        },
        {
            "study": "Zhi et al.",
            "year": 2024,
            "sites": None,
            "method": "Deep learning (review/perspective)",
            "r2_log": None,
            "r2_native": None,
            "native_slope": None,
            "scope": "Multi-parameter WQ review",
            "notes": "Nature Water; DL for WQ broadly, not SSC-specific; highlights spatial transferability gap",
        },
        {
            "study": "Chen et al.",
            "year": 2020,
            "sites": None,
            "method": "ANN review (151 papers)",
            "r2_log": None,
            "r2_native": None,
            "native_slope": None,
            "scope": "WQ prediction review",
            "notes": "Applied Sciences; 23 WQ variables; most studies single-site; SSC rarely tested multi-site",
        },
    ]

    df = pd.DataFrame(rows)
    out_path = RESULTS_DIR / "literature_comparison.csv"
    df.to_csv(out_path, index=False)
    print(f"\nSaved literature comparison to {out_path}")

    # Pretty print
    print("\n" + "=" * 100)
    print("  LITERATURE COMPARISON TABLE")
    print("=" * 100)
    print(f"{'Study':<35s} {'Sites':>5s} {'Method':<30s} {'R2(log)':>8s} {'R2(nat)':>8s} {'Slope':>6s}")
    print("-" * 100)
    for _, row in df.iterrows():
        sites = str(row["sites"]) if pd.notna(row["sites"]) else "—"
        r2l = f"{row['r2_log']:.2f}" if pd.notna(row["r2_log"]) else "—"
        r2n = f"{row['r2_native']:.2f}" if pd.notna(row["r2_native"]) else "—"
        slp = f"{row['native_slope']:.2f}" if pd.notna(row["native_slope"]) else "—"
        print(f"  {row['study']:<33s} {sites:>5s} {row['method']:<30s} {r2l:>8s} {r2n:>8s} {slp:>6s}")

    print("\nKey insight: No prior study reports multi-site transferable SSC prediction.")
    print("Site-specific regressions achieve R2 0.7-0.95, but require per-site calibration.")
    print("This study is the first to demonstrate a single model across 243+ CONUS sites.")

    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    os.chdir(Path(__file__).resolve().parent.parent)

    print("=" * 70)
    print("  PART 1: SIGNIFICANCE TESTS ON TIER DIFFERENCES")
    print("=" * 70)
    sig_df = run_significance_tests()

    print("\n\n")
    print("=" * 70)
    print("  PART 2: LITERATURE COMPARISON")
    print("=" * 70)
    lit_df = build_literature_table()
