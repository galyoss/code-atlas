# Aegra v0.11.0 real scan

`aegra-v0.11.0.graph.json` is the **unedited** output of the scanner at
`0d3fec1748d8c7e2321c130a3251bba041322515`, generated on 2026-11-16 at 14:21:20 UTC.
Source: <https://github.com/aegra/aegra>, tag `v0.11.0`, commit
`46055c0b9adffe51fb168974f79dfadaa6edd612`. Its raw `repo.name` is the actual temporary
checkout name; the app displays the repository's human name separately.

SHA-256: `c480d2ea15034d86d163101054d0714230ef9f5e79b94918b535431ad072737e`
(5,616,397 bytes). `aegra-v0.11.0.provenance.json` records versions, invocation,
source/scanner revisions and counts. The original source is Apache-2.0, copyright
2025 Muhammad Ibrahim (@ibbybuilds); the exact license is retained in `AEGRA-LICENSE`.
The graph contains excerpts from that source, and no source text was edited.

59 routes in 9 source files comprise 56 API/core routes and 3 example-code routes.
There are 213 symbols, 3,650 handler-call occurrences, 1,936 auth-call occurrences,
121 auth steps and 108 data accesses. 55 routes have partial coverage; 4 are complete
within their slices. No security review agents ran and no findings are supplied.

## Reproduce locally

Local tools installed for this scan:

- Joern 4.0.684: `/Users/galyossipov/.local/share/code-atlas-tools/joern-4.0.684/joern-cli`
- Temurin Java 21.0.13+9: `/Users/galyossipov/.local/share/code-atlas-tools/java21/jdk-21.0.13+9/Contents/Home`
- macOS `greadlink` compatibility symlink: `/Users/galyossipov/.local/share/code-atlas-tools/bin/greadlink`
- Python 3.11.13 environment: `/Users/galyossipov/code/code-atlas/.venv`
- Pinned source: `/tmp/export-fastapi-aegra-46055c0`

The original operational report and parser/overlay artifacts are preserved locally
in `.work/atlas-real-scan/scan-report.md` and that directory. Published archive hashes
were verified; the scan used a fresh CPG and overlay, without `--cpg` or `--overlay`.
A repeat invocation may reuse the scanner's cache.

From the combined repository root (Python 3.11+):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e . pytest
# If the source checkout is absent:
git clone --branch v0.11.0 https://github.com/aegra/aegra.git /tmp/export-fastapi-aegra-46055c0
git -C /tmp/export-fastapi-aegra-46055c0 checkout --detach 46055c0b9adffe51fb168974f79dfadaa6edd612

export ATLAS_TOOLS=/Users/galyossipov/.local/share/code-atlas-tools
export JAVA_HOME="$ATLAS_TOOLS/java21/jdk-21.0.13+9/Contents/Home"
export JOERN_HOME="$ATLAS_TOOLS/joern-4.0.684/joern-cli"
export JAVA_OPTS='-Xms256m -Xmx4g'
export PATH="$ATLAS_TOOLS/bin:$JAVA_HOME/bin:$PATH"
mkdir -p .work/atlas-real-scan
.venv/bin/export-fastapi /tmp/export-fastapi-aegra-46055c0 \
  -o .work/atlas-real-scan/aegra.graph.json --joern-home "$JOERN_HOME"
.venv/bin/python -m pytest
```

Validate the committed document and its checksum:

```sh
.venv/bin/python - <<'PY'
import hashlib, json
from pathlib import Path
from scanner.validate import validate_document
path = Path('docs/scans/aegra-v0.11.0.graph.json')
raw = path.read_bytes()
errors = validate_document(json.loads(raw), Path('docs/code-graph-schema.json'))
assert not errors, errors
assert hashlib.sha256(raw).hexdigest() == 'c480d2ea15034d86d163101054d0714230ef9f5e79b94918b535431ad072737e'
print('Valid schema, invariants and SHA-256')
PY
npm run typecheck
npm test
npm run build
```

A new run has a new timestamp/hash. Review and record its provenance before replacing
the committed asset; never substitute a fixture on failure. The scanner's existing
18 Python tests passed with Joern available (none skipped) for this run.
