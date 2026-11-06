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

## Cycle 4: shared ELF library and C ABI

### Exported interface and object generation

`basicc.c` stores BASIC functions in `FuncDef` records. `parse_func()` accepts
`FUNCTION` and `SUB` definitions, derives parameter kinds from `$` suffixes,
and the generator creates MIR functions under the BASIC name itself (for
example, `SQUARE`, not `SQUARE_p`; `_p` is the MIR call prototype). Under
`BASIC_NUM_MODE=double`, numerical arguments/results use `MIR_T_D`, string
arguments/results use `MIR_T_P`, and SUBs have no result. `DEF FN` is an
expression shorthand rather than an exported function definition.

The adapter now accepts explicit repeated `--export NAME` arguments. It
rejects names that are absent or not defined functions and checks the
requested C ABI signature from the parsed MIR item. Only those functions are
marked exported; helpers and `main` remain local. The old two-path adapter
invocation still exports `main` for executable builds. Example:

```sh
experiments/basic-aot/scripts/build-shared.sh \
  experiments/basic-aot/tests/shared/libbasicdemo.bas \
  experiments/basic-aot/results/shared/libbasicdemo.so \
  --export SQUARE --export ADD --export STRLEN --export REPORT
```

The exported API is:

| ELF symbol | C declaration | BASIC behavior |
|---|---|---|
| `SQUARE` | `double SQUARE(double)` | Pure numeric square |
| `ADD` | `double ADD(double, double)` | Pure numeric addition |
| `STRLEN` | `double STRLEN(const char *)` | `LEN` of an input string; does not take ownership or modify it |
| `REPORT` | `void REPORT(double)` | Prints a number through the BASIC runtime |
| `basic_module_init` | `void basic_module_init(void)` | Starts the shared BASIC runtime pool |
| `basic_module_fini` | `void basic_module_fini(void)` | Frees runtime DATA/state and the pool |

String-returning BASIC functions are not part of the stable C API. The frontend
returns a pointer, but the ownership/freeing contract for such a result across
the shared-library boundary is not defined here; `basic_free` is an internal
runtime symbol and the result could also depend on the module pool. A returned
string must not be retained past `basic_module_fini()` or `dlclose()`.

### GCC-linked `libbasicdemo.so`

The runtime archive was already compiled with `-fPIC`; the shared build uses a
separate cache/archive so the ordinary AOT executable archive and its options
remain unchanged. `build-runtime.sh` hashes the compiler version, complete
compile flags, runtime sources, and relevant headers. A cache check confirmed:
same flags reused the archive, while changing a test define rebuilt it. The
shared link uses `-shared -Wl,--no-undefined -Wl,-z,defs -Wl,-z,text
-Wl,--gc-sections -Wl,--exclude-libs,ALL`; archive helpers stay private and
unused MIR metaprogramming sections are discarded.

`results/shared/libbasicdemo.so` is ELF64 `ET_DYN`, x86-64. Its public dynamic
symbols are the four selected BASIC functions and the two explicit runtime
lifecycle functions. It has no `TEXTREL`, no MIR/JIT symbols, no public
runtime helpers, and `ldd -r` reports no unresolved symbols. Its dynamic
dependencies are `libc.so.6` and `libm.so.6`. GCC's strict undefined-symbol
checks are enabled; the linker is not asked to relax PIC or unresolved-symbol
rules.

### Initialization, lifetime, and sanitizer finding

The first sanitizer experiment found one 1 MiB pool allocation per `dlopen`
and a 4 MiB LeakSanitizer report after four load/unload cycles. The cause was
the historical runtime's ELF constructor, which called `basic_pool_init()`
automatically, while its matching cleanup was only reachable from BASIC's
`basic_stop()` path. A host loading a library and calling exported functions
never enters that `main` path.

The shared-only runtime build defines `BASIC_AOT_EXPLICIT_INIT` to omit that
constructor and links the small lifecycle wrapper above. It does not add an
ELF constructor. The C client explicitly initializes and finalizes the
runtime around its use. With this lifecycle, the ASan/UBSan-instrumented
runtime archive, shared library, and client pass value checks and repeated
`dlopen`/`dlclose` with `ASAN_OPTIONS=detect_leaks=1`. `basic_module_init()` is
idempotent within one mapped module; `basic_module_fini()` releases the state.
Thread safety and simultaneous calls from multiple threads have not been
tested or promised.

