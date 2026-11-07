# BASIC Workspace — Program construction and continued-session study

## Status

The numeric construction slice is implemented and validated. An empty in-memory
document can be populated with numeric functions, edited through typed semantic
operations, lowered to the existing MIR worker, and run in both the MIR
interpreter and JIT without rendering BASIC source. The agent study has been
redirected from independent elementary tasks to continued sessions with an
explicit resume before each substantial change. The two proposed target
programs (graphics animation and a related address-book model) are not yet
supported by the current numeric-only execution projection; they are design
targets, not results of this cycle.

## Architecture and what the agent sees

There is one authoritative editable representation: `Document.tokens`, a
lossless token sequence with stable token IDs. Symbol, scope, statement, and
reference indexes are derived from those tokens after every committed edit.
The numeric expression projection is immutable and revision-bound. It is built
from canonical tokens and semantic bindings; it is not another editable AST.

The construction agent is presented with a small set of JSON function tools:

| Tool | Agent-visible purpose | Safety boundary |
|---|---|---|
| `workspace_create_empty` | Create a virtual document with no source input | Establishes its first revision |
| `workspace_structure` / `workspace_symbols` | Discover functions, parameters, locals, types, IDs, and revision | IDs must be returned by the workspace |
| `workspace_create_function` | Create a numeric `FUNCTION` with parameters and a zero result | Commits one validated revision and returns function, parameter, and statement IDs |
| `workspace_statements` | Find assignment statements inside a discovered function | Returns durable statement IDs, target, references, summary, and revision |
| `workspace_edit_expression` | Replace one assignment RHS using a typed expression object | Requires a discovered statement and current revision |
| `workspace_insert_assignment` | Add a numeric local/result assignment | Requires a discovered containing function and any insertion anchor |
| `workspace_execute_function` | Run a discovered function using `interp` or `jit` | Rebuilds the projection for the requested committed revision |

The expression request is a JSON algebra (`number`, `symbol_ref`, `unary`,
`binary`, `call`). It has no source-string field. References carry opaque IDs;
the transaction checks scope, numeric type, arity, supported operators,
finite values, and expression limits. New nodes become canonical BASIC tokens
with fresh IDs. The index rebuild then verifies that each emitted reference
still resolves to the requested symbol. A failed check discards the private
candidate document.

Creation is intentionally two-stage today: create a complete function that
returns zero, discover its assignment identity, then replace its expression.
This makes every committed revision valid and discoverable, but it also costs
extra model turns. A later API could accept a function plus a typed body in one
atomic request, using transaction-local handles for the new parameters. That
would reduce interaction overhead without introducing an editable second
representation.

The current tool schemas are sent with each chat completion. The JSON tool
schema bundle measured 4,735 bytes for the semantic arm, compared with 2,677
bytes for the text arm in the construction pilot. These byte counts are not
token counts. The endpoint reported prefix-cache usage, so repeated schema
context was often cached. A compact-schema experiment should measure schema
bytes, provider prompt tokens, cached prompt tokens, and cumulative session
cost separately; it should not assume the full schema is recomputed at every
turn.

## Direct construction demonstration

Command:

```sh
python3 experiments/basic-workspace/program_construction_demo.py \
  --output experiments/basic-workspace/results/program-construction/constructed.bas \
  --json experiments/basic-workspace/results/program-construction/demo.json
```

The application starts from an empty virtual document and only calls semantic
operations. It creates `DOUBLE(X)`, executes `DOUBLE(9)`, creates
`CALCULATE(Y)` with a call to the discovered `DOUBLE` identity, changes
`DOUBLE` from `X*2` to `X*3`, and renames it to `TRIPLE`. Both engines return
18, 21, then 30 and 30 after the rename. The only BASIC rendering is performed
after the last execution for optional inspection. The JSON trace records 18
workspace RPCs, 4,185 request bytes, 8,229 response bytes, and 35.24 ms of
workspace RPC wall time for this single local run. Execution uses a fresh MIR
worker per call; the recorded small-module process cost is roughly 0.7–1.0 ms.

