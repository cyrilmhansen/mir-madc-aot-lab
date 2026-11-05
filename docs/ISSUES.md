# Issues and reproducers

## Host toolchain is not Linux ELF

Reproducer: `uname -a`, `uname -m`, `gcc --version`, `ld -v`. Results are Darwin arm64; `gcc` reports Apple Clang 21.0.3 and `ld` is Apple's linker. Therefore ELF object loading, ELF PIE emission, Linux `dlopen` behavior, Linux page-fault accounting and GNU binutils inspection are unsupported on this host.

## System make is too old

Reproducer: `make -C src` fails in `src/Makefile:258`: GNU make 3.81 is rejected on Darwin. Install Homebrew `make coreutils gnu-sed grep` and put their `gnubin` directories first on `PATH` as required by MADC's Makefile.

## PCRE2 include path not discovered in develop mode

Reproducer: invoking MADC build with fresh Homebrew dependencies failed at `madc_regex.cpp:17` with `pcre2.h file not found`. Workaround tried: explicitly pass `OPTIONAL_CPPFLAGS='-I/opt/homebrew/opt/pcre2/include -DPCRE2_STATIC ...'` and the static PCRE2/zstd paths.

## Linux link flags in develop mode on Darwin

Reproducer: after successful compilation, default develop link failed with Apple's ld: `unknown options: --whole-archive --no-whole-archive`. Workaround tried: `WHOLE_ARCHIVE_BEGIN=-Wl,-force_load WHOLE_ARCHIVE_END=` and Darwin-compatible library flags. The subsequent PIC build also rejected `-fno-semantic-interposition` under `-Werror`; override `PIC_CXXFLAGS` to omit it. These are experiment command-line overrides only; no project source was changed.

Full logs are stored in `results/logs/`, including `default-build-failure.log` (the `-soname` failure), `test-madc.log`, `test_object_load.log`, and `test_native_shared.log`.

## Current verified run

`scripts/build-madc.sh` produces a host `bin/madc`, `libmadc.a`, and the MIR build products, but does not complete the default `all` target because the Linux-mode shared-library recipe passes `-Wl,-soname` to Apple's linker. `make -C src test` (with the host path/force-load/PCRE2 overrides) stops while compiling `test_ex.cpp`: its `session` class name collides with Apple's `struct session` from `sys/proc.h`. This happens before any unit tests run. `test_object_load` and `test_native_shared` each fail compilation at `<elf.h>`.

The standalone MIR JIT and `.bmir` fresh-process checks do pass. Artifacts and command output are in `results/artifacts/` and `results/logs/`. This is a concrete MADC/MIR baseline for the host JIT and serialized-IR route, but it does not validate the requested ELF AOT route.

## MADC front-end fails on the first libmpdec C translation unit

After building libmpdec 4.0.1 with GNU GCC, the first actual source unit tried with MADC was `libmpdec/context.c` (`madc -c -O2 -I. ... context.c`). MADC fails while parsing the host SDK's `<stdlib.h>` at six function-pointer declarations containing Clang's `_Nonnull` nullability annotation (`Expecting parameter type in function pointer typedef`). Adding `-D_Nonnull=`, `-D_Nullable=`, and related macro definitions did not alter the diagnostic. This is a frontend/system-header compatibility failure before MIR lowering, object capture or ABI/link validation. MADC does not recognize GCC's `-fpreprocessed` option, so preprocessing first with GCC is not currently a direct workaround. No algorithm source was changed.

The C-only library baseline is independently successful: `vendor/mpdecimal-4.0.1-c-only` was configured with `--disable-cxx`, GNU GCC 16.2.0, and its `make check_local` and official `make check` both returned exit status 0. The official archive's SHA-256 is `96d33abb4bb0070c7be0fed4246cd38416188325f820468214471938545b1ac8`. Logs are `mpdecimal-check-local-verified.log` and `mpdecimal-check-verified.log`. The verified full run has 296 PASS rows (official decTest file results for static and shared builds); it does not report individual assertion counts.

## MADC static runtime packaging unavailable in the develop build

Reproducer: `madc -static-libmadc -shared ...` fails before emission: this `bin/madc` has no AOT ledger carrier, and three runtime symbols would remain unresolved. The ordinary Mach-O dylib therefore imports `madc_value_*` and needs the separately built `libmadc-0.dylib`. This is separate from ELF/PIC behavior.

## decNumber 3.68 deferred on the initial macOS host

The official decNumber page still describes version 3.68 and links to the ICU source archive, but following its download link currently returns HTTP 404. The GCC repository alternative was not used. The case remains deferred because MADC already fails on the first libmpdec C unit due to the host system headers, while the requested AOT/ABI matrix needs Linux x86-64. No decNumber compilation or correctness result is claimed.

## Linux build and suite limits under QEMU TCG

