# Linux handoff: MIR/MADC AOT lab

## Purpose and pinned inputs

This independent lab evaluates the maintained MIR backend in MADC as a lightweight AOT route: MIR text and `.bmir` JIT, ELF `.o` persistence/reload, `.so` loading through the system loader, PIE execution, and real C library compatibility. The lab is a separate repository from the compiler.

MADC is pinned as a submodule at **`f541a7a54624869e29b01f2f30b174bc0329eea5`** (MADC 0.106.1, maintained MIR in `third_party/mir`). The commit is available from `https://github.com/cyrilmhansen/madc`. Do not advance this gitlink when continuing comparable experiments.

The top-level layout is:

- `src/`: MIR generators, C clients, and the `mpd_qnew()` reproducer.
- `scripts/`: host, benchmark, AArch64/QEMU, libmpdec and decNumber build/reproduction scripts.
- `results/macos-arm64/`: first campaign, measured on native Apple M2 Ultra.
- `results/linux-x86_64/`: second campaign on Ubuntu 24.04 x86-64 emulated by QEMU TCG; this includes timing CSVs, logs and source-independent diagnostics.
- `results/linux-aarch64-qemu/`: cross-generated ARM64 artefact inspections and QEMU/GCC fixture results.
- `docs/`: consolidated results, compatibility and issue notes.
- `downloads/SHA256SUMS`: hashes for external source archives. Archives and extracted third-party trees are deliberately not committed.

Generated executables/libraries and most object files are ignored. The two small diagnostic objects needed for the known failures are deliberately tracked: the multi-module MIR `multimodule.o` and the MADC-built libmpdec `mpalloc.o` containing `mpd_qnew_size`. Sources and scripts remain the primary way to regenerate artifacts.

## Current findings

### ELF and cache measurements

The four synthetic corpora (10, 100, 1,000 and 5,000 functions) passed correctness checks for MIR text + eager JIT, `.bmir` + eager JIT, ELF `.o` + `MIR_object_load`, `.so` + a separate GCC `dlopen` client, and direct PIE. Each benchmark route has 30 fresh-process observations after one warm-up; emitted artefact creation is measured separately. At 5,000 functions, median time to the verified result was 3,618 ms (text + JIT), 3,548 ms (`.bmir` + JIT), 218 ms (`.o` reload), 17 ms (`.so` load), and 11 ms (PIE launch). These x86-64 numbers are **emulated QEMU TCG measurements**, with a warm Linux page cache, not native x86 performance.

A richer functional case in `src/microbench/mir_elf_multimodule_demo.c` combines two MIR modules, globals, exports, a cross-module call and libc `labs`. Cycle 3 reproduced its SIGSEGV, then found the harness called `demo_plus3` after `MIR_object_loaded_unload`; `demo_result` had returned 30. The harness now checks everything before unload. `scripts/repro-linux-mir-multimodule-object-load.sh` reproduces the corrected `.o` path; text JIT, `.bmir`, `.so`, and PIE were also rerun successfully. GDB pool inspection confirmed the `demo_factor` and `labs` relocation values. See the cycle3 GDB logs and corrected diagnosis in `docs/ISSUES.md`.

### Cross-compiled ARM64

On the Linux x86-64 guest, MADC's `cross-aarch64-linux` build produced ARM64 ELF `.o`, `.so` and PIE. A separate AArch64 GCC `dlopen`/`dlsym` client and three independently compiled MADC units linked by AArch64 GCC passed under `qemu-aarch64`. All nine existing `tests/cross/aarch64_*.c` fixtures matched GCC output under QEMU. This establishes exercised correctness/ABI under emulation, not native ARM64 performance. Tool versions and raw records are in `results/linux-aarch64-qemu/`.

### Decimal libraries and known code-generation failure

