# Cycle 20 — Semantic evolution of an existing program

## Outcome

The exact Cycle 19B two-function program was reconstructed and verified before inference. The single genuine Pi/Sushi session **did not commit the requested edit**. It discovered and inspected the program, then submitted five preview-tool calls: four reached the MissionGateway and were rejected as `INVALID_EDIT_REQUEST`; one was rejected by Pi's active schema because the empty `expression_path` field was omitted. No preview was accepted, no commit occurred, and the authoritative Workspace remained at revision 3.

The failure exposed an integration defect, not a failure of the semantic edit grammar or mission policy: Pi appends `toolCallId` to the typed arguments sent over the bridge, while the Cycle 20 gateway demanded exactly the three semantic keys and treated this transport-only field as a semantic request violation. The exact path values and both edits were otherwise valid in four captured calls. This metadata handling was fixed and covered deterministically after preserving the run. **No retry was made**, as required.

The model continued generating until the 240-second launcher timeout. Pi reported no settled/agent-end event; at timeout there was no pending tool call. The launcher sent SIGTERM and Pi exited 143. Thus the program baseline reconstruction is correct, but the requested semantic mission is not complete and the agent session did not settle normally.

## Baseline reconstruction and semantic edit audit

`cycle20_gateway.py` replays the original two Cycle 19B committed constructor operations into a fresh empty Workspace. It checks the revision-2 normalized snapshot and fingerprint before replaying the original IS_PASSING constructor, then verifies revision-3 normalized structure, function bindings, and recorded MIR results. This passed: revision 3, two original operations, 11 portable identities remapped, and the existing `IS_PASSING → CLAMP_SCORE` edge preserved.

The original Workspace API can replace assignment expressions but cannot directly edit a comparison literal nested under an IF. Cycle 20 adds the narrow `edit_numeric_literal_at_path` transaction operation. It identifies a comparison operand by function identity plus a verified control-flow path, or an assignment RHS by stable statement identity. Literal nodes do not have semantic IDs; both original token IDs are preserved while the token text changes. IF blocks do not have independent statement IDs in this model. `AUDIT.md` records the supported paths and identity distinctions.

The gateway authorizes a candidate only when exactly the two inspected cap-100 targets change to the same permitted value, the complete IS_PASSING projection remains unchanged, the semantic dependency edge remains bound, and candidate MIR interpreter/JIT behavior matches the finite preview corpus. Commit rechecks the same candidate and revision in one Workspace transaction.

## Pi preflight and genuine session

The preflight passed with Pi 1.5.0 and `Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw`. Pi's RPC model inventory contained the requested Sushi model, the five active tools exactly matched the allowlist, and the actual serialized schema was 4,817 bytes. The `edits` array is bounded to exactly two items and both target variants are typed. The RPC inventory check did not call the model endpoint for inference.

`preflight-01` records a baseline-readiness metadata bug: the runner tried to query historical revision 2 after replay had advanced the document to revision 3. The checkpoint had already been verified; the runner now retains and reports its verified fingerprint. `preflight-02` records the next pre-inference harness failure: the shared handler expected gateway timing/flush hooks absent from the Cycle 20 service. Those hooks were added. `preflight-03` then passed completely. The real run's preview calls exposed the separate `toolCallId` semantic-key defect described above. The fourth gateway request also included the required empty `expression_path` and was still rejected by the same gateway defect. One fifth preview call omitted that required field and Pi rejected it before dispatch.

| Metric | Observed |
|---|---:|
| Model turns | 7 started; the seventh was pending at timeout |
| Semantic tool calls | 7 total: discovery 1, inspection 1, preview 5 |
| Gateway preview rejections | 4 (`INVALID_EDIT_REQUEST`) |
| Pi schema rejections | 1 (missing `edits[1].target.expression_path`) |
| Accepted previews / commits | 0 / 0 |
| Workspace revision | 3, unchanged |
| Completed assistant usage records | 6; final request was pending |
| Pi-reported input / output / cache-read tokens | 3,562 / 3,752 / 20,084 |
| Total reported tokens across completed messages | 27,398 |
| Inference/session wall time | 240,066 ms before timeout |
| Gateway tool processing | 1.246 ms total across the seven semantic gateway calls (`gateway-tool-timings.jsonl`; 3.775 ms including observer/status calls) |
| Active tool schema | 4,817 bytes |

Usage is summed from completed assistant `message_end` records. Streaming delta events repeat running counters and were not summed. No token count is attributed to the pending final request.

## Validation, controls, and replay

The pre-inference baseline gate passed. Deterministic unit tests verify the candidate semantics in both MIR engines for inputs `-100, -1, 0, 1, 49, 50, 51, 59, 60, 80, 99, 100, 101, 200`; IS_PASSING then returns zero across that corpus. They also verify impact reporting, stable function/parameter/statement identities, preserved token identities, atomic two-literal commit, a fresh-workspace constructive replay, 11 replay identity remappings, rejection controls and rollback.

These are deterministic tests only. Because this real session never obtained an accepted preview, no Cycle 20 candidate was committed, no candidate host validation was performed, and there is no completed Cycle 20 edit metafile to replay. The baseline's existing validation remains historical evidence, not post-edit validation.

## Visualization and provenance

The standalone report at `real-agent-01/visual-replay-generic.html` is generated from the baseline snapshot, actual Pi discovery/inspection events, the four MissionGateway rejections, the actual Pi schema rejection, and a host lifecycle timeout marker derived from the recorded process-exit event. It shows revision 3 throughout; no proposed or uncommitted text is displayed as committed BASIC. The original Pi JSONL and gateway history are preserved. The timeout marker is host provenance, not a fabricated agent action.

`real-agent-01/attempt-analysis.json` maps the actual model-proposed edits to the inspected semantic paths and records that no candidate was previewed or committed. It is an analysis of the preserved tool calls, not a constructive operation stream.

## Reproduction

From repository root:

```sh
python3 experiments/basic-workspace/pi-integration/run_cycle20.py \
  --preflight-only \
  --output experiments/basic-workspace/pi-integration/results/cycle20-semantic-evolution/preflight-03
python3 experiments/basic-workspace/pi-integration/finalize_cycle20_evidence.py \
  experiments/basic-workspace/pi-integration/results/cycle20-semantic-evolution/real-agent-01
python3 -m unittest discover -s experiments/basic-workspace/tests -v
```

The genuine inference command was the single bounded invocation:

```sh
python3 experiments/basic-workspace/pi-integration/run_cycle20.py \
  --output experiments/basic-workspace/pi-integration/results/cycle20-semantic-evolution/real-agent-01 \
  --timeout 240
```

To inspect the viewer, open `real-agent-01/visual-replay-generic.html` in a browser. To regenerate from preserved events, run `python3 experiments/basic-workspace/scripts/basic-visual.py replay experiments/basic-workspace/pi-integration/results/cycle20-semantic-evolution/real-agent-01`.

## Regression and limits

The full Workspace suite passes **187 tests**. Cycle 20 adds eight tests to the 179-test Cycle 19B baseline. Targeted Cycle 20 tests pass **8 tests**. The real session does not satisfy Cycle 20 acceptance because the gateway metadata defect blocked every semantically valid preview and this cycle explicitly permits no retry. The narrow fix is now covered by a transport-metadata test; its use by a genuine model session remains unverified.

No source-text replacement, host-authored substitute, second model session, or push was performed. The provider's cached-token figure is reported as supplied by Pi, not interpreted as proof of any particular server-side caching implementation.
