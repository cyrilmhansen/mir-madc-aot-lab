# Cycle 35 report — configurable sequential creation

## Result

Both host-owned four-step programs were built from empty revision 1 through the production TypeScript tool handlers and JSONL gateway, with no model inference. Every function was individually previewed, committed as one atomic transaction, checked against an independent host oracle through MIR interpreter and JIT, checkpointed, and followed by explicit host progression.

- Mission A reached revision 5 with `BOUNDED_SCORE`, `IS_PASSING`, `IS_EXCELLENT`, and `HIGH_PRIORITY`.
- Mission B reached revision 5 with `HAS_CREDIT`, `IS_MINOR`, `CAN_APPLY`, and `APPROVAL_FLAG`.
- CAN_APPLY's sequential result assignments produce 1 for a nonnegative input before 18 and reset it to 0 when the second condition marks it minor. The exact specified eligibility behavior passed in both MIR engines.
- Each revision prefix replayed through the shared Cycle 31 dispatcher and matched that revision's normalized committed snapshot, declared dependency graph, portable handle set, and independent finite oracle.
- Mission B resumed from a verified two-constructor prefix at revision 3 and finished through the normal sequence path.
- All portable function, parameter, and statement handles were retained; no handles were retired or reused.

No Pi/Sushi inference was authorized or performed. The typed bodies in `cycle35_preflight.py` are deterministic bridge fixtures, not model-generated work.

## Production path

The active tool inventory remained the existing five creation tools. The actual TypeScript handler schemas accepted valid typed constructors and rejected an unknown semantic field. Python rejected unauthorized function names, stale revisions, and invented callees before mutation. The sequence advancement endpoint was called only by the host harness and does not appear in the active Pi tools.

A first bridge harness attempt failed in its own oracle comparator after the first Mission A validation: it compared every eventual function against a prefix that contained only BOUNDED_SCORE. That failure is preserved at `production-bridge/`. The corrected comparator and final host-only validation/checkpoint rules pass in `production-bridge-attempt-06/`. The gateway and semantic authorization were not weakened to correct the harness.

## Acceptance levels

- **Level 0 — Blocker:** cleared for the scoped create-only sequence.
- **Level 1 — Configurable creation:** passed for Mission A; four separate commits, revisions 2–5.
- **Level 2 — Semantic correctness:** passed at all eight mission prefixes, including both MIR engines and independent reference results.
- **Level 3 — Replay and recovery:** passed for every prefix and for Mission B resumed after revision 3.
- **Level 4 — Production integration:** passed through real TypeScript extension handlers and JSONL dispatch; prior constructor tests remain green.
- **Level 5 — Generalization:** passed for the second, differently shaped dependency graph with zero Mission B production changes.
- **Level 6 — Scoped architectural consolidation:** the new mode removes the need for another campaign-specific sequence gateway within numeric function creation. It remains bounded to one numeric parameter and does not generalize maintenance or rename.

## Interpretation

The reusable per-function path was already present; the missing mechanism was validated, ordered progression between creation contracts. Extending the existing Cycle 19 gateway kept authorization, canonical mutation, transaction handling, identity allocation, and replay shared. The second program needed only distinct contract data and independent oracle fixtures.

The sequence adapter is not free: it adds 336 net production lines to `cycle19_gateway.py`, primarily for strict plan validation and checkpointed prefix recovery. That is substantially narrower than the removed Cycle 33 820-line draft and does not introduce a general workflow engine. It is a moderate one-time cost with zero additional production lines for Mission B. Whether this is the right tradeoff for more than eight steps or heterogeneous operations remains untested.

## Evidence

See `AUDIT.md`, `ARCHITECTURE.md`, `METRICS.md`, `REGRESSION.md`, `mission-a-results.json`, `mission-b-results.json`, `identity-ledger.json`, `replay-equivalence.json`, `negative-controls.json`, `recovery-validation.json`, and `bridge-validation.json`. Historical Cycle 34's derived report summary was corrected from 254 to the 256 tests stated by its preserved raw regression log; no raw evidence was rewritten.
