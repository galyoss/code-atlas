# Atlas cinematic 3D

EFF-330 follow-up. Baseline `9c86c857af79745bc11302db6511e6b1b885dbd7`, current `codex/atlas-integrated` checkout. Local running frontend is the delivery target.

## Intent and design

The owner explicitly prioritizes visual spectacle over readability for this mode: a striking, genuinely three-dimensional code network, orbitable by pointer, with animated energy traveling along connections. Keep the existing investigative 2D workspace accessible and its context intact.

Choose a lazy-loaded Three.js renderer over pseudo-3D SVG or a generic graph widget. Art direction: an electric constellation, near-black space, icy cyan/teal filaments with amber data terminals, luminous clustered cores, soft bloom, restrained star dust and a slowly orbiting cinematic camera. One spacious scene, minimal translucent controls, no wall of widgets. Decorative atmosphere must not be counted as code or fabricated relationships. Motion is illustrative, not observed runtime traffic.

## Contract

- R1: Every loaded AtlasGraph can enter `3D universe` from its workspace; `?sample=aegra&view=cinematic` opens the real bundled Aegra scan directly in 3D. Keep the existing home and scan routes. A visible `2D graph` action returns to the same investigation state. Do not substitute sample data for API scans.
- R2: The opening scene is materially rich, derived from actual symbols and route-qualified occurrences/edges, not a tiny sample. On Aegra show all 213 canonical symbols and at least 1,000 actual recorded occurrences with actual relationships (prefer all 5,586 calls if performant). Display truthful scope/counts and distinguish illustrative pulse animation from runtime observations. Do not mutate scanner, raw graph/schema or findings.
- R3: Actual perspective depth, responsive pointer/touch orbit and zoom, reset framing; cinematic automatic rotation and edge energy pulses. Opening transition, subtle drift, glow and visual layering create a finished memorable scene. Render progress/failure rather than a blank panel; a working 2D escape if WebGL unavailable/context lost.
- R4: Pause stops ambient camera/particles/energy motion, while manual navigation remains available. Honor reduced motion from initial load and on preference changes. Dispose WebGL resources/listeners on unmount, cap device pixel ratio and reduce excessive work while hidden.
- R5: Controls and a concise selected-node detail are usable at desktop 1440x900 and mobile 390x844; no horizontal overflow. Pointer hover/click reveals real node identity. Controls are keyboard accessible with labels; 2D remains accessible for detailed investigation.

## Plan and ownership

One implementer owns `src/components/*` new cinematic surface, `src/graph/*` new 3D projection/layout, minimal `src/App.tsx` integration, isolated CSS and package/lock changes plus meaningful data/projection checks. Existing navigation/2D contracts remain intact. Parent owns this spec, delivery ledger, Linear and preview server. Independent reviewer owns read-only full-diff review; separate verifier owns actual browser acceptance. Serialize code writers in this shared checkout; no merge, deployment, push or remote changes.

Steps: inspect current contracts; install pinned renderer dependency; project real IDs/edges into deterministic 3D positions; implement atmosphere, energy and orbit; integrate mode and real selection; run typecheck, tests and production build; independent review and actual-browser visual/behavior acceptance; fix observed failures and rerun affected checks. Commit the finished accepted local change.

## Acceptance and verification

Done when the local app opens an impressive live 3D Aegra network with thousands of evidence-backed nodes, visible energy movement, functioning orbit/zoom/pause/reset and return to 2D, and all required review/checks pass.

Exact commands: `npm run typecheck`, `npm test`, `npm run build`, `git diff --check`. Existing baseline has only 2D SVG and no cinematic mode, so it fails R1/R3. Data checks compare node IDs and edge endpoints to adapted raw scan, all canonical inclusion, minimum actual-occurrence count, finite stable 3D coordinates, no forged edges. Do not merely snapshot implementation output.

Actual browser checks on built preview: open `?sample=aegra&view=cinematic`, wait for nonempty WebGL scene, inspect screenshots and motion at two times; drag changes projection, wheel zoom changes framing, pause freezes ambient motion, reset restores framed scene; select real node; switch 2D and back with context; resize mobile and exercise controls; emulate reduced motion; confirm unavailable-WebGL fallback and no unexpected console errors. Static screenshots alone cannot prove animation/interaction. Visual review must assess composition, depth, richness and glow, not just existence of a canvas.

Producer: bundled immutable Aegra v0.11.0 scan at `46055c0`, SHA256 `c480d2ea15034d86d163101054d0714230ef9f5e79b94918b535431ad072737e`. Static partial route scan; animated pulses do not claim runtime execution. API scan route uses its own loaded graph. Local browser/device performance only, no universal FPS claim. Evidence in ignored `.work/atlas-cinematic/`, durable outcome in delivery ledger.

Readiness: ready to dispatch. Owner's priority and local authorization are explicit; no unresolved product decision. Parent reviewed contract, file boundaries and acceptance for consistency before dispatch.
