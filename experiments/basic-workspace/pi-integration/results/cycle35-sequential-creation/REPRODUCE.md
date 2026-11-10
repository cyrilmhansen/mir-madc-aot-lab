# Reproduce Cycle 35

From the repository root:

```sh
python3 -m unittest experiments.basic-workspace.tests.test_cycle35_sequential_creation
python3 experiments/basic-workspace/pi-integration/cycle35_preflight.py \
  --output experiments/basic-workspace/pi-integration/results/cycle35-sequential-creation/bridge-reproduction-01
python3 experiments/basic-workspace/pi-integration/cycle35_results.py
python3 -m unittest discover -s experiments/basic-workspace/tests
```

`cycle35_preflight.py` refuses to overwrite a nonempty output path. It launches no model. It calls the actual TypeScript handlers with deterministic typed fixtures, uses the production JSONL bridge, asks the host to validate/checkpoint/advance, and stores the tool schemas, tool requests, tool responses, gateway journals, and per-step oracle observations.

`cycle35_results.py` independently replays every constructive prefix through the shared Cycle 31 portable replay dispatcher, rebuilds the identity ledger and equivalence evidence, validates the revision-3 recovery path, and runs five direct deterministic timing repetitions per mission. Its small arithmetic oracle is separate from the Workspace projection and both MIR engines.

The historical bridge harness failure remains in `production-bridge/`; the final successful capture is preserved in `production-bridge-attempt-06/`.
