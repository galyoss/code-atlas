"""Review every route of a code graph once per registered check, with agents.

The orchestrator is a LangGraph graph and is deterministic: it plans a ledger of
every (route, check) pair, dispatches `agent_count` agent runs per pair
(alternating hunter and skeptic, hunter first), and closes the ledger. A route
with no data access cannot carry a present vote under the gate, so it is
recorded `not_applicable` without a model call. Every other pair ends
`reviewed`, `partial` (an agent run failed) or `not_reviewed` (the provider
refused further requests), and the result says which.

Agents decide verdicts; the gate in `review.gate` decides whether a present vote
stands. Agreement counts standing present votes on a route and check.
"""

from __future__ import annotations

import asyncio
import json
import operator
import uuid
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.messages import AIMessage
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from review.agents import AgentBudget, build_agent
from review.gate import coverage_is_partial, find_access, present_blocker
from review.graph_index import GraphIndex
from review.model import ModelKeyMissing, chat_model as default_chat_model
from review.registry import registered_checks

_REASON_LIMIT = 480
_NO_ACCESS = "The route has no data access, so a present vote could not cite one."
_NO_VOTE = "The agent ended without a vote."
_RETRY = (
    "Your previous attempt ended without SubmitVote. Use at most three more tool calls on what you still need, "
    "then call SubmitVote."
)
_QUOTA = "The provider refused further requests (insufficient quota); this run was not reviewed."
_KEY_MISSING = "The model key is not configured."


@dataclass(frozen=True)
class ReviewResult:
    votes: list[dict]
    findings: list[dict]
    complete: bool
    coverage: dict = field(default_factory=dict)
    usage: dict = field(default_factory=dict)


class _State(TypedDict, total=False):
    tasks: list[dict]
    ledger: list[dict]
    votes: Annotated[list[dict], operator.add]
    usage: Annotated[list[dict], operator.add]
    result: ReviewResult


def review_graph(
    document: dict,
    *,
    model: str,
    agent_count: int,
    agreement_threshold: int,
    chat_model=None,
    checks=None,
    route_ids=None,
    budget: AgentBudget | None = None,
    max_concurrency: int = 8,
) -> ReviewResult:
    """Return votes, findings, the coverage ledger and token usage.

    `chat_model` is a LangChain chat model, a `model name -> chat model` factory, or
    None for the configured provider. `route_ids` limits review to those routes;
    every route stays visible to the agents' tools.
    """
    return asyncio.run(
        areview_graph(
            document,
            model=model,
            agent_count=agent_count,
            agreement_threshold=agreement_threshold,
            chat_model=chat_model,
            checks=checks,
            route_ids=route_ids,
            budget=budget,
            max_concurrency=max_concurrency,
        )
    )


