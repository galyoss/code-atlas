"""Pinned aegra export. Skips only when pysrc2cpg is not installed."""

import subprocess
from pathlib import Path

import pytest

from export_fastapi.check_fields import access_predicates, auth_observations, routes_by_method_path
from export_fastapi.cli import export_repository
from export_fastapi.joern_runner import find_home
from export_fastapi.validate import validate_document

PIN = "46055c0b9adffe51fb168974f79dfadaa6edd612"
SCHEMA = Path(__file__).resolve().parents[1] / "docs" / "code-graph-schema.json"
POST = ("POST", "/threads/{thread_id}/runs")
GET = ("GET", "/threads/{thread_id}")


def _head(path: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip()


def _repository() -> Path:
    candidates = [
        Path("/tmp/export-fastapi-aegra-46055c0"),
        Path("/tmp/code-atlas-fixtures/aegra"),
    ]
    for path in candidates:
        if path.is_dir() and _head(path) == PIN:
            return path
    dest = candidates[0]
    subprocess.run(
        ["git", "clone", "--branch", "v0.11.0", "https://github.com/aegra/aegra.git", str(dest)],
        check=True,
    )
    assert _head(dest) == PIN
    return dest


@pytest.mark.skipif(find_home() is None, reason="pysrc2cpg is not installed; see the Joern 4.0.684 note in the README")
def test_aegra_three_fields():
    repo = _repository()
    document = export_repository(repo)
    errors = validate_document(document, SCHEMA)
    assert errors == [], "\n".join(errors[:30])
    routes = routes_by_method_path(document)
    assert POST in routes
    assert GET in routes
    post = routes[POST]
    get = routes[GET]
    assert "no" in access_predicates(post, "Thread", "load")
    assert "yes" not in access_predicates(post, "Thread", "load")
    assert "yes" in access_predicates(post, "Assistant", "load")
    assert "yes" in access_predicates(get, "Thread", "load")
    assert {
        "kind": "authorization",
        "bindsObjectToCaller": "yes",
        "applicability": "conditional",
    } in auth_observations(post)
    assert all(step["kind"] in {"authentication", "authorization"} for step in auth_observations(post))
    assert all(step["kind"] in {"authentication", "authorization"} for step in auth_observations(get))
