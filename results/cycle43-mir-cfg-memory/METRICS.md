# Metrics

- Valid direct differential cases: 412 (124 CFG, 288 memory).
- Unique generated functions: 34 (10 CFG, 24 memory).
- Cycle42 baseline rerun: 353 rows per path × direct/text/binary; all matched byte-for-byte.
- Cycle43 paths: direct interpreter + JIT; fresh text interpreter + JIT; fresh binary interpreter + JIT; second fresh direct run. All 412 rows equivalent across paths.
- CFG: nine semantic families; 5 branch opcodes observed (`BEQ`, `BGE`, `BGT`, `BLT`, `UBLT`) plus `JMP`; both outcomes for listed conditional sites.
- Memory: 25 unique typed operation/address tuples, 4 load/store widths, 8 semantic/addressing family groupings, 8-byte canaries.
- Opcode coverage: Cycle42 30, Cycle43 adds 4, cumulative unique 34/248 enum names.
- Negative parser controls: 32/32 rejected; no timeouts.
- Reducer tests: 2 injected mismatches minimized; 0 real failures to reduce.
- Selected AOT: 2 functions from a 5,608-byte object, independent C client passed.
- MADC object-load: 9 cases / 142 assertions passed. Native-shared: 5 cases / 169 assertions passed.
- Workspace regression: 303 tests and 148 subtests passed.
- MIR/MADC production source changes: zero. MADC checkout untouched.
- Archive provenance: not established as a clean rebuild from the historical pin.
