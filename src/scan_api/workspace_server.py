"""Local, account-scoped Atlas project API, served through the same-origin web proxy."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException

from scan_api.workspace import SESSION_SECONDS, Workspace, WorkspaceError, canonical_url
from scan_api.workspace_worker import WorkspaceWorker, build_graph

_COOKIE = "atlas_session"


async def json_mutation(request: Request) -> dict:
    origin = request.headers.get("origin")
    if ((origin is not None and origin != str(request.base_url).rstrip("/"))
            or request.headers.get("sec-fetch-site") == "cross-site"):
        raise WorkspaceError(403, "This request must come from the Atlas workspace.")
    if request.headers.get("content-type", "").partition(";")[0].strip().lower() != "application/json":
        raise WorkspaceError(415, "Send the request as application/json.")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 8192:
            raise WorkspaceError(413, "Request body is too large.")
        raw.extend(chunk)
    try:
        body = json.loads(raw)
    except (ValueError, RecursionError):
        raise WorkspaceError(400, "Send a valid JSON object.") from None
    if not isinstance(body, dict):
        raise WorkspaceError(400, "Send a JSON object.")
    return body


def create_app(root: Path | None = None, *, build=build_graph) -> FastAPI:
    store = Workspace(root or Path(os.environ.get("ATLAS_WORKSPACE_DIR", "~/.local/share/code-atlas/workspace")))
    worker = WorkspaceWorker(store, build)

    @asynccontextmanager
    async def lifespan(_app):
        store.initialize()
        worker.start()
        try:
            yield
        finally:
            worker.close()

    app = FastAPI(title="Atlas Workspace", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.router.redirect_slashes = False

    @app.middleware("http")
    async def private_response(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(WorkspaceError)
    async def workspace_error(_request, exc):
        return JSONResponse({"error": str(exc)}, status_code=exc.status)

    @app.exception_handler(HTTPException)
    async def http_error(_request, exc):
        return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)

    def owner(request: Request) -> str:
        user = store.user(request.cookies.get(_COOKIE))
        if user is None:
            raise WorkspaceError(401, "Sign in to open your workspace.")
        return user["id"]

    def authenticate(request: Request, payload: dict, register: bool):
        user, token = store.authenticate(payload, register=register)
        response = JSONResponse({"user": user})
        response.set_cookie(
            _COOKIE, token, max_age=SESSION_SECONDS, httponly=True, samesite="lax",
            secure=request.url.scheme == "https",
        )
        return response

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/session")
    def session(request: Request):
        return {"user": store.user(request.cookies.get(_COOKIE))}

    @app.post("/auth/register")
    def register(request: Request, payload: dict = Depends(json_mutation)):
        return authenticate(request, payload, register=True)

    @app.post("/auth/login")
    def login(request: Request, payload: dict = Depends(json_mutation)):
        return authenticate(request, payload, register=False)

    @app.post("/auth/logout")
    def logout(request: Request, _user: str = Depends(owner), _payload: dict = Depends(json_mutation)):
        store.logout(request.cookies[_COOKIE])
        response = JSONResponse({"user": None})
        response.delete_cookie(_COOKIE)
        return response

    @app.get("/projects")
    def projects(user: str = Depends(owner)):
        return {"projects": store.projects(user)}

    @app.post("/projects")
    def create_project(user: str = Depends(owner), payload: dict = Depends(json_mutation)):
        if set(payload) != {"repositoryUrl"}:
            raise WorkspaceError(400, "Send a repositoryUrl to create a project.")
        project = store.create(user, canonical_url(payload["repositoryUrl"]))
        worker.wake.set()
        return {"project": project}

    @app.get("/projects/{project_id}")
    def project(project_id: str, user: str = Depends(owner)):
        return {"project": store.project(user, project_id)}

    @app.post("/projects/{project_id}/retry")
    def retry_project(project_id: str, user: str = Depends(owner), _payload: dict = Depends(json_mutation)):
        project = store.retry(user, project_id)
        worker.wake.set()
        return {"project": project}

    @app.get("/projects/{project_id}/graph")
    def graph(project_id: str, user: str = Depends(owner)):
        return Response(store.artifact(user, project_id, files=False), media_type="application/json")

    @app.get("/projects/{project_id}/files")
    def files(project_id: str, user: str = Depends(owner)):
        return Response(store.artifact(user, project_id, files=True), media_type="application/json")

    return app


app = create_app()