### Differential and C-client validation

Run `experiments/basic-aot/scripts/validate-shared.sh`. It first compares
interpreter and historical JIT output against
`tests/shared/expected.out` (`6.25`, `9`, `3.25`, `0`, `5`, `42.5`), then:

- Uses `dlopen`/`dlsym` with zero, positive, negative, and fractional numbers.
- Checks multiple functions in one DSO, the string-input ABI, and a SUB called
  through `void (*)(double)`.
- Confirms `dlsym` reports a missing name, reloads the DSO three times, and
  invokes the exports on every load.
- Links a second client directly with `-lbasicdemo` and compares its results.
- Checks export selection, rejects a missing function and a non-C `main`
  signature, and verifies internal helpers are not exported.
- Runs the existing `validate.sh` AOT executable regression suite.

The native client calls both the BASIC function pointer and a `noinline` C
implementation of the same square operation. This checks the native ABI and
call overhead with the same arithmetic, but the result is a small host
microbenchmark, not a general backend performance claim.

### Direct MIR shared emitter

The maintained MIR `MIR_gen_object_emit_executable()` path with `shared_p=1`
also emits a loadable ELF `ET_DYN` containing callable `SQUARE` and `ADD`
exports; the C probe returns the expected values, and the image has no
`TEXTREL`. It is not yet equivalent to the GCC-linked library: loading the
entire BASIC MIR module leaves weak undefined `basic_*` entries in its dynamic
symbol table, and runtime-using exports such as `STRLEN` require `basic_len`
from the separately compiled runtime. The direct-emitter validation therefore
calls only pure arithmetic exports. No MADC change was made; this is a
composition limitation of emitting the complete MIR module without embedding
or linking the BASIC runtime. The GCC-linked library remains the complete
validated path.

### Skip measurements

`scripts/measure-shared.py` ran 30 fresh processes for each build stage and 30
fresh client processes, each making one million BASIC and C calls. The runtime
archive was already built; initial runtime compilation is excluded. Full
min/median/max data and artifact sizes are in
[`results/shared/measurements.json`](results/shared/measurements.json).

| Stage | Median | Min–max |
|---|---:|---:|
| BASIC → MIR | 1.24 ms | 1.14–2.30 ms |
| MIR → ELF `.o` | 1.77 ms | 1.34–2.10 ms |
| GCC `.so` link | 15.59 ms | 12.82–19.35 ms |
| MIR direct shared emission | 1.57 ms | 1.28–2.23 ms |
| `dlopen` | 31.8 µs | 25.5–67.6 µs |
| `dlsym` per lookup (10,000 lookups/process) | 33.3 ns | 21.0–41.1 ns |
| BASIC `SQUARE` call through function pointer | 3.61 ns | 2.35–3.76 ns |
| Equivalent noinline C call | 2.69 ns | 2.34–3.63 ns |
| `dlclose` after explicit runtime fini | 22.0 µs | 11.9–29.8 µs |

The ELF `.o`, GCC-linked `.so`, and direct MIR `.so` measured 9,240, 19,224,
and 11,008 bytes respectively in this run. These timing ranges are machine-
and load-dependent; the square loop is intentionally tiny and mainly exposes
the call path.

### Cycle 4 validation and remaining scope

- `validate-shared.sh`: PASS, including `dlopen`, direct linking, strict ELF
  checks, direct MIR pure-function image, and the existing AOT regression.
- `validate-data.sh` and `validate-features.sh`: PASS after the adapter CLI
  extension.
- ASan/UBSan: PASS for the shared runtime, C client, explicit lifecycle, and
  four DSO load/unload cycles with leak detection.
- The main shared artifact is `results/shared/libbasicdemo.so`; it is a local
  build output and is regenerated by `validate-shared.sh`.
- MADC remains unchanged. No general AOT benchmark campaign was run.
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

