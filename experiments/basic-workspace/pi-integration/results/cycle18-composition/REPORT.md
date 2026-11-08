# Cycle 18 — Composable semantic API under realistic complexity

## Result

This was one pre-registered, bounded A/B feasibility run with Pi 1.5.0 and the same configured Sushi model. The atomic arm completed the semantic task and host validation, although the Pi process reached its 180-second timeout after committing and requesting validation. The incremental arm discovered the functions and began a temporary draft, then timed out before submitting any draft operations. No retry was made and no scripted construction was substituted for either agent.

The result supports the atomic constructor for this mission's practical completion. It does **not** establish that atomic construction is generally more reliable. The incremental representation had a smaller tool schema, but this agent run did not reach expression composition, so it provides no direct evidence about model usability of the graph representation.

## Experimental controls

The pre-registration is [pre-registration.json](pre-registration.json). Each arm started from an independent revision-4 Workspace with AGE_BY_ID, IS_SENIOR, and ages 25/55/53 for IDs 101/205/900. The requested model and Pi settings, prompt task, timeout, no-retry rule, validation criteria and output directories were fixed before inference.

Three dimensions were recorded independently:

| Dimension | Atomic | Incremental |
|---|---|---|
| Semantic representation | Nested typed expression/statement tree | Flat typed graph with draft-local references |
| Model interaction granularity | 6 observed tool calls, including 1 schema-rejected call | 3 observed tool calls; no call contained draft operations |
| Workspace commit granularity | One atomic Workspace transaction | One atomic Workspace transaction (not reached) |

The incremental arm opened draft revision 0 at Workspace revision 4. Its draft operation count remained zero. An operation batch would still have been one model tool call; no batch occurred here.

## Schema and authoring grammar

The exact active tool schemas are preserved under each arm's `tool-schemas.json`, with model/tool inventory evidence in `pi-rpc-preflight.json`. The atomic arm exposed five semantic tools and a 19,792-byte schema. The incremental arm exposed eight tools and a 9,477-byte schema, 52.1% fewer bytes (10,315 bytes smaller). A crude bytes/4 estimate is 4,948 versus 2,369 tokens; it is only an estimate and is not provider token accounting.

The measured atomic schema contains 10 `anyOf` nodes and 20 alternatives; the draft schema contains one 7-branch operation union. These are measured schema facts, not a prediction of provider tokenization or a complete theoretical growth curve. Atomic nested syntax is bounded to numeric expressions, calls with atom arguments, one binary layer in conditions, result assignments, and IF blocks. Draft syntax uses flat typed operations and explicit references, and accepts up to 32 operations per batch. The mission uses only existing BASIC operations; no language or MIR features were added.

Names, parameter names and function handles are general strings in the TypeBox schemas; the schemas do not hard-code AGE_BY_ID or ID. Deterministic tests prove the schema accepts another portable handle, while the gateway checks that a handle resolves to a discovered numeric function, validates its arity, and applies the mission's one-callee restriction. A separate narrow test mission authorizes IS_SENIOR as a callee through the same grammar. The current AGE_CATEGORY mission correctly denies that call.

## Genuine model activity and outcomes

| Measure | Atomic | Incremental |
|---|---:|---:|
| Model turns | 5 | 3 |
| Pi tool calls | 6 | 3 |
| Calls with draft operations | 0 | 0 |
| Individual semantic draft operations | n/a; one constructor proposal | 0 |
| Invalid Pi tool requests | 1 schema rejection | 0 |
| Mission policy rejections | 0 | 0 |
| Preview attempts | 2 (one schema-invalid, one accepted) | 0 |
| Accepted previews | 1 | 0 |
| Commits | 1 | 0 |
| Workspace after session | Revision 5 | Revision 4 |
| Pi runtime | 180-second timeout after validation | 180-second timeout before construction |
| Campaign wall interval (seed setup file to summary file mtimes) | 180,593 ms | 180,290 ms |
| Gateway processing time | 615.743 ms | 4.099 ms |
| Tool schema bytes | 19,792 | 9,477 |
| Pi event-stream bytes | 607,323 | 562,989 |
| Provider input tokens | 8,688 | 5,780 |
| Provider output tokens | 5,986 | 612 |
| Reported cache-read tokens | 43,386 | 9,906 |
| Reported total tokens | 58,060 | 16,298 |

Token fields are the usage values Pi recorded; cache-read is shown separately and is not subtracted from input. Pi did not expose complete serialized HTTP request-context bytes, so they are unavailable. The event-stream byte count is not a substitute for request bytes. Tool schema bytes are the captured model-visible schemas. Both arms used low thinking, the same requested model and a 180-second bound, with no sampling override. Campaign wall intervals are filesystem-mtime deltas from deterministic seed setup to summary creation and include startup, RPC preflight, inference, validation and report generation.

### Atomic arm

The model discovered AGE_BY_ID and inspected the program. Its first constructor proposal put a nested IF in an ELSE branch that the bounded schema does not support; Pi rejected it before the Workspace gateway. The model then submitted a supported sequential-IF implementation. The gateway accepted the preview, committed revision 5, and the agent requested validation.

