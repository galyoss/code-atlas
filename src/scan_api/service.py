"""Validate a scan request, export a graph, then review each route."""

from __future__ import annotations

import queue
import shutil
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path

from review.model import UnconfiguredModel, model_from_env
from review.runner import review_graph

from scanner.joern_runner import INSTALL, JoernNotFound, find_home
from scanner.scan import export_repository

from scan_api.access import AccessError, Revision, clone_at, list_files, parse_github_url, resolve_revision
from scan_api.store import Store, new_scan_id

_FIELDS = {"repositoryUrl", "revision", "model", "agentCount", "agreementThreshold"}
_COMPLETE = "Every route has a full vote set."
_INCOMPLETE = "Review did not finish a full vote set. The code graph is available."
_REVIEW_FAILED = "Review failed before finishing. The code graph is available."
_REVIEWING = "Reviewing routes."


class ConfigError(Exception):
    """The request cannot be scanned. The scan was not started."""


class ScanService:
    def __init__(
        self,
        store: Store,
        *,
        resolve=resolve_revision,
        clone=clone_at,
        export=export_repository,
        joern_home=find_home,
        model_client=None,
        manifest=list_files,
    ) -> None:
        self.store = store
        self._resolve = resolve
        self._clone = clone
        self._export = export
        self._joern_home = joern_home
        self._manifest = manifest
        self._model_client = model_client if model_client is not None else model_from_env()
        self._queue: queue.Queue[str] = queue.Queue()
        self._thread: threading.Thread | None = None
        # Jobs this process will still work on. A queued or running record outside
        # this set was interrupted by a restart and will not progress.
        self._pending: set[str] = set()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="scan-worker", daemon=True)
        self._thread.start()

    def create(self, payload: object) -> tuple[int, dict]:
        try:
            request = parse_request(payload)
            revision = self._resolve(request["repositoryUrl"], request["revision"])
        except ConfigError as exc:
            return 400, {"error": str(exc)}
        except AccessError as exc:
            return 422, {"error": str(exc)}
        if self._joern_home() is None:
            return 503, _joern_missing(revision, request)
        job = self.store.create(_job(revision, request))
        self._pending.add(job["id"])
        self._queue.put(job["id"])
        print(f"scan {job['id']} queued {job['repositoryUrl']}@{job['revision']}", flush=True)
        return 202, public_scan(job)

    def get(self, scan_id: str) -> tuple[int, dict]:
        job = self.store.get(scan_id)
        if job is None:
            return 404, {"error": "Scan not found."}
        return 200, public_scan(job)

    def summary(self, scan_id: str) -> tuple[int, dict]:
        job = self.store.summary(scan_id)
        if job is None:
            return 404, {"error": "Scan not found."}
        return 200, self._summary(job)

    def list(self) -> tuple[int, dict]:
        jobs = sorted(self.store.summaries(), key=lambda job: job.get("createdAt") or "", reverse=True)
        return 200, {"scans": [self._summary(job) for job in jobs]}

    def review_status(self) -> tuple[int, dict]:
        if isinstance(self._model_client, UnconfiguredModel):
            return 200, {"configured": False, "detail": self._model_client.reason}
        return 200, {"configured": True, "detail": "A model provider is configured for review."}

    def _summary(self, job: dict) -> dict:
        summary = public_scan(job)
        del summary["graph"]
        in_progress = job["id"] in self._pending
        summary.update(
            createdAt=job.get("createdAt"),
            hasFiles=isinstance(job.get("files"), dict),
            hasGraph=job["hasGraph"] and job["status"] in {"partial", "completed"},
            inProgress=in_progress,
            reviewing=in_progress and job["status"] == "partial" and job["progress"] == _REVIEWING,
        )
        return summary

    def files(self, scan_id: str) -> tuple[int, dict]:
        job = self.store.summary(scan_id)
        if job is None:
            return 404, {"error": "Scan not found."}
        manifest = job.get("files")
        if not isinstance(manifest, dict):
            return 409, {"error": f"Scan {scan_id} has no file list. Status is {job['status']}."}
        return 200, manifest

    def graph(self, scan_id: str) -> tuple[int, dict]:
        job = self.store.get(scan_id)
        if job is None:
            return 404, {"error": "Scan not found."}
        document = job.get("graph")
        if not isinstance(document, dict):
            return 409, {
                "error": f"Scan {scan_id} has no graph yet. Status is {job['status']}. {job['progress']}"
            }
        return 200, document

    def execute(self, scan_id: str) -> None:
        job = self.store.get(scan_id)
        if job is None or job["status"] not in {"queued", "running"}:
            return
        work = self.store.root / "work" / scan_id
        try:
            self.store.update(scan_id, status="running", progress="Cloning the repository.", error=None)
            self._clone(job["repositoryUrl"], job["resolvedRevision"], work)
            # The tree is context for the report, so a failed listing never fails the scan.
            self.store.update(scan_id, files=self._manifest(Path(work)))
            self.store.update(scan_id, progress="Running the FastAPI scanner.")
            document = self._export(Path(work))
            if not isinstance(document, dict) or document.get("schemaVersion") != "1.0.0":
                raise RuntimeError("The scanner did not return a schema 1.0.0 document.")
        except (JoernNotFound, OSError, RuntimeError) as exc:
            self.store.update(
                scan_id,
                status="failed",
                progress="Scan failed.",
                error=str(exc),
                graph=None,
                votes=[],
                findings=[],
            )
            print(f"scan {scan_id} failed: {exc}", flush=True)
            return
        finally:
            if work.exists():
                shutil.rmtree(work, ignore_errors=True)
        self._review(scan_id, job, document)

    def _review(self, scan_id: str, job: dict, document: dict) -> None:
        self.store.update(
            scan_id,
            status="partial",
            progress=_REVIEWING,
            error=None,
            graph=document,
            votes=[],
            findings=[],
        )
        try:
            result = review_graph(
                document,
                model=job["model"],
                agent_count=job["agentCount"],
                agreement_threshold=job["agreementThreshold"],
                client=self._model_client,
            )
        except Exception as exc:
            self.store.update(
                scan_id,
                status="partial",
                progress=_REVIEW_FAILED,
                error=None,
                graph=document,
                votes=[],
                findings=[],
            )
            print(f"scan {scan_id} partial: {exc}", flush=True)
            return
        status = "completed" if result.complete else "partial"
        self.store.update(
            scan_id,
            status=status,
            progress=_COMPLETE if result.complete else _INCOMPLETE,
            error=None,
            graph=document,
            votes=result.votes,
            findings=result.findings,
        )
        print(f"scan {scan_id} {status}", flush=True)

    def _loop(self) -> None:
        while True:
            scan_id = self._queue.get()
            try:
                self.execute(scan_id)
            except Exception:
                traceback.print_exc()
                job = self.store.get(scan_id)
                if job is not None and isinstance(job.get("graph"), dict):
                    self.store.update(scan_id, status="partial", progress=_REVIEW_FAILED, error=None)
                else:
                    self.store.update(
                        scan_id,
                        status="failed",
                        progress="Scan failed.",
                        error="The scan worker failed before producing a graph.",
                        graph=None,
                    )
            finally:
                self._pending.discard(scan_id)
                self._queue.task_done()


