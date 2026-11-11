# Memory operand coverage

288 executions cover 24 function variants and 25 unique operation/type/address tuples. Types are I8/U8, I16/U16, I32/U32, and I64. Operations include direct reads, direct writes followed by reload, indexed reads at scales 1/2/4/8, overlapping I64-store/U8-load aliasing, and a bounded indexed I64 update loop.

Each execution starts from its own initialized 80-byte buffer with an eight-byte canary on either side of the 64-byte data area. The result scalar, all 64 data bytes and canaries are checked. No valid case accesses out of bounds or reads uninitialized storage. Narrow signed loads are independently sign-extended; unsigned loads are zero-extended. C references use `memcpy`, avoiding strict-aliasing and alignment UB.

I16 indexed scale-1 cases include unaligned but in-bounds reads. The C reference operates on bytes with `memcpy`. I64 effective addresses remain 8-byte aligned in the tested cases. The native object test covers only aligned I64 store/reload. No invalid-pointer probes were executed.

The tuple list, alignment classes, memory types and remaining gaps are in `memory-addressing-coverage.json`. These modes do not inflate opcode counts.
