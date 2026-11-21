#!/usr/bin/env python3
"""
generate_maternacare_navigator.py

Task A: Builds the standalone interactive MaternaCare Patient & Triage Navigator
web application (maternacare_navigator.html) embedding:
  - All deduplicated Upper Egypt clinical facilities + 7 verified Regional NBTS Blood Banks
  - Full Q1-Q8 clinical readiness scorecards and callable phone/hotline numbers
  - One-click pregnant-woman clinical need filters (Delivery, 24/7 C-Section,
    Prenatal Checkups/Clinics, Blood Banks, Maternal ICU, NICU)
  - Interactive "Find Nearest Ready Hospital" Emergency Triage Simulator with
    route lines, distance/ETA ranking, and turn-by-turn Google Maps directions
  - Governorate Coverage Dashboard and filtered CSV export

Zero emojis, zero em-dashes or en-dashes (standard ASCII hyphens - only).
"""

import os
import re
import json
import pandas as pd

BASE_DIR = '/home/yousefmahmoudali/Desktop/GradII'
ROUTING_CSV = os.path.join(BASE_DIR, 'datasets', 'maternal_facilities_routing_ready.csv')
OUT_HTML = os.path.join(BASE_DIR, 'maternacare_navigator.html')
REPO_OUT_HTML = os.path.join(BASE_DIR, 'repo_work', 'maternacare_navigator.html')

EMOJI_RE = re.compile(r'[\U00010000-\U0010ffff]', flags=re.UNICODE)
DASH_RE = re.compile(r'[\u2014\u2013]')

df = pd.read_csv(ROUTING_CSV)
print(f"Loaded {len(df)} routing-ready physical nodes from {ROUTING_CSV}")

records = []
for _, r in df.iterrows():
    records.append({
        'id': str(r['canonical_entity_id']),
        'name': str(r['canonical_name']),
        'ar': str(r['original_arabic_name']),
        'gov': str(r['governorate_assigned']),
        'dist': str(r['district']),
        'addr': str(r['address']),
        'lat': float(r['latitude_final']),
        'lon': float(r['longitude_final']),
        'phone': str(r['phone_clean']),
        'e164': str(r['phone_e164']),
        'ptype': str(r['phone_type']),
        'fclass': str(r['facility_class']),
        'fcat': str(r['facility_category']),
        'tier': str(r['birth_service_tier']),
        'role': str(r['care_role']),
        'score': float(r['readiness_score_0_to_8']),
        'q1': str(r['Q1_maternity_services']),
        'q2': str(r['Q2_obstetric_emerg_24_7']),
        'q3': str(r['Q3_emergency_csection_24_7']),
        'q4': str(r['Q4_qualified_doctor_24_7']),
        'q5': str(r['Q5_blood_bank_transfusion']),
        'q6': str(r['Q6_maternal_icu']),
        'q7': str(r['Q7_nicu']),
        'q8': str(r['Q8_stabilize_and_refer']),
        'ev': str(r['evidence_sources']),
        'dups': str(r['merged_duplicate_ids']),
        'nrec': int(r['merged_record_count']),
    })

