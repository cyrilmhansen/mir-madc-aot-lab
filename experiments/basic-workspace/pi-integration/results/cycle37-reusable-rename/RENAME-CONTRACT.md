# Reusable rename contract

`RENAME-CONTRACT-A.json` and `RENAME-CONTRACT-B.json` are host-owned v2 rename contracts. `MISSION-A.json` and `MISSION-B.json` preserve the exact Cycle35 creation-sequence configurations. Rename contracts use the `basic-workspace.semantic-rename-contract` schema and are separately bound to their Cycle36 handoffs by the trusted destination contract digest.

The contract fixes mission/profile identity, base revision, portable target handle, expected current spelling, sole permitted new spelling, unchanged function handles, dependency invariant, validation inputs, and required one-revision increment. Unknown keys and versions fail closed. The model request contains only `expected_revision`, `function_handle`, `expected_name`, and `new_name`; it cannot supply authorization policy.

The shared policy resolves a discovered portable handle, checks the contract and current symbol spelling, applies canonical `rename_symbol` to a cloned Workspace, and compares the complete candidate. It verifies that the token identity set remains fixed, that only the declaration and symbol-bound references change spelling, that normalized structure changes only at the authorized name, and that dependency edges stay equal by portable identity. The transaction kernel previews and revalidates this same policy before one atomic commit.

Legacy Cycle26 v1 keeps its historical baseline and contract semantics. It is routed through the same candidate authorization helper. V2 handoff verification authenticates a baseline; it grants no rename authority by itself.
