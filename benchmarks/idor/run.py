"""Measure IDOR recall and precision on published advisories.

Each advisory names routes on a vulnerable revision and a fixed one. The static
stage is free: it scans every target, finds each advisory route in the graph, and
asks the gate whether a present vote citing each of the route's data accesses
would stand. The review stage runs the hunter and skeptic agents on those routes
only (every route stays visible to their graph tools) and scores findings: a
finding on a vulnerable route is a true positive, a finding on a fixed route a
false positive. The report records token usage and, for known models, its cost.

    python benchmarks/idor/run.py                       # static stage
    python benchmarks/idor/run.py --review --model gpt-4.1

The review stage reads REVIEW_MODEL_API_KEY and REVIEW_MODEL_BASE_URL like the scan
API. Checkouts, graphs and reports live under .work/idor-benchmark. A graph is
cached per scanner source fingerprint, so a scanner change rescans and nothing else
does. Scanning a target that is not cached needs Joern (see the README).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from review.gate import present_blocker  # noqa: E402
from review.graph_index import GraphIndex  # noqa: E402
from review.model import chat_model  # noqa: E402
from review.registry import registered_checks  # noqa: E402
from review.runner import review_graph  # noqa: E402
from scan_api.access import clone_at  # noqa: E402
from scanner.joern_runner import JoernNotFound  # noqa: E402
from scanner.scan import export_repository  # noqa: E402

WORK = ROOT / ".work" / "idor-benchmark"
CASES = Path(__file__).with_name("cases.json")
_PARAM = re.compile(r"\{[^}/]*\}|:[A-Za-z_][A-Za-z0-9_]*")
# USD per million tokens: input, cached input, output. Unknown models get no cost estimate.
PRICES = {"gpt-4.1": (2.00, 0.50, 8.00), "gpt-4.1-mini": (0.40, 0.10, 1.60)}


class _Usage:
    """Token usage summed over every review run, and whether the provider refused further requests."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.prompt = self.cached = self.completion = 0
        self.quota_exhausted = False

    def add(self, usage: dict) -> None:
        for totals in usage.values():
            self.prompt += totals.get("inputTokens", 0)
            self.cached += totals.get("cachedInputTokens", 0)
            self.completion += totals.get("outputTokens", 0)

    def public(self) -> dict:
        result = {
            "promptTokens": self.prompt,
            "cachedPromptTokens": self.cached,
            "completionTokens": self.completion,
            "quotaExhausted": self.quota_exhausted,
        }
        price = PRICES.get(self.model)
        if price is not None:
            fresh = self.prompt - self.cached
            result["estimatedUSD"] = round((fresh * price[0] + self.cached * price[1] + self.completion * price[2]) / 1e6, 2)
        return result


