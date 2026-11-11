# Test architecture

`mir-cfg-memory.c` builds MIR directly through the public C API; MADC's C frontend is not involved. One bounded fixture set defines function inputs, operations and expected behavior. Simple C references implement the intended algorithms independently of MIR execution.

For each route, the C harness initializes a fresh context and performs the same checks:

1. Direct construction: construct MIR, run interpreter and JIT.
2. Text: load the pre-link MIR text in a new process, execute interpreter and JIT.
3. Binary: decode the pre-link `.bmir` in a new process, execute interpreter and JIT.
4. A second fresh direct process repeats the corpus.

The program saves text/binary before `MIR_load_module`/linking because linking lowers raw memory operands. Persisted artifacts are `generated-programs.mir` and `.bmir`.

Memory tests reset an 80-byte buffer for the C reference, interpreter, and JIT independently. Eight bytes on each side are canaries; all bytes are compared. The reference uses `memcpy` for multibyte accesses and explicitly defines sign extension for 8/16/32-bit loads. The test host is little-endian x86-64; cross-endian behavior was not tested.

The reducer is deliberately limited: it selects a smaller failing row and input from cases already run. It does not rewrite MIR instructions, CFGs or memory sequences. It was validated using two injected expected-value faults. Injected faults are not product findings.
