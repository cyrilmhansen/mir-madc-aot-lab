# Cycle 10 — Persistent execution instances: feasibility and stop report

## Outcome

The requested persistent shared-state feature is **not implemented in this
cycle**. No result below should be read as evidence that multiple BASIC
functions share runtime arrays or that an instance survives a call. The
validated baseline remains the stateless, one-process-per-invocation MIR
worker from Cycle 9. This report records the P0 investigation and the exact
integration boundary before a larger worker/projection change is attempted.

The stop was deliberate: a Python-side cache or dictionary would not make
MIR-generated BASIC functions share mutable state, while keeping the present
worker and merely retaining its process would still reinitialize its
function-local arrays. A valid implementation needs a coordinated change to
the canonical projection, binary protocol, MIR lowering, call ABI, and worker
lifecycle. The architecture decision is in
[`ARCHITECTURE.md`](ARCHITECTURE.md).

## Existing ownership and execution path

```text
Workspace document + revision
    └── canonical tokens (editable source of truth)
          └── build_projection(document, expected_revision)
                └── BWM4 + one target + one argument vector
                      └── subprocess mir-worker
                            ├── parse/validate all functions
                            ├── construct MIR context and functions
                            ├── link and invoke one function
                            ├── copy/JSON-escape returned string
                            └── MIR_finish + process exit
```

`CompilableProjection` is a frozen, revision-bound Python value, but there is
no managed `CompiledModule` handle or `ExecutionInstance` handle. The JSON-RPC
server is long-lived; the native execution worker is not. This distinction
matters: persistence of the editing service does not imply persistence of
MIR code or execution state.

Cycle 9's numeric and string arrays are declared inside a function. The C
worker creates MIR stack storage or per-call registers while building that
function and initializes the cells to zero/empty on each invocation. String
literals and returned strings are worker-owned; the result is copied into the
response before cleanup. There is no mutable string-cell replacement across
calls.

## Pinned MIR API findings

The pinned headers expose `MIR_new_bss`, `MIR_new_data`, `MIR_new_ref_op`,
`MIR_new_mem_op`, `MIR_interp_arr`, `MIR_gen`, `MIR_gen_finish`, and
`MIR_finish`. The current worker also declares its final error-status argument
as `MIR_T_P` and obtains it with `MIR_reg`. These APIs provide plausible
building blocks for a per-instance state pointer or per-context MIR data.

This is a feasibility finding, not a completed state experiment: the current
code has not validated cross-function writes through a state pointer or
isolated MIR globals across two retained execution contexts. The MIR API does
not remove the need to encode state declarations, references, initialization,
and instance ownership in the Workspace model and worker protocol.

## Concrete blockers to a safe minimal patch

1. **Projection has no shared-array concept.** `ArrayProjection` has bounds and
   element type but no scope/lifetime marker. The projection builder collects
   arrays for a function scope and rejects references outside that scope.
   Module-scope `DIM` tokens are indexed as module symbols, but the executable
   expression and assignment validators only accept current-function arrays.
2. **BWM4 describes one invocation.** Its header includes one target and the
   trailing payload contains that target's argument vector. The C reader
   requires exact end-of-buffer consumption. There is no module-load message,
   instance creation, function-call command, request ID, or framed streaming
   protocol.
3. **The worker destroys the compiled state.** It links and invokes once,
   calls `MIR_gen_finish` for JIT, then `MIR_finish`, frees the parsed
   projection, and exits. A retained process requires moving those lifetimes
   outside the invocation loop and retaining generated addresses for all
   callable functions.
4. **MIR calls and host calls have different signatures.** Current functions
   accept user arguments and an error pointer. A hidden state pointer must be
   incorporated consistently into prototypes, function definitions, internal
   `MIR_CALL`s, interpreter argument arrays, and native JIT call wrappers.
5. **Initialization and state mutation need defined semantics.** A new
   instance needs one-time initialization; calls must not rerun it. A failure
   during mutation must invalidate the process/instance rather than silently
   recreate zeroed state. String replacement additionally requires reclaiming
   obsolete values or an explicitly read-only policy.

Implementing only one layer would create misleading semantics. The smallest
coherent next implementation should add a new versioned module projection,
shared array declarations and a designated MIR initializer, then a bounded
framed persistent worker. A worker process per instance is the lower-risk
first version: MIR globals are naturally isolated, but each instance compiles
its own copy. The later optimization is to share compiled code and pass an
explicit state pointer, after confirming interpreter and JIT ABI behavior.

## Baseline validation

Commands, run from `experiments/basic-workspace/`:

```sh
./scripts/build-mir-worker.sh
python3 -m unittest discover -s tests -p 'test_*.py'
```

Results:

- Native worker build: **passed**.
- Existing Workspace unit suite: **81 tests passed**.
- Sanitized worker build (Clang `-fsanitize=address,undefined`) and the same
  81-test suite with `ASAN_OPTIONS=detect_leaks=1:halt_on_error=1` and
  `UBSAN_OPTIONS=halt_on_error=1`: **81 tests passed**, no sanitizer report.
- The sanitizer binary was created in a `TemporaryDirectory` under
  `native/build/` and removed automatically.

The first test invocation was started concurrently with the worker build and
had six expected `MIR_WORKER_NOT_BUILT` errors because it raced the output
file. It was rerun after the build completed; the sequential run above is the
valid baseline result.

No persistent-instance benchmark was run because no persistent execution
path exists. Cycle 9's fresh-worker measurements remain in
[`../string-lookup/REPORT.md`](../string-lookup/REPORT.md); they must not be
compared to nonexistent warm-instance timings.

## Answers to the requested questions

1. **Can several functions operate on shared mutable state?** No. Functions
   can call one another within one invocation, but the projection has no
   shared component state.
2. **Can two instances have independent persistent data?** No instance API
   exists. Separate fresh worker calls have isolated local storage, which is
   not persistence.
3. **Is definition/runtime ownership separated?** Partially by lifetime:
   canonical tokens/revision and immutable projection are separate from
   worker allocations. There is not yet an explicit public object model.
4. **Is compiled code reused?** No. Each invocation builds/links and then
   releases its MIR context; JIT code is released before worker exit.
5. **Does persistence reduce repeated-call latency?** Not measured. Current
   calls include worker startup and MIR build/link; no warm invocation exists.
6. **What happens after timeout?** The subprocess request is terminated and
   returned as an execution timeout. Since calls are stateless, there is no
   prior state to preserve. A future persistent worker must invalidate the
   affected instance and never recreate it transparently.
7. **Is string state bounded and releasable?** Per-invocation string bytes are
   bounded and cleaned up by worker exit; mutable persistent string-cell
   replacement is not implemented.
8. **How do edits affect existing instances?** There are no instances. Each
   execution validates its expected Workspace revision and rebuilds from that
   revision; stale calls are rejected.
9. **What remains for a complete ECS address book?** Shared numeric and string
   state, initializer semantics, string replacement ownership, revision-bound
   compiled modules, instance lifecycle, and agent-facing discovery/inspection
   operations.
10. **What would an agent need?** Opaque module/instance IDs; explicit create,
    inspect, call, destroy, and release operations; revision and schema
    metadata; typed component declarations; and structured errors for invalid
    IDs, bounds, timeouts, and stale definitions.

## Git and scope

This cycle only adds the architecture decision and feasibility report. No
BASIC compiler, MIR, MADC, native worker, or source model was changed. No push
was performed. The pre-existing MPDecimal working-tree changes were left
untouched.
