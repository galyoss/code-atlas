"""IDOR review with deep agents on a scripted chat model. No live model and no repository checkout.

The scripted model really calls the graph tools and votes through SubmitVote, so the
whole path runs: deepagents, the tools, the gate, the coverage ledger.
"""

import json
import socket
from pathlib import Path

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from review.agents import AgentBudget
from review.graph_index import GraphIndex
from review.model import ModelConfigError, ModelKeyMissing, chat_model
from review.registry import registered_checks
from review.runner import review_graph
from review.tools import graph_tools
from scan_api.access import Revision
from scan_api.service import ScanService
from scan_api.store import Store

ROOT = Path(__file__).resolve().parents[1]
AEGRA = ROOT / "docs" / "code-graph-example-aegra.json"
SHA = "a" * 40
CHECK = registered_checks()[0]


class ScriptedModel(BaseChatModel):
    """Calls `decide(target_route_id, messages, system_prompt)` for every turn."""

    decide: object
    calls: list = Field(default_factory=list)
    offered: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        self.offered.append(sorted(getattr(tool, "name", None) or tool.get("name") or tool["function"]["name"] for tool in tools))
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        system = messages[0].content if messages and messages[0].type == "system" else ""
        target = _target(messages)
        self.calls.append({"target": target, "system": system, "messages": messages})
        message = self.decide(target, messages, system)
        if isinstance(message, Exception):
            raise message
        message.usage_metadata = {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110}
        message.response_metadata = {"model_name": "scripted-1"}
        return ChatResult(generations=[ChatGeneration(message=message)])


def _target(messages) -> str | None:
    for message in messages:
        if isinstance(message, HumanMessage) and "targetRouteId" in str(message.content):
            return json.loads(str(message.content).split("\n\n", 1)[1])["targetRouteId"]
    return None


def _tools_used(messages) -> list[str]:
    return [message.name for message in messages if isinstance(message, ToolMessage)]


def _call(name, args, ident):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": ident}])


def reads_then_votes(verdict_for, access_for=lambda route_id: "da_load"):
    """Open the cited access with data_access, then vote."""

    def decide(target, messages, system):
        if "data_access" not in _tools_used(messages):
            return _call("data_access", {"route_id": target, "access_id": access_for(target)}, "c1")
        verdict = verdict_for(target, system)
        args = {"routeId": target, "verdict": verdict, "reason": f"scripted {verdict}", "evidence": [access_for(target)]}
        if verdict == "present":
            args["dataAccessId"] = access_for(target)
        return _call("SubmitVote", args, "c2")

    return decide


def _route(route_id="route_item", *, coverage="complete", helper="resolved", accesses=True, snippet="Item.get(item_id)"):
    access = {
        "id": "da_load",
        "callId": "call_get",
        "operation": "load",
        "object": {"name": "Item", "symbolId": "sym_item"},
        "paramFlows": [{"entryParamId": "param_item_id", "field": "Item.id", "confidence": "exact"}],
        "ownershipEvidence": {"inPredicate": "no", "stampedOnWrite": "not_applicable"},
    }
    if snippet is not None:
        access["snippet"] = {"text": snippet, "truncated": False, "range": {"file": "app.py", "startLine": 9, "endLine": 9}}
    return {
        "id": route_id,
        "httpMethod": "GET",
        "pathTemplate": f"/{route_id}/{{item_id}}",
        "entryParams": [{"id": "param_item_id", "name": "item_id", "location": "path", "namesObject": "yes"}],
        "authChain": [
            {
                "id": "auth_user",
                "symbolId": "sym_user",
                "kind": "authentication",
                "bindsObjectToCaller": "no",
                "snippet": {"text": "def current_user():\n    return user", "truncated": False},
            }
        ],
        "callGraph": [
            {"id": "call_str", "resolution": "ambiguous", "calleeName": "handler", "children": []},
            {
                "id": "call_helper",
                "resolution": helper,
                "calleeName": "load_item",
                "children": [{"id": "call_get", "resolution": "external", "calleeName": "get", "children": []}],
            },
        ],
        "dataAccesses": [access] if accesses else [],
        "relatedRoutes": [],
        "budget": {"coverage": {"authChain": coverage, "callGraph": coverage, "dataFlow": coverage}},
    }


