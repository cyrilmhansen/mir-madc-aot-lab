# Cycle 25 structural-edit feasibility audit

## Verified baseline

- Repository baseline was `710da2beabfa7feda97651c2ca7b4c645fe79d02` on `experiment/mir-aot-correctness-cycle3`.
- The six committed operations in Cycle 24's `constructive-operations.json` reconstruct revision 7 from an empty document. The normalized projection, call bindings, 17 portable handles and interpreter/JIT observations match the preserved Cycle 24 evidence.
- The authoritative Workspace already supports revision-checked, atomic `apply_transaction` on a cloned candidate. Existing creation lowering already parses typed expressions, emits canonical tokens, reindexes bindings, and assigns identities to result assignments.

## Feasibility and smallest addition

There was no general operation to insert a typed IF into an existing function. Replacing the whole function body would discard statement identities and make the maintenance boundary too broad. The minimal addition is `insert_typed_if_block`, which accepts a function identity, a verified result-epilogue statement anchor and a typed IF tree. It uses the existing typed expression parser and expression token emitter, validates the new references after reindexing, and applies as one Workspace transaction.

`_insert_statement_lines_before` is now shared by constructor lowering and structural insertion. The first version of that extraction inserted after the anchor line's existing whitespace. This caused formatting drift in reconstructed code while normalized semantics remained equivalent. The insertion point was corrected to the first token on the anchor line. A regression test now compares the reconstructed revision-7 display snapshot byte-for-byte with the preserved Cycle 24 snapshot.

## Identity model

- Existing function IDs, parameter IDs, statement IDs, and token identities in the 17 portable handles survive the candidate edit.
- The Workspace does not assign standalone identities to IF/ELSE/END IF marker lines; none are fabricated.
- The new result assignment gets one real statement identity, exported as `score_class.statement.category50`.
- The full replay resolves all 18 portable handles afresh. The original 17 remain semantically equivalent, and the new assignment receives the eighteenth mapping.

## Authorization and transaction boundary

The Cycle 25 gateway compares a typed candidate projection with the revision-7 baseline. It permits only one top-level IF before the verified `SCORE_CLASS = SCORE_CLASS` epilogue, using the discovered `CLAMP_SCORE` call and the authorized equality-to-50 condition, assigning result 3. Existing statements and both other functions must remain unchanged; dependencies cannot be added or removed. Preview and commit use the existing `SemanticTransactionKernel`; there is no new transaction lifecycle. The policy is intentionally mission-specific and is not an OS-level security boundary.

## Production-path preflight

The deterministic preflight captured the actual five Pi tools and a 14,957-byte JSON schema, then invoked the TypeScript handler and JSONL gateway. It verified an isolated preview without mutation, commit at revision 8, MIR validation, and fresh replay. Scope, anchor, dependency, condition, stale-revision and unsupported whole-body cases were rejected. No inference was performed during preflight.
