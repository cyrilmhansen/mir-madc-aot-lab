# BASIC Workspace

An in-memory semantic programming experiment for BASIC and coding agents.
The workspace model is authoritative. No source file or editor is needed for
the service API; text can be loaded from a request and rendered back from the
model. Files under `tests/fixtures/` are only examples for dialect comparison.

## Architecture decision

The pinned BASIC compiler in `../basic-aot/upstream/basic/src/basicc.c` has a
hand-written lexer/parser and useful C structures: expression `Node`, tagged
`Stmt` records and line vectors. Its parser, AST arena, pools, symbol lookup,
implicit declarations, global parser state, function collection and MIR
generation are coupled inside a large translation unit. `parse_func()` stores
source lines while building MIR-facing function records; variable lookup and
code generation consult process-global tables. Pulling out its lexer/parser
would require a wider refactor and an API contract not present upstream.

More specifically, the C frontend has a tagged expression `Node` tree
(`N_NUM`, `N_VAR`, `N_BIN`, `N_CALL`, etc.), a tagged-union `Stmt`, a `Line`
with a numeric BASIC line and statements plus original source text, and a
`FuncDef` with parameters, body, EXTERN/procedure/return flags and MIR items.
It allocates expression data from `ast_arena`, grows vectors through pool
helpers, and uses globals such as `g_ctx`, `g_prog`, `g_func`, `g_vars` and
`func_defs`. Its line representation already separates line-number labels
from physical input lines. The C lexer normalizes identifiers before
`get_var()` compares them with `strcmp`. Function generation uses a
per-function variable vector seeded by parameters. These are useful reference
semantics, but cannot be reused independently without untangling parser
lifetime, global state and MIR setup.

This experiment therefore uses a small standalone frontend rather than
modifying BASIC or MADC. The canonical representation is one lossless token
stream. Whitespace, comments, original spelling, strings, physical line
breaks and line-number tokens are tokens in that stream. Statement spans,
function scopes, line labels, symbol bindings and diagnostics are derived
indexes over those same tokens. The indexes can be discarded and rebuilt;
they are not an independently editable AST. Rendering concatenates the
canonical tokens. A semantic operation changes only tokens bound to its
symbol/label identity, so no text/AST synchronization loop exists.

Token identities anchor symbol identities. A function symbol is tied to its
declaration token; a parameter has its own declaration token; an implicit
variable uses its first occurrence token as a provisional declaration. A
supported rename or line renumber keeps those token IDs, and a reindex carries
the same opaque symbol IDs forward. A full-text import from an editor is
explicitly a replacement transaction and invalidates token/symbol identities.
This marks the main semantic-divergence risk: this subset frontend is not the
compiler parser and does not attempt to infer every BASIC construct.

Atomic semantic operations work on a private document snapshot. They check the
base revision and preconditions, apply edits to bound tokens, rebuild indexes,
reject collisions/invalid line references, then replace the live snapshot and
increment its revision. A failed/stale transaction leaves the current model
untouched. This is optimistic single-process concurrency control; there is no
distributed collaboration or thread-safety claim.

## Run the API and demo

```sh
PYTHONPATH=experiments/basic-workspace python3 -m basic_workspace.server
PYTHONPATH=experiments/basic-workspace python3 experiments/basic-workspace/demo_client.py
python3 -m unittest discover -s experiments/basic-workspace/tests -v
```

The service uses JSON-RPC 2.0 with one JSON object per stdin/stdout line. This
simple framing is suitable for agent subprocess pipes and permits streaming
responses without Content-Length parsing. It has no filesystem methods. For
example, send:

```json
{"jsonrpc":"2.0","id":1,"method":"open_document_from_string","params":{"text":"FUNCTION TOTAL(SCORE)\nTOTAL=SCORE+1\nEND FUNCTION\n"}}
```

Core methods include `create_workspace`, `open_document_from_string`,
`list_documents`, `get_document_structure`, `list_symbols`,
`find_definition`, `find_references`, `rename_symbol`, `renumber_line`,
`move_function`, `apply_transaction`, `render_document`, `get_diagnostics`,
and `get_revision`. Every edit supplies `expected_revision`; a transaction can
contain multiple semantic operations. Symbol IDs come only from query results.

## Worked edit

The sample client opens this text at revision 1:

```basic
FUNCTION TOTAL(SCORE)
  TOTAL = SCORE + 1
END FUNCTION
10 GOTO 100
20 PRINT "SCORE is just text" ' SCORE comment
100 PRINT TOTAL(9)
200 END
```

It queries the `parameter` symbol and receives an opaque identity such as
`sym_…` (the actual ID is generated per workspace), then submits a transaction
at revision 1 with `rename_symbol(symbol_id, "POINTS")` and
`renumber_line(100, 150)`. The model commits revision 2 and renders:

