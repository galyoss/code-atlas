"""Auth steps for one Express route: `app.use` middleware, then route middleware."""

from __future__ import annotations

from scanner.expand import build_calls, remember
from scanner.express.routes import ExpressAnalysis
from scanner.facts import AuthStepFact, RouteFact
from scanner.ownership import classify_hook, on_failure
from scanner.project import Project


def read_auth_steps(project: Project, route: RouteFact) -> list[AuthStepFact]:
    analysis: ExpressAnalysis = route.analysis
    steps: list[AuthStepFact] = []
    seen: set[str] = set()
    for fn in analysis.middleware:
        if fn.qualname in seen:
            continue
        seen.add(fn.qualname)
        classified = classify_hook(fn.name, fn.text)
        if classified is None:
            continue
        kind, binds = classified
        remember(fn, route.symbols, "javascript")
        calls, expanded = build_calls(
            fn,
            project,
            analysis.by_full,
            analysis.by_name,
            route.symbols,
            analysis.budget,
            language="javascript",
        )
        if expanded == "partial" and calls:
            calls[-1].omission = calls[-1].omission or (
                "node_budget",
                f"Stopped expanding {fn.name} after maxCallNodes.",
            )
        snippet, truncated = _snippet(fn.text, project.limits.max_snippet_chars)
        steps.append(
            AuthStepFact(
                key=f"mw:{fn.qualname}",
                symbol_key=fn.qualname,
                qualname=fn.qualname,
                file=fn.file,
                start=fn.line,
                end=max(fn.end_line, fn.line),
                kind=kind,
                mechanism="middleware",
                scope="application" if fn.file == route.registration_file else "router",
                applicability="always",
                on_failure=on_failure(fn.text),
                binds_object_to_caller=binds,
                expanded=expanded,
                calls=calls if expanded != "no" else [],
                call_key=None,
                snippet=snippet or fn.signature,
                snippet_truncated=truncated,
            )
        )
    return steps


def _snippet(text: str, limit: int) -> tuple[str, bool]:
    raw = (text or "").strip("\n")
    if len(raw) <= limit:
        return raw, False
    return raw[:limit], True
