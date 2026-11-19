"""Static parsers can process the submitted source inside the OS boundary."""

import json
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from scan_api.workspace_sandbox import SandboxError, export_confined, sandbox_command
from scan_api.workspace_worker import _prepare_source
from scanner.joern_runner import frontend_available


def workspace(tmp_path):
    work = tmp_path / "job"
    repo = work / "source" / "example"
    repo.mkdir(parents=True)
    (work / "tmp").mkdir()
    (work / "home").mkdir()
    return work, repo


def sandbox_available():
    return (sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").is_file()
            or sys.platform.startswith("linux") and shutil.which("bwrap"))


@pytest.mark.skipif(not sandbox_available(), reason="requires the local product sandbox")
def test_readonly_checkout_private_writes_and_no_host_network(tmp_path):
    work, repo = workspace(tmp_path)
    sentinel = tmp_path / "other-project.txt"
    sentinel.write_text("other project")
    source = repo / "file.ts"
    source.write_text("source")
    probe = """
import socket, sys
from pathlib import Path
source, outside, scratch = map(Path, sys.argv[1:4])
def denied(operation):
    try:
        operation()
    except OSError:
        return True
    return False
assert source.read_text() == "source"
scratch.write_text("parsed")
assert denied(lambda: outside.read_text())
assert denied(lambda: outside.write_text("changed"))
assert denied(lambda: source.write_text("changed"))
assert denied(lambda: socket.create_connection(("127.0.0.1", int(sys.argv[4])), 1))
"""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        command, env = sandbox_command(repo, work, [
            str(Path(sys.executable).resolve()), "-P", "-S", "-c", probe,
            str(source), str(sentinel), str(work / "tmp" / "result"), str(listener.getsockname()[1]),
        ])
        subprocess.run(command, cwd=work / "tmp", env=env, check=True)
    assert sentinel.read_text() == "other project"
    assert (work / "tmp" / "result").read_text() == "parsed"


def test_missing_sandbox_fails_closed(tmp_path, monkeypatch):
    work, repo = workspace(tmp_path)
    monkeypatch.setattr(sys, "platform", "unknown")
    with pytest.raises(SandboxError, match="sandbox-exec"):
        sandbox_command(repo, work, ["/bin/true"])


@pytest.mark.skipif(not sandbox_available() or not frontend_available("javascript"),
                    reason="requires Joern JavaScript frontend and the local product sandbox")
def test_confined_joern_reads_mixed_express_source(tmp_path):
    work, repo = workspace(tmp_path)
    (repo / "package.json").write_text('{"dependencies":{"express":"4"}}')
    (repo / "types.ts").write_text('export function label(): string { return "hello" }\n')
    (repo / "app.js").write_text(
        'const express = require("express");\nconst app = express();\n'
        'const { label } = require("./types");\n'
        'app.get("/hello", function hello(req, res) {\n  res.send(label());\n});\n'
    )
    (repo / ".env.local").write_text("APP_MODE=test")
    (repo / "bunfig.toml").write_text("telemetry=false")
    _prepare_source(repo)
    assert not (repo / ".env.local").exists() and not (repo / "bunfig.toml").exists()
    graph = export_confined(repo, work)
    assert graph["generator"]["name"] == "export-express"
    assert [(r["httpMethod"], r["pathTemplate"]) for r in graph["routes"]] == [("GET", "/hello")]
    overlay = json.loads(next((work / "tmp").glob("export-fastapi-*/overlay.json")).read_bytes())
    assert any(item["file"].endswith("types.ts") for item in overlay["methods"])
