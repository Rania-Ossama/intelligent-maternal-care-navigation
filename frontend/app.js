/* Hospital Finder front end. No build step, no framework. */
(function () {
  "use strict";

  const COLORS = ["#2563eb", "#16a34a", "#9333ea", "#ea580c", "#0891b2", "#db2777", "#65a30d", "#7c3aed", "#b45309", "#475569"];
  const $ = (id) => document.getElementById(id);

  // ------------------------------------------------------------------ state
  let cfg = null;
  let map = null;
  let pin = null;                 // Leaflet marker
  let lastValid = null;           // [lat, lon] of the last accepted pin position
  let ready = false;
  let builtAt = null;
  let searching = false;
  let searchToken = 0;
  let statusTimer = null;
  let resultLayer = null;
  let facilityLayer = null;
  let coverageLayer = null;
  let govBoundaryLayer = null;    // governorate outlines (see initBoundaries)
  let routeLayers = [];           // per hospital: {route, connectors, marker}
  let facilitiesLoadedFor = null;
  let current = null;             // the search on screen: {data, moreUsed, loadingMore}

  // ---------------------------------------------------------------- helpers
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) {
      if (c === null || c === undefined || c === false) continue;
      node.append(c.nodeType ? c : document.createTextNode(String(c)));
    }
    return node;
  }

  async function api(path, options) {
    const res = await fetch(path, options);
    let body = null;
    try { body = await res.json(); } catch (_) { /* not JSON */ }
    if (!res.ok) {
      const err = (body && body.error) || { message: `Server error (${res.status})` };
      err.status = res.status;
      throw err;
    }
    return body;
  }

  function toast(message, ms = 4200) {
    const t = $("toast");
    t.textContent = message;
    t.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { t.hidden = true; }, ms);
  }

  const fmtInt = (n) => Number(n).toLocaleString("en-US");
  function fmtMs(ms) {
    if (ms === null || ms === undefined) return "–";
    if (ms >= 1000) return (ms / 1000).toFixed(2) + " s";
    if (ms >= 10) return ms.toFixed(0) + " ms";
    return ms.toFixed(2) + " ms";
  }

  // Accept Arabic-Indic / Persian digits, decimal comma, unicode minus, stray spaces.
  function parseCoordinate(text) {
    if (text === null || text === undefined) return NaN;
    let s = String(text).trim();
    if (!s) return NaN;
    s = s.replace(/[\u0660-\u0669]/g, (d) => String(d.charCodeAt(0) - 0x0660))
         .replace(/[\u06F0-\u06F9]/g, (d) => String(d.charCodeAt(0) - 0x06F0))
         .replace(/[\u066B\u066C\u060C,]/g, ".")
         .replace(/[\u2212\u2013]/g, "-")
         .replace(/[°\s]/g, "");
    if (!/^[+-]?(\d+\.?\d*|\.\d+)$/.test(s)) return NaN;
    return Number(s);
  }

  function inEgypt(lat, lon) {
    if (!isFinite(lat) || !isFinite(lon)) return false;
    const poly = cfg.egypt_polygon;       // [[lon, lat], ...]
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const [xi, yi] = poly[i];
      const [xj, yj] = poly[j];
      if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }

  // -------------------------------------------------------------------- map
  function initMap() {
    const bounds = L.latLngBounds(cfg.egypt_bounds);
    map = L.map("map", {
      center: cfg.map.center, zoom: cfg.map.zoom, minZoom: 5, maxZoom: 18,
      maxBounds: bounds.pad(0.15), maxBoundsViscosity: 1.0, zoomControl: true,
    });
    const tt = cfg.tomtom || {};
    const tiles = tt.tiles && tt.map_key
      ? L.tileLayer(`https://api.tomtom.com/map/1/tile/basic/main/{z}/{x}/{y}.png?key=${encodeURIComponent(tt.map_key)}`,
          { maxZoom: 18, attribution: "&copy; TomTom" })
      : L.tileLayer(cfg.map.tile_url, { maxZoom: 19, attribution: cfg.map.tile_attribution });
    let tileErrors = 0;
    tiles.on("tileerror", () => {
      if (++tileErrors === 5) toast("Map tiles can't be loaded (no internet?). Markers and routes still work.", 7000);
    });
    tiles.addTo(map);

    // optional TomTom live-traffic overlay (checkbox in the side panel)
    const trafficBox = $("showTraffic");
    if (trafficBox) {
      if (tt.traffic_overlay && tt.map_key) {
        const trafficLayer = L.tileLayer(
          `https://api.tomtom.com/traffic/map/4/tile/flow/relative0/{z}/{x}/{y}.png?key=${encodeURIComponent(tt.map_key)}`,
          { maxZoom: 18, opacity: 0.75, attribution: "&copy; TomTom Traffic" });
        trafficBox.addEventListener("change", () => {
          if (trafficBox.checked) trafficLayer.addTo(map); else map.removeLayer(trafficLayer);
        });
      } else {
        trafficBox.closest("label").hidden = true;
      }
    }

    // grey mask everywhere except Egypt, so it is obvious where a pin may go
    const world = [[5, 5], [5, 60], [50, 60], [50, 5]];   // generous box around Egypt (map is locked to Egypt anyway)
    const hole = cfg.egypt_polygon.map(([lon, lat]) => [lat, lon]);
    L.polygon([world, hole], {
      color: "#0b3d91", weight: 1.5, fillColor: "#0f172a", fillOpacity: 0.32,
      fillRule: "evenodd", interactive: false,
    }).addTo(map);

    resultLayer = L.layerGroup().addTo(map);
    facilityLayer = L.layerGroup();
    if ($("showFacilities").checked) facilityLayer.addTo(map);   // "Show all hospitals considered" is ON by default
    coverageLayer = L.layerGroup().addTo(map);
    map.on("click", (e) => placeFromMap(e.latlng.lat, e.latlng.lng));
  }

  // ------------------------------------------- governorate borders + "Full Egypt"
  // Borders are drawn (dashed blue, no fill, no label) only for governorates ticked in the filter.
  // Full Egypt OFF (default): the filter lists only the governorates covered today (config.yaml ->
  // governorates.upper_egypt). ON: it lists every governorate in the boundaries file.
  let govFeatures = [];           // [{name, upper, bounds, polys}]
  let govBorders = new Map();     // name -> Leaflet layer with that governorate's outline
  let borderLayer = null;
  let fullEgypt = false;
  let upperBounds = null, allBounds = null;

  function ringContains(ring, lat, lon) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }
  function featureContains(ft, lat, lon) {
    return ft.polys.some((rings) => ringContains(rings[0], lat, lon) && !rings.slice(1).some((h) => ringContains(h, lat, lon)));
  }
  function governorateAt(lat, lon) {
    const ft = govFeatures.find((f) => f.bounds.contains([lat, lon]) && featureContains(f, lat, lon));
    return ft ? ft.name : null;
  }

  // governorates that may appear in the filter right now
  function visibleBoundaryNames() {
    return govFeatures.filter((f) => fullEgypt || f.upper).map((f) => f.name);
  }

  async function initBoundaries() {
    const box = $("fullEgypt"), note = $("fullEgyptNote");
    let data;
    try {
      data = await api("/api/boundaries");
    } catch (err) {
      note.textContent = "(unavailable)";
      return;
    }
    if (!data.available) {
      note.textContent = "(boundaries file missing)";
      box.title = data.message || "";
      if (data.message) toast(data.message, 9000);
      return;
    }
    const feats = data.geojson.features;
    const anyUpper = feats.some((f) => f.properties.upper);
    if (data.upper_missing && data.upper_missing.length)
      console.warn("Governorates from config not found in the boundaries file:", data.upper_missing);

    borderLayer = L.layerGroup().addTo(map);
    govFeatures = feats.map((f) => {
      const lyr = L.geoJSON(f, {
        interactive: false,
        style: () => ({ color: "#2563eb", weight: 2, dashArray: "7 6", fill: false, opacity: 0.95 }),
      });
      govBorders.set(f.properties.name, lyr);
      return { name: f.properties.name, upper: anyUpper ? !!f.properties.upper : true, bounds: lyr.getBounds(), polys: f.geometry.coordinates };
    });
    const up = govFeatures.filter((f) => f.upper), all = govFeatures;
    upperBounds = up.length ? L.latLngBounds(up.map((f) => f.bounds.getSouthWest()).concat(up.map((f) => f.bounds.getNorthEast()))) : null;
    allBounds = L.latLngBounds(all.map((f) => f.bounds.getSouthWest()).concat(all.map((f) => f.bounds.getNorthEast())));

    box.disabled = up.length === all.length;
    if (box.disabled) note.textContent = "(all governorates already shown)";
    box.addEventListener("change", () => {
      fullEgypt = box.checked;
      syncGovernorates();
      const b = fullEgypt ? allBounds : upperBounds;
      if (b && b.isValid()) map.fitBounds(b.pad(0.05));
    });
    syncGovernorates();
  }

  function pinIcon() { return new L.Icon.Default(); }

  function setPin(lat, lon, pan) {
    lastValid = [lat, lon];
    if (!pin) {
      pin = L.marker([lat, lon], { draggable: true, icon: pinIcon(), title: "Patient location", zIndexOffset: 1000 }).addTo(map);
      pin.on("drag", (e) => {
        const p = e.target.getLatLng();
        if (inEgypt(p.lat, p.lng)) writeInputs(p.lat, p.lng);
      });
      pin.on("dragend", (e) => {
        const p = e.target.getLatLng();
        if (inEgypt(p.lat, p.lng)) {
          lastValid = [p.lat, p.lng];
          writeInputs(p.lat, p.lng);
        } else {
          e.target.setLatLng(lastValid);
          writeInputs(lastValid[0], lastValid[1]);
          toast("The pin must stay inside Egypt – it was moved back.");
        }
      });
    } else {
      pin.setLatLng([lat, lon]);
    }
    writeInputs(lat, lon);
    clearFieldError();
    if (pan) map.panTo([lat, lon], { animate: true });
    updateFindButton();
  }

  function placeFromMap(lat, lon) {
    if (!inEgypt(lat, lon)) {
      toast("That point is outside Egypt. Click inside the un-shaded area.");
      return;
    }
    setPin(lat, lon, false);
  }

  function writeInputs(lat, lon) {
    $("lat").value = lat.toFixed(5);
    $("lon").value = lon.toFixed(5);
    $("lat").classList.remove("invalid");
    $("lon").classList.remove("invalid");
  }

  // ----------------------------------------------------------------- inputs
  function showFieldError(msg, ...fields) {
    const e = $("fieldError");
    e.textContent = msg;
    e.hidden = false;
    for (const f of ["lat", "lon"]) $(f).classList.toggle("invalid", fields.includes(f));
  }
  function clearFieldError() {
    $("fieldError").hidden = true;
    $("lat").classList.remove("invalid");
    $("lon").classList.remove("invalid");
  }

  /** Validate the two text boxes. On success moves the pin and returns [lat, lon]. */
  function commitInputs(pan = true) {
    const latText = $("lat").value, lonText = $("lon").value;
    if (!latText.trim() && !lonText.trim()) { clearFieldError(); return null; }
    const lat = parseCoordinate(latText), lon = parseCoordinate(lonText);
    const bad = [];
    if (!isFinite(lat)) bad.push("lat");
    if (!isFinite(lon)) bad.push("lon");
    if (bad.length) {
      showFieldError(bad.length === 2 ? "Enter numeric latitude and longitude, e.g. 27.18090 and 31.18370."
        : bad[0] === "lat" ? "Latitude must be a number, e.g. 27.18090." : "Longitude must be a number, e.g. 31.18370.", ...bad);
      return null;
    }
    if (Math.abs(lat) > 90 || Math.abs(lon) > 180) {
      showFieldError("Latitude must be between -90 and 90 and longitude between -180 and 180. (Latitude goes first.)", "lat", "lon");
      return null;
    }
    if (!inEgypt(lat, lon)) {
      const swapped = inEgypt(lon, lat);
      showFieldError(swapped ? "That point is outside Egypt – did you swap latitude and longitude?"
                             : "That point is outside Egypt. The pin must be inside Egypt.", "lat", "lon");
      return null;
    }
    setPin(lat, lon, pan);
    return [lat, lon];
  }

  function updateFindButton() {
    $("findBtn").disabled = !(ready && pin && !searching);
  }

  // ---------------------------------------------------------------- results
  function clearResults() {
    resultLayer.clearLayers();
    routeLayers = [];
    $("alerts").replaceChildren();
    $("results").replaceChildren();
    $("moreWrap").replaceChildren();
    $("timing").replaceChildren();
    current = null;
  }

  function showSkeleton() {
    const n = (cfg && cfg.search && cfg.search.results) || 5;
    $("results").replaceChildren(...Array.from({ length: n }, () => el("div", { class: "skeleton" })));
  }

  function showError(err) {
    $("results").replaceChildren();
    if (err.code === "outside_coverage" && lastValid) {
      const g = governorateAt(lastValid[0], lastValid[1]);
      if (g) err = { ...err, message: `No coverage in ${g} yet. ${err.message.replace(/^No coverage here yet:\s*/, "")}` };
    }
    const level = err.code === "outside_egypt" || err.code === "outside_coverage" ? "warning" : "danger";
    $("alerts").replaceChildren(el("div", { class: "alert " + level, role: "alert" }, err.message || "Something went wrong."));
  }

  function phoneLinks(phones, fallbackText) {
    if (!phones || !phones.length) return fallbackText ? document.createTextNode(fallbackText) : el("span", { text: "not available" });
    const out = [];
    phones.forEach((p, i) => {
      const digits = p.replace(/[^\d+]/g, "");
      if (i) out.push(", ");
      out.push(el("a", { href: "tel:" + digits, text: p, onclick: (e) => e.stopPropagation() }));
    });
    return out;
  }

  function hospitalCard(h, i, threshold) {
    const color = COLORS[i % COLORS.length];
    const f = h.facility;
    const card = el("article", { class: "hospital" + (h.flagged ? " flagged" : ""), style: `--c:${color}`, "data-i": i });

    const cb = el("input", { type: "checkbox", checked: true, "aria-label": "Show route " + (i + 1) });
    cb.addEventListener("click", (e) => e.stopPropagation());
    cb.addEventListener("change", () => toggleRoute(i, cb.checked));

    card.append(el("div", { class: "h-head" },
      el("div", { class: "rank", text: String(h.rank) }),
      el("div", { class: "h-title" },
        el("div", { class: "h-name", dir: "auto", text: f.name }),
        (f.alt_names || []).map((a) => el("div", { class: "h-alt", dir: "auto", text: a })),
        el("div", { class: "h-meta", text: [f.tier_label, f.governorate, f.district && f.district !== f.governorate ? f.district : null].filter(Boolean).join(" · ") })),
      h.flagged ? el("span", { class: "badge danger", text: "> " + threshold + " min" }) : null,
      el("label", { class: "vis", title: "Show / hide route" }, cb)));

    card.append(el("div", { class: "stats" },
      el("div", { class: "stat" }, el("div", { class: "k", text: "Road distance" }),
        el("div", { class: "v" }, h.distance_km.toFixed(1), " ", el("small", { text: "km" }))),
      el("div", { class: "stat" + (h.flagged ? " flag" : "") }, el("div", { class: "k", text: "Estimated time" }),
        el("div", { class: "v" }, h.eta_text))));

    if (h.flagged) {
      card.append(el("div", { class: "flagline", text: "⚠ More than " + threshold + " minutes away (estimated)" }));
    }
    card.append(el("div", { class: "detail" }, el("span", { class: "lbl", text: "Straight line: " }),
      `${h.straight_km.toFixed(1)} km` + (h.detour_ratio ? ` (road is ${h.detour_ratio}× longer)` : "")));
    if (h.detour) {
      card.append(el("div", { class: "detour", text: "↻ Long detour: a river or a missing road link may be forcing a roundabout route." }));
    }
    if (cfg.tomtom && cfg.tomtom.live_eta) {
      card.append(el("div", { class: "live", id: "live-" + i, text: "Live traffic: checking…" }));
    }
    if (f.address) card.append(el("div", { class: "detail" }, el("span", { class: "lbl", text: "Address: " }), f.address));
    card.append(el("div", { class: "detail" }, el("span", { class: "lbl", text: "Phone: " }), phoneLinks(f.phones, f.phone)));
    if (f.snap_m > 250) {
      card.append(el("div", { class: "detail" }, el("span", { class: "lbl", text: "Note: " }),
        `the mapped location is about ${fmtInt(Math.round(f.snap_m))} m from the nearest road.`));
    }
    if (h.also_here && h.also_here.length) {
      card.append(el("div", { class: "also" },
        el("div", { text: "Also registered at this location:" }),
        h.also_here.map((o) => el("div", {}, "• ", o.name, o.phones && o.phones.length ? " – " + o.phones.join(", ") : ""))));
    }
    card.addEventListener("click", () => focusHospital(i));
    return card;
  }

  function addHospitalLayer(h, i, snapLL, all) {
    const color = COLORS[i % COLORS.length];
    const route = L.layerGroup().addTo(resultLayer);
    const line = L.polyline(h.route, { color, weight: Math.max(2, 6 - i), opacity: 0.85, lineJoin: "round" }).addTo(route);
    const hospLL = [h.facility.lat, h.facility.lon];
    const end = h.route.length ? h.route[h.route.length - 1] : snapLL;
    L.polyline([end, hospLL], { color, weight: 2, dashArray: "3 6", opacity: 0.9, interactive: false }).addTo(route);
    const icon = L.divIcon({
      className: "", iconSize: [30, 30], iconAnchor: [15, 15],
      html: `<div class="num-marker${h.flagged ? " flagged" : ""}" style="--c:${color}">${h.rank}</div>`,
    });
    const popup = el("div", {}, el("strong", { dir: "auto", text: h.facility.name }), el("br"),
      `${h.distance_km.toFixed(1)} km · ${h.eta_text}${h.flagged ? " ⚠" : ""}`);
    const marker = L.marker(hospLL, { icon, title: h.facility.name, zIndexOffset: 500 - i }).bindPopup(popup).addTo(route);
    marker.on("click", () => focusHospital(i, true));
    routeLayers[i] = { group: route, line, marker, visible: true };
    line.getLatLngs().forEach((p) => all.push(p));
    all.push(L.latLng(hospLL));
  }

  function addMapLayers(data, startIndex) {
    const pinLL = [data.pin.lat, data.pin.lon];
    const snapLL = [data.snap.lat, data.snap.lon];
    const all = [L.latLng(pinLL)];
    if (!startIndex && data.snap.distance_m > 30) {
      L.polyline([pinLL, snapLL], { color: "#64748b", weight: 2, dashArray: "4 6", interactive: false }).addTo(resultLayer);
    }
    data.hospitals.forEach((h, k) => addHospitalLayer(h, (startIndex || 0) + k, snapLL, all));
    // when adding more, keep everything already shown inside the view as well
    routeLayers.forEach((r) => { if (r && r.visible) all.push(...r.line.getLatLngs(), r.marker.getLatLng()); });
    if (all.length > 1) map.fitBounds(L.latLngBounds(all).pad(0.18), { maxZoom: 15 });
  }

  function toggleRoute(i, on) {
    const r = routeLayers[i];
    if (!r) return;
    r.visible = on;
    if (on) resultLayer.addLayer(r.group); else resultLayer.removeLayer(r.group);
  }

  function focusHospital(i, fromMap) {
    document.querySelectorAll(".hospital").forEach((c) => c.classList.toggle("selected", Number(c.dataset.i) === i));
    const r = routeLayers[i];
    if (!r) return;
    if (!r.visible) {
      const cb = document.querySelector(`.hospital[data-i="${i}"] input[type=checkbox]`);
      if (cb) cb.checked = true;
      toggleRoute(i, true);
    }
    map.fitBounds(r.line.getBounds().extend(r.marker.getLatLng()).pad(0.2), { maxZoom: 16 });
    if (!fromMap) r.marker.openPopup();
    r.line.bringToFront();
  }

  // ------------------------------------------------- TomTom live-traffic ETA
  function minText(sec) {
    const m = Math.max(1, Math.round(sec / 60));
    return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
  }

  async function addLiveTraffic(pin, hospitals, startIndex) {
    if (!(cfg.tomtom && cfg.tomtom.live_eta)) return;
    const token = searchToken;
    await Promise.all(hospitals.map(async (h, k) => {
      const i = startIndex + k;
      const box = document.getElementById("live-" + i);
      if (!box) return;
      try {
        const q = new URLSearchParams({ from_lat: pin.lat, from_lon: pin.lon,
                                        to_lat: h.facility.lat, to_lon: h.facility.lon });
        const t = await api("/api/tomtom/route?" + q);
        if (token !== searchToken || !document.body.contains(box)) return;     // a newer search replaced this one
        const delay = Math.round(t.traffic_delay_seconds / 60);
        box.textContent = `Live traffic (TomTom): ${minText(t.eta_seconds)} · ${t.distance_km.toFixed(1)} km` +
                          (delay >= 1 ? ` · +${delay} min traffic delay` : "");
        box.classList.toggle("slow", t.eta_seconds > ((cfg.search && cfg.search.eta_warn_minutes) || 60) * 60);
        h.tomtom = t;
        const r = routeLayers[i];
        if (r && t.route && t.route.length) {                                    // dashed second line = TomTom route
          L.polyline(t.route, { color: "#111827", weight: 3, opacity: 0.8, dashArray: "2 7", interactive: false }).addTo(r.group);
        }
      } catch (err) {
        box.textContent = "Live traffic: not available";
        box.classList.add("off");
      }
    }));
  }

  function renderResults(data) {
    $("alerts").replaceChildren(...data.warnings.map((w) => el("div", { class: "alert " + w.level, role: "alert" }, w.message)));
    const box = $("results");
    box.replaceChildren();
    if (!data.hospitals.length) {
      box.append(el("div", { class: "alert danger" }, "No hospital could be reached from this location."));
    }
    data.hospitals.forEach((h, i) => box.append(hospitalCard(h, i, data.threshold_min)));
    addMapLayers(data, 0);
    renderTiming(data, data.baseline);
    current = { data, moreUsed: false, loadingMore: false };
    renderMoreButton();
    addLiveTraffic(data.pin, data.hospitals, 0);
  }

  // "Show more hospitals": allowed ONCE per search. It adds the next `more_results` hospitals.
  function renderMoreButton() {
    const wrap = $("moreWrap");
    wrap.replaceChildren();
    if (!current || current.moreUsed) return;
    const want = (cfg.search && cfg.search.results) || 5;
    if (current.data.hospitals.length < want) return;          // fewer reachable than asked: nothing more to show
    const extra = (cfg.search && cfg.search.more_results) || 5;
    wrap.append(el("button", {
      id: "moreBtn", class: "secondary more", type: "button", disabled: current.loadingMore,
      text: current.loadingMore ? "Loading…" : `Show ${extra} more hospitals`,
      onclick: showMore,
    }));
  }

  async function showMore() {
    if (!current || current.moreUsed || current.loadingMore) return;
    const cur = current, token = searchToken;
    cur.loadingMore = true;
    renderMoreButton();
    try {
      const d = await api("/api/search", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lat: cur.data.pin.lat, lon: cur.data.pin.lon, more: true }),
      });
      if (token !== searchToken || current !== cur) return;    // a newer search replaced this one
      cur.moreUsed = true;                                      // cannot be pressed again
      const start = cur.data.hospitals.length;
      if (!d.hospitals.length) {
        toast("No more hospitals could be reached from this location.");
      } else {
        d.hospitals.forEach((h, k) => $("results").append(hospitalCard(h, start + k, d.threshold_min)));
        addMapLayers(d, start);
        addLiveTraffic(cur.data.pin, d.hospitals, start);
        cur.data.hospitals.push(...d.hospitals);
      }
    } catch (err) {
      if (token !== searchToken || current !== cur) return;
      toast(err.message || "Could not load more hospitals.");
    } finally {
      cur.loadingMore = false;
      if (current === cur) renderMoreButton();
    }
  }

  function renderTiming(data, base) {
    const e = data.enhanced;
    const done = base && base.status === "done";
    let baseMs, baseNodes;
    if (done) {
      baseMs = el("span", { class: "big", text: fmtMs(base.compute_ms) });
      baseNodes = fmtInt(base.settled_nodes);
    } else if (base && (base.status === "error")) {
      baseMs = el("span", { text: "failed" });
      baseNodes = "–";
    } else if (base && base.status === "cancelled") {
      baseMs = el("span", { text: "cancelled" });
      baseNodes = "–";
    } else {
      baseMs = el("span", { class: "running" }, el("i", { class: "dot-spin" }), "running…");
      baseNodes = el("span", { class: "running" }, el("i", { class: "dot-spin" }), "…");
    }
    const table = el("table", {},
      el("thead", {}, el("tr", {}, el("th", { text: "" }), el("th", { text: "Enhanced" }), el("th", { text: "Standard" }))),
      el("tbody", {},
        el("tr", {}, el("td", { text: "Compute time" }), el("td", {}, el("span", { class: "big", text: fmtMs(e.compute_ms) })), el("td", {}, baseMs)),
        el("tr", {}, el("td", { text: "Nodes settled" }), el("td", { text: fmtInt(e.settled_nodes) }), el("td", {}, baseNodes))));

    const card = el("section", { class: "card timing" }, el("h2", { text: "Algorithm timing" }), table);
    if (done) {
      if (!base.match) {
        card.append(el("div", { class: "speedup bad", text: base.note }));
      } else {
        card.append(el("div", { class: "speedup" },
          base.speedup ? `Enhanced Dijkstra was ${fmtInt(Math.round(base.speedup))}× faster` : "Enhanced Dijkstra was faster",
          base.settled_nodes && e.settled_nodes ? ` and settled ${(base.settled_nodes / e.settled_nodes).toFixed(0)}× fewer nodes.` : "."));
        card.append(el("p", { class: "mini", text: base.note }));
      }
    }
    card.append(el("p", { class: "mini" },
      `Enhanced = Dijkstra that stops once the ${(cfg.search && cfg.search.results) || 5} nearest hospitals are found. Standard = Dijkstra over the whole graph. ` +
      "Timing is for the first set of hospitals (not the extra ones from \"Show more\"). " +
      "Timing covers the search only; locating your pin on the road network took " + fmtMs(data.snap.time_ms) + ". " +
      `Graph: ${fmtInt(data.graph.nodes)} nodes, ${fmtInt(data.graph.edges)} road segments; ` +
      `${fmtInt(data.graph.locations)} hospital locations.`));
    $("timing").replaceChildren(card);
  }

  async function pollBaseline(data, token) {
    const started = Date.now();
    while (token === searchToken && Date.now() - started < 10 * 60 * 1000) {
      await new Promise((r) => setTimeout(r, 600));
      if (token !== searchToken) return;
      let base;
      try { base = await api("/api/baseline/" + data.job_id); } catch (err) {
        if (err.status === 404) return;
        continue;
      }
      if (token !== searchToken) return;
      if (base.status === "done" || base.status === "error" || base.status === "cancelled") {
        renderTiming(data, base);
        return;
      }
    }
  }

  async function runSearch() {
    if (!ready || searching) return;
    const pos = commitInputs(false);
    if (!pos) {
      if (!$("fieldError").hidden) return;
      showFieldError("Click the map or type coordinates first.", "lat", "lon");
      return;
    }
    searching = true;
    updateFindButton();
    const token = ++searchToken;
    clearResults();
    showSkeleton();
    try {
      const data = await api("/api/search", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lat: pos[0], lon: pos[1] }),
      });
      if (token !== searchToken) return;
      renderResults(data);
      pollBaseline(data, token);
    } catch (err) {
      if (token !== searchToken) return;
      showError(err.message ? err : { message: "Could not reach the server. Is the app still running?" });
      if (err.code === "not_ready") schedulePoll(300);
    } finally {
      searching = false;
      updateFindButton();
    }
  }

  // ---------------------------------------------------------------- status
  function showOverlay(st) {
    const o = $("overlay"), box = o.querySelector(".overlay-box");
    o.hidden = false;
    const isErr = st.state === "error";
    box.classList.toggle("err", isErr);
    $("overlaySpinner").hidden = isErr;
    $("overlayBarWrap").hidden = isErr;
    $("retryBtn").hidden = !isErr;
    if (isErr) {
      $("overlayTitle").textContent = "The road graph could not be prepared";
      $("overlayText").textContent = st.error || "Unknown error.";
      $("overlayMeta").textContent = "Fix the problem (see README → Troubleshooting) and press “Try again”. Files used: " +
        Object.values(st.paths || {}).join("  |  ");
      return;
    }
    const building = st.state === "building";
    $("overlayTitle").textContent = building ? "Preparing the road network…" : st.state === "loading" ? "Loading the road network…" : "Starting…";
    $("overlayText").textContent = building
      ? "Building the graph from your parquet files (cleaning, joining small gaps, keeping the connected network). This only happens when the files are new or changed; the result is saved and later starts take seconds."
      : st.state === "loading" ? "Reading the saved graph into memory and preparing the hospital list."
      : "Connecting to the server.";
    $("overlayBar").style.width = Math.round((st.progress || 0) * 100) + "%";
    $("overlayMeta").textContent = `${st.stage || ""}${st.elapsed_s ? " · " + st.elapsed_s + " s" : ""}${st.reason ? " · " + st.reason : ""}`;
  }

  function onReady(st) {
    ready = true;
    $("overlay").hidden = true;
    const g = st.graph || {};
    $("graphInfo").textContent = `Upper Egypt road network · ${fmtInt(g.nodes || 0)} nodes · ${fmtInt(g.edges || 0)} road segments`
      + (g.stitched_pieces ? ` · ${g.stitched_pieces} gap(s) bridged` : "");
    // coverage box
    coverageLayer.clearLayers();
    if (g.bbox) {
      L.rectangle([[g.bbox[1], g.bbox[0]], [g.bbox[3], g.bbox[2]]], {
        color: "#0b6e4f", weight: 1.5, dashArray: "6 6", fill: false, interactive: false,
      }).bindTooltip("Road data coverage", { sticky: true }).addTo(coverageLayer);
    }
    if (builtAt !== g.built_at) {
      builtAt = g.built_at;
      clearResults();
      loadFacilities();
    } else if (st.facilities && facilitiesLoadedFor !== JSON.stringify(st.facilities)) {
      loadFacilities();
    }
    if (st.facility_error) toast("Hospital list problem: " + st.facility_error, 9000);
    updateFindButton();
  }

  // ---- hospitals on the map, grouped by governorate ----------------------
  const NO_GOV = "(no governorate)";
  let govGroups = new Map();       // governorate -> { layer, count }
  let govSelected = new Set();     // governorates currently shown on the map
  let govKnown = new Set();        // governorates seen in earlier loads (so a reload keeps your choice)
  let govTotal = 0;

  function buildFacilityLayers(facilities) {
    facilityLayer.clearLayers();
    govGroups = new Map();
    facilities.forEach((f) => {
      const g = (f.governorate || "").trim() || NO_GOV;
      let grp = govGroups.get(g);
      if (!grp) { grp = { layer: L.layerGroup(), count: 0 }; govGroups.set(g, grp); }
      grp.count++;
      L.circleMarker([f.lat, f.lon], { radius: 4, color: "#7f1d1d", weight: 1, fillColor: "#ef4444", fillOpacity: 0.8 })
        .bindTooltip(f.name, { direction: "top" }).addTo(grp.layer);
    });
    govTotal = facilities.length;
    syncGovernorates();
  }

  // names shown in the filter: hospital groups + boundary governorates, limited by the Full Egypt switch
  function govNames() {
    const bound = new Set(govFeatures.map((f) => f.name));
    const visible = new Set(visibleBoundaryNames());
    const names = new Set(visible);
    govGroups.forEach((_, g) => { if (!bound.has(g) || visible.has(g)) names.add(g); });
    return [...names].sort((a, b) =>
      a === NO_GOV ? 1 : b === NO_GOV ? -1 : a.localeCompare(b));
  }
  const govCount = (g) => (govGroups.has(g) ? govGroups.get(g).count : 0);

  // keep selection / list / borders in step after hospitals load or the switch changes
  function syncGovernorates() {
    const names = new Set(govNames());
    govSelected = new Set([...govSelected].filter((g) => names.has(g)));
    [...govKnown].forEach((g) => { if (!names.has(g)) govKnown.delete(g); });
    names.forEach((g) => { if (!govKnown.has(g)) { govKnown.add(g); govSelected.add(g); } });   // new ones start ticked
    renderGovList();
    applyGovSelection();
  }

  function renderGovList() {
    const ul = $("govList");
    ul.replaceChildren();
    govNames().forEach((g) => {
      const cb = el("input", { type: "checkbox", "data-gov": g, onchange: (e) => {
        if (e.target.checked) govSelected.add(g); else govSelected.delete(g);
        applyGovSelection();
      } });
      const row = el("label", { class: "govrow" }, cb,
        el("span", { class: "govname", dir: "auto", text: g, title: g }),
        el("span", { class: "govcount", text: String(govCount(g)), "aria-label": `${govCount(g)} hospitals` }));
      const only = el("button", { type: "button", class: "linkbtn govonly", text: "only",
        title: `Show only ${g}`, onclick: () => { govSelected = new Set([g]); applyGovSelection(); } });
      ul.append(el("li", {}, row, only));
    });
    $("govBtn").disabled = govNames().length === 0;
  }

  // show/hide each governorate's markers, then refresh the checkboxes, the button text and the count
  function applyGovSelection() {
    let shown = 0;
    govGroups.forEach((grp, g) => {
      const on = govSelected.has(g);
      if (on) { shown += grp.count; if (!facilityLayer.hasLayer(grp.layer)) facilityLayer.addLayer(grp.layer); }
      else if (facilityLayer.hasLayer(grp.layer)) facilityLayer.removeLayer(grp.layer);
    });
    // dashed border only for governorates that are ticked in the filter
    govBorders.forEach((lyr, g) => {
      const on = govSelected.has(g);
      if (on && !borderLayer.hasLayer(lyr)) borderLayer.addLayer(lyr);
      else if (!on && borderLayer.hasLayer(lyr)) borderLayer.removeLayer(lyr);
    });
    document.querySelectorAll("#govList input[data-gov]").forEach((cb) => { cb.checked = govSelected.has(cb.dataset.gov); });
    const n = govSelected.size, all = govNames().length;
    $("govBtnText").textContent = !all ? "Filter by governorate"
      : n === all ? `All governorates (${all})`
      : n === 0 ? "No governorate selected"
      : n === 1 ? [...govSelected][0]
      : `${n} of ${all} governorates`;
    $("govBtnText").dir = n === 1 ? "auto" : "ltr";
    $("facCount").textContent = govTotal ? (shown === govTotal ? `(${govTotal})` : `(${shown} of ${govTotal})`) : "";
  }

  function setGovPanel(open) {
    $("govPanel").hidden = !open;
    $("govBtn").setAttribute("aria-expanded", open ? "true" : "false");
  }

  function initGovFilter() {
    $("govBtn").addEventListener("click", () => setGovPanel($("govPanel").hidden));
    $("govAll").addEventListener("click", () => { govSelected = new Set(govNames()); applyGovSelection(); });
    $("govNone").addEventListener("click", () => { govSelected = new Set(); applyGovSelection(); });
    document.addEventListener("click", (e) => { if (!e.target.closest(".govfilter")) setGovPanel(false); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") setGovPanel(false); });
  }

  async function loadFacilities() {
    try {
      const d = await api("/api/facilities");
      buildFacilityLayers(d.facilities);
      facilitiesLoadedFor = JSON.stringify(d.stats);
    } catch (err) {
      $("facCount").textContent = "";
      if (err.code === "facilities_unavailable") toast(err.message, 9000);
    }
  }

  function schedulePoll(ms) {
    clearTimeout(statusTimer);
    statusTimer = setTimeout(pollStatus, ms);
  }

  async function pollStatus() {
    let st;
    try {
      st = await api("/api/status");
    } catch (err) {
      ready = false;
      updateFindButton();
      showOverlay({ state: "idle", stage: "Waiting for the server…", progress: 0 });
      schedulePoll(2000);
      return;
    }
    if (st.state === "ready") {
      if (!ready || builtAt !== (st.graph && st.graph.built_at) || (st.facilities && facilitiesLoadedFor !== JSON.stringify(st.facilities))) onReady(st);
      schedulePoll(8000);
    } else {
      ready = false;
      updateFindButton();
      showOverlay(st);
      schedulePoll(st.state === "error" ? 4000 : 1000);
    }
  }

  // ------------------------------------------------------------------ boot
  async function boot() {
    try {
      cfg = await api("/api/config");
    } catch (err) {
      showOverlay({ state: "error", error: "Cannot reach the server: " + (err.message || err), paths: {} });
      return;
    }
    initMap();
    initBoundaries();

    $("lat").addEventListener("change", () => commitInputs(true));
    $("lon").addEventListener("change", () => commitInputs(true));
    for (const id of ["lat", "lon"]) {
      $(id).addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); if (commitInputs(true)) runSearch(); } });
      $(id).addEventListener("input", () => { $(id).classList.remove("invalid"); $("fieldError").hidden = true; });
    }
    // pasting "27.1809, 31.1837" (e.g. copied from Google Maps) fills both boxes
    for (const id of ["lat", "lon"]) {
      $(id).addEventListener("paste", (e) => {
        const text = (e.clipboardData || window.clipboardData).getData("text");
        const m = text.match(/^\s*([+-]?\d+(?:\.\d+)?)\s*[,;\s]\s*([+-]?\d+(?:\.\d+)?)\s*$/);
        if (!m) return;
        e.preventDefault();
        $("lat").value = m[1];
        $("lon").value = m[2];
        commitInputs(true);
      });
    }
    $("findBtn").addEventListener("click", runSearch);
    $("showFacilities").addEventListener("change", (e) => {
      if (e.target.checked) facilityLayer.addTo(map); else map.removeLayer(facilityLayer);
    });
    initGovFilter();
    $("retryBtn").addEventListener("click", async () => {
      $("retryBtn").disabled = true;
      try { await api("/api/admin/rebuild", { method: "POST" }); } catch (err) { toast(err.message || "Could not restart the build."); }
      $("retryBtn").disabled = false;
      schedulePoll(200);
    });
    $("locBtn").addEventListener("click", () => {
      if (!navigator.geolocation) { toast("Your browser does not support location."); return; }
      navigator.geolocation.getCurrentPosition(
        (p) => {
          const { latitude: lat, longitude: lon } = p.coords;
          if (!inEgypt(lat, lon)) { toast("Your current location is outside Egypt."); return; }
          setPin(lat, lon, false);
          map.setView([lat, lon], Math.max(map.getZoom(), 11));
        },
        () => toast("Could not get your location. Click the map instead."),
        { enableHighAccuracy: true, timeout: 10000 });
    });
    pollStatus();
  }

  boot();
})();
