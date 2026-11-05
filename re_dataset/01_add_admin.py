"""
Step 1 - Add governorate / district / sub-district (adm3) to the facilities CSV.

Method
------
For every facility point (longitude, latitude):
  1. Point-in-polygon join against each boundary layer ("within").
  2. If no polygon contains the point (coast, border slivers, slightly-off
     coordinates) -> nearest polygon, but only if it is closer than --max-dist metres
     ("nearest"). Otherwise the level stays empty ("none").
  3. Hierarchy check: a district must belong to the matched governorate and an
     adm3 unit to the matched district (compared by pcode). If not, the point is
     re-matched to the nearest polygon *inside the correct parent*.

Output columns (added to the original ones)
-------------------------------------------
  governorate_en / _ar / _pcode      admin_match_gov
  district_en    / _ar / _pcode      admin_match_district
  subdistrict_en / _ar / _pcode      admin_match_subdistrict
admin_match_* is one of: within | nearest | none

Usage
-----
  python 01_add_admin.py
(paths are set at the top of the script; every one can be overridden with --input/--output etc.)
"""
import argparse
import os
import sys

import geopandas as gpd
import numpy as np
import pandas as pd

# ----- paths (edit here if you move things) ------------------------------- #
DATA_DIR = r"D:\intelligent-maternal-care-navigation\re_dataset\medical_facilities"
RAW_CSV = os.path.join(DATA_DIR, "egypt_medical_facilities.csv")
ADMIN_CSV = os.path.join(DATA_DIR, "egypt_medical_facilities_admin.csv")
CLEAN_CSV = os.path.join(DATA_DIR, "egypt_medical_facilities_clean.csv")
FINAL_DIR = os.path.join(DATA_DIR, "final")
BOUNDARIES_DIR = r"D:\intelligent-maternal-care-navigation\boundaries_data\processed"
# --------------------------------------------------------------------------- #

METRIC_CRS = "EPSG:32636"  # UTM zone 36N - fine for distances anywhere in Egypt


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def load_layer(path, level):
    """Read a boundary layer and standardise its attribute names.

    level: 'adm1' | 'adm2' | 'adm3'. Property names are detected by prefix so the
    script still works if the adm3 file uses slightly different field names.
    """
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.to_crs("EPSG:4326")

    cols = {c.lower(): c for c in gdf.columns}

    def pick(*candidates):
        for cand in candidates:
            if cand in cols:
                return cols[cand]
        return None

    name_en = pick(f"{level}_name", f"{level}_ref_name")
    name_ar = pick(f"{level}_name1")
    pcode = pick(f"{level}_pcode")
    if name_en is None or pcode is None:
        sys.exit(f"[{path}] cannot find '{level}_name' / '{level}_pcode'. "
                 f"Columns are: {list(gdf.columns)}")

    out = pd.DataFrame({
        "name_en": gdf[name_en],
        "name_ar": gdf[name_ar] if name_ar else None,
        "pcode": gdf[pcode],
    })
    # parent pcodes (adm2 -> adm1, adm3 -> adm2) when present
    parent_level = {"adm2": "adm1", "adm3": "adm2"}.get(level)
    out["parent_pcode"] = gdf[pick(f"{parent_level}_pcode")] if parent_level and pick(f"{parent_level}_pcode") else None
    out["geometry"] = gdf.geometry

    out = gpd.GeoDataFrame(out, geometry="geometry", crs="EPSG:4326")
    out["geometry"] = out.geometry.make_valid()  # repair self-intersections
    out = out[~out.geometry.is_empty].reset_index(drop=True)
    return out.to_crs(METRIC_CRS)


def match_level(pts, polys, max_dist, parent_codes=None):
    """Return a Series of polygon row-index per point + a Series of match method.

    pts           GeoDataFrame (metric CRS), index = facility index
    polys         GeoDataFrame from load_layer (metric CRS)
    parent_codes  optional Series (index = facility index) with the pcode the
                  chosen polygon must belong to; polys needs 'parent_pcode'.
    """
    poly_idx = pd.Series(np.nan, index=pts.index, dtype="float64")
    method = pd.Series("none", index=pts.index, dtype="object")

    # 1) point-in-polygon
    j = gpd.sjoin(pts[["geometry"]], polys[["geometry"]], how="left", predicate="within")
    j = j[~j.index.duplicated(keep="first")]  # overlapping polygons -> first one
    hit = j["index_right"].notna()
    poly_idx[hit] = j.loc[hit, "index_right"]
    method[hit] = "within"

    # 2) rows that need (re)matching: nothing found, or wrong parent
    redo = poly_idx.isna()
    if parent_codes is not None and polys["parent_pcode"].notna().any():
        have_parent = parent_codes.notna() & poly_idx.notna()
        chosen_parent = poly_idx[have_parent].astype(int).map(polys["parent_pcode"])
        wrong = chosen_parent[chosen_parent != parent_codes[have_parent]].index
        redo.loc[wrong] = True
        poly_idx.loc[wrong] = np.nan
        method.loc[wrong] = "none"

    if redo.any():
        todo = pts.loc[redo, ["geometry"]]
        if parent_codes is not None and polys["parent_pcode"].notna().any():
            groups = parent_codes[redo].fillna("__none__")
        else:
            groups = pd.Series("__all__", index=todo.index)

        for parent, idx in groups.groupby(groups).groups.items():
            cand = polys if parent in ("__all__", "__none__") else polys[polys["parent_pcode"] == parent]
            if cand.empty:
                cand = polys  # parent code unknown to this layer -> don't leave blank
            n = gpd.sjoin_nearest(todo.loc[idx], cand[["geometry"]], how="left",
                                  max_distance=max_dist, distance_col="_dist")
            n = n[~n.index.duplicated(keep="first")]
            ok = n["index_right"].notna()
            poly_idx.loc[n.index[ok]] = n.loc[ok, "index_right"]
            method.loc[n.index[ok]] = "nearest"

    return poly_idx, method


