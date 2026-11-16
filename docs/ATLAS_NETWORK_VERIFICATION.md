# Atlas continuous network verification

Task: EFF-330, continuous graph product correction. Target: local running app.
Baseline: `7cee57b153e577e748e7f09c219b8a845da50f27`.
Implementation: `d83381a15d4c73eda37b4c3906fc1ca523c87b05`.
Final caption correction: `2fe8f0e919df07d53dfc06b22a0093b8b812bab4`.
Branch: `codex/atlas-frontend`.

The [continuous network contract](specs/atlas-continuous-network.md) replaces the
previous file-tree, route-directory and isolated-route experience. Earlier scan
verification remains producer evidence; its frontend navigation describes history.

## Data and implementation

The same real Aegra v0.11.0 scan supplies 213 canonical symbols in 43 source files,
including all 59 handler definitions. Its 244 directed resolved call pairs include
141 cross-file pairs and retain 1,222 original route/call/auth-step references.
All 5,586 detailed call occurrences and 108 data accesses remain available in the
data model. Canonical links use immediate resolved parentage; they never infer a
target from its name or bridge an unresolved intermediate call.

Raw SHA-256 remains
`c480d2ea15034d86d163101054d0714230ef9f5e79b94918b535431ad072737e`.
The scanner, schema, examples and provenance were not changed or rerun for this
frontend correction. [Scan provenance](scans/README.md) documents the original run.

File groups and occurrence branches open on one persistent canvas. Canonical
anchors are deterministic; detail anchors are reserved for the session as branches
are explored. Selection, expansion and collapse preserve the camera. Explicit
pan/zoom/focus/Fit can move it. Source panels show original source and supporting
relationship evidence; partial coverage remains visible.

## Delivery gates

Independent full-range code review: **APPROVED**, all code-assessable requirements
satisfied. Separate local pre-merge browser verification: **PASS** for R1–R6 on
the implementation revision. Both found one minor ambiguity in the caption's
visible-symbol versus total-link counts. The two-line correction received bounded
independent **COMPLIANT / APPROVED** review and an actual desktop/mobile caption
recheck: **PASS** on the final revision. No required gate or finding remains open.

- `npm run typecheck`, `npm test` (**14 tests**), `npm run build` and diff checks
  passed. Typecheck/build repeated after the copy-only fix; unaffected test and
  functional browser evidence reused. Final JS is `index-Byu_5bDz.js`; CSS remains
  `index-Bx0M_08u.css`.
- Chrome at 1440×900 shows all **213** canonical glyphs and **244** real call pairs,
  with no glyph intersections. Both reviewer and verifier independently compared
  exact symbol/pair/reference sets against the raw scan.
- create_run, its _prepare_run occurrence and get_thread remain open together:
  **273 nodes**, comprising 213 symbols plus 60 detail nodes. Group collapse and
  reopening retain the other branches. No replacement screen or directory appears.
- Existing anchors moved **0 CSS px** during measured expansions and group collapse;
  camera remained unchanged. Back restored exact camera, selection, groups and
  expanded occurrences. Sampled animation lasted about 600 ms; 14,040 edge samples
  followed their moving endpoints within floating-point precision. Rapid retargeting
  settled correctly; reduced motion produced zero moving frames.
- Source checks matched the exact _prepare_run invocation at runs.py:131 and the
  ambiguous where call at runs.py:125. Shared canonical evidence preserved distinct
  route-specific occurrences. Unresolved leaves did not offer invented expansion.
- At 88% zoom, 17 newly revealed _prepare_run child labels were readable. Selection,
  source close, pointer-centered wheel zoom, keyboard pan/zoom, search match/no-match
  and reset all passed. At 390×844, viewport and document widths remained 390px;
  direct selection, expansion, source inspection and dragging worked.
- Browser-served raw bytes retained the producer hash. No runtime warnings, errors
  or captured exceptions appeared in the tested flows.
- Final caption recheck exercised collapse/reopening at both widths: 213/213 →
  200/213 → 213/213 symbols shown, with 244 explicitly total call links. The longer
  caption fits within 248px on the 390px screen without horizontal overflow.

Local production preview: <http://127.0.0.1:4173/>.
Development server: <http://127.0.0.1:5173/>.
Reports, measurements and actual-browser screenshots are retained in the ignored
`.work/atlas-network/` directory.

## Limits

This is the exported route-oriented static network, not exhaustive repository or
runtime coverage. Fifty-five route slices remain partial and four complete within
the exporter's scope; example-source routes remain included. No security-review
agents or vulnerability findings were added. Very deep exploration can extend
beyond the viewport, with movement left to explicit user controls. A fresh phone
view centers a real handler at usable scale rather than fitting every glyph.

Delivery is local only. No push, PR merge or cloud deployment was performed.
