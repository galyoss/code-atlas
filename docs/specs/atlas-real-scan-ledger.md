# Real scan execution ledger

- Ticket: EFF-330, reopened for authorized real-data follow-up.
- Frontend base: 730f8ec; scanner: 0d3fec1; Aegra pin: 46055c0.
- Readiness: ready; existing schema is the interface. Scope/plan reviewed inline.
- Producer: `/root/real_scan_setup`; real fresh Joern scan completed at
  2026-11-16T14:21:20Z, CLI exit 0, schema/invariants zero errors. Raw graph SHA-256
  `c480d2ea15034d86d163101054d0714230ef9f5e79b94918b535431ad072737e`.
  59 routes, 213 symbols, 5,586 call occurrences, 108 data accesses; 55 routes partial.
  Controller's independent AST inventory matched all 56 API/core decorators; three
  additional emitted routes come from the repository's example source file.
- Implementation: `/root/real_scan_frontend`, sole product writer. Upstream merged
  locally as bafc306; candidate `4f4113069c03243688cbd6968c5220a205785d08` frozen.
  Initial source-file overview, on-demand route directory, explicit route focus
  and return implemented. Typecheck/build, 17 frontend tests, 18 Python tests pass.
- Independent review: `/root/real_scan_review`, full 730f8ec..4f41130 range reviewed.
  Source/data/integration checks pass; one Minor / Confirmed narrow overview
  caption/offscreen-hint collision requires correction. No other findings.
- Browser verification: `/root/real_scan_verify`, production build on port 4173.
  Initial run complete: FAIL only for caption collision at fresh 390x844. All other
  exercised clauses pass: 59-route browser set matches raw data; source is faithful;
  dense POST state expands 35 direct calls and 58 nested nodes without overlap;
  existing anchors move 0px, exact Back, reduced motion and no browser errors.
- Fix round: 1 complete at `9d6e9c4c65b8a9cf02a966717fb81f562e98779f`.
  Independent fix review COMPLIANT / APPROVED; final browser Local pre-merge PASS.
  CSS-only correction hides redundant caption while offscreen guidance is visible.
  Fresh 390x844, pan/Fit, desktop overview and route views rechecked; unchanged
  interaction evidence reused. Correct dense-case method is POST state (GET has 19).
- Delivery: local app at existing loopback URLs; no release authorized.
- Decisions: use existing Aegra tag to compare real output with prior examples;
  preserve raw scan and truthful partial coverage. No synthetic fallback.
- Delivery gate: all R1–R5 satisfied for the local saved-scan scope. Evidence summary
  in `docs/ATLAS_REAL_SCAN_VERIFICATION.md`; no remaining required code changes.