def _document(*routes):
    return {
        "schemaVersion": "1.0.0",
        "routes": list(routes) or [_route()],
        "symbolIndex": [{"id": "sym_user", "qualifiedName": "app.auth.current_user"}],
    }


def _review(document, decide, **kwargs):
    model = ScriptedModel(decide=decide)
    params = {"model": "reviewer", "agent_count": 2, "agreement_threshold": 2, "max_concurrency": 1}
    params.update(kwargs)
    return review_graph(document, chat_model=model, **params), model


def test_only_idor_is_registered_and_the_runner_does_not_name_it():
    assert [check.id for check in registered_checks()] == ["idor"]
    for name in ("runner.py", "agents.py", "tools.py", "graph_index.py", "gate.py"):
        source = (ROOT / "src" / "review" / name).read_text(encoding="utf-8")
        assert "idor" not in source.lower(), name


def test_agents_read_the_graph_and_agree():
    result, model = _review(_document(), reads_then_votes(lambda route, system: "present"))
    assert result.complete is True
    assert [vote["role"] for vote in result.votes] == ["hunter", "skeptic"]
    assert all(vote["trail"] == [{"tool": "data_access", "args": {"route_id": "route_item", "access_id": "da_load"}}] for vote in result.votes)
    assert [finding["dataAccessIds"] for finding in result.findings] == [["da_load"]]
    assert result.coverage["byStatus"] == {"reviewed": 1}
    assert result.usage == {"scripted-1": {"inputTokens": 400, "outputTokens": 40, "cachedInputTokens": 0}}
    hunter_system = next(call["system"] for call in model.calls if "hunter" in call["system"])
    assert "route_summary" in hunter_system and "SubmitVote" in hunter_system


def test_agents_start_from_the_level_two_summary_not_the_whole_graph():
    neighbors = [_route(f"route_n{i}") for i in range(30)]
    first = _route()
    first["relatedRoutes"] = [{"routeId": n["id"], "relations": ["same_model"]} for n in neighbors]
    _, model = _review(_document(first, *neighbors), reads_then_votes(lambda route, system: "absent"), route_ids=["route_item"])
    opening = next(m for m in model.calls[0]["messages"] if isinstance(m, HumanMessage))
    packet = json.loads(str(opening.content).split("\n\n", 1)[1])
    assert packet["routeSummary"]["relatedRoutesTotal"] == 30
    assert "callGraph" not in packet["routeSummary"]
    assert len(opening.content) < 8000


def test_agents_are_offered_graph_tools_the_explorer_and_the_vote_only():
    _, model = _review(_document(), reads_then_votes(lambda route, system: "absent"), agent_count=1, agreement_threshold=1)
    assert model.offered[0] == sorted(
        ["repo_map", "list_routes", "route_summary", "data_access", "auth_step", "call_tree", "symbol", "routes_touching", "task", "SubmitVote"]
    )


def test_present_below_threshold_keeps_votes_and_writes_no_finding():
    verdict = lambda route, system: "present" if "hunter" in system else "absent"
    result, _ = _review(_document(), reads_then_votes(verdict))
    assert result.findings == []
    assert [vote["verdict"] for vote in result.votes] == ["present", "absent"]
    assert result.complete is True


def test_gate_keeps_the_models_claim_when_it_overrides_an_uncited_present():
    def decide(target, messages, system):
        return _call("SubmitVote", {"routeId": target, "verdict": "present", "reason": "claimed"}, "c1")

    result, _ = _review(_document(_route(coverage="partial")), decide, agent_count=1, agreement_threshold=1)
    vote = result.votes[0]
    assert vote["verdict"] == "inconclusive"
    assert "did not cite a data access" in vote["reason"]
    assert vote["modelVerdict"] == "present" and vote["modelReason"] == "claimed"
    assert result.findings == []


