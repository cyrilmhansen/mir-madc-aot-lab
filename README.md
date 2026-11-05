# MIR/MADC AOT lab

This lab pins MADC at `f541a7a54624869e29b01f2f30b174bc0329eea5` and exercises the MIR copy maintained in `madc/third_party/mir`. MIR is built by MADC into `madc/obj/mir/`; there is no standalone MIR Makefile contract.

## Environments and status

The first cycle ran on macOS 27.2 arm64 (Apple M2 Ultra, 64 GiB), with Apple Clang 21.0.3, Apple ld 27037.1, SDK 27.0 and Darwin `libSystem`. Its measurements and artifacts remain in `results/macos-arm64/`.

The follow-up Linux run used Ubuntu 24.04 x86-64 in a Lima/QEMU TCG VM on that Apple M2 Ultra. It generated ELF `.o`, `.so` and PIE, and completed 30 fresh-process benchmark repetitions across four synthetic corpus sizes. `MIR_object_load` passes that corpus but has a retained failure on a richer two-module object with a global, cross-module call and libc import; the same case passes through text/bmir JIT, `.so` and PIE. Cross-compiled AArch64 fixtures execute under QEMU. **Linux x86-64 timings are emulated, not native hardware measurements.** Environment details are in `results/linux-x86_64/environment.json` and `results/linux-aarch64-qemu/environment.json`.

On macOS, `make -C src` initially failed because system make was GNU make 3.81, and the develop build needed Darwin-specific overrides. The MADC AOT unit tests could not compile because of the Apple SDK. On Linux, the focused AOT tests pass, while the full suite hit its configured timeout under TCG. libmpdec now compiles all units with MADC on Linux, but its allocation code is misgenerated (`mpd_qnew()` returns `NULL`); MADC-compiled tests against the GCC library pass. decNumber 3.68 examples 1–8 pass with both compilers and match byte-for-byte. See `docs/RESULTS.md`, `docs/ISSUES.md`, and `docs/COMPATIBILITY.md`.

## Layout

- `madc/`: pinned MADC checkout, including its maintained MIR subtree.
- `src/`: standalone MIR examples, clients and microbenchmark sources.
- `scripts/`: reproducible build and experiment entry points.
- `results/`: machine-readable environment, correctness and timing outputs plus logs.
- `docs/`: compatibility notes, results and issue/reproducer notes.

For a clean migration, clone with `git clone --recurse-submodules https://github.com/cyrilmhansen/mir-madc-aot-lab.git`; `HANDOFF_LINUX.md` contains the pinned revision, tool setup, reproduction commands and next diagnostic steps. The MADC gitlink is fixed at `f541a7a54624869e29b01f2f30b174bc0329eea5`. Downloaded source archives and extracted dependency trees are ignored; `downloads/SHA256SUMS` records their expected hashes.

## Reproduction

On the supplied macOS host, install prerequisites with `brew install make coreutils gnu-sed grep pcre2 zstd`, then run:

```sh
scripts/build-madc.sh
```

On macOS use `scripts/build-madc.sh`, `scripts/run-correctness.sh`, `scripts/run-benchmarks.sh`, `scripts/run-native-load-benchmarks.sh`, `scripts/build-mpdecimal.sh` and `scripts/try-madc-mpdecimal.sh`. On Linux, use `scripts/build-linux-madc.sh`, `scripts/run-linux-aot-benchmarks.sh`, `scripts/build-linux-aarch64-cross.sh`, `scripts/run-linux-aarch64-qemu.sh`, `scripts/build-mpdecimal.sh`, `scripts/try-linux-mpdecimal-madc.sh`, `scripts/repro-linux-mpdecimal-qnew.sh` and `scripts/build-linux-decnumber.sh`. Linux timing results should be rerun on a native x86-64 host before using them for performance budgets.

No MIR or MADC source files have been changed for this experiment.
