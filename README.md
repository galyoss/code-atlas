# CodeAtlas

A full-window code graph for exploring route handlers, recorded calls and source
evidence. The default app opens a **real Joern scan of Aegra v0.11.0**:
59 routes, 213 indexed symbols, and 9 source files at revision `46055c0`.
The unchanged scan document and its provenance are in [`docs/scans`](docs/scans/README.md).

## Run the app locally

Use Node.js 22.12 or newer (verified with Node 22.18 and npm 10.9).

```sh
npm ci
npm run dev -- --host 127.0.0.1
```

Open Vite's URL, normally <http://127.0.0.1:5173>. No account, backend, external
API or CDN is needed; fonts, icons and the scan asset are served locally. The
committed lockfile supports npm 10.9; dependency refreshes used npm 11.6.2 to avoid
an npm 10 optional-peer resolution bug.

```sh
npm run typecheck
npm test
npm run build
npm run preview -- --host 127.0.0.1
```

The production build is served at <http://127.0.0.1:4173>. `dist/` is generated and
ignored. This repository does not configure a frontend deployment.

## Explore the real scan

- The opening graph groups all routes by source file. Its containment lines are
  labeled **Source grouping**, distinct from call edges. The three routes in
  `examples/custom_routes_example.py` remain visibly identified as example code.
- Select a source file and **Browse routes**, or use **Routes 59** from any view.
  The directory searches literal terms across names, paths, HTTP methods and files.
  Select a handler to focus its route slice. The toolbar identifies that scope.
- Select a graph node, then use its **+** button or **Open calls** for direct recorded
  calls. One deeper branch stays open; ancestors and relevant context remain.
  Dense direct-call sets occupy bounded rows across columns instead of a tall stack.
- Drag or use arrow keys on the focused canvas to pan. Zoom controls and `+` / `-`
  change magnification only. **Bring selection into view** and **Fit visible graph**
  move the camera explicitly. Expansion preserves anchors and camera.
- **Back** restores selection, expanded path, scope, pan and zoom, including route
  changes. **All routes** returns to the saved source-file overview.
- **Source** shows the recorded ranges, snippets, resolution and coverage. **Real
  scan · scope & coverage** shows provenance and known gaps. Escape closes a panel
  or goes Back. Reduced-motion preferences remove expansion animation.

## Data boundaries

The scan is route-oriented static analysis, not a deployed-endpoint inventory or
a complete repository call graph. It reports 55 partially covered routes and 4
complete within their slices. Dynamic dispatch, depth/cycle/snippet budgets and
unsupported GraphQL/WebSocket/framework behavior remain recorded gaps. No security
review agents ran; the graph contains no vulnerability findings.

There are 3,650 handler-call occurrences plus 1,936 authentication-call occurrences.
The canvas explores handler calls; shared authentication internals remain collapsed.
Call identities stay distinct by route and call ID. Gold edges are data summaries;
dashed edges are auth context or unresolved targets. Positions do not establish
execution order. Source evidence is rendered as text without inferring findings.

The original [`Aegra`](docs/code-graph-example-aegra.json) and
[`Papertrail`](docs/code-graph-example.json) examples and schema are unchanged. They
remain test/reference fixtures, not selectable product data. A missing or invalid
real asset produces an explicit error instead of falling back to an example.

## Frontend implementation

`src/data.ts` loads the hashed raw JSON asset. `src/graph/adapter.ts` preserves
occurrence identities; `catalog.ts` provides source grouping and literal search.
`layout.ts` assigns fixed positions within the active scope. `navigation.ts` owns
exact view snapshots, and `useAnimatedScene.ts` animates local changes over 600 ms.
Tests cover fixture regressions and every real route's identity, discovery, layout,
source fidelity and history. Browser behavior receives separate verification.

# Scanner

`scanner` (`src/scanner`) is the code scanner. v1 exports FastAPI routes to one [code-graph schema 1.0.0](docs/code-graph-schema.json) document. It runs Joern `pysrc2cpg`, reads the CPG for routes, calls, and SQLAlchemy predicate text, and fills the facts Joern drops (parameter defaults such as `Depends`, import aliases, ORM models) from the Python AST. `inPredicate` is taken from the CPG call text. If that text does not contain the comparison, the value is `unknown`.

GraphQL, WebSockets, dynamic dispatch, other web frameworks, and an LLM judge are recorded in `unresolvedGaps`. v1 does not add Express, Rails, or a second framework.

The `export-fastapi` command is a thin entry point. It parses arguments and calls `scanner`.

## Framework seam

`FrameworkAdapter` in `src/scanner/framework.py` is the seam. It has three methods: `discover_routes`, `read_auth_steps`, and `read_data_accesses`. `FastAPIAdapter` is the only implementation. It owns decorator paths, `Depends`, included routers, and SQLAlchemy `where` / `filter` text. The command calls `read_project(adapter, project)`. `schema_writer`, the validator, and `check_fields` stay on the other side of the seam and do not import an adapter. A later framework is a second adapter, not a rewrite of the writer.

## Run

Requires Python 3.11+ and Joern 4.0.684 (Java 21). Download the archive for this machine from [the v4.0.684 release](https://github.com/joernio/joern/releases/tag/v4.0.684). On macOS arm64 that file is [joern-cli-macos-arm64.zip](https://github.com/joernio/joern/releases/download/v4.0.684/joern-cli-macos-arm64.zip). Unzip it and set `JOERN_HOME` to the `joern-cli` directory. `pysrc2cpg` and `joern` are in that directory, not under `bin/`. The exporter also looks at `/tmp/joern-dist/joern-cli`.

```bash
python3 -m pip install -e .
export-fastapi /path/to/repo -o graph.json
```

`--cpg cpg.bin` skips `pysrc2cpg` and still runs the overlay script. `--overlay overlay.json` skips Joern. The test skips only when the `pysrc2cpg` binary is missing.

```bash
python3 -m pytest
```

The pinned check is aegra tag `v0.11.0` at `46055c0b9adffe51fb168974f79dfadaa6edd612`. It compares `inPredicate`, auth `kind`, and `bindsObjectToCaller` for `POST /threads/{thread_id}/runs` and `GET /threads/{thread_id}`.

## Scan API

`scan-api` is a FastAPI app: `POST /scans`, `GET /scans/{id}`, `GET /scans/{id}/graph`, and `GET /health`. It clones the requested GitHub revision and calls `scanner.scan.export_repository`. It stores `model`, `agentCount`, and `agreementThreshold` on the job and does not run agents. A graph with no agent review is `partial`, and `unresolvedGaps` stay in the document.

The Railway image is `python:3.12-slim`, `git`, Temurin 21, and Joern 4.0.684 (`JOERN_HOME=/opt/joern-cli`). The Linux archive is about 1.8 GB because it ships every language frontend. The image keeps `pysrc2cpg`, `joern`, and `lib`, and drops the other frontends. If `pysrc2cpg` is still missing at runtime, `POST /scans` returns `failed` and does not pretend a scan ran. `GITHUB_TOKEN` is optional and is sent only as a git HTTP header for private repositories.
