# Cycle 19B — Recovery and continuation from verified semantic state

## Outcome

The resumed workflow completed the two-function program without repeating the successful Mission 1 inference.

The Cycle 19 Mission 1 constructor operation was replayed into a new empty Workspace. The result was revision 2, with normalized semantics identical to the original committed snapshot, the same revision-bound fingerprint, and the same MIR interpreter/JIT observations. The new Workspace received fresh opaque IDs; portable handles were resolved again from the replayed operation.

A new Pi conversation received the verified checkpoint and Mission 2 instructions, but no earlier model messages or failed-session transcript. The genuine Sushi/Qwen agent discovered `CLAMP_SCORE`, inspected its signature, proposed `IS_PASSING` with the discovered portable handle inside the call expression, received an accepted preview, committed revision 3, and requested MIR validation. The host independently validated and replayed the complete program.

The original Cycle 19 Mission 2 failure remains preserved in the Cycle 19 directory and appears in the combined visual timeline as historical agent activity. Cycle 19B is a recovery-and-continuation success; it does not change the original run's outcome.

## Mission 1 reconstruction gate

The host applied exactly the operation in `real-agent-01/mission-1-constructive-operations-partial.json` to a fresh revision-1 empty document. The operation arguments also match the proposal and commit record in the original history.

| Check | Result |
|---|---|
| New document starts empty | Passed |
| Replayed revision | 2 |
| Normalized snapshot matches original transaction commit | Passed |
| Fingerprint matches original checkpoint | `ffa4517205844cf9f4bd18fea35ab99ff6b8f89fcd3aff52eeecaec1f1a1f07c` |
| Recorded interpreter/JIT results match reconstruction | Passed |
| New Workspace document UUID reused from checkpoint | No |
| Portable identities re-resolved | 6 |

The fingerprint comparison is semantic and revision-bound. It does not reuse the original document identity. The original revision-2 code and events are retained as historical visual evidence, with a separate event explicitly marking host reconstruction.

## Corrected dependency contract

Before inference, deterministic tests replayed the original denied Mission 2 proposal from the Cycle 19 Pi trace. Its call expression already contained `function_handle: "clamp_score.function"`, and it had no duplicate top-level `callee_handle`. The corrected gateway accepted its preview while leaving canonical tokens and revision 2 unchanged.

The gateway also verifies that the permitted handle was discovered in the active revision, resolves to a current numeric function, has a compatible argument count, and is the dependency authorized by Mission 2. Tests reject undiscovered, wrong, and wrong-arity references; stale requests and rejected previews do not mutate the Workspace.

Pi 1.5.0's actual active tool inventory contained exactly the five semantic tools. The captured schema was 19,767 bytes and exposed the typed function body with the optional top-level callee field. No source editing, shell, or filesystem tools were active.

## Genuine Mission 2 session

| Measure | Result |
|---|---:|
| Model | Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw |
| Pi turns | 5 |
| Tool calls | 5 |
| Discovery / inspection | 1 / 1 |
| Preview attempts | 1 accepted, 0 rejected |
| Commit | One atomic commit, revision 3 |
| Provider input tokens | 15,538 |
| Provider output tokens | 2,222 |
| Reported cached input tokens | 31,858 |
| Provider total as reported by Pi | 49,618 |
| Pi process elapsed | 74.44 s |
| Gateway tool processing | 99.979 ms total |
| Pi agent settled | Yes |
| Launcher exit | Normal, code 0 |

Cached-token accounting is reported separately from input tokens. These figures are from one session and are not a controlled performance comparison with the failed original session.

## Independent program validation

The host executed both functions through the MIR interpreter and JIT for the full corpus. Both engines agreed and matched the independent oracle.

| X | CLAMP_SCORE(X) | IS_PASSING(X) |
|---:|---:|---:|
| -100 | 0 | 0 |
| -1 | 0 | 0 |
| 0 | 0 | 0 |
| 1 | 1 | 0 |
| 59 | 59 | 0 |
| 60 | 60 | 1 |
| 99 | 99 | 1 |
| 100 | 100 | 1 |
| 101 | 100 | 1 |
| 200 | 100 | 1 |

The normalized `CLAMP_SCORE` projection remained unchanged. `IS_PASSING` contains a bound call to the discovered portable handle `clamp_score.function`; the runtime binding resolves to the reconstructed function identity.

The complete constructive stream contains the original genuine Mission 1 operation followed by the new Mission 2 operation. Fresh-workspace replay passed structural, binding, behavioral, and interpreter/JIT equivalence checks with 11 identities remapped. [full-replay-identity-mapping.json](real-agent-02/full-replay-identity-mapping.json) records each original committed opaque ID, its portable handle, and the fresh replay ID. `equivalence.json` contains the same mapping alongside the validation result.

## Visualization and provenance

The 30-frame combined viewer begins with the original empty Workspace, shows the original genuine Mission 1 construction and commit, includes the original Cycle 19 Mission 2 denials, then marks checkpoint verification and deterministic reconstruction as host actions. It continues with Cycle 19B discovery, preview, revision-3 commit, host validation, and complete replay. Preview and historical denials do not advance committed code.

- Offline HTML: `real-agent-02/visual-replay-generic.html`
- Frames: `real-agent-02/visual-frames-generic.json`
- Normalized events: `real-agent-02/visual-events.jsonl`
- New genuine Pi session: `real-agent-02/mission-2-pi-session.jsonl`
- Lifecycle observations: `real-agent-02/mission-2-pi-lifecycle.jsonl`
- Complete constructive stream: `real-agent-02/constructive-operations.json` (3,842 bytes)
- Full replay identity map: `real-agent-02/full-replay-identity-mapping.json` (11 handles, all remapped)
- Recovery checkpoint supplied to the fresh session: `real-agent-02/mission-2-recovery-checkpoint.json` (2,099 bytes)
- Summary: `real-agent-02/summary.json`

The live loopback viewer was started before the model session. The standalone HTML works after the live process exits. No screenshot was captured.

The first offline render rejected a host reconstruction event's span label. The event was corrected to use the renderer's verified function-boundary mapping, and the final 30-frame HTML was regenerated. The initial diagnostic is retained in `visual-replay-error.txt`; the successful report is `visual-replay-generic.html`.

## Tests and reproduction

The complete Workspace suite passed **179 tests and 51 subtests** after the Cycle 19B changes.

```sh
python3 -m py_compile \
  experiments/basic-workspace/pi-integration/cycle19_gateway.py \
  experiments/basic-workspace/pi-integration/run_cycle19b.py \
  experiments/basic-workspace/tests/test_cycle19_empty_workspace.py

python3 - <<'PY'
import os, pathlib, subprocess, tempfile
root = pathlib.Path.cwd()
with tempfile.TemporaryDirectory(prefix="atlas-cycle19b-tests-", dir="/var/tmp") as base:
    env = os.environ.copy()
    env["PYTHONPATH"] = (f"{root}/experiments/basic-workspace:"
                         f"{root}/experiments/basic-workspace/pi-integration")
    raise SystemExit(subprocess.call([
        "pytest", "-q", f"--basetemp={base}/pytest",
        "experiments/basic-workspace/tests"], env=env))
PY

python3 experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/pi-integration/results/cycle19b-recovery/real-agent-02
```

The genuine run command, using a fresh output directory and the operator's ignored local Pi configuration, is recorded in `reproduce.sh`. It performs one bounded Mission 2 session with no retry.

## Completion states

Semantic correctness, mission authorization, atomic commit, host validation, Pi settlement, and launcher exit all passed. The original Cycle 19 rejected session remains a separate historical record and is not relabeled as successful.
