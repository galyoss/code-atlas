"""Measure IDOR recall and precision on published advisories.

Each advisory names routes on a vulnerable revision and a fixed one. The static
stage is free: it scans every target and asks the review runner whether any data
access on each route could carry a present vote at all. The review stage calls the
configured model on those routes only and scores findings: a finding on a
vulnerable route is a true positive, a finding on a fixed route a false positive.

    python benchmarks/idor/run.py                 # static stage
    python benchmarks/idor/run.py --review --model gpt-4.1-mini

Checkouts and graphs live under .work/idor-benchmark. A graph is cached per
scanner source fingerprint, so a scanner change rescans and nothing else does.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from review.model import model_from_env  # noqa: E402
from review.registry import registered_checks  # noqa: E402
from review.runner import present_blocker, review_graph, review_payload, route_context  # noqa: E402
from scan_api.access import clone_at  # noqa: E402
from scanner.scan import export_repository  # noqa: E402

WORK = ROOT / ".work" / "idor-benchmark"
CASES = Path(__file__).with_name("cases.json")


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
    return repo


def graph_for(target: dict, fingerprint: str) -> dict | None:
    path = WORK / "graphs" / f"{target['id']}-{fingerprint}.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    if fingerprint != scanner_fingerprint():
        return None
    repo = checkout(target)
    print(f"  scanning {target['id']}", flush=True)
    started = time.time()
    document = export_repository(repo)
    print(f"  scanned {target['id']} in {time.time() - started:.0f}s", flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return document


def find_route(document: dict, spec: str) -> dict | None:
    method, path = spec.split(" ", 1)
    for route in document["routes"]:
        if route["httpMethod"] == method and route["pathTemplate"] == path:
            return route
    return None


def static_row(document: dict, route: dict | None) -> dict:
    if route is None:
        return {"found": False}
    neighbors, symbols = route_context(document, route)
    check = next(iter(registered_checks()))
    eligible, blockers = [], {}
    for access in route["dataAccesses"]:
        reason = present_blocker(check, route, neighbors, symbols, access["id"])
        if reason is None:
            eligible.append(access["id"])
        else:
            blockers[reason] = blockers.get(reason, 0) + 1
    return {
        "found": True,
        "coverage": route["budget"]["coverage"],
        "accesses": len(route["dataAccesses"]),
        "eligible": eligible,
        "blockers": blockers,
        "payloadChars": len(review_payload(route, neighbors, symbols)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--review", action="store_true", help="call the model on the advisory routes")
    parser.add_argument("--model", default="gpt-4.1-mini")
    parser.add_argument("--agents", type=int, default=2)
    parser.add_argument("--threshold", type=int, default=2)
    parser.add_argument("--only", help="comma-separated target ids")
    parser.add_argument("--label", default="", help="suffix for the report file")
    parser.add_argument("--fingerprint", help="reuse graphs cached by an earlier scanner version")
    args = parser.parse_args()

    cases = json.loads(CASES.read_text(encoding="utf-8"))
    fingerprint = args.fingerprint or scanner_fingerprint()
    targets = [t for t in cases["targets"] if not args.only or t["id"] in args.only.split(",")]
    client = model_from_env() if args.review else None
    rows = []
    for target in targets:
        print(f"{target['id']}", flush=True)
        document = graph_for(target, fingerprint)
        if document is None:
            print(f"  no graph cached for scanner {fingerprint}", flush=True)
            continue
        expected = []
        for advisory in cases["advisories"]:
            if target["id"] in advisory["vulnerable"]:
                expected += [(advisory["id"], spec, True) for spec in advisory["routes"]]
            elif target["id"] in advisory["fixed"]:
                expected += [(advisory["id"], spec, False) for spec in advisory["routes"]]
        routes = {spec: find_route(document, spec) for _, spec, _ in expected}
        findings: dict[str, list[dict]] = {}
        votes: dict[str, list[dict]] = {}
        if args.review:
            ids = [route["id"] for route in routes.values() if route is not None]
            started = time.time()
            result = review_graph(
                document,
                model=args.model,
                agent_count=args.agents,
                agreement_threshold=args.threshold,
                client=client,
                route_ids=ids,
            )
            print(f"  reviewed {len(ids)} routes in {time.time() - started:.0f}s", flush=True)
            for finding in result.findings:
                findings.setdefault(finding["routeId"], []).append(finding)
            for vote in result.votes:
                votes.setdefault(vote["routeId"], []).append(vote)
        for advisory_id, spec, vulnerable in expected:
            route = routes[spec]
            row = {
                "target": target["id"],
                "advisory": advisory_id,
                "route": spec,
                "vulnerable": vulnerable,
                **static_row(document, route),
            }
            if args.review and route is not None:
                row["finding"] = bool(findings.get(route["id"]))
                row["findingAccesses"] = [f.get("dataAccessId") for f in findings.get(route["id"], [])]
                row["votes"] = [
                    {k: v for k, v in vote.items() if k in {"role", "verdict", "reason", "dataAccessId"}}
                    for vote in votes.get(route["id"], [])
                ]
            rows.append(row)

    report = summarize(rows, args, fingerprint)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = WORK / "reports" / f"{stamp}{'-' + args.label if args.label else ''}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(render(report))
    print(f"\nreport: {out}")


def summarize(rows: list[dict], args, fingerprint: str) -> dict:
    positives = [row for row in rows if row["vulnerable"]]
    negatives = [row for row in rows if not row["vulnerable"]]
    summary = {
        "routes": len(rows),
        "found": sum(row["found"] for row in rows),
        "positives": len(positives),
        "positivesReachable": sum(bool(row.get("eligible")) for row in positives),
    }
    if args.review:
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
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scannerFingerprint": fingerprint,
        "model": args.model if args.review else None,
        "agents": args.agents,
        "threshold": args.threshold,
        "summary": summary,
        "rows": rows,
    }


def render(report: dict) -> str:
    lines = []
    for row in report["rows"]:
        mark = "VULN " if row["vulnerable"] else "FIXED"
        if not row["found"]:
            lines.append(f"{mark} {row['target']:16} {row['route']:52} route not found")
            continue
        status = f"eligible {len(row['eligible'])}/{row['accesses']}"
        if "finding" in row:
            verdicts = ",".join(v["verdict"][0] for v in row["votes"])
            status += f"  finding={'YES' if row['finding'] else 'no '} votes[{verdicts}]"
        lines.append(f"{mark} {row['target']:16} {row['route']:52} {status}  ~{row['payloadChars'] // 4000}k tok")
    lines.append(json.dumps(report["summary"]))
    return "\n".join(lines)


if __name__ == "__main__":
    main()
