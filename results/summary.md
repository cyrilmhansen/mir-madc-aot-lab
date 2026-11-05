# Synthetic benchmark summary

Host: macOS arm64. Every row is a new process; page cache may be warm. These are JIT and MIR-binary decode measurements, not ELF AOT measurements.

| Functions | Scenario | Median wall ms | p95 wall ms | Min ms | SD ms | Median parse ms | Median JIT ms | Median CPU ms |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 10 | text_parse_then_eager_jit | 3.938 | 4.485 | 3.664 | 0.209 | 0.085 | 0.007 | 2.399 |
| 10 | bmir_decode_then_eager_jit | 3.913 | 4.121 | 3.549 | 0.206 | 0.066 | 0.007 | 2.334 |
| 100 | text_parse_then_eager_jit | 7.424 | 8.033 | 6.961 | 0.265 | 0.554 | 0.105 | 5.820 |
| 100 | bmir_decode_then_eager_jit | 7.379 | 7.777 | 6.946 | 0.256 | 0.347 | 0.106 | 5.671 |
| 1000 | text_parse_then_eager_jit | 54.922 | 55.651 | 54.374 | 0.327 | 5.213 | 4.537 | 52.368 |
| 1000 | bmir_decode_then_eager_jit | 53.245 | 54.082 | 52.637 | 0.432 | 3.130 | 4.564 | 50.627 |
| 5000 | text_parse_then_eager_jit | 261.340 | 264.866 | 246.469 | 5.573 | 26.084 | 22.630 | 253.519 |
| 5000 | bmir_decode_then_eager_jit | 236.850 | 238.865 | 234.576 | 1.130 | 15.861 | 20.672 | 228.689 |
