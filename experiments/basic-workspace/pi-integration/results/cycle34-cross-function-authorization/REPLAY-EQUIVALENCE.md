# Replay and semantic equivalence

The Cycle19B two-constructor stream was replayed into a new empty Workspace at revision 1 and matched the authentic revision-3 checkpoint. Both functions have the expected portable identities, and `IS_PASSING` remains bound to `CLAMP_SCORE`.

For each contract, the accepted edit is serialized as one `edit_numeric_literals` operation containing three portable targets. The shared Cycle31 replay implementation applies that record after the two constructors. The fresh replay reaches revision 4 with eleven portable identities remapped to new Workspace-local IDs and no retired handles.

The recorded `replay-equivalence.json` reports structural, binding and behavioral equivalence for both contracts. The full identity mapping and raw validation records are preserved under `production-bridge/{primary,secondary}/gateway-evidence/`. Literal target token IDs are the only changed token IDs; Workspace identity aliases, token ID set, statement/function identities and dependency edges remain stable.

Evidence distinguishes reconstruction/replay from authoritative live commit. Replay is sequential and is not claimed to provide whole-stream atomicity; the three edits inside the maintenance operation are one atomic Workspace transaction.