Official libmpdec 4.0.1 source archive: `https://www.bytereef.org/software/mpdecimal/releases/mpdecimal-4.0.1.tar.gz`, SHA-256 `96d33abb4bb0070c7be0fed4246cd38416188325f820468214471938545b1ac8`. GCC C-only build and both `make check_local` and `make check` passed; the latter recorded 296 PASS rows. MADC compiled all 15 C units with the Linux system headers and linked the library, but the library returns `NULL` from `mpd_qnew()` and its test runners fail at the first allocation. The four GCC/MADC library-vs-runner combinations and outcomes are in `results/linux-x86_64/mpdecimal-matrix.csv`. MADC-compiled test files against the GCC library passed 134 decTest entries.

`src/clients/mpdecimal_qnew_repro.c` is the caller reproducer. `scripts/try-linux-mpdecimal-madc.sh` records the exact source-unit order and options (`-c -O2 -std=c99 -DCONFIG_64 -DASM -DNDEBUG -fPIC`). `scripts/repro-linux-mpdecimal-qnew.sh` links/runs the GCC witness and failing MADC library and captures the object disassembly. The tracked `mpalloc.o` is the MADC-produced object; do not mistake it for a portable input to another architecture. Cycle 3 confirms at GDB entry that `mpd_qnew_size` receives its one argument in `RDI`, then tests non-argument `RSI` before the first allocation. Rebuilding just `mpalloc.c` at `-O0`, `-O1`, and `-O2` preserves the failure. This identifies the first invalid machine behavior but does not distinguish CIR/MIR construction, MIR optimization, or backend generation.

DecNumber 3.68 source was obtained from the ICU archive mirror at `https://ftp.math.utah.edu/pub/mathcw/decNumber/decNumber-icu-368.zip`; MD5 `ba48a64b619f249772d5ad56f510146f`, SHA-256 in `downloads/SHA256SUMS`. Its eight original examples compile with GCC and MADC and produce byte-identical outputs. The archive has no decTest suite.

## Environment records

macOS measurements are from macOS 27.2 arm64, Apple M2 Ultra (24 CPU cores, 64 GiB), Apple Clang 21.0.3, Apple ld 27037.1 and Darwin libSystem. Linux measurements are from Ubuntu 24.04 x86-64 under Lima 2.2.1 / QEMU 11.1.3 TCG on the same M2 Ultra: Linux 6.8.0-142, 8 vCPUs, 16 GiB, glibc 2.39, GCC 13.3.0, Clang 18.1.3, binutils 2.42, AArch64 cross GCC 13.3.0, and qemu-user 8.2.2. The Linux x86 CPU is an emulated QEMU TCG CPU. Full machine-readable records: `results/macos-arm64/environment.json`, `results/linux-x86_64/environment.json`, `results/linux-aarch64-qemu/environment.json`.

## Reproduce on a new Linux machine

### Clone and install tools

```sh
git clone --recurse-submodules https://github.com/cyrilmhansen/mir-madc-aot-lab.git
cd mir-madc-aot-lab
git -C madc checkout f541a7a54624869e29b01f2f30b174bc0329eea5
git submodule status
```

On Ubuntu/Debian, the tested toolchain needs the native build tools and PCRE2; the cross/QEMU steps need the AArch64 GNU toolchain and QEMU user emulator. For source downloads and diagnostics also install curl, unzip, Python, GDB and binutils:

```sh
sudo apt-get update
sudo apt-get install build-essential gcc g++ make pkg-config libpcre2-dev zlib1g-dev \
  libzstd-dev libsqlite3-dev libgdbm-dev curl unzip python3 gdb binutils \
  gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu qemu-user
```

Build MADC/MIR without editing the checkout. This Linux develop configuration needs the explicit PCRE2 optional link flag:

```sh
scripts/build-linux-madc.sh
make -C madc/src OPTIONAL_LIBS=-lpcre2-8
```

The latter command matches the successful baseline. `make -C madc/src test OPTIONAL_LIBS=-lpcre2-8` is the full suite; on the emulated VM it hit the suite's 180 s / 120 CPU s cap at `test_cir_freeze`, so that run was incomplete. The focused AOT tests passed individually:

