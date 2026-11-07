# Cycle 7 — Typed numeric arrays and indexed memory

## Result

The workspace can now construct and execute fixed-capacity, one-dimensional
numeric arrays in memory. The path is still:

`typed semantic request → canonical token transaction → derived projection → BWM2 → MIR → worker`

No BASIC source is provided during construction or rendered/reparsed for MIR
execution. Both MIR interpreter and MIR JIT pass the new array tests. The
complete ECS address book is **not** implemented: this cycle has no strings,
comparisons, conditionals, loops, cross-function mutable state, or ID lookup.

## Historical BASIC semantics checked

Reference compiler:

`experiments/basic-aot/results/aot/standalone/diagnostics/pristine-src/build/basic/basicc`

The pinned frontend initializes `array_base` to 0; `OPTION BASE` accepts 0 or
1. `DIM A(n)` computes a dimension length of `n - array_base + 1`, so the
explicit upper bound is inclusive. The historical runtime uses local MIR
storage for a DIM declared inside a function. Repeated calls to a function
that mutates its local array both returned 1 in interpreter and JIT, confirming
fresh local state in those paths.

Focused historical fixtures under `fixtures/` were run in interpreter and JIT:

| Case | Interpreter | JIT | Observed behavior |
|---|---|---|---|
| `DIM VALUES(3)`, values at 0..3 | PASS | PASS | Outputs 11, 33, 44 at indexes 0, 2, 3 |
| Index `1.9` | PASS | PASS | Selects index 1 (truncation toward zero) |
| Index `-0.5` | PASS | PASS | Truncates to index 0 |
| `OPTION BASE 1`, `DIM VALUES(3)` | PASS | PASS | Bounds are 1..3 and inclusive |
| Local mutation across two calls | PASS | PASS | Both calls return 1; local array is reset |
| Duplicate DIM after a write | PASS | PASS | Second declaration resets observed cell to 0 |
| Same spelling as array and function | PASS | PASS | `A(I)` uses DIMmed array in that scope; standalone `A(1)` calls function |
| Same spelling as scalar and array | PASS | PASS | Scalar `A` and element `A(1)` retain distinct values; sum is 12 |
| Out-of-range index 4 | PASS* | PASS* | Stops before the following PRINT; current process status is 0 |

`*` “PASS” here means the reference behavior was captured, not that OOB access
is a successful numeric result. The new worker instead returns the structured
`ARRAY_BOUNDS` error and does not crash. This is an intentional diagnostic
improvement over the historical silent stop.

An edge in the legacy implementation is `DIM A(0)`: its internal helper treats
size 1 as “not dimensioned” and may replace it with a default length of 11.
This workspace does not reproduce that fallback: upper bound 0 means exactly
one element. Duplicate DIM and array/scalar/function collisions are rejected
explicitly by the workspace subset; the legacy frontend accepts or resolves
some such cases through implicit/default behavior. These are deliberate,
documented subset differences, not claims of full dialect equivalence.

## Supported construction and projection

- Local numeric `DIM NAME(integer-literal)` inside numeric `FUNCTION` bodies.
- Lower bound is zero; the literal is an inclusive upper bound.
- Bounds 0..255 (1..256 cells), up to 32 arrays and 4096 total cells per
  function.
- Array declarations, indexed writes, and `array_element` reads can be
  supplied in `create_numeric_function` alongside the result expression.
- Array references in a constructor use transaction-local
  `{"kind":"local_ref","name":"VALUES"}` handles. Existing array symbols
  are addressed by discovered opaque IDs in subsequent edits.
- One-dimensional numeric arrays only. Multidimensional, string, dynamic,
  module-level, and cross-function shared arrays are rejected or outside the
  compilable projection.
- Cells start at numeric zero on each function invocation. Storage is modeled
  as fixed MIR `double` registers, so the worker exposes no pointer or general
  allocation operation to the agent.
- Numeric indexes truncate toward zero, matching tested historical behavior.
  Bounds are checked after that conversion. Non-finite and out-of-range values
  produce `ARRAY_BOUNDS`.
- Reads and writes at a constant index use a direct cell register. Dynamic
  indexes use a generated checked dispatch over the fixed cells.

The canonical token stream remains editable source of truth. Array symbols,
bounds and statement projections are derived indexes. The projection is
immutable and tied to a document revision. A successful edit rebuilds it from
the new revision; stale-revision execution is rejected. Failed transactions
leave the current executable revision untouched.

The BWM transport is now version 2 (`BWM2`) with per-function bounds and
indexed assignment data. The worker retains BWM1 scalar decoding for backwards
compatibility. It validates array limits and cross-function/local references
before MIR lowering; malformed references return `INVALID_PROJECTION`.

## Demonstration

Reproduce the complete in-memory demonstration:

```sh
cd experiments/basic-workspace
scripts/build-mir-worker.sh
python3 numeric_array_demo.py
```

`numeric_array_demo.py` opens empty virtual documents (no source text),
constructs `VALUE_AT(I)` with four cells, and runs both interpreter and JIT:

