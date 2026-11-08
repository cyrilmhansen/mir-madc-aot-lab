# Cycle 17 — Semantic operation granularity

## Result

Both genuine Pi/Sushi sessions completed the same `IS_ADULT(ID)` mission from independent revision-4 Workspaces. Each discovered `AGE_BY_ID`, submitted one accepted preview, committed exactly one atomic Workspace transaction (revision 4 → 5), and passed the same independent host oracle through MIR interpreter and JIT. Each fresh-workspace constructive replay passed structural, binding and behavioral checks with 24 remapped identities.

Arm A used the existing atomic whole-function constructor. Arm B built the same function in a temporary typed draft from nine ordered operations, then previewed and committed the complete candidate through the same MissionGateway. No invalid model proposal, rejected preview, policy denial or retry occurred in either session. This is one feasibility pair, not a reliability benchmark.

The active incremental schema was smaller and the semantic graph was composable, while the agent used more turns, calls, output tokens and elapsed time in this single trial. The evidence supports offering both granularities: atomic construction for simple one-shot functions; revisioned drafts when composition, inspectable intermediate state or localized diagnostics matter.

## Pre-registered setup

The complete plan was written before inference to `pre-registration.json`; its SHA-256 is `06814d66ad78357231bf604e4cde62a808b9a4ef8e0d46bb7824d00429b8479c`. Both runs used Pi 1.5.0, Sushi, `Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw`, `thinking=low`, the operator's configured provider, 180-second wall limit and zero automatic retries. The same task, common discovery instruction, seed, functional oracle and criteria were used. The only planned difference was authoring protocol. Each arm had an independent Workspace and actual Pi schema capture. The model was not given a completed function body.

Recorded runs:

- [`arm-a-atomic/`](arm-a-atomic/) — genuine atomic session.
- [`arm-b-incremental/`](arm-b-incremental/) — genuine incremental session.
- `preflight-atomic/`, `preflight-incremental/`, and `preflight-incremental-unary/` — deterministic schema/tool captures only; no inference.

## Measured comparison

| Measure | A · Atomic | B · Incremental |
|---|---:|---:|
| Active Pi tools | 5 | 8 |
| Tool schema bytes | 20,343 | 9,662 |
| Approx. schema tokens (bytes ÷ 4) | 5,086 | 2,416 |
| Model turns | 5 | 8 |
| Pi tool calls | 5 | 8 |
| Semantic construction operations | 1 constructor | 9 draft ops |
| Draft revisions | n/a | 0 → 9 |
| Invalid model requests / invalid draft batches | 0 / 0 | 0 / 0 |
| Accepted preview / commit | 1 / 1 | 1 / 1 |
| Workspace revision | 4 → 5 | 4 → 5 |
| Provider prompt/input tokens | 9,068 | 10,526 |
| Provider completion/output tokens | 2,448 | 4,894 |
| Provider-reported cache-read tokens | 30,872 | 63,954 |
| Pi/process wall time | 37,930.56 ms | 56,023.95 ms |
| Constructive stream | 8,312 bytes | 8,318 bytes |
| Historical journal | 64,364 bytes | 64,425 bytes |
| Pi raw event stream | 313,386 bytes | 572,258 bytes |
| Normalized presentation events | 9,169 bytes | 10,850 bytes |
| Generic frame JSON / offline HTML | 28,429 / 37,334 bytes | 33,773 / 41,212 bytes |
| Fresh replay remappings | 24 | 24 |

Pi-reported cache-read counts are shown separately from input tokens and are not treated as free. Provider token accounting is not inferred from bytes. The schema-token estimates are only rough byte/4 estimates. B's provider input was 16.1% above A, output was roughly double, cache-read accounting was also higher, and the run took 18.1 seconds longer. These are observed values for two distinct conversations, not a controlled statistical performance result.

Pi tool-end events measured local discover/inspect/draft calls at 0–4 ms, previews at 8–10 ms, commits at 9–11 ms, and validation around 207–210 ms. These are Pi-reported end-to-end local tool durations, not pure gateway CPU measurements. An existing Cycle 16 bridge microbenchmark reports 0.082 ms median / 0.252 ms p95 IPC, but that is a separate benchmark and should not be conflated with the session timings.

## Behavior and transactional safety

Both arms passed the independent revision-5 checks:

| ID | `AGE_BY_ID` | `IS_SENIOR` | `IS_ADULT` |
|---:|---:|---:|---:|
| 101 | 25 | 0 | 1 |
| 205 | 55 | 1 | 1 |
| 900 | 53 | 1 | 1 |
| 999 | -1 | 0 | 0 |
| 2 | -1 | 0 | 0 |

