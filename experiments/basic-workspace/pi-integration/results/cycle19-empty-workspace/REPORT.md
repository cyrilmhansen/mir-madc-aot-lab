# Cycle 19 — Agent-built program from an empty Workspace

## Result

This is a **partial success**. A genuine Pi/Sushi agent built `CLAMP_SCORE(X)` in an empty document, committed it atomically, and passed independent MIR interpreter/JIT checks for all ten inputs. A fresh-workspace replay reconstructed that committed function and remapped six semantic identities.

The second genuine Pi session discovered `CLAMP_SCORE` and formed the correct typed call expression for `IS_PASSING`, but the initial gateway contract required a duplicate top-level `callee_handle`. Four previews were denied before mutation. Pi was still streaming when its 240-second bound expired. Mission 2 did not commit, so there is no two-function program, complete constructive stream, or IS_PASSING behavioral result. The authoritative Workspace remained at revision 2 with only `CLAMP_SCORE`.

The implementation defect was independently reproduced from the actual tool arguments and corrected in the gateway and tool description. The corrected gateway accepts the portable handle carried by the typed call node, while still requiring prior discovery and checking that the bound call targets the mission-authorized function. Deterministic tests cover this corrected path. **The corrected path was not sent to a model in this cycle.** No retry or scripted fallback was performed.

## Genuine model sessions

Both sessions used Pi 1.5.0 and the locally configured Sushi model `Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw`. The no-inference RPC preflight confirmed the model inventory and exactly five active semantic tools. The captured constructor schema was 19,767 bytes. No credentials or provider endpoint were copied into campaign artifacts.

The first local-only preflight (`preflight-01`) did not receive the loopback gateway address in the Pi child environment, so its extension could not report tool inventory. It made no model request. The launcher was corrected and two subsequent no-inference preflights succeeded; the post-correction schema capture is in `preflight-corrected/`.

| Measure | Mission 1: CLAMP_SCORE | Mission 2: IS_PASSING |
|---|---:|---:|
| Pi turns | 5 | 5 |
| Tool calls | 5 | 6 |
| Discover / inspect | 1 / 1 | 1 / 1 |
| Preview attempts | 1 accepted | 4 rejected |
| Commit / validation tool calls | 1 / 1 | 0 / 0 |
| Host commit | revision 2 | none; stayed at revision 2 |
| Provider input tokens | 8,512 | 4,432 |
| Provider output tokens | 3,352 | 9,940 |
| Reported cached input tokens | 31,834 | 48,394 |
| Pi event stream bytes | 387,349 | 1,336,260 |
| Process elapsed | 77.0 s | 240.1 s, timed out |
| Pi agent settled | yes | no; assistant stream still open |

Provider values are the usage metadata Pi received. Cached tokens are shown separately and are not added to the input-token count. Mission 2's final assistant message had no observed message-end or agent-settled event. There were no pending tool calls at timeout. This is a launcher timeout during ongoing model streaming, not a gateway wait: each rejected preview took approximately 1 ms. The final streamed usage record was 1,412 output tokens (including 1,186 reasoning tokens) for that in-progress message; it was not a completed response.

### Why Mission 2 stopped

The genuine call node initially used `clamp_score.function`, which was the discovered portable handle. The gateway additionally required `callee_handle` at the root of the preview request. The model then tried the transient symbol UUID as the expression handle, and later returned to the correct portable handle, but never added the undocumented duplicate root field. All four previews returned `MISSION_DEPENDENCY_FORBIDDEN`; every response reported revision 2 unchanged. No commit was pending and no program mutation occurred.

The gateway now derives the authorization handle from the call expression if the optional root field is absent. It still rejects calls to an unknown or different function and requires that the permitted handle was discovered. The model-visible tool description now says that the root field is optional and normally omitted. This is a post-trial harness correction, not evidence that the model used the corrected interface.

## Mission 1 correctness and replay

Independent host-owned expected values were checked on both MIR engines:

| X | Expected | Interpreter | JIT |
|---:|---:|---:|---:|
| -100 | 0 | 0 | 0 |
| -1 | 0 | 0 | 0 |
| 0 | 0 | 0 | 0 |
| 1 | 1 | 1 | 1 |
| 59 | 59 | 59 | 59 |
| 60 | 60 | 60 | 60 |
| 99 | 99 | 99 | 99 |
| 100 | 100 | 100 | 100 |
| 101 | 100 | 100 | 100 |
| 200 | 100 | 100 | 100 |

