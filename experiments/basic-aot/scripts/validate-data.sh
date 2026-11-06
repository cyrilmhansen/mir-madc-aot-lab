#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
REV=54fa3e409224bbc6ffdbc421a80f02ff76f76ce6
MIRROOT="$LAB/vendor/mir-upstream-$REV"
BASICROOT="$MIRROOT/basic"
BASIC_C="$MIRROOT/build/basic/basicc"
OUT="$HERE/results/data-validation"
mkdir -p "$OUT"
"$HERE/scripts/build-baseline.sh" >/dev/null 2>&1
"$HERE/scripts/build-runtime.sh" > "$OUT/runtime-build.log" 2>&1
TOOL="$("$HERE/scripts/build-tools.sh")"

cc -O2 -DBASIC_USE_DOUBLE -I "$BASICROOT/include" -I "$LAB/madc/third_party/mir" \
  "$HERE/tests/data-runtime-test.c" -Wl,--gc-sections "$HERE/runtime/libbasicrt.a" \
  -lm -o "$OUT/data-runtime-test"
"$OUT/data-runtime-test" > "$OUT/data-runtime-test.out"
grep -q '^PASS:' "$OUT/data-runtime-test.out"

for source in "$HERE"/tests/data-*.bas; do
  name="$(basename "$source" .bas)"
  expected="$HERE/tests/expected/$name.out"
  "$BASIC_C" "$source" > "$OUT/$name.interp.out" 2> "$OUT/$name.interp.err"
  "$BASIC_C" -j "$source" > "$OUT/$name.jit.out" 2> "$OUT/$name.jit.err"
  cmp "$OUT/$name.interp.out" "$expected"
  cmp "$OUT/$name.jit.out" "$expected"

  "$HERE/scripts/build-aot.sh" "$source" > "$OUT/$name.aot.out" 2> "$OUT/$name.aot.err"
  cmp "$OUT/$name.aot.out" "$expected"
done

# Test same-process re-entry in the REPL interpreter, historical JIT, and ELF.
source="$HERE/tests/data-restore.bas"
expected="$HERE/tests/expected/data-restore.out"
printf 'RUN\nRUN\nQUIT\n' > "$OUT/twice.commands"
cat "$source" "$OUT/twice.commands" | "$BASIC_C" > "$OUT/twice.interp.raw" 2> "$OUT/twice.interp.err"
python3 - "$OUT/twice.interp.raw" "$expected" "$OUT/twice.interp.out" <<'PY'
from pathlib import Path
import sys
lines = [line for line in Path(sys.argv[1]).read_text().splitlines(keepends=True)
         if line.strip() != "READY."]
Path(sys.argv[3]).write_text("".join(lines))
expected = Path(sys.argv[2]).read_text()
if "".join(lines) != expected * 2:
    raise SystemExit("interpreter repeated RUN output mismatch")
PY

"$BASIC_C" -r -o "$OUT/data-restore-jit" "$source"
cc -O2 -I "$MIRROOT" -I "$BASICROOT/include" -I "$LAB/madc/third_party/mir" \
  "$HERE/tests/jit-run-twice.c" \
  "$MIRROOT/build/CMakeFiles/mir.dir/mir.c.o" \
  "$MIRROOT/build/CMakeFiles/mir.dir/mir-gen.c.o" \
  "$MIRROOT/build/CMakeFiles/mir.dir/c2mir/c2mir.c.o" \
  -Wl,--gc-sections "$HERE/runtime/libbasicrt.a" -lm -ldl -lpthread \
  -o "$OUT/jit-run-twice"
"$OUT/jit-run-twice" "$OUT/data-restore-jit.bmir" > "$OUT/twice.jit.out" 2> "$OUT/twice.jit.err"
cat "$expected" "$expected" > "$OUT/twice.expected"
cmp "$OUT/twice.jit.out" "$OUT/twice.expected"

"$HERE/scripts/build-aot.sh" "$source" > "$OUT/data-restore.aot.out" 2> "$OUT/data-restore.aot.err"
objcopy --redefine-sym main=basic_program_main \
  "$HERE/results/aot/data-restore.o" "$OUT/data-restore-renamed.o"
cc "$HERE/tests/aot-run-twice.c" "$OUT/data-restore-renamed.o" \
  -Wl,--gc-sections "$HERE/runtime/libbasicrt.a" -lm -o "$OUT/aot-run-twice"
"$OUT/aot-run-twice" > "$OUT/twice.aot.out" 2> "$OUT/twice.aot.err"
cmp "$OUT/twice.aot.out" "$OUT/twice.expected"

cat "$HERE/tests/data-repl-edit.commands" | "$BASIC_C" \
  > "$OUT/data-repl-edit.raw" 2> "$OUT/data-repl-edit.err"
python3 - "$OUT/data-repl-edit.raw" "$OUT/data-repl-edit.out" <<'PY'
from pathlib import Path
import sys
lines = [line for line in Path(sys.argv[1]).read_text().splitlines(keepends=True)
         if line.strip() != "READY."]
Path(sys.argv[2]).write_text("".join(lines))
PY
cmp "$OUT/data-repl-edit.out" "$HERE/tests/expected/data-repl-edit.out"

printf 'PASS: seven DATA cases, repeated runs in interpreter/JIT/AOT, and REPL DATA line replacement\n'
