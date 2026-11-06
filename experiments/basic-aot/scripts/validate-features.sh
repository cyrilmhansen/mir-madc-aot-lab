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

# GOSUB/RETURN must survive MIR text serialization and native ELF loading.
for name in gosub gosub-nested gosub-loop-data; do
  if [[ "$name" == gosub ]]; then
    source="$HERE/upstream/basic/tests/programs/gosub.bas"
    expected="$HERE/upstream/basic/tests/expected/gosub.out"
  else
    source="$HERE/tests/features/$name.bas"
    expected="$HERE/tests/expected/$name.out"
  fi
  for mode in interp jit; do run_compare "$name" "$source" "$expected" "$mode"; done
  "$HERE/scripts/build-aot.sh" "$source" > "$OUT/$name.aot.out" 2> "$OUT/$name.aot.err"
  cmp "$OUT/$name.aot.out" "$expected"
  printf 'GOSUB %s\tPASS\tPASS\tPASS\n' "$name" >> "$matrix"
done

# EXTERN prototypes must be available before code generation even if the BASIC
# declaration appears after the call. Exercise numeric/string returns and SUBs.
cycle3lib="$OUT/libextcycle3.so"
cc -shared -fPIC -I "$HERE/upstream/basic/include" \
  "$HERE/tests/extlib-cycle3.c" -o "$cycle3lib"
for name in extern-types extern-after-use; do
  source="$HERE/tests/features/$name.bas"
  expected="$HERE/tests/expected/$name.out"
  for mode in interp jit; do
    if [[ "$mode" == interp ]]; then
      LD_PRELOAD="$cycle3lib" "$BASIC" "$source" > "$OUT/$name.$mode.out" 2> "$OUT/$name.$mode.err"
    else
      LD_PRELOAD="$cycle3lib" "$BASIC" -j "$source" > "$OUT/$name.$mode.out" 2> "$OUT/$name.$mode.err"
    fi
    cmp "$OUT/$name.$mode.out" "$expected"
  done
  AOT_EXTRA_LIBS="-L$OUT -Wl,-rpath,$OUT -lextcycle3" \
    "$HERE/scripts/build-aot.sh" "$source" > "$OUT/$name.aot.out" 2> "$OUT/$name.aot.err"
  cmp "$OUT/$name.aot.out" "$expected"
done
printf 'EXTERN before/after use, numeric/string/function/SUB\tPASS\tPASS\tPASS\n' >> "$matrix"

# Conflicting declarations are rejected by every frontend mode. Undefined
# native imports must remain strong ELF references and fail at the system link.
for mode in interp jit; do
  if [[ "$mode" == interp ]]; then
    "$BASIC" "$HERE/tests/features/extern-incompatible.bas" > /dev/null 2> "$OUT/extern-incompatible.$mode.err" && exit 1
  else
    "$BASIC" -j "$HERE/tests/features/extern-incompatible.bas" > /dev/null 2> "$OUT/extern-incompatible.$mode.err" && exit 1
  fi
  grep -q 'conflicting EXTERN declaration' "$OUT/extern-incompatible.$mode.err"
done
for mode in interp jit; do
  if [[ "$mode" == interp ]]; then
    "$BASIC" "$HERE/tests/features/extern-missing.bas" > /dev/null 2> "$OUT/extern-missing.$mode.err" && exit 1
  else
    "$BASIC" -j "$HERE/tests/features/extern-missing.bas" > /dev/null 2> "$OUT/extern-missing.$mode.err" && exit 1
  fi
  grep -q 'import of undefined item EXT_NOT_PRESENT' "$OUT/extern-missing.$mode.err"
done
if "$BASIC" -S -o "$OUT/extern-incompatible" "$HERE/tests/features/extern-incompatible.bas" \
  > /dev/null 2> "$OUT/extern-incompatible.aot.err"; then exit 1; fi
grep -q 'conflicting EXTERN declaration' "$OUT/extern-incompatible.aot.err"
if "$HERE/scripts/build-aot.sh" "$HERE/tests/features/extern-missing.bas" \
  > /dev/null 2> "$OUT/extern-missing.aot.err"; then exit 1; fi
grep -q "undefined reference to .EXT_NOT_PRESENT'" "$OUT/extern-missing.aot.err"
printf 'EXTERN mismatch/missing symbol\tEXPECTED ERROR\tEXPECTED ERROR\tEXPECTED LINK ERROR\n' >> "$matrix"

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
