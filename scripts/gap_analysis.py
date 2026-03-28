"""Analyze how much more paired data we could get by downloading additional turbidity years."""

import pandas as pd
import numpy as np
import os

MURKML = "c:/Users/kaleb/Documents/murkml"

# Load core data
qs = pd.read_parquet(f"{MURKML}/data/qualified_sites.parquet")
paired = pd.read_parquet(f"{MURKML}/data/processed/turbidity_ssc_paired.parquet")
paired_site_ids = set(paired["site_id"].unique())

print(f"Qualified sites: {len(qs)}")
print(f"Paired sites: {len(paired_site_ids)}")
print(f"Unpaired sites: {len(qs) - len(qs[qs['site_id'].isin(paired_site_ids)])}")


def get_continuous_turb_range(site_id):
    """Get actual min/max dates from continuous turbidity parquet files."""
    dir_name = site_id.replace("-", "_")
    turb_dir = f"{MURKML}/data/continuous/{dir_name}/63680/"
    if not os.path.isdir(turb_dir):
        return None, None

    files = [f for f in os.listdir(turb_dir) if f.endswith(".parquet")]
    if not files:
        return None, None

    min_time = None
    max_time = None
    for f in files:
        try:
            df = pd.read_parquet(os.path.join(turb_dir, f), columns=["time"])
            if len(df) > 0:
                fmin = df["time"].min()
                fmax = df["time"].max()
                if min_time is None or fmin < min_time:
                    min_time = fmin
                if max_time is None or fmax > max_time:
                    max_time = fmax
        except Exception:
            pass
    return min_time, max_time


def get_ssc_dates(site_id):
    """Get all SSC sample dates from discrete parquet."""
    dir_name = site_id.replace("-", "_")
    ssc_file = f"{MURKML}/data/discrete/{dir_name}_ssc.parquet"
    if not os.path.isfile(ssc_file):
        return pd.Series(dtype="datetime64[ns, UTC]"), 0

    df = pd.read_parquet(ssc_file)
    if "ActivityStartDate" in df.columns:
        dates = pd.to_datetime(df["ActivityStartDate"], errors="coerce")
        if dates.dt.tz is None:
            dates = dates.dt.tz_localize("UTC")
        return dates.dropna(), len(df)
    return pd.Series(dtype="datetime64[ns, UTC]"), len(df)


# Process all 413 qualified sites
results = []
print("Processing sites...")
for idx, row in qs.iterrows():
    sid = row["site_id"]

    turb_min, turb_max = get_continuous_turb_range(sid)
    ssc_dates, n_ssc_total = get_ssc_dates(sid)
    n_ssc_valid = len(ssc_dates)

    if n_ssc_valid == 0:
        results.append({
            "site_id": sid,
            "ssc_start": pd.NaT,
            "ssc_end": pd.NaT,
            "n_ssc_samples": 0,
            "turb_start": turb_min,
            "turb_end": turb_max,
            "has_turb_data": turb_min is not None,
            "ssc_before_turb": 0,
            "ssc_after_turb": 0,
            "ssc_outside_turb": 0,
            "ssc_inside_turb": 0,
            "is_paired": sid in paired_site_ids,
            "years_to_download_before": "",
            "years_to_download_after": "",
        })
        continue

    ssc_min = ssc_dates.min()
    ssc_max = ssc_dates.max()

    if turb_min is not None:
        if turb_min.tzinfo is None:
            turb_min_tz = turb_min.tz_localize("UTC")
            turb_max_tz = turb_max.tz_localize("UTC")
        else:
            turb_min_tz = turb_min
            turb_max_tz = turb_max

        before = int((ssc_dates < turb_min_tz).sum())
        after = int((ssc_dates > turb_max_tz).sum())
        inside = n_ssc_valid - before - after
        outside = before + after

        if before > 0:
            earliest_ssc = ssc_dates[ssc_dates < turb_min_tz].min()
            yrs_before = f"{earliest_ssc.year}-{turb_min_tz.year}"
        else:
            yrs_before = ""

        if after > 0:
            latest_ssc = ssc_dates[ssc_dates > turb_max_tz].max()
            yrs_after = f"{turb_max_tz.year}-{latest_ssc.year}"
        else:
            yrs_after = ""
    else:
        before = n_ssc_valid
        after = 0
        inside = 0
        outside = n_ssc_valid
        yrs_before = f"{ssc_min.year}-{ssc_max.year}" if n_ssc_valid > 0 else ""
        yrs_after = ""

    results.append({
        "site_id": sid,
        "ssc_start": ssc_min,
        "ssc_end": ssc_max,
        "n_ssc_samples": n_ssc_valid,
        "turb_start": turb_min,
        "turb_end": turb_max,
        "has_turb_data": turb_min is not None,
        "ssc_before_turb": before,
        "ssc_after_turb": after,
        "ssc_outside_turb": outside,
        "ssc_inside_turb": inside,
        "is_paired": sid in paired_site_ids,
        "years_to_download_before": yrs_before,
        "years_to_download_after": yrs_after,
    })

rdf = pd.DataFrame(results)

# ── Summary stats ──
print("\n" + "=" * 70)
print("SUMMARY: DATA GAP ANALYSIS FOR 413 QUALIFIED SITES")
print("=" * 70)

paired_mask = rdf["is_paired"]
unpaired_mask = ~rdf["is_paired"]

