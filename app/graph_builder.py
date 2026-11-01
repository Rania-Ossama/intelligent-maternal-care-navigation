"""Builds the processed road graph (parquet files) from the raw nodes/edges parquet.

Steps
  1. read nodes + edges parquet (only the columns that are needed; geometry is skipped)
  2. travel time: use the time column, or compute it from length + maxspeed/highway
  3. clean: drop edges with unknown nodes, self loops, invalid weights, duplicates
  4. stitch: bridge small disconnected pieces to the main network (gap <= max_gap_m)
  5. keep only the largest STRONGLY connected component
  6. write  graph_nodes.parquet, graph_edges.parquet, graph_meta.json, stitched_edges.csv

Everything is written atomically, and graph_meta.json is written last, so a half
finished build is never mistaken for a valid one.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Callable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from .config import Settings

EARTH_R_M = 6371008.8
ProgressFn = Callable[[str, float], None]


class BuildError(RuntimeError):
    """Raised with a message that is safe to show to the user."""


# ----------------------------------------------------------------- helpers
def to_xyz(lon, lat) -> np.ndarray:
    lon = np.radians(np.asarray(lon, dtype=np.float64))
    lat = np.radians(np.asarray(lat, dtype=np.float64))
    return np.column_stack((np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)))


def chord_to_m(chord) -> np.ndarray:
    """Chord length on the unit sphere -> great-circle metres."""
    return 2.0 * EARTH_R_M * np.arcsin(np.clip(np.asarray(chord) / 2.0, 0.0, 1.0))


def m_to_chord(metres: float) -> float:
    return 2.0 * np.sin(metres / (2.0 * EARTH_R_M))


def haversine_m(lon1, lat1, lon2, lat2) -> np.ndarray:
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_R_M * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def fingerprint(path) -> dict | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return {"path": str(path), "size": st.st_size, "mtime_ns": st.st_mtime_ns}


def source_fingerprints(settings: Settings) -> dict:
    return {"nodes": fingerprint(settings.nodes_path), "edges": fingerprint(settings.edges_path)}


def _parquet_columns(path) -> list[str]:
    try:
        return list(pq.ParquetFile(path).schema.names)
    except Exception as exc:  # corrupt / half-copied file
        raise BuildError(f"Cannot read {os.path.basename(str(path))}: {exc}") from exc


def _dedupe_min_time(src, dst, t, ln, syn, n):
    """Keep one edge per (src, dst): the one with the smallest travel time."""
    if len(src) == 0:
        return src, dst, t, ln, syn
    key = src.astype(np.int64) * np.int64(n) + dst.astype(np.int64)
    order = np.lexsort((t, key))
    ks = key[order]
    first = np.empty(len(order), dtype=bool)
    first[0] = True
    first[1:] = ks[1:] != ks[:-1]
    sel = order[first]
    return src[sel], dst[sel], t[sel], ln[sel], syn[sel]


def _components(n, src, dst, connection: str):
    g = csr_matrix((np.ones(len(src), dtype=np.int32), (src, dst)), shape=(n, n))
    return connected_components(g, directed=True, connection=connection)


def _parse_maxspeed(series: pd.Series) -> pd.Series:
    text = series.astype("string")
    num = pd.to_numeric(text.str.extract(r"(\d+(?:\.\d+)?)", expand=False), errors="coerce")
    mph = text.str.contains("mph", case=False, na=False)
    num = num.where(~mph, num * 1.609344)
    return num.where(num > 0)


_DROPPED_COLS = ["piece", "nodes", "center_lat", "center_lon", "lat_min", "lat_max", "lon_min", "lon_max",
                 "extent_m", "gap_to_main_m", "example_node_id", "reason"]


def _dropped_pieces(labels, sizes, main, keep, lon, lat, node_ids, min_nodes, max_gap, stitching_on,
                    min_listed: int = 5, max_rows: int = 20000) -> pd.DataFrame:
    """List the road pieces that were NOT kept (size >= min_listed) so missing bridges can be found."""
    cand = np.flatnonzero((sizes >= min_listed) & (np.arange(len(sizes)) != main))
    if len(cand) == 0:
        return pd.DataFrame(columns=_DROPPED_COLS)
    xyz = to_xyz(lon, lat)
    tree = cKDTree(xyz[keep])
    idx = np.flatnonzero(np.isin(labels, cand))
    d, _ = tree.query(xyz[idx], k=1)
    df = pd.DataFrame({"piece": labels[idx], "d": d, "lat": lat[idx], "lon": lon[idx], "nid": node_ids[idx]})
    g = df.groupby("piece").agg(nodes=("d", "size"), gap=("d", "min"), center_lat=("lat", "mean"),
                                center_lon=("lon", "mean"), lat_min=("lat", "min"), lat_max=("lat", "max"),
                                lon_min=("lon", "min"), lon_max=("lon", "max"), example_node_id=("nid", "first"))
    g["gap_to_main_m"] = chord_to_m(g["gap"].to_numpy()).round(1)
    g["extent_m"] = haversine_m(g["lon_min"], g["lat_min"], g["lon_max"], g["lat_max"]).round(0)

    def why(row):
        if row["gap_to_main_m"] > max_gap:
            return f"gap to main network larger than max_gap_m ({max_gap:.0f} m)"
        if not stitching_on:
            return "stitching is disabled"
        if row["nodes"] < min_nodes:
            return f"smaller than min_component_nodes ({min_nodes}) so it was not bridged"
        return "bridged, but still not strongly connected (one-way dead end)"
    g["reason"] = g.apply(why, axis=1)
    g = g.reset_index().sort_values("nodes", ascending=False).head(max_rows)
    for c in ("center_lat", "center_lon", "lat_min", "lat_max", "lon_min", "lon_max"):
        g[c] = g[c].round(6)
    return g[_DROPPED_COLS]


# ------------------------------------------------------------------- build
def build_processed_graph(settings: Settings, progress: ProgressFn | None = None,
                          log: Callable[[str], None] = print) -> dict:
    t_start = time.perf_counter()
    prog = progress or (lambda stage, frac: None)
    gcfg = settings.graph
    scfg = gcfg.get("stitching", {})
    cn, ce = settings.cols["nodes"], settings.cols["edges"]
    fps = source_fingerprints(settings)

    for label, key, path in (("nodes", "nodes", settings.nodes_path), ("edges", "edges", settings.edges_path)):
        if fps[key] is None:
            raise BuildError(f"The {label} file was not found: {path}")

    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    if settings.proc_meta.exists():          # invalidate the old build before touching anything
        settings.proc_meta.unlink()

    # ---- 1. nodes -------------------------------------------------------
    prog("Reading nodes", 0.03)
    names = _parquet_columns(settings.nodes_path)
    missing = [c for c in (cn["id"], cn["lon"], cn["lat"]) if c not in names]
    if missing:
        raise BuildError(f"Nodes file is missing column(s) {missing}. Columns found: {names}. "
                         f"Fix 'columns.nodes' in config.yaml.")
    nodes = pd.read_parquet(settings.nodes_path, columns=[cn["id"], cn["lon"], cn["lat"]])
    nodes.columns = ["id", "lon", "lat"]
    n_raw_nodes = len(nodes)
    nodes = nodes.dropna()
    nodes = nodes[(nodes["lat"].between(-90, 90)) & (nodes["lon"].between(-180, 180))]
    nodes = nodes.drop_duplicates("id").sort_values("id").reset_index(drop=True)
    N = len(nodes)
    if N == 0:
        raise BuildError("The nodes file contains no valid nodes.")
    node_ids = nodes["id"].to_numpy(dtype=np.int64)
    lon = nodes["lon"].to_numpy(dtype=np.float64)
    lat = nodes["lat"].to_numpy(dtype=np.float64)
    del nodes
    log(f"nodes: {N:,} (raw {n_raw_nodes:,})")

    # ---- 2. edges -------------------------------------------------------
    prog("Reading edges", 0.10)
    enames = _parquet_columns(settings.edges_path)
    for need in (ce["u"], ce["v"]):
        if need not in enames:
            raise BuildError(f"Edges file is missing column '{need}'. Columns found: {enames}. "
                             f"Fix 'columns.edges' in config.yaml.")
    have_time = ce["time"] in enames
    have_len = ce["length"] in enames
    want = [ce["u"], ce["v"]]
    if have_time:
        want.append(ce["time"])
    if have_len:
        want.append(ce["length"])
    if not have_time:
        if not have_len:
            raise BuildError(f"Edges file has neither '{ce['time']}' nor '{ce['length']}'; "
                             f"at least one is needed to weight the roads.")
        want += [c for c in (ce["highway"], ce["maxspeed"]) if c in enames]
    edges = pd.read_parquet(settings.edges_path, columns=want)
    n_raw_edges = len(edges)
    log(f"edges: {n_raw_edges:,} raw rows")
    if n_raw_edges == 0:
        raise BuildError("The edges file is empty.")

    # ---- 3. map ids -> indices, clean ----------------------------------
    prog("Cleaning edges", 0.22)
    u_id = edges[ce["u"]].to_numpy(dtype=np.int64)
    v_id = edges[ce["v"]].to_numpy(dtype=np.int64)
    u = np.searchsorted(node_ids, u_id)
    v = np.searchsorted(node_ids, v_id)
    u_c, v_c = np.minimum(u, N - 1), np.minimum(v, N - 1)
    ok = (node_ids[u_c] == u_id) & (node_ids[v_c] == v_id)
    n_unknown = int((~ok).sum())
    ok &= u_c != v_c
    n_loops = int(((node_ids[u_c] == u_id) & (node_ids[v_c] == v_id) & (u_c == v_c)).sum())

    if have_len:
        length = pd.to_numeric(edges[ce["length"]], errors="coerce").to_numpy(dtype=np.float64)
    else:
        length = np.full(len(edges), np.nan)
    geo = haversine_m(lon[u_c], lat[u_c], lon[v_c], lat[v_c])
    bad_len = ~np.isfinite(length) | (length <= 0)
    length = np.where(bad_len, np.maximum(geo, 1.0), length)

    if have_time:
        tt = pd.to_numeric(edges[ce["time"]], errors="coerce").to_numpy(dtype=np.float64)
        time_source = ce["time"]
    else:
        prog("Computing travel times", 0.25)
        speed = pd.Series(np.nan, index=edges.index)
        if ce["maxspeed"] in edges:
            speed = _parse_maxspeed(edges[ce["maxspeed"]]).astype("float64")
        table = {str(k): float(val) for k, val in gcfg.get("highway_speed_kmh", {}).items()}
        default = float(gcfg.get("default_speed_kmh", 30))
        if ce["highway"] in edges:
            hw = edges[ce["highway"]].astype("string").map(table).astype("float64")
            speed = speed.fillna(hw)
        speed = speed.fillna(default).to_numpy(dtype=np.float64)
        tt = length / 1000.0 / speed * 3600.0
        time_source = "computed from length + maxspeed/highway"
    bad_w = ~np.isfinite(tt) | (tt <= 0)
    n_bad_w = int((bad_w & ok).sum())
    ok &= ~bad_w

    src = u_c[ok].astype(np.int64)
    dst = v_c[ok].astype(np.int64)
    t = tt[ok]
    ln = length[ok]
    syn = np.zeros(len(src), dtype=np.uint8)
    del edges, u, v, u_id, v_id, u_c, v_c, tt, length, geo
    n_before_dedupe = len(src)
    src, dst, t, ln, syn = _dedupe_min_time(src, dst, t, ln, syn, N)
    n_dupes = n_before_dedupe - len(src)
    if len(src) == 0:
        raise BuildError("No usable edges remain after cleaning (check node ids in the edges file).")
    log(f"edges cleaned: {len(src):,} (unknown-node {n_unknown:,}, loops {n_loops:,}, "
        f"bad weight {n_bad_w:,}, duplicates {n_dupes:,})")

    # ---- 4. components before stitching --------------------------------
    prog("Finding connected pieces", 0.35)
    n_weak, weak_lab = _components(N, src, dst, "weak")
    weak_sizes = np.bincount(weak_lab)
    n_scc0, scc_lab = _components(N, src, dst, "strong")
    scc_sizes0 = np.bincount(scc_lab)
    stats_before = {
        "weak_components": int(n_weak),
        "largest_weak_component": int(weak_sizes.max()),
        "strong_components": int(n_scc0),
        "largest_scc": int(scc_sizes0.max()),
    }
    log(f"before stitching: {n_weak:,} weak components, largest {weak_sizes.max():,}; "
        f"largest SCC {scc_sizes0.max():,}")
    del weak_lab

    # ---- 5. stitching ---------------------------------------------------
    # Small pieces (>= min_component_nodes) are joined to the main network by ONE bridge at
    # the closest point, if the gap is <= max_gap_m.
    # LARGE pieces (>= large_component_nodes, e.g. the other bank of the Nile when the
    # bridges are missing from the OSM extract) are joined with a bigger gap limit
    # (large_max_gap_m) and with SEVERAL bridges, one per `large_bridge_spacing_m` of river
    # bank. A single bridge at one random place would force every east<->west trip to
    # drive to that one spot, which is what made the routes absurd / impossible before.
    stitches: list[pd.DataFrame] = []
    if scfg.get("enabled", True):
        xyz = to_xyz(lon, lat)
        max_gap = float(scfg.get("max_gap_m", 500))
        min_nodes = int(scfg.get("min_component_nodes", 25))
        rounds = int(scfg.get("max_rounds", 4))
        bridge_speed_ms = float(scfg.get("speed_kmh", 30)) / 3.6
        large_nodes = int(scfg.get("large_component_nodes", 1000))
        large_gap = max(float(scfg.get("large_max_gap_m", 3000)), max_gap)
        spacing_m = float(scfg.get("large_bridge_spacing_m", 5000))
        crossing_penalty_s = float(scfg.get("large_bridge_penalty_s", 120))
        chord_max = m_to_chord(large_gap)             # search once with the biggest limit
        labels, sizes = scc_lab, scc_sizes0
        for rnd in range(1, rounds + 1):
            prog(f"Stitching gaps (round {rnd}/{rounds})", 0.40 + 0.08 * rnd)
            main = int(sizes.argmax())
            cand = np.flatnonzero((sizes >= min_nodes) & (np.arange(len(sizes)) != main))
            if len(cand) == 0:
                break
            cand_nodes = np.flatnonzero(np.isin(labels, cand))
            main_nodes = np.flatnonzero(labels == main)
            tree = cKDTree(xyz[main_nodes])
            d, j = tree.query(xyz[cand_nodes], k=1, distance_upper_bound=chord_max)
            hit = np.isfinite(d)
            if not hit.any():
                break
            df = pd.DataFrame({"comp": labels[cand_nodes[hit]], "d": d[hit],
                               "a": cand_nodes[hit], "b": main_nodes[j[hit]]})
            df["dist_m"] = chord_to_m(df["d"].to_numpy())
            df["size"] = sizes[df["comp"].to_numpy()]
            df["large"] = df["size"] >= large_nodes
            # small pieces: normal gap limit, one bridge each (closest pair)
            small = df[~df["large"] & (df["dist_m"] <= max_gap)]
            small = small.sort_values(["comp", "d"]).drop_duplicates("comp")
            # large pieces: bigger limit, closest pair per spacing cell along the bank
            big = df[df["large"]].copy()
            if len(big):
                cell = (np.floor(lat[big["a"].to_numpy()] / (spacing_m / 111_000.0)).astype(np.int64) * 1_000_003
                        + np.floor(lon[big["a"].to_numpy()] / (spacing_m / 96_000.0)).astype(np.int64))
                big["cell"] = cell
                big = big.sort_values(["comp", "cell", "d"]).drop_duplicates(["comp", "cell"])
            df = pd.concat([small, big], ignore_index=True)
            if df.empty:
                break
            a, b = df["a"].to_numpy(), df["b"].to_numpy()
            dist_m = np.maximum(df["dist_m"].to_numpy(), 1.0)
            tm = np.maximum(dist_m / bridge_speed_ms, 0.1) + np.where(df["large"].to_numpy(), crossing_penalty_s, 0.0)
            new_src = np.concatenate([a, b])
            new_dst = np.concatenate([b, a])
            src = np.concatenate([src, new_src])
            dst = np.concatenate([dst, new_dst])
            t = np.concatenate([t, tm, tm])
            ln = np.concatenate([ln, dist_m, dist_m])
            syn = np.concatenate([syn, np.ones(len(new_src), dtype=np.uint8)])
            src, dst, t, ln, syn = _dedupe_min_time(src, dst, t, ln, syn, N)
            stitches.append(pd.DataFrame({
                "round": rnd,
                "component_nodes": df["size"].to_numpy(),
                "gap_m": np.round(dist_m, 1),
                "node_a_id": node_ids[a], "node_b_id": node_ids[b],
                "a_lon": lon[a], "a_lat": lat[a], "b_lon": lon[b], "b_lat": lat[b],
            }))
            log(f"stitch round {rnd}: {len(df)} bridges ({int(df['large'].sum())} for large pieces) "
                f"joining {df['comp'].nunique()} pieces")
            _, labels = _components(N, src, dst, "strong")
            sizes = np.bincount(labels)
        del xyz

    # ---- 6. largest strongly connected component -----------------------
    prog("Keeping the largest strongly connected component", 0.85)
    n_scc, scc_lab = _components(N, src, dst, "strong")
    scc_sizes = np.bincount(scc_lab)
    main = int(scc_sizes.argmax())
    if gcfg.get("keep_largest_scc", True):
        keep = scc_lab == main
    else:
        keep = np.ones(N, dtype=bool)
    M = int(keep.sum())
    dropped_df = _dropped_pieces(scc_lab, scc_sizes, main, keep, lon, lat, node_ids,
                                 int(scfg.get("min_component_nodes", 25)), float(scfg.get("max_gap_m", 500)),
                                 bool(scfg.get("enabled", True))) if gcfg.get("keep_largest_scc", True) else None
    if M < 2:
        raise BuildError("The road network is empty after keeping the largest connected component.")
    new_idx = np.full(N, -1, dtype=np.int64)
    new_idx[keep] = np.arange(M)
    emask = keep[src] & keep[dst]
    src, dst, t, ln, syn = new_idx[src[emask]], new_idx[dst[emask]], t[emask], ln[emask], syn[emask]
    order = np.argsort(src, kind="stable")
    src, dst, t, ln, syn = src[order], dst[order], t[order], ln[order], syn[order]
    out_ids, out_lon, out_lat = node_ids[keep], lon[keep], lat[keep]
    log(f"final graph: {M:,} nodes, {len(src):,} edges (dropped {N - M:,} nodes)")
    if dropped_df is not None and len(dropped_df):
        big_drop = dropped_df[dropped_df["nodes"] >= int(scfg.get("large_component_nodes", 1000))]
        for _, r in big_drop.head(10).iterrows():
            log(f"WARNING: a LARGE road piece ({int(r['nodes'])} nodes) near lat {r['center_lat']}, lon {r['center_lon']} "
                f"was dropped: {r['reason']}. Hospitals there will be unreachable.")

    # ---- 7. write -------------------------------------------------------
    prog("Writing processed parquet files", 0.93)
    stitch_df = pd.concat(stitches, ignore_index=True) if stitches else pd.DataFrame(
        columns=["round", "component_nodes", "gap_m", "node_a_id", "node_b_id",
                 "a_lon", "a_lat", "b_lon", "b_lat"])
    pnodes = pd.DataFrame({"node_id": out_ids, "lon": out_lon, "lat": out_lat})
    pedges = pd.DataFrame({"src": src.astype(np.int32), "dst": dst.astype(np.int32),
                           "time_s": t.astype(np.float64), "length_m": ln.astype(np.float32),
                           "synthetic": syn})
    tmp = {p: p.with_name(p.name + ".tmp") for p in (settings.proc_nodes, settings.proc_edges, settings.proc_stitches,
                                                       settings.proc_dropped)}
    (dropped_df if dropped_df is not None else pd.DataFrame(columns=_DROPPED_COLS)).to_csv(
        tmp[settings.proc_dropped], index=False)
    pnodes.to_parquet(tmp[settings.proc_nodes], index=False, compression="zstd")
    pedges.to_parquet(tmp[settings.proc_edges], index=False, compression="zstd")
    stitch_df.to_csv(tmp[settings.proc_stitches], index=False)
    for final, tmp_path in tmp.items():
        os.replace(tmp_path, final)

    meta = {
        "build_signature": settings.build_signature(),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "build_seconds": round(time.perf_counter() - t_start, 1),
        "sources": fps,
        "time_source": time_source,
        "nodes": int(M),
        "edges": int(len(src)),
        "synthetic_edges": int(syn.sum()),
        "stitched_pieces": int(len(stitch_df)),
        "large_pieces_dropped": int(((dropped_df["nodes"] >= int(scfg.get("large_component_nodes", 1000))).sum())
                                    if dropped_df is not None and len(dropped_df) else 0),
        "nodes_dropped": int(N - M),
        "dropped_pieces_listed": int(len(dropped_df)) if dropped_df is not None else 0,
        "bbox": [float(out_lon.min()), float(out_lat.min()), float(out_lon.max()), float(out_lat.max())],
        "cleaning": {"raw_nodes": int(n_raw_nodes), "raw_edges": int(n_raw_edges),
                     "unknown_node_edges": n_unknown, "self_loops": n_loops,
                     "invalid_weight_edges": n_bad_w, "duplicate_edges": int(n_dupes)},
        "connectivity_before": stats_before,
        "connectivity_after": {"strong_components": int(n_scc), "largest_scc": int(scc_sizes.max())},
    }
    tmp_meta = settings.proc_meta.with_name(settings.proc_meta.name + ".tmp")
    tmp_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    os.replace(tmp_meta, settings.proc_meta)
    prog("Processed graph written", 1.0)
    return meta


def processed_graph_is_current(settings: Settings) -> tuple[bool, str]:
    """True if the processed files exist and match the current inputs + settings."""
    if not (settings.proc_meta.exists() and settings.proc_nodes.exists() and settings.proc_edges.exists()):
        return False, "processed graph not found"
    try:
        meta = json.loads(settings.proc_meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, "processed graph metadata unreadable"
    if meta.get("build_signature") != settings.build_signature():
        return False, "graph settings changed"
    cur = source_fingerprints(settings)
    old = meta.get("sources", {})
    for key in ("nodes", "edges"):
        a, b = cur.get(key), old.get(key)
        if a is None:
            return False, f"{key} file missing"
        if not b or (a["size"], a["mtime_ns"]) != (b.get("size"), b.get("mtime_ns")):
            return False, f"{key} file changed"
    return True, "up to date"
