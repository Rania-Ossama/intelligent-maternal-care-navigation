"""Owns the graph lifecycle: build (if needed) -> load -> ready, and watches the input files."""
from __future__ import annotations

import threading
import time
import traceback

from .config import Settings
from .facilities import FacilityError, FacilityStore
from .graph_builder import BuildError, build_processed_graph, processed_graph_is_current, source_fingerprints
from .graph_store import Graph, load_graph


def _fp_key(fps: dict) -> tuple:
    return tuple((k, (v["size"], v["mtime_ns"]) if v else None) for k, v in sorted(fps.items()))


class GraphManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.facilities = FacilityStore(settings)
        self.graph: Graph | None = None
        self.state = "idle"            # idle | building | loading | ready | error
        self.stage = ""
        self.progress = 0.0
        self.error: str | None = None
        self.facility_error: str | None = None
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.reason = ""
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._attempt_key: tuple | None = None
        self._last_check = 0.0

    # ------------------------------------------------------------ control
    def start(self) -> None:
        self._launch(force=False, reason="startup")

    def rebuild(self) -> bool:
        return self._launch(force=True, reason="rebuild requested")

    def _launch(self, force: bool, reason: str) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self.state = "building"
            self.stage = "Starting"
            self.progress = 0.0
            self.error = None
            self.started_at = time.time()
            self.finished_at = None
            self.reason = reason
            self._attempt_key = _fp_key(source_fingerprints(self.settings))
            self._thread = threading.Thread(target=self._run, args=(force,), name="graph-builder", daemon=True)
            self._thread.start()
            return True

    def _set(self, stage: str, frac: float, state: str | None = None) -> None:
        with self._lock:
            self.stage = stage
            self.progress = max(0.0, min(1.0, frac))
            if state:
                self.state = state

    def _run(self, force: bool) -> None:
        s = self.settings
        try:
            current, why = (False, "forced") if force else processed_graph_is_current(s)
            if not current:
                self.graph = None            # free the memory of the old graph first
                self.facilities.reset()
                print(f"[graph] building processed graph ({why}) ...", flush=True)
                self._set("Building the road graph", 0.01, "building")
                meta = build_processed_graph(s, progress=lambda st, f: self._set(st, f * 0.8, "building"))
                print(f"[graph] built in {meta['build_seconds']} s: {meta['nodes']:,} nodes, "
                      f"{meta['edges']:,} edges, {meta['stitched_pieces']} pieces stitched", flush=True)
            self._set("Loading the graph into memory", 0.82, "loading")
            self.graph = None
            graph = load_graph(s)
            self._set("Preparing hospitals", 0.95, "loading")
            self.facility_error = None
            try:
                self.facilities.reset()
                self.facilities.get(graph)
            except FacilityError as exc:
                self.facility_error = str(exc)
                print(f"[facilities] {exc}", flush=True)
            with self._lock:
                self.graph = graph
                self.state, self.stage, self.progress = "ready", "Ready", 1.0
                self.finished_at = time.time()
            print(f"[graph] ready: {graph.n:,} nodes", flush=True)
        except BuildError as exc:
            self._fail(str(exc))
        except MemoryError:
            self._fail("Not enough memory to build/load the road graph. Close other programs or use a machine with more RAM.")
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._fail(f"Unexpected error while preparing the graph: {exc}")

    def _fail(self, message: str) -> None:
        print(f"[graph] ERROR: {message}", flush=True)
        with self._lock:
            self.graph = None
            self.state, self.stage, self.error = "error", "Failed", message
            self.finished_at = time.time()

    # ------------------------------------------------------- file watching
    def check_sources(self) -> None:
        """Cheap (a few os.stat calls); starts a rebuild if nodes/edges files changed."""
        now = time.monotonic()
        if now - self._last_check < float(self.settings.server.get("source_check_seconds", 5)):
            return
        self._last_check = now
        if self.state in ("building", "loading"):
            return
        if _fp_key(source_fingerprints(self.settings)) != self._attempt_key:
            self._launch(force=False, reason="input files changed")

    # ------------------------------------------------------------- status
    def status(self) -> dict:
        with self._lock:
            elapsed = (self.finished_at or time.time()) - self.started_at if self.started_at else 0.0
            out = {
                "state": self.state, "stage": self.stage, "progress": round(self.progress, 3),
                "elapsed_s": round(elapsed, 1), "reason": self.reason, "error": self.error,
                "facility_error": self.facility_error,
                "paths": {"nodes": str(self.settings.nodes_path), "edges": str(self.settings.edges_path),
                          "facilities": str(self.settings.facilities_path)},
            }
            g = self.graph
        if g is not None:
            m = g.meta
            out["graph"] = {k: m.get(k) for k in ("nodes", "edges", "stitched_pieces", "synthetic_edges",
                                                  "nodes_dropped", "bbox", "built_at", "time_source")}
            out["graph"]["connectivity_before"] = m.get("connectivity_before")
            out["graph"]["connectivity_after"] = m.get("connectivity_after")
            out["facilities"] = self.facilities.stats
        return out
