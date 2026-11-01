"""Two road grids (west bank / east bank) 1.2 km apart with NO bridge, hospitals on both."""
import sys, numpy as np, pandas as pd
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
R = 6371008.8
def hav(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = np.sin((lat2-lat1)/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin((lon2-lon1)/2)**2
    return 2*R*np.arcsin(np.sqrt(a))
def make(out: Path, gap_deg=0.0125):
    out.mkdir(parents=True, exist_ok=True)
    nodes, edges = {}, []
    def grid(prefix, lat0, lon0, rows, cols, step=0.001):
        ids = {}
        for r in range(rows):
            for c in range(cols):
                nid = 6_000_000_000 + prefix*1_000_000 + r*1000 + c
                ids[r, c] = nid; nodes[nid] = (lon0 + c*step, lat0 + r*step)
        for r in range(rows):
            for c in range(cols):
                if c+1 < cols: edges.append((ids[r,c], ids[r,c+1])); edges.append((ids[r,c+1], ids[r,c]))
                if r+1 < rows: edges.append((ids[r,c], ids[r+1,c])); edges.append((ids[r+1,c], ids[r,c]))
        return ids
    west = grid(1, 27.10, 31.00, 40, 40)                       # west bank
    east = grid(2, 27.10, 31.039 + gap_deg, 40, 40)            # east bank, ~1.2 km east, no bridge
    nd = pd.DataFrame([(i, lo, la) for i, (lo, la) in nodes.items()], columns=["id","lon","lat"])
    e = pd.DataFrame(edges, columns=["u","v"]); xy = nd.set_index("id")
    e["length"] = hav(xy.loc[e.u,"lon"].values, xy.loc[e.u,"lat"].values, xy.loc[e.v,"lon"].values, xy.loc[e.v,"lat"].values)
    e["highway"] = "residential"; e["travel_time_s"] = e["length"]/1000/30*3600
    nd.to_parquet(out/"nodes.parquet", index=False); e.to_parquet(out/"edges.parquet", index=False)
    def at(ids, r, c):
        lo, la = nodes[ids[r, c]]; return la+0.00003, lo+0.00003
    rows = []
    for i, (nm, ids, r, c) in enumerate([("مستشفى الغرب 1", west, 10, 10), ("مستشفى الغرب 2", west, 30, 30),
                                         ("مستشفى الشرق 1", east, 12, 12), ("مستشفى الشرق 2", east, 32, 28),
                                         ("مستشفى الشرق 3", east, 20, 35)], 1):
        la, lo = at(ids, r, c)
        rows.append({"canonical_entity_id": f"CE{i:05d}", "canonical_name": nm, "governorate_assigned": "X", "district": "X",
                     "address": "x", "phone": "1", "phone_clean": "1", "latitude_final": la, "longitude_final": lo,
                     "birth_service_tier": "T2_general_hospital_unverified", "facility_category": None, "coord_reliable": True})
    pd.DataFrame(rows).to_csv(out/"fac.csv", index=False, encoding="utf-8-sig")
    cfg = ((Path(__file__).resolve().parent.parent / "config.yaml")).read_text(encoding="utf-8")
    cfg = (cfg.replace("data/Upper_Egypt_nodes.parquet","nodes.parquet").replace("data/Upper_Egypt_edges_weighted.parquet","edges.parquet")
              .replace("data/facilities_flagged.csv","fac.csv").replace("processed_dir: data/processed","processed_dir: processed"))
    (out/"config.yaml").write_text(cfg, encoding="utf-8")
    return out/"config.yaml", nodes, east, west
