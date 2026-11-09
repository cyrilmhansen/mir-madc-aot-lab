# Cycle 26 — Identity-Preserving Semantic Rename

## Outcome

The genuine Pi/Sushi agent renamed `CLAMP_SCORE` to `NORMALIZE_SCORE` through the existing typed `rename_symbol` transaction. Workspace revision advanced once, from 8 to 9. The function identity, its parameter and statement identities, all 18 portable handles, token IDs, and dependency edges were preserved. Interpreter and JIT results remained identical on the 16-input corpus, and the complete constructive stream replayed in a fresh Workspace with 18 identity remappings.

The rename primitive was already correct for this case. No canonical model or Workspace mutation code was changed. Cycle 26 reuses `SemanticTransactionKernel`; it adds a narrow policy adapter and a generic Pi tool schema.

## Evidence and commands

From the repository root:

```sh
python3 -m unittest experiments.basic-workspace.tests.test_cycle26_semantic_rename -v
python3 experiments/basic-workspace/pi-integration/cycle26_preflight.py \
  --output experiments/basic-workspace/pi-integration/results/cycle26-semantic-rename/deterministic-preflight
python3 experiments/basic-workspace/pi-integration/run_cycle26.py \
  --output experiments/basic-workspace/pi-integration/results/cycle26-semantic-rename/real-agent-01 \
  --timeout 240
python3 -m unittest discover -s experiments/basic-workspace/tests -v
```

The deterministic preflight called the actual TypeScript extension handler and JSONL gateway dispatch. It confirmed the active five-tool inventory and 1,387-byte serialized schema; exercised non-mutating preview, commit, duplicate commit, unknown-field rejection, stale revision and policy denials; and independently validated the disposable commit and replay. Pi's configured model was available. No model inference was performed during preflight.

The real run is preserved in [`real-agent-01`](real-agent-01/). It used Pi 1.5.0 and `Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw`; one bounded session, no retries. The model discovered and inspected the target, proposed one rename, previewed it, committed it, and requested validation. There were five turns and five tool calls (one each for discovery, inspection, preview, commit and validation), no rejected preview, and one commit. Pi reported 16,574 input tokens, 1,768 output tokens and 36,004 cached input tokens. Session elapsed time was 38.542 seconds; recorded gateway tool processing totaled 505.39 ms. Cache accounting is reported as provided by Pi, not independently inferred.

The exact committed portable operation is the final `rename_symbol` operation in [`constructive-operations.json`](real-agent-01/constructive-operations.json). It continues to target `clamp_score.function`, whose historical spelling is intentionally retained as a stable handle. Discovery reports that handle alongside its current source name, `NORMALIZE_SCORE`.

## Identity and behavior

The host comparison found exactly the authorized source-name change in the normalized semantic projection. The nine changed token IDs are the declaration and bound reference spellings for the renamed symbol; the token identities themselves remain present. The target Workspace symbol ID, parameter and statement identities, and portable mapping did not change. The call graph is unchanged when expressed using portable caller/callee identities. No replacement function was created.

Both MIR engines returned the same values as the revision-8 host-owned baseline for `-100, -1, 0, 1, 19, 20, 39, 40, 44, 45, 49, 50, 51, 60, 100, 200`. The checks include the renamed function, `IS_PASSING` and `SCORE_CLASS`. Fresh replay passed structural equivalence modulo the single authorized name, binding equivalence and behavioral equivalence.

Cycle 25's historical revision-8 rendered snapshot has indentation-only drift from the corrected replay helper. The historical snapshot was not changed. Cycle 26 classified the difference as whitespace-only and compared semantic projections and execution behavior.

## Policy and failure controls

The host-owned contract authorizes one rename of portable handle `clamp_score.function`, requiring old spelling `CLAMP_SCORE` and new spelling `NORMALIZE_SCORE` at revision 8. The full candidate is checked against the baseline modulo only the target symbol name, and its token-level change set must contain only the declaration and bound references. The transaction kernel performs revision checks and commit revalidation.

The production-dispatch preflight rejected unknown and unauthorized handles, unauthorized names, stale revision and mismatched old-name precondition; rejected a duplicate commit and a transport request containing an unknown semantic field; and confirmed preview did not mutate the authoritative Workspace. Direct clone controls verified native collision (`NAME_COLLISION`) and invalid identifier (`INVALID_NAME`) behavior. An inverse-rename test restored canonical source byte-for-byte. These are deterministic host controls, not model actions.

## Presentation and provenance

[`real-agent-01/visual-replay-generic.html`](real-agent-01/visual-replay-generic.html) is the standalone code-first replay. It keeps committed code at revision 8 during preview and advances to revision 9 only on the recorded commit. It highlights the declaration and bound call-site spelling changes and shows the unchanged dependency graph and revision-bound MIR observations. No browser screenshots were captured for this cycle.

The full Pi transcript, lifecycle events, gateway journal, tool schemas, identity audit, host validation, visual frames, and constructive stream are preserved under `real-agent-01/`. Deterministic production-path evidence is under `deterministic-preflight/`. The transcript is not rewritten to reflect derived reporting corrections.

## Reporting correction

The first derived completion summary mislabeled semantic and host validation as failed because the shared lifecycle classifier looked only for `engines_agree`, while this validator reports `interpreter_jit_agree`. The persisted host validation itself records `mission_complete: true`, interpreter/JIT agreement and passing replay. The classifier now accepts the equivalent field name, with a regression test. The original generated summary is retained as `real-agent-01/summary-pre-correction.json`; `summary.json` and `completion-states.json` are corrected derived summaries. The genuine Pi transcript and gateway history are unchanged. Corrected completion states are: semantic program passed; mission authorized; revision committed; host validation passed; Pi session completed and settled; launcher exited normally.

## Implementation cost and limitations

`Workspace.rename_symbol` needed no changes. The Cycle 26 policy adapter is 335 lines and inherits Cycle 25 reconstruction, normalization, execution, event, and visualization support; it delegates preview/commit to the shared kernel. The runner and deterministic dispatch preflight are 107 and 78 lines. The extension adds a generic four-field rename schema and the dispatch probe adds a rename mode. The implementation introduces no new transaction lifecycle.

The contract is deliberately one target, one old name, one new name. It is a bounded experiment rather than a general rename-policy language. The portable handle `clamp_score.function` retains the original name and can be misleading to a reader; consumers must treat it as an opaque stable handle and consult the current source spelling. No static proof beyond the verified binding graph and finite behavior corpus is claimed.

## Test results and repository state

The focused Cycle 26 rename tests and lifecycle tests passed (14 tests total). The complete Workspace suite then passed **224 tests**. `git diff --check` was clean for all Cycle 26 files; unrelated dirty MPDecimal logs contain their own trailing whitespace and were left untouched. Existing MPDecimal changes and unrelated dirty experiment results are excluded from the Cycle 26 commit. No push is performed.