json_payload = json.dumps(records, ensure_ascii=False)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MaternaCare Upper Egypt - Maternal Readiness &amp; Emergency Triage Navigator</title>

  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin=""/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>

  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css" />
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css" />
  <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>

  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    body { display: flex; height: 100vh; overflow: hidden; background: #0b1120; color: #f1f5f9; }
    #sidebar {
      width: 460px; min-width: 440px; height: 100vh; display: flex; flex-direction: column;
      background: #111827; border-right: 1px solid #1f2937; z-index: 1000;
      box-shadow: 4px 0 18px rgba(0,0,0,0.45);
    }
    #map-container { flex: 1; height: 100vh; position: relative; }
    #map { width: 100%; height: 100%; }

    .header { padding: 14px 18px; background: #0f172a; border-bottom: 1px solid #1f2937; }
    .header-top { display: flex; justify-content: space-between; align-items: center; }
    .header h1 { font-size: 16px; font-weight: 800; color: #38bdf8; letter-spacing: 0.2px; }
    .header .ver-pill { font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 99px; background: #064e3b; color: #34d399; border: 1px solid #059669; }
    .header p { font-size: 11.5px; color: #94a3b8; margin-top: 3px; }

    .tabs { display: flex; background: #0b1120; border-bottom: 1px solid #1f2937; }
    .tab-btn {
      flex: 1; padding: 10px 8px; font-size: 12px; font-weight: 700; color: #94a3b8;
      background: none; border: none; border-bottom: 2px solid transparent; cursor: pointer;
      transition: all 0.15s;
    }
    .tab-btn:hover { color: #e2e8f0; }
    .tab-btn.active { color: #38bdf8; border-bottom-color: #38bdf8; background: #111827; }

    .tab-pane { flex: 1; overflow-y: auto; padding: 14px 16px; display: none; }
    .tab-pane.active { display: block; }

    .section-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px; color: #94a3b8; margin-bottom: 7px; display: block; }
    .preset-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 12px; }
    .preset-btn {
      padding: 8px 9px; border-radius: 7px; border: 1px solid #334155; background: #1e293b;
      color: #e2e8f0; font-size: 11.5px; font-weight: 600; cursor: pointer; text-align: left;
      transition: all 0.15s; display: flex; justify-content: space-between; align-items: center;
    }
    .preset-btn:hover { border-color: #38bdf8; background: #0f172a; }
    .preset-btn.active { border-color: #38bdf8; background: #0c4a6e; color: #ffffff; box-shadow: 0 0 0 1px #38bdf8; }
    .preset-count { font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 10px; background: rgba(15,23,42,0.7); color: #94a3b8; }
    .preset-btn.active .preset-count { background: #0284c7; color: #fff; }

    .row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px; }
    input[type="text"], select {
      width: 100%; padding: 8px 10px; background: #0f172a; border: 1px solid #334155;
      border-radius: 6px; color: #f8fafc; font-size: 12.5px; outline: none;
    }
    input[type="text"]:focus, select:focus { border-color: #38bdf8; }

    .toggle-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-size: 11.5px; color: #cbd5e1; gap: 8px; flex-wrap: wrap; }
    .toggle-bar label { display: flex; align-items: center; gap: 5px; cursor: pointer; }

    .count-bar { display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #0f172a; border-radius: 6px; border: 1px solid #1f2937; margin-bottom: 10px; font-size: 11.5px; color: #94a3b8; }

    .card {
      background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 10px 12px;
      margin-bottom: 8px; cursor: pointer; transition: all 0.15s;
    }
    .card:hover { border-color: #38bdf8; background: #172033; }
    .card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
    .card-title { font-size: 13px; font-weight: 700; color: #f8fafc; line-height: 1.25; }
    .card-ar { font-size: 11.5px; color: #94a3b8; margin-top: 2px; direction: rtl; text-align: left; }
    .card-meta { font-size: 11px; color: #94a3b8; margin-top: 4px; }
    .score-pill { font-size: 10.5px; font-weight: 800; padding: 2px 7px; border-radius: 6px; white-space: nowrap; }
    .score-high { background: #064e3b; color: #34d399; border: 1px solid #059669; }
    .score-mid { background: #0c4a6e; color: #38bdf8; border: 1px solid #0284c7; }
    .score-low { background: #334155; color: #cbd5e1; border: 1px solid #475569; }
    .score-blood { background: #7f1d1d; color: #fca5a5; border: 1px solid #dc2626; }

    .mini-badges { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
    .mini-b { font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 4px; }
    .b-yes { background: #064e3b; color: #6ee7b7; }
    .b-myes { background: #0c4a6e; color: #7dd3fc; }
    .b-mno { background: #78350f; color: #fcd34d; }
    .b-no { background: #450a0a; color: #fca5a5; }
    .b-role-blood { background: #991b1b; color: #ffffff; }
    .b-role-cemonc { background: #065f46; color: #d1fae5; }
    .b-role-deliv { background: #1e40af; color: #dbeafe; }
    .b-role-anc { background: #115e59; color: #ccfbf1; }
    .b-role-spec { background: #334155; color: #cbd5e1; }

    .btn {
      display: inline-block; width: 100%; padding: 9px 12px; border-radius: 6px; border: none;
      font-size: 12.5px; font-weight: 700; cursor: pointer; text-align: center; text-decoration: none;
      transition: background 0.15s; margin-bottom: 8px;
    }
    .btn-primary { background: #0284c7; color: #fff; }
    .btn-primary:hover { background: #0369a1; }
    .btn-danger { background: #dc2626; color: #fff; }
    .btn-danger:hover { background: #b91c1c; }
    .btn-secondary { background: #334155; color: #f1f5f9; }
    .btn-secondary:hover { background: #475569; }
    .btn-chip {
      width: auto; padding: 4px 8px; font-size: 11px; margin: 0 4px 4px 0;
      background: #1e293b; color: #cbd5e1; border: 1px solid #334155; border-radius: 5px;
    }
    .btn-chip:hover { border-color: #38bdf8; color: #fff; }

    .triage-banner {
      padding: 10px 12px; border-radius: 7px; background: #172554; border: 1px solid #1d4ed8;
      font-size: 12px; color: #dbeafe; margin-bottom: 10px; line-height: 1.45;
    }
    .triage-banner.picking { background: #7f1d1d; border-color: #ef4444; color: #fee2e2; }

    .dist-pill { font-size: 11px; font-weight: 800; padding: 2px 7px; border-radius: 6px; background: #7c2d12; color: #fdba74; border: 1px solid #ea580c; }

    .gov-table { width: 100%; border-collapse: collapse; font-size: 11px; margin-bottom: 14px; }
    .gov-table th, .gov-table td { padding: 6px 5px; border-bottom: 1px solid #1f2937; text-align: center; }
    .gov-table th:first-child, .gov-table td:first-child { text-align: left; font-weight: 700; color: #f8fafc; }
    .gov-table th { background: #0f172a; color: #94a3b8; font-size: 10px; text-transform: uppercase; }
    .gov-table tr:hover td { background: #1e293b; }

    .legend {
      position: absolute; bottom: 20px; right: 18px; z-index: 1000;
      background: rgba(15, 23, 42, 0.94); border: 1px solid #334155; border-radius: 8px;
      padding: 10px 14px; font-size: 11.5px; box-shadow: 0 4px 14px rgba(0,0,0,0.45);
      max-width: 290px;
    }
    .legend-title { font-weight: 800; color: #38bdf8; margin-bottom: 6px; font-size: 12px; }
    .legend-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; color: #e2e8f0; }
    .dot { width: 11px; height: 11px; border-radius: 50%; flex-shrink: 0; border: 1.5px solid #fff; }

    .leaflet-popup-content-wrapper { border-radius: 10px; }
    .pop { width: 310px; color: #0f172a; font-size: 12px; line-height: 1.38; }
    .pop-title { font-size: 14px; font-weight: 800; color: #0f172a; }
    .pop-ar { font-size: 12px; color: #475569; margin-bottom: 5px; direction: rtl; text-align: left; }
    .pop-sub { font-size: 11px; color: #334155; margin-bottom: 6px; padding-bottom: 6px; border-bottom: 1px solid #e2e8f0; }
    .q-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin: 7px 0; }
    .q-cell {
      display: flex; justify-content: space-between; align-items: center;
      padding: 3px 6px; border-radius: 5px; font-size: 10.5px; background: #f1f5f9;
    }
    .q-tag { font-weight: 800; padding: 1px 5px; border-radius: 4px; font-size: 9.5px; }
    .qt-yes { background: #10b981; color: #fff; }
    .qt-myes { background: #0284c7; color: #fff; }
    .qt-mno { background: #f59e0b; color: #fff; }
    .qt-no { background: #ef4444; color: #fff; }
    .pop-ev { font-size: 10.5px; color: #475569; background: #f8fafc; padding: 5px 7px; border-radius: 5px; border: 1px solid #e2e8f0; margin-top: 6px; max-height: 58px; overflow-y: auto; }
    .pop-actions { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 5px; margin-top: 8px; }
    .pop-btn {
      padding: 6px 4px; font-size: 10.5px; font-weight: 700; text-align: center;
      border-radius: 5px; text-decoration: none; color: #fff; display: block;
    }
    .pb-call { background: #059669; }
    .pb-dir { background: #2563eb; }
    .pb-gmap { background: #475569; }

    .pulse-pin {
      width: 18px; height: 18px; border-radius: 50%; background: #ef4444; border: 3px solid #fff;
      box-shadow: 0 0 0 6px rgba(239,68,68,0.35);
    }
  </style>
</head>
<body>
  <div id="sidebar">
    <div class="header">
      <div class="header-top">
        <h1>MaternaCare Upper Egypt Navigator</h1>
        <span class="ver-pill">Verified Q1-Q8 + GPS</span>
      </div>
      <p>Deduplicated clinical facilities, Q1-Q8 readiness scorecards, prenatal clinics &amp; NBTS blood banks</p>
    </div>

    <div class="tabs">
      <button class="tab-btn active" onclick="switchTab('tab-finder', this)">Care Finder</button>
      <button class="tab-btn" onclick="switchTab('tab-triage', this)">Nearest Triage</button>
      <button class="tab-btn" onclick="switchTab('tab-stats', this)">Coverage Stats</button>
    </div>

    <div id="tab-finder" class="tab-pane active">
      <span class="section-label">1. What does the pregnant woman need?</span>
      <div class="preset-grid" id="preset-grid">
        <button class="preset-btn active" data-preset="MATERNAL_ALL" onclick="setPreset('MATERNAL_ALL', this)">
          <span>All Maternal &amp; Blood</span><span class="preset-count" id="cnt-MATERNAL_ALL">-</span>
        </button>
        <button class="preset-btn" data-preset="DELIVERY" onclick="setPreset('DELIVERY', this)">
          <span>Give Birth (Q1)</span><span class="preset-count" id="cnt-DELIVERY">-</span>
        </button>
        <button class="preset-btn" data-preset="EMERGENCY_CS" onclick="setPreset('EMERGENCY_CS', this)">
          <span>24/7 C-Section (Q2-Q4)</span><span class="preset-count" id="cnt-EMERGENCY_CS">-</span>
        </button>
        <button class="preset-btn" data-preset="PRENATAL" onclick="setPreset('PRENATAL', this)">
          <span>Prenatal / MCH Clinics</span><span class="preset-count" id="cnt-PRENATAL">-</span>
        </button>
        <button class="preset-btn" data-preset="BLOOD" onclick="setPreset('BLOOD', this)">
          <span>Blood Banks (Q5+NBTS)</span><span class="preset-count" id="cnt-BLOOD">-</span>
        </button>
        <button class="preset-btn" data-preset="MICU" onclick="setPreset('MICU', this)">
          <span>Maternal ICU (Q6)</span><span class="preset-count" id="cnt-MICU">-</span>
        </button>
        <button class="preset-btn" data-preset="NICU" onclick="setPreset('NICU', this)">
          <span>Newborn NICU (Q7)</span><span class="preset-count" id="cnt-NICU">-</span>
        </button>
        <button class="preset-btn" data-preset="ALL_INC_SPEC" onclick="setPreset('ALL_INC_SPEC', this)">
          <span>All (+ Non-Maternity)</span><span class="preset-count" id="cnt-ALL_INC_SPEC">-</span>
        </button>
      </div>

      <span class="section-label">2. Filter by Governorate &amp; Search</span>
      <div class="row-2">
        <select id="gov-select" onchange="applyFinderFilters()">
          <option value="ALL">All 7 Governorates</option>
          <option value="Beni Suef">Beni Suef</option>
          <option value="Minya">Minya</option>
          <option value="Assiut">Assiut</option>
          <option value="Sohag">Sohag</option>
          <option value="Qena">Qena</option>
          <option value="Luxor">Luxor</option>
          <option value="Aswan">Aswan</option>
        </select>
        <input type="text" id="search-box" placeholder="Name, Arabic, district..." oninput="applyFinderFilters()">
      </div>

      <div class="toggle-bar">
        <label><input type="checkbox" id="strict-yes-toggle" onchange="applyFinderFilters()"> Strict "Yes" only (exclude Mostly Yes)</label>
        <label><input type="checkbox" id="cluster-toggle" checked onchange="toggleClustering()"> Cluster pins</label>
      </div>

      <div class="count-bar">
        <span id="shown-count">Showing 0 facilities</span>
        <span style="color:#38bdf8; cursor:pointer; font-weight:700;" onclick="fitFilteredBounds()">Fit Map</span>
      </div>

      <div id="finder-list"></div>
    </div>

    <div id="tab-triage" class="tab-pane">
      <div class="triage-banner" id="triage-banner">
        Select a clinical emergency scenario, then click <strong>Pick Patient Location on Map</strong> (or choose a quick city button below) to rank the nearest capable facilities with driving directions.
      </div>

      <span class="section-label">Clinical Scenario / Required Capability</span>
      <select id="triage-scenario" onchange="if(patientLatLng) runTriage(patientLatLng.lat, patientLatLng.lng)" style="margin-bottom: 10px;">
        <option value="CRITICAL_HEMORRHAGE">Severe Complication / Hemorrhage (C-Section + Blood Bank + M-ICU)</option>
        <option value="EMERGENCY_CS">24/7 Emergency C-Section &amp; Doctor (Q2 + Q3 + Q4)</option>
        <option value="DELIVERY">Routine Childbirth / Delivery (Q1)</option>
        <option value="NICU">Preterm / Critical Newborn Emergency (Q7 NICU)</option>
        <option value="BLOOD">Emergency Blood Bank / Transfusion (Q5 or Regional NBTS)</option>
        <option value="PRENATAL">Routine Prenatal Checkup / Antenatal Clinic</option>
      </select>

      <div class="row-2">
        <button class="btn btn-danger" id="pick-btn" onclick="enableMapPickMode()">Pick Patient on Map</button>
        <button class="btn btn-secondary" onclick="useBrowserGPS()">Use My GPS</button>
      </div>

      <span class="section-label">Or Quick-Test From a City Center</span>
      <div style="margin-bottom: 10px;">
        <button class="btn-chip" onclick="runTriage(29.0661, 31.0994)">Beni Suef</button>
        <button class="btn-chip" onclick="runTriage(28.0980, 30.7520)">Minya</button>
        <button class="btn-chip" onclick="runTriage(27.7315, 30.8415)">Mallawi</button>
        <button class="btn-chip" onclick="runTriage(27.1810, 31.1837)">Assiut</button>
        <button class="btn-chip" onclick="runTriage(26.5569, 31.6948)">Sohag</button>
        <button class="btn-chip" onclick="runTriage(26.1615, 32.7180)">Qena</button>
        <button class="btn-chip" onclick="runTriage(25.6872, 32.6396)">Luxor</button>
        <button class="btn-chip" onclick="runTriage(25.2935, 32.5540)">Esna</button>
        <button class="btn-chip" onclick="runTriage(24.9785, 32.8735)">Edfu</button>
        <button class="btn-chip" onclick="runTriage(24.0889, 32.8998)">Aswan</button>
      </div>

      <div id="triage-results">
        <p style="font-size: 12px; color: #64748b; text-align: center; margin-top: 24px;">
          No patient location set yet. Click "Pick Patient on Map" or tap any city above.
        </p>
      </div>
    </div>

    <div id="tab-stats" class="tab-pane">
      <span class="section-label">Upper Egypt Governorate Readiness Matrix (Deduplicated Nodes)</span>
      <table class="gov-table" id="gov-stats-table">
        <thead>
          <tr>
            <th>Governorate</th>
            <th>Total</th>
            <th>Q1 Deliv</th>
            <th>Q3 CS</th>
            <th>Blood</th>
            <th>M-ICU</th>
            <th>NICU</th>
            <th>Clinics</th>
          </tr>
        </thead>
        <tbody id="gov-stats-body"></tbody>
      </table>

      <div style="font-size: 11.5px; color: #94a3b8; line-height: 1.5; margin-bottom: 14px; background: #0f172a; padding: 10px 12px; border-radius: 7px; border: 1px solid #1f2937;">
        <strong>About This Dataset:</strong><br>
        - Deduplicated physical Upper Egypt nodes from <code>maternal_facilities_routing_ready.csv</code> (excluding 7 Out-of-Upper-Egypt rows, 1 summary row, non-clinical artifacts, and duplicate source pins).<br>
        - Includes <strong>7 Regional NBTS Blood Banks</strong> (Beni Suef, Minya, Assiut, Sohag, Qena, Luxor, Aswan) verified under Law No. 8 of 2021.<br>
        - Emergency Hotlines: <strong>137</strong> (MOHP Critical Care &amp; Referral) and <strong>123</strong> (Egyptian Ambulance Authority).
      </div>

      <button class="btn btn-primary" onclick="exportFilteredCSV()">Export Current Filtered View (CSV)</button>
    </div>
  </div>

  <div id="map-container">
    <div id="map"></div>
    <div class="legend">
      <div class="legend-title">Care Role Legend</div>
      <div class="legend-row"><span class="dot" style="background:#dc2626; width:13px; height:13px;"></span><span>Regional NBTS Blood Bank (7 Hubs)</span></div>
      <div class="legend-row"><span class="dot" style="background:#10b981;"></span><span>CEmONC Tertiary Hub (CS + Blood + ICU/NICU)</span></div>
      <div class="legend-row"><span class="dot" style="background:#3b82f6;"></span><span>Delivery &amp; General Hospital</span></div>
      <div class="legend-row"><span class="dot" style="background:#14b8a6;"></span><span>Prenatal Clinic / OB-GYN / MCH Unit</span></div>
      <div class="legend-row"><span class="dot" style="background:#64748b;"></span><span>Non-Maternity Specialty Hospital</span></div>
    </div>
  </div>

  <script>
    const FACILITIES = __JSON_PAYLOAD__;
    const GOV_ORDER = ['Beni Suef', 'Minya', 'Assiut', 'Sohag', 'Qena', 'Luxor', 'Aswan'];

    const googleStreets = L.tileLayer('https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}', { maxZoom: 20, attribution: '&copy; Google Maps' });
    const esriSatellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19, attribution: 'Tiles &copy; Esri' });
    const googleHybrid = L.tileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', { maxZoom: 20, attribution: '&copy; Google Satellite' });
    const esriStreets = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19, attribution: 'Tiles &copy; Esri' });

    const map = L.map('map', { center: [26.8, 31.6], zoom: 7, layers: [googleStreets] });
    L.control.layers({
      "Google Streets (Default)": googleStreets,
      "High-Res Satellite (ESRI)": esriSatellite,
      "Google Hybrid (Satellite + Roads)": googleHybrid,
      "ESRI Street Map": esriStreets
    }).addTo(map);

    let clusterLayer = L.markerClusterGroup({ chunkedLoading: true, maxClusterRadius: 38, spiderfyOnMaxZoom: true });
    let directLayer = L.featureGroup();
    let triageLayer = L.featureGroup();
    map.addLayer(clusterLayer);
    map.addLayer(triageLayer);

    let useClustering = true;
    let currentPreset = 'MATERNAL_ALL';
    let currentFiltered = [];
    let markerById = new Map();
    let isPickingLocation = false;
    let patientLatLng = null;

    function isPos(val, strict) {
      return strict ? (val === 'Yes') : (val === 'Yes' || val === 'Mostly Yes');
    }

    function matchesPreset(f, preset, strict) {
      if (preset === 'ALL_INC_SPEC') return true;
      if (preset === 'MATERNAL_ALL') return f.role !== 'non_maternity_specialty_hospital';
      if (preset === 'DELIVERY') return isPos(f.q1, strict);
      if (preset === 'EMERGENCY_CS') return isPos(f.q2, strict) && isPos(f.q3, strict) && isPos(f.q4, strict);
      if (preset === 'PRENATAL') return f.role === 'prenatal_clinic_and_mch_unit';
      if (preset === 'BLOOD') return f.role === 'regional_blood_bank' || isPos(f.q5, strict);
      if (preset === 'MICU') return isPos(f.q6, strict);
      if (preset === 'NICU') return isPos(f.q7, strict);
      if (preset === 'CRITICAL_HEMORRHAGE') return isPos(f.q3, strict) && isPos(f.q5, strict) && isPos(f.q6, strict);
      return true;
    }

    function roleColor(role) {
      if (role === 'regional_blood_bank') return '#dc2626';
      if (role === 'cemonc_tertiary_hub') return '#10b981';
      if (role === 'delivery_and_emergency_hospital') return '#3b82f6';
      if (role === 'prenatal_clinic_and_mch_unit') return '#14b8a6';
      return '#64748b';
    }

    function roleLabel(role) {
      if (role === 'regional_blood_bank') return ['Regional Blood Bank', 'b-role-blood'];
      if (role === 'cemonc_tertiary_hub') return ['CEmONC Tertiary Hub', 'b-role-cemonc'];
      if (role === 'delivery_and_emergency_hospital') return ['Delivery Hospital', 'b-role-deliv'];
      if (role === 'prenatal_clinic_and_mch_unit') return ['Prenatal / MCH Clinic', 'b-role-anc'];
      return ['Non-Maternity Specialty', 'b-role-spec'];
    }

    function qTagClass(val) {
      if (val === 'Yes') return 'qt-yes';
      if (val === 'Mostly Yes') return 'qt-myes';
      if (val === 'Mostly No') return 'qt-mno';
      return 'qt-no';
    }

    function miniClass(val) {
      if (val === 'Yes') return 'b-yes';
      if (val === 'Mostly Yes') return 'b-myes';
      if (val === 'Mostly No') return 'b-mno';
      return 'b-no';
    }

    function haversineKm(lat1, lon1, lat2, lon2) {
      const R = 6371.0;
      const p1 = lat1 * Math.PI / 180, p2 = lat2 * Math.PI / 180;
      const dp = (lat2 - lat1) * Math.PI / 180, dl = (lon2 - lon1) * Math.PI / 180;
      const a = Math.sin(dp/2)**2 + Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)**2;
      return 2 * R * Math.asin(Math.sqrt(Math.min(1, a)));
    }

    function buildPopup(f) {
      const [rTxt] = roleLabel(f.role);
      const dirUrl = patientLatLng
        ? `https://www.google.com/maps/dir/?api=1&origin=${patientLatLng.lat},${patientLatLng.lng}&destination=${f.lat},${f.lon}&travelmode=driving`
        : `https://www.google.com/maps/dir/?api=1&destination=${f.lat},${f.lon}&travelmode=driving`;
      const pinUrl = `https://www.google.com/maps?q=${f.lat},${f.lon}`;
      const callDisp = f.ptype === 'hotline' ? `Hotline ${f.phone}` : `0${f.phone}`;
      return `
        <div class="pop">
          <div class="pop-title">${f.name}</div>
          <div class="pop-ar">${f.ar}</div>
          <div class="pop-sub">
            <strong>${rTxt}</strong> | ID: <code>${f.id}</code> | Score: <strong>${f.score.toFixed(1)}/8</strong><br>
            ${f.dist}, ${f.gov} | Class: <code>${f.fclass}</code><br>
            <span style="color:#64748b;">${f.addr}</span>
          </div>
          <div class="q-grid">
            <div class="q-cell"><span>Q1 Delivery</span><span class="q-tag ${qTagClass(f.q1)}">${f.q1}</span></div>
            <div class="q-cell"><span>Q2 24/7 OB ER</span><span class="q-tag ${qTagClass(f.q2)}">${f.q2}</span></div>
            <div class="q-cell"><span>Q3 24/7 C-Sec</span><span class="q-tag ${qTagClass(f.q3)}">${f.q3}</span></div>
            <div class="q-cell"><span>Q4 24/7 Doctor</span><span class="q-tag ${qTagClass(f.q4)}">${f.q4}</span></div>
            <div class="q-cell"><span>Q5 Blood Bank</span><span class="q-tag ${qTagClass(f.q5)}">${f.q5}</span></div>
            <div class="q-cell"><span>Q6 Maternal ICU</span><span class="q-tag ${qTagClass(f.q6)}">${f.q6}</span></div>
            <div class="q-cell"><span>Q7 NICU</span><span class="q-tag ${qTagClass(f.q7)}">${f.q7}</span></div>
            <div class="q-cell"><span>Q8 Stabilize</span><span class="q-tag ${qTagClass(f.q8)}">${f.q8}</span></div>
          </div>
          <div class="pop-ev"><strong>Evidence:</strong> ${f.ev}</div>
          <div class="pop-actions">
            <a class="pop-btn pb-call" href="tel:${f.e164}">Call ${callDisp}</a>
            <a class="pop-btn pb-dir" href="${dirUrl}" target="_blank">Directions</a>
            <a class="pop-btn pb-gmap" href="${pinUrl}" target="_blank">GPS Pin</a>
          </div>
        </div>
      `;
    }

    function updatePresetCounts() {
      const gov = document.getElementById('gov-select').value;
      const strict = document.getElementById('strict-yes-toggle').checked;
      const pool = gov === 'ALL' ? FACILITIES : FACILITIES.filter(f => f.gov === gov);
      ['MATERNAL_ALL','DELIVERY','EMERGENCY_CS','PRENATAL','BLOOD','MICU','NICU','ALL_INC_SPEC'].forEach(p => {
        const el = document.getElementById('cnt-' + p);
        if (el) el.innerText = pool.filter(f => matchesPreset(f, p, strict)).length;
      });
    }

    function setPreset(preset, btnEl) {
      currentPreset = preset;
      document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
      if (btnEl) btnEl.classList.add('active');
      applyFinderFilters();
    }

    function applyFinderFilters() {
      const gov = document.getElementById('gov-select').value;
      const q = document.getElementById('search-box').value.toLowerCase().trim();
      const strict = document.getElementById('strict-yes-toggle').checked;
      updatePresetCounts();

      currentFiltered = FACILITIES.filter(f => {
        if (gov !== 'ALL' && f.gov !== gov) return false;
        if (!matchesPreset(f, currentPreset, strict)) return false;
        if (q) {
          const hit = f.name.toLowerCase().includes(q) || f.ar.toLowerCase().includes(q) ||
                      f.dist.toLowerCase().includes(q) || f.id.toLowerCase().includes(q) ||
                      f.fclass.toLowerCase().includes(q);
          if (!hit) return false;
        }
        return true;
      }).sort((a, b) => (b.role === 'regional_blood_bank' ? 1 : 0) - (a.role === 'regional_blood_bank' ? 1 : 0) || b.score - a.score);

      document.getElementById('shown-count').innerText = `Showing ${currentFiltered.length} of ${FACILITIES.length} unique nodes`;
      renderMarkers(currentFiltered);
      renderFinderList(currentFiltered);
    }

    function renderMarkers(items) {
      clusterLayer.clearLayers();
      directLayer.clearLayers();
      markerById.clear();

      items.forEach(f => {
        const isBlood = f.role === 'regional_blood_bank';
        const marker = L.circleMarker([f.lat, f.lon], {
          radius: isBlood ? 9 : (f.role === 'cemonc_tertiary_hub' ? 8 : 6.5),
          fillColor: roleColor(f.role),
          color: '#ffffff',
          weight: isBlood ? 2.5 : 1.5,
          opacity: 1,
          fillOpacity: 0.92
        });
        marker.bindPopup(() => buildPopup(f), { maxWidth: 330 });
        markerById.set(f.id, marker);
        if (useClustering && !isBlood) {
          clusterLayer.addLayer(marker);
        } else {
          directLayer.addLayer(marker);
        }
      });
      if (!map.hasLayer(directLayer)) map.addLayer(directLayer);
    }

    function toggleClustering() {
      useClustering = document.getElementById('cluster-toggle').checked;
      renderMarkers(currentFiltered);
    }

    function renderFinderList(items) {
      const box = document.getElementById('finder-list');
      box.innerHTML = '';
      items.slice(0, 75).forEach(f => {
        const [rTxt, rCls] = roleLabel(f.role);
        const sCls = f.role === 'regional_blood_bank' ? 'score-blood' : (f.score >= 6 ? 'score-high' : (f.score >= 3 ? 'score-mid' : 'score-low'));
        const sTxt = f.role === 'regional_blood_bank' ? 'NBTS Hub' : `${f.score.toFixed(1)}/8`;
        const phoneStr = f.ptype === 'hotline' ? `Hotline ${f.phone}` : `0${f.phone}`;
        const div = document.createElement('div');
        div.className = 'card';
        div.onclick = () => focusFacility(f.id);
        div.innerHTML = `
          <div class="card-head">
            <div>
              <div class="card-title">${f.name}</div>
              <div class="card-ar">${f.ar}</div>
            </div>
            <span class="score-pill ${sCls}">${sTxt}</span>
          </div>
          <div class="card-meta">${f.dist}, ${f.gov} | ${phoneStr} | ${f.id}</div>
          <div class="mini-badges">
            <span class="mini-b ${rCls}">${rTxt}</span>
            <span class="mini-b ${miniClass(f.q1)}">Deliv:${f.q1}</span>
            <span class="mini-b ${miniClass(f.q3)}">CS:${f.q3}</span>
            <span class="mini-b ${miniClass(f.q5)}">Blood:${f.q5}</span>
            <span class="mini-b ${miniClass(f.q6)}">ICU:${f.q6}</span>
            <span class="mini-b ${miniClass(f.q7)}">NICU:${f.q7}</span>
          </div>
        `;
        box.appendChild(div);
      });
      if (items.length > 75) {
        const more = document.createElement('div');
        more.style = 'font-size:11px; color:#94a3b8; text-align:center; padding:8px;';
        more.innerText = `+ ${items.length - 75} more facilities (filter by governorate or search to narrow)`;
        box.appendChild(more);
      }
    }

    function focusFacility(id) {
      const m = markerById.get(id);
      if (m) {
        map.setView(m.getLatLng(), 16);
        m.openPopup();
      } else {
        const f = FACILITIES.find(x => x.id === id);
        if (f) {
          map.setView([f.lat, f.lon], 16);
          L.popup({ maxWidth: 330 }).setLatLng([f.lat, f.lon]).setContent(buildPopup(f)).openOn(map);
        }
      }
    }

    function fitFilteredBounds() {
      if (!currentFiltered.length) return;
      const bounds = L.latLngBounds(currentFiltered.map(f => [f.lat, f.lon]));
      map.fitBounds(bounds, { padding: [30, 30] });
    }

    function enableMapPickMode() {
      isPickingLocation = true;
      const b = document.getElementById('triage-banner');
      b.classList.add('picking');
      b.innerHTML = '<strong>Click anywhere on the map</strong> to drop the pregnant patient emergency pin and calculate the nearest capable hospitals.';
      document.getElementById('map').style.cursor = 'crosshair';
    }

    map.on('click', function(e) {
      if (!isPickingLocation) return;
      isPickingLocation = false;
      document.getElementById('map').style.cursor = '';
      const b = document.getElementById('triage-banner');
      b.classList.remove('picking');
      b.innerHTML = `Patient pin set at <strong>${e.latlng.lat.toFixed(5)}, ${e.latlng.lng.toFixed(5)}</strong>. Top capable facilities ranked below.`;
      runTriage(e.latlng.lat, e.latlng.lng);
    });

    function useBrowserGPS() {
      if (!navigator.geolocation) {
        alert('Geolocation is not supported by this browser.');
        return;
      }
      navigator.geolocation.getCurrentPosition(
        pos => runTriage(pos.coords.latitude, pos.coords.longitude),
        err => alert('Could not retrieve GPS location: ' + err.message)
      );
    }

    function runTriage(plat, plon) {
      patientLatLng = { lat: plat, lng: plon };
      triageLayer.clearLayers();
      const scenario = document.getElementById('triage-scenario').value;
      const b = document.getElementById('triage-banner');
      b.classList.remove('picking');
      b.innerHTML = `Patient pin at <strong>${plat.toFixed(4)}, ${plon.toFixed(4)}</strong> | Scenario: <strong>${scenario.replace(/_/g, ' ')}</strong>`;

      const pIcon = L.divIcon({ className: '', html: '<div class="pulse-pin"></div>', iconSize: [18, 18], iconAnchor: [9, 9] });
      L.marker([plat, plon], { icon: pIcon }).bindPopup('<strong>Patient Emergency Location</strong>').addTo(triageLayer);

      const candidates = FACILITIES.filter(f => matchesPreset(f, scenario, false))
        .map(f => ({ ...f, distKm: haversineKm(plat, plon, f.lat, f.lon) }))
        .sort((a, b) => a.distKm - b.distKm);

      const top10 = candidates.slice(0, 10);
      const top5 = candidates.slice(0, 5);
      const lineColors = ['#10b981', '#38bdf8', '#f59e0b', '#a78bfa', '#94a3b8'];

      top5.forEach((f, idx) => {
        L.polyline([[plat, plon], [f.lat, f.lon]], {
          color: lineColors[idx], weight: idx === 0 ? 3.5 : 2, dashArray: idx === 0 ? '' : '5, 5', opacity: 0.9
        }).addTo(triageLayer);
        const mk = L.circleMarker([f.lat, f.lon], {
          radius: idx === 0 ? 10 : 8, fillColor: lineColors[idx], color: '#fff', weight: 2, fillOpacity: 0.95
        }).bindPopup(() => buildPopup(f), { maxWidth: 330 });
        mk.addTo(triageLayer);
      });

      if (top5.length) {
        const pts = [[plat, plon], ...top5.map(f => [f.lat, f.lon])];
        map.fitBounds(L.latLngBounds(pts), { padding: [45, 45], maxZoom: 14 });
      }

      const out = document.getElementById('triage-results');
      out.innerHTML = '';
      if (!top10.length) {
        out.innerHTML = '<p style="font-size:12px; color:#f87171; text-align:center;">No matching facilities found for this scenario.</p>';
        return;
      }

      top10.forEach((f, idx) => {
        const etaMin = Math.max(3, Math.round((f.distKm * 1.25 / 55.0) * 60));
        const dirUrl = `https://www.google.com/maps/dir/?api=1&origin=${plat},${plon}&destination=${f.lat},${f.lon}&travelmode=driving`;
        const phoneStr = f.ptype === 'hotline' ? `Hotline ${f.phone}` : `0${f.phone}`;
        const card = document.createElement('div');
        card.className = 'card';
        card.onclick = () => focusFacility(f.id);
        card.innerHTML = `
          <div class="card-head">
            <div>
              <div class="card-title">#${idx + 1}. ${f.name}</div>
              <div class="card-ar">${f.ar}</div>
            </div>
            <span class="dist-pill">${f.distKm.toFixed(1)} km (~${etaMin} min)</span>
          </div>
          <div class="card-meta">${f.dist}, ${f.gov} | Score: ${f.score.toFixed(1)}/8 | ${phoneStr}</div>
          <div class="mini-badges" style="margin-bottom:7px;">
            <span class="mini-b ${miniClass(f.q1)}">Q1:${f.q1}</span>
            <span class="mini-b ${miniClass(f.q3)}">CS:${f.q3}</span>
            <span class="mini-b ${miniClass(f.q5)}">Blood:${f.q5}</span>
            <span class="mini-b ${miniClass(f.q6)}">M-ICU:${f.q6}</span>
            <span class="mini-b ${miniClass(f.q7)}">NICU:${f.q7}</span>
          </div>
          <div style="display:flex; gap:6px;">
            <a href="tel:${f.e164}" onclick="event.stopPropagation()" class="pop-btn pb-call" style="flex:1;">Call ${phoneStr}</a>
            <a href="${dirUrl}" target="_blank" onclick="event.stopPropagation()" class="pop-btn pb-dir" style="flex:1;">Google Directions</a>
          </div>
        `;
        out.appendChild(card);
      });
    }

    function buildCoverageTable() {
      const tbody = document.getElementById('gov-stats-body');
      tbody.innerHTML = '';
      let totals = [0,0,0,0,0,0,0];
      GOV_ORDER.forEach(g => {
        const sub = FACILITIES.filter(f => f.gov === g);
        const c = [
          sub.length,
          sub.filter(f => isPos(f.q1, false)).length,
          sub.filter(f => isPos(f.q3, false)).length,
          sub.filter(f => f.role === 'regional_blood_bank' || isPos(f.q5, false)).length,
          sub.filter(f => isPos(f.q6, false)).length,
          sub.filter(f => isPos(f.q7, false)).length,
          sub.filter(f => f.role === 'prenatal_clinic_and_mch_unit').length
        ];
        c.forEach((v, i) => totals[i] += v);
        tbody.innerHTML += `<tr><td>${g}</td>${c.map(v => `<td>${v}</td>`).join('')}</tr>`;
      });
      tbody.innerHTML += `<tr style="background:#0f172a; font-weight:800; color:#38bdf8;"><td>TOTAL</td>${totals.map(v => `<td>${v}</td>`).join('')}</tr>`;
    }

    function exportFilteredCSV() {
      const cols = ['id','name','ar','gov','dist','addr','lat','lon','e164','fclass','role','score','q1','q2','q3','q4','q5','q6','q7','q8'];
      const esc = v => '"' + String(v).replace(/"/g, '""') + '"';
      const lines = [cols.join(',')];
      currentFiltered.forEach(f => lines.push(cols.map(c => esc(f[c])).join(',')));
      const blob = new Blob([lines.join('\\n')], { type: 'text/csv;charset=utf-8;' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `maternacare_filtered_${currentPreset.toLowerCase()}.csv`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
    }

    function switchTab(id, btn) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(id).classList.add('active');
    }

    buildCoverageTable();
    applyFinderFilters();
  </script>
</body>
</html>
"""

final_html = HTML_TEMPLATE.replace('__JSON_PAYLOAD__', json_payload)
assert not EMOJI_RE.search(final_html), "Emoji found in generated HTML!"
assert not DASH_RE.search(final_html), "Em/en-dash found in generated HTML!"

with open(OUT_HTML, 'w', encoding='utf-8') as f:
    f.write(final_html)
with open(REPO_OUT_HTML, 'w', encoding='utf-8') as f:
    f.write(final_html)

print(f"Generated {OUT_HTML} ({len(final_html):,} bytes) and synced to {REPO_OUT_HTML}")
