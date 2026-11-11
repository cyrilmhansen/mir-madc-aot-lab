# Instruction coverage

Cycle44 baseline: 38/248 enumerated opcode names. Cycle45 successfully executed 18 additional names, yielding 56/248 cumulative unique names. Four of Cycle45's 22 candidate names were already counted: EXT8, UEXT8, I2D and F2D. The 248 denominator is the MIR enum, not a claim that every opcode is legal for this target.

Cycle45 adds 14 conversion opcode/type forms and eight overflow forms; 446 observations include exact input values. Text and binary fresh reloads each reproduce all 446 records. MIR_LD_IS_D=1 means LD candidates do not add distinct opcodes or precision coverage.

The full 248-opcode legal target denominator is not established. Enumerators include target-specific, internal, specialized and otherwise untested forms. See `instruction-coverage.json` and `provenance.json`.
