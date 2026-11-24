"""IDOR review with a fake model. No live model and no repository checkout."""

import json
import socket
from pathlib import Path

from fastapi.testclient import TestClient

from review.model import ChatCompletionsClient
from review.registry import registered_checks
from review.runner import review_graph
from scan_api.access import Revision
from scan_api.server import create_app
from scan_api.service import ScanService
from scan_api.store import Store

ROOT = Path(__file__).resolve().parents[1]
AEGRA = ROOT / "docs" / "code-graph-example-aegra.json"
EXAMPLE = ROOT / "docs" / "code-graph-example.json"
SHA = "a" * 40
CHECK = registered_checks()[0]


class FakeModel:
    def __init__(self, decide):
        self.decide = decide
        self.calls = []

    def complete(self, *, model, system, user):
        self.calls.append({"model": model, "system": system, "user": user})
        return self.decide(model, system, user)


def _body(**overrides):
    payload = {"repositoryUrl": "https://github.com/acme/app", "model": "reviewer"}
    payload.update(overrides)
    return payload


def _run(tmp_path, document, client, **overrides):
    original = json.loads(json.dumps(document))
    checkout = {}

    def resolve(url, revision):
        return Revision("https://github.com/acme/app", "acme", "app", revision or "main", SHA)

    def clone(url, sha, dest: Path):
        checkout["path"] = dest
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "app.py").write_text("print('secret')\n", encoding="utf-8")

    def export(path: Path):
        return json.loads(json.dumps(original))

    class _AfterCheckout:
        def complete(self, **kwargs):
            assert checkout["path"].exists() is False
            return client.complete(**kwargs)

    service = ScanService(
        Store(tmp_path / "scans"),
        resolve=resolve,
        clone=clone,
        export=export,
        joern_home=lambda: Path("/opt/joern"),
        model_client=_AfterCheckout(),
    )
    status, created = service.create(_body(**overrides))
    assert status == 202
    service.execute(created["id"])
    code, job = service.get(created["id"])
    assert code == 200
    assert job["graph"] == original
    assert checkout["path"].exists() is False
    return service, job


def _route(route_id="route_item", *, coverage="complete", snippet="return Item.get(item_id)"):
    access = {
        "id": "da_load",
        "ownershipEvidence": {"inPredicate": "no", "stampedOnWrite": "not_applicable"},
    }
    if snippet is not None:
        access["snippet"] = {"text": snippet, "truncated": False}
    return {
        "id": route_id,
        "authChain": [
            {
                "id": "auth_user",
                "symbolId": "sym_user",
                "snippet": {"text": "def current_user():\n    return user", "truncated": False},
            }
        ],
        "dataAccesses": [access],
        "relatedRoutes": [],
        "budget": {
            "coverage": {"authChain": coverage, "callGraph": coverage, "dataFlow": coverage},
        },
    }


def _document(route):
    return {
        "schemaVersion": "1.0.0",
        "routes": [route],
        "symbolIndex": [{"id": "sym_user", "qualifiedName": "app.auth.current_user"}],
    }


def _reply(route_id, verdict, reason):
    return json.dumps({"routeId": route_id, "verdict": verdict, "reason": reason})


def test_only_idor_is_registered_and_the_runner_does_not_name_it():
    assert [check.id for check in registered_checks()] == ["idor"]
    source = (ROOT / "src" / "review" / "runner.py").read_text(encoding="utf-8")
    assert "idor" not in source.lower()


def test_aegra_post_and_get_are_absent(tmp_path):
    document = json.loads(AEGRA.read_text(encoding="utf-8"))

    def decide(model, system, user):
        route_id = json.loads(user)["route"]["id"]
        return _reply(route_id, "absent", "The included predicate ties the thread to the caller.")

    model = FakeModel(decide)
    _, job = _run(tmp_path, document, model)
    assert job["status"] == "completed"
    assert job["findings"] == []
    by_route = {}
    for call in model.calls:
        body = json.loads(call["user"])
        assert call["model"] == "reviewer"
        by_route.setdefault(body["route"]["id"], []).append(call["system"])
        assert "print('secret')" not in call["user"]
    assert set(by_route) == {"route_post_thread_runs", "route_get_thread"}
    for prompts in by_route.values():
        assert prompts == [CHECK.hunter_prompt, CHECK.skeptic_prompt]
    assert {(vote["routeId"], vote["role"], vote["verdict"]) for vote in job["votes"]} == {
        ("route_post_thread_runs", "hunter", "absent"),
        ("route_post_thread_runs", "skeptic", "absent"),
        ("route_get_thread", "hunter", "absent"),
        ("route_get_thread", "skeptic", "absent"),
    }


