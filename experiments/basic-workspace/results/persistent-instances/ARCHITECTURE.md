# Persistent instance architecture decision

The prototype uses three lifetimes:

1. **ProgramDefinition** is the existing `Workspace` document and its canonical
   token stream/revision. Projection building is read-only and bound to that
   revision.
2. **CompiledModule** is a Python-managed opaque handle for one immutable
   projection and engine. It records the document and revision used to build
   it. A later edit creates a different handle; it does not retarget old code.
3. **ExecutionInstance** is a persistent native worker process for one compiled
   handle. MIR data items provide shared arrays within that process. Destroying
   the process releases the data and MIR context.

The pinned MIR public API declares function parameters as `MIR_var_t` records,
including `MIR_T_P`, and exposes `MIR_new_bss`, `MIR_new_data`,
`MIR_new_ref_op`, and `MIR_new_mem_op`. The current worker already uses a
`MIR_T_P` parameter for its error-status pointer and successfully retrieves it
with `MIR_reg`; this establishes the ABI mechanism. For isolation, the initial
implementation chooses MIR module data per worker rather than passing a
state pointer through every function. Thus all functions in one instance see
the same MIR data, while separate worker processes cannot share it.

MIR's globals are not used as an editable program model: declarations and
initialization functions remain canonical Workspace tokens. A structured
projection identifies shared arrays. A designated BASIC initializer function
contains the actual writes and is called once when an instance starts. Runtime
mutations do not change the Workspace revision.

The tradeoff is that each instance recompiles the projection. The compiled
representation is reused across calls within one instance, but not across
instances. This is intentional in the first validation slice; an explicit
state-pointer ABI can be considered after correctness is established.

The implemented persistent command channel uses bounded length-prefixed
binary requests and one JSON response per request, correlated by request ID.
Python owns the worker lifecycle and serializes commands to a given instance.
The worker reads the BWM projection once, compiles once, and retains the MIR
context and generated functions until shutdown. BWM5 marks shared numeric
arrays and their slots; BWM1–BWM4 remain accepted. The existing one-shot worker
protocol remains the default path.

The explicit initializer is an ordinary projected MIR function selected at
instance creation. It executes once before the handle is published. Its MIR
assignments populate worker-owned module BSS arrays; Python never stores
runtime records. Persistent worker failure or timeout marks that instance
dead, with no restart or state reset. Calls within an instance are serialized.
There is no hot reload, state migration, cross-process shared memory, or claim
of a general security sandbox.

The current implementation compiles one MIR module per worker. “Prepared
module” is an immutable projection and metadata handle, not shared native code.
Compiled functions are reused only across calls made to the same instance.
The top-level fixed numeric `DIM` is a restricted Workspace extension, not a
claim of historical BASIC module-global semantics.

The current worker lowers pointer-valued MIR data references through the
x86-64 host ABI already used by the string implementation. This experiment is
host-specific until pointer lowering is validated on another target.
