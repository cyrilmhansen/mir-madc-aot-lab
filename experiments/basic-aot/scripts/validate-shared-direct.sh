#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
OUT="$HERE/results/shared"
DIRECT="$OUT/libbasicdemo-mir.so"
REFERENCE="$OUT/libbasicdemo-direct-gcc-reference.so"
NUMERIC_ONLY="$OUT/libbasicdemo-numeric-only-mir.so"
mkdir -p "$OUT"

bash "$HERE/scripts/build-shared-direct.sh" \
  "$HERE/tests/shared/libbasicdemo-direct.bas" "$DIRECT" \
  > "$OUT/build-direct.log" 2>&1

readelf -h "$DIRECT" | grep -q 'Class:.*ELF64'
readelf -h "$DIRECT" | grep -q 'Type:.*DYN (Shared object file)'
readelf -h "$DIRECT" | grep -q 'Machine:.*X86-64'
! readelf -d "$DIRECT" | grep -q TEXTREL
readelf -d "$DIRECT" | grep -Fq 'Library runpath: [$ORIGIN]'
readelf -d "$DIRECT" | grep -Fq 'Shared library: [libbasicrt.so]'
readelf -l "$DIRECT" | grep -q GNU_RELRO
readelf -lW "$DIRECT" | grep -Eq 'GNU_STACK.*RW +0x'
! readelf -d "$DIRECT" | grep -Eq '\((INIT|FINI|INIT_ARRAY|FINI_ARRAY)\)'
! readelf -d "$DIRECT" | grep -Eqi 'mir|madc'
! nm -D "$DIRECT" | grep -Eq ' [TW] (MIR_|mir_)'
for sym in 'UPPERTEST$' 'LITERAL$' 'ECHO$' 'LOCAL$' 'CONCAT$' 'EMPTY$' 'FNBORROWED$'; do
  readelf -Ws "$DIRECT" | grep -F "GLOBAL HIDDEN" | grep -Fq "$sym"
done
for sym in SQUARE ADD STRLEN REPORT BASIC_UPPER BASIC_LITERAL BASIC_ECHO BASIC_LOCAL \
           BASIC_CONCAT BASIC_EMPTY BASIC_BORROWED basic_string_free; do
  readelf -Ws "$DIRECT" | grep -Eq "GLOBAL +DEFAULT +[0-9]+ $sym$"
done
for sym in basic_len basic_print basic_free malloc memcpy strlen; do
  readelf -Ws "$DIRECT" | grep -Eq "GLOBAL +DEFAULT +UND $sym$"
done
readelf -h "$NUMERIC_ONLY" | grep -q 'Type:.*DYN (Shared object file)'
! readelf -d "$NUMERIC_ONLY" | grep -q libbasicrt
! nm -D --defined-only "$NUMERIC_ONLY" | grep -Eq ' [TW] (main|REPORT|STRLEN|BASIC_)'
for sym in SQUARE ADD; do nm -D --defined-only "$NUMERIC_ONLY" | grep -Eq " T $sym$"; done
! objdump -d --disassemble=SQUARE "$NUMERIC_ONLY" | grep -Eq '\bcall[q]?[[:space:]]'
! objdump -d --disassemble=ADD "$NUMERIC_ONLY" | grep -Eq '\bcall[q]?[[:space:]]'

cc -std=c11 -O2 -Wall -Wextra -Werror \
  "$HERE/tests/shared/direct-numeric-client.c" -L"$OUT" -Wl,-rpath,'$ORIGIN' \
  -lbasicdemo-numeric-only-mir -o "$OUT/direct-numeric-client"
"$OUT/direct-numeric-client" > "$OUT/direct-numeric-client.out"
cc -std=c11 -O2 -Wall -Wextra -Werror \
  "$HERE/tests/shared/numeric-dlopen-client.c" -ldl -lm -o "$OUT/numeric-dlopen-client"
"$OUT/numeric-dlopen-client" "$NUMERIC_ONLY" > "$OUT/numeric-dlopen-client.out"
cc -std=c11 -O2 -Wall -Wextra -Werror -I "$HERE/include" \
  "$HERE/tests/shared/direct-full-client.c" -L"$OUT" -Wl,-rpath,'$ORIGIN' \
  -Wl,--no-as-needed -lbasicdemo-mir -lbasicrt -ldl -lm \
  -o "$OUT/direct-full-client"
"$OUT/direct-full-client" > "$OUT/direct-full-client.out"
cc -std=c11 -O2 -Wall -Wextra -Werror \
  "$HERE/tests/shared/direct-dlopen-client.c" -ldl -lm -o "$OUT/direct-dlopen-client"
"$OUT/direct-dlopen-client" "$DIRECT" > "$OUT/direct-dlopen-client.out"

# Run identical ABI clients against the direct and GNU-linked reference DSOs.
cc -std=c11 -O2 -Wall -Wextra -Werror -I "$HERE/include" \
  "$HERE/tests/shared/direct-full-client.c" -L"$OUT" -Wl,-rpath,'$ORIGIN' \
  -lbasicdemo-direct-gcc-reference -ldl -lm -o "$OUT/gcc-reference-client"
"$OUT/gcc-reference-client" > "$OUT/gcc-reference-client.out"
cmp "$OUT/direct-full-client.out" "$OUT/gcc-reference-client.out"
"$OUT/direct-dlopen-client" "$REFERENCE" > "$OUT/gcc-reference-dlopen.out"

# A bad dependency with the same SONAME must fail at RTLD_NOW, not crash later.
bad="$OUT/missing-runtime"
mkdir -p "$bad"
cp "$DIRECT" "$bad/libbasicdemo-mir.so"
cat > "$bad/runtime-stub.c" <<'EOF'
void unrelated_runtime_stub(void) {}
EOF
cc -shared -Wl,-soname,libbasicrt.so "$bad/runtime-stub.c" -o "$bad/libbasicrt.so"
if "$OUT/direct-dlopen-client" "$bad/libbasicdemo-mir.so" \
    > "$OUT/missing-runtime.out" 2> "$OUT/missing-runtime.err"; then
  echo 'RTLD_NOW unexpectedly accepted a runtime missing required symbols' >&2
  exit 1
fi
grep -q 'undefined symbol:' "$OUT/missing-runtime.err"

printf 'PASS: direct MIR DSO, strong runtime imports, RTLD_NOW/LOCAL, GCC differential reference\n'
