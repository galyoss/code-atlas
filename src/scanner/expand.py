"""Call trees for the Express and Rails adapters.

The FastAPI adapter keeps its own walker. This one reads the same overlay
and does not import a framework.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from scanner.facts import CallFact, Limits, SymbolFact
from scanner.overlay import CallRec
from scanner.project import Project

_READ = {"find", "findOne", "findById", "find_by", "find_by!", "where", "filter"}
_WRITE = {"save", "save!", "create", "create!", "update", "update!", "destroy", "destroy!", "delete", "delete_all", "insert"}
_EXTERNAL_BARE = {
    "require",
    "express",
    "console",
    "render",
    "redirect_to",
    "head",
    "puts",
    "raise",
    "fail",
    "logger",
    "json",
    "send",
}


@dataclass
class Budget:
    limits: Limits
    remaining: int
    omissions: list[tuple[str, str, str]] = field(default_factory=list)

    @classmethod
    def start(cls, limits: Limits) -> Budget:
        return cls(limits=limits, remaining=limits.max_call_nodes)

    def take(self) -> bool:
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        return True


@dataclass
class Body:
    name: str
    qualname: str
    file: str
    line: int
    end_line: int
    signature: str
    kind: str
    text: str
    full_name: str = ""


def clip(text: str, limit: int) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def touches_of(name: str) -> str:
    if name in _WRITE:
        return "write"
    if name in _READ:
        return "read"
    return "none"


def is_attribute(call: CallRec) -> bool:
    head = (call.code or "").split("(", 1)[0]
    return re.search(r"\." + re.escape(call.name) + r"\s*$", head) is not None


def remember(body: Body, symbols: dict[str, SymbolFact], language: str) -> None:
    symbols.setdefault(
        body.qualname,
        SymbolFact(
            key=body.qualname,
            language=language,
            kind="method" if body.kind == "method" else "function",
            name=body.name[:120],
            qualname=body.qualname[:200],
            signature=(body.signature or body.name)[:300],
            file=body.file,
            start=max(body.line, 1),
            end=max(body.end_line, body.line, 1),
        ),
    )


def build_calls(
    body: Body | None,
    project: Project,
    by_full: dict[str, Body],
    by_name: dict[str, list[Body]],
    symbols: dict[str, SymbolFact],
    budget: Budget,
    *,
    language: str,
    stack: tuple[str, ...] = (),
    depth: int = 1,
) -> tuple[list[CallFact], str]:
    if body is None or not body.full_name:
        return [], "yes"
    if body.qualname in stack:
        return [], "no"
    calls = [call for call in project.overlay.by_caller.get(body.full_name, []) if call.name and not call.name.startswith("<")]
    if not calls:
        return [], "yes"
    if depth > budget.limits.max_call_depth:
        return [], "no"
    nodes: list[CallFact] = []
    stopped = False
    for index, call in enumerate(calls):
        if not budget.take():
            stopped = True
            break
        nodes.append(
            _node(
                call,
                body,
                project,
                by_full,
                by_name,
                symbols,
                budget,
                language=language,
                stack=stack + (body.qualname,),
                depth=depth,
                ordinal=index,
            )
        )
    if stopped:
        return nodes, "partial"
    return nodes, "yes"


def _node(
    call: CallRec,
    caller: Body,
    project: Project,
    by_full: dict[str, Body],
    by_name: dict[str, list[Body]],
    symbols: dict[str, SymbolFact],
    budget: Budget,
    *,
    language: str,
    stack: tuple[str, ...],
    depth: int,
    ordinal: int,
) -> CallFact:
    resolution, target, candidates, qual = _resolve(call, caller, by_name, symbols, language)
    children: list[CallFact] = []
    expanded = "no"
    omission: tuple[str, str] | None = None
    if resolution == "resolved" and target is not None:
        if target.qualname in stack:
            expanded = "no"
            omission = ("cycle", f"Stopped at {target.name} because it is already on the expansion path.")
        elif depth >= budget.limits.max_call_depth:
            expanded = "no"
            omission = ("depth", f"Did not open {target.name} because the call is at maxCallDepth.")
        else:
            children, expanded = build_calls(
                target,
                project,
                by_full,
                by_name,
                symbols,
                budget,
                language=language,
                stack=stack,
                depth=depth + 1,
            )
            if expanded == "partial":
                omission = ("node_budget", f"Stopped expanding {target.name} after maxCallNodes.")
            elif expanded == "no" and not children and target.qualname in stack:
                omission = ("cycle", f"Stopped at {target.name} because it is already on the expansion path.")
    elif resolution == "ambiguous":
        expanded = "no"
        if candidates:
            omission = ("ambiguity", f"Did not open {call.name} because more than one in-repo function matches.")
        else:
            omission = ("dynamic_dispatch", f"Did not open {call.name} because the target is computed at runtime.")
    else:
        expanded = "no"
    node = CallFact(
        key=f"{caller.qualname}:{call.file}:{call.line}:{call.name}:{ordinal}:{call.ordinal}",
        callee_name=(call.name or "call")[:120],
        qualname=(qual or call.name or "call")[:200],
        resolution=resolution,
        symbol_key=target.qualname if resolution == "resolved" and target is not None else None,
        candidates=[item.qualname for item in candidates] if resolution == "ambiguous" else None,
        touches=touches_of(call.name),
        expanded="no" if resolution == "external" else expanded,
        file=call.file,
        line=call.line,
        end_line=call.line,
        excerpt=clip(call.code, 240),
        code=call.code,
        children=children if expanded != "no" and resolution != "external" else [],
        omission=omission,
    )
    if node.expanded == "no":
        node.children = []
    return node


def _resolve(
    call: CallRec,
    caller: Body,
    by_name: dict[str, list[Body]],
    symbols: dict[str, SymbolFact],
    language: str,
) -> tuple[str, Body | None, list[Body], str]:
    if is_attribute(call) or call.name in _EXTERNAL_BARE:
        return "external", None, [], _external_name(call)
    same_file = [item for item in by_name.get(call.name, []) if item.file == caller.file]
    pool = same_file or by_name.get(call.name, [])
    if len(pool) == 1:
        remember(pool[0], symbols, language)
        return "resolved", pool[0], [], pool[0].qualname
    if len(pool) > 1:
        for item in pool:
            remember(item, symbols, language)
        return "ambiguous", None, pool[:12], call.name
    return "ambiguous", None, [], call.name


def _external_name(call: CallRec) -> str:
    full = call.method_full_name or ""
    if full and not full.startswith("<") and "unknown" not in full.lower() and len(full) <= 200:
        return full
    head = (call.code or "").split("(", 1)[0].strip()
    if head and len(head) <= 200:
        return head
    return call.name or "call"
