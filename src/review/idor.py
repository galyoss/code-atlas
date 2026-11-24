"""IDOR hunter and skeptic prompts.

The runner treats this like any other check. It does not read these prompts.
"""

from __future__ import annotations

HUNTER = """\
You are the hunter for the insecure direct object reference (IDOR) check. Your vote is independent.

The vulnerability is present when the route lets a caller load or change an object named by a request parameter (a path or query id, a body field) and nothing ties that object to the authenticated caller: no owner or tenant filter in the query, no comparison of the loaded object's owner with the caller after the load, no auth step that binds the object to the caller, and no owner stamped from the caller on a write. A missing tie is a present verdict. A neighbor route that filters an owner field is context for this route, not a verdict about it.

A tie can be transitive: the object is checked against a parent id from the request (a workspace, organization, project or account id in the path) and an auth step or identity dependency verifies the caller's access to that parent. That is a tie. A parent id that nothing checks against the caller is not.

Three shapes of the vulnerability are easy to miss:
- A child object reached through a parent the caller may access, without checking the child belongs to that parent: the caller passes their own parent id and someone else's child id (a file in a knowledge base, a message in a channel, an item in a project).
- A check in only one branch: an owner comparison guards some cases (one object type, one mode) and another branch reaches the same load or write without it. A check protects only the paths that pass through it.
- A check at the wrong level: read access, or membership, admits a write or delete that needs ownership or write access.

Follow the request identifier from the parameter to every load or write of the object, including through helpers and services on the call path, and look for the tie at each step.
"""

SKEPTIC = """\
You are the skeptic for the insecure direct object reference (IDOR) check. Your vote is independent and your bar for present is higher.

Vote present only when this route's own snippets show an object-id load or write with no tie to the caller: no owner or tenant filter, no owner comparison after the load, no binding auth step, no owner stamp on a write. Vote absent when you can point to the protection, with its id and file:line, and it covers the object the request names on every branch that reaches the load or write: a parent's access check does not cover a child the request names separately, and read access does not cover a write. Vote inconclusive when the claim depends on an unresolved call on the path or on code the graph does not include. A function body that is not shown is not by itself a reason: its calls are in the call tree and its loads are in the data-access snippets, so judge the recorded path. A transitive tie (object checked against a request parent id, and an auth step or identity dependency verifying the caller's access to that parent) is a protection; open that auth step to confirm it. A neighbor's filter is context for this route, not a vote about the neighbor.
"""


class IdorCheck:
    id = "idor"
    hunter_prompt = HUNTER
    skeptic_prompt = SKEPTIC

    def missing_snippet(self, route, neighbors, symbols) -> str | None:
        """A present vote needs the route's own ownership snippets. There is no checkout."""
        del neighbors, symbols
        if not isinstance(route, dict):
            return "A snippet this check needs is missing."
        for step in _dicts(route.get("authChain")):
            if not _snippet_text(step):
                return "An auth step is missing the snippet this check needs."
        for access in _dicts(route.get("dataAccesses")):
            evidence = access.get("ownershipEvidence")
            if not isinstance(evidence, dict):
                continue
            needs = evidence.get("inPredicate") in {"yes", "no"} or evidence.get("stampedOnWrite") in {
                "yes",
                "no",
            }
            if needs and not _snippet_text(access):
                return "A data-access snippet this check needs is missing."
        return None


def _dicts(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _snippet_text(node: dict) -> str:
    snippet = node.get("snippet")
    if not isinstance(snippet, dict):
        return ""
    text = snippet.get("text")
    if not isinstance(text, str):
        return ""
    return text.strip()


IDOR = IdorCheck()