print(f"\n--- PAIRED SITES ({paired_mask.sum()}) ---")
p = rdf[paired_mask]
print(f"Total SSC samples across all paired sites: {p['n_ssc_samples'].sum()}")
print(f"SSC samples INSIDE turbidity coverage:     {p['ssc_inside_turb'].sum()}")
print(f"SSC samples OUTSIDE turbidity coverage:    {p['ssc_outside_turb'].sum()}")
print(f"  - Before turb start: {p['ssc_before_turb'].sum()}")
print(f"  - After turb end:    {p['ssc_after_turb'].sum()}")
total_ssc = p["n_ssc_samples"].sum()
pct = p["ssc_outside_turb"].sum() / total_ssc * 100 if total_ssc > 0 else 0
print(f"Percentage outside:    {pct:.1f}%")
print(f"Sites with >0 outside: {(p['ssc_outside_turb'] > 0).sum()}")

# Current pairing rate
n_actual_pairs = len(paired)
inside_total = p["ssc_inside_turb"].sum()
print(f"\nCurrent paired samples: {n_actual_pairs}")
if inside_total > 0:
    pairing_rate = n_actual_pairs / inside_total
    print(f"Current pairing rate:   {pairing_rate:.1%} of SSC inside turb window")
else:
    pairing_rate = 0.6

outside_total = p["ssc_outside_turb"].sum()
expected_new = int(outside_total * pairing_rate)
print(f"Expected new pairs at same rate: ~{expected_new}")

print(f"\n--- UNPAIRED SITES ({unpaired_mask.sum()}) ---")
u = rdf[unpaired_mask]
print(f"Sites with SSC data:        {(u['n_ssc_samples'] > 0).sum()}")
print(f"Sites with turb data:       {u['has_turb_data'].sum()}")
print(f"Sites with both:            {((u['n_ssc_samples'] > 0) & u['has_turb_data']).sum()}")
print(f"Sites with SSC but no turb: {((u['n_ssc_samples'] > 0) & ~u['has_turb_data']).sum()}")
print(f"Total SSC samples:          {u['n_ssc_samples'].sum()}")
print(f"SSC samples outside turb:   {u['ssc_outside_turb'].sum()}")

# Unpaired detail
unpaired_with_data = u[(u["n_ssc_samples"] > 0)].sort_values("n_ssc_samples", ascending=False)
if len(unpaired_with_data) > 0:
    print(f"\nUnpaired sites with SSC data:")
    for _, r in unpaired_with_data.head(15).iterrows():
        turb_tag = "HAS TURB" if r["has_turb_data"] else "NO TURB"
        print(f"  {r['site_id']:20s}  ssc={r['n_ssc_samples']:4d}  outside={r['ssc_outside_turb']:4d}  [{turb_tag}]")

print(f"\n--- TOP 25 SITES BY SSC OUTSIDE COVERAGE ---")
top25 = rdf.nlargest(25, "ssc_outside_turb")
for _, r in top25.iterrows():
    tag = "PAIRED" if r["is_paired"] else "UNPAIRED"
    turb_range = ""
    if r["has_turb_data"]:
        turb_range = f"turb={str(r['turb_start'])[:10]}..{str(r['turb_end'])[:10]}"
    print(
        f"  {r['site_id']:20s}  outside={r['ssc_outside_turb']:4d}  "
        f"inside={r['ssc_inside_turb']:4d}  total={r['n_ssc_samples']:4d}  "
        f"[{tag}]  {turb_range}"
    )


# Calculate download site-years
def calc_site_years(row):
    years = 0
    for col in ["years_to_download_before", "years_to_download_after"]:
        val = row[col]
        if val and "-" in val:
            parts = val.split("-")
            if len(parts) == 2:
                try:
                    years += max(0, int(parts[1]) - int(parts[0]))
                except ValueError:
                    pass
    return years


rdf["site_years_needed"] = rdf.apply(calc_site_years, axis=1)

print(f"\n--- DOWNLOAD ESTIMATE ---")
sites_needing_dl = rdf[rdf["ssc_outside_turb"] > 0]
print(f"Sites needing additional downloads: {len(sites_needing_dl)}")
print(f"Total site-years to download:       {rdf['site_years_needed'].sum()}")
grand_outside = rdf["ssc_outside_turb"].sum()
print(f"Total SSC samples outside (all):    {grand_outside}")
print(f"Expected new pairs (50%):           ~{int(grand_outside * 0.5)}")
print(f"Expected new pairs (at {pairing_rate:.0%} rate):   ~{int(grand_outside * pairing_rate)}")
print(f"Current total pairs:                {n_actual_pairs}")
print(f"Potential increase:                 {int(grand_outside * pairing_rate) / n_actual_pairs * 100:.0f}%")

# Distribution
print(f"\n--- DISTRIBUTION OF OUTSIDE SAMPLES (ALL SITES) ---")
bins = [0, 1, 5, 10, 20, 50, 100, 500, 10000]
labels = ["0", "1-4", "5-9", "10-19", "20-49", "50-99", "100-499", "500+"]
cut = pd.cut(rdf["ssc_outside_turb"], bins=bins, labels=labels, right=False)
dist = cut.value_counts().sort_index()
for label, count in dist.items():
    print(f"  {label:10s}: {count:4d} sites")

# Save output
output = rdf.sort_values("ssc_outside_turb", ascending=False).copy()
output.to_parquet(f"{MURKML}/data/download_gaps.parquet", index=False)
print(f"\nSaved: {MURKML}/data/download_gaps.parquet ({len(output)} rows)")

# Also save CSV for easy inspection
output.to_csv(f"{MURKML}/data/download_gaps.csv", index=False)
print(f"Saved: {MURKML}/data/download_gaps.csv")
