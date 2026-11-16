"""JavaScript function ranges. Joern keeps the calls; this keeps the bodies."""

from __future__ import annotations

import re
from pathlib import Path

from scanner.expand import Body

_SKIP = {
    ".git",
    "node_modules",
    "vendor",
    "tmp",
    "dist",
    "build",
    "coverage",
    ".next",
    "storage",
    "log",
}
_FUNC = re.compile(r"(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{")
_ARROW = re.compile(
    r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>\s*\{"
)
_APP = re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*express\s*\(\s*\)")
_ROUTER = re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*express\s*\.\s*Router\s*\(")
_CLASS = re.compile(r"\bclass\s+([A-Z][A-Za-z0-9_]*)\b")


class JsIndex:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.functions: list[Body] = []
        self.classes: list[Body] = []
        self.apps: set[str] = {"app"}
        self.routers: set[str] = {"router"}

    def functions_named(self, file: str, name: str) -> list[Body]:
        return [item for item in self.functions if item.file == file and item.name == name]

    def function_named(self, name: str, file: str | None = None) -> Body | None:
        matches = [
            item
            for item in self.functions
            if item.name == name and (file is None or item.file == file)
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    def snippet(self, file: str, start: int, end: int, limit: int) -> tuple[str, bool]:
        lines = self.files.get(file, "").splitlines()
        if start < 1:
            start = 1
        if end < start:
            end = start
        raw = "\n".join(lines[start - 1 : end]).strip("\n")
        if not raw:
            return "", False
        if len(raw) <= limit:
            return raw, False
        return raw[:limit], True


def load_js(repo: Path) -> JsIndex:
    index = JsIndex()
    for path in _files(repo):
        rel = path.relative_to(repo).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        index.files[rel] = text
        module = _module(rel)
        index.apps.update(_APP.findall(text))
        index.routers.update(_ROUTER.findall(text))
        for match in _FUNC.finditer(text):
            index.functions.append(_body(module, rel, text, match, "function"))
        for match in _ARROW.finditer(text):
            index.functions.append(_body(module, rel, text, match, "function"))
        for match in _CLASS.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            name = match.group(1)
            index.classes.append(
                Body(
                    name=name,
                    qualname=f"{module}.{name}",
                    file=rel,
                    line=line,
                    end_line=line,
                    signature=f"class {name}",
                    kind="class",
                    text="",
                )
            )
    return index


def _files(repo: Path) -> list[Path]:
    found: list[Path] = []
    for path in repo.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".js", ".mjs", ".cjs", ".jsx"}:
            continue
        if any(part in _SKIP for part in path.relative_to(repo).parts):
            continue
        found.append(path)
    found.sort()
    return found


def _module(rel: str) -> str:
    stem = rel[: -len(".js")] if rel.endswith(".js") else rel.rsplit(".", 1)[0]
    parts = [part for part in stem.split("/") if part and part != "index"]
    return ".".join(parts) or "app"


def _body(module: str, rel: str, text: str, match: re.Match[str], kind: str) -> Body:
    name = match.group(1)
    params = match.group(2).strip()
    close = _closing_brace(text, match.end() - 1)
    start = text.count("\n", 0, match.start()) + 1
    end = text.count("\n", 0, close) + 1
    signature = f"function {name}({params})"
    if len(signature) > 300:
        signature = signature[:297] + "..."
    return Body(
        name=name,
        qualname=f"{module}.{name}",
        file=rel,
        line=start,
        end_line=max(end, start),
        signature=signature,
        kind=kind,
        text=text[match.start() : close + 1],
    )


def _closing_brace(text: str, open_at: int) -> int:
    if open_at >= len(text) or text[open_at] != "{":
        return open_at
    depth = 0
    quote = ""
    index = open_at
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index)
            index = len(text) if newline < 0 else newline + 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
            index += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return len(text) - 1
