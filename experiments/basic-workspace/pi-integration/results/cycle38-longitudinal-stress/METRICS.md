# Cycle38 code and runtime metrics

## Production LOC

Counts use physical `wc -l` on each named Python/TypeScript file. Generated evidence, tests and scripts are excluded from production LOC.

| Component | Cycle37 baseline | Cycle38 | Delta |
|---|---:|---:|---:|
| Cycle19 creation gateway | 1,169 | 1,169 | 0 |
| Cycle20 maintenance gateway | 1,224 | 1,276 | +52 |
| Cycle26/37 rename gateway | 501 | 501 | 0 |
| Cycle36 creation handoff verifier | 320 | 320 | 0 |
| New verified rename continuation verifier | 0 | 354 | +354 |
| Semantic transaction kernel | 121 | 121 | 0 |
| Cycle31 portable replay | 452 | 452 | 0 |
| Production TypeScript JSONL bridge probe | 103 | 103 | 0 |

Net production addition: **406 LOC**. The new verifier is one host-only continuation capability, not a gateway or mutation engine. It reuses the existing Cycle36 handoff verifier, Cycle37 rename policy and receipt, Cycle31 replay, MIR execution, and Cycle20 maintenance authorization. Cycle20's new 52 lines are an opt-in constructor/CLI adapter path; legacy handoff and raw baseline modes are unchanged. Mission B required **zero** further production lines.

Added experiment tooling LOC: `cycle38_preflight.py` 322; `cycle38_security_matrix.py` 162; `cycle38_interruption_preflight.py` 181; `cycle38_generated_workloads.py` 107; `cycle38_metamorphic.py` 114; `cycle38_metrics.py` 94 (980 total). One focused unittest module adds 80 test LOC. Evidence and tooling are excluded from production runtime LOC. No gateway classes, Workspace mutation primitives, transaction kernels, replay dispatchers, TypeScript schemas or agent tools were added.

## Architecture counts

- Operation families in the full longitudinal stream: 3 (`create_numeric_function`, `rename_symbol`, `edit_numeric_literals`).
- New operation families: 0.
- New transaction lifecycles: 0; all individual commits use existing kernel/Workspace transactions.
- New replay dispatchers: 0; Cycle31 remains authoritative.
- New continuation verifier: 1, accepts one explicit history shape (creation prefix + one rename + destination maintenance contract).
- Maintenance authorization and replay remain separate; the continuation grants no edit permission.

## Runtime samples

Repeated measurements in `performance.json` use the same local machine, Python runtime and deterministic evidence; no model inference was run.

| Operation | Mission A median (range) ms | Mission B median (range) ms | Samples |
|---|---:|---:|---:|
| Empty Workspace initialization | 0.023 (0.020–0.045) | 0.025 (0.020–0.172) | 8 each |
| Complete six/five-operation fresh replay | 22.774 (22.592–23.799) | 15.949 (15.388–19.478) | 8 each |
| Continuation verification incl. nested evidence verification, replay and MIR checks | 774.759 (767.292–788.379) | 534.513 (528.103–550.955) | 4 each |
| MIR interpreter corpus | 173.585 (171.770–175.400) | 95.474 (94.555–96.393) | 2 each |
| MIR JIT corpus | 259.188 (257.179–261.197) | 140.757 (139.606–141.909) | 2 each |

Actual gateway timing journals are preserved per stage under attempt 08. They include repeated authorization denials, accepted previews, commit, duplicate-commit rejection and validation; values are retained raw because some aggregate validation calls include MIR startup and replay. Construction validation grows with revision/function count, so the two missions' host-validation durations should not be read as authorization-only latency. Cycle38 adds a replay/attestation pass at the receiving boundary, visible in the ~0.53–0.77 s continuation verification samples. There is no apples-to-apples prior continuation benchmark.

The twelve generated variants each replayed a five/six-operation stream in a median 24.7 ms overall (the raw per-variant samples are in `generated-workloads.json`). These are bounded canonical replay/oracle stress cases, not twelve additional TypeScript authorization campaigns.
