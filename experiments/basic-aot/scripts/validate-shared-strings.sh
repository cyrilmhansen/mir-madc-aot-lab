#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
REV=54fa3e409224bbc6ffdbc421a80f02ff76f76ce6
ROOT="$LAB/vendor/mir-upstream-$REV"
SOURCE="$HERE/tests/shared/libbasicdemo-strings.bas"
OUT="$HERE/results/shared"
SO="$OUT/libbasicdemo-strings.so"
TEST_SO="$OUT/libbasicdemo-strings-test.so"
ASAN_SO="$OUT/libbasicdemo-strings-asan.so"

mkdir -p "$OUT"
"$HERE/scripts/build-baseline.sh" >/dev/null
"$ROOT/build/basic/basicc" "$SOURCE" > "$OUT/strings-oracle.interp.out"
"$ROOT/build/basic/basicc" -j "$SOURCE" > "$OUT/strings-oracle.jit.out"
cmp "$OUT/strings-oracle.interp.out" "$OUT/strings-oracle.jit.out"
cmp "$OUT/strings-oracle.interp.out" "$HERE/tests/shared/strings-expected.out"

exports=(
  --string-export BASIC_LITERAL=LITERAL$:p:pool
  --string-export BASIC_ECHO=ECHO$:p:pool
  --string-export BASIC_LOCAL=LOCAL$:p:pool
  --string-export BASIC_CONCAT=CONCAT$:p,p:pool
  --string-export BASIC_UPPER=UPPERTEST$:p:pool
  --string-export BASIC_EMPTY=EMPTY$:p:pool
  --string-export BASIC_BORROWED=FNBORROWED$:p:borrowed
)
"$HERE/scripts/build-shared.sh" "$SOURCE" "$SO" "${exports[@]}" \
  > "$OUT/build-strings.log" 2>&1

readelf -h "$SO" | grep -q 'Type:.*DYN (Shared object file)'
if readelf -d "$SO" | grep -q TEXTREL; then echo 'unexpected TEXTREL' >&2; exit 1; fi
for sym in BASIC_LITERAL BASIC_ECHO BASIC_LOCAL BASIC_CONCAT BASIC_UPPER BASIC_EMPTY BASIC_BORROWED basic_module_init basic_module_fini basic_string_free; do
  nm -D --defined-only "$SO" | grep -Eq " T $sym$"
done
! nm -D --defined-only "$SO" | grep -Eq 'LITERAL\$|UPPERTEST\$|MIR_|basic_alloc|basic_free'
ldd -r "$SO" > "$OUT/strings-ldd-r.txt" 2>&1
! grep -q 'undefined symbol' "$OUT/strings-ldd-r.txt"

cc -std=c11 -O2 -Wall -Wextra -Werror -I "$HERE/include" \
  "$HERE/tests/shared/direct-strings-client.c" -L"$OUT" -Wl,-rpath,"$OUT" \
  -lbasicdemo-strings -o "$OUT/direct-strings-client"
"$OUT/direct-strings-client" > "$OUT/direct-strings-client.out"
grep -qx 'PASS: direct link string wrapper' "$OUT/direct-strings-client.out"

BASIC_SHARED_TESTING=1 "$HERE/scripts/build-shared.sh" "$SOURCE" "$TEST_SO" "${exports[@]}" \
  > "$OUT/build-strings-test-hook.log" 2>&1
cc -std=c11 -O2 -Wall -Wextra -Werror -I "$HERE/include" \
  "$HERE/tests/shared/shared-strings-client.c" -ldl \
  -o "$OUT/shared-strings-client"
"$OUT/shared-strings-client" "$TEST_SO" > "$OUT/shared-strings-client.out"

ASAN_FLAGS='-fsanitize=address,undefined -fno-omit-frame-pointer'
BASIC_RUNTIME_BUILD_DIR="$HERE/runtime/shared-strings-asan-build" \
BASIC_RUNTIME_LIB="$HERE/runtime/libbasicrt-shared-strings-asan.a" \
BASIC_RUNTIME_CFLAGS="$ASAN_FLAGS" \
BASIC_SHARED_CFLAGS="$ASAN_FLAGS" BASIC_SHARED_LDFLAGS="$ASAN_FLAGS" \
BASIC_SHARED_TESTING=1 "$HERE/scripts/build-shared.sh" "$SOURCE" "$ASAN_SO" "${exports[@]}" \
  > "$OUT/build-strings-asan.log" 2>&1
cc -std=c11 -O1 -g -Wall -Wextra -Werror $ASAN_FLAGS -I "$HERE/include" \
  "$HERE/tests/shared/shared-strings-client.c" -ldl -o "$OUT/shared-strings-client-asan"
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  "$OUT/shared-strings-client-asan" "$ASAN_SO" > "$OUT/shared-strings-asan.out"

cc -std=c11 -O2 -Wall -Wextra -Werror \
  "$HERE/tests/shared/bench-strings-client.c" -ldl -o "$OUT/bench-strings-client"
python3 "$HERE/scripts/measure-shared-strings.py" 100000 > "$OUT/string-measurements-summary.json"

printf 'PASS: BASIC string-return wrappers, C ownership contract, direct link, dlopen, stress and ASan/UBSan\n'