async def areview_graph(
    document: dict,
    *,
    model: str,
    agent_count: int,
    agreement_threshold: int,
    chat_model=None,
    checks=None,
    route_ids=None,
    budget: AgentBudget | None = None,
    max_concurrency: int = 8,
) -> ReviewResult:
    selected = tuple(registered_checks() if checks is None else checks)
    budget = budget or AgentBudget()
    index = GraphIndex(document)
    raw_routes = document.get("routes") if isinstance(document, dict) else None
    usable = isinstance(raw_routes, list) and len(index.routes) == len(raw_routes)
    wanted = set(route_ids) if route_ids is not None else None
    targets = [route for route in index.routes if wanted is None or route["id"] in wanted]

    # Agents are built only when some route has a data access to review.
    llm = None
    if any(route.get("dataAccesses") for route in targets):
        try:
            llm = _resolve_model(chat_model, model)
        except ModelKeyMissing:
            llm = None
    agents = {}
    if llm is not None:
        for check in selected:
            for role in ("hunter", "skeptic"):
                agents[(check.id, role)] = build_agent(role, check, llm, index, budget)
    stop = asyncio.Event()

    def plan(_state: _State) -> _State:
        tasks, ledger = [], []
        for route in targets:
            for check in selected:
                if not route.get("dataAccesses"):
                    ledger.append({"routeId": route["id"], "check": check.id, "status": "not_applicable", "reason": _NO_ACCESS})
                    continue
                ledger.append({"routeId": route["id"], "check": check.id, "status": "pending"})
                for ordinal in range(max(agent_count, 0)):
                    role = "hunter" if ordinal % 2 == 0 else "skeptic"
                    tasks.append({"routeId": route["id"], "check": check.id, "role": role, "ordinal": ordinal})
        return {"tasks": tasks, "ledger": ledger}

    def dispatch(state: _State) -> list[Send] | str:
        return [Send("review", task) for task in state["tasks"]] or "close"

    async def review(task: dict) -> _State:
        route = index.by_id[task["routeId"]]
        check = next(item for item in selected if item.id == task["check"])
        if llm is None:
            return {"votes": [_vote(task, "inconclusive", _KEY_MISSING, failed=True)]}
        if stop.is_set():
            return {"votes": [_vote(task, "inconclusive", _QUOTA, failed=True, not_reviewed=True)]}
        vote, usage = await _run_agent(agents[(check.id, task["role"])], task, route, check, index, budget, stop)
        return {"votes": [vote], "usage": [usage]}

    def close(state: _State) -> _State:
        votes = sorted(state.get("votes", []), key=lambda vote: (vote["routeId"], vote["check"], vote["_ordinal"]))
        ledger = _close_ledger(state.get("ledger", []), votes, agent_count)
        findings = _findings(votes, index, selected, agreement_threshold)
        complete = usable and all(entry["status"] in {"reviewed", "not_applicable"} for entry in ledger)
        coverage = {
            "routes": len(targets),
            "pairs": len(ledger),
            "byStatus": _count(entry["status"] for entry in ledger),
            "ledger": ledger,
            "complete": complete,
        }
        public = [{key: value for key, value in vote.items() if not key.startswith("_")} for vote in votes]
        return {
            "result": ReviewResult(
                votes=public, findings=findings, complete=complete, coverage=coverage, usage=_sum_usage(state.get("usage", []))
            )
        }

    graph = StateGraph(_State)
    graph.add_node("plan", plan)
    graph.add_node("review", review)
    graph.add_node("close", close)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", dispatch, ["review", "close"])
    graph.add_edge("review", "close")
    graph.add_edge("close", END)
    state = await graph.compile().ainvoke({"votes": [], "usage": []}, config={"max_concurrency": max_concurrency})
    return state["result"]


def _resolve_model(chat_model, model: str):
    if chat_model is None:
        return default_chat_model(model)
    if callable(chat_model) and not hasattr(chat_model, "invoke"):
        return chat_model(model)
    return chat_model


async def _run_agent(agent, task, route, check, index: GraphIndex, budget: AgentBudget, stop: asyncio.Event):
    usage = UsageMetadataCallbackHandler()
    packet = json.dumps({"targetRouteId": route["id"], "routeSummary": index.opening_packet(route["id"])}, ensure_ascii=False)
    messages: list = [{"role": "user", "content": f"Review the target route.\n\n{packet}"}]
    trail: list[dict] = []
    failure = None
    for attempt in range(1, budget.attempts + 1):
        try:
            out = await agent.ainvoke(
                {"messages": messages}, config={"recursion_limit": budget.recursion_limit, "callbacks": [usage]}
            )
        except GraphRecursionError:
            out, failure = {}, "The agent exceeded its step limit."
        except Exception as exc:  # provider errors after the client's own retries
            if "insufficient_quota" in str(exc):
                stop.set()
                return _vote(task, "inconclusive", _QUOTA, failed=True, not_reviewed=True), usage.usage_metadata
            out, failure = {}, _short(f"The review call failed: {type(exc).__name__}.")
        if out.get("messages"):
            # The conversation carries over between attempts, so the trail is the whole of it.
            messages = list(out["messages"])
            trail = _trail(messages)
        submitted = out.get("structured_response")
        if submitted is not None:
            vote = _judge(task, route, check, submitted, trail, attempt)
            return vote, usage.usage_metadata
        messages = [*messages, {"role": "user", "content": _RETRY}]
    return _vote(task, "inconclusive", failure or _NO_VOTE, failed=True, trail=trail), usage.usage_metadata


