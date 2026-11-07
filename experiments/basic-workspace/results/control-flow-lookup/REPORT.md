# Cycle 8 — bounded control flow and entity-ID lookup

Baseline: laboratory commit `eda1090412b99b8a64cd0bf927196fbc11169d9f`,
branch `experiment/mir-aot-correctness-cycle3`. The implementation is confined
to `experiments/basic-workspace/`; the historical compiler, MIR and MADC
sources were not modified. The working host is native Linux x86-64.

## Result

The Workspace constructs `AGE_BY_ID` in an empty virtual document using typed
array declarations, array assignments, a bounded `FOR`, a numeric equality
comparison and a nested `IF`. The execution path remains canonical tokens →
revision-bound projection → BWM3 → MIR. It does not render or reparse BASIC.

Both MIR engines returned the required values:

| Logical ID | Interpreter | JIT |
|---:|---:|---:|
| 101 | 25 | 25 |
| 205 | 42 | 42 |
| 900 | 53 | 53 |
| 999 | -1 | -1 |
| 2 | -1 | -1 |

The last row confirms that stored entity IDs are data values, not array
positions. A semantic update changed the age for 205 to 47 at revision 3.
Both engines then returned 47 for 205 and retained 25 for 101. Function,
array and assignment identities remained stable. A failed zero-step loop
construction left revision 3 and its executable result unchanged; execution
against stale revision 2 returns `STALE_REVISION`. The trace, including the
typed construction request, update statement ID, results and optional final
rendering, is in `construction-trace.json`.

## Verified and restricted semantics

The pinned historical compiler used for comparison is the pristine BASIC
compiler in the AOT diagnostics tree. Fixtures and captured results are in
`fixtures/` and `historical-differential.json`.

| Construct | Historical interpreter/JIT observation | Workspace subset |
|---|---|---|
| `=`, `<>`, `<`, `<=`, `>`, `>=` | True prints as 1; false as 0 | Same, comparison expression returns double 1/0 |
| Top-level `IF 0` / `IF -2` | Zero is false; nonzero is true | Same nonzero truth test |
| Positive `FOR` | Inclusive end; 0..4 step 2 sums to 6 | Same |
| Empty range | 5..2 executes zero times | Same |
| Negative step | 3..-1 step -2 visits 3, 1, -1; sum 3 | Same |
| Loop bound changed in body | Historical compiler re-evaluates `TO` expression | Workspace rejects dynamic bounds; only finite constants |
| `IF` in a `FUNCTION` | **Pinned compiler defect:** `IF X=1 ... ELSE ...` returns 20 for both X=1 and X=2 in both interpreter and JIT | Workspace emits the expected conditional branches and returns the correct branch result |

The conditional-function mismatch is not hidden as a successful differential.
The rendered `AGE_BY_ID` program produces 53 for every ID when run through the
historical interpreter and JIT, while direct Workspace/MIR execution produces
the table above. A minimal historical reproduction is
`fixtures/if-function-result.bas`; it prints `ONE=20` and `TWO=20` in both
modes. The same source’s top-level conditional behaves normally. This points
to a limitation/bug in the historical function code path, not a discrepancy
between the Workspace MIR interpreter and JIT. No upstream compiler changes
were made.

Workspace loops are lexical, single-variable, fixed-bound blocks. Start, end
and step must be finite constants, step cannot be zero, inclusive static trip
count cannot exceed 10,000, and nesting depth is at most 16. Negative steps
are supported. Limits are not re-evaluated, matching the intentionally fixed
subset rather than the historical dynamic-bound behavior. GOTO/FOR
interactions, loop exits and irregular `NEXT` behavior are unsupported. IF
conditions accept numeric expressions and treat any nonzero result as true.

## Worker format, control flow and safety

Control structures and comparisons use BWM3; BWM1 scalar and BWM2 array
decoding remain supported. The parser checks statement count, nesting, local
slots, array slots, call arity, finite constants, static FOR bounds, and
trailing bytes before MIR lowering. IF and FOR become MIR labels and branches;
FOR has a genuine back-edge and a worker-side iteration counter. Exceeding the
counter produces `LOOP_LIMIT`, distinct from the outer process timeout and
`ARRAY_BOUNDS`.

Array indices retain the historical truncation-to-integer rule. The worker
checks the floating range, converts the index, then checks the integer range
before forming an address. That second check is required for exactly -1.0:
the floating check permits fractions such as -0.5 that truncate to zero, but
-1.0 truncates to -1 and must not address memory before the array.

The default array lowering now uses bounded per-function stack storage through
MIR `ALLOCA`, MIR double loads/stores and an indexed memory operand. Arrays
are zeroed for each function invocation, remain local to that invocation, and
cannot escape through this subset. Capacity remains capped at 256 per array and
4,096 total elements per function. `BASIC_WORKSPACE_MEMORY_ARRAYS=0` selects
the prior per-cell register/dispatch path for A/B comparisons. This worker is
not a general sandbox; untrusted native code and arbitrary imports remain
outside the interface.

## Array-lowering measurements

`scripts/benchmark-array-lowering.py` ran one warmup and 30 fresh workers per
capacity, engine and strategy. Each function zero-initializes a local array,
reads one dynamic index, and returns that value. These are process-inclusive
medians; the MIR timing fields isolate build, link and invocation. Results are
in `array-lowering-benchmark.json`.

