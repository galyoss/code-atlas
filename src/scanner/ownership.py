"""Owner-field text for Express and Rails.

`inPredicate` is `yes` only when the call text shows an owner field. A bare
argument, with the comparison not in that text, is `unknown`. FastAPI keeps
its own SQLAlchemy reader.
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
    "userId",
    "ownerId",
    "createdBy",
    "tenantId",
    "accountId",
    "orgId",
    "organizationId",
)
_OWNER_RE = re.compile(r"\b(" + "|".join(OWNER_FIELDS) + r")\b")
_IDENT_RE = re.compile(
    r"\b(req\.user|request\.user|res\.locals\.user|current_user!?|currentUser)\b"
)
_MODEL_RE = re.compile(
    r"(?:\(\s*<[^>\n]+>\s*=\s*([A-Z][A-Za-z0-9_]*)\s*\)|([A-Z][A-Za-z0-9_]*))\s*\.\s*"
    r"(findOne|findById|find_by!|find_by|where|find)\s*\("
)
_COMPARE_RE = re.compile(r"===|!==|==|!=")
_BARE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_AUTH_NAME = re.compile(
    r"auth|current_?user|login|principal|permission|authenticate|authorize",
    re.I,
)
_SET_USER = re.compile(r"req\.user\s*=|request\.user\s*=|@current_user\b|current_user\b|currentUser\b")

DATA_VERBS = {"find", "findOne", "findById", "find_by", "find_by!", "where"}
LOAD_VERBS = {"findOne", "findById", "find_by", "find_by!"}


def model_and_verb(code: str) -> tuple[str, str] | None:
    match = _MODEL_RE.search(code or "")
    if match is None:
        return None
    model = match.group(1) or match.group(2)
    verb = match.group(3)
    if not model or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", model):
        return None
    return model, verb


def call_args(code: str, verb: str) -> str | None:
    match = re.search(re.escape(verb) + r"\s*\(", code or "")
    if match is None:
        return None
    return _balanced(code, match.end() - 1)


def predicate_from_call(code: str, verb: str, model: str) -> tuple[str, list[str], list[str]]:
    """Return `(inPredicate, ownerFields, identity names)` from one call's text."""
    args = call_args(code, verb)
    if args is None or not _visible(args):
        return "unknown", [], []
    owners: list[str] = []
    for field in _OWNER_RE.findall(args):
        qual = f"{model}.{field}"
        if qual not in owners:
            owners.append(qual)
    idents = identity_names(args)
    if owners:
        return "yes", owners, idents
    return "no", [], []


def identity_names(text: str) -> list[str]:
    found: list[str] = []
    for raw in _IDENT_RE.findall(text or ""):
        if raw in {"req.user", "request.user", "res.locals.user"}:
            name = "user"
        elif raw.startswith("current_user"):
            name = "current_user"
        else:
            name = raw
        if name not in found:
            found.append(name)
    return found


def classify_hook(name: str, body: str) -> tuple[str, str] | None:
    """Return `(kind, bindsObjectToCaller)` when `name` or `body` is an auth hook.

    `bindsObjectToCaller` is `yes` only when the body text shows both an owner
    field and an identity. A hook that only loads the caller is `no`.
    """
    text = body or ""
    named = _AUTH_NAME.search(name or "") is not None
    sets_user = _SET_USER.search(text) is not None
    if not named and not sets_user:
        return None
    if not text.strip():
        return "unknown", "unknown"
    owners = _OWNER_RE.search(text) is not None
    idents = _IDENT_RE.search(text) is not None or sets_user
    if owners and idents and (_COMPARE_RE.search(text) or ":" in text):
        return "authorization", "yes"
    if sets_user or named:
        return "authentication", "no"
    return "unknown", "unknown"


def on_failure(body: str) -> str:
    if re.search(
        r"status\s*\(\s*40[13]|sendStatus\s*\(\s*40[13]|redirect_to\b|head\s+:unauthorized|head\s+:forbidden",
        body or "",
    ):
        return "abort"
    return "unknown"


def _visible(args: str) -> bool:
    text = args.strip()
    if not text:
        return False
    if _BARE_RE.fullmatch(text):
        return False
    return True


def _balanced(text: str, open_at: int) -> str | None:
    if open_at >= len(text) or text[open_at] != "(":
        return None
    depth = 0
    quote = ""
    for index in range(open_at, len(text)):
        char = text[index]
        if quote:
            if char == "\\":
                continue
            if char == quote:
                quote = ""
            continue
        if char in {"'", '"', "`"}:
            quote = char
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[open_at + 1 : index]
    return None
