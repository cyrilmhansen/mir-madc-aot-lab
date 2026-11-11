# Internal MIR calls

The first module defines two 8-I64 weighted leaves and a two-result `(I64,D)` function. A second module imports and calls both leaves. `abi_internal_caller` keeps values live across two calls, passes the first call's arguments in order, reverses them for the second, then combines both results. `abi_chain_top` calls that caller and adjusts the result. The reference calculation is separately expressed in C.

Interpreter and JIT results agree for three seeds. The internal caller and chain are also executed from the emitted object, shared library client and selected object-loader path. The multi-result function is tested only through a MIR caller; no unsupported C tuple representation is inferred.

No ordinary indirect function-pointer call was tested. `MIR_JCALL/JRET` are not used as a substitute because their documented ABI is non-standard.
