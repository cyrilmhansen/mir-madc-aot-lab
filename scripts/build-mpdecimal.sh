#!/usr/bin/env bash
set -euo pipefail
LAB_ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=4.0.1
ARCHIVE="$LAB_ROOT/downloads/mpdecimal-$VERSION.tar.gz"
SOURCE=${MPDECIMAL_SOURCE:-"$LAB_ROOT/vendor/mpdecimal-$VERSION-c-only"}
EXPECTED_SHA256=96d33abb4bb0070c7be0fed4246cd38416188325f820468214471938545b1ac8
mkdir -p "$LAB_ROOT/downloads" "$LAB_ROOT/vendor" "$LAB_ROOT/results/logs"
if [ ! -f "$ARCHIVE" ]; then
  curl -fL --retry 3 \
    "https://www.bytereef.org/software/mpdecimal/releases/mpdecimal-$VERSION.tar.gz" \
    -o "$ARCHIVE"
fi
if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL_SHA256=$(sha256sum "$ARCHIVE" | awk '{print $1}')
else
  ACTUAL_SHA256=$(shasum -a 256 "$ARCHIVE" | awk '{print $1}')
fi
if [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
  echo "mpdecimal archive checksum mismatch: $ACTUAL_SHA256" >&2
  exit 1
fi
if [ ! -d "$SOURCE" ]; then
  mkdir -p "$SOURCE"
  tar -xzf "$ARCHIVE" --strip-components=1 -C "$SOURCE"
fi
cd "$SOURCE"
CC=${CC:-gcc} CXX=${CXX:-g++} ./configure --disable-cxx 2>&1 | tee "$LAB_ROOT/results/logs/mpdecimal-configure.log"
make -j"${JOBS:-2}" 2>&1 | tee "$LAB_ROOT/results/logs/mpdecimal-build.log"
make check_local 2>&1 | tee "$LAB_ROOT/results/logs/mpdecimal-check-local.log"
make check 2>&1 | tee "$LAB_ROOT/results/logs/mpdecimal-check.log"
