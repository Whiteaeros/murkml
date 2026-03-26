"""Download StreamCat metrics for missing qualified sites and append to parquet."""
import pandas as pd
import requests
import time
import sys
import os

sys.path.insert(0, os.path.join(os.getcwd(), "src"))

# Load data
cm = pd.read_parquet("data/streamcat/site_comid_mapping.parquet")
q = pd.read_parquet("data/qualified_sites.parquet")
sc = pd.read_parquet("data/site_attributes_streamcat.parquet")

qualified_ids = set(q["site_id"].unique())
streamcat_ids = set(sc["site_id"].unique())
missing = sorted(qualified_ids - streamcat_ids)
print(f"Missing sites: {len(missing)}")

# Get valid COMIDs
missing_cm = cm[cm["site_id"].isin(missing)].copy()
valid_cm = missing_cm[(missing_cm["comid"] != "None") & (missing_cm["comid"].notna())]
print(f"Sites with valid COMID: {len(valid_cm)}")

unique_comids = valid_cm["comid"].unique().tolist()
print(f"Unique COMIDs to fetch: {len(unique_comids)}")

if not unique_comids:
    print("No COMIDs to fetch. Exiting.")
    sys.exit(0)

# StreamCat metrics (same as download_streamcat.py)
STREAMCAT_METRICS = {
    "landcover_2019": [
        "pctdecid2019", "pctconif2019", "pctmxfst2019",
        "pctcrop2019", "pcthay2019",
        "pcturbhi2019", "pcturbmd2019", "pcturblo2019", "pcturbop2019",
        "pctwdwet2019", "pctshrb2019", "pctgrs2019",
        "pctice2019", "pctow2019",
    ],
    "geology": [
        "pctsilicic", "pctcarbresid", "pctnoncarbresid",
        "pctalkintruvol", "pctextruvol",
        "pctglactilloam", "pctglactilclay", "pctglactilcrs",
        "pctglaclakecrs", "pctglaclakefine",
        "pctalluvcoast", "pctcoastcrs", "pcteolcrs", "pcteolfine",
        "pctsallake", "pctwater", "pctcolluvsed", "pcthydric",
    ],
    "geochemistry": ["cao", "sio2", "al2o3", "fe2o3", "mgo", "k2o", "na2o"],
    "soils": ["clay", "sand", "perm", "rckdep", "wtdep", "om", "kffact"],
    "climate_normals": ["precip9120", "tmean9120", "tmax9120", "tmin9120"],
    "topography": ["elev"],
    "hydrology": ["bfi", "runoff", "wetindex"],
    "physical": ["compstrgth", "hydrlcond", "bankfulldepth", "bankfullwidth", "conn"],
    "infrastructure": ["damnidstor", "damdens", "rddens", "popden2010"],
    "point_sources": [
        "npdesdens", "wwtpalldens", "wwtpmajordens", "wwtpminordens",
        "septic", "superfunddens", "coalminedens", "minedens",
    ],
    "nutrient_loading": ["fert", "manure", "nsurp", "pctagdrainage", "cbnf", "rockn"],
    "forest_loss": [f"pctfrstloss{y}" for y in range(2001, 2014)],
    "burn_severity_high": [f"pcthighsev{y}" for y in range(2000, 2019)],
    "impervious_timeseries": [
        f"pctimp{y}" for y in [2001, 2004, 2006, 2008, 2011, 2013, 2016, 2019]
    ],
    "landcover_2001": [
        "pctdecid2001", "pctconif2001", "pctmxfst2001",
        "pctcrop2001", "pcthay2001",
        "pcturbhi2001", "pcturbmd2001", "pcturblo2001", "pcturbop2001",
    ],
    "nitrogen_ag": [f"n_ags_{y}" for y in range(2000, 2018)],
    "phosphorus_ag": [f"p_ags_{y}" for y in range(2000, 2018)],
}

STREAMCAT_API = "https://api.epa.gov/StreamCat/streams/metrics"