| Call | Before edit | After changing cell 2 from 33 to 77 |
|---|---:|---:|
| `VALUE_AT(0)` | 11 | 11 |
| `VALUE_AT(2)` | 33 | 77 |
| `VALUE_AT(3)` | 44 | 44 |

Index 4 returns `ARRAY_BOUNDS`. The function, array and unrelated statement
identities survive the edit. The final rendered source is emitted only after
execution. A second function stores entity IDs 101, 205, 900 in `PERSON_ID`
and ages in `PERSON_AGE`; reading physical slot 2 returns age 53, while a
semantic result-expression change reads logical ID 900. This demonstrates
parallel columns and distinguishes entity IDs from slot indexes; it does not
perform lookup by ID.

Machine-readable output is in `demo.json`; the captured terminal output is in
`demo.stdout.json`. Historical interpreter/JIT and downstream rendered-source
oracle results are in `historical-differential.json`.

## Validation

Commands run from `experiments/basic-workspace`:

```sh
scripts/build-mir-worker.sh
python3 -m unittest discover -s tests -v
python3 scripts/validate-numeric-arrays.py
python3 numeric_array_demo.py
PYTHONPATH=. python3 scripts/validate-mir-execution.py
PYTHONPATH=. python3 scripts/validate-program-construction-oracle.py
scripts/validate-dialect.sh
```

Results:

- 64 unit tests passed (the earlier 54-test baseline plus 10 array tests).
- The numeric-array historical differential runner passed 20 checks:
  eight historical fixtures in both modes, structured workspace execution in
  both modes, and rendered-source oracle execution in both modes.
- Existing MIR execution differential: four fixtures pass in interpreter and
  JIT.
- Program-construction historical interpreter/JIT oracle: pass.
- Existing dialect before/after checks: interpreter and JIT both match.
- The `demo_client.py` and program-construction demos ran without error.
- No BASIC source rendering/reparse occurs in the new execution path.

Targeted ASan/UBSan validation used Clang 23.1.4, the pinned MIR static
library, `-fsanitize=address,undefined -fno-omit-frame-pointer`,
`ASAN_OPTIONS=detect_leaks=1`, and `UBSAN_OPTIONS=halt_on_error=1`. All 10 array
tests passed with the instrumented worker. This validates these exercised
paths only; it is not a general worker sandbox or proof of memory safety for
all malformed inputs.

The array test suite also includes malformed BWM2 array bounds and an invalid
cross-function call target. Both are rejected before MIR lowering; scalar
BWM1 decoding remains covered.

## Performance and memory

`scripts/benchmark-numeric-arrays.py` ran one warmup and 30 fresh-worker
processes per capacity and engine. Each function reads one dynamic index; the
array cells are zero-initialized. Reported process-inclusive time includes
worker startup. Projection and serialization are Python-side; MIR build/link
and invocation fields come from the worker. There is no persistent cache.

| Capacity | BWM2 bytes | Projection median (ms) | Interpreter worker median (ms) | JIT worker median (ms) | Max worker RSS (KiB) |
|---:|---:|---:|---:|---:|---:|
| Scalar baseline | 69 | 0.031 | 0.665 | 0.602 | 17,876 |
| 1 | 78 | 0.036–0.040 | 0.462 | 0.701 | 18,068 |
| 4 | 78 | 0.037 | 0.499 | 0.736 | 18,068 |
| 16 | 78 | 0.039–0.048 | 0.533 | 0.960 | 18,068 |
| 64 | 78 | 0.037–0.045 | 0.638 | 2.166 | 18,260 |
| 256 | 78 | 0.048–0.071 | 1.259 | 12.178 | 18,260 |

The serialized size stays nearly fixed because array declarations carry bounds,
not one payload record per cell. Worker resident memory increased by less than
0.4 MiB across this range at the process RSS granularity observed. MIR has one
register per cell and dynamic reads/writes are lowered as a dispatch across
the cells. Consequently JIT linking time rises sharply: at capacity 256 its
median `mir_link` was about 9.87 ms, versus 0.095 ms for the scalar case. The
interpreter also pays a linear dispatch cost, but remained near 1.26 ms
process-inclusive. This is the clear implementation limit; it is not evidence
that native array loads themselves are slow. Constant-index fixtures avoid
dynamic dispatch.

Full distributions and phase medians are in `benchmark.json`. Timing variation
at sub-millisecond scales is material; these are characterization results,
not performance claims about bare MIR calls.

## Limitations and next step

This establishes the first reusable ECS substrate: local fixed numeric arrays,
typed indexing, per-invocation initialization, bounds diagnostics, semantic
identity, and revision-safe recompilation. It does not yet support strings,
conditions, loops, lookup, shared state, or relationships. The next smallest
step toward the address-book scenario is controlled comparison and conditional
execution, followed by a bounded loop for ID lookup; string arrays and
continued-agent tasks should wait until those semantics have historical and
MIR differential coverage.

Dynamic access currently expands into per-element MIR dispatch and makes large
JIT arrays expensive. Before raising the capacity limit, evaluate a bounded
worker-local memory representation with explicit size and bounds checks, or
retain a conservative capacity limit. Do not expose raw addresses to the
semantic API.
