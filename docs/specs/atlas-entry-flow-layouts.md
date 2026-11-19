# Entry-to-data tracing and animated views — EFF-330

Baseline `9b1f986aa6cd4788b18c8f05daa239e609caf2bd`, feature worktree
`/Users/galyossipov/code/code-atlas-atlas-frontend`, branch `codex/atlas-frontend`.
The user now wants one-click entry-to-data tracing and actual animated layouts per
view, especially entries left / data operations right. This explicitly supersedes
the prior rule that view changes keep node positions fixed. Stable identity,
context, source truth and exact Back remain required. Local frontend only.

## Contract

- F1 — Selecting an entry handler (direct click or search selection) automatically
  reveals and emphasizes every recorded branch from its route contexts to data
  reads/writes. No second Reveal click. Include intermediate call occurrences and
  matching code definitions as context; dim unrelated nodes/edges while retaining
  the surrounding graph. Edge emphasis uses exact route-qualified path evidence,
  not arbitrary transitive walks through the aggregated canonical graph. Multiple
  routes on one handler are unioned without conflating occurrence identities.
- F2 — Trace terminals are named dataAccess calls plus explicit persistence-effect
  frontiers: read/write/read_write calls with no deeper recorded terminal. Named
  accesses remain terminals even if they have children. Preserve operation/object,
  call site, ambiguity/external resolution and auth context (dashed, not a call).
  A propagated wrapper effect is not a substitute for deeper known accesses.
  Unknown effects never imply a data path. If none are recorded, show a concise
  empty-evidence message, not a fabricated path or claim that the endpoint has no
  persistence. Partial scan remains explicit. No new edges or inferred callees.
- F3 — Automatic entry-flow visibility is separate from manually opened branches
  and existing owner access reveals. Switching entries replaces only the automatic
  layer; unrelated manual work survives. Inspecting an intermediate/terminal node
  and Source retains the active entry-flow context. A clear flow/selection action
  returns to the surrounding graph; Back restores flow, selection, view, camera,
  expansion and resolution. Depth/collapse has a coherent explicit interaction
  with auto flow (never claim collapsed/zero depth while auto children still show).
- F4 — Views visibly move existing nodes in the same canvas: Code restores the
  established source-file map; Entry points uses an entry-oriented composition;
  rename Data access to Data flow and use a left-to-right flow composition.
  In Data flow, handlers occupy a left band, actual data-operation occurrences a
  right band, intermediates between. A handler with its own data access stays at
  the entrance; its distinct recorded access occurrence appears at the data end.
  This avoids falsely treating the same definition as two canonical identities.
- F5 — Data flow works before selecting an entry: expose the 108 named access
  occurrences and their minimal actual ancestor paths (182 details), alongside
  all 213 canonical symbols. This produces a connected overview with real data
  operations on the right. Entry selection adds its other explicit-effect terminal
  paths as needed and emphasizes only that flow. Do not globally open all 5,586
  calls or all 497 effect terminals. Keep these mode-derived nodes separate from
  manual/selected-flow visibility; returning to Code removes only mode-derived detail.
- F6 — Deterministic per-view anchors and compact packing keep visible glyphs
  non-overlapping. Within a view, ordinary selection/expansion preserves surviving
  anchors; only explicit view changes intentionally rearrange them. Preserve the
  camera during the rearrangement and fit the standard layouts within comparable
  world extents so default desktop framing remains useful. Keep pan/zoom and an
  explicit Fit; avoid automatic camera jumps. Return to Code/Back restores its
  exact previous anchors. Files/Symbols resolution remains useful in each view;
  source-file regions/labels may fade in semantic layouts instead of misleadingly
  enclosing nodes belonging to different roles. Role captions clarify the layout.
- F7 — A coordinated roughly 600–850ms eased morph moves the same node identities,
  with edges following their interpolated endpoints and labels staying attached
  or gracefully fading during motion. Existing nodes must visibly traverse between
  layouts, not disappear/reappear at destinations. Retarget rapidly interrupted
  transitions from the current pose without snapping or stale timers. Respect
  reduced motion immediately. Selected entry and read/write markers remain legible.
- F8 — Maintain the restrained Atlas rail, exact source evidence, literal search,
  unresolved states, targeted owner access action and mobile controls. At 1440×900
  the Data flow composition must visibly communicate left-entry / middle-call /
  right-data roles without hiding all data offscreen or reducing glyphs to dots.
  At 390px pan/zoom makes the same layout usable with no chrome overflow. Settled
  labels must not cover glyphs or controls; preserve the recent collision fix.

## Data, acceptance and readiness

Raw graph/schema/scanner unchanged. SHA-256 remains
`c480d2ea15034d86d163101054d0714230ef9f5e79b94918b535431ad072737e`.
Controller independently derived `.work/atlas-flow/flow-oracle.json`: 59 routes,
35 with recorded terminal evidence, 497 terminals globally; named-access overview
has 182 detail IDs. POST /threads/{thread_id}/runs has 42 detail path nodes and 34
terminals (8 named accesses); GET /threads/{thread_id} has 8/6; GET /health has 1/1
explicit Read effect with no named object; POST /assistants has no recorded terminal.
Counts describe static records and include auth trees, not execution frequency.

Run npm typecheck/test/build. Derive expected route path/edge/terminal sets from
raw data independently; include route-context isolation, same-name/shared functions,
multi-route handlers, unknown/no-data, auth-context distinction and manual-state
preservation. Discriminate old neighbor-only highlighting and color-only view modes.
Geometry checks require entry.x < intermediate.x < terminal.x for actual traced
nonterminal intermediates in Data flow, plus no settled glyph overlaps; code-map
roundtrip, interruption and Back identities must hold. No new backend producer.

Actual production browser: one-click create_run and get_thread traces, exact path
sets/edges, source inspection without losing focus, switching/clearing/no-evidence
entry, manually open branch retained; Code→Entry points→Data flow→Code with real
intermediate motion and edge tracking, useful default left-to-right composition,
rapid toggles, exact Back/camera, reduced motion, Files/Symbols, 390px and runtime
errors. Capture final overview and selected flow screenshots. The prior build fails
F1 and F4; passing static/unit counts alone is insufficient.

Ready: explicit user outcome, inspected interfaces, immutable producer and browser
available, positive/negative fixtures and executable checks defined. No approval
needed for this authorized local change. Product judgment: global Data flow opens
named data paths only; route selection exposes additional effect frontiers. This
keeps a useful overview without inflating it with all repeated call occurrences.

## Ownership and sequence

One fresh implementer owns frontend projection/state/layout/animation/presentation,
tests and README as one integrated task. Reuse existing motion and node identities;
separate semantic path derivation from layout and navigation. Share an early runnable
flow/layout milestone before final polish. Controller owns this spec, ledger and
final verification docs. Freeze, independent full-range code review, separate
actual-browser verification, then bounded fixes/rechecks. No push, merge or deployment.
