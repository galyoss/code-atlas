# Semantic regions and recorded-flow focus

Local pre-merge: **PASS**, 2026-11-17. Contract: `docs/specs/atlas-3d-semantic-focus.md`.
Baseline `f2a10966fa4807c6182f02877b2df3d877178f9e`, branch `codex/atlas-integrated`.

## Behavior

The cinematic graph shares one evidence-based color taxonomy across its nodes,
spatial regions, legend and selection details. Data flow separates endpoints,
core logic, reads, writes, external/library calls and unresolved targets. Region
labels follow the camera; empty categories are omitted. Other layouts retain
their arrangements and use the same role colors.

Selecting an endpoint highlights its recorded paths to data terminals. If none
exist, it shows the recorded request tree and says no data terminal was recorded.
A call or auth context highlights its exact ancestors and descendant branch.
A shared canonical symbol unions its recorded call contexts; unused symbols are
explicitly untraced. Aggregate symbol relationships never manufacture execution
paths. Definition links remain distinguishable from directional execution edges.

Unrelated geometry and ambient effects dim while focused paths and static arrows
remain visible, including while paused. Focus can temporarily reveal evidence
outside the current detail, search or file filters. Clearing focus restores those
filters without moving the camera. Explicitly filtering out the selected node
clears the focus; selecting another temporarily revealed node remains valid.

## Data scope

The unchanged Aegra fixture has 5,920 nodes, 7,294 relationships, 59 handlers and
497 terminal occurrences (254 reads, 243 writes). Its 108 named accesses are ORM;
none provides explicit RPC evidence. External targets include libraries and
frameworks, so they are not labeled as network services. Alternate-input RPC and
combined read/write roles are covered by fixtures.

Source scan SHA256:
`c480d2ea15034d86d163101054d0714230ef9f5e79b94918b535431ad072737e`.
This is a partial static scan; electric motion illustrates relationships and is
not measured runtime activity. No scan, schema, backend or deployment change.

## Evidence location

Ignored `.work/atlas-semantic/` contains independently derived raw focus oracles,
`implementation-report.md`, `code-review.md`, `behavior-verification.md`,
`behavior-browser-evidence.json` and screenshots `verify-data-regions.jpg`,
`verify-focus-create-run.jpg` and `verify-mobile-focus.jpg`.

## Frozen candidate

- Ten-source-file fingerprint: `bc095f611173f1cf390721f1d6e6868bcdd581b46f4f615241e732f8a108de1b`.
- Production assets: `index-DyHGFkSR.js`, `CinematicGraph-BTvCepTk.js`,
  `CinematicGraph-qnZAE6se.css`.
- Typecheck, production build, diff check and 54 tests across 11 files pass.
- Independent raw-document traversal matches exact path, definition, edge and
  terminal sets for all 5,920 selectable nodes, including shared canonical contexts.
- Independent whole-change code review: **COMPLIANT / APPROVED**, no actionable
  or deferred findings. The review verified every frozen source hash.
- Separate actual Chrome verification: **PASS**, no blocking product findings
  or console warnings/errors.

## Browser acceptance

Actual node clicks matched representative raw-data paths: create_run 43 path
nodes / 34 terminals; health 2 / 1; create_assistant 27-node request tree / no
terminal; unused AssistantUpdate selected-only / no recorded trace. Shared
_prepare_run unions 10 recorded contexts across 9 routes, with 166 terminals.

Symbols + create_run search restores exactly 3 nodes / 2 edges after clearing
focus. Clicking a temporarily revealed _prepare_run occurrence retains those
filters and shows its exact 132-node branch / 26 terminals. Explicit search/file
exclusion clears focus; previously hidden nodes cannot be picked.

The same canvas, camera and selection survive interrupted layout morphs. Paused
time remains fixed while user-requested transitions progress; 42 direction cues
remain visible for create_run. Orbit moves region labels. Empty-canvas clear
restores normal brightness without resetting the camera.

Desktop 1440×900 and 1512×771 and mobile 390×844 pass. Mobile touch selection,
scrollable details, rail and dock fit, and reduced-motion immediate layouts pass.
Existing 2D create_run selection, full dataset, search, flow and Source text are
identical after a 3D roundtrip. Viewport/media overrides were restored.

Detached local preview remains at
<http://127.0.0.1:4173/?sample=aegra&view=cinematic>, with the deliverable browser
tab showing Data flow, all nodes and ordinary animation. Temporary dev server
4174 was stopped. This verification covers local Chrome/WebGL, not a deployment,
physical mobile device, cross-browser matrix or extended performance soak.