def _judge(task, route, check, submitted, trail, attempt) -> dict:
    """Apply the gate to the agent's vote. The model's own verdict is kept when the gate overrides it."""
    reason = _short((submitted.reason or "").strip())
    cited = submitted.dataAccessId if find_access(route, submitted.dataAccessId) else None
    extra = {"evidence": list(submitted.evidence or [])[:40], "trail": trail, "attempts": attempt}
    if cited:
        extra["dataAccessId"] = cited
    if submitted.routeId != route["id"]:
        return _vote(task, "inconclusive", "The vote named a different route.", failed=True, **extra)
    if submitted.verdict != "present":
        return _vote(task, submitted.verdict, reason, **extra)
    blocker = present_blocker(check, route, submitted.dataAccessId)
    if blocker is None and not cited:
        blocker = "The present vote did not cite a data access on this route."
    if blocker is not None:
        return _vote(task, "inconclusive", _short(blocker), modelVerdict="present", modelReason=reason, **extra)
    return _vote(task, "present", reason, **extra)


def _vote(task, verdict, reason, *, failed=False, not_reviewed=False, **extra) -> dict:
    vote = {
        "id": f"vote_{uuid.uuid4().hex}",
        "check": task["check"],
        "routeId": task["routeId"],
        "role": task["role"],
        "verdict": verdict,
        "reason": reason,
        **extra,
        "_ordinal": task["ordinal"],
        "_failed": failed,
        "_notReviewed": not_reviewed,
    }
    return vote


def _trail(messages: list) -> list[dict]:
    """The tool calls an agent made, in order, without the final SubmitVote."""
    calls = []
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls or []:
                if call.get("name") != "SubmitVote":
                    calls.append({"tool": call.get("name"), "args": call.get("args")})
    return calls


def _close_ledger(ledger: list[dict], votes: list[dict], agent_count: int) -> list[dict]:
    by_pair: dict[tuple[str, str], list[dict]] = {}
    for vote in votes:
        by_pair.setdefault((vote["routeId"], vote["check"]), []).append(vote)
    closed = []
    for entry in ledger:
        if entry["status"] == "not_applicable":
            closed.append(entry)
            continue
        bucket = by_pair.get((entry["routeId"], entry["check"]), [])
        if any(vote["_notReviewed"] for vote in bucket):
            status = "not_reviewed"
        elif len(bucket) != agent_count or any(vote["_failed"] for vote in bucket):
            status = "partial"
        else:
            status = "reviewed"
        closed.append({**entry, "status": status, "votes": len(bucket)})
    return closed


def _findings(votes: list[dict], index: GraphIndex, checks, agreement_threshold: int) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for vote in votes:
        grouped.setdefault((vote["check"], vote["routeId"]), []).append(vote)
    findings = []
    for route in index.routes:
        for check in checks:
            present = [vote for vote in grouped.get((check.id, route["id"]), []) if vote["verdict"] == "present"]
            if not present or len(present) < agreement_threshold:
                continue
            finding = {
                "id": f"finding_{uuid.uuid4().hex}",
                "check": check.id,
                "routeId": route["id"],
                "agreementThreshold": agreement_threshold,
                "presentCount": len(present),
                "voteIds": [vote["id"] for vote in present],
                "dataAccessIds": list(dict.fromkeys(vote["dataAccessId"] for vote in present if "dataAccessId" in vote)),
            }
            if coverage_is_partial(route):
                # The finding rests on its cited paths; the rest of the route may be unresolved.
                finding["routeCoverage"] = (route.get("budget") or {}).get("coverage")
            findings.append(finding)
    return findings


def _sum_usage(items: list[dict]) -> dict:
    totals: dict[str, dict[str, int]] = {}
    for item in items:
        for model_name, usage in (item or {}).items():
            bucket = totals.setdefault(model_name, {"inputTokens": 0, "outputTokens": 0, "cachedInputTokens": 0})
            bucket["inputTokens"] += int(usage.get("input_tokens") or 0)
            bucket["outputTokens"] += int(usage.get("output_tokens") or 0)
            details: Any = usage.get("input_token_details") or {}
            bucket["cachedInputTokens"] += int(details.get("cache_read") or 0)
    return totals


def _count(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _short(text: str) -> str:
    return text if len(text) <= _REASON_LIMIT else text[:_REASON_LIMIT]
