#!/usr/bin/env python3
"""
enrich_social_and_maps.py - Social Media, Google Maps & Directory Enrichment Script

Automated 7-governorate pipeline for enrichment of hospital readiness and tier classification
across all Upper Egypt healthcare facilities (798 rows).

Governorates covered:
- Beni Suef (116 records)
- Minya (139 records)
- Assiut (130 records)
- Sohag (207 records)
- Qena (117 records)
- Luxor (41 records)
- Aswan (48 records)

Data Sources Ingested:
1. temp_benisuef_minya_social_maps.json (25 verified facilities)
2. temp_assiut_sohag_social_maps.json (65 verified facilities)
3. temp_qena_luxor_aswan_social_maps.json (206 verified facilities)

Systematic Fixes Applied:
1. Beni Suef NLP / Regex Defect Fix: Prevents naive 'بني|بنى' rural village matching from
   misclassifying secondary/tertiary facilities in Beni Suef (CE00476, CE00208, CE00165).
2. Explicit NICU/ICU Mention Fix: Enforces verified indicator status for maternal centers
   and dedicated intensive care facilities with explicit nursery/ICU labels (CE00166, CE00034, CE01723).
3. Village Health Unit & Artifact Reclassification: Cleans up mislabeled 'Tier 8G: Private Inpatient Hospital'
   records, reclassifying rural family health units, integration clinics, solo practices, and
   commercial shop pins into Tier 8E, Tier 7, Tier 8A, or Tier 9.
4. Misplaced Pin Quarantine: Flags and quarantines out-of-governorate scraped pins (CE00245, CE00260),
   excluding them from Upper Egypt maternal routing graphs and setting readiness to 'No'.
5. Multi-Source Social Media & Maps Enrichment across all 7 Upper Egypt governorates.

Output Synchronizations:
- hospital_validation.csv
- facilities_sorted_by_governorate.csv
- temp_q1_q2_q3_validation.csv
- temp_q4_q5_q6_validation.csv
- temp_q7_q8_validation.csv
- Full replica to repo_work/

Constraints Enforced:
- ZERO emojis
- ZERO em-dashes and ZERO en-dashes; standard ASCII hyphens (-) only
- Deterministic 4-class scale: 'Yes', 'Mostly Yes', 'Mostly No', 'No'
"""

import os
import sys
import json
import shutil
import argparse
import pandas as pd

# -----------------------------------------------------------------------------
# Configuration and Constants
# -----------------------------------------------------------------------------
DEFAULT_QA_DIR = '/home/yousefmahmoudali/Desktop/GradII/Q&A'
DEFAULT_DATASETS_DIR = '/home/yousefmahmoudali/Desktop/GradII/datasets'
DEFAULT_REPO_WORK_DIR = '/home/yousefmahmoudali/Desktop/GradII/repo_work'

BENI_SUEF_FIXES = {
    'CE00476': {
        'tier': 'Tier 4A: Scraped General/Teaching Pin (Social/Maps Enriched)',
        'entity_type': 'Unverified_Scraped_General_Hospital',
        'q': {'Q1': 'Yes', 'Q2': 'Mostly Yes', 'Q3': 'Yes', 'Q4': 'Mostly Yes', 'Q5': 'Mostly Yes', 'Q6': 'Mostly Yes', 'Q7': 'Mostly Yes', 'Q8': 'Yes'},
        'source': 'Beni Suef General Hospital pin correction; secondary referral hospital with blood bank, ICU, and NICU.'
    },
    'CE00208': {
        'tier': 'Tier 4A: Scraped General/Teaching Pin (Social/Maps Enriched)',
        'entity_type': 'Unverified_Scraped_General_Hospital',
        'q': {'Q1': 'Yes', 'Q2': 'Mostly Yes', 'Q3': 'Yes', 'Q4': 'Mostly Yes', 'Q5': 'Mostly Yes', 'Q6': 'Mostly Yes', 'Q7': 'Mostly Yes', 'Q8': 'Yes'},
        'source': 'Bani Sweif General Hospital pin correction; 24-bed inpatient general ward pin.'
    },
    'CE00165': {
        'tier': 'Tier 1A: Verified University CEmONC Hospital (Social/Maps Enriched)',
        'entity_type': 'Verified_University_Maternal_Hospital',
        'q': {'Q1': 'Yes', 'Q2': 'Yes', 'Q3': 'Yes', 'Q4': 'Yes', 'Q5': 'Yes', 'Q6': 'Yes', 'Q7': 'Yes', 'Q8': 'Yes'},
        'source': 'Safe Women Unit Beni Suef University Hospitals; comprehensive tertiary university CEmONC center.'
    }
}

EXPLICIT_NICU_ICU_FIXES = {
    'CE00166': {
        'tier': 'Tier 5A: Verified Private Maternity & Surgical Hospital (Social/Maps Enriched)',
        'entity_type': 'Verified_Private_Maternity_Surgical_Hospital',
        'q': {'Q1': 'Yes', 'Q2': 'Mostly Yes', 'Q3': 'Yes', 'Q4': 'Mostly Yes', 'Q5': 'Mostly No', 'Q6': 'Mostly Yes', 'Q7': 'Mostly Yes', 'Q8': 'Yes'},
        'source': 'Facebook Page & Directory: Dedicated women health center with operating rooms for C-sections, adult intensive care unit, and specialized neonatal incubator ward (حضانات)'
    },
    'CE00034': {
        'tier': 'Tier 8C: Dedicated Intensive Care Center',
        'entity_type': 'Dedicated_Intensive_Care_Center',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly Yes', 'Q5': 'No', 'Q6': 'Mostly Yes', 'Q7': 'No', 'Q8': 'Mostly Yes'},
        'source': 'Verified dedicated adult ICU center in Aswan; non-maternity specialty.'
    },
    'CE01723': {
        'tier': 'Tier 8C: Dedicated Intensive Care Center',
        'entity_type': 'Dedicated_Intensive_Care_Center',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly Yes', 'Q5': 'No', 'Q6': 'Mostly Yes', 'Q7': 'No', 'Q8': 'Mostly Yes'},
        'source': 'Reaia Center For Intensive Care In Luxor; specialized adult intensive care center.'
    }
}

