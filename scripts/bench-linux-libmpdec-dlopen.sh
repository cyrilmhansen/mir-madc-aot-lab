#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
BASE="$ROOT/results/linux-x86_64-native/libmpdec-cycle5"
LIB="$ROOT/vendor/mpdecimal-cycle5-gcc-uint128/libmpdec/libmpdec.so"
MADCLIB="$BASE/madc-uint128-corrected/libmpdec-madc.so"
RUNTIME="$ROOT/madc/lib/libmadc.so"
BIN="$BASE/libmpdec-dlopen-bench"
LOG="$BASE/logs"
mkdir -p "$LOG"

gcc -O2 -std=c99 -I "$ROOT/vendor/mpdecimal-cycle5-gcc-uint128/libmpdec" \
  "$ROOT/src/clients/libmpdec_dlopen_bench.c" -ldl -o "$BIN"

for variant in gcc-uint128 madc-uint128; do
  if [ "$variant" = gcc-uint128 ]; then
    lib="$LIB"
    args=("$lib")
  else
    lib="$MADCLIB"
    args=("$lib" "$RUNTIME")
  fi
  "$BIN" "${args[@]}" > "$LOG/dlopen-$variant-warmup.log"
  runs="$LOG/dlopen-$variant-runs.txt"
  csv="$BASE/dlopen-$variant.csv"
  : > "$runs"
  printf 'rep,load_ns,operation_ns,result\n' > "$csv"
  rep=1
  while [ "$rep" -le 30 ]; do
    "$BIN" "${args[@]}" >> "$runs"
    rep=$((rep + 1))
  done
  awk -v csv="$csv" '
    match($0, /load_ns=[0-9]+/) { load=substr($0, RSTART+8, RLENGTH-8) }
    match($0, /operation_ns=[0-9]+/) { op=substr($0, RSTART+13, RLENGTH-13) }
    match($0, /result=[0-9]+/) { result=substr($0, RSTART+7, RLENGTH-7) }
    { printf "%d,%s,%s,%s\n", NR, load, op, result >> csv }
  ' "$runs"
done
