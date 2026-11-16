# scanner

`scanner` (`src/scanner`) is the code scanner. It writes one [code-graph schema 1.0.0](docs/code-graph-schema.json) document. FastAPI still runs Joern `pysrc2cpg` and reads SQLAlchemy `where` / `filter` text, with `Depends` and import aliases filled from the Python AST. Express uses `jssrc2cpg`. Rails uses `rubysrc2cpg`. `inPredicate` is taken from the call text. If that text does not contain the comparison, the value is `unknown`.

GraphQL, WebSockets, dynamic dispatch, web frameworks other than FastAPI, Express, and Rails, and an LLM judge are recorded in `unresolvedGaps`.

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

## Scan API

`scan-api` is a FastAPI app: `POST /scans`, `GET /scans/{id}`, `GET /scans/{id}/graph`, and `GET /health`. It clones the requested GitHub revision and calls `scanner.scan.export_repository`. It stores `model`, `agentCount`, and `agreementThreshold` on the job and does not run agents. A graph with no agent review is `partial`, and `unresolvedGaps` stay in the document.

The Railway image is `python:3.12-slim`, `git`, Temurin 21, and Joern 4.0.684 (`JOERN_HOME=/opt/joern-cli`). The Linux archive is about 1.8 GB because it ships every language frontend. The image keeps `pysrc2cpg`, `jssrc2cpg`, `rubysrc2cpg`, `joern`, and `lib`, and drops the other frontends. If the frontend for the selected adapter is missing at runtime, `POST /scans` returns `failed` and does not pretend a scan ran. `GITHUB_TOKEN` is optional and is sent only as a git HTTP header for private repositories.
