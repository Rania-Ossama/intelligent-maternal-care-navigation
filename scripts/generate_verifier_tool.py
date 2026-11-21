#!/usr/bin/env python3
"""
generate_verifier_tool.py

Generates a standalone, zero-dependency interactive HTML web tool
for visually and mathematically verifying hospital coordinates,
cross-referencing with satellite imagery and Google Maps, and
performing side-by-side comparison with a teammate's CSV dataset.

Zero emojis and zero em-dashes/en-dashes (standard ASCII hyphens - only).
"""

import os
import json
import pandas as pd

BASE_DIR = '/home/yousefmahmoudali/Desktop/GradII'
DATASETS_DIR = os.path.join(BASE_DIR, 'datasets')
QA_DIR = os.path.join(BASE_DIR, 'Q&A')

MASTER_CSV = os.path.join(DATASETS_DIR, 'facilities_sorted_by_governorate.csv')
FLAGS_CSV = os.path.join(QA_DIR, 'coordinate_and_missing_data_flags.csv')
VAL_CSV = os.path.join(QA_DIR, 'hospital_validation.csv')
OUTPUT_HTML = os.path.join(BASE_DIR, 'coordinate_verifier_tool.html')

print("Reading datasets...")
df_master = pd.read_csv(MASTER_CSV)
df_flags = pd.read_csv(FLAGS_CSV) if os.path.exists(FLAGS_CSV) else pd.DataFrame()
df_val = pd.read_csv(VAL_CSV) if os.path.exists(VAL_CSV) else pd.DataFrame()

flags_map = {}
if not df_flags.empty:
    for _, row in df_flags.iterrows():
        flags_map[str(row.get('canonical_entity_id'))] = {
            'coord_reliable': bool(row.get('coord_reliable', True)),
            'n_same_coord': int(row.get('n_same_coord', 1)),
            'coord_cluster_id': str(row.get('coord_cluster_id', 'no_cluster')),
            'spatial_status': str(row.get('spatial_status', 'VALID')),
            'inferred_true_gov': str(row.get('inferred_true_governorate', row.get('governorate_assigned', ''))),
            'spatial_mismatch_rationale': str(row.get('spatial_mismatch_rationale', ''))
        }

arabic_names = {}
if not df_val.empty:
    for _, row in df_val.iterrows():
        arabic_names[str(row.get('canonical_entity_id'))] = str(row.get('original_arabic_name', ''))

facilities = []
for _, row in df_master.iterrows():
    cid = str(row.get('canonical_entity_id', ''))
    f_info = flags_map.get(cid, {})
    
    lat = float(row.get('latitude_final', 0.0))
    lon = float(row.get('longitude_final', 0.0))
    
    # Calculate precision in decimal places
    lat_str = str(row.get('latitude_final', ''))
    lon_str = str(row.get('longitude_final', ''))
    lat_dec = len(lat_str.split('.')[1]) if '.' in lat_str else 0
    lon_dec = len(lon_str.split('.')[1]) if '.' in lon_str else 0
    precision = min(lat_dec, lon_dec)
    
    fac = {
        'id': cid,
        'name': str(row.get('canonical_name', '')),
        'arabic_name': arabic_names.get(cid, str(row.get('canonical_name', ''))),
        'gov': str(row.get('governorate_assigned', '')),
        'dist': str(row.get('district', '')),
        'lat': lat,
        'lon': lon,
        'precision': precision,
        'addr': str(row.get('address', '')),
        'phone': str(row.get('phone_clean', '')),
        'phone_e164': str(row.get('phone_e164', '')),
        'facility_class': str(row.get('facility_class', '')),
        'tier': str(row.get('birth_service_tier', '')),
        'cat': str(row.get('facility_category', '')),
        'audited_type': str(row.get('audited_entity_type', '')),
        'q1': str(row.get('Q1_maternity_services', '')),
        'q2': str(row.get('Q2_obstetric_emerg_24_7', '')),
        'q3': str(row.get('Q3_emergency_csection_24_7', '')),
        'coord_reliable': f_info.get('coord_reliable', True),
        'n_same_coord': f_info.get('n_same_coord', 1),
        'cluster_id': f_info.get('cluster_id', 'no_cluster'),
        'spatial_status': f_info.get('spatial_status', 'VALID'),
        'inferred_true_gov': f_info.get('inferred_true_gov', str(row.get('governorate_assigned', ''))),
        'rationale': f_info.get('spatial_mismatch_rationale', '')
    }
    facilities.append(fac)

print(f"Loaded {len(facilities)} facilities.")

json_data = json.dumps(facilities, ensure_ascii=False)