Historical validation is downstream only:

```sh
python3 experiments/basic-workspace/scripts/validate-program-construction-oracle.py
```

The historical interpreter and JIT both passed their exported-program check
(`27\n30\n`). They do not participate in constructing or executing the
authoritative in-memory workspace.

## Model endpoint and context measurements

The endpoint at the operator-supplied private address exposed an OpenAI
`/v1/models` endpoint and accepted `/v1/chat/completions` tool calls. It
reported `Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw` ready with a 220,000-token
context limit. The endpoint URL and credentials are intentionally omitted from
committed records. The runner's 64,000-byte request-context cap is a separate
local safety guard over serialized messages plus tools; it is not the model's
context window. `max_tokens=1024` is a per-completion output cap, not a total
session output budget.

An initial one-task pilot used a text arm without an execution tool. Its text
result therefore was not a fair executable comparison and is retained only as
exploratory evidence in `llm-trials-sushi-pilot/`.

The corrected one-task pilot gave both arms the same in-memory numeric
MIR-interpreter/JIT execution capability:

| Measure (`construct_double`) | Semantic tools | Text tools |
|---|---:|---:|
| Outcome | Correct, interp/JIT = 18 | Correct, interp/JIT = 18 |
| Model turns / tool calls | 7 / 7 | 6 / 7 |
| Failed tool calls | 2 | 1 |
| Tool schema JSON bytes, per request | 4,735 | 2,677 |
| Largest compact messages + schema context | 10,875 bytes | 5,929 bytes |
| Total serialized request bodies | 58,304 bytes | 29,708 bytes |
| Total response wire bytes | 7,355 bytes | 5,789 bytes |
| Provider prompt / completion tokens | 15,843 / 880 | 7,691 / 505 |
| Provider cached prompt tokens | 12,318 | 5,971 |
| Inference wait | 38.83 s | 18.84 s |

This is one task per arm and is not evidence that one editing style is
generally more efficient. It does show why per-operation comparisons are
misleading: the semantic arm paid discovery and revision-protocol costs, while
its typed operations and identity checks supplied stronger guarantees. In this
pilot it also made two avoidable calls by trying to create a function before
opening the document. The API should make the initial empty workspace more
obvious, and a higher-level atomic function-with-body operation may amortize
discovery. The provider marked approximately 77.7% of prompt tokens as cached
in both arms. Those cache counts are reported independently from raw bytes.

The local Ollama Gemma exploratory run is kept in `llm-trials/`. It used a
different, earlier text tool set and reached an iteration limit in the semantic
arm; its numbers must not be combined with the fair Sushi pilot or interpreted
as a semantic-versus-text result.

Four further paired elementary tasks completed before the operator redirected
the study to continued program-level sessions. All four completed tasks were
correct in each arm, but this partial run is explicitly marked
`interrupted_by_user_scope_steering` in `llm-trials-sushi-full/trials.json` and
is not a final benchmark. It used 92,692 prompt / 5,365 completion tokens for
semantic and 31,385 / 2,419 for text across those four pairs. The rows remain
available for audit; the remaining four task pairs were not run.

Reproduction command, with the private endpoint supplied locally and not
written into artifacts:

```sh
python3 experiments/basic-workspace/experiment/program_construction_trials.py \
  --endpoint-url "$BASIC_WORKSPACE_ENDPOINT/v1/chat/completions" \
  --model Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw \
  --request-timeout 180 --max-output-tokens 1024 --max-iterations 12 \
  --max-tool-calls 20 --seed 18 --limit 1 \
  --output-dir experiments/basic-workspace/results/program-construction/my-pilot
```

## Continued-session study: revised design

