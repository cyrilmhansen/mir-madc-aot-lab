#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
ROOT="$LAB/vendor/mir-upstream-54fa3e409224bbc6ffdbc421a80f02ff76f76ce6"

if [[ $# -lt 2 ]]; then
  echo "usage: $0 source.bas output.so --export NAME [--export NAME ...]" >&2
  exit 2
fi
source="$(realpath "$1")"
output="$(realpath -m "$2")"
shift 2
if [[ $# -eq 0 ]]; then
  echo "at least one --export NAME is required for a shared library" >&2
  exit 2
fi

base="$HERE/results/shared/$(basename "$source" .bas)"
mkdir -p "$(dirname "$output")" "$HERE/results/shared"
export BASIC_RUNTIME_BUILD_DIR="${BASIC_RUNTIME_BUILD_DIR:-$HERE/runtime/shared-build}"
export BASIC_RUNTIME_LIB="${BASIC_RUNTIME_LIB:-$HERE/runtime/libbasicrt-shared.a}"
export BASIC_RUNTIME_CFLAGS="${BASIC_RUNTIME_CFLAGS:-} -DBASIC_AOT_EXPLICIT_INIT"
"$HERE/scripts/build-baseline.sh" >/dev/null
"$HERE/scripts/build-runtime.sh" >/dev/null
TOOL="$("$HERE/scripts/build-tools.sh")"
"$ROOT/build/basic/basicc" -S -o "$base" "$source"
"$TOOL" "$@" "$base.mir" "$base.o"
extra_ldflags=()
if [[ -n "${BASIC_SHARED_LDFLAGS:-}" ]]; then
  read -r -a extra_ldflags <<< "$BASIC_SHARED_LDFLAGS"
fi
cc -std=gnu11 -O2 -fPIC -I "$ROOT/basic/include" -I "$ROOT/basic/src" \
  -I "$LAB/madc/third_party/mir" -c "$HERE/src/basic-module-lifecycle.c" \
  -o "$HERE/results/shared/basic-module-lifecycle.o"

# The archive is compiled as PIC. Hiding its implementation symbols keeps
# BASIC runtime internals out of the public C ABI and permits --gc-sections to
# discard the runtime's optional MIR metaprogramming entry points.
cc "${extra_ldflags[@]}" -shared -Wl,--no-undefined -Wl,-z,defs -Wl,-z,text \
  -Wl,-z,relro -Wl,-z,now -Wl,--gc-sections -Wl,--exclude-libs,ALL \
  "$base.o" "$HERE/results/shared/basic-module-lifecycle.o" \
  "$BASIC_RUNTIME_LIB" -lm -o "$output"
printf 'shared library: %s\n' "$output"
