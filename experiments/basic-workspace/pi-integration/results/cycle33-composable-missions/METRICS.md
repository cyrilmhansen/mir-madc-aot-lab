# Cycle 33 metrics

Physical LOC uses `wc -l`, comments and blank lines included. Tests and generated evidence are excluded from production LOC.

| Component | Before (baseline) | After retained | Draft at stop | Notes |
|---|---:|---:|---:|---|
| Workspace core | 3,709 | 3,709 | 0 changed | No canonical model files changed |
| Shared transaction kernel | 121 | 121 | 0 changed | No lifecycle changes |
| Legacy mission gateways C19/C20/C26/C29 | 2,970 | 2,970 | 0 changed | Historical gateways unchanged |
| Shared portable replay | 439 | 439 | 0 changed | One dispatcher, six operation families; no new family |
| TypeScript extension | 234 | 234 | 0 changed | No schema or handler change |
| Bounded coordinator | 0 | 0 | 727 | Unvalidated working-tree draft, removed at stop |
| Two host validation profiles | 0 | 0 | 93 | Both mission profiles were drafted before Mission A; module removed at stop |
| New production bridge | 0 | 0 | 0 | Not started |
| New tests / test fixtures | 0 | 0 | 0 | Mission plans are configuration proposals, not test fixtures |
| New retained classes / mutation dispatchers / replay dispatchers / transaction kernels | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 1 coordinator class drafted | No new implementation retained |
| Mission A production cost | — | Not measured as a passing implementation | 820 draft LOC total with profiles | No mission ran |
| Mission B additional production after A | — | Not measured | Not measured | No Mission A success point existed |

The first bounded implementation attempt was 820 Python LOC before any TypeScript integration or tests and crossed the ~700 LOC stop criterion. No line packing was used. The final committed production-code delta is zero. Mission-specific contract data and reports are committed as experimental evidence, not executable runtime code.

## Execution/performance

Full regression: 249 tests passed, 42.205 seconds test time / 42.33 seconds wall. No Cycle 33 construction, preview, commit, validation, replay, evidence verification, or model timings exist. The historical bridge preflight tests passed inside the suite but are not Cycle 33 mission timing evidence.
