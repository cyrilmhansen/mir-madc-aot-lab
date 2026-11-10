# Metrics

## Production versus test tooling

No production Python, Workspace, replay, MIR, TypeScript schema, gateway, transaction kernel or authorization file was changed. New production LOC: **0**. New Workspace mutation primitives, transaction mechanisms, replay dispatchers and agent tools: **0**.

| Added tooling | Physical LOC |
|---|---:|
| Differential generator, oracle, replay runner | 375 |
| Actual TypeScript/JSONL Cycle19 bridge campaign | 188 |
| Metamorphic campaign | 122 |
| Performance probe | 64 |
| Evidence aggregator | 92 |
| Focused regression tests | 71 |
| Total test/evidence tooling | 912 |

Counts use physical lines from `wc -l`; generated JSON evidence and historical production modules are excluded. Existing production context inspected: Workspace model 2,355 LOC; portable replay 452; transaction kernel 121; Cycle19 1,169; Cycle20 1,276; Cycle26 501; TypeScript extension 241. These modules were reused unchanged.

## Execution volume

- 120 valid cases; 7 template families; 15,980 scalar oracle comparisons across interpreter/JIT and committed/replayed states (the complete values are preserved in JSONL).
- 16 distinct generated sequence contracts through actual TypeScript → JSONL → Cycle19; 30 constructor commits.
- 102 negative controls: 100 production bridge rejections plus two deterministic replay/Workspace unit controls.
- 28 generated metamorphic cases plus one provider propagation fixture.
- Seven repeated timing samples for each semantic stage; production handler round trips provide 30 samples across the 16 workflows.
- Additional independent deterministic campaign: 14 cases, seed offset 100000; production unchanged.

## Timing

Confirmatory seven-run medians (milliseconds):

| Stage | Median | Range |
|---|---:|---:|
| Empty Workspace initialization | 0.030 | 0.025–0.067 |
| Typed constructor application (representative two-function case) | 5.643 | 5.205–8.216 |
| Rename plus literal edit application | 2.912 | 2.852–3.281 |
| Projection build | 0.228 | 0.218–0.239 |
| MIR interpreter, three-input batch | 6.507 | 5.580–6.999 |
| MIR JIT, three-input batch | 9.125 | 7.714–9.873 |
| Fresh four-operation replay | 8.950 | 8.560–11.859 |

Across 30 actual TS/JSONL tool round trips, median dispatch latency was 383.740 ms (301.083–695.635). This call includes discovery, inspection, rejected controls, preview, commit and the extension's post-commit validation call. Separate host oracle validation had median 103.829 ms (90.341–419.185); checkpoint/progression median was 4.351 ms (3.333–5.310).

Cycle38's replay median was documented as 24.7 ms over five/six-operation histories. The confirmatory Cycle39 fresh replay measured 2.237 ms per operation median (2.140–2.965). Using a conservative five-operation normalization, the registered suspicious threshold was 9.88 ms/operation (2× 24.7/5). No suspicious replay regression was observed. This is a coarse baseline comparison, not an identical program or substage benchmark.

The earlier performance sample preceded a registered threshold and is retained as exploratory only. The confirmatory sample followed the threshold registration. MIR timings include the worker process compile/startup/invoke path; no worker-startup-free claim is made.
