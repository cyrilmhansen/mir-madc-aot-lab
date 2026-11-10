# Complexity and measurements

## Production code

Physical line counts use `wc -l`; changes use `git diff --numstat` against Cycle40 HEAD `6da6d2816afdd1069288265eb104f0f24e8ef377`. No line packing is used.

| Component | Before | After | Change |
|---|---:|---:|---:|
| Cycle20 gateway | 1276 | 1340 | +68 / −4; net +64 |
| Transaction kernel | 121 | 121 | 0 |
| Shared portable replay | 452 | 452 | 0 |
| Verified construction handoff | 320 | 320 | 0 |
| Verified rename continuation | 357 | 357 | 0 |
| TypeScript extension | 241 | 241 | 0 |

The additions are strict v3 table validation, v3 version dispatch, table-to-existing-observation normalization, and early resolution of v3 validation handles after authenticated reconstruction. The removed lines are only version-specific branches replaced by explicit v2/v3 conditions. Mission authorization and existing v1/v2 oracle evaluation remain in their original path. No new class, operation, transaction kernel, replay dispatcher, gateway family, or model-facing tool was introduced.

Experimental tooling adds a bounded generated workflow adapter and benchmark script; test and evidence line counts are reported separately from production runtime. The second seed set adds no mission-specific runtime code. TypeScript schemas and bridge LOC are unchanged.

The new experiment runner is 250 LOC, the isolated benchmark is 77 LOC, and the focused regression module is 185 LOC. These are campaign/test tooling, not production runtime. The generated fixture data and evidence are separate from these counts.

## Performance

See `PERFORMANCE.md` and both raw confirmatory benchmark JSON files. Five fresh samples were collected for v2 and v3 at 16, 32 and 64 inputs with two functions, three authorized targets and dependency depth one, in two uncontented runs. The 2× threshold was registered in the campaign configuration. Table schema validation was repeatedly 2.5–8.5x the v2 parse median, but remained below 0.08 ms per contract. Preview, commit, MIR observation and full validation/replay remained within 4%. This small absolute parse cost is confirmed but not material to end-to-end validation latency. Finite expected-row lookup was faster than formula-oracle evaluation. These are environment-specific measurements, not a general performance claim.

The generated campaign includes two- and three-function workloads. Four-function cases were not emitted by the current generator. The isolated v2/v3 comparison intentionally holds function count and target count constant.