## Cycle 6: direct shared-object emission investigation

### Pinned MIR emitter constraints (pre-implementation)

The MADC-pinned API is in `madc/third_party/mir/mir-gen.h` and
`mir-debug.h`. Object mode captures machine code and relocations through
`MIR_gen_set_object_mode`, `MIR_gen`, and `MIR_gen_get_object`; the complete
shared image is written with `MIR_gen_object_emit_executable(ctx, &params,
&buf, &size)` and `params.shared_p = 1`. This path emits ELF64 `ET_DYN` on
the current x86-64 Linux target; it is not a request for GCC/ld to link the
image.

For shared images the emitter exports defined nonlocal MIR symbols, places
ABS64 address slots in `.rela.dyn`, uses `R_X86_64_RELATIVE` for internal
addresses and `R_X86_64_64` for imports, and emits `DT_NEEDED` and optional
`DT_RUNPATH` from the caller's parameter struct. There is no PLT/lazy binding;
the image carries BIND_NOW. Its documented layout includes Full RELRO,
`PT_GNU_STACK` without execute permission, and `DT_INIT_ARRAY` when the
builder has initializers. The dynamic loader runs those entries at DSO load;
the BASIC experiment will continue to use explicit lifecycle functions and
will not add an initializer.

The emitter records strong undefined MIR imports as strong dynamic symbols;
the loader must resolve them when the consumer uses `RTLD_NOW`. Undefined
weak references are distinct and can become address zero, so runtime imports
must not be weakened as a workaround. The existing `.mir -> .o` adapter
temporarily weakens imports only to satisfy `MIR_link`, then restores the MIR
item bindings before machine-code capture; the direct-image path needs the
same restored bindings so the emitter writes the original strength.

`MIR_object_read()` is the merge reader for relocatable artifacts emitted by
this MIR builder. It rebases the supported sections/symbols/relocations and
is not a general-purpose reader for arbitrary GCC ELF objects. Therefore
runtime objects and C ABI wrappers, if merged into an image, must first be
emitted as MIR-compatible ET_REL objects (the proposed wrapper proof uses
MADC itself). This constraint rules out feeding GCC's existing wrapper
object into the merge reader.

## Cycle 5: string-returning C ABI

### Runtime ownership findings

MIR string literals are module-address-pool data and remain valid only while
the DSO is loaded. C parameters are borrowed for the duration of the call.
BASIC function parameters and locals are pointer values; a `LET` from a string
variable or literal calls `basic_strdup`, while concatenation and string
builtins such as `basic_upper` allocate through `basic_alloc_string` in the
BASIC pool. `basic_free` is specifically `basic_pool_free`; it must not be
used on a literal, arbitrary C pointer, or a returned string whose origin is
unknown. The compiler does not attach ownership metadata to MIR_T_P results:
a `DEF FN` can return its input pointer directly, while a `FUNCTION` may
return a pool allocation. There is no universal ownership transfer rule.

| Internal value category | Example | Lifetime / wrapper treatment |
|---|---|---|
| MIR literal | `"text"` in emitted MIR | DSO lifetime; never pass to `basic_free` |
| Borrowed C argument | `const char *` passed to `BASIC_*` | Caller-owned; copy before returning |
| BASIC parameter | `TEXT$` in a function | Aliases its input unless assignment creates a copy |
| BASIC string variable | `LET S$ = TEXT$` | `basic_strdup` creates a pool copy; the variable slot itself is not ownership |
| Pool allocation | `UPPER$`, concatenation | Pool allocation; free only when the target's return contract proves it |
| BASIC function result | `DEF FNBORROWED$` vs `FUNCTION ECHO$` | Can be borrowed or pool-owned; MIR pointer type alone does not decide |
| Public C result | `BASIC_UPPER` return | New `malloc` copy; caller frees with `free` |

