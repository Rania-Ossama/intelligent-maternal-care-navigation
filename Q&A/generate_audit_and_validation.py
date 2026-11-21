import os
import re
import io
import csv
import json
import shutil
import subprocess
import pandas as pd

BASE_DIR = '/home/yousefmahmoudali/Desktop/GradII'
QA_DIR = os.path.join(BASE_DIR, 'Q&A')
REPO_DIR = os.path.join(BASE_DIR, 'repo_work')
os.makedirs(QA_DIR, exist_ok=True)
os.makedirs(os.path.join(REPO_DIR, 'Q&A'), exist_ok=True)

df_en = pd.read_csv(os.path.join(BASE_DIR, 'datasets', 'facilities_sorted_by_governorate.csv'))
df_ar = pd.read_csv(os.path.join(REPO_DIR, 'final_maternal_facilities_clean.csv'))

csv_bytes = subprocess.check_output([
    'git', '-C', REPO_DIR, 'show',
    'origin/GIS-Features:Enhanced Dijkstra Algorithms/facilities_flagged.csv'
])
df_flag = pd.read_csv(io.BytesIO(csv_bytes))

orig_22_cols = [
    'canonical_entity_id', 'canonical_name', 'governorate_assigned', 'district', 'address',
    'phone_clean', 'phone_type', 'phones_other', 'phone_e164', 'latitude_final', 'longitude_final',
    'facility_class', 'birth_service_tier', 'alternate_names', 'facility_category',
    'birth_service_evidence', 'phone', 'phones_normalized_all', 'source_files_all',
    'source_files', 'source_count', 'n_source_records_total'
]
df_master_orig = df_en[orig_22_cols].copy()

df = df_master_orig.merge(
    df_ar[['canonical_entity_id', 'canonical_name', 'name_check', 'same_location_as']],
    on='canonical_entity_id',
    suffixes=('', '_ar')
).merge(
    df_flag[['canonical_entity_id', 'n_same_coord', 'coord_reliable']],
    on='canonical_entity_id'
)

VERIFICATION_DATE = '2026-10-24'

emoji_pattern = re.compile(r'[\U00010000-\U0010ffff]', flags=re.UNICODE)

def clean_text(val):
    if isinstance(val, str):
        v = emoji_pattern.sub('', val)
        v = v.replace('\u2014', '-').replace('\u2013', '-')
        return v.strip() if v != val else val
    return val

VERIFIED_CEMONC_IDS = {
    'CE01955': ('Verified_University_Maternal_Hospital', 'Assiut University Womens Health Hospital; SCUH & Assiut University Official Records'),
    'CE00929': ('Verified_University_Maternal_Hospital_Duplicate', 'Duplicate scrape of CE01955 Assiut University Womens Health Hospital'),
    'CE01907': ('Verified_University_Maternal_Hospital', 'Minya University Maternity and Children Hospital; Minya University Official Records'),
    'CE01934': ('Verified_University_Maternal_Hospital', 'South Valley University Womens Health Hospital Qena; SVU Official Records'),
    'CE00028': ('Verified_UHIA_Maternal_Hospital', 'Isis Specialized Maternity Hospital Luxor; EHA/UHIA & GAHAR Official Records (70 beds, 10 ICU, 22 NICU, 4 ORs)'),
    'CE00009': ('Verified_University_General_Hospital', 'Beni Suef University Hospital; Law 19/2018 & Beni Suef University Official Records'),
    'CE00001': ('Verified_University_General_Hospital_Duplicate', 'Generic-name duplicate of CE00009 Beni Suef University Hospital (same_location_as=CE00009)'),
    'CE01908': ('Verified_University_General_Hospital', 'Minya Main University Hospital; Law 19/2018 & Minya University Official Records'),
    'CE01928': ('Verified_University_General_Hospital_Duplicate', 'Duplicate record of CE01908 Minya University Hospital'),
    'CE01969': ('Verified_University_General_Hospital', 'Assiut University Main Hospital; Law 19/2018 & Assiut University Official Records'),
    'CE01982': ('Verified_University_General_Hospital_Duplicate', 'OSM duplicate of CE01969 Assiut University Hospital'),
    'CE01957': ('Verified_University_General_Hospital', 'Sohag University Hospital Old Campus; Law 19/2018 & Sohag University Official Records'),
    'CE01967': ('Verified_University_General_Hospital', 'New Sohag University Hospital; Law 19/2018 & Sohag University Official Records'),
    'CE00005': ('Verified_University_General_Hospital', 'South Valley University Hospitals Qena (Maabar & Campus); Law 19/2018 & SVU Records'),
    'CE01935': ('Verified_University_General_Hospital_Duplicate', 'Duplicate Qena registry record of CE00005 South Valley University Hospitals'),
    'CE00007': ('Verified_University_General_Hospital', 'Aswan University Hospital; Law 19/2018 & Aswan University Official Records'),
    'CE00014': ('Verified_University_General_Hospital_Duplicate', 'Duplicate record of CE00007 Aswan University Hospital'),
    'CE00030': ('Verified_UHIA_General_Hospital', 'Karnak International Hospital Luxor; EHA/UHIA & GAHAR Accredited Tertiary Hospital'),
    'CE00021': ('Verified_UHIA_General_Hospital', 'Taibah Specialized Hospital Esna Luxor; EHA/UHIA Accredited General Hospital'),
    'CE00022': ('Verified_UHIA_General_Hospital', 'Horus Specialized Hospital Armant Luxor; EHA/UHIA Accredited General Hospital'),
    'CE00044': ('Verified_UHIA_General_Hospital', 'Nile Specialized Hospital Edfu Aswan; EHA/UHIA General Hospital'),
    'CE00042': ('Verified_UHIA_General_Hospital', 'Abu Simbel International Hospital Aswan; EHA/UHIA & SMC Hospital'),
}

