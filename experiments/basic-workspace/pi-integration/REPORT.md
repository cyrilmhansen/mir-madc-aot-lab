# Cycle 16 report — Pi semantic integration

## Outcome

The Pi-to-Python integration worked: Pi 1.5.0 loaded the Sushi/Qwen model, the extension exposed exactly five semantic tools, the real model discovered `AGE_BY_ID`, inspected the revision-4 program, and dispatched eight genuine typed-construction proposals through the Python MissionGateway. The gateway rejected each malformed/unauthorized body without changing the Workspace. The bounded session timed out at 240 seconds before a commit.

**The acceptance criterion was not met.** There is no `IS_ADULT` commit, no post-commit interpreter/JIT result, and no completed fresh-workspace replay for this Pi campaign. Revision remained 4. No scripted substitute was inserted. Existing Cycle 14B success remains intact and was not rerun.

## Real model metrics

Evidence: [`results/real-pi-01/summary.json`](results/real-pi-01/summary.json), `pi-session-observed.jsonl`, `history.jsonl`, `pi-tool-lifecycle.jsonl`, and `visual-events.jsonl`.

| Metric | Pi campaign |
|---|---:|
| Pi / provider model | Pi 1.5.0 / Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw |
| Model turns ending | 5 |
| Tool calls dispatched | 10 |
| Discovery / inspect | 1 / 1 |
| Preview attempts | 8 |
| Accepted previews / commits | 0 / 0 |
| Gateway rejection codes | `MISSION_BODY`: 4; `MISSION_TARGET`: 4 |
| Workspace revision | 4 → 4 |
| Independent validation | Not run; no committed candidate |
| Provider-reported input / output tokens | 4,342 / 8,494 |
| Provider-reported cache-read tokens | 28,844 |
| Inference/process wall time | 240,009 ms; timeout |
| Tool schema bytes | 1,527 |
| Full Pi JSON event stream | 1,120,273 bytes locally; includes thinking events, not committed |
| Sanitized observed event stream | 58,184 bytes |
| Constructive stream | None; nothing committed |
| Python gateway startup / warm bridge RPC | 74.0 ms / median 0.082 ms (p95 0.252 ms; 100 local calls) |

Token and cache numbers are copied from Pi/provider usage events. They are not estimates from bytes. Cache-read is reported separately and is not treated as zero-cost. The request began after a successful RPC model-catalog/tool-inventory preflight; that preflight itself did not test model inference. Actual model tool calls prove the provider accepted this Pi request format.

The loopback bridge measurement is a separate deterministic microbenchmark, not part of Pi's inference time. Pi startup time and browser delivery latency were not independently timed; the 240,009 ms figure includes Pi startup and the full bounded run.

## What happened

The agent made one discovery and one structure-inspection call, then tried eight variants of the typed `body` payload. Four failed the gateway's allowed statement-shape check (`MISSION_BODY`); four failed its result-target check (`MISSION_TARGET`). Every rejection retained base/result revision 4. The tool result was a valid RPC response containing a rejected semantic preview; no preview advanced the authoritative source.

The cause visible in the captured Pi tool schemas is that the `body` property was described as an array whose items have schema `{}`. The model was told which expression concepts existed, but not given the constructor's exact nested request schema or a concrete typed body example. This is an interface description defect. It is not a Pi or Sushi incompatibility. The task requires a constructor schema improvement before a future trial; no repeat was run in this cycle.

The recorded Pi JSON stream includes real tool starts and ends. The live extension journal captured tool starts; semantic rejections were separately emitted by the Python gateway and are present in the event history. This does not duplicate a commit, because no commit happened. It is a small live telemetry gap: the next adapter should verify Pi's extension end-event delivery and/or derive the completed tool lifecycle from the Pi event stream after the session. The shareable Pi event stream removes thinking-channel payloads and replaces the local absolute checkout path with `<repo>`; tool arguments, tool outputs, usage and completion events are retained.

## Live and offline visualization

The gateway and Cycle 15 read-only viewer were started before Pi. During the model session, the browser received the deterministic revision-4 seed, genuine function discovery, and eight proposal-rejection frames. Since there was no accepted preview or commit, the displayed BASIC stayed at revision 4 throughout. The browser did not show a fabricated function insertion.

Offline replay was generated from the same normalized event stream:

- [`visual-replay-generic.html`](results/real-pi-01/visual-replay-generic.html)
- [`visual-frames-generic.json`](results/real-pi-01/visual-frames-generic.json)
- [`visual-replay-screenshot.png`](results/real-pi-01/visual-replay-screenshot.png) — actual Firefox headless capture of the viewer.
- [`visual-events.jsonl`](results/real-pi-01/visual-events.jsonl)

The screenshot shows the revision-4 program and its real existing dependencies. The timeline includes one discovery and eight rejections. The green `COMMITTED` badge is the viewer's label for the displayed authoritative committed snapshot; it does not mean the Pi mission committed. The action panel says the agent has not changed code. This distinction should be more prominent in a future campaign header.

## Deterministic bridge validation

Seven focused tests pass, covering revision-4 seed, discovery, preview without mutation, stale revision, wrong dependency, mission target refusal, unknown method, duplicate Pi events, correlated loopback request/response, disconnect before a complete request, malformed typed body, oversized frame rejection and gateway termination. The complete Workspace suite passes 138 tests (the 131-test baseline plus seven new bridge tests). The Workspace is kept alive in one Python process for the whole agent mission; the gateway lock serializes potentially parallel Pi tools. Pi and gateway processes run with ignored isolated session/config directories.

These controls do not constitute a full OS security sandbox. Pi cannot see shell/file tools through the configured model tool set, but the experiment does not constrain other processes running as the same user.

## Comparison with Cycle 14B Python reference

The preserved Python Mission 3 reference in `results/semantic-replay/longitudinal-01/calibrated-resume-02/summary.json` completed in five turns and five tool calls, with one commit, 19,445 input tokens, 1,660 output tokens, 17,631 cached prompt tokens, and about 38.2 seconds inference. The Pi run also reached five turns but used ten tool calls, achieved no commit, reported 4,342 input and 8,494 output tokens, 28,844 cache-read tokens, and timed out at four minutes.

This is not a controlled performance comparison: Pi and Python use different system prompts, schemas, execution/output limits and orchestration. A single failed Pi trial cannot establish a ranking. In this run Pi adds an extension, an IPC bridge and process setup; it did not reduce agent turns or latency. Its model-visible tool schema is smaller in bytes but incomplete for nested expressions.

## Recommendation

Pi successfully hosted the model and constrained extension tools without changing Workspace contracts. The browser remains a useful independent supervisory view, and the Python MissionGateway remained authoritative. However, the present experiment has not shown a better interactive experience or lower orchestration complexity, and did not complete the requested function composition. Keep Pi as an optional frontend feasibility path. Keep the Python harness as the scientific reference. Before another real model trial, publish a compact, exact recursive schema (or named typed constructors) and include a valid semantic body example in the tool description, then test that schema deterministically against the gateway. Do not infer model success from tool availability alone.

## Reproduction

```sh
python3 experiments/basic-workspace/pi-integration/run_cycle16.py \
  --preflight-only --output experiments/basic-workspace/pi-integration/results/preflight-01
python3 -m unittest experiments.basic-workspace.tests.test_pi_gateway -v
python3 -m unittest discover -s experiments/basic-workspace/tests -v
python3 experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/pi-integration/results/real-pi-01
```

The genuine inference command and full artifacts are documented in [README.md](README.md). Do not repeat it into the preserved run directory.
