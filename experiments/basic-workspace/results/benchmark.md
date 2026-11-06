# BASIC Workspace microbenchmarks

Read-only inputs are historical `basic-aot` samples. Parse timing includes tokenization and semantic index construction; edits include candidate snapshot, validation and index rebuild. `tracemalloc` peak covers initial open/index. 25-operation medians are used except parse (9) and lookup (2,000). No source files are written.

| Case | Source B | Lines | Tokens | Symbols | Parse/index ms | Rename tx ms | Lookup µs | Renumber tx ms | Render ms | Peak bytes | Diagnostics |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| tiny | 85 | 4 | 44 | 8 | 0.103 | 0.1797 | 0.261 | 0.1772 | 0.0014 | 22489 | 0 |
| medium | 5204 | 232 | 2255 | 323 | 9.095 | 8.2076 | 0.261 | 8.2649 | 0.0525 | 866173 | 2 |
| large | 8054 | 416 | 3632 | 442 | 21.844 | 13.6034 | 0.261 | 13.7816 | 0.085 | 1392476 | 0 |
