"""QC filtering for USGS continuous sensor data.

Filters based on USGS approval status and qualifier codes.
Uses the NEW API format where approval_status = "Approved" (not "A")
and qualifiers are in a separate column.
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

# Qualifiers that indicate bad/unusable data (case-insensitive matching)
# NOTE: USGS API returns qualifiers as array strings like "['ICE' 'EQUIP']"
# or as comma-separated like "Ice,Eqp". We normalize to uppercase for matching.
#
# ICE/EQUIP/BACKWATER/MAINT: sensor readings are physically compromised
# DRY/DISCONTINUED: no valid measurement
# DEBRIS: sensor obscured
#
# NOT excluded: ESTIMATED (hydrographer-reviewed gap fills — Nair: "may be more
# reliable than raw sensor reading"), REVISED (corrected data)
EXCLUDE_QUALIFIERS = {"ICE", "EQUIP", "EQP", "BACKWATER", "BKW", "MAINT", "MNT",
                       "DISCONTINUED", "UNAVAIL", "DRY", "DEBRIS"}

# Qualifiers to keep even if co-occurring with bad qualifiers
KEEP_QUALIFIERS = {"FLD", "FLOOD"}

# Buffer periods after certain qualifiers end (keys are uppercase for matching)
QUALIFIER_BUFFERS = {
    "ICE": pd.Timedelta(hours=48),   # Bottom ice releases trapped sediment during thaw
    "MAINT": pd.Timedelta(hours=4),  # Freshly cleaned sensor step discontinuity
}


def filter_continuous(
    df: pd.DataFrame,
    approval_col: str = "approval_status",
    qualifier_col: str = "qualifier",
    datetime_col: str = "datetime",
    include_provisional: bool = False,
) -> tuple[pd.DataFrame, dict]:
    """Apply QC filtering to continuous sensor data.

    Rules (from domain expert review):
    - Keep only approval_status = "Approved" (or also "Provisional" if include_provisional=True)
    - Exclude records with qualifiers: Ice, Eqp, Bkw, Mnt, e, ***, --
    - Extend Ice exclusion by 48hr after flag ends (NOT YET IMPLEMENTED — see TODO below)
    - Extend Mnt exclusion by 4hr after flag ends (NOT YET IMPLEMENTED — see TODO below)
    - Keep Fld (flood) data — critical for storm events
    - Qualifier-based QC applies regardless of approval status

    WARNING: If approval_col or qualifier_col are missing from the input DataFrame,
    the corresponding filter is silently SKIPPED (only a log warning is emitted).
    This means unfiltered data passes through without error.

    Args:
        df: Raw continuous data DataFrame.
        approval_col: Column name for approval status.
        qualifier_col: Column name for qualifier codes.
        datetime_col: Column name for datetime.

    Returns:
        Tuple of (filtered DataFrame, stats dict with filter counts).
    """
    n_original = len(df)
    stats = {"n_original": n_original, "approval_filter_applied": False, "qualifier_filter_applied": False}

    if df.empty:
        return df, stats

    # Step 1: Keep only Approved data
    # Normalize USGS abbreviation codes from batch downloads:
    #   "A" -> "Approved", "P" -> "Provisional"
    # Also handle compound codes like "A, R", "A, >", "A, <" (approved + remark)
    if approval_col in df.columns:
        _APPROVAL_MAP = {"A": "Approved", "P": "Provisional"}
        raw_vals = df[approval_col].astype(str).str.strip()
        # Map single-letter codes; for compound codes like "A, R", use first letter
        mapped = raw_vals.map(_APPROVAL_MAP)
        # For compound codes not in map, try first character
        unmapped = mapped.isna() & raw_vals.notna()
        if unmapped.any():
            first_char = raw_vals[unmapped].str.split(",").str[0].str.strip()
            mapped[unmapped] = first_char.map(_APPROVAL_MAP)
        # Only replace values that were actually mapped (preserve "Approved"/"Provisional" as-is)
        already_full = raw_vals.isin({"Approved", "Provisional"})
        df.loc[~already_full, approval_col] = mapped[~already_full].fillna(raw_vals[~already_full])

        if include_provisional:
            mask_approved = df[approval_col].isin(["Approved", "Provisional"])
        else:
            mask_approved = df[approval_col] == "Approved"
        stats["n_not_approved"] = int((~mask_approved).sum())
        stats["n_provisional_included"] = int((df[approval_col] == "Provisional").sum()) if include_provisional else 0
        stats["approval_filter_applied"] = True
        stats["include_provisional"] = include_provisional
        df = df[mask_approved].copy()
    else:
        raise ValueError(
            f"QC filter: expected column '{approval_col}' not found in DataFrame "
            f"(columns: {list(df.columns[:10])}...). Cannot apply approval filter. "
            f"This may indicate a schema change in the upstream data source."
        )

    # Save qualifier + time columns before filtering for buffer detection in Step 3
    # (only the columns we need, not a full DataFrame copy)
    datetime_actual = datetime_col if datetime_col in df.columns else "time"
    if qualifier_col in df.columns and datetime_actual in df.columns:
        _orig_qualifiers = df[qualifier_col].copy()
        _orig_times = pd.to_datetime(df[datetime_actual], utc=True)
    else:
        _orig_qualifiers = None
        _orig_times = None

    # Step 2: Exclude bad qualifiers (vectorized for performance on large datasets)
    if qualifier_col in df.columns:
        def _has_bad_qualifier(val) -> bool:
            """Check if a qualifier value contains any excluded qualifier.

            Handles multiple formats:
            - Array strings from USGS API: "['ICE' 'EQUIP']"
            - Comma-separated: "Ice,Eqp"
            - Single values: "Ice"
            """
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return False
            val_str = str(val).strip()
            if val_str in ("", "None", "nan"):
                return False
            # Parse array string format: "['ICE' 'EQUIP']" -> {"ICE", "EQUIP"}
            cleaned = val_str.strip("[]").replace("'", "").replace('"', '')
            # Split on whitespace or commas
            quals = {q.strip().upper() for q in cleaned.replace(",", " ").split() if q.strip()}
            # Check for exclusions, but preserve KEEP qualifiers
            bad = quals & EXCLUDE_QUALIFIERS
            keep = quals & KEEP_QUALIFIERS
            # If the record has a keep qualifier (e.g., FLOOD), don't exclude
            if keep and not bad:
                return False
            return bool(bad)

        mask_exclude = df[qualifier_col].apply(_has_bad_qualifier)
        stats["n_bad_qualifier"] = int(mask_exclude.sum())
        stats["qualifier_filter_applied"] = True
        df = df[~mask_exclude].copy()
    else:
        raise ValueError(
            f"QC filter: expected column '{qualifier_col}' not found in DataFrame "
            f"(columns: {list(df.columns[:10])}...). Cannot apply qualifier filter. "
            f"This may indicate a schema change in the upstream data source."
        )

    # Step 3: Apply buffer periods after Ice and Mnt flags
    # We use the pre-filter qualifier data to find where Ice/Mnt flags
    # ended, then exclude buffered periods from the post-filtered data.
    stats["n_buffer_excluded"] = 0
    if _orig_qualifiers is not None and datetime_actual in df.columns:
        df_times = pd.to_datetime(df[datetime_actual], utc=True)

        buffer_mask = pd.Series(False, index=df.index)

        for qual_code, buffer_duration in QUALIFIER_BUFFERS.items():
            # Find rows in original data with this qualifier (case-insensitive)
            orig_qual = _orig_qualifiers.astype(str).str.upper()
            flagged_mask = orig_qual.str.contains(qual_code, na=False)
            if not flagged_mask.any():
                continue

            flagged_times = _orig_times[flagged_mask].sort_values()
            if flagged_times.empty:
                continue

            # Find episode end times: where there's a gap > 1hr between
            # consecutive flagged records (i.e., the flag ended)
            time_diffs = flagged_times.diff()
            # Each gap > 1 hour marks the start of a new episode;
            # the record before the gap is the end of the previous episode
            episode_ends = []
            for i in range(1, len(time_diffs)):
                if time_diffs.iloc[i] > pd.Timedelta(hours=1):
                    episode_ends.append(flagged_times.iloc[i - 1])
            # Last flagged record is always an episode end
            episode_ends.append(flagged_times.iloc[-1])

            # Mark records in filtered df that fall within buffer after each episode end
            for end_time in episode_ends:
                in_buffer = (df_times > end_time) & (df_times <= end_time + buffer_duration)
                buffer_mask = buffer_mask | in_buffer

        n_buffered = buffer_mask.sum()
        if n_buffered > 0:
            df = df[~buffer_mask].copy()
            stats["n_buffer_excluded"] = int(n_buffered)
            logger.info(f"  Buffer exclusion: removed {n_buffered} records within post-Ice/Mnt buffer")

    # Step 4: Value-range QC (Fix 8 — Rivera revised)
    if "value" in df.columns:
        n_before_range = len(df)
        value_col = df["value"]
        # Flag but don't exclude turbidity=0 (suspect but not impossible)
        # Hard bounds vary by parameter — caller should specify, but for
        # the common case (turbidity), use generous bounds
        range_mask = (value_col >= -0.01) & (value_col <= 100_000)  # generous default
        df = df[range_mask].copy()
        stats["n_range_excluded"] = n_before_range - len(df)
        if stats["n_range_excluded"] > 0:
            logger.info(f"  Value-range QC: excluded {stats['n_range_excluded']} records")

    stats["n_after_filter"] = len(df)
    stats["pct_retained"] = round(len(df) / max(n_original, 1) * 100, 1)

    logger.info(
        f"QC filter: {n_original} → {len(df)} records "
        f"({stats['pct_retained']}% retained)"
    )

    return df, stats


def deduplicate_discrete(
    df: pd.DataFrame,
    datetime_col: str = "datetime",
    value_col: str = "value",
    org_col: str = "Org_Identifier",
) -> tuple[pd.DataFrame, dict]:
    """Deduplicate discrete samples, resolving conflicts by organization.

    For rows with the same datetime:
    - Identical values: keep first
    - Conflicting values: keep USGS record; if both/neither USGS, keep first

    Args:
        df: Discrete samples DataFrame.
        datetime_col: Column with sample timestamps.
        value_col: Column with measured values.
        org_col: Column with organization identifier.

    Returns:
        Tuple of (deduplicated DataFrame, stats dict).
    """
    n_before = len(df)
    stats = {"n_before": n_before, "n_exact_dupes": 0, "n_conflicts_resolved": 0}

    if df.empty or datetime_col not in df.columns or value_col not in df.columns:
        return df, stats

    # Find duplicate groups by datetime
    dup_mask = df.duplicated(subset=[datetime_col], keep=False)
    n_in_dup_groups = dup_mask.sum()

    if n_in_dup_groups == 0:
        return df, stats

    # Split into unique and duplicate groups
    unique_rows = df[~dup_mask]
    dup_rows = df[dup_mask]

    kept = []
    for dt, group in dup_rows.groupby(datetime_col):
        # Okafor fix: nunique() ignores NaN, so [NaN, 150, 150] looks like
        # "all agree". Prefer non-null rows first, then check uniqueness.
        non_null = group.dropna(subset=[value_col])
        if len(non_null) == 0:
            # All values are NaN — keep first
            kept.append(group.iloc[[0]])
            stats["n_exact_dupes"] += len(group) - 1
        elif non_null[value_col].nunique() <= 1:
            # All non-null values agree — keep first non-null row
            kept.append(non_null.iloc[[0]])
            stats["n_exact_dupes"] += len(group) - 1
        else:
            # Conflicting values — prefer USGS
            if org_col in non_null.columns:
                usgs_mask = non_null[org_col].astype(str).str.contains("USGS", case=False, na=False)
                if usgs_mask.any():
                    kept.append(non_null[usgs_mask].iloc[[0]])
                else:
                    kept.append(non_null.iloc[[0]])
            else:
                kept.append(non_null.iloc[[0]])
            stats["n_conflicts_resolved"] += 1

    result = pd.concat([unique_rows] + kept, ignore_index=True)
    result = result.sort_values(datetime_col).reset_index(drop=True)

    stats["n_after"] = len(result)
    stats["n_removed"] = n_before - len(result)

    if stats["n_removed"] > 0:
        logger.info(
            f"Dedup: {n_before} → {len(result)} "
            f"({stats['n_exact_dupes']} exact dupes, "
            f"{stats['n_conflicts_resolved']} conflicts resolved)"
        )

    return result, stats


def filter_high_censoring(
    df: pd.DataFrame,
    site_col: str = "site_id",
    nondetect_col: str = "is_nondetect",
    threshold: float = 0.5,
) -> tuple[pd.DataFrame, list[str]]:
    """Drop sites with censoring rates above threshold.

    Args:
        df: DataFrame with discrete samples.
        site_col: Column identifying site.
        nondetect_col: Boolean column flagging non-detects.
        threshold: Maximum fraction of non-detects to keep a site (default 0.5 = 50%).

    Returns:
        Tuple of (filtered DataFrame, list of dropped site_ids).
    """
    if df.empty or nondetect_col not in df.columns:
        return df, []

    dropped = []
    for site_id, group in df.groupby(site_col):
        n_nd = group[nondetect_col].sum()
        rate = n_nd / len(group) if len(group) > 0 else 0
        if rate > threshold:
            dropped.append(site_id)
            logger.info(
                f"Dropping {site_id}: {rate:.0%} censored "
                f"({n_nd}/{len(group)}) > {threshold:.0%} threshold"
            )

    if dropped:
        df = df[~df[site_col].isin(dropped)].copy()

    return df, dropped


# Contamination/unreliable result keywords to exclude from discrete data
# Rivera: "Detected Not Quantified" and "Present Above Quantification Limit"
# produce unreliable numeric results in WQP controlled vocabulary
CONTAMINATION_KEYWORDS = [
    "systematic contamination",
    "contamination",
    "detected not quantified",
    "present above quantification limit",
]


def exclude_contamination(
    df: pd.DataFrame,
    detection_col: str = "Result_ResultDetectionCondition",
) -> tuple[pd.DataFrame, int]:
    """Exclude discrete records flagged as contamination.

    Args:
        df: Discrete samples DataFrame.
        detection_col: Column with detection condition text.

    Returns:
        Tuple of (filtered DataFrame, count of excluded rows).
    """
    if df.empty or detection_col not in df.columns:
        return df, 0

    pattern = "|".join(CONTAMINATION_KEYWORDS)
    contam_mask = (
        df[detection_col]
        .astype(str)
        .str.lower()
        .str.contains(pattern, na=False)
    )
    n_excluded = contam_mask.sum()

    if n_excluded > 0:
        logger.info(f"Excluded {n_excluded} contamination-flagged records")
        df = df[~contam_mask].copy()

    return df, n_excluded
