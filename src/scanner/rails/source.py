"""Ruby class and method ranges. Joern keeps the calls; this keeps the bodies."""

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
    "storage",
    "log",
}
_CLASS = re.compile(r"^\s*class\s+([A-Z]\w*(?:::[A-Z]\w*)*)")
_DEF = re.compile(r"^\s*def\s+(?:self\.)?([A-Za-z_][\w?!]*)")
_OPEN = re.compile(r"^\s*(class|module|def|if|unless|case|while|until|for|begin)\b")
_DO = re.compile(r"\bdo\b")
_END = re.compile(r"\bend\b")


class RubyIndex:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.methods: list[Body] = []
        self.classes: list[Body] = []

    def method_named(self, file: str, class_name: str, name: str) -> Body | None:
        matches = [
            item
            for item in self.methods
            if item.file == file and item.name == name and item.qualname.endswith(f".{class_name}.{name}")
        ]
        if len(matches) == 1:
            return matches[0]
        named = [item for item in self.methods if item.file == file and item.name == name]
        if len(named) == 1:
            return named[0]
        return None

    def class_named(self, name: str) -> Body | None:
        matches = [item for item in self.classes if item.name == name or item.name.endswith("::" + name)]
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


def load_ruby(repo: Path) -> RubyIndex:
    index = RubyIndex()
    for path in _files(repo):
        rel = path.relative_to(repo).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        index.files[rel] = text
        module = ".".join(part for part in rel[:-3].split("/") if part) if rel.endswith(".rb") else rel
        classes, methods = _parse(rel, module, text)
        index.classes.extend(classes)
        index.methods.extend(methods)
    return index


def _files(repo: Path) -> list[Path]:
    found: list[Path] = []
    for path in repo.rglob("*.rb"):
        if any(part in _SKIP for part in path.relative_to(repo).parts):
            continue
        found.append(path)
    found.sort()
    return found


def _parse(rel: str, module: str, text: str) -> tuple[list[Body], list[Body]]:
    lines = text.splitlines()
    classes: list[Body] = []
    pending: list[tuple[str, int, int]] = []
    for index, line in enumerate(lines):
        code = _code_line(line)
        match = _CLASS.match(code)
        if match is None:
            continue
        end = _block_end(lines, index)
        name = match.group(1)
        short = name.split("::")[-1]
        signature = code.strip()
        classes.append(
            Body(
                name=short,
                qualname=f"{module}.{name}",
                file=rel,
                line=index + 1,
                end_line=end,
                signature=signature[:300],
                kind="class",
                text="\n".join(lines[index:end]),
            )
        )
        pending.append((name, index + 1, end))
    methods: list[Body] = []
    for index, line in enumerate(lines):
        code = _code_line(line)
        match = _DEF.match(code)
        if match is None:
            continue
        end = _block_end(lines, index)
        line_no = index + 1
        name = match.group(1)
        owner = _owner(pending, line_no)
        qual = f"{module}.{owner}.{name}" if owner else f"{module}.{name}"
        methods.append(
            Body(
                name=name,
                qualname=qual,
                file=rel,
                line=line_no,
                end_line=end,
                signature=code.strip()[:300],
                kind="method",
                text="\n".join(lines[index:end]),
            )
        )
    return classes, methods


def _owner(classes: list[tuple[str, int, int]], line: int) -> str | None:
    matches = [item for item in classes if item[1] <= line <= item[2]]
    if not matches:
        return None
    name = min(matches, key=lambda item: item[2] - item[1])[0]
    return name.split("::")[-1]


def _block_end(lines: list[str], start: int) -> int:
    depth = 0
    for index in range(start, len(lines)):
        code = _code_line(lines[index])
        if _OPEN.match(code):
            depth += 1
        if _DO.search(code):
            depth += 1
        depth -= len(_END.findall(code))
        if index > start and depth <= 0:
            return index + 1
    return len(lines)


def _code_line(line: str) -> str:
    text = re.sub(r'"(?:\\.|[^"\\])*"', '""', line)
    text = re.sub(r"'(?:\\.|[^'\\])*'", "''", text)
    comment = text.find("#")
    if comment >= 0:
        text = text[:comment]
    return text
