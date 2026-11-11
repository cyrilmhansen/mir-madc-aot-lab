# Exit decision: A — close the direct MIR validation phase

The 24 composite program specifications (six mechanism families) passed 160 independent observations through interpreter, JIT and fresh text/binary reconstruction. JIT outputs were identical across optimizer levels 0–3. Selected ELF objects passed GCC and Clang clients, and the shared-library client passed eight checks. The full Cycle42–45 suites and established regressions remain green. No valid composite semantic or code-generation defect was found.

The remaining uncovered opcode names do not by themselves justify another broad laboratory cycle. The malformed-label SIGSEGV is a real diagnostic risk but occurs on invalid MIR; it does not block integration if the frontend adapter validates branch targets before linking. Preserve this limitation as a backend boundary requirement and revisit only if a real frontend can emit invalid label references or requires recoverable MIR diagnostics.

**Recommendation:** close standalone direct-MIR validation as a general research phase and move to a scoped integration prototype in a real compiler frontend. Start with a lowering inventory and an adapter spike covering the validated subset; measure compiler-level diagnostics, object/linker integration, runtime helper calls and reproducible artifact generation. For PL/I-80, first map its required numeric, storage and call semantics; do not assume the current evidence implies a `drpli` port.

Integration checklist:

1. Keep the MIR source/archive revision and toolchain hashes pinned.
2. Validate MIR function prototypes, branch labels, register types and imports before `MIR_link`.
3. Use exact target ABI prototypes for runtime helpers.
4. Compare emitted objects through an independent native client in CI.
5. Retain focused interpreter/JIT/text/binary smoke cases for each lowering family.
6. Treat unsupported target/type forms as explicit adapter errors.
