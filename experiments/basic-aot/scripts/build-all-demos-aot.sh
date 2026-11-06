#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
DEFAULT_MIR_ROOT="$LAB/vendor/mir-upstream-54fa3e409224bbc6ffdbc421a80f02ff76f76ce6"
UPSTREAM_MIR_ROOT="${UPSTREAM_MIR_ROOT:-$DEFAULT_MIR_ROOT}"
BASIC_ROOT="$UPSTREAM_MIR_ROOT/basic"
BASIC_C="${BASIC_C:-$UPSTREAM_MIR_ROOT/build/basic/basicc}"
SOURCE_ROOT="${1:-$BASIC_ROOT/samples}"
OUTPUT_ROOT="${2:-$HERE/results/aot/standalone}"

if [[ $# -eq 1 && "$1" == --help ]]; then
  echo "usage: $0 [BASIC_SOURCE_DIR [OUTPUT_DIR]]"
  echo "Defaults to the historical basic/samples tree and results/aot/standalone."
  exit 0
fi
if [[ $# -gt 2 ]]; then
  echo "usage: $0 [BASIC_SOURCE_DIR [OUTPUT_DIR]]" >&2
  exit 2
fi
if [[ ! -d "$SOURCE_ROOT" ]]; then
  echo "missing BASIC source directory: $SOURCE_ROOT" >&2
  exit 2
fi
SOURCE_ROOT="$(cd "$SOURCE_ROOT" && pwd)"
mkdir -p "$OUTPUT_ROOT/bin" "$OUTPUT_ROOT/obj" "$OUTPUT_ROOT/logs"
OUTPUT_ROOT="$(cd "$OUTPUT_ROOT" && pwd)"

extra_libs=()
if [[ -n "${AOT_EXTRA_LIBS:-}" ]]; then
  read -r -a extra_libs <<< "$AOT_EXTRA_LIBS"
fi

# Build shared prerequisites once; build-runtime.sh reuses its source/flags cache.
bash "$HERE/scripts/build-baseline.sh" >/dev/null || exit $?
TOOL="$(bash "$HERE/scripts/build-tools.sh")" || exit $?
bash "$HERE/scripts/build-runtime.sh" >/dev/null || exit $?

mapfile -d '' programs < <(find "$SOURCE_ROOT" -type f -iname '*.bas' -print0 | sort -z)
if [[ ${#programs[@]} -eq 0 ]]; then
  echo "no .bas programs found under $SOURCE_ROOT" >&2
  exit 2
fi

manifest="$OUTPUT_ROOT/manifest.tsv"
printf 'source\tbuild_status\texecution_status\tstage\texecutable\tdetail\n' > "$manifest"
built=0
failed=0
for source in "${programs[@]}"; do
  relative="${source#"$SOURCE_ROOT"/}"
  stem="${relative%.*}"
  intermediate="$OUTPUT_ROOT/obj/$stem"
  executable="$OUTPUT_ROOT/bin/$stem"
  log="$OUTPUT_ROOT/logs/$stem.log"
  temporary="$executable.tmp.$BASHPID"
  mkdir -p "$(dirname "$intermediate")" "$(dirname "$executable")" "$(dirname "$log")"
  : > "$log"
  stage=frontend
  if ! "$BASIC_C" -S -o "$intermediate" "$source" >"$log" 2>&1; then
    printf '%s\tfrontend-fail\tnot-run\t%s\t\t%s\n' "$relative" "$stage" "basicc -S failed" >> "$manifest"
    failed=$((failed + 1))
    continue
  fi
  stage=mir-to-object
  if ! python3 - "$TOOL" "$intermediate.mir" "$intermediate.o" >>"$log" 2>&1 <<'PY'
import subprocess
import sys

command = sys.argv[1:]
result = subprocess.run(command)
if result.returncode < 0:
    signal_number = -result.returncode
    print(f"MIR object adapter terminated by signal {signal_number}", file=sys.stderr)
    raise SystemExit(128 + signal_number)
raise SystemExit(result.returncode)
PY
  then
    adapter_detail="MIR-to-object adapter failed"
    if grep -q 'terminated by signal' "$log"; then
      adapter_detail="$(sed -n 's/.*terminated by signal \([0-9][0-9]*\).*/signal-\1/p' "$log" | tail -1)"
    fi
    printf '%s\tadapter-fail\tnot-run\t%s\t\t%s\n' "$relative" "$stage" "$adapter_detail" >> "$manifest"
    failed=$((failed + 1))
    continue
  fi
  stage=native-link
  if ! cc "$intermediate.o" -Wl,--gc-sections "$HERE/runtime/libbasicrt.a" \
      -lm "${extra_libs[@]}" -o "$temporary" >>"$log" 2>&1; then
    rm -f "$temporary"
    printf '%s\tlink-fail\tnot-run\t%s\t\t%s\n' "$relative" "$stage" "native linker failed" >> "$manifest"
    failed=$((failed + 1))
    continue
  fi
  mv -f "$temporary" "$executable"
  printf '%s\tbuilt\tnot-run\tcomplete\t%s\t\n' "$relative" "${executable#"$OUTPUT_ROOT"/}" >> "$manifest"
  built=$((built + 1))
done

printf 'AOT standalone builds: %d built, %d failed, %d total\n' \
  "$built" "$failed" "${#programs[@]}"
printf 'Executables: %s/bin/\nManifest: %s\n' "$OUTPUT_ROOT" "$manifest"
if [[ $failed -ne 0 ]]; then
  echo 'See per-program logs; failures are recorded with their failing stage in the manifest.' >&2
  exit 1
fi
