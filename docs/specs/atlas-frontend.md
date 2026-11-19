# Atlas frontend — EFF-330

## Outcome and delivery

Turn the approved Atlas interaction into a runnable CodeAtlas frontend in this
repository. Deliver a reviewed local app, normal browser URL, reproducible npm
commands, and static production build. No deployment or merge is authorized.

Baseline f8ceb12808b90f0145c00bde93e33e5ba47161f8 contains documentation and two
schema v1.0.0 fixtures, with no frontend or build commands. The user approved Atlas
and local progressive exploration, then explicitly requested a real frontend
instead of an inline conversation mockup.

## Implementation boundary

Use React, TypeScript and Vite at the repository root. A client-only static app fits
the current fixture-backed workspace; a server/SSR framework has no current user
need. Keep the graph adapter, deterministic layout, navigation state, animation and
React presentation in separate small modules. Use the existing JSON documents
directly; do not copy them into hand-maintained node arrays. The schema stays owned
by the analysis core and must not change for this UI.

Reference design:
`/Users/galyossipov/.codex/visualizations/2026/11/16/01a1e411-2e71-78d1-8134-79453cd5b464/atlas-focus.html`.
This is a visual/interaction reference, not application architecture to wrap in
an iframe. Do not retain Codex host APIs, widget state, Tweak, or CDN runtime glue.

## Behavioral contract

- R1: Opening the app immediately shows the Atlas graph, occupying most of the
  window, with restrained navigation and no permanent panels or metrics wall.
  Aegra is the default; both existing fixtures are selectable. Dataset switching
  resets dataset-specific exploration safely. The full app can be opened outside
  Codex and does not require an external service or account.
- R2: Read all visible relationships from the chosen fixture. Separate route/data
  summaries, auth context and actual calls. Preserve route/call occurrence identity,
  source ranges, external/ambiguous resolution and partial expansion. Do not infer
  execution order from layout. Aggregate shared symbols only in a summary view;
  do not merge distinct route-specific call occurrences.
- R3: A click selects. An explicit expansion reveals only the selected node's
  direct recorded calls. Reveal children from the parent's position with a smooth
  approximately 600 ms transition; existing node world positions and the camera
  remain unchanged. Edges follow their animated endpoints. Explore one deep branch
  at a time, retaining ancestors and dimmed surroundings. Unresolved or unexpanded
  leaves cannot invent a continuation. Shared auth internals may stay collapsed
  in this first handler-call explorer and must be labeled accurately.
- R4: Drag to pan, zoom with accessible controls, explicitly bring selection into
  view, collapse and use breadcrumbs/Back. Zoom does not change graph detail.
  Back restores the exact prior selection, pan, zoom and expanded path. Never
  auto-fit/re-layout on expansion. Rapid navigation cancels/retargets animation
  cleanly; exiting nodes cannot become a hidden active selection.
- R5: Source details open on demand in one closeable panel, without moving the
  graph. Show actual names, files/lines and available snippets, inline checks and
  resolution/coverage; render source as text. Do not fabricate source or findings.
  Distinguish the hand-authored fixtures, partial coverage and the fact that two
  route slices do not represent the whole repository.
- R6: Readable dark Atlas treatment, responsive desktop/narrow layout, keyboard
  operable controls with clear names/focus, accessible source panel, reduced-motion
  support. Keep full labels accessible when abbreviated. Small screens may pan the
  graph but application chrome must not overflow horizontally. Use local bundled
  assets/fonts or resilient fallbacks; the production app must not need CDN scripts.
- R7: `npm ci`, `npm run dev`, `npm run typecheck`, `npm test`, and `npm run build`
  are documented and functional. Build emits `dist/index.html` and referenced assets;
  `npm run preview -- --host 127.0.0.1` serves the same app. Dist is generated, ignored
  output, not a committed duplicate source. Root README explains starting, building,
  data boundaries, and the future scanner integration point.

No scan submission/backend, auth, cloud hosting, new scans, real findings or whole
repository/AST claims are in this slice. Example scope is explicit in product copy;
implementation details do not occupy the user workflow.

## Acceptance and discrimination

All checks use the exact checked-out candidate and bundled fixtures. Record build
identity, commands and browser observations in `docs/ATLAS_FRONTEND_VERIFICATION.md`.

1. `npm ci && npm run typecheck && npm test && npm run build` exits successfully;
   serve the generated build. Baseline has no scripts, so cannot pass this check.
2. On Aegra first load, graph nodes/relationships visibly match the fixture. On
   papertrail, labels/counts/source change to that fixture. No stale Aegra detail.
3. Pan and zoom, record camera and create_run anchor relative to canvas. Expand
   create_run (3 direct calls), then _prepare_run (4 direct calls). Existing anchors
   must not move more than 1 CSS px and camera must remain equal. Pan/zoom again;
   Back must restore the snapshot from before entering the deeper branch. This
   rejects fit-on-expand, replacement-layout and shallow-history implementations.
4. Open the two handle_event occurrences under _apply_create_run_auth; each points
   to its own recorded ambiguous child. Selecting the ambiguous child has source
   evidence and no enabled expansion. Source/check excerpts match the fixture. This
   rejects shared-symbol call merging and invented continuations.
5. Exercise branch switches/collapse during animation, source close/Escape, keyboard
   actions, reduced motion and a 390px viewport. Chrome fits; graph remains usable;
   no stale scene/selection or uncaught runtime errors. Verify production assets,
   not just a successful HTTP status or screenshot.

Focused automated tests should cover distinct graph/navigation failure modes using
real fixture inputs. Avoid tests that simply duplicate rendering formulas. Actual
UI behavior requires separate browser verification.

## Readiness

Ready to dispatch: outcome, commands, fixtures, browser environment, producer and
references are available. The approved interaction supplies the product decisions.
Local fixture results do not establish scalability or scanner integration; those
remain future work rather than implied acceptance.

## Execution plan

1. One scoped implementer owns app/build/config/README and meaningful focused tests.
   It may install registry dependencies and run a loopback dev/preview server.
2. Freeze candidate. Independent reviewer checks the complete diff against R1–R7.
3. Separate behavior verifier exercises the running production build, including
   desktop, 390px and reduced-motion behavior. Read-only review and browser work may
   run together; no product edits during either.
4. Batch required fixes through the implementer, review the fix range, rerun affected
   checks. Finish with a local handoff, verification record and Linear update.

Controller owns this spec, ledger and delivery record. Workers cannot merge, deploy,
message others, mutate Linear or touch unrelated repositories.
