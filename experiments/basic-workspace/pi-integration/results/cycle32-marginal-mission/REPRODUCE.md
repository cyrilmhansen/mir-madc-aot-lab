# Reproduction

This Cycle 32 investigation deliberately stops before mission execution; it does not provide a replay or oracle command because no Cycle 32 operation stream was created.

At the baseline commit, the audit's line counts can be reproduced with:

```sh
find experiments/basic-workspace/basic_workspace -maxdepth 1 -type f -name '*.py' -print0 | xargs -0 wc -l
wc -l experiments/basic-workspace/pi-integration/gateway.py \
  experiments/basic-workspace/pi-integration/transaction_kernel.py \
  experiments/basic-workspace/pi-integration/cycle19_gateway.py \
  experiments/basic-workspace/pi-integration/cycle20_gateway.py \
  experiments/basic-workspace/pi-integration/cycle25_gateway.py \
  experiments/basic-workspace/pi-integration/cycle29_gateway.py \
  experiments/basic-workspace/basic_workspace/portable_replay.py
```

The full regression command is in `REGRESSION.md`. Existing Cycle 23 production TypeScript-to-JSONL preflight evidence and its command are in the Cycle 31 report/reproduction files; those checks exercise their historical creation and maintenance fixtures and do not authorize the Cycle 32 contract.
