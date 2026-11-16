"""Scan API validation, partial results, and the HTTP routes."""

import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from scan_api.access import AccessError, ProbeFailure, Revision, clone_at, parse_github_url, resolve_revision
from scan_api.server import serve
from scan_api.service import ScanService
from scan_api.store import Store

SHA = "a" * 40
OTHER = "d" * 40
TAG = "c" * 40
REFS = "\n".join(
    [
        "ref: refs/heads/main\tHEAD",
        f"{SHA}\tHEAD",
        f"{SHA}\trefs/heads/main",
        f"{'b' * 40}\trefs/tags/v1",
        f"{TAG}\trefs/tags/v1^{{}}",
        f"{OTHER}\trefs/heads/feature/x",
        "",
    ]
)
GRAPH = {
    "schemaVersion": "1.0.0",
    "routes": [],
    "unresolvedGaps": [{"id": "gap_llm_judge", "area": "other", "coverage": "unsupported"}],
}


def _service(tmp_path, *, joern=True, export=None, clone=None, resolve=None):
    def default_resolve(url, revision):
        return Revision("https://github.com/acme/app", "acme", "app", revision or "main", SHA)

    def default_clone(url, sha, dest: Path):
        dest.mkdir(parents=True, exist_ok=True)

    def default_export(path: Path):
        return json.loads(json.dumps(GRAPH))

    return ScanService(
        Store(tmp_path / "scans"),
        resolve=resolve or default_resolve,
        clone=clone or default_clone,
        export=export or default_export,
        joern_home=(lambda: Path("/opt/joern")) if joern else (lambda: None),
    )


def _body(**overrides):
    payload = {
        "repositoryUrl": "https://github.com/acme/app",
        "model": "reviewer",
    }
    payload.update(overrides)
    return payload


def test_invalid_config_does_not_resolve(tmp_path):
    calls = []

    def resolve(url, revision):
        calls.append(url)
        raise AssertionError("should not probe")

    service = _service(tmp_path, resolve=resolve)
    status, body = service.create(_body(agreementThreshold=3, agentCount=2))
    assert status == 400
    assert "agreementThreshold (3)" in body["error"]
    assert "not started" in body["error"]
    assert calls == []

    status, body = service.create(_body(repositoryUrl="https://gitlab.com/acme/app"))
    assert status == 422
    assert "GitHub" in body["error"]

    status, body = service.create({"repositoryUrl": "https://github.com/acme/app"})
    assert status == 400
    assert "model" in body["error"]

    status, body = service.create(_body(agentCount=True))
    assert status == 400
    assert "agentCount" in body["error"]


def test_repository_access_failure_does_not_start(tmp_path):
    def resolve(url, revision):
        raise AccessError("Cannot access https://github.com/acme/missing. The scan was not started.")

    service = _service(tmp_path, resolve=resolve)
    status, body = service.create(_body(repositoryUrl="https://github.com/acme/missing"))
    assert status == 422
    assert "not started" in body["error"]
    assert list((tmp_path / "scans").glob("scan_*.json")) == []


def test_missing_pysrc2cpg_does_not_clone(tmp_path):
    cloned = []

    def clone(url, sha, dest):
        cloned.append(url)

    service = _service(tmp_path, joern=False, clone=clone)
    status, body = service.create(_body(model="gpt"))
    assert status == 503
    assert body["status"] == "failed"
    assert "pysrc2cpg" in body["error"]
    assert "not started" in body["error"]
    assert "no graph was produced" in body["error"].lower() or "no graph was produced" in body["progress"].lower()
    assert body["model"] == "gpt"
    assert body["agentCount"] == 2
    assert body["agreementThreshold"] == 2
    assert "id" not in body
    assert cloned == []


def test_graph_without_agents_is_partial_and_keeps_gaps(tmp_path):
    seen = {}

    def export(path: Path):
        seen["path"] = path
        return json.loads(json.dumps(GRAPH))

    service = _service(tmp_path, export=export)
    status, created = service.create(_body(revision="feature/x", agentCount=4, agreementThreshold=3))
    assert status == 202
    assert created["status"] == "queued"
    assert created["model"] == "reviewer"
    assert created["agentCount"] == 4
    assert created["agreementThreshold"] == 3
    assert created["graph"] is None

    service.execute(created["id"])
    status, job = service.get(created["id"])
    assert status == 200
    assert job["status"] == "partial"
    assert job["progress"] == "Agent review is not implemented. The code graph is available."
    assert job["error"] is None
    assert job["graph"]["unresolvedGaps"] == GRAPH["unresolvedGaps"]
    assert job["graph"]["schemaVersion"] == "1.0.0"
    assert "findings" not in job["graph"]
    assert seen["path"].is_dir() is False

    code, document = service.graph(created["id"])
    assert code == 200
    assert document == job["graph"]

    reloaded = ScanService(Store(tmp_path / "scans"), joern_home=lambda: Path("/opt/joern"))
    assert reloaded.get(created["id"])[1]["graph"]["unresolvedGaps"] == GRAPH["unresolvedGaps"]


