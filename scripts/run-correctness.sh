#!/usr/bin/env bash
set -euo pipefail
LAB_ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
MADC_DIR=${MADC_DIR:-"$LAB_ROOT/madc"}
BREW_PREFIX=${BREW_PREFIX:-/opt/homebrew}
ARTIFACTS="$LAB_ROOT/results/artifacts"
mkdir -p "$ARTIFACTS" "$LAB_ROOT/results/logs"
"$LAB_ROOT/scripts/build-microbench.sh"

if [ "$(uname -s)" = Darwin ]; then
  AOT_CC=${CC:-gcc-16}
  LIB="$ARTIFACTS/libmir-sample.dylib"
  OBJECT="$ARTIFACTS/macho-object.o"
  RUNTIME="$ARTIFACTS/libmadc-0.dylib"
  JIT_LOG="$LAB_ROOT/results/logs/macho-jit.log"
  "$MADC_DIR/bin/madc" --no-includes --no-forest-bind -shared -o "$LIB" \
    "$LAB_ROOT/src/loaders/macho_exports.c"
  "$MADC_DIR/bin/madc" --no-forest-bind "$LAB_ROOT/src/loaders/macho_demo.c" >"$JIT_LOG"
  "$MADC_DIR/bin/madc" --no-forest-bind -o "$ARTIFACTS/madc-macho-exe" \
    "$LAB_ROOT/src/loaders/macho_demo.c"
  "$MADC_DIR/bin/madc" --no-includes --no-forest-bind -c -o "$OBJECT" \
    "$LAB_ROOT/src/loaders/macho_exports.c"
  # The macOS develop build's default shared rule uses Linux -soname. Link the
  # equivalent dylib from existing MADC outputs without changing MADC sources.
  clang++ -dynamiclib -o "$RUNTIME" -Wl,-install_name,@rpath/libmadc-0.dylib \
    -Wl,-force_load "$MADC_DIR/lib/libmadc.a" "$MADC_DIR/obj/mir/host/libmir.a" \
    -lz -lm "$BREW_PREFIX/opt/pcre2/lib/libpcre2-8.a" \
    "$BREW_PREFIX/opt/zstd/lib/libzstd.a"
  ${AOT_CC} -std=c11 -O2 -Wall -Wextra -Werror \
    "$LAB_ROOT/src/clients/macho_object_link_client.c" "$OBJECT" "$RUNTIME" \
    -Wl,-rpath,@executable_path -o "$ARTIFACTS/native-object-client"
  ${AOT_CC} -std=c11 -O2 -Wall -Wextra -Werror \
    "$LAB_ROOT/src/clients/dlopen_client.c" -o "$ARTIFACTS/dlopen-client"
  DSO_PATH="$LIB"
  RUNTIME_PATH="$ARTIFACTS"
  RUNTIME_ENV=DYLD_LIBRARY_PATH
else
  AOT_CC=${CC:-gcc}
  LIB="$ARTIFACTS/libmir-sample.so"
  OBJECT="$ARTIFACTS/native-object.o"
  RUNTIME="$MADC_DIR/lib/libmadc.so"
  JIT_LOG="$LAB_ROOT/results/logs/native-jit.log"
  "$MADC_DIR/bin/madc" --no-includes --no-forest-bind -shared -o "$LIB" \
    "$LAB_ROOT/src/loaders/macho_exports.c"
  "$MADC_DIR/bin/madc" --no-forest-bind "$LAB_ROOT/src/loaders/macho_demo.c" >"$JIT_LOG"
  "$MADC_DIR/bin/madc" --no-forest-bind -o "$ARTIFACTS/madc-native-exe" \
    "$LAB_ROOT/src/loaders/macho_demo.c"
  "$MADC_DIR/bin/madc" --no-includes --no-forest-bind -c -o "$OBJECT" \
    "$LAB_ROOT/src/loaders/macho_exports.c"
  make -C "$MADC_DIR/src" libmadc
  ${AOT_CC} -std=c11 -O2 -Wall -Wextra -Werror \
    "$LAB_ROOT/src/clients/macho_object_link_client.c" "$OBJECT" -L"$MADC_DIR/lib" \
    -lmadc -Wl,-rpath,"$MADC_DIR/lib" -o "$ARTIFACTS/native-object-client"
  ${AOT_CC} -std=c11 -O2 -Wall -Wextra -Werror \
    "$LAB_ROOT/src/clients/dlopen_client.c" -o "$ARTIFACTS/dlopen-client"
  DSO_PATH="$LIB"
  RUNTIME_PATH="$MADC_DIR/lib"
  RUNTIME_ENV=LD_LIBRARY_PATH
fi
"$ARTIFACTS/libmir-smoke" write "$ARTIFACTS/program.bmir" \
  >"$LAB_ROOT/results/logs/libmir-jit.log"
"$ARTIFACTS/libmir-smoke" read "$ARTIFACTS/program.bmir" \
  >"$LAB_ROOT/results/logs/libmir-bmir-jit.log"
env "$RUNTIME_ENV=$RUNTIME_PATH" "$ARTIFACTS/dlopen-client" "$DSO_PATH" \
  >"$LAB_ROOT/results/logs/native-dlopen.log"
"$ARTIFACTS/native-object-client" >"$LAB_ROOT/results/logs/native-object-link.log"
if [ "$(uname -s)" = Darwin ]; then
  DYLD_LIBRARY_PATH="$ARTIFACTS" "$ARTIFACTS/madc-macho-exe"
else
  LD_LIBRARY_PATH="$RUNTIME_PATH${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    "$ARTIFACTS/madc-native-exe"
fi