def test_synthetic_load_by_id_agrees_once(tmp_path):
    document = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def decide(model, system, user):
        body = json.loads(user)
        route_id = body["route"]["id"]
        if system == CHECK.hunter_prompt:
            role = "hunter"
        elif system == CHECK.skeptic_prompt:
            role = "skeptic"
        else:
            raise AssertionError("unexpected prompt")
        if route_id == "route_post_thread_runs":
            return _reply(route_id, "present", f"{role} names app/api/runs.py:15")
        return _reply(route_id, "absent", f"{role} sees the owner filter at app/api/threads.py:14")

    model = FakeModel(decide)
    service, job = _run(tmp_path, document, model, agentCount=2, agreementThreshold=2)
    assert job["status"] == "completed"
    assert len(job["findings"]) == 1
    finding = job["findings"][0]
    assert set(finding) == {
        "id",
        "check",
        "routeId",
        "agreementThreshold",
        "presentCount",
        "voteIds",
    }
    assert finding["check"] == "idor"
    assert finding["routeId"] == "route_post_thread_runs"
    assert finding["agreementThreshold"] == 2
    assert finding["presentCount"] == 2
    votes = {vote["id"]: vote for vote in job["votes"]}
    agreed = [votes[vote_id] for vote_id in finding["voteIds"]]
    assert [vote["role"] for vote in agreed] == ["hunter", "skeptic"]
    assert {vote["verdict"] for vote in agreed} == {"present"}
    assert {vote["reason"] for vote in agreed} == {
        "hunter names app/api/runs.py:15",
        "skeptic names app/api/runs.py:15",
    }
    assert "app/api/runs.py" not in json.dumps(finding)
    get_votes = [vote for vote in job["votes"] if vote["routeId"] == "route_get_thread"]
    assert [vote["verdict"] for vote in get_votes] == ["absent", "absent"]
    assert all(vote["id"] not in finding["voteIds"] for vote in get_votes)

    post_calls = [
        json.loads(call["user"])
        for call in model.calls
        if json.loads(call["user"])["route"]["id"] == "route_post_thread_runs"
    ]
    assert post_calls
    assert [item["id"] for item in post_calls[0]["neighborRoutes"]] == ["route_get_thread"]
    names = {item["id"] for item in post_calls[0]["symbolIndex"]}
    assert {"sym_thread", "sym_get_current_user", "sym_get_thread"} <= names

    api = TestClient(create_app(service))
    got = api.get(f"/scans/{job['id']}")
    assert got.status_code == 200
    assert got.json()["findings"] == job["findings"]
    assert got.json()["votes"] == job["votes"]
    graph = api.get(f"/scans/{job['id']}/graph")
    assert graph.status_code == 200
    assert graph.json()["schemaVersion"] == "1.0.0"
    assert graph.json() == job["graph"]
    assert "votes" not in graph.json()
    assert "findings" not in graph.json()


def test_present_below_threshold_keeps_votes_and_writes_no_finding(tmp_path):
    verdicts = ["present", "inconclusive", "inconclusive"]
    seen = {"n": 0}

    def decide(model, system, user):
        route_id = json.loads(user)["route"]["id"]
        verdict = verdicts[seen["n"]]
        seen["n"] += 1
        return _reply(route_id, verdict, f"scripted {verdict}")

    _, job = _run(
        tmp_path,
        _document(_route()),
        FakeModel(decide),
        agentCount=3,
        agreementThreshold=2,
    )
    assert job["status"] == "completed"
    assert job["findings"] == []
    assert [vote["verdict"] for vote in job["votes"]] == verdicts
    assert [vote["role"] for vote in job["votes"]] == ["hunter", "skeptic", "hunter"]
    assert [vote["reason"] for vote in job["votes"]] == [
        "scripted present",
        "scripted inconclusive",
        "scripted inconclusive",
    ]


def test_present_on_a_partial_slice_is_stored_inconclusive(tmp_path):
    document = json.loads(AEGRA.read_text(encoding="utf-8"))
    for route in document["routes"]:
        coverage = route["budget"]["coverage"]
        assert coverage["authChain"] == "partial"
        assert coverage["callGraph"] == "partial"
        assert coverage["dataFlow"] == "partial"

    def decide(model, system, user):
        route_id = json.loads(user)["route"]["id"]
        return _reply(route_id, "present", "The model claims a missing owner check.")

    model = FakeModel(decide)
    _, job = _run(tmp_path, document, model)
    assert job["status"] == "completed"
    assert job["findings"] == []
    assert len(model.calls) == 4
    assert {vote["verdict"] for vote in job["votes"]} == {"inconclusive"}
    assert {vote["reason"] for vote in job["votes"]} == {
        "Slice coverage is not complete and the present vote did not cite a data access on this route."
    }


