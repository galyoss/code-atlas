"""Call trees from Joern, used by the FastAPI adapter.

The schema writer only sees `CallFact`. It does not resolve Python calls.
"""

from __future__ import annotations

import builtins
import re
from dataclasses import dataclass, field

from scanner.facts import CallFact, Limits, SymbolFact
from scanner.overlay import CallRec, Overlay
from scanner.project import Project
from scanner.source_index import FuncInfo, SourceIndex

_AWAIT = re.compile(r"^\s*await\s+")
_SELECT = re.compile(r"\b(select|query)\s*\(")
_WRITE = re.compile(r"\b(update|delete|insert|pg_insert)\s*\(")
_SESSION_WRITE = re.compile(r"\.(add|add_all|commit|flush|merge|delete)\s*\(")
# A bare name the index cannot resolve is a builtin, not a runtime-computed target.
_BUILTINS = frozenset(name for name in dir(builtins) if not name.startswith("_"))


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


def clip(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def touches_of(name: str, code: str) -> str:
    if _SESSION_WRITE.search(code) or name in {"add", "add_all", "commit", "flush", "merge"}:
        return "write"
    if _WRITE.search(code) and not _SELECT.search(code):
        return "write"
    if name in {"where", "filter", "select", "scalar", "scalars", "query"} or _SELECT.search(code):
        return "read"
    if name == "execute":
        return "write" if _WRITE.search(code) else "read"
    return "none"


def combine_touches(left: str, right: str) -> str:
    if "unknown" in {left, right} and "none" in {left, right}:
        return "unknown"
    kinds = {left, right} - {"none"}
    if not kinds:
        return "none"
    if "unknown" in kinds and len(kinds) == 1:
        return "unknown"
    kinds.discard("unknown")
    if "read_write" in kinds or kinds >= {"read", "write"}:
        return "read_write"
    return next(iter(kinds))


def is_emitted_call(call: CallRec) -> bool:
    return bool(call.name) and not call.name.startswith("<")


def _head(code: str) -> str:
    return _AWAIT.sub("", code.strip()).split("(", 1)[0]


def _is_attribute(call: CallRec) -> bool:
    head = _head(call.code)
    if re.search(r"\." + re.escape(call.name) + r"\s*$", head) is not None:
        return True
    # A chained call such as select(X).where(...) is a method on the previous result.
    name = re.escape(call.name)
    code = _AWAIT.sub("", (call.code or "").strip())
    return re.match(name + r"\s*\(", code) is None and re.search(r"[)\]]\s*\.\s*" + name + r"\s*\(", code) is not None


def _symbol_for_function(index: SourceIndex, qual: str, symbols: dict[str, SymbolFact]) -> None:
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


def _symbol_for_class(index: SourceIndex, qual: str, symbols: dict[str, SymbolFact]) -> None:
    cls = index.classes_by_qual.get(qual)
    if cls is None:
        return
    symbols.setdefault(
        qual,
        SymbolFact(
            key=qual,
            language="python",
            kind="class",
            name=cls.name,
            qualname=qual,
            signature=cls.signature[:300],
            file=cls.file,
            start=cls.line,
            end=max(cls.end_line, cls.line),
        ),
    )


def resolve_call(
    call: CallRec,
    module: str,
    index: SourceIndex,
    overlay: Overlay,
    symbols: dict[str, SymbolFact],
) -> tuple[str, str | None, list[str] | None, str]:
    """Return resolution, symbol key, candidates, and a qualified name."""
    if not _is_attribute(call):
        resolved = index.resolve_name(module, call.name)
        if resolved is None:
            if call.name in _BUILTINS:
                return "external", None, None, f"builtins.{call.name}"
            return "ambiguous", None, [], call.name
        kind, qual = resolved
        if kind == "function":
            _symbol_for_function(index, qual, symbols)
            return "resolved", qual, None, qual
        if kind == "class":
            _symbol_for_class(index, qual, symbols)
            return "resolved", qual, None, qual
        return "external", None, None, qual
    method = overlay.methods_by_full.get(call.method_full_name)
    if method is not None and index.module_for_file(method.file) is not None:
        func = index.function_at(method.file, method.name, method.line)
        if func is not None:
            _symbol_for_function(index, func.qualname, symbols)
            return "resolved", func.qualname, None, func.qualname
    qual = _external_name(call)
    return "external", None, None, qual


def _external_name(call: CallRec) -> str:
    full = call.method_full_name or ""
    if full and not full.startswith("<") and "unknown" not in full.lower():
        cleaned = full.split(":")[-1]
        cleaned = cleaned.replace("<module>.", "")
        if cleaned and len(cleaned) <= 200:
            return cleaned
    head = _head(call.code).strip()
    if head and len(head) <= 200:
        return head
    return call.name


def _function_calls(overlay: Overlay, func: FuncInfo) -> list[CallRec]:
    method = overlay.method_for(func.file, func.name, func.line)
    if method is None:
        return []
    return [call for call in overlay.by_caller.get(method.full_name, []) if is_emitted_call(call)]


def build_calls(
    func: FuncInfo,
    project: Project,
    symbols: dict[str, SymbolFact],
    budget: Budget,
    stack: tuple[str, ...] = (),
    depth: int = 1,
) -> tuple[list[CallFact], str]:
    """Expand `func` one level. The returned status is the parent's expanded value."""
    if func.qualname in stack:
        return [], "no"
    calls = _function_calls(project.overlay, func)
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
            _node_for(
                call,
                func.module,
                project,
                symbols,
                budget,
                stack + (func.qualname,),
                depth,
                index,
            )
        )
    if stopped:
        return nodes, "partial"
    return nodes, "yes"


