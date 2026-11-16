"""Validate a document against the schema and the generator invariants."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


def load_schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_document(document: dict, schema_path: Path) -> list[str]:
    schema = load_schema(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = [
        f"{_path(error)}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path))
    ]
    errors.extend(invariant_errors(document))
    return errors


def _path(error) -> str:
    parts = [str(part) for part in error.absolute_path]
    return "/".join(parts) if parts else "<root>"


def invariant_errors(document: dict) -> list[str]:
    errors: list[str] = []
    ids: list[str] = []

    def take(value: str, where: str) -> None:
        if value in ids:
            errors.append(f"duplicate id {value} at {where}")
        ids.append(value)

    for gap in document.get("unresolvedGaps", []):
        take(gap["id"], "unresolvedGaps")
    symbols = {item["id"]: item for item in document.get("symbolIndex", [])}
    for item in document.get("symbolIndex", []):
        take(item["id"], "symbolIndex")
        _range_ok(item.get("range"), f"symbol {item['id']}", errors)
    referenced: set[str] = set()
    route_ids = []
    for route in document.get("routes", []):
        take(route["id"], "routes")
        route_ids.append(route["id"])
        _check_route(route, symbols, referenced, take, errors)
    if set(symbols) != referenced:
        extra = sorted(set(symbols) - referenced)
        missing = sorted(referenced - set(symbols))
        if extra:
            errors.append(f"symbolIndex has unreferenced ids: {extra}")
        if missing:
            errors.append(f"routes reference missing symbols: {missing}")
    frameworks = set(document.get("frameworks") or [])
    route_frameworks = {route["framework"] for route in document.get("routes", [])}
    if frameworks != route_frameworks and document.get("routes"):
        errors.append(f"frameworks {sorted(frameworks)} != route frameworks {sorted(route_frameworks)}")
    languages = set(document.get("languages") or [])
    for route in document.get("routes", []):
        if route["language"] not in languages:
            errors.append(f"route language {route['language']} is not in languages")
    known_routes = set(route_ids)
    for route in document.get("routes", []):
        for related in route.get("relatedRoutes", []):
            if related["routeId"] == route["id"]:
                errors.append(f"{route['id']} relatedRoutes points at itself")
            if related["routeId"] not in known_routes:
                errors.append(f"{route['id']} related route {related['routeId']} is missing")
    return errors


def _check_route(route: dict, symbols: dict, referenced: set[str], take, errors: list[str]) -> None:
    prefix = route["id"]
    handler = route["handler"]
    _ref_symbol(handler["symbolId"], symbols, referenced, errors, f"{prefix} handler")
    symbol = symbols.get(handler["symbolId"])
    if symbol is not None:
        if handler["qualifiedName"] != symbol["qualifiedName"]:
            errors.append(f"{prefix} handler qualifiedName does not match its symbol")
        if handler["range"] != symbol["range"]:
            errors.append(f"{prefix} handler range does not match its symbol")
    _range_ok(route["registration"]["range"], f"{prefix} registration", errors)
    param_ids = set()
    for param in route["entryParams"]:
        take(param["id"], f"{prefix} entryParams")
        param_ids.add(param["id"])
        if param.get("typeSymbolId"):
            _ref_symbol(param["typeSymbolId"], symbols, referenced, errors, param["id"])
        for read in param["reads"]:
            _ref_symbol(read["symbolId"], symbols, referenced, errors, param["id"])
            _range_ok(read["range"], param["id"], errors)
    binding_ids = set()
    for binding in route["identityBindings"]:
        take(binding["id"], f"{prefix} identityBindings")
        binding_ids.add(binding["id"])
        if binding.get("typeSymbolId"):
            _ref_symbol(binding["typeSymbolId"], symbols, referenced, errors, binding["id"])
        _range_ok(binding["range"], binding["id"], errors)
    call_ids: set[str] = set()
    orders: list[int] = []

    def walk(nodes: list[dict], parent_order: int | None, parent_depth: int | None) -> None:
        for node in nodes:
            take(node["id"], f"{prefix} call")
            call_ids.add(node["id"])
            orders.append(node["order"])
            if parent_order is not None and node["order"] <= parent_order:
                errors.append(f"{node['id']} order {node['order']} is not after parent {parent_order}")
            if parent_depth is None:
                if node["depth"] != 1:
                    errors.append(f"{node['id']} root depth is {node['depth']}")
            elif node["depth"] != parent_depth + 1:
                errors.append(f"{node['id']} depth {node['depth']} is not parent+1")
            if node["resolution"] == "resolved":
                _ref_symbol(node.get("symbolId", ""), symbols, referenced, errors, node["id"])
                resolved = symbols.get(node.get("symbolId"))
                if resolved is not None and node["qualifiedName"] != resolved["qualifiedName"]:
                    errors.append(f"{node['id']} qualifiedName does not match its symbol")
            for candidate in node.get("candidates") or []:
                _ref_symbol(candidate, symbols, referenced, errors, node["id"])
            _range_ok(node["callSite"], node["id"], errors)
            walk(node.get("children") or [], node["order"], node["depth"])

    for step in route["authChain"]:
        take(step["id"], f"{prefix} auth")
        _ref_symbol(step["symbolId"], symbols, referenced, errors, step["id"])
        resolved = symbols.get(step["symbolId"])
        if resolved is not None and step["qualifiedName"] != resolved["qualifiedName"]:
            errors.append(f"{step['id']} qualifiedName does not match its symbol")
        if resolved is not None and step["mechanism"] != "inline" and step["range"] != resolved["range"]:
            errors.append(f"{step['id']} range does not match its symbol")
        _range_ok(step["range"], step["id"], errors)
        if step.get("callId"):
            pass
        walk(step.get("calls") or [], None, None)
    walk(route["callGraph"], None, None)
    if orders:
        expected = list(range(1, len(orders) + 1))
        if sorted(orders) != expected:
            errors.append(f"{prefix} call order is not 1..{len(orders)} without gaps")
    access_ids = set()
    for access in route["dataAccesses"]:
        take(access["id"], f"{prefix} dataAccess")
        access_ids.add(access["id"])
        if access["callId"] not in call_ids:
            errors.append(f"{access['id']} callId {access['callId']} is not a call in this route")
        symbol_id = access["object"].get("symbolId")
        if symbol_id:
            _ref_symbol(symbol_id, symbols, referenced, errors, access["id"])
        for flow in access["paramFlows"]:
            if flow["entryParamId"] not in param_ids:
                errors.append(f"{access['id']} param flow {flow['entryParamId']} is missing")
        for binding_id in access["ownershipEvidence"]["identityBindingIds"]:
            if binding_id not in binding_ids:
                errors.append(f"{access['id']} identity binding {binding_id} is missing")
    for step in route["authChain"]:
        produced = step.get("callId")
        if produced and produced not in call_ids:
            errors.append(f"{step['id']} callId {produced} is not a call in this route")
    for binding in route["identityBindings"]:
        produced = binding.get("producedByAuthStepId")
        if produced and produced not in {step["id"] for step in route["authChain"]}:
            errors.append(f"{binding['id']} producedByAuthStepId {produced} is missing")
    counts = route["budget"]["counts"]
    call_count = _count_nodes(route["callGraph"]) + sum(_count_nodes(step.get("calls") or []) for step in route["authChain"])
    if counts["authSteps"] != len(route["authChain"]):
        errors.append(f"{prefix} authSteps count {counts['authSteps']} != {len(route['authChain'])}")
    if counts["callNodes"] != call_count:
        errors.append(f"{prefix} callNodes count {counts['callNodes']} != {call_count}")
    if counts["dataAccesses"] != len(route["dataAccesses"]):
        errors.append(f"{prefix} dataAccesses count mismatch")
    snippet_count = _count_snippets(route)
    if counts["snippets"] != snippet_count:
        errors.append(f"{prefix} snippets count {counts['snippets']} != {snippet_count}")
    coverage = route["budget"]["coverage"]
    non_snippet = [item for item in route["budget"]["omitted"] if item["reason"] != "snippet_budget"]
    if coverage["callGraph"] == "complete" and non_snippet:
        errors.append(f"{prefix} callGraph is complete but has omissions")
    if coverage["callGraph"] == "complete" and _incomplete_calls(route):
        errors.append(f"{prefix} callGraph is complete but an in-repo body is not expanded yes")
    for item in route["budget"]["omitted"]:
        take(item["id"], f"{prefix} omitted")
        if item.get("callId") and item["callId"] not in call_ids:
            errors.append(f"{item['id']} callId is not a call in this route")


def _incomplete_calls(route: dict) -> bool:
    def walk(nodes: list[dict]) -> bool:
        for node in nodes:
            if node["resolution"] == "ambiguous" or node["expanded"] == "partial":
                return True
            if node["resolution"] == "resolved" and node["expanded"] != "yes":
                return True
            if walk(node.get("children") or []):
                return True
        return False

    if any(step["expanded"] != "yes" for step in route["authChain"]):
        return True
    return walk(route["callGraph"]) or any(walk(step.get("calls") or []) for step in route["authChain"])


def _ref_symbol(symbol_id: str, symbols: dict, referenced: set[str], errors: list[str], where: str) -> None:
    if not symbol_id or symbol_id not in symbols:
        errors.append(f"{where} symbolId {symbol_id} is missing")
        return
    referenced.add(symbol_id)


def _range_ok(source: dict | None, where: str, errors: list[str]) -> None:
    if not source:
        return
    if source["endLine"] < source["startLine"]:
        errors.append(f"{where} endLine is before startLine")


def _count_nodes(nodes: list[dict]) -> int:
    return sum(1 + _count_nodes(node.get("children") or []) for node in nodes)


def _count_snippets(node) -> int:
    if isinstance(node, dict):
        count = 1 if "text" in node and "truncated" in node and "range" in node and "calleeName" not in node and "httpMethod" not in node else 0
        # A snippet is an object with text, truncated, and range, and nothing else required.
        if set(node) >= {"text", "truncated", "range"} and "calleeName" not in node and "id" not in node:
            count = 1
        else:
            count = 0
        for value in node.values():
            count += _count_snippets(value)
        return count
    if isinstance(node, list):
        return sum(_count_snippets(item) for item in node)
    return 0
