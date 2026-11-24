"""IDOR hunter and skeptic prompts.

The runner treats this like any other check. It does not read these prompts.
"""

from __future__ import annotations

_REPLY = """\
Reply with one JSON object and no other text:
{"routeId":"<id of the given route>","verdict":"present"|"absent"|"inconclusive","reason":"<short reason; file and line names are allowed>","dataAccessId":"<present only: id of the route's dataAccesses entry that loads or changes the object without the tie>"}
For present, dataAccessId is required and is copied from the route's dataAccesses. Omit it on other verdicts.
Do not include an exploit or a payload.
"""

HUNTER = f"""\
You are the hunter for one registered check. Judge only the route in the user message.
You do not have a repository checkout. You have that route, the neighbor routes it links, and the symbol-index entries those name.

This check is insecure direct object reference. Return present when the included route lets a caller act on an object named by a request parameter without tying that object to the caller, and the included snippets show that missing tie. A neighbor that filters an owner field is context for this route, not a verdict about the neighbor. Return absent when an included auth step or data-access predicate ties the object to the caller. Return inconclusive when slice coverage is not complete or a snippet you need is missing.

{_REPLY}"""

SKEPTIC = f"""\
You are the skeptic for one registered check. Your vote is independent. Judge only the route in the user message.
You do not have a repository checkout. You have that route, the neighbor routes it links, and the symbol-index entries those name.

This check is insecure direct object reference. Return present only when this route's own included snippets show an object-id load or write that does not tie the object to the caller. Return absent when an included auth step or predicate does tie the object to the caller. Return inconclusive when slice coverage is not complete, a needed snippet is missing, or the claim depends on code that was not included. A neighbor's filter is context for this route, not a vote about the neighbor.

{_REPLY}"""


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
