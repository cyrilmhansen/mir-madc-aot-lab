# Metrics

- MIR source functions constructed in the matrix: 52 (48 confirmatory, 4 exploratory), plus helper/caller functions.
- Main argument/result observations: 260.
- Text round-trip observations: 260; binary round-trip observations: 260.
- Direct, text and binary JSONL observation files are byte-identical.
- Native system-linked ET_REL client: 52 signatures, GCC and Clang, zero mismatches.
- Shared library/dlsym client: 52 signatures, GCC and Clang, zero mismatches.
- Object loader: 52 signatures × 3 values plus five call-side-effect checks, zero mismatches.
- Additional direct calls: 3 seeds across internal nested call, imported integer, imported mixed, pointer side effect, type identities and multiple-return caller.
- Invalid MIR parser controls: 32/32 rejected in isolated processes. Missing object-loader import: rejected with unresolved-symbol diagnostic.
- Cumulative Cycle42/43 opcode-name coverage: 34/248; Cycle44 adds CALL, DMOV, F2D and I2D, for 38/248 unique names. Signature coverage is reported separately; this does not mean 38 opcodes cover all types.
- Production MIR/MADC source changes: 0. Test tooling added: `cycle44-abi-matrix.py`, `mir-abi-corpus.c`, `cycle44-inventory.py`, `cycle44-performance.py`.
- Binary artifact provenance: checked-out archive is not claimed to be a reproducible build; isolated archive was built from the unchanged checkout and fingerprinted in `provenance.json`.