def test_missing_snippet_blocks_a_present_vote(tmp_path):
    def decide(model, system, user):
        route_id = json.loads(user)["route"]["id"]
        return _reply(route_id, "present", "Looks missing.")

    _, job = _run(tmp_path, _document(_route(snippet=None)), FakeModel(decide))
    assert job["status"] == "completed"
    assert job["findings"] == []
    assert [vote["verdict"] for vote in job["votes"]] == ["inconclusive", "inconclusive"]
    assert {vote["reason"] for vote in job["votes"]} == {
        "A data-access snippet this check needs is missing."
    }


def test_failed_calls_stay_partial_and_do_not_invent_a_finding(tmp_path):
    route_id = "route_item"
    seen = {"n": 0}

    def decide(model, system, user):
        kind = seen["n"]
        seen["n"] += 1
        if kind == 0:
            raise TimeoutError("timed out")
        if kind == 1:
            return "not json"
        if kind == 2:
            return json.dumps({"routeId": "route_other", "verdict": "present", "reason": "wrong route"})
        return json.dumps({"routeId": route_id, "verdict": "likely", "reason": "bad verdict"})

    model = FakeModel(decide)
    _, job = _run(
        tmp_path,
        _document(_route()),
        model,
        agentCount=4,
        agreementThreshold=1,
    )
    assert job["status"] == "partial"
    assert job["progress"] == "Review did not finish a full vote set. The code graph is available."
    assert job["error"] is None
    assert job["findings"] == []
    assert job["graph"]["schemaVersion"] == "1.0.0"
    assert [vote["verdict"] for vote in job["votes"]] == ["inconclusive"] * 4
    assert [vote["routeId"] for vote in job["votes"]] == [route_id] * 4
    assert [vote["reason"] for vote in job["votes"]] == [
        "timed out",
        "The model did not return JSON.",
        "The vote named a different route.",
        "The vote used an unknown verdict.",
    ]


def test_agreement_is_kept_when_another_call_fails(tmp_path):
    seen = {"n": 0}

    def decide(model, system, user):
        kind = seen["n"]
        seen["n"] += 1
        route_id = json.loads(user)["route"]["id"]
        if kind == 2:
            raise TimeoutError("timed out")
        return _reply(route_id, "present", f"vote {kind} at item.py:4")

    _, job = _run(
        tmp_path,
        _document(_route()),
        FakeModel(decide),
        agentCount=3,
        agreementThreshold=2,
    )
    assert job["status"] == "partial"
    assert job["error"] is None
    assert job["graph"]["schemaVersion"] == "1.0.0"
    assert len(job["findings"]) == 1
    finding = job["findings"][0]
    assert finding["presentCount"] == 2
    assert finding["agreementThreshold"] == 2
    assert len(finding["voteIds"]) == 2
    assert "item.py" not in json.dumps(finding)
    votes = {vote["id"]: vote for vote in job["votes"]}
    assert [votes[vote_id]["verdict"] for vote_id in finding["voteIds"]] == ["present", "present"]
    assert [vote["verdict"] for vote in job["votes"]] == ["present", "present", "inconclusive"]


def test_missing_model_key_stores_inconclusive_and_does_not_open_a_socket(tmp_path, monkeypatch):
    monkeypatch.delenv("REVIEW_MODEL_API_KEY", raising=False)
    opened = {"n": 0}

    def refuse(*args, **kwargs):
        opened["n"] += 1
        raise AssertionError("socket opened")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)

    def resolve(url, revision):
        return Revision("https://github.com/acme/app", "acme", "app", "main", SHA)

    def clone(url, sha, dest: Path):
        dest.mkdir(parents=True, exist_ok=True)

    document = _document(_route())

    def export(path: Path):
        return json.loads(json.dumps(document))

    service = ScanService(
        Store(tmp_path / "scans"),
        resolve=resolve,
        clone=clone,
        export=export,
        joern_home=lambda: Path("/opt/joern"),
    )
    _, created = service.create(_body(model="reviewer"))
    service.execute(created["id"])
    _, job = service.get(created["id"])
    assert opened["n"] == 0
    assert job["status"] == "partial"
    assert job["error"] is None
    assert job["findings"] == []
    assert job["graph"] == document
    assert job["graph"]["schemaVersion"] == "1.0.0"
    assert [vote["verdict"] for vote in job["votes"]] == ["inconclusive", "inconclusive"]
    assert {vote["reason"] for vote in job["votes"]} == {"The model key is not configured."}


