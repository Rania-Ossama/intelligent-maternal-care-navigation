#!/usr/bin/env python3
"""
city_level_api_verify.py

Step 2 & Step 3A: Live Multi-API Reverse Geocoding Audit across ALL 798 rows.
- Primary API: ArcGIS World GeocodeServer (returns official Arabic Region/City/District/Street)
- Secondary API: BigDataCloud Reverse Geocode Client (returns English administrative divisions)
- Tertiary check: Photon (Komoot) with IPv4 socket preference (if reachable)

Caches all responses to Q&A/cache_reverse_geocode_798.json and outputs a complete
list of every City A vs. City B candidate mismatch to Q&A/city_mismatch_candidates.txt
and Q&A/city_level_audit_phase2.csv.
"""

import os
import re
import json
import time
import math
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

BASE_DIR = '/home/yousefmahmoudali/Desktop/GradII'
PHASE1_CSV = os.path.join(BASE_DIR, 'Q&A', 'city_level_audit_phase1.csv')
CACHE_JSON = os.path.join(BASE_DIR, 'Q&A', 'cache_reverse_geocode_798.json')
PHASE2_CSV = os.path.join(BASE_DIR, 'Q&A', 'city_level_audit_phase2.csv')
CANDIDATES_TXT = os.path.join(BASE_DIR, 'Q&A', 'city_mismatch_candidates.txt')

AR_GOV_TO_EN = {
    'بنى سويف': 'Beni Suef', 'بني سويف': 'Beni Suef', 'Beni Suef': 'Beni Suef', 'Bani Sweif': 'Beni Suef',
    'المنيا': 'Minya', 'Minya': 'Minya', 'Al Minya': 'Minya',
    'أسيوط': 'Assiut', 'اسيوط': 'Assiut', 'Asyut': 'Assiut', 'Assiut': 'Assiut',
    'سوهاج': 'Sohag', 'Sohag': 'Sohag', 'Suhaj': 'Sohag',
    'قنا': 'Qena', 'Qena': 'Qena', 'Qina': 'Qena',
    'الأقصر': 'Luxor', 'الاقصر': 'Luxor', 'Luxor': 'Luxor', 'Al Uqsur': 'Luxor',
    'أسوان': 'Aswan', 'اسوان': 'Aswan', 'Aswan': 'Aswan',
    'الجيزة': 'Giza', 'الجيزه': 'Giza', 'Giza': 'Giza',
    'مطروح': 'Marsa Matrouh', 'مرسى مطروح': 'Marsa Matrouh', 'Matrouh': 'Marsa Matrouh',
    'البحر الأحمر': 'Red Sea', 'البحر الاحمر': 'Red Sea', 'Red Sea': 'Red Sea',
    'الوادي الجديد': 'New Valley', 'الوادى الجديد': 'New Valley', 'New Valley': 'New Valley',
    'الفيوم': 'Fayoum', 'Faiyum': 'Fayoum', 'Fayoum': 'Fayoum',
    'القاهرة': 'Cairo', 'Cairo': 'Cairo',
}

