# Reproduction

From the repository root, the deterministic production-path preflight is:

```sh
python experiments/basic-workspace/pi-integration/run_cycle20.py \
  --output experiments/basic-workspace/pi-integration/results/cycle30-post-extraction-maintenance/pi-preflight-rerun-01 \
  --contract experiments/basic-workspace/pi-integration/results/cycle30-post-extraction-maintenance/mission-contract.json \
  --baseline-stream experiments/basic-workspace/pi-integration/results/cycle29-function-extraction/real-agent-01/constructive-operations.json \
  --baseline-history experiments/basic-workspace/pi-integration/results/cycle29-function-extraction/real-agent-01/history.jsonl \
  --baseline-validation experiments/basic-workspace/pi-integration/results/cycle29-function-extraction/real-agent-01/mission-2-validation-host.json \
  --preflight-only
python experiments/basic-workspace/pi-integration/cycle30_preflight.py \
  --output experiments/basic-workspace/pi-integration/results/cycle30-post-extraction-maintenance/production-bridge-preflight-rerun-01
```

The second command invokes the actual TypeScript handlers from the deterministic dispatch probe and talks to the Python JSONL gateway. It performs a disposable preview/commit/validation and is not model evidence.

The genuine run used the existing local Pi/Sushi configuration and one bounded session. To reproduce a new model experiment intentionally, use a fresh output directory (the recorded path is intentionally non-empty) and the same Cycle 20 runner arguments **without** `--preflight-only`. The mission prompt, raw Pi JSONL, lifecycle and gateway evidence are preserved in `real-agent-01/`; no automatic retry was used.

To regenerate the offline visual replay from recorded events:

```sh
python experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/pi-integration/results/cycle30-post-extraction-maintenance/real-agent-01
```

To run the Workspace suite:

```sh
python -m pytest -q experiments/basic-workspace/tests
```
