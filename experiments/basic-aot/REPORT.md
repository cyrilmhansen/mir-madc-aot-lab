# BASIC to MIR/MADC native AOT: cycles 1 and 2

## Baselines and source provenance

- BASIC frontend/runtime: `cyrilmhansen/mir`, commit
  `54fa3e409224bbc6ffdbc421a80f02ff76f76ce6`, extracted from `basic/` without
  edits. See [UPSTREAM.txt](UPSTREAM.txt).
- MIR AOT backend: this lab's existing `madc/` submodule, commit
  `868847a76434058483bade03ead09ba6acb9d771`, branch
  `experiment/mir-aot-correctness`, based on the lab's existing MADC work.
- Host: Linux `skip`, x86-64 native.
- C compiler: GCC 16.2.1.
- Numeric mode: `double` only.

The historical BASIC compiler builds from the full pinned MIR archive with
`scripts/build-baseline.sh`. Its normal interpreter path and `-j` JIT path
matched the expected outputs for `hello`, `arith`, `loop`, `if_block`, `string`,
and `data_read`. The string sample used the same `MIR\nY\n` stdin for all
execution modes.

`basicc -b` does **not** emit native code for the BASIC program. `basicc.c`
serializes the module into a C byte array (`.ctab`) and compiles
`mir-bin-driver.c`, `mir.c`, `mir-gen.c`, and `basic_runtime.c`. The driver
reads the embedded MIR and calls `MIR_gen`/`MIR_gen_init` when the executable
runs. In this checkout the generated compile command also omits BASIC include
paths and runtime support sources. Supplying those inputs allowed the sample
executable to build, but it exited before running with `can not load symbol
basic_chain`: the generated module imports the frontend's `basic_chain`, which
is not present in the MIR binary driver/runtime. The attempted executable
contains MIR generation symbols. Therefore `-b` is neither the desired native
AOT path nor currently a working hello baseline on this host.

## Prototype and exact commands

The separate adapter [mir-to-elf.c](src/mir-to-elf.c) uses the MADC-integrated
MIR API. It parses the text emitted by upstream `basicc -S`, loads and links
the module, enables `MIR_gen_set_object_mode`, generates functions, then calls
`MIR_gen_object_emit` to produce ELF `ET_REL`. The adapter inserts an `export
main` MIR directive into the in-memory text: upstream BASIC emits a `main`
function but no MIR export, so the raw generated object otherwise made it a
local ELF symbol.

Reproduce the first native executable with:

```sh
experiments/basic-aot/scripts/build-baseline.sh
experiments/basic-aot/scripts/build-aot.sh hello
```

The first command downloads/extracts the pinned MIR source archive under the
ignored `vendor/` directory and builds upstream `basicc`. The second command
uses that compiler for MIR text, the existing MADC static MIR library for the
adapter, and GCC for the BASIC runtime and final link.

The object `results/aot/hello.o` is ELF64 `ET_REL`, machine x86-64. It exports
`main`, imports `basic_enable_line_tracking`, `basic_set_line`, and
`basic_print_str`, and contains `.text`, `.mir.addrpool`, `.rela.text`,
`.rela.mir.addrpool`, and `.rela.eh_frame`. `readelf`, `nm`, and
`objdump -dr` output is retained beside the artifacts. The final executable
prints `HELLO`, has only `libc.so.6` and `libm.so.6` as dynamic dependencies,
and has no MIR/JIT symbols or MIR shared-library dependency. It does not parse
or compile MIR at startup.

`basic_runtime.c` includes MIR APIs for BASIC's documented MIR metaprogramming
functions (`MIRCTX`, `MIRFUNC`, `MIRRUN`, etc.). Those functions are removed
from this small executable by compiling runtime code into function sections
and linking with `--gc-sections`; the tested BASIC samples do not call them.
Programs using runtime MIR metaprogramming are not yet supported by this
MIR-free AOT link. The runtime header also includes MIR headers at compile
time, although those headers do not add a runtime dependency by themselves.

## Differential validation

Run `experiments/basic-aot/scripts/validate.sh`. It compares interpreter, JIT,
and AOT output byte-for-byte against upstream expected output.

