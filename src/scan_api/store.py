"""In-memory scan records mirrored to JSON files beside the process."""

from __future__ import annotations

import copy
import json
import threading
import uuid
from pathlib import Path


def new_scan_id() -> str:
    return f"scan_{uuid.uuid4().hex}"


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._load()

    def create(self, job: dict) -> dict:
        with self._lock:
            self._jobs[job["id"]] = copy.deepcopy(job)
            self._write(job["id"])
            return copy.deepcopy(self._jobs[job["id"]])

    def update(self, scan_id: str, **fields) -> dict:
        with self._lock:
            job = self._jobs[scan_id]
            job.update(fields)
            self._write(scan_id)
            return copy.deepcopy(job)

    def get(self, scan_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(scan_id)
            if job is None:
                return None
            if job.get("graph") is None:
                graph_path = self._graph_path(scan_id)
                if graph_path.is_file():
                    job["graph"] = json.loads(graph_path.read_text(encoding="utf-8"))
            return copy.deepcopy(job)

    def summary(self, scan_id: str) -> dict | None:
        """The record without its graph, so polling does not read the document."""
        with self._lock:
            job = self._jobs.get(scan_id)
            return None if job is None else self._without_graph(job)

    def summaries(self) -> list[dict]:
        with self._lock:
            return [self._without_graph(job) for job in self._jobs.values()]

    def _without_graph(self, job: dict) -> dict:
        meta = copy.deepcopy({key: value for key, value in job.items() if key != "graph"})
        meta["hasGraph"] = isinstance(job.get("graph"), dict) or self._graph_path(job["id"]).is_file()
        return meta

    def _write(self, scan_id: str) -> None:
        job = self._jobs[scan_id]
        meta = {key: value for key, value in job.items() if key != "graph"}
        meta["hasGraph"] = isinstance(job.get("graph"), dict)
        _atomic_json(self._meta_path(scan_id), meta)
        graph_path = self._graph_path(scan_id)
        if isinstance(job.get("graph"), dict):
            _atomic_json(graph_path, job["graph"])
        elif graph_path.exists():
            graph_path.unlink()

    def _load(self) -> None:
        if not self.root.is_dir():
            return
        for path in sorted(self.root.glob("scan_*.json")):
            if path.name.endswith(".graph.json"):
                continue
            meta = json.loads(path.read_text(encoding="utf-8"))
            scan_id = meta.get("id")
            if not isinstance(scan_id, str):
                continue
            meta["graph"] = None
            meta.pop("hasGraph", None)
            self._jobs[scan_id] = meta

    def _meta_path(self, scan_id: str) -> Path:
        return self.root / f"{scan_id}.json"

    def _graph_path(self, scan_id: str) -> Path:
        return self.root / f"{scan_id}.graph.json"


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
