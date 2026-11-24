"""Express and Rails fixtures.

Each fixture is a few files. One route loads Item by id with no owner check.
The other filters Item by the current user. Assertions are inPredicate, auth
kind, and bindsObjectToCaller.

Joern's jssrc2cpg and rubysrc2cpg are used when they are installed. When a
frontend is missing, the test writes an overlay in the same shape as
export_overlay.sc and passes it to export_repository, which is the path the
FastAPI mini-slice uses.
"""

import json
from pathlib import Path

from scanner.detect import select_adapter
from scanner.joern_runner import frontend_available
from scanner.ownership import predicate_from_call
from scanner.scan import export_repository
from scanner.validate import validate_document

SCHEMA = Path(__file__).resolve().parents[1] / "docs" / "code-graph-schema.json"

EXPRESS_PACKAGE = '{ "name": "items", "dependencies": { "express": "^4.18.0" } }\n'
EXPRESS_APP = """const express = require("express");
const app = express();

function currentUser(req, res, next) {
  req.user = { id: req.header("authorization") };
  next();
}

app.use(currentUser);

app.get("/items/:id", function getItem(req, res) {
  const item = Item.findOne({ id: req.params.id });
  res.json(item);
});

app.get("/items", function listMine(req, res) {
  const items = Item.find({ ownerId: req.user.id });
  res.json(items);
});

app.ws("/live", function live(socket) {
  socket.send("ok");
});

module.exports = app;
"""

RAILS_GEMFILE = 'source "https://rubygems.org"\ngem "rails", "~> 7.1"\n'
RAILS_ROUTES = """Rails.application.routes.draw do
  get "/items/:id", to: "items#show"
  get "/items", to: "items#index"
end
"""
RAILS_CONTROLLER = """class ItemsController < ApplicationController
  before_action :current_user

  def show
    @item = Item.find_by(id: params[:id])
    render json: @item
  end

  def index
    @items = Item.where(owner_id: current_user.id)
    render json: @items
  end

  def current_user
    @current_user ||= User.find_by(token: request.headers["Authorization"])
  end
end
"""
RAILS_MODEL = """class Item < ApplicationRecord
end
"""


def test_owner_call_is_yes_and_hidden_call_is_unknown():
    decision, owners, idents = predicate_from_call(
        "Item.find({ ownerId: req.user.id })", "find", "Item"
    )
    assert decision == "yes"
    assert owners == ["Item.ownerId"]
    assert idents == ["user"]
    decision, owners, idents = predicate_from_call(
        "(<tmp-0> = Item).where(owner_id: current_user.id)", "where", "Item"
    )
    assert decision == "yes"
    assert owners == ["Item.owner_id"]
    assert idents == ["current_user"]
    assert predicate_from_call("Item.findOne({ id: req.params.id })", "findOne", "Item")[0] == "no"
    assert predicate_from_call("(<tmp-0> = Item).find_by(id: params[:id])", "find_by", "Item")[0] == "no"
    assert predicate_from_call("Item.find(query)", "find", "Item")[0] == "unknown"
    assert predicate_from_call("(<tmp-0> = Item).where(scope)", "where", "Item")[0] == "unknown"
    assert predicate_from_call("", "find", "Item")[0] == "unknown"


