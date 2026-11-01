"""Runs searches. All CPU work happens on ONE worker thread, so timings are not distorted by
two searches running at once. The fast (enhanced) result is returned first; the slow
baseline runs afterwards in the background and is polled by the browser."""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import math

from .algorithms import (SearchCancelled, baseline_dijkstra, enhanced_dijkstra, path_length_m,
                         reconstruct_path, thin_path)
from .config import Settings
from .egypt import point_in_egypt
from .facilities import FacilityError, FacilityIndex
from .graph_store import Graph
from .manager import GraphManager


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1.0, a)))


def format_eta(seconds: float) -> str:
    minutes = int(round(seconds / 60.0))
    if seconds < 30:
        return "less than 1 min"
    if minutes < 60:
        return f"{minutes} min"
    h, m = divmod(minutes, 60)
    return f"{h} h {m:02d} min" if m else f"{h} h"


@dataclass
class Job:
    id: str
    graph: Graph = field(repr=False)
    source: int = 0
    targets: set = field(default_factory=set, repr=False)
    k: int = 3
    enhanced_hits: list = field(default_factory=list, repr=False)
    enhanced_ms: float = 0.0
    cancel: threading.Event = field(default_factory=threading.Event)
    status: str = "pending"        # pending | running | done | cancelled | error
    result: dict | None = None
    error: str | None = None