# Fetch all metrics
comid_str = ",".join(str(c) for c in unique_comids)
all_metrics = pd.DataFrame({"comid": [str(c) for c in unique_comids]})

for category, metric_names in STREAMCAT_METRICS.items():
    metric_str = ",".join(metric_names)
    print(f"\nFetching {category} ({len(metric_names)} metrics)...")

    for attempt in range(3):
        try:
            resp = requests.get(
                STREAMCAT_API,
                params={"comid": comid_str, "name": metric_str, "aoi": "ws"},
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                print(f"  Got {len(items)} results")
                if items:
                    cat_df = pd.DataFrame(items)
                    cat_df.columns = [c.lower() for c in cat_df.columns]
                    cat_df["comid"] = cat_df["comid"].astype(str)
                    new_cols = [c for c in cat_df.columns if c not in all_metrics.columns]
                    if new_cols:
                        all_metrics = all_metrics.merge(
                            cat_df[["comid"] + new_cols], on="comid", how="left"
                        )
                break
            elif resp.status_code == 429:
                wait = 2 ** attempt * 10
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"  HTTP {resp.status_code}: {resp.text[:200]}")
                break
        except Exception as e:
            print(f"  Error: {e}")
            if attempt < 2:
                time.sleep(3)

    time.sleep(1)

print(f"\nRaw metrics shape: {all_metrics.shape}")

# Save raw intermediate
all_metrics.to_parquet("data/streamcat/missing_raw_metrics.parquet", index=False)
print("Saved raw metrics intermediate")

# ── Apply map_to_internal_schema (exact copy from download_streamcat.py) ──
raw = all_metrics.copy()
raw.columns = [c.lower() for c in raw.columns]

mapped = pd.DataFrame()
mapped["comid"] = raw.get("comid")
mapped["drainage_area_km2"] = raw.get("wsareasqkm")

# Land cover
mapped["forest_pct"] = (
    raw.get("pctdecid2019ws", pd.Series(0, index=raw.index)).fillna(0)
    + raw.get("pctconif2019ws", pd.Series(0, index=raw.index)).fillna(0)
    + raw.get("pctmxfst2019ws", pd.Series(0, index=raw.index)).fillna(0)
)
mapped["agriculture_pct"] = (
    raw.get("pctcrop2019ws", pd.Series(0, index=raw.index)).fillna(0)
    + raw.get("pcthay2019ws", pd.Series(0, index=raw.index)).fillna(0)
)
mapped["developed_pct"] = (
    raw.get("pcturbhi2019ws", pd.Series(0, index=raw.index)).fillna(0)
    + raw.get("pcturbmd2019ws", pd.Series(0, index=raw.index)).fillna(0)
    + raw.get("pcturblo2019ws", pd.Series(0, index=raw.index)).fillna(0)
    + raw.get("pcturbop2019ws", pd.Series(0, index=raw.index)).fillna(0)
)
mapped["wetland_pct"] = raw.get("pctwdwet2019ws")
mapped["shrub_pct"] = raw.get("pctshrb2019ws")
mapped["grass_pct"] = raw.get("pctgrs2019ws")

# Geology
geology_cols = {
    "pctsilicicws": "pct_siliciclastic",
    "pctcarbresidws": "pct_carbonate_resid",
    "pctnoncarbresidws": "pct_nonite_resid",
    "pctalkintruvolws": "pct_alkaline_intrusive",
    "pctextruvolws": "pct_extrusive_volcanic",
    "pctglactilloamws": "pct_glacial_till_loam",
    "pctglactilclayws": "pct_glacial_till_clay",
    "pctglactilcrsws": "pct_glacial_till_coarse",
    "pctglaclakecrsws": "pct_glacial_lake_coarse",
    "pctglaclakefinews": "pct_glacial_lake_fine",
    "pctalluvcoastws": "pct_alluvial_coastal",
    "pctcoastcrsws": "pct_coastal_coarse",
    "pcteolcrsws": "pct_eolian_coarse",
    "pcteolfinews": "pct_eolian_fine",
    "pctsallakews": "pct_saline_lake",
    "pctwaterws": "pct_water_geology",
    "pctcolluvsedws": "pct_colluvial_sediment",
    "pcthydricws": "pct_hydric",
}
for sc_col, internal_col in geology_cols.items():
    mapped[internal_col] = raw.get(sc_col)

