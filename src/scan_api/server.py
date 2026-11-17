"""FastAPI service for scan jobs. The Atlas frontend reaches it through a dev proxy."""

from __future__ import annotations

import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from scan_api.service import ScanService
from scan_api.store import Store

_MAX_BODY = 65_536
_SCAN_ID = re.compile(r"^scan_[0-9a-f]{32}$")


def create_app(service: ScanService | None = None) -> FastAPI:
    """Build the scan API. A passed-in service is not started; the process service is."""
    owns_worker = service is None
    scans = service if service is not None else _default_service()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if owns_worker:
            scans.start()
        yield

    app = FastAPI(title="code-atlas-scan", lifespan=lifespan)
    app.state.scans = scans

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/")
    def root() -> dict:
        return {
            "service": "code-atlas-scan",
            "endpoints": [
                "GET /review",
                "GET /scans",
                "POST /scans",
                "GET /scans/{id}",
                "GET /scans/{id}/summary",
                "GET /scans/{id}/files",
                "GET /scans/{id}/graph",
            ],
        }

    @app.get("/review")
    def review() -> JSONResponse:
        return _json(*scans.review_status())

    @app.get("/scans")
    def list_scans() -> JSONResponse:
        return _json(*scans.list())

    @app.post("/scans")
    async def create_scan(request: Request) -> JSONResponse:
        length = request.headers.get("content-length")
        if length is None or not length.isdigit():
            return _json(400, {"error": "Content-Length is required. The scan was not started."})
        if int(length) > _MAX_BODY:
            return _json(413, {"error": "Request body is too large. The scan was not started."})
        try:
            payload = json.loads((await request.body()).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _json(400, {"error": "Request body must be JSON. The scan was not started."})
        return _json(*scans.create(payload))

    @app.get("/scans/{scan_id}")
    def get_scan(scan_id: str) -> JSONResponse:
        if _SCAN_ID.fullmatch(scan_id) is None:
            return _json(404, {"error": "Not found."})
        return _json(*scans.get(scan_id))

    @app.get("/scans/{scan_id}/summary")
    def get_summary(scan_id: str) -> JSONResponse:
        if _SCAN_ID.fullmatch(scan_id) is None:
            return _json(404, {"error": "Not found."})
        return _json(*scans.summary(scan_id))

    @app.get("/scans/{scan_id}/files")
    def get_files(scan_id: str) -> JSONResponse:
        if _SCAN_ID.fullmatch(scan_id) is None:
            return _json(404, {"error": "Not found."})
        return _json(*scans.files(scan_id))

    @app.get("/scans/{scan_id}/graph")
    def get_graph(scan_id: str) -> JSONResponse:
        if _SCAN_ID.fullmatch(scan_id) is None:
            return _json(404, {"error": "Not found."})
        return _json(*scans.graph(scan_id))

    return app


def _default_service() -> ScanService:
    root = Path(os.environ.get("SCAN_DATA_DIR", "data/scans"))
    return ScanService(Store(root))


def _json(status: int, payload: dict) -> JSONResponse:
    return JSONResponse(status_code=status, content=payload)


app = create_app()
