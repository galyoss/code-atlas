"""`scan-api` process. Binds HOST and PORT, default 0.0.0.0:8080."""

from __future__ import annotations

from scan_api.server import serve


def main() -> None:
    server = serve()
    host, port = server.server_address[:2]
    print(f"scan-api listening on http://{host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