Age 17 returned adult=0, age 18 returned adult=1, and unknown IDs remained 0 in isolated interpreter and JIT fixtures. `AGE_BY_ID` and `IS_SENIOR` were unchanged. `IS_ADULT` has a resolved semantic call edge to `AGE_BY_ID`. Interpreter and JIT agreed on the required corpus and boundary cases.

Arm B's nine draft operations were: parameter reference; bound call; literals 18, 1 and 0; `>=` expression; IF with then/else blocks; one result assignment in each branch. Each operation had a distinct operation ID and handle and advanced the draft revision. The final candidate alone went through the atomic mission preview/commit. `draft-operation-history.json` records the draft activity; `constructive-operations.json` contains only the committed constructor operation required for replay.

The draft tests verify unknown draft/handle, wrong type, invalid parent and operation order, duplicate IDs, stale draft and Workspace revisions, partial-batch rollback, scope denial, commit without an accepted preview, post-commit mutation and external Workspace commit invalidation. Rejected or uncommitted draft changes do not mutate canonical state. **Erratum (Cycle 18 audit):** the operator summary recorded 153 tests; rerunning `python3 -m unittest discover -s tests` before Cycle 18 additions confirms 153, so the previous 152 count was a reporting error. The exact cause of the one-test discrepancy was not established.

## Visualization and provenance

Each arm has `visual-replay-generic.html`, `visual-frames-generic.json`, `visual-events.jsonl`, and `visual-source.json`. Initial seed construction is labeled scripted, discovery and authoring are genuine Pi actions, preview/commit are gateway and Workspace outcomes, and interpreter/JIT results are host validation. Arm B's observed genuine session submitted all nine operations in one Pi batch. The captured session's visual trace therefore shows the ordered batch as a draft proposal and the complete candidate preview; it does not claim nine separate model turns or individual live observations between those operations. The current gateway can publish ordered intermediate states derived from each operation as it handles that batch, with provenance explicitly labeling the single-call batch. It remains one draft transaction and never advances committed BASIC before revision 5.

## Decision

1. **Is incremental authoring materially simpler for the model?** Not established. It uses flat typed handles and a much smaller schema, but required 8 turns/8 tool calls versus 5/5. Both models succeeded without malformed proposals.
2. **More interactions but fewer malformed proposals?** More interactions yes in this pair; malformed proposals were zero in both arms, so no reliability advantage is shown.
3. **More compact/extensible schema?** Yes in measured serialized schema: 9,662 bytes versus 20,343. New flat operation kinds add a bounded branch rather than copying a recursive tree into nested locations. Tool count is larger, and practical provider support still needs broader trials.
4. **More useful intermediate validation?** The draft supports typed validation, handle-level diagnostics and inspection before the complete candidate preview. The session's one batch prevented the model from observing a tool response between its nine operations; the gateway nevertheless validates each operation and atomically rejects a partial batch.
5. **Better human visibility?** The draft is clearly distinct from committed code and can be presented incrementally from recorded operations. In this actual batch, live visibility is of the submitted batch and final candidate, not nine separate interactive calls.
6. **Is draft state justified?** For longer compositions, resumable tool interaction, localized errors or an operator who wants to inspect partial construction, possibly. For this short function, it adds state and policy lifecycle work without demonstrated correctness or token savings.
7. **Support both?** Yes, provisionally. Retain atomic construction as the straightforward path and offer bounded incremental drafts for composability. Keep commits atomic and route both through the same semantic validator and MissionGateway.

## Reproduction and evidence

Deterministic tests and offline viewer commands:

```sh
python3 -m unittest discover -s experiments/basic-workspace/tests -v
python3 experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/pi-integration/results/cycle17-granularity/arm-a-atomic
python3 experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/pi-integration/results/cycle17-granularity/arm-b-incremental
```

The outputs open offline at the corresponding `visual-replay-generic.html` files. To repeat inference, first inspect the registered plan and local Pi/provider configuration; the recorded sessions are the actual one-shot A/B evidence, and are not regenerated by tests. No LLM retry was performed to improve these statistics.

## Limitations

- One A/B pair cannot establish reliability, general usability or model superiority.
- Both runs succeeded, so this experiment did not exercise a genuine model rejection or recovery; those failure paths are deterministic tests.
- The incremental grammar is numeric and mission-bounded. It does not expose arbitrary local assignment, loop construction or a general BASIC language.
- The temporary draft is process-local and is not designed for persistence or resume after gateway termination.
- Pi tool allowlisting is not an OS security boundary.
- No text-editing comparison was run.
