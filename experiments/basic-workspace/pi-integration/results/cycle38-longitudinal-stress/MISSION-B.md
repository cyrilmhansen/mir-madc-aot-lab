# Mission B — Three-function age chain

## Executed history

| Revision | Event | Result |
|---:|---|---|
| 1 | Empty Workspace | Verified empty start |
| 2–4 | Create `NORMALIZED_AGE`, `IS_SENIOR`, `SENIOR_FLAG` | Cycle36 configurable creation sequence, actual TypeScript→JSONL handlers, per-revision independent host validation/checkpoints |
| 5 | Rename `NORMALIZED_AGE` to `CAPPED_AGE` | Cycle37 host-owned v2 rename contract; historical identity remains `normalized_age.function` |
| 6 | Atomic Cycle20 v2 edit of three literals across `CAPPED_AGE` and `IS_SENIOR` | Cap comparison/result 100→60 and threshold 65→55 |

## Final behavior

`CAPPED_AGE(X) = min(60, max(0, X))`; `IS_SENIOR(X) = 1` when the capped age is at least 55; `SENIOR_FLAG(X)` continues to call `IS_SENIOR`. The call graph remains the three-node chain and all original functions/statement identities survive.

All functions matched the independent arithmetic oracle and both MIR engines across the 14-input corpus, at each replay prefix and final revision. Complete observations are in `production-bridge-attempt-07/mission-b/independent-oracle-observations.json` and `revision-checkpoints.json`.

Mission B used the same continuation builder/verifier, Cycle37 rename policy, Cycle20 v2 authorization, transaction kernel, Cycle31 replay, and TypeScript schemas as Mission A. No mission-specific production branch was added.

No inference was run.