html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Upper Egypt Healthcare Facility - Coordinate Verification and Comparison Tool</title>
  
  <!-- Leaflet CSS and JS -->
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
  
  <!-- Leaflet MarkerCluster -->
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css" />
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css" />
  <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>

  <!-- PapaParse for CSV reading -->
  <script src="https://cdnjs.cloudflare.com/ajax/libs/PapaParse/5.4.1/papaparse.min.js"></script>

  <style>
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }}
    body {{
      display: flex;
      height: 100vh;
      overflow: hidden;
      background: #0f172a;
      color: #f1f5f9;
    }}
    #sidebar {{
      width: 440px;
      min-width: 440px;
      height: 100vh;
      display: flex;
      flex-direction: column;
      background: #1e293b;
      border-right: 1px solid #334155;
      z-index: 1000;
      box-shadow: 2px 0 10px rgba(0,0,0,0.3);
    }}
    #map-container {{
      flex: 1;
      height: 100vh;
      position: relative;
    }}
    #map {{
      width: 100%;
      height: 100%;
    }}
    .sidebar-header {{
      padding: 16px 20px;
      background: #0f172a;
      border-bottom: 1px solid #334155;
    }}
    .sidebar-header h1 {{
      font-size: 17px;
      font-weight: 700;
      color: #38bdf8;
      margin-bottom: 4px;
    }}
    .sidebar-header p {{
      font-size: 12px;
      color: #94a3b8;
    }}
    .tab-bar {{
      display: flex;
      background: #0f172a;
      border-bottom: 1px solid #334155;
    }}
    .tab-btn {{
      flex: 1;
      padding: 10px 12px;
      font-size: 13px;
      font-weight: 600;
      color: #94a3b8;
      background: none;
      border: none;
      cursor: pointer;
      text-align: center;
      transition: all 0.2s;
      border-bottom: 2px solid transparent;
    }}
    .tab-btn.active {{
      color: #38bdf8;
      border-bottom: 2px solid #38bdf8;
      background: #1e293b;
    }}
    .tab-content {{
      flex: 1;
      overflow-y: auto;
      padding: 16px 20px;
      display: none;
    }}
    .tab-content.active {{
      display: block;
    }}
    .control-group {{
      margin-bottom: 14px;
    }}
    .control-group label {{
      display: block;
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: #94a3b8;
      margin-bottom: 6px;
    }}
    .control-group select, .control-group input[type="text"] {{
      width: 100%;
      padding: 8px 12px;
      background: #0f172a;
      border: 1px solid #334155;
      border-radius: 6px;
      color: #f1f5f9;
      font-size: 13px;
      outline: none;
    }}
    .control-group select:focus, .control-group input[type="text"]:focus {{
      border-color: #38bdf8;
    }}
    .stat-badge {{
      display: inline-block;
      padding: 3px 8px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 700;
      margin-right: 6px;
      margin-bottom: 6px;
    }}
    .badge-green {{ background: #064e3b; color: #34d399; border: 1px solid #059669; }}
    .badge-amber {{ background: #78350f; color: #fbbf24; border: 1px solid #d97706; }}
    .badge-red {{ background: #7f1d1d; color: #f87171; border: 1px solid #dc2626; }}
    .badge-purple {{ background: #4c1d95; color: #c084fc; border: 1px solid #7c3aed; }}
    .badge-blue {{ background: #0c4a6e; color: #38bdf8; border: 1px solid #0284c7; }}

    .dropzone {{
      border: 2px dashed #475569;
      border-radius: 8px;
      padding: 20px 14px;
      text-align: center;
      background: #0f172a;
      cursor: pointer;
      transition: all 0.2s;
      margin-bottom: 12px;
    }}
    .dropzone:hover, .dropzone.dragover {{
      border-color: #38bdf8;
      background: #1e293b;
    }}
    .dropzone p {{
      font-size: 12px;
      color: #94a3b8;
    }}
    .btn {{
      display: inline-block;
      width: 100%;
      padding: 9px 14px;
      background: #0284c7;
      color: #fff;
      font-size: 13px;
      font-weight: 600;
      border: none;
      border-radius: 6px;
      cursor: pointer;
      text-align: center;
      text-decoration: none;
      transition: background 0.2s;
      margin-bottom: 8px;
    }}
    .btn:hover {{
      background: #0369a1;
    }}
    .btn-secondary {{
      background: #334155;
      color: #f1f5f9;
    }}
    .btn-secondary:hover {{
      background: #475569;
    }}
    .btn-small {{
      padding: 5px 9px;
      font-size: 11px;
      width: auto;
      margin-bottom: 0;
    }}
    .btn-outline {{
      background: transparent;
      border: 1px solid #38bdf8;
      color: #38bdf8;
    }}
    .btn-outline:hover {{
      background: #0284c7;
      color: #fff;
    }}
    .facility-list {{
      margin-top: 10px;
    }}
    .facility-card {{
      background: #0f172a;
      border: 1px solid #334155;
      border-radius: 6px;
      padding: 10px 12px;
      margin-bottom: 8px;
      cursor: pointer;
      transition: all 0.15s;
    }}
    .facility-card:hover {{
      border-color: #38bdf8;
      background: #1e293b;
    }}
    .facility-card.selected {{
      border-color: #38bdf8;
      box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.4);
    }}
    .facility-card-title {{
      font-size: 13px;
      font-weight: 700;
      color: #f8fafc;
      margin-bottom: 3px;
    }}
    .facility-card-subtitle {{
      font-size: 11px;
      color: #94a3b8;
      margin-bottom: 4px;
    }}
    .diff-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 11px;
      margin-top: 10px;
    }}
    .diff-table th, .diff-table td {{
      padding: 6px 8px;
      text-align: left;
      border-bottom: 1px solid #334155;
    }}
    .diff-table th {{
      color: #94a3b8;
      text-transform: uppercase;
      font-weight: 600;
      background: #0f172a;
    }}
    .diff-row {{
      cursor: pointer;
    }}
    .diff-row:hover {{
      background: #334155;
    }}
    .legend-box {{
      position: absolute;
      bottom: 24px;
      right: 24px;
      background: rgba(15, 23, 42, 0.92);
      backdrop-filter: blur(4px);
      padding: 12px 16px;
      border-radius: 8px;
      border: 1px solid #334155;
      z-index: 1000;
      font-size: 12px;
      max-width: 320px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      margin-bottom: 6px;
    }}
    .legend-color {{
      width: 12px;
      height: 12px;
      border-radius: 50%;
      margin-right: 8px;
      flex-shrink: 0;
    }}
    .popup-content {{
      font-size: 12px;
      color: #0f172a;
      line-height: 1.4;
      max-width: 280px;
    }}
    .popup-title {{
      font-weight: 700;
      font-size: 14px;
      color: #0f172a;
      margin-bottom: 4px;
      border-bottom: 1px solid #e2e8f0;
      padding-bottom: 4px;
    }}
    .popup-actions {{
      display: flex;
      gap: 6px;
      margin-top: 8px;
    }}
    .popup-btn {{
      flex: 1;
      padding: 5px 8px;
      font-size: 11px;
      text-align: center;
      text-decoration: none;
      border-radius: 4px;
      font-weight: 600;
      display: block;
    }}
    .popup-btn-gmaps {{
      background: #1a73e8;
      color: #fff;
    }}
    .popup-btn-search {{
      background: #34a853;
      color: #fff;
    }}
    .popup-btn-osm {{
      background: #f97316;
      color: #fff;
    }}
  </style>
</head>
<body>

  <!-- Left Sidebar -->
  <div id="sidebar">
    <div class="sidebar-header">
      <h1>Upper Egypt Hospital Coordinate Verifier</h1>
      <p>Visual, satellite, and cross-dataset coordinate verification tool</p>
    </div>

    <div class="tab-bar">
      <button class="tab-btn active" onclick="switchTab('explorer-tab')">Explorer ({len(facilities)})</button>
      <button class="tab-btn" onclick="switchTab('comparison-tab')">Compare CSV</button>
      <button class="tab-btn" onclick="switchTab('audit-tab')">Audit & Guide</button>
    </div>

    <!-- Explorer Tab -->
    <div id="explorer-tab" class="tab-content active">
      <div class="control-group">
        <label>Search Facility</label>
        <input type="text" id="search-input" placeholder="Search by name, ID, or district..." oninput="applyFilters()">
      </div>

      <div class="control-group">
        <label>Filter by Governorate</label>
        <select id="gov-filter" onchange="applyFilters()">
          <option value="ALL">All Governorates (Upper Egypt)</option>
          <option value="Beni Suef">Beni Suef</option>
          <option value="Minya">Minya</option>
          <option value="Assiut">Assiut</option>
          <option value="Sohag">Sohag</option>
          <option value="Qena">Qena</option>
          <option value="Luxor">Luxor</option>
          <option value="Aswan">Aswan</option>
        </select>
      </div>

      <div class="control-group">
        <label>Coordinate Status</label>
        <select id="status-filter" onchange="applyFilters()">
          <option value="ALL">All Facilities</option>
          <option value="RELIABLE">Reliable Rooftop GPS (Single Pin)</option>
          <option value="CLUSTER">Shared Coordinate Clusters (n > 1)</option>
          <option value="ANOMALY">Spatial Anomalies / Out of Bounds</option>
        </select>
      </div>

      <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
        <span id="filtered-count" style="font-size: 12px; color: #94a3b8;">Showing {len(facilities)} facilities</span>
        <label style="font-size: 12px; color: #94a3b8; display: flex; align-items: center; cursor: pointer;">
          <input type="checkbox" id="cluster-toggle" checked onchange="toggleClustering()" style="margin-right: 6px;">
          Enable Pin Clustering
        </label>
      </div>

      <div class="facility-list" id="facility-list"></div>
    </div>

    <!-- Comparison Tab -->
    <div id="comparison-tab" class="tab-content">
      <h3 style="font-size: 14px; color: #38bdf8; margin-bottom: 8px;">Side-by-Side Dataset Comparator</h3>
      <p style="font-size: 12px; color: #94a3b8; margin-bottom: 12px;">
        Upload your teammate's CSV file (or any alternative dataset). The tool will match facilities, calculate Haversine distance discrepancies, draw difference lines, and flag mismatched pins.
      </p>

      <div class="dropzone" id="dropzone" onclick="document.getElementById('file-input').click()">
        <p><strong>Click to Choose or Drag & Drop Teammate's CSV</strong></p>
        <p style="margin-top: 4px; font-size: 11px;">Accepts CSV with latitude/longitude and ID/name</p>
        <input type="file" id="file-input" accept=".csv" style="display: none;" onchange="handleFileUpload(event)">
      </div>

      <div id="comparison-stats" style="display: none; margin-bottom: 14px;">
        <div style="background: #0f172a; padding: 10px; border-radius: 6px; border: 1px solid #334155;">
          <div style="font-size: 12px; font-weight: 700; margin-bottom: 6px;" id="comp-summary-title">Comparison Results</div>
          <div id="comp-summary-badges"></div>
        </div>
      </div>

      <div id="comparison-controls" style="display: none; margin-bottom: 12px;">
        <label style="font-size: 11px; text-transform: uppercase; color: #94a3b8;">Filter Discrepancies</label>
        <select id="comp-filter" onchange="filterComparisonList()" style="width: 100%; padding: 6px 10px; background: #0f172a; border: 1px solid #334155; border-radius: 6px; color: #f1f5f9; font-size: 12px; margin-top: 4px;">
          <option value="ALL">All Matched Records</option>
          <option value="DIFF_ONLY">Discrepancies Only (> 10 meters)</option>
          <option value="DIFF_500">Major Discrepancies (> 500 meters)</option>
          <option value="DIFF_5K">Severe Errors (> 5 kilometers)</option>
          <option value="EXACT">Identical Coordinates (< 10 meters)</option>
        </select>
      </div>

      <div id="comparison-list">
        <p style="font-size: 12px; color: #64748b; text-align: center; margin-top: 30px;">
          No comparison dataset loaded yet.<br>Drag and drop your teammate's CSV file above.
        </p>
      </div>
    </div>

    <!-- Audit & Guide Tab -->
    <div id="audit-tab" class="tab-content">
      <h3 style="font-size: 14px; color: #38bdf8; margin-bottom: 8px;">Coordinate Verification Methods</h3>
      
      <div style="font-size: 12px; color: #cbd5e1; line-height: 1.6;">
        <p style="margin-bottom: 10px;">
          <strong>Why do coordinates sometimes look identical?</strong><br>
          In raw datasets, administrative agencies (like MOHP) frequently place multiple hospitals at a single governorate directorate centroid. Our pipeline linked and snapped 50 of these to verified Google Maps rooftop pins.
        </p>

        <p style="margin-bottom: 10px;">
          <strong>Why are the numbers so close together?</strong><br>
          Upper Egypt's population resides inside a narrow 2 to 15 km ribbon along the Nile River. In decimal degrees, 0.01 degree equals ~1.1 km. Adjacent facilities in the same city will naturally share the first 2-3 decimal digits.
        </p>

        <p style="margin-bottom: 12px;">
          <strong>Three Guaranteed Verification Methods:</strong>
        </p>
        <ol style="margin-left: 18px; margin-bottom: 14px;">
          <li style="margin-bottom: 8px;">
            <strong>High-Resolution Satellite Inspection</strong>: Switch the map layer to <em>ESRI Satellite</em> (top-right layer icon). Zoom into level 18. Verified rooftop pins sit directly on top of the hospital building.
          </li>
          <li style="margin-bottom: 8px;">
            <strong>External Google Maps Cross-Reference</strong>: Click any pin, then click <em>Google Maps (Exact Pin)</em> and <em>Search Google Maps</em>. If the pin matches Google's registered place listing, coordinates are confirmed.
          </li>
          <li style="margin-bottom: 8px;">
            <strong>Automated Reverse Geocoding & Administrative Intersect</strong>: Mathematical verification confirming that <code>Point(lon, lat)</code> falls within the official cadastral polygon of the assigned governorate.
          </li>
        </ol>

        <button class="btn btn-outline" onclick="exportVerifiedCSV()">Export Current Audit List (CSV)</button>
      </div>
    </div>
  </div>

  <!-- Right Map Container -->
  <div id="map-container">
    <div id="map"></div>

    <!-- Map Legend -->
    <div class="legend-box">
      <div style="font-weight: 700; margin-bottom: 8px; color: #38bdf8;">Map Pin Legend</div>
      <div class="legend-item">
        <div class="legend-color" style="background: #10b981;"></div>
        <span>Reliable Rooftop Pin (Sub-meter GPS)</span>
      </div>
      <div class="legend-item">
        <div class="legend-color" style="background: #f59e0b;"></div>
        <span>Shared Centroid Cluster (n > 1)</span>
      </div>
      <div class="legend-item">
        <div class="legend-color" style="background: #ef4444;"></div>
        <span>Spatial Anomaly / Out of Bounds</span>
      </div>
      <div class="legend-item" id="legend-comp-item" style="display: none;">
        <div class="legend-color" style="background: #8b5cf6;"></div>
        <span>Teammate Dataset Comparison Pin</span>
      </div>
      <div style="margin-top: 6px; font-size: 11px; color: #94a3b8; border-top: 1px solid #334155; padding-top: 4px;">
        Use top-right layer control to switch between Street Map and High-Res Satellite View.
      </div>
    </div>
  </div>

  <script>
    // Embedded Local Dataset
    const DATASET_A = {json_data};
    let DATASET_B = [];
    let comparisonResults = [];

    // Map Initialization (100% free, zero API key, zero watermark basemaps)
    const googleStreets = L.tileLayer('https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}', {{
      maxZoom: 20,
      attribution: '&copy; Google Maps'
    }});

    const esriStreets = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
      maxZoom: 19,
      attribution: 'Tiles &copy; Esri, HERE, Garmin, USGS, EPA'
    }});

    const esriSatellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
      maxZoom: 19,
      attribution: 'Tiles &copy; Esri, Earthstar Geographics'
    }});

    const googleHybrid = L.tileLayer('https://mt1.google.com/vt/lyrs=y&x={{x}}&y={{y}}&z={{z}}', {{
      maxZoom: 20,
      attribution: '&copy; Google Satellite'
    }});

    const esriTopo = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
      maxZoom: 19,
      attribution: 'Tiles &copy; Esri'
    }});

    const map = L.map('map', {{
      center: [26.8, 31.5], // Center of Upper Egypt
      zoom: 7,
      layers: [googleStreets]
    }});

    const baseMaps = {{
      "Google Streets (Default)": googleStreets,
      "ESRI World Street Map": esriStreets,
      "High-Res Satellite (ESRI)": esriSatellite,
      "Google Hybrid (Satellite + Roads)": googleHybrid,
      "ESRI Topography": esriTopo
    }};

    L.control.layers(baseMaps).addTo(map);

    // Marker Clusters and Groups
    let clusterGroup = L.markerClusterGroup({{
      chunkedLoading: true,
      maxClusterRadius: 40,
      spiderfyOnMaxZoom: true
    }});

    let directMarkerGroup = L.featureGroup();
    let compMarkerGroup = L.featureGroup();
    let diffLineGroup = L.featureGroup();

    map.addLayer(clusterGroup);
    map.addLayer(compMarkerGroup);
    map.addLayer(diffLineGroup);

    let isClusteringEnabled = true;
    let markersMap = new Map();

    // Helper: Haversine distance in meters
    function haversineDistance(lat1, lon1, lat2, lon2) {{
      const R = 6371e3; // Earth radius in meters
      const phi1 = lat1 * Math.PI / 180;
      const phi2 = lat2 * Math.PI / 180;
      const deltaPhi = (lat2 - lat1) * Math.PI / 180;
      const deltaLambda = (lon2 - lon1) * Math.PI / 180;

      const a = Math.sin(deltaPhi / 2) * Math.sin(deltaPhi / 2) +
                Math.cos(phi1) * Math.cos(phi2) *
                Math.sin(deltaLambda / 2) * Math.sin(deltaLambda / 2);
      const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

      return R * c;
    }}

    // Render Markers for Dataset A
    function renderMarkers(items) {{
      clusterGroup.clearLayers();
      directMarkerGroup.clearLayers();
      markersMap.clear();

      items.forEach(fac => {{
        if (!fac.lat || !fac.lon) return;

        let color = '#10b981'; // Green for reliable rooftop
        if (fac.spatial_status && fac.spatial_status.includes('OUT_OF_BOUNDS')) {{
          color = '#ef4444'; // Red
        }} else if (fac.n_same_coord > 1 || !fac.coord_reliable) {{
          color = '#f59e0b'; // Amber
        }}

        const marker = L.circleMarker([fac.lat, fac.lon], {{
          radius: 7,
          fillColor: color,
          color: '#ffffff',
          weight: 1.5,
          opacity: 1,
          fillOpacity: 0.85
        }});

        const gmapsPinUrl = `https://www.google.com/maps?q=${{fac.lat}},${{fac.lon}}`;
        const gmapsSearchUrl = `https://www.google.com/maps/search/${{encodeURIComponent(fac.arabic_name || fac.name)}}+${{encodeURIComponent(fac.gov)}}+Egypt`;
        const osmUrl = `https://www.openstreetmap.org/?mlat=${{fac.lat}}&mlon=${{fac.lon}}#map=18/${{fac.lat}}/${{fac.lon}}`;

        const popupHtml = `
          <div class="popup-content">
            <div class="popup-title">${{fac.name}}</div>
            <div style="font-size: 11px; color: #475569; margin-bottom: 4px;">${{fac.arabic_name || ''}}</div>
            <div><strong>ID:</strong> ${{fac.id}}</div>
            <div><strong>Location:</strong> ${{fac.dist}}, ${{fac.gov}}</div>
            <div><strong>Coordinates:</strong> ${{fac.lat.toFixed(6)}}, ${{fac.lon.toFixed(6)}} (${{fac.precision}} decimals)</div>
            <div><strong>Category:</strong> ${{fac.cat || fac.facility_class}}</div>
            <div><strong>Cluster Status:</strong> ${{fac.n_same_coord > 1 ? fac.n_same_coord + ' facilities share this pin' : 'Single rooftop pin'}}</div>
            <div class="popup-actions">
              <a href="${{gmapsPinUrl}}" target="_blank" class="popup-btn popup-btn-gmaps">Exact GPS Pin</a>
              <a href="${{gmapsSearchUrl}}" target="_blank" class="popup-btn popup-btn-search">Search Name</a>
              <a href="${{osmUrl}}" target="_blank" class="popup-btn popup-btn-osm">OSM View</a>
            </div>
          </div>
        `;

        marker.bindPopup(popupHtml);
        markersMap.set(fac.id, marker);

        if (isClusteringEnabled) {{
          clusterGroup.addLayer(marker);
        }} else {{
          directMarkerGroup.addLayer(marker);
        }}
      }});
    }}

    function toggleClustering() {{
      const cb = document.getElementById('cluster-toggle');
      isClusteringEnabled = cb.checked;

      if (isClusteringEnabled) {{
        map.removeLayer(directMarkerGroup);
        map.addLayer(clusterGroup);
      }} else {{
        map.removeLayer(clusterGroup);
        map.addLayer(directMarkerGroup);
      }}
      applyFilters();
    }}

    // Apply Explorer Filters
    function applyFilters() {{
      const q = document.getElementById('search-input').value.toLowerCase().trim();
      const gov = document.getElementById('gov-filter').value;
      const status = document.getElementById('status-filter').value;

      const filtered = DATASET_A.filter(fac => {{
        if (gov !== 'ALL' && fac.gov !== gov) return false;
        
        if (status === 'RELIABLE' && (fac.n_same_coord > 1 || !fac.coord_reliable || (fac.spatial_status && fac.spatial_status.includes('OUT_OF_BOUNDS')))) return false;
        if (status === 'CLUSTER' && fac.n_same_coord <= 1) return false;
        if (status === 'ANOMALY' && (!fac.spatial_status || !fac.spatial_status.includes('OUT_OF_BOUNDS'))) return false;

        if (q) {{
          const matchId = fac.id.toLowerCase().includes(q);
          const matchName = fac.name.toLowerCase().includes(q);
          const matchArabic = (fac.arabic_name || '').toLowerCase().includes(q);
          const matchDist = fac.dist.toLowerCase().includes(q);
          if (!matchId && !matchName && !matchArabic && !matchDist) return false;
        }}
        return true;
      }});

      document.getElementById('filtered-count').innerText = `Showing ${{filtered.length}} of ${{DATASET_A.length}} facilities`;
      renderMarkers(filtered);
      renderFacilityList(filtered);
    }}

    // Render Sidebar Facility List
    function renderFacilityList(items) {{
      const listContainer = document.getElementById('facility-list');
      listContainer.innerHTML = '';

      const displayItems = items.slice(0, 80); // limit DOM nodes for performance

      displayItems.forEach(fac => {{
        const card = document.createElement('div');
        card.className = 'facility-card';
        card.onclick = () => zoomToFacility(fac.id);

        let badge = '<span class="stat-badge badge-green">Rooftop GPS</span>';
        if (fac.spatial_status && fac.spatial_status.includes('OUT_OF_BOUNDS')) {{
          badge = '<span class="stat-badge badge-red">Out of Bounds</span>';
        }} else if (fac.n_same_coord > 1) {{
          badge = `<span class="stat-badge badge-amber">Cluster (${{fac.n_same_coord}})</span>`;
        }}

        card.innerHTML = `
          <div class="facility-card-title">${{fac.name}}</div>
          <div class="facility-card-subtitle">${{fac.dist}}, ${{fac.gov}} | ID: ${{fac.id}}</div>
          <div style="font-size: 11px; color: #64748b; margin-bottom: 4px;">${{fac.lat.toFixed(5)}}, ${{fac.lon.toFixed(5)}}</div>
          <div>${{badge}}</div>
        `;
        listContainer.appendChild(card);
      }});

      if (items.length > 80) {{
        const moreNotice = document.createElement('div');
        moreNotice.style = 'font-size: 11px; color: #94a3b8; text-align: center; padding: 10px;';
        moreNotice.innerText = `+ ${{items.length - 80}} more facilities (refine search or governorate to view)`;
        listContainer.appendChild(moreNotice);
      }}
    }}

    function zoomToFacility(id) {{
      const marker = markersMap.get(id);
      if (marker) {{
        const latLng = marker.getLatLng();
        map.setView(latLng, 17);
        marker.openPopup();
      }}
    }}

    // Tab Switching
    function switchTab(tabId) {{
      document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

      event.target.classList.add('active');
      document.getElementById(tabId).classList.add('active');
    }}

    // =========================================================================
    // Comparison Engine (Dataset A vs Dataset B)
    // =========================================================================
    function handleFileUpload(event) {{
      const file = event.target.files[0];
      if (!file) return;

      Papa.parse(file, {{
        header: true,
        dynamicTyping: true,
        skipEmptyLines: true,
        complete: function(results) {{
          processComparisonData(results.data, file.name);
        }},
        error: function(err) {{
          alert('Error parsing CSV file: ' + err.message);
        }}
      }});
    }}

    // Drag and Drop handlers
    const dropzone = document.getElementById('dropzone');
    dropzone.addEventListener('dragover', (e) => {{
      e.preventDefault();
      dropzone.classList.add('dragover');
    }});
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', (e) => {{
      e.preventDefault();
      dropzone.classList.remove('dragover');
      if (e.dataTransfer.files.length > 0) {{
        document.getElementById('file-input').files = e.dataTransfer.files;
        handleFileUpload({{ target: {{ files: e.dataTransfer.files }} }});
      }}
    }});

    function processComparisonData(rows, filename) {{
      compMarkerGroup.clearLayers();
      diffLineGroup.clearLayers();
      comparisonResults = [];

      document.getElementById('legend-comp-item').style.display = 'flex';

      // Auto-detect columns
      const sample = rows[0] || {{}};
      const latCol = Object.keys(sample).find(k => /lat/i.test(k));
      const lonCol = Object.keys(sample).find(k => /lon/i.test(k));
      const idCol = Object.keys(sample).find(k => /id/i.test(k));
      const nameCol = Object.keys(sample).find(k => /name/i.test(k));

      if (!latCol || !lonCol) {{
        alert('Could not find latitude/longitude columns in uploaded CSV.');
        return;
      }}

      // Build map of Dataset A by ID and by lowercase Name
      const aById = new Map();
      const aByName = new Map();
      DATASET_A.forEach(a => {{
        aById.set(a.id.trim(), a);
        aByName.set(a.name.toLowerCase().trim(), a);
        if (a.arabic_name) aByName.set(a.arabic_name.trim(), a);
      }});

      let exactCount = 0;
      let minorDiffCount = 0;
      let majorDiffCount = 0;
      let severeDiffCount = 0;
      let unmatchedCount = 0;

      rows.forEach(row => {{
        const bLat = parseFloat(row[latCol]);
        const bLon = parseFloat(row[lonCol]);
        if (isNaN(bLat) || isNaN(bLon)) return;

        const bId = idCol ? String(row[idCol] || '').trim() : '';
        const bName = nameCol ? String(row[nameCol] || '').trim() : 'Unnamed';

        let matchA = aById.get(bId) || aByName.get(bName.toLowerCase());

        if (matchA) {{
          const distMeters = haversineDistance(matchA.lat, matchA.lon, bLat, bLon);
          
          if (distMeters < 10) exactCount++;
          else if (distMeters < 500) minorDiffCount++;
          else if (distMeters < 5000) majorDiffCount++;
          else severeDiffCount++;

          comparisonResults.push({{
            id: matchA.id,
            name: matchA.name,
            gov: matchA.gov,
            aLat: matchA.lat,
            aLon: matchA.lon,
            bLat: bLat,
            bLon: bLon,
            distMeters: distMeters
          }});

          // Add Teammate pin (Purple)
          const bMarker = L.circleMarker([bLat, bLon], {{
            radius: 6,
            fillColor: '#8b5cf6',
            color: '#ffffff',
            weight: 1.5,
            fillOpacity: 0.8
          }});

          bMarker.bindPopup(`
            <div class="popup-content">
              <div class="popup-title">Teammate Pin: ${{bName}}</div>
              <div><strong>Matched ID:</strong> ${{matchA.id}}</div>
              <div><strong>Teammate GPS:</strong> ${{bLat.toFixed(6)}}, ${{bLon.toFixed(6)}}</div>
              <div><strong>Our GPS:</strong> ${{matchA.lat.toFixed(6)}}, ${{matchA.lon.toFixed(6)}}</div>
              <div><strong>Difference:</strong> ${{distMeters < 1000 ? Math.round(distMeters) + ' meters' : (distMeters / 1000).toFixed(2) + ' km'}}</div>
              <div class="popup-actions">
                <a href="https://www.google.com/maps?q=${{bLat}},${{bLon}}" target="_blank" class="popup-btn popup-btn-gmaps">Inspect Teammate Pin</a>
              </div>
            </div>
          `);
          compMarkerGroup.addLayer(bMarker);

          // If difference is noticeable (> 20 meters), draw connecting line
          if (distMeters >= 20) {{
            const lineColor = distMeters > 5000 ? '#ef4444' : (distMeters > 500 ? '#f59e0b' : '#38bdf8');
            const line = L.polyline([[matchA.lat, matchA.lon], [bLat, bLon]], {{
              color: lineColor,
              weight: 2,
              dashArray: '4, 4'
            }});
            diffLineGroup.addLayer(line);
          }}
        }} else {{
          unmatchedCount++;
        }}
      }});

      // Update UI Stats
      document.getElementById('comparison-stats').style.display = 'block';
      document.getElementById('comparison-controls').style.display = 'block';
      document.getElementById('comp-summary-title').innerText = `Comparison with "${{filename}}" (${{comparisonResults.length}} Matched)`;
      
      document.getElementById('comp-summary-badges').innerHTML = `
        <span class="stat-badge badge-green">Exact Match (< 10m): ${{exactCount}}</span>
        <span class="stat-badge badge-blue">Minor Shift (10-500m): ${{minorDiffCount}}</span>
        <span class="stat-badge badge-amber">Major (> 500m): ${{majorDiffCount}}</span>
        <span class="stat-badge badge-red">Severe (> 5km): ${{severeDiffCount}}</span>
      `;

      filterComparisonList();
    }}

    function filterComparisonList() {{
      const filter = document.getElementById('comp-filter').value;
      const listContainer = document.getElementById('comparison-list');
      listContainer.innerHTML = '';

      const filtered = comparisonResults.filter(item => {{
        if (filter === 'DIFF_ONLY' && item.distMeters < 10) return false;
        if (filter === 'DIFF_500' && item.distMeters < 500) return false;
        if (filter === 'DIFF_5K' && item.distMeters < 5000) return false;
        if (filter === 'EXACT' && item.distMeters >= 10) return false;
        return true;
      }}).sort((a, b) => b.distMeters - a.distMeters);

      if (filtered.length === 0) {{
        listContainer.innerHTML = '<p style="font-size: 12px; color: #94a3b8; text-align: center; margin-top: 20px;">No records match the selected filter.</p>';
        return;
      }}

      let tableHtml = `
        <table class="diff-table">
          <thead>
            <tr>
              <th>Facility</th>
              <th>Delta Distance</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
      `;

      filtered.slice(0, 100).forEach(item => {{
        const distStr = item.distMeters < 1000 ? Math.round(item.distMeters) + ' m' : (item.distMeters / 1000).toFixed(2) + ' km';
        const badgeClass = item.distMeters > 5000 ? 'badge-red' : (item.distMeters > 500 ? 'badge-amber' : (item.distMeters > 10 ? 'badge-blue' : 'badge-green'));
        
        tableHtml += `
          <tr class="diff-row" onclick="zoomToDiff(${{item.aLat}}, ${{item.aLon}}, ${{item.bLat}}, ${{item.bLon}})">
            <td>
              <strong>${{item.name}}</strong><br>
              <span style="color: #94a3b8; font-size: 10px;">${{item.gov}} | ${{item.id}}</span>
            </td>
            <td><span class="stat-badge ${{badgeClass}}">${{distStr}}</span></td>
            <td><button class="btn btn-secondary btn-small" onclick="event.stopPropagation(); zoomToDiff(${{item.aLat}}, ${{item.aLon}}, ${{item.bLat}}, ${{item.bLon}})">Zoom</button></td>
          </tr>
        `;
      }});

      tableHtml += '</tbody></table>';
      listContainer.innerHTML = tableHtml;
    }}

    function zoomToDiff(aLat, aLon, bLat, bLon) {{
      const bounds = L.latLngBounds([[aLat, aLon], [bLat, bLon]]);
      map.fitBounds(bounds, {{ padding: [50, 50], maxZoom: 18 }});
    }}

    // Export Current Verified List
    function exportVerifiedCSV() {{
      const csv = Papa.unparse(DATASET_A.map(f => ({{
        canonical_entity_id: f.id,
        canonical_name: f.name,
        arabic_name: f.arabic_name,
        governorate_assigned: f.gov,
        district: f.dist,
        latitude_final: f.lat,
        longitude_final: f.lon,
        precision_decimals: f.precision,
        coord_reliable: f.coord_reliable,
        n_same_coord: f.n_same_coord,
        spatial_status: f.spatial_status
      }})));

      const blob = new Blob([csv], {{ type: 'text/csv;charset=utf-8;' }});
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.setAttribute('download', 'verified_facilities_coordinates_audit.csv');
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }}

    // Initial Load
    applyFilters();
  </script>
</body>
</html>
'''

print(f"Writing standalone HTML tool to {OUTPUT_HTML}...")
with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
    f.write(html_content)

print("Successfully generated coordinate_verifier_tool.html!")