class SearchService:
    def __init__(self, settings: Settings, manager: GraphManager):
        self.settings = settings
        self.manager = manager
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="search")
        self.jobs: OrderedDict[str, Job] = OrderedDict()
        self._jobs_lock = threading.Lock()

    # ---------------------------------------------------------- public API
    async def search(self, lat: float, lon: float, more: bool = False) -> dict:
        graph, fac = self._require_ready()
        if not point_in_egypt(lat, lon):
            raise ApiError(400, "outside_egypt", "The pin must be inside Egypt. Move it onto Egyptian territory.")

        # stop any older baseline so this request is not queued behind it
        # (a "show more" request must NOT cancel the baseline of the search it belongs to)
        if not more:
            with self._jobs_lock:
                for j in self.jobs.values():
                    if j.status in ("pending", "running"):
                        j.cancel.set()

        loop = asyncio.get_running_loop()
        payload, job = await loop.run_in_executor(self.pool, self._enhanced_step, graph, fac, lat, lon, more)
        if job is None:                                     # "show more": no timing comparison, no baseline
            return payload
        with self._jobs_lock:
            for other in self.jobs.values():
                if other.status in ("pending", "running"):
                    other.cancel.set()
            self.jobs[job.id] = job
            while len(self.jobs) > 30:
                self.jobs.popitem(last=False)
        self.pool.submit(self._baseline_step, job)         # fire and forget
        return payload

    def baseline_status(self, job_id: str) -> dict:
        with self._jobs_lock:
            job = self.jobs.get(job_id)
        if job is None:
            raise ApiError(404, "unknown_job", "Unknown or expired search id.")
        if job.status == "done":
            return {"status": "done", **(job.result or {})}
        if job.status == "error":
            return {"status": "error", "message": job.error}
        return {"status": job.status}

    # ------------------------------------------------------------ internals
    def _require_ready(self) -> tuple[Graph, FacilityIndex]:
        m = self.manager
        m.check_sources()
        graph = m.graph
        if m.state != "ready" or graph is None:
            st = m.status()
            msg = st["error"] if st["state"] == "error" else f"The road graph is not ready yet ({st['stage']})."
            raise ApiError(503, "not_ready", msg, state=st["state"])
        try:
            fac = m.facilities.get(graph)
        except FacilityError as exc:
            raise ApiError(503, "facilities_unavailable", str(exc)) from exc
        return graph, fac

    def _enhanced_step(self, graph: Graph, fac: FacilityIndex, lat: float, lon: float, more: bool = False):
        s = self.settings.search
        k_first = int(s.get("results", 5))
        # first search: the k_first nearest. "Show more": search again for k_first + more_results
        # and return only the extra ones (ranks k_first+1 ...).
        k = k_first + int(s.get("more_results", 5)) if more else k_first
        offset = k_first if more else 0
        t_snap = time.perf_counter()
        source, snap_m = graph.snap(lat, lon)
        snap_ms = (time.perf_counter() - t_snap) * 1000.0

        if snap_m > float(s.get("max_snap_to_road_m", 5000)):
            b = graph.meta.get("bbox")
            area = (f" The road data covers roughly lat {b[1]:.2f}–{b[3]:.2f}, lon {b[0]:.2f}–{b[2]:.2f} "
                    f"(Upper Egypt). If you typed the coordinates, check that latitude and longitude are not swapped." if b else "")
            raise ApiError(400, "outside_coverage",
                           f"No road network within {snap_m / 1000:.0f} km of this pin.{area}", snap_m=round(snap_m))

        res = enhanced_dijkstra(graph, source, fac.targets, k)
        enhanced_ms = res.elapsed_s * 1000.0

        thr_s = float(s.get("eta_warn_minutes", 60)) * 60.0
        detour_ratio_warn = float(s.get("detour_warn_ratio", 3.0))
        detour_min_km = float(s.get("detour_min_straight_km", 1.0))
        max_pts = int(s.get("max_route_points", 4000))
        hospitals = []
        for rank, (t_s, node) in enumerate(res.hits[offset:], start=offset + 1):
            loc = fac.location(node)
            path = reconstruct_path(res.prev, node)
            dist_m = path_length_m(graph, path)
            primary = {kk: vv for kk, vv in loc["primary"].items() if kk != "node"}
            straight_km = _haversine_km(lat, lon, primary["lat"], primary["lon"])
            road_km = dist_m / 1000.0
            ratio = (road_km / straight_km) if straight_km >= detour_min_km else None
            hospitals.append({
                "rank": rank,
                "straight_km": round(straight_km, 2),
                "detour_ratio": round(ratio, 1) if ratio is not None else None,
                "detour": bool(ratio is not None and ratio >= detour_ratio_warn),
                "facility": primary,
                "also_here": [{"id": o["id"], "name": o["name"], "phone": o["phone"], "phones": o["phones"],
                               "tier_label": o["tier_label"]} for o in loc["others"]],
                "distance_km": round(dist_m / 1000.0, 2),
                "eta_seconds": round(t_s, 1),
                "eta_min": round(t_s / 60.0, 1),
                "eta_text": format_eta(t_s),
                "flagged": t_s > thr_s,
                "route": thin_path(graph.coords_of(path), max_pts),
                "road_access": [round(float(graph.lat[node]), 6), round(float(graph.lon[node]), 6)],
            })

        warnings = []
        if not more and snap_m > float(s.get("warn_snap_to_road_m", 1000)):
            warnings.append({"level": "warning", "code": "far_from_road",
                             "message": f"Your pin is {snap_m / 1000:.1f} km from the nearest road. "
                                        f"Routes start from that road point."})
        if not more and len(hospitals) < k:
            warnings.append({"level": "warning", "code": "few_hospitals",
                             "message": f"Only {len(hospitals)} hospital(s) could be reached "
                                        f"(requested {k})."})
        n_det = [h["rank"] for h in hospitals if h["detour"]]
        if n_det:
            warnings.append({"level": "warning", "code": "detour",
                             "message": "Hospital " + ", ".join(f"#{r}" for r in n_det) + " needs a long detour "
                                        f"(road distance at least {detour_ratio_warn:g}x the straight-line distance). "
                                        "This is normal when a river lies in between, but it can also mean a bridge "
                                        "or road link is missing from the map data."})
        n_flag = sum(h["flagged"] for h in hospitals)
        if more:
            pass                                            # the page already shows the "far away" summary
        elif hospitals and n_flag == len(hospitals):
            warnings.append({"level": "danger", "code": "all_far",
                             "message": f"All of the nearest hospitals are more than "
                                        f"{int(thr_s // 60)} minutes away (estimated)."})
        elif n_flag:
            warnings.append({"level": "warning", "code": "some_far",
                             "message": f"{n_flag} hospital(s) are more than {int(thr_s // 60)} minutes away (estimated)."})

        if more:
            return {"pin": {"lat": lat, "lon": lon}, "snap": {"lat": round(float(graph.lat[source]), 6),
                    "lon": round(float(graph.lon[source]), 6), "distance_m": round(snap_m, 1)},
                    "hospitals": hospitals, "warnings": warnings,
                    "threshold_min": int(thr_s // 60)}, None
        job = Job(id=uuid.uuid4().hex[:12], graph=graph, source=source, targets=fac.targets, k=k,
                  enhanced_hits=res.hits, enhanced_ms=enhanced_ms)
        node_lat, node_lon = float(graph.lat[source]), float(graph.lon[source])
        payload = {
            "job_id": job.id,
            "pin": {"lat": lat, "lon": lon},
            "snap": {"lat": round(node_lat, 6), "lon": round(node_lon, 6),
                     "distance_m": round(snap_m, 1), "time_ms": round(snap_ms, 3)},
            "hospitals": hospitals,
            "enhanced": {"compute_ms": round(enhanced_ms, 3), "settled_nodes": res.settled},
            "baseline": {"status": "pending"},
            "threshold_min": int(thr_s // 60),
            "warnings": warnings,
            "graph": {"nodes": graph.n, "edges": int(graph.meta.get("edges", 0)),
                      "facilities_used": fac.stats.get("kept"), "locations": fac.stats.get("locations")},
        }
        return payload, job

    def _baseline_step(self, job: Job) -> None:
        if job.cancel.is_set():
            job.status = "cancelled"
            return
        job.status = "running"
        try:
            res = baseline_dijkstra(job.graph, job.source, job.targets, job.k, cancel=job.cancel)
        except SearchCancelled:
            job.status = "cancelled"
            return
        except Exception as exc:  # noqa: BLE001
            job.status, job.error = "error", f"Baseline search failed: {exc}"
            return
        base_ms = res.elapsed_s * 1000.0
        e_hits, b_hits = job.enhanced_hits, res.hits
        same_times = len(e_hits) == len(b_hits) and all(
            abs(a[0] - b[0]) <= 1e-6 * (1.0 + a[0]) for a, b in zip(e_hits, b_hits))
        same_nodes = [n for _, n in e_hits] == [n for _, n in b_hits]
        if same_times and same_nodes:
            note = "Both searches returned the same hospitals and travel times."
        elif same_times:
            note = "Same travel times (hospitals at equal distance were ordered differently)."
        else:
            note = "WARNING: the two searches disagree. Please report this."
        job.result = {
            "compute_ms": round(base_ms, 3),
            "settled_nodes": res.settled,
            "speedup": round(base_ms / job.enhanced_ms, 1) if job.enhanced_ms > 0 else None,
            "match": bool(same_times),
            "note": note,
        }
        job.status = "done"
