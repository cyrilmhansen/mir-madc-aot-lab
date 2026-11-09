# Regression and production bridge checks

Command:

```sh
python3 -m unittest discover -s experiments/basic-workspace/tests -v
```

Result: **249 tests passed** in 44.253 seconds (44.40 seconds wall time; one full-suite run). The unittest summary counts test methods and does not print an aggregate subtest count. Cycle 31's preserved report records 80 subtests for its baseline run; this Cycle 32 log preserves the exact current runner output.

The full suite passed the following production-path tests:

- `test_cycle23_transaction_kernel.SharedTransactionKernelTests.test_production_extension_dispatch_covers_creation_and_maintenance` — invokes `cycle23_transaction_preflight.py`, which runs the actual TypeScript extension handler and JSONL bridge against the existing Cycle19 creation and Cycle20/Cycle21 maintenance gateways.
- `test_cycle24_dependency_propagation.MultiDependencyCreationTests.test_production_typescript_jsonl_and_shared_kernel_preflight` — existing multi-dependency creation bridge preflight.

These are deterministic controls on already supported campaigns. They do **not** execute the Cycle 32 mission or show that its contracts can be passed through the bridge. No Cycle 32-specific tool request was synthesized, and no Pi/Sushi process was launched.

The complete output is retained in `regression.log`; elapsed time is in `regression-timing.txt`.