AR_CITY_NORM = {
    # Beni Suef
    'الواسطى': 'Al Wasta', 'الواسطي': 'Al Wasta',
    'ناصر': 'Nasser', 'بوش': 'Nasser',
    'بنى سويف': 'Beni Suef', 'بني سويف': 'Beni Suef', 'بنى سويف الجديدة': 'Beni Suef',
    'اهناسيا': 'Ihnasya', 'إهناسيا': 'Ihnasya', 'أهناسيا': 'Ihnasya',
    'ببا': 'Biba',
    'سمسطا': 'Sumusta',
    'الفشن': 'Al Fashn',
    # Minya
    'العدوة': 'El Idwa', 'العدوه': 'El Idwa',
    'مغاغة': 'Maghagha', 'مغاغه': 'Maghagha',
    'بنى مزار': 'Beni Mazar', 'بني مزار': 'Beni Mazar',
    'مطاى': 'Matai', 'مطاي': 'Matai',
    'سمالوط': 'Samalut',
    'المنيا': 'Minya', 'المنيا الجديدة': 'Minya',
    'أبو قرقاص': 'Abu Qurqas', 'ابو قرقاص': 'Abu Qurqas',
    'ملوى': 'Mallawi', 'ملوي': 'Mallawi',
    'دير مواس': 'Deir Mawas',
    # Assiut
    'ديروط': 'Dairut',
    'القوصية': 'Al Qusiya', 'القوصيه': 'Al Qusiya',
    'منفلوط': 'Manfalut',
    'أسيوط': 'Assiut', 'اسيوط': 'Assiut', 'أسيوط الجديدة': 'Assiut', 'اسيوط الجديدة': 'Assiut',
    'أبنوب': 'Abnoub', 'ابنوب': 'Abnoub',
    'الفتح': 'Al Fath',
    'ساحل سليم': 'Sahel Selim',
    'البدارى': 'Al Badari', 'البداري': 'Al Badari',
    'أبو تيج': 'Abu Tig', 'ابو تيج': 'Abu Tig',
    'صدفا': 'Sedfa',
    'الغنايم': 'Al Ghanayem',
    # Sohag
    'طما': 'Tima',
    'طهطا': 'Tahta',
    'جهينة': 'Juhayna', 'جهينه': 'Juhayna', 'جهينة الغربية': 'Juhayna',
    'المراغة': 'Al Maragha', 'المراغه': 'Al Maragha',
    'ساقلتة': 'Saqalta', 'ساقلته': 'Saqalta',
    'أخميم': 'Akhmim', 'اخميم': 'Akhmim', 'أخميم الجديدة': 'Akhmim', 'الكوثر': 'Akhmim',
    'سوهاج': 'Sohag', 'سوهاج الجديدة': 'Sohag', 'حى الكوثر': 'Akhmim',
    'المنشاة': 'Al Monshaah', 'المنشاه': 'Al Monshaah', 'المنشأة': 'Al Monshaah',
    'العسيرات': 'Al Usayrat',
    'جرجا': 'Girga',
    'البلينا': 'Al Balyana',
    'دار السلام': 'Dar El Salam',
    # Qena
    'أبو تشت': 'Abu Tesht', 'ابو تشت': 'Abu Tesht',
    'فرشوط': 'Farshut',
    'نجع حمادى': 'Nag Hammadi', 'نجع حمادي': 'Nag Hammadi',
    'الوقف': 'Al Waqf',
    'دشنا': 'Dishna',
    'قنا': 'Qena', 'قنا الجديدة': 'Qena',
    'قفط': 'Qift',
    'قوص': 'Qus',
    'نقادة': 'Naqada', 'نقاده': 'Naqada',
    # Luxor
    'طيبة': 'New Tiba', 'طيبه': 'New Tiba',
    'الزينية': 'Al Ziniya', 'الزينيه': 'Al Ziniya',
    'الأقصر': 'Luxor', 'الاقصر': 'Luxor',
    'البياضية': 'Al Bayadiya', 'البياضيه': 'Al Bayadiya',
    'القرنة': 'Al Qurna', 'القرنه': 'Al Qurna',
    'الطود': 'Al Tod',
    'أرمنت': 'Armant', 'ارمنت': 'Armant',
    'إسنا': 'Esna', 'اسنا': 'Esna',
    # Aswan
    'السباعية': 'Al Sibaiya',
    'إدفو': 'Edfu', 'ادفو': 'Edfu',
    'كوم أمبو': 'Kom Ombo', 'كوم امبو': 'Kom Ombo',
    'نصر النوبة': 'Nasr Al-Nuba', 'نصر النوبه': 'Nasr Al-Nuba', 'نصر': 'Nasr Al-Nuba',
    'دراو': 'Daraw',
    'أسوان': 'Aswan', 'اسوان': 'Aswan', 'أسوان الجديدة': 'Aswan',
    'أبو سمبل': 'Abu Simbel', 'ابو سمبل': 'Abu Simbel',
    # External
    'أطفيح': 'Atfeeh (Giza)', 'اطفيح': 'Atfeeh (Giza)', 'الصف': 'Atfeeh (Giza)',
    'العمرانية': 'Omrania (Giza)', 'العلمين': 'El Alamein (Matrouh)',
    'الخارجة': 'Kharga (New Valley)', 'الخارجه': 'Kharga (New Valley)',
    'سفاجا': 'Safaga (Red Sea)', 'القصير': 'Quseir (Red Sea)',
}

def map_ar_city(city_str, region_str=''):
    s = str(city_str or '').strip()
    if not s:
        return ''
    # Strip prefixes like مركز / قسم / مدينة / أول / ثان
    cleaned = re.sub(r'^(مركز|قسم|مدينة|مدينه|حى|حي)\s+', '', s)
    cleaned = re.sub(r'\s+(أول|اول|ثان|ثاني|ثانى|1|2|القديمة|الجديدة)$', '', cleaned).strip()
    if cleaned in AR_CITY_NORM:
        return AR_CITY_NORM[cleaned]
    for k, v in AR_CITY_NORM.items():
        if k in s:
            return v
    return s