MISPLACED_PIN_FIXES = {
    'CE00245': {
        'tier': 'Tier 9: Special Audited (Misplaced Out-of-Governorate Pin)',
        'entity_type': 'Misplaced_Out_Of_Governorate_Pin',
        'desc': 'Misplaced out-of-governorate pin (Andalusia Hospitals North Coast); excluded from Upper Egypt maternal routing graph',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Misplaced out-of-governorate pin (North Coast / Matrouh); excluded from Upper Egypt maternal routing graph'
    },
    'CE00260': {
        'tier': 'Tier 9: Special Audited (Misplaced Out-of-Governorate Pin)',
        'entity_type': 'Misplaced_Out_Of_Governorate_Pin',
        'desc': 'Misplaced out-of-governorate pin (AAST-MT ALAMEIN HOSPITAL); excluded from Upper Egypt maternal routing graph',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Misplaced out-of-governorate pin (El Alamein / Matrouh); excluded from Upper Egypt maternal routing graph'
    },
    'CE00256': {
        'tier': 'Tier 9: Special Audited (Misplaced Out-of-Governorate Pin)',
        'entity_type': 'Misplaced_Out_Of_Governorate_Pin',
        'desc': 'Misplaced out-of-governorate pin (Marina Central Hospital, North Coast, Matrouh); excluded from Upper Egypt maternal routing graph',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Misplaced out-of-governorate pin (Marina / North Coast / Matrouh); excluded from Upper Egypt maternal routing graph'
    },
    'CE00225': {
        'tier': 'Tier 9: Special Audited (Misplaced Out-of-Governorate Pin)',
        'entity_type': 'Misplaced_Out_Of_Governorate_Pin',
        'desc': 'Misplaced out-of-governorate pin (Medina Hospital, El Wahat El Bahariya / Atfeeh, Giza); excluded from Upper Egypt maternal routing graph',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Misplaced out-of-governorate pin (El Wahat El Bahariya / Atfeeh / Giza); excluded from Upper Egypt maternal routing graph'
    },
    'CE00233': {
        'tier': 'Tier 9: Special Audited (Misplaced Out-of-Governorate Pin)',
        'entity_type': 'Misplaced_Out_Of_Governorate_Pin',
        'desc': 'Misplaced out-of-governorate pin (Atfeeh General Hospital, El Wahat El Bahariya / Atfeeh, Giza); excluded from Upper Egypt maternal routing graph',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Misplaced out-of-governorate pin (Atfeeh / El Wahat El Bahariya / Giza); excluded from Upper Egypt maternal routing graph'
    },
    'CE00291': {
        'tier': 'Tier 9: Special Audited (Misplaced Out-of-Governorate Pin)',
        'entity_type': 'Misplaced_Out_Of_Governorate_Pin',
        'desc': 'Misplaced out-of-governorate pin (Al Shifa Specialized Center, El Wahat El Bahariya / Atfeeh, Giza); excluded from Upper Egypt maternal routing graph',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Misplaced out-of-governorate pin (El Wahat El Bahariya / Giza); excluded from Upper Egypt maternal routing graph'
    },
    'CE00326': {
        'tier': 'Tier 9: Special Audited (Misplaced Out-of-Governorate Pin)',
        'entity_type': 'Misplaced_Out_Of_Governorate_Pin',
        'desc': 'Misplaced out-of-governorate pin (Bramble General Hospital / مستشفي البرمبل العام, Al Borombol, Atfeeh, Giza); excluded from Upper Egypt maternal routing graph',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Misplaced out-of-governorate pin (Al Borombol / Atfeeh / Giza); excluded from Upper Egypt maternal routing graph'
    },
    'CE01635': {
        'tier': 'Tier 9: Special Audited (Misplaced Out-of-Governorate Pin)',
        'entity_type': 'Misplaced_Out_Of_Governorate_Pin',
        'desc': 'Misplaced out-of-governorate pin (Al Atamin Specialized Charity Hospital, Al Omraniya, Giza); excluded from Upper Egypt maternal routing graph',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Misplaced out-of-governorate pin (Al Omraniya / Giza); excluded from Upper Egypt maternal routing graph'
    }
}

VILLAGE_AND_ARTIFACT_FIXES = {
    'CE00522': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Azab El-Fent village unit (Al-Fashn); rural primary health facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00529': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Manshaat Amr village unit (Al-Fashn); rural primary health facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00532': {
        'tier': 'Tier 7: Primary Care / MCH Unit',
        'entity_type': 'Primary_Care_Or_MCH_Unit',
        'desc': 'Kafr Darwish Family Health Unit (Al-Fashn); primary outpatient clinic',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00537': {
        'tier': 'Tier 7: Primary Care / MCH Unit',
        'entity_type': 'Primary_Care_Or_MCH_Unit',
        'desc': 'Nazlet El-Barqi Health Unit (Al-Fashn); primary outpatient clinic',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00163': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Non_Hospital_Health_Admin_Office',
        'desc': 'Medical Commission administrative office; non-clinical entity',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Medical Commission administrative office; excluded from maternal routing graph'
    },
    'CE00230': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Abweit village health unit (Al-Wasta); rural primary facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00236': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Atwab village health unit (Al-Wasta); rural primary facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00738': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Nazlet Amr village health unit (Beni Mazar); rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00753': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Kafr El-Sheikh Ibrahim village health unit (Beni Mazar); rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00781': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Naga Ait El-Hashani village unit (Minya); rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01655': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Samhoud health unit (Abu Tesht); rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01435': {
        'tier': 'Tier 7: Primary Care / MCH Unit',
        'entity_type': 'Primary_Care_Or_MCH_Unit',
        'desc': 'Al-Monshaah family healthcare unit; primary care center',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01416': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Naga Al-Deir village unit (Al-Asirat); rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01420': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Naga Radwan village unit (Al-Asirat); rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01489': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Naga Al-Hussein village unit (Dar El-Salam); rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01366': {
        'tier': 'Tier 7: Primary Care / MCH Unit',
        'entity_type': 'Primary_Care_Or_MCH_Unit',
        'desc': 'Saqalta family healthcare unit; primary care center',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE02009': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Al Zouk Al Gharbia village unit (Al-Monshaah); rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE02010': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Al Ghawanem village unit (Sohag); rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE02011': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Qarmatah West village unit (Sohag); rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE02012': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Ouled Hamza Island village unit (Al-Monshaah); rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE02014': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Mahrous Abu Shousha Padva village unit; rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01258': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Awlad Shalloul village unit (Sohag); rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01479': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Awlad Khalifa village unit (Dar El-Salam); rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01475': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Sheikh Mutawa village unit (Dar El-Salam); rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01492': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Amarna village unit (Dar El-Salam); rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01496': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Umrah Marine village unit (Dar El-Salam); rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01239': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Souq village unit (Sohag); rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01367': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Fawjaly village unit (Saqalta); rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01419': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Al Asrat village unit; rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01414': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Al Rashaida village unit (Al-Monshaah); rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE02003': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Aabar Al Malek village unit; rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01084': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Bani Mohammed Al-Aqab village unit (Abnoub); rural facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01116': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Non_Hospital_Post_Office',
        'desc': 'Post Office - El Wasta Asiout; non-clinical postal service artifact',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Post Office artifact; excluded from maternal routing graph'
    },
    'CE01001': {
        'tier': 'Tier 8A: Non-Clinical/Commercial/Solo Practice',
        'entity_type': 'Private_Solo_Doctor_Practice',
        'desc': 'Mostfa younis; private solo doctor outpatient clinic',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'}
    },
    'CE00960': {
        'tier': 'Tier 8A: Non-Clinical/Commercial/Solo Practice',
        'entity_type': 'Private_Solo_Doctor_Practice',
        'desc': 'Sahar Mohamed Sultan; private solo doctor outpatient practice',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'}
    },
    'CE00946': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Non_Hospital_Health_Admin_Office',
        'desc': 'Al Orman Association; NGO charitable office',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'NGO charity office pin; non-clinical'
    },
    'CE01445': {
        'tier': 'Tier 8A: Non-Clinical/Commercial/Solo Practice',
        'entity_type': 'Private_Solo_Doctor_Practice',
        'desc': 'Asmaa Yasser; private practice clinic',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'}
    },
    'CE01446': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Non_Hospital_Commercial_Shop',
        'desc': 'Alamia Exhibition Tools Health Algossry; sanitary ware / commercial shop artifact',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Commercial shop artifact; excluded from maternal routing graph'
    },
    'CE01484': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Place_Name_Only_Artifact',
        'desc': 'Bishop Abram Services Building; community service hall',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Community services hall; non-clinical'
    },
    'CE01173': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Place_Name_Only_Artifact',
        'desc': 'Martyr Abdul Moneim Riad Old Hospital; decommissioned facility pin',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Decommissioned hospital pin; excluded from maternal routing graph'
    },
    'CE01178': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Non_Hospital_Pharmacy',
        'desc': 'Rashid Hospital Pharmacy; community retail pharmacy',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Retail pharmacy; non-hospital'
    },
    'CE01449': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Place_Name_Only_Artifact',
        'desc': 'Al Minshah; administrative district label pin',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Administrative district label pin; non-facility'
    },
    'CE02016': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Generic_Name_Only_Artifact',
        'desc': 'Generic Hospital pin without clinical data',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Generic scraped pin without identifiable clinical facility'
    },
    'CE01280': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Generic_Name_Only_Artifact',
        'desc': 'Generic Hospital pin without clinical data',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Generic scraped pin without identifiable clinical facility'
    }
