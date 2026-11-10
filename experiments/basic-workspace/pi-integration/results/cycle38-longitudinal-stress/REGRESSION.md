# Regression and preflight results

- Full command: `python3 -m unittest discover -s experiments/basic-workspace/tests -v`
- Result: **287 tests passed** in 115.122 seconds. Final output: `full-workspace-tests-final.log`.
- Cycle37 baseline was 282 passing tests. Cycle38 adds five focused continuation tests.
- Focused tests: `python3 -m unittest experiments.basic-workspace.tests.test_cycle38_verified_continuation -v` — 5 tests passed.
- `py_compile` passed for all Cycle38 production, orchestration and test modules.
- Actual TypeScript extension → JSONL → Python bridge: attempt 08 completed both missions. Creation, rename, and maintenance retained the existing five-tool inventories. Both maintenance batches had a non-mutating preview and exactly one revision-checked commit, then independent host validation and fresh replay.
- Mission A revisions: 1→5 creation, 5→6 rename, 6→7 maintenance. Mission B: 1→4 creation, 4→5 rename, 5→6 maintenance.
- Negative controls: 69 distinct exercised cases in `negative-controls.json` (43 production bridge control/schema rows plus 26 continuation integrity/provenance mutations). Rejections did not activate a mutation transaction.
- Interrupted preview recovery: both rename and maintenance previews were abandoned, their processes stopped, and new processes authenticated/reconstructed at the same revision and created distinct preview transaction IDs. See `interruption-recovery.json`.
- Metamorphic checks and twelve bounded replay workloads passed: `metamorphic-results.json`, `generated-workloads.json`.
- No Pi/Sushi inference was run.

The final run had no semantic or authorization failure. Attempts 01–06 record harness-only faults; attempt 07 records the first completed pair before the anchor-layout issue was found; attempt 08 is the final accepted run. See `RUN-ATTEMPTS.md`.
