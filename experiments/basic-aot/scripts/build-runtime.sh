#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
REV=54fa3e409224bbc6ffdbc421a80f02ff76f76ce6
MIRROOT="$LAB/vendor/mir-upstream-$REV"
BUILD="$HERE/runtime/build"
LIB="$HERE/runtime/libbasicrt.a"
CC="${CC:-cc}"
AR="${AR:-ar}"

"$HERE/scripts/build-baseline.sh" >/dev/null
BASICROOT="$MIRROOT/basic"
mkdir -p "$BUILD"
CFLAGS=(-std=gnu11 -O2 -fPIC -ffunction-sections -fdata-sections -DBASIC_USE_DOUBLE -DBASIC_AOT_NO_MIR_RUNTIME
  -I "$LAB/madc/third_party/mir" -I "$BASICROOT/include" -I "$BASICROOT/src"
  -I "$BASICROOT/src/vendor" -I "$BASICROOT/src/vendor/kitty"
  -I "$BASICROOT/src/vendor/libdfp")

signature="$BUILD/signature.new"
python3 - "$BASICROOT" "$LAB/madc/third_party/mir" "$CC" "${CFLAGS[*]}" "$signature" <<'PY'
import hashlib
import pathlib
import subprocess
import sys

basic = pathlib.Path(sys.argv[1])
mir = pathlib.Path(sys.argv[2])
cc, flags, output = sys.argv[3:]
digest = hashlib.sha256()
digest.update(subprocess.check_output([cc, "--version"], text=False))
digest.update(flags.encode())
runtime_sources = [
    basic / "src/basic_runtime.c", basic / "src/basic_pool.c",
    basic / "src/vendor/kitty/kitty.c", basic / "src/vendor/kitty/lodepng.c",
]
files = runtime_sources[:]
for root in (basic / "include", basic / "src", basic / "src/vendor/kitty", mir):
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in {".h", ".inc"}:
            files.append(path)
for path in sorted(set(files)):
    digest.update(str(path).encode())
    digest.update(path.read_bytes())
pathlib.Path(output).write_text(digest.hexdigest() + "\n")
PY
if [[ "${FORCE_REBUILD:-0}" != 1 && -f "$LIB" && -f "$BUILD/signature" ]] && cmp -s "$signature" "$BUILD/signature"; then
  python3 - "$signature" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).unlink(missing_ok=True)
PY
  echo "reusing $LIB (sources, compiler and flags unchanged)"
  exit 0
fi

sources=(src/basic_runtime.c src/basic_pool.c src/vendor/kitty/kitty.c src/vendor/kitty/lodepng.c)
objects=()
for source in "${sources[@]}"; do
  object="$BUILD/$(basename "${source%.c}").o"
  "$CC" "${CFLAGS[@]}" -c "$BASICROOT/$source" -o "$object"
  objects+=("$object")
done
"$AR" rcs "$LIB" "${objects[@]}"
mv "$signature" "$BUILD/signature"
echo "built $LIB"
