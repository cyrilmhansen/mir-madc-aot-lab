# Cycle 20B — End-to-End Semantic Edit Recovery

## Outcome

**Mission passed.** One genuine Pi 1.5.0 / Sushi / Qwen session changed the two authorized `CLAMP_SCORE` literals from 100 to 50 in one transaction. It preserved `IS_PASSING`, its threshold 60, its function identity, and its semantic call binding. The Workspace advanced once, revision 3 → 4.

The agent made five turns and five tool calls: discover, inspect, preview, commit, validate. Preview was accepted; there were no rejected model proposals. The final validation came from both the Pi validation tool and an independent host validation. The agent settled and the launcher exited normally. The original output summary incorrectly classified host validation as failed due to a stale field requirement; see `AUDIT.md` and `real-agent-02/completion-classification-correction.json`. The preserved raw transcript was not changed.

## Deterministic preflight

The actual TypeScript extension handlers and JSONL bridge were invoked without inference, with real tool-call correlation values. The live Pi 1.5 inventory exposed exactly five mission tools and a 4,817-byte schema capture.

- Four genuine, well-formed proposal arguments from Cycle 20 each passed the TypeBox schema and MissionGateway preview in separate reconstructed workspaces.
- Each preview left revision 3 unchanged and changed exactly two numeric literal token IDs in its candidate; interpreter and JIT agreed.
- The original fifth proposal remains rejected by the actual schema because `expression_path` is missing. `expression_path: []` is accepted for assignment-root edits.
- Unknown semantic fields and unknown transport metadata were rejected without mutation.
- A known-good candidate completed preview, atomic commit to revision 4, independent MIR validation, and fresh replay in a disposable workspace.

No deterministic preflight activity is counted as model activity.

## Genuine agent result

The model discovered and inspected the live `CLAMP_SCORE` and `IS_PASSING` functions, then proposed both edits together using one control-path target and one statement handle. Both expected values were 100 and both replacements were 50. The gateway accepted the candidate and reported the dependent caller impact. The commit changed exactly two literal tokens; no statement, function, parameter, or dependency identity was regenerated.

The actual execution corpus was `-100, -1, 0, 1, 49, 50, 51, 59, 60, 80, 99, 100, 101, 200`. Interpreter and JIT both matched `min(50, max(0, X))`; `IS_PASSING` returned 0 throughout the corpus. Its structure and call edge to `CLAMP_SCORE` were unchanged. Fresh-workspace constructive replay passed structural, binding, behavioral, and engine-agreement checks, remapping 11 portable identities.

## Measurements

| Measure | Result |
|---|---:|
| Pi model / version | Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw / 1.5.0 |
| Active tools / schema | 5 / 4,817 bytes |
| Model turns / tool calls | 5 / 5 |
| Preview attempts / accepted | 1 / 1 |
| Commits | 1 (revision 4) |
| Provider input / output / cached input tokens | 8,426 / 1,204 / 17,169 |
| Pi session elapsed | 61.384 s |
| Agent semantic tool processing | 276.538 ms total |
| Independent host validation processing | 139.715 ms |
| Constructive stream | 4,673 bytes |
| Raw Pi JSONL event stream | 448,406 bytes |
| Gateway history | 12,950 bytes |
| Visual frames / HTML | 8 / 33,653 bytes |

Provider token fields are Pi-reported usage, not estimates from bytes. Cached input is shown separately. No schema-token estimate is claimed.

## Artifacts

- [Transport audit](AUDIT.md)
- [No-inference dispatch preflight](dispatch-preflight-04/preflight-summary.json)
- [Genuine Pi session transcript](real-agent-02/pi-session.jsonl)
- [Gateway semantic history](real-agent-02/history.jsonl)
- [Portable constructive stream](real-agent-02/constructive-operations.json)
- [Validation and replay results](real-agent-02/validation.json)
- [Corrected completion-state summary](real-agent-02/summary-corrected.json)
- [Completion-classifier correction note](real-agent-02/completion-classification-correction.json)
- [Offline code-first replay](real-agent-02/visual-replay-generic.html)
- [Normalized presentation events](real-agent-02/visual-events.jsonl)

The live viewer URL was loopback-only and ended with its campaign process. Browser automation inventory was unavailable for a captured screenshot; the generated offline replay is present. No screenshot is claimed.

## Reproduction

Run deterministic gateway/schema tests:

```sh
python3 -m unittest discover -s experiments/basic-workspace/tests -p 'test_cycle20*.py' -v
```

Run the complete Workspace suite:

```sh
python3 -m unittest discover -s experiments/basic-workspace/tests -v
```

The no-inference dispatch probe can be rerun into a new empty output directory:

```sh
python3 experiments/basic-workspace/pi-integration/cycle20b_preflight.py \
  --output experiments/basic-workspace/pi-integration/results/cycle20b-semantic-edit-recovery/dispatch-preflight-new \
  --pi-schema-dir experiments/basic-workspace/pi-integration/results/cycle20b-semantic-edit-recovery/pi-inventory-preflight
```

Regenerate offline HTML from the normalized presentation evidence:

```sh
python3 experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/pi-integration/results/cycle20b-semantic-edit-recovery/real-agent-02
```

The genuine session was launched once with the existing bounded runner and low-thinking configuration:

```sh
python3 experiments/basic-workspace/pi-integration/run_cycle20.py \
  --output experiments/basic-workspace/pi-integration/results/cycle20b-semantic-edit-recovery/real-agent-02 \
  --timeout 240 --open-browser
```

Do not rerun it to reproduce the evidence; inspect `real-agent-02/pi-session.jsonl` instead.

## Limitations

This is one successful agent session, not a reliability estimate. The mission authorizes this specific two-literal edit; it is not a general expression-edit policy. The behavioral result is established for the specified finite corpus plus the Workspace's semantic and replay checks, not as a proof for all real inputs. The raw journal contains the original inaccurate completion-classifier event; the correction is explicit and separately recorded. No browser screenshot was captured.
