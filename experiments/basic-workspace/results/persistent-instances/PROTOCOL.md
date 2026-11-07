# Persistent MIR worker protocol

The existing one-shot worker remains the default. Persistent mode is selected
only by `BASIC_WORKSPACE_PERSISTENT=1`.

All inbound messages are framed as a four-byte little-endian length followed
by exactly that many bytes. The module-load frame contains one complete BWM4
or BWM5 projection (maximum 16 MiB). After validating it, the worker builds
and links the MIR context once, generates all functions once for JIT, and emits
one JSON `ready` line containing the build/link counters and timings.

Subsequent command payloads are:

| Opcode | Payload after opcode | Meaning |
|---:|---|---|
| 1 | `request_id:u32, function_slot:u32, argc:u32, argc*f64` | Call a numeric function |
| 2 | `request_id:u32` | Shut down and release MIR |

The maximum call frame is 61 bytes (one opcode, three 32-bit fields, and six
finite doubles). Every command gets one JSON response line with its request ID.
The Python owner validates the response ID, enforces a per-call timeout, and
serializes calls per instance. A timeout, broken pipe or response mismatch
kills the worker and marks the instance dead; it is not restarted.

BWM5 retains BWM4's expression and statement records and adds an explicit
shared-array flag and dense module-array slot after each array's element type.
The current restricted Workspace syntax represents module state as top-level
`DIM NAME(inclusive-upper-bound)` declarations. That scope/lifetime meaning is
a Workspace execution extension; historical BASIC compatibility is not
claimed. Shared numeric cells are MIR BSS data, zero initialized by the MIR
module loader. A typed initializer FUNCTION writes them through the generated
array assignments and is invoked once by the instance-creation API.
