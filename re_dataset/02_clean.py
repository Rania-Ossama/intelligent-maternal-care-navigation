"""
Step 2 - Clean the facilities CSV (output of 01_add_admin.py).

What it does
------------
* drops empty / constant / technical / duplicate columns
* merges phone+contact_phone+mobile, email+contact_email, website+contact_website
* builds name, name_ar, name_en (filling gaps from each other), keeps unnamed rows
  and flags them (missing_name)
* builds address_osm and full_address (OSM address parts + official admin names)
* recovers real OSM dates (the source stored seconds as nanoseconds)
* rescues a few useful keys from the all_tags JSON (alt_name, facebook, ...)
* flags (does NOT delete) likely duplicates: same name + type within 100 m
* normalises phone numbers to +20 format, yes/no fields, facility_type spelling

Usage
-----
  python 02_clean.py
(paths are set at the top of the script; every one can be overridden with --input/--output etc.)
"""
import argparse
import os
import json
import re

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

ARABIC = re.compile(r"[\u0600-\u06FF]")
LATIN = re.compile(r"[A-Za-z]")

FACILITY_TYPE_MAP = {
    "center": "centre",
    "مركز_صحي": "health_centre",
}

# Final column order (any column not listed is appended at the end)
COLUMN_ORDER = [
    "osm_id", "osm_type", "facility_type",
    "name", "name_ar", "name_en", "alt_name", "brand", "operator", "operator_type",
    "missing_name",
    "latitude", "longitude",
    "governorate_en", "governorate_ar", "governorate_pcode",
    "district_en", "district_ar", "district_pcode",
    "subdistrict_en", "subdistrict_ar", "subdistrict_pcode",
    "full_address", "full_address_ar", "address_osm", "postcode",
    "phone", "email", "website", "facebook", "whatsapp",
    "emergency", "wheelchair", "opening_hours", "specialty", "level", "dispensing",
    "description", "note",
    "osm_created_date", "osm_last_edited_date",
    "admin_match_governorate", "admin_match_district", "admin_match_subdistrict",
    "possible_duplicate_of",
]


# --------------------------------------------------------------------------- #
# generic helpers
# --------------------------------------------------------------------------- #
def blank_to_nan(s):
    s = s.astype("object")
    s = s.where(s.notna(), None)
    return s.map(lambda v: None if v is None or str(v).strip() in ("", "nan", "None") else str(v).strip())


def first_valid(*series):
    """Row-wise first non-null value across the given Series."""
    out = series[0].copy()
    for s in series[1:]:
        out = out.where(out.notna(), s)
    return out


def is_arabic(txt):
    if not isinstance(txt, str):
        return False
    return bool(txt) and len(ARABIC.findall(txt)) >= len(LATIN.findall(txt)) and bool(ARABIC.search(txt))


def is_latin(txt):
    if not isinstance(txt, str):
        return False
    return bool(txt) and bool(LATIN.search(txt)) and not is_arabic(txt)


# --------------------------------------------------------------------------- #
# phones
# --------------------------------------------------------------------------- #
def norm_one_phone(p):
    raw = p.strip()
    digits = re.sub(r"[^\d+]", "", raw)
    if not digits:
        return None
    if digits.startswith("+"):
        digits = "+" + re.sub(r"\D", "", digits)
    elif digits.startswith("00"):
        digits = "+" + digits[2:]
    elif digits.startswith("0") and 9 <= len(digits) <= 11:   # 01xxxxxxxxx / 02xxxxxxxx
        digits = "+20" + digits[1:]
    elif digits.startswith("20") and len(digits) >= 11:
        digits = "+" + digits
    # hotlines (e.g. 16602, 19xxx) are left as they are
    return digits


def merge_phones(*values):
    seen, out = set(), []
    for v in values:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            continue
        for part in re.split(r"[;,/|]", str(v)):
            n = norm_one_phone(part) if part.strip() else None
            if n and n not in seen:
                seen.add(n)
                out.append(n)
    return "; ".join(out) if out else None