Interpreter/JIT agreement, the independent oracle, and fresh-workspace structural and behavioral replay all passed at revision 2. The partial constructive operation is preserved as `real-agent-01/mission-1-constructive-operations-partial.json`. It contains only the committed first function. It is not a completed two-function metafile.

The original `mission-1-completion-states.json` says host validation failed due to a result-shape mismatch: the shared Cycle 18B classifier expected a `boundary_oracle` field that the first Cycle 19 validator response omitted. The underlying `mission-1-host-validation.json` records a successful independent oracle and replay. Cycle 19 now emits the classifier field, and a regression test verifies correct classification. `mission-1-completion-classification-correction.json` records this post-hoc classification repair without altering the original Pi session or Workspace evidence.

Mission 2 has no committed candidate and therefore no independent execution result. It is not counted as semantically validated or authorized.

## Visualization and artifacts

The live loopback viewer displayed the empty document, discovery, preview-only candidates, the committed revision 2 snapshot, validation, checkpoint, context reset, and four rejected Mission 2 proposals. The offline replay was generated from these observed events and committed snapshots. It shows `CLAMP_SCORE` as committed and never advances the code listing for the denied proposals.

- Offline replay: `real-agent-01/visual-replay-generic.html`
- Generic frames: `real-agent-01/visual-frames-generic.json` (19 frames)
- Visual event stream: `real-agent-01/visual-events.jsonl`
- Pi event streams: `real-agent-01/mission-{1,2}-pi-session.jsonl`
- Lifecycle streams: `real-agent-01/mission-{1,2}-pi-lifecycle.jsonl`
- Contracts: `real-agent-01/MISSION-{1,2}.json`
- Checkpoint: `real-agent-01/mission-2-recovery-checkpoint.json` (2,099 bytes)
- Active tool schemas: `real-agent-01/tool-schemas.json` (19,767 bytes)
- Campaign summary: `real-agent-01/summary.json`

The live server shut down at campaign exit; the HTML replay is standalone. No screenshot was captured.

## Deterministic validation

Seven new tests cover empty-document construction, M1 policy, stale revisions, checkpoint validation, discovery and dependency enforcement, atomic rollback, uncommitted visualization, one-function replay, and the Cycle 19 completion-state shape. The complete suite passed **175 tests and 51 subtests**.

```sh
python3 -m py_compile \
  experiments/basic-workspace/pi-integration/cycle19_gateway.py \
  experiments/basic-workspace/pi-integration/run_cycle19.py \
  experiments/basic-workspace/tests/test_cycle19_empty_workspace.py

python3 - <<'PY'
import os, pathlib, subprocess, tempfile
root = pathlib.Path.cwd()
with tempfile.TemporaryDirectory(prefix="atlas-cycle19-tests-", dir="/var/tmp") as base:
    env = os.environ.copy()
    env["PYTHONPATH"] = (f"{root}/experiments/basic-workspace:"
                         f"{root}/experiments/basic-workspace/pi-integration")
    raise SystemExit(subprocess.call([
        "pytest", "-q", f"--basetemp={base}/pytest",
        "experiments/basic-workspace/tests"], env=env))
PY
```

The run's preflight and single bounded two-session command are recorded in `reproduction.sh`. The provider config is local and ignored; the script does not embed a URL or credential.

## Completion dimensions

| Dimension | Mission 1 | Mission 2 |
|---|---|---|
| Semantic program correctness | Passed | Not validated |
| Mission authorization | Authorized | Four proposals denied |
| Authoritative commit | Revision 2 | None |
| Host validation | Passed | Not run |
| Pi agent settlement | Completed | Incomplete; timeout during assistant stream |
| Launcher process | Exited normally | Timed out at 240 s |

## Limitations and next step

The requested complete acceptance was **not achieved**. This run proves that an agent can start from no program state and construct and validate a typed function. It does not prove successful multi-function composition from empty state. Mission 2's failure was caused by the initial host/tool contract duplication, not by a MIR, projection, or language limitation. The corrected gateway path passes deterministic tests. A later, explicitly identified trial would be needed to test that corrected contract with a genuine model.

The gateway uses two narrow, fixed mission contracts rather than a general policy language. The first mission's workspace is empty; the second mission's invariant baseline is captured after the first commit. No hidden seed or host-inserted code was present.
