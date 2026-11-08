# Cycle 19 architecture audit

## Verified starting point

- The Workspace API has `create_empty_document()`. It creates a canonical document at revision 1 with no tokens, symbols, functions, declarations, or program logic.
- `create_numeric_function` is already an atomic semantic transaction. The typed projection, MIR interpreter/JIT, and portable operation replay support numeric parameters, result assignments, comparisons, IF statements, and bound function calls.
- The existing Cycle 16 gateway is tied to an AGE_BY_ID seed and its mission-specific invariants. It is not suitable for authoring into an empty document.
- Pi's existing five-tool atomic interface is sufficient. The only tool-schema change for Cycle 19 was making the optional `callee_handle` field optional so a self-contained first function can be proposed.
- An empty document cannot produce a compilable projection. The gateway uses the explicit semantic empty state `{ "functions": [] }` until the first function is committed; it does not insert hidden BASIC.

## Narrow adaptation

`cycle19_gateway.py` reuses the existing Workspace, typed constructor validator, transaction boundary, semantic normalizer, MIR executor, Pi loopback server, lifecycle observer, and generic visualization events. It adds two fixed mission contracts and a revision-bound transition after Mission 1 validation. Mission 2's comparison baseline is captured from the committed revision 2 projection.

The first live run exposed a redundant authorization argument: the call expression already included the discovered portable function handle, while the gateway also required the same handle in the separate top-level `callee_handle`. The tool description did not state that duplication. The gateway now derives the required handle from the typed call node when the legacy wrapper is omitted, while still checking that the dependency was discovered and has the required identity. The original failed session remains unchanged; no second model run was made.

## Trust and identity boundaries

Pi only receives discovery, inspection, preview, commit, and validation tools. The Python gateway owns the Workspace, mission scope, revisions, candidate validation, and commits. Portable handles such as `clamp_score.function` are mapped to workspace-local opaque IDs by the host. The recovery checkpoint sent to the new Pi process omits the document UUID and conversation history.

The loopback tool restriction is an experiment boundary, not an operating-system sandbox. Host shell and filesystem access are outside the claim.