def scanner_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in sorted((ROOT / "src" / "scanner").rglob("*")):
        if path.suffix in {".py", ".sc"}:
            digest.update(path.relative_to(ROOT).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def checkout(target: dict) -> Path:
    repo = WORK / "repos" / target["id"]
    if not repo.is_dir():
        print(f"  cloning {target['repository']} at {target['sha'][:7]}", flush=True)
        clone_at(target["repository"], target["sha"], repo)
    return repo / target.get("path", "")


def graph_for(target: dict, fingerprint: str) -> tuple[dict | None, str | None]:
    """The cached or freshly scanned graph, or None and the reason there is none."""
    path = WORK / "graphs" / f"{target['id']}-{fingerprint}.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8")), None
    if fingerprint != scanner_fingerprint():
        return None, f"no graph cached for scanner {fingerprint}"
    repo = checkout(target)
    print(f"  scanning {target['id']}", flush=True)
    started = time.time()
    try:
        document = export_repository(repo)
    except JoernNotFound as exc:
        return None, f"not scanned: {exc}"
    print(f"  scanned {target['id']} in {time.time() - started:.0f}s", flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return document, None


def _segments(path: str) -> list[str]:
    return [_PARAM.sub("{}", part) for part in path.strip("/").split("/") if part]


def route_spec(entry) -> tuple[str, str | None]:
    """A case route: "METHOD /path", or {"route": ..., "handlerFile": ...} when the path alone is ambiguous."""
    if isinstance(entry, dict):
        return entry["route"], entry.get("handlerFile")
    return entry, None


def find_routes(document: dict, spec: str, handler_file: str | None = None) -> list[dict]:
    """Routes for `spec`, ignoring parameter names and a mount prefix the scanner may not record.

    An exact path wins. Otherwise a route matches when one path is a segment-aligned
    suffix of the other; the longest such match wins, and ties are all returned.
    `handler_file` keeps only routes whose handler is in a file ending with it.
    """
    method, path = spec.split(" ", 1)
    want = _segments(path)
    candidates = [route for route in document["routes"] if route.get("httpMethod") == method]
    if handler_file:
        candidates = [route for route in candidates if _handler_file(route).endswith(handler_file)]
    exact = [route for route in candidates if _segments(route.get("pathTemplate", "")) == want]
    if exact:
        return exact
    scored = []
    for route in candidates:
        have = _segments(route.get("pathTemplate", ""))
        shorter, longer = sorted((have, want), key=len)
        if shorter and longer[len(longer) - len(shorter):] == shorter:
            scored.append((len(shorter), route))
    if not scored:
        return []
    best = max(score for score, _ in scored)
    return [route for score, route in scored if score == best]


def _handler_file(route: dict) -> str:
    handler = route.get("handler") if isinstance(route.get("handler"), dict) else {}
    return str((handler.get("range") or {}).get("file") or "")


def static_row(document: dict, route: dict, index: GraphIndex) -> dict:
    """Whether a present vote on `route` could stand, citing each of its accesses in turn."""
    check = next(iter(registered_checks()))
    accesses = [access.get("id") for access in route.get("dataAccesses") or [] if isinstance(access, dict)]
    eligible, blockers = [], {}
    for access_id in accesses:
        reason = present_blocker(check, route, access_id)
        if reason is None:
            eligible.append(access_id)
        else:
            blockers[reason] = blockers.get(reason, 0) + 1
    return {
        "routeId": route["id"],
        "path": route.get("pathTemplate"),
        "coverage": (route.get("budget") or {}).get("coverage"),
        "accesses": len(accesses),
        "eligible": eligible,
        "blockers": blockers,
        # What an agent starts from; tool calls add to it.
        "promptChars": len(json.dumps(index.opening_packet(route["id"]))),
    }


def review_target(document: dict, matches: dict[str, list[dict]], model, args, usage: _Usage) -> dict[str, dict]:
    """One review run over every advisory route of a target. Returns votes and findings per route id."""
    route_ids = sorted({route["id"] for routes in matches.values() for route in routes})
    started = time.time()
    result = review_graph(
        document,
        model=args.model,
        agent_count=args.agents,
        agreement_threshold=args.threshold,
        chat_model=model,
        checks=(next(iter(registered_checks())),),
        route_ids=route_ids,
        max_concurrency=args.concurrency,
    )
    print(f"  reviewed {len(route_ids)} routes in {time.time() - started:.0f}s", flush=True)
    usage.add(result.usage)
    status = {entry["routeId"]: entry["status"] for entry in result.coverage.get("ledger", [])}
    if "not_reviewed" in status.values():
        usage.quota_exhausted = True
    per_route = {}
    for route_id in route_ids:
        per_route[route_id] = {
            "status": status.get(route_id),
            "votes": [_public_vote(vote) for vote in result.votes if vote["routeId"] == route_id],
            "findings": [finding for finding in result.findings if finding["routeId"] == route_id],
        }
    return per_route


def _public_vote(vote: dict) -> dict:
    kept = {key: vote[key] for key in ("role", "verdict", "reason", "dataAccessId", "modelVerdict", "attempts") if key in vote}
    kept["toolCalls"] = len(vote.get("trail") or [])
    kept["trail"] = vote.get("trail") or []
    return kept


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--review", action="store_true", help="call the model on the advisory routes")
    parser.add_argument("--model", default="gpt-4.1")
    parser.add_argument("--agents", type=int, default=2)
    parser.add_argument("--threshold", type=int, default=2)
    parser.add_argument("--concurrency", type=int, default=6, help="agent runs in flight")
    parser.add_argument("--only", help="comma-separated target ids")
    parser.add_argument("--label", default="", help="suffix for the report file")
    parser.add_argument("--fingerprint", help="reuse graphs cached by an earlier scanner version")
    args = parser.parse_args()

    cases = json.loads(CASES.read_text(encoding="utf-8"))
    fingerprint = args.fingerprint or scanner_fingerprint()
    only = set(args.only.split(",")) if args.only else None
    targets = [target for target in cases["targets"] if only is None or target["id"] in only]
    usage = _Usage(args.model)
    model = chat_model(args.model) if args.review else None
    rows, skipped = [], {}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = WORK / "reports" / f"{stamp}{'-' + args.label if args.label else ''}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    for target in targets:
        print(target["id"], flush=True)
        document, reason = graph_for(target, fingerprint)
        if document is None:
            print(f"  {reason}", flush=True)
            skipped[target["id"]] = reason
            continue
        index = GraphIndex(document)
        target_rows, matches = [], {}
        for advisory in cases["advisories"]:
            if target["id"] in advisory["vulnerable"]:
                vulnerable = True
            elif target["id"] in advisory["fixed"]:
                vulnerable = False
            else:
                continue
            for entry in advisory["routes"]:
                spec, handler_file = route_spec(entry)
                found = find_routes(document, spec, handler_file)
                matches[spec] = found
                target_rows.append(
                    {
                        "target": target["id"],
                        "advisory": advisory["id"],
                        "route": spec,
                        "vulnerable": vulnerable,
                        "gap": "gap" in advisory,
                        "found": bool(found),
                        "matches": [static_row(document, route, index) for route in found],
                    }
                )
        if args.review and any(matches.values()):
            if usage.quota_exhausted:
                for row in target_rows:
                    if row["found"]:
                        row["notReviewed"] = "The model account ran out of credit before this route."
            else:
                reviewed = review_target(document, matches, model, args, usage)
                for row in target_rows:
                    if not row["found"]:
                        continue
                    if any(reviewed[m["routeId"]]["status"] == "not_reviewed" for m in row["matches"]):
                        row["notReviewed"] = "The model account ran out of credit before this route."
                        continue
                    row["finding"] = False
                    for match in row["matches"]:
                        outcome = reviewed[match["routeId"]]
                        match.update(votes=outcome["votes"], findings=outcome["findings"], status=outcome["status"])
                        row["finding"] = row["finding"] or bool(outcome["findings"])
        rows.extend(target_rows)
        # Keep what a long paid run has done so far.
        partial = summarize(rows, skipped, args, fingerprint, usage)
        out.with_suffix(".partial.json").write_text(json.dumps(partial, indent=2), encoding="utf-8")

    report = summarize(rows, skipped, args, fingerprint, usage)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    out.with_suffix(".partial.json").unlink(missing_ok=True)
    print(render(report))
    print(f"\nreport: {out}")


def _score(rows: list[dict], review: bool) -> dict:
    positives = [row for row in rows if row["vulnerable"]]
    negatives = [row for row in rows if not row["vulnerable"]]
    summary = {
        "routes": len(rows),
        "found": sum(row["found"] for row in rows),
        "positives": len(positives),
        "positivesReachable": sum(any(m["eligible"] for m in row["matches"]) for row in positives),
    }
    if review:
        # A route the run never sent (credit ran out) is neither found nor missed.
        positives = [row for row in positives if "notReviewed" not in row]
        negatives = [row for row in negatives if "notReviewed" not in row]
        tp = sum(row.get("finding", False) for row in positives)
        fp = sum(row.get("finding", False) for row in negatives)
        recall = tp / len(positives) if positives else None
        precision = tp / (tp + fp) if tp + fp else None
        summary.update(
            notReviewed=sum("notReviewed" in row for row in rows),
            truePositives=tp,
            falseNegatives=len(positives) - tp,
            falsePositives=fp,
            trueNegatives=len(negatives) - fp,
            recall=round(recall, 3) if recall is not None else None,
            precision=round(precision, 3) if precision is not None else None,
            f1=round(2 * precision * recall / (precision + recall), 3) if precision and recall else None,
        )
    return summary


def summarize(rows: list[dict], skipped: dict, args, fingerprint: str, usage: _Usage | None = None) -> dict:
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scannerFingerprint": fingerprint,
        "model": args.model if args.review else None,
        "agents": args.agents,
        "threshold": args.threshold,
        "summary": _score(rows, args.review),
        "summaryWithoutKnownGaps": _score([row for row in rows if not row["gap"]], args.review),
        "skippedTargets": skipped,
        "usage": usage.public() if usage is not None and args.review else None,
        "rows": rows,
    }


