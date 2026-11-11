# Generator and corpus

The generator is `experiments/mir-api-coverage/mir-diff.c`. It creates 16
functions per integer operation and uses a fixed 16-pair operand table. Division and
remainder replace zero divisors with one; shift counts are masked to the
valid 0..63 range. The resulting 288 I64 and 56 D case specifications (344 total) are reproducible
without a random seed. This first direct API tranche is deterministic
stratification, not a randomized campaign.

Covered concrete instructions: `ADD`, `SUB`, `MUL`, `DIV`, `MOD`, `AND`, `OR`,
`XOR`, `LSH`, `RSH`, `URSH`, `EQ`, `LT`, `ULT`, `GE`, `UGE`, `EXT8`, `UEXT8`, `DADD`, `DSUB`, `DMUL`, `DDIV`, `DEQ`, `DLT`, `DGE`.
Integer operations use I64 registers; floating operations use D operands and D or I64 results in the available host interpreter and JIT.
Control-flow, ABI and multi-module families are not part of these 344
cases. Existing direct MIR experiments provide separate selected evidence for
multi-module calls, external `labs`, globals, `.so`, PIE, `.o`, and AArch64
QEMU, but those are not merged into the direct opcode denominator.
