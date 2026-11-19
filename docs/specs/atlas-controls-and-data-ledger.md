# Atlas controls/data execution ledger

- EFF-330 reopened for the user's left-rail and entry/data clarity follow-up.
- Baseline 0cee3a204a9eade6ad74de14ead083bba2118fbb; local feature worktree unchanged.
- Canonical contract: atlas-controls-and-data.md, reviewed inline; ready.
- Immutable scan independently counted: 108 access records, 72 reads /36 writes,
  32 immediate resolved owners; 94 ambiguous access calls retain known effects.
- Implementation: `/root/controls_implement`, single frontend author, running;
  controller documents excluded. Frozen report destination:
  `.work/atlas-controls/implementation-report.md`.
- Independent raw-derived reference oracle: `.work/atlas-controls/data-oracle.json`.
- Parent early CUA visual review: rail and view composition approved; initial Code,
  Data and Entry views inspected at 1440×900. Product feedback before freeze:
  access reveal expanded 446 sibling-heavy details for _prepare_run, obscuring
  actual accesses. Author implementing targeted explicit path IDs with emphasis
  and operation/object labels, preserving manual branches/history. Strengthen entry
  indication when R/W badge coexists. Screenshots in `.work/atlas-controls/screenshots/`.
  Parent CUA phase completed and browser released.
- Author revised targeted reveal: reports actual CUA _prepare_run result of 31
  detail nodes (16 access occurrences +15 ancestors), instead of 446 sibling-heavy
  details. Exact operation/object labels and larger coexisting entry marker added;
  final overlay-label exclusion/self-check before freeze.
- Candidate frozen: `92d06112015bcf97ffffe85a865557d1d87e3b31`; author reports
  typecheck, 20 tests, build and raw/served hash pass. Production assets
  `index-B4dMiiiU.js`, `index-mSlTqDcm.css`.
- Independent full-range review: `/root/controls_review`, `0cee3a2..92d0611`,
  quality **APPROVED**, code-assessable clauses satisfied; rendered acceptance
  assigned to verifier. No blocking code findings. Exact raw oracle/reference
  matches and 224 navigation/Back cases checked. Existing active-label overlap
  risk passed to verifier for actual rendered evidence, not a confirmed new defect.
  Report: `.work/atlas-controls/code-review.md`.
- Separate browser acceptance: `/root/controls_verify`, first gate **FAIL** only
  confirmed active-label collision F1; C1–C5 and remaining exercised C6 pass. Exact
  31-target set, operation/source fidelity, 0px anchor drift, exact Back, depth/mixed
  path behavior, mobile controls/source and reduced motion verified; zero console
  errors. Report: `.work/atlas-controls/behavior-verification.md`.
- Browser phase complete/released. Same author resumed for bounded F1/F2 fix;
  no concurrent writer or browser conflict. Unchanged evidence will be reused.
- Fix round 1 queued, pending completion of browser gate before author edits:
  F1 confirmed active _prepare_run label obscures neighboring glyphs after manual
  get_thread plus targeted reveal. Active label placement skips occupied rectangles.
  F2 parent confirmed raw index includes class declarations (Assistant/RunCreate),
  so generic Function/Functions captions should say Code symbol/Symbols. No data or
  state change required for F2. Spec clarified accordingly; batch through author.
- No new scan/backend/cloud mutations required or authorized.
- Fix round 1 frozen at `2753efc30fc79c0cc96722ac387e49b8c6f73601`. Active labels
  now check occupied glyph bounds and use bounded alternate positions/leader lines;
  generic Code symbol/Symbols copy corrected. Author reports typecheck, 22 tests,
  build pass and zero actual label/glyph intersections in both desktop reproductions
  and 390px search/reveal. New JS `index-CENPCJVe.js`; same CSS/raw scan.
  Bounded independent review and affected desktop/mobile recheck dispatched to the
  same reviewer/verifier. Product code frozen again.
- Final bounded code review **APPROVED**; F1/F2 addressed with no new code findings.
  Independent browser recheck **PASS** on `2753efc`: zero settled label/glyph
  intersections in both desktop reproductions and mobile, clear leader/overlay
  exclusion, unchanged camera/anchors within 1px, correct Symbols copy and retained
  Files/Symbols detail state. Initial full browser evidence reused for unchanged
  behavior. Reports preserve the original failure and the final resolution.
- All C1–C6 and local delivery gates complete; no residual findings. Durable
  acceptance: `docs/ATLAS_CONTROLS_VERIFICATION.md`. Final user-facing screenshot:
  `.work/atlas-controls/screenshots/verified-overview.jpg`.