CONFLICTING_OR_NON_HOSPITAL_IDS = {
    'CE00130': ('Non_Hospital_Summary_Row', 'MOHP Excel table summary row (Total 19 Hospitals / الاجمالى) ingested as public_general_hospital'),
    'CE00013': ('Planned_Under_Construction_Hospital', 'Luxor University Hospital is explicitly marked (under construction / قيد الإنشاء; planned_not_operational in univ source)'),
    'CE01966': ('Non_Maternal_University_Hospital_Mislabeled', 'Umm Al-Qusour Hospital Assiut is a chest/rehabilitation facility mislabeled as university_maternal_hospital in registry'),
    'CE01965': ('University_Hospital_Mislabeled_Maternal', 'New Assiut University Hospital is a general/pediatric/trauma university branch mislabeled as university_maternal_hospital'),
    'CE00117': ('Place_Name_Only_Artifact', 'Name is only a village place name (Al-Deir / الدير) flagged as name_is_only_a_place'),
    'CE00133': ('Place_Name_Only_Artifact', 'Name is only a governorate place name (Aswan / اسوان) flagged as name_is_only_a_place at shared centroid'),
    'CE00501': ('Place_Name_Only_Artifact', 'Name is only a district place name (Biba) flagged as name_is_only_a_place'),
    'CE01675': ('Generic_Name_Only_Artifact', 'Bare generic word Hospital (مستشفى) in Qena flagged as generic_name'),
    'CE02015': ('Generic_Name_Only_Artifact', 'Bare generic word Hospital (مستشفى) in Sohag flagged as generic_name'),
    'CE00708': ('Non_Hospital_ATM', 'National Bank of Egypt ATM machine in Minya'),
    'CE01440': ('Non_Hospital_ATM', 'National Bank of Egypt ATM machine in Sohag mislabeled as general_hospital'),
    'CE01877': ('Non_Hospital_ATM', 'National Bank of Egypt ATM machine in Aswan mislabeled as general_hospital'),
    'CE01803': ('Non_Hospital_Restaurant', 'Seafood restaurant (Asmak Al-Morsi / اسماك المرسي) in Luxor scraped as hospital'),
    'CE01783': ('Non_Hospital_Park', 'Public park (General Hospital Park) in Luxor mislabeled as general_hospital'),
    'CE01781': ('Non_Hospital_Laboratory', 'Private diagnostic lab (Al-Israa Laboratories) mislabeled as general_hospital due to address phrase in front of the General Hospital'),
    'CE01784': ('Non_Hospital_Laboratory', 'Private diagnostic lab (Al-Khudairi Laboratories) mislabeled as general_hospital due to branch name'),
    'CE00709': ('Non_Hospital_Pharmacy', 'Standalone pharmacy (Hospital Pharmacy) in Minya'),
    'CE01178': ('Non_Hospital_Pharmacy', 'Standalone pharmacy (Rashid Hospital Pharmacy) in Sohag'),
    'CE01064': ('Hospital_Department_Only', 'Radiology department sub-pin at Al-Qusiya Central Hospital mislabeled as standalone general_hospital'),
    'CE00603': ('Non_Human_Veterinary', 'Veterinary Medicine unit in Beni Suef'),
    'CE01003': ('Non_Human_Veterinary', 'Babotej Veterinary Unit in Assiut'),
    'CE02094': ('Non_Human_Veterinary', 'Veterinary Hospital in Sohag (facility_category=veterinary)'),
    'CE01807': ('Non_Human_Veterinary', 'Qurna Veterinary Unit in Luxor'),
    'CE01735': ('Non_Human_Veterinary', 'Brooke Hospital For Animals Office in Luxor (equine veterinary charity)'),
    'CE01933': ('Non_Hospital_Health_Admin_Office', 'Administrative health office (AL DOODIA HEALTH OFFICE) in Minya'),
    'CE01236': ('Non_Hospital_Health_Admin_Office', 'Administrative office (Health Administration in Akhmim) in Sohag'),
    'CE01649': ('Non_Hospital_Health_Admin_Office', 'Administrative office (Abu Tesht Health Administration) in Qena mislabeled as general_hospital'),
    'CE01663': ('Non_Hospital_Health_Admin_Office', 'Administrative office (Abu Tesht Health Office) in Qena mislabeled as general_hospital'),
    'CE00686': ('Non_Maternal_Specialty_Dental', 'University Dental Hospital in Minya mislabeled as general_hospital'),
    'CE01519': ('Non_Maternal_Specialty_Psychiatry', 'Irada Psychiatry and Addiction Treatment Hospital in Qena'),
    'CE00617': ('Non_Maternal_Specialty_Fever', 'Tropical Diseases / Fever Hospital in Minya'),
    'CE01752': ('Non_Maternal_Specialty_Oncology', 'Shifa Al-Orman Oncology Hospital in Luxor'),
    'CE00045': ('Non_Maternal_Specialty_Fever', 'Al-Mesalla Fever/Infectious Diseases Hospital in Aswan labeled public_general_hospital'),
    'CE01529': ('Non_Maternal_Specialty_Neurology', 'Neurocare Center for Neurology in Qena'),
    'CE01476': ('Non_Maternal_Specialty_Pediatric_Only', 'Pediatric-only facility in Sohag'),
    'CE00928': ('University_Student_Hospital', 'Assiut University Student Hospital (male/student outpatient & general care) labeled general_hospital'),
    'CE01395': ('University_Student_Hospital', 'South Valley University Student Hospital in Sohag labeled general_hospital'),
}

