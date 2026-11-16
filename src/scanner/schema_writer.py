"""Turn route facts into a schema 1.0.0 document.

This module does not import a framework adapter.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from scanner.facts import CallFact, Limits, RepoFact, RouteFact

_GAPS = [
    (
        "gap_graphql",
        "graphql",
        "unsupported",
        "v1 does not slice GraphQL operations or resolvers. An HTTP handler that serves GraphQL may still appear as a route.",
    ),
    (
        "gap_websocket",
        "websocket",
        "unsupported",
        "v1 does not slice WebSocket handlers. A websocket decorator is not emitted as a route.",
    ),
    (
        "gap_dynamic_dispatch",
        "dynamic_dispatch",
        "partial",
        "Computed call targets stay resolution ambiguous and are not inlined.",
    ),
    (
        "gap_other_frameworks",
        "other",
        "unsupported",
        "The scanner reads FastAPI, Express, and Rails. Other web frameworks are not modeled.",
    ),
    (
        "gap_llm_judge",
        "other",
        "unsupported",
        "This document is a code graph, not a finding.",
    ),
]


class Ids:
    def __init__(self) -> None:
        self.used: set[str] = set()

    def make(self, base: str) -> str:
        text = re.sub(r"[^a-z0-9]+", "_", base.lower()).strip("_")
        if not text or not text[0].isalpha():
            text = "n_" + text
        text = text[:60].strip("_") or "n_x"
        if len(text) < 2:
            text = "n_x"
        candidate = text
        number = 2
        while candidate in self.used or not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", candidate):
            suffix = f"_{number}"
            candidate = text[: 64 - len(suffix)].strip("_") + suffix
            number += 1
        self.used.add(candidate)
        return candidate


def write_document(
    routes: list[RouteFact],
    repo: RepoFact,
    limits: Limits,
    *,
    generator_name: str = "export-fastapi",
    generator_version: str = "1.0.0",
) -> dict:
    ids = Ids()
    symbol_ids: dict[str, str] = {}
    referenced: set[str] = set()
    _share_symbols(routes)
    emitted_routes = []
    for route in routes:
        emitted_routes.append(_route(route, ids, symbol_ids, referenced, limits))
    _relate(emitted_routes)
    symbols = []
    for key in sorted(referenced):
        fact = _find_symbol(routes, key)
        if fact is None:
            continue
        signature = " ".join((fact.signature or fact.name or "def").split())[:300] or (fact.name or "def")
        symbols.append(
            {
                "id": symbol_ids[key],
                "language": fact.language,
                "kind": fact.kind,
                "name": (fact.name or "symbol")[:120],
                "qualifiedName": (fact.qualname or fact.name or "symbol")[:200],
                "signature": signature,
                "range": _range(fact.file, fact.start, fact.end),
            }
        )
    frameworks = sorted({route.framework for route in routes})
    languages = sorted({route.language for route in routes}) or ["python"]
    document = {
        "schemaVersion": "1.0.0",
        "illustrative": False,
        "generator": {"name": generator_name, "version": generator_version},
        "repo": _repo(repo),
        "languages": languages,
        "frameworks": frameworks,
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "unresolvedGaps": [
            {"id": ids.make(item[0]), "kind": item[1], "support": item[2], "detail": item[3]}
            for item in _GAPS
        ],
        "symbolIndex": symbols,
        "routes": emitted_routes,
    }
    return document


def _share_symbols(routes: list[RouteFact]) -> None:
    """One definition key has one range, so every route agrees with the index."""
    canonical: dict[str, object] = {}
    for route in routes:
        for key, fact in list(route.symbols.items()):
            current = canonical.get(key)
            if current is None:
                canonical[key] = fact
            else:
                route.symbols[key] = current


def _repo(repo: RepoFact) -> dict:
    payload = {"name": repo.name, "revision": repo.revision, "vcs": repo.vcs}
    if repo.remote:
        payload["remote"] = repo.remote
    return payload


def _find_symbol(routes: list[RouteFact], key: str):
    for route in routes:
        fact = route.symbols.get(key)
        if fact is not None:
            return fact
    return None


def _route(route: RouteFact, ids: Ids, symbol_ids: dict[str, str], referenced: set[str], limits: Limits) -> dict:
    slug = ids.make(f"route_{route.http_method}_{route.path}")
    handler_symbol = _sym(route.handler_symbol_key, route, ids, symbol_ids, referenced)
    call_ids: dict[str, str] = {}
    omissions: list[dict] = []
    order = 1

    def emit_calls(nodes: list[CallFact], depth: int) -> list[dict]:
        nonlocal order
        emitted = []
        for node in nodes:
            node_id = ids.make(f"call_{slug}_{node.callee_name}")
            call_ids[node.key] = node_id
            this_order = order
            order += 1
            if node.resolution == "resolved" and node.symbol_key in route.symbols:
                resolution = "resolved"
            elif node.resolution == "ambiguous":
                resolution = "ambiguous"
            else:
                resolution = "external"
            expand = resolution == "resolved" and node.expanded != "no"
            if resolution == "ambiguous" and node.expanded == "partial" and node.children:
                expand = True
            children = emit_calls(node.children, depth + 1) if expand else []
            expanded = node.expanded if expand else "no"
            if resolution == "ambiguous" and expanded == "yes":
                expanded = "partial" if children else "no"
            if resolution == "external":
                expanded = "no"
                children = []
            qualname = (node.qualname or node.callee_name)[:200]
            if resolution == "resolved":
                qualname = route.symbols[node.symbol_key].qualname[:200]
            payload = {
                "id": node_id,
                "order": this_order,
                "depth": depth,
                "calleeName": node.callee_name[:120] or "call",
                "qualifiedName": qualname or "call",
                "resolution": resolution,
                "touchesPersistence": node.touches if node.touches in {"none", "read", "write", "read_write", "unknown"} else "unknown",
                "expanded": expanded,
                "callSite": _range(node.file, node.line, node.end_line),
                "children": children,
            }
            if node.excerpt:
                payload["argumentsExcerpt"] = node.excerpt[:240]
            if resolution == "resolved":
                payload["symbolId"] = _sym(node.symbol_key, route, ids, symbol_ids, referenced)
            elif resolution == "ambiguous":
                payload["candidates"] = [
                    _sym(key, route, ids, symbol_ids, referenced)
                    for key in (node.candidates or [])
                    if key in route.symbols
                ][:12]
            needs_omission = resolution != "external" and (
                expanded == "partial" or (resolution == "resolved" and expanded == "no") or resolution == "ambiguous"
            )
            if needs_omission:
                reason, detail = node.omission or (
                    "dynamic_dispatch" if resolution == "ambiguous" else "depth",
                    f"Did not fully open {payload['calleeName']}.",
                )
                if resolution == "ambiguous" and reason not in {"ambiguity", "dynamic_dispatch"}:
                    reason = "dynamic_dispatch" if not payload["candidates"] else "ambiguity"
                omissions.append(
                    {
                        "id": ids.make(f"omit_{reason}"),
                        "reason": reason,
                        "detail": detail[:400],
                        "callId": node_id,
                    }
                )
            emitted.append(payload)
        return emitted

    auth_payloads = []
    emitted_steps = []
    for step in route.auth_steps:
        symbol = route.symbols.get(step.symbol_key)
        if symbol is None:
            continue
        if step.mechanism == "inline":
            file, start, end = step.file, step.start, step.end
        else:
            file, start, end = symbol.file, symbol.start, symbol.end
        step_calls = emit_calls(step.calls, 1) if step.expanded != "no" else []
        auth_id = ids.make(f"auth_{step.key}")
        payload = {
            "id": auth_id,
            "symbolId": _sym(step.symbol_key, route, ids, symbol_ids, referenced),
            "qualifiedName": symbol.qualname[:200],
            "range": _range(file, start, end),
            "kind": step.kind,
            "mechanism": step.mechanism,
            "scope": step.scope,
            "applicability": step.applicability,
            "onFailure": step.on_failure,
            "bindsObjectToCaller": step.binds_object_to_caller,
            "expanded": step.expanded,
            "calls": step_calls if step.expanded != "no" else [],
        }
        if payload["expanded"] == "no":
            payload["calls"] = []
        if step.call_key and step.call_key in call_ids:
            payload["callId"] = call_ids[step.call_key]
        snippet = _snippet(step.snippet, step.file, step.start, step.end, limits.max_snippet_chars, step.snippet_truncated)
        if snippet:
            payload["snippet"] = snippet
            if snippet["truncated"]:
                omissions.append(
                    {
                        "id": ids.make("omit_snippet"),
                        "reason": "snippet_budget",
                        "detail": "An auth-step excerpt was cut to the snippet budget.",
                    }
                )
        auth_payloads.append(payload)
        emitted_steps.append(step)

    # Number handler calls after auth calls. emit_calls already used `order`.
    call_graph = emit_calls(route.call_graph, 1)

    # Auth steps that point at a handler call are numbered before that call
    # exists. Fill callId now.
    for step, payload in zip(emitted_steps, auth_payloads, strict=True):
        if step.call_key and step.call_key in call_ids:
            payload["callId"] = call_ids[step.call_key]

    binding_ids: dict[str, str] = {}
    bindings = []
    for binding in route.bindings:
        binding_id = ids.make(f"bind_{binding.name}")
        binding_ids[binding.name] = binding_id
        payload = {
            "id": binding_id,
            "name": binding.name[:120],
            "kind": binding.kind,
            "presence": binding.presence,
            "expression": (binding.expression or binding.name)[:200],
            "range": _range(binding.file, binding.start, binding.end),
        }
        produced = _auth_id_for(auth_payloads, emitted_steps, binding.produced_by_qualname)
        if produced:
            payload["producedByAuthStepId"] = produced
        if binding.type_symbol_key and binding.type_symbol_key in route.symbols:
            payload["typeSymbolId"] = _sym(binding.type_symbol_key, route, ids, symbol_ids, referenced)
        bindings.append(payload)

    params = []
    param_ids: dict[str, str] = {}
    for param in route.entry_params:
        param_id = ids.make(f"param_{param.name}")
        param_ids[param.name] = param_id
        reads = []
        for read in param.reads[:8]:
            symbol = read.symbol_key if read.symbol_key in route.symbols else route.handler_symbol_key
            reads.append(
                {
                    "range": _range(read.file, read.start, read.end),
                    "symbolId": _sym(symbol, route, ids, symbol_ids, referenced),
                    "expression": read.expression[:200],
                }
            )
        if not reads:
            continue
        payload = {
            "id": param_id,
            "name": param.name[:120],
            "location": param.location,
            "pathInRequest": param.path_in_request[:200],
            "presence": param.presence,
            "valueShape": param.value_shape,
            "namesObject": param.names_object,
            "reads": reads,
        }
        if param.type_symbol_key and param.type_symbol_key in route.symbols:
            payload["typeSymbolId"] = _sym(param.type_symbol_key, route, ids, symbol_ids, referenced)
        params.append(payload)

    accesses = []
    for access in route.data_accesses:
        call_id = call_ids.get(access.call_key)
        if call_id is None:
            continue
        access_id = ids.make(f"da_{access.object_name}_{access.operation}")
        flows = []
        for flow in access.param_flows:
            if flow.entry_param_name not in param_ids:
                continue
            flows.append(
                {
                    "entryParamId": param_ids[flow.entry_param_name],
                    "field": flow.field[:120],
                    "confidence": flow.confidence,
                }
            )
        written = []
        for field in access.written_fields:
            item = {"field": field.field[:120], "source": field.source}
            if field.source == "request_param" and field.entry_param_name in param_ids:
                item["entryParamId"] = param_ids[field.entry_param_name]
            elif field.source == "identity" and field.binding_name in binding_ids:
                item["identityBindingId"] = binding_ids[field.binding_name]
            elif field.source in {"request_param", "identity", "loaded_object"}:
                item["source"] = "unknown"
            written.append(item)
        identity_ids = []
        for name in access.identity_names:
            if name in binding_ids and binding_ids[name] not in identity_ids:
                identity_ids.append(binding_ids[name])
        in_predicate = access.in_predicate
        stamped = access.stamped_on_write
        owners = list(access.owner_fields)
        if in_predicate == "yes" and not owners:
            in_predicate = "unknown"
        if stamped == "yes" and (not owners or not identity_ids):
            stamped = "unknown"
            if in_predicate != "yes":
                owners = []
                identity_ids = []
        if in_predicate in {"no", "not_applicable"} and stamped in {"no", "not_applicable"}:
            owners = []
            identity_ids = []
        if stamped == "no" and access.operation == "create" and not written:
            stamped = "unknown"
        evidence = {
            "inPredicate": in_predicate,
            "stampedOnWrite": stamped,
            "ownerFields": owners,
            "identityBindingIds": identity_ids,
        }
        payload = {
            "id": access_id,
            "callId": call_id,
            "operation": access.operation,
            "persistenceApi": access.persistence_api,
            "object": {"name": access.object_name},
            "paramFlows": flows,
            "ownershipEvidence": evidence,
            "writtenFields": [] if access.operation in {"load", "query", "delete"} else written,
        }
        if access.object_symbol_key and access.object_symbol_key in route.symbols:
            payload["object"]["symbolId"] = _sym(access.object_symbol_key, route, ids, symbol_ids, referenced)
        if access.store and re.fullmatch(r"[A-Za-z0-9_.-]+", access.store):
            payload["object"]["store"] = access.store
        snippet = _snippet(
            access.snippet,
            access.snippet_file,
            access.snippet_start,
            access.snippet_end,
            limits.max_snippet_chars,
            access.snippet_truncated,
        )
        if snippet:
            payload["snippet"] = snippet
        if access.operation in {"load", "query", "delete"}:
            payload["ownershipEvidence"]["stampedOnWrite"] = "not_applicable"
            payload["writtenFields"] = []
        if access.operation == "create":
            payload["ownershipEvidence"]["inPredicate"] = "not_applicable"
        evidence = payload["ownershipEvidence"]
        if evidence["inPredicate"] != "yes" and evidence["stampedOnWrite"] != "yes":
            evidence["ownerFields"] = []
        if evidence["inPredicate"] in {"no", "not_applicable"} and evidence["stampedOnWrite"] in {"no", "not_applicable"}:
            evidence["identityBindingIds"] = []
        if evidence["stampedOnWrite"] == "no" and access.operation == "create" and not payload["writtenFields"]:
            evidence["stampedOnWrite"] = "unknown"
        accesses.append(payload)

    reg_snippet = _snippet(
        route.registration_text,
        route.registration_file,
        route.registration_start,
        route.registration_end,
        limits.max_snippet_chars,
        route.registration_truncated,
    )
    mechanism = route.registration_mechanism
    if mechanism not in {"decorator", "route_table", "resource_dsl", "unknown"}:
        mechanism = "unknown"
    registration = {
        "mechanism": mechanism,
        "range": _range(route.registration_file, route.registration_start, route.registration_end),
    }
    if reg_snippet:
        registration["snippet"] = reg_snippet

    snippets = _count_snippets(registration, auth_payloads, call_graph, accesses)
    handler_fact = route.symbols[route.handler_symbol_key]
    coverage = "partial" if _coverage_partial(auth_payloads, call_graph, accesses, omissions) else "complete"
    return {
        "id": slug,
        "language": route.language,
        "framework": route.framework,
        "httpMethod": route.http_method,
        "pathTemplate": route.path,
        "registration": registration,
        "handler": {
            "symbolId": handler_symbol,
            "qualifiedName": handler_fact.qualname[:200],
            "range": _range(handler_fact.file, handler_fact.start, handler_fact.end),
        },
        "entryParams": params,
        "identityBindings": bindings,
        "authChain": auth_payloads,
        "callGraph": call_graph,
        "dataAccesses": accesses,
        "relatedRoutes": [],
        "budget": {
            "limits": {
                "maxCallDepth": limits.max_call_depth,
                "maxCallNodes": limits.max_call_nodes,
                "maxSnippetChars": min(limits.max_snippet_chars, 480),
            },
            "counts": {
                "authSteps": len(auth_payloads),
                "callNodes": _count_call_nodes(auth_payloads, call_graph),
                "dataAccesses": len(accesses),
                "snippets": snippets,
            },
            "coverage": {"authChain": coverage, "callGraph": coverage, "dataFlow": coverage},
            "omitted": omissions,
        },
    }


def _sym(key: str, route: RouteFact, ids: Ids, symbol_ids: dict[str, str], referenced: set[str]) -> str:
    if key not in symbol_ids:
        symbol_ids[key] = ids.make("sym_" + key.split(".")[-1])
    referenced.add(key)
    return symbol_ids[key]


def _auth_id_for(steps: list[dict], facts, qual: str | None) -> str | None:
    if not qual:
        return None
    matches = [step["id"] for step, fact in zip(steps, facts, strict=True) if fact.qualname == qual]
    return matches[-1] if matches else None


def _relate(routes: list[dict]) -> None:
    for route in routes:
        related = []
        for other in routes:
            if other["id"] == route["id"]:
                continue
            relations = []
            shared: list[str] = []
            models = _model_ids(route)
            other_models = _model_ids(other)
            both_models = [item for item in models if item in other_models]
            if both_models:
                relations.append("same_model")
                shared.extend(both_models)
            if _static_prefix(route["pathTemplate"]) and _static_prefix(route["pathTemplate"]) == _static_prefix(other["pathTemplate"]):
                relations.append("same_path_prefix")
            if route["handler"]["range"]["file"] == other["handler"]["range"]["file"]:
                relations.append("same_handler_module")
                for symbol in (route["handler"]["symbolId"], other["handler"]["symbolId"]):
                    if symbol not in shared:
                        shared.append(symbol)
            auth = _auth_ids(route)
            both_auth = [item for item in auth if item in _auth_ids(other)]
            if both_auth:
                relations.append("shared_auth_symbol")
                shared.extend(both_auth)
            if not relations:
                continue
            deduped = []
            for item in shared:
                if item not in deduped:
                    deduped.append(item)
            if not deduped and relations != ["same_path_prefix"]:
                relations = [item for item in relations if item == "same_path_prefix"]
            if not relations:
                continue
            related.append(
                {
                    "routeId": other["id"],
                    "relations": relations,
                    "sharedSymbolIds": deduped,
                }
            )
            if len(related) >= 24:
                break
        route["relatedRoutes"] = related


def _model_ids(route: dict) -> list[str]:
    found = []
    for access in route["dataAccesses"]:
        symbol = access["object"].get("symbolId")
        if symbol and symbol not in found:
            found.append(symbol)
    return found


def _auth_ids(route: dict) -> list[str]:
    return [step["symbolId"] for step in route["authChain"]]


def _static_prefix(path: str) -> str:
    for part in path.split("/"):
        if part and not part.startswith("{"):
            return part
    return ""


def _range(file: str, start: int, end: int) -> dict:
    if start < 1:
        start = 1
    if end < start:
        end = start
    return {"file": file, "startLine": start, "endLine": end}


def _snippet(text: str, file: str, start: int, end: int, limit: int, truncated: bool) -> dict | None:
    body = (text or "").strip("\n")
    if not body:
        return None
    limit = min(limit, 480)
    cut = truncated or len(body) > limit
    if len(body) > limit:
        body = body[:limit]
    return {"text": body, "truncated": cut, "range": _range(file, start, end)}


def _coverage_partial(auth: list[dict], graph: list[dict], accesses: list[dict], omissions: list[dict]) -> bool:
    if any(item["reason"] != "snippet_budget" for item in omissions):
        return True
    if any(step.get("expanded") != "yes" for step in auth):
        return True

    def walk(nodes: list[dict]) -> bool:
        for node in nodes:
            if node.get("resolution") == "ambiguous" or node.get("expanded") == "partial":
                return True
            if node.get("resolution") == "resolved" and node.get("expanded") != "yes":
                return True
            if walk(node.get("children") or []):
                return True
        return False

    if walk(graph) or any(walk(step.get("calls") or []) for step in auth):
        return True
    return any(
        access["ownershipEvidence"]["inPredicate"] == "unknown" or access["ownershipEvidence"]["stampedOnWrite"] == "unknown"
        for access in accesses
    )


def _count_call_nodes(auth: list[dict], graph: list[dict]) -> int:
    def walk(nodes: list[dict]) -> int:
        total = 0
        for node in nodes:
            total += 1
            total += walk(node.get("children") or [])
        return total

    return sum(walk(step.get("calls") or []) for step in auth) + walk(graph)


def _count_snippets(registration: dict, auth: list[dict], graph: list[dict], accesses: list[dict]) -> int:
    count = 1 if "snippet" in registration else 0

    def walk(node: dict) -> None:
        nonlocal count
        if "snippet" in node:
            count += 1
        for child in node.get("children") or node.get("calls") or []:
            if isinstance(child, dict) and ("calleeName" in child or "calls" in child or "children" in child):
                walk(child)

    for step in auth:
        if "snippet" in step:
            count += 1
        for call in step.get("calls") or []:
            walk(call)
    for call in graph:
        walk(call)
    for access in accesses:
        if "snippet" in access:
            count += 1
    return count
