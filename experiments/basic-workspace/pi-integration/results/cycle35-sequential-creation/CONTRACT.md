# Creation-sequence contract

`MISSION-A.json` and `MISSION-B.json` use `basic-workspace.numeric-function-creation-sequence` version 1. The gateway rejects unknown or missing fields. The contract supports at most eight ordered steps, starting from an empty revision-1 document and the existing numeric-composition execution profile.

Each step supplies a unique step and mission ID, its exact base revision, one function name and portable handle, one numeric parameter and numeric return type, the set of required functions created earlier in the sequence, exact expected call edges, the prior function handles that must remain unchanged, and a finite host-owned input/output table for every function present at that revision. It contains no BASIC source, executable callback, expression evaluator or agent-defined permission.

The authorization scope is limited to `create_numeric_function`. The existing Cycle 19 `_candidate` validates the proposed typed constructor and discovered callees; `_preview` and `_commit` use the existing `SemanticTransactionKernel`. A successful commit adds one function and one revision. Validation checks every existing normalized function, the complete dependency edge set, signature, both MIR engines, host-owned results and fresh portable replay.

After a successful host validation, the host requests a checkpoint. It binds the ordered completed prefix to the sequence-contract fingerprint, revision, normalized semantic fingerprint, portable handle set, signatures, dependency graph and validation status. Only then may the trusted host progression method activate the next step. That method is not registered in the TypeScript Pi extension or active tool inventory.

A sequence is not one atomic transaction. If a later step fails, its successfully committed prefix stays authoritative. Recovery requires both the portable constructor prefix and matching checkpoint. The shared Cycle 31 replay path reconstructs and independently validates each prefix before the next configured step is activated.

The supported signature remains one numeric parameter and numeric result, matching the existing constructor gateway. The two configurations exercise both one-callee and two-callee functions without adding name-based production branches.
