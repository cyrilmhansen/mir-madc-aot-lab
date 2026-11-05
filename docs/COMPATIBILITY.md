# Compatibility notes

## Initial macOS host

The first cycle ran on macOS arm64. Its native artifacts use Mach-O, not ELF. The system compiler named `gcc` is Apple Clang; GNU GCC 16.2.0 is separately available as `gcc-16` and was used for libmpdec and the external client. Linux ELF behavior was unavailable during that cycle and is recorded in the follow-up section below.

## MADC and MIR

MADC commit: `f541a7a54624869e29b01f2f30b174bc0329eea5`.

MIR is the maintained in-tree copy at `madc/third_party/mir`. MADC's build invokes that subtree Makefile and emits `libmir.a` and `c2m` in `madc/obj/mir/host` for the host build. Do not run an assumed standalone build from `third_party/mir`.

API declarations are in `madc/third_party/mir/mir-gen.h` and `mir-debug.h`; existing AOT tests are `madc/tests/unit/test_object_load.cpp` and `test_native_shared.cpp`. Their signatures and behaviors are version-specific and must be read from this pinned copy.

## AOT API contract from this checkout

- `MIR_gen_get_code(ctx, func_item, &ptr, &size)` reports a generated function's current machine-code span. Generate every required function before running or serializing a JIT result.
- `MIR_gen_set_object_mode(ctx, 1)` creates a relocation-aware capture when the target supports it; the implementation reports a MIR function error if the target has no capture/relocation backend. The generic header describes the `.o` path as x86-64 ELF. Apple executable emission is separately documented as Mach-O in `mir-debug.h`.
- `MIR_gen_object_emit` packages a complete capture as an ELF `ET_REL`; the returned buffer is `malloc`-owned by the caller. It is described as x86-64 first.
- `MIR_object_emit` writes a relocatable native object: ELF on the Linux backend, Mach-O `MH_OBJECT` on Apple, and COFF on Windows. On this Apple arm64 build the produced object is accepted by the system linker/GCC driver; it is not an arbitrary compiler-object loader.
- `MIR_object_emit_executable(obj, params, &buf, &size)` emits a standalone native image. On ELF this is `ET_EXEC` or PIE; with `shared_p` it is an ELF shared object. Apple builds emit signed Mach-O executable/dylib images instead.
- `MIR_object_read` appends an MIR-emitted ET_REL object into a builder, resolving symbols across appended inputs. It returns `0` on success and `-1` on failure.
- `MIR_object_load(bytes, size, resolver, env, err, err_len)` maps and relocates an MIR-emitted ET_REL object in the current process. It supports the MIR emitter's own relocation subset and resolves built-in `mir.*` helpers before consulting the supplied resolver.
- `MIR_object_loaded_sym(handle, name)` returns a defined global/weak symbol address, or `NULL`. `MIR_object_loaded_unload` unmaps the object; callers must ensure no code or exit callback can still execute.

`MIR_object_load` explicitly refuses Mach-O objects on Apple targets with `in-process loading of Mach-O objects is not supported yet (emit an executable instead)`. The OS linker path does work: MADC emitted a 2,224-byte Mach-O object containing `lab_add`, `lab_scale`, initialized global data, and relocations; GNU GCC 16.2.0 linked it into a separate C executable with the MADC runtime dylib, and that executable returned success.

The concrete declarations are in `mir-gen.h` (lines 24–39) and `mir-debug.h` (lines 308, 440, 477, 487, 491). On Linux, `MIR_object_load` explicitly says it is not a general ELF loader and does not accept arbitrary GCC `.o` files.

## Standalone libmir proof on the available host

