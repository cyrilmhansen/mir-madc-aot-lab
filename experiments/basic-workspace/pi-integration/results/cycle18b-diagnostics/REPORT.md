# Cycle 18B — Pi/Sushi session stall diagnosis

## Finding

The two preserved Cycle 18 sessions ended differently at the semantic and runtime layers, but both ended with an **incomplete Pi assistant response** and no pending tool call. The traces do not prove whether the final wait was slow generation, an upstream provider wait, or a Pi stream/event handling problem. No new model request was made.

| Arm | Last completed tool action | Workspace / host result | Assistant response at cutoff | Gap from last tool result to timeout |
|---|---|---|---|---:|
| Atomic | `workspace_validate_mission` | Revision 5 committed; interpreter/JIT, boundary oracle, and replay passed | Started `2026-11-08T12:17:05.675Z`; 127 `message_update` events afterward; no `message_end`, `turn_end`, `agent_end`, or `agent_settled`; zero pending tools | 15.679 s |
| Incremental | `workspace_begin_function_draft` | Draft opened; zero draft operations; Workspace remained revision 4; no post-commit validation | Started `2026-11-08T12:18:06.048Z`; 1,847 `message_update` events afterward; no `message_end`, `turn_end`, `agent_end`, or `agent_settled`; zero pending tools | 148.221 s |

The timeout timestamps above are the host timeout-record file mtimes (`12:17:21.353Z`, `12:20:34.267Z`), not native process-exit timestamps. The recorded subprocess intervals were 180,007.72 ms and 180,008.11 ms. The atomic run's last completed Pi assistant usage record was 101 input, 69 output, 7,167 cache-read tokens at `12:17:01.576Z`; it predates the final assistant response. The incremental run's last completed usage record was 360 input, 224 output, 2,612 cache-read tokens at `12:17:50.662Z`. Neither session has provider usage for its open final generation. These are previous completed-message records, not final-generation counts.

Full content-free event-order/timing extraction is in [timelines.json](timelines.json). It references, but does not alter, the preserved raw files in [Cycle 18 atomic](../cycle18-composition/arm-a-atomic/) and [Cycle 18 incremental](../cycle18-composition/arm-b-incremental/).

The first Pi prompt-message timestamps are `12:14:21.512Z` (atomic) and `12:17:34.421Z` (incremental). The final assistant message began at the timestamps in the table. In the raw session JSON, tool execution start/end events are ordered, but have no arrival timestamps; their tool-call identifiers contain timestamp-like digits, which this report does not treat as a verified clock. Gateway timing rows provide method and duration correlated by call ID, but no request/response wall time. The old traces also have no Pi process-start timestamp; the reported subprocess duration is the parent wrapper interval.

## What the evidence resolves

- **Waiting for a tool:** ruled out at both cutoffs. Every Pi `tool_execution_start` has a matching end; pending tool count is zero. The last completed actions were the listed validation and draft-start tools.
- **Gateway work:** not the source of the 180-second duration. Total agent gateway processing was 615.743 ms atomic and 4.099 ms incremental. The final incremental gateway call itself took under 1 ms.
- **Useful work followed by a lingering session:** confirmed for atomic. It committed revision 5 and the agent invoked the validation tool, which passed. Pi nevertheless remained active until the external timeout. The host-level post-session validation and replay also passed.
- **Incremental authoring:** no semantic construction was submitted. Draft revision stayed at its initial state and the authoritative Workspace did not change.
- **Normal Pi completion:** absent. No `agent_end` or `agent_settled` was observed; the last assistant message has no `message_end` or `turn_end`.

## What remains unknowable

The old streams do not timestamp individual `message_update` arrivals or Pi tool start/end receipt. Gateway timing logs contain durations and correlation IDs but no wall-clock timestamp. They therefore cannot show whether the final stream kept producing deltas steadily or paused for most of the interval. There is no provider-side request trace, final finish reason, final usage record, native timeout/exit event, or saved process state. Consequently:

- We cannot distinguish slow model generation from a provider/network wait or Pi's stream handling.
- We cannot say that Sushi failed to respond: both streams contain assistant deltas after their last completed tool result, but their arrival cadence was not recorded.
- We cannot determine whether an output budget was exhausted; there is no final response finish reason or usage record.
- We cannot attribute a bug to an event handler or a wrapper waiting for an extra completion condition. The prior launcher used `subprocess.run(..., timeout=180)`, which simply waited for process exit and then timed out.
- The old launcher killed the child through `subprocess.run` timeout handling; exact graceful-shutdown and process-exit times were not captured.

