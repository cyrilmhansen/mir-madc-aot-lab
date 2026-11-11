# Independent reference semantics

The C references implement bounded mathematical algorithms separately from MIR construction and execution. CFG references use ordinary signed/unsigned C arithmetic over small registered values; loop operands are bounded to 0–8. Thus sums/products remain in range and avoid signed overflow. The signed/unsigned branch reference converts to `uint64_t` using defined modulo conversion.

Memory references use initialized byte arrays, explicit `memcpy` loads/stores, and explicit sign extension for signed narrow values. The host is little-endian x86-64; expected memory bytes are compared exactly for this host. No floating-point arithmetic, NaN, infinity or exceptional operations are part of Cycle43.

Every result row stores the case, input, expected scalar, interpreter scalar, JIT scalar, post-execution memory bytes (for memory tests), and canary status. Reordered or mutated backend memory is never reused as another route's input.