`src/microbench/libmir_smoke.c` calls `MIR_scan_string`, `MIR_load_module`, `MIR_load_external`, `MIR_link`, `MIR_gen` and the resulting native function pointers. It is compiled only against MADC's `obj/mir/host/libmir.a`; it does not link `libmadc` or use MADC's frontend. It verifies a cross-module MIR call and a libc `labs` call. `scripts/build-microbench.sh` also writes MIR binary to `program.bmir` and reads it in a fresh process before JIT compilation. Both currently return the checked value `5`.

The MIR header declares `MIR_get_global_item`, but this checkout's `libmir.a` does not define that symbol. The standalone example therefore locates a function by walking module items and checking `MIR_item_name` and `MIR_func_item`.

## Mach-O AOT observation

`macho_demo.c` includes the same `macho_exports.c` functions tested by the separate GCC clients. MADC JIT executes this demo, and `madc -o` emits its arm64 Mach-O PIE. MADC also emits the shared function source as a Mach-O `.o` and dylib. The standalone GCC C client loads the dylib via `dlopen`, resolves `lab_add` and `lab_scale` with `dlsym`, reads initialized global data through `lab_scale`, checks results, and closes the handle. The client links only `libSystem`; it has no direct MIR/MADC link dependency. The emitted dylib depends on `libmadc-0.dylib`, and `nm -u` reports these imports: `_madc_value_get_integer`, `_madc_value_get_type_id`, `_madc_value_set_integer`. A 30-process check confirms dyld retains the MADC runtime after the client closes the sample dylib.

`otool -hv` reports `MH_EXECUTE` with the `PIE` flag. Both emitted images pass `codesign --verify --deep --strict`. The executable `__TEXT` segment is R-X and data segments are RW, with no W+X segment in these images. This is not an ELF relocation audit.

## ABI / shared library

The independent GCC `dlopen` client works for Mach-O as described above. ELF `.so` loading and ABI results are recorded in the Linux section below.

## Linux x86-64 and AArch64 follow-up

The Linux host was an Ubuntu 24.04 x86-64 guest under QEMU TCG on an Apple M2 Ultra. It is not native x86-64 hardware. See `results/linux-x86_64/environment.json` and `results/linux-aarch64-qemu/environment.json` for CPU, memory, compiler, binutils, glibc, cross-toolchain and QEMU versions. MADC remains pinned at `f541a7a54624869e29b01f2f30b174bc0329eea5`; its tracked checkout is clean.

The actual Linux MADC command is `make -C madc/src OPTIONAL_LIBS=-lpcre2-8`; without that explicit optional link library, the develop build ended with undefined `pcre2_substitute_8`. The focused Linux AOT tests pass: `test_object_load` (9 cases / 142 assertions) and `test_native_shared` (5 cases / 169 assertions). The full suite hit its 180 second / 120 CPU second cap at `test_cir_freeze` under TCG.

On Linux, the standalone MIR benchmark linked an external C client only with `madc/obj/mir/host/libmir.a`. It verified MIR text to eager JIT, `.bmir` to eager JIT, ELF `.o` to `MIR_object_load`, ELF `.so` with a separate GCC `dlopen` client, and direct ELF PIE. Four corpora (10/100/1,000/5,000 functions) ran in 30 fresh processes each after warm-up. The `.o` object-loader path returned all expected calls with no regeneration; the shared path resolved every exported function independently. Details and raw measurements are in `results/linux-x86_64/`.

The expanded two-module example in `src/microbench/mir_elf_multimodule_demo.c` verifies globals, exports, a cross-module call and libc `labs`: text JIT, `.bmir` JIT, a GCC-loaded `.so`, and a directly executed PIE pass. Its combined `.o` case loads and exposes symbols, and `demo_plus3` passes, but `demo_result` segfaults at an indirect call: see the captured resolver/GDB evidence in `docs/ISSUES.md`. Thus the corpus `.o` results establish the tested MIR-emitted object-loader path, not arbitrary imported-symbol relocation combinations.

