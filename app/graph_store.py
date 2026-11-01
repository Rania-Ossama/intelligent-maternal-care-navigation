"""Loads the processed parquet files into memory-friendly structures."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from .config import Settings
from .graph_builder import BuildError, chord_to_m, to_xyz


@dataclass
class Graph:
    n: int
    # python lists: fastest for the heap loops in algorithms.py
    indptr: list = field(repr=False)
    indices: list = field(repr=False)
    weights: list = field(repr=False)
    # numpy copies: used after the search (route length, coordinates, snapping)
    indptr_np: np.ndarray = field(repr=False)
    indices_np: np.ndarray = field(repr=False)
    length_np: np.ndarray = field(repr=False)
    node_ids: np.ndarray = field(repr=False)
    lon: np.ndarray = field(repr=False)
    lat: np.ndarray = field(repr=False)
    tree: cKDTree = field(repr=False)
    meta: dict = field(default_factory=dict)
    build_id: str = ""

    def snap(self, lat: float, lon: float) -> tuple[int, float]:
        """Nearest graph node to a point -> (node index, distance in metres)."""
        d, i = self.tree.query(to_xyz([lon], [lat])[0], k=1)
        return int(i), float(chord_to_m(d))

    def snap_many(self, lats, lons) -> tuple[np.ndarray, np.ndarray]:
        d, i = self.tree.query(to_xyz(lons, lats), k=1)
        return i.astype(np.int64), chord_to_m(d)

    def coords_of(self, path: list[int]) -> list[list[float]]:
        idx = np.asarray(path, dtype=np.int64)
        return np.column_stack((self.lat[idx], self.lon[idx])).round(6).tolist()


def load_graph(settings: Settings) -> Graph:
    try:
        meta = json.loads(settings.proc_meta.read_text(encoding="utf-8"))
        nodes = pd.read_parquet(settings.proc_nodes)
        edges = pd.read_parquet(settings.proc_edges, columns=["src", "dst", "time_s", "length_m"])
    except Exception as exc:
        raise BuildError(f"Could not read the processed graph files: {exc}") from exc

    n = len(nodes)
    src = edges["src"].to_numpy(dtype=np.int64)
    if len(src) and not np.all(src[1:] >= src[:-1]):          # safety: ensure CSR order
        order = np.argsort(src, kind="stable")
        edges = edges.iloc[order]
        src = src[order]
    dst = edges["dst"].to_numpy(dtype=np.int32)
    time_s = edges["time_s"].to_numpy(dtype=np.float64)
    length = edges["length_m"].to_numpy(dtype=np.float32)
    indptr = np.zeros(n + 1, dtype=np.int64)
    np.cumsum(np.bincount(src, minlength=n), out=indptr[1:])

    lon = nodes["lon"].to_numpy(dtype=np.float64)
    lat = nodes["lat"].to_numpy(dtype=np.float64)
    tree = cKDTree(to_xyz(lon, lat))
    return Graph(
        n=n,
        indptr=indptr.tolist(), indices=dst.tolist(), weights=time_s.tolist(),
        indptr_np=indptr, indices_np=dst, length_np=length,
        node_ids=nodes["node_id"].to_numpy(dtype=np.int64), lon=lon, lat=lat,
        tree=tree, meta=meta, build_id=meta.get("built_at", ""),
    )
