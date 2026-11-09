# Cycle 25 — Structural semantic editing

## Result

The experiment succeeded. A genuine Pi 1.5.0 / Sushi Qwen session inserted a typed conditional into the existing `SCORE_CLASS(X)` function. The gateway previewed and committed one structural transaction, advancing Workspace revision 7 to 8. The original function body was not replaced. `CLAMP_SCORE` and `IS_PASSING` stayed unchanged, and `SCORE_CLASS` retained its existing statements and call bindings.

The agent's first proposal was rejected with `UNKNOWN_PARAMETER`: it supplied the discovered portable parameter handle `score_class.parameter.id` as a `local_ref.name`, where the expression grammar requires the parameter's source name `X`. The rejected preview left revision 7 and the authoritative program unchanged. The agent corrected the reference in its next proposal; that preview was accepted and committed. The transcript records both requests and results.

## Reconstruction and editing

The baseline was replayed from the six authentic Cycle 24 committed operations into an empty Workspace. It reached revision 7, matched the normalized semantic state and recorded validation, retained all 17 portable identities, and had the expected `IS_PASSING → CLAMP_SCORE` and `SCORE_CLASS → {CLAMP_SCORE, IS_PASSING}` bindings.

The authorized edit added an IF comparing the discovered `CLAMP_SCORE(X)` call to 50 and assigning 3 to the function result. It was inserted before the existing generated result epilogue. Preview did not mutate the Workspace. Commit created exactly one result-assignment statement identity: `score_class.statement.category50` → `stmt_dbfd1226a54a495ca046b8712592fa27`. IF marker lines have no independent identity in the current canonical model. No IF identity was invented.

The Cycle 25 replay stream contains the six original committed operations plus the committed structural insertion. A fresh empty Workspace replay remapped all 18 portable handles, preserved equivalence of the original 17, and matched the final normalized structure, bindings, and observed behavior.

## Independent MIR checks

Interpreter and JIT agreed with the host-owned oracle for all 16 inputs:

`-100, -1, 0, 1, 19, 20, 39, 40, 44, 45, 49, 50, 51, 60, 100, 200`

The results match the requested four categories after normalization: below 20 → 0; 20–44 → 1; 45–49 → 2; 50 → 3. Values above 50 normalize to 50 and return 3. Existing `CLAMP_SCORE` and `IS_PASSING` outputs remained unchanged on the corpus. This is finite test evidence, not a proof over all numeric inputs.

## Production interface and implementation cost

The no-inference preflight exercised the production TypeScript handler and JSONL bridge, captured the five active tools, and measured the structural-preview schema at 14,957 bytes. It verified accepted preview, non-mutation, atomic commit, host validation and replay. It also rejected unauthorized function scope, changed anchor, wrong dependency, invalid condition, stale revision, and whole-body replacement.

The Workspace change adds the `insert_typed_if_block` transaction operation and shared line insertion helper: 144 additions and 10 removals in `model.py`, 13 client lines, and 7 server lines. The Pi extension change is 10 additions and 1 removal; the production dispatch probe changed by 3 additions and 2 removals. The campaign gateway is 472 lines including reconstruction, mission authorization, host oracle, lifecycle reporting, and evidence writing. No transaction lifecycle implementation was added: both preview and commit use the Cycle 23 `SemanticTransactionKernel`. The expression parser, typed expression token emitter, Workspace transaction cloning, MIR engines, and existing replay machinery were reused.

## Genuine model session measurements

- Model: `Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw`; Pi `1.5.0`.
- Tools: 5; schema bytes: 14,957.
- Turns: 6; tool calls: 6 (discover 1, inspect 1, structural preview 2, commit 1, validate 1).
- Preview attempts: 2; rejected proposals: 1 (`UNKNOWN_PARAMETER`); accepted previews: 1; commits: 1.
- Provider-reported usage: 16,764 input, 5,064 output, 63,586 cache-read tokens; these figures are provider metadata, not estimates from bytes.
- Recorded elapsed inference/session time: 137,749.775 ms; gateway tool processing: 626.103 ms.
- Agent settled normally; launcher exited 0; no timeout or automatic retry.
- Committed constructive stream: 9,262 bytes; history journal: 13,039 bytes; Pi JSONL session: 718,059 bytes.
- Generic frames: 9; frame JSON: 33,841 bytes; standalone HTML: 44,571 bytes.

## Visualization and provenance

Open [visual-replay-generic.html](real-agent-01/visual-replay-generic.html) locally. It shows the committed revision-7 program, discovery and inspection, the rejected first proposal, accepted preview while revision 7 remains authoritative, revision-8 commit, and two revision-bound interpreter/JIT observations. The new IF appears in committed source only after the commit event. The dependency graph remains unchanged. The HTML is standalone and offline.

The first generated viewer run rejected `event_type: validated`; the generic presentation contract uses `validation`. The producer now emits the canonical event type, the saved derived presentation events were canonicalized without changing their observations or event order, and the viewer was regenerated. The raw Pi transcript and semantic history were not rewritten. No screenshots were captured, so pixel-level browser appearance was not evaluated.

## Formatting note

The first extraction of the shared token insertion helper inserted after the epilogue line's existing whitespace. Consequently, the genuine run's revision-7 display snapshot has six indentation-only differences from the preserved Cycle 24 snapshot; its normalized semantics, identity mapping and execution were equivalent. This was found during the final audit and fixed by inserting at the first token of the anchor line. The regression suite now verifies exact revision-7 display equality under the corrected code. The preserved genuine session snapshots remain unchanged as evidence of what that run observed.

## Reproduction

From the repository root:

```sh
python3 experiments/basic-workspace/pi-integration/cycle25_preflight.py \
  --output experiments/basic-workspace/pi-integration/results/cycle25-structural-edit/deterministic-preflight

python3 experiments/basic-workspace/pi-integration/run_cycle25.py \
  --output experiments/basic-workspace/pi-integration/results/cycle25-structural-edit/real-agent-01 \
  --timeout 240

python3 experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/pi-integration/results/cycle25-structural-edit/real-agent-01

python3 -m unittest discover -s experiments/basic-workspace/tests -v
```

The complete suite passed 219 tests (the 212-test baseline plus seven Cycle 25 tests).

The genuine inference command above is documented for provenance and is not needed to inspect or replay saved evidence. It should not be repeated as part of artifact review.
