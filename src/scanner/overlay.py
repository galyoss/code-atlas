"""In-memory view of the Joern overlay JSON."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MethodRec:
    full_name: str
    name: str
    file: str
    line: int
    end_line: int


@dataclass
class CallRec:
    name: str
    method_full_name: str
    code: str
    file: str
    line: int
    caller: str
    dispatch: str
    ordinal: int


def relativize(file_name: str, repo: Path) -> str | None:
    if not file_name or file_name in {"<empty>", "<unknown>"}:
        return None
    raw = file_name.replace("\\", "/")
    path = Path(raw)
    repo_res = repo.resolve()
    if path.is_absolute():
        try:
            rel = path.resolve().relative_to(repo_res)
        except (OSError, ValueError):
            try:
                rel = Path(raw).relative_to(repo_res)
            except ValueError:
                return None
    else:
        rel = path
    text = rel.as_posix()
    if text.startswith("../") or text == ".." or "/../" in f"/{text}":
        return None
    return text


class Overlay:
    def __init__(self, methods: list[MethodRec], calls: list[CallRec]) -> None:
        self.methods = methods
        self.calls = calls
        self.by_caller: dict[str, list[CallRec]] = defaultdict(list)
        self.methods_by_full: dict[str, MethodRec] = {}
        self.methods_by_file: dict[str, list[MethodRec]] = defaultdict(list)
        for method in methods:
            self.methods_by_full[method.full_name] = method
            self.methods_by_file[method.file].append(method)
        for call in calls:
            self.by_caller[call.caller].append(call)
        for bucket in self.methods_by_file.values():
            bucket.sort(key=lambda item: (item.line, item.name))
        for bucket in self.by_caller.values():
            bucket.sort(key=lambda item: (item.line, item.ordinal))

    def method_for(self, file: str, name: str, line: int) -> MethodRec | None:
        best: MethodRec | None = None
        best_dist = 10**9
        for method in self.methods_by_file.get(file, []):
            if method.name != name or method.name.startswith("<"):
                continue
            dist = abs(method.line - line)
            if dist < best_dist:
                best = method
                best_dist = dist
        if best is not None and best_dist <= 5:
            return best
        return None


def load_overlay(payload: dict, repo: Path) -> Overlay:
    methods: list[MethodRec] = []
    for item in payload.get("methods", []):
        rel = relativize(item.get("file") or "", repo)
        if rel is None:
            continue
        name = item.get("name") or ""
        if name.startswith("<") and name != "<module>":
            continue
        end_line = int(item.get("endLine") or -1)
        line = int(item.get("line") or -1)
        if line < 1:
            continue
        if end_line < line:
            end_line = line
        methods.append(
            MethodRec(
                full_name=item.get("fullName") or "",
                name=name,
                file=rel,
                line=line,
                end_line=end_line,
            )
        )
    calls: list[CallRec] = []
    for ordinal, item in enumerate(payload.get("calls", [])):
        rel = relativize(item.get("file") or "", repo)
        if rel is None:
            continue
        line = int(item.get("line") or -1)
        if line < 1:
            continue
        calls.append(
            CallRec(
                name=item.get("name") or "",
                method_full_name=item.get("methodFullName") or "",
                code=item.get("code") or "",
                file=rel,
                line=line,
                caller=item.get("caller") or "",
                dispatch=item.get("dispatch") or "",
                ordinal=ordinal,
            )
        )
    return Overlay(methods, calls)


def load_overlay_file(path: Path, repo: Path) -> Overlay:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return load_overlay(payload, repo)
