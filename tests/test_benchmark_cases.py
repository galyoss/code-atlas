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
        for entry in advisory["routes"]:
            spec, _handler_file = run.route_spec(entry)
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


def test_usage_sums_runs_and_prices_known_models():
    usage = run._Usage("gpt-4.1")
    usage.add({"gpt-4.1-2025-04-14": {"inputTokens": 1_000_000, "cachedInputTokens": 400_000, "outputTokens": 10_000}})
    usage.add({"gpt-4.1-2025-04-14": {"inputTokens": 500_000, "cachedInputTokens": 0, "outputTokens": 0}})
    public = usage.public()
    assert public["promptTokens"] == 1_500_000 and public["cachedPromptTokens"] == 400_000
    assert public["estimatedUSD"] == round((1_100_000 * 2.0 + 400_000 * 0.5 + 10_000 * 8.0) / 1e6, 2)
    assert "estimatedUSD" not in run._Usage("some-other-model").public()


def test_unreviewed_routes_are_left_out_of_the_metrics():
    rows = [
        {"vulnerable": True, "found": True, "matches": [{"eligible": ["a"]}], "finding": True},
        {"vulnerable": True, "found": True, "matches": [{"eligible": ["a"]}], "notReviewed": "quota"},
        {"vulnerable": False, "found": True, "matches": [{"eligible": []}], "finding": False},
    ]
    summary = run._score(rows, review=True)
    assert summary["notReviewed"] == 1
    assert (summary["truePositives"], summary["falseNegatives"], summary["recall"], summary["precision"]) == (1, 0, 1.0, 1.0)


def test_a_handler_file_settles_an_ambiguous_path():
    document = {
        "routes": [
            {"id": "r_audio", "httpMethod": "POST", "pathTemplate": "/{id}/update", "handler": {"range": {"file": "app/routers/audio.py"}}},
            {"id": "r_folders", "httpMethod": "POST", "pathTemplate": "/{id}/update", "handler": {"range": {"file": "app/routers/folders.py"}}},
        ]
    }
    assert [r["id"] for r in run.find_routes(document, "POST /api/v1/folders/{id}/update")] == ["r_audio", "r_folders"]
    spec, handler_file = run.route_spec({"route": "POST /api/v1/folders/{id}/update", "handlerFile": "routers/folders.py"})
    assert [r["id"] for r in run.find_routes(document, spec, handler_file)] == ["r_folders"]
