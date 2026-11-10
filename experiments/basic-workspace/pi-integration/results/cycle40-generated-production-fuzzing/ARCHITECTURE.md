# Architecture and trust path

The campaign composes existing boundaries rather than inserting a workflow engine:

1. Cycle19 authorizes each typed constructor, commits one revision, validates, and advances only by host checkpoint.
2. The existing verified handoff binds the completed creation evidence and destination Cycle37 contract to a separate host anchor; Cycle37 reconstructs it in a new Workspace.
3. Cycle37 authorizes and commits one `rename_symbol` through its existing TypeScript handler and transaction kernel.
4. The verified rename continuation packages the creation root plus rename suffix and binds Cycle20's destination contract to a new host anchor.
5. Cycle20 reconstructs and authorizes one `edit_numeric_literals` batch containing three targets, then validates and replays the result.

The generator creates only math specs and host contracts. It does not transfer Workspace objects between processes. Canonical operation semantics remain in Workspace; one-step atomicity remains in the shared transaction kernel; replay remains in Cycle31's dispatcher. The creation-to-maintenance workflow itself is sequential, not globally atomic.

The variation that was representable without production changes includes names, values, function count, shared-provider fanout, dependency chain depth, rename-reference count, and edit target values. The key limit is the Cycle20 oracle type set, not construction or replay.
