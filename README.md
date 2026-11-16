# CodeAtlas

A full-window code graph for exploring route handlers, their recorded calls, and
source evidence. The app currently opens two bundled, hand-authored examples;
Aegra is selected by default.

## Run locally

Use Node.js 22.12 or newer (verified with Node 22.18 and npm 10.9).

```sh
npm ci
npm run dev -- --host 127.0.0.1
```

The committed lockfile supports `npm ci` with npm 10.9. Dependency refreshes were
performed with npm 11.6.2 to avoid an npm 10 optional-peer resolution bug.

Open the URL printed by Vite. No account, backend, external API, or CDN is needed.
Fonts and icons are bundled with the app.

```sh
npm run typecheck
npm test
npm run build
npm run preview -- --host 127.0.0.1
```

The build emits `dist/index.html` and hashed assets. Preview normally serves at
<http://127.0.0.1:4173>. `dist/` is generated and ignored. A static host can serve the
contents of `dist/`; this repository does not configure a deployment.

## Explore

The initial view keeps labels readable. When the full overview would be too small,
it starts around the selected route; the canvas indicates when nodes are offscreen.

- Click a node to select it. Its **+** button or **Open calls** reveals only direct
  recorded calls. One deeper branch stays open, with ancestors and context retained.
- Drag the canvas to pan. Focus the canvas and use arrow keys to pan by keyboard.
  Zoom controls (or `+` / `-` while the canvas is focused) change magnification only.
- **Bring selection into view** and **Fit visible graph** move the camera explicitly.
  Expansion leaves existing world positions and the camera unchanged.
- **Back** restores the previous selection, expanded path, pan, and zoom.
  Breadcrumbs return to saved ancestor views; collapse closes a local branch.
- **Source** opens one closeable evidence panel. Escape closes it, or goes Back
  when no panel is open. **Hand-authored example** opens coverage and scope details.
- The repository selector starts a fresh exploration of the other fixture.

## Data boundaries

The unchanged sources are [`docs/code-graph-example-aegra.json`](docs/code-graph-example-aegra.json)
and [`docs/code-graph-example.json`](docs/code-graph-example.json), conforming to
[schema v1.0.0](docs/code-graph-schema.json). Neither is a scanner result or a set of
security findings. Each contains two route slices, not a whole repository graph.
Aegra includes partial expansion and unresolved runtime dispatch; Papertrail is a
synthetic example with complete coverage only within its included slices.

Solid mint arrows are recorded calls. Gold lines summarize route/data relationships;
dashed lines mark authentication context or unresolved calls. Positions do not claim
execution order. Call occurrences remain distinct by route and call ID, even when
they reference the same symbol. Data objects and shared auth definitions aggregate
only as summary/context nodes. Shared auth internals intentionally remain collapsed
in this handler-call explorer. Source snippets, inline checks, resolution, and
coverage are displayed from the documents, without inferring findings.

## Implementation and future scanner integration

- `src/data.ts` imports the two source documents directly.
- `src/graph/adapter.ts` maps schema records to route-specific occurrence identities.
- `src/graph/layout.ts` computes deterministic world positions once per dataset.
- `src/graph/navigation.ts` owns branch navigation and exact view snapshots.
- `src/hooks/useAnimatedScene.ts` retargets 600 ms local expansion/collapse animation;
  reduced-motion preferences remove it. Edges use the same animated node positions.
- `src/components/` renders the canvas and evidence panel. React renders source as text.

A future scanner should supply a validated schema document at the `adaptGraph`
boundary instead of the bundled imports. Authentication, scan submission, persisted
reports, findings, and large-repository layout/performance are separate work. The
current layout is designed for bounded route slices, not arbitrary full-repository
scale. Focused tests cover fixture identity, edge provenance, direct expansion,
branch switching, stale selections, camera isolation, and history restoration;
production browser interaction still needs separate verification.

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
