#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
ART="$ROOT/results/linux-x86_64-native/libmpdec-cycle5/inline-asm"
LOG="$ROOT/results/linux-x86_64-native/libmpdec-cycle5/logs"
SRC="$ROOT/src/clients/mpdecimal_inline_asm_min.c"
MADC="$ROOT/madc/bin/madc"
mkdir -p "$ART" "$LOG"

gcc -O2 -std=gnu11 "$SRC" -o "$ART/inline-asm-gcc"
clang -O2 -std=gnu11 "$SRC" -o "$ART/inline-asm-clang"

for compiler in gcc clang; do
  set +e
  "$ART/inline-asm-$compiler" >"$LOG/cycle5-inline-asm-$compiler.log" 2>&1
  status=$?
  set -e
  printf '%s\n' "$status" >"$LOG/cycle5-inline-asm-$compiler.status"
done
set +e
"$MADC" --no-config -c -O2 -std=gnu11 \
  -o "$ART/inline-asm-madc.o" "$SRC" \
  >"$LOG/cycle5-inline-asm-madc.log" 2>&1
madc_status=$?
set -e
printf '%s\n' "$madc_status" >"$LOG/cycle5-inline-asm-madc.status"
if [ "$madc_status" -eq 0 ] || \
   ! grep -qF 'non-empty GNU asm templates are not supported' \
     "$LOG/cycle5-inline-asm-madc.log"; then
  echo "MADC failed to reject unsupported inline asm" >&2
  exit 1
fi
for compiler in gcc clang; do
  if ! grep -qx 'high=0' "$LOG/cycle5-inline-asm-$compiler.log"; then
    echo "inline-asm result mismatch for $compiler" >&2
    exit 1
  fi
done
echo "GCC and Clang execute mulq correctly; MADC rejects the unsupported template."
