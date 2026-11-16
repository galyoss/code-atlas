"""FastAPI path templates. Only the FastAPI adapter imports this."""

from __future__ import annotations

import re

_PATH_PARAM = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?::[^}]*)?\}")
_SCHEMA_PATH = re.compile(
    r"^/(?:(?:[A-Za-z0-9._~-]+|\{[A-Za-z_][A-Za-z0-9_]*\})(?:/(?:[A-Za-z0-9._~-]+|\{[A-Za-z_][A-Za-z0-9_]*\}))*)?$"
)


def normalize_path(path: str) -> str:
    raw = (path or "").strip()
    if raw in {"", "/"}:
        return "/"
    if not raw.startswith("/"):
        raw = "/" + raw
    raw = _PATH_PARAM.sub(r"{\1}", raw)
    raw = re.sub(r"//+", "/", raw)
    if len(raw) > 1 and raw.endswith("/"):
        raw = raw[:-1]
    return raw or "/"


def join_paths(*parts: str) -> str:
    acc = ""
    for part in parts:
        if not part:
            continue
        piece = str(part).strip()
        if piece in {"", "/"}:
            continue
        acc = piece if not acc else acc.rstrip("/") + "/" + piece.lstrip("/")
    return normalize_path(acc)


def is_schema_path(path: str) -> bool:
    return _SCHEMA_PATH.fullmatch(path or "") is not None
