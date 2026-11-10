# Reproduce Cycle 34

From the repository root:

```sh
python3 experiments/basic-workspace/pi-integration/cycle34_preflight.py
python3 experiments/basic-workspace/pi-integration/cycle34_negative_controls.py
python3 experiments/basic-workspace/pi-integration/cycle34_measure.py
python3 -m unittest experiments.basic-workspace.tests.test_cycle34_cross_function_authorization -v
python3 -m unittest discover -s experiments/basic-workspace/tests -v
```

The bridge preflight starts the real Cycle20 gateway with each contract and invokes the registered TypeScript extension tool handlers through `cycle20b_dispatch_probe.ts`; the extension uses its production JSONL transport. It performs no model inference. By default, preflight refuses to overwrite existing bridge evidence. Use `--output <new-empty-directory>` for an additional capture.

The negative-control and timing programs use temporary directories under `/var/tmp` and remove them automatically. The full regression output is written into this Cycle34 result directory only when the exact command is redirected as in this run.

No Pi/Sushi request is made by any command above.
