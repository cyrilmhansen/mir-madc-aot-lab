# Regression

- Cycle45 direct conversion/overflow corpus: 446 observations passed in interpreter/JIT.
- Fresh MIR text: 446 passed.
- Fresh MIR binary: 446 passed.
- Native ELF ET_REL object with independent C client: 12 checks passed.
- MADC `test_object_load`: 9 cases / 142 assertions passed.
- MADC `test_native_shared`: 5 cases / 169 assertions passed.
- BASIC Workspace pytest: 303 tests and 148 subtests passed.
- Cycle42: 353 passed; Cycle43: 412 passed; Cycle44: 52 signature shapes × 5 values, zero mismatches. These binaries are the isolated-archive regression executables retained from Cycle44.

The full direct observation JSONL is retained once. Text and binary route outputs were byte-compared to it and matched; UBSan-instrumented oracle run also matched it byte-for-byte. `serialization-results.json` records artifact hashes and this equality. Redundant identical route logs and the generated ELF object/client executable were omitted; source and exact reproduction commands are retained.
