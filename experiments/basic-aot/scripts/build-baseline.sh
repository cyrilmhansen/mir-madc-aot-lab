#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
REV=54fa3e409224bbc6ffdbc421a80f02ff76f76ce6
VENDOR="$LAB/vendor"
ROOT="$VENDOR/mir-upstream-$REV"
ARCHIVE="$VENDOR/mir-$REV.tar.gz"
BUILD="$ROOT/build"
PATCH_FILE="$HERE/patches/data-runtime.patch"

mkdir -p "$VENDOR"
if [[ ! -d "$ROOT/basic" ]]; then
  [[ -f "$ARCHIVE" ]] || curl -fL \
    "https://github.com/cyrilmhansen/mir/archive/$REV.tar.gz" -o "$ARCHIVE"
  mkdir -p "$ROOT"
  tar -xzf "$ARCHIVE" --strip-components=1 -C "$ROOT"
fi
if ! patch -s -R --dry-run -p1 -d "$ROOT" < "$PATCH_FILE"; then
  python3 "$HERE/scripts/sync-basic-source.py" "$HERE/upstream/basic" "$ROOT/basic"
  patch -s -p1 -d "$ROOT" < "$PATCH_FILE"
fi
cmake -S "$ROOT" -B "$BUILD" -DBUILD_TESTING=ON \
  -DBASIC_NUM_MODE=double -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD" --target basicc -j"$(nproc)"
printf 'basicc: %s\n' "$BUILD/basic/basicc"