The new wrapper generator therefore requires an explicit per-export result
annotation. Its CLI syntax is `--string-export PUBLIC=INTERNAL:ARGS:pool` or
`...:borrowed`; arguments are `p` (`const char *`) or `d` (`double`). A
`:pool` wrapper is used only when the BASIC source proves the result is an
exact runtime-pool allocation. It copies to `malloc` storage and then calls
`basic_free` on that proven pool result, including the allocation-failure
path. A `:borrowed` wrapper copies and leaves the internal pointer untouched.
It is used for the `DEF FNBORROWED$` fixture, which returns its argument.
Neither wrapper exposes an internal pointer to C. Invalid non-NULL pointers
cannot be probed safely in C; the internal function must return a valid
NUL-terminated BASIC string.

The fixture checks six pool-owned result shapes: literal, copied argument,
local variable, concatenation, `UPPER$`, and empty string. A seventh
`DEF FN` returns its input by reference and uses the borrowed annotation. The
generated public API includes `BASIC_UPPER(const char *) -> char *` and a
header at `include/basic-shared-api.h`. The C result is an independent
`malloc` allocation, remains valid after `basic_module_fini()` and `dlclose()`,
and must then be freed with `free()`. `basic_string_free()` delegates to
`free()` but can only be called while the DSO is loaded. A NULL input returns
NULL; an empty BASIC string returns an allocated one-byte empty C string;
wrapper allocation failure returns NULL. BASIC strings remain NUL-terminated
byte strings: embedded NUL data is not representable and uppercase behavior
follows the runtime's byte/locale implementation, without a Unicode promise.

### Pool lifetime and repeated calls

Pool-owned exported results are returned to the BASIC free list after copying,
but intermediate allocations inside a BASIC function can remain in the pool.
Borrowed results are never freed. The pool is destroyed by explicit
`basic_module_fini()`, not reset after each call, so persistent module state is
not invalidated. This makes lifetime explicit and LeakSanitizer-clean, but it
does not promise bounded memory for arbitrary string functions or indefinitely
long module sessions. A future general solution should add ownership tracking
or a scoped temporary allocator and define which allocations may escape into
persistent BASIC state; resetting the whole pool per wrapper call is unsafe.

The stress client executes 10,000 `BASIC_UPPER` calls, frees each C result,
and then finalizes the module. RSS changed from 2,356 to 2,420 KiB in the
normal build. The ASan/UBSan process changed from 17,072 to 19,836 KiB; that
measurement includes sanitizer runtime overhead. Leak detection passes after
fini and after three additional load/init/call/fini/unload cycles. The test
also checks simultaneously live results, mutation, reverse-order frees,
NULL arguments, a wrapper-allocation failure hook, direct C linking, and a C
result that survives DSO unload.

### Validation, ELF and timing

Commands run after the wrapper changes:

```sh
experiments/basic-aot/scripts/validate.sh
experiments/basic-aot/scripts/validate-data.sh
experiments/basic-aot/scripts/validate-features.sh
experiments/basic-aot/scripts/validate-shared.sh
experiments/basic-aot/scripts/validate-shared-strings.sh
```

All pass. Interpreter, JIT and native fixture output match for literal,
argument, local, concat, uppercase, empty and borrowed-return cases. The
library is ELF64 `ET_DYN`, has no `TEXTREL`, depends on libc/libm, and `ldd -r`
reports no unresolved symbol or MIR/JIT dependency. A linker version script
exports only selected C wrappers, `basic_module_init/fini`, and
`basic_string_free`; internal BASIC names containing `$` remain hidden.
`libbasicdemo-strings.so` is 28,640 bytes. The numerical `libbasicdemo.so`
remains 19,224 bytes. After rebuilding the normal (non-sanitized) runtime, the
numeric shared benchmark was rerun: `SQUARE` measured 3.14 ns/call versus
2.43 ns for the equivalent C call, with the same numeric ABI checks passing.
The updated 30-process sample is
[`results/shared/numeric-measurements-cycle5.json`](results/shared/numeric-measurements-cycle5.json);
the original Cycle 4 measurements file was preserved.

