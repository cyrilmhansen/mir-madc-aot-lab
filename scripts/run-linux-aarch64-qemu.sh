#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
MADC="$ROOT/madc/bin/madc-aarch64-linux"
CC=aarch64-linux-gnu-gcc
QEMU=(qemu-aarch64 -L /usr/aarch64-linux-gnu)
RESULTS="$ROOT/results/linux-aarch64-qemu"
ART="$RESULTS/artifacts"
mkdir -p "$ART/fixtures" "$RESULTS/logs"

test -x "$MADC" || { echo "build first: scripts/build-linux-aarch64-cross.sh" >&2; exit 2; }

MIRBUILD="$ROOT/madc/obj/mir/aarch64-native"
mkdir -p "$MIRBUILD"
make -j4 -C "$ROOT/madc/third_party/mir" BUILD_DIR="$MIRBUILD" \
  CC="$CC" "$MIRBUILD/libmir.a" \
  >"$RESULTS/logs/libmir-aarch64-runtime-build.log" 2>&1

# Cross-generated AArch64 objects, shared library and standalone PIE.
"$MADC" --no-includes --no-forest-bind -fno-eval-shims -c \
  -o "$ART/madc-arm-exports.o" "$ROOT/src/loaders/aarch64_exports.c" \
  >"$RESULTS/logs/madc-arm-object.log" 2>&1
"$MADC" --no-includes --no-forest-bind -fno-eval-shims -shared \
  -o "$ART/libmadc-arm-sample.so" "$ROOT/src/loaders/aarch64_exports.c" \
  >"$RESULTS/logs/madc-arm-shared-noshim.log" 2>&1
"$CC" -O2 "$ROOT/src/clients/elf_dlopen_client.c" -ldl \
  -o "$ART/arm-dlopen-client-gcc"
"${QEMU[@]}" "$ART/arm-dlopen-client-gcc" "$ART/libmadc-arm-sample.so" \
  >"$RESULTS/logs/madc-arm-dlopen.log"
"$MADC" --no-includes --no-forest-bind \
  -o "$ART/arm-madc-pie" \
  "$ROOT/src/loaders/aarch64_unit_a.c" \
  "$ROOT/src/loaders/aarch64_unit_b.c" \
  "$ROOT/src/loaders/aarch64_link_main.c" \
  >"$RESULTS/logs/madc-arm-pie.log" 2>&1
"${QEMU[@]}" "$ART/arm-madc-pie"

# Separate MADC compilation units linked by the target GCC driver.
for unit in aarch64_unit_a aarch64_unit_b aarch64_link_main; do
  "$MADC" --no-includes --no-forest-bind -fno-eval-shims -c \
    -o "$ART/$unit-madc.o" "$ROOT/src/loaders/$unit.c" \
    >"$RESULTS/logs/$unit-madc.log" 2>&1
done
"$CC" -O2 "$ART/aarch64_unit_a-madc.o" "$ART/aarch64_unit_b-madc.o" \
  "$ART/aarch64_link_main-madc.o" -o "$ART/arm-madc-multiobj-gcc-link"
"${QEMU[@]}" "$ART/arm-madc-multiobj-gcc-link"

# Every existing cross AOT fixture is compared to the GCC/QEMU oracle.
echo "fixture,status,details" > "$RESULTS/fixtures.csv"
failed=0
for fixture in "$ROOT"/madc/tests/cross/aarch64_*.c; do
  name=$(basename "$fixture" .c)
  dir="$ART/fixtures"
  if ! "$CC" -O0 "$fixture" -o "$dir/$name.gcc" 2>"$dir/$name.gcc-build.log"; then
    echo "$name,GCC_BUILD_FAIL,oracle build" >> "$RESULTS/fixtures.csv"
    failed=1
    continue
  fi
  if ! "${QEMU[@]}" "$dir/$name.gcc" >"$dir/$name.oracle" 2>&1; then
    echo "$name,GCC_RUN_FAIL,oracle run" >> "$RESULTS/fixtures.csv"
    failed=1
    continue
  fi
  if ! "$MADC" --std=gnu17 -c -o "$dir/$name.madc.o" "$fixture" \
      >"$dir/$name.madc-build.log" 2>&1; then
    echo "$name,MADC_COMPILE_FAIL,see fixture log" >> "$RESULTS/fixtures.csv"
    failed=1
    continue
  fi
  if ! "$CC" "$dir/$name.madc.o" \
      "$MIRBUILD/libmir.a" -lm -ldl -lpthread \
      -o "$dir/$name.madc" 2>"$dir/$name.madc-link.log"; then
    echo "$name,MADC_LINK_FAIL,see fixture log" >> "$RESULTS/fixtures.csv"
    failed=1
    continue
  fi
  if ! "${QEMU[@]}" "$dir/$name.madc" >"$dir/$name.madc.out" 2>&1; then
    echo "$name,MADC_RUN_FAIL,see fixture output" >> "$RESULTS/fixtures.csv"
    failed=1
    continue
  fi
  if cmp -s "$dir/$name.oracle" "$dir/$name.madc.out"; then
    echo "$name,PASS,byte-identical to GCC under QEMU" >> "$RESULTS/fixtures.csv"
  else
    echo "$name,OUTPUT_MISMATCH,see oracle and MADC output" >> "$RESULTS/fixtures.csv"
    failed=1
  fi
done

aarch64-linux-gnu-readelf -h "$ART/madc-arm-exports.o" \
  "$ART/libmadc-arm-sample.so" "$ART/arm-madc-pie" > "$RESULTS/elf-headers.txt"
aarch64-linux-gnu-readelf -d "$ART/libmadc-arm-sample.so" \
  > "$RESULTS/shared-dynamic.txt"
aarch64-linux-gnu-readelf -r "$ART/madc-arm-exports.o" \
  > "$RESULTS/object-relocations.txt"
aarch64-linux-gnu-objdump -dr "$ART/madc-arm-exports.o" \
  > "$RESULTS/object-disassembly.txt"
exit "$failed"
