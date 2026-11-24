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
python benchmarks/idor/run.py --rescore .work/idor-benchmark/reports/<run>.json   # re-match routes, no model calls
python benchmarks/idor/report.py <run>.json [<other run>.json] --notes notes.txt -o report.html
```

The static stage scans each target, finds every advisory route in the graph, and runs the review runner with a scripted model that votes `present` citing each data access in turn. A route is reachable when one of those votes stands. No network call is made.

The review stage sends only the advisory routes to the model. Every other route is answered `inconclusive` without a call. It reads `REVIEW_MODEL_API_KEY` and `REVIEW_MODEL_BASE_URL` like the scan API. Rate limits are waited out; when the account reports `insufficient_quota` the run stops sending, and the remaining routes are marked not reviewed and left out of the metrics. The report records the token counts the API returned. The static report's token estimate (characters / 4) runs about a third low on this JSON.

`report.py` renders one HTML page from run reports: summary, where vulnerable routes were lost, each repository, a model comparison on the routes every run reviewed, and every route's votes.

Checkouts, graphs and reports are under `.work/idor-benchmark`. A graph is cached per scanner source fingerprint, so changing `src/scanner` rescans and changing `src/review` does not. `--fingerprint` reuses graphs from an earlier scanner. A target that is not cached needs Joern 4.0.684 and Java 21 (see the root README); without Joern the target is skipped and named in the report.

Advisory paths are the public paths. Matching ignores parameter names (`{id}`, `:id`) and accepts a segment-aligned suffix, because the scanner does not always record a mount prefix. An exact path wins. Among tied suffix matches, the route whose handler module names the unmatched prefix wins (Open WebUI has eight `/{id}/update` routes); remaining ties are all reviewed.

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

## Model results on 2026-11-24

`main` + galyoss/code-atlas#9 + galyoss/code-atlas#12, 2 agents, agreement threshold 2.

| Model | Vulnerable routes found | Without known gaps | False alarms on fixed routes | Calls | Input tokens | Cost |
|---|---|---|---|---|---|---|
| gpt-4.1 | 19 of 40 | 19 of 33 | 0 of 36 | 176 | 44.1M | $88.10 |
| gpt-4.1-mini (stopped when credit ran out) | 2 of 29 reviewed | 2 of 23 | 0 of 24 | 100 | 27.5M | $11.00 |

On the 51 routes both runs reviewed, gpt-4.1 found 16 of 28 and gpt-4.1-mini 2 of 28. Of gpt-4.1's 21 misses, 15 have no recorded data access (Rails association loads, known gaps), 1 route is not discovered, and 5 are Open WebUI routes where the model took a container ownership check as covering a second object id in the request.