| BASIC feature/sample | Interpreter | `-j` JIT | MADC ELF AOT | Notes |
|---|---:|---:|---:|---|
| `hello.bas` | pass | pass | pass | `PRINT` string, `END` |
| `arith.bas` | pass | pass | pass | arithmetic and numeric printing |
| `loop.bas` | pass | pass | pass | `FOR`/`NEXT` loop |
| `if_block.bas` | pass | pass | pass | conditional branches |
| `string.bas` | pass | pass | pass | string input/output, with identical stdin |
| `data_read.bas` | pass | pass | **Cycle 1 fail; Cycle 2 pass** | Cycle 2 emits explicit runtime initialization calls |

The original Cycle 1 `DATA` limitation was traced to upstream frontend state, not ELF relocation:
`basicc.c` accumulates `DATA` items in its process-local `data_vals` and assigns
them to `basic_data_items` immediately before interpreter/JIT execution. Its
MIR text writer emitted no representation for that state, so the separately
linked runtime saw zero-initialized globals. Cycle 2 resolves this by emitting
runtime startup calls; it does not add a static ELF table or serialized data
format.

## Measurements

`scripts/measure.py` performs 30 fresh-process runs per execution mode and five
repetitions per AOT compilation stage. It records wall time to process exit,
line-buffered time to first output, `/usr/bin/time` maximum RSS, artifact sizes,
and AOT stage compilation time in `results/measurements/summary.json`. These
tiny examples are dominated by process startup, so the timings do not represent
steady-state BASIC throughput. No `-b` timing is reported because its hello
executable did not run successfully.

| Program | Mode | Median to exit (ms) | Median first line (ms) | Median max RSS (KiB) | Executable bytes |
|---|---|---:|---:|---:|---:|
| hello | interpreter | 1.082 | 0.963 | 3,610 | 1,722,560 |
| hello | `-j` | 1.240 | 1.099 | 4,018 | 1,722,560 |
| hello | AOT | 0.720 | 0.660 | 2,008 | 17,040 |
| arith | interpreter | 1.102 | 0.977 | 3,618 | 1,722,560 |
| arith | `-j` | 1.487 | 1.331 | 4,200 | 1,722,560 |
| arith | AOT | 0.733 | 0.665 | 2,194 | 18,856 |
| loop | interpreter | 1.125 | 0.972 | 3,634 | 1,722,560 |
| loop | `-j` | 1.403 | 1.235 | 4,278 | 1,722,560 |
| loop | AOT | 0.751 | 0.688 | 2,216 | 17,608 |

Median AOT compile pipeline times (5 runs, sum of stage medians):

| Program | `basicc -S` | MIR to ELF object | GCC runtime compile/link | Total | Object bytes |
|---|---:|---:|---:|---:|---:|
| hello | 1.47 ms | 1.09 ms | 1,799.56 ms | 1,802.12 ms | 2,928 |

## Cycle 3: EXTERN ordering and GOSUB/RETURN

### EXTERN declarations

The BASIC parser originally parsed each source line immediately. If a numeric
external was called before its later `EXTERN` line, the name was not yet in
`func_defs`; `EXT_LATE(3)` became an implicit array access and printed `0`.
Emitting external MIR prototypes earlier in `gen_program()` alone could not
repair that already-built AST. The experimental frontend now pre-scans only
EXTERN declarations before parsing program lines, then parses the source
normally. This also lets calls use their declared argument and return types.
Conflicting declarations fail with `conflicting EXTERN declaration`.

The external prototypes/imports are emitted in the first MIR declaration pass,
before `main` and its calls. The tests cover numeric and string arguments and
returns, two SUBs, multiple imports, and declarations both before and after
calls. Interpreter and JIT runs resolve the test library with `LD_PRELOAD`; AOT
links the same shared library. Undefined imports are not filled with a dummy
address: interpreter/JIT report `import of undefined item EXT_NOT_PRESENT`,
while GCC refuses to link the AOT executable with an undefined strong ELF
symbol.

The adapter has to accommodate MIR's eager-link API for relocatable output:
`MIR_link` accepts a missing import only if temporarily marked weak. The
adapter records each declaration's original binding, links without a resolver,
emits the object, and restores originally strong imports to `STB_GLOBAL` in
the ELF symbol table. They remain `SHN_UNDEF` relocations, so the system linker
still enforces symbol presence. The `extern-missing` case verifies that failure
path. No made-up resolver address is used.