def get_base_entity_type(r):
    cid = r['canonical_entity_id']
    name = str(r['canonical_name'])
    name_ar = clean_text(str(r['canonical_name_ar']))
    full_name = name + ' ' + name_ar
    fclass = str(r['facility_class'])
    fcat = '' if pd.isna(r['facility_category']) else str(r['facility_category'])
    src = str(r['source_files_all'])

    if cid in CONFLICTING_OR_NON_HOSPITAL_IDS:
        return CONFLICTING_OR_NON_HOSPITAL_IDS[cid][0]
    if cid in VERIFIED_CEMONC_IDS:
        return VERIFIED_CEMONC_IDS[cid][0]
    if re.search(r'Health Administration|Health Directorate|Medical Administration|Health Office|إدارة صحية|الادارة الصحية|الاداره الصحيه|مكتب صحة|مكتب الصحه', full_name, re.I):
        return 'Non_Hospital_Health_Admin_Office'
    if re.search(r'Health Unit|Family Medicine|Family Health|Medical Unit|Childhood and Motherhood|Maternal and Child|Motherhood and Childhood|وحدة صحية|وحده صحيه|طب الأسرة|طب الاسرة|طب اسره|رعاية الأمومة|رعاية الامومة|امومه وطفوله|أمومة وطفولة', full_name, re.I):
        return 'Primary_Care_Or_MCH_Unit'
    if fcat == 'restricted_access_hospital' or re.search(r'Military|Police|Armed Forces|عسكري|العسكرى|الشرطة|القوات المسلحة', full_name, re.I):
        return 'Restricted_Military_Or_Police_Hospital'
    if fcat == 'public_general_hospital' or (any(s in src for s in ['mohp', 'uhia', 'smc', 'minya', 'qena', 'registry']) and fclass == 'general_hospital'):
        return 'Public_General_Or_Central_Hospital'
    if fclass == 'general_hospital' and src == 'scrape':
        return 'Unverified_Scraped_General_Hospital'
    if fclass in ('maternity_hospital', 'maternity_center_or_unit') or fcat in ('maternity_hospital', 'maternity_center'):
        if re.search(r'Microscopic Injection|Infertility|IVF|ICSI|حقن مجهري|حفن مجهرى|علاج العقم|أطفال الأنابيب', full_name, re.I):
            return 'Private_Fertility_Or_IVF_Center'
        if re.search(r'أخصائي|استشاري|عيادة|عياده|Specialist|Consultant|Clinic\b', full_name, re.I) and not re.search(r'Hospital|مستشفى|مستشفي|Center|مركز', full_name, re.I):
            return 'Private_Doctor_Clinic_Mislabeled_Maternal'
        return 'Private_Maternity_Hospital_Or_Center_Unverified'
    if fcat == 'clinic_or_center' or re.search(r'\bClinic\b|عيادة|عياده|مستوصف|Polyclinic', full_name, re.I):
        return 'Outpatient_Clinic_Or_Dispensary'
    return 'Unspecified_Unverified_Facility'