The Linux ELF audit found `ET_REL` x86-64 objects, PIE `ET_DYN` executables, and shared `ET_DYN` images. ELF PIE segments separate R-X code and RW data, use a non-executable `GNU_STACK`, and have GNU RELRO. There are no text relocations in the emitted images inspected. The direct MIR synthetic shared image has no dynamic imports for this corpus. A MADC frontend shared image normally has `DT_NEEDED libmadc.so.0` and `madc_value_*` imports; its transitive dependencies include libc, libz, PCRE2, libstdc++ and related libraries. With `-fno-eval-shims`, the sample shared C API has no MADC helper imports and works with a GCC client without libmadc.

The documented `make -C src cross-aarch64-linux` mode built `bin/madc-aarch64-linux` on the Linux x86-64 guest. AArch64 output was linked by `aarch64-linux-gnu-gcc` and run with `qemu-aarch64 -L /usr/aarch64-linux-gnu`. ELF `.o`, `.so`, and PIE artifacts were verified as AArch64. A separate GCC client used `dlopen`/`dlsym` on the MADC `.so`, checked multiple functions and initialized global data, and closed the handle. Three MADC compilation units linked with GCC and executed correctly; all nine `tests/cross/aarch64_*.c` AOT fixtures matched their GCC oracle byte-for-byte. This establishes the exercised AArch64 ABI/functionality under emulation, not native ARM64 performance.

The Linux libmpdec matrix distinguishes the C test runner compiler from the library compiler. All 15 library units compile with MADC, but MADC-built library allocation is wrong: `mpd_qnew()` returns `NULL` in the minimal reproducer and official test runners crash at that first allocation. MADC-built test sources against the GCC library pass. The compiler error is in emitted function code, after front-end parsing and successful ELF linking; the current reproducer does not yet distinguish MADC frontend MIR lowering from MIR native code generation. `-fno-eval-shims` was required for MADC-compiled test objects to link as ordinary GCC clients without MADC value helper imports.

## Cycle 3 native Linux host

The follow-up ran in a container on an AMD Ryzen AI 9 HX 370 x86-64 host (`systemd-detect-virt --vm` = `none`); it is not the prior QEMU TCG guest. The MADC submodule remains at `f541a7a54624869e29b01f2f30b174bc0329eea5` on local branch `experiment/mir-aot-correctness`, with no compiler source changes.

GDB corrected the multi-module diagnosis: the reported segfault occurs after `MIR_object_loaded_unload`, when the demo's return expression calls `demo_plus3` through an unmapped pointer. `demo_result(-8)` itself returned 30, and the relocated `.mir.addrpool` entries held the expected `demo_factor` and `labs` addresses. The harness now completes all checks before unloading. The standalone script verifies object loading; JIT, `.bmir`, `.so`, and PIE were also rerun successfully.

The libmpdec diagnosis is narrower but incomplete. `mpd_qnew_size` enters with its single ABI argument in `RDI`; the first wrong instruction tests `RSI` before calling the allocator, then takes the NULL return branch. The same failure occurs when only `mpalloc.c` is rebuilt at `-O0`, `-O1`, and `-O2`. An MADC `-g` build changes the code but later aborts on invalid `free`. This proves invalid MADC-generated machine code, but does not yet distinguish CIR/MIR construction, MIR optimization, or backend generation. No fix or cross-target effect is claimed.

The focused test results remain 9/9 cases / 142 assertions for `test_object_load` and 5/5 / 169 for `test_native_shared`. The first full-suite invocation hit its 180 second wall cap while compiling test binaries. The resumed run without zstd reached `test_cir_freeze` and passed 40/48 cases (1,240/1,248 assertions). A forced rebuild with `HAVE_ZSTD` reached 42/48 (1,286/1,292); the six failures concern C++ `std::string` and file-scope freeze reconstruction. These test failures are distinct from the initial build timeout and are not caused by a missing zstd package. No native benchmark or ARM64 rebuild was performed because the allocation defect remains unresolved and no shared backend patch was made.