```basic
FUNCTION TOTAL(POINTS)
  TOTAL = POINTS + 1
END FUNCTION
10 GOTO 150
20 PRINT "SCORE is just text" ' SCORE comment
150 PRINT TOTAL(9)
200 END
```

The string, comment and unrelated `200` stay unchanged. The parameter and its
reference keep their symbol identity. A second client still holding revision
1 receives `STALE_REVISION`; it cannot overwrite revision 2.

## Semantic coverage and boundaries

Implemented indexes and edits:

- Multiline `FUNCTION` / `SUB` declarations and parameter/local scopes.
- `DEF FN` and `EXTERN` / `EXTERNAL FUNCTION` or `SUB` declarations and
  calls. External signatures are recorded by parameter spelling/count only;
  type compatibility is not yet checked.
- BASIC case-insensitive matching while preserving displayed spelling.
- Implicit numeric/string variables, explicitly marked `implicit` in results.
  They are scoped by module or function; local `X` in two functions is distinct.
- Numbered physical source lines, distinct from physical line positions.
- Direct `GOTO` / `GOSUB` and constant target lists in `ON ... GOTO/GOSUB`.
- Rename a resolved parameter, variable or function; renumber a line and its
  indexed branch references; move a complete `FUNCTION`/`SUB` block within a
  module. Cross-module moves and incomplete/colon-embedded function blocks are
  refused.
- Diagnostics for duplicate/missing line labels, duplicate functions,
  incomplete functions/strings, unmatched terminators, and ambiguous
  array/function-like calls.

The expression grammar is intentionally not reconstructed. `DATA`, `READ`,
`RESTORE`, `IF`, `FOR`, `NEXT`, array forms outside the fixed local numeric
subset, `ON ERROR`, computed branches, and many dialect extensions are
preserved losslessly. Numeric array declarations and references are indexed
only within the documented MIR execution subset. Dynamic/evaluated source,
array-vs-call ambiguities and unsupported constructs remain explicit
limitations. The frontend must not be used to claim compiler-level semantic
correctness for programs outside the supported subset. Full source equivalence
is not proof of behavior equivalence.

The baseline interpreter and JIT were run on
`tests/fixtures/semantic-before.bas` and the semantically transformed
`semantic-after.bas`; both print `10` in both modes. Use
`experiments/basic-workspace/scripts/validate-dialect.sh` to repeat that
comparison. The core tests themselves build programs from strings and do not
write BASIC source files.

## Direct in-memory MIR execution experiment

The numeric `FUNCTION` subset can be lowered from the canonical token model
without rendering or reparsing BASIC. Build the native bridge and run the
semantic edit/re-execution example with:

```sh
experiments/basic-workspace/scripts/build-mir-worker.sh
PYTHONPATH=experiments/basic-workspace python3 experiments/basic-workspace/mir_execution_demo.py
```

The JSON-RPC `execute_function` operation requires a discovered function ID,
the current document revision, numeric arguments, and `engine: "interp"` or
`"jit"`. Unsupported constructs return explicit diagnostics. Scope, API,
differential results and limitations are documented in
`results/mir-execution/REPORT.md`.

The projection also supports function-local, one-dimensional numeric
arrays declared with `DIM NAME(n)`, where `n` is an inclusive upper bound
(0..255). Typed construction can declare arrays, write indexed elements and
read them with `array_element`; each invocation initializes cells to zero and
invalid dynamic access returns `ARRAY_BOUNDS`. BWM3 adds comparisons,
conditionals and bounded FOR loops; BWM4 adds UTF-8 string literals, locals,
returns and fixed string arrays. String memory belongs to one worker call and
returned values are copied into JSON before that worker is released. Strings
are not compared or concatenated, passed as arguments, or shared between
functions. This does not add module-level state or a general ECS. Run
`python3 numeric_array_demo.py` from this directory; historical comparison,
performance data and subset limits are in
`results/numeric-arrays/REPORT.md`.

Cycle 9's complete in-memory ID-to-name construction and semantic edit is
reproducible with:

```sh
experiments/basic-workspace/scripts/build-mir-worker.sh
python3 experiments/basic-workspace/scripts/demo-string-lookup.py
python3 -m unittest discover -s experiments/basic-workspace/tests -p 'test_*.py'
```

See `results/string-lookup/REPORT.md` for ownership rules, historical compiler
differences, sanitizer results and string lookup measurements.

## JSON-RPC and optional LSP

The native JSON-RPC service is the primary interface. The optional facade can
be started with:

```sh
PYTHONPATH=experiments/basic-workspace python3 -m basic_workspace.lsp
```

