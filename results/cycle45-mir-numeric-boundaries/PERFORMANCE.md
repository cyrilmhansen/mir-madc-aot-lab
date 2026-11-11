# Performance

A small exploratory process-level sample was measured after correctness testing. Five runs followed one warm-up. These timings include process startup and initialization and are not an isolated MIR-phase benchmark. No preregistered performance threshold existed, so no regression claim is made.

| Route | Median ms | Range ms |
|---|---:|---:|
| Construct + interpreter/JIT corpus | 7.584 | 7.548–7.616 |
| Fresh text parse + interpreter/JIT | 7.577 | 7.496–7.607 |
| Fresh binary decode + interpreter/JIT | 7.655 | 7.582–7.668 |
| Native object client | 1.408 | 1.322–1.412 |

Exact samples are in `performance-results.json`; the post hoc exploratory procedure is explicitly labeled there.
