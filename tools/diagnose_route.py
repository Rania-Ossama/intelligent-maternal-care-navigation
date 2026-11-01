"""Explain why a route is long (e.g. a missing Nile bridge) or why a hospital is not recommended.

Examples (run from the project folder, after the app has built the graph at least once):

  # route between two points (say, east bank -> west bank of the Nile)
  python tools/diagnose_route.py --from 28.0900 30.7500 --to 28.1000 30.7800

  # route from a point to a facility by id, and why that facility is (not) in the list
  python tools/diagnose_route.py --from 28.0900 30.7500 --facility CE00123

It prints: the road time/length vs the straight-line distance, whether the endpoints
are in the cleaned network, which facility filter removed a facility, and which dropped
road pieces (possible cut-off bridges) lie near the route. It also writes
data/processed/diagnose_route.geojson, which you can drag into https://geojson.io
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.algorithms import enhanced_dijkstra, path_length_m, reconstruct_path  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.facilities import FacilityError, build_facility_index  # noqa: E402
from app.graph_builder import build_processed_graph, processed_graph_is_current  # noqa: E402
from app.graph_store import load_graph  # noqa: E402


def hav_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1, a)))


def dist_to_bbox_km(lat, lon, row):
    clat = min(max(lat, row.lat_min), row.lat_max)
    clon = min(max(lon, row.lon_min), row.lon_max)
    return hav_km(lat, lon, clat, clon)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config")
    ap.add_argument("--from", dest="src", nargs=2, type=float, metavar=("LAT", "LON"), required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--to", dest="dst", nargs=2, type=float, metavar=("LAT", "LON"))
    g.add_argument("--facility", help="facility id, e.g. CE00123")
    ap.add_argument("--radius-km", type=float, default=3.0, help="how far from the route ends to look for dropped pieces")
    a = ap.parse_args()

    s = load_settings(a.config)
    ok, why = processed_graph_is_current(s)
    if not ok:
        print(f"Processed graph is not ready ({why}); building it now ...")
        build_processed_graph(s, progress=lambda st, f: print(f"  {st}"))
    graph = load_graph(s)
    print(f"Graph: {graph.n:,} nodes, {len(graph.indices):,} road segments\n")

    fac = None
    try:
        fac = build_facility_index(s, graph)
    except FacilityError as exc:
        print(f"(facility list unavailable: {exc})\n")

    src_lat, src_lon = a.src
    if a.dst:
        dst_lat, dst_lon = a.dst
        label = "destination point"
    else:
        fid = a.facility
        row = next((r for r in (fac.rows if fac else []) if r["id"] == fid), None)
        if row:
            print(f"Facility {fid}: IN the recommendation list -> {row['name']} ({row['tier_label']}), "
                  f"{row['snap_m']:.0f} m from its road node")
            dst_lat, dst_lon, label = row["lat"], row["lon"], row["name"]
        else:
            reason = fac.removed.get(fid) if fac else None
            c = s.cols["facilities"]
            raw = pd.read_csv(s.facilities_path, encoding="utf-8-sig", dtype=str)
            hit = raw[raw[c["id"]] == fid]
            if hit.empty:
                print(f"Facility {fid} is not in the CSV at all.")
                return 1
            r0 = hit.iloc[0]
            print(f"Facility {fid} ({r0[c['name']]}) is NOT in the recommendation list.")
            print(f"  reason: {reason or 'unknown'}")
            try:
                dst_lat, dst_lon = float(r0[c["lat"]]), float(r0[c["lon"]])
            except (TypeError, ValueError):
                print("  it has no usable coordinates, so no route can be drawn.")
                return 1
            label = str(r0[c["name"]])
            print("  (routing to it anyway, ignoring the filters)")

    n1, m1 = graph.snap(src_lat, src_lon)
    n2, m2 = graph.snap(dst_lat, dst_lon)
    straight = hav_km(src_lat, src_lon, dst_lat, dst_lon)
    print(f"\nFROM  {src_lat:.5f}, {src_lon:.5f}  -> road node {graph.node_ids[n1]} ({m1:.0f} m away)")
    print(f"TO    {dst_lat:.5f}, {dst_lon:.5f}  -> road node {graph.node_ids[n2]} ({m2:.0f} m away)   [{label}]")
    print(f"Straight-line distance: {straight:.2f} km")
    for nm, m in (("FROM", m1), ("TO", m2)):
        if m > 500:
            print(f"  WARNING: the {nm} point is {m / 1000:.1f} km from the nearest road in the cleaned network, so the "
                  f"route below really starts/ends at that road point. The point may sit on a dropped piece.")

    res = enhanced_dijkstra(graph, n1, {n2}, 1)
    if not res.hits:
        print("\nRESULT: NOT REACHABLE in the cleaned graph.")
    else:
        t_s, node = res.hits[0]
        path = reconstruct_path(res.prev, node)
        km = path_length_m(graph, path) / 1000
        print(f"\nRESULT: road distance {km:.2f} km, estimated time {t_s / 60:.1f} min, "
              f"{len(path):,} nodes on the route")
        if straight >= 0.5:
            print(f"        the road is {km / straight:.1f}x the straight-line distance")
            if km / straight >= 3:
                print("        -> BIG DETOUR. If the two points are on opposite sides of a river, the route probably\n"
                      "           goes around because no bridge connects them in the graph (or the bridge is far away).")
        coords = [[float(graph.lon[i]), float(graph.lat[i])] for i in path]
        out = s.processed_dir / "diagnose_route.geojson"
        out.write_text(json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"name": "route", "km": round(km, 2), "min": round(t_s / 60, 1)},
             "geometry": {"type": "LineString", "coordinates": coords}},
            {"type": "Feature", "properties": {"name": "from"}, "geometry": {"type": "Point", "coordinates": [src_lon, src_lat]}},
            {"type": "Feature", "properties": {"name": "to"}, "geometry": {"type": "Point", "coordinates": [dst_lon, dst_lat]}},
        ]}), encoding="utf-8")
        print(f"        route saved to {out}  (drag it into https://geojson.io to see it)")

    # ---- dropped pieces near the endpoints / midpoint
    if not s.proc_dropped.exists():
        print("\n(no dropped_pieces.csv yet: delete data/processed and start the app once to create it)")
        return 0
    dp = pd.read_csv(s.proc_dropped)
    if dp.empty:
        print("\nNo road pieces of 5+ nodes were dropped.")
        return 0
    mid = ((src_lat + dst_lat) / 2, (src_lon + dst_lon) / 2)
    pts = {"from point": (src_lat, src_lon), "to point": (dst_lat, dst_lon), "midpoint": mid}
    dp["near_km"] = dp.apply(lambda r: min(dist_to_bbox_km(la, lo, r) for la, lo in pts.values()), axis=1)
    near = dp[dp.near_km <= a.radius_km].sort_values("near_km").head(12)
    print(f"\nDropped road pieces within {a.radius_km:g} km of the endpoints/midpoint: {len(near)} "
          f"(of {len(dp):,} listed in dropped_pieces.csv)")
    if len(near):
        print("A cut-off BRIDGE usually shows up as a long thin piece (extent_m of a few hundred metres to ~2 km)\n"
              "with a small gap_to_main_m:\n")
        print(near[["piece", "nodes", "extent_m", "gap_to_main_m", "center_lat", "center_lon", "reason"]]
              .to_string(index=False))
        print("\nIf one of these is the bridge: lower stitching.min_component_nodes (e.g. 5) and/or raise "
              "stitching.max_gap_m in config.yaml, delete data/processed and restart.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