def test_one_adapter_is_selected(tmp_path: Path):
    express = tmp_path / "express"
    _write_express(express)
    assert select_adapter(express).framework == "express"

    rails = tmp_path / "rails"
    _write_rails(rails)
    assert select_adapter(rails).framework == "rails"

    both = tmp_path / "both"
    _write_rails(both)
    (both / "package.json").write_text(EXPRESS_PACKAGE, encoding="utf-8")
    (both / "app.js").write_text(EXPRESS_APP, encoding="utf-8")
    assert select_adapter(both).framework == "rails"

    python_repo = tmp_path / "python"
    python_repo.mkdir()
    (python_repo / "app.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    assert select_adapter(python_repo).framework == "fastapi"


def test_express_id_load_and_owner_filter(tmp_path: Path):
    repo = tmp_path / "express"
    _write_express(repo)
    document = _scan(repo, "javascript", _express_overlay)
    _assert_pair(document, "express")


def test_rails_id_load_and_owner_filter(tmp_path: Path):
    repo = tmp_path / "rails"
    _write_rails(repo)
    document = _scan(repo, "ruby", _rails_overlay)
    _assert_pair(document, "rails")


def test_express_overlay_fallback(tmp_path: Path):
    """The overlay path used when jssrc2cpg is not installed."""
    repo = tmp_path / "express"
    _write_express(repo)
    _express_overlay(repo)
    document = export_repository(repo, overlay_path=repo / "overlay.json")
    _assert_pair(document, "express")


def test_rails_overlay_fallback(tmp_path: Path):
    """The overlay path used when rubysrc2cpg is not installed."""
    repo = tmp_path / "rails"
    _write_rails(repo)
    _rails_overlay(repo)
    document = export_repository(repo, overlay_path=repo / "overlay.json")
    _assert_pair(document, "rails")


def _scan(repo: Path, frontend: str, overlay) -> dict:
    if frontend_available(frontend):
        return export_repository(repo)
    overlay(repo)
    return export_repository(repo, overlay_path=repo / "overlay.json")


def _assert_pair(document: dict, framework: str) -> None:
    errors = validate_document(document, SCHEMA)
    assert errors == [], "\n".join(errors[:30])
    assert document["schemaVersion"] == "1.0.0"
    assert document["frameworks"] == [framework]
    assert {gap["kind"] for gap in document["unresolvedGaps"]} >= {"graphql", "websocket", "dynamic_dispatch"}
    routes = {(route["httpMethod"], route["pathTemplate"]): route for route in document["routes"]}
    assert set(routes) == {("GET", "/items/{id}"), ("GET", "/items")}
    by_id = routes[("GET", "/items/{id}")]
    owned = routes[("GET", "/items")]
    assert _item_predicates(by_id) == ["no"]
    assert _item_predicates(owned) == ["yes"]
    assert _auth(by_id) == [("authentication", "no")]
    assert _auth(owned) == [("authentication", "no")]


def _item_predicates(route: dict) -> list[str]:
    return [
        access["ownershipEvidence"]["inPredicate"]
        for access in route["dataAccesses"]
        if access["object"]["name"] == "Item"
    ]


def _auth(route: dict) -> list[tuple[str, str]]:
    return [(step["kind"], step["bindsObjectToCaller"]) for step in route["authChain"]]


def _write_express(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "package.json").write_text(EXPRESS_PACKAGE, encoding="utf-8")
    (repo / "app.js").write_text(EXPRESS_APP, encoding="utf-8")


def _write_rails(repo: Path) -> None:
    (repo / "config").mkdir(parents=True, exist_ok=True)
    (repo / "app" / "controllers").mkdir(parents=True, exist_ok=True)
    (repo / "app" / "models").mkdir(parents=True, exist_ok=True)
    (repo / "Gemfile").write_text(RAILS_GEMFILE, encoding="utf-8")
    (repo / "config" / "routes.rb").write_text(RAILS_ROUTES, encoding="utf-8")
    (repo / "app" / "controllers" / "items_controller.rb").write_text(RAILS_CONTROLLER, encoding="utf-8")
    (repo / "app" / "models" / "item.rb").write_text(RAILS_MODEL, encoding="utf-8")


def _line(text: str, snippet: str) -> int:
    for number, line in enumerate(text.splitlines(), start=1):
        if snippet in line:
            return number
    raise AssertionError(snippet)


def _express_overlay(repo: Path) -> None:
    app = EXPRESS_APP
    get_item = _line(app, "function getItem")
    list_mine = _line(app, "function listMine")
    current = _line(app, "function currentUser")
    live = _line(app, "function live")
    methods = [
        _method("currentUser", "app.js::program:currentUser", "app.js", current, _line(app, "next();") + 1),
        _method(":program", "app.js::program", "app.js", 1, len(app.splitlines())),
        _method("getItem", "app.js::program:getItem", "app.js", get_item, _line(app, "res.json(item);") + 1),
        _method("listMine", "app.js::program:listMine", "app.js", list_mine, _line(app, "res.json(items);") + 1),
        _method("live", "app.js::program:live", "app.js", live, _line(app, 'socket.send("ok");') + 1),
    ]
    calls = [
        _call("header", "<unknownFullName>", 'req.header("authorization")', "app.js", _line(app, "req.header"), "app.js::program:currentUser"),
        _call("next", "app.js::program:next", "next()", "app.js", _line(app, "next();"), "app.js::program:currentUser"),
        _call("use", "express:<returnValue>:use", "app.use(currentUser)", "app.js", _line(app, "app.use"), "app.js::program"),
        _call(
            "get",
            "express:<returnValue>:get",
            'app.get("/items/:id", function getItem(req, res) { const item = Item.findOne({ id: req.params.id }); res.json(item); })',
            "app.js",
            get_item,
            "app.js::program",
        ),
        _call(
            "findOne",
            "<unknownFullName>",
            "Item.findOne({ id: req.params.id })",
            "app.js",
            _line(app, "Item.findOne"),
            "app.js::program:getItem",
        ),
        _call("json", "<unknownFullName>", "res.json(item)", "app.js", _line(app, "res.json(item)"), "app.js::program:getItem"),
        _call(
            "get",
            "express:<returnValue>:get",
            'app.get("/items", function listMine(req, res) { const items = Item.find({ ownerId: req.user.id }); res.json(items); })',
            "app.js",
            list_mine,
            "app.js::program",
        ),
        _call(
            "find",
            "<unknownFullName>",
            "Item.find({ ownerId: req.user.id })",
            "app.js",
            _line(app, "Item.find({"),
            "app.js::program:listMine",
        ),
        _call("json", "<unknownFullName>", "res.json(items)", "app.js", _line(app, "res.json(items)"), "app.js::program:listMine"),
        _call(
            "ws",
            "express:<returnValue>:ws",
            'app.ws("/live", function live(socket) { socket.send("ok"); })',
            "app.js",
            live,
            "app.js::program",
        ),
    ]
    (repo / "overlay.json").write_text(json.dumps({"methods": methods, "calls": calls}), encoding="utf-8")


def _rails_overlay(repo: Path) -> None:
    controller = RAILS_CONTROLLER
    routes = RAILS_ROUTES
    file = "app/controllers/items_controller.rb"
    show = _line(controller, "def show")
    index = _line(controller, "def index")
    current = _line(controller, "def current_user")
    methods = [
        _method("show", f"{file}:<main>.ItemsController.show", file, show, _line(controller, "render json: @item") + 1),
        _method("index", f"{file}:<main>.ItemsController.index", file, index, _line(controller, "render json: @items") + 1),
        _method(
            "current_user",
            f"{file}:<main>.ItemsController.current_user",
            file,
            current,
            _line(controller, "User.find_by") + 1,
        ),
    ]
    calls = [
        _call("before_action", "<unknownFullName>", "before_action :current_user", file, _line(controller, "before_action"), f"{file}:<main>.ItemsController.<body>"),
        _call("find_by", "<unknownFullName>", "(<tmp-0> = Item).find_by(id: params[:id])", file, _line(controller, "Item.find_by"), f"{file}:<main>.ItemsController.show"),
        _call("render", "<unknownFullName>", "render json: @item", file, _line(controller, "render json: @item"), f"{file}:<main>.ItemsController.show"),
        _call("where", "<unknownFullName>", "(<tmp-0> = Item).where(owner_id: current_user.id)", file, _line(controller, "Item.where"), f"{file}:<main>.ItemsController.index"),
        _call("current_user", "<unknownFullName>", "current_user", file, _line(controller, "current_user.id"), f"{file}:<main>.ItemsController.index"),
        _call("render", "<unknownFullName>", "render json: @items", file, _line(controller, "render json: @items"), f"{file}:<main>.ItemsController.index"),
        _call(
            "find_by",
            "<unknownFullName>",
            '(<tmp-0> = User).find_by(token: request.headers["Authorization"])',
            file,
            _line(controller, "User.find_by"),
            f"{file}:<main>.ItemsController.current_user",
        ),
        _call("get", "<unknownFullName>", 'get "/items/:id", to: "items#show"', "config/routes.rb", _line(routes, "items#show"), "config/routes.rb:<main>.<lambda>0"),
        _call("get", "<unknownFullName>", 'get "/items", to: "items#index"', "config/routes.rb", _line(routes, "items#index"), "config/routes.rb:<main>.<lambda>0"),
    ]
    (repo / "overlay.json").write_text(json.dumps({"methods": methods, "calls": calls}), encoding="utf-8")


def _method(name: str, full: str, file: str, line: int, end: int) -> dict:
    return {"name": name, "fullName": full, "file": file, "line": line, "endLine": end}


def _call(name: str, full: str, code: str, file: str, line: int, caller: str) -> dict:
    return {
        "name": name,
        "methodFullName": full,
        "code": code,
        "file": file,
        "line": line,
        "caller": caller,
        "dispatch": "DYNAMIC_DISPATCH",
    }


NESTED_ROUTES = """\
Rails.application.routes.draw do
  namespace :api do
    namespace :v1 do
      resources :accounts, only: [:show] do
        scope module: :accounts do
          resources :macros, only: [:create, :update]
          namespace :channels do
            resource :twilio_channel, only: [:create]
          end
        end
      end
    end
  end
  if Rails.env.development?
    get "/debug", to: "debug#show"
  end
  resources :agents, only: [:index] do
    member do
      post :run
    end
    collection do
      post :propagate
    end
  end
end
"""


def _nested_declarations(code: str, name: str):
    from types import SimpleNamespace

    from scanner.rails.routes import _declarations

    controllers = {
        "app/controllers/api/v1/accounts_controller.rb": "class Api::V1::AccountsController\nend\n",
        "app/controllers/api/v1/accounts/macros_controller.rb": "class Api::V1::Accounts::MacrosController\nend\n",
        "app/controllers/api/v1/accounts/channels/twilio_channels_controller.rb": "class TwilioChannelsController\nend\n",
        "app/controllers/agents_controller.rb": "class AgentsController\nend\n",
        "app/controllers/debug_controller.rb": "class DebugController\nend\n",
    }
    index = SimpleNamespace(files={"config/routes.rb": NESTED_ROUTES, **controllers})
    line = next(number for number, text in enumerate(NESTED_ROUTES.splitlines(), 1) if code in text)
    call = SimpleNamespace(name=name, code=code, file="config/routes.rb", line=line)
    return [(method, path, located) for method, path, _mechanism, _action, located, _cls in _declarations(call, index)]


def test_nested_resources_take_the_namespace_path_and_module():
    assert _nested_declarations("resources :macros, only: [:create, :update]", "resources") == [
        ("POST", "/api/v1/accounts/{account_id}/macros", "app/controllers/api/v1/accounts/macros_controller.rb"),
        ("PATCH", "/api/v1/accounts/{account_id}/macros/{id}", "app/controllers/api/v1/accounts/macros_controller.rb"),
        ("PUT", "/api/v1/accounts/{account_id}/macros/{id}", "app/controllers/api/v1/accounts/macros_controller.rb"),
    ]


def test_singular_resource_routes_to_the_plural_controller():
    assert _nested_declarations("resource :twilio_channel, only: [:create]", "resource") == [
        (
            "POST",
            "/api/v1/accounts/{account_id}/channels/twilio_channel",
            "app/controllers/api/v1/accounts/channels/twilio_channels_controller.rb",
        )
    ]


def test_member_and_collection_routes_and_plain_blocks():
    assert _nested_declarations("post :run", "post") == [("POST", "/agents/{id}/run", "app/controllers/agents_controller.rb")]
    assert _nested_declarations("post :propagate", "post") == [
        ("POST", "/agents/propagate", "app/controllers/agents_controller.rb")
    ]
    assert _nested_declarations('get "/debug", to: "debug#show"', "get") == [
        ("GET", "/debug", "app/controllers/debug_controller.rb")
    ]


def test_block_calls_join_their_method_but_not_main():
    from scanner.overlay import CallRec, Overlay

    def call(name, caller, line):
        return CallRec(name, "", name, "app.rb", line, caller, "STATIC_DISPATCH", 1)

    method = "app.rb:<main>.ItemsController.update"
    overlay = Overlay(
        [],
        [
            call("transaction", method, 2),
            call("update!", method + ".<lambda>0", 3),
            call("render", method + ".<lambda>0.<lambda>1", 4),
            call("route_a", "app.rb:<main>", 1),
            call("inside_a", "app.rb:<main>.<lambda>0", 5),
        ],
    )
    assert [c.name for c in overlay.calls_with_blocks(method)] == ["transaction", "update!", "render"]
    assert [c.name for c in overlay.calls_with_blocks("app.rb:<main>")] == ["route_a"]
