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

The static stage scans each target, finds every advisory route in the graph, and runs the review runner with a scripted model that votes `present` citing each data access in turn. A route is reachable when one of those votes stands. No network call is made.

The review stage sends only the advisory routes to the model. Every other route is answered `inconclusive` without a call. It reads `REVIEW_MODEL_API_KEY` and `REVIEW_MODEL_BASE_URL` like the scan API. Cost scales with prompt size: the static report prints approximate tokens per route.

Checkouts, graphs and reports are under `.work/idor-benchmark`. A graph is cached per scanner source fingerprint, so changing `src/scanner` rescans and changing `src/review` does not. `--fingerprint` reuses graphs from an earlier scanner. A target that is not cached needs Joern 4.0.684 and Java 21 (see the root README); without Joern the target is skipped and named in the report.

Advisory paths are the public paths. Matching ignores parameter names (`{id}`, `:id`) and accepts a segment-aligned suffix, because the scanner does not always record a mount prefix. An exact path wins; duplicate routes are all reviewed.

## Static results on 2026-11-24

Aegra and Langflow, from graphs cached on 2026-11-17. The other targets need Joern.

| Code | Vulnerable routes reachable |
|---|---|
| `main` (scanner `20221709d4c7`) | 0 of 15 (Langflow 1.9.1 was not cached for this scanner) |
| `main` + galyoss/code-atlas#9 (scanner `51794a56d859`) | 16 of 17; the miss is the image-download gap |
