# Instruction and signature coverage

Cycle42/43 cumulatively exercised 34 unique concrete opcode names out of 248 enumerated. Cycle44 adds `CALL`, `DMOV`, `F2D` and `I2D`, for 38 unique names. These are direct MIR instruction uses in the ABI harness; call behavior is further divided by signature, import mode and native path.

The 248 enumerator count is retained as the requested name-level denominator. It is not multiplied by every type because many combinations are illegal or nonsensical. `instruction-coverage.json` lists names and tested argument-type sequences. `signature-coverage.json` reports the ordered function signature matrix and stack-placement shapes separately. Native ET_REL, shared and loader execution are separate from interpreter/JIT opcode execution.
