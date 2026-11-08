# Pi integration experiment

Cycle 16 connects Pi to the existing Python semantic gateway and Cycle 15 browser viewer. Cycle 16B repairs the typed constructor schema and records one successful genuine retry. See [AUDIT.md](AUDIT.md) and [REPORT.md](REPORT.md) for the architecture and outcomes.

## Requirements

- Pi 1.5.0 or a version validated against the ExtensionAPI used here.
- The operator's ignored `~/.sushi/pi/models.json` must contain provider `sushi` and model `Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw`.
- Firefox is optional; it can open the live URL printed by the launcher.

The launcher copies only the selected model configuration into the ignored `.runtime/pi-config/` directory. That file is mode 0600. Do not commit `.runtime/`. The operator's global Pi settings are not edited. The model endpoint is not repeated here.

## Run

From the repository root:

```sh
python3 experiments/basic-workspace/pi-integration/run_cycle16.py \
  --preflight-only --output experiments/basic-workspace/pi-integration/results/preflight-01

python3 experiments/basic-workspace/pi-integration/run_cycle16.py \
  --output experiments/basic-workspace/pi-integration/results/real-pi-01 \
  --timeout 240 --open-browser
```

The first command checks Pi's configured model catalog and exact active tool inventory; it does not call the inference endpoint. The second command is the preserved Cycle 16 failure and must not be repeated into its output directory. Cycle 16B preflight and the single corrected retry are:

```sh
python3 experiments/basic-workspace/pi-integration/run_cycle16.py \
  --preflight-only --output experiments/basic-workspace/pi-integration/results/preflight-08

python3 experiments/basic-workspace/pi-integration/run_cycle16.py \
  --output experiments/basic-workspace/pi-integration/results/real-pi-02 \
  --timeout 180 --open-browser
```

Do not repeat the mission into either evidence directory. The actual result is recorded in the report. `tool-schemas.json` captures the JSON schemas Pi actually exposed; the Python gateway remains authoritative for validation and policy.

To inspect the original failure offline, open `results/real-pi-01/visual-replay-generic.html`. The successful retry is `results/real-pi-02/visual-replay-generic.html`; its commit and validation screenshots are in that directory. To serve a saved event stream again, use:

```sh
python3 experiments/basic-workspace/scripts/basic-visual.py live \
  experiments/basic-workspace/pi-integration/results/real-pi-01 --port 8765
```

The latter is playback of recorded evidence, not live agent activity. `pi-session-observed.jsonl` retains the user/model-visible message and tool events with model thinking-channel content removed and the local checkout path redacted. The complete local Pi session and its session directory are ignored because they contain private reasoning traces; raw provider usage and tool-call counts are summarized separately.

## Tests

```sh
python3 -m unittest experiments.basic-workspace.tests.test_pi_gateway -v
python3 -m unittest discover -s experiments/basic-workspace/tests -v
```