| Capacity | Engine | Register dispatch: process / MIR link | Stack memory: process / MIR link | Change |
|---:|---|---:|---:|---:|
| 1 | JIT | 0.720 / 0.193 ms | 0.710 / 0.213 ms | noise-level |
| 4 | JIT | 0.755 / 0.247 ms | 0.765 / 0.240 ms | noise-level |
| 16 | JIT | 0.992 / 0.434 ms | 0.886 / 0.329 ms | 19% lower process time |
| 64 | JIT | 2.276 / 1.526 ms | 1.289 / 0.684 ms | 43% lower process time |
| 256 | JIT | 12.755 / 10.318 ms | 3.311 / 2.562 ms | 74% lower process time |
| 256 | Interpreter | 1.238 / 0.375 ms | 1.441 / 0.663 ms | 16% higher process time |

The memory representation materially reduces JIT link expansion at larger
capacities. Interpreter execution is modestly slower in the simple one-read
case at capacity 256 because it pays address and memory-operation overhead;
the default is chosen for the much better JIT scaling, while the dispatch mode
remains available for characterization. RSS varied by about 0.2 MiB and did
not show a meaningful strategy-specific increase at these sizes.

`scripts/benchmark-control-flow-lookup.py` also ran 30 fresh workers per
engine and strategy for a two-array linear lookup. Results are in
`benchmark.json`:

| Entries | Engine | Dispatch process / link | Stack memory process / link |
|---:|---|---:|---:|
| 3 | JIT | 1.107 / 0.542 ms | 1.133 / 0.542 ms |
| 16 | JIT | 2.786 / 2.049 ms | 1.364 / 0.766 ms |
| 64 | JIT | 23.199 / 21.171 ms | 2.272 / 1.619 ms |
| 64 | Interpreter | 0.847 / 0.165 ms | 0.937 / 0.267 ms |

At 64 entries, the stack-memory lookup reduces JIT linking by about 92% and
process-inclusive time by about 90%. Interpreter time is within 0.1 ms in this
sample. Transport
was 344 bytes in all three lookup sizes because the loop is represented once,
not unrolled. Constructor commit took 2.1–3.0 ms across these sizes. The
constructor currently emits canonical tokens and reindexes after each
generated line to verify bindings; this is convenient and safe for the small
blocks here, though repeated whole-document indexing is a scaling cost worth
revisiting before larger generated programs.

## Validation

Commands run from the repository root:

```sh
experiments/basic-workspace/scripts/build-mir-worker.sh
python3 -m unittest discover -s experiments/basic-workspace/tests -q
BASIC_WORKSPACE_MEMORY_ARRAYS=0 python3 -m unittest discover -s experiments/basic-workspace/tests -q
PYTHONPATH=experiments/basic-workspace python3 experiments/basic-workspace/control_flow_lookup_demo.py
PYTHONPATH=experiments/basic-workspace python3 experiments/basic-workspace/scripts/validate-control-flow-lookup.py
PYTHONPATH=experiments/basic-workspace python3 experiments/basic-workspace/scripts/fuzz-control-flow-input.py
PYTHONPATH=experiments/basic-workspace python3 experiments/basic-workspace/scripts/benchmark-array-lowering.py
PYTHONPATH=experiments/basic-workspace python3 experiments/basic-workspace/scripts/benchmark-control-flow-lookup.py
```

Both lowering strategies passed all 71 Workspace unit tests. Historical
validation passed the six comparison/top-level-IF/FOR fixtures in both
interpreter and JIT (12 runs). The additional function-IF fixture captured
the same known legacy behavior in both modes (2 records), and the rendered
lookup differed in both modes as described above (2 records). Previous
validation also passed: dialect before/after in interpreter and JIT, four MIR
execution fixtures in both engines, 20 numeric-array differential checks, and
the program-construction historical oracle.

Targeted Clang 23.1.4 ASan/UBSan with LeakSanitizer ran the seven
control-flow tests and ten numeric-array tests against each lowering strategy
(34 test executions total), with leak detection enabled; all passed. The
worker also rejected 100 seeded malformed byte payloads with a structured
JSON response and no abnormal exit; reproduce that smoke-fuzz with
`PYTHONPATH=experiments/basic-workspace python3 experiments/basic-workspace/scripts/fuzz-control-flow-input.py`.
These checks cover only the exercised
paths, not every malformed input or a general security boundary.

## Reproduction and scope

Build and run the lookup:

```sh
experiments/basic-workspace/scripts/build-mir-worker.sh
PYTHONPATH=experiments/basic-workspace python3 experiments/basic-workspace/control_flow_lookup_demo.py
```

Capture historical observations and downstream rendered-source comparison:

```sh
PYTHONPATH=experiments/basic-workspace python3 experiments/basic-workspace/scripts/validate-control-flow-lookup.py
```

Run 30-sample benchmarks:

```sh
PYTHONPATH=experiments/basic-workspace python3 experiments/basic-workspace/scripts/benchmark-array-lowering.py
PYTHONPATH=experiments/basic-workspace python3 experiments/basic-workspace/scripts/benchmark-control-flow-lookup.py
```

The output render is used only as an optional historical-compiler oracle. The
new execution path itself does not call `render_document` or re-lex BASIC.
This cycle implements no strings, cross-function shared data, general ECS,
dynamic loop bounds, file I/O, graphics or Atlas integration. No real-model
pilot was run; deterministic correctness and the historical frontend
discrepancy were the priority.
