#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
ROOT="$HERE/upstream/basic"
BASIC_C="${BASIC_C:-$LAB/vendor/mir-upstream-54fa3e409224bbc6ffdbc421a80f02ff76f76ce6/build/basic/basicc}"
OUT="$HERE/results/validation"
mkdir -p "$OUT"

for name in hello arith loop if_block; do
  expected="$ROOT/tests/expected/$name.out"
  "$BASIC_C" "$ROOT/tests/programs/$name.bas" > "$OUT/$name-interp.out"
  "$BASIC_C" -j "$ROOT/tests/programs/$name.bas" > "$OUT/$name-jit.out"
  "$HERE/scripts/build-aot.sh" "$name" > "$OUT/$name-aot.out" 2> "$OUT/$name-aot.err"
  cmp "$OUT/$name-interp.out" "$expected"
  cmp "$OUT/$name-jit.out" "$expected"
  cmp "$OUT/$name-aot.out" "$expected"
done

printf 'MIR\nY\n' > "$OUT/string.in"
expected="$ROOT/tests/expected/string.out"
"$BASIC_C" "$ROOT/tests/programs/string.bas" < "$OUT/string.in" > "$OUT/string-interp.out"
"$BASIC_C" -j "$ROOT/tests/programs/string.bas" < "$OUT/string.in" > "$OUT/string-jit.out"
"$HERE/scripts/build-aot.sh" string "$OUT/string.in" > "$OUT/string-aot.out" 2> "$OUT/string-aot.err"
cmp "$OUT/string-interp.out" "$expected"
cmp "$OUT/string-jit.out" "$expected"
cmp "$OUT/string-aot.out" "$expected"

# DATA/READ is serialized as generated startup calls by the experimental
# frontend patch, and must agree across all three execution paths.
expected="$ROOT/tests/expected/data_read.out"
"$BASIC_C" "$ROOT/tests/programs/data_read.bas" > "$OUT/data_read-interp.out"
"$BASIC_C" -j "$ROOT/tests/programs/data_read.bas" > "$OUT/data_read-jit.out"
"$HERE/scripts/build-aot.sh" data_read > "$OUT/data_read-aot.out" 2> "$OUT/data_read-aot.err"
cmp "$OUT/data_read-interp.out" "$expected"
cmp "$OUT/data_read-jit.out" "$expected"
cmp "$OUT/data_read-aot.out" "$expected"
printf 'PASS: hello arith loop if_block string data_read (interpreter/JIT/AOT)\n'