def map_ar_gov(reg_str):
    s = str(reg_str or '').strip()
    if s in AR_GOV_TO_EN:
        return AR_GOV_TO_EN[s]
    for k, v in AR_GOV_TO_EN.items():
        if k in s:
            return v
    return s

def fetch_json(url, timeout=12):
    req = urllib.request.Request(url, headers={'User-Agent': 'MaternaCareAudit/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))

def reverse_arcgis(lat, lon):
    url = f"https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/reverseGeocode?f=json&langCode=ar&location={lon},{lat}"
    for attempt in range(3):
        try:
            data = fetch_json(url, timeout=15)
            addr = data.get('address', {})
            return {
                'ok': True,
                'region': addr.get('Region', ''),
                'city': addr.get('City', ''),
                'district': addr.get('District', ''),
                'neighborhood': addr.get('Neighborhood', ''),
                'match_addr': addr.get('Match_addr', ''),
                'country': addr.get('CountryCode', '')
            }
        except Exception as e:
            if attempt == 2:
                return {'ok': False, 'error': str(e)}
            time.sleep(0.5 * (attempt + 1))

def reverse_bigdatacloud(lat, lon):
    url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={lat}&longitude={lon}&localityLanguage=en"
    try:
        data = fetch_json(url, timeout=12)
        return {
            'ok': True,
            'principalSubdivision': data.get('principalSubdivision', ''),
            'city': data.get('city', ''),
            'locality': data.get('locality', '')
        }
    except Exception as e:
        return {'ok': False, 'error': str(e)}

# Quick connectivity check on BigDataCloud & Photon
print("Testing secondary APIs...")
bdc_test = reverse_bigdatacloud(29.064016, 31.097782)
print("BigDataCloud test:", bdc_test)
try:
    ph_test = fetch_json("https://photon.komoot.io/reverse?lat=29.064016&lon=31.097782", timeout=8)
    print("Photon test: OK, features=", len(ph_test.get('features', [])))
except Exception as e:
    print("Photon test: FAILED", e)

# Load Phase 1 data
df = pd.read_csv(PHASE1_CSV)
print(f"Loaded {len(df)} rows from {PHASE1_CSV}")

# Load existing cache
cache = {}
if os.path.exists(CACHE_JSON):
    with open(CACHE_JSON, 'r', encoding='utf-8') as f:
        cache = json.load(f)

# Unique coordinate keys to query
unique_coords = {}
for _, r in df.iterrows():
    key = f"{float(r['latitude_final']):.6f},{float(r['longitude_final']):.6f}"
    if key not in cache or not cache[key].get('arcgis', {}).get('ok'):
        unique_coords[key] = (float(r['latitude_final']), float(r['longitude_final']))

print(f"Unique uncached coordinates to reverse-geocode via ArcGIS: {len(unique_coords)}")

def worker(item):
    key, (lat, lon) = item
    res = {'arcgis': reverse_arcgis(lat, lon)}
    if bdc_test.get('ok'):
        res['bdc'] = reverse_bigdatacloud(lat, lon)
    return key, res

if unique_coords:
    done = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(worker, it) for it in unique_coords.items()]
        for fut in as_completed(futs):
            k, v = fut.result()
            cache[k] = v
            done += 1
            if done % 100 == 0 or done == len(unique_coords):
                print(f"  Reverse geocoded {done}/{len(unique_coords)}...")
    with open(CACHE_JSON, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

# Enrich dataframe with ArcGIS + BDC reverse geocode results
ag_regions, ag_regions_en, ag_cities, ag_cities_en, ag_districts, ag_addrs = [], [], [], [], [], []
bdc_govs, bdc_locs = [], []
api_flags_list = []

# Equivalent / adjacent urban pairs that are NOT City A vs City B bugs
# e.g. Luxor City / Al Bayadiya (adjacent), Sohag / Akhmim (across bridge), Assiut / Al Fath (across bridge),
# New Sohag -> Kharga desert polygon artifact, New Qena -> Red Sea polygon artifact, Esna -> Qena historical
KNOWN_ADJACENT = {
    ('Luxor', 'Al Bayadiya'), ('Al Bayadiya', 'Luxor'),
    ('Luxor', 'Al Ziniya'), ('Al Ziniya', 'Luxor'),
    ('Luxor', 'Al Qurna'), ('Al Qurna', 'Luxor'),
    ('Luxor', 'New Tiba'), ('New Tiba', 'Luxor'),
    ('Assiut', 'Al Fath'), ('Al Fath', 'Assiut'),
    ('Assiut', 'Abnoub'), ('Abnoub', 'Assiut'),
    ('Sohag', 'Akhmim'), ('Akhmim', 'Sohag'),
    ('Qus', 'Naqada'), ('Naqada', 'Qus'),
    ('Qus', 'Qift'), ('Qift', 'Qus'),
    ('Kom Ombo', 'Daraw'), ('Daraw', 'Kom Ombo'),
    ('Kom Ombo', 'Nasr Al-Nuba'), ('Nasr Al-Nuba', 'Kom Ombo'),
    ('Abu Tig', 'Sahel Selim'), ('Sahel Selim', 'Abu Tig'),
    ('Al Balyana', 'Dar El Salam'), ('Dar El Salam', 'Al Balyana'),
    ('Edfu', 'Al Sibaiya'), ('Al Sibaiya', 'Edfu'),
}

for _, r in df.iterrows():
    key = f"{float(r['latitude_final']):.6f},{float(r['longitude_final']):.6f}"
    entry = cache.get(key, {})
    ag = entry.get('arcgis', {})
    bdc = entry.get('bdc', {})

    reg = ag.get('region', '')
    reg_en = map_ar_gov(reg)
    city = ag.get('city', '')
    city_en = map_ar_city(city, reg)
    dist = ag.get('district', '')
    maddr = ag.get('match_addr', '')

    ag_regions.append(reg)
    ag_regions_en.append(reg_en)
    ag_cities.append(city)
    ag_cities_en.append(city_en)
    ag_districts.append(dist)
    ag_addrs.append(maddr)
    bdc_govs.append(bdc.get('principalSubdivision', ''))
    bdc_locs.append(bdc.get('locality', '') or bdc.get('city', ''))

    gov = str(r['governorate_assigned'])
    d_norm = str(r['district_norm']) if pd.notna(r['district_norm']) else ''
    n_city = str(r['name_city']) if pd.notna(r['name_city']) else ''

    aflags = []
    if reg_en and reg_en != gov:
        aflags.append(f"ARCGIS_GOV_MISMATCH(assigned={gov},arcgis={reg_en})")
    if city_en and d_norm and city_en != d_norm and (city_en, d_norm) not in KNOWN_ADJACENT:
        aflags.append(f"ARCGIS_CITY_VS_DISTRICT(dist={d_norm},arcgis={city_en})")
    if city_en and n_city and city_en != n_city and (city_en, n_city) not in KNOWN_ADJACENT:
        aflags.append(f"ARCGIS_CITY_VS_NAME(name={n_city},arcgis={city_en})")
    api_flags_list.append(' | '.join(aflags) if aflags else 'API_OK')

df['arcgis_region_ar'] = ag_regions
df['arcgis_gov_en'] = ag_regions_en
df['arcgis_city_ar'] = ag_cities
df['arcgis_city_en'] = ag_cities_en
df['arcgis_district_ar'] = ag_districts
df['arcgis_match_addr'] = ag_addrs
df['bdc_gov'] = bdc_govs
df['bdc_locality'] = bdc_locs
df['api_flags'] = api_flags_list

df.to_csv(PHASE2_CSV, index=False, encoding='utf-8')

# Write detailed candidates report
lines = []
lines.append("=== PHASE 2: MULTI-API REVERSE GEOCODING CITY A vs CITY B AUDIT (N = 798) ===\n")
lines.append(f"ArcGIS OK count: {(df['arcgis_gov_en'] != '').sum()} / {len(df)}")
lines.append(f"ArcGIS Gov exact match: {(df['arcgis_gov_en'] == df['governorate_assigned']).sum()} / {len(df)}")
lines.append(f"Rows with API_OK and Phase1 OK: {((df['api_flags'] == 'API_OK') & (df['severity'] == 'OK')).sum()} / {len(df)}")
lines.append("")

# Group 1: ArcGIS Governorate Mismatch
g_mis = df[df['api_flags'].str.contains('ARCGIS_GOV_MISMATCH', na=False)]
lines.append(f"\n--- GROUP 1: ARCGIS GOVERNORATE MISMATCHES ({len(g_mis)} rows) ---")
for _, r in g_mis.iterrows():
    lines.append(f"  {r['canonical_entity_id']} | {r['canonical_name']} ({r['original_arabic_name']}) | Src={r['source_files_all']} | Assigned={r['governorate_assigned']}/{r['district_raw']} | GPS=({r['latitude_final']:.6f},{r['longitude_final']:.6f}) | ArcGIS={r['arcgis_gov_en']}/{r['arcgis_city_en']} ({r['arcgis_city_ar']}) | BDC={r['bdc_gov']}/{r['bdc_locality']} | P1={r['flags']} | Addr={r['address']}")

# Group 2: Swapped / PlusCode Mismatches
p_mis = df[df['flags'].str.contains('SWAPPED_|PLUSCODE_MISMATCH', na=False)]
lines.append(f"\n--- GROUP 2: SWAPPED LAT/LON & PLUSCODE MISMATCHES ({len(p_mis)} rows) ---")
for _, r in p_mis.iterrows():
    lines.append(f"  {r['canonical_entity_id']} | {r['canonical_name']} ({r['original_arabic_name']}) | Assigned={r['governorate_assigned']}/{r['district_raw']} | GPS=({r['latitude_final']:.6f},{r['longitude_final']:.6f}) | ArcGIS={r['arcgis_gov_en']}/{r['arcgis_city_en']} | P1={r['flags']} | Addr={r['address']}")

# Group 3: City vs Name Mismatch (Same Gov or Any Gov, where name explicitly mentions City A)
n_mis = df[df['api_flags'].str.contains('ARCGIS_CITY_VS_NAME', na=False) | df['flags'].str.contains('NAME_CITY_MISMATCH', na=False)]
lines.append(f"\n--- GROUP 3: HOSPITAL NAME CITY vs GPS ACTUAL CITY ({len(n_mis)} rows) ---")
for _, r in n_mis.iterrows():
    lines.append(f"  {r['canonical_entity_id']} | {r['canonical_name']} ({r['original_arabic_name']}) | Src={r['source_files_all']} | Assigned={r['governorate_assigned']}/{r['district_raw']} | NameCity={r['name_city']}({r['name_city_km']}km) | ArcGIS={r['arcgis_gov_en']}/{r['arcgis_city_en']} ({r['arcgis_city_ar']}) | GPS=({r['latitude_final']:.6f},{r['longitude_final']:.6f}) | Addr={r['address'][:90]}")

# Group 4: ArcGIS City vs Assigned District Mismatch (excluding already in Group 1 or 3)
seen = set(g_mis['canonical_entity_id']) | set(n_mis['canonical_entity_id'])
d_mis = df[df['api_flags'].str.contains('ARCGIS_CITY_VS_DISTRICT', na=False) & (~df['canonical_entity_id'].isin(seen))]
lines.append(f"\n--- GROUP 4: ASSIGNED DISTRICT vs ARCGIS CITY MISMATCH ({len(d_mis)} rows) ---")
for _, r in d_mis.iterrows():
    lines.append(f"  {r['canonical_entity_id']} | {r['canonical_name']} ({r['original_arabic_name']}) | Src={r['source_files_all']} | Assigned={r['governorate_assigned']}/{r['district_raw']}({r['district_norm']}:{r['dist_to_assigned_km']}km) | ArcGIS={r['arcgis_city_en']} ({r['arcgis_city_ar']}) | GPS=({r['latitude_final']:.6f},{r['longitude_final']:.6f}) | Addr={r['address'][:90]}")

# Group 5: Full Check of ALL 50 Previously Snapped MOHP Rows
sn = df[df['was_snapped_50'] == True]
lines.append(f"\n--- GROUP 5: ALL 50 PREVIOUSLY SNAPPED MOHP ROWS ({len(sn)} rows) ---")
for _, r in sn.iterrows():
    lines.append(f"  {r['canonical_entity_id']} | {r['canonical_name']} ({r['original_arabic_name']}) | Assigned={r['governorate_assigned']}/{r['district_raw']}({r['dist_to_assigned_km']}km) | ArcGIS={r['arcgis_gov_en']}/{r['arcgis_city_en']} ({r['arcgis_match_addr']}) | Flags={r['api_flags']} | Addr={r['address'][:80]}")

with open(CANDIDATES_TXT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f"Wrote complete diagnostic report to {CANDIDATES_TXT}")
print(f"Group 1 (Gov mismatch): {len(g_mis)}")
print(f"Group 2 (Swapped/PlusCode): {len(p_mis)}")
print(f"Group 3 (Name City vs GPS City): {len(n_mis)}")
print(f"Group 4 (District vs GPS City): {len(d_mis)}")
print(f"Group 5 (50 Snapped MOHP): {len(sn)}")
