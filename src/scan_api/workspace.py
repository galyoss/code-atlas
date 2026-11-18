"""Persistent local account, session, project and graph data."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from scan_api.access import AccessError, parse_github_url

SESSION_SECONDS = 30 * 24 * 3600
_PROJECT_COLUMNS = "id, repository, scan_id, created, status, progress, error, branch, sha"


class WorkspaceError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def canonical_url(value: object) -> str:
    try:
        if isinstance(value, str) and len(value) <= 2048:
            return parse_github_url(value.lower())[0]
    except AccessError:
        pass
    raise WorkspaceError(422, "Enter a public GitHub repository URL such as https://github.com/owner/repo.")


def _credentials(payload: dict) -> tuple[str, bytes]:
    email = payload.get("email")
    password = payload.get("password")
    if not isinstance(email, str) or len(email) > 254 or not email.isascii():
        raise WorkspaceError(400, "Enter a valid email address.")
    email = email.strip().lower()
    if not re.fullmatch(r"[^\s@\x00-\x1f\x7f]+@[^\s@\x00-\x1f\x7f]+\.[^\s@\x00-\x1f\x7f]+", email):
        raise WorkspaceError(400, "Enter a valid email address.")
    if not isinstance(password, str) or not 10 <= len(password) <= 128:
        raise WorkspaceError(400, "Use a password with 10 to 128 characters.")
    try:
        return email, password.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise WorkspaceError(400, "Enter a valid password.") from exc


def _password_hash(password: bytes, salt: bytes) -> bytes:
    return hashlib.scrypt(password, salt=salt, n=2**15, r=8, p=1, maxmem=64 * 1024**2)


def _session_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def _project(row: sqlite3.Row) -> dict:
    ready = row["status"] == "completed"
    return {
        "id": row["id"],
        "repositoryUrl": row["repository"],
        "scan": {
            "id": row["scan_id"], "repositoryUrl": row["repository"], "createdAt": row["created"],
            "status": row["status"], "progress": row["progress"], "error": row["error"],
            "revision": row["branch"], "resolvedRevision": row["sha"] or "",
            "hasGraph": ready, "hasFiles": ready, "inProgress": row["status"] in ("queued", "running"),
            "reviewing": False, "model": "", "agentCount": 0, "agreementThreshold": 0,
            "votes": [], "findings": [],
        },
    }


class Workspace:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.path = self.root / "workspace.sqlite3"

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("PRAGMA foreign_keys = ON")
                yield db
        finally:
            db.close()

    def initialize(self) -> None:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, salt BLOB NOT NULL, password_hash BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash BLOB PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id), expires INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id), repository TEXT NOT NULL,
                    scan_id TEXT NOT NULL UNIQUE, created TEXT NOT NULL, status TEXT NOT NULL,
                    progress TEXT NOT NULL, error TEXT, branch TEXT, sha TEXT, UNIQUE(owner, repository)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    project_id TEXT PRIMARY KEY REFERENCES projects(id), graph TEXT NOT NULL, files TEXT NOT NULL
                );
            """)

    def authenticate(self, payload: dict, *, register: bool) -> tuple[dict, str]:
        email, password = _credentials(payload)
        with self.connect() as db:
            if register:
                owner = uuid.uuid4().hex
                salt = secrets.token_bytes(16)
                digest = _password_hash(password, salt)
                try:
                    db.execute("INSERT INTO users VALUES (?,?,?,?)", (owner, email, salt, digest))
                except sqlite3.IntegrityError as exc:
                    raise WorkspaceError(409, "An account with this email already exists.") from exc
            else:
                row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
                digest = _password_hash(password, row["salt"] if row else bytes(16))
                if row is None or not hmac.compare_digest(row["password_hash"], digest):
                    raise WorkspaceError(401, "Email or password is incorrect.")
                owner = row["id"]
            token = secrets.token_urlsafe(32)
            now = int(time.time())
            db.execute("DELETE FROM sessions WHERE expires <= ?", (now,))
            db.execute("INSERT INTO sessions VALUES (?,?,?)", (_session_hash(token), owner, now + SESSION_SECONDS))
        return {"id": owner, "email": email}, token

    def user(self, token: str | None) -> dict | None:
        if not token:
            return None
        with self.connect() as db:
            row = db.execute("""
                SELECT users.id, users.email FROM users JOIN sessions ON sessions.owner = users.id
                WHERE token_hash = ? AND expires > ?
            """, (_session_hash(token), int(time.time()))).fetchone()
        return dict(row) if row else None

    def logout(self, token: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (_session_hash(token),))

    def projects(self, owner: str) -> list[dict]:
        with self.connect() as db:
            return [_project(row) for row in db.execute(
                f"SELECT {_PROJECT_COLUMNS} FROM projects WHERE owner = ? ORDER BY created DESC, rowid DESC", (owner,)
            )]

    def _owned(self, db, owner: str, project_id: str) -> sqlite3.Row:
        row = db.execute(f"SELECT {_PROJECT_COLUMNS} FROM projects WHERE owner = ? AND id = ?", (owner, project_id)).fetchone()
        if row is None:
            raise WorkspaceError(404, "Project not found.")
        return row

    def project(self, owner: str, project_id: str) -> dict:
        with self.connect() as db:
            return _project(self._owned(db, owner, project_id))

    def create(self, owner: str, repository: str) -> dict:
        with self.connect() as db:
            db.execute("""
                INSERT INTO projects (id, owner, repository, scan_id, created, status, progress)
                VALUES (?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'queued', 'Queued.')
                ON CONFLICT(owner, repository) DO NOTHING
            """, (uuid.uuid4().hex, owner, repository, "scan_" + uuid.uuid4().hex))
            row = db.execute(f"SELECT {_PROJECT_COLUMNS} FROM projects WHERE owner = ? AND repository = ?", (owner, repository)).fetchone()
            return _project(row)

    def retry(self, owner: str, project_id: str) -> dict:
        with self.connect() as db:
            changed = db.execute("""
                UPDATE projects SET scan_id = ?, status = 'queued', progress = 'Queued.', error = NULL,
                    sha = NULL, branch = NULL, created = strftime('%Y-%m-%dT%H:%M:%fZ','now')
                WHERE owner = ? AND id = ? AND status = 'failed'
            """, ("scan_" + uuid.uuid4().hex, owner, project_id))
            row = self._owned(db, owner, project_id)
            if not changed.rowcount:
                raise WorkspaceError(409, "Only a failed scan can be retried.")
            return _project(row)

    def artifact(self, owner: str, project_id: str, *, files: bool) -> str:
        field = "files" if files else "graph"
        with self.connect() as db:
            row = db.execute(f"""
                SELECT artifacts.{field} FROM projects LEFT JOIN artifacts ON artifacts.project_id = projects.id
                WHERE projects.owner = ? AND projects.id = ?
            """, (owner, project_id)).fetchone()
            if row is None:
                raise WorkspaceError(404, "Project not found.")
            if row[0] is None:
                raise WorkspaceError(409, "The scan has no saved " + ("file list." if files else "graph."))
            return row[0]

    def recover(self) -> None:
        with self.connect() as db:
            db.execute("UPDATE projects SET status = 'queued', progress = 'Resuming interrupted scan.' WHERE status = 'running'")

    def claim(self) -> sqlite3.Row | None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id, repository FROM projects WHERE status = 'queued' ORDER BY created, rowid LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE projects SET status = 'running', progress = 'Reading the public repository and building the static graph.' WHERE id = ?", (row["id"],))
            return row

    def complete(self, project_id: str, result: dict) -> None:
        graph = result["graph"]
        if graph.get("schemaVersion") != "1.0.0" or not re.fullmatch("[0-9a-f]{40}", graph["repo"]["revision"]):
            raise ValueError("Invalid graph identity.")
        with self.connect() as db:
            db.execute("INSERT INTO artifacts VALUES (?,?,?)", (project_id, json.dumps(graph), json.dumps(result["files"])))
            db.execute("""
                UPDATE projects SET status = 'completed', progress = 'Static graph ready. Vulnerability review was not run.',
                    branch = ?, sha = ? WHERE id = ?
            """, (result["branch"], graph["repo"]["revision"], project_id))

    def fail(self, project_id: str, error: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE projects SET status = 'failed', progress = 'Scan failed.', error = ? WHERE id = ?", (error, project_id))
