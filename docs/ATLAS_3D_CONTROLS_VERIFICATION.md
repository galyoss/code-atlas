# 3D layouts and filters verification

Local pre-merge: **PASS**, 2026-11-17. Baseline `e690407beda7fbf03900735046911023be98a624`, branch `codex/atlas-integrated`. Contract: `docs/specs/atlas-3d-controls.md`.

## Behavior

A collapsible left rail controls Files, Entry points and Data flow layouts within the cinematic 3D scene. The same nodes and their edges morph over900ms, including interrupted transitions, without recreating WebGL or resetting the camera. File layout preserves the original constellation. Semantic layouts separate actual handlers, code and recorded data terminal occurrences.

All calls / Symbols detail, source-file cluster and literal AND-term search intersect. Hidden nodes cannot be selected, edges require both endpoints, and hidden selection clears. Clear filters restores the exact original population. Entry-owned file groups are distinguished from actual call-site source fields. Symbols-only Data flow explains why call-level data operations are hidden. Layout movement remains available while ambient motion is paused; reduced motion makes layout changes immediate.

## Candidate and evidence

- Final five-source-file fingerprint: `e15a1fed94659a6e93af764e96d29f10daaa928ce1dfa3962a7ded4f16c31d05` (ordered paths and procedure in implementation report).
- Built assets: `index-CbzNarVL.js`, `CinematicGraph-B5ptj_bY.js`, `CinematicGraph-BPaT1Vb8.css`.
- Typecheck, production build,45tests in9files and diff check pass. Independent full code review: **COMPLIANT / APPROVED**, no actionable findings.
- Independent raw oracle: all5920nodes/7294edges; Symbols213/244; health cluster35/33; health Symbols6/2; health+suppress4/0; impossible query0/0. Clear restores5920/7294. Data flow places exactly59handlers,497terminal occurrences and5364remaining nodes in their correct bands.
- Separate actual Chrome verification sampled410frames: same canvas, fixed camera and paused ambient clock;70intermediate transition frames and78poses across interrupted Files→Data→Entries. This is continuity evidence, not an FPS benchmark.
- Actual node selection tracks the displayed node; visible `get_thread_state` survives layout/search changes. Filtering it out clears detail/selection; clicking its old position cannot select the hidden node.
- Desktop1440×900 screenshots and a1512×771rail-fit check pass. Mobile390×844 layout/filter/rail reopen, count restoration and no horizontal overflow pass; rail bottom608 remains above dock top707.
- Initial reduced motion renders with time0 and immediate layout/filter progress1.0000. Dynamic preference passes. Exact2D create_run flow, Source text and search survive the roundtrip.

## Scope and artifacts

Open <http://127.0.0.1:4173/?sample=aegra&view=cinematic>. Detached production preview serves this checkout. No deployment, push, new scan or schema/backend modification. The raw partial Aegra scan remains SHA256 `c480d2ea15034d86d163101054d0714230ef9f5e79b94918b535431ad072737e`; electric motion is illustrative. Supplied alternate graph behavior is checked by tests/review rather than a new live API scan. Existing WebGL recovery is unchanged and retains the preceding cinematic verification evidence.

Evidence under ignored `.work/atlas-3d-controls/`: `implementation-report.md`, `code-review.md`, `behavior-verification.md`, `independent-oracle.json`, `verify-files-desktop.jpg` and `verify-data-desktop.jpg`. No universal-device performance or exhaustive memory-profile claim.
