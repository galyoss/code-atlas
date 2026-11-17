# Atlas real Aegra scan — EFF-330 follow-up

## Outcome and scope

Open the existing local Atlas app and explore genuine scanner output for public
Aegra v0.11.0, revision `46055c0b9adffe51fb168974f79dfadaa6edd612`, instead of the
two hand-authored route examples. User authorized local tool installation, scanning
and frontend integration. Delivery is a reviewed, running local app; no cloud
deployment, PR merge, security-agent execution or arbitrary repository upload UI.

Frontend baseline: `730f8ec0c03e8a07b6c0a832c69e90e0c513ca22` in
`/Users/galyossipov/code/code-atlas-atlas-frontend`, branch `codex/atlas-frontend`.
Scanner source: merged `origin/main` at `0d3fec1`, currently in the primary checkout.
Use Joern 4.0.684 and Java 21. Keep the schema and original examples unchanged.

## Contract

- R1: Run real Joern parsing and overlay export on the pinned public repository.
  Preserve unedited schema-valid JSON, source/scanner revisions, generation time,
  tool versions, invocation and SHA-256. `illustrative` must be false and route count
  must exceed two. Never substitute a sample when scanning fails.
- R2: The default app loads that generated document. Label it as a real scan with
  repository/revision and actual route/symbol counts. Scope details describe
  route-oriented coverage, unresolved gaps and absent agent review accurately.
  Keep original examples only as test/reference fixtures, not the default product.
- R3: All emitted routes are reachable without hunting through a huge vertical map.
  Preserve the sparse Atlas graph experience. Use source-based grouping or compact
  route navigation as needed; show the broader scan scope on initial load. Any
  focused subset must identify its scope. Do not invent calls, findings or edges.
- R4: Selection, direct-call expansion, source details, pan/zoom, Back, reduced motion
  and narrow viewports work on the real graph. Existing anchors and camera remain
  unchanged during expansion; Back restores prior context. Visible active nodes do
  not overlap. Source ranges/snippets and call occurrence identities remain faithful.
- R5: Document reproducible scan/validation/run commands and local tool locations.
  Merge the already-authorized upstream scanner work locally into the frontend
  feature branch, retaining both frontend and scanner instructions. Do not alter
  scanner semantics unless a separately diagnosed blocker is explicitly scoped.

## Acceptance and readiness

Producer: operational worker installs official binaries, clones the pinned Aegra
revision, and runs the existing scanner into `.work/atlas-real-scan/aegra.graph.json`.
That fresh output, not a prepared expected graph, becomes the application asset.
Validate with `scanner.validate.validate_document`; require zero errors and record
the output hash. Count routes/symbols/calls independently from the generated JSON.

Run `npm run typecheck`, `npm test`, `npm run build`, plus existing Python tests with
Joern available. Preserve any scanner test failure as evidence rather than hiding it.
Independent review examines the full frontend baseline-to-candidate diff, generated
asset provenance and any integration resolution. Browser verification exercises the
actual production build at desktop and 390px, opens create_run and get_thread plus
at least one route absent from the old examples, matches source against the JSON,
and checks expansion anchor movement <=1 CSS px and exact Back restoration after
pan/zoom. Verify route discovery/navigation, readable initial context and no runtime
errors. The prior two-route build fails R1/R2 and the additional-route check.

Ready to dispatch: source, runtime installation permission, fixture schema and
browser tooling are available. Actual scan counts are producer outputs, not product
choices. Any failure to produce valid JSON blocks the real-data claim.

## Execution and ownership

1. Operational worker installs and runs scanner, changing no product source; writes
   provenance/report under `.work/atlas-real-scan/`. Source/tool directories isolated.
2. Sole product implementer integrates upstream on the feature branch, consumes the
   produced JSON, adapts UI/layout/navigation, documents and verifies. May prepare
   against schema while scan runs; cannot claim completion before using its output.
3. Freeze final candidate. Independent code reviewer and separate browser verifier
   check R1–R5. Batch necessary fixes through the author and recheck affected paths.
4. Controller records results, updates EFF-330 and hands off the running local app.

Controller owns this spec, ledger and final verification record. No worker may merge
PRs, deploy, edit Linear, message third parties or spawn agents.
