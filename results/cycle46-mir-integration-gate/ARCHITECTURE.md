# Architecture and evidence boundaries

Cycle46 reuses MIR's pinned public construction, interpreter, serialization, generator, object-emission and linking APIs. The campaign adds only bounded test tooling; it changes no MIR, MADC or BASIC Workspace production code.

`mir-composition.c` builds six composite families from typed specifications and computes expected values independently in C. The same module is exercised through direct interpretation/JIT, text and binary persistence, and optimizer settings 0–3. Native object and shared-library artifacts are produced by the existing MIR object-emission interface and consumed by separate typed C clients. `mir-validation-probe.c` isolates malformed-input and link-error probes. `reduce-composition.py` reuses bounded typed MIR templates to test structural reduction of injected discrepancies.

## Trust boundaries

- **Reference semantics:** explicit C arithmetic, byte-level memory expectations, and hand-checked branch/conversion rules; it does not call MIR.
- **Interpreter:** executes the generated MIR module and is compared to the reference.
- **JIT:** generated code is called through exact C prototypes and compared independently.
- **Persistence:** serialized text and binary inputs are loaded into fresh MIR contexts before execution.
- **AOT:** emitted ELF objects/shared objects are called by separately compiled clients; successful linking alone is not counted as a pass.
- **Optimization:** each registered MIR generation level is tested for output equivalence; timing is reported separately.

## Scope boundary

The Cycle46 confirmation set covers six composite families and selected Linux x86-64 routes. Cross-module composition, a composite MIR-imported C helper, `MIR_object_load`, PIE, cross-target execution and a second independent input configuration were not executed in this cycle. Cycle44's separate evidence does not upgrade these to Cycle46 composite coverage.
