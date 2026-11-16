"""Thin `export-fastapi` entry. Argument parsing only; the scan lives in `scanner`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scanner.facts import Limits
from scanner.joern_runner import JoernNotFound
from scanner.scan import export_repository
from scanner.validate import validate_document

_DEFAULT_SCHEMA = Path(__file__).resolve().parents[2] / "docs" / "code-graph-schema.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="export-fastapi", description="Export FastAPI routes to a code-graph document.")
    parser.add_argument("repo", type=Path, help="Repository to scan")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Where to write the JSON document")
    parser.add_argument("--schema", type=Path, default=_DEFAULT_SCHEMA, help="Schema 1.0.0 file")
    parser.add_argument("--overlay", type=Path, help="Existing Joern overlay JSON. Skips pysrc2cpg and joern.")
    parser.add_argument("--cpg", type=Path, help="Existing CPG. Skips pysrc2cpg and still runs the overlay script.")
    parser.add_argument("--joern-home", type=Path, help="Directory that contains pysrc2cpg and joern")
    parser.add_argument("--max-call-depth", type=int, default=4)
    parser.add_argument("--max-call-nodes", type=int, default=400)
    parser.add_argument("--max-snippet-chars", type=int, default=480)
    parser.add_argument("--no-cache", action="store_true", help="Do not reuse a cached CPG or overlay")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    if not repo.is_dir():
        print(f"Not a directory: {repo}", file=sys.stderr)
        return 2
    limits = Limits(
        max_call_depth=args.max_call_depth,
        max_call_nodes=args.max_call_nodes,
        max_snippet_chars=min(args.max_snippet_chars, 480),
    )
    try:
        document = export_repository(
            repo,
            limits=limits,
            overlay_path=args.overlay,
            cpg_path=args.cpg,
            joern_home=args.joern_home,
            cache=not args.no_cache,
        )
    except JoernNotFound as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    errors = validate_document(document, args.schema)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output} routes={len(document['routes'])} symbols={len(document['symbolIndex'])}")
    if errors:
        print(f"{len(errors)} schema error(s):", file=sys.stderr)
        for error in errors[:40]:
            print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
