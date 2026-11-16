"""Read the three fields the aegra check compares.

This module does not know which framework produced the document. It only
looks at object name, operation, inPredicate, auth kind, bindsObjectToCaller,
and applicability.
"""

from __future__ import annotations


def routes_by_method_path(document: dict) -> dict[tuple[str, str], dict]:
    found: dict[tuple[str, str], dict] = {}
    for route in document.get("routes", []):
        found[(route["httpMethod"], route["pathTemplate"])] = route
    return found


def three_fields(route: dict) -> dict:
    """The only facts the pinned-repository check asserts."""
    return {
        "httpMethod": route["httpMethod"],
        "pathTemplate": route["pathTemplate"],
        "dataAccesses": [
            {
                "object": access["object"]["name"],
                "operation": access["operation"],
                "inPredicate": access["ownershipEvidence"]["inPredicate"],
            }
            for access in route.get("dataAccesses", [])
        ],
        "authSteps": [
            {
                "kind": step["kind"],
                "bindsObjectToCaller": step["bindsObjectToCaller"],
                "applicability": step["applicability"],
            }
            for step in route.get("authChain", [])
        ],
    }


def access_predicates(route: dict, object_name: str, operation: str) -> list[str]:
    return [
        item["inPredicate"]
        for item in three_fields(route)["dataAccesses"]
        if item["object"] == object_name and item["operation"] == operation
    ]


def auth_observations(route: dict) -> list[dict]:
    return three_fields(route)["authSteps"]
