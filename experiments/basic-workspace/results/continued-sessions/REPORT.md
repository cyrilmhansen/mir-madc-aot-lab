# BASIC Workspace — Cycle 6: atomic construction and continued ECS sessions

## Result summary

Atomic numeric function construction is implemented and validated. A request
can create a complete function, resolve transaction-local parameter/local
handles, construct ordered local assignments, and commit the body in one
revision. Successful calls return stable symbol and statement identities; any
invalid handle, name collision, unsupported expression, or projection error
leaves the document unchanged.

The complete ECS address-book session is **not implemented or claimed**. The
current MIR projection and worker remain numeric-only. The historical BASIC
frontend contains array, string, condition, and loop implementations, but
reusing them requires a larger stateful projection/worker design than can be
validated by merely adding declarations to the token index. The evidence and
minimum semantics are in [`FEASIBILITY.md`](FEASIBILITY.md). Per the scope
fallback, this cycle prioritizes the independently tested atomic constructor
and preserves an explicit stop line for data execution.

## P0 reconnaissance

The historical compiler supports `DIM` for numeric arrays and `$`-suffixed
string arrays; `OPTION BASE` accepts 0 or 1 and defaults to 0. A declared upper
bound is inclusive. Indexed access converts the BASIC numeric index to an
integer, adjusts it by the active base, and branches to the BASIC `STOP` helper
when it is outside allocated storage. `IF` tests numeric nonzero, and
`FOR`/`NEXT` supports an optional step (default 1) and inclusive loop end.
String arrays contain pointers and use the historical runtime pool. These
details are source-inspected semantics and still require focused historical
interpreter/JIT fixtures before they can be copied into a separate worker.

The Workspace MIR path currently supports numeric parameters/locals, simple
assignments, `+ - * /`, parentheses, numeric function calls, and MIR interpreter
or JIT execution. It has no arrays, string values, indexed expressions,
comparisons, conditionals, loops, or shared mutable module data. In the
historical compiler, array storage is represented by function registers; this
does not establish safe shared-array behavior across BASIC functions.

The proposed ECS data model is explicitly structure-of-arrays:

- `PERSON_ID[]`, `PERSON_NAME$[]`, `PERSON_AGE[]`, and later `PERSON_CITY$[]`;
- distinct professional-component IDs and their parallel columns;
- `PROF_PERSON_ID[]` stores logical Person entity IDs, never physical array
  positions;
- lookup resolves an entity ID to a physical slot, and relationship creation
  rejects unknown entity IDs.

The program's canonical tokens describe declarations, code and deterministic
initialization. A fresh MIR worker owns a separate execution instance of those
arrays. It must not call Python address-book code or hide state in a database.
Cross-function array sharing, string ownership and cleanup need explicit
projection and BWM transport semantics before the whole app is executable.

## Atomic function constructor

The agent-facing `workspace_create_function` schema now requires a typed result
expression and accepts an optional ordered `locals` array. Within constructor
bodies, `{"kind":"local_ref","name":"X"}` names a parameter or earlier local
without requiring a not-yet-created persistent ID. Calls to existing functions
still use discovered function IDs. The operation reuses the existing clone →
mutate → index → validate → projection-check → commit transaction path. No
secondary AST is retained.

The host creates an empty document before the first semantic model turn and
provides revision 1; the model's tool set no longer exposes an empty-document
creation call. This removes the observed stale-revision attempt to create a
function before opening a document.

Atomic constructor tests cover `DOUBLE(X)=X*2`, a `COMBINE(A,B)` function with a
transaction-local `PRODUCT=A*B`, interpreter/JIT agreement, stable returned
IDs, and rollback when a handle is unknown. The older zero-result API remains
available for compatibility.

The semantic numeric demo still constructs `DOUBLE`, then `CALCULATE` calling
it, edits `DOUBLE` to multiply by three, and renames it to `TRIPLE`. Both MIR
engines return 18, 21, 30, and 30. The reproducible trace and rendered final
program are in [`demo-cycle6.json`](demo-cycle6.json) and
[`constructed-cycle6.bas`](constructed-cycle6.bas). In the recorded local
demo run, atomic construction reduced the workflow from 18 to 14 workspace
RPCs; request bytes fell from 4,185 to 3,295 and response bytes from 8,229 to
6,731. Those are host/tool transport measurements, not model token savings.
They reflect two created functions and are single-run values. A later rerun
measured 38.15 ms workspace RPC wall time; request/response byte totals can
vary slightly because opaque IDs and timing metadata have different lengths.

## Real-model pilot and accounting

The previous fair Qwen `DOUBLE(9)` pilot succeeded in both arms, before atomic
construction: semantic 7 turns / 7 tool calls, 15,843 prompt and 880 completion
tokens; text 6 turns / 7 calls, 7,691 prompt and 505 completion tokens. Prefix
cache reported 12,318 and 5,971 prompt tokens respectively. This is the
non-atomic baseline pilot from `results/program-construction/`.

