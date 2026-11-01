"""Loads, filters and snaps the facilities CSV. Reloads automatically when the CSV changes."""
from __future__ import annotations

import math
import re
import threading
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import Settings
from .egypt import point_in_egypt
from .graph_builder import fingerprint
from .graph_store import Graph


class FacilityError(RuntimeError):
    """Problem with the facilities file that is safe to show to the user."""


def _clean(x):
    if x is None:
        return None
    if isinstance(x, float) and math.isnan(x):
        return None
    s = str(x).strip()
    return s if s and s.lower() not in ("nan", "none", "<na>") else None


def _tier_rank(tier: str | None) -> int:
    m = re.match(r"T(\d+)", tier or "")
    return int(m.group(1)) if m else 9


def split_phones(text: str | None) -> list[str]:
    """'096-3345726 | 323105 - 323243' -> ['096-3345726', '323105', '323243']"""
    if not text:
        return []
    parts = re.split(r"\s*[|/,;]\s*|\s+-\s+", text)
    return [p.strip() for p in parts if re.search(r"\d{5,}", p)]


@dataclass
class FacilityIndex:
    rows: list[dict]                               # kept facilities (public form)
    by_node: dict[int, list[int]]                  # graph node -> row positions (best first)
    targets: set[int]
    stats: dict
    removed: dict = field(default_factory=dict)       # facility id -> reason it was removed
    csv_fingerprint: dict | None = None
    build_id: str = ""
    config_key: str = ""

    def location(self, node: int) -> dict:
        members = [self.rows[i] for i in self.by_node[node]]
        primary = members[0]
        return {"primary": primary, "others": members[1:]}


def _compile(pattern: str | None, what: str):
    if not pattern:
        return None
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise FacilityError(f"Invalid regular expression for {what} in config.yaml: {exc}") from exc


