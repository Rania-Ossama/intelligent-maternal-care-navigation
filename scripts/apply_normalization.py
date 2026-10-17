import os
import re
import json
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)

DATASET_PATH = os.path.join(PARENT_DIR, 'facilities_sorted_by_governorate.csv')
if not os.path.exists(DATASET_PATH):
    DATASET_PATH = os.path.join(PARENT_DIR, 'datasets', 'facilities_sorted_by_governorate.csv')

NAMES_CACHE_PATH = os.path.join(PARENT_DIR, 'datasets', 'translation_cache_names.json')
if not os.path.exists(os.path.dirname(NAMES_CACHE_PATH)):
    NAMES_CACHE_PATH = os.path.join(PARENT_DIR, 'translation_cache_names.json')

ADDRS_CACHE_PATH = os.path.join(PARENT_DIR, 'datasets', 'translation_cache_addrs.json')
if not os.path.exists(os.path.dirname(ADDRS_CACHE_PATH)):
    ADDRS_CACHE_PATH = os.path.join(PARENT_DIR, 'translation_cache_addrs.json')

REPO_DEST_PATH = os.path.join(PARENT_DIR, 'repo_work', 'facilities_sorted_by_governorate.csv')

ARABIC_RE = re.compile(r'[\u0600-\u06ff]')
DASH_RE = re.compile(r'[\u2014\u2013—–]')
EMOJI_RE = re.compile(
    r'[\U00010000-\U0010ffff]'
    r'|[\u2600-\u27bf]'
    r'|[\u2300-\u23ff]'
    r'|[\u2b50-\u2b55]'
    r'|[\u203c-\u2049]'
)

def clean_text(val):
    if val is None or pd.isna(val):
        return val
    s = str(val)
    s = DASH_RE.sub('-', s)
    s = EMOJI_RE.sub('', s)
    s = s.replace('،', ', ')
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r' ,', ',', s)
    s = re.sub(r',+', ',', s)
    return s.strip()

from translate_dataset import DISTRICT_MAP, ALT_MAP, SPECIAL_NAMES

SPECIAL_NAMES.update({
    'السلام': 'Al Salam Hospital',
    'قفط المركزى': 'Qift Central Hospital',
    'اولاد حمزه المركزى': 'Awlad Hamza Central Hospital',
    'مستشفى البلابيش بحري': 'Al Balabish Bahri Hospital',
    'رعاية الامومة والطفولة بالمنشاة': 'Maternal and Child Health Center in Al Monshaah',
    'مستشفى التكامل بأولاد يحيى الحاجر': 'Al Takamol Hospital in Awlad Yehia Al Hajer',
    'مًسِتٌشُفُﮯ بًنِيَ سِوٌيَفُ آلَعٌآمً': 'Beni Suef General Hospital',
    'َمستشفي الفجر التخصصي': 'Al Fajr Specialized Hospital',
    'اسمالك المرسي': 'Asmak Al-Morsi'
})

SPECIAL_ADDRS = {
    'الزواليك الغربية، مركز المنشأة': 'Al-Zawalek Al-Gharbiyya, Al Monshaah Center',
    'اولاد حمزه - العسيرات': 'Awlad Hamza - Al Oseirat'
}

def normalize_dataset():
    df = pd.read_csv(DATASET_PATH)
    orig_shape = df.shape
    orig_cols = list(df.columns)
    print(f'Original dataset shape: {orig_shape}')

    names_cache = {}
    if os.path.exists(NAMES_CACHE_PATH):
        with open(NAMES_CACHE_PATH, 'r', encoding='utf-8') as f:
            names_cache = json.load(f)
    names_cache.update(SPECIAL_NAMES)

    addrs_cache = {}
    if os.path.exists(ADDRS_CACHE_PATH):
        with open(ADDRS_CACHE_PATH, 'r', encoding='utf-8') as f:
            addrs_cache = json.load(f)
    addrs_cache.update(SPECIAL_ADDRS)

    def normalize_district(d):
        if pd.isna(d):
            return d
        d_str = str(d).strip()
        if d_str in DISTRICT_MAP:
            return DISTRICT_MAP[d_str]
        return clean_text(d_str)

    df['district'] = df['district'].apply(normalize_district)

    def normalize_alt(a):
        if pd.isna(a):
            return a
        a_str = str(a).strip()
        if a_str in ALT_MAP:
            return ALT_MAP[a_str]
        return clean_text(a_str)

    df['alternate_names'] = df['alternate_names'].apply(normalize_alt)

    def normalize_name(n):
        if pd.isna(n):
            return n
        n_str = str(n).strip()
        if n_str in names_cache:
            return clean_text(names_cache[n_str])
        return clean_text(n_str)

    df['canonical_name'] = df['canonical_name'].apply(normalize_name)

    def normalize_addr(a):
        if pd.isna(a):
            return a
        a_str = str(a).strip()
        if a_str in addrs_cache:
            return clean_text(addrs_cache[a_str])
        return clean_text(a_str)

    df['address'] = df['address'].apply(normalize_addr)

    for col in df.columns:
        if df[col].dtype == object or df[col].dtype == 'string':
            df[col] = df[col].apply(clean_text)

    arabic_count = 0
    dash_count = 0
    emoji_count = 0
    for col in df.columns:
        s = df[col].dropna().astype(str)
        ar_matches = s[s.apply(lambda x: bool(ARABIC_RE.search(x)))]
        dash_matches = s[s.apply(lambda x: bool(DASH_RE.search(x)))]
        emoji_matches = s[s.apply(lambda x: bool(EMOJI_RE.search(x)))]
        arabic_count += len(ar_matches)
        dash_count += len(dash_matches)
        emoji_count += len(emoji_matches)
        if len(ar_matches) > 0:
            print(f'Remaining Arabic in {col}: {list(ar_matches.unique())}')

    print(f'Verification Results:')
    print(f'- Arabic occurrences: {arabic_count}')
    print(f'- Em/en-dash occurrences: {dash_count}')
    print(f'- Emoji occurrences: {emoji_count}')
    print(f'- Total rows: {len(df)}')
    print(f'- Total columns: {len(df.columns)}')

    assert arabic_count == 0, f'Found {arabic_count} remaining Arabic strings!'
    assert dash_count == 0, f'Found {dash_count} remaining dashes!'
    assert emoji_count == 0, f'Found {emoji_count} remaining emojis!'
    assert df.shape == orig_shape, f'Shape mismatch: {df.shape} vs {orig_shape}'
    assert list(df.columns) == orig_cols, f'Columns mismatch'

    df.to_csv(DATASET_PATH, index=False, encoding='utf-8')
    print(f'Saved normalized dataset to {DATASET_PATH}')

    if os.path.exists(os.path.dirname(REPO_DEST_PATH)):
        df.to_csv(REPO_DEST_PATH, index=False, encoding='utf-8')
        print(f'Saved normalized dataset to {REPO_DEST_PATH}')

    return df

if __name__ == '__main__':
    df = normalize_dataset()
    print('Normalization completed successfully!')
