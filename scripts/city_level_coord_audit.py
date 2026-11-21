#!/usr/bin/env python3
"""
city_level_coord_audit.py

Step 1 & Step 2 of the City/District Coordinate Truth Audit across all 798 rows.
Checks every facility for the "City A vs. City B" bug using:
  1. Official Upper Egypt District (Markaz/City) Reference Centroids (~75 centers)
  2. Hospital English + Arabic Name City Extraction
  3. Assigned District vs. GPS Nearest District Haversine Distance
  4. Google Open Location Code (Plus Code) Decoding & Swapped Lat/Lon Detection
  5. Audit of all 50 previously snapped MOHP/registry LINKAGE_PAIRS

Outputs:
  - /home/yousefmahmoudali/Desktop/GradII/Q&A/city_level_audit_phase1.csv
  - Detailed console diagnostic report of every flagged row.
"""

import os
import re
import math
import json
import pandas as pd

BASE_DIR = '/home/yousefmahmoudali/Desktop/GradII'
MASTER_CSV = os.path.join(BASE_DIR, 'datasets', 'facilities_sorted_by_governorate.csv')
VAL_CSV = os.path.join(BASE_DIR, 'Q&A', 'hospital_validation.csv')
FLAGS_CSV = os.path.join(BASE_DIR, 'Q&A', 'coordinate_and_missing_data_flags.csv')
OUT_CSV = os.path.join(BASE_DIR, 'Q&A', 'city_level_audit_phase1.csv')