# --------------------------------------------------------------------------- #
# dates (stored as ns but actually seconds, e.g. 1970-01-01 00:00:01.237149737)
# --------------------------------------------------------------------------- #
def recover_date(s):
    dt = pd.to_datetime(s, errors="coerce", utc=True)
    # the epoch offset in nanoseconds IS the real timestamp in seconds
    secs = pd.to_numeric(dt.map(lambda x: (x - pd.Timestamp(0, tz="UTC")).value if pd.notna(x) else np.nan),
                         errors="coerce")
    real = pd.to_datetime(secs, unit="s", errors="coerce")
    # sanity: OSM started 2004; anything outside is not a real timestamp
    real = real.where((real >= "2004-01-01") & (real <= pd.Timestamp.now() + pd.Timedelta(days=1)))
    return real.dt.strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# duplicates
# --------------------------------------------------------------------------- #
AR_NORM = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})


def S(v):
    """Return a stripped string, or None for NaN / None / empty values."""
    if isinstance(v, str) and v.strip() and v.strip().lower() not in ("nan", "none"):
        return v.strip()
    return None


def name_key(txt):
    txt = S(txt)
    if not txt:
        return None
    t = re.sub(r"[\u064B-\u0652\u0640]", "", txt).translate(AR_NORM).lower()
    t = re.sub(r"[^\w]", "", t)
    return t or None


