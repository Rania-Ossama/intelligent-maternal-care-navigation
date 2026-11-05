"""Governorate boundaries (GeoJSON) served to the map.

The file is read once at start-up, thinned a little (Douglas-Peucker, so the browser stays fast)
and each governorate is tagged as "Upper Egypt" or not, using the list in config.yaml.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# Spelling variants seen in different Egyptian admin datasets. Keys are normalised (see _norm).
_ALIASES = {
    "assiut": {"asyut", "assuit", "asiut", "اسيوط", "أسيوط"},
    "aswan": {"assuan", "اسوان", "أسوان"},
    "beni suef": {"bani suwayf", "bani suef", "beni suweif", "benisuef", "بني سويف"},
    "luxor": {"al uqsur", "uqsur", "الاقصر", "الأقصر"},
    "minya": {"menia", "minia", "al minya", "el minia", "el minya", "المنيا"},
    "qena": {"qina", "kena", "قنا"},
    "sohag": {"suhag", "sohaj", "سوهاج"},
}


def _norm(s) -> str:
    s = str(s or "").strip().lower()
    s = re.sub(r"[\u064b-\u065f\u0640]", "", s)             # Arabic diacritics / tatweel
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")
    s = re.sub(r"[-_.']", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _name_keys(name: str) -> set[str]:
    n = _norm(name)
    keys = {n}
    for canon, alts in _ALIASES.items():
        group = {canon} | {_norm(a) for a in alts}
        if n in group:
            keys |= group
    return keys


def _dp(points: list, tol: float) -> list:
    """Douglas-Peucker on a list of [x, y] (iterative)."""
    n = len(points)
    if n <= 4 or tol <= 0:
        return points
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = points[a]
        bx, by = points[b]
        dx, dy = bx - ax, by - ay
        den = dx * dx + dy * dy
        best, idx = -1.0, -1
        for i in range(a + 1, b):
            px, py = points[i]
            if den == 0:
                d = (px - ax) ** 2 + (py - ay) ** 2
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / den))
                d = (px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2
            if d > best:
                best, idx = d, i
        if best > tol * tol and idx > 0:
            keep[idx] = True
            stack.append((a, idx))
            stack.append((idx, b))
    out = [p for p, k in zip(points, keep) if k]
    return out if len(out) >= 4 else points


def _ring(coords: list, tol: float) -> list:
    pts = [[float(c[0]), float(c[1])] for c in coords]
    pts = _dp(pts, tol)
    return [[round(x, 4), round(y, 4)] for x, y in pts]


def _geometry(geom: dict, tol: float) -> dict | None:
    if not geom:
        return None
    t, c = geom.get("type"), geom.get("coordinates")
    if t == "Polygon":
        polys = [c]
    elif t == "MultiPolygon":
        polys = c
    else:
        return None
    out = [[_ring(r, tol) for r in poly] for poly in polys]
    return {"type": "MultiPolygon", "coordinates": out}


_NOT_GOV = re.compile(r"district|adm2|adm3|adm4|markaz|qism|subdistrict|village|shiakha|sheyakha|city", re.I)
MAX_GOVERNORATES = 40          # Egypt has 27; a file with far more polygons is a district-level file


def find_file(path: Path) -> tuple[Path | None, str]:
    """`path` should be the governorates .geojson file. If it is a folder, only a file whose name
    says "governorate" is accepted (never "the first file"), so district files are never read."""
    if path.is_file():
        return path, ""
    if path.is_dir():
        files = sorted(list(path.glob("*.geojson")) + list(path.glob("*.json")))
        good = [x for x in files if re.search(r"governorate|adm1", x.name, re.I) and not _NOT_GOV.search(x.name)]
        if len(good) == 1:
            return good[0], ""
        if not good:
            return None, (f"No governorates file found in {path}. Set paths.governorates in config.yaml to the exact "
                          f"file (e.g. {path.name}/egypt_governorates.geojson). Files seen: "
                          f"{', '.join(x.name for x in files) or 'none'}")
        return None, (f"More than one governorates file in {path} ({', '.join(x.name for x in good)}). "
                      f"Set paths.governorates in config.yaml to the exact file.")
    return None, f"Governorate boundaries file not found: {path}"


def _fail(src, upper_names, msg):
    return {"available": False, "source": str(src), "features": [], "upper_matched": [],
            "upper_missing": upper_names, "message": msg, "index": {}}


def load_boundaries(path: Path, upper_names: list[str], name_field: str, name_ar_field: str,
                    simplify_deg: float) -> dict:
    """Returns {"available", "source", "features", "upper_matched", "upper_missing", "message", "index"}.
    `index` maps every normalised spelling of a governorate to its display name."""
    f, why = find_file(path)
    if f is None:
        return _fail(path, upper_names, why)
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return _fail(f, upper_names, f"Could not read {f.name}: {exc}")
    raw = data.get("features", [])
    if len(raw) > MAX_GOVERNORATES:
        return _fail(f, upper_names, f"{f.name} has {len(raw)} polygons - that looks like a district-level file, not "
                                     f"governorates (Egypt has 27). Point paths.governorates at the governorates file.")

    upper_keys: dict[str, set[str]] = {n: _name_keys(n) for n in upper_names}
    matched: set[str] = set()
    feats, index = [], {}
    for ft in raw:
        props = ft.get("properties") or {}
        name = props.get(name_field) or props.get("adm1_ref_name") or ""
        name_ar = props.get(name_ar_field) or ""
        geom = _geometry(ft.get("geometry"), simplify_deg)
        if not geom or not (name or name_ar):
            continue
        mine = _name_keys(name) | _name_keys(name_ar)
        disp = name or name_ar
        for k in mine:
            index[k] = disp
        upper = False
        for cfg_name, keys in upper_keys.items():
            if keys & mine or _norm(props.get("adm1_pcode")) == _norm(cfg_name):
                upper, _ = True, matched.add(cfg_name)
                break
        feats.append({"type": "Feature",
                      "properties": {"name": disp, "name_ar": name_ar, "pcode": props.get("adm1_pcode"), "upper": upper},
                      "geometry": geom})
    missing = [n for n in upper_names if n not in matched]
    return {"available": bool(feats), "source": str(f), "features": feats, "index": index,
            "upper_matched": sorted(matched), "upper_missing": missing,
            "message": "" if feats else f"No usable governorate polygons in {f.name}"}


def canonical_name(index: dict, name) -> str | None:
    """Display name of the boundary that matches `name` (any spelling), else None."""
    for k in _name_keys(name):
        if k in index:
            return index[k]
    return None