The resulting behavior uses the actual bound call `AGE_BY_ID(ID)`: default result 2, then assign 1 for age `<=49`, 0 for age `<=17`, and -1 for age `=-1`. The first three assignments encode the requested categories; the final check preserves missing-ID behavior. The model process timed out before it returned a completed final response, but the semantic operation itself had committed and the host validation tool returned success. The runner therefore records both `timed_out: true` and a validated mission outcome; these facts are not collapsed into a normal Pi exit.

Independent interpreter and JIT results matched for IDs 101, 205, 900, 999 and 2. Isolated fixtures passed ages 0, 17, 18, 49, 50 and 130, including missing IDs. AGE_BY_ID/IS_SENIOR and existing data remained unchanged. The dependency edge to AGE_BY_ID was present. Fresh-workspace replay passed structural and behavioral equivalence, with 26 identity remappings. The constructive stream is 9,434 bytes.

### Incremental arm

The model discovered AGE_BY_ID, inspected the program, and opened an AGE_CATEGORY draft at base revision 4. It submitted no operation, did not inspect the incomplete draft, and made no preview or commit before its timeout. The canonical Workspace remained revision 4. There are no incremental behavioral or replay results to claim. The deterministic draft test separately submitted a 19-operation graph as one batch, verified intermediate draft revisions and handle reuse, and passed the same host boundary/replay checks; this is scripted protocol evidence, not model activity.

## Deterministic validation

The host-owned deterministic fixture passed schema validation, generic function-handle resolution, discovered-signature checks, policy separation, atomic preview/commit, and the full category oracle for both MIR engines. Its incremental reference graph used 19 semantic operations in one batch and referenced the existing `age` expression handle in three later comparisons; draft revisions advanced to 19 while the Workspace stayed at revision 4 until the single commit. The atomic real session passed the same oracle and replay. The incremental real session did not produce a program to validate.

The invalid atomic proposal is visible in the offline replay as a rejection frame derived from the genuine Pi `tool_execution_end` schema error. The adapter is [adapt_schema_failures.py](../../adapt_schema_failures.py); raw Pi events and gateway history remain preserved. This error occurred in Pi's schema validator before the tool reached the Python gateway, so that rejection was not visible live in the browser; the post-run adapter restores it for accurate offline review. The viewers are generated from normalized presentation events, not from imagined keystrokes. The authorized commit is the only event advancing the shown committed source. The incremental viewer shows an empty draft start and timeout, not a fictional function body.

The raw gateway `session_completed` rows have a stale `phase` string (`cycle17-...`) from the reused runner, while their `mission_id` correctly identifies Cycle 18. Raw rows are preserved unchanged; the normalized visual campaign and reports use the actual Cycle 18 mission ID. This is a metadata-label defect, not a change to tool actions or program state.

## Measurements and artifacts

| Artifact | Atomic | Incremental |
|---|---:|---:|
| Historical gateway journal | 68,642 bytes | 46,899 bytes |
| Draft operation history | none | 246 bytes (draft start only) |
| Normalized visual events | 19,758 bytes after one observed schema-rejection adapter event | 2,451 bytes |
| Generated visual frames | 47,208 bytes | 9,475 bytes |
| Offline code-first replay | 49,808 bytes | 28,164 bytes |
| Visual event count | 8 | 4 |
| Replay identity remappings | 26 | not applicable |

The atomic HTML is `arm-a-atomic/visual-replay-generic.html`; the incremental HTML is `arm-b-incremental/visual-replay-generic.html`. Each run also contains the actual `pi-session.jsonl`, Pi lifecycle events, gateway history, schema capture, summary and timeout record. The live browser server was available during each run at the loopback URL preserved in `viewer-url.txt`; the completed HTML files open offline.

## Conclusions

1. **Is the incremental API simpler for the model?** Not established. Its schema is smaller, but the model did not compose any graph nodes in this trial.
2. **Did it require more interactions but fewer malformed proposals?** It made fewer calls only because it stopped before construction. This is not a valid efficiency comparison. The atomic model made one schema-invalid nested proposal and repaired it.
3. **Is its schema more compact/extensible?** It is materially smaller in this captured interface, and its flat union grows by operation kinds rather than recursively repeating nested shapes. Reusability was verified deterministically.
4. **Did it provide more useful intermediate validation?** Deterministic draft frames show each operation and reused handle; the real model produced none, so agent-facing value is untested.
5. **Did it improve operator understanding?** The genuine atomic rejection, accepted preview, commit, validation and replay are visible. Incremental view accurately shows only draft start and timeout.
6. **Is temporary draft state justified?** This trial does not justify that added state on completion efficiency grounds. It remains useful for local diagnostics and intermediate visualization, but needs a successful model interaction study.
7. **Should both granularities remain available?** Retain both as distinct options for now. Prefer the atomic path for bounded constructors; use incremental drafting where larger structures need reuse and local feedback, pending a successful real-model trial.

This single pair is a feasibility observation only. The long timeout in both arms and the incremental arm's lack of construction dominate the result. It does not establish general model reliability, token efficiency, or superiority over source editing.
