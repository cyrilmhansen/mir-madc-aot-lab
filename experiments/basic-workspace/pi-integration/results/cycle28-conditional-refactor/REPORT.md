# Cycle 28 — Conditional refactor results

## Outcome

One genuine Pi 1.5.0 / Sushi / Qwen session refactored the final SCORE_CLASS conditional. The agent discovered IS_AT_CAP, inspected the typed SCORE_CLASS condition and assignment anchor, previewed the replacement, committed it once, and requested MIR validation. The program advanced from revision 10 to 11. The agent session settled normally and the launcher exited with status 0.

The operation changed only the selected IF condition:

- Before: `IF (NORMALIZE_SCORE(X) = 50) THEN`
- After: `IF (IS_AT_CAP(X) = 1) THEN`

`IS_AT_CAP` is bound through portable handle `is_at_cap.function`. The other conditions, all result assignments, all four function identities and all 23 existing portable handles were preserved. The semantic dependency graph gained exactly `SCORE_CLASS → IS_AT_CAP`; the prior graph edges remain.

## Deterministic bridge preflight

The production Pi TypeScript handler and loopback JSONL gateway accepted a known-good typed request with a tool-call correlation ID. Preview remained at revision 10; disposable commit advanced once to revision 11. Interpreter/JIT behavior and a fresh complete replay passed. The actual active inventory was exactly five tools.

The preflight rejected wrong target, wrong expected condition, undiscovered call handle, unauthorized call and stale revision without mutation. TypeBox rejected the bad-arity request, assignment-target-shaped request, and an unknown top-level field. Duplicate commit was rejected. See `deterministic-preflight/production-bridge-contract-v2/summary.json` for the final explicit-contract run.

## Independent validation and replay

The host oracle checked 16 inputs: `-100, -1, 0, 1, 19, 20, 39, 40, 44, 45, 49, 50, 51, 60, 100, 200`. All outputs for NORMALIZE_SCORE, IS_PASSING, SCORE_CLASS and IS_AT_CAP matched the independent expected results in both MIR interpreter and JIT. Before and after SCORE_CLASS values are identical across the entire corpus. The call graph check is semantic-ID based.

The final constructive stream contains the nine authentic Cycle 27 operations plus the genuine committed conditional edit. A fresh empty Workspace rebuilt revision 11 with structural, binding and behavioral equivalence. All 23 portable handles resolved; a separate host-to-host identity map records the scope of the UUID remapping. No BASIC source was used as replay input.

## Genuine model activity

- Model: `Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw`; Pi 1.5.0.
- Model turns: 6; tool calls: 5 (discover 1, inspect 1, conditional preview 1, commit 1, validate 1).
- Preview: 1 accepted; rejected proposals: 0; commit: 1.
- Pi-reported usage: input 25,248; output 3,026; cacheRead 66,230; cacheWrite 0. These are provider-reported fields as emitted by Pi, not estimates from bytes.
- Pi-observed inference elapsed: 60,134.543 ms; gateway tool processing total: 905.479 ms.
- Pretty serialized active schema: 17,767 bytes; compact JSON serialization: 5,410 bytes.
- Total launcher wall time was not separately measured. No timeout or retry occurred.

## Visual evidence

The code-first replay is `real-agent-01/visual-replay-generic.html`, with recorded frames in `visual-frames-generic.json`. The preview remains code revision 10 and shows the exact one-line before/after diff as a candidate overlay. Only the commit advances code to revision 11. The dependency panel shows the added semantic edge. The validation panel is revision-bound and uses authentic host observations; `visual-evidence-view.json` selects boundary inputs 44, 45, 49 and 50 for the compact display.

Firefox headless rendered actual screenshots at `real-agent-01/screenshots/`: baseline, preview, commit and validation. The HTML opens offline. Launch with:

```sh
python3 experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/pi-integration/results/cycle28-conditional-refactor/real-agent-01
```

The original visual event output is retained as `visual-events-original.jsonl`; the renderer consumes its normalized counterpart. The raw Pi transcript and gateway history are unchanged.

## Schema accounting

The Cycle 27 19,767-byte figure was the on-disk pretty JSON array; 5,151 bytes was a compact serialization of the same array. Both saved captures contain the same schema. Cycle 28's captured five-tool schema is 17,767 bytes pretty and 5,410 bytes compact. The Cycle 28 operation uses the existing typed expression representation and transaction kernel; no second transaction lifecycle was added.

## Regression results

The full suite passed **234 tests and 80 subtests**. The four focused Cycle 28 conditional-edit tests also passed. No MIR, BASIC syntax, canonical representation, BWM or language backend changes were made.

## Limitations

- The IF itself has no semantic ID; an unambiguous typed control path plus stable direct assignment anchor is required.
- Replaced condition token IDs are not preserved. Other token identities and all statement/function identities were checked.
- The live process did not journal every transient opaque ID, so the identity table compares deterministic Workspace reconstruction with fresh replay, not all actual model-process UUIDs.
- The first run's generated MISSION file used a generic numeric-maintenance schema even though its gateway enforced the exact condition edit. The corrected explicit condition contract was then validated through the production bridge without inference. This mismatch is documented in AUDIT.md; no inference was repeated.
- The finite 16-value corpus is strong boundary evidence, not a proof for all numeric inputs.
- One successful model run supports feasibility only; it does not establish general agent reliability.
