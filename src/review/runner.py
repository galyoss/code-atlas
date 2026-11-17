"""Review routes in parallel and aggregate agreement on cited evidence."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from operator import add
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from review.model import ModelError
from review.registry import registered_checks

_MAX_CONCURRENT_ROUTES = 4
_REASON_LIMIT = 480
_COVERAGE_AXES = ("authChain", "callGraph", "dataFlow")
_VERDICTS = {"present", "absent", "inconclusive"}
_COVERAGE_REASON = "Slice coverage is not complete, so a present vote is inconclusive."
_INVALID_REASON = "The vote did not include a valid text reason."


@dataclass(frozen=True)
class ReviewResult:
    votes: list[dict]
    findings: list[dict]
    complete: bool


@dataclass(frozen=True)
class _Parsed:
    verdict: str
    reason: str
    failed: bool
    citation: tuple[str, dict] | None = None


@dataclass(frozen=True)
class _Vote:
    public: dict
    evidence: dict | None


@dataclass(frozen=True)
class _RouteReview:
    index: int
    votes: list[_Vote]
    failed: bool


class _ReviewState(TypedDict, total=False):
    route_reviews: Annotated[list[_RouteReview], add]
    result: ReviewResult


class _RouteTask(TypedDict):
    index: int


def review_graph(
    document: dict,
    *,
    model: str,
    agent_count: int,
    agreement_threshold: int,
    client,
    checks=None,
) -> ReviewResult:
    """Dispatch valid routes and retain successful votes when another call fails."""
    selected = tuple(registered_checks() if checks is None else checks)
    routes, usable = _routes(document)
    symbol_index = document.get("symbolIndex") if isinstance(document, dict) else None
    by_id = {route["id"]: route for route in routes}

    def dispatch(_state: _ReviewState) -> list[Send] | str:
        return [Send("review_route", {"index": index}) for index in range(len(routes))] or "aggregate"

    def review_route(task: _RouteTask) -> _ReviewState:
        route = routes[task["index"]]
        neighbors = _neighbors(route, by_id)
        symbols = _symbols_for([route, *neighbors], symbol_index)
        user = json.dumps(
            {"neighborRoutes": neighbors, "symbolIndex": symbols, "route": route},
            ensure_ascii=False,
        )
        votes: list[_Vote] = []
        failed = False
        for check in selected:
            for index_in_check in range(agent_count):
                role = "hunter" if index_in_check % 2 == 0 else "skeptic"
                system = check.hunter_prompt if role == "hunter" else check.skeptic_prompt
                try:
                    text = client.complete(model=model, system=system, user=user)
                    parsed = _parse(text, check, route, neighbors, symbols)
                except TimeoutError:
                    parsed = _Parsed("inconclusive", "The review call timed out.", True)
                except ModelError as exc:
                    parsed = _Parsed("inconclusive", _short(str(exc)), True)
                except Exception:
                    parsed = _Parsed("inconclusive", "The review call failed.", True)
                failed = failed or parsed.failed
                vote = {
                    "id": f"vote_{uuid.uuid4().hex}",
                    "check": check.id,
                    "routeId": route["id"],
                    "role": role,
                    "verdict": parsed.verdict,
                    "reason": parsed.reason,
                }
                evidence = None
                if parsed.citation is not None:
                    vote["dataAccessId"], evidence = parsed.citation
                votes.append(_Vote(vote, evidence))
        return {"route_reviews": [_RouteReview(task["index"], votes, failed)]}

    def aggregate(state: _ReviewState) -> _ReviewState:
        reviews = sorted(state["route_reviews"], key=lambda review: review.index)
        votes = [vote for review in reviews for vote in review.votes]
        public_votes = [vote.public for vote in votes]
        full = _full_vote_sets(public_votes, routes, selected, agent_count)
        return {"result": ReviewResult(
            votes=public_votes,
            findings=_findings(votes, agreement_threshold),
            complete=usable and full and not any(review.failed for review in reviews),
        )}

    workflow = StateGraph(_ReviewState)
    workflow.add_node("review_route", review_route)
    workflow.add_node("aggregate", aggregate)
    workflow.add_conditional_edges(START, dispatch, ["review_route", "aggregate"])
    workflow.add_edge("review_route", "aggregate")
    workflow.add_edge("aggregate", END)
    state = workflow.compile().invoke({"route_reviews": []}, config={"max_concurrency": _MAX_CONCURRENT_ROUTES})
    return state["result"]


def _routes(document: dict) -> tuple[list[dict], bool]:
    if not isinstance(document, dict):
        return [], False
    raw = document.get("routes")
    if not isinstance(raw, list):
        return [], False
    routes = []
    seen: set[str] = set()
    for route in raw:
        route_id = route.get("id") if isinstance(route, dict) else None
        if isinstance(route_id, str) and route_id and route_id not in seen:
            routes.append(route)
            seen.add(route_id)
    return routes, len(routes) == len(raw)


def _neighbors(route: dict, by_id: dict[str, dict]) -> list[dict]:
    links = route.get("relatedRoutes")
    if not isinstance(links, list):
        return []
    neighbors = []
    seen: set[str] = set()
    for link in links:
        if not isinstance(link, dict):
            continue
        route_id = link.get("routeId")
        if not isinstance(route_id, str) or route_id in seen or route_id == route["id"]:
            continue
        other = by_id.get(route_id)
        if other is None:
            continue
        seen.add(route_id)
        neighbors.append(other)
    return neighbors


def _symbols_for(routes: list[dict], index) -> list[dict]:
    needed: set[str] = set()
    for route in routes:
        _collect_symbol_ids(route, needed)
    if not isinstance(index, list):
        return []
    found = []
    seen: set[str] = set()
    for entry in index:
        if not isinstance(entry, dict):
            continue
        symbol_id = entry.get("id")
        if isinstance(symbol_id, str) and symbol_id in needed and symbol_id not in seen:
            found.append(entry)
            seen.add(symbol_id)
    return found


def _collect_symbol_ids(value, found: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "sharedSymbolIds" and isinstance(item, list):
                for symbol_id in item:
                    if isinstance(symbol_id, str):
                        found.add(symbol_id)
                continue
            if (key == "symbolId" or key.endswith("SymbolId")) and isinstance(item, str):
                found.add(item)
                continue
            _collect_symbol_ids(item, found)
    elif isinstance(value, list):
        for item in value:
            _collect_symbol_ids(item, found)


def _parse(text: str, check, route: dict, neighbors: list[dict], symbols: list[dict]) -> _Parsed:
    if not isinstance(text, str):
        return _Parsed("inconclusive", "The model did not return JSON.", True)
    text = text.strip()
    opening, _, body = text.partition("\n")
    if opening.rstrip("\r").lower() == "```json" and body.endswith("\n```"):
        text = body[:-4]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _Parsed("inconclusive", "The model did not return JSON.", True)
    if not isinstance(payload, dict):
        return _Parsed("inconclusive", "The model did not return a JSON object.", True)
    if payload.get("routeId") != route["id"]:
        return _Parsed("inconclusive", "The vote named a different route.", True)
    verdict = payload.get("verdict")
    if not isinstance(verdict, str) or verdict not in _VERDICTS:
        return _Parsed("inconclusive", "The vote used an unknown verdict.", True)
    reason = payload.get("reason")
    if not isinstance(reason, str):
        return _Parsed("inconclusive", _INVALID_REASON, True)
    try:
        reason.encode("utf-8")
    except UnicodeEncodeError:
        return _Parsed("inconclusive", _INVALID_REASON, True)
    parsed = _Parsed(verdict, _short(reason.strip()), False)
    if verdict == "present":
        return _validate_present(check, route, neighbors, symbols, payload, parsed)
    return parsed


def _validate_present(check, route, neighbors, symbols, payload, parsed: _Parsed) -> _Parsed:
    if _coverage_is_partial(route):
        return _Parsed("inconclusive", _COVERAGE_REASON, False)
    gap = check.missing_snippet(route, neighbors, symbols)
    if isinstance(gap, str) and gap.strip():
        return _Parsed("inconclusive", _short(gap.strip()), False)
    validate_evidence = getattr(check, "present_evidence", None)
    if validate_evidence is None:
        return parsed
    try:
        citation = validate_evidence(route, payload.get("dataAccessId"))
    except ValueError as exc:
        return _Parsed("inconclusive", _short(str(exc)), True)
    if citation is None:
        return _Parsed("inconclusive", "The cited data access has no source snippet with a range.", False)
    return _Parsed(parsed.verdict, parsed.reason, False, citation)


def _coverage_is_partial(route: dict) -> bool:
    """A present vote needs every coverage axis to be complete."""
    budget = route.get("budget")
    coverage = budget.get("coverage") if isinstance(budget, dict) else None
    if not isinstance(coverage, dict):
        return True
    return any(coverage.get(axis) != "complete" for axis in _COVERAGE_AXES)


def _findings(votes: list[_Vote], agreement_threshold: int) -> list[dict]:
    grouped: dict[tuple[str, str, str | None], list[_Vote]] = {}
    for vote in votes:
        payload = vote.public
        if payload["verdict"] == "present":
            key = (payload["check"], payload["routeId"], payload.get("dataAccessId"))
            grouped.setdefault(key, []).append(vote)
    findings = []
    for (check_id, route_id, access_id), present in grouped.items():
        if len(present) < agreement_threshold:
            continue
        finding = {
            "id": f"finding_{uuid.uuid4().hex}",
            "check": check_id,
            "routeId": route_id,
            "agreementThreshold": agreement_threshold,
            "presentCount": len(present),
            "voteIds": [vote.public["id"] for vote in present],
        }
        if access_id is not None:
            finding.update(dataAccessId=access_id, evidence=present[0].evidence)
        findings.append(finding)
    return findings


def _full_vote_sets(votes: list[dict], routes: list[dict], checks, agent_count: int) -> bool:
    if not isinstance(agent_count, int) or isinstance(agent_count, bool) or agent_count < 1:
        return False
    counts: dict[tuple[str, str], int] = {}
    for vote in votes:
        key = (vote["check"], vote["routeId"])
        counts[key] = counts.get(key, 0) + 1
    expected = {(check.id, route["id"]) for route in routes for check in checks}
    return all(counts.get(key, 0) == agent_count for key in expected)


def _short(text: str) -> str:
    if len(text) <= _REASON_LIMIT:
        return text
    return text[:_REASON_LIMIT]