def flag_duplicates(df, radius_m=100):
    """possible_duplicate_of = osm_id of the first row it duplicates (same name key
    + same facility_type + within radius_m). Nothing is deleted."""
    key = df["name_ar"].map(name_key).where(df["name_ar"].notna(), df["name_en"].map(name_key))
    tmp = pd.DataFrame({"key": key, "type": df["facility_type"], "lat": df["latitude"],
                        "lon": df["longitude"], "osm_id": df["osm_id"]}, index=df.index)
    tmp = tmp[tmp["key"].notna() & tmp["lat"].notna()]
    out = pd.Series(pd.NA, index=df.index, dtype="object")
    for _, g in tmp.groupby(["key", "type"]):
        if len(g) < 2:
            continue
        lat = np.radians(g["lat"].values)
        lon = np.radians(g["lon"].values)
        ids = g["osm_id"].values
        idx = g.index.values
        for i in range(1, len(g)):
            d = 6371000 * 2 * np.arcsin(np.sqrt(
                np.sin((lat[:i] - lat[i]) / 2) ** 2
                + np.cos(lat[i]) * np.cos(lat[:i]) * np.sin((lon[:i] - lon[i]) / 2) ** 2))
            if (d <= radius_m).any():
                out.at[idx[i]] = str(ids[int(np.argmax(d <= radius_m))])
    return out


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=ADMIN_CSV)
    ap.add_argument("--output", default=CLEAN_CSV)
    a = ap.parse_args()

    df = pd.read_csv(a.input, low_memory=False, dtype={"osm_id": "int64"})
    n0, c0 = len(df), df.shape[1]
    print(f"Loaded {n0:,} rows x {c0} columns")

    # tidy strings everywhere
    for c in df.select_dtypes(include=["object", "string"]).columns:
        df[c] = blank_to_nan(df[c])

    # ---- rescue useful keys from all_tags -------------------------------- #
    tags = df["all_tags"].map(lambda s: json.loads(s) if isinstance(s, str) else {})
    def tag(k):
        return tags.map(lambda d: (str(d[k]).strip() or None) if k in d else None)
    df["alt_name"] = first_valid(tag("alt_name"), tag("alt_name:ar"), tag("alt_name:en"))
    df["facebook"] = tag("contact:facebook")
    df["whatsapp"] = tag("contact:whatsapp")
    mobile = tag("mobile")
    osm_subdistrict = tag("addr:subdistrict")
    osm_province = tag("addr:province")

    # ---- facility type ---------------------------------------------------- #
    df["facility_type"] = df["facility_type"].replace(FACILITY_TYPE_MAP)

    # ---- names ------------------------------------------------------------ #
    name_ar = df["name_ar"].copy()
    name_en = df["name_en"].copy()
    generic = df["name"]
    # untagged `name` goes to the language column that matches its script
    name_ar = name_ar.where(name_ar.notna(), generic.where(generic.map(is_arabic)))
    name_en = name_en.where(name_en.notna(), generic.where(generic.map(is_latin)))
    # official_name / short_name / brand only used to fill gaps
    for extra in ("official_name", "short_name", "brand"):
        name_ar = name_ar.where(name_ar.notna(), df[extra].where(df[extra].map(is_arabic)))
        name_en = name_en.where(name_en.notna(), df[extra].where(df[extra].map(is_latin)))
    df["name_ar"], df["name_en"] = name_ar, name_en
    df["name"] = first_valid(generic, name_ar, name_en)
    df["missing_name"] = df["name"].isna()

    # ---- contacts --------------------------------------------------------- #
    df["phone"] = [merge_phones(p, c, m) for p, c, m in zip(df["phone"], df["contact_phone"], mobile)]
    df["email"] = first_valid(df["email"], df["contact_email"]).str.lower()
    df["website"] = first_valid(df["website"], df["contact_website"])

    # ---- yes / no style fields -------------------------------------------- #
    for c in ("emergency", "wheelchair", "dispensing"):
        df[c] = df[c].str.lower()
    df["level"] = pd.to_numeric(df["level"], errors="coerce").astype("Int64")
    df = df.rename(columns={"healthcare_speciality": "specialty", "addr_postcode": "postcode"})

    # ---- address ---------------------------------------------------------- #
    def osm_address(r, i):
        if S(r["addr_full"]):
            return S(r["addr_full"])
        street = " ".join(S(x) for x in (r["addr_housenumber"], r["addr_street"]) if S(x))
        parts = [street, S(osm_subdistrict[i]), S(r["addr_city"]), S(r["addr_district"]), S(osm_province[i])]
        seen, out = set(), []
        for p in parts:
            if p and p.lower() not in seen:
                seen.add(p.lower())
                out.append(p)
        return ", ".join(out) if out else None

    df["address_osm"] = [osm_address(r, i) for i, r in df.iterrows()]

    def full(addr, sub, dist, gov):
        parts, seen = [], set()
        for p in (S(addr), S(sub), S(dist), S(gov)):
            if p and str(p).lower() not in seen and not any(str(p).lower() in s for s in seen):
                seen.add(str(p).lower())
                parts.append(str(p))
        return ", ".join(parts) if parts else None

    df["full_address"] = [full(*x) for x in zip(df["address_osm"], df["subdistrict_en"],
                                                 df["district_en"], df["governorate_en"])]
    df["full_address_ar"] = [full(*x) for x in zip(df["address_osm"], df["subdistrict_ar"],
                                                    df["district_ar"], df["governorate_ar"])]

    # ---- dates ------------------------------------------------------------ #
    df["osm_created_date"] = recover_date(df["osm_created_at"])
    df["osm_last_edited_date"] = recover_date(df["osm_last_edited_at"])

    # ---- duplicates (flag only) ------------------------------------------- #
    df["possible_duplicate_of"] = flag_duplicates(df)

    # exact duplicates by OSM identity (none expected)
    df = df.drop_duplicates(subset=["osm_type", "osm_id"]).reset_index(drop=True)

    # ---- column selection ------------------------------------------------- #
    keep = [c for c in COLUMN_ORDER if c in df.columns]
    dropped = [c for c in df.columns if c not in keep]
    out = df[keep]

    out.to_csv(a.output, index=False, encoding="utf-8-sig")

    print(f"\nColumns: {c0} -> {out.shape[1]}   Rows: {n0:,} -> {len(out):,}")
    print(f"Dropped columns ({len(dropped)}): {', '.join(dropped)}")
    print("\nFill rates (%):")
    print((out.notna().mean() * 100).round(1).to_string())
    print(f"\nUnnamed (kept, flagged): {int(out['missing_name'].sum())}")
    print(f"Possible duplicates (flagged, kept): {int(out['possible_duplicate_of'].notna().sum())}")
    print(f"Saved -> {a.output}")


if __name__ == "__main__":
    main()
