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

`create_numeric_function` creates a complete function whose result is initially
0. The operation returns its function, parameter, and default assignment IDs.
Agents then discover those IDs and use `edit_assignment_expression` to provide
the intended body. This avoids temporary transaction handles and makes every
committed revision well-formed and executable. A second function can be created
and populated in the same sequence, using a previously discovered callee ID.
Locals are introduced with `insert_assignment`; after commit their implicit
variable IDs are returned and can be referenced in later expressions.

The existing `preview_transaction` and `apply_transaction` accept these
operations too. Preview reports a created-entity count/summary rather than
ephemeral candidate IDs; commit returns stable published IDs.

## Limits

The constructive language remains the existing numeric function subset. No
control flow, strings, arrays, imports, global statements, or deletion is
introduced. No second editable AST or BASIC source import/reparse is added.
