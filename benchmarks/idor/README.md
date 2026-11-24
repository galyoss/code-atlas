# IDOR benchmark

`cases.json` pins published IDOR advisories to a vulnerable and a fixed revision. A vulnerable route should get a finding. The same route on the fixed revision should not.

| Repository | Framework | Advisories | Known gaps |
|---|---|---|---|
| Aegra | FastAPI | 1 (3 routes) | |
| Langflow | FastAPI | 5 (12 routes) | image download reads file storage |
| Open WebUI | FastAPI | 7 (10 routes) | 2 advisories read vector-store collections |
| PraisonAI platform | FastAPI, monorepo `path` | 1 (3 routes) | |
| Chatwoot | Rails | 1 (7 routes) | |
| Huginn | Rails | 1 (1 route) | |
| Fat Free CRM | Rails | 1 (1 route) | Rails comes from the gemspec, so the adapter is not picked |
| Khoj | FastAPI | 1 (1 route) | Django ORM |

`gap` marks a case the scanner is known not to model. Reports show totals with and without those cases. `outOfScope` lists advisories that route-level analysis cannot score, and the TypeScript Express apps the adapter does not read yet.

## Run

```bash
python benchmarks/idor/run.py                                   # static stage, no model
python benchmarks/idor/run.py --review --model gpt-4.1          # calls the model
python benchmarks/idor/run.py --only open-webui-v0.8.5,open-webui-v0.8.6
```

The static stage scans each target, finds every advisory route in the graph, and asks the gate whether a `present` vote citing each of the route's data accesses would stand. A route is reachable when one would. No network call is made.

The review stage runs the hunter and skeptic agents on the advisory routes only (`route_ids`); every route stays visible to their graph tools. It reads `REVIEW_MODEL_API_KEY` and `REVIEW_MODEL_BASE_URL` like the scan API, and `--concurrency` sets how many agent runs are in flight. The report records prompt, cached and completion tokens and, for models in `PRICES`, an estimated cost. A run that hits `insufficient_quota` stops sending, and the routes it never reviewed are left out of the metrics. The static report's token column is the agent's opening packet; tool calls add to it.

Checkouts, graphs and reports are under `.work/idor-benchmark`. A graph is cached per scanner source fingerprint, so changing `src/scanner` rescans and changing `src/review` does not. `--fingerprint` reuses graphs from an earlier scanner. A target that is not cached needs Joern 4.0.684 and Java 21 (see the root README); without Joern the target is skipped and named in the report.

Advisory paths are the public paths. Matching ignores parameter names (`{id}`, `:id`) and accepts a segment-aligned suffix, because the scanner does not always record a mount prefix. An exact path wins; duplicate routes are all reviewed.

On macOS the Joern 4.0.684 launch scripts call `greadlink`. Install coreutils, or put a `greadlink` that runs `/usr/bin/readlink "$@"` on `PATH`.

## Static results on 2026-11-24

Vulnerable routes reachable, counting known gaps. `#9` is `main` + galyoss/code-atlas#9 (scanner `51794a56d859`); `#12` adds galyoss/code-atlas#12.

| Repository | #9 | #12 | What blocks the rest |
|---|---|---|---|
| Aegra | 3 of 3 | 3 of 3 | |
| Langflow | 13 of 14 | 13 of 14 | image download reads file storage (known gap) |
| Open WebUI | 0 of 10 | 5 of 10 | `process/files/batch` has no data access; 4 routes are vector-store gaps. With #9 alone, methods on `Files = FilesTable()` were `external` and namespace subpackages collided |
| PraisonAI platform | 0 of 3 | 3 of 3 | With #9 alone, `AgentService(session).get(...)` was `external` |
| Chatwoot | route not found | 0 of 7 | routes are found now; the Rails reader does not see association loads such as `Current.account.macros.find(...)` |
| Huginn | route not found | 0 of 1 | route found now; no ActiveRecord data accesses |
| Fat Free CRM | route not found | route not found | known gap: Rails adapter not picked |
| Khoj | 0 of 1 | 0 of 1 | known gap: Django ORM |

On `main` (scanner `20221709d4c7`), Aegra and Langflow reach 0 of 15; Langflow 1.9.1 was not cached for that scanner.

Totals without known gaps: 16 of 33 with #9, 24 of 33 with #12.

## Review results on 2026-11-24 (deep agents)

gpt-4.1, 2 agents (hunter and skeptic), agreement threshold 2, scanner and agents from the `review/deep-agents` branch, report `20261124T084147Z-full-deep-2`. Counts exclude known gaps.

| Repository | Found | False positives on the fixed revision |
|---|---|---|
| Aegra | 3 of 3 | 0 of 3 |
| Langflow | 13 of 13 | 0 of 10 |
| PraisonAI platform | 3 of 3 | 0 of 3 |
| Open WebUI | 1 of 6 (`pin`) | 1 of 6 (`knowledge/{id}/file/add` on 0.9.5) |
| Chatwoot, Huginn | 0 of 8 | 0 of 8 (no Rails data accesses, nothing to cite) |
| **Total** | **20 of 33** (recall 0.61; 20 of the 24 reachable) | **1 of 30** (precision 0.95) |

The whole run cost about $3.95 (3.0M prompt tokens, half of them cached). The old runner sent each route with its neighbors in full: about 39M prompt tokens for the same routes.

Open WebUI misses are the subtler shapes the prompts now name: a child object not tied to the parent it is reached through (`file/remove`, `file/add` on 0.9.4, where the hunter votes present and the skeptic accepts the parent's check), and an owner check in only one branch (`messages/{id}/update`). The false positive cites a load of knowledge bases by `file_id` without an owner check; Open WebUI fixed related issues in later releases, so it may be real, but the benchmark counts it as wrong.
