"""Discover FastAPI routes from Joern decorator and include_router calls."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from export_fastapi.facts import (
    BindingFact,
    CallFact,
    EntryParamFact,
    ReadFact,
    RouteFact,
    SymbolFact,
)
from export_fastapi.fastapi.calls import Budget, build_calls, walk
from export_fastapi.fastapi.paths import is_schema_path, join_paths, normalize_path
from export_fastapi.overlay import CallRec
from export_fastapi.project import Project
from export_fastapi.source_index import FuncInfo, SourceIndex

_HTTP = (
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
    "trace",
    "api_route",
)
_ROUTE_RE = re.compile(
    r"""([A-Za-z_][A-Za-z0-9_]*)\.(get|post|put|patch|delete|head|options|trace|api_route|websocket)\s*\(\s*(['"])(.*?)\3""",
    re.S,
)
_INCLUDE_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\.include_router\s*\((.*)\)\s*$", re.S)
_PREFIX_RE = re.compile(r"""prefix\s*=\s*(['"])(.*?)\1""")
_AUTH_NAME = re.compile(r"auth|current_user|login|principal|permission", re.I)
_SESSION_NAME = re.compile(r"session|database|^db$|settings", re.I)
_METHOD_WORD = re.compile(r"""['"](GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|TRACE)['"]""")


def is_auth_callable(name: str) -> bool:
    if _SESSION_NAME.search(name) and not _AUTH_NAME.search(name):
        return False
    return _AUTH_NAME.search(name) is not None


@dataclass
class RouteAnalysis:
    module: str
    handler: FuncInfo
    alias_to_class: dict[str, str]
    class_or_alias: set[str]
    mount_deps: list[str]
    budget: Budget
    overlay_calls: list[CallRec] = field(default_factory=list)


@dataclass
class _Router:
    module: str
    name: str
    prefix: str
    deps: list[str]
    file: str


@dataclass
class _Include:
    src: tuple[str, str] | None
    dst: tuple[str, str]
    prefix: str
    deps: list[str]


def discover_routes(project: Project, notes: list[str]) -> list[RouteFact]:
    index = project.index
    routers = _routers(project)
    includes = _includes(project, routers)
    mounts = _mounts(routers, includes)
    routes: list[RouteFact] = []
    seen: set[tuple[str, str, str]] = set()
    for call in project.overlay.calls:
        parsed = _parse_route(call)
        if parsed is None:
            continue
        receiver, method, path = parsed
        if method == "websocket":
            notes.append(f"WebSocket decorator at {call.file}:{call.line} is not a route.")
            continue
        module = index.module_for_file(call.file)
        if module is None:
            continue
        key = (module.qual, receiver)
        router = routers.get(key)
        mount_list = mounts.get(key)
        if not mount_list:
            prefix = router.prefix if router else ""
            deps = list(router.deps) if router else []
            mount_list = [(prefix, deps)]
        handler_method = _next_method(project, call)
        if handler_method is None:
            continue
        handler = index.function_at(handler_method.file, handler_method.name, handler_method.line)
        if handler is None:
            continue
        for prefix, deps in mount_list:
            external = join_paths(prefix, path)
            if not is_schema_path(external):
                continue
            ident = (method.upper() if method != "api_route" else "GET", external, handler.qualname)
            methods = _methods(method, call.code)
            for http_method in methods:
                ident = (http_method, external, handler.qualname)
                if ident in seen:
                    continue
                seen.add(ident)
                route = _make_route(project, call, handler, http_method, external, deps)
                if route is not None:
                    routes.append(route)
    routes.sort(key=lambda item: (item.http_method, item.path, item.handler_qualname))
    return routes


def _methods(method: str, code: str) -> list[str]:
    if method != "api_route":
        return [method.upper()]
    found = _METHOD_WORD.findall(code)
    return found or ["GET"]


def _parse_route(call: CallRec) -> tuple[str, str, str] | None:
    if call.name not in _HTTP and call.name != "websocket":
        return None
    match = _ROUTE_RE.search(call.code)
    if match is None or match.group(2) != call.name:
        return None
    path = match.group(4)
    if path and not path.startswith("/") and call.name != "websocket":
        return None
    full = call.method_full_name
    if "APIRouter" not in full and "FastAPI" not in full and match.group(1) not in {"router", "app", "api"}:
        if not path.startswith("/"):
            return None
    return match.group(1), call.name, path


def _next_method(project: Project, call: CallRec):
    candidates = [
        method
        for method in project.overlay.methods_by_file.get(call.file, [])
        if method.line > call.line and not method.name.startswith("<")
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda method: method.line)


def _routers(project: Project) -> dict[tuple[str, str], _Router]:
    found: dict[tuple[str, str], _Router] = {}
    for call in project.overlay.calls:
        if call.name != "APIRouter":
            continue
        module = project.index.module_for_file(call.file)
        if module is None:
            continue
        prefix = ""
        prefix_match = _PREFIX_RE.search(call.code)
        if prefix_match:
            prefix = normalize_path(prefix_match.group(2))
            if prefix == "/":
                prefix = ""
        name = _assignment_name(project.overlay.by_caller.get(call.caller, []), call.code)
        if name is None:
            continue
        deps = project.index.dependency_targets(module.qual, _keyword(call.code, "dependencies") or "")
        found[(module.qual, name)] = _Router(module.qual, name, prefix, deps, call.file)
    return found


def _includes(project: Project, routers: dict[tuple[str, str], _Router]) -> list[_Include]:
    edges: list[_Include] = []
    for call in project.overlay.calls:
        if call.name != "include_router":
            continue
        match = _INCLUDE_RE.search(call.code.strip())
        if match is None:
            continue
        module = project.index.module_for_file(call.file)
        if module is None:
            continue
        receiver = match.group(1)
        args = _split_args(match.group(2))
        positional = [arg for arg in args if "=" not in arg.split("(")[0]]
        if not positional:
            continue
        target_name = positional[0].strip()
        dst = _resolve_router(module.qual, target_name, routers, project.index)
        if dst is None:
            continue
        prefix = ""
        prefix_match = _PREFIX_RE.search(call.code)
        if prefix_match:
            prefix = normalize_path(prefix_match.group(2))
            if prefix == "/":
                prefix = ""
        deps = project.index.dependency_targets(module.qual, _keyword(call.code, "dependencies") or "")
        src = (module.qual, receiver) if (module.qual, receiver) in routers else None
        edges.append(_Include(src, dst, prefix, deps))
    return edges


def _resolve_router(
    module: str,
    name: str,
    routers: dict[tuple[str, str], _Router],
    index: SourceIndex,
) -> tuple[str, str] | None:
    if (module, name) in routers:
        return module, name
    mod = index.modules.get(module)
    if mod is None:
        return None
    imported = mod.imports.get(name)
    if imported is None:
        return None
    src_mod, src_name = imported
    target = src_name or name
    if (src_mod, target) in routers:
        return src_mod, target
    return None


def _mounts(
    routers: dict[tuple[str, str], _Router],
    includes: list[_Include],
) -> dict[tuple[str, str], list[tuple[str, list[str]]]]:
    """Full external prefix and dependency qualnames for each mounted router."""
    outgoing: dict[tuple[str, str], list[_Include]] = {}
    for edge in includes:
        if edge.src is not None:
            outgoing.setdefault(edge.src, []).append(edge)
    mounts: dict[tuple[str, str], list[tuple[str, list[str]]]] = {}
    queue: list[tuple[tuple[str, str], str, list[str]]] = []
    for edge in includes:
        if edge.src is not None or edge.dst not in routers:
            continue
        router = routers[edge.dst]
        queue.append((edge.dst, join_paths(edge.prefix, router.prefix), [*edge.deps, *router.deps]))
    seen: set[tuple[tuple[str, str], str]] = set()
    while queue:
        key, prefix, deps = queue.pop(0)
        marker = (key, prefix)
        if marker in seen:
            continue
        seen.add(marker)
        mounts.setdefault(key, []).append((prefix if prefix != "/" else "", _unique(deps)))
        for edge in outgoing.get(key, []):
            if edge.dst not in routers:
                continue
            child = routers[edge.dst]
            queue.append(
                (
                    edge.dst,
                    join_paths(prefix, edge.prefix, child.prefix),
                    [*deps, *edge.deps, *child.deps],
                )
            )
    return mounts


def _make_route(
    project: Project,
    decorator: CallRec,
    handler: FuncInfo,
    http_method: str,
    path: str,
    deps: list[str],
) -> RouteFact | None:
    reg_end = handler.line - 1 if handler.line > decorator.line else decorator.line
    text, truncated = project.index.snippet(
        decorator.file, decorator.line, reg_end, project.limits.max_snippet_chars
    )
    if not text:
        text, truncated = decorator.code[: project.limits.max_snippet_chars], len(decorator.code) > project.limits.max_snippet_chars
    end_line = handler.end_line
    method = project.overlay.method_for(handler.file, handler.name, handler.line)
    if method is not None:
        end_line = method.end_line
    symbols: dict[str, SymbolFact] = {}
    symbols[handler.qualname] = SymbolFact(
        key=handler.qualname,
        language="python",
        kind="method" if handler.is_method else "function",
        name=handler.name,
        qualname=handler.qualname,
        signature=handler.signature[:300],
        file=handler.file,
        start=handler.line,
        end=max(end_line, handler.line),
    )
    aliases = project.index.alias_map(handler.module)
    budget = Budget.start(project.limits)
    call_graph, expanded = build_calls(handler, project, symbols, budget)
    if expanded == "partial" and call_graph:
        last = walk(call_graph)[-1]
        if last.omission is None:
            last.omission = ("node_budget", "Stopped the handler walk after maxCallNodes.")
            last.expanded = "partial" if last.children else "no"
            if last.expanded == "no":
                last.children = []
    entry = _entry_params(project, handler, path, symbols)
    _body_fields(project, handler, entry, symbols)
    bindings = _bindings(handler, project.index, symbols)
    route = RouteFact(
        http_method=http_method,
        path=path,
        framework="fastapi",
        language="python",
        registration_file=decorator.file,
        registration_start=decorator.line,
        registration_end=max(reg_end, decorator.line),
        registration_text=text or decorator.code[:240],
        registration_truncated=truncated,
        handler_symbol_key=handler.qualname,
        handler_qualname=handler.qualname,
        handler_file=handler.file,
        handler_start=handler.line,
        handler_end=max(end_line, handler.line),
        entry_params=entry,
        bindings=bindings,
        call_graph=call_graph,
        symbols=symbols,
    )
    caller = method.full_name if method is not None else ""
    route.analysis = RouteAnalysis(
        module=handler.module,
        handler=handler,
        alias_to_class=aliases,
        class_or_alias=set(aliases) | {cls.name for cls in project.index.classes_in_file(handler.file)},
        mount_deps=list(deps),
        budget=budget,
        overlay_calls=list(project.overlay.by_caller.get(caller, [])),
    )
    for qual in deps:
        _ensure_function_symbol(project.index, qual, symbols)
    return route


def _entry_params(project: Project, handler: FuncInfo, path: str, symbols: dict[str, SymbolFact]) -> list[EntryParamFact]:
    names = re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", path)
    params: list[EntryParamFact] = []
    seen: set[str] = set()
    by_name = {param.name: param for param in handler.params}
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        param = by_name.get(name)
        line = param.line if param else handler.line
        params.append(
            EntryParamFact(
                name=name,
                location="path",
                path_in_request=f"path.{name}",
                presence="required",
                value_shape="scalar",
                names_object="yes" if name == "id" or name.endswith("_id") else "unknown",
                type_symbol_key=None,
                reads=[ReadFact(handler.file, line, line, handler.qualname, name)],
            )
        )
    for param in handler.params:
        if param.name in seen:
            continue
        if any(is_auth_callable(dep) for dep in param.depends):
            continue
        if param.depends and _SESSION_NAME.search(param.depends[0]) and not is_auth_callable(param.depends[0]):
            continue
        location, shape, type_key = _param_location(param, project.index, handler.module, symbols)
        if location == "unknown":
            continue
        seen.add(param.name)
        params.append(
            EntryParamFact(
                name=param.name if location != "header" else param.name.lower(),
                location=location,
                path_in_request=f"{location}.{param.name}",
                presence="optional" if param.default_src else "required",
                value_shape=shape,
                names_object="no" if location == "body" else "unknown",
                type_symbol_key=type_key,
                reads=[ReadFact(handler.file, param.line, param.line, handler.qualname, param.name)],
            )
        )
    return params


def _param_location(param, index: SourceIndex, module: str, symbols: dict[str, SymbolFact]):
    default = param.default_src
    if "Query(" in default or "Query (" in default:
        return "query", "scalar", None
    if "Header(" in default:
        return "header", "scalar", None
    if "Cookie(" in default:
        return "cookie", "scalar", None
    if "Form(" in default:
        return "form", "scalar", None
    if param.annotation:
        resolved = index.resolve_name(module, param.annotation)
        if resolved and resolved[0] == "class":
            cls = index.classes_by_qual.get(resolved[1])
            if cls is not None and not cls.is_orm:
                symbols.setdefault(
                    cls.qualname,
                    SymbolFact(
                        key=cls.qualname,
                        language="python",
                        kind="class",
                        name=cls.name,
                        qualname=cls.qualname,
                        signature=cls.signature[:300],
                        file=cls.file,
                        start=cls.line,
                        end=max(cls.end_line, cls.line),
                    ),
                )
                return "body", "object", cls.qualname
    return "unknown", "unknown", None


def _body_fields(project: Project, handler: FuncInfo, params: list[EntryParamFact], symbols: dict[str, SymbolFact]) -> None:
    body = [param for param in params if param.location == "body"]
    if not body:
        return
    method = project.overlay.method_for(handler.file, handler.name, handler.line)
    calls = project.overlay.by_caller.get(method.full_name, []) if method else []
    blob = "\n".join(call.code for call in calls)
    existing = {param.name for param in params}
    for param in body:
        for match in re.finditer(rf"\b{re.escape(param.name)}\.([A-Za-z_][A-Za-z0-9_]*)", blob):
            field_name = match.group(1)
            if not field_name.endswith("_id") or field_name in existing:
                continue
            existing.add(field_name)
            params.append(
                EntryParamFact(
                    name=field_name,
                    location="body",
                    path_in_request=f"body.{field_name}",
                    presence=param.presence,
                    value_shape="scalar",
                    names_object="yes",
                    type_symbol_key=None,
                    reads=[ReadFact(handler.file, handler.line, handler.line, handler.qualname, f"{param.name}.{field_name}")],
                )
            )


def _bindings(handler: FuncInfo, index: SourceIndex, symbols: dict[str, SymbolFact]) -> list[BindingFact]:
    found: list[BindingFact] = []
    for param in handler.params:
        auth_deps = [dep for dep in param.depends if is_auth_callable(dep)]
        if not auth_deps and param.name not in {"user", "current_user"}:
            continue
        if not auth_deps and param.name in {"user", "current_user"} and not param.depends:
            continue
        produced = None
        if auth_deps:
            resolved = index.resolve_name(handler.module, auth_deps[0])
            if resolved and resolved[0] == "function":
                produced = resolved[1]
                _ensure_function_symbol(index, produced, symbols)
        type_key = None
        if param.annotation:
            resolved_type = index.resolve_name(handler.module, param.annotation)
            if resolved_type and resolved_type[0] == "class":
                type_key = resolved_type[1]
                cls = index.classes_by_qual.get(type_key)
                if cls is not None:
                    symbols.setdefault(
                        cls.qualname,
                        SymbolFact(
                            key=cls.qualname,
                            language="python",
                            kind="class",
                            name=cls.name,
                            qualname=cls.qualname,
                            signature=cls.signature[:300],
                            file=cls.file,
                            start=cls.line,
                            end=max(cls.end_line, cls.line),
                        ),
                    )
        expression = param.default_src or param.name
        found.append(
            BindingFact(
                name=param.name,
                kind="user",
                presence="required" if not param.default_src or "Depends" in param.default_src else "optional",
                expression=expression[:200],
                file=handler.file,
                start=param.line,
                end=param.line,
                produced_by_qualname=produced,
                type_symbol_key=type_key,
            )
        )
    return found


def _ensure_function_symbol(index: SourceIndex, qual: str, symbols: dict[str, SymbolFact]) -> None:
    func = index.functions_by_qual.get(qual)
    if func is None:
        return
    symbols.setdefault(
        qual,
        SymbolFact(
            key=qual,
            language="python",
            kind="method" if func.is_method else "function",
            name=func.name,
            qualname=qual,
            signature=func.signature[:300],
            file=func.file,
            start=func.line,
            end=max(func.end_line, func.line),
        ),
    )


def _assignment_name(calls: list[CallRec], needle: str) -> str | None:
    for call in calls:
        if call.name != "<operator>.assignment" or needle not in call.code:
            continue
        match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", call.code)
        if match:
            return match.group(1)
    return None


def _keyword(code: str, name: str) -> str | None:
    match = re.search(rf"{name}\s*=\s*", code)
    if match is None:
        return None
    return _take_expr(code[match.end() :])


def _take_expr(text: str) -> str:
    if not text:
        return ""
    if text[0] in "[(":
        open_ch, close_ch = ("[", "]") if text[0] == "[" else ("(", ")")
        depth = 0
        for index, char in enumerate(text):
            if char == open_ch:
                depth += 1
            elif char == close_ch:
                depth -= 1
                if depth == 0:
                    return text[: index + 1]
        return text
    match = re.match(r"[A-Za-z_][A-Za-z0-9_\.]*", text)
    return match.group(0) if match else ""


def _split_args(text: str) -> list[str]:
    args: list[str] = []
    buf: list[str] = []
    depth = 0
    quote = ""
    for char in text:
        if quote:
            buf.append(char)
            if char == quote:
                quote = ""
            continue
        if char in {"'", '"'}:
            quote = char
            buf.append(char)
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            args.append("".join(buf).strip())
            buf = []
            continue
        buf.append(char)
    if buf:
        args.append("".join(buf).strip())
    return [arg for arg in args if arg]


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def call_index(nodes: list[CallFact]) -> dict[str, CallFact]:
    return {node.key: node for node in walk(nodes)}
