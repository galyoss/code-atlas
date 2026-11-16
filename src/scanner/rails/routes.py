"""Rails routes from Joern calls in `config/routes.rb`.

Explicit `get "/path", to: "controller#action"` lines are route-table entries.
`resources :name` expands to one entry per action whose method exists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from scanner.expand import Body, Budget, build_calls, remember
from scanner.facts import BindingFact, EntryParamFact, ReadFact, RouteFact, SymbolFact
from scanner.overlay import CallRec
from scanner.ownership import classify_hook
from scanner.project import Project
from scanner.rails.source import RubyIndex

_VERBS = {"get", "post", "put", "patch", "delete", "head", "options"}
_EXPLICIT = re.compile(
    r"""\b(get|post|put|patch|delete|head|options)\s+['"]([^'"]+)['"]"""
    r"""(?:\s*,\s*to:\s*['"]([a-z0-9_/]+)#([A-Za-z0-9_]+)['"]|\s*=>\s*['"]([a-z0-9_/]+)#([A-Za-z0-9_]+)['"])"""
)
_RESOURCES = re.compile(
    r"resources\s+:([a-z0-9_]+)(?:\s*,\s*only:\s*\[([^\]]*)\])?(?:\s*,\s*except:\s*\[([^\]]*)\])?"
)
_BEFORE = re.compile(
    r"before_action\s+:([A-Za-z_][\w?!]*)"
    r"(?:\s*,\s*(only|except)\s*:\s*(?:\[([^\]]*)\]|:([A-Za-z_][\w?!]*)))?"
)
_NS = re.compile(r"\bnamespace\s+:([A-Za-z0-9_]+)")
_SCOPE = re.compile(r"""\bscope\s+(?:path:\s*)?['"]([^'"]+)['"]""")
_DO = re.compile(r"\bdo\b")
_END = re.compile(r"\bend\b")
_ACTIONS = (
    ("GET", "", "index"),
    ("POST", "", "create"),
    ("GET", "/new", "new"),
    ("GET", "/{id}", "show"),
    ("GET", "/{id}/edit", "edit"),
    ("PATCH", "/{id}", "update"),
    ("PUT", "/{id}", "update"),
    ("DELETE", "/{id}", "destroy"),
)


@dataclass
class RailsAnalysis:
    handler: Body
    filters: list[Body]
    budget: Budget
    by_full: dict[str, Body]
    by_name: dict[str, list[Body]]
    classes: dict[str, Body] = field(default_factory=dict)


def discover_routes(project: Project, index: RubyIndex) -> list[RouteFact]:
    _bind(project, index)
    by_full = {item.full_name: item for item in index.methods if item.full_name}
    by_name: dict[str, list[Body]] = {}
    for item in index.methods:
        by_name.setdefault(item.name, []).append(item)
    classes = {item.name: item for item in index.classes}
    routes: list[RouteFact] = []
    seen: set[tuple[str, str, str]] = set()
    for call in project.overlay.calls:
        for decl in _declarations(call, index):
            handler = index.method_named(decl[4], decl[5], decl[3])
            if handler is None or not _schema_path(decl[1]):
                continue
            ident = (decl[0], decl[1], handler.qualname)
            if ident in seen:
                continue
            seen.add(ident)
            filters = _filters(project, index, handler, decl[3], decl[5])
            route = _make(
                project, index, call, handler, decl, filters, by_full, by_name, classes
            )
            if route is not None:
                routes.append(route)
    routes.sort(key=lambda item: (item.http_method, item.path, item.handler_qualname))
    return routes


def _bind(project: Project, index: RubyIndex) -> None:
    for fn in index.methods:
        method = project.overlay.method_for(fn.file, fn.name, fn.line)
        if method is None:
            continue
        fn.full_name = method.full_name
        fn.end_line = max(method.end_line, fn.line)


