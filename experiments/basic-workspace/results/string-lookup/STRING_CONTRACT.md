# Workspace string contract (Cycle 9)

This experiment deliberately does not inherit the historical BASIC runtime's
pooled allocation model. The historical frontend represents string values as
`char *`, uses `$` to identify string variables/functions, and its runtime
allocates many string results from a pool that callers release with
`basic_free()`. String DIM arrays contain `char *` cells. Those rules are
useful compatibility evidence, but pool ownership is too implicit for this
isolated execution worker.

The Workspace subset uses valid UTF-8 byte strings and rejects embedded NUL.
String comparisons are not implemented. Empty string is a valid zero-length
value. Source literals cannot contain NUL or physical line breaks. A literal
is limited to 4096 UTF-8 bytes, and all serialized string-literal bytes plus
terminators in one execution are limited to 256 KiB.
Uninitialized string slots and array cells contain the empty string. Array
bounds retain the Workspace's zero-based, inclusive-upper-bound semantics.

At runtime, each worker invocation owns the literal storage and empty-string
sentinel. String local variables and array cells hold references to immutable
values in that invocation. Assignment replaces a reference; it does not free
or mutate a value. A string result is measured and copied into the worker's
JSON response before MIR context and instance storage are released. No native
pointer crosses the JSON-RPC boundary. This contract does not expose string
parameters, concatenation, builtins, mutable buffers, or module-persistent
strings. Python requests must be valid UTF-8 encodable strings and pass the
same byte and NUL limits.

The canonical token stream remains authoritative. String and array type,
function projections, and bindings are derived from `$` names and DIM tokens;
the execution instance is ephemeral runtime data, never a second program
representation.
