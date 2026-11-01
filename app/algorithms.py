"""The two searches compared by the app.

enhanced_dijkstra : standard Dijkstra that STOPS as soon as it has settled the k nearest
                    hospital nodes (early exit).
baseline_dijkstra : standard Dijkstra over the WHOLE reachable graph, then picks the k
                    nearest hospital nodes.

Both use the same heap loop and the same edge weights (travel time in seconds), so
they must return the same hospitals and times; only the work done differs.
"""
from __future__ import annotations

import heapq
import threading
import time
from dataclasses import dataclass, field

import numpy as np

INF = float("inf")
CANCEL_CHECK_MASK = 0x3FFF          # check the cancel flag every 16384 settled nodes


class SearchCancelled(Exception):
    pass


@dataclass
class SearchResult:
    hits: list[tuple[float, int]]       # (seconds, node) sorted by seconds, at most k
    settled: int                        # nodes taken off the heap and finalised
    elapsed_s: float                    # search time only (no snapping / JSON)
    prev: object = field(repr=False)    # dict (enhanced) or list (baseline): predecessor per node


def enhanced_dijkstra(graph, source: int, targets, k: int,
                      cancel: threading.Event | None = None) -> SearchResult:
    t0 = time.perf_counter()
    indptr, indices, weights = graph.indptr, graph.indices, graph.weights
    push, pop = heapq.heappush, heapq.heappop
    dist = {source: 0.0}
    prev = {source: -1}
    heap = [(0.0, source)]
    hits: list[tuple[float, int]] = []
    settled = 0
    while heap:
        d, u = pop(heap)
        if d > dist[u]:
            continue                      # stale heap entry
        settled += 1
        if u in targets:
            hits.append((d, u))
            if len(hits) >= k:
                break                     # early exit: k nearest hospitals are final
        if cancel is not None and not (settled & CANCEL_CHECK_MASK) and cancel.is_set():
            raise SearchCancelled()
        for e in range(indptr[u], indptr[u + 1]):
            v = indices[e]
            nd = d + weights[e]
            old = dist.get(v)
            if old is None or nd < old:
                dist[v] = nd
                prev[v] = u
                push(heap, (nd, v))
    return SearchResult(hits, settled, time.perf_counter() - t0, prev)


def baseline_dijkstra(graph, source: int, targets, k: int,
                      cancel: threading.Event | None = None) -> SearchResult:
    t0 = time.perf_counter()
    indptr, indices, weights = graph.indptr, graph.indices, graph.weights
    push, pop = heapq.heappush, heapq.heappop
    n = graph.n
    dist = [INF] * n
    prev = [-1] * n
    dist[source] = 0.0
    heap = [(0.0, source)]
    settled = 0
    while heap:
        d, u = pop(heap)
        if d > dist[u]:
            continue
        settled += 1
        if cancel is not None and not (settled & CANCEL_CHECK_MASK) and cancel.is_set():
            raise SearchCancelled()
        for e in range(indptr[u], indptr[u + 1]):
            v = indices[e]
            nd = d + weights[e]
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                push(heap, (nd, v))
    found = sorted((dist[t], t) for t in targets if dist[t] < INF)
    return SearchResult(found[:k], settled, time.perf_counter() - t0, prev)


# ------------------------------------------------------------- path helpers
def reconstruct_path(prev, target: int) -> list[int]:
    """Node list source -> target from a predecessor map (dict or list)."""
    path = []
    node = target
    guard = 0
    while node != -1:
        path.append(node)
        node = prev[node]
        guard += 1
        if guard > 50_000_000:
            raise RuntimeError("path reconstruction did not terminate")
    path.reverse()
    return path


def path_length_m(graph, path: list[int]) -> float:
    """Sum of edge lengths along the path (looked up in the CSR arrays)."""
    total = 0.0
    ip, idx, ln = graph.indptr_np, graph.indices_np, graph.length_np
    for a, b in zip(path[:-1], path[1:]):
        lo, hi = ip[a], ip[a + 1]
        pos = np.flatnonzero(idx[lo:hi] == b)
        if len(pos) == 0:
            raise RuntimeError(f"edge {a}->{b} not found while measuring the route")
        total += float(ln[lo + pos[0]])
    return total


def thin_path(coords: list[list[float]], max_points: int) -> list[list[float]]:
    """Reduce a long polyline to at most ~max_points, always keeping both ends."""
    n = len(coords)
    if n <= max_points or max_points < 3:
        return coords
    step = int(np.ceil((n - 1) / (max_points - 1)))
    out = coords[::step]
    if out[-1] != coords[-1]:
        out.append(coords[-1])
    return out