def classify_row_exact_4state(r, etype):
    cid = str(r['canonical_entity_id'])
    name = str(r['canonical_name'])
    name_ar = clean_text(str(r['canonical_name_ar'])) if pd.notna(r['canonical_name_ar']) else ''
    full_name = name + ' ' + name_ar
    src_all = str(r['source_files_all']) if pd.notna(r['source_files_all']) else ''

    # Tier 9: Special Audited Rows
    if cid == 'CE01965':
        return ('No', 'No', 'No', 'No', 'Yes', 'Mostly Yes', 'Yes', 'Yes', 'Tier 9: Special Audited (New Assiut Univ Hospital)')
    if cid == 'CE01966':
        return ('No', 'No', 'No', 'No', 'No', 'Mostly No', 'No', 'Mostly Yes', 'Tier 9: Special Audited (Umm Al-Qusour Chest/Rehab)')
    if cid in ('CE00928', 'CE01395') or etype == 'University_Student_Hospital':
        return ('No', 'No', 'No', 'No', 'Mostly No', 'Mostly No', 'No', 'Mostly Yes', 'Tier 9: Special Audited (Univ Student Hospital)')
    
    specialty_ids = {'CE00686', 'CE01519', 'CE00617', 'CE01752', 'CE00045', 'CE01529', 'CE01476'}
    if cid in specialty_ids or etype.startswith('Non_Maternal_Specialty_'):
        return ('No', 'No', 'No', 'No', 'No', 'No', 'No', 'Mostly No', 'Tier 9: Special Audited (Operational Non-Maternity Specialty)')
    
    if etype in ('Outpatient_Clinic_Or_Dispensary', 'Private_Doctor_Clinic_Mislabeled_Maternal'):
        return ('No', 'No', 'No', 'No', 'No', 'No', 'No', 'Mostly No', 'Tier 9: Special Audited (Outpatient Clinic / Doctor Practice)')
    
    corrupted_ids = {'CE00130', 'CE00013', 'CE01064', 'CE00117', 'CE00133', 'CE00501', 'CE01675', 'CE02015'}
    if cid in corrupted_ids or etype in (
        'Non_Hospital_ATM', 'Non_Hospital_Park', 'Non_Hospital_Restaurant', 'Non_Human_Veterinary',
        'Non_Hospital_Pharmacy', 'Non_Hospital_Laboratory', 'Non_Hospital_Health_Admin_Office',
        'Non_Hospital_Summary_Row', 'Planned_Under_Construction_Hospital', 'Place_Name_Only_Artifact',
        'Generic_Name_Only_Artifact', 'Hospital_Department_Only'
    ):
        return ('No', 'No', 'No', 'No', 'No', 'No', 'No', 'No', 'Tier 9: Special Audited (Non-Clinical / Artifact)')

    # Tier 1A: Verified University Maternity & General Hospitals (16 rows)
    if etype in (
        'Verified_University_Maternal_Hospital',
        'Verified_University_Maternal_Hospital_Duplicate',
        'Verified_University_General_Hospital',
        'Verified_University_General_Hospital_Duplicate'
    ):
        return ('Yes', 'Yes', 'Yes', 'Yes', 'Yes', 'Yes', 'Yes', 'Yes', 'Tier 1A: Verified University CEmONC Hospital')

    # Tier 1B: Verified EHA/UHIA Maternity Hospital (CE00028, 1 row)
    if cid == 'CE00028' or etype == 'Verified_UHIA_Maternal_Hospital':
        return ('Yes', 'Yes', 'Yes', 'Yes', 'Yes', 'Yes', 'Yes', 'Yes', 'Tier 1B: Verified EHA/UHIA Maternity Hospital (Isis)')

    # Tier 1C: Verified EHA/UHIA General Hospitals in Luxor & Aswan (5 rows)
    if etype == 'Verified_UHIA_General_Hospital':
        return ('Yes', 'Yes', 'Yes', 'Yes', 'Yes', 'Mostly Yes', 'Mostly Yes', 'Yes', 'Tier 1C: Verified EHA/UHIA General Hospital')

    # Tier 2: Public General Or Central Hospital (105 rows)
    if etype == 'Public_General_Or_Central_Hospital':
        if re.search(r'General|العام|Teaching|التعليمى|التعليمي|Specialized|Specialist|التخصصى|التخصصي|Mabarra|المبرة|التأمين|International|الدولى|الدولي|Cleopatra', full_name, re.I) or 'smc' in src_all:
            return ('Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Yes', 'Tier 2A: Public General/Teaching/Specialized Hospital')
        else:
            return ('Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly No', 'Mostly Yes', 'Yes', 'Tier 2B: Public District Central Hospital')

    # Tier 3: Restricted Military & Police Hospitals (11 rows)
    if etype == 'Restricted_Military_Or_Police_Hospital':
        return ('Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly No', 'Mostly Yes', 'Tier 3: Restricted Military/Police Hospital')

    # Tier 4: Scraped General Hospital Pins (136 rows)
    if etype == 'Unverified_Scraped_General_Hospital':
        if re.search(r'Village|قروي|قروى|قرية|قريه|تكامل|الجديدة|عزبة|العزبه|بني|بنى|كوم|نواى|اشنين|سراوه|دروه|الصفيحة|الهيشة|النجع|العسرات|العسيرات|الصوامعة', full_name, re.I):
            return ('Mostly No', 'No', 'No', 'No', 'No', 'No', 'No', 'Mostly Yes', 'Tier 4C: Scraped Rural/Integration Hospital')
        if re.search(r'University|Teaching|جامع|تعليم|General|العام', full_name, re.I):
            return ('Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Yes', 'Tier 4A: Scraped General/Teaching Pin')
        if re.search(r'Central|المركزي|المركزى|مركزي', full_name, re.I):
            return ('Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly No', 'Mostly Yes', 'Yes', 'Tier 4B: Scraped District Central Pin')
        return ('Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly No', 'Mostly No', 'Mostly No', 'Mostly Yes', 'Tier 4D: Scraped General Hospital Pin')

    # Tier 5: Private Maternity Hospitals & OB/GYN Centers (41 rows)
    if etype == 'Private_Maternity_Hospital_Or_Center_Unverified':
        if re.search(r'Hospital|مستشفى|مستشفي', full_name, re.I):
            return ('Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly No', 'No', 'Mostly No', 'Mostly Yes', 'Tier 5A: Private Maternity Hospital')
        else:
            return ('Mostly Yes', 'Mostly No', 'Mostly Yes', 'Mostly No', 'No', 'No', 'Mostly No', 'Mostly Yes', 'Tier 5B: Private OB/GYN Center')

    # Tier 6: Private Fertility / IVF Centers (+ any T3 with IVF terms)
    if etype == 'Private_Fertility_Or_IVF_Center' or re.search(r'IVF|I\.V\.F|Fertility|خصوبة|عقم|أنابيب|حقن مجهري', full_name, re.I):
        return ('Mostly No', 'No', 'Mostly No', 'Mostly No', 'No', 'No', 'No', 'Mostly No', 'Tier 6: Private Fertility/IVF Center')

    # Tier 7: Primary Care / Family Medicine / MCH (18 rows)
    if etype == 'Primary_Care_Or_MCH_Unit':
        return ('Mostly No', 'No', 'No', 'No', 'No', 'No', 'No', 'Mostly Yes', 'Tier 7: Primary Care / MCH Unit')

    # Tier 8: Granular NLP Sub-Classification of Unspecified_Unverified_Facility (T3)
    is_doctor = re.search(r'Dr\.|Prof\.|د/|د\.|ا\.د|أ\.د', full_name, re.I) and not re.search(r'Hospital|مستشفى|مستشفي', full_name, re.I)
    has_non_clinical = re.search(r'Pharmacy|صيدلية|صيدليات|Lab|Laboratory|Laboratories|معمل|معامل|Scan|أشعة|اشعة|Kiosk|كشك|Clothing|للملابس|Home Medical|المنزلية|Syndicate|النقابة', full_name, re.I)
    if is_doctor or has_non_clinical:
        return ('No', 'No', 'No', 'No', 'No', 'No', 'No', 'No', 'Tier 8A: Non-Clinical/Commercial/Solo Practice')

    if re.search(r'Eye|Ophthalm|العيون|عيون|رمد|الرمد|Conjunctivitis|Nour eleyoon|Oncology|أورام|اورام|الأورمان|الاورمان|Chest|الصدر|صدر|Fever|الحميات|حميات|Psychiatr|النفسية|Heart|Cardiac|القلب|Kidney|Renal|Dialysis|الكلى|كلى|غسيل|Hemo Cure|هيمو كيور|Liver|الكبد|الجهاز الهضمي|Orthoped|العظام|Burns|الحروق|Injury|الاصابات|تأهيل|Rehabilitation|Dental|الأسنان', full_name, re.I):
        return ('No', 'No', 'No', 'No', 'No', 'No', 'No', 'Mostly No', 'Tier 8B: Non-Maternity Specialty Center')

    if re.search(r'Intensive Care|العناية المركزة', full_name, re.I):
        return ('No', 'No', 'No', 'No', 'Mostly Yes', 'Mostly Yes', 'No', 'Yes', 'Tier 8C: Dedicated Intensive Care Center')

    if re.search(r'Insurance|التأمين|التامين|Mabarra|المبرة|المبره|Red Crescent|الهلال|Teachers|للمعلمين|National Hospital|الوطني|Military|العسكري', full_name, re.I):
        return ('Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly No', 'Mostly Yes', 'Yes', 'Tier 8D: Public/Insurance/Mabarra Hospital')

    if re.search(r'Village|قروي|قروى|قرية|قريه|El Karway|القروي|تكامل|integration', full_name, re.I):
        return ('Mostly No', 'No', 'No', 'No', 'No', 'No', 'No', 'Mostly Yes', 'Tier 8E: Rural Village/Integration Hospital')

    if re.search(r'Center|Centre|مركز|Complex|مجمع|Society|جمعية|الجمعية|Foundation|مؤسسة|Dispensary|مستوصف|Clinics|العيادات|House|دار', full_name, re.I) and not re.search(r'Hospital|مستشفى|مستشفي', full_name, re.I):
        return ('Mostly No', 'No', 'No', 'No', 'No', 'No', 'No', 'Mostly No', 'Tier 8F: Outpatient Center/Dispensary')

    return ('Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly Yes', 'Mostly No', 'Mostly No', 'Mostly No', 'Mostly Yes', 'Tier 8G: Private Inpatient Hospital')

