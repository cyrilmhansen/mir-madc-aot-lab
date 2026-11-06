# libmpdec Cycle 5 — supported `uint128` configuration and asm rejection

## Outcome

MADC now builds a working libmpdec 4.0.1 library using the officially
supported `MACHINE=uint128` C implementation. The normal `MACHINE=x64` path
still depends on GNU extended asm and is intentionally rejected by MADC with a
compilation diagnostic. The compiler change is a parser-side safety fix; it
does not implement GNU extended asm.

MADC reference: `f541a7a54624869e29b01f2f30b174bc0329eea5`.
MADC fix: `868847a76434058483bade03ead09ba6acb9d771` on
`experiment/mir-aot-correctness`.

The lab remains on `experiment/mir-aot-correctness-cycle3`. The submodule
gitlink is updated to the corrected commit in the lab commit. No remote push
was performed.

## Host and source provenance

The machine is native x86-64 hardware: AMD Ryzen AI 9 HX 370, 24 logical CPUs;
`uname -m` is `x86_64`, and `systemd-detect-virt --vm` returned `none`. This is
separate from the historical QEMU TCG data under `results/linux-x86_64/`.
Tool versions were GCC 16.2.1, Clang 23.1.4, and GNU binutils 2.47. See
[`environment.json`](../results/linux-x86_64-native/environment.json).

Both configurations used the verified upstream 4.0.1 archive
(`96d33abb4bb0070c7be0fed4246cd38416188325f820468214471938545b1ac8`) extracted
to separate clean trees. `config.status --config` recorded:

```text
--disable-cxx CC=gcc CXX=g++ MACHINE=x64
--disable-cxx CC=gcc CXX=g++ MACHINE=uint128
```

The generated library flags were:

| Configuration | Generated library C flags | `config.h` |
|---|---|---|
| GCC x64 | `-DCONFIG_64 -DASM -DNDEBUG -O2 -m64` | `HAVE_GCC_ASM_FOR_X64=1`, `HAVE_UINT128_T=1` |
| GCC uint128 | `-DCONFIG_64 -DANSI -DHAVE_UINT128_T -DNDEBUG -O2 -m64` | `HAVE_UINT128_T=1` |
| MADC uint128 | same defines as GCC uint128, plus `-fPIC` | same generated `config.h` and public header |

`ANSI` and `CONFIG_64` are build flags from the generated Makefile, not
definitions in `config.h`. MADC compiled all 15 C units from the uint128 source
tree into a separate output directory; none of the `ASM` objects were reused.
The resulting static archive and shared library were created from only those
MADC objects.

## Library and test results

The GCC x64 and GCC uint128 builds both pass `make check_local` (15 local
vectors against static and shared libraries: 30 PASS rows) and `make check`
(296 official PASS rows across static and shared libraries). The first campaign
is captured in `gcc-x64-*` and `gcc-uint128-*` logs; uint128 flags and generated
macros are visible in the respective configure logs and Makefiles.

All 15 MADC uint128 translation units compiled successfully. The MADC static
and shared libraries linked. The strengthened `mpd_qnew()` probe passes with
GCC and MADC libraries: non-NULL structure, zero-initialized public fields,
`alloc=2`, correct recorded request sizes for the structure and coefficient
buffer, writes/readbacks within every allocated word, and exactly two frees
through `mpd_del()`. libmpdec deliberately leaves coefficient words
uninitialized, so the probe writes them before reading them.

All four library/test-compiler combinations pass both test modes:

| Library | Test runner | `check_local` | Official `check` |
|---|---|---:|---:|
| GCC uint128 | GCC | 30/30 | 296/296 |
| MADC uint128 | GCC | 30/30 | 296/296 |
| GCC uint128 | MADC | 30/30 | 296/296 |
| MADC uint128 | MADC | 30/30 | 296/296 |

Each failure count is zero. After the MADC parser fix was committed, all 15
library units and both MADC test sources were rebuilt with the corrected
compiler; the three cells containing an MADC-built library and/or runner were
rerun and again passed with the same counts. Those final logs are in
`results/linux-x86_64-native/libmpdec-cycle5/matrix-corrected/`; the first
`matrix/` directory preserves the initial baseline-run records. GCC/GCC is
unchanged and its clean uint128 reference is in the `gcc-uint128-*` logs. The
MADC test runner objects were built from the same `runtest.c` and `test.c` and
linked with the MADC runtime as required by their generated helper references.

The optional `ansi64` fallback was not needed: uint128 passed the full matrix.
The six existing `test_cir_freeze` C++ failures from the earlier MADC full-suite
baseline are independent; this cycle did not rerun the broad MADC suite.

