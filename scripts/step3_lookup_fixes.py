#!/usr/bin/env python3
"""
step3_lookup_fixes.py

Step 3B:
1. Re-normalizes all ArcGIS governorate/city spellings across all 798 rows in
   city_level_audit_phase2.csv to confirm the EXACT remaining set of genuine
   Governorate or City mismatches (zero false positives).
2. Inspects all internal candidate matches inside facilities_sorted_by_governorate.csv
   and queries ArcGIS World GeocodeServer (findAddressCandidates) + Photon (Komoot)
   to get verified rooftop coordinates for every genuine City A vs City B bug.
"""

import os
import re
import json
import math
import urllib.request
import urllib.parse
import pandas as pd

BASE_DIR = '/home/yousefmahmoudali/Desktop/GradII'
MASTER_CSV = os.path.join(BASE_DIR, 'datasets', 'facilities_sorted_by_governorate.csv')
PHASE2_CSV = os.path.join(BASE_DIR, 'Q&A', 'city_level_audit_phase2.csv')

df_m = pd.read_csv(MASTER_CSV)
df2 = pd.read_csv(PHASE2_CSV)

GOV_NORM_FULL = {
    'Beni Suef': 'Beni Suef', 'Bani Suwayf': 'Beni Suef', 'بنى سويف': 'Beni Suef', 'بني سويف': 'Beni Suef',
    'Minya': 'Minya', 'المنية': 'Minya', 'المنيا': 'Minya', 'El Menia': 'Minya', 'Al Minya': 'Minya',
    'Assiut': 'Assiut', 'Assiout': 'Assiut', 'Asyut': 'Assiut', 'أسيوط': 'Assiut', 'اسيوط': 'Assiut',
    'Sohag': 'Sohag', 'Souhaj': 'Sohag', 'سوهاج': 'Sohag',
    'Qena': 'Qena', 'Qinā': 'Qena', 'Qina': 'Qena', 'قنا': 'Qena',
    'Luxor': 'Luxor', "al-'Uqsur": 'Luxor', 'Al Uqsur': 'Luxor', 'الأقصر': 'Luxor', 'الاقصر': 'Luxor',
    'Aswan': 'Aswan', 'أسوان': 'Aswan', 'اسوان': 'Aswan',
    'Giza': 'Giza', 'Al Jizah': 'Giza', 'الجيزة': 'Giza',
    'Marsa Matrouh': 'Marsa Matrouh', 'Matrouh': 'Marsa Matrouh', 'مطروح': 'Marsa Matrouh',
    'New Valley': 'New Valley', 'الوادي الجديد': 'New Valley',
    'Red Sea': 'Red Sea', 'البحر الأحمر': 'Red Sea',
}

def norm_gov(s):
    s = str(s or '').strip()
    return GOV_NORM_FULL.get(s, s)

df2['ag_gov_clean'] = df2['arcgis_gov_en'].apply(norm_gov)

print("=== 1. TRUE GOVERNORATE MISMATCHES AFTER SPELLING NORMALIZATION (N = 798) ===")
real_gov_mis = df2[df2['ag_gov_clean'] != df2['governorate_assigned']]
print(f"Count: {len(real_gov_mis)}")
for _, r in real_gov_mis.iterrows():
    print(f"  {r['canonical_entity_id']} | {r['canonical_name']} | Assigned={r['governorate_assigned']}/{r['district_raw']} | ArcGIS={r['ag_gov_clean']}/{r['arcgis_city_en']} ({r['arcgis_city_ar']}) | BDC={r['bdc_gov']}/{r['bdc_locality']} | GPS=({r['latitude_final']:.6f},{r['longitude_final']:.6f})")

print("\n=== 2. INTERNAL DATASET MATCHES FOR CANDIDATE FIXES ===")
inspect_ids = [
    'CE00139', 'CE00208', 'CE00054', # Beni Suef General
    'CE00737', 'CE00588', # Iman Hospital Bani Mazar
    'CE00074', 'CE01082', 'CE01979', # Al Ghanayem
    'CE00071', 'CE00994', 'CE01980', # Sahel Selim
    'CE00072', 'CE01101', 'CE01976', # Sidfa
    'CE00091', 'CE01463', 'CE01981', # Dar El Salam
    'CE00086', 'CE00797', 'CE01978', # Tima
    'CE00087', 'CE01224', 'CE01956', 'CE01258', # Akhmim
    'CE00085', 'CE01332', 'CE01962', 'CE01437', # Al Monshaah
    'CE00088', 'CE01987', # Al Maragha
    'CE00089', 'CE01958', 'CE01416', # Awlad Hamza
    'CE00106', 'CE01942', # Al Waqf
    'CE00107', 'CE01572', 'CE01553', # Qift
    'CE02000', # Dar AlShifa Tahta
    'CE00036', 'CE00045', # Edfu hospitals
    'CE00013', # Luxor Univ New Thebes
    'CE00961', # M Mallawi Assiut
    'CE00456', 'CE00476', 'CE00214', 'CE00218', # Ihnasya/Bahsamoon
    'CE01370', # El-Sheikh Hospital Balyana/Abu Tesht border
]
sub = df2[df2['canonical_entity_id'].isin(inspect_ids)]
for cid in inspect_ids:
    rows = sub[sub['canonical_entity_id'] == cid]
    if not rows.empty:
        r = rows.iloc[0]
        print(f"  {cid} | {r['canonical_name']} ({r['original_arabic_name']}) | Src={r['source_files_all']} | {r['governorate_assigned']}/{r['district_raw']} | GPS=({r['latitude_final']:.6f},{r['longitude_final']:.6f}) | ArcGIS={r['ag_gov_clean']}/{r['arcgis_city_en']} [{r['arcgis_match_addr']}] | Addr={r['address']}")

