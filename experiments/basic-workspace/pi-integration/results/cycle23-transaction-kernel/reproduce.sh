#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
python3 pi-integration/cycle23_transaction_preflight.py \
  --output pi-integration/results/cycle23-transaction-kernel/reproduced-preflight \
  --maintenance-schema-dir pi-integration/results/cycle21-reusable-maintenance/schema-preflight-02
python3 -m unittest discover -s tests -p 'test_cycle23_transaction_kernel.py' -v
