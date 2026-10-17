import os
import re
import json
import time
import urllib.request
import urllib.parse
import concurrent.futures
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

ARABIC_RE = re.compile(r'[\u0600-\u06ff]')
DASH_RE = re.compile(r'[\u2014\u2013—–]')
EMOJI_RE = re.compile(
    r'[\U00010000-\U0010ffff]'
    r'|[\u2600-\u27bf]'
    r'|[\u2300-\u23ff]'
    r'|[\u2b50-\u2b55]'
    r'|[\u203c-\u2049]'
)

def clean_text(text):
    if not text or pd.isna(text):
        return text
    s = str(text)
    s = DASH_RE.sub('-', s)
    s = EMOJI_RE.sub('', s)
    s = s.replace('،', ', ')
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r' ,', ',', s)
    s = re.sub(r',+', ',', s)
    return s.strip()

SPECIAL_NAMES = {
    'As-Salam International Hospital Assiut Branch العيادات التخصصية لمستشفي السلام الدولي بأسيوط': 'As-Salam International Hospital Assiut Branch - Specialized Clinics',
    'Elsafwa Specialized hospital مستشفى الصفوة التخصصي': 'Elsafwa Specialized Hospital',
    'Evangelical Mission Hospital, Al-Germaniyya. مستشفى الجرمانية': 'Evangelical Mission Hospital, Al-Germaniyya',
    'Mariam Center مركز مريم للنساء والتوليد': 'Mariam Center for Obstetrics and Gynecology',
    'NBE ATM - Central facility hospital - مستشفى المنشأة المركزى': 'NBE ATM - Al Monshaah Central Hospital',
    'NBE ATM - Daraw Central Hospital - مستشفى دراو المركزى': 'NBE ATM - Daraw Central Hospital',
    'NBE ATM - Good Shepherd Hospital - El Menia - مستشفى الراعى الصالح - المنيا': 'NBE ATM - Good Shepherd Hospital - El Menia',
    'Ritaj Specialized Hospital | مستشفى ريتاج التخصصي': 'Ritaj Specialized Hospital',
    'Sara Center For Obs. & Gyna Sohag مركز سارة للنساء والتوليد وجراحات المناظير بسوهاج': 'Sara Center For Obs. & Gyna Sohag - Center for Obstetrics, Gynecology and Laparoscopy',
    'Sohag Military Hospital مستشفي سوهاج العسكري': 'Sohag Military Hospital',
    'مستشفى الأقصر التخصصي Luxor Specialized Hospital': 'Luxor Specialized Hospital',
    'مستشفى الإصابات جامعة اسيوط Trauma Hospital Assiut University': 'Trauma Hospital Assiut University',
    'مستشفى جنات JANNAT': 'Jannat Hospital',
    'مستشفى نفرتاري | Nefertari Hospital': 'Nefertari Hospital',
    'مستشفي النور التخصصي - Al Noor Hosptial': 'Al Noor Specialized Hospital',
    'مستشفي قنا الجامعي بالمعبر Qina university hospita at Maabar Ash-Shabab': 'Qena University Hospital at Maabar Ash-Shabab',
    'مستشفي نورالأملnooralamalhospital': 'Noor Al-Amal Hospital',
    'اسمالك المرسي': 'Asmak Al-Morsi',
    'عدد 19 مستشفى': 'Total 19 Hospitals',
    'ابنوب المركزى': 'Abnoub Central Hospital',
    'ابو تشت المركزى': 'Abu Tesht Central Hospital',
    'ابو تيج المركزى': 'Abu Tij Central Hospital',
    'اخميم المركزى': 'Akhmim Central Hospital',
    'ادفو العام': 'Edfu General Hospital',
    'ارمنت المركزى': 'Armant Central Hospital',
    'اسنا المركزى': 'Esna Central Hospital',
    'اسيوط العام': 'Assiut General Hospital',
    'البدارى المركزى': 'Al Badari Central Hospital',
    'البلينا المركزى': 'Al Balyana Central Hospital',
    'الفشن المركزى': 'Al Fashn Central Hospital',
    'القرنة المركزى': 'Al Qurna Central Hospital',
    'القوصية المركزى': 'Al Qusiya Central Hospital',
    'المراغة المركزى': 'Al Maragha Central Hospital',
    'المنشاة المركزى': 'Al Monshaah Central Hospital',
    'الواسطى المركزى': 'Al Wasta Central Hospital',
    'الوقف المركزى': 'Al Waqf Central Hospital',
    'ببا المركزى': 'Biba Central Hospital',
    'جرجا العام': 'Girga General Hospital',
    'جهينة المركزى': 'Juhayna Central Hospital',
    'دار السلام المركزى': 'Dar El Salam Central Hospital',
    'دراو المركزى': 'Daraw Central Hospital',
    'دشنا المركزى': 'Dishna Central Hospital',
    'ديروط المركزى': 'Dairut Central Hospital',
    'ساحل سليم المركزى': 'Sahel Selim Central Hospital',
    'ساقلته المركزى': 'Saqalta Central Hospital',
    'سمسطا المركزى': 'Sumusta Central Hospital',
    'سوهاج العام': 'Sohag General Hospital',
    'صدفا المركزى': 'Sidfa Central Hospital',
    'طما المركزى': 'Tima Central Hospital',
    'طهطا العام': 'Tahta General Hospital',
    'فرشوط المركزى': 'Farshut Central Hospital',
    'قنا العام': 'Qena General Hospital',
    'قوص المركزى': 'Qus Central Hospital',
    'كوم امبو العام': 'Kom Ombo General Hospital',
    'منفلوط المركزى': 'Manfalut Central Hospital',
    'ناصر العام': 'Nasser General Hospital',
    'نجع حمادى العام': 'Nag Hammadi General Hospital',
    'نقادة المركزى': 'Naqada Central Hospital'
}

