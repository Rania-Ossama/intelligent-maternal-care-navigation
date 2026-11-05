"""
Step 3 - Produce the two final CSVs from the cleaned file.

  <prefix>_full_egypt.csv    every row (rows without governorate are kept and flagged)
  <prefix>_upper_egypt.csv   only the Upper Egypt governorates

Governorates are matched by Arabic name OR any English spelling, so
Assiut/Asyut, Minya/Menia, Beni Suef/Bani Suwayf, Sohag/Suhag all work.
Edit UPPER_EGYPT below to change the region definition.

Usage
-----
  python 03_split.py
(paths are set at the top of the script; every one can be overridden with --input/--output etc.)
"""
import argparse
import os
import re
import sys

import pandas as pd

# ----- paths (edit here if you move things) ------------------------------- #
DATA_DIR = r"D:\intelligent-maternal-care-navigation\re_dataset\medical_facilities"
RAW_CSV = os.path.join(DATA_DIR, "egypt_medical_facilities.csv")
ADMIN_CSV = os.path.join(DATA_DIR, "egypt_medical_facilities_admin.csv")
CLEAN_CSV = os.path.join(DATA_DIR, "egypt_medical_facilities_clean.csv")
FINAL_DIR = os.path.join(DATA_DIR, "final")
BOUNDARIES_DIR = r"D:\intelligent-maternal-care-navigation\boundaries_data\processed"
# --------------------------------------------------------------------------- #

# canonical name -> accepted spellings (English lower-case, Arabic)
UPPER_EGYPT = {
    "Assiut":    ["assiut", "asyut", "assyut", "أسيوط", "اسيوط"],
    "Aswan":     ["aswan", "assuan", "أسوان", "اسوان"],
    "Beni Suef": ["beni suef", "bani suwayf", "beni sweif", "beni swief", "bani suef", "بني سويف"],
    "Luxor":     ["luxor", "al uqsur", "الأقصر", "الاقصر"],
    "Minya":     ["minya", "menia", "el minya", "al minya", "minia", "المنيا"],
    "Qena":      ["qena", "qina", "قنا"],
    "Sohag":     ["sohag", "suhag", "sohaj", "سوهاج"],
}


def norm(s):
    if s is None or pd.isna(s):
        return ""
    s = re.sub(r"[\u064B-\u0652]", "", str(s)).lower().strip()
    return re.sub(r"\s+", " ", s)


def canonical(row):
    for col in ("governorate_en", "governorate_ar"):
        v = norm(row.get(col))
        if not v:
            continue
        for canon, aliases in UPPER_EGYPT.items():
            if v in {norm(x) for x in aliases}:
                return canon
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=CLEAN_CSV)
    ap.add_argument("--outdir", default=FINAL_DIR)
    ap.add_argument("--prefix", default="egypt_medical_facilities")
    a = ap.parse_args()

    df = pd.read_csv(a.input, low_memory=False, dtype={"osm_id": "int64"})
    os.makedirs(a.outdir, exist_ok=True)

    # one lookup per distinct governorate (fast)
    gov = df[["governorate_en", "governorate_ar"]].drop_duplicates()
    gov["_upper"] = gov.apply(canonical, axis=1)
    df = df.merge(gov, on=["governorate_en", "governorate_ar"], how="left")
    df["is_upper_egypt"] = df["_upper"].notna()
    df["governorate_missing"] = df["governorate_en"].isna() & df["governorate_ar"].isna()

    found = set(df["_upper"].dropna())
    missing = set(UPPER_EGYPT) - found
    if missing:
        print("WARNING - these Upper Egypt governorates matched NO rows: " + ", ".join(sorted(missing)))
        print("Governorate names present in the data:")
        print(df[["governorate_en", "governorate_ar"]].drop_duplicates().to_string(index=False))

    full = df.drop(columns=["_upper"])
    upper = full[full["is_upper_egypt"]].drop(columns=["is_upper_egypt"]).reset_index(drop=True)

    f_full = os.path.join(a.outdir, f"{a.prefix}_full_egypt.csv")
    f_up = os.path.join(a.outdir, f"{a.prefix}_upper_egypt.csv")
    full.to_csv(f_full, index=False, encoding="utf-8-sig")
    upper.to_csv(f_up, index=False, encoding="utf-8-sig")

    print(f"\nFull Egypt : {len(full):,} rows  -> {f_full}")
    print(f"  without governorate (flagged): {int(full['governorate_missing'].sum())}")
    print(f"Upper Egypt: {len(upper):,} rows -> {f_up}")
    print("\nUpper Egypt by governorate:")
    print(upper["governorate_en"].value_counts().to_string())
    print("\nUpper Egypt by facility type:")
    print(upper["facility_type"].value_counts().to_string())


if __name__ == "__main__":
    main()
