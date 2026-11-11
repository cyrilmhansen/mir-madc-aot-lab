# Cycle 42 — Direct MIR API coverage

## Outcome

The first direct, deterministic MIR differential tranche passed. A standalone
C client built 344 functions programmatically through MIR's public API and
compared the interpreter and JIT against an independent arithmetic reference.
The exact same module was serialized as MIR text and binary, then parsed in
fresh processes and executed through JIT. All 1,032 emitted result rows agree;
the three JSONL result streams are byte-identical.

This establishes direct semantic and persistence checks for 25 instructions across I64 and D. It is not comprehensive MIR coverage: the pinned enum has
248 concrete opcodes and 18 type enumerators, while this corpus exercises 25
opcodes and two types. The requested broad control-flow, floating-point, ABI
and negative API campaign is not complete; the float slice uses only finite
exactly representable values. A strict-C11 compile probe also
found a header issue: `mir.h` uses `va_list` without including `<stdarg.h>`.
Direct inclusion fails unless the caller preincludes that standard header.
This is not an execution defect; no pinned source was changed.

## API/build qualification

Root HEAD matches the expected Cycle41 commit prefix. MADC is a clean checkout
at `868847a76434058483bade03ead09ba6acb9d771`, one local commit beyond the
requested f541 baseline. That commit only changes parser handling/tests for
unsupported GNU asm; the submodule was not modified. The exact provenance of
the prebuilt archive relative to f541 cannot be established, so all direct
results are qualified to the available headers and archive, not claimed as a
fresh exact-f541 build.

The header/archive comparison found 181 API names including header inline
helpers and 171 exported MIR symbols. `MIR_get_global_item` is the sole
non-inline declaration in this inventory without an archive definition.
`MIR_init` and related inline calls are header implementations, not missing
symbols. Inventory detail is machine-readable in `mir-api-inventory.json`.

## Evidence

- Direct construction + interpreter/JIT: 344/344 agree.
- Fresh text serialization parse + JIT: 344/344 agree.
- Fresh binary decode + JIT: 344/344 agree.
- MADC object-load regression: 9 cases / 142 assertions pass.
- MADC native shared regression: 5 cases / 169 assertions pass.
- Full Workspace suite was run during this cycle; its final count is recorded
  in `REGRESSION.md`.
- New MIR/MADC production code: zero.

Prior direct MIR ABI/AOT coverage was reused from lab history rather than
rerunning those large matrices. See `ABI.md`. No new ABI or MIR semantic
counterexample was discovered. A compile-time header self-containment
issue and the initial zero-divisor harness defect are described in
`FAILURES.md`.

## Acceptance levels

- Level 0 API availability: pass with qualification (archive is from the
  checked-out MADC descendant, not a verified fresh f541 build).
- Level 1 API inventory: pass.
- Level 2 independent direct semantic corpus: pass for the bounded I64/D slice.
- Level 3 differential execution: pass for interpreter, JIT, text and binary
  paths in that slice.
- Level 4 control-flow and ABI: prior lab evidence exists, but new diversified
  Cycle42 generation is incomplete.
- Level 5 AOT/persistence: persistence passes here; prior selected AOT paths
  are documented, not rerun.
- Level 6 robustness: incomplete; no new broad invalid-input campaign.
- Level 7 counterexample reduction: no failure to reduce; reducer validation
  incomplete.
- Level 8 concrete coverage metrics: pass, with uncovered regions reported.
- Level 9 performance: exploratory samples recorded; confirmatory baseline
  incomplete.
- Level 10 new MIR semantic/code-generation defect: none found. A strict-C11
  header self-containment issue was reproduced and preserved.

See `AUDIT.md`, `INSTRUCTION-COVERAGE.md`, and `REPRODUCE.md` for details.
