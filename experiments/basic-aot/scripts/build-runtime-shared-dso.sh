#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
REV=54fa3e409224bbc6ffdbc421a80f02ff76f76ce6
ROOT="$LAB/vendor/mir-upstream-$REV"

if [[ $# -ne 4 ]]; then
  echo "usage: $0 runtime.a basic.o wrappers.o output/libbasicrt.so" >&2
  exit 2
fi
archive="$(realpath "$1")"
basic_obj="$(realpath "$2")"
wrapper_obj="$(realpath "$3")"
output="$(realpath -m "$4")"
mkdir -p "$(dirname "$output")" "$HERE/results/shared"
map="$HERE/results/shared/libbasicrt.map"
lifecycle="$HERE/results/shared/basic-module-lifecycle-runtime.o"
exports_file="$HERE/results/shared/libbasicrt.exports"

# Export exactly the BASIC runtime functions referenced by the merged BASIC
# and wrapper objects. Other archive sections stay private or are GC'd.
mapfile -t referenced < <(nm -u "$basic_obj" "$wrapper_obj" | awk '$NF ~ /^basic_/ {print $NF}' | sort -u)
mapfile -t archive_symbols < <(nm -g --defined-only "$archive" | awk '{print $NF}' | sort -u)
exports=(basic_module_init basic_module_fini)
for name in "${referenced[@]}"; do
  if ! printf '%s\n' "${archive_symbols[@]}" | grep -Fxq "$name"; then
    echo "BASIC runtime does not define required symbol: $name" >&2
    exit 1
  fi
  exports+=("$name")
done
printf '%s\n' "${exports[@]}" | sort -u > "$exports_file"
{
  echo '{ global:'
  while IFS= read -r name; do echo "  $name;"; done < "$exports_file"
  echo ' local: *; };'
} > "$map"

cc -std=gnu11 -O2 -fPIC -ffunction-sections -fdata-sections \
  -DBASIC_AOT_EXPLICIT_INIT -I "$ROOT/basic/include" -I "$ROOT/basic/src" \
  -I "$LAB/madc/third_party/mir" -c "$HERE/src/basic-module-lifecycle.c" \
  -o "$lifecycle"
cc -shared -Wl,-soname,libbasicrt.so -Wl,--no-undefined -Wl,-z,defs -Wl,-z,text \
  -Wl,-z,relro -Wl,-z,now -Wl,--gc-sections -Wl,--version-script="$map" \
  -Wl,--whole-archive "$archive" -Wl,--no-whole-archive "$lifecycle" -lm -o "$output"
printf 'shared BASIC runtime: %s\n' "$output"