The successful Cycle 17 reference sessions completed with `agent_end`, `agent_settled`, normal exit, and no pending tools (atomic: 5 turns/5 tools, 37.9 s; incremental: 8 turns/8 tools, 56.0 s). That contrast establishes lifecycle differences, not a provider root cause.

## Bounded instrumentation added

`pi_lifecycle.py` now provides a JSONL process runner that keeps the original raw Pi event stream byte-for-byte while writing a compact, separate lifecycle stream. It adds host UTC and monotonic receipt times for each Pi JSON event, event counts, assistant-stream state, tool start/end correlation, latest completed usage metadata, no-progress intervals, timeout, SIGTERM grace, hard kill (if needed), and process exit. It deliberately omits prompt text, message deltas, tool arguments and tool results from the metadata stream. Size and line limits bound collection. The no-progress label says only that no Pi event arrived during the configured interval; it does not identify the provider/model/Pi component responsible.

The runner uses the existing Pi JSON mode; it adds no inference transport. `run_cycle16.py` now uses this runner for any future campaign invocation and sends coarse `working`, `waiting_for_tool`, `no_observable_progress`, `agent_turn_ended`, or `agent_session_completed` status to the existing read-only browser through the Python gateway. It retains the 180-second overall timeout and sends SIGTERM before a bounded hard-kill fallback. It does **not** stop on commit. The browser status and final summary report separate dimensions:

- semantic program correctness;
- mission authorization (`authorized`, `denied`, or not attempted);
- whether an authoritative commit occurred;
- host validation outcome;
- Pi agent-loop completion (`completed`, ended but unsettled, or incomplete/unobserved);
- launcher process outcome (`timed_out`, normal/nonzero exit, etc.).

Thus a correct, committed and host-validated program can coexist with `pi_agent_session: incomplete_or_unobserved` and `launcher_process: timed_out`. A preview/commit does not by itself terminate Pi. No live confirmation was justified by the old evidence, so there was no new inference.

## Reproduction

From the repository root:

```sh
python3 experiments/basic-workspace/pi-integration/diagnose_cycle18.py
python3 -m unittest experiments.basic-workspace.tests.test_pi_lifecycle experiments.basic-workspace.tests.test_pi_gateway -v
python3 -m unittest discover -s experiments/basic-workspace/tests
```

The first command regenerates `timelines.json` from the existing Cycle 18 arm directories. It reads the old raw event streams, gateway timings, summaries, and timeout record mtimes only.

## Recommendation

For the next semantic API experiment, keep the existing 180-second hard bound and use the new event-arrival log first. If a run stalls again, inspect the monotonic intervals between actual `message_update` events and correlate them with tool and gateway boundaries before adjusting the model, prompt, output budget, or timeout. Do not treat a process timeout as a provider incompatibility. Consider a controlled Pi stop only after Pi reports a settled agent and required host validation/replay are complete; that would be recorded as a host-requested stop, not a normal model-generated completion. Cycle 18B did not test this optional stop path.

## Validation outcome

The new deterministic lifecycle and bridge tests cover independent completion-state dimensions, no-progress timeouts, event ordering and duplicate tool boundaries, content-free metadata, timeout shutdown, a settled agent with a lingering timed-out process, read-only lifecycle visualization, and timeout classification after a valid commit. Historical schema regression tests now read the exact captured atomic and incremental tool schemas from small fixtures under `tests/fixtures/pi-cycle18/`; the previous test paths referenced ignored preflight directories that were not present in this checkout. No historical session file was changed.

Validated commands and results:

- `python3 -m py_compile experiments/basic-workspace/pi-integration/run_cycle16.py experiments/basic-workspace/pi-integration/gateway.py experiments/basic-workspace/pi-integration/pi_lifecycle.py experiments/basic-workspace/pi-integration/diagnose_cycle18.py experiments/basic-workspace/scripts/visualization.py`: passed.
- `python3 experiments/basic-workspace/pi-integration/run_cycle16.py --help`: passed.
- `python3 -m unittest discover -s experiments/basic-workspace/tests`: **168 tests passed**.
- New live inference requests: **0**.