def render(report: dict) -> str:
    lines = []
    for row in report["rows"]:
        mark = "VULN " if row["vulnerable"] else "FIXED"
        gap = " (known gap)" if row["gap"] else ""
        if not row["found"]:
            lines.append(f"{mark} {row['target']:28} {row['route']:62} route not found{gap}")
            continue
        eligible = sum(len(m["eligible"]) for m in row["matches"])
        accesses = sum(m["accesses"] for m in row["matches"])
        status = f"eligible {eligible}/{accesses}"
        if len(row["matches"]) > 1:
            status += f" over {len(row['matches'])} routes"
        if "finding" in row:
            verdicts = ",".join(v["verdict"][0] for m in row["matches"] for v in m.get("votes", []))
            status += f"  finding={'YES' if row['finding'] else 'no '} votes[{verdicts}]"
        elif "notReviewed" in row:
            status += "  not reviewed (out of credit)"
        tokens = max(m["promptChars"] for m in row["matches"]) // 4000
        lines.append(f"{mark} {row['target']:28} {row['route']:62} {status}  ~{tokens}k tok{gap}")
    for target, reason in report["skippedTargets"].items():
        lines.append(f"SKIP  {target:28} {reason}")
    lines.append("all:              " + json.dumps(report["summary"]))
    lines.append("without gaps:     " + json.dumps(report["summaryWithoutKnownGaps"]))
    if report.get("usage"):
        lines.append("usage:            " + json.dumps(report["usage"]))
    return "\n".join(lines)


if __name__ == "__main__":
    main()
