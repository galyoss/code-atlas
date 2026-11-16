# scanner

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
