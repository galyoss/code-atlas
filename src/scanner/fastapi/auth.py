"""Auth steps for a FastAPI route: router dependencies, handler Depends, inline checks."""

from __future__ import annotations

import re

from scanner.facts import AuthStepFact, RouteFact
from scanner.fastapi.calls import build_calls
from scanner.fastapi.predicates import instance_owner_compare
from scanner.fastapi.routes import RouteAnalysis, _ensure_function_symbol, is_auth_callable
from scanner.project import Project

_SKIP_CALLS = {"build_auth_context", "build_metadata_filter"}


def read_auth_steps(project: Project, route: RouteFact) -> list[AuthStepFact]:
    analysis: RouteAnalysis = route.analysis
    steps: list[AuthStepFact] = []
    seen: set[str] = set()
    for qual in analysis.mount_deps:
        if qual in seen:
            continue
        seen.add(qual)
        step = _dependency_step(project, route, analysis, qual, "router")
        if step is not None:
            steps.append(step)
    for binding in route.bindings:
        qual = binding.produced_by_qualname
        if not qual or qual in seen:
            continue
        seen.add(qual)
        step = _dependency_step(project, route, analysis, qual, "route")
        if step is not None:
            steps.append(step)
    steps.extend(_inline_steps(project, route, analysis))
    steps.extend(_called_steps(project, route, analysis))
    return steps


def _dependency_step(
    project: Project,
    route: RouteFact,
    analysis: RouteAnalysis,
    qual: str,
    scope: str,
) -> AuthStepFact | None:
    func = project.index.functions_by_qual.get(qual)
    if func is None:
        return None
    _ensure_function_symbol(project.index, qual, route.symbols)
    kind, binds = _classify_function(project, func, analysis.class_or_alias | _alias_names(project, func.module))
    if kind == "authentication" and binds == "yes":
        kind = "authorization"
    calls, expanded = build_calls(func, project, route.symbols, analysis.budget)
    if expanded == "partial" and calls:
        calls[-1].omission = calls[-1].omission or (
            "node_budget",
            f"Stopped expanding {func.name} after maxCallNodes.",
        )
    snippet, truncated = project.index.snippet(
        func.file, func.line, func.end_line, project.limits.max_snippet_chars
    )
    method = project.overlay.method_for(func.file, func.name, func.line)
    end_line = method.end_line if method is not None else func.end_line
    return AuthStepFact(
        key=f"dep:{qual}",
        symbol_key=qual,
        qualname=qual,
        file=func.file,
        start=func.line,
        end=max(end_line, func.line),
        kind=kind,
        mechanism="dependency",
        scope=scope,
        applicability="always",
        on_failure=_on_failure(project, func),
        binds_object_to_caller=binds,
        expanded=expanded,
        calls=calls if expanded != "no" else [],
        call_key=None,
        snippet=snippet or func.signature,
        snippet_truncated=truncated,
    )


def _inline_steps(project: Project, route: RouteFact, analysis: RouteAnalysis) -> list[AuthStepFact]:
    steps: list[AuthStepFact] = []
    used_lines: set[int] = set()
    classes = analysis.class_or_alias
    for call in analysis.overlay_calls:
        if call.name not in {"<operator>.equals", "<operator>.notEquals"}:
            continue
        if call.line in used_lines:
            continue
        if not instance_owner_compare(call.code, classes):
            continue
        used_lines.add(call.line)
        wrapped = any(
            other.line == call.line
            and other.name == "<operator>.logicalAnd"
            and " and " in other.code
            for other in analysis.overlay_calls
        )
        end = call.line
        failed = False
        for other in analysis.overlay_calls:
            if call.line <= other.line <= call.line + 2 and (
                other.name in {"HTTPException", "<operator>.raise"} or other.code.lstrip().startswith("raise ")
            ):
                failed = True
                end = max(end, other.line)
        snippet, truncated = project.index.snippet(
            call.file, call.line, end, project.limits.max_snippet_chars
        )
        steps.append(
            AuthStepFact(
                key=f"inline:{call.file}:{call.line}",
                symbol_key=route.handler_symbol_key,
                qualname=route.handler_qualname,
                file=call.file,
                start=call.line,
                end=end,
                kind="authorization",
                mechanism="inline",
                scope="inline",
                applicability="conditional" if wrapped else "always",
                on_failure="abort" if failed else "unknown",
                binds_object_to_caller="yes",
                expanded="yes",
                calls=[],
                call_key=None,
                snippet=snippet or call.code,
                snippet_truncated=truncated,
            )
        )
    return steps


