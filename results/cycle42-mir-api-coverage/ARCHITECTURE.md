# Harness architecture

The corpus has four independent pieces:

1. `mir-diff.c` deterministically creates one MIR module with 288 two-argument
   I64 functions plus 56 two-argument D functions using public `MIR_new_module`, `MIR_new_func`, register,
   instruction and return APIs.
2. A small C reference switch computes expected bit patterns from the saved
   operands. Inputs avoid signed overflow and division/remainder exceptional
   cases. Arithmetic right shift is defined explicitly in the oracle; shift
   counts are restricted to 0..63.
3. Each function runs via `MIR_interp_arr` and `MIR_gen` in the original
   context. The same module is emitted to MIR text and binary forms, then each
   is parsed in a fresh process and run through JIT against the same oracle.
4. JSONL output records case name, operands, expected result, interpreter
   result and JIT result.

This is a bounded direct API test, not a MIR compiler or general IR
interpreter. The independent calculation intentionally supports only the
enumerated integer and finite double operations used by the campaign.

Integer operations use I64 operands/results; a separate finite F64 family tests DADD, DSUB, DMUL, DDIV, DEQ, DLT and DGE. Although the header lists
I8/U8/I16/U16/I32/U32/I64/U64 and F/D/LD/P/BLK/RBLK/V128 types, those are not
all tested combinations. The existing lab's native ABI and AOT clients are
reused as prior evidence, with their limits called out in the report.
