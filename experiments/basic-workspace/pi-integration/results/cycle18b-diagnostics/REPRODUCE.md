# Cycle 18B reproduction

No inference was run. The diagnosis reads preserved Cycle 18 records only.

```sh
python3 experiments/basic-workspace/pi-integration/diagnose_cycle18.py
python3 -m unittest experiments.basic-workspace.tests.test_pi_lifecycle experiments.basic-workspace.tests.test_pi_gateway -v
python3 -m unittest discover -s experiments/basic-workspace/tests
```

For future cycles, `run_cycle16.py` writes `pi-observed-lifecycle.jsonl` beside the unmodified raw `pi-session.jsonl`. The lifecycle file contains content-free event metadata and host arrival timestamps. Use the existing live viewer to see coarse no-progress state while the process is still running; the viewer remains read-only.
