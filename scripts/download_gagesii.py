"""Download GAGES-II catchment attributes from USGS ScienceBase.

Downloads the basin characteristics zip (~53MB), extracts attribute files,
and joins them into a single parquet keyed by station ID.

Usage:
    python scripts/download_gagesii.py
"""

from __future__ import annotations

import logging
import os
import zipfile
from pathlib import Path

import sys
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from murkml.provenance import start_run, log_step, log_file, end_run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
GAGESII_DIR = DATA_DIR / "gagesii"

# Direct download URL from ScienceBase
BASIN_CHAR_URL = (
    "https://www.sciencebase.gov/catalog/file/get/631405bbd34e36012efa304a"
    "?f=__disk__01/0a/d2/010ad2fb628d42c764b81596fda93f0e86be478c"
)
ZIP_FILENAME = "basinchar_and_report_sept_2011.zip"


def download_zip():
    """Download the GAGES-II basin characteristics zip if not already present."""
    GAGESII_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = GAGESII_DIR / ZIP_FILENAME

    if zip_path.exists():
        logger.info(f"Zip already downloaded: {zip_path} ({zip_path.stat().st_size / 1e6:.1f} MB)")
        return zip_path

    logger.info(f"Downloading GAGES-II basin characteristics (~53 MB)...")
    resp = requests.get(BASIN_CHAR_URL, stream=True, timeout=120)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    with open(zip_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = downloaded / total * 100
                if downloaded % (5 * 1024 * 1024) < 65536:  # Log every ~5MB
                    logger.info(f"  {downloaded / 1e6:.1f} / {total / 1e6:.1f} MB ({pct:.0f}%)")

    logger.info(f"Download complete: {zip_path.stat().st_size / 1e6:.1f} MB")
    return zip_path


def extract_zip(zip_path: Path):
    """Extract the zip file."""
    extract_dir = GAGESII_DIR / "extracted"
    if extract_dir.exists() and any(extract_dir.iterdir()):
        logger.info(f"Already extracted to {extract_dir}")
        return extract_dir

    extract_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Extracting {zip_path.name}...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)
        logger.info(f"Extracted {len(zf.namelist())} files")

    # Also extract nested CSV zip if present
    nested_zip = extract_dir / "spreadsheets-in-csv-format.zip"
    csv_dir = extract_dir / "csv"
    if nested_zip.exists() and not csv_dir.exists():
        csv_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Extracting nested CSV zip...")
        with zipfile.ZipFile(nested_zip, "r") as zf:
            zf.extractall(csv_dir)
            logger.info(f"Extracted {len(zf.namelist())} CSV files")

    return extract_dir


def load_attribute_files(extract_dir: Path) -> pd.DataFrame:
    """Load all GAGES-II attribute files and merge on STAID.

    Prefers CSV files from nested zip, falls back to Excel sheets.
    """
    # Check for extracted CSVs first (from nested zip)
    csv_dir = extract_dir / "csv"
    csv_files = list(csv_dir.rglob("*.csv")) if csv_dir.exists() else []
    txt_files = list(csv_dir.rglob("*.txt")) if csv_dir.exists() else []
    all_tabular = csv_files + txt_files

    if not all_tabular:
        # Fall back to top-level txt files
        all_tabular = [f for f in extract_dir.rglob("*.txt") if "readme" not in f.name.lower()]

    xlsx_files = list(extract_dir.glob("*.xlsx"))
    logger.info(f"Found {len(all_tabular)} CSV/TXT files, {len(xlsx_files)} .xlsx files")

    all_dfs = {}

    # Try CSV/TXT files first
    for f in sorted(all_tabular):
        if any(skip in f.name.lower() for skip in ["readme", "report", "variable_def", "bound_"]):
            continue
        try:
            # Try comma first (CSV), then tab
            try:
                df = pd.read_csv(f, dtype={"STAID": str}, encoding="latin-1")
                if "STAID" not in df.columns:
                    df = pd.read_csv(f, sep="\t", dtype={"STAID": str}, encoding="latin-1")
            except Exception:
                df = pd.read_csv(f, sep="\t", dtype={"STAID": str}, encoding="latin-1")

            if "STAID" in df.columns and len(df) > 100:
                logger.info(f"  Loaded {f.name}: {len(df)} rows, {len(df.columns)} cols")
                all_dfs[f.stem] = df
            else:
                logger.debug(f"  Skipping {f.name} (no STAID or too few rows)")
        except Exception as e:
            logger.warning(f"  Could not read {f.name}: {e}")

    # Fall back to xlsx if no CSVs worked
    if not all_dfs and xlsx_files:
        # Use the conterm (CONUS) file — that's where our sites are
        for xf in xlsx_files:
            if "conterm" in xf.name.lower() or "AKHIPR" not in xf.name:
                try:
                    xl = pd.ExcelFile(xf)
                    logger.info(f"  Excel sheets in {xf.name}: {xl.sheet_names}")
                    for sheet in xl.sheet_names:
                        df = xl.parse(sheet, dtype={"STAID": str})
                        if "STAID" in df.columns and len(df) > 100:
                            logger.info(f"    Sheet '{sheet}': {len(df)} rows, {len(df.columns)} cols")
                            all_dfs[sheet] = df
                except Exception as e:
                    logger.warning(f"  Could not read {xf.name}: {e}")

    if not all_dfs:
        logger.error("No attribute files could be loaded!")
        return pd.DataFrame()

    # Merge all on STAID
    logger.info(f"\nMerging {len(all_dfs)} attribute tables on STAID...")
    merged = None
    for name, df in all_dfs.items():
        if merged is None:
            merged = df
        else:
            # Avoid duplicate columns (except STAID)
            overlap = set(merged.columns) & set(df.columns) - {"STAID"}
            if overlap:
                df = df.drop(columns=list(overlap))
            merged = merged.merge(df, on="STAID", how="outer")

    logger.info(f"Merged result: {len(merged)} sites, {len(merged.columns)} attributes")
    return merged


