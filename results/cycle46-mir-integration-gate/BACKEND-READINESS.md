# MIR backend readiness

| Capability | Evidence | Status | Remaining risk |
|---|---|---|---|
| Integer arithmetic | Cycles42/45; Cycle46 overflow composition | Validated for tested I64 and low-32 cases | Not all integer op/type forms; signed overflow behavior outside tested operators remains uncharacterized |
| Floating point | Cycles42/44/45; mixed calls in Cycle46 | Partially validated | Finite selected D operations/conversions; exceptional values, alternate rounding and full F/LD matrix remain open |
| Conversions | Cycle45 14 forms; Cycle46 conversion branches and memory conversion | Validated for tested forms | Out-of-range float-to-int, NaN/Inf, distinct LD precision, exhaustive boundaries untested |
| Overflow handling | Cycle45 all eight candidates; Cycle46 branch and call propagation | Validated for tested op/type forms | ADDO/SUBO unsigned flag not composed; not all overflow instructions/types |
| Control flow | Cycle43 CFGs; Cycle46 branch/loop composites | Validated for bounded CFGs | No general CFG proof, exception/unwind behavior untested |
| Memory | Cycle43 loads/stores/index/alias; Cycle46 memory conversion and bounded loops | Partially validated | Broader alignment/aliasing/concurrency and memory model not exhaustively tested |
| Function calls | Cycle44 signature matrix; Cycle46 internal calls/live values | Validated for selected Linux x86-64 ABI shapes | Other ABIs/aggregate layouts/variadic cases remain risk |
| Cross-module calls | Cycle44 import/export and linking tests | Validated separately | Not combined with Cycle46 composites |
| C ABI | Cycle44 GCC/Clang clients and imports; Cycle46 native clients | Validated for tested host signatures | No portability inference beyond Linux x86-64 and tested prototypes |
| JIT execution | Cycles42–46 | Validated for tested corpus | Uncovered opcode/type combinations remain |
| ELF object emission | Cycles44 and 46 ET_REL objects | Validated for selected functions | Relocation/type breadth limited; not a full linker qualification |
| Shared libraries | Cycle44 and Cycle46 dlopen/dlsym | Validated for selected exports | Lifecycle and symbol-versioning breadth limited |
| Executable/PIE | Historical lab controls | Partially validated | Not exercised by Cycle46 composite corpus |
| Optimization stability | Cycle46 levels 0–3, 160 observations and selected AOT calls | Validated for this corpus | Not all MIR forms or target backends |
| Error diagnostics | Five Cycle46 invalid controls | Partially validated; known crash | Missing branch label causes SIGSEGV during MIR_link in this build; callers should validate MIR before link |
| Cross-target support | Historical platform reports | Partially validated historically | No Cycle46 cross-target execution; current result is Linux x86-64 only |
| Reproducibility | Isolated archive and hashes; repeated process and serialization comparisons | Validated for this environment | Historical build provenance is not guaranteed by source-tree identity alone |

## Compiler integration implications

The evidence supports a real compiler adapter prototype on Linux x86-64 for a deliberately scoped typed IR subset: typed value lowering, ordinary branches and loops, bounded memory operations, scalar calls, C-compatible helper calls, and ELF ET_REL linking. A compiler must own source-language semantics, target ABI classification, runtime-helper prototypes, object metadata and diagnostics. MIR does not replace a frontend verifier or linker integration layer.

For a future PL/I-80 backend abstraction, this evidence supports an isolated adapter spike after a lowering inventory maps the required PL/I-80 types, condition codes, storage model, calls and runtime helpers to MIR constructs. It does not establish that an existing `drpli` implementation has been ported or that PL/I-80-specific numeric/storage semantics fit the tested subset. `drpli` was not modified.
