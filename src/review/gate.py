"""Whether a present vote can stand. Deterministic; no model involved.

A present vote cites one of the route's data accesses. On a route with partial
coverage it stands only when every call on the recorded path from the handler to
that access is resolved. The check may also require snippets the vote rests on.
"""

from __future__ import annotations

_COVERAGE_AXES = ("authChain", "callGraph", "dataFlow")
COVERAGE_REASON = "Slice coverage is not complete, so a present vote is inconclusive."
CITATION_REASON = "Slice coverage is not complete and the present vote did not cite a data access on this route."
PATH_REASON = "The recorded path to the cited data access passes through an unresolved call, so a present vote is inconclusive."


def present_blocker(check, route: dict, access_id: str | None) -> str | None:
    """Why a present vote citing `access_id` would not stand, or None when it would."""
    gap = cited_path_gap(route, access_id)
    if gap is not None:
        return gap
    missing = check.missing_snippet(route, [], [])
    if isinstance(missing, str) and missing.strip():
        return missing.strip()
    return None


def coverage_is_partial(route: dict) -> bool:
    """A route is complete only when every coverage axis is complete."""
    budget = route.get("budget")
    coverage = budget.get("coverage") if isinstance(budget, dict) else None
    if not isinstance(coverage, dict):
        return True
    return any(coverage.get(axis) != "complete" for axis in _COVERAGE_AXES)


def cited_path_gap(route: dict, access_id: str | None) -> str | None:
    """Why the citation cannot carry a present vote on coverage grounds, or None.

    A route with complete coverage needs no citation. On a partial route, unresolved
    calls elsewhere stay visible to the reviewer and do not block a claim about an
    access whose own recorded path is resolved.
    """
    if not coverage_is_partial(route):
        return None
    access = find_access(route, access_id)
    if access is None:
        return CITATION_REASON
    call_id = access.get("callId")
    path = call_path(route, call_id) if isinstance(call_id, str) else None
    if path is None:
        return COVERAGE_REASON
    if any(node.get("resolution") != "resolved" for node in path[:-1]):
        return PATH_REASON
    return None


def find_access(route: dict, access_id: str | None) -> dict | None:
    if access_id is None:
        return None
    return next((item for item in dicts(route.get("dataAccesses")) if item.get("id") == access_id), None)


def call_path(route: dict, call_id: str) -> list[dict] | None:
    """The recorded calls from the handler (or an auth step) down to `call_id`, inclusive."""
    roots = list(dicts(route.get("callGraph")))
    for step in dicts(route.get("authChain")):
        roots.extend(dicts(step.get("calls")))
    stack = [(node, [node]) for node in reversed(roots)]
    while stack:
        node, trail = stack.pop()
        if node.get("id") == call_id:
            return trail
        for child in reversed(dicts(node.get("children"))):
            stack.append((child, [*trail, child]))
    return None


def dicts(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
