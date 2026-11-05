#!/usr/bin/env bash
set -uo pipefail
ROOT=${1:-$(cd -- "$(dirname -- "$0")/.." && pwd)}
SRC=${MPDECIMAL_SOURCE:-"$ROOT/vendor/mpdecimal-4.0.1-c-only"}/libmpdec
ART="$ROOT/results/linux-x86_64/artifacts/mpdecimal-madc"
LOG="$ROOT/results/linux-x86_64/logs"
MADC="$ROOT/madc/bin/madc"
mkdir -p "$ART" "$LOG"
printf 'unit,status,exit_code,object_bytes\n' > "$ROOT/results/linux-x86_64/mpdecimal-madc-units.csv"
cd "$SRC" || exit 2
failed=0
for unit in basearith context constants convolute crt mpdecimal mpsignal difradix2 fnt fourstep io mpalloc numbertheory sixstep transpose; do
  output="$ART/$unit.o"
  if "$MADC" -c -O2 -std=c99 -DCONFIG_64 -DASM -DNDEBUG -fPIC \
      -o "$output" "$unit.c" >"$LOG/mpdecimal-madc-$unit.log" 2>&1; then
    bytes=$(stat -c %s "$output")
    printf '%s,PASS,0,%s\n' "$unit" "$bytes" >> "$ROOT/results/linux-x86_64/mpdecimal-madc-units.csv"
  else
    rc=$?
    failed=1
    printf '%s,COMPILE_FAIL,%s,0\n' "$unit" "$rc" >> "$ROOT/results/linux-x86_64/mpdecimal-madc-units.csv"
  fi
done
if [ "$failed" -eq 0 ]; then
  ar rcs "$ART/libmpdec-madc.a" "$ART"/*.o
  if gcc -shared -o "$ART/libmpdec-madc.so" "$ART"/*.o -lm -ldl -lpthread \
      >"$LOG/mpdecimal-madc-link.log" 2>&1; then
    echo 'link_status,PASS' > "$ROOT/results/linux-x86_64/mpdecimal-madc-link.status"
  else
    echo 'link_status,LINK_FAIL' > "$ROOT/results/linux-x86_64/mpdecimal-madc-link.status"
    failed=1
  fi
else
  echo 'link_status,UNSUPPORTED_INCOMPLETE_OBJECT_SET' > "$ROOT/results/linux-x86_64/mpdecimal-madc-link.status"
fi
exit 0
