"""
Full pipeline to rebuild the paired dataset with provisional data included.

Reproduces the v11 dataset assembly process:
  Step 1: assemble_dataset.py --include-provisional  (base pairs)
  Step 2: assemble_extreme_sites_fullssc.py --include-provisional  (extreme expansion)
  Step 3: Merge base + extreme, deduplicate
  Step 4: Verify result is a SUPERSET of the approved-only dataset

Does NOT modify the v11 model or split file.
Saves output as turbidity_ssc_paired_with_provisional.parquet (separate file).
"""
import subprocess
import sys
import shutil
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
PYTHON = PROJECT / ".venv" / "Scripts" / "python"
DATA = PROJECT / "data"
PROCESSED = DATA / "processed"

ORIGINAL = PROCESSED / "turbidity_ssc_paired.parquet"
BACKUP = PROCESSED / "turbidity_ssc_paired_v11_approved_only.parquet"
PROVISIONAL_OUT = PROCESSED / "turbidity_ssc_paired_with_provisional.parquet"
EXTREME_OUT = PROCESSED / "extreme_ssc_paired.parquet"


def run(cmd, label):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=str(PROJECT))
    if result.returncode != 0:
        print(f"FAILED: {label} (exit code {result.returncode})")
        sys.exit(1)


def main():
    # Verify backup exists
    if not BACKUP.exists():
        print(f"Backing up original: {ORIGINAL} -> {BACKUP}")
        shutil.copy2(ORIGINAL, BACKUP)

    original = pd.read_parquet(BACKUP)
    print(f"Original v11 dataset: {len(original)} samples, {original['site_id'].nunique()} sites")

    # Step 1: Reassemble base pairs with provisional
    run([str(PYTHON), str(PROJECT / "scripts" / "assemble_dataset.py"), "--include-provisional"],
        "Step 1: Assemble base dataset with provisional")

    base = pd.read_parquet(ORIGINAL)
    print(f"Base with provisional: {len(base)} samples, {base['site_id'].nunique()} sites")

    # Step 2: Reassemble extreme sites with provisional
    run([str(PYTHON), str(PROJECT / "scripts" / "assemble_extreme_sites_fullssc.py"), "--include-provisional"],
        "Step 2: Assemble extreme sites with provisional")

    if EXTREME_OUT.exists():
        extreme = pd.read_parquet(EXTREME_OUT)
        print(f"Extreme with provisional: {len(extreme)} samples, {extreme['site_id'].nunique()} sites")
    else:
        print("WARNING: No extreme_ssc_paired.parquet produced")
        extreme = pd.DataFrame()

    # Step 3: Merge base + extreme
    print(f"\n{'='*60}")
    print(f"  Step 3: Merge base + extreme")
    print(f"{'='*60}")

    if not extreme.empty:
        # Drop suggested_role if present (extreme has it, base doesn't)
        if "suggested_role" in extreme.columns:
            extreme = extreme.drop(columns=["suggested_role"])

        # Align columns
        common_cols = sorted(set(base.columns) & set(extreme.columns))
        merged = pd.concat([base[common_cols], extreme[common_cols]], ignore_index=True)
        n_before_dedup = len(merged)
        merged = merged.drop_duplicates(subset=["site_id", "sample_time"], keep="first")
        n_after_dedup = len(merged)
        print(f"Merged: {n_before_dedup} -> {n_after_dedup} after dedup ({n_before_dedup - n_after_dedup} duplicates)")
    else:
        merged = base

    print(f"Final dataset: {len(merged)} samples, {merged['site_id'].nunique()} sites")

    # Step 4: Verify it's a superset (or at least similar)
    original_sites = set(original["site_id"])
    merged_sites = set(merged["site_id"])
    lost_sites = original_sites - merged_sites
    gained_sites = merged_sites - original_sites

    print(f"\n{'='*60}")
    print(f"  Step 4: Comparison with v11 approved-only")
    print(f"{'='*60}")
    print(f"Samples: {len(original)} -> {len(merged)} ({len(merged) - len(original):+d})")
    print(f"Sites:   {len(original_sites)} -> {len(merged_sites)} ({len(gained_sites)} gained, {len(lost_sites)} lost)")

    if lost_sites:
        print(f"\nWARNING: Lost {len(lost_sites)} sites:")
        for s in sorted(lost_sites):
            n = len(original[original["site_id"] == s])
            print(f"  {s}: {n} samples")

    if gained_sites:
        print(f"\nGained {len(gained_sites)} new sites:")
        for s in sorted(gained_sites):
            n = len(merged[merged["site_id"] == s])
            print(f"  {s}: {n} samples")

    # SSC distribution comparison
    print(f"\nSSC distribution:")
    print(f"  {'':>20} {'Approved-only':>15} {'With-provisional':>18}")
    print(f"  {'Median':>20} {original['lab_value'].median():>15.1f} {merged['lab_value'].median():>18.1f}")
    print(f"  {'P95':>20} {original['lab_value'].quantile(0.95):>15.1f} {merged['lab_value'].quantile(0.95):>18.1f}")
    print(f"  {'P99':>20} {original['lab_value'].quantile(0.99):>15.1f} {merged['lab_value'].quantile(0.99):>18.1f}")
    print(f"  {'Max':>20} {original['lab_value'].max():>15.1f} {merged['lab_value'].max():>18.1f}")
    print(f"  {'SSC > 1000':>20} {(original['lab_value'] > 1000).sum():>15d} {(merged['lab_value'] > 1000).sum():>18d}")
    print(f"  {'SSC > 5000':>20} {(original['lab_value'] > 5000).sum():>15d} {(merged['lab_value'] > 5000).sum():>18d}")

    # Save as SEPARATE file (never overwrite v11)
    merged.to_parquet(PROVISIONAL_OUT, index=False)
    print(f"\nSaved: {PROVISIONAL_OUT} ({PROVISIONAL_OUT.stat().st_size // 1024} KB)")

    # Restore original v11 dataset
    shutil.copy2(BACKUP, ORIGINAL)
    print(f"Restored original v11 dataset: {ORIGINAL}")


if __name__ == "__main__":
    main()
