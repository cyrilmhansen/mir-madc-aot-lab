# Cycle 26 rename feasibility audit

## Existing Workspace behavior

`Workspace.rename_symbol` already provides the required canonical operation. It resolves a symbol ID, validates BASIC identifier and keyword rules, preserves type suffixes, rejects same-scope collisions, and updates the declaration token plus the symbol's bound `references`. It preserves token UIDs and recomputes source columns before the transaction reindexes the candidate. Function identity, parameter identities, assignment identities, and call bindings are therefore attributes/references of the existing symbol rather than products of its spelling.

The operation is applied through the existing revision-checked `Workspace._transaction` path. Preview and commit use the existing `SemanticTransactionKernel`; Cycle 26 adds no mutation primitive and no transaction lifecycle.

## Revision-8 source and identity baseline

The authentic seven-operation Cycle 25 stream reconstructs revision 8 from an empty Workspace. It remaps 18 portable identities and reproduces the saved normalized structure, function-call edges and MIR observations. Cycle 25's preserved revision-8 display has indentation-only differences from the corrected replay. The replay compares line contents after trimming leading/trailing whitespace and verifies normalized semantics; historical snapshots are retained unchanged.

`clamp_score.function` remains the portable identity after rename. Discovery and inspection expose the same handle alongside the current source spelling, so the handle's old name is not used to infer the current function name.

## Policy boundary

The host-owned contract permits one transaction against the discovered `clamp_score.function`, from expected name `CLAMP_SCORE` to `NORMALIZE_SCORE`, at revision 8. The candidate is built by applying `rename_symbol` to a cloned Workspace. Authorization requires:

- The complete normalized candidate to equal the baseline except for that function's `name` field.
- Exactly the target symbol's declaration and bound-reference token IDs to change text.
- All token IDs and the 18 portable mappings to remain stable.
- All dependency edges, compared by portable caller/callee identity, to remain unchanged.
- The target symbol to have the requested new name and all its bound source tokens to use it.

The gateway obtains preview and commit records from `SemanticTransactionKernel`, and reruns authorization and revision checks immediately before commit.

## Production bridge preflight

The actual TypeScript Pi handler and JSONL gateway accepted the generic four-field rename request and exposed exactly five tools. Its serialized active schema is 1,387 bytes and contains no mission-specific symbol or names. The preflight proved non-mutating preview, revision-9 commit, host validation, replay, duplicate-commit rejection, unknown-field schema rejection, stale revision and target denials. Native `Workspace.rename_symbol` collision and invalid-name controls were run on a clone before commit. A separate deterministic inverse operation restored the revision-8 canonical source byte-for-byte.

## Implementation-size assessment

No changes were made to `Workspace.rename_symbol` or the canonical token model. The Cycle 26 gateway adapter is 335 lines, but it subclasses Cycle 25's seven-operation replay, semantic normalization, engine runner, Pi event recording and presentation lifecycle. Its own candidate authorizer calls `rename_symbol`; its preview/commit wrappers call the existing transaction kernel. It does not add a second authoritative mutation or transaction implementation. The runner and deterministic preflight are 107 and 78 lines respectively. The TypeScript change adds one small generic schema/tool handler; the shared dispatch probe adds the `rename` mode.
