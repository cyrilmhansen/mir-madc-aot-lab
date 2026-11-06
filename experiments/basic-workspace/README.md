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
`RESTORE`, `IF`, `FOR`, `NEXT`, arrays, `ON ERROR`, computed branches, and
many dialect extensions are preserved losslessly, but only the listed
name/target relationships are indexed. Dynamic/evaluated source, array-vs-call
ambiguities and unsupported constructs remain explicit limitations. The
frontend must not be used to claim compiler-level semantic correctness for
programs outside the supported subset. Full source equivalence is not proof of
behavior equivalence.

The baseline interpreter and JIT were run on
`tests/fixtures/semantic-before.bas` and the semantically transformed
`semantic-after.bas`; both print `10` in both modes. Use
`experiments/basic-workspace/scripts/validate-dialect.sh` to repeat that
comparison. The core tests themselves build programs from strings and do not
write BASIC source files.

## JSON-RPC and optional LSP

The native JSON-RPC service is the primary interface. The optional facade can
be started with:

```sh
PYTHONPATH=experiments/basic-workspace python3 -m basic_workspace.lsp
```

It implements framed LSP `initialize`, `didOpen`, full-text `didChange`,
`didClose`, `documentSymbol`, `definition`, `references`, `prepareRename` and
`rename`. It maps requests to the same `Workspace` object. `didChange` imports
a complete document as an explicit replacement transaction and invalidates
identities; incremental range changes are rejected. A returned LSP
`WorkspaceEdit` is derived from the semantic references, while the semantic
engine commits the token edit itself. The facade is intentionally thin and
does not store a second editable document.

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