def _called_steps(project: Project, route: RouteFact, analysis: RouteAnalysis) -> list[AuthStepFact]:
    steps: list[AuthStepFact] = []
    for node in route.call_graph:
        if node.callee_name in _SKIP_CALLS or not _is_auth_call(node.callee_name):
            continue
        if node.symbol_key is None:
            continue
        func = project.index.functions_by_qual.get(node.symbol_key)
        if func is None:
            continue
        _ensure_function_symbol(project.index, func.qualname, route.symbols)
        classes = analysis.class_or_alias | _alias_names(project, func.module)
        _kind, binds = _classify_function(project, func, classes)
        if binds == "no" and _delegates(project, func):
            binds = "unknown"
        snippet, truncated = project.index.snippet(
            node.file, node.line, node.end_line, project.limits.max_snippet_chars
        )
        steps.append(
            AuthStepFact(
                key=f"call:{node.key}",
                symbol_key=func.qualname,
                qualname=func.qualname,
                file=func.file,
                start=func.line,
                end=max(func.end_line, func.line),
                kind="authorization",
                mechanism="inline",
                scope="inline",
                applicability="always",
                on_failure="unknown" if binds == "unknown" else _on_failure(project, func),
                binds_object_to_caller=binds,
                expanded="partial" if binds == "unknown" else "yes",
                calls=[],
                call_key=node.key,
                snippet=snippet or node.excerpt,
                snippet_truncated=truncated,
            )
        )
    return steps


def _is_auth_call(name: str) -> bool:
    if name in _SKIP_CALLS:
        return False
    if name == "handle_event":
        return True
    return is_auth_callable(name)


def _alias_names(project: Project, module: str) -> set[str]:
    aliases = project.index.alias_map(module)
    return set(aliases) | set(aliases.values())


def _classify_function(project: Project, func, classes: set[str]) -> tuple[str, str]:
    calls = _body_calls(project, func)
    blob = "\n".join(call.code for call in calls)
    compared = any(instance_owner_compare(call.code, classes) for call in calls)
    if compared:
        return "authorization", "yes"
    if _delegates(project, func) or re.search(r"\bhandle_event\s*\(", blob):
        if is_auth_callable(func.name) or func.name == "handle_event":
            return "authorization", "unknown"
        return "authentication", "unknown"
    return "authentication", "no"


def _delegates(project: Project, func) -> bool:
    for call in _body_calls(project, func):
        if call.name == "handle_event":
            return True
        if call.name == "handler" and not call.code.lstrip().startswith("def "):
            head = re.sub(r"^\s*await\s+", "", call.code.strip()).split("(", 1)[0]
            if head.strip() in {"handler", "await handler"} or head.strip().endswith("handler"):
                if "." not in head.replace("await ", ""):
                    return True
    return False


def _on_failure(project: Project, func) -> str:
    for call in _body_calls(project, func):
        if call.name in {"HTTPException", "<operator>.raise"} or call.code.lstrip().startswith("raise "):
            return "abort"
    return "unknown"


def _body_calls(project: Project, func):
    method = project.overlay.method_for(func.file, func.name, func.line)
    if method is None:
        return []
    return project.overlay.by_caller.get(method.full_name, [])
