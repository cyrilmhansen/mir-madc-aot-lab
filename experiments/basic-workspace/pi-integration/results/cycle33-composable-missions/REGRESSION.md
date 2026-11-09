# Cycle 33 regression status

Command:

```sh
python3 -m unittest discover -s experiments/basic-workspace/tests -v
```

Result: **249 tests passed** in 42.205 seconds (42.33 seconds wall time). No existing regression failures. The current test runner reports test methods; it does not print an aggregate subtest count. Cycle 32's preserved report recorded 80 subtests.

The existing full suite includes historical Cycle 19/20/23/26/29/30/31 tests, and the actual Cycle 23/24 TypeScript-to-JSONL deterministic bridge preflights. Their baseline results pass. They do not exercise Cycle 33, because the Cycle 33 extension mode and production coordinator were not implemented after the complexity stop.

No Cycle 33 tests were added. No Cycle 33 Workspace mutation, transaction preview/commit, independent oracle, or constructive replay was run. See `COMPLEXITY-REVIEW.md` for the stop decision.
