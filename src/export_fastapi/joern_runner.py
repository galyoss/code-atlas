"""Run pysrc2cpg and the overlay script. Missing binaries are reported, not faked."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from export_fastapi.overlay import Overlay, load_overlay_file
from export_fastapi.source_index import EXCLUDE_DIRS, iter_python_files

INSTALL = (
    "Joern 4.0.684 is required. Download the archive for this machine from "
    "https://github.com/joernio/joern/releases/tag/v4.0.684 "
    "(macOS arm64: https://github.com/joernio/joern/releases/download/v4.0.684/joern-cli-macos-arm64.zip), "
    "unzip it, and set JOERN_HOME to the joern-cli directory. pysrc2cpg and joern live in that "
    "directory, not under bin/. Java 21 is required."
)

_SCRIPT = Path(__file__).with_name("export_overlay.sc")


class JoernNotFound(FileNotFoundError):
    """pysrc2cpg or joern is not on disk."""


def find_home(explicit: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    env = os.environ.get("JOERN_HOME")
    if env:
        candidates.append(Path(env))
    for name in ("pysrc2cpg", "joern"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found).resolve().parent)
    candidates.append(Path("/tmp/joern-dist/joern-cli"))
    for path in candidates:
        if _binary(path, "pysrc2cpg") is not None and _binary(path, "joern") is not None:
            return path
    return None


def _binary(home: Path, name: str) -> Path | None:
    for candidate in (home / name, home / "bin" / name):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def require_home(explicit: Path | None = None) -> Path:
    home = find_home(explicit)
    if home is None:
        raise JoernNotFound(INSTALL)
    return home


def build_overlay(
    repo: Path,
    *,
    joern_home: Path | None = None,
    cpg_path: Path | None = None,
    cache: bool = True,
) -> Overlay:
    """Return the overlay for `repo`, running Joern when an overlay file was not supplied."""
    home = require_home(joern_home)
    work = _work_dir(repo, home, cache)
    work.mkdir(parents=True, exist_ok=True)
    overlay_path = work / "overlay.json"
    cpg = Path(cpg_path) if cpg_path is not None else work / "cpg.bin"
    need_cpg = cpg_path is None and not (cache and cpg.is_file())
    if need_cpg:
        _run_pysrc2cpg(home, repo, cpg)
    need_overlay = cpg_path is not None or need_cpg or not (cache and overlay_path.is_file())
    if need_overlay:
        _run_script(home, cpg, overlay_path, work)
    return load_overlay_file(overlay_path, repo)


def _work_dir(repo: Path, home: Path, cache: bool) -> Path:
    if not cache:
        return Path(os.environ.get("TMPDIR", "/tmp")) / f"export-fastapi-{os.getpid()}"
    digest = hashlib.sha256()
    digest.update(str(home).encode())
    digest.update(_SCRIPT.read_bytes())
    for path in iter_python_files(repo):
        rel = path.relative_to(repo).as_posix()
        stat = path.stat()
        digest.update(rel.encode())
        digest.update(str(stat.st_mtime_ns).encode())
        digest.update(str(stat.st_size).encode())
    root = Path.home() / ".cache" / "export-fastapi"
    return root / digest.hexdigest()[:24]


def _run_pysrc2cpg(home: Path, repo: Path, cpg: Path) -> None:
    binary = _binary(home, "pysrc2cpg")
    if binary is None:
        raise JoernNotFound(INSTALL)
    ignored = ",".join(sorted(EXCLUDE_DIRS))
    command = [
        str(binary),
        str(repo),
        "-o",
        str(cpg),
        "--ignore-dir-names",
        ignored,
    ]
    completed = subprocess.run(command, cwd=cpg.parent, capture_output=True, text=True)
    if completed.returncode != 0 or not cpg.is_file():
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"pysrc2cpg failed ({completed.returncode}). {detail[-2000:]}")


def _run_script(home: Path, cpg: Path, overlay_path: Path, work: Path) -> None:
    binary = _binary(home, "joern")
    if binary is None:
        raise JoernNotFound(INSTALL)
    # Joern writes a workspace next to the process cwd. Keep that out of the repo.
    command = [
        str(binary),
        "--script",
        str(_SCRIPT),
        "--param",
        f"out={overlay_path}",
        str(cpg),
    ]
    completed = subprocess.run(command, cwd=work, capture_output=True, text=True)
    if completed.returncode != 0 or not overlay_path.is_file():
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"joern overlay script failed ({completed.returncode}). {detail[-2000:]}")