def test_scanner_failure_has_no_graph(tmp_path):
    def export(path: Path):
        raise RuntimeError("pysrc2cpg failed (1). boom")

    service = _service(tmp_path, export=export)
    _, created = service.create(_body())
    service.execute(created["id"])
    _, job = service.get(created["id"])
    assert job["status"] == "failed"
    assert "boom" in job["error"]
    assert job["graph"] is None
    assert service.graph(created["id"])[0] == 409


def test_parse_refs_and_urls():
    url, owner, repo = parse_github_url("git@github.com:acme/my.repo.git")
    assert (url, owner, repo) == ("https://github.com/acme/my.repo", "acme", "my.repo")
    url, _, repo = parse_github_url("https://github.com/acme/repo.git")
    assert url == "https://github.com/acme/repo" and repo == "repo"
    try:
        parse_github_url("https://user:token@github.com/acme/repo")
    except AccessError as exc:
        assert "credentials" in str(exc)
    else:
        raise AssertionError("credentials should be rejected")

    resolved = resolve_revision("https://github.com/acme/app", None, run=lambda url: REFS)
    assert resolved.revision == "main"
    assert resolved.resolved_sha == SHA

    tagged = resolve_revision("https://github.com/acme/app", "v1", run=lambda url: REFS)
    assert tagged.resolved_sha == TAG

    feature = resolve_revision("https://github.com/acme/app", "feature/x", run=lambda url: REFS)
    assert feature.resolved_sha == OTHER

    def fail(url):
        raise ProbeFailure("remote: Repository not found.")

    try:
        resolve_revision("https://github.com/acme/private", "main", run=fail)
    except AccessError as exc:
        text = str(exc)
        assert "private" in text
        assert "not started" in text
    else:
        raise AssertionError("missing repository should fail closed")

    looked = []

    def lookup(owner, repo, revision):
        looked.append(revision)
        return "e" * 40

    commit = resolve_revision(
        "https://github.com/acme/app",
        "e" * 40,
        run=lambda url: REFS,
        lookup_commit=lookup,
    )
    assert commit.resolved_sha == "e" * 40
    assert looked == ["e" * 40]


def test_clone_checks_out_the_commit(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    git = ["git", "-C", str(source)]
    subprocess.run(["git", "init", str(source)], check=True, capture_output=True)
    subprocess.run([*git, "config", "user.email", "scan@example.com"], check=True)
    subprocess.run([*git, "config", "user.name", "scan"], check=True)
    (source / "app.py").write_text("print('ok')\n", encoding="utf-8")
    subprocess.run([*git, "add", "app.py"], check=True)
    subprocess.run([*git, "commit", "-m", "init"], check=True, capture_output=True)
    sha = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    dest = tmp_path / "dest"
    clone_at(source.as_uri(), sha, dest)
    checked = subprocess.check_output(["git", "-C", str(dest), "rev-parse", "HEAD"], text=True).strip()
    assert checked == sha
    assert (dest / "app.py").read_text(encoding="utf-8") == "print('ok')\n"


def test_http_routes(tmp_path):
    service = _service(tmp_path)
    server = serve("127.0.0.1", 0, service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        health, health_body = _request(port, "GET", "/health")
        assert health == 200 and health_body["status"] == "ok"

        missing, missing_body = _request(port, "POST", "/scans", {"repositoryUrl": "https://example.com/a"})
        assert missing == 422
        assert "GitHub" in missing_body["error"]

        created_status, created = _request(port, "POST", "/scans", _body())
        assert created_status == 202
        service.execute(created["id"])
        got, job = _request(port, "GET", f"/scans/{created['id']}")
        assert got == 200
        assert job["status"] == "partial"
        assert "not implemented" in job["progress"]
        graph_status, document = _request(port, "GET", f"/scans/{created['id']}/graph")
        assert graph_status == 200
        assert document["schemaVersion"] == "1.0.0"
        assert document["unresolvedGaps"] == GRAPH["unresolvedGaps"]
    finally:
        server.shutdown()


def test_worker_thread_reaches_partial(tmp_path):
    service = _service(tmp_path)
    service.start()
    _, created = service.create(_body())
    deadline = time.time() + 2
    job = None
    while time.time() < deadline:
        _, job = service.get(created["id"])
        if job["status"] == "partial":
            break
        time.sleep(0.01)
    assert job is not None
    assert job["status"] == "partial"


def _request(port: int, method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"} if data is not None else {}
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)
