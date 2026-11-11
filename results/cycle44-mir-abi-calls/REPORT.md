# Cycle44 — Calling conventions, ABI and native linking

## Result

The Cycle44 confirmatory matrix exercised **48 distinct scalar signatures** on the checked-out Linux x86-64 MIR implementation. Four extra mixed register/stack signatures were run as a clearly marked exploratory supplement. All 52 shapes agreed with the independent weighted reference through MIR interpreter, JIT, fresh text parse/JIT, fresh binary decode/JIT, system-linked ELF object, shared library/dlsym and `MIR_object_load` for the applicable cases. GCC and Clang clients both passed the emitted object and shared-library checks.

The direct semantic tier recorded 260 signature/seed observations (48 confirmatory and 4 exploratory, five seeds each). The 52 shapes were also checked through each serialized path. Nested MIR-to-MIR calls, imported C integer and mixed calls, pointer side effects, narrow integer identities, float/pointer identities and a multiple-result MIR call were checked separately. No MIR ABI or execution defect was confirmed.

The observed first failures were harness defects: duplicate generated local names, use of integer `MOV` for a double register, and one wrong expected value in the object-loader mixed-import check. Each was corrected, retained in `FAILURES.md`, then rerun from a fresh process. The missing-import control rejected as expected. Strict C11 inclusion of `mir.h` still fails without `<stdarg.h>` preincluded; this is an API header usability issue, not an execution failure.

## Coverage and limits

- 52 distinct signature shapes tested: 48 preregistered and 4 exploratory mixed spill cases.
- 260 main interpreter/JIT observations; 260 text and 260 binary replay observations.
- 156 object-loader signature calls (52 signatures × 3 input seeds), plus internal, imported, pointer and multiple-result checks.
- 52 emitted functions called by independent GCC and Clang clients from ET_REL and `.so` output.
- Three imported C call families: eight integer arguments, mixed integer/double arguments, and pointer plus length with bounded writes.
- Internal 8-argument calls, reordered call arguments, nested caller/callee, caller-live values across calls, and a two-result MIR callee.
- One missing-import loader rejection and 32 isolated malformed MIR parser controls.
- Existing Cycle42 (353 cases) and Cycle43 (412 cases) corpora passed again against the isolated archive with direct/text/binary result files byte-identical.
- Workspace regression: 303 tests and 148 subtests passed. Existing MADC object-load: 9 tests/142 assertions; native-shared: 5 tests/169 assertions.

The archive already present in the MADC checkout has an unverified historical build provenance. Cycle44 therefore built an isolated archive from the checked-out MIR source into the ignored Cycle44 build directory and ran the ABI corpus against it. The MADC submodule and its archive were not modified. The ABI matrix covers scalar SysV argument classes; it does not establish correctness for aggregates, long double, vector types, variadic calls, all return combinations or every target ABI. `MIR_JCALL/JRET` use a documented non-standard threading ABI and were not treated as ordinary C indirect calls. No cross-target execution was performed.

## Acceptance levels

| Level | Status |
|---|---|
| 0 API/ABI blocker | Passed for the tested scalar signatures; unsupported families are listed in `ABI-CONTRACT.md`. |
| 1 Verified ABI matrix | Passed for Linux x86-64 SysV scalar integer, pointer, float and double argument classes and observed register/stack crossings. |
| 2 Independent direct calls | Passed: interpreter and JIT match reference. |
| 3 Internal composition | Passed for direct and nested MIR calls and live values across calls. |
| 4 External C integration | Passed for imported integer, mixed and pointer calls in interpreter/JIT. |
| 5 System-linked AOT | Passed: 52 signatures linked to independent GCC and Clang clients. |
| 6 Dynamic/native loading | Passed for shared library/dlsym and selected `MIR_object_load` paths. |
| 7 Signature coverage | Passed for the matrix described above; not a full ABI Cartesian product. |
| 8 Negative API robustness | Partial: 32 parser controls and a missing-import resolver rejection; mismatched native C prototypes were deliberately never invoked. |
| 9 Counterexample reduction | Not completed as a structural MIR reducer; initial harness discrepancies were diagnosed and preserved. |
| 10 Historical compatibility | Passed for Cycle42/43, MADC object-load/native-shared, and Workspace regression. |
| 11 Genuine defect discovery | None confirmed. |

See `REPRODUCE.md` for regeneration commands and `provenance.json` for source/archive fingerprints.
