# Atlas continuous code network — EFF-330

## Purpose and baseline

The user rejected the file-tree launcher and isolated route views. Opening Atlas
must immediately show a rich code network from the existing real scan. Groups and
calls open within that network with smooth motion and preserved spatial context;
no route list or replacement scene is required. This supersedes the prior
source-tree/directory/focused-route product decisions.

Base `7cee57b153e577e748e7f09c219b8a845da50f27`, feature branch `codex/atlas-frontend`,
worktree `/Users/galyossipov/code/code-atlas-atlas-frontend`. EFF-330 reopened.
Keep raw Aegra graph, schema, scanner and provenance unchanged. No new scan, raw CPG
integration, findings, backend workflow, cloud deployment, push or PR merge needed.

## Data and design decision

Use a canonical symbol network as the overview and retained route/call occurrences
for detailed evidence. A controller's independent traversal finds 213 indexed
symbols in 43 source files, 59 distinct handler symbols, and 244 unique directed
resolved symbol-call pairs (141 crossing source files), backed by 1,222 resolved
call occurrences including auth trees. The full scan has 5,586 call occurrences.
Do not present occurrences as unique functions or static evidence as execution.

Selected approach: one persistent scene, compact code-node glyphs, restrained
source/module group regions, real directed call links, selective readable labels
and direct in-place expansion. Retain the dark Atlas identity. A static/deterministic
layout computes world anchors once per dataset; it must not jitter or restart on
selection/expansion. Layout libraries may be used if warranted. A wide card tree,
a file gallery, a route picker as the primary journey, and a screenshot-only mock
are rejected because they reproduce the user's complaint.

## Contract

- R1 — Rich opening: display the 213 real indexed symbols (including all 59 handler
  definitions) and the 244 recorded resolved call pairs from the existing JSON on
  the initial network. Other auth/data connections may appear distinctly with
  evidence. At 1440x900 the opening viewport must visibly contain at least 120 code
  glyphs and many cross-group call links; counts alone or offscreen nodes do not
  satisfy this. Labels for selected/hovered nodes and meaningful landmarks remain
  readable. Whole-scan scope, partial coverage and current visible/detail counts
  remain truthful. Group regions must not dominate the graph like cards.
- R2 — Honest projection: canonical nodes use symbol IDs, never names as identity.
  Every aggregated call edge retains all original evidence references shaped as
  `{routeId, callId, authStepId?}`. Derive caller/callee from immediate recorded
  parentage and resolved symbol IDs; do not connect across unresolved intermediate
  calls or guess relations from common names/files. Group membership, auth context,
  data relationships and calls are visually/semantically distinct. Unresolved and
  external calls appear honestly when detail is opened. Summary aggregation must
  not lose route-specific occurrences or fabricate deeper paths.
- R3 — Direct exploration: groups collapse/reopen in place, multiple groups can
  stay open, and opening a handler/call reveals its recorded children in the same
  canvas. Support create_run -> _prepare_run and a second branch/group concurrently.
  Selecting a node highlights its actual neighbors while the rest remains visible.
  Shared functions remain connected across source areas. Full names and exact source
  are available on selection/hover. Optional search highlights/navigates the same
  scene; no modal/list is required to reach any handler. Group opening is not a
  link to another screen. Remove the old route-directory navigation path.
- R4 — Spatial continuity: selection, group/call expansion and collapse preserve
  the camera and all surviving node anchors (<=1 CSS px movement). Newly revealed
  nodes emerge from their group/parent and return there on collapse in roughly
  450–650ms, with edges following endpoints. Group boundaries may adjust without
  relocating unrelated code. Back restores exact camera, selection, open groups
  and expanded occurrences. Explicit user pan/zoom/focus/Fit may move the camera;
  no automatic fit or graph replacement on expansion. Rapid actions retarget
  animations; reduced motion settles immediately. No stale invisible selection.
- R5 — Usable graph: compact glyphs, meaningful visual hierarchy and selective
  label reveal prevent a wall of overlapping text. Settled interactive glyphs do
  not overlap. Pan, pointer-centered wheel zoom and keyboard camera controls work;
  source details are closeable without graph movement. The 390px layout has no
  chrome overflow, readable controls and direct graph interaction. Preserve source
  fidelity and truthful scan limits. Keep the canvas nearly full-window with few
  controls; do not add dashboard widgets or continuous decorative motion.
- R6 — Delivery: repeatable npm checks/build, running local preview at 4173 and dev
  at 5173, updated current README/verification, independent full-range code review
  and separate actual-browser verification. Preserve raw artifact SHA-256
  `c480d2ea15034d86d163101054d0714230ef9f5e79b94918b535431ad072737e`.

## Acceptance and readiness

`npm run typecheck`, `npm test`, `npm run build` must pass. Tests independently
derive the expected node/pair/evidence sets from the immutable raw graph (not from
the new projection), discriminate same-name symbols, preserve distinct occurrence
IDs and reject unresolved-target inference. Check group/call visibility/history and
deterministic anchor stability. Obsolete focused-route tests should be replaced
with the new behavioral contract; retain useful provenance/source regressions.

On the actual production build: capture initial 1440x900 graph and count on-screen
code glyphs/real edges. Visually verify a network, not a tree/gallery. Select
create_run directly (search may highlight it); open its calls and _prepare_run,
then another region/branch without replacing the canvas. Measure camera and surviving
anchors throughout, sample intermediate animation poses and edge endpoints, collapse
and Back. Compare at least two actual call-site/source examples to JSON, including
an unresolved leaf and shared function. Check group collapse/reopen, impossible
search/no-match reset if search exists, wheel zoom, rapid toggles, reduced motion,
390px and runtime errors. Raw/served artifact hashes must match. Existing baseline
fails opening density, real cross-file edges and continuous in-place exploration.

Ready to dispatch: user behavior is explicit, source/interface and browser tools
exist; no new producer dependency. Scope is the exported route-oriented code network,
not exhaustive repository or security coverage. Visual acceptance is required in
addition to numerical/unit checks; do not mark done merely because tests pass.

## Execution plan and ownership

One implementer owns the frontend projection/layout/navigation/rendering, affected
tests and current README. Keep data/projection, scene state/layout and presentation
separate. Implement the core network first and share a runnable visual milestone
early; complete expansion/evidence and checks against the same architecture.
Controller owns this spec, ledger and final verification document. Freeze candidate,
then independent reviewer and separate browser verifier check R1–R6. Batch fixes
through the author and recheck affected behavior. No product edits during gates.
