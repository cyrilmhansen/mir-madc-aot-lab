#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
OUT="$HERE/build/mir-objects-to-shared"
LIB="$LAB/madc/obj/mir/host/libmir.a"
mkdir -p "$HERE/build"
cc -std=gnu11 -O2 -Wall -Wextra -Werror \
  -I "$LAB/madc/third_party/mir" "$HERE/src/mir-objects-to-shared.c" \
  "$LIB" -lm -ldl -lpthread -o "$OUT"
echo "$OUT"
