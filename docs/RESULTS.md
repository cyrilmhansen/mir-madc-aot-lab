# Results

The first half of this document records the completed macOS arm64 cycle. Linux follow-up results are appended below and do not overwrite those measurements. The Linux x86-64 guest ran as QEMU TCG on an Apple M2 Ultra, so its timings are **emulated x86-64 timings**, not native Linux x86-64 performance. AArch64 execution also used QEMU user mode. Full environment details are in `results/linux-x86_64/environment.json` and `results/linux-aarch64-qemu/environment.json`.

| Experiment | Status | Result |
|---|---|---|
| MADC/MIR host build | Partial | `libmir.a`, `c2m`, `libmadc.a`, and `bin/madc` built. Default full `all` fails at Linux `-soname`; see logs. |
| `make -C src test` | Compile failure | `test_ex.cpp` conflicts with Darwin's global `struct session` declaration from `sys/proc.h`; no test suite executed. |
| Existing AOT test builds | Compile failure | Both include `<elf.h>`, unavailable in macOS SDK; no AOT assertions executed. |
| Standalone libmir JIT | PASS | External C client linked only to `libmir.a`, two modules + `labs`, result verified as 5. |
| MIR binary reload + JIT | PASS | `.bmir` written in one process and reloaded/JITed in a second; result 5. |
| ELF AOT / PIE / `dlopen` | UNSUPPORTED | Requires Linux x86-64 for the requested artifact paths. |
| Mach-O PIE from MADC | PASS | Same function implementation as the `.o`/dylib; emitted and ran with status 0; only `libSystem` needed. |
| Mach-O relocatable object from MADC | PASS | Emitted `MH_OBJECT` with code/data and relocations; system linker accepted it. |
| GCC link of MADC `.o` | PASS | Separate C client linked against the object and `libmadc-0.dylib`, then returned status 0. |
| Mach-O dylib from MADC | PASS | Exported `lab_add`, `lab_scale`, and initialized global data. |
| Same C function logic across JIT/AOT paths | PASS | `macho_demo.c` includes the shared function source, passes in MADC JIT and emitted PIE; the function source also produced the `.o` and dylib used by GCC clients. |
| Independent GCC `dlopen` client | PASS | GCC 16.2.0 client links only `libSystem`; calls both exports and verifies 42 in a new process. |
| Mach-O AOT helper imports | FOUND | Dylib imports three `madc_value_*` helpers and needs `libmadc-0.dylib`. |
| Mach-O resident load/unload | PASS | 30 cycles; dyld reports the test dylib absent after every close. |
| Mach-O fresh-process load | MEASURED | 30 processes after warm-up: median `dlopen` 23.482 ms, median process wall 27.572 ms, p95 28.023 ms; page cache warm, 9.38 MiB median peak RSS, zero major faults. |
| libmpdec 4.0.1 GCC C baseline | PASS | GCC 16.2.0; C-only `--disable-cxx`; static archive and Mach-O dylib. Official archive checksum verified. |
| libmpdec `make check_local` | PASS | 30 suite-result rows: 15 decTest suites against static and shared outputs. |
| libmpdec `make check` | PASS | 296 official decTest PASS rows across static and shared outputs; exit status 0. |
| libmpdec MADC compile | FRONTEND_FAIL | First unit `context.c` rejected six `_Nonnull` declarations from the macOS SDK's `stdlib.h`. |
| libmpdec GCC/GCC matrix cell | PASS | GCC-built C library and GCC-built local + official tests pass. |
| libmpdec MADC/GCC matrix cell | UNSUPPORTED | MADC cannot compile the library's first C unit due to system header parse errors. |
| libmpdec GCC/MADC matrix cell | UNSUPPORTED | No MADC-built library/test executable available; distinct test-compiler experiment is not yet reached. |
| libmpdec MADC/MADC matrix cell | UNSUPPORTED | MADC cannot compile the first library unit on this host; tests are not reached. |

## Synthetic corpus, warmed and fresh-process runs

