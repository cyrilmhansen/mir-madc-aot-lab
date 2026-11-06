#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0
HERE="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
ADAPTER="${MIR_TO_ELF:-$HERE/build/mir-to-elf}"
MIR="$HERE/tests/demo-corpus/awari-adapter-crash.mir"
MINIMAL_MIR="$HERE/tests/demo-corpus/undefined-label-minimal.mir"
BASIC_C="${BASIC_C:-$LAB/vendor/mir-upstream-54fa3e409224bbc6ffdbc421a80f02ff76f76ce6/build/basic/basicc}"
MINIMAL_BASIC="$HERE/tests/demo-corpus/unmatched-for-goto.bas"
DIAG="$HERE/results/aot/standalone/diagnostics"
if [[ ! -x "$ADAPTER" ]]; then
  echo "missing adapter: $ADAPTER (run scripts/build-tools.sh)" >&2
  exit 2
fi
mkdir -p "$DIAG"
WORK="$(mktemp -d "$DIAG/repro-awari.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

python3 - "$ADAPTER" "$MIR" "$MINIMAL_MIR" <<'PY'
import subprocess, sys
for path in sys.argv[2:]:
    p = subprocess.run([sys.argv[1], path, '/dev/null'], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
    if p.returncode != -11:
        sys.stderr.buffer.write(p.stderr)
        raise SystemExit(f'{path}: expected adapter SIGSEGV (-11), got {p.returncode}')
    print(f'reproduced adapter SIGSEGV (11): {path}')
PY

if [[ -x "$BASIC_C" ]]; then
  "$BASIC_C" -S -o "$WORK/unmatched-for-goto" "$MINIMAL_BASIC" >"$WORK/frontend.log" 2>&1
  if grep -Eq '^[[:space:]]*L10:' "$WORK/unmatched-for-goto.mir"; then
    echo 'minimal BASIC fixture unexpectedly defines the dangling FOR exit label L10' >&2
    exit 1
  fi
  if ! grep -q $'dbgt\tL10,' "$WORK/unmatched-for-goto.mir"; then
    echo 'minimal BASIC fixture no longer emits the expected branch to L10' >&2
    exit 1
  fi
  python3 - "$ADAPTER" "$WORK/unmatched-for-goto.mir" <<'PY'
import subprocess, sys
p = subprocess.run([sys.argv[1], sys.argv[2], '/dev/null'], stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE)
if p.returncode != -11:
    sys.stderr.buffer.write(p.stderr)
    raise SystemExit(f'expected adapter SIGSEGV (-11), got {p.returncode}')
print('reproduced: four-line BASIC FOR/GOTO fixture emits an undefined label and crashes the adapter')
PY
else
  echo "pristine/historical basicc not found; skipped BASIC-to-MIR reproduction: $BASIC_C" >&2
fi
