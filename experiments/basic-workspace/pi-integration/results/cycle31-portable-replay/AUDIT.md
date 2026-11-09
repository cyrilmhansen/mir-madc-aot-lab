# Cycle 31 replay duplication audit

## Scope and boundary

Audited `cycle19_gateway.py`, `cycle20_gateway.py`, `cycle25_gateway.py`,
`cycle28_gateway.py`, `cycle29_gateway.py`, their portable identity helpers,
and the six operation kinds in the authentic Cycle 30 constructive stream. No
inference was run.

| Responsibility | Before | After |
|---|---|---|
| Portable operation dispatch | Six replay loops/dispatch paths: Cycle 19; Cycle 20 baseline and full replay; Cycle 25; Cycle 28; Cycle 29 | `basic_workspace.portable_replay` dispatches the six bounded operation kinds |
| Expression / local reference resolution | Repeated in Cycle 20, Cycle 25, and Cycle 29 | Shared typed resolver maps portable handles to current Workspace IDs and validates arity |
| Statement anchor resolution | Repeated in insertion and replacement replay branches | Shared dispatcher resolves the function and anchor handles before calling Workspace |
| Identity assignment | Campaign helpers duplicated constructor and insertion mapping | Shared result records constructor, insertion and replacement identity changes |
| Retirement | Cycle 20/29 maintained replay-specific maps | Shared live/retired/ever-seen sets; retired handles cannot be resolved or reused |
| Revision tracking | Per-gateway loops inspected the Workspace revision | Every operation records base/resulting revisions and must advance once |
| Evidence attestation | Mixed into Cycle 20 stream loop and mission validators | Kept in the gateway/verifier layer; replay itself does not read campaign JSON |
| Authorization and host oracle | Mission-specific by design | Remain in their existing gateways and validators |

The semantics are compatible because each recorded constructive item is one
Workspace revision transaction. `edit_numeric_literals` may contain multiple
canonical literal operations, but the batch is applied as one transaction.
The replay is sequential across items; it does **not** promise whole-stream
atomicity. If a later item is invalid, earlier committed replay revisions
remain in the caller-owned temporary Workspace and the stream is reported as
failed.

## Historical evidence distinction

The replayed revisions 11, 12, and 14 have normalized semantic snapshots and
were compared directly. Revision 9 has a rename identity/behavior validation
but no complete normalized snapshot in the preserved campaign record. Revision
13 has its exact block-replacement transaction, retired-handle receipt, prior
revision-12 semantic snapshot, and host validation; it lacks a final normalized
snapshot. These two checkpoints are recorded as narrower historical
attestations, not upgraded into structural snapshot checks.

The authentic Cycle 30 operation stream and all prior transcripts, snapshots,
journals, and validation files remain unchanged.