print("\n=== 3. SEARCH EXISTING TAHTA & MARAGHA & WAQF ROWS IN MASTER ===")
for kw in ['الشفا', 'Shifa', 'المراغ', 'Maragh', 'الوقف', 'Waqf', 'بني سويف العام', 'بنى سويف العام', 'Beni Suef General', 'Benisuef General', 'طيبة الجديدة', 'جامعة الأقصر']:
    hits = df2[df2['canonical_name'].str.contains(kw, case=False, na=False) | df2['original_arabic_name'].str.contains(kw, case=False, na=False)]
    if len(hits) > 0:
        print(f"  Keyword '{kw}':")
        for _, r in hits.iterrows():
            if kw in ['الشفا', 'Shifa'] and r['governorate_assigned'] != 'Sohag':
                continue
            print(f"    {r['canonical_entity_id']} | {r['canonical_name']} ({r['original_arabic_name']}) | {r['governorate_assigned']}/{r['district_raw']} | ({r['latitude_final']:.6f},{r['longitude_final']:.6f}) | {r['arcgis_match_addr']}")

print("\n=== 4. LIVE FORWARD GEOCODING (ArcGIS + Photon) FOR TARGET HOSPITALS ===")
def query_arcgis_fwd(q):
    url = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?" + urllib.parse.urlencode({
        'f': 'json', 'singleLine': q, 'countryCode': 'EGY', 'maxLocations': 3, 'outFields': 'Match_addr,City,Region'
    })
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'MaternaCareAudit/1.0'})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            out = []
            for c in data.get('candidates', []):
                loc = c.get('location', {})
                attr = c.get('attributes', {})
                out.append((c.get('score'), round(loc.get('y', 0), 6), round(loc.get('x', 0), 6), attr.get('Match_addr', ''), attr.get('City', ''), attr.get('Region', '')))
            return out
    except Exception as e:
        return [('ERR', str(e))]

def query_photon_fwd(q):
    url = "https://photon.komoot.io/api?" + urllib.parse.urlencode({'q': q, 'limit': 3})
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'MaternaCareAudit/1.0'})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            out = []
            for feat in data.get('features', []):
                coords = feat.get('geometry', {}).get('coordinates', [0, 0])
                props = feat.get('properties', {})
                out.append((round(coords[1], 6), round(coords[0], 6), props.get('name', ''), props.get('city', ''), props.get('state', ''), props.get('country', '')))
            return out
    except Exception as e:
        return [('ERR', str(e))]

queries = [
    ("CE00106/CE01942 Al Waqf Central Hospital", "مستشفى الوقف المركزي, الوقف, قنا, مصر"),
    ("CE00106/CE01942 Al Waqf Central (EN)", "El Waqf Central Hospital, Qena, Egypt"),
    ("CE02000 Dar AlShifa Tahta", "مستشفى دار الشفاء, طهطا, سوهاج, مصر"),
    ("CE02000 Army St Tahta", "شارع الجيش, طهطا, سوهاج, مصر"),
    ("CE00088 Al Maragha Central", "مستشفى المراغة المركزي, المراغة, سوهاج, مصر"),
    ("CE00088 Al Maragha Central (EN)", "Al Maragha Central Hospital, Sohag, Egypt"),
    ("CE00054 Beni Suef General", "مستشفى بني سويف التخصصي, بني سويف, مصر"),
    ("CE00588 Iman Hospital Bani Mazar", "مستشفى الايمان, بني مزار, المنيا, مصر"),
    ("CE00013 Luxor University Hospital New Thebes", "مستشفى جامعة الاقصر, طيبة الجديدة, الاقصر, مصر"),
    ("CE00087 Akhmim Central", "مستشفى أخميم المركزي, أخميم, سوهاج, مصر"),
]
for label, q in queries:
    print(f"\n  [{label}] query='{q}'")
    print("    ArcGIS:", query_arcgis_fwd(q))
    print("    Photon:", query_photon_fwd(q))

# Also decode Plus Code GQ2X+GG2 around Bani Mazar (28.496, 30.802)
from city_level_coord_audit import decode_short_olc
print("\n=== 5. PLUS CODE DECODE CHECK ===")
print("  CE00588 GQ2X+GG2 around Bani Mazar (28.496, 30.802):", decode_short_olc("GQ2X+GG2", 28.496, 30.802))
print("  CE00588 GQ2X+GG2 around Sumusta (28.918, 30.854):", decode_short_olc("GQ2X+GG2", 28.918, 30.854))
print("  CE00245 XPFR+F3M around El Alamein (30.835, 28.955):", decode_short_olc("XPFR+F3M", 30.835, 28.955))
print("  CE00260 RVHJ+FQ4 around El Alamein (30.835, 28.955):", decode_short_olc("RVHJ+FQ4", 30.835, 28.955))
print("  CE00256 R2FH+343 around El Alamein (30.835, 28.955):", decode_short_olc("R2FH+343", 30.835, 28.955))