DISTRICT_MAP = {
    '،': None,
    'أبو تشت': 'Abu Tesht',
    'أبو تيج': 'Abu Tig',
    'أول المنيا': 'First Minya',
    'ابنوب': 'Abnoub',
    'ابو تشت': 'Abu Tesht',
    'ابو تيج': 'Abu Tig',
    'اخميم': 'Akhmim',
    'ادفو': 'Edfu',
    'ارمنت': 'Armant',
    'اسنا': 'Esna',
    'اسوان': 'Aswan',
    'الاجمالى': 'Total',
    'الاقصر': 'Luxor',
    'البدارى': 'Al Badari',
    'البلينا': 'Al Balyana',
    'العمرانية': 'Al Omraniya',
    'الغنايم': 'Al Ghanayem',
    'الفشن': 'Al Fashn',
    'القرنة': 'Al Qurna',
    'القوصية': 'Al Qusiya',
    'المراغة': 'Al Maragha',
    'المنشاة': 'Al Monshaah',
    'الواسطى': 'Al Wasta',
    'الوقف': 'Al Waqf',
    'اهناسيا': 'Ihnasiya',
    'اول': 'First District',
    'ببا': 'Biba',
    'بندر الاقصر': 'Luxor City',
    'بنى سويف': 'Beni Suef',
    'جرجا': 'Girga',
    'جهينة': 'Juhayna',
    'حي الزهور': 'Al Zohour District',
    'دار السلام': 'Dar El Salam',
    'دراو': 'Daraw',
    'دشنا': 'Dishna',
    'ديروط': 'Dairut',
    'ساحل سليم': 'Sahel Selim',
    'ساقلته': 'Saqalta',
    'سمالوط شرق': 'East Samalut',
    'سمسطا': 'Sumusta',
    'سوهاج': 'Sohag',
    'شرق اسيوط': 'East Assiut',
    'شرق النيل': 'East Nile',
    'صدفا': 'Sidfa',
    'طما': 'Tima',
    'طهطا': 'Tahta',
    'غرب اسيوط': 'West Assiut',
    'فرشوط': 'Farshut',
    'فرشوط،': 'Farshut',
    'فقط': 'Qift',
    'قسم أول سوهاج': 'First Sohag District',
    'قسم ثان أسيوط': 'Second Assiut District',
    'قسم ثان سوهاج': 'Second Sohag District',
    'قسم طهطا': 'Tahta District',
    'قسم مدينة جرجا': 'Girga City District',
    'قنا': 'Qena',
    'قوص': 'Qus',
    'كوم امبو': 'Kom Ombo',
    'مدينة البياضية': 'Al Bayadiya City',
    'مركز أخميم': 'Akhmim Center',
    'مركز ابو قرقاص': 'Abu Qurqas Center',
    'مركز الأقصر': 'Luxor Center',
    'مركز الاقصر': 'Luxor Center',
    'مركز المنشأة،': 'Al Monshaah Center',
    'مركز المنيا': 'Minya Center',
    'مركز المنيا،': 'Minya Center',
    'مركز بنى سويف': 'Beni Suef Center',
    'مركز بنى مزار': 'Bani Mazar Center',
    'مركز بنى مزار،': 'Bani Mazar Center',
    'مركز سوهاج': 'Sohag Center',
    'مركز قنا': 'Qena Center',
    'مركز مغاغة': 'Maghagha Center',
    'منفلوط': 'Manfalut',
    'ناصر': 'Nasser',
    'نجع حمادى': 'Nag Hammadi',
    'نصر': 'Nasr',
    'نقادة': 'Naqada'
}