def _declarations(call: CallRec, index: RubyIndex) -> list[tuple[str, str, str, str, str, str]]:
    """Return `(method, path, mechanism, action, file, class_name)`."""
    code = call.code or ""
    prefix = _prefix_at(index, call.file, call.line)
    explicit = _EXPLICIT.search(code)
    if call.name in _VERBS and explicit and explicit.group(1) == call.name:
        controller = explicit.group(3) or explicit.group(5)
        action = explicit.group(4) or explicit.group(6)
        path = _join(prefix, _template(explicit.group(2)))
        file_name, class_name = _controller(controller)
        located = _locate(index, file_name, class_name)
        if located is None:
            return []
        return [(call.name.upper(), path, "route_table", action, located, class_name)]
    if call.name != "resources":
        return []
    match = _RESOURCES.search(code)
    if match is None:
        return []
    resource, only, exclude = match.group(1), match.group(2), match.group(3)
    allowed = _names(only) if only is not None else None
    blocked = _names(exclude) if exclude is not None else set()
    file_name, class_name = _controller(resource)
    located = _locate(index, file_name, class_name)
    if located is None:
        return []
    found = []
    base = _join(prefix, "/" + resource)
    for method, suffix, action in _ACTIONS:
        if allowed is not None and action not in allowed:
            continue
        if action in blocked:
            continue
        path = _template(base + suffix) if suffix else base
        found.append((method, path, "resource_dsl", action, located, class_name))
    return found


def _locate(index: RubyIndex, file_name: str, class_name: str) -> str | None:
    if file_name in index.files:
        return file_name
    for rel, text in index.files.items():
        if re.search(rf"^\s*class\s+{re.escape(class_name)}\b", text, re.M):
            return rel
    return None


def _controller(name: str) -> tuple[str, str]:
    parts = [part for part in name.split("/") if part]
    class_name = "".join(part[:1].upper() + part[1:] for part in parts[-1:]) + "Controller"
    file_name = "app/controllers/" + "/".join(parts) + "_controller.rb"
    return file_name, class_name


def _filters(project: Project, index: RubyIndex, handler: Body, action: str, class_name: str) -> list[Body]:
    found: list[Body] = []
    seen: set[str] = set()
    for file_name, owner in _chain(index, handler.file, class_name):
        for call in project.overlay.calls:
            if call.file != file_name or call.name != "before_action":
                continue
            match = _BEFORE.search(call.code or "")
            if match is None:
                continue
            if not _applies(match, action):
                continue
            fn = index.method_named(file_name, owner, match.group(1))
            if fn is None or fn.qualname in seen:
                continue
            seen.add(fn.qualname)
            found.append(fn)
    return found


def _chain(index: RubyIndex, file_name: str, class_name: str) -> list[tuple[str, str]]:
    chain = [(file_name, class_name)]
    seen = {class_name}
    current_file, current_name = file_name, class_name
    for _ in range(4):
        text = index.files.get(current_file, "")
        match = re.search(
            rf"class\s+{re.escape(current_name)}\s*<\s*([A-Z]\w*(?:::[A-Z]\w*)*)",
            text,
        )
        if match is None:
            break
        parent = match.group(1).split("::")[-1]
        if parent in seen:
            break
        seen.add(parent)
        parent_body = index.class_named(parent)
        if parent_body is None:
            break
        chain.append((parent_body.file, parent_body.name))
        current_file, current_name = parent_body.file, parent_body.name
    return chain


def _applies(match: re.Match[str], action: str) -> bool:
    gate, listed, single = match.group(2), match.group(3), match.group(4)
    if gate is None:
        return True
    names = _names(listed) if listed is not None else {single} if single else set()
    if gate == "only":
        return action in names
    return action not in names


def _names(text: str | None) -> set[str]:
    if not text:
        return set()
    return {item[1:] if item.startswith(":") else item for item in re.findall(r":?([A-Za-z_][\w?!]*)", text)}