geol_pct_cols = [c for c in geology_cols.values() if c in mapped.columns]
if geol_pct_cols:
    geol_subset = mapped[geol_pct_cols].fillna(0)
    mapped["geol_class"] = geol_subset.idxmax(axis=1).str.replace("pct_", "")
    mapped.loc[geol_subset.sum(axis=1) == 0, "geol_class"] = None

# Geochemistry
geochem_cols = {
    "caows": "geo_cao", "sio2ws": "geo_sio2", "al2o3ws": "geo_al2o3",
    "fe2o3ws": "geo_fe2o3", "mgows": "geo_mgo", "k2ows": "geo_k2o",
    "na2ows": "geo_na2o",
}
for sc_col, internal_col in geochem_cols.items():
    mapped[internal_col] = raw.get(sc_col)

# Soils
mapped["clay_pct"] = raw.get("clayws")
mapped["sand_pct"] = raw.get("sandws")
mapped["soil_permeability"] = raw.get("permws")
mapped["soil_rock_depth"] = raw.get("rckdepws")
mapped["water_table_depth"] = raw.get("wtdepws")
mapped["soil_organic_matter"] = raw.get("omws")
mapped["soil_erodibility"] = raw.get("kffactws")

# Climate
mapped["precip_mean_mm"] = raw.get("precip9120ws")
mapped["temp_mean_c"] = raw.get("tmean9120ws")

# Topography
mapped["elevation_m"] = raw.get("elevws")

# Hydrology
mapped["baseflow_index"] = raw.get("bfiws")
mapped["runoff_mean"] = raw.get("runoffws")
mapped["wetness_index"] = raw.get("wetindexws")

# Infrastructure
mapped["dam_storage_density"] = raw.get("damnidstorws")
mapped["dam_density"] = raw.get("damdensws")
mapped["road_density"] = raw.get("rddensws")
mapped["pop_density"] = raw.get("popden2010ws")

# Point sources
mapped["npdes_density"] = raw.get("npdesdensws")
mapped["wwtp_all_density"] = raw.get("wwtpalldensws")
mapped["wwtp_major_density"] = raw.get("wwtpmajordensws")
mapped["wwtp_minor_density"] = raw.get("wwtpminordensws")
mapped["septic_density"] = raw.get("septicws")
mapped["superfund_density"] = raw.get("superfunddensws")
mapped["coalmine_density"] = raw.get("coalminedensws")
mapped["mine_density"] = raw.get("minedensws")

# Nutrient loading
mapped["fertilizer_rate"] = raw.get("fertws")
mapped["manure_rate"] = raw.get("manurews")
mapped["nitrogen_surplus"] = raw.get("nsurpws")
mapped["ag_drainage_pct"] = raw.get("pctagdrainagews")
mapped["bio_n_fixation"] = raw.get("cbnfws")
mapped["rock_nitrogen"] = raw.get("rocknws")

# Physical
mapped["compressive_strength"] = raw.get("compstrgthws")
mapped["hydraulic_conductivity"] = raw.get("hydrlcondws")
mapped["bankfull_depth"] = raw.get("bankfulldepthws")
mapped["bankfull_width"] = raw.get("bankfullwidthws")
mapped["hydrologic_connectivity"] = raw.get("connws")

# Time-varying: forest loss
for y in range(2001, 2014):
    col = f"pctfrstloss{y}ws"
    if col in raw.columns:
        mapped[f"forest_loss_{y}"] = raw[col]

# Time-varying: high-severity burn
for y in range(2000, 2019):
    col = f"pcthighsev{y}ws"
    if col in raw.columns:
        mapped[f"burn_highsev_{y}"] = raw[col]

