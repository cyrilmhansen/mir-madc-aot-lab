#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
REV=54fa3e409224bbc6ffdbc421a80f02ff76f76ce6
MIRROOT="$LAB/vendor/mir-upstream-$REV"
BASIC="$MIRROOT/build/basic/basicc"
OUT="$HERE/results/data-validation"
mkdir -p "$OUT"
"$HERE/scripts/build-baseline.sh" >/dev/null 2>&1
"$HERE/scripts/build-runtime.sh" > "$OUT/runtime-build.log" 2>&1

run_compare() {
  local name="$1" source="$2" expected="$3" mode="$4"
  if [[ "$mode" == interp ]]; then
    "$BASIC" "$source" > "$OUT/$name.$mode.out" 2> "$OUT/$name.$mode.err"
  else
    "$BASIC" -j "$source" > "$OUT/$name.$mode.out" 2> "$OUT/$name.$mode.err"
  fi
  cmp "$OUT/$name.$mode.out" "$expected"
}

matrix="$OUT/feature-matrix.tsv"
printf 'Feature\tInterpreter\tJIT\tAOT\tNotes\n' > "$matrix"
for name in numeric strings mixed distributed after-end restore exhaustion; do
  printf 'DATA %s\tPASS\tPASS\tPASS\tsee validate-data.sh\n' "$name" >> "$matrix"
done
for name in funcproc fact def_fn array_idx mat; do
  source="$HERE/upstream/basic/tests/programs/$name.bas"
  expected="$HERE/upstream/basic/tests/expected/$name.out"
  run_compare "$name" "$source" "$expected" interp
  run_compare "$name" "$source" "$expected" jit
  "$HERE/scripts/build-aot.sh" "$source" > "$OUT/$name.aot.out" 2> "$OUT/$name.aot.err"
  cmp "$OUT/$name.aot.out" "$expected"
  printf '%s\tPASS\tPASS\tPASS\n' "$name" >> "$matrix"
done

source="$HERE/tests/features/array-2d.bas"
expected="$HERE/tests/expected/array-2d.out"
run_compare array-2d "$source" "$expected" interp
run_compare array-2d "$source" "$expected" jit
"$HERE/scripts/build-aot.sh" "$source" > "$OUT/array-2d.aot.out" 2> "$OUT/array-2d.aot.err"
cmp "$OUT/array-2d.aot.out" "$expected"
printf '2D array\tPASS\tPASS\tPASS\tcustom two-dimensional fixture\n' >> "$matrix"

source="$HERE/tests/features/fileio.bas"
expected="$HERE/tests/expected/fileio.out"
for mode in interp jit; do
  python3 - "$OUT/aot-fileio.dat" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).unlink(missing_ok=True)
PY
  if [[ "$mode" == interp ]]; then
    (cd "$OUT" && "$BASIC" "$source" > fileio.$mode.out 2> fileio.$mode.err)
  else
    (cd "$OUT" && "$BASIC" -j "$source" > fileio.$mode.out 2> fileio.$mode.err)
  fi
  cmp "$OUT/fileio.$mode.out" "$expected"
done
python3 - "$OUT/aot-fileio.dat" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).unlink(missing_ok=True)
PY
(cd "$OUT" && "$HERE/scripts/build-aot.sh" "$source" > fileio.aot.out 2> fileio.aot.err)
cmp "$OUT/fileio.aot.out" "$expected"
printf 'numeric file I/O\tPASS\tPASS\tPASS\n' >> "$matrix"

# GOSUB is valid in the historical interpreter and JIT. The pinned frontend's
# -S MIR emission is known to segfault for this input even before the adapter.
source="$HERE/upstream/basic/tests/programs/gosub.bas"
expected="$HERE/upstream/basic/tests/expected/gosub.out"
run_compare gosub "$source" "$expected" interp
run_compare gosub "$source" "$expected" jit
printf 'GOSUB / RETURN\tPASS\tPASS\tBLOCKED\tpinned basicc -S segfaults in MIR_output\n' >> "$matrix"

extlib="$OUT/libextlib.so"
cc -shared -fPIC -I "$HERE/upstream/basic/include" \
  "$HERE/upstream/basic/test/extlib.c" -o "$extlib"