It implements framed LSP `initialize`, `didOpen`, full-text `didChange`,
`didClose`, `documentSymbol`, `definition`, `references`, `prepareRename` and
`rename`. It maps requests to the same `Workspace` object. Rename proposes a
versioned `documentChanges` WorkspaceEdit and does not mutate the workspace.
The subsequent full-document `didChange` is accepted as one explicit
replacement transaction only when the document version increases and the
synchronized text matches the pending proposal. Incremental range changes are
rejected. UTF-16 positions are negotiated and converted, including rejection
of offsets that split a surrogate pair. A stale proposal is rejected if
another operation changes the workspace. The facade does not store a second
editable document.

## Agent client and semantic tools

`basic_workspace.client.WorkspaceClient` launches one long-lived JSON-RPC
subprocess, correlates request IDs, enforces timeouts and closes the process
cleanly. `AgentToolAdapter` exposes eight structured operations:

| Tool | Purpose |
|---|---|
| `workspace_open` | Load source text into the in-memory model |
| `workspace_structure` | Page concise line/function/label summaries |
| `workspace_symbols` | Filter and page semantic entities |
| `workspace_references` | Page references for a discovered identity |
| `workspace_preview` | Validate a transaction on a private snapshot |
| `workspace_commit` | Revalidate and commit at an expected revision |
| `workspace_diagnostics` | Read diagnostics |
| `workspace_render` | Explicitly request bounded text export |

The client refuses fabricated symbol IDs and line labels not discovered through
query tools. Preview and commit share transaction validation. Preview does not
reserve a revision; the service checks again at commit. Multiple adapters can
fork views over one client process, sharing the authoritative in-memory model
while retaining separate observed revisions.

```sh
PYTHONPATH=experiments/basic-workspace python3 experiments/basic-workspace/agent_demo.py
python3 experiments/basic-workspace/experiment/run_trials.py
python3 -m unittest discover -s experiments/basic-workspace/tests -v
```

The demo performs open → structure → symbol discovery → references → preview
→ commit → diagnostics/revision verification. It renders only when a text
export is explicitly requested. Editing requires no source file.

## Atlas boundary and deterministic task results

The Atlas Python checkout inspected is `/home/john/luna/atlas-py-v012` at
`3aad255b5e049766db06f7541d5da1b212ec3f20`. Its `CodexExecutor` runs a sealed
Codex profile with fixed tools (`exec_command`, `write_stdin`, `apply_patch`)
and digest-validated assets. It has no Python structured-tool callback seam.
Adding one would change Atlas's existing tool selection/profile contract, so
that repository remains untouched. The standalone adapter exercises the
subprocess and structured-result boundary. Atlas registration and
Atlas-mediated model trials remain unverified; no Atlas changes were made.

`experiment/run_trials.py` runs 16 deterministic tasks from clean in-memory
workspaces: scoped/local and function renames, GOTO/GOSUB/ON GOTO renumbering,
an atomic multi-operation edit, collision rejection, function movement,
ambiguity/incomplete-input refusal, colon-separated statements, a two-agent
stale revision conflict, and historical `fn`, `mastermind` and `poker`
examples. Historical files are read-only. The text arm is literal
search/replace, not a model or human estimate. Results under
`results/agent-editing/` include per-task metrics and machine-readable data.
The first deterministic run measured 16/16 semantic outcomes and 10/16 text
outcomes; semantic tools made 108 calls and the text arm 32. The task suite
counts 35,582 semantic tool-response bytes versus 13,906 source bytes shown to
the text arm. One harness run took 581.528 ms versus 0.125 ms, dominated
by 16 fresh server processes; this is not a fair agent-latency comparison.
That response overhead is higher even though it does not expose the complete
program text. Small samples do not establish a general context advantage.
Model token use in the deterministic task suite is unavailable, not estimated.

The trial exposed and fixed an index gap: a BASIC function's result-assignment
name was not bound to the function symbol. Renaming the function used to leave
that assignment under the old name. The index now binds that occurrence, and
the regression test covers declaration, result assignment and calls together.

## Real LLM editing comparison

`experiment/llm_runner.py` is an independent OpenAI-compatible tool-calling
harness. It supports explicit endpoint/model/settings and keeps both arms
in-memory: the semantic arm uses the long-lived Workspace JSON-RPC service;
the text arm uses read/search/context-checked patch/diff/subset-diagnostic
tools over a separate buffer. The model receives no oracle or source in its
initial prompt. Raw trials and provider usage are stored under
`results/llm-editing/`.

