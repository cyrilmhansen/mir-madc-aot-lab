#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
ARCHIVE="$ROOT/downloads/decNumber-icu-368.zip"
EXPECTED_MD5=ba48a64b619f249772d5ad56f510146f
SOURCE="$ROOT/results/linux-x86_64/vendor/decNumber-3.68-original/decNumber"
GCC_OUT="$ROOT/results/linux-x86_64/artifacts/decnumber-gcc"
MADC_OUT="$ROOT/results/linux-x86_64/artifacts/decnumber-madc"
LOG="$ROOT/results/linux-x86_64/logs"

if [ ! -f "$ARCHIVE" ]; then
  curl -fL --retry 3 https://ftp.math.utah.edu/pub/mathcw/decNumber/decNumber-icu-368.zip -o "$ARCHIVE"
fi
actual=$(md5sum "$ARCHIVE" | awk '{print $1}')
[ "$actual" = "$EXPECTED_MD5" ] || { echo "decNumber archive MD5 mismatch: $actual" >&2; exit 1; }
if [ ! -d "$SOURCE" ]; then
  mkdir -p "$(dirname "$SOURCE")"
  unzip -q "$ARCHIVE" -d "$(dirname "$SOURCE")"
fi
mkdir -p "$GCC_OUT" "$MADC_OUT" "$LOG"
cd "$SOURCE"

build_gcc() {
  local n=$1; shift
  gcc -O2 -std=c99 -o "$GCC_OUT/example$n" "$@" \
    2>"$LOG/decnumber-gcc-example$n-build.log"
}
build_madc() {
  local n=$1; shift
  "$ROOT/madc/bin/madc" --no-forest-bind -fno-eval-shims -O2 -std=c99 \
    -o "$MADC_OUT/example$n" "$@" \
    >"$LOG/decnumber-madc-example$n-build.log" 2>&1
}

build_gcc 1 example1.c decNumber.c decContext.c
build_gcc 2 example2.c decNumber.c decContext.c
build_gcc 3 example3.c decNumber.c decContext.c
build_gcc 4 example4.c decNumber.c decContext.c
build_gcc 5 example5.c decNumber.c decContext.c decimal64.c
build_gcc 6 example6.c decNumber.c decContext.c decPacked.c
build_gcc 7 example7.c decContext.c decQuad.c
build_gcc 8 example8.c decContext.c decQuad.c decNumber.c decimal128.c decimal64.c

declare -A units args
units[1]='example1.c decNumber.c decContext.c'; args[1]='1.23 1.27'
units[2]='example2.c decNumber.c decContext.c'; args[2]='10000 5.0 7'
units[3]='example3.c decNumber.c decContext.c'; args[3]='10000 5.0 7'
units[4]='example4.c decNumber.c decContext.c'; args[4]='1.23 1.27'
units[5]='example5.c decNumber.c decContext.c decimal64.c'; args[5]='123.45'
units[6]='example6.c decNumber.c decContext.c decPacked.c'; args[6]=''
units[7]='example7.c decContext.c decQuad.c'; args[7]='1.23 1.27'
units[8]='example8.c decContext.c decQuad.c decNumber.c decimal128.c decimal64.c'; args[8]='1.23 5'

for n in {1..8}; do
  # Word-splitting here is intentional: unit lists and example arguments above
  # are fixed literals from the upstream readme.
  build_madc "$n" ${units[$n]}
  "$GCC_OUT/example$n" ${args[$n]} >"$LOG/decnumber-example$n-gcc.log"
  LD_LIBRARY_PATH="$ROOT/madc/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    "$MADC_OUT/example$n" ${args[$n]} >"$LOG/decnumber-example$n-madc.log"
  cmp "$LOG/decnumber-example$n-gcc.log" "$LOG/decnumber-example$n-madc.log"
done
