# Atlas controls and data semantics — EFF-330

Baseline `0cee3a204a9eade6ad74de14ead083bba2118fbb`, branch `codex/atlas-frontend`,
worktree `/Users/galyossipov/code/code-atlas-atlas-frontend`. Local frontend only.
The user accepts the continuous network and now wants a left rail controlling
resolution/view type, plus understandable entry and data read/write points.
Preserve the established continuous-graph contract; no scanner/schema/raw changes.

## Product contract

- C1 — A restrained, collapsible left rail contains graph view, resolution and a
  compact visual key. Use the existing Atlas typography/dark identity. Default
  desktop rail is open; at 390px it opens as a closeable overlay. Keep most space
  for the graph. Explain that clusters are source files and arrows are recorded
  calls, not execution order. Controls have real effects and accessible names.
- C2 — Views: Code, Entry points, Data access. These emphasize the relevant nodes
  while preserving the surrounding network, not navigate to a new screen. Entry
  view identifies all 59 canonical route handlers; selected/hovered entry points
  expose actual HTTP methods and paths, including multiple routes if applicable.
  Data view emphasizes recorded data-access owners and revealed access occurrences.
  Read / Write / Both are distinguishable by shape or label as well as color.
  Default Code view also shows entry/data glyph semantics, so the initial view is
  understandable without first finding a filter. Legend uses product terms. The
  general node key says Code symbol: the index includes functions and classes.
- C3 — Resolution: Files versus Symbols globally collapses/reopens existing
  file groups at their fixed anchors. This is a genuine same-canvas resolution
  control, preserving saved call expansions. A contextual Call depth control
  (0–3 recorded levels, disabled with explanation without a suitable selection)
  changes only the selected branch; other branches remain open. Direct manual
  group/call toggles continue working; mixed/manual states are truthful. No global
  automatic expansion of all 5,586 occurrences. Back includes resolution/view
  and depth changes. No invisible stale selection after coarsening.
- C4 — Project data from evidence, not function names. A dataAccess.operation is
  read for load/query and write for create/update/delete per the schema. Retain
  route/access/call identity and exact source. During the existing raw traversal,
  associate each access with its immediate resolved parent symbol only. An absent
  resolved parent must not cause inferred ownership. Keep every access on its
  occurrence, including ambiguous calls; ambiguity does not erase known effects.
  Canonical badges summarize recorded accesses in that function body, not runtime
  counts or unique code sites. Detail calls may additionally show the explicit
  touchesPersistence read/write/read_write effect; distinguish this from a named
  object access. Unknown must stay unknown. Do not infer from names like delete.
- C5 — From a data-owning function, a clear action reveals its recorded access
  calls and their actual ancestor paths in this same graph. Access-node selection
  shows operation, object, exact call site and resolution; Source retains all
  evidence. Never draw a shortcut call edge or invent a database entity relation.
  Repeated route-scoped occurrences stay distinct. Source descriptions explain
  badges as summaries; counts identify their scope. A read-only function must not
  look like a writer merely because it has a write-like name.
  Reveal only the targeted access/ancestor paths, preserving other manually opened
  branches; do not open every unrelated sibling merely to reach an access. Emphasize
  those paths and prioritize operation/object labels while retaining call identity.
- C6 — View/rail changes do not move the camera or node anchors. Surviving anchors
  during file/detail/depth changes stay within 1 CSS px; entering/leaving nodes use
  existing smooth motion and reduced-motion handling. Back exactly restores camera,
  selection, expanded/collapsed state and presentation settings. Avoid control,
  label or glyph overlap at desktop/390px; use selective labels. Preserve existing
  search, zoom, pan, source, unresolved and partial-scan behavior.

## Data oracle and acceptance

The unchanged scan has 213 symbols, 43 files, 59 handlers, 244 resolved call pairs.
Independent raw traversal found 108 dataAccess records on 108 route-qualified calls:
72 reads (59 load +13 query), 36 writes (14 create +20 update +2 delete), 32 immediate
resolved owner symbols, 31 routes. All 108 have known immediate parents; 94 access
calls themselves are ambiguous. There are 44 unique file/line/operation/object
sites, which is not the same metric as 108 route-scoped records. Do not conflate them.
Examples: sym_get_thread has one load; sym_prepare_run has eight load +eight create
records; sym_delete_thread has load/query and no recorded write. Exact raw source
hash stays c480d2ea15034d86d163101054d0714230ef9f5e79b94918b535431ad072737e.

Run npm typecheck/test/build. Focused behavioral tests independently derive owner,
operation and reference sets from raw JSON; include unresolved-parent, ambiguous
access, same-name, unknown-effect and read-only negative cases. Verify depth/local
branch state and Back instead of mirroring implementation internals.

Actual production browser at 1440×900 and 390×844: all controls present/useful;
opening remains rich (>=120 code glyphs outside rail), 59-entry emphasis and exact
32-owner data emphasis; readable legend and R/W distinctions; Files→Symbols,
selected branch depths 0→1→2 with another branch open; data reveal for _prepare_run
and source fidelity for a load and create; ambiguous effect remains visible; camera
and survivor positions stable; exact Back; rail open/close, search, reduced motion,
mobile interaction and no overflow/runtime errors. Capture actual screenshots.
Baseline fails C1 and data-semantic opening; labels or inactive controls alone fail.

## Plan, readiness and ownership

Ready to dispatch: explicit outcome, local immutable producer available, interfaces
and controls inspected, meaningful positive/negative checks defined. No external
service or new scan is needed. The chosen approach adds semantic emphasis and
evidence-backed badges to the existing graph rather than inventing another layout.

One fresh implementer owns frontend files/tests and README, C1–C6 as one integrated
unit: (1) evidence projection, (2) navigation controls/state, (3) rail/glyph/source
presentation, (4) checks/build and frozen report. No parallel code writers.
Controller owns spec/ledger/final verification docs. Independent full-range code
review and separate actual-browser verification follow freeze; batch fixes through
the author and recheck affected behavior. No push, merge or cloud deployment.
