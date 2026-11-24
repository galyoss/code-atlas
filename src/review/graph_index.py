"""Multi-resolution views of one schema 1.0.0 code graph, for review agents.

Agents never see the repository; everything here reads the exported graph.

- Level 0, `overview`: the repository map — frameworks, route groups, the objects
  routes load or change, and the gaps the scanner does not model.
- Level 1, `route_lines`: one line per route.
- Level 2, `route_summary`: one route without code — parameters, identity, auth
  steps, data accesses with their ownership evidence and call path names.
- Level 3, `access_detail`, `auth_detail`, `call_tree`, `symbol`: the snippets,
  call sites and signatures behind one node.

`routes_touching` compares how every route treats the same object.
"""

from __future__ import annotations

from collections import Counter

from review.gate import call_path, coverage_is_partial, dicts, find_access

PAGE = 40
_CHILDREN_SHOWN = 25


class GraphError(LookupError):
    """A tool asked for an id the graph does not have."""


class GraphIndex:
    def __init__(self, document: dict) -> None:
        self.document = document if isinstance(document, dict) else {}
        self.routes = [
            route for route in dicts(self.document.get("routes")) if isinstance(route.get("id"), str) and route["id"]
        ]
        self.by_id = {route["id"]: route for route in self.routes}
        self.symbols = {
            entry["id"]: entry for entry in dicts(self.document.get("symbolIndex")) if isinstance(entry.get("id"), str)
        }

    def route(self, route_id: str) -> dict:
        route = self.by_id.get(route_id)
        if route is None:
            raise GraphError(f"No route {route_id!r}. Use list_routes to find route ids.")
        return route

    # Level 0

    def overview(self) -> dict:
        groups: Counter[str] = Counter()
        objects: dict[str, Counter[str]] = {}
        partial = 0
        for route in self.routes:
            groups[_group(route.get("pathTemplate", ""))] += 1
            partial += coverage_is_partial(route)
            for access in dicts(route.get("dataAccesses")):
                name = _object_name(access)
                objects.setdefault(name, Counter())[access.get("operation", "?")] += 1
        return {
            "repository": (self.document.get("repo") or {}).get("name"),
            "frameworks": self.document.get("frameworks"),
            "routes": len(self.routes),
            "routesWithPartialCoverage": partial,
            "routeGroups": dict(groups.most_common()),
            "objects": {name: dict(ops) for name, ops in sorted(objects.items())},
            "unresolvedGaps": [gap.get("kind") for gap in dicts(self.document.get("unresolvedGaps"))],
        }

    # Level 1

    def route_lines(self, path_prefix: str = "", object_name: str = "", method: str = "", offset: int = 0) -> dict:
        selected = [
            route
            for route in self.routes
            if route.get("pathTemplate", "").startswith(path_prefix or "")
            and (not method or route.get("httpMethod", "").upper() == method.upper())
            and (not object_name or any(_object_name(a) == object_name for a in dicts(route.get("dataAccesses"))))
        ]
        offset = max(int(offset or 0), 0)
        page = selected[offset : offset + PAGE]
        result = {"total": len(selected), "offset": offset, "routes": [_route_line(route) for route in page]}
        if offset + PAGE < len(selected):
            result["nextOffset"] = offset + PAGE
        return result

    # Level 2

    def route_summary(self, route_id: str) -> dict:
        route = self.route(route_id)
        handler = route.get("handler") if isinstance(route.get("handler"), dict) else {}
        budget = route.get("budget") if isinstance(route.get("budget"), dict) else {}
        omitted = Counter(item.get("reason") for item in dicts(budget.get("omitted")))
        related = dicts(route.get("relatedRoutes"))
        return {
            "id": route["id"],
            "route": f"{route.get('httpMethod')} {route.get('pathTemplate')}",
            "handler": {"qualifiedName": handler.get("qualifiedName"), "range": _range(handler.get("range"))},
            "params": [
                {key: param.get(key) for key in ("id", "name", "location", "namesObject")}
                for param in dicts(route.get("entryParams"))
            ],
            "identityBindings": [
                {key: binding.get(key) for key in ("id", "name", "kind", "expression")}
                for binding in dicts(route.get("identityBindings"))
            ],
            "authChain": [_auth_line(step) for step in dicts(route.get("authChain"))],
            "dataAccesses": [_access_summary(route, access) for access in dicts(route.get("dataAccesses"))],
            "coverage": budget.get("coverage"),
            "omittedCalls": dict(omitted),
            "callNodes": len(_walk(dicts(route.get("callGraph")))),
            "relatedRoutes": [
                {"routeId": link.get("routeId"), "relations": link.get("relations")} for link in related[:PAGE]
            ],
            "relatedRoutesTotal": len(related),
        }

    # Level 3

    def access_detail(self, route_id: str, access_id: str) -> dict:
        route = self.route(route_id)
        access = find_access(route, access_id)
        if access is None:
            raise GraphError(f"Route {route_id!r} has no data access {access_id!r}.")
        call_id = access.get("callId")
        path = call_path(route, call_id) if isinstance(call_id, str) else None
        return {
            "id": access_id,
            "operation": access.get("operation"),
            "object": access.get("object"),
            "paramFlows": access.get("paramFlows"),
            "ownershipEvidence": access.get("ownershipEvidence"),
            "writtenFields": access.get("writtenFields"),
            "snippet": _snippet(access.get("snippet")),
            "callPath": [_call_line(node) for node in path] if path else None,
            "objectSymbol": self.symbols.get((access.get("object") or {}).get("symbolId")),
        }

    def auth_detail(self, route_id: str, auth_step_id: str) -> dict:
        route = self.route(route_id)
        step = next((item for item in dicts(route.get("authChain")) if item.get("id") == auth_step_id), None)
        if step is None:
            raise GraphError(f"Route {route_id!r} has no auth step {auth_step_id!r}.")
        return {
            **_auth_line(step),
            "range": _range(step.get("range")),
            "snippet": _snippet(step.get("snippet")),
            "calls": [_call_line(node) for node in _walk(dicts(step.get("calls")))[:_CHILDREN_SHOWN]],
        }

    def call_tree(self, route_id: str, call_id: str = "", depth: int = 2) -> dict:
        route = self.route(route_id)
        roots = dicts(route.get("callGraph"))
        if call_id:
            path = call_path(route, call_id)
            if path is None:
                raise GraphError(f"Route {route_id!r} has no call {call_id!r}.")
            roots = [path[-1]]
        depth = min(max(int(depth or 1), 1), 4)
        return {"routeId": route_id, "calls": [_tree(node, depth) for node in roots[:_CHILDREN_SHOWN]], "callsTotal": len(roots)}

    def symbol(self, symbol_id: str) -> dict:
        entry = self.symbols.get(symbol_id)
        if entry is None:
            raise GraphError(f"No symbol {symbol_id!r} in the symbol index.")
        return entry

    def routes_touching(self, object_name: str, operation: str = "") -> dict:
        found = []
        for route in self.routes:
            for access in dicts(route.get("dataAccesses")):
                if _object_name(access) != object_name:
                    continue
                if operation and access.get("operation") != operation:
                    continue
                evidence = access.get("ownershipEvidence") or {}
                found.append(
                    {
                        "routeId": route["id"],
                        "route": f"{route.get('httpMethod')} {route.get('pathTemplate')}",
                        "accessId": access.get("id"),
                        "operation": access.get("operation"),
                        "inPredicate": evidence.get("inPredicate"),
                        "stampedOnWrite": evidence.get("stampedOnWrite"),
                        "ownerFields": evidence.get("ownerFields"),
                        "authBindsObject": [step.get("bindsObjectToCaller") for step in dicts(route.get("authChain"))],
                    }
                )
        return {"object": object_name, "total": len(found), "accesses": found[: PAGE * 2]}

    def opening_packet(self, route_id: str) -> dict:
        """What an agent starts from: the target's level-2 summary."""
        return self.route_summary(route_id)