class _Body:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_chat_client_sends_the_model_name_and_returns_the_message(monkeypatch):
    monkeypatch.delenv("REVIEW_MODEL_BASE_URL", raising=False)
    seen = {}

    def urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        seen["auth"] = request.get_header("Authorization")
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return _Body(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"routeId":"route_item","verdict":"absent","reason":"tied"}',
                        }
                    }
                ]
            }
        )

    client = ChatCompletionsClient(api_key="test-key", urlopen=urlopen)
    text = client.complete(model="reviewer", system="hunter prompt", user="route json")
    assert text == '{"routeId":"route_item","verdict":"absent","reason":"tied"}'
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["timeout"] == 60
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"] == {
        "model": "reviewer",
        "messages": [
            {"role": "system", "content": "hunter prompt"},
            {"role": "user", "content": "route json"},
        ],
    }

    def custom(request, timeout):
        seen["custom_url"] = request.full_url
        return _Body({"choices": [{"message": {"content": "{\"routeId\":\"r\",\"verdict\":\"absent\",\"reason\":\"ok\"}"}}]})

    other = ChatCompletionsClient(
        base_url="https://models.example.test/v1/",
        api_key="test-key",
        urlopen=custom,
    )
    assert other.complete(model="other-model", system="s", user="u").startswith("{")
    assert seen["custom_url"] == "https://models.example.test/v1/chat/completions"


def test_unknown_coverage_blocks_present():
    def decide(model, system, user):
        route_id = json.loads(user)["route"]["id"]
        return _reply(route_id, "present", "claimed")

    result = review_graph(
        _document(_route(coverage="unknown")),
        model="reviewer",
        agent_count=1,
        agreement_threshold=1,
        client=FakeModel(decide),
    )
    assert result.complete is True
    assert result.findings == []
    assert result.votes[0]["verdict"] == "inconclusive"
    assert "coverage" in result.votes[0]["reason"]


def _partial_route(helper_resolution):
    route = _route(coverage="partial")
    route["dataAccesses"][0]["callId"] = "call_get"
    route["callGraph"] = [
        {"id": "call_str", "resolution": "ambiguous", "children": []},
        {
            "id": "call_helper",
            "resolution": helper_resolution,
            "children": [{"id": "call_get", "resolution": "external", "children": []}],
        },
    ]
    return route


def _cite(access_id):
    def decide(model, system, user):
        route_id = json.loads(user)["route"]["id"]
        return json.dumps(
            {"routeId": route_id, "verdict": "present", "reason": "claimed", "dataAccessId": access_id}
        )

    return FakeModel(decide)


def test_present_on_a_partial_route_stands_on_a_resolved_cited_path():
    route = _partial_route("resolved")
    result = review_graph(
        _document(route),
        model="reviewer",
        agent_count=2,
        agreement_threshold=2,
        client=_cite("da_load"),
    )
    assert result.complete is True
    assert [vote["verdict"] for vote in result.votes] == ["present", "present"]
    assert [vote["dataAccessId"] for vote in result.votes] == ["da_load", "da_load"]
    assert len(result.findings) == 1
    assert result.findings[0]["dataAccessIds"] == ["da_load"]
    assert result.findings[0]["routeCoverage"] == route["budget"]["coverage"]


def test_unresolved_call_on_the_cited_path_blocks_present():
    result = review_graph(
        _document(_partial_route("ambiguous")),
        model="reviewer",
        agent_count=1,
        agreement_threshold=1,
        client=_cite("da_load"),
    )
    assert result.findings == []
    assert result.votes[0]["verdict"] == "inconclusive"
    assert "unresolved call" in result.votes[0]["reason"]
    assert "dataAccessId" not in result.votes[0]


def test_citing_an_access_from_another_route_blocks_present():
    result = review_graph(
        _document(_partial_route("resolved")),
        model="reviewer",
        agent_count=1,
        agreement_threshold=1,
        client=_cite("da_elsewhere"),
    )
    assert result.findings == []
    assert result.votes[0]["verdict"] == "inconclusive"
    assert "did not cite a data access on this route" in result.votes[0]["reason"]


def test_a_second_check_is_another_pass():
    class Other:
        def __init__(self, check_id):
            self.id = check_id
            self.hunter_prompt = f"hunter {check_id}"
            self.skeptic_prompt = f"skeptic {check_id}"

        def missing_snippet(self, route, neighbors, symbols):
            return None

    def decide(model, system, user):
        route_id = json.loads(user)["route"]["id"]
        verdict = "present" if system.startswith("hunter") else "absent"
        return _reply(route_id, verdict, system)

    result = review_graph(
        _document(_route()),
        model="reviewer",
        agent_count=2,
        agreement_threshold=1,
        client=FakeModel(decide),
        checks=(Other("alpha"), Other("beta")),
    )
    assert result.complete is True
    assert [vote["check"] for vote in result.votes] == ["alpha", "alpha", "beta", "beta"]
    assert [vote["role"] for vote in result.votes] == ["hunter", "skeptic", "hunter", "skeptic"]
    assert [finding["check"] for finding in result.findings] == ["alpha", "beta"]
    assert [finding["presentCount"] for finding in result.findings] == [1, 1]
    assert all("reason" not in finding for finding in result.findings)
