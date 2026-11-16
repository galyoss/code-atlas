"""SQLAlchemy predicate text taken from pysrc2cpg call nodes.

`inPredicate` is `yes` only when that text names an owner field. If the CPG
call does not include the comparison, the result is `unknown`.
"""

from __future__ import annotations

import re

OWNER_FIELDS = (
    "user_id",
    "owner_id",
    "created_by",
    "tenant_id",
    "account_id",
    "org_id",
    "organization_id",
)
OWNER_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.(%s)\b" % "|".join(OWNER_FIELDS))
IDENTITY_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.(identity|id)\b")
COMPARE_RE = re.compile(r"==|!=")
WHERE_NAME_RE = re.compile(r"\.(where|filter)\s*\(\s*[A-Za-z_][A-Za-z0-9_]*\s*\)\s*$", re.S)
WHERE_RE = re.compile(r"\.(where|filter)\s*\(")


def owner_fields(text: str, alias_to_class: dict[str, str] | None = None) -> list[str]:
    aliases = alias_to_class or {}
    found: list[str] = []
    for receiver, field in OWNER_RE.findall(text or ""):
        qual = f"{aliases.get(receiver, receiver)}.{field}"
        if qual not in found:
            found.append(qual)
    return found


def identity_receivers(text: str) -> list[str]:
    found: list[str] = []
    for name, _attr in IDENTITY_RE.findall(text or ""):
        if name not in found:
            found.append(name)
    return found


def predicate_from_cpg(
    text: str | None, alias_to_class: dict[str, str] | None = None
) -> tuple[str, list[str], list[str]]:
    """Return `(inPredicate, ownerFields, identity receiver names)` from CPG text."""
    if text is None or not str(text).strip():
        return "unknown", [], []
    owners = owner_fields(text, alias_to_class)
    idents = identity_receivers(text)
    has_cmp = COMPARE_RE.search(text) is not None
    has_where = WHERE_RE.search(text) is not None
    if owners and (has_cmp or has_where):
        return "yes", owners, idents
    if has_cmp:
        return "no", [], []
    if has_where:
        return "unknown", [], []
    return "unknown", [], []


def instance_owner_compare(text: str, class_or_alias: set[str]) -> bool:
    """An inline check compares an instance owner field to an identity.

    `ThreadORM.user_id == user.identity` is a column predicate. It is not an
    inline auth step. `existing_thread.user_id != user.identity` is.
    """
    if not text or COMPARE_RE.search(text) is None:
        return False
    match = OWNER_RE.search(text)
    if match is None or match.group(1) in class_or_alias:
        return False
    return bool(identity_receivers(text))