,
    'CE00580': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Non_Hospital_Mosque',
        'desc': 'Samasta Hospital Mosque (مسجد مستشفى سمسطا); place of worship, non-clinical entity',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Hospital mosque place of worship; excluded from maternal routing graph'
    },
    'CE00780': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Non_Hospital_Mosque',
        'desc': 'Mosque of Faith (مسجد الإيمان); place of worship, non-clinical entity',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Mosque place of worship; excluded from maternal routing graph'
    },
    'CE00549': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Place_Name_Only_Artifact',
        'desc': 'El Fashn; bare town/place name label pin, non-clinical',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Bare place name pin; excluded from maternal routing graph'
    },
    'CE00482': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Place_Name_Only_Artifact',
        'desc': 'Ihnasya Al Madinah; bare town/place name label pin, non-clinical',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Bare place name pin; excluded from maternal routing graph'
    },
    'CE00875': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Place_Name_Only_Artifact',
        'desc': 'Abu Qirqas; bare town/place name label pin, non-clinical',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Bare place name pin; excluded from maternal routing graph'
    },
    'CE00755': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Place_Name_Only_Artifact',
        'desc': 'Bani Mazar; bare town/place name label pin, non-clinical',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Bare place name pin; excluded from maternal routing graph'
    },
    'CE00746': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Place_Name_Only_Artifact',
        'desc': 'Beni Mazar; bare town/place name label pin, non-clinical',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Bare place name pin; excluded from maternal routing graph'
    },
    'CE01114': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Place_Name_Only_Artifact',
        'desc': 'Al Badari; bare town/place name label pin, non-clinical',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Bare place name pin; excluded from maternal routing graph'
    },
    'CE01714': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Place_Name_Only_Artifact',
        'desc': 'Dishna; bare town/place name label pin, non-clinical',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Bare place name pin; excluded from maternal routing graph'
    },
    'CE00533': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Place_Name_Only_Artifact',
        'desc': 'Ahmed Bey Saber; person / street address label pin, non-clinical',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Person / street label pin; excluded from maternal routing graph'
    },
    'CE00961': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Place_Name_Only_Artifact',
        'desc': 'M Mallawi (م ملوي); place name label pin in Assiut, non-clinical',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Place name label pin; excluded from maternal routing graph'
    },
    'CE00454': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Generic_Name_Only_Artifact',
        'desc': 'Hospital (مستشفي); generic unidentifiable hospital pin in Sumusta, non-clinical',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Generic scraped pin without identifiable clinical facility'
    },
    'CE00587': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Generic_Name_Only_Artifact',
        'desc': 'Hospital (مستشفي); generic unidentifiable hospital pin in Sumusta, non-clinical',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Generic scraped pin without identifiable clinical facility'
    },
    'CE00800': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Generic_Name_Only_Artifact',
        'desc': 'Hospital (مستشفى); generic unidentifiable hospital pin in Beni Mazar, non-clinical',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Generic scraped pin without identifiable clinical facility'
    },
    'CE00974': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Generic_Name_Only_Artifact',
        'desc': 'Hospital (مستشفي); generic unidentifiable hospital pin in Assiut, non-clinical',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Generic scraped pin without identifiable clinical facility'
    },
    'CE01561': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Generic_Name_Only_Artifact',
        'desc': 'Hospital (Hospital); generic unidentifiable hospital pin in Qena, non-clinical',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Generic scraped pin without identifiable clinical facility'
    },
    'CE01733': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Generic_Name_Only_Artifact',
        'desc': 'ELAMEED; non-clinical commercial/place pin in Luxor',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Commercial / place pin; excluded from maternal routing graph'
    },
    'CE01954': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Planned_Under_Construction_Hospital',
        'desc': 'Hospital 175 beds (مستشفى 175 سرير); planned under-construction hospital in New Qena, non-operational',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Planned under-construction hospital; non-operational'
    },
    'CE01547': {
        'tier': 'Tier 9: Special Audited (Non-Clinical / Artifact)',
        'entity_type': 'Non_Hospital_Health_Admin_Office',
        'desc': 'Local Medical Committee (اللجنة الطبية العامة بقنا); administrative health commission office, non-clinical',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'},
        'issue': 'Medical Commission administrative office; excluded from maternal routing graph'
    },
    'CE00656': {
        'tier': 'Tier 8A: Non-Clinical/Commercial/Solo Practice',
        'entity_type': 'Private_Solo_Doctor_Practice',
        'desc': 'Attention of the best (عناية الافضل); private outpatient doctor practice clinic',
        'q': {'Q1': 'No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'No'}
    },
    'CE00769': {
        'tier': 'Tier 7: Primary Care / MCH Unit',
        'entity_type': 'Primary_Care_Or_MCH_Unit',
        'desc': 'Medical Unit (الوحدة الطبية ببني مزار); outpatient primary healthcare clinic',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00444': {
        'tier': 'Tier 7: Primary Care / MCH Unit',
        'entity_type': 'Primary_Care_Or_MCH_Unit',
        'desc': 'Health Care Unit (إهناسيا); outpatient primary healthcare clinic',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00747': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Silent Brown Unit (وحدة بني صامت ببني مزار); rural primary health unit',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00524': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Western Alphent Hospital (مستشفى الفنت الغربية بالفشن); rural village health facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00525': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Dlhans Hospital (مستشفى دلهانس بالفشن); rural village health facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00545': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Masura Hospital (مستشفى مازورة بسمسطا); rural village health facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00574': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Masura Hospital duplicate (مستشفى مازورة بسمسطا); rural village health facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00584': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Bani Hilla Hospital (مستشفى بني حلة بسمسطا); rural village health facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00840': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Hospital Mnsavas A F (مستشفى منسافيس بأبوقرقاص); rural village health facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00841': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Atildum Hospital (مستشفى اتليدم بأبوقرقاص); rural village health facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00749': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Alatlat Hospital (مستشفي الاتلات ببني مزار); rural village health facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00696': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Gulwsna Hospital (مستشفى قلوصنا بسمالوط); rural village health facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00880': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Bani Mahdi Hospital (مستشفى بنى مهدى بالمنيا); rural village health facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01657': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Al Olaimat Hospital (مستشفى العليمات بأبوتشت); rural village health facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01658': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Umrah Hospital Southern (مستشفى العمرة القبلية بأبوتشت); rural village health facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01659': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Al Kaimat Medical Hospital (مستشفي الكعيمات الطبية بأبوتشت); rural village health facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01653': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Hospital Salwa Bahri (مستشفى سلوى بحري بكوم أمبو); rural village health facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE01685': {
        'tier': 'Tier 8E: Rural Village/Integration Hospital',
        'entity_type': 'Rural_Village_Integration_Hospital',
        'desc': 'Alamiria (العامرية بأبوتشت); rural village health facility',
        'q': {'Q1': 'Mostly No', 'Q2': 'No', 'Q3': 'No', 'Q4': 'Mostly No', 'Q5': 'No', 'Q6': 'No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00930': {
        'tier': 'Tier 9: Special Audited (Operational Non-Maternity Specialty)',
        'entity_type': 'Non_Maternal_Specialty_Chest',
        'desc': 'Sadr hospital in Assiut (مستشفى الصدر بأسيوط); specialized pulmonary hospital, non-maternity',
        'q': {'Q1': 'Mostly No', 'Q2': 'Mostly No', 'Q3': 'No', 'Q4': 'Mostly Yes', 'Q5': 'Mostly No', 'Q6': 'Mostly No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE02024': {
        'tier': 'Tier 9: Special Audited (Operational Non-Maternity Specialty)',
        'entity_type': 'Non_Maternal_Specialty_Chest',
        'desc': 'El Sadr Hospital (مستشفى الصدر بأسيوط); specialized pulmonary hospital, non-maternity',
        'q': {'Q1': 'Mostly No', 'Q2': 'Mostly No', 'Q3': 'No', 'Q4': 'Mostly Yes', 'Q5': 'Mostly No', 'Q6': 'Mostly No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00935': {
        'tier': 'Tier 9: Special Audited (Operational Non-Maternity Specialty)',
        'entity_type': 'Non_Maternal_Specialty_Liver',
        'desc': 'Al rajhy hospital (Assiut University Al-Rajhi Liver Hospital); specialized hepatic surgery hospital, non-maternity',
        'q': {'Q1': 'Mostly No', 'Q2': 'Mostly No', 'Q3': 'No', 'Q4': 'Mostly Yes', 'Q5': 'Mostly No', 'Q6': 'Mostly Yes', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    },
    'CE00956': {
        'tier': 'Tier 9: Special Audited (Operational Non-Maternity Specialty)',
        'entity_type': 'Non_Maternal_Specialty_Fever',
        'desc': 'Endemic Diseases Hospital (مستشفى الحميات والأمراض المتوطنة بأسيوط); specialized infectious disease hospital, non-maternity',
        'q': {'Q1': 'Mostly No', 'Q2': 'Mostly No', 'Q3': 'No', 'Q4': 'Mostly Yes', 'Q5': 'Mostly No', 'Q6': 'Mostly No', 'Q7': 'No', 'Q8': 'Mostly Yes'}
    }

}

TIER_TO_ENTITY_TYPE = {
    'Tier 5A: Verified Private Maternity & Surgical Hospital (Social/Maps Enriched)': 'Verified_Private_Maternity_Surgical_Hospital',
    'Tier 5B: Verified Private OB/GYN Center (Social/Maps Enriched)': 'Verified_Private_OB_GYN_Center',
    'Tier 6: Private Fertility/IVF Center (Social/Maps Enriched)': 'Private_Fertility_Or_IVF_Center',
    'Tier 8F: Outpatient Center/Dispensary (Social/Maps Enriched)': 'Outpatient_Clinic_Or_Dispensary',
    'Tier 1A: Verified University CEmONC Hospital (Social/Maps Enriched)': 'Verified_University_Maternal_Hospital',
    'Tier 1C: Verified SMC Tertiary Specialized Hospital (Social/Maps Enriched)': 'Verified_UHIA_General_Hospital',
    'Tier 2A: Public General/Teaching/Specialized Hospital (Social/Maps Enriched)': 'Public_General_Or_Central_Hospital',
    'Tier 4A: Scraped General/Teaching Pin (Social/Maps Enriched)': 'Unverified_Scraped_General_Hospital',
    'Tier 4B: Scraped District Central Pin (Social/Maps Enriched)': 'Unverified_Scraped_General_Hospital',
    'Tier 2A: Public/Non-Profit General/Specialized Hospital (Social/Maps Enriched)': 'Public_General_Or_Central_Hospital'
}

DISTRICT_TO_GOV = {
    # Beni Suef
    'beni suef': 'Beni Suef', 'beni suef center': 'Beni Suef', 'new bani suef': 'Beni Suef',
    'el wasta': 'Beni Suef', 'al wasta': 'Beni Suef', 'nasser': 'Beni Suef',
    'ihnasia': 'Beni Suef', 'ihnasiya': 'Beni Suef', 'ihnasya al madinah': 'Beni Suef', 'herakleopolis magna': 'Beni Suef',
    'biba': 'Beni Suef', 'sumusta': 'Beni Suef', 'sumusta el waqf': 'Beni Suef',
    'el fashn': 'Beni Suef', 'al fashn': 'Beni Suef', 'east nile': 'Beni Suef', 'al zohour district': 'Beni Suef',

    # Minya
    'minya': 'Minya', 'minya center': 'Minya', 'el menia': 'Minya',
    'first al minya': 'Minya', 'first minya': 'Minya', 'second al minya': 'Minya', 'third al minya': 'Minya',
    'maghagha': 'Minya', 'maghagha center': 'Minya',
    'beni mazar': 'Minya', 'bani mazar': 'Minya', 'bani mazar center': 'Minya',
    'matay': 'Minya', 'matai': 'Minya',
    'samalut': 'Minya', 'east samalout': 'Minya', 'east samalut': 'Minya', 'west samalout': 'Minya',
    'abu qirqas': 'Minya', 'mallawi': 'Minya', 'deir mawas': 'Minya',
    'el adwa': 'Minya', 'el idwa': 'Minya', 'el edawa': 'Minya',

    # Assiut
    'assiut': 'Assiut', 'asyut': 'Assiut', 'asyut 1': 'Assiut', 'asyut 2': 'Assiut',
    'first assiut district': 'Assiut', 'second assiut district': 'Assiut',
    'east assiut': 'Assiut', 'west assiut': 'Assiut', 'new asyut': 'Assiut',
    'dairut': 'Assiut', 'el qusiya': 'Assiut', 'al qusiya': 'Assiut',
    'manfalut': 'Assiut', 'abnoub': 'Assiut', 'abnub': 'Assiut',
    'el fateh': 'Assiut', 'abu tij': 'Assiut', 'sedfa': 'Assiut', 'sodfa': 'Assiut',
    'el ghanayem': 'Assiut', 'sahel selim': 'Assiut', 'el badari': 'Assiut', 'al badari': 'Assiut',

    # Sohag
    'sohag': 'Sohag', 'sohag 1': 'Sohag', 'sohag 2': 'Sohag', 'sohag center': 'Sohag',
    'first sohag district': 'Sohag', 'second sohag district': 'Sohag', 'sohag al gadida city': 'Sohag',
    'akhmin': 'Sohag', 'akhmim': 'Sohag', 'akhmim center': 'Sohag',
    'el balyana': 'Sohag', 'el maragha': 'Sohag', 'el mansha': 'Sohag', 'al monshaah': 'Sohag',
    'el munshaa': 'Sohag', 'al monshaah center': 'Sohag',
    'gerga': 'Sohag', 'girga': 'Sohag', 'girga city district': 'Sohag',
    'juhayna': 'Sohag', 'juhaynah west': 'Sohag',
    'dar el salam': 'Sohag', 'saqalta': 'Sohag', 'saqulta': 'Sohag', 'saqultah': 'Sohag',
    'tima': 'Sohag', 'tahta': 'Sohag', 'tahta district': 'Sohag',
    'el usayrat': 'Sohag', 'aserat': 'Sohag',

    # Qena
    'qena': 'Qena', 'qena center': 'Qena', 'new qena': 'Qena',
    'abu tesht': 'Qena', 'farshut': 'Qena', 'nag hammadi': 'Qena',
    'dishna': 'Qena', 'el waqf': 'Qena', 'al waqf': 'Qena',
    'qift': 'Qena', 'qus': 'Qena', 'naqada': 'Qena',

    # Luxor
    'luxor': 'Luxor', 'luxor center': 'Luxor', 'luxor city': 'Luxor',
    'esna': 'Luxor', 'armant': 'Luxor', 'al qurna': 'Luxor', 'el toda': 'Luxor',
    'el zeyneya': 'Luxor', 'new thebes': 'Luxor', 'tiba': 'Luxor',

    # Aswan
    'aswan': 'Aswan', 'aswan 1': 'Aswan', 'aswan 2': 'Aswan', 'first district': 'Aswan',
    'daraw': 'Aswan', 'draw': 'Aswan', 'kom ombo': 'Aswan', 'markaz kom ombo': 'Aswan',
    'edfu': 'Aswan', 'nasr': 'Aswan'
}

def load_data(qa_dir=DEFAULT_QA_DIR, datasets_dir=DEFAULT_DATASETS_DIR):
    """Load validation and facilities CSVs, plus all 3 social/maps enrichment JSONs."""
    val_path = os.path.join(qa_dir, 'hospital_validation.csv')
    fac_path = os.path.join(datasets_dir, 'facilities_sorted_by_governorate.csv')

    df_val = pd.read_csv(val_path)
    df_fac = pd.read_csv(fac_path)

    json_bm_path = os.path.join(qa_dir, 'temp_benisuef_minya_social_maps.json')
    json_as_path = os.path.join(qa_dir, 'temp_assiut_sohag_social_maps.json')
    json_qla_path = os.path.join(qa_dir, 'temp_qena_luxor_aswan_social_maps.json')

    with open(json_bm_path, 'r', encoding='utf-8') as f:
        bm_data = json.load(f)

    with open(json_as_path, 'r', encoding='utf-8') as f:
        as_data = json.load(f)

    with open(json_qla_path, 'r', encoding='utf-8') as f:
        qla_data = json.load(f)

    return df_val, df_fac, bm_data, as_data, qla_data

def enrich_pipeline(df_val, df_fac, bm_data, as_data, qla_data):
    """Apply the full 7-governorate enrichment pipeline in deterministic order."""
    df_v = df_val.copy()
    df_f = df_fac.copy()

    indicators = [
        'Q1_maternity_services', 'Q2_obstetric_emerg_24_7', 'Q3_emergency_csection_24_7',
        'Q4_qualified_doctor_24_7', 'Q5_blood_bank_transfusion', 'Q6_maternal_icu',
        'Q7_nicu', 'Q8_stabilize_and_refer'
    ]

    df_f_map = {row['canonical_entity_id']: idx for idx, row in df_f.iterrows()}

    # Step 1: Misplaced Pin Quarantine
    for cid, info in MISPLACED_PIN_FIXES.items():
        v_idx = df_v[df_v['canonical_entity_id'] == cid].index
        if len(v_idx) > 0:
            i = v_idx[0]
            df_v.at[i, 'tier_classification'] = info['tier']
            df_v.at[i, 'audited_entity_type'] = info['entity_type']
            for qk, qv in info['q'].items():
                col = [c for c in indicators if c.startswith(qk + '_')][0]
                df_v.at[i, col] = qv
            df_v.at[i, 'unresolved_issues'] = info['issue']
            df_v.at[i, 'evidence_sources'] = str(df_v.at[i, 'evidence_sources']) + '; ' + info['desc']
            df_v.at[i, 'verification_date'] = '2026-10-31'

            if cid in df_f_map:
                fi = df_f_map[cid]
                df_f.at[fi, 'audited_entity_type'] = info['entity_type']
                for qk, qv in info['q'].items():
                    col = [c for c in indicators if c.startswith(qk + '_')][0]
                    df_f.at[fi, col] = qv
                df_f.at[fi, 'unresolved_issues'] = info['issue']
                df_f.at[fi, 'evidence_sources'] = str(df_f.at[fi, 'evidence_sources']) + '; ' + info['desc']
                df_f.at[fi, 'verification_date'] = '2026-10-31'

    # Step 2: Village Units and Artifact Reclassifications
    for cid, info in VILLAGE_AND_ARTIFACT_FIXES.items():
        v_idx = df_v[df_v['canonical_entity_id'] == cid].index
        if len(v_idx) > 0:
            i = v_idx[0]
            df_v.at[i, 'tier_classification'] = info['tier']
            df_v.at[i, 'audited_entity_type'] = info['entity_type']
            for qk, qv in info['q'].items():
                col = [c for c in indicators if c.startswith(qk + '_')][0]
                df_v.at[i, col] = qv
            if 'issue' in info:
                df_v.at[i, 'unresolved_issues'] = info['issue']
            df_v.at[i, 'evidence_sources'] = str(df_v.at[i, 'evidence_sources']) + '; ' + info['desc']
            df_v.at[i, 'verification_date'] = '2026-10-31'

            if cid in df_f_map:
                fi = df_f_map[cid]
                df_f.at[fi, 'audited_entity_type'] = info['entity_type']
                for qk, qv in info['q'].items():
                    col = [c for c in indicators if c.startswith(qk + '_')][0]
                    df_f.at[fi, col] = qv
                if 'issue' in info:
                    df_f.at[fi, 'unresolved_issues'] = info['issue']
                df_f.at[fi, 'evidence_sources'] = str(df_f.at[fi, 'evidence_sources']) + '; ' + info['desc']
                df_f.at[fi, 'verification_date'] = '2026-10-31'

    # Step 3: Beni Suef Regex Bug Fix
    for cid, info in BENI_SUEF_FIXES.items():
        v_idx = df_v[df_v['canonical_entity_id'] == cid].index
        if len(v_idx) > 0:
            i = v_idx[0]
            df_v.at[i, 'tier_classification'] = info['tier']
            df_v.at[i, 'audited_entity_type'] = info['entity_type']
            for qk, qv in info['q'].items():
                col = [c for c in indicators if c.startswith(qk + '_')][0]
                df_v.at[i, col] = qv
            df_v.at[i, 'evidence_sources'] = str(df_v.at[i, 'evidence_sources']) + '; ' + info['source']
            df_v.at[i, 'verification_date'] = '2026-10-31'

            if cid in df_f_map:
                fi = df_f_map[cid]
                df_f.at[fi, 'audited_entity_type'] = info['entity_type']
                for qk, qv in info['q'].items():
                    col = [c for c in indicators if c.startswith(qk + '_')][0]
                    df_f.at[fi, col] = qv
                df_f.at[fi, 'evidence_sources'] = str(df_f.at[fi, 'evidence_sources']) + '; ' + info['source']
                df_f.at[fi, 'verification_date'] = '2026-10-31'

    # Step 4: Qena, Luxor, Aswan Social & Maps Ingestion (206 facilities)
    for cid, v in qla_data.items():
        if cid in EXPLICIT_NICU_ICU_FIXES or cid in MISPLACED_PIN_FIXES or cid in VILLAGE_AND_ARTIFACT_FIXES:
            continue
        v_idx = df_v[df_v['canonical_entity_id'] == cid].index
        if len(v_idx) > 0:
            i = v_idx[0]
            # Ratings update
            for qcol, val in v['ratings'].items():
                df_v.at[i, qcol] = val

            # Evidence update
            src = v.get('evidence_source', '')
            curr_src = str(df_v.at[i, 'evidence_sources'])
            if src and src not in curr_src:
                df_v.at[i, 'evidence_sources'] = curr_src + '; ' + src
            df_v.at[i, 'verification_date'] = '2026-10-31'

            # Category and Tier mapping
            cat = v.get('facility_category_detected', '')
            entity_type = 'Unspecified_Unverified_Facility'
            target_tier = df_v.at[i, 'tier_classification']

            if cat in ['Verified UHIA / EHA General Hospital', 'Verified UHIA Specialized Maternity Hospital']:
                target_tier = 'Tier 1C: Verified SMC Tertiary Specialized Hospital (Social/Maps Enriched)'
                entity_type = 'Verified_UHIA_Maternal_Hospital' if 'Maternity' in cat else 'Verified_UHIA_General_Hospital'
            elif cat in ['Verified University Hospital / Complex', 'Verified University Maternal Hospital']:
                target_tier = 'Tier 1A: Verified University CEmONC Hospital (Social/Maps Enriched)'
                entity_type = 'Verified_University_Maternal_Hospital' if 'Maternal' in cat else 'Verified_University_General_Hospital'
            elif cat in ['Private Multi-Specialty General Hospital', 'Private Maternity Hospital / Center']:
                target_tier = 'Tier 5A: Verified Private Maternity & Surgical Hospital (Social/Maps Enriched)'
                entity_type = 'Verified_Private_Maternity_Surgical_Hospital'
            elif cat == 'Private Fertility and IVF Center':
                target_tier = 'Tier 6: Private Fertility/IVF Center (Social/Maps Enriched)'
                entity_type = 'Private_Fertility_Or_IVF_Center'
            elif cat == 'Rural Village Family Health Unit':
                target_tier = 'Tier 8E: Rural Village/Integration Hospital'
                entity_type = 'Rural_Village_Integration_Hospital'
            elif cat == 'Private Solo Physician Clinic':
                target_tier = 'Tier 8A: Non-Clinical/Commercial/Solo Practice'
                entity_type = 'Private_Solo_Doctor_Practice'
            elif cat in ['Diagnostic Pathology Laboratory', 'Commercial Food Restaurant', 'Governmental Post Office',
                         'Medical Supplies Retail Store', 'Municipal Mortuary', 'Banking ATM', 'Public Park',
                         'Under-Construction Hospital', 'Spreadsheet Summary Row', 'Veterinary Animal Care Unit',
                         'Public Health Administration Office', 'Place-Name or Generic Artifact']:
                target_tier = 'Tier 9: Special Audited (Non-Clinical / Artifact)'
                entity_type = 'Place_Name_Only_Artifact'
                df_v.at[i, 'unresolved_issues'] = f'{cat}; non-clinical artifact excluded from maternal routing graph'

            df_v.at[i, 'tier_classification'] = target_tier
            df_v.at[i, 'audited_entity_type'] = entity_type

            # Facilities dataframe update
            if cid in df_f_map:
                fi = df_f_map[cid]
                df_f.at[fi, 'audited_entity_type'] = entity_type
                if 'Tier 5A' in target_tier or 'Tier 1A' in target_tier or 'Tier 1C' in target_tier:
                    df_f.at[fi, 'birth_service_tier'] = 'T1_maternity_hospital'
                for qcol, val in v['ratings'].items():
                    df_f.at[fi, qcol] = val
                curr_src_f = str(df_f.at[fi, 'evidence_sources'])
                if src and src not in curr_src_f:
                    df_f.at[fi, 'evidence_sources'] = curr_src_f + '; ' + src
                df_f.at[fi, 'verification_date'] = '2026-10-31'
                if cat in ['Diagnostic Pathology Laboratory', 'Commercial Food Restaurant', 'Governmental Post Office',
                           'Medical Supplies Retail Store', 'Municipal Mortuary', 'Banking ATM', 'Public Park',
                           'Under-Construction Hospital', 'Spreadsheet Summary Row', 'Veterinary Animal Care Unit',
                           'Public Health Administration Office', 'Place-Name or Generic Artifact']:
                    df_f.at[fi, 'unresolved_issues'] = f'{cat}; non-clinical artifact excluded from maternal routing graph'

    # Step 5: Beni Suef, Minya, Assiut, Sohag Social & Maps Profiles (90 Facilities)
    enriched_bm_as = {**bm_data, **as_data}
    for cid, info in enriched_bm_as.items():
        if cid in EXPLICIT_NICU_ICU_FIXES or cid in MISPLACED_PIN_FIXES or cid in VILLAGE_AND_ARTIFACT_FIXES:
            continue
        v_idx = df_v[df_v['canonical_entity_id'] == cid].index
        if len(v_idx) > 0:
            i = v_idx[0]
            tier = info['tier']
            df_v.at[i, 'tier_classification'] = tier
            entity_type = TIER_TO_ENTITY_TYPE.get(tier, 'Verified_Private_Maternity_Surgical_Hospital')
            df_v.at[i, 'audited_entity_type'] = entity_type

            for qk in ['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7', 'Q8']:
                if qk in info:
                    col = [c for c in indicators if c.startswith(qk + '_')][0]
                    df_v.at[i, col] = info[qk]

            src_entry = info['source']
            curr_src = str(df_v.at[i, 'evidence_sources'])
            if src_entry not in curr_src:
                df_v.at[i, 'evidence_sources'] = curr_src + '; ' + src_entry
            df_v.at[i, 'verification_date'] = '2026-10-31'

            if cid in df_f_map:
                fi = df_f_map[cid]
                df_f.at[fi, 'audited_entity_type'] = entity_type
                if 'Tier 5A' in tier or 'Tier 5B' in tier or 'Tier 1A' in tier:
                    df_f.at[fi, 'birth_service_tier'] = 'T1_maternity_hospital'
                for qk in ['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7', 'Q8']:
                    if qk in info:
                        col = [c for c in indicators if c.startswith(qk + '_')][0]
                        df_f.at[fi, col] = info[qk]
                curr_src_f = str(df_f.at[fi, 'evidence_sources'])
                if src_entry not in curr_src_f:
                    df_f.at[fi, 'evidence_sources'] = curr_src_f + '; ' + src_entry
                df_f.at[fi, 'verification_date'] = '2026-10-31'

    # Step 6: Explicit NICU/ICU Enforcements (CE00166, CE00034, CE01723)
    for cid, info in EXPLICIT_NICU_ICU_FIXES.items():
        v_idx = df_v[df_v['canonical_entity_id'] == cid].index
        if len(v_idx) > 0:
            i = v_idx[0]
            df_v.at[i, 'tier_classification'] = info['tier']
            df_v.at[i, 'audited_entity_type'] = info['entity_type']
            for qk, qv in info['q'].items():
                col = [c for c in indicators if c.startswith(qk + '_')][0]
                df_v.at[i, col] = qv
            df_v.at[i, 'evidence_sources'] = str(df_v.at[i, 'evidence_sources']) + '; ' + info['source']
            df_v.at[i, 'verification_date'] = '2026-10-31'

            if cid in df_f_map:
                fi = df_f_map[cid]
                df_f.at[fi, 'audited_entity_type'] = info['entity_type']
                for qk, qv in info['q'].items():
                    col = [c for c in indicators if c.startswith(qk + '_')][0]
                    df_f.at[fi, col] = qv
                df_f.at[fi, 'evidence_sources'] = str(df_f.at[fi, 'evidence_sources']) + '; ' + info['source']
                df_f.at[fi, 'verification_date'] = '2026-10-31'

    # Step 7: Document Cross-Governorate Misassigned Pins (45 facilities)
    cross_count = 0
    for idx, r in df_v.iterrows():
        cid = r['canonical_entity_id']
        if cid in MISPLACED_PIN_FIXES:
            continue
        gov_ass = r['governorate_assigned']
        dist = str(r['district']).strip().lower()
        true_gov = DISTRICT_TO_GOV.get(dist)
        if true_gov and true_gov != gov_ass:
            cross_count += 1
            dist_val = r['district']
            note = f'Geographically located in {true_gov} Governorate (district: {dist_val}); cross-governorate misassigned pin under {gov_ass} in legacy scrape.'
            df_v.at[idx, 'unresolved_issues'] = note
            if cid in df_f_map:
                fi = df_f_map[cid]
                df_f.at[fi, 'unresolved_issues'] = note

    # Step 8: Clean HTML entities and deduplicate evidence_sources
    for idx in range(len(df_v)):
        cname = str(df_v.at[idx, 'canonical_name']).replace('&#10;', '').replace('&#13;', '').strip()
        df_v.at[idx, 'canonical_name'] = cname
        cid = df_v.at[idx, 'canonical_entity_id']
        if cid in df_f_map:
            fi = df_f_map[cid]
            df_f.at[fi, 'canonical_name'] = cname

        ev_v = str(df_v.at[idx, 'evidence_sources'])
        parts_v = [p.strip() for p in ev_v.split(';') if p.strip()]
        dedup_v = '; '.join(dict.fromkeys(parts_v))
        df_v.at[idx, 'evidence_sources'] = dedup_v

        if cid in df_f_map:
            fi = df_f_map[cid]
            ev_f = str(df_f.at[fi, 'evidence_sources'])
            parts_f = [p.strip() for p in ev_f.split(';') if p.strip()]
            dedup_f = '; '.join(dict.fromkeys(parts_f))
            df_f.at[fi, 'evidence_sources'] = dedup_f

    return df_v, df_f

def save_data(df_v, df_f, qa_dir=DEFAULT_QA_DIR, datasets_dir=DEFAULT_DATASETS_DIR, repo_work_dir=DEFAULT_REPO_WORK_DIR, sync_repo=True):
    """Write out enriched CSV files and synchronize with repo_work."""
    val_out = os.path.join(qa_dir, 'hospital_validation.csv')
    fac_out = os.path.join(datasets_dir, 'facilities_sorted_by_governorate.csv')

    df_v.to_csv(val_out, index=False, encoding='utf-8')
    df_f.to_csv(fac_out, index=False, encoding='utf-8')
    print('Successfully wrote updated validation CSV: ' + val_out)
    print('Successfully wrote updated facilities CSV: ' + fac_out)

    # Generate synchronized temp_q validation files
    q13_df = pd.DataFrame({
        'facility_id': df_v['canonical_entity_id'],
        'Q1_maternity_services': df_v['Q1_maternity_services'],
        'Q2_obstetric_emerg_24_7': df_v['Q2_obstetric_emerg_24_7'],
        'Q3_emergency_csection_24_7': df_v['Q3_emergency_csection_24_7'],
        'Q1_Q3_evidence_source': df_v['evidence_sources']
    })
    q13_path = os.path.join(qa_dir, 'temp_q1_q2_q3_validation.csv')
    q13_df.to_csv(q13_path, index=False, encoding='utf-8')
    print('Successfully wrote updated Q1-Q3 validation CSV: ' + q13_path)

    q46_df = pd.DataFrame({
        'facility_id': df_v['canonical_entity_id'],
        'Q4_qualified_doctor_24_7': df_v['Q4_qualified_doctor_24_7'],
        'Q5_blood_bank_transfusion': df_v['Q5_blood_bank_transfusion'],
        'Q6_maternal_icu': df_v['Q6_maternal_icu'],
        'Q4_Q6_evidence_source': df_v['evidence_sources']
    })
    q46_path = os.path.join(qa_dir, 'temp_q4_q5_q6_validation.csv')
    q46_df.to_csv(q46_path, index=False, encoding='utf-8')
    print('Successfully wrote updated Q4-Q6 validation CSV: ' + q46_path)

    q78_df = pd.DataFrame({
        'facility_id': df_v['canonical_entity_id'],
        'Q7_nicu': df_v['Q7_nicu'],
        'Q8_stabilize_and_refer': df_v['Q8_stabilize_and_refer'],
        'Q7_Q8_evidence_source': df_v['evidence_sources']
    })
    q78_path = os.path.join(qa_dir, 'temp_q7_q8_validation.csv')
    q78_df.to_csv(q78_path, index=False, encoding='utf-8')
    print('Successfully wrote updated Q7-Q8 validation CSV: ' + q78_path)

    if sync_repo and os.path.exists(repo_work_dir):
        repo_qa_dir = os.path.join(repo_work_dir, 'Q&A')
        os.makedirs(repo_qa_dir, exist_ok=True)

        for fname, dframe in [
            ('hospital_validation.csv', df_v),
            ('temp_q1_q2_q3_validation.csv', q13_df),
            ('temp_q4_q5_q6_validation.csv', q46_df),
            ('temp_q7_q8_validation.csv', q78_df)
        ]:
            out_p = os.path.join(repo_qa_dir, fname)
            dframe.to_csv(out_p, index=False, encoding='utf-8')
            print('Synchronized to repo_work/Q&A: ' + out_p)

        repo_fac_out = os.path.join(repo_work_dir, 'facilities_sorted_by_governorate.csv')
        df_f.to_csv(repo_fac_out, index=False, encoding='utf-8')
        print('Synchronized to repo_work: ' + repo_fac_out)

        # Also copy json files and enrichment script
        for jname in ['temp_benisuef_minya_social_maps.json', 'temp_assiut_sohag_social_maps.json', 'temp_qena_luxor_aswan_social_maps.json', 'enrich_social_and_maps.py']:
            src_j = os.path.join(qa_dir, jname)
            dst_j = os.path.join(repo_qa_dir, jname)
            if os.path.exists(src_j):
                shutil.copy2(src_j, dst_j)
                print('Synchronized file: ' + dst_j)

def print_audit_report(df_before, df_after):
    """Print comparative audit metrics before and after enrichment."""
    indicators = [
        'Q1_maternity_services', 'Q2_obstetric_emerg_24_7', 'Q3_emergency_csection_24_7',
        'Q4_qualified_doctor_24_7', 'Q5_blood_bank_transfusion', 'Q6_maternal_icu',
        'Q7_nicu', 'Q8_stabilize_and_refer'
    ]

    print('=' * 80)
    print('FINAL 7-GOVERNORATE HOSPITAL READINESS Q1-Q8 AUDIT (BEFORE VS AFTER ENRICHMENT)')
    print('=' * 80)

    header = f"{'Indicator':<30} | {'Status':<12} | {'Before':<8} | {'After':<8} | {'Delta':<8}"
    print(header)
    print('-' * len(header))

    for ind in indicators:
        vc_b = df_before[ind].value_counts().to_dict()
        vc_a = df_after[ind].value_counts().to_dict()
        for cat in ['Yes', 'Mostly Yes', 'Mostly No', 'No']:
            b_cnt = vc_b.get(cat, 0)
            a_cnt = vc_a.get(cat, 0)
            diff = a_cnt - b_cnt
            diff_str = f'+{diff}' if diff > 0 else str(diff)
            print(f"{ind:<30} | {cat:<12} | {b_cnt:<8} | {a_cnt:<8} | {diff_str:<8}")
        print('-' * len(header))

    print('\n' + 'TOP 12 TIER CLASSIFICATIONS (POST-ENRICHMENT):')
    vc_tiers = df_after['tier_classification'].value_counts()
    for t_name, count in vc_tiers.head(15).items():
        print(f'  {t_name:<75}: {count}')

    print('=' * 80)

def main():
    parser = argparse.ArgumentParser(description='Automated Social Media, Google Maps & Directory Enrichment Script')
    parser.add_argument('--qa-dir', default=DEFAULT_QA_DIR, help='Path to Q&A directory')
    parser.add_argument('--datasets-dir', default=DEFAULT_DATASETS_DIR, help='Path to datasets directory')
    parser.add_argument('--repo-work-dir', default=DEFAULT_REPO_WORK_DIR, help='Path to repo_work directory')
    parser.add_argument('--dry-run', action='store_true', help='Perform simulation without writing files')
    parser.add_argument('--no-sync', action='store_true', help='Skip syncing to repo_work')

    args = parser.parse_args()

    print('Loading datasets and all 3 enrichment dictionaries...')
    df_val, df_fac, bm_data, as_data, qla_data = load_data(args.qa_dir, args.datasets_dir)
    print(f'Loaded {len(df_val)} validation rows, {len(df_fac)} facilities rows.')
    print(f'Enrichment pools: Beni Suef/Minya={len(bm_data)}, Assiut/Sohag={len(as_data)}, Qena/Luxor/Aswan={len(qla_data)}.')

    print('\n' + 'Running 7-governorate enrichment pipeline...')
    df_val_enriched, df_fac_enriched = enrich_pipeline(df_val, df_fac, bm_data, as_data, qla_data)

    print('\n' + 'Audit Report:')
    print_audit_report(df_val, df_val_enriched)

    if not args.dry_run:
        print('\n' + 'Saving enriched datasets across all files...')
        save_data(df_val_enriched, df_fac_enriched, args.qa_dir, args.datasets_dir, args.repo_work_dir, sync_repo=not args.no_sync)
    else:
        print('\n' + '[DRY RUN] No files were modified.')

if __name__ == '__main__':
    main()
