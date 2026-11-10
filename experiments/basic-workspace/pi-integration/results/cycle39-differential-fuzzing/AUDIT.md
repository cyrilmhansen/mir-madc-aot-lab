# Cycle 39 pre-run audit

## Baseline

- Expected Cycle 38 short SHA: `df750b4`.
- Verified HEAD: `df750b4e62f17d9aa7696f09ef7be1c187a1f814`.
- Branch: `experiment/mir-aot-correctness-cycle3`.
- Tracked working-tree changes are pre-existing MPDecimal, semantic-replay and control-flow evidence. Untracked `preflight-08`, `real-pi-02`, and `real-model-02` evidence also predates this campaign and will be preserved.
- The existing Cycle 38 generator changes three literals in twelve previously saved histories. It verifies replay and MIR against an arithmetic oracle, but does not independently authorize those histories through production tools.

## Existing layers and boundaries

| Layer | Existing capability | Cycle 39 use |
|---|---|---|
| Canonical Workspace | Typed numeric function creation, transactions, rename, literal edits | Create generated programs and apply authorized mutation histories |
| Portable replay | Explicit six-family dispatcher with portable identity allocation and retirement | Reconstruct histories and every operation prefix |
| MIR | Interpreter and JIT worker interfaces in `basic_workspace/mir_execution.py` | Compare both engines to independent specifications |
| Creation authorization | Cycle19 configurable bounded creation sequence; host-controlled validation/checkpoint progression | Selected valid creation workflows through Cycle19 |
| Numeric edit authorization | Cycle20 v1 single-function and v2 per-target contracts through the transaction kernel | Selected maintenance workflows |
| Rename authorization | Cycle37 host-owned rename policy and Cycle36/38 authenticated handoff | Used only when selected for production tier; no new production behavior |
| Agent transport | `extension.ts` and `cycle20b_dispatch_probe.ts` exercise actual TypeScript tool schemas and JSONL | Production bridge subset |

The supported end-to-end constructor grammar is narrower than the Python canonical model. Cycle39 must send only typed constructors admitted by the existing TypeScript schema and Cycle19 gateway. In particular, fixtures are made from one-parameter numeric functions, numeric literals and parameter references, comparison IFs, result assignments and bound one-argument calls; generated source text is never parsed to establish authoritative state.

## Pre-run design

The valid corpus is a bounded cross product of six template families, finite boundary configurations and fixed seeds. It is created from declarative numeric specifications, encoded as existing typed constructor operations, then replayed by the shared replay engine. Expected values come from an independent test-only evaluator over the declarative specifications. Canonical Workspace, projection, replay and both MIR engines are observations only.

Production tier uses the existing Cycle19 sequence mode and TypeScript dispatch probe with host-generated one-step contracts. It is reported separately from direct Workspace/replay coverage. No production code or tool schema change is planned.

Counterexample reduction is bounded to a campaign-specific failing observation: remove irrelevant input points and unused functions/operation suffixes only when a fresh run preserves the same failure classification. A deliberately injected oracle mismatch will validate the reducer and is never counted as a production defect.

## Initial complexity baseline

Production runtime changes expected: zero. Existing production modules and dispatchers are reused. New code belongs only to campaign tooling, tests and evidence. LOC and timing details are recorded after the pre-run inventory and final run.

## Known limits to resolve before execution

The first inspection indicates production creation sequences support at most eight functions and one numeric parameter per function. The generated corpus will stay within those bounds. Whether all supported function body shapes can be driven from generic host sequence data through the actual Pi schema is being checked during harness development; any unsupported shape will be reported as a capability gap, not passed as a valid production case.
