"""Measure IDOR recall and precision on published advisories.

Each advisory names routes on a vulnerable revision and a fixed one. The static
stage is free: it scans every target, finds each advisory route in the graph, and
asks the review runner, with a scripted model, whether a present vote on that route
would stand at all. The review stage calls the configured model on those routes
only and scores findings: a finding on a vulnerable route is a true positive, a
finding on a fixed route a false positive.

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

from review.model import ChatCompletionsClient  # noqa: E402
from review.registry import registered_checks  # noqa: E402
from review.runner import review_graph  # noqa: E402
from scan_api.access import clone_at  # noqa: E402
from scanner.joern_runner import JoernNotFound  # noqa: E402
from scanner.scan import export_repository  # noqa: E402

WORK = ROOT / ".work" / "idor-benchmark"
CASES = Path(__file__).with_name("cases.json")
_PARAM = re.compile(r"\{[^}/]*\}|:[A-Za-z_][A-Za-z0-9_]*")


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


def find_routes(document: dict, spec: str) -> list[dict]:
    """Routes for `spec`, ignoring parameter names and a mount prefix the scanner may not record.

    An exact path wins. Otherwise a route matches when one path is a segment-aligned
    suffix of the other; the longest such match wins, and ties are all returned.
    """
    method, path = spec.split(" ", 1)
    want = _segments(path)
    candidates = [route for route in document["routes"] if route.get("httpMethod") == method]
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


def _context_document(document: dict, route: dict) -> dict:
    """The route and the routes it links: enough for the runner to build the same prompt."""
    linked = {link.get("routeId") for link in route.get("relatedRoutes") or [] if isinstance(link, dict)}
    routes = [route] + [other for other in document["routes"] if other.get("id") in linked and other is not route]
    return {**document, "routes": routes}


class _Scripted:
    """Answers present for one route, citing one access; every other route is inconclusive."""

    def __init__(self, route_id: str, access_id: str | None):
        self.route_id, self.access_id, self.prompt_chars = route_id, access_id, 0

    def complete(self, *, model, system, user):
        route_id = json.loads(user)["route"]["id"]
        if route_id != self.route_id:
            return json.dumps({"routeId": route_id, "verdict": "inconclusive", "reason": "context"})
        self.prompt_chars = len(system) + len(user)
        reply = {"routeId": route_id, "verdict": "present", "reason": "probe"}
        if self.access_id is not None:
            reply["dataAccessId"] = self.access_id
        return json.dumps(reply)


class _OnlyRoute:
    """Sends the target route to the model; every other route is inconclusive without a call."""

    def __init__(self, inner, route_id: str):
        self.inner, self.route_id, self.seconds = inner, route_id, []

    def complete(self, *, model, system, user):
        route_id = json.loads(user)["route"]["id"]
        if route_id != self.route_id:
            return json.dumps({"routeId": route_id, "verdict": "inconclusive", "reason": "context"})
        started = time.time()
        try:
            return self.inner.complete(model=model, system=system, user=user)
        finally:
            self.seconds.append(round(time.time() - started, 1))


def _review(document: dict, route: dict, client, args) -> tuple[list[dict], list[dict]]:
    result = review_graph(
        _context_document(document, route),
        model=args.model,
        agent_count=args.agents,
        agreement_threshold=args.threshold,
        client=client,
        checks=(next(iter(registered_checks())),),
    )
    votes = [vote for vote in result.votes if vote["routeId"] == route["id"]]
    findings = [finding for finding in result.findings if finding["routeId"] == route["id"]]
    return votes, findings


def static_row(document: dict, route: dict, args) -> dict:
    """Whether a present vote on `route` could stand, citing each of its accesses in turn."""
    accesses = [access.get("id") for access in route.get("dataAccesses") or [] if isinstance(access, dict)]
    probe = argparse.Namespace(model="probe", agents=1, threshold=1)
    eligible, blockers, prompt_chars = [], {}, 0
    for access_id in accesses or [None]:
        client = _Scripted(route["id"], access_id)
        votes, _ = _review(document, route, client, probe)
        prompt_chars = max(prompt_chars, client.prompt_chars)
        vote = votes[0] if votes else {"verdict": "inconclusive", "reason": "no vote"}
        if vote["verdict"] == "present":
            if access_id is not None:
                eligible.append(access_id)
        else:
            blockers[vote["reason"]] = blockers.get(vote["reason"], 0) + 1
    return {
        "routeId": route["id"],
        "path": route.get("pathTemplate"),
        "coverage": (route.get("budget") or {}).get("coverage"),
        "accesses": len(accesses),
        "eligible": eligible,
        "blockers": blockers,
        "promptChars": prompt_chars,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--review", action="store_true", help="call the model on the advisory routes")
    parser.add_argument("--model", default="gpt-4.1")
    parser.add_argument("--agents", type=int, default=2)
    parser.add_argument("--threshold", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=60, help="seconds per model call")
    parser.add_argument("--only", help="comma-separated target ids")
    parser.add_argument("--label", default="", help="suffix for the report file")
    parser.add_argument("--fingerprint", help="reuse graphs cached by an earlier scanner version")
    args = parser.parse_args()

    cases = json.loads(CASES.read_text(encoding="utf-8"))
    fingerprint = args.fingerprint or scanner_fingerprint()
    only = set(args.only.split(",")) if args.only else None
    targets = [target for target in cases["targets"] if only is None or target["id"] in only]
    model = ChatCompletionsClient(timeout=args.timeout) if args.review else None
    rows, skipped = [], {}
    for target in targets:
        print(target["id"], flush=True)
        document, reason = graph_for(target, fingerprint)
        if document is None:
            print(f"  {reason}", flush=True)
            skipped[target["id"]] = reason
            continue
        for advisory in cases["advisories"]:
            if target["id"] in advisory["vulnerable"]:
                vulnerable = True
            elif target["id"] in advisory["fixed"]:
                vulnerable = False
            else:
                continue
            for spec in advisory["routes"]:
                matches = find_routes(document, spec)
                row = {
                    "target": target["id"],
                    "advisory": advisory["id"],
                    "route": spec,
                    "vulnerable": vulnerable,
                    "gap": "gap" in advisory,
                    "found": bool(matches),
                    "matches": [static_row(document, route, args) for route in matches],
                }
                if args.review and matches:
                    row["finding"] = False
                    for match in row["matches"]:
                        route = next(item for item in matches if item["id"] == match["routeId"])
                        client = _OnlyRoute(model, route["id"])
                        votes, findings = _review(document, route, client, args)
                        match["votes"] = [
                            {key: vote[key] for key in ("role", "verdict", "reason", "dataAccessId") if key in vote}
                            for vote in votes
                        ]
                        match["findings"] = findings
                        match["callSeconds"] = client.seconds
                        row["finding"] = row["finding"] or bool(findings)
                rows.append(row)

    report = summarize(rows, skipped, args, fingerprint)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = WORK / "reports" / f"{stamp}{'-' + args.label if args.label else ''}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
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
        tp = sum(row.get("finding", False) for row in positives)
        fp = sum(row.get("finding", False) for row in negatives)
        summary.update(
            truePositives=tp,
            falseNegatives=len(positives) - tp,
            falsePositives=fp,
            trueNegatives=len(negatives) - fp,
            recall=round(tp / len(positives), 3) if positives else None,
            precision=round(tp / (tp + fp), 3) if tp + fp else None,
        )
    return summary


def summarize(rows: list[dict], skipped: dict, args, fingerprint: str) -> dict:
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scannerFingerprint": fingerprint,
        "model": args.model if args.review else None,
        "agents": args.agents,
        "threshold": args.threshold,
        "summary": _score(rows, args.review),
        "summaryWithoutKnownGaps": _score([row for row in rows if not row["gap"]], args.review),
        "skippedTargets": skipped,
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
        tokens = max(m["promptChars"] for m in row["matches"]) // 4000
        lines.append(f"{mark} {row['target']:28} {row['route']:62} {status}  ~{tokens}k tok{gap}")
    for target, reason in report["skippedTargets"].items():
        lines.append(f"SKIP  {target:28} {reason}")
    lines.append("all:              " + json.dumps(report["summary"]))
    lines.append("without gaps:     " + json.dumps(report["summaryWithoutKnownGaps"]))
    return "\n".join(lines)


if __name__ == "__main__":
    main()