def get_evidence_source_string(r, etype, tlabel):
    base_src = str(r['source_files_all'])
    if 'Tier 1A' in tlabel or 'Tier 1B' in tlabel or 'Tier 1C' in tlabel:
        return f"{tlabel}; Law 19/2018 (Univ 24/7 rota) / Law 2/2018 (UHIA GAHAR); Law 8/2021 (licensed blood bank); tertiary CEmONC"
    elif 'Tier 2A' in tlabel:
        return f"{tlabel}; MOHP Decree 75/2024 shift rota; Law 8/2021 blood bank; PM Decree 1063/2014; MOHP Hotline 137"
    elif 'Tier 2B' in tlabel:
        return f"{tlabel}; MOHP Decree 75/2024; district central hospital; on-call specialist rota; NBTS relay dependency; no dedicated M-ICU"
    elif 'Tier 3' in tlabel:
        return f"{tlabel}; Armed Forces/Police Medical Services; conditional civilian access under PM Decree 1063/2014"
    elif 'Tier 4A' in tlabel or 'Tier 4B' in tlabel:
        return f"{tlabel}; Scraped hospital pin ({base_src}); MOHP Decree 75/2024; general/central hospital standard"
    elif 'Tier 4C' in tlabel or 'Tier 8E' in tlabel:
        return f"{tlabel}; Rural village/integration hospital ({base_src}); basic primary care only; no 24/7 surgical/blood/ICU"
    elif 'Tier 5A' in tlabel:
        return f"{tlabel}; Private maternity hospital ({base_src}); Law 51/1981 & 153/2004; private inpatient OB/GYN surgery"
    elif 'Tier 5B' in tlabel:
        return f"{tlabel}; Private OB/GYN clinic/center ({base_src}); Law 153/2004; scheduled daytime surgery; no 24/7 resident/ICU"
    elif 'Tier 6' in tlabel:
        return f"{tlabel}; Private fertility/IVF clinic ({base_src}); assisted reproduction only; acute obstetric emergencies prohibited"
    elif 'Tier 7' in tlabel:
        return f"{tlabel}; MOHP Primary Healthcare Registry ({base_src}); basic care only; lacks surgical theater, blood bank, ICU"
    elif 'Tier 8A' in tlabel:
        return f"{tlabel}; Non-clinical/commercial/solo doctor practice ({base_src}); Law 153/2004; outpatient non-inpatient facility"
    elif 'Tier 8B' in tlabel:
        return f"{tlabel}; Non-maternity specialty center ({base_src}); specialized care; lacks emergency maternity/obstetric capacity"
    elif 'Tier 8C' in tlabel:
        return f"{tlabel}; Dedicated intensive care center ({base_src}); adult critical care only; lacks labor and delivery ward"
    elif 'Tier 8D' in tlabel:
        return f"{tlabel}; Public/Insurance/Mabarra hospital ({base_src}); MOHP Decree 75/2024; general inpatient hospital standard"
    elif 'Tier 8F' in tlabel:
        return f"{tlabel}; Outpatient medical center/dispensary ({base_src}); Law 153/2004; no surgical theater, blood bank, or ICU"
    elif 'Tier 8G' in tlabel or 'Tier 4D' in tlabel:
        return f"{tlabel}; Private inpatient hospital ({base_src}); Law 51/1981 & 153/2004; external blood procurement; no M-ICU"
    else:
        return f"{tlabel}; Audited record ({base_src}); Law 153/2004 / PM Decree 1063/2014"