def build_facility_index(settings: Settings, graph: Graph) -> FacilityIndex:
    fc, cols = settings.fac, settings.cols["facilities"]
    path = settings.facilities_path
    fp = fingerprint(path)
    if fp is None:
        raise FacilityError(f"The facilities file was not found: {path}")
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False, na_values=[""])
    except Exception as exc:
        raise FacilityError(f"Could not read the facilities CSV: {exc}") from exc

    for key in ("id", "name", "lat", "lon", "tier"):
        if cols[key] not in df.columns:
            raise FacilityError(f"Facilities CSV is missing column '{cols[key]}'. "
                                f"Columns found: {list(df.columns)}. Fix 'columns.facilities' in config.yaml.")

    def col(key):
        c = cols.get(key)
        return df[c] if c and c in df.columns else pd.Series([None] * len(df), index=df.index, dtype="object")

    stats: dict = {"csv_rows": int(len(df)), "removed": {}}
    removed_ids: dict = {}

    def drop(mask: pd.Series, reason: str):
        nonlocal df
        mask = mask.reindex(df.index, fill_value=False)
        n = int(mask.sum())
        if n:
            if reason != "duplicate id":
                for fid in df.loc[mask, cols["id"]].dropna():
                    removed_ids[str(fid)] = reason
            stats["removed"][reason] = stats["removed"].get(reason, 0) + n
            df = df[~mask]

    # ---- identity and coordinates
    drop(df[cols["id"]].isna(), "missing id")
    drop(df.duplicated(cols["id"], keep="first"), "duplicate id")
    lat = pd.to_numeric(df[cols["lat"]], errors="coerce")
    lon = pd.to_numeric(df[cols["lon"]], errors="coerce")
    drop(lat.isna() | lon.isna(), "missing coordinates")
    lat = pd.to_numeric(df[cols["lat"]], errors="coerce")
    lon = pd.to_numeric(df[cols["lon"]], errors="coerce")
    inside = pd.Series([point_in_egypt(a, o) for a, o in zip(lat, lon)], index=df.index)
    drop(~inside, "coordinates outside Egypt")

    if fc.get("drop_unreliable_coordinates", True) and cols.get("coord_reliable") in df.columns:
        reliable = df[cols["coord_reliable"]].fillna("true").astype(str).str.strip().str.lower()
        drop(reliable.isin(["false", "0", "no"]), "unreliable coordinates")

    # ---- what kind of place is it
    tier = df[cols["tier"]].fillna("").astype(str).str.strip()
    name = df[cols["name"]].fillna("").astype(str)
    always = set(fc.get("include_tiers", []))
    conditional = fc.get("include_tiers_if_name_matches", {}) or {}
    ok_tier = tier.isin(always)
    for t, pattern in conditional.items():
        rx = _compile(pattern, f"include_tiers_if_name_matches[{t}]")
        ok_tier |= (tier == t) & name.str.contains(rx, na=False) if rx else (tier == t)
    drop(~ok_tier, "tier not eligible")

    tier = df[cols["tier"]].fillna("").astype(str).str.strip()
    name = df[cols["name"]].fillna("").astype(str)
    rx_ex = _compile(fc.get("exclude_name_regex"), "exclude_name_regex")
    if rx_ex is not None:
        drop(name.str.contains(rx_ex, na=False), "name excluded (under construction / not a hospital)")
    cats = set(fc.get("exclude_categories", []) or [])
    if cats and cols.get("category") in df.columns:
        drop(df[cols["category"]].isin(cats), "category excluded")

    if df.empty:
        raise FacilityError("No facilities remain after applying the filters in config.yaml "
                            "(check 'facilities.include_tiers').")

    # ---- snap to the (largest strongly connected) road network
    lat = pd.to_numeric(df[cols["lat"]]).to_numpy(dtype=np.float64)
    lon = pd.to_numeric(df[cols["lon"]]).to_numpy(dtype=np.float64)
    nodes, snap_m = graph.snap_many(lat, lon)
    too_far = snap_m > float(fc.get("max_snap_to_road_m", 1000))
    drop(pd.Series(too_far, index=df.index), "too far from a road")
    keep = ~too_far
    nodes, snap_m, lat, lon = nodes[keep], snap_m[keep], lat[keep], lon[keep]

    labels = fc.get("tier_labels", {}) or {}
    rows: list[dict] = []
    for i, (_, r) in enumerate(df.iterrows()):
        full = _clean(r[cols["name"]]) or "(unnamed facility)"
        parts = [p.strip() for p in full.split("|") if p.strip()]
        phone_text = _clean(r.get(cols.get("phone"))) or _clean(r.get(cols.get("phone_fallback")))
        t = _clean(r[cols["tier"]])
        rows.append({
            "id": _clean(r[cols["id"]]),
            "name": parts[0] if parts else full,
            "alt_names": parts[1:],
            "governorate": _clean(r.get(cols.get("governorate"))),
            "district": _clean(r.get(cols.get("district"))),
            "address": _clean(r.get(cols.get("address"))),
            "phone": phone_text,
            "phones": split_phones(phone_text),
            "tier": t,
            "tier_label": labels.get(t, t),
            "lat": float(lat[i]), "lon": float(lon[i]),
            "snap_m": round(float(snap_m[i]), 1),
            "node": int(nodes[i]),
        })

    # group facilities that snap to the same road node: they are ONE location
    order = sorted(range(len(rows)), key=lambda k: (_tier_rank(rows[k]["tier"]), rows[k]["snap_m"], rows[k]["name"]))
    by_node: dict[int, list[int]] = {}
    for k in order:
        by_node.setdefault(rows[k]["node"], []).append(k)

    stats["kept"] = len(rows)
    stats["locations"] = len(by_node)
    stats["shared_locations"] = sum(1 for v in by_node.values() if len(v) > 1)
    return FacilityIndex(rows=rows, by_node=by_node, targets=set(by_node), stats=stats, removed=removed_ids,
                         csv_fingerprint=fp, build_id=graph.build_id)


class FacilityStore:
    """Caches the facility index and reloads it when the CSV or the graph changes."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._index: FacilityIndex | None = None
        self._lock = threading.Lock()
        self.last_error: str | None = None

    def get(self, graph: Graph) -> FacilityIndex:
        fp = fingerprint(self.settings.facilities_path)
        idx = self._index
        fresh = (idx is not None and fp is not None and idx.build_id == graph.build_id
                 and idx.csv_fingerprint
                 and (idx.csv_fingerprint["size"], idx.csv_fingerprint["mtime_ns"]) == (fp["size"], fp["mtime_ns"]))
        if fresh:
            return idx
        with self._lock:
            idx = self._index
            fp = fingerprint(self.settings.facilities_path)
            if (idx is not None and fp is not None and idx.build_id == graph.build_id and idx.csv_fingerprint
                    and (idx.csv_fingerprint["size"], idx.csv_fingerprint["mtime_ns"]) == (fp["size"], fp["mtime_ns"])):
                return idx
            try:
                new = build_facility_index(self.settings, graph)
                self._index = new
                self.last_error = None
                return new
            except FacilityError as exc:
                self.last_error = str(exc)
                # keep serving the previous good list if it belongs to this graph
                if idx is not None and idx.build_id == graph.build_id:
                    return idx
                raise

    def reset(self):
        with self._lock:
            self._index = None

    @property
    def stats(self) -> dict | None:
        return self._index.stats if self._index else None
