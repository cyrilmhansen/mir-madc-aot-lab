#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
REV=54fa3e409224bbc6ffdbc421a80f02ff76f76ce6
ROOT="$LAB/vendor/mir-upstream-$REV"
SOURCE="$HERE/tests/shared/libbasicdemo.bas"
OUT="$HERE/results/shared"
SO="$OUT/libbasicdemo.so"
DIRECT_SO="$OUT/libbasicdemo-direct.so"
MIR="$OUT/libbasicdemo.mir"
OBJ="$OUT/libbasicdemo.o"
TOOL="$($HERE/scripts/build-tools.sh)"
mkdir -p "$OUT"

"$HERE/scripts/build-baseline.sh" >/dev/null
"$HERE/scripts/build-shared.sh" "$SOURCE" "$SO" \
  --export SQUARE --export ADD --export STRLEN --export REPORT \
  > "$OUT/build-gcc-shared.log" 2>&1

"$ROOT/build/basic/basicc" "$SOURCE" > "$OUT/oracle.interp.out"
"$ROOT/build/basic/basicc" -j "$SOURCE" > "$OUT/oracle.jit.out"
cmp "$OUT/oracle.interp.out" "$OUT/oracle.jit.out"
cmp "$OUT/oracle.interp.out" "$HERE/tests/shared/expected.out"

readelf -h "$SO" | grep -q 'Type:.*DYN (Shared object file)'
readelf -h "$SO" | grep -q 'Machine:.*X86-64'
if readelf -d "$SO" | grep -q TEXTREL; then echo 'unexpected shared-library TEXTREL' >&2; exit 1; fi
! nm -D --defined-only "$SO" | grep -Eq 'main|basic_|MIR_|MIR_gen'
for sym in SQUARE ADD STRLEN REPORT; do nm -D --defined-only "$SO" | grep -Eq " T $sym$"; done
! nm -D --defined-only "$SO" | grep -Eq 'SQUARE_p|ADD_p|STRLEN_p|REPORT_p'
ldd -r "$SO" > "$OUT/ldd-r.txt" 2>&1
! grep -q 'undefined symbol' "$OUT/ldd-r.txt"

cc -O2 -Wall -Wextra -Werror "$HERE/tests/shared/shared-client.c" -ldl -lm \
  -o "$OUT/shared-client"
"$OUT/shared-client" "$SO" > "$OUT/client.out"
printf '12.5\nPASS: dlopen/dlsym/dlclose, reload, numeric ABI and string input\n' > "$OUT/client.expected"
cmp "$OUT/client.out" "$OUT/client.expected"

cc -O2 -Wall -Wextra -Werror -DBASIC_DEMO_DIRECT \
  "$HERE/tests/shared/shared-client.c" -L"$OUT" -Wl,-rpath,"$OUT" -lbasicdemo -lm -ldl \
  -o "$OUT/direct-client"
"$OUT/direct-client" > "$OUT/direct-client.out"
printf '12.5\nPASS: direct ELF link to BASIC exports\n' > "$OUT/direct-client.expected"
cmp "$OUT/direct-client.out" "$OUT/direct-client.expected"

# Export selection is opt-in and rejects missing functions / non-C signatures.
"$TOOL" --export SQUARE "$MIR" "$OUT/square-only.o" > /dev/null 2> "$OUT/square-only.err"
nm -g --defined-only "$OUT/square-only.o" | grep -Eq ' T SQUARE$'
! nm -g --defined-only "$OUT/square-only.o" | grep -Eq ' T (ADD|STRLEN|REPORT|main)$'
if "$TOOL" --export NO_SUCH_BASIC_FUNCTION "$MIR" "$OUT/missing-export.o" \
  > /dev/null 2> "$OUT/missing-export.err"; then exit 1; fi
grep -q 'not defined in MIR input' "$OUT/missing-export.err"
if "$TOOL" --export main "$MIR" "$OUT/unsupported-export.o" \
  > /dev/null 2> "$OUT/unsupported-export.err"; then exit 1; fi
grep -q 'unsupported result type' "$OUT/unsupported-export.err"

# Exercise the maintained MIR direct shared-image writer independently. Only
# pure arithmetic exports are called; the full MIR module still carries weak,
# unused BASIC runtime imports in its dynamic symbol table.
"$TOOL" --export SQUARE --export ADD --direct-shared "$MIR" "$DIRECT_SO" \
  > "$OUT/direct-emitter.out" 2> "$OUT/direct-emitter.err"
readelf -h "$DIRECT_SO" | grep -q 'Type:.*DYN (Shared object file)'
if readelf -d "$DIRECT_SO" | grep -q TEXTREL; then exit 1; fi
cc -O2 -Wall -Wextra -Werror "$HERE/tests/shared/pure-dso-client.c" -ldl -lm \
  -o "$OUT/pure-dso-client"
"$OUT/pure-dso-client" "$DIRECT_SO" > "$OUT/direct-emitter-client.out"
grep -q '^PASS:' "$OUT/direct-emitter-client.out"
! nm -D "$DIRECT_SO" | grep -Eq 'MIR_|MIR_gen'

"$HERE/scripts/validate.sh" > "$OUT/aot-regression.log" 2>&1
printf 'PASS: shared GCC ELF ABI, selected exports, dlopen/direct C clients, and direct MIR pure-function image\n'