The Linux guest is Ubuntu 24.04 x86-64 under QEMU TCG on Apple M2 Ultra, not a native x86-64 machine. Its timings must not be presented as native x86-64 performance. `make -C src` reached a link error for `pcre2_substitute_8` because this MADC develop configuration left `OPTIONAL_LIBS` empty. Reproducer/workaround: `make -C madc/src OPTIONAL_LIBS=-lpcre2-8`. No source edits were made.

`make -C madc/src test OPTIONAL_LIBS=-lpcre2-8` passed the tests it reached, then the test harness killed `test_cir_freeze` at its 180 s wall / 120 CPU s cap. This is a VM execution-time limit; it is not a full test-suite pass. The focused AOT tests were run separately and passed: `test_object_load` 9/9 cases and `test_native_shared` 5/5 cases. Their logs are under `results/linux-x86_64/logs/`.

## libmpdec 4.0.1: MADC-generated allocation code returns NULL

Linux GCC 13.3.0 builds and both official test targets pass. Unlike macOS, Linux MADC compiles all 15 `libmpdec` C units and links the static and shared libraries, so the `_Nonnull` failure was Apple SDK-specific. The MADC library nevertheless fails at its first test allocation. Both a GCC-built test runner and an MADC-built test runner crash when linked to the MADC library; an MADC-built test runner against the GCC library passes 134 decTest entries.

Minimal reproducer: `src/clients/mpdecimal_qnew_repro.c`. GCC + GCC libmpdec reports a non-NULL `mpd_qnew()` result; the same GCC executable linked to MADC-built `libmpdec-madc.a` reports NULL and exits 2. `mpdecimal-matrix.csv` records the four cells. `mpdecimal-qnew-disassembly.txt` captures the MADC-built `mpd_qnew_size` object. That function has one C argument in the x86-64 ABI, but its emitted allocation paths consume registers beyond that argument without defining them; this points to incorrect MADC-generated machine code in the function body. The ELF object links and its relocations apply, while the external GCC caller uses the public ABI. Current evidence localizes the defect to MADC's C-to-machine-code path (frontend MIR lowering or MIR code generation); it does not distinguish those sublayers yet. No workaround changed libmpdec algorithms, and no MADC/MIR patch was made.

The MADC-built shared library also imports five `madc_value_*` helpers and needs `libmadc.so.0`; the standalone load test therefore links that runtime. This dependency is independent of the allocation miscompile.

## AArch64 QEMU scope and runtime helpers

The cross compiler and all nine existing AArch64 AOT fixtures pass under QEMU with byte-identical output to GCC. This validates the target ABI for the exercised cases. It does not validate performance on native ARM64. The complete MADC `aarch64_ldouble_lane.sh` JIT/bootstrap legs were inspected but not run: the AOT fixture loop covers all its C fixtures, while the script's additional target `c2m` JIT and bootstrap work is outside the AOT requirement and substantially more expensive under TCG.

By default, a MADC-produced `.so` can have a `DT_NEEDED` entry for `libmadc.so.0` and imports `madc_value_*`, even for a small exported C sample. With `-fno-eval-shims`, the tested sample exports and initialized global load from a normal GCC `dlopen` client with no MADC runtime dependency. Treat that option as a deliberate runtime/host-call contract, not a global compatibility switch.

## decNumber 3.68 Linux outcome

The official page's original `speleotrove.com` download was unavailable in the first run. The same original `decNumber-icu-368.zip` is available from the ICU archive mirror; its MD5 `ba48a64b619f249772d5ad56f510146f` matches the archive manifest. The unmodified source compiles and runs examples 1–8 under GCC and MADC; all outputs compare byte-for-byte. The archive contains examples, not the official decTest corpus, so broader decNumber test coverage remains unavailable.

## Linux MIR object loader: combined imported call/data relocation reproducer

`src/microbench/mir_elf_multimodule_demo.c` builds two MIR modules containing an exported function and global, a cross-module call, and an imported libc `labs` call. Text MIR + eager JIT and `.bmir` + eager JIT both return 30. The emitted ELF `.so` passes a standalone GCC `dlopen`/`dlsym` client, and the PIE executes directly (exit status 30). The emitted `.o` is a valid ET_REL x86-64 object and `MIR_object_load` returns valid addresses for the defined function/global; calling `demo_plus3` also returns -5. Calling `demo_result` segfaults.

The resolver log confirms that each request for `labs` returns libc's address. In the failing loaded image, `demo_result` instead jumps to the loaded `demo_plus3` entry (GDB RIP equals `MIR_object_loaded_sym(..., "demo_plus3")`). This reproducer therefore isolates a relocation/object-loader failure in the combined object path; it is not a resolver miss, shared-loader failure, JIT failure, or ELF emission failure. The object has `.rela.text` PC-relative references to `.mir.addrpool` and `.rela.mir.addrpool` absolute references to `demo_factor` and `labs`. No MIR/MADC source was patched. Captured logs: `results/linux-x86_64/logs/multimodule-object-load.{stderr,status}`; object: `results/linux-x86_64/artifacts/multimodule.o`.
