#!/usr/bin/env bash
set -euo pipefail

# Run from the repository root. PI_CODING_AGENT_DIR may point at the operator's
# ignored local Pi/Sushi configuration; no endpoint or credential is embedded.
python3 -m py_compile \
  experiments/basic-workspace/pi-integration/cycle19_gateway.py \
  experiments/basic-workspace/pi-integration/run_cycle19.py \
  experiments/basic-workspace/tests/test_cycle19_empty_workspace.py

python3 - <<'PY'
import os, pathlib, subprocess, tempfile
root = pathlib.Path.cwd()
with tempfile.TemporaryDirectory(prefix="atlas-cycle19-tests-", dir="/var/tmp") as base:
    env = os.environ.copy()
    env["PYTHONPATH"] = (f"{root}/experiments/basic-workspace:"
                         f"{root}/experiments/basic-workspace/pi-integration")
    raise SystemExit(subprocess.call([
        "pytest", "-q", f"--basetemp={base}/pytest",
        "experiments/basic-workspace/tests"], env=env))
PY

# Both commands are bounded. The model campaign contains exactly one session
# per mission and does not retry. Choose fresh output directories for a new run.
python3 experiments/basic-workspace/pi-integration/run_cycle19.py \
  --preflight-only \
  --output experiments/basic-workspace/pi-integration/results/cycle19-empty-workspace/preflight-reproduction

python3 experiments/basic-workspace/pi-integration/run_cycle19.py \
  --timeout 240 \
  --output experiments/basic-workspace/pi-integration/results/cycle19-empty-workspace/real-agent-reproduction \
  --open-browser
