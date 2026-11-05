# ELF PIE execution, fresh process

Each artifact is executed once as warm-up, then in 30 new processes. The workload verifies its expected result by returning zero. Linux runs in QEMU TCG on Apple M2 Ultra; page cache remains warm.

| Functions | Median wall ms | p95 ms | Min ms | SD ms | Median CPU ms | Median RSS KiB |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 11.418 | 12.304 | 10.870 | 0.440 | 9.816 | 9148 |
| 100 | 11.087 | 12.073 | 10.633 | 0.584 | 9.526 | 9166 |
| 1000 | 11.369 | 12.156 | 10.654 | 0.422 | 9.684 | 9184 |
| 5000 | 11.076 | 11.689 | 10.530 | 0.297 | 9.532 | 9204 |
