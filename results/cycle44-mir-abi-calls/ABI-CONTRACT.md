# ABI contract and tested scope

The host is Linux x86-64, using the System V AMD64 ABI for C-compatible native calls. The scalar matrix classifies integer and pointer arguments in the GP sequence RDI, RSI, RDX, RCX, R8, R9; float/double arguments in XMM0–XMM7; and arguments that exhaust their class into stack slots. Scalar integer/pointer results are observed through RAX and double results through XMM0. The generated matrix metadata records per-argument class/location and stack count.

The implementation classifies scalar arguments by class independently; it is not a complete psABI classifier for aggregates, vectors, x87/long-double values, hidden structure returns, variadic calls or all alignment corner cases. Stack alignment is exercised indirectly by generated calls and native clients but was not inspected at every call site. Callee-saved register correctness is probed by caller-live values across nested calls, not exhaustively enumerated.

The 48 confirmatory shapes cover I64-only, D-only, alternating, integer-then-double, double-then-integer and mixed-width sequences at arities 0, 1, 2, 4–10 as available. Four extra exploratory shapes put mixed arguments over GP/SSE boundaries. Return forms include I64, D, I32-to-I64, U32-to-U64, F-to-F, P-to-P, and an internal two-result `(I64,D)` callee consumed by a single-D caller. No incompatible C function-pointer prototype is called.

`MIR_JCALL/JRET` are not ordinary indirect calls. The pinned documentation explicitly assigns them a non-standard ABI for functions without ordinary arguments/returns. A general indirect C call path, variadic ABI, aggregate ABI and cross-target ABI remain outside the validated scope.
