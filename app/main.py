"""FastAPI app: JSON API + static front end."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import PROJECT_ROOT, load_settings
from .egypt import EGYPT_POLYGON, LAT_MAX, LAT_MIN, LON_MAX, LON_MIN
from .facilities import FacilityError
from .manager import GraphManager
from .search_service import ApiError, SearchService

FRONTEND_DIR = PROJECT_ROOT / "frontend"


class SearchRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(..., ge=-180, le=180, allow_inf_nan=False)
    more: bool = False          # True = "Show more hospitals": returns only the extra ones


class NoCacheStatic(StaticFiles):
    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        if path in ("", ".", "index.html") or path.endswith((".js", ".css")) and "vendor" not in path:
            resp.headers["Cache-Control"] = "no-cache"
        return resp


def create_app(config_path: str | Path | None = None) -> FastAPI:
    settings = load_settings(config_path)
    manager = GraphManager(settings)
    service = SearchService(settings, manager)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        manager.start()
        yield

    app = FastAPI(title="Hospital Finder", version="1.0", lifespan=lifespan)
    app.state.settings, app.state.manager, app.state.service = settings, manager, service

    # ------------------------------------------------------------ errors
    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status,
                            content={"error": {"code": exc.code, "message": exc.message, **exc.extra}})

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": {
            "code": "invalid_input",
            "message": "Latitude must be a number between -90 and 90 and longitude between -180 and 180."}})

    # --------------------------------------------------------------- API
    @app.get("/api/config")
    def get_config():
        s = settings
        return {
            "egypt_polygon": [[lon, lat] for lon, lat in EGYPT_POLYGON],
            "egypt_bounds": [[LAT_MIN, LON_MIN], [LAT_MAX, LON_MAX]],
            "map": s.map,
            "search": {"results": s.search.get("results", 5),
                       "more_results": s.search.get("more_results", 5),
                       "eta_warn_minutes": s.search.get("eta_warn_minutes", 60)},
        }

    @app.get("/api/status")
    def get_status():
        manager.check_sources()
        return manager.status()

    @app.get("/api/facilities")
    def get_facilities():
        manager.check_sources()
        graph = manager.graph
        if manager.state != "ready" or graph is None:
            raise ApiError(503, "not_ready", "The road graph is not ready yet.")
        try:
            idx = manager.facilities.get(graph)
        except FacilityError as exc:
            raise ApiError(503, "facilities_unavailable", str(exc)) from exc
        return {"facilities": [{"id": r["id"], "name": r["name"], "lat": r["lat"], "lon": r["lon"],
                                "tier_label": r["tier_label"], "governorate": r["governorate"]}
                               for r in idx.rows],
                "stats": idx.stats}

    @app.post("/api/search")
    async def post_search(req: SearchRequest):
        return await service.search(req.lat, req.lon, req.more)

    @app.get("/api/baseline/{job_id}")
    def get_baseline(job_id: str):
        return service.baseline_status(job_id)

    @app.post("/api/admin/rebuild")
    def admin_rebuild(request: Request):
        if settings.server.get("admin_localhost_only", True):
            host = request.client.host if request.client else ""
            if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
                raise ApiError(403, "forbidden", "Rebuild is only allowed from the computer running the app.")
        started = manager.rebuild()
        return {"started": started, "state": manager.state}

    @app.get("/health")
    def health():
        return {"ok": True, "state": manager.state}

    # ------------------------------------------------------------ front end
    if FRONTEND_DIR.exists():
        app.mount("/", NoCacheStatic(directory=str(FRONTEND_DIR), html=True), name="frontend")
    return app


app = create_app()
