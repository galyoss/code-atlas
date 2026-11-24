"""Read-only graph tools for review agents. They read the exported graph only.

Every tool returns compact JSON. A wrong id comes back as an error message the
agent can act on, not an exception.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from langchain_core.tools import BaseTool, StructuredTool

from review.graph_index import GraphError, GraphIndex

_LIMIT = 24_000


def graph_tools(index: GraphIndex) -> list[BaseTool]:
    def repo_map() -> str:
        """Level 0. The repository map: frameworks, route groups, objects routes load or change, and scanner gaps."""
        return _run(index.overview)

    def list_routes(path_prefix: str = "", object_name: str = "", method: str = "", offset: int = 0) -> str:
        """Level 1. One line per route: id, method and path, auth kinds, data accesses with inPredicate, coverage.
        Filter by path prefix, object name (as in repo_map) or HTTP method; page with offset."""
        return _run(lambda: index.route_lines(path_prefix, object_name, method, offset))

    def route_summary(route_id: str) -> str:
        """Level 2. One route without code: parameters, identity bindings, auth steps, data accesses with
        ownership evidence and the names on their call path, coverage, and related routes."""
        return _run(lambda: index.route_summary(route_id))

    def data_access(route_id: str, access_id: str) -> str:
        """Level 3. One data access: its source snippet (the query and the lines after it), ownership evidence,
        parameter flows, the recorded call path from the handler with call sites, and the object's symbol."""
        return _run(lambda: index.access_detail(route_id, access_id))

    def auth_step(route_id: str, auth_step_id: str) -> str:
        """Level 3. One auth step: its snippet, whether it binds the object to the caller, and the calls it makes."""
        return _run(lambda: index.auth_detail(route_id, auth_step_id))

    def call_tree(route_id: str, call_id: str = "", depth: int = 2) -> str:
        """Level 3. The recorded call tree of a route, or the subtree under call_id, to the given depth (1-4),
        with call sites, resolution and argument excerpts."""
        return _run(lambda: index.call_tree(route_id, call_id, depth))

    def symbol(symbol_id: str) -> str:
        """Level 3. A symbol-index entry: kind, qualified name, signature and source range."""
        return _run(lambda: index.symbol(symbol_id))

    def routes_touching(object_name: str, operation: str = "") -> str:
        """Every data access on one object across all routes, with its ownership evidence, to compare how
        other routes treat the same object (optionally one operation: load, create, update, delete)."""
        return _run(lambda: index.routes_touching(object_name, operation))

    functions = [repo_map, list_routes, route_summary, data_access, auth_step, call_tree, symbol, routes_touching]
    return [StructuredTool.from_function(func) for func in functions]


def _run(build: Callable[[], object]) -> str:
    try:
        text = json.dumps(build(), ensure_ascii=False)
    except GraphError as exc:
        return json.dumps({"error": str(exc)})
    if len(text) > _LIMIT:
        return text[:_LIMIT] + '... [truncated: ask for a narrower view]'
    return text
