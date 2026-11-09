# Cycle 30 report — post-extraction maintenance

## Outcome

One genuine Pi 1.5.0 / Sushi session edited the extracted `BASE_SCORE_CLASS` function through the existing numeric-literal maintenance tool. The host gateway accepted one preview and one atomic commit, moving the Workspace from revision 13 to 14. No model proposal was rejected; the model did not receive the target path or statement identities in its mission prompt and discovered the function and edit target through the semantic tools.

All six completion dimensions passed independently:

| Dimension | Result |
|---|---|
| Semantic program | Passed |
| Mission authorization | Authorized |
| Authoritative commit | Revision 14 committed |
| Independent host validation | Passed |
| Pi agent settlement | Completed |
| Launcher process | Exited normally |

The exact proposal and response chronology is in [`real-agent-01/pi-session.jsonl`](real-agent-01/pi-session.jsonl), with the separate Pi lifecycle and gateway records beside it.

## Baseline and retired identities

The 12 authentic Cycle 29 operations replayed from an empty document to revision 13. The first ten operations were matched exactly to Cycle 28's committed stream and revision-11 semantic snapshot; Cycle 29's revision-12 snapshot, revision-13 commit record, host validation and retirement ledger were also checked. The replay produced five functions, six dependency edges and 27 live portable handles. All 27 replay-local Workspace identities differ from the original recording.

`score_class.statement.0` and `score_class.statement.1` remain historical references only. Neither appears in the live alias map, current discovery or current edit targets. The edit-target resolver rejects both retired statement handles, and the replacement-anchor resolver rejects a retired handle without changing revision 13. The revision ledger is in [`identity-state-ledger.json`](identity-state-ledger.json).

## Genuine maintenance result

The agent proposed the authorized typed path targeting the existing `BASE_SCORE_CLASS` comparison and changed its literal from 20 to 25. The preview left the committed source at revision 13. The gateway rechecked the contract and revision at commit and advanced exactly one revision. The canonical edit check preserved the token-ID set and required exactly one changed literal token text; function, parameter, statement and call-binding identities remained unchanged.

Interpreter and JIT each checked all five functions on the 20-input contract corpus. Both engines matched the independent host oracle, and all six dependency edges were unchanged. The only changed function projection is `BASE_SCORE_CLASS`; `SCORE_CLASS` remains structurally unchanged. Its result changes through its existing bound call to the helper: scores 20–24 now classify as 0. The contract corpus included 20, 21 and 24; an additional host recomputation on the fresh replay explicitly checked every value from 20 through 24 plus 25 in [`extended-boundary-checks.json`](extended-boundary-checks.json).

The semantic diff is in [`semantic-diff.json`](semantic-diff.json). The final committed operation is appended to the original 12 operations in [`real-agent-01/constructive-operations.json`](real-agent-01/constructive-operations.json). Fresh replay passed structural, binding, behavior and interpreter/JIT equivalence with 27/27 live identities remapped and both retired handles still unavailable.

## Deterministic production-path preflight

Before inference, the Pi schema capture and the actual extension handler schema were byte-for-byte equivalent as parsed JSON. The five active tools were discover, inspect, preview edit, commit preview and validate. The production TypeScript handler sent genuine-shaped correlation IDs through the JSONL bridge; transport metadata remained outside semantic parameters.

The disposable revision-13 preview was accepted without mutation, then committed at revision 14 and passed both MIR engines and fresh replay. Deterministic denials covered both retired statement targets, wrong function, incorrect original value, stale revision and an extra edit; the unknown semantic field was rejected by the TypeScript schema. Direct host checks confirmed retired replacement anchors are unresolved. A separate regression test changes the mission invariant between preview and commit and confirms reauthorization rejects the commit without mutation. The full evidence is in [`production-bridge-preflight-05/`](production-bridge-preflight-05/).

An earlier local preflight checker had a false negative because it compared tool inventory order; the actual inventory was correct. The checker was corrected to compare membership, and the final preflight passed. This was deterministic harness activity, not model behavior; see [`preflight-checker-correction.json`](preflight-checker-correction.json).

## Measurements

| Measurement | Result |
|---|---:|
| Provider model | `Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw` |
| Model turns / completed assistant messages | 5 / 5 |
| Model tool calls | 5; one each for discover, inspect, preview, commit and validate |
| Rejected proposals / accepted previews / commits | 0 / 1 / 1 |
| Provider-reported input tokens | 18,266 |
| Provider-reported output tokens | 938 |
| Reported cached input tokens (`cacheRead`) | 28,258 |
| Pi process elapsed time | 117,758 ms |
| Gateway tool-processing time | 1,560.58 ms across five agent tools |
| Active Pi schema | 4,817 pretty bytes; 1,890 compact JSON bytes |
| Raw Pi transcript | 648,565 bytes |
| Constructive stream | 16,543 bytes; 13 operations |
| Historical gateway journal | 29,572 bytes |
| Presentation event journal | 38,709 bytes |
| Generic frames / standalone HTML | 138,123 / 96,075 bytes; 12 frames |
| Replay identity remappings | 27; no new or retired identities from Cycle 30 edit |

The reported cache-read count is provider telemetry and is kept separate from input tokens. This is a single feasibility run, not a reliability or performance benchmark.

## Visualization

The offline generic replay is [`real-agent-01/visual-replay-generic.html`](real-agent-01/visual-replay-generic.html). It shows the verified revision-13 source, genuine function discovery, accepted 20→25 preview while the committed source stays at revision 13, revision-14 commit, Pi and host validation observations, and a separately labeled host identity-ledger audit. The final 12-frame view includes one host audit frame appended after the runner's original 11-frame summary; [`presentation-summary.json`](real-agent-01/presentation-summary.json) records this derivation. No agent edits are attributed to deterministic reconstruction or host verification. The browser view stays code-first; lifecycle evidence is not synthesized.

The saved run did not display a false “No Pi event observed” state during its accepted preview, so no lifecycle evidence or status projection was altered to correct that issue.

## Architecture accounting

No Workspace mutation primitive, BASIC feature, mission transaction engine or SemanticTransactionKernel lifecycle was added. The existing numeric-literal operation and shared transaction lifecycle handled both preview and commit.

The Cycle 20 shared maintenance bootstrap needed additional support for replaying the already-existing Cycle 28 IF-condition edit and Cycle 29 block replacement, plus explicit retirement-ledger checks. The host oracle gained an optional cap branch in its existing declarative `score_class_call` form. These are reusable replay/oracle extensions, not a Cycle 30 policy branch. No new transaction lifecycle implementation was introduced.

The shared gateway diff contains 300 added and 32 removed production lines (net +268). It also required a 154-line deterministic production-handler preflight, a 105-line regression file, and a 45-line declarative mission contract. The mission policy itself added no gateway class or Workspace operation. The replay/bootstrap addition is material; future maintenance missions that need another historical operation family should share this replay support rather than copy it into a campaign gateway.

## Validation

- Focused Cycle 30 identity, preview/commit, oracle and replay tests passed.
- Full Workspace suite: **241 passed, 80 subtests passed**.

The finite tests establish the requested corpus behavior and preserved dependencies. They do not prove behavior over all numeric inputs.