# =============================================================================
# 1. Official Reference Centroids for Upper Egypt Districts + External Neighbors
#    Format: canonical_district: (governorate, lat, lon, [english_patterns], [arabic_patterns])
# =============================================================================
DISTRICT_REF = {
    # --- BENI SUEF ---
    'Al Wasta': ('Beni Suef', 29.3360, 31.2060,
        [r'\bwasta\b', r'\bel[\s-]*wasta\b', r'\bal[\s-]*wasta\b'],
        ['الواسطى', 'الواسطي', 'واسطى', 'واسطي']),
    'Nasser': ('Beni Suef', 29.1415, 31.1260,
        [r'\bnasser\b', r'\bnasir\b', r'\bbush\b', r'\bboush\b'],
        ['ناصر', 'بوش']),
    'Beni Suef': ('Beni Suef', 29.0661, 31.0994,
        [r'\bbeni\s*suef\b', r'\bbani\s*s[uw]eif\b', r'\bzohour\b', r'\bnew\s*beni\s*suef\b', r'\bsharq\s*el\s*nil\b'],
        ['بني سويف', 'بنى سويف', 'شرق النيل', 'الزهور']),
    'Ihnasya': ('Beni Suef', 29.0865, 30.9355,
        [r'\bihnas[iy]a\b', r'\behnas[iy]a\b', r'\bahans[iy]a\b', r'\bbahsamoon\b'],
        ['اهناسيا', 'إهناسيا', 'أهناسيا', 'البهسمون']),
    'Biba': ('Beni Suef', 28.9205, 30.9850,
        [r'\bbiba\b', r'\bbeba\b'],
        ['ببا']),
    'Sumusta': ('Beni Suef', 28.9185, 30.8540,
        [r'\bsumusta\b', r'\bsamasta\b', r'\bsomosta\b', r'\bsamosta\b'],
        ['سمسطا']),
    'Al Fashn': ('Beni Suef', 28.8235, 30.8995,
        [r'\bfashn\b', r'\bfishn\b'],
        ['الفشن', 'فشن']),

    # --- MINYA ---
    'El Idwa': ('Minya', 28.6980, 30.7580,
        [r'\bidwa\b', r'\bedwa\b', r'\badwa\b', r'\bedawa\b'],
        ['العدوة', 'العدوه', 'عدوة', 'عدوه']),
    'Maghagha': ('Minya', 28.6485, 30.8425,
        [r'\bmaghagha\b', r'\bmaghaghah\b'],
        ['مغاغة', 'مغاغه']),
    'Beni Mazar': ('Minya', 28.4960, 30.8025,
        [r'\bbeni\s*mazar\b', r'\bbani\s*mazar\b'],
        ['بني مزار', 'بنى مزار']),
    'Matai': ('Minya', 28.4190, 30.7790,
        [r'\bmatai\b', r'\bmatay\b', r'\bmutai\b'],
        ['مطاي', 'مطاى']),
    'Samalut': ('Minya', 28.3120, 30.7105,
        [r'\bsamalut\b', r'\bsamalout\b'],
        ['سمالوط']),
    'Minya': ('Minya', 28.0980, 30.7520,
        [r'\bminya\b', r'\bmenia\b', r'\bmenya\b', r'\bel\s*minya\b', r'\bnew\s*minya\b'],
        ['المنيا', 'منيا']),
    'Abu Qurqas': ('Minya', 27.9310, 30.8380,
        [r'\babu\s*q[uo]rqas\b', r'\babou\s*q[uo]rqas\b', r'\bfikriya\b', r'\bfekreya\b'],
        ['ابو قرقاص', 'أبو قرقاص', 'أبوقرقاص', 'ابوقرقاص', 'الفكرية']),
    'Mallawi': ('Minya', 27.7315, 30.8415,
        [r'\bmallawi\b', r'\bmalawi\b', r'\bmallawy\b'],
        ['ملوي', 'ملوى']),
    'Deir Mawas': ('Minya', 27.6415, 30.8485,
        [r'\bdeir\s*mawas\b', r'\bdayr\s*mawas\b', r'\bdir\s*mawas\b'],
        ['دير مواس', 'ديرمواس']),

    # --- ASSIUT ---
    'Dairut': ('Assiut', 27.5560, 30.8075,
        [r'\bdairut\b', r'\bdayrout\b', r'\bdirout\b', r'\bdairout\b'],
        ['ديروط']),
    'Al Qusiya': ('Assiut', 27.4415, 30.8180,
        [r'\bqusiy?a\b', r'\bqousiy?a\b', r'\bkusiy?a\b', r'\bel[\s-]*qusiya\b'],
        ['القوصية', 'القوصيه', 'قوصية', 'قوصيه']),
    'Manfalut': ('Assiut', 27.3105, 30.9700,
        [r'\bmanfalut\b', r'\bmanfalout\b'],
        ['منفلوط']),
    'Assiut': ('Assiut', 27.1810, 31.1837,
        [r'\bassiut\b', r'\basyut\b', r'\bassuit\b', r'\bnew\s*assiut\b', r'\bnew\s*asyut\b', r'\bshattab\b'],
        ['أسيوط', 'اسيوط', 'شطب']),
    'Abnoub': ('Assiut', 27.2695, 31.1510,
        [r'\babnoub\b', r'\babnub\b'],
        ['أبنوب', 'ابنوب']),
    'Al Fath': ('Assiut', 27.1950, 31.2200,
        [r'\bal[\s-]*fath\b', r'\bel[\s-]*fath\b', r'\bfath\b'],
        ['الفتح']),
    'Sahel Selim': ('Assiut', 27.0580, 31.3250,
        [r'\bsahel\s*selim\b', r'\bsahil\s*salim\b'],
        ['ساحل سليم']),
    'Al Badari': ('Assiut', 26.9920, 31.4150,
        [r'\bbadari\b', r'\bbadary\b'],
        ['البداري', 'البدارى', 'بداري']),
    'Abu Tig': ('Assiut', 27.0435, 31.3185,
        [r'\babu\s*tig\b', r'\babo\s*tig\b', r'\babou\s*tig\b', r'\babu\s*teeg\b'],
        ['أبو تيج', 'ابو تيج', 'أبوتيج', 'ابوتيج']),
    'Sedfa': ('Assiut', 26.9475, 31.3675,
        [r'\bsedfa\b', r'\bsidfa\b', r'\bsodfa\b'],
        ['صدفا']),
    'Al Ghanayem': ('Assiut', 26.8630, 31.3370,
        [r'\bghanayem\b', r'\bghanaim\b', r'\bghanayim\b'],
        ['الغنايم', 'غنايم']),

    # --- SOHAG ---
    'Tima': ('Sohag', 26.9095, 31.4345,
        [r'\btima\b', r'\btema\b', r'\btama\b'],
        ['طما']),
    'Tahta': ('Sohag', 26.7690, 31.5020,
        [r'\btahta\b'],
        ['طهطا']),
    'Juhayna': ('Sohag', 26.6730, 31.4980,
        [r'\bjuhayna\b', r'\bgohayna\b', r'\bgehayna\b', r'\bjuhaynah\b'],
        ['جهينة', 'جهينه']),
    'Al Maragha': ('Sohag', 26.6980, 31.6020,
        [r'\bmaragha\b', r'\bmaraghah\b'],
        ['المراغة', 'المراغه', 'مراغة']),
    'Saqalta': ('Sohag', 26.6550, 31.6675,
        [r'\bsaqalta\b', r'\bsaklata\b', r'\bsaqultah\b', r'\bsaqulta\b'],
        ['ساقلتة', 'ساقلته']),
    'Akhmim': ('Sohag', 26.5640, 31.7450,
        [r'\bakhmim\b', r'\bakhmeem\b', r'\bkawthar\b', r'\bkawther\b'],
        ['أخميم', 'اخميم', 'الكوثر']),
    'Sohag': ('Sohag', 26.5569, 31.6948,
        [r'\bsohag\b', r'\bsuhaj\b', r'\bsohaj\b', r'\bnew\s*sohag\b'],
        ['سوهاج']),
    'Al Monshaah': ('Sohag', 26.4765, 31.8030,
        [r'\bmonshaa?h?\b', r'\bmanshaa?h?\b', r'\bmensha[ah]?\b', r'\bawlad\s*hamza\b'],
        ['المنشاة', 'المنشاه', 'المنشأة', 'المنشأه', 'أولاد حمزة', 'اولاد حمزه']),
    'Al Usayrat': ('Sohag', 26.3950, 31.8250,
        [r'\basirat\b', r'\busayrat\b', r'\boseirat\b'],
        ['العسيرات', 'عسيرات']),
    'Girga': ('Sohag', 26.3385, 31.8915,
        [r'\bgirga\b', r'\bgerga\b', r'\bjirja\b'],
        ['جرجا']),
    'Al Balyana': ('Sohag', 26.2355, 32.0040,
        [r'\bbalyana\b', r'\bbaliana\b', r'\bel[\s-]*balyana\b'],
        ['البلينا', 'بلينا']),
    'Dar El Salam': ('Sohag', 26.2650, 32.0500,
        [r'\bdar\s*(?:el|es|al)[\s-]*salam\b'],
        ['دار السلام']),

    # --- QENA ---
    'Abu Tesht': ('Qena', 26.1155, 32.1180,
        [r'\babu\s*tesht\b', r'\babou\s*tesht\b', r'\babu\s*tisht\b'],
        ['أبو تشت', 'ابو تشت', 'أبوتشت', 'ابوتشت']),
    'Farshut': ('Qena', 26.0550, 32.1645,
        [r'\bfarsh[uo]+t\b'],
        ['فرشوط']),
    'Nag Hammadi': ('Qena', 26.0490, 32.2410,
        [r'\bnag\s*hamm?adi\b', r'\bnaj\s*hamm?adi\b', r'\bnagaa?\s*hamm?adi\b'],
        ['نجع حمادي', 'نجع حمادى']),
    'Al Waqf': ('Qena', 26.0680, 32.3935,
        [r'\bwaqf\b', r'\bwakf\b'],
        ['الوقف', 'وقف']),
    'Dishna': ('Qena', 26.1245, 32.4730,
        [r'\bdishna\b', r'\bdashna\b', r'\bdeshna\b'],
        ['دشنا']),
    'Qena': ('Qena', 26.1615, 32.7180,
        [r'\bqena\b', r'\bqina\b', r'\bkena\b', r'\bnew\s*qena\b'],
        ['قنا']),
    'Qift': ('Qena', 25.9985, 32.8155,
        [r'\bqift\b', r'\bqeft\b', r'\bkeft\b'],
        ['قفط']),
    'Qus': ('Qena', 25.9145, 32.7635,
        [r'\bqus\b', r'\bqous\b', r'\bkous\b'],
        ['قوص']),
    'Naqada': ('Qena', 25.9015, 32.7245,
        [r'\bnaqada\b', r'\bnaqadah\b', r'\bnakada\b'],
        ['نقادة', 'نقاده']),

    # --- LUXOR ---
    'New Tiba': ('Luxor', 25.7520, 32.7630,
        [r'\bnew\s*tiba\b', r'\bnew\s*thebes\b'],
        ['طيبة الجديدة', 'طيبه الجديده']),
    'Al Ziniya': ('Luxor', 25.7470, 32.6830,
        [r'\bziniya\b', r'\bzainiya\b', r'\bzeiniya\b'],
        ['الزينية', 'الزينيه']),
    'Luxor': ('Luxor', 25.6872, 32.6396,
        [r'\bluxor\b', r'\bkarnak\b'],
        ['الأقصر', 'الاقصر', 'الكرنك']),
    'Al Bayadiya': ('Luxor', 25.6540, 32.6415,
        [r'\bbayadiy?ah?\b', r'\bbayadey?a\b'],
        ['البياضية', 'البياضيه']),
    'Al Qurna': ('Luxor', 25.7285, 32.6100,
        [r'\bqurna\b', r'\bqorna\b', r'\bgourna\b', r'\bgurna\b'],
        ['القرنة', 'القرنه']),
    'Al Tod': ('Luxor', 25.5810, 32.5360,
        [r'\bal[\s-]*tod\b', r'\bel[\s-]*tod\b', r'\btod\b', r'\btoud\b'],
        ['الطود']),
    'Armant': ('Luxor', 25.6225, 32.5315,
        [r'\barmant\b', r'\berment\b'],
        ['أرمنت', 'ارمنت']),
    'Esna': ('Luxor', 25.2935, 32.5540,
        [r'\besna\b', r'\bisna\b'],
        ['إسنا', 'اسنا']),

    # --- ASWAN ---
    'Al Sibaiya': ('Aswan', 25.1748, 32.6786,
        [r'\bsibaiy?a\b', r'\bsebaiy?a\b', r'\bheptathlon\b', r'\bcentral\s*seven\b'],
        ['السباعية', 'السباعيه']),
    'Edfu': ('Aswan', 24.9785, 32.8735,
        [r'\bedfu\b', r'\bidfu\b', r'\badfu\b'],
        ['إدفو', 'ادفو']),
    'Kom Ombo': ('Aswan', 24.4760, 32.9460,
        [r'\bkom\s*ombo\b', r'\bkoum\s*ombo\b', r'\bkom\s*umbo\b'],
        ['كوم أمبو', 'كوم امبو', 'كومومبو']),
    'Nasr Al-Nuba': ('Aswan', 24.5320, 32.9890,
        [r'\bnasr\s*al[\s-]*nuba\b', r'\bnasr\s*el[\s-]*nuba\b', r'\bnasr\s*central\b'],
        ['نصر النوبة', 'نصر النوبه']),
    'Daraw': ('Aswan', 24.4050, 32.9225,
        [r'\bdaraw\b', r'\bdrau\b', r'\bdarau\b'],
        ['دراو']),
    'Aswan': ('Aswan', 24.0889, 32.8998,
        [r'\baswan\b', r'\bassouan\b', r'\bnew\s*aswan\b'],
        ['أسوان', 'اسوان']),
    'Abu Simbel': ('Aswan', 22.3490, 31.6160,
        [r'\babu\s*simbel\b', r'\babo\s*simbel\b'],
        ['أبو سمبل', 'ابو سمبل']),

    # --- EXTERNAL NEIGHBORS (for detecting Out-of-Upper-Egypt / Swapped pins) ---
    'Atfeeh (Giza)': ('Giza', 29.4050, 31.2480,
        [r'\batfeeh\b', r'\batfih\b', r'\bborombol\b', r'\bbramble\b', r'\bkuraimat\b', r'\braqqa\b'],
        ['أطفيح', 'اطفيح', 'البرمبل']),
    'Omrania (Giza)': ('Giza', 29.9990, 31.2010,
        [r'\bomrani?a\b', r'\bgiza\b'],
        ['العمرانية', 'الجيزة']),
    'El Alamein (Matrouh)': ('Marsa Matrouh', 30.8350, 28.9550,
        [r'\balamein\b', r'\balameen\b', r'\bnorth\s*coast\b', r'\bmarina\b', r'\bmatrouh\b'],
        ['العلمين', 'الساحل الشمالي', 'مارينا', 'مطروح']),
}

