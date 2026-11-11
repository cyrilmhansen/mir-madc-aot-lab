# Instruction coverage

The denominator is the 248 concrete instruction enumerators parsed from the
pinned `MIR_insn_code_t` declaration, excluding `INSN_BOUND`. MIR types
enumerated from the pinned `MIR_type_t` include 18 values, including block
types and sentinel values. Thus 25/248 opcodes are exercised by this new
direct semantic harness (10.08%), across two operand/result types
(`MIR_T_I64` and `MIR_T_D`) out of 18 enumerated values.
These ratios are deliberately conservative and do not imply all opcodes are
valid with every type.

The full opcode-to-family list and direct coverage flag are in
`mir-api-inventory.json`. The campaign covers representatives from integer and
floating arithmetic/comparison, bitwise, shift and extension families. It does
not claim complete family coverage:
branch variants, indirect calls, memory operations, vector instructions and
overflow flags remain uncovered by the new corpus.

Existing historical coverage is listed separately in `AUDIT.md` and the lab's
compatibility documentation; it is not inflated into a systematic opcode/type
matrix.