rows_out = []
for idx, r in df.iterrows():
    etype = get_base_entity_type(r)
    q1, q2, q3, q4, q5, q6, q7, q8, tlabel = classify_row_exact_4state(r, etype)
    ev_src = get_evidence_source_string(r, etype, tlabel)
    
    rows_out.append({
        'canonical_entity_id': r['canonical_entity_id'],
        'canonical_name': clean_text(str(r['canonical_name'])),
        'original_arabic_name': clean_text(str(r['canonical_name_ar'])),
        'governorate_assigned': r['governorate_assigned'],
        'district': '' if pd.isna(r['district']) else str(r['district']),
        'facility_class': r['facility_class'],
        'facility_category': 'MISSING' if pd.isna(r['facility_category']) else r['facility_category'],
        'birth_service_tier': r['birth_service_tier'],
        'birth_service_evidence': 'MISSING' if pd.isna(r['birth_service_evidence']) else r['birth_service_evidence'],
        'source_files_all': r['source_files_all'],
        'coord_reliable': r['coord_reliable'],
        'n_same_coord': r['n_same_coord'],
        'audited_entity_type': etype,
        'tier_classification': tlabel,
        'Q1_maternity_services': q1,
        'Q2_obstetric_emerg_24_7': q2,
        'Q3_emergency_csection_24_7': q3,
        'Q4_qualified_doctor_24_7': q4,
        'Q5_blood_bank_transfusion': q5,
        'Q6_maternal_icu': q6,
        'Q7_nicu': q7,
        'Q8_stabilize_and_refer': q8,
        'evidence_sources': ev_src,
        'verification_date': VERIFICATION_DATE,
        'unresolved_issues': 'Deterministic 4-scale institutional and legal classification applied'
    })