def attach(df, level_name, polys, poly_idx, method):
    """Write the matched polygon's attributes into df."""
    ok = poly_idx.notna()
    pi = poly_idx[ok].astype(int)
    for src, dst in (("name_en", "en"), ("name_ar", "ar"), ("pcode", "pcode")):
        col = f"{level_name}_{dst}"
        df[col] = pd.Series(pd.NA, index=df.index, dtype="object")
        df.loc[ok, col] = polys.loc[pi.values, src].values
    df[f"admin_match_{level_name}"] = method


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=RAW_CSV)
    ap.add_argument("--gov", default=os.path.join(BOUNDARIES_DIR, "egypt_governorates.geojson"))
    ap.add_argument("--districts", default=os.path.join(BOUNDARIES_DIR, "egypt_districts.geojson"))
    ap.add_argument("--adm3", default=os.path.join(BOUNDARIES_DIR, "egypt_adm3.geojson"))
    ap.add_argument("--output", default=ADMIN_CSV)
    ap.add_argument("--max-dist", type=float, default=3000,
                    help="max metres for the nearest-polygon fallback (default 3000)")
    a = ap.parse_args()

    df = pd.read_csv(a.input, low_memory=False)
    print(f"Loaded {len(df):,} facilities")

    bad = df["latitude"].isna() | df["longitude"].isna()
    if bad.any():
        print(f"  WARNING: {bad.sum()} rows without coordinates -> admin columns stay empty")
    pts = gpd.GeoDataFrame(
        df.loc[~bad, []],
        geometry=gpd.points_from_xy(df.loc[~bad, "longitude"], df.loc[~bad, "latitude"]),
        crs="EPSG:4326",
    ).to_crs(METRIC_CRS)

    print("Loading boundaries ...")
    gov = load_layer(a.gov, "adm1")
    dist = load_layer(a.districts, "adm2")
    sub = load_layer(a.adm3, "adm3")
    print(f"  governorates={len(gov)}  districts={len(dist)}  adm3={len(sub)}")

    # governorate
    g_idx, g_m = match_level(pts, gov, a.max_dist)
    attach(df, "governorate", gov, g_idx.reindex(df.index), g_m.reindex(df.index).fillna("none"))

    # district (must sit inside the matched governorate)
    d_idx, d_m = match_level(pts, dist, a.max_dist,
                             parent_codes=df.loc[pts.index, "governorate_pcode"])
    attach(df, "district", dist, d_idx.reindex(df.index), d_m.reindex(df.index).fillna("none"))

    # adm3 (must sit inside the matched district)
    s_idx, s_m = match_level(pts, sub, a.max_dist,
                             parent_codes=df.loc[pts.index, "district_pcode"])
    attach(df, "subdistrict", sub, s_idx.reindex(df.index), s_m.reindex(df.index).fillna("none"))

    # fill missing governorate from the district's parent if the gov layer missed it
    miss = df["governorate_pcode"].isna() & df["district_pcode"].notna()
    if miss.any():
        lookup = gov.set_index("pcode")
        par = dist.set_index("pcode")["parent_pcode"]
        for i in df.index[miss]:
            pc = par.get(df.at[i, "district_pcode"])
            if pc in lookup.index:
                df.at[i, "governorate_pcode"] = pc
                df.at[i, "governorate_en"] = lookup.at[pc, "name_en"]
                df.at[i, "governorate_ar"] = lookup.at[pc, "name_ar"]
                df.at[i, "admin_match_governorate"] = "from_district"

    df.to_csv(a.output, index=False, encoding="utf-8-sig")

    print("\nMatch summary")
    for lvl in ("governorate", "district", "subdistrict"):
        print(f"  {lvl:12s}", df[f"admin_match_{lvl}"].value_counts().to_dict())
    print("\nFacilities per governorate:")
    print(df["governorate_en"].fillna("<unmatched>").value_counts().to_string())
    print(f"\nSaved -> {a.output}")


if __name__ == "__main__":
    main()
