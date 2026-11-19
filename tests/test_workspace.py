"""Workspace ownership, durable jobs and anonymous checkout boundaries."""

import json
import sqlite3
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from scan_api.workspace import Workspace
from scan_api.workspace_server import create_app
from scan_api.workspace_worker import BuildError, _prepare_source, _worker_environment
from scanner.scan import export_repository


def account(client, name, *, login=False):
    return client.post("/auth/" + ("login" if login else "register"), json={
        "email": f"{name}@example.test", "password": "sample password",
    })


def create(client, name):
    return client.post("/projects", json={"repositoryUrl": f"https://github.com/sample/{name}"}).json()["project"]


def settled(client, project):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        scan = client.get(f"/projects/{project['id']}").json()["project"]["scan"]
        if not scan["inProgress"]:
            return scan
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def fixture_graph(url, work, _stop):
    # Fresh source and git history per build. Only the Joern overlay is supplied.
    name = url.rsplit("/", 1)[1]
    repo = work / name
    repo.mkdir()
    git = ["git", "-C", str(repo)]
    subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
    subprocess.run([*git, "remote", "add", "origin", url], check=True)
    source = repo / f"{name}.py"
    source.write_text(f'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/{name}")\ndef route():\n    return 1\n')
    subprocess.run([*git, "add", source.name], check=True)
    subprocess.run([*git, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                    "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "commit", "-qm", name], check=True)
    overlay = work / "overlay.json"
    overlay.write_text(json.dumps({
        "methods": [{"name": "route", "fullName": f"{name}:route", "file": source.name, "line": 4, "endLine": 5}],
        "calls": [{"name": "get", "code": f'app.get("/{name}")', "file": source.name, "line": 3}],
    }))
    graph = export_repository(repo, overlay_path=overlay)
    return {"branch": "main", "files": {"paths": [source.name], "total": 1, "truncated": False}, "graph": graph}


def test_owned_artifacts_sessions_and_canonical_duplicate_race(tmp_path):
    app = create_app(tmp_path, build=fixture_graph)
    with TestClient(app) as alice:
        assert alice.get("/session").json() == {"user": None}
        assert alice.get("/projects").status_code == 401
        assert alice.post("/projects", json={"repositoryUrl": "x"}).status_code == 401
        registered = account(alice, "Alice")
        assert registered.json()["user"]["email"] == "alice@example.test"
        assert "HttpOnly" in registered.headers["set-cookie"]
        alice_cookie = alice.cookies.get("atlas_session")
        with ThreadPoolExecutor(max_workers=4) as pool:
            copies = list(pool.map(lambda url: alice.post("/projects", json={"repositoryUrl": url}).json()["project"],
                                   ["https://github.com/Sample/A.git", "github.com/sample/a/", "git@github.com:sample/A", "https://github.com/sample/a"]))
        a = copies[0]
        assert {item["id"] for item in copies} == {a["id"]}
        b = create(alice, "b")
        for project, name in [(a, "a"), (b, "b")]:
            scan = settled(alice, project)
            assert scan["status"] == "completed", scan
            assert scan["hasGraph"] and scan["hasFiles"] and not scan["reviewing"]
            assert scan["agentCount"] == 0 and scan["findings"] == []
            path = "/projects/" + project["id"]
            graph = alice.get(path + "/graph").json()
            assert graph["repo"]["revision"] == scan["resolvedRevision"]
            assert graph["repo"]["remote"] == "https://github.com/sample/" + name
            assert [route["pathTemplate"] for route in graph["routes"]] == ["/" + name]
            assert alice.get(path + "/files").json()["paths"] == [name + ".py"]
        assert settled(alice, a)["resolvedRevision"] != settled(alice, b)["resolvedRevision"]
        assert len(alice.get("/projects").json()["projects"]) == 2

    with TestClient(create_app(tmp_path, build=fixture_graph)) as bob:
        bob.cookies.set("atlas_session", alice_cookie, domain="testserver.local")
        assert bob.get("/session").json() == registered.json()
        assert len(bob.get("/projects").json()["projects"]) == 2
        assert bob.get(f"/projects/{a['id']}/graph").json()["routes"][0]["pathTemplate"] == "/a"
        assert bob.post("/auth/logout", json={}).status_code == 200
        assert bob.get("/session", headers={"Cookie": "atlas_session=" + alice_cookie}).json() == {"user": None}
        assert account(bob, "alice", login=True).status_code == 200
        assert account(bob, "bob").status_code == 200
        assert bob.get("/projects").json() == {"projects": []}
        owned_by_alice = "/projects/" + a["id"]
        for suffix in ("", "/graph", "/files"):
            assert bob.get(owned_by_alice + suffix).status_code == 404
        assert bob.post(owned_by_alice + "/retry", json={}).status_code == 404
        assert create(bob, "a")["id"] != a["id"]
    with sqlite3.connect(tmp_path / "workspace.sqlite3") as db:
        assert all(row[0] != alice_cookie.encode() and len(row[0]) == 32
                   for row in db.execute("SELECT token_hash FROM sessions"))
        assert all(len(row[0]) == 64 for row in db.execute("SELECT password_hash FROM users"))


def test_authorization_and_mutation_validation(tmp_path):
    with TestClient(create_app(tmp_path, build=fixture_graph)) as client:
        path = "/auth/register"
        body = {"email": "person@example.test", "password": "sample password"}
        assert client.post(path, headers={"Origin": "https://outside.test"}, json=body).status_code == 403
        assert client.post(path, headers={"Sec-Fetch-Site": "cross-site"}, json=body).status_code == 403
        assert client.post(path, data=body).status_code == 415
        assert client.post(path, headers={"Content-Type": "application/json"}, content=b"bad").status_code == 400
        assert client.post(path, json={"email": "invalid", "password": "sample password"}).status_code == 400
        assert client.post(path, json={**body, "password": "short"}).status_code == 400
        assert client.post(path, headers={"Origin": "http://testserver"}, json=body).status_code == 200
        assert client.post(path, json=body).status_code == 409
        assert client.post("/auth/login", json={**body, "password": "wrong password"}).status_code == 401
        for bad in ("file:///tmp/repo", "https://creds@github.com/org/name", "https://github.com/org/name/tree/main"):
            assert client.post("/projects", json={"repositoryUrl": bad}).status_code == 422
        assert client.post("/projects", json={"owner": "other", "repositoryUrl": "github.com/acme/a"}).status_code == 400
        assert client.get("/projects").json()["projects"] == []
        for path in ("/scans", "/review"):
            assert client.get(path).json() == {"error": "Not Found"}


def test_failed_retry_and_interrupted_recovery(tmp_path):
    started = threading.Event()

    def interrupted(_url, _dir, stop):
        started.set()
        stop.wait(5)
        raise InterruptedError()

    with TestClient(create_app(tmp_path, build=interrupted)) as client:
        account(client, "recover")
        project = create(client, "job")
        assert started.wait(2)
        url = "/projects/" + project["id"]
        assert client.get(url + "/graph").status_code == 409
        assert client.post(url + "/retry", json={}).status_code == 409
    assert Workspace(tmp_path).claim() is None

    attempts = []

    def build(repository, directory, stop):
        attempts.append(repository)
        if len(attempts) == 1:
            raise BuildError("Public repository temporarily unavailable.")
        return fixture_graph(repository, directory, stop)

    with TestClient(create_app(tmp_path, build=build)) as client:
        account(client, "recover", login=True)
        failed = settled(client, project)
        assert failed["status"] == "failed" and "unavailable" in failed["error"]
        assert client.get(url + "/files").status_code == 409
        retry = client.post(url + "/retry", json={}).json()["project"]
        assert retry["id"] == project["id"] and retry["scan"]["id"] != failed["id"]
        assert settled(client, retry)["status"] == "completed"
        assert len(attempts) == 2


def test_checkout_environment_and_source_links(tmp_path, monkeypatch):
    for key in ("GIT_CONFIG_COUNT", "GH_TOKEN", "GITHUB_TOKEN", "SSH_AUTH_SOCK", "HTTPS_PROXY", "GIT_ASKPASS"):
        monkeypatch.setenv(key, "fixture")
    work = tmp_path / "job"
    work.mkdir()
    env = _worker_environment(work)
    assert "fixture" not in env.values()
    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null" and Path(env["HOME"]).is_relative_to(work)
    assert env["GIT_CONFIG_NOSYSTEM"] == "1" and env["GIT_ALLOW_PROTOCOL"] == "https"
    outside = tmp_path / "external"
    outside.mkdir()
    (outside / "safe.txt").write_text("outside")
    repo = work / "source"
    repo.mkdir()
    (repo / "pkg").symlink_to(outside, target_is_directory=True)
    (repo / "app.py").symlink_to(outside / "safe.txt")
    (repo / "broken.py").symlink_to(repo / "missing")
    (repo / "real.py").write_text("inside")
    _prepare_source(repo)
    assert [path.name for path in repo.iterdir()] == ["real.py"]
    assert (outside / "safe.txt").read_text() == "outside"
