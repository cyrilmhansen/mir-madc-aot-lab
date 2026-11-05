#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
MADC="$ROOT/madc"
RESULTS="$ROOT/results/linux-x86_64"
ART="$RESULTS/artifacts"
REPEATS=${REPEATS:-30}
mkdir -p "$ART/corpora" "$RESULTS/logs"
gcc -std=gnu11 -O2 -Wall -Wextra -Werror -I"$MADC/third_party/mir" \
  "$ROOT/src/microbench/libmir_smoke.c" "$MADC/obj/mir/host/libmir.a" \
  -lm -o "$ART/libmir-smoke"
gcc -std=gnu11 -O2 -Wall -Wextra -Werror -I"$MADC/third_party/mir" \
  "$ROOT/src/microbench/aot_corpus.c" "$MADC/obj/mir/host/libmir.a" \
  -ldl -lm -o "$ART/aot-corpus"
gcc -std=gnu11 -O2 -Wall -Wextra -Werror "$ROOT/src/clients/elf_dlopen_corpus.c" \
  -ldl -o "$ART/elf-dlopen-corpus"
python3 "$ROOT/scripts/bench_linux_aot.py" "$ROOT" "$REPEATS"
python3 "$ROOT/scripts/bench_linux_pie.py" "$ROOT" "$REPEATS"
{
  for path in "$ART"/corpora/corpus-{10,100,1000,5000}.o \
              "$ART"/libcorpus-{10,100,1000,5000}.so \
              "$ART"/corpus-{10,100,1000,5000}-pie; do
    [ -f "$path" ] || continue
    echo "===== $path ====="
    readelf -h "$path" | grep -E 'Type:|Machine:'
    readelf -d "$path" 2>/dev/null | grep NEEDED || true
    readelf -r "$path" 2>/dev/null | head -25 || true
    nm -D --defined-only "$path" 2>/dev/null | head -15 || true
  done
} > "$RESULTS/elf-inspection.txt"
