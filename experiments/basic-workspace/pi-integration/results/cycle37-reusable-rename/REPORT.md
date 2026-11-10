# Cycle 37 — Reusable semantic rename after verified construction

## Outcome

Both independently configured programs were built from empty Workspaces using the Cycle35 creation sequence, transferred through Cycle36's host-anchored verified handoff, and renamed by the existing Cycle26 gateway through its actual TypeScript-to-JSONL production path. Each rename committed exactly once, revision 5 → 6. No Pi/Sushi inference was run.

Mission A renamed BOUNDED_SCORE to NORMALIZED_SCORE under the unchanged portable handle `bounded_score.function`. Mission B renamed HAS_CREDIT to HAS_NONNEGATIVE_CREDIT under `has_credit.function`, including CAN_APPLY's multi-callee dependency graph. Both retained all 21 portable identities, all function/parameter/statement/token identities, and the semantic dependency edges. Interpreter and JIT outputs matched the independently authenticated Cycle35 construction receipts before and after rename. The complete constructor-plus-rename histories replayed successfully through the shared Cycle31 dispatcher.

The reusable policy lives in `rename_policy.py`. Both legacy Cycle26 v1 and new authenticated-handoff v2 initialization modes call the same exact candidate authorizer, and both use `SemanticTransactionKernel`. The existing Cycle36 handoff verifier, Cycle31 replay dispatcher, canonical Workspace `rename_symbol`, TypeScript schema, and JSONL transport were reused without changes. Mission B required only its host-owned contract and evidence fixture; it added no production behavior.

## Architecture decision and cost

The implementation extends Cycle26Gateway and extracts its policy instead of adding a second gateway or a mutable in-process Workspace transfer. The receiving process verifies the destination contract against a separate host trust anchor, replays the creation stream into an empty Workspace, checks checkpoint and validation evidence, then activates the independently scoped rename contract.

The cost is 289 net production lines: a 123-line shared policy module and 166 net lines in the existing gateway. The Cycle36 verifier remains 320 lines; the TypeScript extension remains 241 lines. This is meaningful capability and reuse, though not near-zero infrastructure: the v2 bootstrap and generic host validation increase the historic gateway. One authorization implementation now serves both contracts, and Mission B has zero marginal production code. No Workspace mutation, transaction, replay, or tool operation was added.

## Correctness and evidence

- Cycle36-authenticated construction checkpoints were verified at revisions 2–5.
- `revision-snapshots.json` records normalized semantics, function signatures, dependency edges, portable handles, and validation receipt provenance for every constructor prefix and revision 6.
- The final operation stream is four constructors plus one portable `rename_symbol` operation; there are no source-text patches.
- The identity ledger records unchanged handles and the new source spellings. The replay-local UUID mapping is separate from portable identity.
- The accepted preview leaves committed source and revision unchanged. The commit advances exactly one revision.
- Production dispatch evidence includes the active five-tool inventory and compact schema size of 860 bytes.
- Cycle26 legacy preflight passed unchanged in meaning: its historical revision-8 CLAMP_SCORE → NORMALIZE_SCORE contract commits revision 9.
- Focused Cycle37, Cycle26, and Cycle36 regressions passed 19 tests. Full Workspace regression status is in `REGRESSION.md`.

The finite input corpora are independent checks, not proofs over all numeric inputs. Cycle36 authenticates the host-owned expected observations; Cycle37 independently executes both MIR engines against those expectations after fresh reconstruction and rename.

## Failure records and limitations

The first bridge run stopped on a preflight defect, the second exposed an evidence-path mistake, and attempt 4 found an `UnboundLocalError` while building the v2 validation identity mapping. That bug was fixed. Attempt 5 reran both missions through the complete production bridge on the fixed code and passed. All earlier attempts remain preserved. Attempt 5 is the acceptance bridge evidence.

There is no genuine agent evidence by design. The Cycle37 result establishes reusable deterministic host authorization and production integration, not autonomous agent performance. The next rename-to-maintenance composition remains unimplemented; Cycle36's destination contract binding would need a separate authorized handoff and is only assessed as future work.

## Acceptance levels

| Level | Result |
|---|---|
| 0 — Blocker | No blocker: existing canonical rename and transaction path sufficed. |
| 1 — Authenticated rename | Passed for Mission A. |
| 2 — Identity preservation and MIR/oracle agreement | Passed for A and B. |
| 3 — Replay and security | Passed for recorded constructor prefixes, complete streams, trust binding, and deterministic rejection suite. |
| 4 — Production integration | Passed for A and B through TypeScript → JSONL → Python; Cycle26 legacy bridge also passed. |
| 5 — Generalization | Passed: B introduced no additional production code. |
| 6 — Consolidation | One shared rename candidate policy and one gateway/kernel/replay path; net 289 production lines. |
| 7 — Future composition assessment | Not implemented; a separately anchored maintenance destination contract appears compatible, subject to its own validation. |

No push was performed.
