#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
ART="$ROOT/results/linux-x86_64/artifacts/cycle4-mpdecimal"
LOG="$ROOT/results/linux-x86_64/logs"
SRC="$ROOT/src/clients/mpdecimal_inline_asm_min.c"
MADC="$ROOT/madc/bin/madc"
mkdir -p "$ART" "$LOG"

gcc -O2 "$SRC" -o "$ART/inline-asm-gcc"
clang -O2 "$SRC" -o "$ART/inline-asm-clang"
"$MADC" -c -O2 -std=c99 -o "$ART/inline-asm-madc.o" "$SRC"
gcc "$ART/inline-asm-madc.o" -L"$ROOT/madc/lib" -lmadc \
  -Wl,-rpath,"$ROOT/madc/lib" -ldl -lpthread \
  -o "$ART/inline-asm-madc-aot"

for compiler in gcc clang madc-aot; do
  set +e
  "$ART/inline-asm-$compiler" >"$LOG/cycle4-inline-asm-$compiler.log" 2>&1
  status=$?
  set -e
  printf '%s\n' "$status" >"$LOG/cycle4-inline-asm-$compiler.status"
done
for compiler in gcc clang madc-aot; do
  if ! grep -qx 'high=0' "$LOG/cycle4-inline-asm-$compiler.log"; then
    echo "inline-asm result mismatch for $compiler" >&2
    exit 1
  fi
done
echo "inline-asm semantics match GCC and Clang"