def _make(
    project: Project,
    index: RubyIndex,
    call: CallRec,
    handler: Body,
    decl: tuple[str, str, str, str, str, str],
    filters: list[Body],
    by_full: dict[str, Body],
    by_name: dict[str, list[Body]],
    classes: dict[str, Body],
) -> RouteFact | None:
    http, path, mechanism, _action, _file, _class_name = decl
    symbols: dict[str, SymbolFact] = {}
    remember(handler, symbols, "ruby")
    for fn in filters:
        remember(fn, symbols, "ruby")
    budget = Budget.start(project.limits)
    calls, expanded = build_calls(handler, project, by_full, by_name, symbols, budget, language="ruby")
    if expanded == "partial" and calls:
        calls[-1].omission = calls[-1].omission or ("node_budget", "Stopped the handler walk after maxCallNodes.")
        calls[-1].expanded = "partial" if calls[-1].children else "no"
        if calls[-1].expanded == "no":
            calls[-1].children = []
    text, truncated = index.snippet(call.file, call.line, call.line, project.limits.max_snippet_chars)
    route = RouteFact(
        http_method=http,
        path=path,
        framework="rails",
        language="ruby",
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
        registration_mechanism=mechanism,
        entry_params=_params(path, handler),
        bindings=_bindings(filters),
        call_graph=calls,
        symbols=symbols,
    )
    route.analysis = RailsAnalysis(handler, filters, budget, by_full, by_name, classes)
    return route


def _params(path: str, handler: Body) -> list[EntryParamFact]:
    params = []
    for name in re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", path):
        line = handler.line
        for offset, text in enumerate(handler.text.splitlines()):
            if f"params[:{name}]" in text or f"params['{name}']" in text:
                line = handler.line + offset
                break
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
    return params


def _bindings(filters: list[Body]) -> list[BindingFact]:
    for fn in filters:
        if classify_hook(fn.name, fn.text) is None:
            continue
        name = "current_user" if "current_user" in fn.name or "@current_user" in fn.text else fn.name
        if name.endswith("!"):
            name = name[:-1]
        return [
            BindingFact(
                name=name[:120] or "user",
                kind="user",
                presence="required",
                expression=fn.name[:200],
                file=fn.file,
                start=fn.line,
                end=fn.line,
                produced_by_qualname=fn.qualname,
                type_symbol_key=None,
            )
        ]
    return []


def _prefix_at(index: RubyIndex, file: str, line: int) -> str:
    text = index.files.get(file, "")
    if not text:
        return ""
    depth = 0
    stack: list[tuple[int, str]] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if number == line:
            return "/" + "/".join(part for _depth, part in stack if part)
        code = _strip(raw)
        ns = _NS.search(code)
        scope = _SCOPE.search(code)
        if _DO.search(code):
            depth += 1
            if ns:
                stack.append((depth, ns.group(1)))
            elif scope:
                stack.append((depth, scope.group(1).strip("/")))
        ends = len(_END.findall(code))
        for _ in range(ends):
            depth = max(0, depth - 1)
            while stack and stack[-1][0] > depth:
                stack.pop()
    return ""


def _template(path: str) -> str:
    text = (path or "").strip()
    text = re.sub(r"\(\.:format\)", "", text)
    text = re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", r"{\1}", text)
    if text and not text.startswith("/"):
        text = "/" + text
    text = re.sub(r"//+", "/", text)
    if len(text) > 1 and text.endswith("/"):
        text = text[:-1]
    return text or "/"


def _join(prefix: str, path: str) -> str:
    if not prefix or prefix == "/":
        return _template(path)
    return _template(prefix.rstrip("/") + "/" + path.lstrip("/"))


def _schema_path(path: str) -> bool:
    return re.fullmatch(
        r"^/(?:(?:[A-Za-z0-9._~-]+|\{[A-Za-z_][A-Za-z0-9_]*\})(?:/(?:[A-Za-z0-9._~-]+|\{[A-Za-z_][A-Za-z0-9_]*\}))*)?$",
        path or "",
    ) is not None


def _strip(line: str) -> str:
    text = re.sub(r'"(?:\\.|[^"\\])*"', '""', line)
    text = re.sub(r"'(?:\\.|[^'\\])*'", "''", text)
    comment = text.find("#")
    if comment >= 0:
        text = text[:comment]
    return text
