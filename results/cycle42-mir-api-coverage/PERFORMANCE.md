# Performance

Seven exploratory whole-process samples per route were recorded in
`performance-results.json` for the same 353-case corpus. Medians were 20.68 ms
for programmatic construction, interpreter/JIT and text/binary emit, 18.75 ms
for fresh text parse/JIT, and 17.49 ms for fresh binary decode/JIT. Observed
ranges were 18.09–22.41 ms, 16.54–21.10 ms and 15.54–19.97 ms respectively.

These timings include process and context startup, had no warm-up, and were not
collected against a pre-registered regression threshold. They are exploratory
only; no path is declared faster. Historical MIR parse/JIT/AOT timing data
exists in `results/linux-x86_64/timings.csv`, `emission.csv`, and related
reports, but Cycle42 did not rerun those large matrices. Confirmatory
performance acceptance remains incomplete.
