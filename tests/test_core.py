"""Run with:  pip install -r requirements-dev.txt   then   pytest -q"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra as scipy_dijkstra

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from app.algorithms import baseline_dijkstra, enhanced_dijkstra  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.egypt import point_in_egypt  # noqa: E402
from app.graph_builder import BuildError, build_processed_graph, processed_graph_is_current  # noqa: E402
from app.graph_store import load_graph  # noqa: E402
import make_sample_data  # noqa: E402


@pytest.fixture()
def sample(tmp_path):
    out = make_sample_data.main(tmp_path / "s")
    return out, out / "config.sample.yaml"


# ------------------------------------------------------------------ Egypt
@pytest.mark.parametrize("lat,lon,expected", [
    (30.04, 31.24, True),    # Cairo
    (27.18, 31.18, True),    # Assiut
    (24.09, 32.90, True),    # Aswan
    (31.20, 29.92, True),    # Alexandria
    (31.26, 32.30, True),    # Port Said
    (27.91, 34.33, True),    # Sharm el-Sheikh
    (29.20, 25.52, True),    # Siwa
    (22.34, 31.62, True),    # Abu Simbel region
    (32.08, 34.78, False),   # Tel Aviv
    (15.60, 32.53, False),   # Khartoum
    (32.12, 20.07, False),   # Benghazi
    (21.42, 39.83, False),   # Mecca
    (33.50, 30.00, False),   # Mediterranean, far offshore
    (28.60, 33.15, False),   # Gulf of Suez water
    (float("nan"), 31.0, False),
    (0.0, 0.0, False),
])
def test_point_in_egypt(lat, lon, expected):
    assert point_in_egypt(lat, lon) is expected


# ---------------------------------------------------------------- builder
def test_builder_cleans_stitches_and_keeps_scc(sample):
    out, cfg = sample
    s = load_settings(cfg)
    meta = build_processed_graph(s)
    assert meta["cleaning"]["unknown_node_edges"] == 1
    assert meta["cleaning"]["self_loops"] == 1
    assert meta["cleaning"]["invalid_weight_edges"] == 1
    assert meta["cleaning"]["duplicate_edges"] == 1
    assert meta["stitched_pieces"] == 1                       # island A (198 m away)
    assert meta["nodes_dropped"] == 15 * 15 + 5               # island B + the dead-end stub
    g = load_graph(s)
    # every node can reach every other: single strong component
    from scipy.sparse.csgraph import connected_components
    m = csr_matrix((np.ones(len(g.indices)), g.indices_np, g.indptr_np), shape=(g.n, g.n))
    assert connected_components(m, directed=True, connection="strong")[0] == 1
    assert (out / "processed" / "stitched_edges.csv").exists()


def test_dropped_pieces_report(sample):
    out, cfg = sample
    s = load_settings(cfg)
    build_processed_graph(s)
    dp = pd.read_csv(s.proc_dropped)
    big = dp.sort_values("nodes", ascending=False).iloc[0]
    assert big.nodes == 15 * 15 and big.gap_to_main_m > 500 and "larger than max_gap_m" in big.reason


def test_facility_removal_reasons(sample):
    out, cfg = sample
    s = load_settings(cfg)
    build_processed_graph(s)
    from app.facilities import build_facility_index
    idx = build_facility_index(s, load_graph(s))
    assert "tier not eligible" in idx.removed["CE00006"]            # post office
    assert "name excluded" in idx.removed["CE00007"]                # under construction
    assert "unreliable" in idx.removed["CE00009"]
    assert "too far" in idx.removed["CE00011"]


def test_stitching_can_be_disabled(sample):
    out, cfg = sample
    text = cfg.read_text(encoding="utf-8").replace("enabled: true             # join", "enabled: false            # join")
    cfg.write_text(text, encoding="utf-8")
    meta = build_processed_graph(load_settings(cfg))
    assert meta["stitched_pieces"] == 0
    assert meta["nodes_dropped"] > 15 * 15 + 5               # island A is lost without stitching


def test_staleness_detection(sample):
    out, cfg = sample
    s = load_settings(cfg)
    assert processed_graph_is_current(s)[0] is False
    build_processed_graph(s)
    assert processed_graph_is_current(s)[0] is True
    time.sleep(0.05)
    os.utime(s.edges_path, None)                              # "edge file was updated"
    assert processed_graph_is_current(s) == (False, "edges file changed")


def test_missing_file_and_bad_columns(sample):
    out, cfg = sample
    s = load_settings(cfg)
    s.nodes_path.rename(s.nodes_path.with_name("x.parquet"))
    with pytest.raises(BuildError, match="nodes file was not found"):
        build_processed_graph(s)
    s.nodes_path.with_name("x.parquet").rename(s.nodes_path)
    s.cols["edges"]["u"] = "nope"
    with pytest.raises(BuildError, match="missing column 'nope'"):
        build_processed_graph(s)


def test_time_computed_when_column_missing(sample):
    out, cfg = sample
    s = load_settings(cfg)
    e = pd.read_parquet(s.edges_path).drop(columns=["travel_time_s", "speed_kmh"])
    e.to_parquet(s.edges_path, index=False)
    meta = build_processed_graph(s)
    assert "computed" in meta["time_source"]
    g = load_graph(s)
    assert min(g.weights) > 0


# ------------------------------------------------------------- algorithms
def test_algorithms_match_scipy(sample):
    out, cfg = sample
    s = load_settings(cfg)
    build_processed_graph(s)
    g = load_graph(s)
    mat = csr_matrix((np.array(g.weights), g.indices_np, g.indptr_np), shape=(g.n, g.n))
    rng = np.random.default_rng(0)
    targets = set(rng.choice(g.n, 40, replace=False).tolist())
    for src in rng.choice(g.n, 15, replace=False):
        src = int(src)
        ref = scipy_dijkstra(mat, directed=True, indices=src)
        expected = sorted((ref[t], t) for t in targets)[:3]
        enh = enhanced_dijkstra(g, src, targets, 3)
        base = baseline_dijkstra(g, src, targets, 3)
        assert [round(t, 6) for t, _ in enh.hits] == pytest.approx([round(t, 6) for t, _ in expected])
        assert [round(t, 6) for t, _ in base.hits] == pytest.approx([round(t, 6) for t, _ in expected])
        assert enh.settled <= base.settled
        assert base.settled == g.n                           # strongly connected: baseline reaches all


def test_source_is_a_hospital(sample):
    out, cfg = sample
    s = load_settings(cfg)
    build_processed_graph(s)
    g = load_graph(s)
    res = enhanced_dijkstra(g, 5, {5, 9, 20}, 3)
    assert res.hits[0] == (0.0, 5)


# -------------------------------------------------------------------- API
@pytest.fixture()
def client(sample):
    from fastapi.testclient import TestClient
    from app.main import create_app
    out, cfg = sample
    app = create_app(cfg)
    with TestClient(app) as c:
        c.out = out
        for _ in range(200):
            st = c.get("/api/status").json()
            if st["state"] in ("ready", "error"):
                break
            time.sleep(0.1)
        assert st["state"] == "ready", st
        yield c


def _wait_baseline(c, job_id, timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = c.get(f"/api/baseline/{job_id}").json()
        if r["status"] in ("done", "error", "cancelled"):
            return r
        time.sleep(0.05)
    raise AssertionError("baseline timed out")


def test_api_search_basic(client):
    r = client.post("/api/search", json={"lat": 27.115, "lon": 31.115})
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["hospitals"]) == 3
    etas = [h["eta_min"] for h in d["hospitals"]]
    assert etas == sorted(etas)
    for h in d["hospitals"]:
        assert h["distance_km"] > 0 and h["route"] and h["facility"]["name"]
        assert "node" not in h["facility"]
    names = " ".join(h["facility"]["name"] for h in d["hospitals"])
    assert "Post Office" not in names and "الإنشاء" not in names
    assert d["enhanced"]["compute_ms"] >= 0 and d["enhanced"]["settled_nodes"] > 0
    b = _wait_baseline(client, d["job_id"])
    assert b["status"] == "done" and b["match"] is True
    assert b["settled_nodes"] > d["enhanced"]["settled_nodes"]


def test_api_detour_fields(client):
    d = client.post("/api/search", json={"lat": 27.115, "lon": 31.115}).json()
    for h in d["hospitals"]:
        assert h["straight_km"] > 0 and h["straight_km"] <= h["distance_km"] + 0.5
        assert h["detour"] is False
    far = client.post("/api/search", json={"lat": 27.5590, "lon": 31.1590}).json()
    assert all(h["detour_ratio"] is None or h["detour_ratio"] < 3 for h in far["hospitals"])


def test_api_same_location_grouped(client):
    # CE00002 and CE00003 share one spot -> reported once, with the other listed as "also here"
    r = client.post("/api/search", json={"lat": 27.1295, "lon": 31.1295}).json()
    hits = [h for h in r["hospitals"] if h["facility"]["id"] in ("CE00002", "CE00003")]
    assert len(hits) == 1 and len(hits[0]["also_here"]) == 1


def test_api_flag_over_one_hour(client):
    r = client.post("/api/search", json={"lat": 27.5590, "lon": 31.1590}).json()
    assert [h["flagged"] for h in r["hospitals"]] == [False, True, True]   # 1 hospital at the road end, 2 far away
    assert r["hospitals"][1]["eta_min"] > 60
    assert any(w["code"] == "some_far" for w in r["warnings"])
    near = client.post("/api/search", json={"lat": 27.115, "lon": 31.115}).json()
    assert not any(h["flagged"] for h in near["hospitals"])


def test_api_pin_validation(client):
    r = client.post("/api/search", json={"lat": 30.04, "lon": 31.24})        # Cairo: Egypt, but no roads
    assert r.status_code == 400 and r.json()["error"]["code"] == "outside_coverage"
    r = client.post("/api/search", json={"lat": 32.08, "lon": 34.78})        # Tel Aviv
    assert r.status_code == 400 and r.json()["error"]["code"] == "outside_egypt"
    for bad in ({"lat": "abc", "lon": 31}, {"lat": 95, "lon": 31}, {"lat": 27}, {}, {"lat": None, "lon": None}):
        r = client.post("/api/search", json=bad)
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_input"
    r = client.post("/api/search", content='{"lat": NaN, "lon": 31}', headers={"content-type": "application/json"})
    assert r.status_code in (400, 422)


def test_api_unknown_job(client):
    assert client.get("/api/baseline/doesnotexist").status_code == 404


def test_api_config_and_facilities(client):
    cfg = client.get("/api/config").json()
    assert len(cfg["egypt_polygon"]) > 20
    f = client.get("/api/facilities").json()
    assert f["stats"]["kept"] == 7 and len(f["facilities"]) == 7


def test_facilities_csv_hot_reload(client):
    path = client.out / "facilities_flagged.csv"
    before = client.post("/api/search", json={"lat": 27.115, "lon": 31.115}).json()
    names = [h["facility"]["id"] for h in before["hospitals"]]
    df = pd.read_csv(path, encoding="utf-8-sig")
    df = df[~df.canonical_entity_id.isin(names[:1])]
    time.sleep(0.05)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    after = client.post("/api/search", json={"lat": 27.115, "lon": 31.115}).json()
    assert names[0] not in [h["facility"]["id"] for h in after["hospitals"]]


def test_broken_facilities_csv_keeps_previous_list(client):
    path = client.out / "facilities_flagged.csv"
    client.post("/api/search", json={"lat": 27.115, "lon": 31.115})
    time.sleep(0.05)
    path.write_text("garbage,only\n1,2\n", encoding="utf-8")
    r = client.post("/api/search", json={"lat": 27.115, "lon": 31.115})
    assert r.status_code == 200                                    # still served from the last good list


def test_graph_file_change_triggers_rebuild(client):
    s = client.app.state.settings
    client.app.state.settings.server["source_check_seconds"] = 0
    time.sleep(0.05)
    os.utime(s.edges_path, None)
    st = client.get("/api/status").json()
    assert st["state"] in ("building", "loading", "ready")
    for _ in range(200):
        st = client.get("/api/status").json()
        if st["state"] == "ready":
            break
        time.sleep(0.1)
    assert st["state"] == "ready"
    assert client.post("/api/search", json={"lat": 27.115, "lon": 31.115}).status_code == 200


def test_not_ready_and_missing_files(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app
    out = make_sample_data.main(tmp_path / "m")
    (out / "Upper_Egypt_nodes.parquet").unlink()
    with TestClient(create_app(out / "config.sample.yaml")) as c:
        for _ in range(100):
            st = c.get("/api/status").json()
            if st["state"] == "error":
                break
            time.sleep(0.05)
        assert st["state"] == "error" and "nodes file was not found" in st["error"]
        r = c.post("/api/search", json={"lat": 27.1, "lon": 31.1})
        assert r.status_code == 503 and r.json()["error"]["code"] == "not_ready"


# --------------------------------------------- river with NO bridge in the data
def test_far_bank_is_not_dropped_when_bridges_are_missing(tmp_path):
    """Two big road grids ~1.2 km apart (a 'Nile') with no bridge: both banks must survive,
    all hospitals on both banks must be usable, and a pin on either bank finds 3 hospitals."""
    import make_nile_test_data
    from app.facilities import build_facility_index
    cfg, nodes, east, west = make_nile_test_data.make(tmp_path / "nile")
    s = load_settings(cfg)
    meta = build_processed_graph(s)
    assert meta["nodes_dropped"] == 0 and meta["stitched_pieces"] >= 1
    g = load_graph(s)
    fac = build_facility_index(s, g)
    assert fac.stats["kept"] == 5 and not fac.removed
    for ids in (east, west):
        lon, lat = nodes[ids[20, 20]]
        src, snap = g.snap(lat, lon)
        assert snap < 50                                   # snaps to its OWN bank
        assert len(enhanced_dijkstra(g, src, fac.targets, 3).hits) == 3


# ------------------------------------------------------------ "Show more"
def test_api_show_more(client):
    base = client.post("/api/search", json={"lat": 27.115, "lon": 31.115}).json()
    first = [h["facility"]["id"] for h in base["hospitals"]]
    more = client.post("/api/search", json={"lat": 27.115, "lon": 31.115, "more": True}).json()
    ids = [h["facility"]["id"] for h in more["hospitals"]]
    assert len(first) == 3 and len(ids) >= 1
    assert not set(first) & set(ids)                                   # only NEW hospitals
    assert [h["rank"] for h in more["hospitals"]] == list(range(4, 4 + len(ids)))
    etas = [h["eta_min"] for h in base["hospitals"]] + [h["eta_min"] for h in more["hospitals"]]
    assert etas == sorted(etas)                                        # still nearest-first overall
    assert "job_id" not in more                                        # no second timing comparison
    # and it must not cancel the baseline of the original search
    assert _wait_baseline(client, base["job_id"])["status"] == "done"


def test_api_config_exposes_result_counts(client):
    c = client.get("/api/config").json()["search"]
    assert c["results"] == 3 and c["more_results"] == 3                # sample config; real default is 5 + 5