Each format received one unrecorded warm-up, then 30 measured repetitions in separate processes. The page cache was not flushed; these are warm-cache new-process timings, not cold disk reads. Each corpus function is JIT-compiled eagerly, called once, and checked against an independent expected value. The CSV also carries CPU time, page faults, peak RSS, checksums and bytes. The table below reports median, nearest-rank p95, minimum, and sample standard deviation of parent-observed wall time.

At 5,000 functions, MIR binary decode saves about 10.2 ms of median parse time vs text (15.861 vs 26.084 ms), but total median wall time differs by 24.49 ms (236.85 vs 261.34 ms) and includes JIT and process startup. This does not answer native object reload vs decode+JIT: native ELF AOT emission/reload could not run on this host.

In the resident Mach-O loader benchmark, the first `dlopen` took 23.864 ms; the median of the following 29 cycles was 0.180 ms (p95 0.221 ms). Dyld image inspection confirms the test dylib is removed after each `dlclose`, so these are actual unload/reload cycles; the dependent MADC runtime stays loaded in all 30 cycles. The test dylib's first exported call is verified but too short to time alone at the observed clock resolution; the client also measures a loop of 20,000 verified calls per sample.

Synthetic artifact sizes are in `results/sizes.csv`: `.bmir` ranges from 279 bytes (10 functions) to 84,745 bytes (5,000), compared with MIR text from 1,135 to 594,299 bytes. The emitted dylib is 50,288 bytes, but also needs the 32,452,352-byte MADC runtime dylib. The demo PIE is 49,835 bytes and has no MADC runtime dependency. The relocatable object is 2,224 bytes and needs the runtime for its three helper imports. Native loader raw rows are in `results/macho-new-process.csv` and `results/macho-resident.csv`.

The decNumber 3.68 case was deferred during the initial macOS cycle. Linux results follow below.

## Architecture decisions supported by these runs

1. **Use existing native object/shared formats where a runtime is already acceptable.** The maintained MADC backend emits Mach-O `.o`, dylib and PIE from this host. A separate GCC driver linked the object successfully, and a separate GCC client loaded/called the dylib. On Linux, repeat the same checks with ELF before claiming that route works there. The MIR in-process object loader remains ELF-only and explicitly refuses Mach-O.
2. **Do not add a custom binary cache based on these results alone.** `.bmir` is much smaller than MIR text and saves about 10 ms of parse/decode time at 5,000 functions, but the measured eager JIT still costs about 21–23 ms. The native object-vs-`.bmir`+JIT comparison was not run, so there is no measured case yet for another cache format.
3. **Treat runtime ownership as part of the artifact contract.** The 50 KB dylib imports three MADC value helpers and requires a roughly 32 MB runtime dylib; the develop executable lacks the AOT ledger needed for `-static-libmadc`. The trivial standalone executable needs only `libSystem`. A production cache therefore needs explicit helper inventory and runtime packaging rules.

## Linux ELF and AArch64 results

MADC commit `f541a7a54624869e29b01f2f30b174bc0329eea5` and its maintained `madc/third_party/mir` built on Ubuntu 24.04. The normal Linux develop link needed `OPTIONAL_LIBS=-lpcre2-8`; no tracked MADC/MIR files were changed. Existing Linux AOT unit tests both pass individually: `test_object_load` (9 cases / 142 assertions) and `test_native_shared` (5 cases / 169 assertions). The full `make test` command began successfully but stopped at `test_cir_freeze`, which hit its 180 second wall / 120 CPU second test cap under TCG; this is an incomplete suite, not a pass.

The external `libmir` benchmark exercised all five paths at 10, 100, 1,000 and 5,000 functions: text parse + eager JIT, `.bmir` decode + eager JIT, ELF `.o` + `MIR_object_load`, ELF `.so` + a separate GCC `dlopen`/`dlsym` client, and direct PIE execution. The first four have 30 fresh-process repetitions per corpus after one warm-up; PIE has its own 30-process run. Every path checked its result. The page cache stayed warm. Parent-observed wall time includes process startup; stage times, CPU, faults, RSS, raw samples, artifact sizes and object emission measurements are in `results/linux-x86_64/timings.csv`, `emission.csv`, `pie-execution.csv` and `sizes.csv`.

