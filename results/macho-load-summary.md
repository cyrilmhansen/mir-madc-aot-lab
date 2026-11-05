# Mach-O dylib load pilot

Fresh process per sample, one warm-up, 30 measured samples. macOS page cache was left warm. The loader confirms the test dylib is absent after `dlclose`; libmadc runtime image retained after close in 30/30 processes.

- Median direct `dlopen`: 23.482 ms
- Median process wall time: 27.572 ms
- p95 process wall time: 28.023 ms
- Minimum process wall time: 26.853 ms
- Sample standard deviation: 0.316 ms
- Median process peak RSS: 9.38 MiB (Darwin `ru_maxrss`)
- Median major faults per process: 0
- Median compute loop time (20,000 calls): 16.0 µs
