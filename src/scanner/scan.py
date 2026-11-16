"""Scan a repository into a code-graph document.

The FastAPI command calls this. A later framework passes a different adapter
to `read_project` without changing the writer.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scanner import __version__
from scanner.facts import Limits, RepoFact
from scanner.fastapi import FastAPIAdapter
from scanner.framework import read_project
from scanner.joern_runner import build_overlay
from scanner.overlay import load_overlay_file
from scanner.project import Project
from scanner.schema_writer import write_document
from scanner.source_index import load_index


def export_repository(
    repo: Path,
    *,
    limits: Limits | None = None,
    overlay_path: Path | None = None,
    cpg_path: Path | None = None,
    joern_home: Path | None = None,
    cache: bool = True,
) -> dict:
    """Scan `repo` with the FastAPI adapter and return a schema document."""
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
