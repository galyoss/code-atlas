"""Model loads shared by the Express and Rails adapters.

The call's own text decides `inPredicate`. This module does not look past a
bare argument and call it a yes.
"""

from __future__ import annotations

import re

from scanner.expand import Body
from scanner.facts import CallFact, DataAccessFact, ParamFlowFact, RouteFact, SymbolFact
from scanner.ownership import LOAD_VERBS, model_and_verb, predicate_from_call

_JS_FLOW = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*req\.params\.([A-Za-z_][A-Za-z0-9_]*)")
_RB_FLOW = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*params\[:([A-Za-z_][A-Za-z0-9_]*)\]")
_BY_ID = re.compile(r"findById\s*\(\s*req\.params\.([A-Za-z_][A-Za-z0-9_]*)\s*\)")


def _walk(nodes: list[CallFact]) -> list[CallFact]:
    found: list[CallFact] = []
    for node in nodes:
        found.append(node)
        found.extend(_walk(node.children))
    return found


def read_model_accesses(
    route: RouteFact,
    *,
    classes: dict[str, Body],
    language: str,
    limit: int,
) -> list[DataAccessFact]:
    found: list[DataAccessFact] = []
    seen: set[str] = set()
    for node in _walk(route.call_graph):
        parsed = model_and_verb(node.code or node.excerpt)
        if parsed is None or parsed[1] != node.callee_name:
            continue
        model, verb = parsed
        if node.key in seen:
            continue
        seen.add(node.key)
        decision, owners, idents = predicate_from_call(node.code or "", verb, model)
        if decision != "yes":
            owners = []
            idents = []
        operation = "load" if verb in LOAD_VERBS or (verb == "find" and "{" not in (node.code or "")) else "query"
        symbol_key = None
        cls = classes.get(model)
        if cls is not None:
            symbol_key = cls.qualname
            route.symbols.setdefault(
                cls.qualname,
                SymbolFact(
                    key=cls.qualname,
                    language=language,
                    kind="class",
                    name=cls.name[:120],
                    qualname=cls.qualname[:200],
                    signature=(cls.signature or cls.name)[:300],
                    file=cls.file,
                    start=max(cls.line, 1),
                    end=max(cls.end_line, cls.line, 1),
                ),
            )
        bindings = {binding.name for binding in route.bindings}
        snippet = (node.code or node.excerpt or "").strip()
        truncated = len(snippet) > limit
        if truncated:
            snippet = snippet[:limit]
        found.append(
            DataAccessFact(
                key=f"da:{node.key}",
                call_key=node.key,
                operation=operation,
                persistence_api="orm",
                object_name=model,
                object_symbol_key=symbol_key,
                store=None,
                param_flows=_flows(node.code or "", model, route),
                in_predicate=decision,
                stamped_on_write="not_applicable",
                owner_fields=owners,
                identity_names=[name for name in idents if name in bindings] if decision == "yes" else [],
                written_fields=[],
                snippet=snippet,
                snippet_file=node.file,
                snippet_start=node.line,
                snippet_end=node.line,
                snippet_truncated=truncated,
            )
        )
    return found


def _flows(code: str, model: str, route: RouteFact) -> list[ParamFlowFact]:
    entry = {param.name for param in route.entry_params}
    found: list[ParamFlowFact] = []
    seen: set[tuple[str, str]] = set()

    def add(param: str, field: str) -> None:
        if param not in entry:
            return
        qual = f"{model}.{field}"
        if (param, qual) in seen:
            return
        seen.add((param, qual))
        found.append(ParamFlowFact(param, qual, "exact"))

    for field, param in _JS_FLOW.findall(code):
        add(param, field)
    for field, param in _RB_FLOW.findall(code):
        add(param, field)
    by_id = _BY_ID.search(code)
    if by_id:
        add(by_id.group(1), "id")
    return found
