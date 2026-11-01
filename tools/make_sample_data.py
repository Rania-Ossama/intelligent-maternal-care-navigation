"""Creates a small synthetic dataset (same columns as the real files) so the app can be tried
without the 2.3M-node network:

    python tools/make_sample_data.py
    python run.py --config sample_data/config.sample.yaml

It deliberately contains the problems found in the real data: a small island 190 m away
(should be stitched), an island 10 km away (should be dropped), one-way dead ends,
duplicate edges, bad rows, facilities with unreliable / missing coordinates, a
post office, an "under construction" hospital, and two facilities at the same spot.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sample_data"
R = 6371008.8


def hav(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def main(out: Path = OUT) -> Path:
    out.mkdir(exist_ok=True)
    nodes, edges = {}, []
    BASE = 5_000_000_000

    def add_node(nid, lon, lat):
        nodes[nid] = (lon, lat)

    def add_edge(a, b, highway="residential", maxspeed=None, both=True):
        edges.append((a, b, highway, maxspeed))
        if both:
            edges.append((b, a, highway, maxspeed))

    def grid(prefix, lat0, lon0, rows, cols, step=0.001, oneway_rows=()):
        ids = {}
        for r in range(rows):
            for c in range(cols):
                nid = BASE + prefix * 1_000_000 + r * 1000 + c
                ids[r, c] = nid
                add_node(nid, lon0 + c * step, lat0 + r * step)
        for r in range(rows):
            for c in range(cols):
                if c + 1 < cols:
                    add_edge(ids[r, c], ids[r, c + 1], "primary" if r % 10 == 0 else "residential",
                             "60" if r % 10 == 0 else None, both=r not in oneway_rows)
                if r + 1 < rows:
                    add_edge(ids[r, c], ids[r + 1, c], "residential")
        return ids

    main = grid(1, 27.100, 31.100, 60, 60, oneway_rows=(15, 30))       # main network (~6 km square)
    grid(2, 27.120, 31.161, 15, 15)                                   # island A: 190 m gap -> stitched
    grid(3, 27.100, 31.250, 15, 15)                                   # island B: ~10 km away -> dropped

    # dead-end one-way stub flowing INTO the main network (cannot get back out)
    prev = None
    for k in range(5):
        nid = BASE + 4_000_000 + k
        add_node(nid, 31.090 - k * 0.0005, 27.130)
        if prev is not None:
            add_edge(nid, prev, both=False)
        prev = nid
    add_edge(prev, main[30, 0], both=False)

    # long, slow road north of the grid -> trips from its far end exceed 60 minutes
    prev = main[59, 59]
    for k in range(1, 41):
        nid = BASE + 5_000_000 + k
        add_node(nid, 31.159, 27.159 + k * 0.01)
        add_edge(prev, nid, "unclassified")
        prev = nid
    far_end = nodes[prev]

    nodes_df = pd.DataFrame([(i, lon, lat) for i, (lon, lat) in nodes.items()], columns=["id", "lon", "lat"])
    e = pd.DataFrame(edges, columns=["u", "v", "highway", "maxspeed"])
    xy = nodes_df.set_index("id")
    e["length"] = hav(xy.loc[e.u, "lon"].to_numpy(), xy.loc[e.u, "lat"].to_numpy(),
                      xy.loc[e.v, "lon"].to_numpy(), xy.loc[e.v, "lat"].to_numpy())
    speeds = {"primary": 60, "residential": 30, "unclassified": 30}
    spd = pd.to_numeric(e["maxspeed"], errors="coerce").fillna(e["highway"].map(speeds))
    e["speed_kmh"] = spd
    e["travel_time_s"] = e["length"] / 1000 / spd * 3600
    e["oneway"] = None
    e["id"] = np.arange(len(e))

    # --- deliberately dirty rows
    dirty = pd.DataFrame([
        {"u": BASE + 1_000_000, "v": 999, "highway": "residential", "length": 10.0, "speed_kmh": 30, "travel_time_s": 1.2, "id": -1},   # unknown node
        {"u": BASE + 1_000_000, "v": BASE + 1_000_000, "highway": "residential", "length": 5.0, "speed_kmh": 30, "travel_time_s": 0.6, "id": -2},  # self loop
        {"u": BASE + 1_000_000, "v": BASE + 1_000_001, "highway": "residential", "length": 100.0, "speed_kmh": 30, "travel_time_s": float("nan"), "id": -3},  # NaN weight
        {"u": BASE + 1_000_000, "v": BASE + 1_000_001, "highway": "residential", "length": 100.0, "speed_kmh": 30, "travel_time_s": 9999.0, "id": -4},   # slower duplicate
    ])
    e = pd.concat([e, dirty], ignore_index=True)

    nodes_df.sample(frac=1, random_state=1).to_parquet(out / "Upper_Egypt_nodes.parquet", index=False)
    e.sample(frac=1, random_state=2).to_parquet(out / "Upper_Egypt_edges_weighted.parquet", index=False)

    def at(r, c, ids=main):
        lon, lat = nodes[ids[r, c]]
        return lat + 0.00003, lon + 0.00003

    rows = []

    def fac(i, name, tier, lat, lon, **kw):
        rows.append({"canonical_entity_id": f"CE{i:05d}", "canonical_name": name,
                     "governorate_assigned": kw.get("gov", "Assiut"), "district": kw.get("district", "Assiut"),
                     "address": kw.get("address", "Assiut, Assiut"), "phone": kw.get("phone"),
                     "phone_clean": kw.get("phone_clean"), "latitude_final": lat, "longitude_final": lon,
                     "birth_service_tier": tier, "facility_category": kw.get("category"),
                     "coord_reliable": kw.get("reliable", True)})

    T1, T2, T3, T4 = ("T1_maternity_hospital", "T2_general_hospital_unverified",
                      "T3_unspecified_hospital_unverified", "T4_needs_review")
    fac(1, "مستشفى الأمومة والطفولة", T1, *at(10, 10), phone="088-2333158")
    fac(2, "مستشفى أسيوط الجامعي", T2, *at(30, 30), phone="088-2413500")
    fac(3, "مستشفى أسيوط الجامعي (نسخة مكررة)", T2, *at(30, 30), phone="088-2413501")          # same spot as #2
    fac(4, "مستشفى النيل | Nile Hospital", T3, *at(50, 12), phone="088 2345678 - 088 2345679")
    fac(5, "Regional Union For Sohag Labors Syndicates", T3, *at(20, 40))                         # not a hospital
    fac(6, "Post Office - Farshout", T3, *at(40, 40))                                           # not a hospital
    fac(7, "مستشفى الصداقة قيد الإنشاء", T2, *at(45, 45))                                       # under construction
    fac(8, "مركز الملكة للنساء والتوليد", T4, *at(25, 5))                                       # tier excluded
    fac(9, "مستشفى بإحداثيات غير موثوقة", T2, *at(5, 5), reliable=False)
    island_a = {(r, c): BASE + 2_000_000 + r * 1000 + c for r in range(15) for c in range(15)}
    fac(10, "مستشفى الجزيرة العام", T2, *at(7, 7, island_a))
    fac(11, "مستشفى الجزيرة البعيدة", T2, 27.105, 31.255)                                       # island B: too far
    fac(12, "Hospital outside Egypt", T1, 31.5, 35.0)
    fac(13, "مستشفى بلا إحداثيات", T2, float("nan"), float("nan"))
    fac(14, "Veterinary Hospital", T2, *at(15, 50), category="veterinary (not human health)")
    fac(15, "مستشفى الركن البعيد", T2, *at(2, 57), phone="0100 1234567")
    fac(16, "مستشفى الطريق الشمالي", T2, far_end[1] - 0.0003, far_end[0] - 0.0003, phone="088-1112223")
    pd.DataFrame(rows).to_csv(out / "facilities_flagged.csv", index=False, encoding="utf-8-sig")

    cfg = (ROOT / "config.yaml").read_text(encoding="utf-8")
    cfg = (cfg.replace("data/Upper_Egypt_nodes.parquet", "Upper_Egypt_nodes.parquet")
              .replace("data/Upper_Egypt_edges_weighted.parquet", "Upper_Egypt_edges_weighted.parquet")
              .replace("data/facilities_flagged.csv", "facilities_flagged.csv")
              .replace("processed_dir: data/processed", "processed_dir: processed")
              .replace("center: [27.0, 31.0]", "center: [27.13, 31.13]")
              .replace("zoom: 7", "zoom: 12")
              .replace("results: 5 ", "results: 3 ").replace("more_results: 5 ", "more_results: 3 "))
    (out / "config.sample.yaml").write_text(cfg, encoding="utf-8")
    print(f"Sample data written to {out}")
    print(f"Run it with:  python run.py --config {out / 'config.sample.yaml'}")
    print(f"Try a pin at the far end of the slow road (1 near hospital + 2 flagged as > 1 h): lat {far_end[1]:.4f}, lon {far_end[0]:.4f}")
    return out


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
