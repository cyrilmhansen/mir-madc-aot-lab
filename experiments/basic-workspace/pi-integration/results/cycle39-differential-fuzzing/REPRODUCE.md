# Reproduction

From repository root:

```bash
python3 experiments/basic-workspace/pi-integration/cycle39_differential_campaign.py --output experiments/basic-workspace/pi-integration/results/cycle39-differential-fuzzing/semantic-final --limit 120
python3 experiments/basic-workspace/pi-integration/cycle39_production_bridge.py --output experiments/basic-workspace/pi-integration/results/cycle39-differential-fuzzing/production-final
python3 experiments/basic-workspace/pi-integration/cycle39_metamorphic_campaign.py --output experiments/basic-workspace/pi-integration/results/cycle39-differential-fuzzing/metamorphic-results.json --count 28
python3 experiments/basic-workspace/pi-integration/cycle39_performance.py --output experiments/basic-workspace/pi-integration/results/cycle39-differential-fuzzing/performance-confirmatory.json --production-summary experiments/basic-workspace/pi-integration/results/cycle39-differential-fuzzing/production-final/production-bridge-summary.json --repetitions 7
python3 experiments/basic-workspace/pi-integration/cycle39_differential_campaign.py --output experiments/basic-workspace/pi-integration/results/cycle39-differential-fuzzing/alternative-run --limit 14 --seed-offset 100000
python3 experiments/basic-workspace/pi-integration/cycle39_finalize_evidence.py
python3 -m unittest discover -s experiments/basic-workspace/tests -v
```

The production runner requires the repository's existing `bun`, TypeBox/Pi package path and MIR worker build. It does not invoke Pi or a model. Each command refuses to overwrite its output path; use a new named attempt directory for a rerun and preserve prior attempts.

Preliminary generator calibration outputs are deliberately preserved under `preflight-fast*` and `semantic-run-*`. `performance-results.json` is exploratory; `performance-confirmatory.json` applies the threshold registered in the campaign configuration.
