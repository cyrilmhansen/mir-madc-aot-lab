#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
MIR="$LAB/madc/third_party/mir"
LIB="$LAB/madc/obj/mir/host/libmir.a"
CC="${CC:-cc}"
OUT="$HERE/native/build/mir-worker"
[[ -f "$MIR/mir.h" ]] || { echo "pinned MIR headers missing: $MIR" >&2; exit 2; }
[[ -f "$LIB" ]] || { echo "pinned MIR library missing: $LIB (build MADC/MIR first)" >&2; exit 2; }
mkdir -p "$(dirname "$OUT")"
"$CC" -std=gnu11 -O2 -Wall -Wextra -I "$MIR" \
  "$HERE/native/mir_worker.c" "$LIB" -lm -ldl -lpthread \
  -Wl,--no-undefined -o "$OUT"
printf 'built %s\n' "$OUT"
