# Cycle 24 — Multi-dependency construction and change propagation

## Outcome

Both genuine Pi/Sushi missions succeeded. Starting from the authentic Cycle 21 revision-5 stream, the first session created `SCORE_CLASS(X)` with semantic calls to both existing functions and committed revision 6. A fresh Pi conversation then changed the `IS_PASSING` threshold from 40 to 45 and committed revision 7. The existing `SCORE_CLASS` source and its bindings remained unchanged; its runtime result changed through the call graph.

The interpreter, JIT, host-owned oracles and fresh-workspace constructive replay passed for both missions. No source-text replacement, BASIC reparse or new MIR transaction mechanism was used.

## Verified baseline

The original Cycle 21 constructive stream was replayed by the host into an empty Workspace. It produced revision 5, the two expected functions, the `IS_PASSING → CLAMP_SCORE` binding, 11 remapped portable identities, and MIR interpreter/JIT results matching the independent cap-50 / threshold-40 oracle. See [baseline verification](cycle21-baseline-host-verification.json) and the preserved source stream under `../cycle21-reusable-maintenance/real-agent-01/`.

The baseline has cap 50 and threshold 40. Its existing code and stream were not replaced or edited.

## Mission 1 — Add `SCORE_CLASS(X)`

The real model discovered both callable functions and constructed a numeric function using sequential IF statements. Its committed function uses `CLAMP_SCORE(X)` to distinguish values below 20 and `IS_PASSING(X)` to distinguish passing values. The two call expressions carry the discovered portable function handles.

- Base revision: 5; committed revision: 6.
- Pi: 6 turns, 6 tool calls (two discovery/inspection calls, two previews, one commit, one validation).
- The first preview was rejected with `MISSION_DEPENDENCY_REQUIRED`: it called `CLAMP_SCORE` in two separate conditions, and the initial implementation compared call-site occurrences against unique graph edges. No state changed. The model submitted a corrected candidate in the same session; its preview was accepted and committed. Afterward, the gateway comparison was corrected to treat dependencies as an edge set, and the production bridge preflight now tests a valid constructor with repeated `CLAMP_SCORE` call sites.
- Host oracle: all 12 specified inputs passed under interpreter and JIT; the complete normalized program replay passed with 17 semantic identities remapped.
- Pi session settled normally; launcher exited 0.

## Mission 2 — Raise the threshold to 45

A separate Pi process/session started from the revision-6 constructive stream. The MissionContract allowed one edit to the verified `IS_PASSING` comparison literal, expected 40 and allowed 45. The shared maintenance gateway previewed and committed one atomic edit.

- Base revision: 6; committed revision: 7.
- Pi: 6 turns and 5 tool calls: discovery, inspection, one preview, one commit and one validation. No rejected proposal.
- Host validation confirmed the only semantic change was the authorized literal, `CLAMP_SCORE` and `SCORE_CLASS` remained structurally unchanged, all original dependency edges remained bound, and all 17 portable semantic identities were preserved in the live Workspace.
- Fresh replay rebuilt all six committed operations into an empty Workspace, remapped 17 identities, and passed structural, binding and behavioral equivalence.
- Pi settled normally; launcher exited 0.

### Propagated behavior

| Input | Rev 6 `IS_PASSING` | Rev 6 `SCORE_CLASS` | Rev 7 `IS_PASSING` | Rev 7 `SCORE_CLASS` |
|---:|---:|---:|---:|---:|
| 39 | 0 | 1 | 0 | 1 |
| 40 | 1 | 2 | 0 | 1 |
| 44 | 1 | 2 | 0 | 1 |
| 45 | 1 | 2 | 1 | 2 |
| 50 | 1 | 2 | 1 | 2 |

All listed values agree between interpreter and JIT. `CLAMP_SCORE` remained unchanged. The direct semantic edit is one literal in `IS_PASSING`; `SCORE_CLASS` changed behavior at 40 and 44 without a source or identity change.

## Deterministic preflight

Before either model session, the production TypeScript handlers and JSONL gateway path were exercised without inference. The checks covered revision-5 replay, discovery, accepted and rejected creation proposals, non-mutating preview, revision-6 creation commit, the configurable threshold edit, stale revision, wrong scope, incorrect old value, revision-7 maintenance commit, host oracles and fresh replay. A failed/unauthorized second-mission preview preserved the already committed `SCORE_CLASS` function and revision.

The post-observation preflight additionally used a candidate that calls the same authorized dependency twice, proving the corrected set-based edge semantics. Full result: [deterministic preflight summary](deterministic-preflight-edge-set/summary.json).

## Architecture and cost

