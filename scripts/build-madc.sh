#!/usr/bin/env bash
set -euo pipefail
LAB_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
MADC_DIR=${MADC_DIR:-"$LAB_ROOT/madc"}
BREW_PREFIX=${BREW_PREFIX:-/opt/homebrew}
export PATH="$BREW_PREFIX/opt/make/libexec/gnubin:$BREW_PREFIX/opt/coreutils/libexec/gnubin:$BREW_PREFIX/opt/gnu-sed/libexec/gnubin:$BREW_PREFIX/opt/grep/libexec/gnubin:$PATH"
mkdir -p "$LAB_ROOT/results/logs"

if [ "$(uname -s)" = Darwin ]; then
  make -C "$MADC_DIR/src" ../bin/madc \
    "OPTIONAL_CPPFLAGS=-I$BREW_PREFIX/opt/pcre2/include -DPCRE2_STATIC -DHAVE_ZSTD -I$BREW_PREFIX/opt/zstd/include" \
    "OPTIONAL_LIBS=$BREW_PREFIX/opt/pcre2/lib/libpcre2-8.a $BREW_PREFIX/opt/zstd/lib/libzstd.a" \
    WHOLE_ARCHIVE_BEGIN=-Wl,-force_load WHOLE_ARCHIVE_END= \
    "LIBS=-lz -lm $BREW_PREFIX/opt/pcre2/lib/libpcre2-8.a $BREW_PREFIX/opt/zstd/lib/libzstd.a" \
    "PIC_CXXFLAGS=-std=c++11 -Wall -Werror -O0 -fPIC" 2>&1 | tee "$LAB_ROOT/results/logs/build-madc.log"
  if ! make -C "$MADC_DIR/src" test \
    "OPTIONAL_CPPFLAGS=-I$BREW_PREFIX/opt/pcre2/include -DPCRE2_STATIC -DHAVE_ZSTD -I$BREW_PREFIX/opt/zstd/include" \
    "OPTIONAL_LIBS=$BREW_PREFIX/opt/pcre2/lib/libpcre2-8.a $BREW_PREFIX/opt/zstd/lib/libzstd.a" \
    WHOLE_ARCHIVE_BEGIN=-Wl,-force_load WHOLE_ARCHIVE_END= \
    "LIBS=-lz -lm $BREW_PREFIX/opt/pcre2/lib/libpcre2-8.a $BREW_PREFIX/opt/zstd/lib/libzstd.a" \
    "PIC_CXXFLAGS=-std=c++11 -Wall -Werror -O0 -fPIC" 2>&1 | tee "$LAB_ROOT/results/logs/test-madc.log"; then
    echo "MADC unit-test build failed; see test-madc.log" >&2
  fi
  for test_name in test_object_load test_native_shared; do
    if ! make -C "$MADC_DIR/src" "../bin/$test_name" \
      "OPTIONAL_CPPFLAGS=-I$BREW_PREFIX/opt/pcre2/include -DPCRE2_STATIC -DHAVE_ZSTD -I$BREW_PREFIX/opt/zstd/include" \
      "OPTIONAL_LIBS=$BREW_PREFIX/opt/pcre2/lib/libpcre2-8.a $BREW_PREFIX/opt/zstd/lib/libzstd.a" \
      WHOLE_ARCHIVE_BEGIN=-Wl,-force_load WHOLE_ARCHIVE_END= \
      "LIBS=-lz -lm $BREW_PREFIX/opt/pcre2/lib/libpcre2-8.a $BREW_PREFIX/opt/zstd/lib/libzstd.a" \
      >"$LAB_ROOT/results/logs/$test_name.log" 2>&1; then
      echo "$test_name build failed; see $test_name.log" >&2
    fi
  done
else
  make -C "$MADC_DIR/src" 2>&1 | tee "$LAB_ROOT/results/logs/build-madc.log"
  make -C "$MADC_DIR/src" test 2>&1 | tee "$LAB_ROOT/results/logs/test-madc.log"
fi