`scripts/measure-shared-strings.py` ran 30 fresh processes with 100,000 calls
per process. Medians were 25.94 ns for the BASIC `UPPER$` wrapper including
copy/allocation, 3.01 ns for a same-sized C malloc/copy/free, and 9.68 ns for
a noinline-style C ASCII-uppercase/malloc/free loop. This is a microbenchmark,
not a like-for-like algorithm comparison (the BASIC runtime uses its
locale-aware conversion path). Raw samples are in
[`results/shared/string-measurements.json`](results/shared/string-measurements.json).

`BASIC_UPPER_INTO(input, output, capacity)` was not implemented. A useful
contract would return required bytes including the NUL, write nothing for
capacity zero, and if capacity is nonzero always terminate the output (empty
string on insufficient capacity). It avoids result allocation but gives the
caller buffer sizing and retry work; the current malloc-return API is simpler
for C callers and supports results surviving module unload.

## Cycle 6: direct MIR shared-library emission

### Emitter constraints and architecture

The pinned MADC backend is `868847a76434058483bade03ead09ba6acb9d771` and
the host is native Linux x86-64. `MIR_gen_object_emit_executable()` can emit a
shared object from a generator context. For combining independently emitted
objects, the useful route is `MIR_object_create()` → repeated
`MIR_object_read()` of MIR/MADC ELF `ET_REL` files →
`MIR_object_emit_executable()` with a zero-initialized
`MIR_object_exec_params`, `shared_p = 1`, explicit `needed` entries and
`runpath = "$ORIGIN"`. The resulting ELF is `ET_DYN`, has dynamic RELA
relocations and a BIND_NOW policy, and carries the requested `DT_NEEDED` and
`DT_RUNPATH`. Its program headers mark the stack non-executable and include
GNU RELRO. Internal address-pool references use relative relocations; imports
use symbol relocations. This emitter does not invoke a system linker.

`MIR_object_read()` accepts MIR-emitted relocatable objects; it is not a reader
for arbitrary GCC objects. Accordingly, wrapper C was compiled to `ET_REL`
with MADC and `-fno-eval-shims`, while the reusable BASIC runtime was built as
a PIC shared library with GCC. The BASIC DSO is assembled only from MIR/MADC
objects. GCC is still used for the separate runtime DSO and the reference
library. The runtime DSO has SONAME `libbasicrt.so`; a generated version
script exports exactly the `basic_*` runtime functions referenced by the
program/wrappers plus `basic_module_init/fini`. It depends on libc and libm.

The MIR emitter places every global definition from merged inputs in the
dynamic symbol table. To retain the Cycle 5 public ABI, the adapter
`src/mir-objects-to-shared.c` applies ELF `STV_HIDDEN` to internal BASIC
function names after emission, and verifies required undefined imports are
strong global symbols. These names remain present as hidden `.dynsym` entries
(and can appear in `nm -D`); `dlsym` cannot resolve them. `main` is already a
local symbol. The selected public functions and wrappers remain default
visibility. No linker-generated version script is applied to the direct MIR
image.

### Direct DSO and runtime behavior

`scripts/build-shared-direct.sh` reproduces the complete Cycle 5 surface from
`tests/shared/libbasicdemo-direct.bas`. It emits the BASIC `.mir`, converts it
to `ET_REL`, compiles the generated C ownership wrappers with MADC, builds the
PIC `libbasicrt.so`, merges the two MIR/MADC objects, then writes
`libbasicdemo-mir.so` through `MIR_object_emit_executable()`. No GCC/ld command
links that BASIC DSO. The existing GCC-linked DSO is also rebuilt as the
reference path.

The direct image exports `SQUARE`, `ADD`, `STRLEN`, `REPORT`, the selected
`BASIC_*` string wrappers, and `basic_string_free`; the internal BASIC names
are hidden. `basic_module_init/fini` are supplied by the `DT_NEEDED` runtime.
The generated DSO contains no MIR/JIT dependency, has no `TEXTREL`, has
`DT_NEEDED` entries for `libbasicrt.so`, libc and libm, and uses only the
relative `$ORIGIN` RUNPATH. Its dynamic imports are strong. The emitted
`.init_array` has zero size and there is no `DT_INIT`, `DT_FINI`,
`DT_INIT_ARRAY` or `DT_FINI_ARRAY` dynamic tag; lifecycle remains explicit.
The BASIC DSO has no ELF SONAME field, while the runtime dependency does.

