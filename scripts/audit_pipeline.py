#!/usr/bin/env python3
"""murkml Data Pipeline Audit Script.

Part A: Validation checks (pass/fail) on all data products.
Part B: Provenance report from manifest files (if available).

Run after every retrain, after downloading new sites, and before paper submission.

Usage:
    python scripts/audit_pipeline.py              # full audit
    python scripts/audit_pipeline.py --checks     # validation only
    python scripts/audit_pipeline.py --provenance # provenance report only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# ──────────────────────────────────────────────────────────────────────
# Part A: Validation checks
# ──────────────────────────────────────────────────────────────────────

class AuditResult:
    def __init__(self):
        self.results: list[tuple[str, bool, str]] = []

    def check(self, name: str, passed: bool, detail: str = ""):
        self.results.append((name, passed, detail))
        tag = "[PASS]" if passed else "[FAIL]"
        print(f"  {tag} {name}" + (f" — {detail}" if detail else ""))

    def summary(self):
        n_pass = sum(1 for _, p, _ in self.results if p)
        n_fail = sum(1 for _, p, _ in self.results if not p)
        return n_pass, n_fail


def check_empty_caches(audit: AuditResult):
    """2.1: Check for empty parquet files that might be cached API failures."""
    # Discrete
    discrete_dir = DATA_DIR / "discrete"
    if discrete_dir.exists():
        discrete_files = list(discrete_dir.glob("*.parquet"))
        small_discrete = [f for f in discrete_files if f.stat().st_size < 1024]
        audit.check(
            "Discrete cache integrity",
            len(small_discrete) == 0,
            f"{len(small_discrete)}/{len(discrete_files)} files < 1KB"
        )
    else:
        audit.check("Discrete cache integrity", False, "data/discrete/ not found")

    # Continuous
    continuous_dir = DATA_DIR / "continuous"
    if continuous_dir.exists():
        cont_files = list(continuous_dir.rglob("*.parquet"))
        small_cont = [f for f in cont_files if f.stat().st_size < 1024]
        audit.check(
            "Continuous cache integrity",
            len(small_cont) < len(cont_files) * 0.5,
            f"{len(small_cont)}/{len(cont_files)} files < 1KB "
            f"({100*len(small_cont)/max(len(cont_files),1):.0f}%)"
        )


def check_gagesii_schema(audit: AuditResult):
    """2.2: Validate GAGES-II file schemas."""
    pruned_path = DATA_DIR / "site_attributes_gagesii.parquet"
    full_path = DATA_DIR / "site_attributes_gagesii_full.parquet"

    if pruned_path.exists():
        df = pd.read_parquet(pruned_path)
        audit.check(
            "GAGES-II pruned: has forest_pct",
            "forest_pct" in df.columns,
        )
        audit.check(
            "GAGES-II pruned: no raw column names",
            "FORESTNLCD06" not in df.columns,
        )
        # Categorical dtypes
        for col in ["geol_class", "ecoregion", "reference_class"]:
            if col in df.columns:
                audit.check(
                    f"GAGES-II pruned: {col} dtype=object",
                    df[col].dtype == object,
                    f"actual dtype={df[col].dtype}"
                )
        # Real values
        audit.check(
            "GAGES-II pruned: forest_pct has real values",
            df["forest_pct"].notna().any() and (df["forest_pct"] != 0).any(),
            f"mean={df['forest_pct'].mean():.1f}, non-zero={int((df['forest_pct'] != 0).sum())}"
        )
        audit.check(
            "GAGES-II pruned: site count",
            df["site_id"].nunique() >= 90,
            f"{df['site_id'].nunique()} sites"
        )
    else:
        audit.check("GAGES-II pruned file exists", False, "not found")

    if full_path.exists():
        df_full = pd.read_parquet(full_path, columns=["STAID"] if "STAID" in pd.read_parquet(full_path, columns=[]).columns else None)
        # Just check first column existence
        cols = pd.read_parquet(full_path).columns
        audit.check(
            "GAGES-II full: has raw column names",
            "FORESTNLCD06" in cols or "STAID" in cols,
            f"first 5 cols: {list(cols[:5])}"
        )
    else:
        audit.check("GAGES-II full file exists", False, "not found")


def check_paired_datasets(audit: AuditResult):
    """2.3: Spot-check paired dataset integrity."""
    expected = {
        "turbidity_ssc_paired.parquet": {"sites": 102, "target": "ssc_log1p"},
        "total_phosphorus_paired.parquet": {"sites": 72, "target": "total_phosphorus_log1p"},
        "nitrate_nitrite_paired.parquet": {"sites": 66, "target": "nitrate_nitrite_log1p"},
        "orthophosphate_paired.parquet": {"sites": 62, "target": "orthophosphate_log1p"},
    }

    for filename, spec in expected.items():
        path = DATA_DIR / "processed" / filename
        if not path.exists():
            audit.check(f"{filename}: exists", False, "not found")
            continue

        df = pd.read_parquet(path)
        param = filename.split("_paired")[0]

        # Site count
        n_sites = df["site_id"].nunique()
        audit.check(
            f"{param}: site count",
            n_sites == spec["sites"],
            f"{n_sites} (expected {spec['sites']})"
        )

        # Lab value non-negative
        audit.check(
            f"{param}: lab_value >= 0",
            (df["lab_value"] >= 0).all(),
            f"min={df['lab_value'].min():.4f}"
        )

        # Turbidity instant never NaN
        if "turbidity_instant" in df.columns:
            n_nan = df["turbidity_instant"].isna().sum()
            audit.check(
                f"{param}: turbidity_instant not NaN",
                n_nan == 0,
                f"{n_nan} NaN values"
            )

        # Match gap within 15 minutes
        if "match_gap_seconds" in df.columns:
            max_gap = df["match_gap_seconds"].max()
            audit.check(
                f"{param}: match_gap <= 900s",
                max_gap <= 900,
                f"max gap={max_gap:.0f}s"
            )

        # No duplicate (site_id, sample_time)
        if "sample_time" in df.columns:
            n_dupes = df.duplicated(subset=["site_id", "sample_time"]).sum()
            audit.check(
                f"{param}: no duplicate (site, time)",
                n_dupes == 0,
                f"{n_dupes} duplicates"
            )

        # Log1p target matches lab_value
        target_col = spec["target"]
        if target_col in df.columns:
            expected_log = np.log1p(df["lab_value"])
            max_diff = (df[target_col] - expected_log).abs().max()
            audit.check(
                f"{param}: {target_col} == log1p(lab_value)",
                max_diff < 1e-10,
                f"max diff={max_diff:.2e}"
            )

        # No all-NaN feature columns (excluding metadata)
        meta_cols = {"site_id", "sample_time", "lab_value", "match_gap_seconds",
                     "window_count", "is_nondetect", "hydro_event", target_col}
        feature_cols = [c for c in df.columns if c not in meta_cols]
        all_nan_cols = [c for c in feature_cols if df[c].isna().all()]
        audit.check(
            f"{param}: no all-NaN feature columns",
            len(all_nan_cols) == 0,
            f"{len(all_nan_cols)} all-NaN: {all_nan_cols[:5]}" if all_nan_cols else ""
        )


def check_feature_sanity(audit: AuditResult):
    """2.4: Feature value sanity checks."""
    ssc_path = DATA_DIR / "processed" / "turbidity_ssc_paired.parquet"
    if not ssc_path.exists():
        return

    df = pd.read_parquet(ssc_path)

    # doy_sin/cos in [-1, 1]
    for col in ["doy_sin", "doy_cos"]:
        if col in df.columns:
            audit.check(
                f"Feature: {col} in [-1, 1]",
                df[col].min() >= -1.0 - 1e-10 and df[col].max() <= 1.0 + 1e-10,
                f"range=[{df[col].min():.6f}, {df[col].max():.6f}]"
            )

    # rising_limb is 0 or 1
    if "rising_limb" in df.columns:
        vals = df["rising_limb"].dropna().unique()
        audit.check(
            "Feature: rising_limb is binary",
            set(vals).issubset({0, 1, 0.0, 1.0}),
            f"unique values: {sorted(vals)[:10]}"
        )

    # Zero-variance features
    meta_cols = {"site_id", "sample_time", "lab_value", "ssc_log1p",
                 "match_gap_seconds", "window_count", "is_nondetect"}
    feature_cols = [c for c in df.columns if c not in meta_cols
                    and df[c].dtype in [np.float64, np.float32, np.int64, np.int32]]
    zero_var = [c for c in feature_cols if df[c].dropna().nunique() <= 1]
    audit.check(
        "Feature: no zero-variance columns",
        len(zero_var) == 0,
        f"{len(zero_var)} zero-variance: {zero_var[:5]}" if zero_var else ""
    )


def check_nlcd_consistency(audit: AuditResult):
    """2.5: NLCD backfill consistency."""
    gagesii_path = DATA_DIR / "site_attributes_gagesii.parquet"
    nlcd_path = DATA_DIR / "site_attributes_nlcd.parquet"

    if not (gagesii_path.exists() and nlcd_path.exists()):
        audit.check("NLCD consistency", False, "missing attribute files")
        return

    g = pd.read_parquet(gagesii_path)
    n = pd.read_parquet(nlcd_path)

    shared_cols = set(g.columns) & set(n.columns) - {"site_id"}
    audit.check(
        "NLCD: shared columns with GAGES-II",
        len(shared_cols) > 0,
        f"{len(shared_cols)} shared: {sorted(shared_cols)[:5]}"
    )

    # Check for negative or >100 percentages
    pct_cols = [c for c in shared_cols if "pct" in c.lower()]
    for col in pct_cols:
        if col in n.columns:
            vals = n[col].dropna()
            audit.check(
                f"NLCD: {col} in [0, 100]",
                vals.min() >= -0.01 and vals.max() <= 100.01,
                f"range=[{vals.min():.2f}, {vals.max():.2f}]"
            )


def check_model_metadata(audit: AuditResult):
    """2.6: Model metadata integrity."""
    model_dir = DATA_DIR / "results" / "models"
    if not model_dir.exists():
        audit.check("Model metadata directory exists", False)
        return

    for meta_path in sorted(model_dir.glob("*_meta.json")):
        with open(meta_path) as f:
            meta = json.load(f)

        name = meta_path.stem.replace("_meta", "")
        tier = meta.get("tier", "unknown")

        # Check feature_ranges for NaN
        ranges = meta.get("feature_ranges", {})
        nan_ranges = [c for c, r in ranges.items()
                      if r and (r.get("min") is None or r.get("max") is None
                                or np.isnan(r["min"]) or np.isnan(r["max"]))]
        audit.check(
            f"Meta {name}: no NaN feature ranges",
            len(nan_ranges) == 0,
            f"{len(nan_ranges)} NaN ranges: {nan_ranges[:5]}" if nan_ranges else ""
        )

        # Check cat_cols for Tier C
        if "gagesii" in tier.lower():
            cat_cols = meta.get("cat_cols", [])
            expected_cats = {"geol_class", "ecoregion", "reference_class", "huc2"}
            found = set(cat_cols) & expected_cats
            audit.check(
                f"Meta {name}: has expected categoricals",
                len(found) >= 3,
                f"found {sorted(found)}, expected {sorted(expected_cats)}"
            )

            # Check sites_per_ecoregion not empty
            eco = meta.get("sites_per_ecoregion", {})
            audit.check(
                f"Meta {name}: sites_per_ecoregion populated",
                len(eco) > 0,
                f"{len(eco)} ecoregions" if eco else "EMPTY"
            )

        # Plausible n_sites / n_samples
        n_sites = meta.get("n_sites", 0)
        n_samples = meta.get("n_samples", 0)
        audit.check(
            f"Meta {name}: plausible counts",
            10 <= n_sites <= 200 and 1000 <= n_samples <= 100000,
            f"{n_sites} sites, {n_samples} samples"
        )


def run_validation_checks() -> tuple[int, int]:
    """Run all validation checks and return (n_pass, n_fail)."""
    print("=" * 60)
    print("  MURKML DATA PIPELINE AUDIT — VALIDATION CHECKS")
    print("=" * 60)
    print()

    audit = AuditResult()

    print("2.1 Raw data cache integrity:")
    check_empty_caches(audit)
    print()

    print("2.2 GAGES-II file schema:")
    check_gagesii_schema(audit)
    print()

    print("2.3 Paired datasets:")
    check_paired_datasets(audit)
    print()

    print("2.4 Feature sanity:")
    check_feature_sanity(audit)
    print()

    print("2.5 NLCD consistency:")
    check_nlcd_consistency(audit)
    print()

    print("2.6 Model metadata:")
    check_model_metadata(audit)
    print()

    n_pass, n_fail = audit.summary()
    print("-" * 60)
    print(f"  {n_pass}/{n_pass + n_fail} checks passed, {n_fail} failed")
    print("-" * 60)
    return n_pass, n_fail


# ──────────────────────────────────────────────────────────────────────
# Part B: Provenance report
# ──────────────────────────────────────────────────────────────────────

def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def run_provenance_report():
    """Generate provenance report from manifest files."""
    print()
    print("=" * 60)
    print("  MURKML DATA PIPELINE AUDIT — PROVENANCE REPORT")
    print("=" * 60)
    print()

    prov_dir = DATA_DIR / "provenance"
    if not prov_dir.exists() or not list(prov_dir.glob("*.json")):
        print("  No provenance manifests found in data/provenance/.")
        print("  Run pipeline scripts with provenance instrumentation to generate them.")
        print("  See Phase 3.8-3.9 in the audit plan.")
        return

    # Load all manifests
    manifests = []
    for p in sorted(prov_dir.glob("*.json")):
        with open(p) as f:
            manifests.append(json.load(f))

    print(f"  Found {len(manifests)} manifest(s)")
    print()

    # Latest manifest per run_name
    latest = {}
    for m in manifests:
        name = m.get("run_name", "unknown")
        if name not in latest or m.get("started_at", "") > latest[name].get("started_at", ""):
            latest[name] = m

    # Sample funnel table (aggregate steps by name)
    for run_name, m in sorted(latest.items()):
        print(f"  Run: {run_name}")
        print(f"    Started:  {m.get('started_at', 'unknown')}")
        print(f"    Finished: {m.get('finished_at', 'unknown')}")
        print(f"    Git:      {m.get('git_commit', 'unknown')[:12]}")
        print(f"    Steps:    {len(m.get('steps', []))}")
        print(f"    Files:    {len(m.get('files', []))}")
        print()

        # Step summary — aggregate by step name
        steps = m.get("steps", [])
        if steps:
            step_names = {}
            for s in steps:
                sname = s.get("step", "unknown")
                if sname not in step_names:
                    step_names[sname] = {"count": 0, "total_in": 0, "total_out": 0}
                step_names[sname]["count"] += 1
                step_names[sname]["total_in"] += s.get("rows_in", 0)
                step_names[sname]["total_out"] += s.get("rows_out", 0)

            print(f"    {'Step':<25} {'Count':>6} {'Rows In':>10} {'Rows Out':>10} {'Drop %':>8}")
            print(f"    {'-'*25} {'-'*6} {'-'*10} {'-'*10} {'-'*8}")
            for sname, info in step_names.items():
                drop_pct = ""
                if info["total_in"] > 0:
                    drop_pct = f"{100*(info['total_in']-info['total_out'])/info['total_in']:.1f}%"
                print(f"    {sname:<25} {info['count']:>6} {info['total_in']:>10} {info['total_out']:>10} {drop_pct:>8}")
            print()

        # File checksums — verify current state
        files = m.get("files", [])
        if files:
            n_verified = 0
            n_stale = 0
            n_missing = 0
            for finfo in files:
                fpath = PROJECT_ROOT / finfo.get("path", "")
                if not fpath.exists():
                    n_missing += 1
                    continue
                if "sha256" in finfo:
                    current_hash = _file_sha256(fpath)
                    if current_hash == finfo["sha256"]:
                        n_verified += 1
                    else:
                        n_stale += 1

            print(f"    File integrity: {n_verified} verified, {n_stale} stale, {n_missing} missing")
            if n_stale > 0:
                print(f"    ⚠ STALE PROVENANCE: {n_stale} file(s) modified after pipeline run")
            print()

    # Environment snapshot from most recent manifest
    most_recent = max(manifests, key=lambda m: m.get("started_at", ""))
    env = most_recent.get("environment", {})
    if env:
        print("  Environment snapshot:")
        parts = [f"{k}={v}" for k, v in env.items()]
        print(f"    {' | '.join(parts)}")
        print()

    # Data source table — list all input files across manifests
    print("  Data sources (input files across all runs):")
    print(f"    {'Path':<50} {'Rows':>8} {'Checksum':>10}")
    print(f"    {'-'*50} {'-'*8} {'-'*10}")
    seen_inputs = {}
    for m in manifests:
        for finfo in m.get("files", []):
            if finfo.get("role") == "input" and finfo.get("path") not in seen_inputs:
                seen_inputs[finfo["path"]] = finfo
    for path, finfo in sorted(seen_inputs.items()):
        rows = finfo.get("n_rows", "?")
        checksum = finfo.get("sha256", "?")[:8]
        print(f"    {path:<50} {str(rows):>8} {checksum:>10}")
    if not seen_inputs:
        print("    (no input files recorded — scripts may not be instrumented yet)")
    print()

    # Check for untracked parquets
    tracked_outputs = set()
    for m in manifests:
        for finfo in m.get("files", []):
            if finfo.get("role") == "output":
                tracked_outputs.add(finfo.get("path", ""))

    untracked = []
    for d in [DATA_DIR / "processed", DATA_DIR / "results"]:
        if d.exists():
            for p in d.rglob("*.parquet"):
                try:
                    rel = str(p.relative_to(PROJECT_ROOT))
                except ValueError:
                    rel = str(p)
                # Normalize path separators
                rel_norm = rel.replace("\\", "/")
                tracked_norm = {t.replace("\\", "/") for t in tracked_outputs}
                if rel_norm not in tracked_norm:
                    untracked.append(rel)

    if untracked:
        print(f"  Untracked output files ({len(untracked)}):")
        for u in untracked[:10]:
            print(f"    - {u}")
        if len(untracked) > 10:
            print(f"    ... and {len(untracked) - 10} more")
    else:
        print("  All output parquets are tracked in provenance manifests.")
    print()


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="murkml data pipeline audit")
    parser.add_argument("--checks", action="store_true", help="Run validation checks only")
    parser.add_argument("--provenance", action="store_true", help="Run provenance report only")
    args = parser.parse_args()

    run_checks = not args.provenance or args.checks
    run_prov = not args.checks or args.provenance

    if run_checks:
        n_pass, n_fail = run_validation_checks()

    if run_prov:
        run_provenance_report()

    if run_checks and n_fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