def _group(path: str) -> str:
    parts = [part for part in path.split("/") if part and not part.startswith("{")]
    return "/" + "/".join(parts[:2]) if parts else "/"


def _object_name(access: dict) -> str:
    obj = access.get("object")
    if isinstance(obj, dict):
        return str(obj.get("name") or "?")
    return str(obj or "?")


def _route_line(route: dict) -> str:
    accesses = ", ".join(
        f"{_object_name(a)}:{a.get('operation')}(in={(a.get('ownershipEvidence') or {}).get('inPredicate')})"
        for a in dicts(route.get("dataAccesses"))[:6]
    )
    auth = ",".join(sorted({str(step.get("kind")) for step in dicts(route.get("authChain"))})) or "none"
    coverage = "partial" if coverage_is_partial(route) else "complete"
    return f"{route['id']} | {route.get('httpMethod')} {route.get('pathTemplate')} | auth={auth} | {accesses or 'no data access'} | {coverage}"


def _auth_line(step: dict) -> dict:
    return {
        key: step.get(key)
        for key in ("id", "qualifiedName", "kind", "mechanism", "scope", "applicability", "onFailure", "bindsObjectToCaller")
    }


def _access_summary(route: dict, access: dict) -> dict:
    call_id = access.get("callId")
    path = call_path(route, call_id) if isinstance(call_id, str) else None
    params = {param.get("id"): param.get("name") for param in dicts(route.get("entryParams"))}
    return {
        "id": access.get("id"),
        "operation": access.get("operation"),
        "object": _object_name(access),
        "paramFlows": [
            f"{params.get(flow.get('entryParamId'), flow.get('entryParamId'))} -> {flow.get('field')} ({flow.get('confidence')})"
            for flow in dicts(access.get("paramFlows"))
        ],
        "ownershipEvidence": access.get("ownershipEvidence"),
        "writtenFields": access.get("writtenFields"),
        "path": [f"{node.get('qualifiedName') or node.get('calleeName')} [{node.get('resolution')}]" for node in path] if path else None,
    }


def _call_line(node: dict) -> dict:
    return {
        "id": node.get("id"),
        "callee": node.get("qualifiedName") or node.get("calleeName"),
        "resolution": node.get("resolution"),
        "touchesPersistence": node.get("touchesPersistence"),
        "site": _range(node.get("callSite")),
        "code": node.get("argumentsExcerpt"),
    }


def _tree(node: dict, depth: int) -> dict:
    line = _call_line(node)
    children = dicts(node.get("children"))
    if depth > 1 and children:
        line["children"] = [_tree(child, depth - 1) for child in children[:_CHILDREN_SHOWN]]
        if len(children) > _CHILDREN_SHOWN:
            line["childrenTotal"] = len(children)
    elif children:
        line["childrenTotal"] = len(children)
    return line


def _walk(nodes: list[dict]) -> list[dict]:
    found: list[dict] = []
    stack = list(reversed(nodes))
    while stack:
        node = stack.pop()
        found.append(node)
        stack.extend(reversed(dicts(node.get("children"))))
    return found


def _snippet(snippet) -> dict | None:
    if not isinstance(snippet, dict):
        return None
    return {"text": snippet.get("text"), "truncated": snippet.get("truncated"), "range": _range(snippet.get("range"))}


def _range(value) -> str | None:
    if not isinstance(value, dict) or not value.get("file"):
        return None
    start, end = value.get("startLine"), value.get("endLine")
    return f"{value['file']}:{start}" + (f"-{end}" if end and end != start else "")