| Functions | MIR text + JIT median | `.bmir` + JIT median | `.o` load + call median | `.so` load + call median | PIE fresh launch median |
|---:|---:|---:|---:|---:|---:|
| 10 | 18.330 ms | 18.183 ms | 9.673 ms | 7.064 ms | 11.418 ms |
| 100 | 83.400 ms | 75.745 ms | 13.114 ms | 6.746 ms | 11.087 ms |
| 1,000 | 737.794 ms | 666.562 ms | 52.914 ms | 8.651 ms | 11.369 ms |
| 5,000 | 3,618.018 ms | 3,547.672 ms | 217.726 ms | 16.658 ms | 11.076 ms |

The 5,000-function `.o` reload path is about 16.3 times faster than decoding `.bmir` and eagerly JITing it in this emulated environment. `.bmir` saves only about 70 ms relative to MIR text at that size; both still pay for code generation. The `.so` load path is faster for this workload because it uses the system ELF loader and avoids MIR object-loader relocation work. These relative results answer the cache question directionally, but absolute times should be remeasured on native Linux hardware.

Emission is measured separately in `emission.csv`. Artifact bytes and dynamic dependencies are in `sizes.csv` and `elf-security-inspection.txt`. The synthetic MIR `.so` is self-contained for this corpus. The independent GCC client loads `.o` only through `MIR_object_load`; that API is for MIR-emitted objects and is not a general loader for arbitrary GCC `.o` files. ELF images use non-executable `GNU_STACK`, separate R-X and RW load segments, and GNU RELRO where emitted. The emitted PIE is ELF `DYN` with `libc.so.6`; its observed dynamic relocation is on the data/address pool, not a text relocation. MADC's ordinary shared output imports `madc_value_*`, needs `libmadc.so.0`, libc, libz, PCRE2, libstdc++ and related runtime libraries. `-fno-eval-shims` removes these helper imports for the simple exported C API used by the standalone client.

### AArch64 cross compile and QEMU

The documented `cross-aarch64-linux` mode built `bin/madc-aarch64-linux` on the Linux x86-64 guest. The generated `.o` is ELF `REL/AArch64`, its `.so` is ELF `DYN/AArch64`, and its executable is an AArch64 PIE. A separate `aarch64-linux-gnu-gcc` client loaded the MADC `.so`, resolved two functions and a global with `dlsym`, checked `42/42/6`, and closed it. A three-unit set of MADC objects linked with the target GCC driver and returned the same success result as a GCC-built witness. MADC's AArch64 PIE linked three units and ran successfully under QEMU.

All nine `madc/tests/cross/aarch64_*.c` AOT fixtures were compiled by `madc-aarch64-linux`, linked against an AArch64 `libmir.a` and run under `qemu-aarch64`; their output was byte-identical to `aarch64-linux-gnu-gcc` for long double arithmetic and constants, plain-char sign, varargs, large struct by-value arguments, signaling NaN, target macros, float and volatile. Raw statuses and generated binaries are in `results/linux-aarch64-qemu/`. This is functional/ABI validation only; no QEMU execution time is compared with native x86-64 or native ARM64.

### libmpdec and decNumber

The official libmpdec 4.0.1 archive was SHA-256 verified and built with GCC 13.3.0 as C-only (`--disable-cxx`). `make check_local` passes and official `make check` returns exit 0 with 296 PASS rows across static and shared test runs. MADC compiles all 15 C library units to ELF objects and links both `.a` and `.so`; this confirms the macOS `_Nonnull` parser error came from Apple SDK headers. However, the MADC library fails at the first allocation test: a minimal GCC caller receives `NULL` from MADC-built `mpd_qnew()`, while the GCC library returns a non-NULL pointer. See `src/clients/mpdecimal_qnew_repro.c`, the disassembly log and `mpdecimal-matrix.csv`. GCC tests against the MADC library and MADC tests against the MADC library both fail there. MADC-built official test C files against the GCC library pass 134 decTest entries.

The original decNumber 3.68 archive was fetched from the ICU archive mirror and matches its published MD5. Its eight upstream examples compile under GCC and MADC and print byte-identical output. No separate official decTest suite is included in that source archive, so no broader decNumber suite result is claimed.

### Cross-module MIR functional paths

