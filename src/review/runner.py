"""Review every route once per registered check.

Each call alternates the check's hunter and skeptic prompts, starting with
the hunter. Agreement counts present votes on that route and check. Reasons
are stored and not compared.

A present vote cites one of the route's data accesses. On a route with partial
coverage it stands only when the recorded call path to that access is resolved.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from review.registry import registered_checks

_REASON_LIMIT = 480
_COVERAGE_AXES = ("authChain", "callGraph", "dataFlow")
_VERDICTS = {"present", "absent", "inconclusive"}
_COVERAGE_REASON = "Slice coverage is not complete, so a present vote is inconclusive."
_CITATION_REASON = "Slice coverage is not complete and the present vote did not cite a data access on this route."
_PATH_REASON = "The recorded path to the cited data access passes through an unresolved call, so a present vote is inconclusive."


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
    access_id: str | None = None


def review_graph(
    document: dict,
    *,
    model: str,
    agent_count: int,
    agreement_threshold: int,
    client,
    checks=None,
) -> ReviewResult:
    """Return votes and findings. complete is false when any call failed."""
    selected = tuple(registered_checks() if checks is None else checks)
    routes, usable = _routes(document)
    index = document.get("symbolIndex") if isinstance(document, dict) else None
    by_id = {route["id"]: route for route in routes}
    votes: list[dict] = []
    failures = 0
    for route in routes:
        neighbors = _neighbors(route, by_id)
        symbols = _symbols_for([route, *neighbors], index)
        user = json.dumps(
            {"route": route, "neighborRoutes": neighbors, "symbolIndex": symbols},
            ensure_ascii=False,
        )
        for check in selected:
            for index_in_check in range(agent_count):
                role = "hunter" if index_in_check % 2 == 0 else "skeptic"
                system = check.hunter_prompt if role == "hunter" else check.skeptic_prompt
                try:
                    text = client.complete(model=model, system=system, user=user)
                    parsed = _parse(text, route["id"])
                    if not parsed.failed and parsed.verdict == "present":
                        parsed = _downgrade_present(check, route, neighbors, symbols, parsed)
                except TimeoutError as exc:
                    parsed = _Parsed("inconclusive", _failure_reason(exc, "The review call timed out."), True)
                except Exception as exc:
                    parsed = _Parsed("inconclusive", _failure_reason(exc, "The review call failed."), True)
                if parsed.failed:
                    failures += 1
                vote = {
                    "id": f"vote_{uuid.uuid4().hex}",
                    "check": check.id,
                    "routeId": route["id"],
                    "role": role,
                    "verdict": parsed.verdict,
                    "reason": parsed.reason,
                }
                if parsed.verdict == "present" and parsed.access_id is not None:
                    vote["dataAccessId"] = parsed.access_id
                votes.append(vote)
    findings = _findings(votes, routes, selected, agreement_threshold)
    full = _full_vote_sets(votes, routes, selected, agent_count)
    return ReviewResult(votes=votes, findings=findings, complete=failures == 0 and full and usable)


def _routes(document: dict) -> tuple[list[dict], bool]:
    if not isinstance(document, dict):
        return [], False
    raw = document.get("routes")
    if not isinstance(raw, list):
        return [], False
    routes = [
        route
        for route in raw
        if isinstance(route, dict) and isinstance(route.get("id"), str) and route["id"]
    ]
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


def _parse(text: str, route_id: str) -> _Parsed:
    if not isinstance(text, str):
        return _Parsed("inconclusive", "The model did not return JSON.", True)
    try:
        payload = json.loads(text.strip())
    except json.JSONDecodeError:
        return _Parsed("inconclusive", "The model did not return JSON.", True)
    if not isinstance(payload, dict):
        return _Parsed("inconclusive", "The model did not return a JSON object.", True)
    if payload.get("routeId") != route_id:
        return _Parsed("inconclusive", "The vote named a different route.", True)
    verdict = payload.get("verdict")
    if verdict not in _VERDICTS:
        return _Parsed("inconclusive", "The vote used an unknown verdict.", True)
    reason = payload.get("reason", "")
    if not isinstance(reason, str):
        reason = ""
    access_id = payload.get("dataAccessId")
    if not isinstance(access_id, str) or not access_id.strip():
        access_id = None
    return _Parsed(verdict, _short(reason.strip()), False, access_id)


def _downgrade_present(check, route, neighbors, symbols, parsed: _Parsed) -> _Parsed:
    gap = _cited_path_gap(route, parsed.access_id)
    if gap is not None:
        return _Parsed("inconclusive", gap, False)
    gap = check.missing_snippet(route, neighbors, symbols)
    if isinstance(gap, str) and gap.strip():
        return _Parsed("inconclusive", _short(gap.strip()), False)
    return parsed


def _cited_path_gap(route: dict, access_id: str | None) -> str | None:
    """Why a present vote citing `access_id` cannot stand on coverage, or None.

    A route with complete coverage needs no citation. On a partial route, unresolved
    calls elsewhere stay visible to the reviewer and do not block a claim about an
    access whose own recorded path is resolved.
    """
    if not _coverage_is_partial(route):
        return None
    access = next(
        (item for item in _dicts(route.get("dataAccesses")) if access_id is not None and item.get("id") == access_id),
        None,
    )
    if access is None:
        return _CITATION_REASON
    call_id = access.get("callId")
    path = _call_path(route, call_id) if isinstance(call_id, str) else None
    if path is None:
        return _COVERAGE_REASON
    if any(node.get("resolution") != "resolved" for node in path[:-1]):
        return _PATH_REASON
    return None


def _call_path(route: dict, call_id: str) -> list[dict] | None:
    """The recorded calls from the handler down to `call_id`, inclusive."""
    roots = list(_dicts(route.get("callGraph")))
    for step in _dicts(route.get("authChain")):
        roots.extend(_dicts(step.get("calls")))
    stack = [(node, [node]) for node in reversed(roots)]
    while stack:
        node, trail = stack.pop()
        if node.get("id") == call_id:
            return trail
        for child in reversed(_dicts(node.get("children"))):
            stack.append((child, [*trail, child]))
    return None


def _dicts(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _coverage_is_partial(route: dict) -> bool:
    """A present vote needs every coverage axis to be complete."""
    budget = route.get("budget")
    coverage = budget.get("coverage") if isinstance(budget, dict) else None
    if not isinstance(coverage, dict):
        return True
    return any(coverage.get(axis) != "complete" for axis in _COVERAGE_AXES)


def _findings(votes: list[dict], routes: list[dict], checks, agreement_threshold: int) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for vote in votes:
        grouped.setdefault((vote["check"], vote["routeId"]), []).append(vote)
    findings = []
    for route in routes:
        for check in checks:
            bucket = grouped.get((check.id, route["id"]), [])
            present = [vote for vote in bucket if vote["verdict"] == "present"]
            if len(present) < agreement_threshold:
                continue
            finding = {
                "id": f"finding_{uuid.uuid4().hex}",
                "check": check.id,
                "routeId": route["id"],
                "agreementThreshold": agreement_threshold,
                "presentCount": len(present),
                "voteIds": [vote["id"] for vote in present],
            }
            cited = list(dict.fromkeys(vote["dataAccessId"] for vote in present if "dataAccessId" in vote))
            if cited:
                finding["dataAccessIds"] = cited
            if _coverage_is_partial(route):
                # The finding rests on its cited paths; the rest of the route may be unresolved.
                budget = route.get("budget")
                coverage = budget.get("coverage") if isinstance(budget, dict) else None
                finding["routeCoverage"] = coverage if isinstance(coverage, dict) else None
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


def _failure_reason(exc: Exception, fallback: str) -> str:
    text = str(exc).strip()
    if not text:
        return fallback
    return _short(text)


def _short(text: str) -> str:
    if len(text) <= _REASON_LIMIT:
        return text
    return text[:_REASON_LIMIT]