df_val = pd.DataFrame(rows_out)

val_path = os.path.join(QA_DIR, 'hospital_validation.csv')
df_val.to_csv(val_path, index=False, encoding='utf-8')
print(f"Saved {len(df_val)} records to {val_path}")

df_master_clean = df_master_orig.copy()
for col in df_master_clean.columns:
    df_master_clean[col] = df_master_clean[col].apply(clean_text)

df_master_clean['Q1_maternity_services'] = df_val['Q1_maternity_services']
df_master_clean['Q2_obstetric_emerg_24_7'] = df_val['Q2_obstetric_emerg_24_7']
df_master_clean['Q3_emergency_csection_24_7'] = df_val['Q3_emergency_csection_24_7']
df_master_clean['Q4_qualified_doctor_24_7'] = df_val['Q4_qualified_doctor_24_7']
df_master_clean['Q5_blood_bank_transfusion'] = df_val['Q5_blood_bank_transfusion']
df_master_clean['Q6_maternal_icu'] = df_val['Q6_maternal_icu']
df_master_clean['Q7_nicu'] = df_val['Q7_nicu']
df_master_clean['Q8_stabilize_and_refer'] = df_val['Q8_stabilize_and_refer']
df_master_clean['audited_entity_type'] = df_val['audited_entity_type']
df_master_clean['evidence_sources'] = df_val['evidence_sources']
df_master_clean['verification_date'] = df_val['verification_date']
df_master_clean['unresolved_issues'] = df_val['unresolved_issues']

