# Reproduce Cycle41

From the repository root, with the same configured Python/BASIC test environment and `bun` available for the real TypeScript/JSONL preflights:

```sh
python -m pytest -q experiments/basic-workspace/tests/test_cycle41_finite_oracle.py
python experiments/basic-workspace/pi-integration/cycle41_v3_production_campaign.py \
  --output experiments/basic-workspace/pi-integration/results/cycle41-finite-oracle-coverage/reproduction-primary \
  --count 16 --seed-offset 810000
python experiments/basic-workspace/pi-integration/cycle41_v3_production_campaign.py \
  --output experiments/basic-workspace/pi-integration/results/cycle41-finite-oracle-coverage/reproduction-secondary \
  --count 8 --seed-offset 910000
python experiments/basic-workspace/pi-integration/cycle41_v3_benchmark.py \
  --output experiments/basic-workspace/pi-integration/results/cycle41-finite-oracle-coverage/reproduction-benchmark
python -m pytest -q experiments/basic-workspace/tests
```

Campaign outputs refuse to overwrite nonempty directories. The production runs create every workflow in a fresh directory and call existing Cycle19, Cycle37 and Cycle20 preflight/bridge implementations. Generated specifications, exact contracts, bridge logs, snapshots, observations and replay evidence are kept with each case. Seeds and selection rules are in `campaign-config.json` and `campaign-amendment-three-targets.json`.

The isolated benchmark requires the historical 16-value Cycle34 corpus as the base so the unchanged v1/v2 baseline attestation can compare its complete recorded observations. It extends that same corpus to 32 and 64 values. Each measurement mode uses five fresh gateways.