## GNU asm safety correction

The bug is still exactly the Cycle 4 finding: MADC parsed and accepted
`mulq` while omitting its machine operation, so its output locals were
undefined before CIR/c2mir. This was not an ABI, inlining, relocation, or
libmpdec algorithm defect.

At the parser boundary MADC now rejects:

- Any non-empty GNU asm template, including `asm`, `__asm__`, and
  `asm volatile` templates.
- Any clobber list, including `asm volatile("" ::: "memory")`.
- `asm goto` and statements with goto labels.
- Output operands without an explicit matching input, including `+` read/write
  outputs and output-only constraints. An empty template with an explicit
  matching numeric or named input remains representable as a C assignment.

Empty-template input-only forms, including `asm volatile` operand evaluation,
and explicitly tied outputs remain supported. GNU asm declaration labels such
as `extern int f asm("symbol")` are a separate declarator feature and still
pass their existing tests. The diagnostics are emitted before CIR construction.

The independent `mulq` program compiles and runs with GCC and Clang, printing
`high=0`. MADC refuses it with
`non-empty GNU asm templates are not supported` at `-O0`, `-O1`, and `-O2`;
the compile-negative fixture also requires a nonzero compiler exit. The
memory-clobber, output-only, and goto negative fixtures check their specific
diagnostics. Empty operand evaluation, tied output, nested asm, and asm-label
fixtures pass. See [`scripts/test-linux-madc-inline-asm-min.sh`](../scripts/test-linux-madc-inline-asm-min.sh)
and the per-test files under `madc/tests/`.

## Native loading measurements

The benchmark performs `123456789 * 987654321`, checks the exact decimal result
`121932631112635269`, and runs one warm-up followed by 30 new processes per
path. Dlopen and operation clocks are measured separately inside the process.
For the MADC `.so`, `libmadc.so` is loaded globally before the timer because
the library imports MADC runtime helpers; the reported load interval is for
libmpdec itself, not the runtime dependency closure.
The operation interval includes parsing both operands, multiplication, and
formatting; it is not a general libmpdec throughput benchmark.

| Path | Median `dlopen` | Median decimal operation |
|---|---:|---:|
| GCC uint128 `.so` + `dlopen` | 75.0 µs | 2.51 µs |
| MADC uint128 `.so` + `dlopen` | 100.3 µs | 5.56 µs |

All 60 measured operations returned the expected result. Raw rows and warm-up
logs are `dlopen-gcc-uint128.csv` and `dlopen-madc-uint128.csv` under the cycle5
results directory. Compile and emission timing on this host:

| Work | Wall time |
|---|---:|
| GCC uint128: 15 PIC object compilations | 2.28 s |
| GCC uint128: archive and shared-library link/emission | 0.02 s |
| MADC uint128, corrected compiler: 15 object compilations/emission | 1.143 s |
| MADC uint128: archive and shared-library link/emission | 0.030 s |
| MADC decimal probe compile to `.o` | 0.05 s |
| `ld -r --discard-all` combining the MADC objects | <0.01 s |

The combined MADC ELF `.o` loads through MADC's `MIR_object_load` path and
executes the same checked multiplication. A normal `ld -r` aggregate was
rejected by this loader on an `STT_FILE` symbol; `ld -r --discard-all` produced
an accepted aggregate while retaining the needed external symbols. Thirty
fresh `madc` processes after one warm-up all passed. Their median end-to-end
process wall time was 7.08 ms (mean 7.30 ms); this includes MADC process startup
and object loading, so it is not a loader-only timing. Results are in
`objectload-madc-uint128.csv`.

The MADC CLI exposes a text MIR dump for diagnostics and an internal frozen
MIR cache for compiler support, but this C-library workflow does not expose a
standalone serialized user-library MIR artifact that can be loaded and eagerly
JITed. No `.bmir` JIT timing is claimed.

## Validation limits and Git

The parser correction does not touch the MIR backend or target-specific code
generation. No ARM64 rebuild was needed; this cycle makes no new ARM64 claim.
The full MADC conformance suite and the six known C++ freeze failures were not
rerun. No libmpdec sources or algorithms were changed.

The MADC fix is committed as `868847a76434058483bade03ead09ba6acb9d771`.
The lab records the original MADC baseline and updates its submodule gitlink to
that fix in its own local commit. No push was made. The root working tree also
contained pre-existing user-edited cycle3 log files; they remain uncommitted
and are not included in the cycle5 lab commit.