The next model trial should measure a sustained work session, not average an
elementary operation. For each target program, the agent should construct a
working baseline, receive a new objective together with an explicit resume
summary, and then make a multi-level change. The summary should state the
current revision, program structure, semantic IDs relevant to the next task,
decisions/invariants, last validation result, and remaining objective. The
agent must verify that summary against the live workspace before editing.
The text arm should receive an equivalent resume summary derived from its
buffer version, current program outline, diff, and validation. Both arms should
keep their authoritative program in memory, and every phase should share one
long-lived model conversation or an explicitly resumed conversation as the
protocol specifies.

Proposed sessions:

1. **Graphics animation:** construct layered, colored circles; resume with a
   request to replace circles with ellipses and revise the color-variation
   algorithm. Validate the final rendering or deterministic frame output.
2. **Related directories (ECS/structure-of-arrays):** construct an in-memory
   address book with stable entity IDs and parallel component arrays for
   people; resume by adding person attributes; then add professional-component
   arrays and a relationship array containing person entity IDs. Validate
   lookup/link behavior and data invariants. This avoids assuming BASIC record
   types: entity IDs, components, and links are explicit arrays.

These are materially broader than the implemented numeric subset. The
historical BASIC frontend has `CIRCLE`, `COLOR`, `HCOLOR`, and Kitty-terminal
graphics marked work in progress; no `ELLIPSE` construct was found. The
workspace MIR projection currently accepts only numeric functions, simple
assignments, arithmetic, and numeric calls. It rejects loops, arrays, strings,
graphics effects, and imported runtime calls. The address-book scenario needs
string and indexed-array semantics plus entity/link invariants (records can be
represented as ECS-like parallel arrays); the animation needs
control flow, graphics effects, a frame or output oracle, and an ellipse
primitive (or a justified derivation from existing primitives).

Therefore, neither scenario should be run through the existing semantic
authoring tools and then scored as a failure. Before a fair comparison, select
the smallest capability slice for each case and add typed semantic operations
that lower into the canonical tokens, with revision checking and executable
validation. Avoid turning the tool into a generic arbitrary-source generator.
The first architectural question is whether these domain changes should be
represented as BASIC constructs (arrays, strings, loops, graphics statements)
or as a compact, typed domain layer that deterministically generates those
constructs. Any domain layer must remain a derived/editing interface to the
canonical program model, not a second independent source of truth.

For the ECS address-book option, a minimal model is: `entity_id[]`, one
person-component column per attribute, a separate `professional_entity_id[]`
and its columns, plus `professional_person_id[]` for the relation. Adding an
attribute adds one component column; it should not renumber existing entities.
Adding a professional relationship must validate that its referenced person
ID exists. The agent tools should expose operations such as add-component,
add-entity, and link-entities over discovered collection/component IDs, then
lower those edits deterministically into canonical BASIC array declarations
and assignments. This is a candidate typed authoring layer, not yet an
implemented data model. The first executable slice would need arrays, string
values, indexing, mutation, capacity/bounds behavior, and referential
validation in the direct MIR projection.

For each session, report cumulative model turns, tool calls, retries, correct
intermediate and final behavior, input/output tokens, cached prompt tokens,
schema overhead, request/response bytes, latency, and the quality of each
explicit resume. A session-level summary should separately attribute costs to
the repeated schema, discovery/revision safeguards, and model corrections.
This permits the structured API's setup cost to be assessed as an investment
over subsequent edits rather than as a one-call penalty.

## Validation and remaining scope

Commands run after the construction and fair-text execution changes:

```sh
PYTHONPATH=experiments/basic-workspace python3 -m unittest discover \
  -s experiments/basic-workspace/tests -v
PYTHONPATH=experiments/basic-workspace python3 \
  experiments/basic-workspace/experiment/llm_runner.py --fixture-test
python3 -m py_compile experiments/basic-workspace/experiment/llm_runner.py \
  experiments/basic-workspace/experiment/program_construction_trials.py
```

Result: 51 tests pass; the offline protocol fixture passes. The numeric
construction demo and historical interpreter/JIT oracle pass. The ongoing
study is exploratory until the two program-level scenarios have a supported
semantic/execution slice and explicit resumed-session trial protocol.
