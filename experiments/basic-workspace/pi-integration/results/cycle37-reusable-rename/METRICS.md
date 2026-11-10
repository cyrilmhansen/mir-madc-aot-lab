# Cycle 37 metrics

## Code size

Line counts use `wc -l` over the named source files. “Before” is the Cycle36 HEAD; “after” is the Cycle37 worktree. Generated evidence is excluded.

| Component | Before | After | Change |
|---|---:|---:|---:|
| Cycle26 gateway | 335 | 501 | +166 |
| Shared rename policy | 0 | 123 | +123 |
| Cycle36 handoff verifier | 320 | 320 | 0 |
| TypeScript extension | 241 | 241 | 0 |
| Cycle37 bridge/preflight harness | 0 | 325 | +325 test/evidence tooling |
| Cycle37 focused unit tests | 0 | 155 | +155 tests |

Production runtime net increase is 289 lines across the existing rename gateway and one shared policy module. The bridge harness and tests are not counted as runtime. Some legacy candidate checks were moved into the shared policy; the gateway retains the Cycle26-specific historical bootstrap and adds the v2 verified-handoff initialization/validation path. No old handoff verifier, replay dispatcher, Workspace operation, transaction kernel, or TypeScript handler was copied or modified.

| Architecture measure | Before | After |
|---|---:|---:|
| Rename authorization implementations | 1 Cycle26-specialized path | 1 shared candidate policy used by legacy v1 and handoff v2 |
| Gateway classes | 1 historical rename class | 1 class, two explicit initialization modes |
| Workspace rename primitives | 1 canonical `rename_symbol` | 1 |
| Transaction kernels/lifecycles | 1 shared kernel | 1 |
| Replay dispatchers | 1 shared Cycle31 dispatcher | 1 |
| Tool schemas | Existing five-tool rename schema | Same schema, 860 compact serialized bytes |
| Production TypeScript changes | 0 | 0 |

Mission A runtime-specific additions: zero beyond the generic v2 path and its host contract. Mission B additional runtime: zero. Mission A and B each used 21 portable semantic identities, four constructors, one rename, and revisions 1–6.

## Timing

Three host-only runs per mission used `perf_counter`; every run reconstructed from its authenticated handoff, discovered the target, previewed, committed in an isolated Workspace, and independently validated. Temporary run state was created under `/var/tmp` with automatic cleanup. The raw samples are in `performance-measurements.json`.

| Phase (ms) | Mission A median [min, max] | Mission B median [min, max] |
|---|---:|---:|
| Handoff authentication + Workspace reconstruction + baseline oracle | 393.830 [384.934, 409.829] | 292.200 [288.382, 295.842] |
| Discovery | 1.057 [1.026, 1.078] | 1.448 [1.017, 1.606] |
| Preview | 9.399 [7.953, 10.062] | 9.924 [7.996, 12.045] |
| Commit | 9.170 [9.048, 11.927] | 10.614 [9.370, 13.575] |
| Full host validation incl. MIR and fresh replay | 705.813 [705.416, 709.457] | 494.034 [491.036, 495.952] |

The phase timings are deterministic local measurements, not model latency and not a performance comparison between equivalent-size programs. The host validation and reconstruction phases include work proportional to each mission's operation and observation records.
