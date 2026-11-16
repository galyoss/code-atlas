"""`scan-api` process. Binds HOST and PORT, default 0.0.0.0:8080."""

from __future__ import annotations

import os

import uvicorn

from scan_api.server import app


def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    print(f"scan-api listening on http://{host}:{port}", flush=True)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
