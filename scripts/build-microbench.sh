#!/usr/bin/env bash
set -euo pipefail
LAB_ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
MADC_DIR=${MADC_DIR:-"$LAB_ROOT/madc"}
mkdir -p "$LAB_ROOT/results/logs" "$LAB_ROOT/results/artifacts"
cc=${CC:-clang}
"$cc" -std=c11 -O2 -Wall -Wextra -Werror \
  -I"$MADC_DIR/third_party/mir" \
  "$LAB_ROOT/src/microbench/libmir_smoke.c" \
  "$MADC_DIR/obj/mir/host/libmir.a" -lm \
  -o "$LAB_ROOT/results/artifacts/libmir-smoke"
cd "$LAB_ROOT/results/artifacts"
./libmir-smoke write program.bmir | tee "$LAB_ROOT/results/logs/libmir-jit.log"
./libmir-smoke read program.bmir | tee "$LAB_ROOT/results/logs/libmir-bmir-jit.log"
