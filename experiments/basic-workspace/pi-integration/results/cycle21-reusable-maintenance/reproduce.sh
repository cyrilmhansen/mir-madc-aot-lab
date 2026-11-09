#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../../../.."
RUN_DIR=$(mktemp -d /var/tmp/cycle21-reproduce-XXXXXX)
trap 'rm -rf "$RUN_DIR"' EXIT
python3 experiments/basic-workspace/pi-integration/run_cycle20.py \
  --output "$RUN_DIR/schema-preflight" \
  --contract experiments/basic-workspace/pi-integration/contracts/numeric-edit/cycle21-is-passing-threshold40.json \
  --baseline-stream experiments/basic-workspace/pi-integration/results/cycle20b-semantic-edit-recovery/real-agent-02/constructive-operations.json \
  --baseline-history experiments/basic-workspace/pi-integration/results/cycle20b-semantic-edit-recovery/real-agent-02/history.jsonl \
  --baseline-validation experiments/basic-workspace/pi-integration/results/cycle20b-semantic-edit-recovery/real-agent-02/validation.json \
  --preflight-only
python3 experiments/basic-workspace/pi-integration/cycle21_preflight.py \
  --output "$RUN_DIR/dispatch-preflight" \
  --pi-schema-dir "$RUN_DIR/schema-preflight"
python3 -m unittest discover -s experiments/basic-workspace/tests -v
python3 experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/pi-integration/results/cycle21-reusable-maintenance/real-agent-01
