#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
UPSTREAM_MIR_ROOT="${UPSTREAM_MIR_ROOT:-$LAB/vendor/mir-upstream-54fa3e409224bbc6ffdbc421a80f02ff76f76ce6}"
BASIC_ROOT="$UPSTREAM_MIR_ROOT/basic"
BASIC_C="${BASIC_C:-$UPSTREAM_MIR_ROOT/build/basic/basicc}"
RESULTS="$HERE/results/aot"
extra_libs=()
if [[ -n "${AOT_EXTRA_LIBS:-}" ]]; then
  read -r -a extra_libs <<< "$AOT_EXTRA_LIBS"
fi

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 PROGRAM_NAME [input-file]" >&2
  exit 2
fi
name="$1"
input="${2:-}"
if [[ -f "$name" ]]; then
  src="$(cd "$(dirname "$name")" && pwd)/$(basename "$name")"
  name="$(basename "$name" .bas)"
else
  src="$BASIC_ROOT/tests/programs/$name.bas"
fi
mkdir -p "$RESULTS"
if [[ ! -f "$src" ]]; then
  echo "missing BASIC source: $src" >&2
  exit 2
fi
"$HERE/scripts/build-baseline.sh" >/dev/null
TOOL="$("$HERE/scripts/build-tools.sh")"
"$HERE/scripts/build-runtime.sh" >/dev/null
"$BASIC_C" -S -o "$RESULTS/$name" "$src"
"$TOOL" "$RESULTS/$name.mir" "$RESULTS/$name.o"

cc "$RESULTS/$name.o" -Wl,--gc-sections "$HERE/runtime/libbasicrt.a" \
  -lm "${extra_libs[@]}" -o "$RESULTS/$name-native"

if [[ -n "$input" ]]; then
  "$RESULTS/$name-native" < "$input"
else
  "$RESULTS/$name-native"
fi