The required minimal case is also built independently by the adapter's
`MIR_gen_object_emit_executable()` route from
`tests/shared/direct-numeric.bas`, exporting only `SQUARE` and `ADD`. The
result is a 9,840-byte ET_DYN with no BASIC runtime dependency; it passes both
direct linking and `dlopen(RTLD_NOW | RTLD_LOCAL)` C clients. Its disassembly
shows the two exports are only `mulsd`/`addsd` plus `ret`, with no runtime
calls. The generated, non-exported local `main` does retain weak undefined
startup helpers in `.dynsym`; this does not make either selected function
dependent on them. Runtime-using exports use the separate merge path above,
where required imports remain strong and missing runtime definitions fail at
load time.

Validation includes direct C linkage and a separate `dlopen(RTLD_NOW |
RTLD_LOCAL)` client. It calls all the selected numeric and string APIs,
including `REPORT`, checks `SQUARE`/`ADD` values, checks that an internal
`UPPERTEST$` lookup fails, and compares output with the GCC-linked DSO. A
malloc-owned `BASIC_UPPER` result remains valid after `basic_module_fini()`
and `dlclose()`, then is freed with `free()`. To verify required imports, a
test directory substitutes a DSO with the same `libbasicrt.so` SONAME but no
BASIC exports; `dlopen(RTLD_NOW)` fails deterministically with an undefined
`basic_*` symbol rather than reaching a later call. No weak-binding workaround
is used. Runtime-dependent string wrappers, `STRLEN`, `REPORT`, explicit
initialization/finalization, and the Cycle 5 pool/borrowed ownership policies
all passed. This fixture does not exercise DATA-dependent exported functions;
the generated `main` initializes its own DATA table, and the current explicit
module initializer does not execute `main`.

Reproduce and validate with:

```sh
experiments/basic-aot/scripts/build-shared-direct.sh
experiments/basic-aot/scripts/validate-shared-direct.sh
```

The validation suite checks ELF64/x86-64/ET_DYN, selected default-visibility
exports, hidden internals, strong runtime imports, `DT_NEEDED`, `$ORIGIN`, no
TEXTREL, GNU RELRO, non-executable stack, no init/fini tags, direct linking,
`RTLD_NOW|RTLD_LOCAL`, and failure with the intentionally incomplete runtime.
All five existing suites also passed after the changes:
`validate.sh`, `validate-data.sh`, `validate-features.sh`,
`validate-shared.sh`, and `validate-shared-strings.sh`.

### Self-contained attempt and limits

The four required runtime translation units (`basic_runtime.c`,
`basic_pool.c`, `kitty.c`, and `lodepng.c`) plus the lifecycle source compile
with MADC using `-fno-eval-shims`, `-fPIC`, `-O2`,
`BASIC_AOT_NO_MIR_RUNTIME`, and `BASIC_AOT_EXPLICIT_INIT`. MADC rejects
`-ffunction-sections`; without section-level function elimination, the
compiled runtime objects retain their optional BASIC eval/metaprogramming
functions. Merging all seven objects can emit a large ET_DYN, but
`ldd -r` reports required undefined MIR API symbols including `_MIR_init`,
`MIR_link`, and `MIR_load_module`. Therefore this image is not loadable as a
self-contained BASIC runtime and is retained only as a diagnostic artifact.
Adding MIR itself as a runtime dependency would violate the no-MIR runtime
goal. The working shared-runtime architecture remains usable. The next
self-contained attempt needs either function-level elimination in MADC object
emission or a deliberately reduced runtime translation unit; no compiler or
upstream MIR change was made in this cycle.

MADC also rejects `-fsanitize=address,undefined`, so the direct MADC-generated
wrapper code could not be instrumented. The existing GCC-linked
`validate-shared-strings.sh` ASan/UBSan/LeakSanitizer checks passed; this is not
a sanitizer claim for the direct MIR DSO. The direct ownership and unload
checks are functional tests only.

### Native measurements

