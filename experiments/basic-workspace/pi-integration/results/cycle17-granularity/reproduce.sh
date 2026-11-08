#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../../../../.." && pwd)
cd "$ROOT"

python3 -m unittest discover -s experiments/basic-workspace/tests -v
python3 experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/pi-integration/results/cycle17-granularity/arm-a-atomic
python3 experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/pi-integration/results/cycle17-granularity/arm-b-incremental