The atomic pilot used the same operator-configured Sushi endpoint/model,
temperature 0, seed 19, 1,024 maximum output tokens per turn, 12 iterations,
20 tool calls, and a 180-second request timeout. The host-created empty
workspace was revision 1. Before any model response, the semantic tool request
timed out. The text arm therefore did not run. No provider token usage or
execution result was returned, and this is **not** a correctness comparison.
The reconstructed prompt and request dimensions are preserved in
[`atomic-pilot/failed-attempt.json`](atomic-pilot/failed-attempt.json), along
with the tool schemas in `atomic-pilot/tool-definitions.json`:

| Atomic pilot request | Size |
|---|---:|
| Semantic tool schema bundle | 6,216 bytes |
| Compact serialized messages + tools | 7,650 bytes |
| Full JSON request body | 8,258 bytes |
| Response body / provider tokens | 0 bytes / unavailable |

The full request was only about 8.3 KB and below the local 64,000-byte cap;
the model server advertises 220,000 tokens. The 180-second timeout therefore
does not establish a context-size failure. It leaves the atomic model pilot
inconclusive. The semantic schema grew from 4,735 to 6,216 bytes (about 31%)
because the constructor schema describes transaction-local bodies and locals.
The extra schema cost must be weighed against fewer request/response turns in
a completed agent session. No atomic token reduction is claimed until a model
response is available.

The runner now records endpoint timeouts as failed model attempts with request
and response byte counts instead of terminating without a result row. A
deterministic unit test covers that error path. We did not repeat the timed-out
real-model request solely to produce a cleaner measurement.

## Continued-session result

The requested three phases—people directory, added attribute, then a linked
professional component—were not run because the current worker cannot execute
the required arrays, strings, comparisons, loops, and shared instance data.
Scoring that as an agent failure would conflate tool quality with missing
compiler capability. The previous four paired elementary tasks remain
archival, interrupted data; they are not counted as continued-session evidence.

For the next ECS implementation, keep the authoring surface general: typed
array declaration, indexed read/write, comparison, and bounded control-flow
blocks, with discovered collection/statement identities. A domain layer may
offer `add-component`, `add-entity`, and `link-entities`, but it must lower
deterministically into the same canonical BASIC tokens. Before adding these
features, establish string ownership and execution-instance lifetime, array
bounds/initialization behavior, bounded loop semantics, and a way for several
functions to share the same array state. The complete language subset and
historical evidence required are detailed in `FEASIBILITY.md`.

For a resumed multi-stage model session, each phase boundary should provide a
compact resume record with document revision, discovered IDs, current
structure, invariants, last execution result, next objective, and unsupported
constructs. The receiving agent must query the live revision and structure
before acting; the summary is context, never authority. The text arm should
receive the equivalent buffer version, source outline, diff, and validation
result. No such full session was run in this cycle.

## Validation

Commands:

```sh
PYTHONPATH=experiments/basic-workspace python3 -m unittest discover \
  -s experiments/basic-workspace/tests -v
PYTHONPATH=experiments/basic-workspace python3 \
  experiments/basic-workspace/experiment/llm_runner.py --fixture-test
PYTHONPATH=experiments/basic-workspace python3 \
  experiments/basic-workspace/program_construction_demo.py \
  --output experiments/basic-workspace/results/continued-sessions/constructed-cycle6.bas \
  --json experiments/basic-workspace/results/continued-sessions/demo-cycle6.json
PYTHONPATH=experiments/basic-workspace python3 \
  experiments/basic-workspace/experiment/program_construction_trials.py \
  --endpoint-url "$MODEL_ENDPOINT" --model "$MODEL_NAME" --limit 1 \
  --output-dir experiments/basic-workspace/results/continued-sessions/atomic-pilot

# The real endpoint attempt above timed out. The retained atomic-pilot record
# has the exact trial options and reconstructed request sizes. Do not count it
# as a model result.
PYTHONPATH=experiments/basic-workspace python3 \
  experiments/basic-workspace/experiment/llm_runner.py --fixture-test
```

Result: **54 tests pass**, including all 51 prior tests plus constructor and
timeout-trace coverage. The offline protocol fixture passes. The in-memory
numeric demo and both MIR engines pass. The continued ECS phases remain
explicitly untested/unsupported.

## Decisions and next step

1. Atomic construction is a justified improvement to the numeric authoring
   API, but its real-model token savings remain unmeasured due to timeout.
2. Stable numeric function/parameter/local/statement identities are returned
   and preserved through tested edits. ECS entity identity versus array slot
   behavior is specified but not implemented.
3. The smallest honest next executable slice is fixed-capacity arrays with
   initialized execution-instance state and bounds failures, followed by
   string arrays and lookup control flow. Start with a single function if
   possible; do not claim shared state until multiple-function tests prove it.
4. The ECS address book is a better next vertical slice than graphics: it can
   reuse established BASIC array/string constructs, while the existing
   historical graphics frontend has no `ELLIPSE` token/primitive and the
   Workspace worker currently lacks effectful execution. Graphics should wait
   until the data/control-flow worker path is safe.

The atomic constructor and this feasibility/report work are local experiment
changes only. No BASIC compiler, MIR, MADC, AOT corpus, or Atlas executor was
modified.
