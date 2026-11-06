#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
BASICC="${BASICC:-$HERE/../basic-aot/results/aot/standalone/diagnostics/pristine-src/build/basic/basicc}"
BEFORE="$HERE/tests/fixtures/semantic-before.bas"
AFTER="$HERE/tests/fixtures/semantic-after.bas"
[[ -x "$BASICC" ]] || { echo "historical basicc not executable: $BASICC" >&2; exit 2; }
for mode in interpreter jit; do
  if [[ "$mode" == jit ]]; then args=(-j); else args=(); fi
  before="$($BASICC "${args[@]}" "$BEFORE")"
  after="$($BASICC "${args[@]}" "$AFTER")"
  [[ "$before" == "$after" ]] || { printf '%s output differs: %q vs %q\n' "$mode" "$before" "$after" >&2; exit 1; }
  [[ "$before" == "10" ]] || { echo "$mode returned unexpected result: $before" >&2; exit 1; }
  printf '%s: before/after output %s matches\n' "$mode" "$before"
done
