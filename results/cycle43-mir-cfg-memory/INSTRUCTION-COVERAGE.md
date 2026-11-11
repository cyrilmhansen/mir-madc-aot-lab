# Instruction coverage

The pinned enum denominator remains 248. Cycle42's 30 tested names and Cycle43's direct MIR source yield 34 unique cumulative names (13.71%). Cycle43 adds `BEQ`, `BGT`, `JMP`, and `UBLT`; memory addressing modes do not count as opcodes. The current CFG program also uses `ADD`, `BGE`, `BLT`, `MOV`, `MUL`, `RET`, and `SUB`, all represented in the Cycle42 set.

Cycle43 did not add 20 new opcode names. The campaign target was not met and is reported rather than padded. `instruction-coverage.json` lists the exact cumulative names. New conditional branches are exercised with both taken and not-taken inputs as shown in `cfg-coverage.json`; branch outcome totals are calculated from the frozen inputs/specification, not hardware tracing.

Memory coverage is a separate axis: 25 distinct typed operation/address tuples across 24 memory functions. See `memory-addressing-coverage.json`.