# Time-varying: impervious surface
for y in [2001, 2004, 2006, 2008, 2011, 2013, 2016, 2019]:
    col = f"pctimp{y}ws"
    if col in raw.columns:
        mapped[f"impervious_{y}"] = raw[col]

# Time-varying: land cover 2001
for nlcd_type in [
    "pctdecid", "pctconif", "pctmxfst", "pctcrop", "pcthay",
    "pcturbhi", "pcturbmd", "pcturblo", "pcturbop",
]:
    col_2001 = f"{nlcd_type}2001ws"
    if col_2001 in raw.columns:
        mapped[f"{nlcd_type}_2001"] = raw[col_2001]

# Time-varying: nitrogen and phosphorus
for y in range(2000, 2018):
    n_col = f"n_ags_{y}ws"
    p_col = f"p_ags_{y}ws"
    if n_col in raw.columns:
        mapped[f"n_ag_{y}"] = raw[n_col]
    if p_col in raw.columns:
        mapped[f"p_ag_{y}"] = raw[p_col]

print(f"\nMapped columns: {len(mapped.columns)}")

# ── Map COMID -> site_id and expand ──
comid_to_sites = valid_cm.groupby("comid")["site_id"].apply(list).to_dict()

rows = []
for _, row in mapped.iterrows():
    comid = str(row["comid"])
    site_ids = comid_to_sites.get(comid, [])
    for sid in site_ids:
        new_row = row.copy()
        new_row["site_id"] = sid
        rows.append(new_row)

mapped_expanded = pd.DataFrame(rows)
mapped_expanded = mapped_expanded.drop(columns=["comid"], errors="ignore")

cols = ["site_id"] + [c for c in mapped_expanded.columns if c != "site_id"]
mapped_expanded = mapped_expanded[cols]

print(f"Expanded rows (one per site): {len(mapped_expanded)}")
print(f"Sites covered: {mapped_expanded['site_id'].unique().tolist()}")

# ── Align columns with existing file and append ──
existing = pd.read_parquet("data/site_attributes_streamcat.parquet")
existing_cols = set(existing.columns)
new_cols_set = set(mapped_expanded.columns)

for col in existing_cols - new_cols_set:
    mapped_expanded[col] = None
for col in new_cols_set - existing_cols:
    existing[col] = None

all_cols = existing.columns.tolist()
for c in mapped_expanded.columns:
    if c not in all_cols:
        all_cols.append(c)

mapped_expanded = mapped_expanded.reindex(columns=all_cols)

combined = pd.concat([existing, mapped_expanded], ignore_index=True)
combined = combined.drop_duplicates(subset=["site_id"], keep="last")

print(f"\nExisting rows: {len(existing)}")
print(f"New rows added: {len(mapped_expanded)}")
print(f"Combined rows: {len(combined)}")
print(f"Unique site_ids: {combined['site_id'].nunique()}")

# Verify
for sid in mapped_expanded["site_id"].unique():
    in_combined = sid in combined["site_id"].values
    print(f"  {sid}: {'OK' if in_combined else 'MISSING'}")

# Spot check: verify values are not all NaN for a new site
sample_site = mapped_expanded["site_id"].iloc[0]
sample_row = combined[combined["site_id"] == sample_site].iloc[0]
n_non_null = sample_row.drop("site_id").notna().sum()
print(f"\nSpot check {sample_site}: {n_non_null} non-null values out of {len(sample_row) - 1}")

# Save
combined.to_parquet("data/site_attributes_streamcat.parquet", index=False)
print(f"\nSaved to data/site_attributes_streamcat.parquet")
print(f"Final shape: {combined.shape}")

# Report the 43 sites without StreamCat data
no_streamcat = sorted(set(missing) - set(mapped_expanded["site_id"].unique()))
print(f"\n{len(no_streamcat)} sites could NOT get StreamCat data (no NHDPlus COMID):")
for s in no_streamcat:
    print(f"  {s}")
