"""One durable queue consumer for static graphs from anonymous GitHub checkouts."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from scan_api.workspace import Workspace, canonical_url
from scan_api.workspace_sandbox import SandboxError, export_confined


_MANIFEST_LIMIT = 20_000


def list_files(checkout) -> dict | None:
    """Tracked paths of the checkout, so the report can show the whole project tree."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(checkout), "ls-files", "-z"],
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    paths = sorted(path for path in completed.stdout.decode("utf-8", "replace").split("\0") if path)
    return {"paths": paths[:_MANIFEST_LIMIT], "total": len(paths), "truncated": len(paths) > _MANIFEST_LIMIT}


class BuildError(Exception):
    """A worker error suitable for the project owner."""


def _worker_environment(work: Path) -> dict[str, str]:
    # Anonymous Git and curl get a fresh home. Only the toolchain is inherited.
    home = work / "home"
    temp = work / "tmp"
    home.mkdir()
    temp.mkdir()
    return {
        **{key: os.environ[key] for key in ("JAVA_HOME", "JOERN_HOME") if key in os.environ},
        "PATH": os.pathsep.join(p for p in os.get_exec_path() if os.path.isabs(p)),
        "HOME": str(home),
        "TMPDIR": str(temp),
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "PYTHONNOUSERSITE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CEILING_DIRECTORIES": str(work.parent),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ALLOW_PROTOCOL": "https",
    }


def _prepare_source(repo: Path) -> None:
    # The manifest retains every tracked path. No parser may follow a submitted link.
    for parent, directories, files in os.walk(repo, followlinks=False):
        for name in list(directories):
            target = Path(parent, name)
            if target.is_symlink():
                target.unlink()
                directories.remove(name)
            elif target == repo / ".git":
                directories.remove(name)
        for name in files:
            target = Path(parent, name)
            # Bun's bundled AST generator can read project-local runtime settings.
            # Keep those tracked names in the manifest, outside the parser's input.
            name_lower = name.lower()
            if target.is_symlink() or name_lower in {"bunfig.toml", ".env"} or name_lower.startswith(".env."):
                target.unlink()
            elif os.access(target, os.X_OK):
                # Git's regular-file modes are 100644 and 100755. Parsers only need read access.
                target.chmod(0o644)


def export_checkout(url: str, work: Path) -> dict:
    url = canonical_url(url)
    checkout = work / "source" / url.rsplit("/", 1)[1]
    checkout.parent.mkdir()
    try:
        subprocess.run(
            ["git", "-c", "http.followRedirects=false", "clone", "--template=", "--depth=1",
             "--single-branch", "--no-tags", "--no-recurse-submodules", "--", url, str(checkout)],
            cwd=work, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=180,
        )
        git = ["git", "-C", str(checkout)]
        sha = subprocess.check_output([*git, "rev-parse", "--verify", "HEAD"], text=True).strip()
        branch = subprocess.check_output([*git, "symbolic-ref", "--short", "HEAD"], text=True).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise BuildError("Could not read the public GitHub repository. Check its URL, visibility, and default branch, then retry.") from exc

    manifest = list_files(checkout)
    if manifest is None:
        raise BuildError("Could not record the repository file list.")
    _prepare_source(checkout)
    graph = export_confined(checkout, work)
    if graph["repo"].get("remote") != url or graph["repo"].get("revision") != sha:
        raise BuildError("The exported graph does not match the checked-out revision.")
    return {"branch": branch, "files": manifest, "graph": graph}


def build_graph(url: str, work: Path, stop: threading.Event) -> dict:
    # The worker process and its Git/Joern children share a process group. A
    # shutdown or deadline stops all of them before their private files go away.
    process = subprocess.Popen(
        [sys.executable, "-m", "scan_api.workspace_worker", url],
        env=_worker_environment(work), cwd=work, start_new_session=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 30 * 60
    try:
        while process.poll() is None:
            if stop.wait(0.25):
                raise InterruptedError("Workspace worker stopped.")
            if time.monotonic() >= deadline:
                raise BuildError("The graph build exceeded 30 minutes. Retry with a smaller repository.")
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
    if process.returncode:
        error = work / "error.txt"
        raise BuildError(error.read_text() if error.is_file() else "The static graph exporter failed. Check the local Joern and Java installation, then retry.")
    return json.loads((work / "result.json").read_bytes())


class WorkspaceWorker:
    def __init__(self, store: Workspace, build=build_graph):
        self.store = store
        self.build = build
        self.wake = threading.Event()
        self.stop = threading.Event()
        self.work = store.root / "jobs"

    def start(self) -> None:
        self.lock = (self.store.root / "worker.lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Only the process holding the lock can recover unfinished builds.
            self.work.mkdir(exist_ok=True)
            for leftover in self.work.glob("job-*"):
                if leftover.is_dir() and not leftover.is_symlink():
                    shutil.rmtree(leftover)
            self.store.recover()
            self.stop.clear()
            self.thread = threading.Thread(target=self._loop, name="atlas-workspace", daemon=True)
            self.thread.start()
        except BaseException:
            self.lock.close()
            raise

    def close(self) -> None:
        self.stop.set()
        self.wake.set()
        self.thread.join()
        self.lock.close()

    def _loop(self) -> None:
        while not self.stop.is_set():
            self.wake.clear()
            job = self.store.claim()
            if job is None:
                if not self.stop.is_set():
                    self.wake.wait()
                continue
            try:
                with tempfile.TemporaryDirectory(prefix="job-", dir=self.work) as directory:
                    result = self.build(job["repository"], Path(directory), self.stop)
                self.store.complete(job["id"], result)
            except InterruptedError:
                if self.stop.is_set():
                    return
                self.store.fail(job["id"], "The graph build was interrupted. Retry the scan.")
            except BuildError as exc:
                self.store.fail(job["id"], str(exc))
            except Exception:
                logging.exception("Static graph build failed for project %s", job["id"])
                self.store.fail(job["id"], "The scan worker could not save a graph. Retry the scan.")


if __name__ == "__main__":
    work_dir = Path.cwd()
    try:
        result = export_checkout(sys.argv[1], work_dir)
        (work_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    except (BuildError, SandboxError) as error:
        (work_dir / "error.txt").write_text(str(error), encoding="utf-8")
        sys.exit(1)
