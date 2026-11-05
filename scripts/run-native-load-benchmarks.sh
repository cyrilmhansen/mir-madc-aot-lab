#!/usr/bin/env bash
set -euo pipefail
LAB_ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
REPEATS=${REPEATS:-30}
ARTIFACTS="$LAB_ROOT/results/artifacts"
"$LAB_ROOT/scripts/run-correctness.sh"
DYLD_LIBRARY_PATH="$ARTIFACTS" "$ARTIFACTS/dlopen-client" \
  "$ARTIFACTS/libmir-sample.dylib" -n "$REPEATS" \
  > "$LAB_ROOT/results/macho-resident.csv"
python3 "$LAB_ROOT/scripts/bench_macho_load.py" \
  "$ARTIFACTS/dlopen-client" "$ARTIFACTS/libmir-sample.dylib" \
  "$LAB_ROOT/results/macho-new-process.csv" "$REPEATS"
