#!/usr/bin/env bash
set -euo pipefail
LAB_ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
MADC_DIR=${MADC_DIR:-"$LAB_ROOT/madc"}
SOURCE=${MPDECIMAL_SOURCE:-"$LAB_ROOT/vendor/mpdecimal-4.0.1-c-only"}
mkdir -p "$LAB_ROOT/results/logs" "$LAB_ROOT/results/artifacts"
cd "$SOURCE/libmpdec"
if "$MADC_DIR/bin/madc" -c -O2 -I. \
  -o "$LAB_ROOT/results/artifacts/mpdecimal-context.o" context.c \
  > "$LAB_ROOT/results/logs/mpdecimal-madc-context.log" 2>&1; then
  printf 'PASS\n' > "$LAB_ROOT/results/logs/mpdecimal-madc-context.status"
else
  printf 'FRONTEND_FAIL\n' > "$LAB_ROOT/results/logs/mpdecimal-madc-context.status"
fi
cat "$LAB_ROOT/results/logs/mpdecimal-madc-context.status"