`scripts/measure-shared-direct.py` ran 30 fresh processes per stage and 30
fresh processes per runtime client (1,000,000 numeric calls and 100,000 string
calls each). It reuses the already-built runtime; its one-time construction is
not included in warm-stage times. Results and raw per-process samples are in
`results/shared/cycle6-measure/summary.json`.

| Stage / value | Median |
|---|---:|
| BASIC → MIR | 1.67 ms |
| MIR → MADC ET_REL | 1.99 ms |
| MIR object capture + direct ET_DYN emission | 0.66 ms |
| GCC final link of reference DSO | 15.87 ms |
| One-time GCC runtime archive build | 1.88 s |
| One-time GCC runtime DSO build | 62.03 ms |
| Direct MIR `SQUARE` call | 3.14 ns/call |
| GCC-linked `SQUARE` call | 3.63 ns/call |
| Direct `BASIC_UPPER` (copy + allocation) | 31.76 ns/call |
| GCC `BASIC_UPPER` reference | 26.23 ns/call |
| Direct DSO `dlopen` / `dlclose` | 66.08 / 25.74 µs |
| Direct DSO `dlsym` | 33.78 ns/symbol |

The direct BASIC DSO is 19,904 bytes and the shared runtime is 17,368 bytes,
for 37,272 bytes of deployed ELF files. The GCC-linked reference DSO is
28,432 bytes and contains the runtime statically. The packaging sizes are
therefore not equivalent. Timing spreads overlap substantially; no performance
advantage is claimed for direct emission or calls. This experiment shows the
direct emitter can remove the measured final system-link step, not that the
whole compile pipeline or deployment is faster/smaller.

### Cycle 6 status

- Required direct MIR ELF with `SQUARE` and `ADD`: PASS, direct-linked and
  loaded by C.
- Shared BASIC runtime architecture: PASS for the selected numeric, procedure,
  string input/return, ownership, lifecycle and RTLD_NOW cases.
- Five previous validation suites and `validate-shared-direct.sh`: PASS.
- Self-contained runtime DSO: blocked by retained metaprogramming references
  and unresolved MIR API imports; no false success claimed.
- MADC submodule unchanged at `868847a76434058483bade03ead09ba6acb9d771`;
  no pushes performed. The direct implementation and tests are local lab
  changes; pre-existing root MPDecimal log changes remain untouched.

## Building the BASIC demo corpus as standalone AOT executables

Run `experiments/basic-aot/scripts/build-all-demos-aot.sh` to recursively
compile every `.bas` file under the historical `basic/samples/` tree. An
optional first argument selects another source directory (for example
`basic/tests/programs/`); an optional second argument selects the output root.
The script builds the frontend, MIR adapter and cached static BASIC runtime
once, then processes each source into an executable. `AOT_EXTRA_LIBS` accepts
additional linker flags for demos with external dependencies. The BASIC
runtime is linked statically; the resulting native executables still use the
host libc/libm, but do not need MIR/JIT at runtime.

Executables preserve their source-relative paths under
`results/aot/standalone/bin/`. Intermediary MIR and object files are under
`obj/`, per-program logs under `logs/`, and `manifest.tsv` records pass/fail
and the failing stage. The batch continues after individual failures and
returns nonzero if any program fails, avoiding a misleading all-success exit.

On this machine the 163 files under `basic/samples/` yielded 149 standalone
executables. Thirteen sources fail in the historical frontend on syntax or
type handling (`bcg/blackjack.bas`, `bcg/bug.bas`, `bcg/checkers.bas`,
`bcg/civilwar.bas`, `bcg/combat.bas`, `bcg/horserace.bas`, `bcg/mine.bas`,
`bcg/stockmarket.bas`, `bcg/suite.bas`, `bcg/superstartrek.bas`,
`bcg/test.bas`, `bcg/tictactoe2.bas`, and `pi_spigot.bas`). The remaining
`bcg/awari.bas` parses but the MIR-to-object adapter terminates with signal 11.
These are reported rather than hidden or treated as successful builds. The
generated `array` executable was run and matched the historical interpreter
output; its ELF dependency list has no MIR/JIT library.