def test_present_on_a_partial_route_stands_on_a_resolved_cited_path():
    route = _route(coverage="partial", helper="resolved")
    result, _ = _review(_document(route), reads_then_votes(lambda r, s: "present"))
    assert [vote["verdict"] for vote in result.votes] == ["present", "present"]
    assert result.findings[0]["routeCoverage"] == route["budget"]["coverage"]


def test_unresolved_call_on_the_cited_path_blocks_present():
    result, _ = _review(_document(_route(coverage="partial", helper="ambiguous")), reads_then_votes(lambda r, s: "present"))
    assert result.findings == []
    assert all("unresolved call" in vote["reason"] for vote in result.votes)


def test_missing_snippet_blocks_a_present_vote():
    result, _ = _review(_document(_route(snippet=None)), reads_then_votes(lambda r, s: "present"))
    assert result.findings == []
    assert all(vote["verdict"] == "inconclusive" for vote in result.votes)


def test_routes_without_data_access_are_covered_without_a_model_call():
    result, model = _review(_document(_route(accesses=False)), reads_then_votes(lambda r, s: "present"))
    assert model.calls == []
    assert result.votes == []
    assert result.coverage["ledger"][0]["status"] == "not_applicable"
    assert result.complete is True


def test_an_agent_without_a_vote_gets_one_retry_then_is_inconclusive():
    def decide(target, messages, system):
        return AIMessage(content="I am still thinking.")

    result, model = _review(_document(), decide, agent_count=1, agreement_threshold=1)
    assert len(model.calls) == 2
    assert result.votes[0]["verdict"] == "inconclusive"
    assert result.coverage["ledger"][0]["status"] == "partial"
    assert result.complete is False


def test_the_retry_continues_the_conversation():
    def decide(target, messages, system):
        if not any("previous attempt" in str(m.content) for m in messages if isinstance(m, HumanMessage)):
            if "route_summary" not in _tools_used(messages):
                return _call("route_summary", {"route_id": target}, "c1")
            return AIMessage(content="done?")
        return _call("SubmitVote", {"routeId": target, "verdict": "absent", "reason": "late"}, "c2")

    result, _ = _review(_document(), decide, agent_count=1, agreement_threshold=1)
    vote = result.votes[0]
    assert vote["verdict"] == "absent" and vote["attempts"] == 2
    assert vote["trail"] == [{"tool": "route_summary", "args": {"route_id": "route_item"}}]


def test_a_vote_for_another_route_is_inconclusive():
    def decide(target, messages, system):
        return _call("SubmitVote", {"routeId": "route_other", "verdict": "present", "reason": "x", "dataAccessId": "da_load"}, "c1")

    result, _ = _review(_document(), decide, agent_count=1, agreement_threshold=1)
    assert result.votes[0]["reason"] == "The vote named a different route."
    assert result.complete is False


def test_route_ids_limit_review_and_ledger():
    document = _document(_route("route_a"), _route("route_b"))
    result, model = _review(document, reads_then_votes(lambda r, s: "absent"), route_ids=["route_b"])
    assert {call["target"] for call in model.calls} == {"route_b"}
    assert [entry["routeId"] for entry in result.coverage["ledger"]] == ["route_b"]


def test_insufficient_quota_stops_further_requests():
    def decide(target, messages, system):
        return RuntimeError("Error code: 429 - {'error': {'code': 'insufficient_quota'}}")

    document = _document(_route("route_a"), _route("route_b"))
    result, model = _review(document, decide)
    assert len(model.calls) == 1
    assert {entry["status"] for entry in result.coverage["ledger"]} == {"not_reviewed"}
    assert result.complete is False


def test_a_second_check_is_another_pass():
    class Other:
        def __init__(self, check_id):
            self.id = check_id
            self.hunter_prompt = f"hunter {check_id}"
            self.skeptic_prompt = f"skeptic {check_id}"

        def missing_snippet(self, route, neighbors, symbols):
            return None

    verdict = lambda route, system: "present" if system.startswith("hunter") else "absent"
    result, _ = _review(_document(), reads_then_votes(verdict), agreement_threshold=1, checks=(Other("alpha"), Other("beta")))
    assert [vote["check"] for vote in result.votes] == ["alpha", "alpha", "beta", "beta"]
    assert [finding["check"] for finding in result.findings] == ["alpha", "beta"]