# =============================================================================
# 2. Haversine Distance & Open Location Code (Plus Code) Decoder
# =============================================================================
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(min(1.0, a)))

OLC_ALPHABET = "23456789CFGHJMPQRVWX"
OLC_MAP = {c: i for i, c in enumerate(OLC_ALPHABET)}

def decode_full_olc(code):
    code = code.upper().replace('+', '')
    lat = -90.0
    lon = -180.0
    lat_res = 400.0
    lon_res = 400.0
    # Pair resolution: 20, 1, 0.05, 0.0025, 0.000125
    pairs = min(len(code), 10)
    for i in range(0, pairs, 2):
        lat_res /= 20.0
        lon_res /= 20.0
        lat += OLC_MAP[code[i]] * lat_res
        lon += OLC_MAP[code[i+1]] * lon_res
    if len(code) > 10:
        for ch in code[10:]:
            lat_res /= 5.0
            lon_res /= 4.0
            idx = OLC_MAP[ch]
            lat += (idx // 4) * lat_res
            lon += (idx % 4) * lon_res
    return lat + lat_res / 2.0, lon + lon_res / 2.0

def encode_prefix_olc(lat, lon):
    lat = min(max(lat + 90.0, 0.0), 179.999999)
    lon = min(max(lon + 180.0, 0.0), 359.999999)
    d1_lat = int(lat // 20)
    d1_lon = int(lon // 20)
    d2_lat = int(lat % 20)
    d2_lon = int(lon % 20)
    return OLC_ALPHABET[d1_lat] + OLC_ALPHABET[d1_lon] + OLC_ALPHABET[d2_lat] + OLC_ALPHABET[d2_lon]

def decode_short_olc(short_code, ref_lat, ref_lon):
    """Recover full Plus Code (e.g. RVFX+9HR) nearest to (ref_lat, ref_lon)."""
    short_code = short_code.upper().strip()
    if '+' not in short_code:
        return None
    before_plus = short_code.split('+')[0]
    if len(before_plus) == 8:
        return decode_full_olc(short_code)
    if len(before_plus) != 4:
        return None
    # Try ref cell and 8 surrounding 1-degree cells to find closest recovery
    best = None
    best_d = 1e9
    for dlat in (-1, 0, 1):
        for dlon in (-1, 0, 1):
            pref = encode_prefix_olc(ref_lat + dlat, ref_lon + dlon)
            full = pref + short_code
            try:
                clat, clon = decode_full_olc(full)
                d = haversine_km(ref_lat, ref_lon, clat, clon)
                if d < best_d:
                    best_d = d
                    best = (clat, clon)
            except Exception:
                continue
    return best

PLUS_CODE_RE = re.compile(r'\b([23456789CFGHJMPQRVWX]{4,8}\+[23456789CFGHJMPQRVWX]{2,3})\b', re.I)

def normalize_district_name(dist_str, gov_str):
    if pd.isna(dist_str):
        return None
    s = str(dist_str).strip().lower()
    # Direct match
    for k, (g, lat, lon, en_pats, ar_pats) in DISTRICT_REF.items():
        if k.lower() == s:
            return k
    # Pattern match (prefer same governorate)
    for prefer_same_gov in (True, False):
        for k, (g, lat, lon, en_pats, ar_pats) in DISTRICT_REF.items():
            if prefer_same_gov and g != gov_str:
                continue
            for p in en_pats:
                if re.search(p, s, re.I):
                    return k
            for ap in ar_pats:
                if ap in str(dist_str):
                    return k
    return None

def extract_city_mentions(text_en, text_ar, gov_str):
    """Extract all distinct districts/cities explicitly mentioned in English/Arabic name or address."""
    hits = []
    combined_en = str(text_en or '')
    combined_ar = str(text_ar or '')
    for k, (g, lat, lon, en_pats, ar_pats) in DISTRICT_REF.items():
        matched = False
        for p in en_pats:
            if re.search(p, combined_en, re.I):
                matched = True
                break
        if not matched:
            for ap in ar_pats:
                if ap in combined_ar or ap in combined_en:
                    matched = True
                    break
        if matched:
            hits.append(k)
    return hits

def nearest_district(lat, lon):
    best_k, best_g, best_d = None, None, 1e9
    for k, (g, rlat, rlon, _, _) in DISTRICT_REF.items():
        d = haversine_km(lat, lon, rlat, rlon)
        if d < best_d:
            best_d = d
            best_k = k
            best_g = g
    return best_k, best_g, best_d

# =============================================================================
# 3. Load Data & Run All Checks
# =============================================================================
df_m = pd.read_csv(MASTER_CSV)
df_v = pd.read_csv(VAL_CSV)
df_f = pd.read_csv(FLAGS_CSV)

df = df_m.merge(
    df_v[['canonical_entity_id', 'original_arabic_name', 'coord_reliable', 'n_same_coord', 'tier_classification']],
    on='canonical_entity_id', how='left'
).merge(
    df_f[['canonical_entity_id', 'spatial_status', 'inferred_true_governorate', 'coord_cluster_id']],
    on='canonical_entity_id', how='left'
)

# List of 50 previously snapped IDs from impute_and_sync_pipeline.py
SNAPPED_50 = {
    'CE00055','CE00056','CE00057','CE00058','CE00059','CE00060','CE00054','CE00061',
    'CE00064','CE00067','CE00069','CE00070','CE00071','CE00072','CE00073','CE00074','CE00075',
    'CE00100','CE00101','CE00102','CE00103','CE00104','CE00105','CE00106','CE00107','CE00108',
    'CE00124','CE00125','CE00126','CE00127','CE00128','CE00129','CE00133',
    'CE00081','CE00082','CE00084','CE00085','CE00086','CE00087','CE00088','CE00089','CE00090','CE00091','CE00092','CE00094',
    'CE00112','CE00113','CE00114','CE00115','CE00116'
}

results = []
for idx, r in df.iterrows():
    cid = r['canonical_entity_id']
    cname = str(r['canonical_name'])
    arname = str(r['original_arabic_name'])
    gov = str(r['governorate_assigned'])
    dist_raw = str(r['district'])
    addr = str(r['address'])
    lat = float(r['latitude_final'])
    lon = float(r['longitude_final'])
    src = str(r['source_files_all'])

    # 1. GPS nearest town
    gps_dist, gps_gov, gps_dist_km = nearest_district(lat, lon)

    # 2. Assigned district match
    assigned_norm = normalize_district_name(dist_raw, gov)
    if assigned_norm and assigned_norm in DISTRICT_REF:
        a_gov, a_lat, a_lon, _, _ = DISTRICT_REF[assigned_norm]
        dist_to_assigned_km = haversine_km(lat, lon, a_lat, a_lon)
    else:
        a_gov = gov
        dist_to_assigned_km = -1.0

    # 3. City mentions in Name (English + Arabic) and Address
    name_cities = extract_city_mentions(cname, arname, gov)
    addr_cities = extract_city_mentions(addr, addr, gov)

    # Filter out generic governorate capital name if a more specific district in that gov is also mentioned
    def refine_cities(clist):
        if len(clist) > 1:
            gov_capitals = {'Beni Suef', 'Minya', 'Assiut', 'Sohag', 'Qena', 'Luxor', 'Aswan'}
            non_cap = [c for c in clist if c not in gov_capitals]
            if non_cap:
                return non_cap
        return clist

    name_cities_ref = refine_cities(name_cities)
    addr_cities_ref = refine_cities(addr_cities)

    # Distance to closest named city
    min_name_city = ''
    min_name_city_km = -1.0
    if name_cities_ref:
        best_nc = min(name_cities_ref, key=lambda c: haversine_km(lat, lon, DISTRICT_REF[c][1], DISTRICT_REF[c][2]))
        min_name_city = best_nc
        min_name_city_km = haversine_km(lat, lon, DISTRICT_REF[best_nc][1], DISTRICT_REF[best_nc][2])

    # Distance to closest address city
    min_addr_city = ''
    min_addr_city_km = -1.0
    if addr_cities_ref:
        best_ac = min(addr_cities_ref, key=lambda c: haversine_km(lat, lon, DISTRICT_REF[c][1], DISTRICT_REF[c][2]))
        min_addr_city = best_ac
        min_addr_city_km = haversine_km(lat, lon, DISTRICT_REF[best_ac][1], DISTRICT_REF[best_ac][2])

    # 4. Plus Code check & Swapped Lat/Lon check
    m_olc = PLUS_CODE_RE.search(addr)
    plus_code = m_olc.group(1).upper() if m_olc else ''
    plus_code_delta_km = -1.0
    swapped_match = False
    if plus_code:
        dec = decode_short_olc(plus_code, lat, lon)
        if dec:
            plus_code_delta_km = haversine_km(lat, lon, dec[0], dec[1])
        # Also test swapped lat/lon against Plus Code!
        dec_swap = decode_short_olc(plus_code, lon, lat)
        if dec_swap:
            swap_delta = haversine_km(lon, lat, dec_swap[0], dec_swap[1])
            if swap_delta < 0.5 and plus_code_delta_km > 1.0:
                swapped_match = True

    # 5. Flag logic
    flags = []
    if swapped_match:
        flags.append('SWAPPED_LAT_LON_CONFIRMED_BY_PLUSCODE')
    if plus_code_delta_km > 1.0 and not swapped_match:
        flags.append(f'PLUSCODE_MISMATCH({plus_code_delta_km:.1f}km)')
    if min_name_city and min_name_city_km > 18.0:
        flags.append(f'NAME_CITY_MISMATCH(named={min_name_city},dist={min_name_city_km:.1f}km,gps_near={gps_dist})')
    if min_addr_city and min_addr_city_km > 22.0:
        flags.append(f'ADDR_CITY_MISMATCH(addr={min_addr_city},dist={min_addr_city_km:.1f}km,gps_near={gps_dist})')
    if dist_to_assigned_km > 25.0:
        flags.append(f'ASSIGNED_DIST_FAR(assigned={assigned_norm},dist={dist_to_assigned_km:.1f}km,gps_near={gps_dist})')
    if gps_gov != gov and gps_dist_km < 15.0:
        # Check if truly closer to another governorate's town
        if dist_to_assigned_km < 0 or gps_dist_km + 5.0 < dist_to_assigned_km:
            flags.append(f'GPS_NEAR_OTHER_GOV(gps_gov={gps_gov},gps_dist={gps_dist}:{gps_dist_km:.1f}km)')
    if assigned_norm is None:
        flags.append(f'UNMAPPED_DISTRICT({dist_raw})')
    if str(r['spatial_status']) == 'OUT_OF_BOUNDS':
        flags.append('FLAGGED_OUT_OF_BOUNDS')
    if cid in SNAPPED_50:
        flags.append('PREV_SNAPPED_50')

    # Severity
    critical_flags = [f for f in flags if f != 'PREV_SNAPPED_50']
    severity = 'CRITICAL' if any(
        f.startswith(('SWAPPED_', 'PLUSCODE_MISMATCH', 'NAME_CITY_MISMATCH', 'ADDR_CITY_MISMATCH', 'FLAGGED_OUT_OF_BOUNDS'))
        for f in critical_flags
    ) else ('REVIEW' if critical_flags else 'OK')

    results.append({
        'canonical_entity_id': cid,
        'canonical_name': cname,
        'original_arabic_name': arname,
        'source_files_all': src,
        'governorate_assigned': gov,
        'district_raw': dist_raw,
        'district_norm': assigned_norm or '',
        'latitude_final': lat,
        'longitude_final': lon,
        'gps_nearest_district': gps_dist,
        'gps_nearest_gov': gps_gov,
        'gps_nearest_km': round(gps_dist_km, 2),
        'dist_to_assigned_km': round(dist_to_assigned_km, 2),
        'name_city': min_name_city,
        'name_city_km': round(min_name_city_km, 2),
        'addr_city': min_addr_city,
        'addr_city_km': round(min_addr_city_km, 2),
        'plus_code': plus_code,
        'plus_code_delta_km': round(plus_code_delta_km, 3),
        'was_snapped_50': cid in SNAPPED_50,
        'severity': severity,
        'flags': ' | '.join(flags) if flags else 'OK',
        'address': addr
    })

out_df = pd.DataFrame(results)
out_df.to_csv(OUT_CSV, index=False, encoding='utf-8')

print("=== PHASE 1 CITY-LEVEL COORDINATE AUDIT SUMMARY (N = 798) ===")
print(out_df['severity'].value_counts().to_string())
print("\n--- CRITICAL FLAGS ---")
crit = out_df[out_df['severity'] == 'CRITICAL']
print(f"Total CRITICAL rows: {len(crit)}")
for _, row in crit.iterrows():
    print(f"  {row['canonical_entity_id']} | {row['canonical_name']} ({row['original_arabic_name']}) | Gov={row['governorate_assigned']} Dist={row['district_raw']} | GPS=({row['latitude_final']:.5f},{row['longitude_final']:.5f}) near {row['gps_nearest_district']} ({row['gps_nearest_km']}km) | {row['flags']}")

print("\n--- REVIEW FLAGS ---")
rev = out_df[out_df['severity'] == 'REVIEW']
print(f"Total REVIEW rows: {len(rev)}")
for _, row in rev.iterrows():
    print(f"  {row['canonical_entity_id']} | {row['canonical_name']} ({row['original_arabic_name']}) | Gov={row['governorate_assigned']} Dist={row['district_raw']} | GPS=({row['latitude_final']:.5f},{row['longitude_final']:.5f}) near {row['gps_nearest_district']} ({row['gps_nearest_km']}km) | {row['flags']}")

print("\n--- AUDIT OF ALL 50 PREVIOUSLY SNAPPED ROWS ---")
sn = out_df[out_df['was_snapped_50']]
for _, row in sn.iterrows():
    print(f"  {row['canonical_entity_id']} | {row['canonical_name']} | Assigned={row['district_raw']} ({row['dist_to_assigned_km']}km) | GPS near={row['gps_nearest_district']} ({row['gps_nearest_km']}km) | NameCity={row['name_city']} ({row['name_city_km']}km) | Addr={row['address'][:75]}")
