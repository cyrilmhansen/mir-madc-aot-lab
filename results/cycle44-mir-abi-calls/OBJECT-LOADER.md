# MIR native object loader

The emitted ET_REL artifact was passed to `MIR_object_load` in a fresh process with a resolver that explicitly supplies the three C fixture addresses. The loader executed all 52 scalar exports over three inputs (156 observations), plus the nested internal caller, imported integer and mixed calls, pointer side effects/canaries, and a MIR caller consuming a two-result callee. All checks passed.

With the resolver deliberately withholding `abi_c_mixed`, the loader rejected the artifact with `2 unresolved symbol(s), first: abi_c_mixed` and exit 52. This is a successful negative control, not a loader defect. The loader is not claimed to accept arbitrary ELF objects; these tests use MIR's own emitted format and the documented resolver path.
