"""export-fastapi command.

The command builds a project, passes FastAPIAdapter to read_project, and then
stays on the framework-agnostic side: write the schema document and validate it.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from export_fastapi import __version__
from export_fastapi.facts import Limits, RepoFact
from export_fastapi.fastapi import FastAPIAdapter
from export_fastapi.framework import read_project
from export_fastapi.joern_runner import JoernNotFound, build_overlay
from export_fastapi.overlay import load_overlay_file
from export_fastapi.project import Project
from export_fastapi.schema_writer import write_document
from export_fastapi.source_index import load_index
from export_fastapi.validate import validate_document

_DEFAULT_SCHEMA = Path(__file__).resolve().parents[2] / "docs" / "code-graph-schema.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="export-fastapi", description="Export FastAPI routes to a code-graph document.")
    parser.add_argument("repo", type=Path, help="Repository to scan")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Where to write the JSON document")
    parser.add_argument("--schema", type=Path, default=_DEFAULT_SCHEMA, help="Schema 1.0.0 file")
    parser.add_argument("--overlay", type=Path, help="Existing Joern overlay JSON. Skips pysrc2cpg and joern.")
    parser.add_argument("--cpg", type=Path, help="Existing CPG. Skips pysrc2cpg and still runs the overlay script.")
    parser.add_argument("--joern-home", type=Path, help="Directory that contains pysrc2cpg and joern")
    parser.add_argument("--max-call-depth", type=int, default=4)
    parser.add_argument("--max-call-nodes", type=int, default=400)
    parser.add_argument("--max-snippet-chars", type=int, default=480)
    parser.add_argument("--no-cache", action="store_true", help="Do not reuse a cached CPG or overlay")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    if not repo.is_dir():
        print(f"Not a directory: {repo}", file=sys.stderr)
        return 2
    limits = Limits(
        max_call_depth=args.max_call_depth,
        max_call_nodes=args.max_call_nodes,
        max_snippet_chars=min(args.max_snippet_chars, 480),
    )
    try:
        document = export_repository(
            repo,
            limits=limits,
            overlay_path=args.overlay,
            cpg_path=args.cpg,
            joern_home=args.joern_home,
            cache=not args.no_cache,
        )
    except JoernNotFound as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    errors = validate_document(document, args.schema)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output} routes={len(document['routes'])} symbols={len(document['symbolIndex'])}")
    if errors:
        print(f"{len(errors)} schema error(s):", file=sys.stderr)
        for error in errors[:40]:
            print(error, file=sys.stderr)
        return 1
    return 0


def export_repository(
    repo: Path,
    *,
    limits: Limits | None = None,
    overlay_path: Path | None = None,
    cpg_path: Path | None = None,
    joern_home: Path | None = None,
    cache: bool = True,
) -> dict:
    """Scan `repo` and return a schema document. Does not validate it."""
    limits = limits or Limits()
    if overlay_path is not None:
        overlay = load_overlay_file(overlay_path, repo)
    else:
        overlay = build_overlay(repo, joern_home=joern_home, cpg_path=cpg_path, cache=cache)
    project = Project(repo=repo, index=load_index(repo), overlay=overlay, limits=limits)
    routes = read_project(FastAPIAdapter(), project)
    return write_document(routes, _repo_fact(repo), limits, generator_version=__version__)


def _repo_fact(repo: Path) -> RepoFact:
    name = _repo_name(repo.name)
    revision = _git(repo, ["rev-parse", "HEAD"])
    remote = _https_remote(_git(repo, ["remote", "get-url", "origin"]) or "")
    if revision:
        return RepoFact(name=name, revision=revision[:80], vcs="git", remote=remote)
    return RepoFact(name=name, revision="unknown", vcs="unknown", remote=remote)


def _repo_name(name: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "._-" else "-" for char in name).strip("-._")
    if not cleaned or not cleaned[0].isalnum():
        cleaned = "repo"
    return cleaned[:80]


def _git(repo: Path, args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    text = completed.stdout.strip()
    return text or None


def _https_remote(url: str) -> str | None:
    text = url.strip()
    if not text:
        return None
    if text.startswith("git@") and ":" in text:
        host, path = text[4:].split(":", 1)
        text = f"https://{host}/{path}"
    elif text.startswith("ssh://"):
        rest = text[len("ssh://") :]
        if rest.startswith("git@"):
            rest = rest[4:]
        text = "https://" + rest
    if text.startswith("http://") or text.startswith("https://"):
        return text[:300]
    return None


if __name__ == "__main__":
    raise SystemExit(main())
