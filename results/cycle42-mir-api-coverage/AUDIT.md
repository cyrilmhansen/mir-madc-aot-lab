# Cycle 42 audit

## Checkout and build

The root checkout is at `348a4c4e1d8374b2ec04af8339ad503f1b178015` on
`experiment/mir-aot-correctness-cycle3`, matching the expected Cycle41 prefix.
The repository had pre-existing unrelated edits and untracked evidence in the
BASIC Workspace, MPDecimal and Pi areas. They were preserved and not staged.

MADC is **not** at the requested baseline: its clean checkout is
`868847a76434058483bade03ead09ba6acb9d771`, one commit after
`f541a7a54624869e29b01f2f30b174bc0329eea5`. The extra commit is
`Reject unsupported GNU asm statements`; it changes parser behavior/tests and
does not modify the MIR subtree. The submodule was not reset or updated.
Consequently this report's linked archive is the available archive from that
checkout, not a freshly rebuilt artifact proven to come from the exact f541
commit. The archive and headers were inspected and the direct harness linked
successfully. The `third_party/mir` subtree is byte-identical between f541 and
the checked-out descendant. SHA-256 digests for the archive and inspected
headers are recorded in `mir-api-inventory.json`.

Host: Linux x86-64, GCC 16.2.1. The tested archive is
`madc/obj/mir/host/libmir.a`.

## Existing coverage reused

The lab already has a standalone C MIR smoke test, a programmatic multimodule
example, text and `.bmir` round trips, Linux ELF object/shared/PIE experiments,
and AArch64 QEMU results. Those artifacts are documented in `docs/RESULTS.md`
and `docs/COMPATIBILITY.md`; this campaign did not rerun their large benchmark
matrices. It did rerun the existing host `test_object_load` and
`test_native_shared` binaries.

MADC frontend tests are not counted as direct MIR-generated semantic cases.
The direct Cycle42 corpus is specifically the standalone programmatic C
harness in `experiments/mir-api-coverage/mir-diff.c`.

## API inventory finding

The pinned headers expose 181 function-like API names after excluding macros;
171 MIR-prefixed symbols are defined by the available archive. Header-only
inline functions are distinguished from missing archive symbols. The
declaration `MIR_get_global_item` has no corresponding archive definition and
must not be treated as usable from this build. The generated inventory is in
`mir-api-inventory.json`.

The instruction enum contains 248 concrete instructions (excluding the bound
sentinel), across 18 MIR types. The final differential harness covers 18 integer instructions, 7 double
instructions and one small loop shape across I64 and D; this is a measured
first slice, not broad opcode coverage. Most vector, memory, call and control-flow
instruction/type combinations remain untested by the new harness.

## API surface observed

The headers declare program/module/function/prototype construction, operands,
instructions, imports/exports, linking, interpreter calls, MIR text/binary
I/O, JIT and native object emission/loading. The linked archive confirms most
entry points by symbol inspection. Interpreter and JIT are available on the
current host. Native object/shared/PIE emission is supported by the Linux
x86-64 paths already documented by the lab. `MIR_object_load` is a targeted
loader for MIR-emitted objects, not a general object loader.

Target support is build dependent. Existing lab evidence establishes native
Linux x86-64 and prior AArch64 cross/QEMU coverage; this Cycle42 run itself is
Linux x86-64 only. No other target was executed here.
