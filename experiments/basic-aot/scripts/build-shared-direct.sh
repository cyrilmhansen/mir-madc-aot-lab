#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
ROOT="$LAB/vendor/mir-upstream-54fa3e409224bbc6ffdbc421a80f02ff76f76ce6"
SOURCE="${1:-$HERE/tests/shared/libbasicdemo-direct.bas}"
OUTPUT="${2:-$HERE/results/shared/libbasicdemo-mir.so}"
OUTPUT="$(realpath -m "$OUTPUT")"
OUTDIR="$(dirname "$OUTPUT")"
REF="$OUTDIR/libbasicdemo-direct-gcc-reference.so"
BASE="$HERE/results/shared/libbasicdemo-direct"
WRAPPER="$HERE/results/shared/basic-shared-api-madc.o"

exports=(
  --export SQUARE --export ADD --export STRLEN --export REPORT
  --string-export BASIC_LITERAL=LITERAL$:p:pool
  --string-export BASIC_ECHO=ECHO$:p:pool
  --string-export BASIC_LOCAL=LOCAL$:p:pool
  --string-export BASIC_CONCAT=CONCAT$:p,p:pool
  --string-export BASIC_UPPER=UPPERTEST$:p:pool
  --string-export BASIC_EMPTY=EMPTY$:p:pool
  --string-export BASIC_BORROWED=FNBORROWED$:p:borrowed
)

mkdir -p "$OUTDIR" "$HERE/results/shared"
# This also generates the reproducible MIR ET_REL and the GCC-linked reference.
bash "$HERE/scripts/build-shared.sh" "$SOURCE" "$REF" "${exports[@]}"
numeric_prefix="$HERE/results/shared/libbasicdemo-numeric-only"
"$ROOT/build/basic/basicc" -S -o "$numeric_prefix" "$HERE/tests/shared/direct-numeric.bas"
tool="$(bash "$HERE/scripts/build-tools.sh")"
"$tool" --export SQUARE --export ADD --direct-shared \
  "$numeric_prefix.mir" "$OUTDIR/libbasicdemo-numeric-only-mir.so"
madc/bin/madc --no-config -fno-eval-shims -std=gnu11 -fPIC \
  -I "$ROOT/basic/include" -I "$ROOT/basic/src" \
  -c -o "$WRAPPER" "$HERE/results/shared/basic-shared-api.c"
bash "$HERE/scripts/build-runtime-shared-dso.sh" \
  "$HERE/runtime/libbasicrt-shared.a" "$BASE.o" "$WRAPPER" "$HERE/results/shared/libbasicrt.so"
bash "$HERE/scripts/build-mir-merge-tool.sh" >/dev/null

tool="$HERE/build/mir-objects-to-shared"
args=(--needed libbasicrt.so --needed libc.so.6 --needed libm.so.6 --runpath '$ORIGIN')
for name in 'CONCAT$' 'ECHO$' 'EMPTY$' 'FNBORROWED$' 'LITERAL$' 'LOCAL$' 'UPPERTEST$'; do
  args+=(--hide "$name")
done
for name in basic_concat basic_data_fini basic_data_init basic_enable_line_tracking \
            basic_free basic_len basic_print basic_print_str basic_set_line \
            basic_strdup basic_upper free malloc memcpy strlen; do
  args+=(--require "$name")
done
"$tool" "${args[@]}" "$OUTPUT" "$BASE.o" "$WRAPPER"
# RUNPATH is relative to the final DSO; install/copy the shared runtime beside it.
if [[ "$(realpath -m "$OUTDIR/libbasicrt.so")" != "$HERE/results/shared/libbasicrt.so" ]]; then
  cp "$HERE/results/shared/libbasicrt.so" "$OUTDIR/libbasicrt.so"
fi
printf 'GCC reference: %s\nDirect MIR DSO: %s\n' "$REF" "$OUTPUT"
