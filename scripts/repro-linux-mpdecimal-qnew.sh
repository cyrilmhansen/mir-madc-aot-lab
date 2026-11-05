#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
MADC_DIR=${MADC_DIR:-"$ROOT/madc"}
SOURCE=${MPDECIMAL_SOURCE:-"$ROOT/vendor/mpdecimal-4.0.1-c-only"}
LIBDIR="$SOURCE/libmpdec"
ART="$ROOT/results/linux-x86_64/artifacts"
LOG="$ROOT/results/linux-x86_64/logs"
MADCLIB="$ART/mpdecimal-madc/libmpdec-madc.a"
mkdir -p "$ART" "$LOG"

gcc -I"$LIBDIR" "$ROOT/src/clients/mpdecimal_qnew_repro.c" \
  "$LIBDIR/libmpdec.a" -lm -o "$ART/mpd-qnew-gcc"
gcc -I"$LIBDIR" "$ROOT/src/clients/mpdecimal_qnew_repro.c" \
  "$MADCLIB" -L"$MADC_DIR/lib" -lmadc \
  -Wl,-rpath,"$MADC_DIR/lib" -lm -ldl -lpthread \
  -o "$ART/mpd-qnew-madc-lib"

"$ART/mpd-qnew-gcc" >"$LOG/mpdecimal-qnew-gcc.log"
set +e
LD_LIBRARY_PATH="$MADC_DIR/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  "$ART/mpd-qnew-madc-lib" >"$LOG/mpdecimal-qnew-madc-run.log" 2>&1
status=$?
set -e
printf '%s\n' "$status" >"$LOG/mpdecimal-qnew-madc-run.status"
objdump -dr "$ART/mpdecimal-madc/mpalloc.o" \
  >"$LOG/mpdecimal-qnew-disassembly.txt"
if [ "$status" -ne 2 ] || ! grep -qx 'mpd_qnew=NULL' "$LOG/mpdecimal-qnew-madc-run.log"; then
  echo "The MADC qnew reproducer changed behavior (exit $status); inspect $LOG" >&2
  exit 1
fi
echo "Reproduced known failure: mpd_qnew=NULL (exit 2)."
