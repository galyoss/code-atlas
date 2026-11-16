# CodeAtlas

A continuous code network for exploring a real Joern scan of **Aegra v0.11.0**,
revision `46055c0`. Atlas opens on all **213 indexed symbols in 43 source files**,
including 59 route handlers, with **244 recorded directed call pairs**. Of these,
141 cross source files. Every aggregated pair retains its route-specific evidence;
1,222 recorded occurrences support the canonical links.

The unchanged document and provenance are in [`docs/scans`](docs/scans/README.md).

## Run locally

Use Node.js 22.12 or newer.

```sh
npm ci
npm run dev -- --host 127.0.0.1
```

Open <http://127.0.0.1:5173>. No account, backend, external API or CDN is needed;
fonts, icons and the scan asset are served locally. The committed lockfile supports
npm 10.9; dependency refreshes used npm 11.6.2 to avoid an npm 10 optional-peer bug.

```sh
npm run typecheck
npm test
npm run build
npm run preview -- --host 127.0.0.1
```

The production preview is at <http://127.0.0.1:4173>. `dist/` is generated and
ignored. This repository does not configure a frontend deployment.

## Explore the network

- The opening canvas contains every indexed symbol and all resolved call pairs.
  Square mint glyphs are handlers; circular blue glyphs are other symbols. Subtle
  source regions provide context. File controls collapse/reopen their symbols in
  place, preserving real links crossing the region boundary.
- Select any glyph to highlight its actual neighbors. Full names appear on hover,
  selection and in **Source**. Double-click a handler/call or use **Open detail** to
  reveal its direct recorded children in the same network. Several branches can
  remain open. Dashed auth context and definition links differ from call arrows;
  unresolved invocations and data accesses have distinct glyphs.
- For a concrete path, find `create_run`, press Enter to focus its canonical node,
  open its calls, select the `_prepare_run` occurrence and open it. The canonical
  `_prepare_run` symbol remains connected to its recorded callers across files.
  Open another handler independently; the first branch and camera stay in place.
- Search matches literal terms across symbol names, qualified names, files and
  route fields. Exact identifiers rank first. Typing highlights the same scene;
  Enter / the arrow explicitly focuses the next result. Clear resets highlighting.
- Drag or use arrow keys on the focused canvas to pan. Wheel zoom is centered on
  the pointer; `+` / `-` and camera buttons zoom about the viewport center. **Bring
  selection into view** and **Fit visible graph** explicitly move the camera.
  Selection and expansion never fit or recenter automatically. A fresh phone-sized
  view starts near a recorded handler at usable magnification; Fit shows the full graph.
- **Back** restores the exact camera, selection, collapsed files and expanded
  occurrences. **Source** is closeable without graph movement. Escape closes the
  panel, clears search, or goes Back. Shift+Space on a focused glyph toggles its
  recorded children. Reduced-motion preferences settle expansions immediately.
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
recorded fields. `layout.ts` computes a deterministic stopped D3 group layout once
and uses fixed collision-free symbol slots; an append-only spatial allocator places
new detail near its parent and reserves those anchors for the session. Allocations
never move surviving nodes. `navigation.ts` owns view snapshots, and
`useAnimatedScene.ts` retargets local node/edge motion over 600 ms.

Tests independently traverse raw JSON to verify the exact symbol, call-pair and
reference sets. They also cover source fidelity, same-name/ID distinctions,
unresolved-parent boundaries, multiple open branches, collapse/history, pointer
zoom, initial framing and fixed non-overlapping glyphs. Visual acceptance uses the
actual production build and is documented separately by the behavior verifier.

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
