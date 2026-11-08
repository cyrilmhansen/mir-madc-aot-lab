# Reproduction and artifact access

Run from the repository root.

## Deterministic regression

```sh
cd experiments/basic-workspace
python3 -m unittest tests.test_pi_composition -v
python3 -m unittest discover -s tests
```

Recorded result: focused Cycle 18 tests, 6 passed; full Workspace suite, 159 passed.

## Pi/model preflight without inference

The captured preflights are in `provider-preflight-atomic/` and `provider-preflight-incremental/`. They inspected Pi's configured model inventory and actual active tool schemas but made no inference request. To run the same bounded preflight again:

```sh
PI_CODING_AGENT_DIR="$HOME/.sushi/pi" python3 experiments/basic-workspace/pi-integration/run_cycle16.py \
  --mission-kind category --arm atomic \
  --registered-plan experiments/basic-workspace/pi-integration/results/cycle18-composition/pre-registration.json \
  --timeout 180 --preflight-only \
  --output experiments/basic-workspace/pi-integration/results/cycle18-composition/new-preflight-atomic
```

Change `--arm atomic` and the output directory to `incremental` for the second tool inventory. The runner reads provider endpoint/model settings from the local ignored Pi configuration; no endpoint or credential is stored in this campaign.

## Recorded sessions

The genuine model sessions have already been run once each. Their immutable evidence is `arm-a-atomic/pi-session.jsonl` and `arm-b-incremental/pi-session.jsonl`, with corresponding Pi lifecycle and Python gateway journals. Do not rerun those output directories: the runner rejects non-empty destinations. A future intentional repeat must use new output directories and must be labeled as another trial.

## Offline replay

```sh
python3 experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/pi-integration/results/cycle18-composition/arm-a-atomic
python3 experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/pi-integration/results/cycle18-composition/arm-b-incremental
```

Open the generated `visual-replay-generic.html` in a browser. The atomic arm includes one rejection presentation event adapted from the genuine Pi tool error; the raw Pi session and gateway traces remain untouched. The incremental replay displays only its actual draft-start and timeout observations.