def parse_request(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ConfigError("Request body must be a JSON object. The scan was not started.")
    unknown = sorted(set(payload) - _FIELDS)
    if unknown:
        raise ConfigError(
            f"Unrecognized field(s): {', '.join(unknown)}. The scan was not started."
        )
    repository_url, _, _ = parse_github_url(payload.get("repositoryUrl"))
    if "model" not in payload or not isinstance(payload["model"], str) or not payload["model"].strip():
        raise ConfigError("model is required and must be a non-empty string. The scan was not started.")
    model = payload["model"].strip()
    if len(model) > 200:
        raise ConfigError("model must be 200 characters or fewer. The scan was not started.")
    if "revision" in payload and payload["revision"] is not None and not isinstance(payload["revision"], str):
        raise ConfigError("revision must be a string branch, tag, or commit SHA. The scan was not started.")
    agent_count = _integer(payload, "agentCount", 2)
    threshold = _integer(payload, "agreementThreshold", 2)
    if agent_count < 1:
        raise ConfigError("agentCount must be an integer of at least 1. The scan was not started.")
    if threshold < 1:
        raise ConfigError("agreementThreshold must be an integer of at least 1. The scan was not started.")
    if threshold > agent_count:
        raise ConfigError(
            f"agreementThreshold ({threshold}) is higher than agentCount ({agent_count}). "
            "That configuration can never reach agreement. The scan was not started."
        )
    return {
        "repositoryUrl": repository_url.strip(),
        "revision": payload.get("revision"),
        "model": model,
        "agentCount": agent_count,
        "agreementThreshold": threshold,
    }


def public_scan(job: dict) -> dict:
    graph = job.get("graph") if job["status"] in {"partial", "completed"} else None
    return {
        "id": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "error": job["error"],
        "repositoryUrl": job["repositoryUrl"],
        "revision": job["revision"],
        "resolvedRevision": job["resolvedRevision"],
        "model": job["model"],
        "agentCount": job["agentCount"],
        "agreementThreshold": job["agreementThreshold"],
        "graph": graph,
        "votes": job.get("votes") if isinstance(job.get("votes"), list) else [],
        "findings": job.get("findings") if isinstance(job.get("findings"), list) else [],
    }


def _integer(payload: dict, name: str, default: int) -> int:
    if name not in payload or payload[name] is None:
        return default
    value = payload[name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{name} must be an integer. The scan was not started.")
    return value


def _job(revision: Revision, request: dict) -> dict:
    return {
        "id": new_scan_id(),
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "status": "queued",
        "progress": "Queued.",
        "error": None,
        "repositoryUrl": revision.repository_url,
        "revision": revision.revision,
        "resolvedRevision": revision.resolved_sha,
        "model": request["model"],
        "agentCount": request["agentCount"],
        "agreementThreshold": request["agreementThreshold"],
        "graph": None,
        "votes": [],
        "findings": [],
    }


def _joern_missing(revision: Revision, request: dict) -> dict:
    return {
        "status": "failed",
        "progress": "pysrc2cpg is missing. No repository was cloned and no graph was produced.",
        "error": (
            "pysrc2cpg is not available, so the scan was not started. "
            f"{revision.repository_url} at {revision.revision} ({revision.resolved_sha}) "
            "was not cloned and no graph was produced. "
            f"{INSTALL}"
        ),
        "repositoryUrl": revision.repository_url,
        "revision": revision.revision,
        "resolvedRevision": revision.resolved_sha,
        "model": request["model"],
        "agentCount": request["agentCount"],
        "agreementThreshold": request["agreementThreshold"],
    }
