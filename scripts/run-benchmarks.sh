#!/usr/bin/env bash
set -euo pipefail
LAB_ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
MADC_DIR=${MADC_DIR:-"$LAB_ROOT/madc"}
REPEATS=${REPEATS:-30}
scripts_dir="$LAB_ROOT/scripts"
mkdir -p "$LAB_ROOT/results/artifacts/corpora" "$LAB_ROOT/results/logs"
if [ ! -x "$LAB_ROOT/results/artifacts/libmir-smoke" ]; then
  "$scripts_dir/build-microbench.sh"
fi
python3 "$LAB_ROOT/scripts/bench_corpora.py" \
  "$LAB_ROOT/results/artifacts/libmir-smoke" \
  "$LAB_ROOT/results/artifacts/corpora" \
  "$LAB_ROOT/results/timings.csv" \
  "$LAB_ROOT/results/sizes.csv" "$REPEATS"
