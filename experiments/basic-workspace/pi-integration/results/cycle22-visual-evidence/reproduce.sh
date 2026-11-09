#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../../../../.." && pwd)
cd "$ROOT"
python3 experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/pi-integration/results/cycle20b-semantic-edit-recovery/real-agent-02 \
  --output-dir experiments/basic-workspace/pi-integration/results/cycle22-visual-evidence/cycle20b \
  --evidence-view experiments/basic-workspace/pi-integration/results/cycle22-visual-evidence/cycle20b-real-agent-02-evidence-view.json
python3 experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/pi-integration/results/cycle21-reusable-maintenance/real-agent-01 \
  --output-dir experiments/basic-workspace/pi-integration/results/cycle22-visual-evidence/cycle21 \
  --evidence-view experiments/basic-workspace/pi-integration/results/cycle22-visual-evidence/cycle21-real-agent-01-evidence-view.json
python3 -m unittest experiments.basic-workspace.tests.test_cycle22_visual_evidence -v
