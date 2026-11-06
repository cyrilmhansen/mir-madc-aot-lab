#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
UPSTREAM_MIR_ROOT="${UPSTREAM_MIR_ROOT:-$LAB/vendor/mir-upstream-54fa3e409224bbc6ffdbc421a80f02ff76f76ce6}"
BASIC_ROOT="$HERE/upstream/basic"
BASIC_C="${BASIC_C:-$UPSTREAM_MIR_ROOT/build/basic/basicc}"
MADC_MIR_LIB="${MADC_MIR_LIB:-$LAB/madc/obj/mir/host/libmir.a}"
RESULTS="$HERE/results/aot"

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 PROGRAM_NAME [input-file]" >&2
  exit 2
fi
name="$1"
input="${2:-}"
src="$BASIC_ROOT/tests/programs/$name.bas"
mkdir -p "$RESULTS"
if [[ ! -f "$src" ]]; then
  echo "missing BASIC source: $src" >&2
  exit 2
fi

cc -O2 -I "$LAB/madc/third_party/mir" \
  "$HERE/src/mir-to-elf.c" "$MADC_MIR_LIB" -lm -ldl -lpthread \
  -o "$RESULTS/mir-to-elf"
"$BASIC_C" -S -o "$RESULTS/$name" "$src"
"$RESULTS/mir-to-elf" "$RESULTS/$name.mir" "$RESULTS/$name.o"

# --gc-sections keeps only runtime helpers referenced by this BASIC program.
# The remaining imports are libc/libm; MIR metaprogramming code is not linked.
cc -O2 -ffunction-sections -fdata-sections \
  -I "$LAB/madc/third_party/mir" \
  -I "$BASIC_ROOT/include" -I "$BASIC_ROOT/src" \
  -I "$BASIC_ROOT/src/vendor" -I "$BASIC_ROOT/src/vendor/kitty" \
  -I "$BASIC_ROOT/src/vendor/libdfp" -Wl,--gc-sections \
  "$RESULTS/$name.o" "$BASIC_ROOT/src/basic_runtime.c" \
  "$BASIC_ROOT/src/basic_pool.c" \
  "$BASIC_ROOT/src/vendor/kitty/kitty.c" \
  "$BASIC_ROOT/src/vendor/kitty/lodepng.c" -lm -o "$RESULTS/$name-native"

if [[ -n "$input" ]]; then
  "$RESULTS/$name-native" < "$input"
else
  "$RESULTS/$name-native"
fi
