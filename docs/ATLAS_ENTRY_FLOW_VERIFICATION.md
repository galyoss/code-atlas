# Entry-to-data tracing and animated layouts

Task: EFF-330. Local frontend scope; no staging or production deployment.
Full task base: `9b1f986aa6cd4788b18c8f05daa239e609caf2bd`.
Initial candidate: `b6533e87cc6e99f919432bb156e8643b6fbc37f3`.
Accepted candidate: `6ad480a21e9074e27b423fee09c12e3039499bd7`.
**Local pre-merge: PASS.** Independent cumulative code review is COMPLIANT /
APPROVED; separate actual-browser acceptance passed after one correction round.

## Behavior

Selecting an entry point highlights its recorded paths to named data accesses and
explicit persistence-effect frontiers, including intermediate calls. Unrelated
code remains visible but muted. Inspecting an intermediate node or its Source
retains the active entry flow. The paths are static scan evidence, not a runtime
execution trace or a claim of complete scan coverage.

Code, Entry points and Data flow use separate cached layouts. View changes move
the same node identities over a 740 ms eased transition; edges follow those poses.
Data flow places handlers on the left, intermediate calls in the middle and data
operation occurrences on the right. Camera, manual exploration and Back context
are retained; reduced motion settles immediately.

The initial Data flow overview contains all 213 canonical symbols plus 182 detail
records on paths to the 108 named accesses. Selecting an entry adds its other
recorded persistence frontiers. This avoids expanding every call in the scan.

## Evidence and limits

- All 59 route path/terminal/edge sets independently match the raw scan oracle.
  `create_run` has 43 path nodes including the entry and 34 terminals, eight with
  named objects. `get_thread` has nine path nodes and six terminals. Health has
  one explicit-effect terminal; POST /assistants has no recorded data terminal.
- Independent geometry checks cover all 59 selected routes: ordered semantic
  bands and at least 34 world units between visible nongroup anchors.
- Typecheck, 28 tests and build passed on the initial candidate. The browser
  loaded `index-DpASlrxV.js` and `index-5ZbSbZmg.css` from the production preview.
- Final candidate: typecheck, all 29 tests, build and whitespace checks pass.
  Browser recheck loaded `index-Cu7BLoTv.js` with the same CSS asset.
- Actual desktop at 1440×900 and mobile at 390×844 pass. Expected highlighted
  path/terminal/edge identities match the independent raw oracle. Source
  inspection, entry switching, manual branch retention, no-evidence entry,
  Files/Symbols, camera, Back, search and reduced motion were exercised.
- Settled rectangle audits found no label/glyph/caption/control overlaps; all
  terminals in the selected desktop example remain above its detail bar.
  Mobile has no horizontal page overflow; its controls and Source fit.
- Complete morphs retain existing DOM nodes and intermediate poses; edges follow
  their current positions. A continuous 131-frame sampler spans two interrupted
  transitions, retaining 255 elements and 43 distinct actual CSS poses. CSS/pose
  error stays below 0.00069 world units; edge error below 6.1e-14. Camera stays
  fixed and Code anchors restore within 1.2e-13. Sampling affects frame cadence;
  this establishes motion/continuity rather than a performance benchmark.
- No captured console warnings/errors. Temporary viewport/media settings were
  reset after verification.
- Raw scan SHA-256 remains
  `c480d2ea15034d86d163101054d0714230ef9f5e79b94918b535431ad072737e`.
  Scanner, schema, source scan and provenance are unchanged.
- Source-file controls fade in semantic layouts. An expanded file can retain its
  selection bar; Locate centers its saved group coordinate without a visible
  file marker. Collapse remains available. Reviewed as nonblocking.

## Initial gate and correction

Independent full-range review and browser reproduction found one blocking issue:
the selection-bar **Clear flow** action also removed overlapping saved manual
expansion and owner paths. The separate top clear action correctly preserved
them. The correction couples each primary action's label with its semantic
transition; both clear controls now use the existing flow-only action. Independent
fix review found no new defects. The bounded browser recheck confirms both
controls preserve all ten same-entry manual detail IDs and all three saved owner
path IDs. Back restores the same 430 node identities, selected entry, 43 path
nodes, 34 terminals and camera. The initial failure is resolved.

Detailed local artifacts: `.work/atlas-flow/implementation-report.md`,
`code-review.md`, `fix-review.md`, `behavior-verification.md`, `flow-oracle.json`
and `screenshots/`. Final screenshots are `12-fixed-desktop-overview.png` and
`13-fixed-desktop-selected.png`; mobile screenshots 09–11 cover unchanged layout.
Specification and execution history are in
`docs/specs/atlas-entry-flow-layouts.md` and its adjacent ledger.
