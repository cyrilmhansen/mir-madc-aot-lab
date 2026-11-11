# Performance

Seven exploratory whole-process samples per route were recorded in
`performance-results.json` for the same 344-function corpus. Medians were
19.45 ms for programmatic construction, interpreter/JIT and text/binary emit,
16.81 ms for fresh text parse/JIT, and 16.56 ms for fresh binary decode/JIT. Observed ranges
were 18.29–25.50 ms, 16.06–19.97 ms and 15.18–19.62 ms respectively.

These timings include process and context startup, had no warm-up, and were not
collected against a pre-registered regression threshold. They are exploratory
only; no path is declared faster. Historical MIR parse/JIT/AOT timing data
exists in `results/linux-x86_64/timings.csv`, `emission.csv`, and related
reports, but Cycle42 did not rerun those large matrices. Confirmatory
performance acceptance remains incomplete.
