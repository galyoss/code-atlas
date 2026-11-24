"""The IDOR benchmark cases are well formed and its route matching is loose only where it should be."""

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "benchmarks" / "idor" / "cases.json").read_text(encoding="utf-8"))
_spec = importlib.util.spec_from_file_location("idor_benchmark", ROOT / "benchmarks" / "idor" / "run.py")
run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run)


def test_every_advisory_names_known_targets_and_parseable_routes():
    ids = [target["id"] for target in CASES["targets"]]
    assert len(ids) == len(set(ids))
    for target in CASES["targets"]:
        assert re.fullmatch(r"[0-9a-f]{40}", target["sha"]), target["id"]
    for advisory in CASES["advisories"]:
        assert advisory["vulnerable"], advisory["id"]
        assert set(advisory["vulnerable"] + advisory["fixed"]) <= set(ids), advisory["id"]
        for spec in advisory["routes"]:
            method, path = spec.split(" ", 1)
            assert method in {"GET", "POST", "PUT", "PATCH", "DELETE"} and path.startswith("/"), spec


def _doc(*routes):
    return {"routes": [{"id": f"r{i}", "httpMethod": m, "pathTemplate": p} for i, (m, p) in enumerate(routes)]}


def test_parameter_names_and_mount_prefixes_are_ignored():
    document = _doc(("POST", "/knowledge/{knowledge_id}/file/remove"), ("POST", "/knowledge/{id}/file/add"))
    assert [r["id"] for r in run.find_routes(document, "POST /api/v1/knowledge/{id}/file/remove")] == ["r0"]
    rails = _doc(("DELETE", "/emails/:id"))
    assert [r["id"] for r in run.find_routes(rails, "DELETE /emails/{id}")] == ["r0"]


def test_method_and_segments_must_match():
    document = _doc(("GET", "/monitor/builds"), ("DELETE", "/monitor/builds/extra"))
    assert run.find_routes(document, "DELETE /monitor/builds") == []
    assert run.find_routes(document, "GET /builds") != []
    assert run.find_routes(document, "GET /monitor/build") == []


def test_exact_path_beats_suffix_and_duplicates_are_all_returned():
    document = _doc(("GET", "/api/v1/monitor/builds"), ("GET", "/monitor/builds"), ("GET", "/monitor/builds"))
    assert [r["id"] for r in run.find_routes(document, "GET /monitor/builds")] == ["r1", "r2"]


def test_rate_limits_are_retried_and_quota_stops_the_run(monkeypatch):
    import email.message
    import urllib.error

    usage = run._Usage()
    replies = []

    def error(code, body, retry_after=None):
        headers = email.message.Message()
        if retry_after:
            headers["retry-after"] = retry_after
        return urllib.error.HTTPError("u", code, "x", headers, __import__("io").BytesIO(body.encode()))

    class Opener:
        def open(self, request, timeout):
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return __import__("io").BytesIO(reply.encode())

    monkeypatch.setattr(run, "_opener", lambda: Opener())
    monkeypatch.setattr(run.time, "sleep", lambda seconds: None)
    ok = json.dumps({"usage": {"prompt_tokens": 10, "completion_tokens": 2, "prompt_tokens_details": {"cached_tokens": 4}}})
    replies[:] = [error(429, "rate limit", "1"), ok]
    urlopen = run.patient_urlopen(usage)
    assert urlopen("request", 5).read() == ok.encode()
    assert usage.public() == {
        "calls": 1, "promptTokens": 10, "cachedPromptTokens": 4, "completionTokens": 2, "quotaExhausted": False
    }
    replies[:] = [error(429, '{"error": {"code": "insufficient_quota"}}')]
    try:
        urlopen("request", 5)
    except urllib.error.HTTPError:
        pass
    assert usage.quota_exhausted and replies == []


def test_unreviewed_routes_are_left_out_of_the_metrics():
    rows = [
        {"vulnerable": True, "found": True, "matches": [{"eligible": ["a"]}], "finding": True},
        {"vulnerable": True, "found": True, "matches": [{"eligible": ["a"]}], "notReviewed": "quota"},
        {"vulnerable": False, "found": True, "matches": [{"eligible": []}], "finding": False},
    ]
    summary = run._score(rows, review=True)
    assert summary["notReviewed"] == 1
    assert (summary["truePositives"], summary["falseNegatives"], summary["recall"], summary["precision"]) == (1, 0, 1.0, 1.0)
