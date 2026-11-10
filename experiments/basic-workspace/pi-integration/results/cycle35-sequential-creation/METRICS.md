# Cycle 35 complexity and timing

## Production LOC

Counts are physical source lines (`wc -l`) in tracked production files. Generated evidence and test code are excluded.

| Component | Before | After | Change |
|---|---:|---:|---:|
| `cycle19_gateway.py` | 828 | 1,164 | +336 net (+352 / −16) |
| `transaction_kernel.py` | 121 | 121 | 0 |
| `basic_workspace/portable_replay.py` | 452 | 452 | 0 |
| `extension.ts` | 241 | 241 | 0 |
| New gateway classes | 0 | 0 | 0 |
| New Workspace mutation operations | 0 | 0 | 0 |
| New transaction kernels | 0 | 0 | 0 |
| New replay dispatchers | 0 | 0 | 0 |
| New operation families | 0 | 0 | 0 |

The eight sequence-specific methods total 252 physical lines: strict contract validation, sequence initialization/activation, checkpoint and prefix recovery. Remaining gateway growth adapts existing status, validation, preview boundary and CLI handling. The existing `_candidate` changed by two lines; it remains the authorization implementation for legacy Cycle 19, verified-stream creation, and sequence mode. `_preview`, `_commit` and the transaction kernel remain the same lifecycle path, with no new transaction implementation.

Mission-specific production runtime: **0 lines for Mission A and 0 lines for Mission B**. Mission B's marginal production runtime cost after Mission A: **0 lines**.

## Evidence and configuration size

| Artifact | Lines / bytes |
|---|---:|
| Mission A host contract | 415 lines / 9,962 bytes |
| Mission B host contract | 325 lines / 7,630 bytes |
| Cycle35 deterministic production bridge runner | 165 lines |
| Cycle35 replay/metrics evidence builder | 198 lines |
| Cycle35 regression tests | 239 lines across 11 test methods |
| TypeScript schema/transport changes | 0 lines |
| New active tools | 0 |

The actual serialized five-tool extension registration capture measured **5,151 compact JSON bytes** and **19,766 pretty-printed bytes** in both missions. This is the TypeScript extension's exposed schemas, not a live Pi session context; no inference was run. The configuration and typed fixtures are separate from production runtime code.

## Reuse counts

- Independent numeric-function construction authorization paths for these modes: **one**, `Cycle19Gateway._candidate`.
- Preview/commit lifecycle implementations: **one**, the existing Cycle19 methods over `SemanticTransactionKernel`.
- Portable replay dispatchers: **one**, Cycle31 `replay_constructive_stream`.
- Function-creation operation families: **one**, existing `create_numeric_function`.
- Configured steps executed: **8** total, all on the same bounded path.
- Cross-mission reuse: Mission B added no production code after Mission A.

## Deterministic timing

Five repetitions per mission were run on this workspace. Each full run constructed four functions and validated/checkpointed/progressed after each step. Values below are median and observed min–max in milliseconds. The timing harness uses direct deterministic gateway calls; it excludes TypeScript process startup and has no model inference component.

| Measurement | Mission A median (min–max) | Mission B median (min–max) |
|---|---:|---:|
| Empty Workspace initialization | 1.105 (0.943–1.211) | 0.880 (0.564–1.092) |
| Constructor authorization + preview | 4.166 (2.007–6.788) | 4.466 (1.407–8.355) |
| Commit | 3.976 (2.107–6.799) | 4.556 (1.470–6.726) |
| Host validation (oracle + replay) | 155.774 (46.285–304.123) | 102.740 (30.783–208.668) |
| Checkpoint creation | 0.534 (0.251–0.646) | 0.442 (0.298–0.830) |
| Host progression | 0.384 (0.252–0.876) | 0.360 (0.233–0.909) |
| Complete four-step sequence | 703.839 (695.344–707.896) | 482.923 (475.618–491.971) |
| Separate fresh replay of final stream | 150.844 (147.587–154.633) | 106.595 (103.702–109.823) |

Validation latency has broad spread because each check launches MIR execution and replay work; the table reports observed timings, not a performance ranking. The programs and per-revision corpora differ, so Mission A and B timing is descriptive only.

Raw repeated samples are in `METRICS-data.json`. Bridge-level tool timings and schema captures remain under `production-bridge-attempt-05/`.
