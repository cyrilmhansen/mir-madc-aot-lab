#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
OUT="$HERE/build/mir-to-elf"
LIB="$LAB/madc/obj/mir/host/libmir.a"
mkdir -p "$HERE/build"
if [[ ! -x "$OUT" || "$HERE/src/mir-to-elf.c" -nt "$OUT" || "$LIB" -nt "$OUT" || \
      "$LAB/madc/third_party/mir/mir.h" -nt "$OUT" || "$LAB/madc/third_party/mir/mir-gen.h" -nt "$OUT" ]]; then
  cc -O2 -I "$LAB/madc/third_party/mir" "$HERE/src/mir-to-elf.c" \
    "$LIB" -lm -ldl -lpthread -o "$OUT"
fi
echo "$OUT"
