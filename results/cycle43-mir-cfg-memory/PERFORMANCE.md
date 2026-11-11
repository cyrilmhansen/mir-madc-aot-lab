# Performance observations

A threshold was registered before the confirmatory measurement: investigate if either fresh persistence route's median end-to-end process time exceeds 2.0× the direct route median. Each route used two warmups and seven measured fresh processes over the same 412 cases.

| Route | Median ms | Range ms | Ratio to direct |
|---|---:|---:|---:|
| Direct construction + interpreter/JIT | 7.042 | 6.457–8.326 | 1.000 |
| Fresh text parse + interpreter/JIT | 5.683 | 4.445–6.255 | 0.807 |
| Fresh binary decode + interpreter/JIT | 5.681 | 5.084–5.829 | 0.807 |

No registered ratio threshold was exceeded. These are exploratory end-to-end process timings; startup, construction or parsing, linking, execution and output are not instrumented separately. They do not isolate JIT compilation, first-call or repeated-call costs and are not an authorization-layer performance claim. Raw samples are in `performance-results.json`; the earlier 256-case exploratory run is retained separately.
