"""Pick one framework adapter for a repository.

Rails wins when a Gemfile depends on Rails and `config/routes.rb` is present.
Express wins when `package.json` depends on Express and a source file calls
`app.use`, `router.METHOD`, or `express.Router`. Anything else stays on the
FastAPI adapter. One repository uses one adapter.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from scanner.express.adapter import ExpressAdapter
from scanner.fastapi.adapter import FastAPIAdapter
from scanner.framework import FrameworkAdapter
from scanner.rails.adapter import RailsAdapter

_RAILS_GEM = re.compile(r"""^\s*gem\s+['"]rails['"]""", re.M)
_EXPRESS_USE = re.compile(
    r"""\b(?:app|router)\s*\.\s*(?:use|get|post|put|patch|delete|head|options|all)\s*\(|\bexpress\s*\.\s*Router\s*\("""
)
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


def select_adapter(repo: Path) -> FrameworkAdapter:
    if looks_like_rails(repo):
        return RailsAdapter()
    if looks_like_express(repo):
        return ExpressAdapter()
    return FastAPIAdapter()


def looks_like_rails(repo: Path) -> bool:
    gemfile = repo / "Gemfile"
    routes = repo / "config" / "routes.rb"
    if not gemfile.is_file() or not routes.is_file():
        return False
    try:
        text = gemfile.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    return _RAILS_GEM.search(text) is not None


def looks_like_express(repo: Path) -> bool:
    package = repo / "package.json"
    if not package.is_file():
        return False
    try:
        payload = json.loads(package.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    deps: dict = {}
    if isinstance(payload, dict):
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            block = payload.get(key)
            if isinstance(block, dict):
                deps.update(block)
    if "express" not in deps:
        return False
    for path in _source_files(repo):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if _EXPRESS_USE.search(text):
            return True
    return False


def _source_files(repo: Path) -> list[Path]:
    found: list[Path] = []
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".js", ".mjs", ".cjs", ".jsx"}:
            continue
        if any(part in _SKIP for part in path.relative_to(repo).parts):
            continue
        found.append(path)
    found.sort()
    return found