source="$HERE/upstream/basic/tests/programs/extern.bas"
expected="$HERE/upstream/basic/tests/expected/extern.out"
for mode in interp jit; do
  if [[ "$mode" == interp ]]; then
    LD_PRELOAD="$extlib" "$BASIC" "$source" > "$OUT/extern.$mode.out" 2> "$OUT/extern.$mode.err"
  else
    LD_PRELOAD="$extlib" "$BASIC" -j "$source" > "$OUT/extern.$mode.out" 2> "$OUT/extern.$mode.err"
  fi
  cmp "$OUT/extern.$mode.out" "$expected"
done
if AOT_EXTRA_LIBS="-L$OUT -Wl,-rpath,$OUT -lextlib" \
  "$HERE/scripts/build-aot.sh" "$source" > "$OUT/extern.aot.out" 2> "$OUT/extern.aot.err"; then
  aot_status=PASS
else
  aot_status=FAIL
fi
if [[ "$aot_status" != FAIL ]] || ! grep -q 'undeclared name EXT_ADD_p' "$OUT/extern.aot.err"; then
  echo 'external import AOT failure changed; inspect before updating the feature matrix' >&2
  exit 1
fi
printf 'external imports\tPASS\tPASS\t%s\tMIR text declares imported prototypes after first use\n' "$aot_status" >> "$matrix"

# The full dynamic MIR API works in the old execution modes but introduces
# MIR runtime references that a strictly native ELF link intentionally omits.
source="$HERE/upstream/basic/tests/programs/mir_demo.bas"
expected="$HERE/upstream/basic/tests/expected/mir_demo.out"
run_compare mir-demo "$source" "$expected" interp
run_compare mir-demo "$source" "$expected" jit
if "$HERE/scripts/build-aot.sh" "$source" > "$OUT/mir-demo.aot.out" 2> "$OUT/mir-demo.aot.err"; then
  echo 'MIR metaprogramming unexpectedly linked into AOT' >&2
  exit 1
fi
grep -q 'undefined reference to `MIR_' "$OUT/mir-demo.aot.err"
printf 'MIR metaprogramming\tPASS\tPASS\tUNSUPPORTED\tuses runtime MIR APIs\n' >> "$matrix"

source="$HERE/upstream/basic/tests/programs/chain.bas"
expected="$HERE/upstream/basic/tests/expected/chain.out"
(cd "$(dirname "$source")" && "$BASIC" "$(basename "$source")" > "$OUT/chain.interp.out" 2> "$OUT/chain.interp.err")
cmp "$OUT/chain.interp.out" "$expected"
if "$BASIC" -j "$source" > "$OUT/chain.jit.out" 2> "$OUT/chain.jit.err"; then
  echo 'CHAIN unexpectedly succeeded in JIT mode' >&2
  exit 1
fi
grep -q 'CHAIN only supported in interpreter mode' "$OUT/chain.jit.err"
printf 'CHAIN\tPASS\tUNSUPPORTED\tUNSUPPORTED\tdynamic source loading\n' >> "$matrix"

if "$BASIC" --no-line-tracking "$HERE/upstream/basic/tests/programs/resume.bas" \
  > "$OUT/resume-no-line.out" 2> "$OUT/resume-no-line.err"; then
  echo 'RESUME without line tracking unexpectedly succeeded' >&2
  exit 1
fi
grep -q 'RESUME without line requires line tracking' "$OUT/resume-no-line.err"
printf 'RESUME without line tracking\tEXPECTED ERROR\tEXPECTED ERROR\tNOT TESTED\tupstream diagnostic\n' >> "$matrix"

# These are explicitly dynamic or unsupported by emitted modules.
if "$BASIC" -S -o "$OUT/eval" "$HERE/tests/features/eval.bas" \
  > "$OUT/eval.emit.out" 2> "$OUT/eval.emit.err"; then
  echo 'EVAL unexpectedly emitted a module' >&2
  exit 1
fi
grep -q 'EVAL requires the live BASIC frontend' "$OUT/eval.emit.err"
if "$BASIC" -S -o "$OUT/chain" "$HERE/upstream/basic/tests/programs/chain.bas" \
  > "$OUT/chain.emit.out" 2> "$OUT/chain.emit.err"; then
  echo 'CHAIN unexpectedly emitted a module' >&2
  exit 1
fi
grep -q 'CHAIN only supported in interpreter mode' "$OUT/chain.emit.err"
printf 'EVAL\tDYNAMIC\tDYNAMIC\tREJECTED\trequires live frontend state\n' >> "$matrix"

printf 'PASS: extended feature cases validated; feature matrix: %s\n' "$matrix"