The additional `src/microbench/mir_elf_multimodule_demo.c` example combines two MIR modules, an exported data global, multiple exported functions, a cross-module function call, and a libc `labs` import. Text MIR + eager JIT and `.bmir` decode + eager JIT both verify result 30. ELF `.so` emitted from the same input passes the independent GCC `dlopen`/`dlsym` client, which checks the result function, a second function, and the global; PIE runs directly and returns 30. The corresponding emitted ET_REL `.o` passes parsing/loading and symbol lookup, but calling `demo_result` segfaults. The callback resolves `labs` to libc correctly; GDB shows the bad indirect target is `demo_plus3`. This known object-loader failure is documented with the reproducer and logs in `docs/ISSUES.md` and is not counted as a pass. The existing synthetic `.o` corpus benchmark still passes its correctness checks. This expands functional coverage while qualifying the recommendation that MIR's in-process ELF loader is ready for arbitrary cross-module/import combinations.

## Cache recommendation from Linux results

1. **Prefer ELF `.so` for a persisted library loaded by normal clients** when its import set is acceptable; it gave the shortest first-result path and uses the platform loader. Package the actual MADC runtime dependencies or use the tested `-fno-eval-shims` mode where its restricted semantics fit.
2. **Use ELF `.o` plus `MIR_object_load` when in-process loading and symbol resolution are required.** It is much faster than decode + eager JIT at 5,000 functions in this run, with no machine-code regeneration.
3. **Do not add a specialized native cache format based on these measurements.** ELF already persists and reloads the native code. `.bmir` is compact, but still incurs JIT and is roughly an order of magnitude slower than `.o` loading at the large corpus size. Revisit absolute budgets using native x86-64 and ARM64 measurements.

## Cycle 3: Linux x86-64 native diagnostics

This run used an AMD Ryzen AI 9 HX 370 host. `uname -m` reports `x86_64`; `systemd-detect-virt --vm` reports `none`. The process is containerized (`container-other`), but the guest CPU is hardware-backed and is not QEMU TCG. No performance campaign was run because the libmpdec correctness defect remains unresolved.

The apparent `MIR_object_load` failure was a test-harness use-after-unload. GDB shows the segfault occurs in `load_object`'s return expression after the object has been unmapped. Before that, `demo_result(-8)` returns 30 and the loaded address-pool slots contain the correct `demo_factor` and libc `labs` values. The corrected harness evaluates all checks before unloading. The `.o`, text JIT, `.bmir` JIT and `.so` client all return 30; the PIE exits 30. Reproduce with `scripts/repro-linux-mir-multimodule-object-load.sh`.

The `mpd_qnew()` failure reproduces on MADC's baseline library (`NULL`, exit 2). Replacing only `mpalloc.o` with MADC builds from `-O0`, `-O1`, or `-O2` does not fix it. GDB confirms `RDI=2` at `mpd_qnew_size` entry, then the generated code tests the unrelated `RSI` register before the first allocation and takes the NULL return path. GCC sets both `mpd_alloc` arguments and tests the allocator result instead. `-g` avoids that exact path but aborts later on an invalid `free`. This locates the first invalid behavior in MADC-generated function code, but the available driver does not expose the MIR representation needed to decide whether the source is frontend lowering, MIR optimization, or machine-code generation. No MADC source patch or compiler commit was made.

The rebuilt focused tests pass: `test_object_load` 9 cases / 142 assertions and `test_native_shared` 5 cases / 169 assertions. The first full-suite invocation hit the 180 second wall cap while compiling test binaries. Resuming without optional zstd reached `test_cir_freeze`: 40/48 cases passed (1,240/1,248 assertions). A forced parallel rebuild with `HAVE_ZSTD` enabled reached 42/48 cases (1,286/1,292 assertions). The remaining six failures are C++ `std::string` and file-scope freeze reconstruction cases. These are recorded as suite failures, separately from the initial build timeout.

The GCC libmpdec baseline remains 30 local suite rows and 296 official `make check` PASS rows. MADC library testing remains blocked at its first `mpd_qnew()` allocation; MADC-built test sources against the GCC library previously passed 134 decTest entries. No ARM64 rebuild was needed because no shared backend correction was made; existing AArch64 QEMU fixtures remain as historical validation only.
