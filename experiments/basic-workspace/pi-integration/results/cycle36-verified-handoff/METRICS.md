# Cycle 36 implementation and runtime metrics

## Code size

Counts use `wc -l` on the named production sources. Test, preflight, and report
code are counted separately and do not contribute to production runtime.

| Component | Before | After | Change |
|---|---:|---:|---:|
| Cycle19 creation gateway | 1,169 | 1,169 | 0 |
| Cycle20 maintenance gateway | 1,204 | 1,224 | +20 net (+22 added, −2 removed) |
| Verified handoff verifier | 0 | 320 | +320 |
| Transaction kernel | 121 | 121 | 0 |
| Shared portable replay | 452 | 452 | 0 |
| TypeScript extension | 241 | 241 | 0 |
| **Net production lines** | — | — | **+340** |

Cycle19's ordered creation and Cycle20's existing baseline reconstruction,
authorization, transaction, validation, and constructive history remain active.
The handoff verifier is a host-only evidence adapter. It adds no gateway class,
mutation operation, replay dispatcher, transaction kernel, or Pi tool. There
are zero new Cycle36-specific policy lines for Mission A or Mission B; their
runtime authorization is represented by Cycle35/Cycle34 data contracts.

Experimental support added 448 lines of end-to-end preflight, 169 lines of
negative evidence generation, 74 lines of metrics collection, 54 lines of
evidence indexing, and 168 test lines. These are test/evidence tooling, not
runtime authorization.

## Repeated deterministic timing

`performance.json` contains raw summaries. Each summary reports median and
min/max observed values. Handoff hashing/building and verification were run
five times; gateway initialization with full baseline reconstruction and MIR
observations was run three times; portable replay and independent arithmetic
were run five times. Tool timings are aggregated from the actual bridge run
and include both valid calls and the recorded rejected controls where the
method name is shared.

| Operation | Mission A median (range) | Mission B median (range) |
|---|---:|---:|
| Handoff serialization + hashing, 5 runs | 0.907 ms (0.734–1.038) | 0.587 ms (0.542–0.726) |
| Handoff verification + prefix replay, 5 runs | 19.467 ms (17.238–20.433) | 9.048 ms (8.924–9.515) |
| Cycle20 startup, handoff + reconstruction + initial MIR, 3 runs | 224.955 ms (222.192–228.649) | 124.524 ms (122.424–126.312) |
| Full portable stream replay, 5 runs | 8.737 ms (8.402–10.388) | 6.601 ms (5.592–9.188) |
| Independent arithmetic corpus, 5 runs | 0.002 ms (0.001–0.005) | 0.001 ms (0.001–0.004) |
| Host validation tool processing, observed calls | 263.491 ms (59.993–407.104) | 183.771 ms (53.570–246.115) |
| Constructor preview processing, including controls | 0.593 ms (0.193–9.473), 15 calls | 0.607 ms (0.247–7.724), 11 calls |
| Edit preview processing, including rejected controls | 0.178 ms (0.171–203.791), 3 calls | 0.180 ms (0.119–113.615), 3 calls |

The wide maximums are real observations in this local run, not performance
guarantees. They include host scheduling and the mixed valid/rejected bridge
workload. The deterministic campaign did not perform inference.

## Generalization cost

Mission B added a new creation contract, a new maintenance contract, an
independent oracle fixture, and its output evidence. It required **zero
additional production changes after Mission A**. Both missions used the same
handoff schema/verifier, Cycle19 sequence implementation, Cycle20 v2 policy,
SemanticTransactionKernel, six-family portable replay dispatcher, and
TypeScript schemas.