def _node_for(
    call: CallRec,
    module: str,
    project: Project,
    symbols: dict[str, SymbolFact],
    budget: Budget,
    stack: tuple[str, ...],
    depth: int,
    ordinal: int,
) -> CallFact:
    resolution, symbol_key, candidates, qual = resolve_call(
        call, module, project.index, project.overlay, symbols
    )
    touches = touches_of(call.name, call.code)
    children: list[CallFact] = []
    expanded = "no"
    omission: tuple[str, str] | None = None
    kind = None
    if symbol_key and resolution == "resolved":
        func = project.index.functions_by_qual.get(symbol_key)
        cls = project.index.classes_by_qual.get(symbol_key)
        if cls is not None and func is None:
            expanded = "yes"
        elif func is None:
            expanded = "no"
            resolution = "external"
            symbol_key = None
            qual = _external_name(call)
        elif func.qualname in stack:
            expanded = "no"
            omission = ("cycle", f"Stopped at {func.qualname} because it is already on the expansion path.")
        elif depth >= budget.limits.max_call_depth:
            expanded = "no"
            omission = ("depth", f"Did not open {func.qualname} because the call is at maxCallDepth.")
        else:
            children, expanded = build_calls(func, project, symbols, budget, stack, depth + 1)
            if expanded == "partial":
                omission = ("node_budget", f"Stopped expanding {func.qualname} after maxCallNodes.")
            elif expanded == "no" and func.qualname in stack:
                omission = ("cycle", f"Stopped at {func.qualname} because it is already on the expansion path.")
            for child in children:
                touches = combine_touches(touches, child.touches)
    elif resolution == "ambiguous":
        expanded = "no"
        if candidates:
            omission = ("ambiguity", f"Did not open {call.name} because more than one in-repo function matches.")
        else:
            omission = ("dynamic_dispatch", f"Did not open {call.name} because the target is computed at runtime.")
    else:
        expanded = "no"
        kind = "external"
    if resolution == "external":
        kind = "external"
    node = CallFact(
        key=f"{call.file}:{call.line}:{call.name}:{ordinal}:{call.ordinal}",
        callee_name=call.name[:120],
        qualname=(qual or call.name)[:200],
        resolution=resolution,
        symbol_key=symbol_key if resolution == "resolved" else None,
        candidates=candidates if resolution == "ambiguous" else None,
        touches=touches,
        expanded=expanded if resolution != "external" else "no",
        file=call.file,
        line=call.line,
        end_line=call.line,
        excerpt=clip(call.code, 240),
        code=call.code,
        children=children if expanded != "no" else [],
        omission=omission,
    )
    if resolution == "external":
        node.children = []
        node.expanded = "no"
        node.symbol_key = None
        node.candidates = None
    if node.expanded == "no":
        node.children = []
    _ = kind
    return node


def walk(nodes: list[CallFact]) -> list[CallFact]:
    found: list[CallFact] = []
    for node in nodes:
        found.append(node)
        found.extend(walk(node.children))
    return found