def match_to_sites(gagesii: pd.DataFrame, site_list: list[str]) -> pd.DataFrame:
    """Match GAGES-II data to our site catalog by station number.

    Handles the fact that GAGES-II STAIDs may be integers (leading zeros stripped)
    while our site IDs are strings like 'USGS-01491000'.
    """
    # Convert STAID to string with zero-padding for comparison
    gagesii = gagesii.copy()
    gagesii["STAID_str"] = gagesii["STAID"].astype(str).str.zfill(8)

    # Our sites: "USGS-XXXXXXXX" -> "XXXXXXXX"
    site_numbers = {}
    for s in site_list:
        num = s.replace("USGS-", "")
        # Pad to 8 digits for standard sites, keep as-is for long IDs
        if len(num) <= 8:
            num_padded = num.zfill(8)
        else:
            num_padded = num
        site_numbers[num_padded] = s

    matched = gagesii[gagesii["STAID_str"].isin(site_numbers.keys())].copy()
    matched["site_id"] = matched["STAID_str"].map(site_numbers)
    matched = matched.drop(columns=["STAID_str"])

    logger.info(f"Matched {len(matched)} of {len(site_list)} sites to GAGES-II")

    unmatched_nums = set(site_numbers.keys()) - set(matched["STAID_str"] if "STAID_str" in matched.columns else [])
    # Re-check unmatched
    matched_padded = set(gagesii["STAID_str"])
    unmatched = {site_numbers[n] for n in site_numbers if n not in matched_padded}
    if unmatched:
        logger.warning(f"Sites NOT in GAGES-II ({len(unmatched)}):")
        for s in sorted(unmatched):
            logger.warning(f"  {s}")

    return matched


def main():
    start_run("download_gagesii")

    # Download and extract
    zip_path = download_zip()
    extract_dir = extract_zip(zip_path)

    # List what we got
    logger.info("\nExtracted contents:")
    for f in sorted(extract_dir.rglob("*")):
        if f.is_file():
            logger.info(f"  {f.relative_to(extract_dir)} ({f.stat().st_size / 1024:.0f} KB)")

    # Load attributes
    gagesii = load_attribute_files(extract_dir)
    if gagesii.empty:
        logger.error("Failed to load GAGES-II attributes")
        return

    # Save full GAGES-II — convert mixed-type columns to string to avoid arrow errors
    full_path = DATA_DIR / "site_attributes_gagesii_full.parquet"
    for col in gagesii.columns:
        if gagesii[col].dtype == object:
            # Check if it's a numeric column with some string values (like 'ND')
            numeric = pd.to_numeric(gagesii[col], errors="coerce")
            non_null_orig = gagesii[col].notna().sum()
            non_null_numeric = numeric.notna().sum()
            # If >80% of non-null values are numeric, keep as numeric
            if non_null_orig > 0 and non_null_numeric / non_null_orig > 0.8:
                gagesii[col] = numeric
            # Otherwise leave as string (will be saved as string in parquet)
    # Fix HUC02: stored as float (1.0, 2.0) — should be zero-padded string ("01", "02")
    if "HUC02" in gagesii.columns:
        gagesii["HUC02"] = (
            gagesii["HUC02"]
            .dropna()
            .astype(int)
            .astype(str)
            .str.zfill(2)
        )
        # Re-fill NaN positions
        gagesii["HUC02"] = gagesii["HUC02"].where(gagesii["HUC02"].notna(), None)
        logger.info(f"Fixed HUC02 dtype: {gagesii['HUC02'].dtype}")

    gagesii.to_parquet(full_path, index=False)
    log_file(full_path, role="output")
    log_step("save_full_gagesii", n_sites=len(gagesii), n_cols=len(gagesii.columns))
    logger.info(f"Saved full GAGES-II: {full_path}")

    # Match to our 57 sites
    assembled = pd.read_parquet(DATA_DIR / "processed" / "turbidity_ssc_paired.parquet")
    our_sites = list(assembled["site_id"].unique())
    matched = match_to_sites(gagesii, our_sites)

    if not matched.empty:
        matched_path = DATA_DIR / "site_attributes_gagesii.parquet"
        matched.to_parquet(matched_path, index=False)
        logger.info(f"Saved matched attributes: {matched_path}")
        logger.info(f"Columns available: {len(matched.columns)}")

        # Show key attribute categories
        cols = matched.columns.tolist()
        logger.info(f"\nSample attributes for first matched site:")
        row = matched.iloc[0]
        for col in cols[:20]:
            logger.info(f"  {col}: {row[col]}")

        log_file(matched_path, role="output")
        log_step("match_to_sites", n_matched=len(matched), n_our_sites=len(our_sites))

    end_run()


if __name__ == "__main__":
    main()