### GOSUB/RETURN diagnosis and repair

The smallest BASIC reproducer is
`tests/features/gosub-minimal.bas` (one `GOSUB`, `END`, one `RETURN`). Before
the frontend change, its return address used
`MIR_new_lref_data(ctx, NULL, label, NULL, 0)`. `MIR_new_ref_op` put that item
in a `MIR_MOV`; during `basicc -S`, `MIR_output_insn` printed the REF name via
`MIR_item_name`, which was NULL. GDB shows `fputs -> MIR_output_insn ->
MIR_output_item -> MIR_output_module -> gen_program`; the standalone reducer
`tests/mir-null-lref-crash.c` reproduces the same null-name crash with both the
pinned upstream MIR and MADC-integrated MIR. Giving the lref data a generated
name makes `MIR_output` finish. This identifies the original crash as BASIC
frontend misuse of the MIR API, not a code generator or ELF relocation fault.
The captured stacks are [upstream GDB](diagnostics/gosub-lref-upstream.gdb.txt)
and [MADC GDB](diagnostics/gosub-lref-madc.gdb.txt); the reader-order checks
are recorded in [gosub-lref-reader-order.txt](diagnostics/gosub-lref-reader-order.txt).

There is a second serialization boundary: both MIR versions append lref
declarations after their referencing function. Feeding this text unchanged to
either version's reader fails with `undeclared name return_addr_0` (line 7).
Moving the named lref declarations before the first function makes both readers
accept it. The `.mir -> .o` adapter now performs that order-only adjustment
before calling `MIR_scan_string`; labels and the generated return-address
semantics are unchanged. The adapter then emits the ELF object as before.
This compatibility issue is distinct from the NULL-name crash and is not
attributed to the MADC machine-code backend.

No integer continuation dispatcher was introduced. The existing address stack
already handles nested calls and multiple returns; replacing it would add a
dispatcher and a second set of control-flow cases without avoiding the needed
MIR reader ordering adjustment.

### Cycle 3 validation

The following commands pass on Skip (Linux x86-64 native):

```sh
experiments/basic-aot/scripts/validate.sh
experiments/basic-aot/scripts/validate-data.sh
experiments/basic-aot/scripts/validate-features.sh
```

The extended differential fixtures compare stdout in the interpreter, JIT,
and native ELF paths for the historical GOSUB program, nested GOSUB/RETURN,
GOSUB in a loop with DATA/READ/RESTORE, and EXTERN before/after use. Prototype
mismatches and missing symbols are asserted to fail explicitly. The full
feature matrix is in `results/data-validation/feature-matrix.tsv`.

Targeted ASan/UBSan builds of the BASIC runtime passed
`tests/data-runtime-test.c` and a nested-GOSUB native executable (with leak
detection enabled). These are focused checks, not a claim that the entire
frontend or all BASIC programs are sanitizer-clean. Valgrind was not rerun;
the previously observed dynamic-loader failure remains outside program
execution. The runtime objects and harness used matching
`-fsanitize=address,undefined -fno-omit-frame-pointer` instrumentation;
runtime objects also used `-ffunction-sections -fdata-sections`, and the test
links used `-Wl,--gc-sections`. The targeted invocations were:

```sh
ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=print_stacktrace=1 \
  results/cycle3-sanitizers/data-runtime-test
ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=print_stacktrace=1 \
  results/cycle3-sanitizers/gosub-native
```

The `tests/mir-null-lref-crash.c` reducers are built once against the pinned
MIR `mir.c.o`/`mir-gen.c.o` and once against
`madc/obj/mir/host/libmir.a`, with `-lm -ldl -lpthread`. Run each with no
arguments under GDB to see the NULL-name stack, or with `named` to see
successful output. Feeding named output to its `read` mode reproduces the
forward-reference parse error; moving the lref declaration before the function
produces `read-ok`.

### Direct integration recommendation

Keep `.mir -> .o` as the supported experimental seam for now. Direct use of
`MIR_gen_init`, `MIR_gen_set_object_mode`, `MIR_link`, `MIR_gen`, and
`MIR_gen_object_emit` inside `basicc` would remove MIR text parsing and the
small adapter, but would couple the historical BASIC source/build to the
specific MADC-integrated MIR headers, ABI, and static library. The text path
currently provides a useful inspectable/debuggable boundary and keeps the
upstream source provenance isolated. A later direct backend can be added as an
optional build target after a deliberate MIR versioning policy exists; it does
not require merging MIR and MADC histories.

