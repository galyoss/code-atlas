"""SQLAlchemy-shaped data accesses for one FastAPI route.

Predicate text comes from the Joern call's `code`. A missing comparison stays
`unknown`.
"""

from __future__ import annotations

import re

from scanner.facts import (
    DataAccessFact,
    ParamFlowFact,
    RouteFact,
    SymbolFact,
    WrittenFieldFact,
)
from scanner.fastapi.calls import walk
from scanner.fastapi.predicates import predicate_from_cpg
from scanner.fastapi.routes import RouteAnalysis
from scanner.project import Project

_MODEL_RE = re.compile(r"\b(select|query|update|delete)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)")
_ADD_RE = re.compile(r"\.add\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)")
_KWARG_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^,]+)")
_FLOW_RE = re.compile(
    r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*==\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)"
)
_IDENTITY_RHS = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\.(identity|id)$")
_CONST_RHS = re.compile(r"^(None|True|False|-?\d+|\"[^\"]*\"|'[^']*')$")


def read_data_accesses(project: Project, route: RouteFact) -> list[DataAccessFact]:
    analysis: RouteAnalysis = route.analysis
    accesses: list[DataAccessFact] = []
    seen: set[str] = set()
    for node in walk(route.call_graph):
        access = _from_call(project, route, analysis, node)
        if access is None or access.key in seen:
            continue
        seen.add(access.key)
        accesses.append(access)
    return accesses


def _from_call(project: Project, route: RouteFact, analysis: RouteAnalysis, node) -> DataAccessFact | None:
    code = node.code or node.excerpt
    if node.callee_name in {"where", "filter"} and _MODEL_RE.search(code):
        return _query_access(project, route, analysis, node, code)
    if node.callee_name == "add" and _ADD_RE.search(code):
        return _create_access(project, route, analysis, node, code)
    return None


