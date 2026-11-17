# Cinematic 3D verification

Local pre-merge: **PASS**. Verified 2026-11-17 on `codex/atlas-integrated`, baseline `9c86c857af79745bc11302db6511e6b1b885dbd7`.

## Delivered behavior

The **3D universe** mode displays the selected scan as a perspective constellation with glowing nodes, curved relationships, illustrative electrical pulses and an orbiting camera. Drag, touch, wheel and keyboard camera controls, pause, reset, fullscreen and real node details work. The existing 2D workspace stays mounted and returns with its selection, entry flow, search, source panel and camera intact.

Aegra renders all **5,920 recorded nodes** (213 symbols, 5,586 qualified call occurrences, 121 authentication steps) and **7,294 relationships** in 43 file groups. No graph evidence is fabricated; decorative atmosphere is separate. Definition/auth-context edges remain static. The immutable raw scan SHA256 is `c480d2ea15034d86d163101054d0714230ef9f5e79b94918b535431ad072737e`.

## Candidate and checks

Final source fingerprint over the nine implementation/dependency files: `1b60a2a911e009226a0131c7ab9f1e0cf26b47baa08703774c8dda6c0f2037b8` (ordered list in the implementation report). Final production assets: `index-BbBHTiHX.js`, `CinematicGraph-DvhPBtPB.js`, `CinematicGraph-A6uh7cm1.css`.

- Typecheck and production build pass. All 41 tests in eight files pass; the two subsequent bounded shader/markup corrections received typecheck/build and independent review plus affected browser rechecks.
- Independent full-change review and both bounded fix reviews: **COMPLIANT / APPROVED**.
- Separate actual Chrome verification: rich rendered scene, real perspective changes with orbit, wheel/touch zoom, pause freezes ambient clock/camera, reset, node selection with original source/uncertainty, and exact 2D investigation roundtrip pass.
- Desktop 1440×900 and mobile 390×844 verified. An initially hidden mobile launch control was corrected; fresh 2D → 3D → 2D → 3D entry and no horizontal overflow pass on the final build.
- Initial and dynamic reduced-motion preferences pass. Unavailable WebGL and lost-context recovery to 2D and reopening pass. Temporary browser overrides restored; no unexpected console errors in normal operation.

## Running locally

Open <http://127.0.0.1:4173/?sample=aegra&view=cinematic>. The detached preview serves the build from this checkout. For a restart: `npm run build` then `npm run preview -- --host 127.0.0.1 --port 4173 --strictPort`.

The scene represents a partial static scan, not observed runtime execution. Browser evidence concerns the bundled real Aegra fixture; alternate input fidelity is covered by projection tests and code review, not a new live scan. This is local delivery, not a deployment or universal device-performance benchmark. The lazy Three.js chunk produces Vite's normal size advisory (about 589 kB / 147 kB gzip); it is not downloaded for ordinary 2D entry.

Evidence is retained under ignored `.work/atlas-cinematic/`: `implementation-report.md`, `fix-report.md`, `mobile-fix-report.md`, `code-review.md`, `fix-review.md`, `mobile-fix-review.md`, `behavior-verification.md`, and `verify-final-desktop.jpg`.
