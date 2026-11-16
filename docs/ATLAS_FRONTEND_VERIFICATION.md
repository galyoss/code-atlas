# Atlas frontend — local delivery evidence

Date: 2026-11-16. Tracking: [EFF-330](https://linear.app/effective-ads-ai/issue/EFF-330).
Contract: [Atlas frontend specification](specs/atlas-frontend.md).

## Candidate and environment

- Repository: `galyoss/code-atlas`, branch `codex/atlas-frontend`.
- Baseline: `f8ceb12808b90f0145c00bde93e33e5ba47161f8` (documentation and fixtures only).
- Implementation: `d44f28c5d768e6bf61a5bc799853fe95228460e1`.
- Final code: `003e45dff0cc6722f786096e2baa56ac09e686ca` (readable initial framing fix).
- Local workspace: `/Users/galyossipov/code/code-atlas-atlas-frontend`.
- Production-build preview: <http://127.0.0.1:4173/>.
- Development server: <http://127.0.0.1:5173/>.
- Runtime: Node 22.18.0, npm 10.9.3, Vite 7.3.8, Vitest 4.1.12.

This is local delivery of the frontend. No push, PR merge, cloud deployment,
scanner invocation, backend change or production mutation was performed.

## Build and tests

`npm ci`, `npm run typecheck`, `npm test`, and `npm run build` passed. The initial
candidate had nine focused tests; the corrected candidate has ten. A failing
pre-fix sizing control demonstrated the added regression detects F1. npm audit
reported zero known vulnerabilities at installation time.

Both JSON fixtures and the schema/spec retain their original SHA-256 hashes.
Generated `dist/` and local evidence are ignored. Fonts and icons are bundled;
the app has no Codex host API, iframe runtime, backend or CDN dependency.

Final build identity:

| Asset | SHA-256 |
| --- | --- |
| `assets/index-MwjQAFFD.js` | `3548ad511c8f112819b0f03bdfc6930432ffb7e2a253a294d9c017d58a836e18` |
| `assets/index-LdD-WJFY.css` | `ce7415b9d14fe3ddb0a0bff8602d0b3455a63dc6674caecc210769b35b890564` |

The implementer compared all thirteen served build files byte-for-byte to dist.
The independent verifier also proved artifact identity for the initial candidate;
the corrected artifact also passed an independent byte-for-byte check of all thirteen files.

## Independent review and behavior

The code reviewer was separate from the implementer. The behavior verifier was
separate from both. Full base-to-candidate review plus the complete correction
range yielded **COMPLIANT / APPROVED**, with F1 addressed and no residual code
blockers. Browser work used a dedicated Chrome tab via CUA, normal UI interactions
and read-only DOM measurements; viewport/media overrides were restored afterward.

The first production-browser run passed the functional checks below and failed
only F1, initial readability at intermediate widths. Unchanged functional evidence
is retained across the narrowly scoped framing correction.

| Contract | Evidence |
| --- | --- |
| R1–R2 | Aegra defaults to seven summary/context nodes; Papertrail switches to five, resets source/path/history and shows its own source and coverage. Relationships derive from the fixtures. |
| R3 | create_run reveals exactly three direct Aegra calls; _prepare_run reveals four. All seven then ten existing anchors have exactly zero CSS-pixel movement; the camera is unchanged. Child poses and SVG endpoints move together. |
| R4 | Real drag/keyboard pan and zoom, explicit focus/Fit, collapse and breadcrumbs exercised. Back restores camera, path and selection exactly after deeper pan/zoom. Rapid branch switches during animation leave no hidden selected nodes. |
| R5 | The two handle_event occurrences reveal their distinct ambiguous children, each with exact source/invocation and disabled expansion. Inline owner-check evidence matches JSON. Source opening preserves canvas/camera; close and Escape restore focus. |
| R6, unchanged clauses | Keyboard navigation, visible focus, reduced-motion instant poses, and 390px chrome/source panel/panning passed. No horizontal document overflow at 390px. |
| R6, F1 | Initial full fit at 800px made titles 9.26px and subtitles 6.79px. The fix chooses readable selected-route framing when either dimension makes full fit too small; offscreen context is labeled. Explicit Fit remains a deliberate action. The independent recheck passed both fixtures at widths 699/700/800/900, short desktop 1280×620 and roomy 1920×1100. |
| R7 | Reproducible scripts/build, local assets, normal browser serving and future adapter boundary documented in README. No source or analysis is fabricated to populate the UI. |

Final independent browser gate: **PASS** at `003e45dff0cc6722f786096e2baa56ac09e686ca`. Both fixtures use readable .95 initial scale in constrained windows (14.25px titles / 10.45px subtitles) and preserve the full overview at roomy 1.1 scale. The selected route and expansion control remain inside the canvas; offscreen hints match observed clipping and update on resize without moving the camera. Explicit Fit remains functional. At 800px, expansions again preserved all seven then ten existing anchors at zero-pixel delta, and Back restored the complete snapshot exactly after further pan/zoom. Captured browser warning/error logs were empty for these flows.

## Retained local reports

The ignored `.work/atlas-frontend/` directory holds implementation-report.md,
code-review.md, behavior-verification.md, fix-report.md, fix-review.md, the fixture
hash baseline and browser screenshots. Final affected-behavior results are recorded in fix-behavior-verification.md and
summarized above. Screenshots include the original 800px failure and corrected
800px/short-desktop views.

## Limits

The two documents are hand-authored route slices, not scanner results or findings.
Shared auth internals remain collapsed in this handler-call explorer. Validation
does not establish whole-repository scalability, backend/scanner integration,
persisted reports, findings generation, staging/production operation, every browser
engine or full assistive-technology certification. Future scanner input must be
validated against the documented schema before the graph adapter boundary.