```sh
make -C madc/src ../bin/test_object_load ../bin/test_native_shared OPTIONAL_LIBS=-lpcre2-8
madc/bin/test_object_load
madc/bin/test_native_shared
```

### AOT and cross-compile reproduction

```sh
scripts/run-linux-aot-benchmarks.sh
scripts/build-linux-aarch64-cross.sh
scripts/run-linux-aarch64-qemu.sh
```

The AOT benchmark defaults to 30 repetitions (`REPEATS=30` can be set explicitly). Cross execution expects `qemu-aarch64 -L /usr/aarch64-linux-gnu`. Do not compare QEMU timings to native x86-64/ARM64 timings.

### Reproduce the object-loader failure

The x86-64 `.o` diagnostic artifact is tracked; on a new host rebuild the harness and regenerate it if you want to confirm addresses under that process's ASLR:

```sh
mkdir -p results/linux-x86_64/artifacts results/linux-x86_64/logs
gcc -g -O0 -I madc/third_party/mir src/microbench/mir_elf_multimodule_demo.c \
  madc/obj/mir/host/libmir.a -lm -ldl -lpthread \
  -o results/linux-x86_64/artifacts/mir-elf-multimodule-demo
results/linux-x86_64/artifacts/mir-elf-multimodule-demo generate \
  results/linux-x86_64/artifacts/multimodule.mir \
  results/linux-x86_64/artifacts/multimodule.bmir
results/linux-x86_64/artifacts/mir-elf-multimodule-demo emit object \
  results/linux-x86_64/artifacts/multimodule.mir \
  results/linux-x86_64/artifacts/multimodule.o
gdb -q -batch -ex run -ex bt -ex 'info registers' --args \
  results/linux-x86_64/artifacts/mir-elf-multimodule-demo load \
  results/linux-x86_64/artifacts/multimodule.o
```

For comparison, run `jit-text` and `jit-bmir`, emit `shared` and `pie`, then use `src/clients/mir_elf_multimodule_client.c` as the independent GCC `.so` client. The expected verified result is 30. Do not treat successful `.so`/PIE paths as proof that `MIR_object_load` works for this relocation combination.

### Reproduce libmpdec and `mpd_qnew()`

The scripts fetch the public release archive when absent, verify its SHA-256, unpack to ignored `vendor/`, and keep generated files out of Git:

```sh
scripts/build-mpdecimal.sh
scripts/try-linux-mpdecimal-madc.sh
scripts/repro-linux-mpdecimal-qnew.sh
```

The first script configures `--disable-cxx`, builds with GCC, then runs both local and official test targets. The second compiles all 15 C units with the exact options recorded in `results/linux-x86_64/mpdecimal-madc-units.csv`, then archives/links them. The third compares the GCC witness with a GCC caller linked to the MADC-built static library and retains a fresh `mpalloc.o` disassembly. The expected baseline remains `mpd_qnew=NULL`/exit 2 for the MADC library. `MPDECIMAL_SOURCE` and `MADC_DIR` can override the detected relative locations.

To regenerate the GCC/MADC runner matrix, use `results/linux-x86_64/mpdecimal-matrix.csv` as the outcome checklist and the captured `mpdecimal-tests-*` logs for the exact prior run outcomes. Keep the runner compiler and library compiler as independent axes; do not infer ABI correctness from MADC/MADC alone.

DecNumber examples can be reconstructed with `scripts/build-linux-decnumber.sh`; it verifies the archive MD5 and compares all eight outputs.

## Cycle 3 status and next steps

The reported loader crash was a use-after-unload in the lab harness, not an MADC relocation defect. The fix is in the lab source and the dedicated script validates `.o` load result 30. MADC remains at the pinned baseline on local branch `experiment/mir-aot-correctness`; no compiler source changes or commits were made.

