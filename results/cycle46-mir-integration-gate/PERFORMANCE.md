# Performance

Five process-level samples followed one warm-up. These timings include process startup and context initialization, so they do not separate construction, linking, JIT compilation or steady-state calls. They are exploratory, not a backend speed comparison.

| Route | Median ms | Range ms |
|---|---:|---:|
| Direct construct + JIT | 7.654 | 7.582–7.666 |
| Fresh text + JIT | 3.523 | 3.378–7.667 |
| Fresh binary + JIT | 3.442 | 3.379–7.574 |
| Native GCC client | 1.341 | 1.267–1.427 |
| Shared dlopen client | 1.367 | 1.208–1.517 |

Wide route ranges show scheduler/startup noise; no backend performance ranking is claimed. See `performance-results.json` for raw samples. Fine-grained JIT compile, first-call and per-call instrumentation was not added.
