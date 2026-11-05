# Linux x86-64 AOT fresh-process benchmark

Host CPU is QEMU TCG on an Apple M2 Ultra; results are emulated and not native x86-64 performance. One warm-up per scenario, then fresh process per measured row; page cache remains warm.

| Functions | Path | Median wall ms | p95 ms | Min ms | SD ms | Median setup/load ms | Median first call ms | Median RSS KiB |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 10 | text_parse_then_eager_jit | 18.330 | 19.540 | 15.390 | 1.118 | 5.888 | 0.183501 | 13824 |
| 10 | bmir_decode_then_eager_jit | 18.183 | 19.498 | 16.525 | 0.873 | 5.863 | 0.188501 | 13824 |
| 10 | elf_object_MIR_object_load | 9.673 | 10.714 | 8.392 | 0.700 | 0.483 | 0.170501 | 13824 |
| 10 | elf_shared_dlopen | 7.064 | 7.575 | 6.245 | 0.336 | 0.449 | 0.003000 | 13952 |
| 100 | text_parse_then_eager_jit | 83.400 | 90.655 | 69.534 | 5.896 | 62.943 | 0.190501 | 14080 |
| 100 | bmir_decode_then_eager_jit | 75.745 | 80.996 | 67.501 | 3.606 | 56.200 | 0.175001 | 14208 |
| 100 | elf_object_MIR_object_load | 13.114 | 14.307 | 8.948 | 1.545 | 4.193 | 0.152501 | 14208 |
| 100 | elf_shared_dlopen | 6.746 | 7.618 | 6.198 | 0.466 | 0.455 | 0.003000 | 14208 |
| 1000 | text_parse_then_eager_jit | 737.794 | 841.135 | 609.873 | 67.539 | 639.197 | 0.343002 | 14336 |
| 1000 | bmir_decode_then_eager_jit | 666.562 | 758.053 | 597.404 | 48.845 | 565.374 | 0.315501 | 14336 |
| 1000 | elf_object_MIR_object_load | 52.914 | 55.450 | 19.861 | 12.935 | 34.771 | 0.152001 | 14336 |
| 1000 | elf_shared_dlopen | 8.651 | 9.152 | 7.432 | 0.443 | 0.452 | 0.020500 | 14336 |
| 5000 | text_parse_then_eager_jit | 3618.018 | 4068.915 | 3094.391 | 296.484 | 3149.282 | 0.445501 | 57152 |
| 5000 | bmir_decode_then_eager_jit | 3547.672 | 4216.317 | 3019.304 | 314.369 | 3099.465 | 0.423501 | 56696 |
| 5000 | elf_object_MIR_object_load | 217.726 | 235.876 | 61.896 | 76.123 | 169.254 | 0.139500 | 14464 |
| 5000 | elf_shared_dlopen | 16.658 | 19.793 | 14.322 | 1.512 | 0.433 | 0.023000 | 14592 |