ALT_MAP = {
    'التأمين الصحي - فرع قنا': 'Health Insurance - Qena Branch',
    'المستشفى الجامعي بقنا - جنوب الوادي': 'Qena University Hospital - South Valley',
    'م المراغة العام': 'Al Maragha General Hospital',
    'مستشفى أبو تشت العام': 'Abu Tesht General Hospital',
    'مستشفى أبو قرقاص المركزي': 'Abu Qurqas Central Hospital',
    'مستشفى اخميم المركزى': 'Akhmim Central Hospital',
    'مستشفى الاقصر العام': 'Luxor General Hospital',
    'مستشفى العدوة العام': 'Al Idwa General Hospital',
    'مستشفى الكاشف التخصصي': 'Al Kashef Specialized Hospital',
    'مستشفى المنيا الأميري': 'Minya Amiri Hospital',
    'مستشفى النيل التخصصى': 'Nile Specialized Hospital',
    'مستشفى الهلال للتأمين الصحي': 'Al Hilal Health Insurance Hospital',
    'مستشفى الوقف': 'Al Waqf Hospital',
    'مستشفى اولاد حمزة المركزى | مستشفى العسيرات المركزى': 'Awlad Hamza Central Hospital | Al Oseirat Central Hospital',
    'مستشفى بني مزار العام': 'Bani Mazar General Hospital',
    'مستشفى جامعة المنيا العام': 'Minya University General Hospital',
    'مستشفى جزيرة شندويل المركزى': 'Jazirat Shandawil Central Hospital',
    'مستشفى دشنا العام': 'Dishna General Hospital',
    'مستشفى دكتور محمد شندى': 'Dr. Mohamed Shendi Hospital',
    'مستشفى دير مواس التخصصي': 'Deir Mawas Specialized Hospital',
    'مستشفى روفان': 'Rovan Hospital',
    'مستشفى سمالوط النموذجي | سمالوط المركزي سابقاً': 'Samalut Model Hospital | Formerly Samalut Central',
    'مستشفى سوزان مبارك الجامعي للنساء والأطفال | جامعة المنيا': 'Maternity and Children University Hospital | Minya University',
    'مستشفى سوهاج العام(الاميري)': 'Sohag General Hospital (Amiri)',
    'مستشفى صحة المرأة - جامعة جنوب الوادي': 'Womens Health Hospital - South Valley University',
    'مستشفى فرشوط العام': 'Farshut General Hospital',
    'مستشفى قنا الأميري': 'Qena Amiri Hospital',
    'مستشفى قوص العام': 'Qus General Hospital',
    'مستشفى مبرة المنيا': 'Mabarret El Minya Hospital',
    'مستشفى مطاي العام': 'Matay General Hospital',
    'مستشفى مغاغة العام': 'Maghagha General Hospital',
    'مستشفى ملوي النموذجي | ملوي المركزي سابقاً': 'Mallawi Model Hospital | Formerly Mallawi Central',
    'مستشفى نجع حمادي المركزي': 'Nag Hammadi Central Hospital',
    'مستشفى نقادة العام': 'Naqada General Hospital',
    'مستشفي المنشاه المركزي': 'Al Monshaah Central Hospital',
    'مستشفي جهينة النموذجي': 'Juhayna Model Hospital',
    'مستشفي دراو المركزي': 'Daraw Central Hospital',
    'مستشفي ساقلتة المركزى': 'Saqalta Central Hospital',
    'مستشفي سوهاج التعليمي': 'Sohag Teaching Hospital',
    'مستشفي سوهاج الجامعي': 'Sohag University Hospital',
    'مستشفي سوهاج الجامعي الجديد': 'New Sohag University Hospital',
    'مستشفي كيلوباترا- | مستشفي كيلوباترا-الاسم: مستشفى كليوباترا-': 'Cleopatra Hospital'
}

def call_mymemory(text):
    q = urllib.parse.quote(text)
    url = f'https://api.mymemory.translated.net/get?q={q}&langpair=ar|en&de=yousm99@gmail.com'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                res = data.get('responseData', {}).get('translatedText')
                if res:
                    return clean_text(res)
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    return None

def batch_translate(items, cache_file, special_map=None):
    cache = {}
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache = json.load(f)

    if special_map:
        for k, v in special_map.items():
            cache[k] = clean_text(v)

    todo = [item for item in items if item not in cache]
    print(f'Total items: {len(items)}, Already cached: {len(items) - len(todo)}, Todo: {len(todo)}')

    if not todo:
        return cache

    def worker(item):
        trans = call_mymemory(item)
        time.sleep(0.15)
        return item, trans

    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_to_item = {executor.submit(worker, item): item for item in todo}
        for future in concurrent.futures.as_completed(future_to_item):
            item, trans = future.result()
            if trans and not ARABIC_RE.search(trans):
                cache[item] = trans
            elif trans:
                cache[item] = trans
            else:
                print(f'Failed to translate: {item}')
            completed += 1
            if completed % 25 == 0 or completed == len(todo):
                print(f'Progress: {completed}/{len(todo)} ({(completed/len(todo))*100:.1f}%)')
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)

    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    return cache

if __name__ == '__main__':
    print('Starting translation pipeline...')
    df = pd.read_csv(DATASET_PATH)

    arabic_names = sorted(list(set(df['canonical_name'].dropna().astype(str).loc[lambda s: s.apply(lambda x: bool(ARABIC_RE.search(x)))])))
    arabic_addrs = sorted(list(set(df['address'].dropna().astype(str).loc[lambda s: s.apply(lambda x: bool(ARABIC_RE.search(x)))])))

    print(f'Translating {len(arabic_names)} unique names...')
    names_cache = batch_translate(arabic_names, NAMES_CACHE_PATH, SPECIAL_NAMES)

    print(f'Translating {len(arabic_addrs)} unique addresses...')
    addrs_cache = batch_translate(arabic_addrs, ADDRS_CACHE_PATH)

    print('Batch translation phase completed.')
