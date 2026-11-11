# ABI and native execution evidence

Cycle42 did not add or rerun a new ABI fixture. Existing direct MIR lab
evidence is available in `docs/COMPATIBILITY.md` and `docs/RESULTS.md`:

- Standalone C clients link directly against `libmir.a` without MADC frontend
  libraries.
- Existing MIR smoke tests call generated functions and an imported libc
  `labs` function.
- Linux runs previously covered MIR-emitted ELF objects through
  `MIR_object_load`, `.so` through an independent GCC `dlopen` client, and
  PIE via a separate process; AArch64 was exercised under QEMU.
- The expanded multimodule object-loader example has a documented failing
  indirect-call path and is not considered a pass; its text/JIT, shared and
  PIE paths pass as recorded in historical evidence.

This is reuse of prior evidence, not new Cycle42 ABI coverage. The direct
Cycle42 harness is I64 semantic execution only and does not establish C ABI
coverage for every type or arity.
