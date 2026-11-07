# Continued ECS sessions — feasibility before implementation

## Repository and boundary

The workspace branch starts at `ad397e9c15af7920fad0f882140e4267c5dce94f`.
The authoritative representation remains the lossless canonical token stream;
semantic indexes and the immutable numeric projection are derived from it.
The existing native worker receives a versioned BWM1 transport value, builds
MIR in process memory, then runs either the MIR interpreter or JIT in a fresh
worker process. It currently accepts only numeric functions, parameters,
simple assignments, arithmetic, and calls between numeric functions.

## Smallest coherent ECS language slice

An address book represented as structure-of-arrays needs these BASIC
constructs:

1. Fixed-capacity `DIM` arrays, numeric first and string-valued columns next.
2. Indexed reads and writes with defined initialization and bounds behavior.
3. Numeric and string equality (and numeric ordering for lookup/control).
4. `IF` and a bounded `FOR`/`NEXT` or equivalent structured loop for lookup.
5. A way to preserve state while multiple operations/functions inspect the same
   data instance.

The historical frontend contains parsing and MIR generation paths for `DIM`,
`IF`, `FOR`/`NEXT`, numeric and `$`-suffixed arrays, numeric comparisons, and
string comparisons. Its `array_base` defaults to 0; `OPTION BASE` accepts 0 or
1. `DIM A(n)` treats `n` as the inclusive upper bound and allocates
`n - array_base + 1` slots. Index expressions are converted from BASIC numeric
values to integer indices, adjusted by `array_base`, then checked against the
allocated slot count. An out-of-range branch calls the BASIC `STOP` helper.
`IF` takes its then-branch when the numeric condition is nonzero. `FOR` defaults
to step 1 and uses an inclusive end test, with a separate comparison path for
negative steps. These semantics are visible in the historical compiler and
must still be covered by small differential fixtures before adoption.

String arrays are arrays of pointers. The historical runtime allocates array
storage through `basic_dim_alloc`; string assignment retains allocated strings
in its pool rather than freeing replaced values. This is unsuitable as an
implicit ownership rule for a new independently initialized execution
instance. The Workspace subset must instead define one explicit policy for
literal and assigned strings, comparison encoding, array initialization, and
cleanup. The initial ECS fixture can avoid replacement-heavy strings, but it
cannot claim general string-array memory safety without that policy.

## Program shape and ECS mapping

The data uses stable logical IDs distinct from array indexes:

- `PERSON_ID(index)`, `PERSON_NAME$(index)`, `PERSON_AGE(index)`, and later
  `PERSON_CITY$(index)` are parallel Person-component columns.
- A separate professional ID and its component columns form the Professional
  component.
- `PROF_PERSON_ID(professional_index)` stores a Person entity ID, never a
  physical Person index.
- A lookup scans the Person IDs to resolve an entity ID to a physical slot;
  professional-to-person lookup resolves the stored ID through the same path.

Adding `PERSON_CITY$` adds a column and its initialization, without renumbering
existing Person IDs. Linking a Professional validates that the referenced
Person ID exists. Deterministic tests should distinguish a valid ID from a
coincidentally valid array position and test a dangling link rejection.

## Program structure versus runtime data

The canonical BASIC tokens describe declarations, lookup code, and literal
initialization. An execution instance owns its initialized array values. A
fresh worker invocation must initialize that instance deterministically; no
hidden Python database, filesystem state, or shared process-global data may
stand in for BASIC execution. If multiple BASIC functions need the same array
instance, the projection and BWM transport must represent that shared data
explicitly. The historical generator's array registers are function-local, so
cross-function shared-array behavior is not assumed from `DIM` support alone.

For a first vertical slice, keep the address-book logic within one numeric
function if that permits a deterministic test result, or add explicit module
data only after its lifetime and cross-function semantics are specified. Do
not call a Python lookup routine from the MIR worker and describe it as BASIC
execution.

## Structured authoring operations

The minimum authoring operations should map to general BASIC constructs, not
to a hidden address-book implementation:

- Declare an array with a numeric or string element type and fixed capacity.
- Construct typed indexed expressions and indexed assignment targets.
- Construct comparisons and bounded conditional/loop blocks.
- Add or replace a statement block atomically.
- Discover array declarations, statement identities, and bound references.

Transaction-local names may refer to declarations made earlier in the same
transaction; successful commit returns persistent symbol and statement IDs.
The resulting canonical tokens must pass the same index rebuild and MIR
projection validation as other edits. The domain-specific ECS layer may
generate these operations, but it cannot keep an independently editable copy
of entity/component state.

## MIR and runtime requirements

The numeric worker already emits MIR for double arithmetic and function calls.
The array/control-flow slice additionally needs integer index conversion,
scaled pointer arithmetic, loads/stores, bounds branches, labels, numeric
comparisons and loop control. String values require pointer-valued MIR
registers, string constants with safe lifetime, pointer array loads/stores,
and a well-defined comparison primitive. Array instance initialization and
ownership/cleanup must be explicit in the BWM protocol or generated MIR.
Required helpers must be small, bounded, deterministic worker primitives;
arbitrary native imports remain prohibited.

## Explicitly unsupported unless separately demonstrated

- Dynamic/resizable collections or unbounded input.
- File I/O, network, process creation, and arbitrary native imports.
- General multi-dimensional arrays.
- String mutation, Unicode normalization, and embedded-NUL strings.
- Cross-function mutable array sharing until its projection/lifetime is
  explicitly implemented and tested.
- Unbounded loops; execution must enforce a deterministic step/instruction
  limit or accept only statically bounded loops.
- Full BASIC compatibility.

This reconnaissance does not establish that the complete ECS scenario fits
the cycle. The first implementation priority is the independently useful
atomic numeric function constructor. The ECS subset will proceed only if its
typed array and execution semantics can be completed and tested coherently;
otherwise the report will stop at the validated constructor and precise
language boundary.