### Cycle 3 status

- EXTERN before and after use: PASS in interpreter, JIT, and AOT fixtures.
- GOSUB/RETURN, including nested and loop/DATA cases: PASS in all three paths.
- Incompatible EXTERN signature: explicit frontend error in all three modes.
- Missing EXTERN symbol: explicit runtime/JIT import error or native link error.
- ASan/UBSan: targeted DATA runtime and nested-GOSUB checks PASS.
- General AOT benchmarks were not rerun.
| arith | 1.96 ms | 1.85 ms | 1,756.64 ms | 1,760.46 ms | 8,112 |
| loop | 1.85 ms | 1.57 ms | 1,832.31 ms | 1,835.73 ms | 4,384 |

These historical Cycle 1 figures include recompiling the complete runtime for
each sample. Cycle 2 separates runtime construction and uses a reusable static
archive; see the Cycle 2 measurements below. The GCC
interpreter/JIT executable and AOT executable both depend dynamically on
`libc.so.6` and `libm.so.6` here.

## Current scope and architecture recommendation

The first success criterion is met: `hello.bas` becomes a native x86-64 ELF
executable which prints the expected output without runtime MIR loading or
JIT. Arithmetic, loop and branch samples, and a string-input sample also pass.
The generated machine code is produced by MADC's maintained MIR backend; no
MADC source is copied into the BASIC tree.

Recommend keeping option A, a separate `.mir` to `.o` adapter, for the next
prototype stage. It gives a small, reviewable compatibility boundary and does
not require changing the BASIC parser or code generator. Remaining integration
work is the known GOSUB and external-prototype MIR emission failures, plus an
explicit runtime choice for MIR metaprogramming. Option B, adding object mode directly to `basicc.c`, can
remove the intermediate MIR-text adapter later, but couples the BASIC
frontend to MADC's object API. The current MADC object emitter is x86-64 ELF
specific;
this prototype does not establish cross-generation support.

## Repository state

No MADC sources were changed and the submodule remains at
`868847a76434058483bade03ead09ba6acb9d771`. No push was performed. The report,
scripts, extracted BASIC subtree, and outputs are lab artifacts under
`experiments/basic-aot/`; ignored upstream full-source build trees live under
`vendor/`. Cycle 2 changes are committed locally on
`experiment/mir-aot-correctness-cycle3`.

## Cycle 2 current result

The current experiment adds process-owned `DATA` initialization to emitted
MIR. Generated `main` calls `basic_data_init`, then appends every parsed
numeric/string item in collection order before the first BASIC statement. The
runtime copies strings and owns a dynamically grown table; `RESTORE` resets
the cursor, `END` and implicit return free the table, and a new call to `main`
initializes it again. The compiler's parse-time vector is only the source used
to emit these calls; `READ` consumes the runtime table.

Seven focused DATA fixtures and historical `data_read.bas` now match byte for
byte in interpreter, JIT and native ELF modes. Coverage includes numeric,
string and mixed entries, distributed statements, DATA after END, RESTORE,
exhaustion, two calls in one process, REPL line replacement, and runtime table
cleanup. See `scripts/validate-data.sh` and
`results/data-validation/feature-matrix.tsv`.

The GCC runtime is built as `runtime/libbasicrt.a`. Its cache signature includes
runtime sources, headers, compiler version and flags; subsequent BASIC builds
reuse the archive. AOT samples link with `--gc-sections`, so ordinary
executables drop unused MIR metaprogramming functions. Tested AOT binaries have
no MIR undefined symbols and depend only on libc and libm. Programs that
invoke `MIRCTX`/`MIRFUNC` still require MIR at runtime and fail the strict
native link. The AOT runtime build defines `BASIC_AOT_NO_MIR_RUNTIME` so the
common shutdown helper does not retain an otherwise unused `MIR_finish`
reference.

The experiment patch is applied only to the ignored, locally built pinned MIR
tree. `upstream/basic/` remains the pristine BASIC source snapshot. No upstream
repository or MADC source was changed.

