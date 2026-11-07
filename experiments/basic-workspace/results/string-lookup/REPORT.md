# Cycle 9 — Typed strings and entity-name lookup

## Result

The Workspace can construct a string-returning `PERSON_NAME$` function from an
empty in-memory document, lower it directly to MIR, and execute it with both
the MIR interpreter and JIT. No BASIC text is supplied to the constructor, and
execution does not render or re-lex BASIC. The function searches numeric IDs
and reads the matching value from a parallel local string array.

| ID | MIR interpreter | MIR JIT |
|---:|---|---|
| 101 | Alice | Alice |
| 205 | Bob | Bob |
| 900 | Chloé | Chloé |
| 999 | empty | empty |
| 2 | empty | empty |

After a semantic transaction changed the string array assignment `"Bob"` to
`"Robert"`, both engines returned Robert for ID 205. The function, both arrays
and all pre-existing statement identities remained stable. The transaction
advanced revision 2 to revision 3. A stale execution request and a numeric
value assignment into the string array were rejected; the latter left the
revision and executable result unchanged.

The checked-in trace is
[`structured-construction-trace.json`](structured-construction-trace.json).
It also records the final optional rendering, done after all execution and
editing. The BASIC rendering uses `PERSON_NAMES$` for the array because the
current Workspace index does not allow a local array to shadow the module
function name `PERSON_NAME$`.

## String contract and representation ownership

The contract was written before implementation in
[`STRING_CONTRACT.md`](STRING_CONTRACT.md). In brief:

- Values are valid UTF-8. Embedded NUL and physical line breaks in source
  literals are rejected. String comparison and normalization are not
  implemented.
- Literals are at most 4096 bytes; the serialized literals for one worker
  call are capped at 256 KiB. One-dimensional local arrays have the same
  zero-based inclusive bound and capacity rules as numeric arrays.
- Uninitialized string locals and cells contain the empty string. Each
  invocation owns its literal bytes; variables and cells hold references to
  immutable strings. Assignment replaces a reference and never frees a value.
- The result is validated and copied/escaped into a JSON response while the
  execution context is alive. JSON-RPC returns an ordinary string and byte
  length, never a native address. The receiving Python string is independent
  of worker cleanup.
- String arguments, concatenation, builtins, mutable buffers, string function
  calls inside other functions, cross-function arrays and module-persistent
  strings are outside this cycle.

Canonical tokens remain the editable source of truth. `$` suffixes, DIM
element types, expression types, and bindings are derived on projection build.
The worker invocation owns runtime values; it does not retain or edit program
structure.

The pinned MIR implementation does not permit `MIR_T_P` function registers
(`MIR_reg_type_p` excludes pointer registers). On this native x86-64 worker,
string references therefore travel in I64 MIR registers; pointer loads and
stores use `MIR_T_P` memory operands, and the function ABI declares a pointer
result. This x86-64 representation passed interpreter and generated-code
tests. It is an explicit host-specific constraint, not a portable pointer
lowering claim.

## Construction and semantic edit

Reproduce the vertical demonstration:

```sh
cd experiments/basic-workspace
./scripts/build-mir-worker.sh
python3 scripts/demo-string-lookup.py
```

The demo creates an empty document, calls `create_string_function` with
numeric parameter `WANTED`, declarations `PERSON_ID` and `PERSON_NAMES$`,
typed literal/numeric array assignments and nested typed FOR/IF statements.
It executes both engines, discovers the assignment whose expression is
`"Bob"`, and commits `edit_assignment_expression` as revision 3. No BASIC
source is passed to `open_document_from_string`, and no text is used as an
editing instruction. The same constructor is available through the JSON-RPC
client and `create_string_function` method.

The projection distinguishes string and numeric arrays and function results.
Expression requests accept `{"kind":"string","value":"…"}`; references
remain identity-bound, including constructor-local handles. Type checking
rejects numeric/string assignment mismatches before a transaction commits.
The native worker validates BWM4 lengths, type tags, NUL, UTF-8, bounds and
aggregate limits before lowering. Numeric expressions and function calls
remain the previous numeric subset.

## Historical compiler observations

The pinned historical compiler was run from
`experiments/basic-aot/results/aot/standalone/diagnostics/pristine-src/build/basic/basicc`.
The small top-level fixture in `historical/string-arrays.bas` prints Alice and
Chloé identically in interpreter and JIT; those modes confirm ordinary string
DIM storage and literal assignment at top level.

Function-path observations were recorded separately and are not counted as
successful differential checks:

- `historical/function-string-no-if.bas`: the interpreter exits 0 but emits
  the corrupted bytes `@n*$LV`; the JIT segfaults (139). This isolates a
  historical function string return/array defect even without IF.
- `historical/function-if-lookup.bas`: interpreter and JIT both segfault
  (139). This overlaps the already known historical FUNCTION/IF defect from
  Cycle 8 and does not validate or invalidate the Workspace implementation.

Workspace values are compared against explicit expected outputs and against
each other. No historical function mismatch is claimed as a pass, and the
historical compiler was not modified.

## Validation and memory safety

The full Workspace unit suite passes: **81 tests** (the previous 71 plus 10
string lookup tests). The string-specific tests cover UTF-8 (`Chloé`), quote
escaping, empty results, locals, string arrays, zero initialization, dynamic
bounds, type mismatch rollback, semantic replacement, stale revisions,
identity preservation, JSON-RPC construction, and execution without render or
re-lex. A malformed BWM4 string length is rejected as `INVALID_PROJECTION`.
Existing BWM1/BWM2/BWM3 and numeric regressions remain covered by the earlier
tests, all of which pass in the full 81-test run.

The 10 string tests also pass with the worker compiled by Clang using
`-fsanitize=address,undefined`, with `ASAN_OPTIONS=detect_leaks=1:halt_on_error=1`
and `UBSAN_OPTIONS=halt_on_error=1`. LeakSanitizer reported no leaks. The
sanitizer binary was created in a `TemporaryDirectory` under
`native/build/` and removed automatically. This is targeted worker testing,
not a claim that the worker is a comprehensive sandbox. Malformed transport
validation is deterministic; no broad fuzz campaign was run.

Commands:

```sh
cd experiments/basic-workspace
./scripts/build-mir-worker.sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/demo-string-lookup.py
```

## Performance

`benchmark.json` contains 30 fresh-worker calls per engine and table size; the
test selects the final row, so results include a bounded loop and dynamic
numeric/string array reads. These are measurements of the whole path, not a
comparison to an optimized C database implementation.

| Rows | Engine | Projection median (ms) | Encoding (ms) | Worker end-to-end (ms) | MIR build (ms) | MIR link (ms) | Invocation (ms) | Result copy + JSON escape (ms) | Payload (bytes) | Peak RSS (KiB) |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | Interpreter | 0.170 | 0.039 | 0.712 | 0.085 | 0.042 | 0.009 | 0.0006 | 359 | 18,276 |
| 3 | JIT | 0.147 | 0.032 | 1.107 | 0.083 | 0.513 | 0.000 | 0.0006 | 359 | 18,276 |
| 16 | Interpreter | 0.344 | 0.061 | 0.713 | 0.098 | 0.101 | 0.018 | 0.0007 | 1,093 | 18,276 |
| 16 | JIT | 0.338 | 0.062 | 1.613 | 0.098 | 0.916 | 0.000 | 0.0007 | 1,093 | 18,276 |
| 64 | Interpreter | 1.036 | 0.161 | 1.205 | 0.160 | 0.320 | 0.055 | 0.0008 | 3,829 | 18,852 |
| 64 | JIT | 1.070 | 0.166 | 3.672 | 0.171 | 2.591 | 0.001 | 0.0008 | 3,829 | 19,044 |

The worker process is fresh for each sample; worker time includes MIR build,
link, execution, result extraction and process overhead. The `result_copy_json`
field times length validation and escaped response-buffer creation; pipe write
and Python JSON decoding remain within wall/worker end-to-end time. JIT link
cost dominates at 64 rows, consistent with the previous observation that MIR
linking is the expensive stage. RSS is process peak RSS, including MIR/runtime
overhead, not just string payload storage.

Reproduce with:

```sh
python3 scripts/benchmark-string-lookup.py
```

## Limits and next steps

This is an executable name-lookup slice, not a complete address book or ECS.
There is no string equality, selector for multiple attributes, cross-function
shared array state, string parameter ABI, concatenation, Unicode
normalization, or persistent runtime. The historical function path is
currently unreliable, which prevents a meaningful interpreter/JIT historical
differential for function-local strings. A next safe extension should add a
typed bytewise string equality operator and focused tests before adding city
columns or general string operations. Keep the per-invocation ownership model
until cross-function state has an explicit lifetime design.

No LLM pilot was run; deterministic correctness and historical compatibility
triage were prioritized. No BASIC, MIR or MADC source was changed. No push was
performed.
