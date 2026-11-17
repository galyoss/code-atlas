# IDOR benchmark results

Run on 2026-11-17 with `benchmarks/idor/run.py` against the cases in `cases.json`:
17 vulnerable advisory routes and 13 of the same routes on fixed revisions
(Aegra 0.9.6/0.9.7, Langflow 1.7.3/1.9.1). Two agents per route, both must agree
on the same data access. Reports are in `.work/idor-benchmark/reports`.

| Stage | Reachable | Recall | False positives |
|---|---|---|---|
| Before the fixes, any model | 0 of 15 (Langflow 1.9.1 crashed) | 0 | — |
| After the fixes, gpt-4.1-mini | 16 of 17 | 6/17 (0.35) | 0/13 |
| After the fixes, gpt-4.1 | 16 of 17 | 14/17 (0.82) | 0/13 |

"Reachable" means at least one data access on the route could carry a `present`
vote that the runner keeps.

## What blocked detection

1. Route-wide coverage gate. Any unresolved call anywhere in a route blocked every
   `present` vote on it, and nearly every route had one. A present vote now needs the
   cited access's own recorded path to be resolved; the rest of the route is shown to
   the reviewer and recorded on the finding as `routeCoverage`.
2. Python builtins (`str`, `isinstance`, `hasattr`, ...) were `ambiguous` with a
   `dynamic_dispatch` omission. They are now `external`.
3. Chained calls (`select(X).where(...)`) were bare-name calls and `ambiguous`. They
   are now method calls on the previous result.
4. `session.get(Model, key)` primary-key loads were not data accesses, so routes such
   as `DELETE /api_key/{id}` had nothing to cite.
5. Load snippets were the query expression alone. They now include the next lines of
   the function, where `if obj.user_id != user.identity: raise` checks live, and any
   later `stmt = stmt.where(...)` refinement, which also counts toward `inPredicate`.
6. Neighbor routes were embedded in full: about 1 MB of a 1.17 MB prompt. They are
   summaries now, and prompts dropped from about 290k to about 30k tokens.
7. The model read `present`/`absent` as the ownership check, not the vulnerability,
   and voted `absent` while describing a missing check. The prompt now defines the
   verdict explicitly.
8. A `present` vote without a valid `dataAccessId` was silently downgraded. It now
   gets one corrected answer from the same agent.
9. A re-export cycle between modules crashed the scanner (Langflow 1.9.1).

## Remaining misses (gpt-4.1)

- `GET /files/images/{flow_id}/{file_name}`: the object is read from file storage, not
  the database, so the scanner records no data access.
- `POST /threads/{thread_id}/runs` (Aegra 0.9.6): both agents voted present but cited
  different accesses, and agreement is counted per access.
- `POST /responses` (Langflow 1.7.3): the agents split; the vulnerable branch (load by
  UUID without the owner filter) sits next to a protected branch in the same helper.

Precision here covers only the fixed revisions of the advisory routes. It is not a
false-positive rate for other routes.
