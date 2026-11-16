# CodeAtlas

A full-window code graph for exploring route handlers, their recorded calls, and
source evidence. The app currently opens two bundled, hand-authored examples;
Aegra is selected by default.

## Run locally

Use Node.js 22.12 or newer (verified with Node 22.18 and npm 10.9).

```sh
npm ci
npm run dev -- --host 127.0.0.1
```

The committed lockfile supports `npm ci` with npm 10.9. Dependency refreshes were
performed with npm 11.6.2 to avoid an npm 10 optional-peer resolution bug.

Open the URL printed by Vite. No account, backend, external API, or CDN is needed.
Fonts and icons are bundled with the app.

```sh
npm run typecheck
npm test
npm run build
npm run preview -- --host 127.0.0.1
```

The build emits `dist/index.html` and hashed assets. Preview normally serves at
<http://127.0.0.1:4173>. `dist/` is generated and ignored. A static host can serve the
contents of `dist/`; this repository does not configure a deployment.

## Explore

The initial view keeps labels readable. When the full overview would be too small,
it starts around the selected route; the canvas indicates when nodes are offscreen.

- Click a node to select it. Its **+** button or **Open calls** reveals only direct
  recorded calls. One deeper branch stays open, with ancestors and context retained.
- Drag the canvas to pan. Focus the canvas and use arrow keys to pan by keyboard.
  Zoom controls (or `+` / `-` while the canvas is focused) change magnification only.
- **Bring selection into view** and **Fit visible graph** move the camera explicitly.
  Expansion leaves existing world positions and the camera unchanged.
- **Back** restores the previous selection, expanded path, pan, and zoom.
  Breadcrumbs return to saved ancestor views; collapse closes a local branch.
- **Source** opens one closeable evidence panel. Escape closes it, or goes Back
  when no panel is open. **Hand-authored example** opens coverage and scope details.
- The repository selector starts a fresh exploration of the other fixture.

## Data boundaries

The unchanged sources are [`docs/code-graph-example-aegra.json`](docs/code-graph-example-aegra.json)
and [`docs/code-graph-example.json`](docs/code-graph-example.json), conforming to
[schema v1.0.0](docs/code-graph-schema.json). Neither is a scanner result or a set of
security findings. Each contains two route slices, not a whole repository graph.
Aegra includes partial expansion and unresolved runtime dispatch; Papertrail is a
synthetic example with complete coverage only within its included slices.

Solid mint arrows are recorded calls. Gold lines summarize route/data relationships;
dashed lines mark authentication context or unresolved calls. Positions do not claim
execution order. Call occurrences remain distinct by route and call ID, even when
they reference the same symbol. Data objects and shared auth definitions aggregate
only as summary/context nodes. Shared auth internals intentionally remain collapsed
in this handler-call explorer. Source snippets, inline checks, resolution, and
coverage are displayed from the documents, without inferring findings.

## Implementation and future scanner integration

- `src/data.ts` imports the two source documents directly.
- `src/graph/adapter.ts` maps schema records to route-specific occurrence identities.
- `src/graph/layout.ts` computes deterministic world positions once per dataset.
- `src/graph/navigation.ts` owns branch navigation and exact view snapshots.
- `src/hooks/useAnimatedScene.ts` retargets 600 ms local expansion/collapse animation;
  reduced-motion preferences remove it. Edges use the same animated node positions.
- `src/components/` renders the canvas and evidence panel. React renders source as text.

A future scanner should supply a validated schema document at the `adaptGraph`
boundary instead of the bundled imports. Authentication, scan submission, persisted
reports, findings, and large-repository layout/performance are separate work. The
current layout is designed for bounded route slices, not arbitrary full-repository
scale. Focused tests cover fixture identity, edge provenance, direct expansion,
branch switching, stale selections, camera isolation, and history restoration;
production browser interaction still needs separate verification.
