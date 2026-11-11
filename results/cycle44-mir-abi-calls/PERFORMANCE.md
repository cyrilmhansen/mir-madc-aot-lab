# Performance

The confirmatory process-level benchmark used one warmup and seven fresh-process samples per route. It includes process startup, MIR initialization and route setup; it is not per-call ABI latency and is not compared as a backend speed ranking. Raw samples are in `performance-results.json`.

| Route | Median ms | Range ms |
|---|---:|---:|
| Direct construction + interpreter/JIT | 14.60 | 11.98–14.92 |
| Fresh text parse + interpreter/JIT | 15.40 | 13.01–17.26 |
| Fresh binary decode + interpreter/JIT | 12.32 | 11.62–17.38 |
| `MIR_object_load` | 1.45 | 1.29–1.65 |
| System-linked object client | 0.57 | 0.56–0.66 |
| Shared library/dlopen client | 0.87 | 0.67–1.05 |

The preregistered 2× per-call threshold could not be applied because these timings are process-level and the harness does not isolate a stable repeated-call loop from startup. No performance regression claim is made. Per-call and memory-use benchmarking remains incomplete.