`mpd_qnew()` remains unresolved for the normal `-DASM` libmpdec build. Cycle 4 identified the root cause: MADC discards non-empty GNU inline-assembly templates while parsing, so `_mpd_mul_words()` reads uninitialized `h`/`l` outputs. `MADC_DUMP_MIR=1` exposes the AOT pre-link MIR. The independent `src/clients/mpdecimal_inline_asm_min.c` reproduces the first semantic loss without libmpdec. See `docs/LIBMPDEC_ROOT_CAUSE.md`; do not attribute the failure to ABI or MIR inlining.

On this native x86-64 host, the focused object-load/native-shared tests pass. The first full-suite invocation timed out at 180 seconds while compiling tests. The resumed run without optional zstd passed 40/48 `test_cir_freeze` cases; a forced rebuild with installed zstd enabled passed 42/48, with six C++ header/global reconstruction failures. Existing AArch64 QEMU fixtures remain the only ARM64 validation; no ARM64 build was needed because no shared backend patch was made. Native benchmarks were deferred until the remaining compiler correctness issue is resolved.

## Cycle 4 handoff

The lab is on `experiment/mir-aot-correctness-cycle3`; MADC is on the dedicated
`experiment/mir-aot-correctness` branch at the unchanged baseline
`f541a7a54624869e29b01f2f30b174bc0329eea5`. Temporary instrumentation for MIR
before/after `MIR_link` and disabling only MIR inlining was removed from the
MADC source after collecting `results/linux-x86_64/logs/cycle4-*`. The MADC
working tree is clean. Focused object-load and native-shared tests pass after
the removal.

The `-DASM` libmpdec issue is traced to unsupported non-empty GNU extended asm
in MADC's source parser/CIR builder, not c2mir, the MIR inliner, machine
register allocation, ELF relocation, or symbol resolution. No minimal compiler
patch was made because correct handling requires extended-asm semantics; the
ANSI 128-bit path only verified allocation initialization/free and is not a
full-library result. The failing cross-compiler regression harness is
`scripts/test-linux-madc-inline-asm-min.sh`. No full libmpdec matrix, ARM64
rebuild, or generic benchmark campaign was run in Cycle 4.

The Cycle 3 full-suite baseline remains: after the initial 180-second build
timeout, the zstd-enabled suite completed with six `test_cir_freeze` C++
failures (42/48 cases, 1,286/1,292 assertions). Treat those as independent.

## Cycle 5 handoff

The lab is still on `experiment/mir-aot-correctness-cycle3`. MADC is committed
on `experiment/mir-aot-correctness` at
`868847a76434058483bade03ead09ba6acb9d771`, based on the preserved
`f541a7a54624869e29b01f2f30b174bc0329eea5`. The root lab commit updates only
the gitlink and cycle5 report/artifacts; do not push without the owner's
request.

The full supported libmpdec `MACHINE=uint128` matrix passes. GCC x64 and GCC
uint128 each pass 30 local and 296 official rows. All four GCC/MADC uint128
library/test-runner combinations pass the same counts. MADC built 15/15 units,
and the `mpd_qnew()` probe checks structure state, allocation sizes, safe
buffer writes/reads, and two frees. Raw results and commands are in
`docs/LIBMPDEC_CYCLE5.md` and `results/linux-x86_64-native/libmpdec-cycle5/`.

The MADC parser now rejects non-empty GNU asm templates, clobbers, `asm goto`,
and outputs without an explicit tied input. The `mulq` regression compiles and
runs under GCC/Clang with `high=0`; MADC refuses it at `-O0/-O1/-O2`. Empty
operand-only/tied-output forms and asm declaration-label fixtures pass. This is
a refusal boundary, not extended-asm support.

The native `.so` measurements verify one decimal multiply per process: median
load 75.0 µs / operation 2.51 µs for GCC uint128, 100.3 µs / 5.56 µs for MADC
uint128. The combined MADC `.o` also passes the CLI `MIR_object_load` path; 30
fresh processes return the checked product. The reported 7.08 ms median
includes MADC startup. A user-library `.bmir` JIT path was not constructible
through this C-library flow. No new ARM64 claim was needed because codegen and
the integrated MIR backend did not change. The six baseline C++ freeze-suite
failures remain independent and were not rerun this cycle.
