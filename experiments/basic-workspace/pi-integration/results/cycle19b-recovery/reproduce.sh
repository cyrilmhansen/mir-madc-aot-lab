#!/usr/bin/env bash
set -euo pipefail

# Run from repository root. The operator's Pi/Sushi configuration is read from
# PI_CODING_AGENT_DIR (or ~/.sushi/pi); no endpoint or credential is embedded.
python3 -m py_compile \
  experiments/basic-workspace/pi-integration/cycle19_gateway.py \
  experiments/basic-workspace/pi-integration/run_cycle19b.py \
  experiments/basic-workspace/tests/test_cycle19_empty_workspace.py

python3 - <<'PY'
import os, pathlib, subprocess, tempfile
root = pathlib.Path.cwd()
with tempfile.TemporaryDirectory(prefix="atlas-cycle19b-tests-", dir="/var/tmp") as base:
    env = os.environ.copy()
    env["PYTHONPATH"] = (f"{root}/experiments/basic-workspace:"
                         f"{root}/experiments/basic-workspace/pi-integration")
    raise SystemExit(subprocess.call([
        "pytest", "-q", f"--basetemp={base}/pytest",
        "experiments/basic-workspace/tests"], env=env))
PY

# Use a new empty output path for a new bounded genuine Mission 2 session.
python3 experiments/basic-workspace/pi-integration/run_cycle19b.py \
  --resume-from experiments/basic-workspace/pi-integration/results/cycle19-empty-workspace/real-agent-01 \
  --output experiments/basic-workspace/pi-integration/results/cycle19b-recovery/real-agent-03 \
  --timeout 240 --open-browser
