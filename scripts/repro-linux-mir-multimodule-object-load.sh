#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
ART="$ROOT/results/linux-x86_64/artifacts"
mkdir -p "$ART" "$ROOT/results/linux-x86_64/logs"

gcc -g -O0 -I "$ROOT/madc/third_party/mir" \
  "$ROOT/src/microbench/mir_elf_multimodule_demo.c" \
  "$ROOT/madc/obj/mir/host/libmir.a" -lm -ldl -lpthread \
  -o "$ART/mir-elf-multimodule-demo"

"$ART/mir-elf-multimodule-demo" generate \
  "$ART/multimodule.mir" "$ART/multimodule.bmir"
"$ART/mir-elf-multimodule-demo" emit object \
  "$ART/multimodule.mir" "$ART/multimodule.o"
"$ART/mir-elf-multimodule-demo" load "$ART/multimodule.o"