- New transaction engines/lifecycles: **0**. Both operation families use `SemanticTransactionKernel.preview` and `.commit`.
- New BASIC constructs, BWM formats, MIR backends and Pi tools: **0**.
- The Pi constructor schema was reused unchanged (19,767 serialized bytes); maintenance schema was 4,817 bytes.
- New mission configuration: three JSON contracts (the creation mission, revision-5 reconstruction contract and threshold-45 maintenance mission).
- Existing production files extended: Cycle19 creation gateway (+234/-36 lines including baseline replay plumbing, multi-callee validation and cycle-specific oracle/replay reporting); Cycle20 maintenance gateway (+25/-7 lines including the composed host oracle and deduplicated dependency graph). The shared 121-line transaction kernel was unchanged.
- Added test module: five tests. Added two bounded scripts: the production bridge preflight and the Mission 1 runner; the Mission 2 runner is the existing `run_cycle20.py`.

The creation adapter now contains notable campaign/reconstruction code. It is still an extension of the existing creation gateway and delegates all previews/commits to the shared kernel, but future work should factor baseline replay/reporting only if a second creation campaign needs the same path. No broader abstraction is justified by this one study.

## Measurements

| Measure | Mission 1 | Mission 2 |
|---|---:|---:|
| Model turns | 6 | 6 |
| Pi tool calls | 6 | 5 |
| Accepted previews | 1 | 1 |
| Rejected model previews | 1 | 0 |
| Commits | 1 | 1 |
| Input tokens reported by Pi | 18,014 | 10,237 |
| Output tokens reported by Pi | 6,224 | 781 |
| Cached input tokens reported by Pi | 61,560 | 20,816 |
| Recorded elapsed time | 153,617 ms | 51,017 ms |
| Gateway tool processing | 233.121 ms | 466.933 ms |
| Tool schema bytes | 19,767 | 4,817 |

Token values are provider-reported and kept separate by category; cached reads are not inferred from request bytes. One run per mission is feasibility evidence, not a model-performance comparison.

Final constructive stream: 6 operations and 17 portable handles; stream size 8,254 bytes. Historical visualization combines 17 significant frames. The combined offline HTML is 74,627 bytes; generic frame JSON is 95,170 bytes.

## Operator artifacts

- [Combined code-first replay](combined-replay/visual-replay-generic.html)
- [Combined frame data](combined-replay/visual-frames-generic.json)
- [Dependency and propagation observations](dependency-propagation.json)
- [Complete constructive stream](constructive-operations.json)
- [Structural/binding/behavioral equivalence](equivalence.json)
- [Machine-readable campaign summary](campaign-summary.json)
- Individual genuine sessions: [Mission 1](mission-1-real-agent-01/) and [Mission 2](mission-2-real-agent-01/)

The replay includes the verified revision-5 baseline, genuine discovery/proposals/commit events, the fresh-session boundary (host-derived from separate launcher/session evidence), threshold edit, revision-7 host validation and final replay. A Cycle19 event-bundle omission was handled by taking the revision-6 source from its genuine commit event and checking it byte-for-byte against the fresh revision-6 reconstruction; raw event records were left intact.

## Reproduction

From the repository root:

```sh
python3 -m unittest discover -s experiments/basic-workspace/tests -v
python3 experiments/basic-workspace/pi-integration/results/cycle24-dependency-propagation/build_combined_replay.py
```

The no-inference production bridge preflight can be rerun using a temporary `/var/tmp` output directory; this shell snippet removes that directory on exit:

```sh
tmpdir=$(mktemp -d /var/tmp/cycle24-preflight.XXXXXX)
trap 'rm -rf "$tmpdir"' EXIT
python3 experiments/basic-workspace/pi-integration/cycle24_preflight.py --output "$tmpdir/preflight"
```

The genuine sessions are preserved; the commands below are recorded for audit and will perform new inference if rerun. Do not rerun them as reproduction of this evidence:

```sh
python3 experiments/basic-workspace/pi-integration/run_cycle24.py \
  --output experiments/basic-workspace/pi-integration/results/cycle24-dependency-propagation/mission-1-real-agent-01 --timeout 240
python3 experiments/basic-workspace/pi-integration/run_cycle20.py \
  --contract experiments/basic-workspace/pi-integration/results/cycle24-dependency-propagation/contracts/mission-2-threshold45.json \
  --baseline-stream experiments/basic-workspace/pi-integration/results/cycle24-dependency-propagation/mission-1-real-agent-01/constructive-operations.json \
  --baseline-history experiments/basic-workspace/pi-integration/results/cycle24-dependency-propagation/mission-1-real-agent-01/history.jsonl \
  --baseline-validation experiments/basic-workspace/pi-integration/results/cycle24-dependency-propagation/mission-1-real-agent-01/mission-3-validation-host.json \
  --output experiments/basic-workspace/pi-integration/results/cycle24-dependency-propagation/mission-2-real-agent-01 --timeout 240
```

Open the combined replay directly in a local browser, or regenerate it with the third command above.

## Limitations

- The behavior checks use the specified finite input corpus; this is not a proof over all numeric inputs.
- The Pi call/discovery and host validation are separate observations. The host oracle and replay, not the model's final text, determine correctness.
- Creation and maintenance keep separate authorization adapters, although transaction lifecycle is shared.
- The first real proposal was denied due to the edge-multiplicity defect described above. The trace preserves it; the post-observation regression proves the corrected behavior without running a third model session.
- No Kitty or browser screenshot was required or captured for this cycle.
