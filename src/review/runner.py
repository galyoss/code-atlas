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
_PATH_REASON = "The recorded path to the cited access passes through an unresolved call, so a present vote is inconclusive."
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
    # An invalid citation is worth one corrected answer from the same agent.
    repairable: bool = False


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
    route_ids=None,
) -> ReviewResult:
    """Dispatch valid routes and retain successful votes when another call fails.

    `route_ids` limits review to those routes; every route stays available as context.
    """
    selected = tuple(registered_checks() if checks is None else checks)
    routes, usable = _routes(document)
    if route_ids is not None:
        wanted = set(route_ids)
        targets = [route for route in routes if route["id"] in wanted]
    else:
        targets = routes

    def dispatch(_state: _ReviewState) -> list[Send] | str:
        return [Send("review_route", {"index": index}) for index in range(len(targets))] or "aggregate"

    def review_route(task: _RouteTask) -> _ReviewState:
        route = targets[task["index"]]
        neighbors, symbols = route_context(document, route)
        user = review_payload(route, neighbors, symbols)
        votes: list[_Vote] = []
        failed = False
        for check in selected:
            for index_in_check in range(agent_count):
                role = "hunter" if index_in_check % 2 == 0 else "skeptic"
                system = check.hunter_prompt if role == "hunter" else check.skeptic_prompt
                try:
                    text = client.complete(model=model, system=system, user=user)
                    parsed = _parse(text, check, route, neighbors, symbols)
                    if parsed.repairable:
                        correction = json.dumps(
                            {
                                "previousAnswer": text[:2000],
                                "problem": parsed.reason,
                                "instruction": "Return one corrected JSON object for the same route.",
                            },
                            ensure_ascii=False,
                        )
                        text = client.complete(model=model, system=system, user=f"{user}\n\n{correction}")
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
        full = _full_vote_sets(public_votes, targets, selected, agent_count)
        return {"result": ReviewResult(
            votes=public_votes,
            findings=_findings(votes, agreement_threshold, {route["id"]: route for route in targets}),
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


def route_context(document: dict, route: dict) -> tuple[list[dict], list[dict]]:
    """The neighbor routes and symbol-index entries a review of `route` receives."""
    routes, _ = _routes(document)
    neighbors = [_neighbor_summary(other) for other in _neighbors(route, {item["id"]: item for item in routes})]
    symbols = _symbols_for([route, *neighbors], document.get("symbolIndex") if isinstance(document, dict) else None)
    return neighbors, symbols


def _neighbor_summary(route: dict) -> dict:
    """Related routes are context: what they touch and whether they filter by owner, without their code."""
    handler = route.get("handler") if isinstance(route.get("handler"), dict) else {}
    accesses = []
    for access in route.get("dataAccesses") or []:
        if isinstance(access, dict):
            accesses.append(
                {key: access[key] for key in ("id", "operation", "object", "ownershipEvidence") if key in access}
            )
    summary = {key: route[key] for key in ("id", "httpMethod", "pathTemplate") if key in route}
    if handler:
        summary["handler"] = {key: handler[key] for key in ("symbolId", "qualifiedName") if key in handler}
    summary["dataAccesses"] = accesses
    return summary


def review_payload(route: dict, neighbors: list[dict], symbols: list[dict]) -> str:
    """The user message for one route. The check's prompt is the system message."""
    return json.dumps(
        {
            "targetRouteId": route["id"],
            "neighborRoutes": neighbors,
            "symbolIndex": symbols,
            "route": route,
        },
        ensure_ascii=False,
    )


def present_blocker(check, route: dict, neighbors: list[dict], symbols: list[dict], access_id) -> str | None:
    """Why a present vote citing `access_id` would not stand, or None when it would."""
    reason, _failed, _citation = _present_gate(check, route, neighbors, symbols, access_id)
    return reason


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
    reason, failed, citation = _present_gate(check, route, neighbors, symbols, payload.get("dataAccessId"))
    if reason is not None:
        return _Parsed("inconclusive", _short(reason), failed, repairable=failed)
    return _Parsed(parsed.verdict, parsed.reason, False, citation)


def _present_gate(check, route, neighbors, symbols, access_id) -> tuple[str | None, bool, tuple[str, dict] | None]:
    """Return (downgrade reason, whether the vote itself was invalid, citation).

    A missing or foreign citation is checked first: it is a malformed vote, not a coverage gap.
    """
    validate_evidence = getattr(check, "present_evidence", None)
    citation = None
    if validate_evidence is not None:
        try:
            citation = validate_evidence(route, access_id)
        except ValueError as exc:
            return str(exc), True, None
    gap = _cited_path_gap(route, access_id)
    if gap is not None:
        return gap, False, None
    gap = check.missing_snippet(route, neighbors, symbols)
    if isinstance(gap, str) and gap.strip():
        return gap.strip(), False, None
    if validate_evidence is not None and citation is None:
        return "The cited data access has no source snippet with a range.", False, None
    return None, False, citation


def _cited_path_gap(route: dict, access_id) -> str | None:
    """A partial route still supports a present vote when the cited access's own path is resolved.

    Unresolved calls elsewhere in the route stay visible to the reviewer and are
    recorded on the finding; they do not block a claim about a fully recorded path.
    """
    if not _coverage_is_partial(route):
        return None
    access = next(
        (item for item in route.get("dataAccesses") or [] if isinstance(item, dict) and item.get("id") == access_id),
        None,
    )
    call_id = access.get("callId") if access else None
    path = _call_path(route, call_id) if isinstance(call_id, str) else None
    if path is None:
        return _COVERAGE_REASON
    if any(node.get("resolution") != "resolved" for node in path[:-1]):
        return _PATH_REASON
    return None


def _call_path(route: dict, call_id: str) -> list[dict] | None:
    """The recorded calls from the handler down to `call_id`, inclusive."""
    roots = list(route.get("callGraph") or [])
    for step in route.get("authChain") or []:
        if isinstance(step, dict):
            roots.extend(step.get("calls") or [])

    def search(nodes, trail):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            here = [*trail, node]
            if node.get("id") == call_id:
                return here
            found = search(node.get("children") or [], here)
            if found:
                return found
        return None

    return search(roots, [])


def _coverage_is_partial(route: dict) -> bool:
    """A present vote needs every coverage axis to be complete."""
    budget = route.get("budget")
    coverage = budget.get("coverage") if isinstance(budget, dict) else None
    if not isinstance(coverage, dict):
        return True
    return any(coverage.get(axis) != "complete" for axis in _COVERAGE_AXES)


def _findings(votes: list[_Vote], agreement_threshold: int, routes: dict[str, dict]) -> list[dict]:
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
        budget = routes.get(route_id, {}).get("budget")
        if isinstance(budget, dict) and isinstance(budget.get("coverage"), dict):
            # A finding on a partial route rests on its cited path; the rest of the route may be unresolved.
            finding["routeCoverage"] = budget["coverage"]
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
