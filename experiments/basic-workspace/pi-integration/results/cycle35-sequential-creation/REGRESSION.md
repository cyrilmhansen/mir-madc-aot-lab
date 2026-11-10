# Cycle 35 regression results

Command:

```sh
python3 -m unittest discover -s experiments/basic-workspace/tests
```

Result after Cycle 35 implementation: **267 tests passed** in 49.292 seconds. The previous Cycle 34 count was 256, so this cycle adds eleven discovered test methods. No existing test was removed.

Focused compatibility command:

```sh
python3 -m unittest \
  experiments.basic-workspace.tests.test_cycle19_empty_workspace \
  experiments.basic-workspace.tests.test_cycle24_dependency_propagation \
  experiments.basic-workspace.tests.test_cycle35_sequential_creation
```

Result: 27 tests passed. This covers the original Cycle 19 flow, multi-callee construction, sequence creation, host-gated progression, recovery, strict configuration and rejected history controls.

Production bridge: `cycle35_preflight.py --output <new-empty-output-dir>` passed both sequence configurations through `cycle20b_dispatch_probe.ts` → registered `extension.ts` handlers → JSONL → `Cycle19Gateway`. The preserved final evidence is `production-bridge-attempt-06/bridge-validation.json`. Both missions used the same five active tools and committed revisions 2, 3, 4 and 5.

No Pi/Sushi inference was performed.
