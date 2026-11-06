# BASIC to MIR/MADC native AOT: first experiment

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
| `data_read.bas` | pass | pass | **fail** | AOT prints `0 0` / `0`; `DATA` is not serialized in MIR |

The `DATA` limitation is traced to upstream frontend state, not ELF relocation:
`basicc.c` accumulates `DATA` items in its process-local `data_vals` and assigns
them to `basic_data_items` immediately before interpreter/JIT execution. Its
MIR text writer emits no representation for that state. The separately linked
runtime therefore sees its zero-initialized data globals. `DATA`, `READ`, and
`RESTORE` need an explicit emitted data table or startup initialization before
they can be supported in AOT.

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
| arith | 1.96 ms | 1.85 ms | 1,756.64 ms | 1,760.46 ms | 8,112 |
| loop | 1.85 ms | 1.57 ms | 1,832.31 ms | 1,835.73 ms | 4,384 |

The GCC stage recompiles the complete BASIC runtime for each sample; a cached
runtime object or library should be used for a practical build pipeline. The
numbers above include this deliberately simple prototype cost. The GCC
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
not require changing the BASIC parser or code generator. The main integration
work still required is a data-initialization representation and explicit
handling of runtime MIR metaprogramming. Option B, adding object mode directly
to `basicc.c`, can remove the intermediate MIR-text adapter later, but couples
the BASIC frontend to MADC's object API and does not by itself solve those
runtime-state issues. The current MADC object emitter is x86-64 ELF specific;
this prototype does not establish cross-generation support.

## Repository state

No MADC sources were changed and the submodule remains at
`868847a76434058483bade03ead09ba6acb9d771`. No push was performed. The report,
scripts, extracted BASIC subtree, and outputs are lab artifacts under
`experiments/basic-aot/`; ignored upstream full-source build trees live under
`vendor/`.
