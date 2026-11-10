# Reproduce Cycle38

Run from the repository root. Requires the existing Python/MIR and Bun runtime used by Cycle19–37.

```bash
python3 experiments/basic-workspace/pi-integration/cycle38_preflight.py \
  --output experiments/basic-workspace/pi-integration/results/cycle38-longitudinal-stress/production-bridge-reproduced
python3 experiments/basic-workspace/pi-integration/cycle38_security_matrix.py \
  --attempt experiments/basic-workspace/pi-integration/results/cycle38-longitudinal-stress/production-bridge-reproduced \
  --output experiments/basic-workspace/pi-integration/results/cycle38-longitudinal-stress/negative-controls-reproduced.json
python3 experiments/basic-workspace/pi-integration/cycle38_interruption_preflight.py \
  --attempt experiments/basic-workspace/pi-integration/results/cycle38-longitudinal-stress/production-bridge-reproduced \
  --output experiments/basic-workspace/pi-integration/results/cycle38-longitudinal-stress/interruption-reproduced
python3 experiments/basic-workspace/pi-integration/cycle38_generated_workloads.py \
  --attempt experiments/basic-workspace/pi-integration/results/cycle38-longitudinal-stress/production-bridge-reproduced \
  --output experiments/basic-workspace/pi-integration/results/cycle38-longitudinal-stress/generated-workloads-reproduced.json
python3 experiments/basic-workspace/pi-integration/cycle38_metamorphic.py \
  --attempt experiments/basic-workspace/pi-integration/results/cycle38-longitudinal-stress/production-bridge-reproduced \
  --output experiments/basic-workspace/pi-integration/results/cycle38-longitudinal-stress/metamorphic-results-reproduced.json
python3 experiments/basic-workspace/pi-integration/cycle38_metrics.py \
  --attempt experiments/basic-workspace/pi-integration/results/cycle38-longitudinal-stress/production-bridge-reproduced \
  --output experiments/basic-workspace/pi-integration/results/cycle38-longitudinal-stress/performance-reproduced.json
python3 -m unittest experiments.basic-workspace.tests.test_cycle38_verified_continuation -v
python3 -m unittest discover -s experiments/basic-workspace/tests -v
```

The final accepted evidence is `production-bridge-attempt-08`; attempts 01–07 are retained and must not be overwritten. Attempt 07 is diagnostic because its anchor was colocated with the evidence bundle; attempt 08 keeps the host anchor outside that mutable bundle. The stress scripts use deterministic host configurations and do not start Pi or Sushi. `cycle38_security_matrix.py` creates its isolated copies under `/var/tmp` with automatic cleanup. The repository test uses a `TemporaryDirectory` under `/var/tmp` and cleans it on exit.