master_out_path = os.path.join(BASE_DIR, 'datasets', 'facilities_sorted_by_governorate.csv')
df_master_clean.to_csv(master_out_path, index=False, encoding='utf-8')
print(f"Saved {len(df_master_clean)} rows, {df_master_clean.shape[1]} columns to {master_out_path}")

q13_df = pd.DataFrame({
    'facility_id': df_val['canonical_entity_id'],
    'Q1_maternity_services': df_val['Q1_maternity_services'],
    'Q2_obstetric_emerg_24_7': df_val['Q2_obstetric_emerg_24_7'],
    'Q3_emergency_csection_24_7': df_val['Q3_emergency_csection_24_7'],
    'Q1_Q3_evidence_source': df_val['evidence_sources']
})
q13_path = os.path.join(QA_DIR, 'temp_q1_q2_q3_validation.csv')
q13_df.to_csv(q13_path, index=False, encoding='utf-8')
print(f"Exported {len(q13_df)} rows to {q13_path}")

q46_df = pd.DataFrame({
    'facility_id': df_val['canonical_entity_id'],
    'Q4_qualified_doctor_24_7': df_val['Q4_qualified_doctor_24_7'],
    'Q5_blood_bank_transfusion': df_val['Q5_blood_bank_transfusion'],
    'Q6_maternal_icu': df_val['Q6_maternal_icu'],
    'Q4_Q6_evidence_source': df_val['evidence_sources']
})
q46_path = os.path.join(QA_DIR, 'temp_q4_q5_q6_validation.csv')
q46_df.to_csv(q46_path, index=False, encoding='utf-8')
print(f"Exported {len(q46_df)} rows to {q46_path}")

q78_df = pd.DataFrame({
    'facility_id': df_val['canonical_entity_id'],
    'Q7_nicu': df_val['Q7_nicu'],
    'Q8_stabilize_and_refer': df_val['Q8_stabilize_and_refer'],
    'Q7_Q8_evidence_source': df_val['evidence_sources']
})
q78_path = os.path.join(QA_DIR, 'temp_q7_q8_validation.csv')
q78_df.to_csv(q78_path, index=False, encoding='utf-8')
print(f"Exported {len(q78_df)} rows to {q78_path}")

for f in os.listdir(QA_DIR):
    s = os.path.join(QA_DIR, f)
    d = os.path.join(REPO_DIR, 'Q&A', f)
    if os.path.isfile(s):
        shutil.copy2(s, d)
shutil.copy2(master_out_path, os.path.join(REPO_DIR, 'facilities_sorted_by_governorate.csv'))
print("Successfully synced all files to repo_work/")

q_cols = [
    'Q1_maternity_services', 'Q2_obstetric_emerg_24_7', 'Q3_emergency_csection_24_7',
    'Q4_qualified_doctor_24_7', 'Q5_blood_bank_transfusion', 'Q6_maternal_icu',
    'Q7_nicu', 'Q8_stabilize_and_refer'
]
summary_df = pd.DataFrame({c: df_val[c].value_counts() for c in q_cols}).fillna(0).astype(int)
summary_df = summary_df.reindex(['Yes', 'Mostly Yes', 'Mostly No', 'No'])
print("\n=== FINAL 4-ANSWER SCALE SUMMARY TABLE (N=798) ===")
print(summary_df.to_string())
