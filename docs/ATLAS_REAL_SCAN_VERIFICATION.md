# Atlas real Aegra scan verification

Task: EFF-330 real-data follow-up. Delivery target: local running Atlas, no deployment.
Frontend baseline: `730f8ec0c03e8a07b6c0a832c69e90e0c513ca22`.

## Producer evidence — PASS

The unmodified scanner at `0d3fec1748d8c7e2321c130a3251bba041322515` ran Joern
4.0.684 with Temurin Java 21.0.13+9 on public Aegra v0.11.0,
`46055c0b9adffe51fb168974f79dfadaa6edd612`. Source checkout was clean. Both
CPG and overlay cache files were absent before the invocation; neither a prepared
overlay nor a sample graph was supplied. CLI exited 0 after 10.681 seconds.

Output generation time: `2026-11-16T14:21:20Z`.
Graph SHA-256: `c480d2ea15034d86d163101054d0714230ef9f5e79b94918b535431ad072737e`.
Size: 5,616,397 bytes. `illustrative` is false. The application asset is byte-for-byte
identical to that producer output. Source excerpts retain the Apache-2.0 license.

| Population | Count |
| --- | ---: |
| Python files parsed | 164 |
| Exported HTTP routes | 59 |
| Referenced symbols | 213 |
| Handler call occurrences | 3,650 |
| Authentication call occurrences | 1,936 |
| Data accesses | 108 |

An independent AST inventory of the pinned API/core source found 56 HTTP decorators;
all 56 handlers occur in the exported graph. The remaining three routes are from
`examples/custom_routes_example.py`, not a claim about deployed application routes.
The scan records 55 routes with partial coverage and four complete within the
exporter's scope. Ambiguous dispatch, depth limits and external calls remain visible
limitations. No vulnerability-review agents ran and no findings were generated.

`scanner.validate.validate_document` returned zero schema/invariant errors.
The existing Aegra integration test passed. Full Python suite: **18 passed, 0 skipped**,
with one upstream Starlette deprecation warning. Original schema and examples are
unchanged. Full local producer logs, raw CPG/overlay, checksum proofs and independent
inventory are retained in ignored `.work/atlas-real-scan/`; reproducible invocation
and tool locations are documented with the bundled scan.

## Frontend delivery gates

Final code candidate: `9d6e9c4c65b8a9cf02a966717fb81f562e98779f` on
`codex/atlas-frontend`. Local pre-merge result: **PASS**. Independent code/fix review:
**COMPLIANT / APPROVED**. No blocking findings remain. Original review and browser
run found one narrow-screen caption collision; a three-line CSS correction passed
bounded independent review and the affected browser recheck.

- `npm run typecheck`, `npm test` (**17 tests**) and `npm run build`: pass. Existing
  Python suite remains **18 passed, 0 skipped**. No scanner semantics changed.
- A dedicated Chrome browser loaded the production build on port 4173. Served
  HTML, JavaScript, CSS and graph bytes match `dist` exactly; the graph retains the
  producer hash above. The final CSS SHA-256 is
  `e01c596f37948c8cab6ee4a74efe56d1b058631fac2ba13047980498d8591c8c`.
- The actual browser directory contains the complete 59-route set from raw JSON.
  Initial overview is a connected repository/source graph with nine file groups;
  structural edges are explicitly distinguished from calls. Source-example routes,
  scan revision, coverage, unresolved gaps and absent agent review are identified.
- create_run (6 direct calls), get_thread (9), create_assistant (1), GET thread state
  (19), and POST thread state (35) were exercised. Source and occurrence IDs match
  the raw document. Search matching, no-match and reset paths work.
- Dense nested expansion shows 58 active nodes with no settled node intersections.
  All 39 prior anchors moved **0 CSS px**. Back restores exact scope, selection,
  expanded path and camera across expansion, pan/zoom, route changes and overview.
- Reduced motion, rapid navigation, source close/Escape and narrow source viewing
  pass. Fresh 390x844, overview pan/Fit, desktop overview and route views pass after
  the caption correction. No page horizontal overflow or browser warning/error
  logs were observed in the tested paths.

Evidence is retained in `.work/atlas-real-scan/implementation-report.md`,
`code-review.md`, `fix-report.md`, `fix-review.md`, `behavior-verification.md`,
`browser-evidence.json`, and the screenshot directory. Prior unchanged interaction
evidence was reused for the CSS-only correction; affected rendering was retested.

The app serves a saved real scan, not a live scan-submission service. Authentication
call trees remain collapsed context in the handler explorer. This delivery does
not prove exhaustive static coverage, runtime endpoint behavior or security findings.
No cloud deployment, PR merge or push was performed.
