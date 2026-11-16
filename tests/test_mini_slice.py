"""A hand-built overlay proves the schema writer and the three-field check.

Joern is not required. The overlay is the same shape export_overlay.sc writes.
"""

import json
from pathlib import Path

from export_fastapi.check_fields import access_predicates, auth_observations
from export_fastapi.cli import export_repository
from export_fastapi.facts import Limits
from export_fastapi.validate import validate_document

SCHEMA = Path(__file__).resolve().parents[1] / "docs" / "code-graph-schema.json"

APP = '''from fastapi import APIRouter, Depends
from models import Item

router = APIRouter(prefix="/v1")

def get_current_user():
    return None

@router.get("/items/{item_id}")
def get_item(item_id: str, user = Depends(get_current_user)):
    stmt = select(Item).where(Item.item_id == item_id, Item.user_id == user.identity)
    return session.scalar(stmt)

@router.post("/items")
def create_item(user = Depends(get_current_user)):
    stmt = select(Item).where(Item.item_id == item_id)
    row = session.scalar(stmt)
    if row and row.user_id != user.identity:
        raise HTTPException(status_code=404)
    return row
'''

MAIN = '''from fastapi import FastAPI
from app import router as items_router

app = FastAPI()
app.include_router(items_router, prefix="/api")
'''

MODELS = '''class Item:
    __tablename__ = "items"
    item_id: str
    user_id: str
'''


def _line(text: str, snippet: str) -> int:
    for number, line in enumerate(text.splitlines(), start=1):
        if snippet in line:
            return number
    raise AssertionError(snippet)


def _end(text: str, name: str) -> int:
    lines = text.splitlines()
    start = _line(text, f"def {name}")
    end = start
    for number, line in enumerate(lines[start:], start=start + 1):
        if line.startswith("def ") or line.startswith("@") or line.startswith("class "):
            break
        if line.strip():
            end = number
    return end


def _overlay(repo: Path) -> None:
    app = (repo / "app.py").read_text()
    main = (repo / "main.py").read_text()
    get_line = _line(app, "def get_item")
    post_line = _line(app, "def create_item")
    user_line = _line(app, "def get_current_user")
    methods = [
        _method("<module>", "app.py:<module>", "app.py", 1, 1),
        _method("get_current_user", "app.py:<module>.get_current_user", "app.py", user_line, _end(app, "get_current_user")),
        _method("get_item", "app.py:<module>.get_item", "app.py", get_line, _end(app, "get_item")),
        _method("create_item", "app.py:<module>.create_item", "app.py", post_line, _end(app, "create_item")),
        _method("<module>", "main.py:<module>", "main.py", 1, len(main.splitlines())),
    ]
    calls = [
        _call("APIRouter", "fastapi.APIRouter", 'APIRouter(prefix = "/v1")', "app.py", _line(app, "APIRouter"), "app.py:<module>"),
        _call("<operator>.assignment", "<operator>.assignment", 'router = APIRouter(prefix = "/v1")', "app.py", _line(app, "APIRouter"), "app.py:<module>"),
        _call("get", "fastapi.APIRouter.get", 'router.get("/items/{item_id}")', "app.py", _line(app, '@router.get'), "app.py:<module>"),
        _call("post", "fastapi.APIRouter.post", 'router.post("/items")', "app.py", _line(app, "@router.post"), "app.py:<module>"),
        _call("where", "sqlalchemy.Query.where", "select(Item).where(Item.item_id == item_id, Item.user_id == user.identity)", "app.py", _line(app, "Item.user_id == user.identity"), "app.py:<module>.get_item"),
        _call("<operator>.assignment", "<operator>.assignment", "stmt = select(Item).where(Item.item_id == item_id, Item.user_id == user.identity)", "app.py", _line(app, "Item.user_id == user.identity"), "app.py:<module>.get_item"),
        _call("scalar", "sqlalchemy.Session.scalar", "session.scalar(stmt)", "app.py", _line(app, "session.scalar(stmt)"), "app.py:<module>.get_item"),
        _call("where", "sqlalchemy.Query.where", "select(Item).where(Item.item_id == item_id)", "app.py", _line(app, "Item.item_id == item_id"), "app.py:<module>.create_item"),
        _call("<operator>.assignment", "<operator>.assignment", "stmt = select(Item).where(Item.item_id == item_id)", "app.py", _line(app, "Item.item_id == item_id"), "app.py:<module>.create_item"),
        _call("scalar", "sqlalchemy.Session.scalar", "session.scalar(stmt)", "app.py", _line(app, "row = session.scalar"), "app.py:<module>.create_item"),
        _call("<operator>.notEquals", "<operator>.notEquals", "row.user_id != user.identity", "app.py", _line(app, "row.user_id"), "app.py:<module>.create_item"),
        _call("<operator>.logicalAnd", "<operator>.logicalAnd", "row and row.user_id != user.identity", "app.py", _line(app, "row and row.user_id"), "app.py:<module>.create_item"),
        _call("HTTPException", "fastapi.HTTPException", "raise HTTPException(status_code=404)", "app.py", _line(app, "HTTPException"), "app.py:<module>.create_item"),
        _call("include_router", "fastapi.FastAPI.include_router", 'app.include_router(items_router, prefix = "/api")', "main.py", _line(main, "include_router"), "main.py:<module>"),
    ]
    payload = {"methods": methods, "calls": calls}
    (repo / "overlay.json").write_text(json.dumps(payload), encoding="utf-8")


def _method(name: str, full: str, file: str, line: int, end: int) -> dict:
    return {"name": name, "fullName": full, "file": str(file), "line": line, "endLine": end}


def _call(name: str, full: str, code: str, file: str, line: int, caller: str) -> dict:
    return {
        "name": name,
        "methodFullName": full,
        "code": code,
        "file": file,
        "line": line,
        "caller": caller,
        "dispatch": "STATIC_DISPATCH",
    }


def test_mini_slice_validates_and_keeps_the_three_fields(tmp_path: Path):
    (tmp_path / "app.py").write_text(APP, encoding="utf-8")
    (tmp_path / "main.py").write_text(MAIN, encoding="utf-8")
    (tmp_path / "models.py").write_text(MODELS, encoding="utf-8")
    _overlay(tmp_path)
    document = export_repository(tmp_path, overlay_path=tmp_path / "overlay.json", limits=Limits())
    errors = validate_document(document, SCHEMA)
    assert errors == []
    routes = {(route["httpMethod"], route["pathTemplate"]): route for route in document["routes"]}
    assert ("GET", "/api/v1/items/{item_id}") in routes
    assert ("POST", "/api/v1/items") in routes
    loaded = routes[("GET", "/api/v1/items/{item_id}")]
    created = routes[("POST", "/api/v1/items")]
    assert access_predicates(loaded, "Item", "load") == ["yes"]
    assert access_predicates(created, "Item", "load") == ["no"]
    assert {
        "kind": "authorization",
        "bindsObjectToCaller": "yes",
        "applicability": "conditional",
    } in auth_observations(created)
    assert any(
        step["kind"] == "authentication" and step["bindsObjectToCaller"] == "no"
        for step in auth_observations(loaded)
    )
    assert document["illustrative"] is False
    assert document["frameworks"] == ["fastapi"]
    assert {gap["kind"] for gap in document["unresolvedGaps"]} >= {"graphql", "websocket", "dynamic_dispatch", "other"}
