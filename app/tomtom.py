"""TomTom integration: live-traffic routing (server side, the key never reaches the browser).

Keys are read from environment variables or from a file called `.env` in the project folder:
    TOMTOM_KEY=...        used for routing (kept on the server)
    TOMTOM_MAP_KEY=...    optional, used by the browser for map tiles / traffic overlay.
                          If missing, TOMTOM_KEY is used for the tiles too.
"""
from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .config import PROJECT_ROOT

ROUTING_URL = "https://api.tomtom.com/routing/1/calculateRoute"


class TomTomError(Exception):
    pass


def _load_dotenv() -> None:
    path = PROJECT_ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def routing_key() -> str | None:
    return os.environ.get("TOMTOM_KEY") or None


def map_key() -> str | None:
    return os.environ.get("TOMTOM_MAP_KEY") or os.environ.get("TOMTOM_KEY") or None


def _fetch(url: str, timeout: float) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise TomTomError("TomTom rejected the key (check TOMTOM_KEY and that Routing is enabled for it).") from exc
        if exc.code == 429:
            raise TomTomError("TomTom daily limit reached.") from exc
        raise TomTomError(f"TomTom error {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TomTomError("Could not reach TomTom (no internet?).") from exc


def parse_route(payload: dict, max_points: int = 4000) -> dict:
    routes = payload.get("routes") or []
    if not routes:
        raise TomTomError("TomTom found no route.")
    r = routes[0]
    s = r["summary"]
    pts = [[p["latitude"], p["longitude"]] for leg in r.get("legs", []) for p in leg.get("points", [])]
    if len(pts) > max_points:                       # thin the line for the browser
        step = len(pts) / max_points
        pts = [pts[int(i * step)] for i in range(max_points - 1)] + [pts[-1]]
    travel = int(s["travelTimeInSeconds"])
    delay = int(s.get("trafficDelayInSeconds", 0))
    return {
        "distance_km": round(s["lengthInMeters"] / 1000.0, 2),
        "eta_seconds": travel,
        "traffic_delay_seconds": delay,
        "no_traffic_seconds": int(s.get("noTrafficTravelTimeInSeconds", travel - delay)),
        "route": pts,
    }


async def live_route(lat1: float, lon1: float, lat2: float, lon2: float, timeout: float = 8.0) -> dict:
    key = routing_key()
    if not key:
        raise TomTomError("No TomTom key found. Put TOMTOM_KEY in the .env file.")
    q = urllib.parse.urlencode({"key": key, "traffic": "true", "travelMode": "car",
                                "routeType": "fastest", "computeTravelTimeFor": "all"})
    url = f"{ROUTING_URL}/{lat1:.6f},{lon1:.6f}:{lat2:.6f},{lon2:.6f}/json?{q}"
    payload = await asyncio.to_thread(_fetch, url, timeout)
    return parse_route(payload)
