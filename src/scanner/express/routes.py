"""Express routes from Joern `app.METHOD` and `router.METHOD` calls.

`app.ws` is not a route. A handler the call text does not name is skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from scanner.expand import Body, Budget, build_calls, remember
from scanner.express.source import JsIndex
from scanner.facts import BindingFact, EntryParamFact, ReadFact, RouteFact, SymbolFact
from scanner.overlay import CallRec
from scanner.project import Project

_HTTP = {"get", "post", "put", "patch", "delete", "head", "options", "all"}
_ROUTE = re.compile(
    r"""\b([A-Za-z_$][\w$]*)\s*\.\s*(get|post|put|patch|delete|head|options|all)\s*\(\s*['"]([^'"]+)['"]"""
)
_USE_FN = re.compile(r"""\b([A-Za-z_$][\w$]*)\s*\.\s*use\s*\(\s*([A-Za-z_$][\w$]*)\s*\)""")
_USE_PATH = re.compile(
    r"""\b([A-Za-z_$][\w$]*)\s*\.\s*use\s*\(\s*['"]([^'"]+)['"]\s*,\s*([A-Za-z_$][\w$]*)\s*\)"""
)
_MOUNT = re.compile(
    r"""\b([A-Za-z_$][\w$]*)\s*\.\s*use\s*\(\s*(?:['"]([^'"]*)['"]\s*,\s*)?([A-Za-z_$][\w$]*)\s*\)"""
)
_FUNC_NAME = re.compile(r"function\s+([A-Za-z_$][\w$]*)\s*\(")
_IDENT = re.compile(r"[A-Za-z_$][\w$]*")


@dataclass
class ExpressAnalysis:
    handler: Body
    middleware: list[Body]
    budget: Budget
    by_full: dict[str, Body]
    by_name: dict[str, list[Body]]
    classes: dict[str, Body] = field(default_factory=dict)


def discover_routes(project: Project, index: JsIndex) -> list[RouteFact]:
    _bind(project, index)
    by_full = {item.full_name: item for item in index.functions if item.full_name}
    by_name: dict[str, list[Body]] = {}
    for item in index.functions:
        by_name.setdefault(item.name, []).append(item)
    classes = {item.name: item for item in index.classes}
    uses = _uses(project)
    mounts = _mounts(project, index)
    routes: list[RouteFact] = []
    seen: set[tuple[str, str, str]] = set()
    for call in project.overlay.calls:
        parsed = _parse_route(call, index)
        if parsed is None:
            continue
        receiver, method, path, handler_name = parsed
        handler = _handler(index, call, handler_name)
        if handler is None:
            continue
        prefixes = _prefixes(receiver, index, mounts)
        for prefix in prefixes:
            external = _join(prefix, _template(path))
            if not _schema_path(external):
                continue
            http = "ALL" if method == "all" else method.upper()
            ident = (http, external, handler.qualname)
            if ident in seen:
                continue
            seen.add(ident)
            middleware = _middleware(index, call, receiver, external, uses, handler)
            route = _make(project, index, call, handler, http, external, middleware, by_full, by_name, classes)
            if route is not None:
                routes.append(route)
    routes.sort(key=lambda item: (item.http_method, item.path, item.handler_qualname))
    return routes


def _bind(project: Project, index: JsIndex) -> None:
    for fn in index.functions:
        method = project.overlay.method_for(fn.file, fn.name, fn.line)
        if method is None:
            continue
        fn.full_name = method.full_name
        fn.end_line = max(method.end_line, fn.line)


def _parse_route(call: CallRec, index: JsIndex) -> tuple[str, str, str, str] | None:
    if call.name not in _HTTP and call.name not in {"ws", "websocket"}:
        return None
    if call.name in {"ws", "websocket"}:
        return None
    match = _ROUTE.search(call.code or "")
    if match is None or match.group(2) != call.name:
        return None
    receiver, _method, path = match.group(1), match.group(2), match.group(3)
    known = index.apps | index.routers
    if receiver not in known and "express" not in (call.method_full_name or ""):
        return None
    if not path.startswith("/"):
        return None
    handler = _handler_name(call.code, receiver)
    if handler is None:
        return None
    return receiver, call.name, path, handler


def _handler_name(code: str, receiver: str) -> str | None:
    named = _FUNC_NAME.search(code or "")
    if named:
        return named.group(1)
    args = _args_after_path(code)
    idents = [item for item in _IDENT.findall(args) if item not in {receiver, "function", "async"}]
    if not idents:
        return None
    return idents[-1]


def _args_after_path(code: str) -> str:
    match = re.search(r"""['"][^'"]+['"]\s*,\s*(.*)$""", code or "", re.S)
    return match.group(1) if match else ""


def _handler(index: JsIndex, call: CallRec, name: str) -> Body | None:
    in_file = index.functions_named(call.file, name)
    if len(in_file) == 1:
        return in_file[0]
    closest = [item for item in in_file if abs(item.line - call.line) <= 5]
    if len(closest) == 1:
        return closest[0]
    if len(in_file) > 1:
        return min(in_file, key=lambda item: abs(item.line - call.line))
    return index.function_named(name)


def _uses(project: Project) -> list[tuple[int, str, str | None, str, str]]:
    found = []
    for call in project.overlay.calls:
        if call.name != "use":
            continue
        path_match = _USE_PATH.search(call.code or "")
        if path_match:
            found.append((call.line, path_match.group(1), path_match.group(2), path_match.group(3), call.file))
            continue
        plain = _USE_FN.search(call.code or "")
        if plain:
            found.append((call.line, plain.group(1), None, plain.group(2), call.file))
    return found


def _mounts(project: Project, index: JsIndex) -> list[tuple[str, str, str]]:
    found = []
    for call in project.overlay.calls:
        if call.name != "use":
            continue
        match = _MOUNT.search(call.code or "")
        if match is None:
            continue
        parent, prefix, child = match.group(1), match.group(2), match.group(3)
        if child in index.routers and child not in index.apps:
            found.append((parent, prefix or "", child))
    return found


def _prefixes(receiver: str, index: JsIndex, mounts: list[tuple[str, str, str]]) -> list[str]:
    if receiver in index.apps and receiver not in index.routers:
        return [""]
    if receiver in index.apps and receiver not in {item[2] for item in mounts}:
        return [""]
    prefixes = [prefix for parent, prefix, child in mounts if child == receiver]
    if prefixes:
        return prefixes
    return [""]


def _middleware(index: JsIndex, call: CallRec, receiver: str, path: str, uses, handler: Body) -> list[Body]:
    found: list[Body] = []
    seen: set[str] = set()
    for line, use_receiver, use_path, name, file in uses:
        if use_receiver != receiver or line > call.line or name == handler.name:
            continue
        if use_path and not _under(path, _template(use_path)):
            continue
        fn = index.function_named(name, file) or index.function_named(name)
        if fn is None or fn.qualname in seen:
            continue
        seen.add(fn.qualname)
        found.append(fn)
    for name in _local_middleware(call.code or "", handler.name):
        fn = index.function_named(name, call.file) or index.function_named(name)
        if fn is None or fn.qualname in seen:
            continue
        seen.add(fn.qualname)
        found.append(fn)
    return found


def _local_middleware(code: str, handler_name: str) -> list[str]:
    if _FUNC_NAME.search(code):
        head = code.split("function", 1)[0]
    else:
        head = code
    args = _args_after_path(head)
    names = [item for item in _IDENT.findall(args) if item not in {"function", "async", handler_name}]
    if names and names[-1] == handler_name:
        names = names[:-1]
    return names


def _make(
    project: Project,
    index: JsIndex,
    call: CallRec,
    handler: Body,
    http: str,
    path: str,
    middleware: list[Body],
    by_full: dict[str, Body],
    by_name: dict[str, list[Body]],
    classes: dict[str, Body],
) -> RouteFact | None:
    symbols: dict[str, SymbolFact] = {}
    remember(handler, symbols, "javascript")
    for fn in middleware:
        remember(fn, symbols, "javascript")
    budget = Budget.start(project.limits)
    calls, expanded = build_calls(
        handler, project, by_full, by_name, symbols, budget, language="javascript"
    )
    if expanded == "partial" and calls:
        calls[-1].omission = calls[-1].omission or ("node_budget", "Stopped the handler walk after maxCallNodes.")
        calls[-1].expanded = "partial" if calls[-1].children else "no"
        if calls[-1].expanded == "no":
            calls[-1].children = []
    text, truncated = index.snippet(call.file, call.line, call.line, project.limits.max_snippet_chars)
    route = RouteFact(
        http_method=http,
        path=path,
        framework="express",
        language="javascript",
        registration_file=call.file,
        registration_start=call.line,
        registration_end=call.line,
        registration_text=text or (call.code or "")[:240],
        registration_truncated=truncated,
        handler_symbol_key=handler.qualname,
        handler_qualname=handler.qualname,
        handler_file=handler.file,
        handler_start=handler.line,
        handler_end=max(handler.end_line, handler.line),
        registration_mechanism="route_table",
        entry_params=_params(path, handler),
        bindings=_bindings(middleware),
        call_graph=calls,
        symbols=symbols,
    )
    route.analysis = ExpressAnalysis(handler, middleware, budget, by_full, by_name, classes)
    return route


def _params(path: str, handler: Body) -> list[EntryParamFact]:
    params = []
    for name in re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", path):
        line = handler.line
        for offset, text in enumerate(handler.text.splitlines()):
            if f"req.params.{name}" in text or f"params.{name}" in text:
                line = handler.line + offset
                break
        params.append(
            EntryParamFact(
                name=name,
                location="path",
                path_in_request=f"path.{name}",
                presence="required",
                value_shape="scalar",
                names_object="yes" if name == "id" or name.endswith("_id") or name.endswith("Id") else "unknown",
                type_symbol_key=None,
                reads=[ReadFact(handler.file, line, line, handler.qualname, name)],
            )
        )
    return params


def _bindings(middleware: list[Body]) -> list[BindingFact]:
    found = []
    for fn in middleware:
        if "req.user" not in fn.text and "currentUser" not in fn.name and "current_user" not in fn.name:
            continue
        found.append(
            BindingFact(
                name="user",
                kind="user",
                presence="required",
                expression="req.user",
                file=fn.file,
                start=fn.line,
                end=fn.line,
                produced_by_qualname=fn.qualname,
                type_symbol_key=None,
            )
        )
        break
    return found


def _template(path: str) -> str:
    text = (path or "").strip()
    text = re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", r"{\1}", text)
    text = re.sub(r"//+", "/", text)
    if len(text) > 1 and text.endswith("/"):
        text = text[:-1]
    if text and not text.startswith("/"):
        text = "/" + text
    return text or "/"


def _join(prefix: str, path: str) -> str:
    if not prefix:
        return _template(path)
    return _template(prefix.rstrip("/") + "/" + path.lstrip("/"))


def _under(path: str, prefix: str) -> bool:
    if prefix in {"", "/"}:
        return True
    return path == prefix or path.startswith(prefix.rstrip("/") + "/")


def _schema_path(path: str) -> bool:
    return re.fullmatch(
        r"^/(?:(?:[A-Za-z0-9._~-]+|\{[A-Za-z_][A-Za-z0-9_]*\})(?:/(?:[A-Za-z0-9._~-]+|\{[A-Za-z_][A-Za-z0-9_]*\}))*)?$",
        path or "",
    ) is not None
