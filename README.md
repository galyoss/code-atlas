# CodeAtlas

Atlas saves static code graphs for public GitHub repositories in an account-owned workspace. Each repository is one project. Its 3D graph, 2D inspection, route list and issue view share the same saved revision. The [bundled Aegra scan](docs/scans/README.md) is also available as a public example.

## Run the workspace locally

Use Node.js 22.12+, Python 3.11+, Java 21 and the Joern installation described in [the scan setup](docs/scans/README.md). The workspace uses the built-in macOS sandbox for static analysis. Linux requires bubblewrap (`bwrap`) with unprivileged user namespaces. Start the local product API in one terminal:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
# Export JAVA_HOME and JOERN_HOME for your installation; add their launchers to PATH.
.venv/bin/python -m uvicorn scan_api.workspace_server:app --host 127.0.0.1 --port 8080
```

Start the frontend in another terminal:

```sh
npm ci
npm run dev -- --host 127.0.0.1
```

Open <http://127.0.0.1:5173>, create an account, and paste a public GitHub URL. The worker clones the default branch anonymously, builds a static graph with the existing FastAPI, Express or Rails adapter, and saves the JSON, tracked files and commit SHA. Duplicate submissions by the same account reopen that project. The project selector and the four tabs are available throughout the workspace. A selected route opens its trace in 2D. **Issues Found** shows the available review coverage; workspace graph jobs do not run a vulnerability review.

Accounts, sessions, projects and graphs live under `~/.local/share/code-atlas/workspace`. Set `ATLAS_WORKSPACE_DIR` to another private directory outside the web root to change it. Run one API process per workspace directory. The worker resumes interrupted scans on startup. Vite proxies same-origin workspace API requests to the loopback API.

```sh
npm test
npm run build
npm run preview -- --host 127.0.0.1
```

The preview serves <http://127.0.0.1:4173>. The public sample link also works with only the frontend running. The standalone [scan API](#scan-api) is a separate interface for historical scans.

## Cinematic 3D universe

Choose **3D Mode** in a project workspace, or open
<http://127.0.0.1:4173/?sample=aegra&view=cinematic> in the local preview.
The immersive view shows all 5,920 recorded Aegra nodes and 7,294 relationships:
symbols, route-qualified call occurrences and authentication context. Drag to
orbit, scroll or use the zoom buttons, and click a node for its identity. Pause,
reset and fullscreen controls sit below the scene. **2D Mode** returns to the
preserved investigation. Reduced motion disables ambient animation.

The electric pulses illustrate static scan relationships; they are not measured
runtime traffic. Unconnected star dust is decorative and excluded from counts.
The renderer uses the selected scan, including API scans; it never replaces one
with Aegra. WebGL is required for 3D, with a return to 2D when unavailable.
See [cinematic verification](docs/ATLAS_CINEMATIC_VERIFICATION.md) for local checks and scope.

The left **Explore** rail changes the 3D arrangement between **Files**, **Entry points**
and **Data flow**, smoothly moving the same nodes and their connections while preserving
the camera. Data flow separates handlers, implementation and recorded data terminals.
**All calls / Symbols**, **File cluster** and **Find code** combine to narrow the scene;
counts show the remaining population and **Clear filters** restores it. File clusters
follow the entry source, while search also matches actual call-site files. Symbols
excludes call-level data operations. Layout changes animate even when ambient motion
is paused; reduced-motion preferences make them immediate.
See [3D controls verification](docs/ATLAS_3D_CONTROLS_VERIFICATION.md) for the exact checks.

Data flow uses colored regions for **Endpoints**, **Core logic**, **Data reads**,
**Data writes**, **External / libraries** and **Unresolved targets**. Labels follow
the scene as you orbit. External code is not automatically a network service;
the service role requires explicit RPC evidence in the scan.

Click a node to emphasize its recorded flow and dim the surrounding graph. An
endpoint highlights paths to recorded data terminals; an individual call shows
its ancestors and descendants. Shared symbols show their recorded contexts,
and missing traces are stated explicitly. Arrows remain visible while paused.
Focus temporarily reveals required nodes through the current filters. Clear
the selection or click empty space to restore the original filtered view.
See [semantic focus verification](docs/ATLAS_SEMANTIC_FOCUS_VERIFICATION.md).

## Routes and recorded issues

**List of Routes** reads HTTP methods, paths, handlers and source locations from the open document. Filter by method or coverage and select a result to inspect its trace. **Issues Found** distinguishes recorded review evidence from a graph-only scan. The protected **Graph JSON** download exports the selected project's saved document. The explicit sample downloads its bundled document.

## Explore the network

- The opening canvas contains every indexed symbol and all resolved call pairs.
  Mint ↗ markers identify HTTP entry points; circular blue glyphs are other
  code symbols (functions and classes). Subtle source regions provide context.
  File controls collapse/reopen their symbols in place, preserving real links crossing the region boundary.
- The collapsible left rail emphasizes **Code**, **Entry points**, or **Data flow**
  on the same canvas. View changes morph between a source-file map, an entry-led
  composition and entry → code/calls → data bands. **Files / Symbols** changes resolution;
  **Call depth 0–3** changes only the selected handler or call branch. Mixed manual
  states are labeled. Explicit depth replaces the active entry flow; Data flow’s
  overview paths remain visible and are included in the depth indicator. File resolution
  temporarily hides detail and preserves every saved layer.
- **R / W / RW** badges distinguish reads, writes and both. The 32 owner functions
  summarize 108 route-scoped named object accesses (72 reads, 36 writes), attributed
  only to immediate resolved parents. These are evidence records, not runtime
  counts or unique source sites. An ambiguous target can still have a known effect.
- Select a data-owning function, such as `_prepare_run`, and **Reveal access paths**
  to show its exact access calls and ancestors without opening unrelated siblings.
  Read/object labels help identify the operations; original call names, routes,
  resolution, exact source and all evidence remain in selection and **Source**.
  Call-level persistence effects are identified separately from named object access.
- Select an entry handler to immediately trace every recorded branch to named
  data accesses and explicit persistence-effect frontiers. Unrelated code dims;
  exact intermediate occurrences and definition links remain visible. Inspecting
  any call or its **Source** keeps that flow active. **Clear entry flow** returns to
  the surrounding graph. An entry without evidence says “No data path recorded”;
  the partial scan does not establish that it has no persistence.
- Data flow opens 108 named access calls and their minimal ancestor paths
  (182 detail nodes) alongside all 213 symbols. Selecting an entry adds its other
  explicit read/write frontiers. Named accesses stay terminals even with children;
  propagated wrapper effects yield to deeper recorded terminals. Unknown effects
  never manufacture a path. Manual branches and targeted owner paths are separate
  from both automatic layers.
- Select another glyph to inspect its actual neighbors when no flow is active. Full names appear on hover,
  selection and in **Source**. Double-click a handler/call or use **Open detail** to
  reveal its direct recorded children in the same network. Several branches can
  remain open. Dashed auth context and definition links differ from call arrows;
  unresolved invocations and data accesses have distinct glyphs.
- For a concrete path, find `create_run` and press Enter: its 42 recorded detail
  nodes lead to 34 data terminals (8 with named objects). `get_thread` reveals 8
  detail nodes and 6 terminals. Switching entries replaces only automatic flow;
  manually opened branches and camera stay in place. Dashed definition links
  connect the exact occurrences to canonical symbols without inventing call edges.
- Search matches literal terms across symbol names, qualified names, files and
  route fields. Exact identifiers rank first. Typing highlights the same scene;
  Enter / the arrow explicitly focuses the next result. Clear resets highlighting.
- Drag or use arrow keys on the focused canvas to pan. Wheel zoom is centered on
  the pointer; `+` / `-` and camera buttons zoom about the viewport center. **Bring
  selection into view** and **Fit visible graph** explicitly move the camera.
  Selection and expansion never fit or recenter automatically. A fresh phone-sized
  view starts near a recorded handler at usable magnification; Fit shows the full graph.
- **Back** restores the exact camera, selection, collapsed files and expanded
  occurrences, targeted access paths, active entry flow, view and rail settings. **Source** is
  closeable without graph movement. Escape closes the panel or rail, clears
  search, or goes Back. Shift+Space on a focused glyph toggles its
  recorded children. Reduced-motion preferences settle view changes and expansions immediately.
- **Partial static scan** opens provenance, the original document download, route
  coverage and known gaps. A symbol's source panel includes its incoming/outgoing
  canonical relationships and all supporting route/call/auth-step references.

## Data boundaries

This route-oriented static scan includes example code. It is not a deployed-endpoint
inventory or exhaustive repository graph. 55 routes have partial coverage and 4 are
complete within their slices. Dynamic dispatch, depth/cycle/snippet budgets and
unsupported GraphQL/WebSocket/framework behavior remain recorded gaps. No security
review agents ran; no vulnerability findings are supplied.

All 5,586 call occurrences are retained: 3,650 in handler trees and 1,936 in auth
contexts. Identity includes route, optional auth step and original call ID. Canonical
calls require the immediate parent and callee to have resolved symbol IDs; no edge
jumps across an unresolved intermediate call or infers a target from its name.
Record counts describe static evidence, not runtime execution frequency. Source
ranges, invocation text, snippets, data access and ownership evidence stay intact.

The original [`Aegra`](docs/code-graph-example-aegra.json) and
[`Papertrail`](docs/code-graph-example.json) examples and schema remain test/reference
fixtures. A missing/invalid real asset reports an explicit error without substituting
an example. Raw SHA-256:
`c480d2ea15034d86d163101054d0714230ef9f5e79b94918b535431ad072737e`.

## Frontend architecture and verification

`src/data.ts` loads the immutable scan asset. `graph/adapter.ts` constructs canonical
nodes/aggregated evidence and complete occurrence trees. `catalog.ts` searches
recorded fields. `layout.ts` computes a deterministic stopped D3 source-file layout once.
`view-layout.ts` caches semantic role bands and append-only detail slots per view;
ordinary selection/expansion never moves surviving anchors. View changes deliberately
rearrange identities and returning to Code restores its saved anchors. `flow.ts`
indexes exact occurrence ancestry and terminal frontiers, keeping auth/definition
context distinct from calls. `navigation.ts` owns snapshots and independent manual,
mode and active-flow visibility. `useAnimatedScene.ts` retargets node/edge motion from
the current pose over 740 ms, including rapid interruptions and reduced motion.

Tests independently traverse raw JSON to verify the exact symbol, call-pair and
reference sets. They also cover source fidelity, same-name/ID distinctions,
unresolved-parent data ownership, read-only and unknown-effect cases, exact targeted
access paths, complete entry flow and route/auth identity, independent visibility
layers, collapse/history, pointer zoom, semantic band order, source-map round trips
and non-overlapping glyphs. Visual acceptance uses the
actual production build; results and scope are recorded in
[`ATLAS_NETWORK_VERIFICATION.md`](docs/ATLAS_NETWORK_VERIFICATION.md), the
[controls/data verification](docs/ATLAS_CONTROLS_VERIFICATION.md), and the
[entry-flow/layout verification](docs/ATLAS_ENTRY_FLOW_VERIFICATION.md).

# Scanner

`scanner` (`src/scanner`) is the code scanner. It writes one [code-graph schema 1.0.0](docs/code-graph-schema.json) document. FastAPI still runs Joern `pysrc2cpg` and reads SQLAlchemy `where` / `filter` text, with `Depends` and import aliases filled from the Python AST. Express uses `jssrc2cpg`. Rails uses `rubysrc2cpg`. `inPredicate` is taken from the call text. If that text does not contain the comparison, the value is `unknown`.

GraphQL, WebSockets, dynamic dispatch, web frameworks other than FastAPI, Express, and Rails, and an LLM judge are recorded in `unresolvedGaps`. Findings are not fields of the graph.

The `export-fastapi` command is a thin entry point. It parses arguments and calls `scanner`.

## Framework seam

`FrameworkAdapter` in `src/scanner/framework.py` is the seam. It has three methods: `discover_routes`, `read_auth_steps`, and `read_data_accesses`. `FastAPIAdapter`, `ExpressAdapter`, and `RailsAdapter` implement it. The scanner picks one adapter from the repo: a Rails `Gemfile` plus `config/routes.rb`, an Express `package.json` plus `app.use` or `router`, otherwise FastAPI. It does not run the other adapters and merge the routes. The command calls `read_project(adapter, project)`. `schema_writer`, the validator, and `check_fields` stay on the other side of the seam and do not import an adapter.

## Run

Requires Python 3.11+ and Joern 4.0.684 (Java 21). Download the archive for this machine from [the v4.0.684 release](https://github.com/joernio/joern/releases/tag/v4.0.684). On macOS arm64 that file is [joern-cli-macos-arm64.zip](https://github.com/joernio/joern/releases/download/v4.0.684/joern-cli-macos-arm64.zip). Unzip it and set `JOERN_HOME` to the `joern-cli` directory. `pysrc2cpg`, `jssrc2cpg` (or `jssrc2cpg.sh`), `rubysrc2cpg`, and `joern` are in that directory, not under `bin/`. The exporter also looks at `/tmp/joern-dist/joern-cli`. A missing `jssrc2cpg` or `rubysrc2cpg` stops that scan. The fixture tests can instead pass an overlay, the same path the FastAPI mini-slice uses.

```bash
python3 -m pip install -e .
export-fastapi /path/to/repo -o graph.json
```

`--cpg cpg.bin` skips the language frontend and still runs the overlay script. `--overlay overlay.json` skips Joern. The aegra test skips only when `pysrc2cpg` is missing. Express and Rails fixture tests use an overlay when `jssrc2cpg` or `rubysrc2cpg` is missing.

```bash
python3 -m pytest
```

The pinned check is aegra tag `v0.11.0` at `46055c0b9adffe51fb168974f79dfadaa6edd612`. It compares `inPredicate`, auth `kind`, and `bindsObjectToCaller` for `POST /threads/{thread_id}/runs` and `GET /threads/{thread_id}`.

## IDOR benchmark

`benchmarks/idor/cases.json` pins published IDOR advisories in Aegra and Langflow to a vulnerable and a fixed revision. `python benchmarks/idor/run.py` scans each target with Joern (checkouts and graphs are cached under `.work/idor-benchmark`, per scanner source fingerprint) and reports, for every advisory route, whether any of its data accesses could carry a `present` vote. `--review --model <model>` also runs the review on those routes with the configured provider and reports recall and precision: a finding on a vulnerable route is a true positive, a finding on the fixed revision a false positive. Reports are written to `.work/idor-benchmark/reports`. Aegra's GHSA-q494 is listed as out of scope: the flaw is in a dependency, and Aegra's own code does not change between the vulnerable and fixed releases.

## Scan API

`scan-api` clones the requested GitHub revision and calls `scanner.scan.export_repository`. Once the schema 1.0.0 graph exists, the service deletes the checkout and runs the registered checks. LangGraph reviews up to four routes concurrently and aggregates the votes. The current registry contains the IDOR check.

For each route and check, the runner makes `agentCount` independent calls to the scan's `model`, alternating hunter and skeptic. Each call receives the route, its linked neighbor routes, and the symbol-index entries they reference. Each vote records the check, route, role, verdict, and reason. A `present` IDOR vote must cite a `dataAccessId` from the route with a source snippet and range. A finding forms when votes on the same access reach `agreementThreshold`. It records the route, check, data access, graph excerpt under `evidence`, threshold, count, and agreeing vote IDs.

A `present` vote stands on a partially covered route only when the recorded call path from the handler to the cited access is resolved; unresolved calls elsewhere in the route are left to the reviewer and recorded on the finding as `routeCoverage`. An unresolved call on that path, an access that is not on a recorded path, or a missing source snippet downgrades the vote to `inconclusive`. Related routes reach the model as summaries (method, path, handler, data accesses and their ownership evidence) without their code. An invalid vote or failed model call also records an `inconclusive` vote and makes the scan `partial`. The graph and other votes and findings remain available in that case. The scan is `completed` when all routes have a full vote set for every check and all model calls returned valid votes. The API requires a `model` and an `agreementThreshold` at most `agentCount`.

Set `OPENAI_API_KEY` in the service environment before launching `scan-api` to use OpenAI. For a compatible provider, set `CODEATLAS_LLM_BASE_URL` to its API base URL (for example, `https://provider.example/v1`) and `CODEATLAS_LLM_API_KEY` to that provider's credential. Remote providers require HTTPS. HTTP is allowed for loopback endpoints at `127.0.0.1`, `[::1]`, or `localhost`. The model selected in `POST /scans` must support Chat Completions JSON object mode. Calls have a 60-second timeout. Without provider credentials, scans return the graph and remain `partial`.

`GET /scans/{id}` returns the votes and findings. `GET /scans/{id}/summary` returns the same record without the graph, plus `createdAt`, `hasGraph`, `inProgress` (this process still works on it) and `reviewing`. `GET /scans` lists summaries, newest first. `GET /scans/{id}/files` returns the checkout's tracked paths (`git ls-files`, up to 20,000), recorded before the checkout is deleted. `GET /review` reports whether a model provider is configured. `GET /scans/{id}/graph` returns the schema 1.0.0 document, including `unresolvedGaps`. Use `GET /health` to check that the service is running.

The Railway image is `python:3.12-slim`, `git`, Temurin 21, and Joern 4.0.684 (`JOERN_HOME=/opt/joern-cli`). The Linux archive is about 1.8 GB because it ships every language frontend. The image keeps `pysrc2cpg`, `jssrc2cpg`, `rubysrc2cpg`, `joern`, and `lib`, and drops the other frontends. If the frontend for the selected adapter is missing at runtime, `POST /scans` returns `failed` and does not pretend a scan ran. `GITHUB_TOKEN` is optional and is sent only as a git HTTP header for private repositories.