## Cycle 2 validation and measurements

Validation commands:

```sh
experiments/basic-aot/scripts/validate.sh
experiments/basic-aot/scripts/validate-data.sh
experiments/basic-aot/scripts/validate-features.sh
python3 experiments/basic-aot/scripts/measure.py
```

All three validation scripts pass. The feature matrix marks `funcproc`, `fact`,
`def_fn`, one- and two-dimensional arrays, and numeric file I/O as passing in
all three modes. GOSUB works in interpreter/JIT, but the pinned historical
`basicc -S` segfaults inside `MIR_output_insn` for `gosub.bas`; this was
reproduced after rebuilding from pristine source, before the experiment patch
was reapplied. This is a frontend/MIR text-emission defect, before the AOT
adapter. External imports work in interpreter/JIT; emitted MIR places an
external prototype after its first call, so the MADC MIR parser rejects it
(`undeclared name EXT_ADD_p`). `CHAIN` is interpreter-only, EVAL requires live
frontend state and is explicitly rejected in emitted modes, and MIR
metaprogramming remains unsupported by the MIR-free ELF link. The official
`RESUME --no-line-tracking` diagnostic passes; full error-handler resume
behavior is not covered. File I/O validation uses numeric values; string
`INPUT#` is not claimed.

Measurements use Linux x86-64 on Skip (native host, not QEMU), GCC 16.2.1,
double numeric mode, 30 fresh processes per execution mode and 30 repetitions
per compile phase. AOT compilation is separated into frontend MIR, MADC object
emission, and native linking against the already built archive. The one-time
full runtime/archive build took 1.85 s; a cached build check took 225 ms,
including CMake/compiler freshness checks. Tiny-program execution is dominated
by process startup.

| Program | Interpreter exit / first output (ms) | JIT exit / first output (ms) | AOT exit / first output (ms) | Median RSS I/J/AOT (KiB) | AOT executable bytes |
|---|---:|---:|---:|---:|
| hello | 1.045 / 0.953 | 1.229 / 1.105 | 0.671 / 0.649 | 3,610 / 4,172 / 2,018 | 17,384 |
| arith | 1.158 / 1.034 | 1.437 / 1.328 | 0.686 / 0.634 | 3,540 / 4,182 / 2,204 | 19,192 |
| loop | 1.068 / 0.942 | 1.326 / 1.222 | 0.661 / 0.630 | 3,598 / 4,270 / 2,212 | 17,944 |
| data-restore | 1.089 / 1.016 | 1.376 / 1.221 | 0.726 / 0.703 | 3,596 / 4,310 / 2,282 | 19,192 |
| funcproc | 1.087 / 0.988 | 1.373 / 1.272 | 0.666 / 0.640 | 3,598 / 4,146 / 2,244 | 18,184 |
| array-2d | 1.191 / 1.116 | 2.234 / 2.049 | 0.737 / 0.713 | 3,736 / 4,674 / 2,220 | 30,112 |

Median AOT phase times (30 repetitions, milliseconds):

| Program | BASIC to MIR | MIR to ELF object | Native link with cached runtime | Sum of phase medians |
|---|---:|---:|---:|---:|
| hello | 1.678 | 1.288 | 14.482 | 17.448 |
| arith | 1.628 | 1.670 | 14.980 | 18.278 |
| loop | 1.613 | 1.537 | 15.540 | 18.690 |
| data-restore | 1.558 | 1.564 | 15.302 | 18.424 |
| funcproc | 1.598 | 1.552 | 15.563 | 18.712 |
| array-2d | 1.781 | 2.962 | 15.046 | 19.790 |

Raw phase output, RSS, first-output timing, artifact sizes and `ldd` results
are in `results/measurements-cycle2/summary.json`. The archive is 270,480 bytes (about 264 KiB) on
this host. A Valgrind check of the two-run native DATA harness terminated in
the dynamic loader (`SIGILL` in `_dl_start`) before BASIC code began; it gives
no memory-safety result.

The separate MIR-text adapter remains the recommended integration boundary.
Direct generation via `MIR_gen_object_emit` would couple the historical BASIC
frontend to MADC's object API. The text path remains useful for inspection and
comparison; no direct integration was attempted in this cycle.
