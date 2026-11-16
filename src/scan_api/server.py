"""JSON HTTP server for scan jobs. There is no frontend."""

from __future__ import annotations

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from scan_api.service import ScanService
from scan_api.store import Store

_MAX_BODY = 65_536
_SCAN_ID = re.compile(r"^scan_[0-9a-f]{32}$")


def serve(host: str | None = None, port: int | None = None, service: ScanService | None = None) -> ThreadingHTTPServer:
    bind_host = host or os.environ.get("HOST", "0.0.0.0")
    bind_port = int(port if port is not None else os.environ.get("PORT", "8080"))
    if service is None:
        root = Path(os.environ.get("SCAN_DATA_DIR", "data/scans"))
        service = ScanService(Store(root))
        service.start()
    server = ThreadingHTTPServer((bind_host, bind_port), _handler(service))
    return server


def _handler(service: ScanService):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            if path == "/health":
                self._send(200, {"status": "ok"})
                return
            if path == "/":
                self._send(
                    200,
                    {
                        "service": "code-atlas-scan",
                        "endpoints": ["POST /scans", "GET /scans/{id}", "GET /scans/{id}/graph"],
                    },
                )
                return
            kind, scan_id = _match(path)
            if kind == "scan" and scan_id is not None:
                self._send(*service.get(scan_id))
                return
            if kind == "graph" and scan_id is not None:
                self._send(*service.graph(scan_id))
                return
            self._send(404, {"error": "Not found."})

        def do_POST(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            if path != "/scans":
                self._send(404, {"error": "Not found."})
                return
            length = self.headers.get("Content-Length")
            if length is None or not length.isdigit():
                self._send(400, {"error": "Content-Length is required. The scan was not started."})
                return
            size = int(length)
            if size > _MAX_BODY:
                self._send(413, {"error": "Request body is too large. The scan was not started."})
                return
            raw = self.rfile.read(size)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send(400, {"error": "Request body must be JSON. The scan was not started."})
                return
            self._send(*service.create(payload))

        def log_message(self, fmt: str, *args) -> None:
            print(f"{self.address_string()} {fmt % args}", flush=True)

        def _send(self, status: int, payload: dict) -> None:
            body = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def _match(path: str) -> tuple[str, str | None]:
    parts = [part for part in path.split("/") if part]
    if len(parts) == 2 and parts[0] == "scans" and _SCAN_ID.fullmatch(parts[1]):
        return "scan", parts[1]
    if len(parts) == 3 and parts[0] == "scans" and parts[2] == "graph" and _SCAN_ID.fullmatch(parts[1]):
        return "graph", parts[1]
    return "", None
