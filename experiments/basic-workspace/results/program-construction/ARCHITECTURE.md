# Program construction design boundary

## Canonical ownership

`Document.tokens` remains the sole editable BASIC representation. Constructive
requests do not accept source fragments. They validate typed expression nodes,
turn those nodes into canonical token objects with fresh token IDs, and splice
only the requested tokens into a private document clone. Existing unrelated
tokens are retained. The ordinary semantic index rebuild then resolves names;
the operation compares every newly written identifier token with the requested
symbol ID and rejects the clone if resolution differs.

This continues the current transaction lifecycle: clone → apply semantic
operation(s) → rebuild indexes → validate → increment revision → swap. Preview
uses the same pipeline on a private clone and never publishes IDs or mutates the
live document. A commit returns the newly created symbol and statement IDs.

## Statement identity

Only supported function assignment statements receive statement IDs. An ID is
retained by a map keyed to the assignment target token ID. Replacing the RHS
preserves that target token, so the statement ID survives. Inserting an
assignment creates a fresh target token and therefore a fresh statement ID.
Moving, renaming other entities, and unrelated insertions preserve existing
anchors. Removing/replacing the target token is not part of this cycle.

The query returns a bounded list of assignment metadata: statement ID, function
ID, target symbol ID/name, ordered referenced symbol IDs, a short token-derived
expression summary, and revision. Physical positions are descriptive only.

## Typed expression request

Expressions use a small JSON algebra (`number`, `symbol_ref`, `unary`,
`binary`, `call`). The request validator builds the same immutable `Expr` node
types consumed by the current MIR projection. It enforces finite doubles,
supported operators, maximum depth/arity, numeric types, scope membership and
function arity. It does not parse BASIC text. Token construction serializes the
validated tree with explicit parentheses for arithmetic precedence. Reindexing
then proves that identifiers resolve to the exact supplied symbol identities.

## Construction sequencing

`create_numeric_function` can atomically create a complete body in one
transaction. The expression tree may refer to newly declared parameters with
`{"kind":"local_ref","name":"X"}`; it may refer to locals declared earlier
in the same `locals` list the same way. The transaction creates the function
header, indexes the candidate to obtain temporary persistent IDs, resolves
these name handles in the function scope, emits local assignments in order,
then emits the result expression and validates its bindings. The temporary
name map exists only during transaction construction; successful commit
returns stable function, parameter, local, and statement IDs. A failure
discards the entire candidate and publishes no IDs.

For backwards compatibility, callers may omit the body; that retains the
previous zero-result constructor. The agent-facing construction schema now
requires a typed result expression and supports optional ordered locals. The
previous two-step path (create zero function, discover assignment, replace
expression) remains available through the general edit API, but is no longer
needed for initial construction. Calls to already existing functions still
require a function ID discovered by the agent.

The host now creates the empty virtual document before the first model turn
and provides its revision in the prompt. The agent tool list does not expose
`workspace_create_empty`; this avoids a failed function creation on an absent
document and an unnecessary bootstrap call.

The existing `preview_transaction` and `apply_transaction` accept these
operations too. Preview reports a created-entity count/summary rather than
ephemeral candidate IDs; commit returns stable published IDs.

## Fixed numeric arrays (Cycle 7)

The same token-based construction boundary now recognizes function-local,
one-dimensional numeric `DIM NAME(n)` declarations. The declaration symbol,
inclusive zero-based bounds, indexed reads, and indexed assignment targets
are derived from canonical tokens. The typed construction operation accepts
array declarations and ordered indexed writes; expressions can use a
transaction-local array handle while building a function or a discovered
array ID in later edits. Reindexing verifies the new token bindings before a
transaction commits.

The immutable projection carries array bounds and typed element expressions
through BWM2. The worker allocates MIR double registers for each cell and
initializes them on every function invocation. Constant indexes lower to
direct register accesses; dynamic indexes use checked dispatch, not exposed
pointers. BWM1 scalar payloads are still accepted. The worker limits each
array to 256 cells, each function to 32 arrays and 4096 total cells. OOB and
non-finite indexes return a structured execution diagnostic.

This remains a narrow subset. It does not support strings, multidimensional
or dynamic arrays, module-level/shared storage, conditions, loops, or
cross-function mutation. The pinned historical compiler uses zero-based
inclusive DIM bounds by default and truncates numeric indexes in tested
cases. Its size-one DIM fallback differs from this workspace: `DIM A(0)` is
one element here. Details and differential evidence are in
`results/numeric-arrays/REPORT.md`.

## Limits

The constructive language remains a numeric function subset with fixed local
numeric arrays. No control flow, strings, imports, global statements, or
deletion is introduced. No second editable AST or BASIC source import/reparse
is added.