On 2026-11-07, local Ollama 0.20.0 served `gemma4:latest` (8B, Q4_K_M) with
temperature 0, seed 17, thinking off, 1,024 response tokens, 8 iterations, 14
tool calls, 120-second request timeout and a 64,000-byte context cap. Across 15
paired non-conflict tasks, semantic editing was correct on 15/15, including
three safe refusals; text tools were correct on 12/15, including the same three
safe refusals. Semantic used 43 calls and 140,171 provider tokens; text used 70
calls and 156,090 tokens. Semantic produced more tool-response bytes (38,798
vs. 32,748), despite fewer calls and lower total inference time. This is one
small single-seed trial, not evidence of general model accuracy. See
`results/llm-editing/SUMMARY.md` and per-turn `run.json` for failures, latency
and raw traces.

The deterministic compact-discovery comparison reduces response bytes from
64,680 to 19,279 and calls from 90 to 59. A genuine two-agent run also shows a
revision-1 proposal rejected after the first agent commits revision 2; the
second agent then inspected current state and refused to rebase. The earlier
pilot that rebased without a stale rejection is preserved separately and not
counted as a successful conflict trial.

The standalone model runner is not Atlas integration. Atlas's inspected Python
executor still has a sealed fixed tool set and no supported structured Python
callback seam; that contract was not changed or bypassed.

## Microbenchmarks

Run `python3 experiments/basic-workspace/bench.py` to read (not rewrite) the
historical tiny `fn`, medium `mastermind` and large `poker` examples and
regenerate `results/benchmark.{json,md}`. Timings include semantic index
rebuilding for edits and `tracemalloc` peak during initial model construction.
The current Skip run is recorded in `results/benchmark.md`. It measured parse
and index at 0.103 ms for 85-byte `fn`, 9.095 ms for 5.2 KiB `mastermind` and
21.844 ms for 8.1 KiB `poker`; a semantic rename transaction took 0.180, 8.208
and 13.603 ms. Symbol lookup was about 0.26 μs; render took 0.0014–0.085 ms.
`tracemalloc` peak was 22 KiB, 866 KiB and 1.39 MiB respectively. This is a
Python prototype baseline, not an optimization target. Full index rebuilding
is simple and predictable here; incremental parsing should wait until measured
workloads show it is necessary.

## Roadmap

1. Validate symbol binding against more compiler fixtures and refine BASIC
   grammar boundaries without changing the upstream compiler.
2. Add transaction audit/undo and explicit client identity once multi-agent
   usage needs it; keep revision checks as the conflict boundary.
3. Extend semantic expression and branch parsing with fixtures for every new
   construct, including computed `ON` branches.
4. Add an in-memory compiler adapter only after the canonical model is stable:
   model → MIR → interpreter/JIT feedback, with AOT as an explicit downstream
   consumer. Text export remains useful for debugging but not authoritative.

## Structured program construction

The numeric construction prototype starts with an empty virtual document and
creates/edit functions through typed semantic tools, then runs the committed
revision through MIR interpreter or JIT. See
[`results/program-construction/REPORT.md`](results/program-construction/REPORT.md)
for the API as presented to the agent, prompt/schema/context measurements, and
the revised continued-session study design. That report distinguishes the
validated numeric slice from the proposed graphics-animation and related
address-book sessions, which require additional language and execution
capabilities before a fair semantic-versus-text trial. The Cycle 6 atomic
constructor, historical BASIC feasibility findings, ECS boundary, model
timeout record, and exact in-memory demo are documented in
[`results/continued-sessions/REPORT.md`](results/continued-sessions/REPORT.md).

## Bounded control flow and entity-ID lookup

The typed numeric projection supports `=`, `<>`, `<`, `<=`, `>`, `>=`,
multiline `IF/ELSE/END IF`, and lexically matched `FOR/NEXT` with finite
constant bounds and a statically verified limit of 10,000 iterations.
Comparisons produce numeric 1/0; `IF` treats any nonzero value as true. Arrays
are fixed, zero-based, per-call locals initialized to zero. The default MIR
lowering uses bounds-checked `ALLOCA` stack storage. Set
`BASIC_WORKSPACE_MEMORY_ARRAYS=0` to compare the earlier per-cell register
dispatch path. Dynamic loop bounds, strings, cross-function state and general
control flow remain unsupported. The pinned historical compiler's function
`IF` lowering disagrees with these semantics; the exact differential and
performance results are in
[`results/control-flow-lookup/REPORT.md`](results/control-flow-lookup/REPORT.md).
Reproduce the entirely in-memory AGE_BY_ID build and semantic update with:

```sh
experiments/basic-workspace/scripts/build-mir-worker.sh
PYTHONPATH=experiments/basic-workspace python3 experiments/basic-workspace/control_flow_lookup_demo.py
```
