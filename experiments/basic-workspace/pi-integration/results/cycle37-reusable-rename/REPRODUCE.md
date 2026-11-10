# Reproduction

Run from the repository root.

```bash
python3 experiments/basic-workspace/pi-integration/cycle37_preflight.py \
  --output experiments/basic-workspace/pi-integration/results/cycle37-reusable-rename/production-bridge-reproduced
python3 experiments/basic-workspace/pi-integration/cycle37_finalize_evidence.py \
  --bridge-dir production-bridge-reproduced
python3 -m unittest experiments.basic-workspace.tests.test_cycle37_reusable_rename \
  experiments.basic-workspace.tests.test_cycle26_semantic_rename \
  experiments.basic-workspace.tests.test_cycle36_verified_handoff -v
python3 -m unittest discover -s experiments/basic-workspace/tests -v
```

The production preflight is deterministic and does not launch Pi/Sushi. The archived successful production bridge evidence is `production-bridge-attempt-05/`. `cycle37_finalize_evidence.py` verifies the archived handoffs, replays every operation prefix, and performs a fresh host-only rename and validation for each mission. It does not infer missing historical evidence. The full suite command is included for reproducibility; its actual result is recorded in `REGRESSION.md`.