def test_tools_answer_wrong_ids_with_a_message():
    tools = {tool.name: tool for tool in graph_tools(GraphIndex(_document()))}
    assert set(tools) == {"repo_map", "list_routes", "route_summary", "data_access", "auth_step", "call_tree", "symbol", "routes_touching"}
    assert "No route" in tools["route_summary"].invoke({"route_id": "nope"})
    detail = json.loads(tools["data_access"].invoke({"route_id": "route_item", "access_id": "da_load"}))
    assert [step["id"] for step in detail["callPath"]] == ["call_helper", "call_get"]
    assert detail["snippet"]["range"] == "app.py:9"
    touching = json.loads(tools["routes_touching"].invoke({"object_name": "Item"}))
    assert touching["accesses"][0]["inPredicate"] == "no"


def test_chat_model_needs_a_key_and_a_safe_url(monkeypatch):
    monkeypatch.delenv("REVIEW_MODEL_API_KEY", raising=False)
    with pytest.raises(ModelKeyMissing):
        chat_model("gpt-4.1")
    with pytest.raises(ModelConfigError):
        chat_model("gpt-4.1", api_key="k", base_url="http://example.com/v1")
    model = chat_model("gpt-4.1", api_key="k", base_url="http://localhost:8080/v1/")
    assert model.model_name == "gpt-4.1" and model.temperature == 0
    assert model.openai_api_base == "http://localhost:8080/v1"


# The scan service end to end.


def _run(tmp_path, document, model_client, checkout=None, **overrides):
    original = json.loads(json.dumps(document))
    checkout = {} if checkout is None else checkout

    def resolve(url, revision):
        return Revision("https://github.com/acme/app", "acme", "app", revision or "main", SHA)

    def clone(url, sha, dest: Path):
        checkout["path"] = dest
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "app.py").write_text("print('secret')\n", encoding="utf-8")

    service = ScanService(
        Store(tmp_path / "scans"),
        resolve=resolve,
        clone=clone,
        export=lambda path: json.loads(json.dumps(original)),
        joern_home=lambda: Path("/opt/joern"),
        model_client=model_client,
    )
    payload = {"repositoryUrl": "https://github.com/acme/app", "model": "reviewer", "agentCount": 2, "agreementThreshold": 2}
    payload.update(overrides)
    status, created = service.create(payload)
    assert status == 202
    service.execute(created["id"])
    code, job = service.get(created["id"])
    assert code == 200
    assert job["graph"] == original
    assert checkout["path"].exists() is False
    return job, checkout


def test_scan_reviews_after_the_checkout_is_gone(tmp_path):
    checkout = {}
    vote = reads_then_votes(lambda r, s: "present")

    def decide(target, messages, system):
        assert checkout["path"].exists() is False
        return vote(target, messages, system)

    job, _ = _run(tmp_path, _document(), ScriptedModel(decide=decide), checkout)
    assert job["status"] == "completed"
    assert len(job["findings"]) == 1
    assert job["coverage"]["complete"] is True
    assert job["usage"]["scripted-1"]["inputTokens"] > 0


def test_missing_model_key_stores_inconclusive_and_does_not_open_a_socket(tmp_path, monkeypatch):
    monkeypatch.delenv("REVIEW_MODEL_API_KEY", raising=False)

    def no_socket(*args, **kwargs):
        raise AssertionError("no network call expected")

    # asyncio still needs its internal socketpair; only outbound connections are refused.
    monkeypatch.setattr(socket.socket, "connect", no_socket)
    monkeypatch.setattr(socket, "create_connection", no_socket)
    document = json.loads(AEGRA.read_text(encoding="utf-8"))
    job, _ = _run(tmp_path, document, None)
    assert job["status"] == "partial"
    assert job["findings"] == []
    assert {vote["verdict"] for vote in job["votes"]} == {"inconclusive"}
    assert {vote["reason"] for vote in job["votes"]} == {"The model key is not configured."}
    assert len(job["votes"]) == 2 * sum(1 for route in document["routes"] if route["dataAccesses"])
