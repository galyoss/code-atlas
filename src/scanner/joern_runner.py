"""Run pysrc2cpg and the overlay script. Missing binaries are reported, not faked."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from scanner.overlay import Overlay, load_overlay_file
from scanner.source_index import EXCLUDE_DIRS, iter_python_files

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
    frontend: str = "python",
) -> Overlay:
    """Return the overlay for `repo`, running Joern when an overlay file was not supplied."""
    home = _home_for(joern_home, frontend)
    work = _work_dir(repo, home, cache, frontend)
    work.mkdir(parents=True, exist_ok=True)
    overlay_path = work / "overlay.json"
    cpg = Path(cpg_path) if cpg_path is not None else work / "cpg.bin"
    need_cpg = cpg_path is None and not (cache and cpg.is_file())
    if need_cpg:
        if frontend == "python":
            _run_pysrc2cpg(home, repo, cpg)
        else:
            _run_src2cpg(home, repo, cpg, frontend)
    need_overlay = cpg_path is not None or need_cpg or not (cache and overlay_path.is_file())
    if need_overlay:
        _run_script(home, cpg, overlay_path, work)
    return load_overlay_file(overlay_path, repo)


_FRONTEND_NAMES = {
    "python": ("pysrc2cpg",),
    "javascript": ("jssrc2cpg", "jssrc2cpg.sh"),
    "ruby": ("rubysrc2cpg", "rubysrc2cpg.sh"),
}
_FRONTEND_MISSING = {
    "javascript": (
        "jssrc2cpg is required to scan Express. It ships with Joern 4.0.684 next to pysrc2cpg "
        "(jssrc2cpg or jssrc2cpg.sh). Set JOERN_HOME to the joern-cli directory."
    ),
    "ruby": (
        "rubysrc2cpg is required to scan Rails. It ships with Joern 4.0.684 next to pysrc2cpg. "
        "Set JOERN_HOME to the joern-cli directory."
    ),
}


def frontend_available(frontend: str, explicit: Path | None = None) -> bool:
    """True when `joern` and the language frontend for `frontend` are installed."""
    try:
        _home_for(explicit, frontend)
    except JoernNotFound:
        return False
    return True


def _frontend_binary(home: Path, frontend: str) -> Path | None:
    for name in _FRONTEND_NAMES.get(frontend, (frontend,)):
        found = _binary(home, name)
        if found is not None:
            return found
    return None


def _home_for(explicit: Path | None, frontend: str) -> Path:
    home = find_home(explicit)
    if home is None:
        home = _joern_home(explicit)
    if home is None or _binary(home, "joern") is None:
        raise JoernNotFound(INSTALL)
    if _frontend_binary(home, frontend) is None:
        raise JoernNotFound(_FRONTEND_MISSING.get(frontend, INSTALL))
    return home


def _joern_home(explicit: Path | None) -> Path | None:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    env = os.environ.get("JOERN_HOME")
    if env:
        candidates.append(Path(env))
    found = shutil.which("joern")
    if found:
        candidates.append(Path(found).resolve().parent)
    candidates.append(Path("/tmp/joern-dist/joern-cli"))
    for path in candidates:
        if _binary(path, "joern") is not None:
            return path
    return None


def _work_dir(repo: Path, home: Path, cache: bool, frontend: str = "python") -> Path:
    if not cache:
        return Path(os.environ.get("TMPDIR", "/tmp")) / f"export-fastapi-{os.getpid()}"
    digest = hashlib.sha256()
    digest.update(str(home).encode())
    digest.update(frontend.encode())
    digest.update(_SCRIPT.read_bytes())
    for path in _input_files(repo, frontend):
        rel = path.relative_to(repo).as_posix()
        stat = path.stat()
        digest.update(rel.encode())
        digest.update(str(stat.st_mtime_ns).encode())
        digest.update(str(stat.st_size).encode())
    root = Path.home() / ".cache" / "export-fastapi"
    return root / digest.hexdigest()[:24]


def _input_files(repo: Path, frontend: str) -> list[Path]:
    if frontend == "python":
        return iter_python_files(repo)
    suffixes = {".js", ".mjs", ".cjs", ".jsx"} if frontend == "javascript" else {".rb"}
    found: list[Path] = []
    for path in repo.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        if any(part in EXCLUDE_DIRS or part in {"vendor", "tmp", "log", "storage", "coverage"} for part in path.relative_to(repo).parts):
            continue
        found.append(path)
    found.sort()
    return found


def _run_src2cpg(home: Path, repo: Path, cpg: Path, frontend: str) -> None:
    binary = _frontend_binary(home, frontend)
    if binary is None:
        raise JoernNotFound(_FRONTEND_MISSING.get(frontend, INSTALL))
    command = [str(binary), str(repo), "-o", str(cpg)]
    for name in ("node_modules", "vendor", "tmp", "dist", "build", "coverage", ".git", "storage", "log"):
        command.extend(["--exclude", name])
    completed = subprocess.run(command, cwd=cpg.parent, capture_output=True, text=True)
    if completed.returncode != 0 or not cpg.is_file():
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"{binary.name} failed ({completed.returncode}). {detail[-2000:]}")


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
