# Reproduce Cycle40

From the repository root, with Python, Bun and the configured MIR interpreter/JIT available:

```sh
python experiments/basic-workspace/pi-integration/cycle40_generated_production.py \
  --output experiments/basic-workspace/pi-integration/results/cycle40-generated-production-fuzzing/reproduction-16 \
  --count 16
python experiments/basic-workspace/pi-integration/cycle40_generated_production.py \
  --output experiments/basic-workspace/pi-integration/results/cycle40-generated-production-fuzzing/reproduction-seed-140001 \
  --count 8 --seed-offset 100000
python experiments/basic-workspace/pi-integration/cycle40_generated_production.py \
  --output experiments/basic-workspace/pi-integration/results/cycle40-generated-production-fuzzing/reproduction-leaf-rename \
  --count 1 --start-index 3 --seed-offset 200000 --rename-index 2
```

The checked-in `attempt-07` is the primary run with creation and continuation tamper controls. `attempt-05` is the second eight-seed production run. `attempt-01` and `attempt-02` preserve two adapter wiring failures; `attempt-03` is the first successful single case; `attempt-04` preserves the initial 16-case run; `attempt-06` is a one-case verifier-control check. The rerun commands refuse to overwrite nonempty output directories.

Focused generator tests:

```sh
pytest -q experiments/basic-workspace/tests/test_cycle40_generated_production.py
python experiments/basic-workspace/pi-integration/cycle40_reduce_production_rejection.py \
  --output experiments/basic-workspace/pi-integration/results/cycle40-generated-production-fuzzing/reducer-reproduction
```