def _query_access(project, route, analysis: RouteAnalysis, node, code: str) -> DataAccessFact | None:
    match = _MODEL_RE.search(code)
    if match is None:
        return None
    verb, alias = match.group(1), match.group(2)
    aliases = _aliases(project, analysis, node.file)
    cls = _class_for(project, analysis, alias, node.file)
    object_name = cls.name if cls is not None else aliases.get(alias, alias)
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", object_name):
        return None
    symbol_key = None
    if cls is not None:
        symbol_key = cls.qualname
        route.symbols.setdefault(
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
    decision, owners, idents = predicate_from_cpg(code, aliases)
    if verb == "update":
        operation = "update"
        stamped, written = _update_stamp(code, analysis, route, owners)
    elif verb == "delete":
        operation = "delete"
        stamped, written = "not_applicable", []
    else:
        operation = _load_or_query(project, code, node)
        stamped, written = "not_applicable", []
        owners = owners if decision == "yes" else []
        idents = idents if decision == "yes" else []
    if decision != "yes":
        owners = []
        idents = []
    snippet = clip_snippet(code, project.limits.max_snippet_chars)
    return DataAccessFact(
        key=f"da:{node.key}",
        call_key=node.key,
        operation=operation,
        persistence_api="orm",
        object_name=object_name,
        object_symbol_key=symbol_key,
        store=cls.tablename if cls is not None else None,
        param_flows=_flows(code, aliases, route),
        in_predicate=decision if operation != "update" else decision,
        stamped_on_write=stamped,
        owner_fields=owners if decision == "yes" or stamped == "yes" else [],
        identity_names=_known_bindings(idents, route) if decision == "yes" or stamped == "yes" else [],
        written_fields=written,
        snippet=snippet,
        snippet_file=node.file,
        snippet_start=node.line,
        snippet_end=node.line,
        snippet_truncated=len(code) > project.limits.max_snippet_chars,
    )


def _create_access(project, route, analysis: RouteAnalysis, node, code: str) -> DataAccessFact | None:
    match = _ADD_RE.search(code)
    if match is None:
        return None
    variable = match.group(1)
    ctor = _constructor_code(_caller_calls(project, node), variable)
    if ctor is None:
        return None
    ctor_match = re.match(r"\s*(?:[A-Za-z_][A-Za-z0-9_]*\s*=\s*)*([A-Za-z_][A-Za-z0-9_]*)\s*\(", ctor)
    # Prefer the model call inside the assignment text.
    model_match = re.search(r"\b([A-Z][A-Za-z0-9_]*)\s*\(", ctor)
    if model_match is None:
        return None
    alias = model_match.group(1)
    cls = _class_for(project, analysis, alias, node.file)
    if cls is None or not cls.is_orm:
        return None
    route.symbols.setdefault(
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
    written, stamped, owners, idents = _written(ctor, cls, route)
    snippet = clip_snippet(ctor, project.limits.max_snippet_chars)
    return DataAccessFact(
        key=f"da:{node.key}",
        call_key=node.key,
        operation="create",
        persistence_api="orm",
        object_name=cls.name,
        object_symbol_key=cls.qualname,
        store=cls.tablename,
        param_flows=_create_flows(written, route),
        in_predicate="not_applicable",
        stamped_on_write=stamped,
        owner_fields=owners if stamped == "yes" else [],
        identity_names=idents if stamped == "yes" else [],
        written_fields=written,
        snippet=snippet,
        snippet_file=node.file,
        snippet_start=node.line,
        snippet_end=node.line,
        snippet_truncated=len(ctor) > project.limits.max_snippet_chars,
    )


def _aliases(project: Project, analysis: RouteAnalysis, file: str) -> dict[str, str]:
    merged = dict(analysis.alias_to_class)
    module = project.index.module_for_file(file)
    if module is not None:
        merged.update(project.index.alias_map(module.qual))
    return merged


def _caller_calls(project: Project, node):
    methods = [
        method
        for method in project.overlay.methods_by_file.get(node.file, [])
        if method.line <= node.line <= method.end_line and not method.name.startswith("<")
    ]
    if not methods:
        return []
    method = min(methods, key=lambda item: (item.end_line - item.line, item.line))
    return project.overlay.by_caller.get(method.full_name, [])


def _class_for(project: Project, analysis: RouteAnalysis, alias: str, file: str):
    aliases = _aliases(project, analysis, file)
    class_name = aliases.get(alias, alias)
    module = project.index.module_for_file(file)
    matches = [cls for cls in project.index.classes_by_qual.values() if cls.name == class_name]
    if module is not None:
        imported = module.imports.get(alias) or module.imports.get(class_name)
        if imported and imported[0] in project.index.modules:
            src_mod, src_name = imported
            target = src_name or class_name
            for cls in project.index.modules[src_mod].classes:
                if cls.name == target:
                    return cls
    if len(matches) == 1:
        return matches[0]
    return None


def _load_or_query(project: Project, code: str, node) -> str:
    calls = _caller_calls(project, node)
    target = _assignment_target(calls, code)
    sibling_blob = "\n".join(call.code for call in calls)
    if target and re.search(rf"\bscalars\s*\(\s*{re.escape(target)}\s*\)", sibling_blob):
        return "query"
    if target and re.search(rf"\bscalar\s*\(\s*{re.escape(target)}\s*\)", sibling_blob):
        return "load"
    if re.search(r"\blimit\s*\(", sibling_blob):
        return "query"
    return "load"


def _assignment_target(calls, inner: str) -> str | None:
    needle = inner.strip()
    if len(needle) > 180:
        needle = needle[:180]
    for call in calls:
        if call.name != "<operator>.assignment" or needle not in call.code:
            continue
        match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", call.code)
        if match:
            return match.group(1)
    return None


def _constructor_code(calls, variable: str) -> str | None:
    pattern = re.compile(rf"(?:^|\n)\s*{re.escape(variable)}\s*=")
    for call in calls:
        if call.name != "<operator>.assignment":
            continue
        if pattern.search(call.code) and re.search(r"\b[A-Z][A-Za-z0-9_]*\s*\(", call.code):
            return call.code
    return None


def _written(ctor: str, cls, route: RouteFact):
    owner_cols = set(cls.columns) & {
        "user_id",
        "owner_id",
        "created_by",
        "tenant_id",
        "account_id",
        "org_id",
        "organization_id",
    }
    body = ctor
    paren = ctor.find("(")
    if paren >= 0:
        body = ctor[paren:]
    binding_names = {binding.name for binding in route.bindings}
    entry_names = {param.name for param in route.entry_params}
    written: list[WrittenFieldFact] = []
    stamped = "no"
    owners: list[str] = []
    idents: list[str] = []
    for field_name, rhs in _kwargs(body):
        source, entry_name, binding_name = _value_source(field_name, rhs.strip(), entry_names, binding_names, owner_cols)
        item = WrittenFieldFact(field=field_name, source=source)
        if source == "request_param" and entry_name:
            item.entry_param_name = entry_name
        elif source == "identity" and binding_name:
            item.binding_name = binding_name
        elif source == "identity" and not binding_name:
            item.source = "unknown"
            source = "unknown"
        written.append(item)
        if source == "identity" and field_name in owner_cols:
            stamped = "yes"
            qual = f"{cls.name}.{field_name}"
            if qual not in owners:
                owners.append(qual)
            if binding_name and binding_name not in idents:
                idents.append(binding_name)
    if stamped == "yes" and not idents:
        stamped = "unknown"
        owners = []
    if stamped == "no" and not written:
        stamped = "unknown"
    return written, stamped, owners, idents


def _kwargs(text: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    depth = 0
    buf: list[str] = []
    parts: list[str] = []
    for char in text:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        if char == "," and depth == 1:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(char)
    if buf:
        parts.append("".join(buf))
    for part in parts:
        match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$", part, re.S)
        if match:
            found.append((match.group(1), " ".join(match.group(2).split())))
    return found


def _value_source(field_name: str, rhs: str, entry_names: set[str], binding_names: set[str], owner_cols: set[str]):
    if _CONST_RHS.match(rhs):
        return "constant", None, None
    ident = _IDENTITY_RHS.match(rhs)
    if ident and ident.group(1) in binding_names:
        return "identity", None, ident.group(1)
    if rhs in entry_names:
        return "request_param", rhs, None
    if "." in rhs:
        obj, attr = rhs.split(".", 1)
        if attr in entry_names:
            return "request_param", attr, None
        if obj in entry_names and attr == field_name:
            return "request_param", obj, None
    return "unknown", None, None


def _update_stamp(code: str, analysis: RouteAnalysis, route: RouteFact, owners: list[str]):
    if ".values" not in code and "values(" not in code:
        return "unknown", []
    if re.search(r"\.values\s*\(\s*\*\*", code):
        return "unknown", []
    return "unknown", []


def _flows(code: str, aliases: dict[str, str], route: RouteFact) -> list[ParamFlowFact]:
    entry = {param.name: param for param in route.entry_params}
    found: list[ParamFlowFact] = []
    seen: set[tuple[str, str]] = set()
    for match in _FLOW_RE.finditer(code):
        recv, field, rhs = match.group(1), match.group(2), match.group(3)
        cls = aliases.get(recv, recv)
        qual = f"{cls}.{field}"
        param_name = None
        confidence = "exact"
        if rhs in entry:
            param_name = rhs
        elif "." in rhs:
            attr = rhs.split(".", 1)[1]
            if attr in entry:
                param_name = attr
                confidence = "probable"
        if param_name is None:
            continue
        key = (param_name, qual)
        if key in seen:
            continue
        seen.add(key)
        found.append(ParamFlowFact(param_name, qual, confidence))
    return found


def _create_flows(written: list[WrittenFieldFact], route: RouteFact) -> list[ParamFlowFact]:
    flows: list[ParamFlowFact] = []
    for item in written:
        if item.source == "request_param" and item.entry_param_name:
            flows.append(ParamFlowFact(item.entry_param_name, item.field, "exact"))
    return flows


def _known_bindings(names: list[str], route: RouteFact) -> list[str]:
    have = {binding.name for binding in route.bindings}
    return [name for name in names if name in have]


def clip_snippet(text: str, limit: int) -> str:
    compact = text.strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit]
