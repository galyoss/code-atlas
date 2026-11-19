# Atlas controls and data semantics verification

Task: EFF-330 left-rail and entry/data clarity follow-up. Local frontend delivery.
Baseline: `0cee3a204a9eade6ad74de14ead083bba2118fbb`.
Implementation: `92d06112015bcf97ffffe85a865557d1d87e3b31`.
Final label/copy correction: `2753efc30fc79c0cc96722ac387e49b8c6f73601`.
Contract: [Atlas controls and data](specs/atlas-controls-and-data.md), C1–C6.

## Delivered interface

A collapsible left rail controls Code / Entry points / Data access emphasis,
Files / Symbols resolution and selected-branch call depth 0–3. It includes a
visual key explaining source-file groups, recorded-call arrows, entry markers and
R/W/RW data effects. The general key says Code symbol because the index includes
functions and classes. Views emphasize the same graph without replacing it.

Entry points expose HTTP methods and paths. Function badges summarize named object
access records in the function body. Detailed calls distinguish those records from
explicit persistence effects such as transaction control. Unknown effects and
ambiguous callees retain their uncertainty. No effect is inferred from a name.

Reveal access paths adds only the actual access occurrences and their ancestors,
preserving other manual branches. For _prepare_run, this adds 31 detail nodes:
16 access occurrences and 15 ancestors, with operation/object labels such as
Read Assistant and Create Run. Source retains invocation, call-site range, target
resolution and route-specific evidence. No shortcut call edges are invented.

## Data evidence

Independent traversal of the unchanged raw document found 108 named access records:
72 reads (59 load, 13 query) and 36 writes (14 create, 20 update, 2 delete), in 31
route contexts and 32 immediate resolved owner functions. Ninety-four access calls
have ambiguous targets; their recorded object effects are still known. These are
route-scoped records, not runtime counts or 108 unique lines of code.

Positive/negative examples include get_thread (load), _prepare_run (eight load and
eight create records), and delete_thread (load/query, no named write recorded).
Schema, scanner, original fixtures, provenance and raw scan were not changed.
Raw SHA-256: `c480d2ea15034d86d163101054d0714230ef9f5e79b94918b535431ad072737e`.

## Delivery gates

Final local pre-merge result: **PASS** on `2753efc`. Independent full-range and
bounded fix code reviews: **APPROVED**, code-assessable clauses satisfied. Separate
browser acceptance: **PASS** for C1–C6 using the full initial run and affected
final-candidate recheck. The initial run found an active-label collision; it was
fixed and independently rechecked rather than treated as an evaluation limit.

- At 1440×900 the initial rail is readable and at least 211 canonical glyphs are
  fully visible outside it. Exact 59-entry and 32-data-owner sets match the oracle.
- Depth 0→1→2 on create_run preserves a manually opened get_thread branch; all 235
  surviving nodes stay at the same screen coordinates. View/rail changes preserve
  the camera and 213 anchors. Back restores exact state and camera.
- Targeted _prepare_run reveal is the exact 31-ID set, with zero extra siblings;
  another manual branch remains open. Partial paths report Mixed; depth 0 and
  manual collapse remove only their own descendants, with exact Back restoration.
- Actual Source matches load Assistant at run_preparation.py:291 (ambiguous target,
  known Read) and create Run at line 363 (external target, known Write). Original
  invocation, access snippet and route-qualified identities remain intact.
- At 390×844, rail open/scroll/close/view and source scroll/close work with no
  horizontal overflow. Reduced-motion Files/Symbols changes settle immediately.
  Search, zoom, keyboard pan, stale-focus clearing and partial-scan smoke passed.
- No captured console warnings/errors. Parent additionally hashed HTTP-served raw
  bytes and confirmed the unchanged producer hash above.
- Final actual-browser label recheck found zero settled glyph intersections in
  fresh desktop reveal, reveal with get_thread already open, and mobile search/
  reveal. The selected 97.203×28.5px label uses a readable leader and excludes
  controls/source overlays. Camera is unchanged; measured survivor movement is
  0px fresh/mobile and below 0.104px in the manual-branch case while prior entering
  motion settles, with identical world anchors. Both meet the 1px acceptance bound.
- Final Code symbol / Symbols copy fits desktop/mobile. Files/Symbols retains
  saved manual and targeted detail state. No required gate or finding remains open.

Author checks: `npm run typecheck`, `npm test` (22 tests across four files),
`npm run build` and diff checks passed. Tests independently derive access ownership
and reference sets and exercise ambiguous/unresolved-parent/read-only negatives,
explicit effects, multi-route entry text, local depth, targeted-path sets, mixed
states, resolution restoration and Back. Baseline failed the new positive checks.
Two additional label regressions failed before the correction and pass afterward;
they check the actual measured text-box footprint in both reproduced scenarios.

Final production assets: `index-CENPCJVe.js`, `index-mSlTqDcm.css`.
Preview: <http://127.0.0.1:4173/>. Dev: <http://127.0.0.1:5173/>.
Detailed reports, independent data oracle, browser measurements and screenshots
are retained under ignored `.work/atlas-controls/`.

## Boundaries

This remains the saved route-oriented Aegra static scan; partial coverage and
source-example routes remain explicit. A badge is evidence about recorded code,
not proof that a request executed or an exhaustive inventory of persistence.
No vulnerability agents/findings, new scan, backend change, push, merge or cloud
deployment were included.
