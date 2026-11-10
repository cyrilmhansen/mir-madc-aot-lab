# Mission A — Shared provider rename

The exact Cycle35 Mission A creation sequence creates BOUNDED_SCORE, IS_PASSING, IS_EXCELLENT, and HIGH_PRIORITY at revisions 2–5. The final host checkpoint and receipts are handed to a separate Cycle37 rename gateway.

The host contract in `RENAME-CONTRACT-A.json` permits `bounded_score.function` to change source spelling from `BOUNDED_SCORE` to `NORMALIZED_SCORE`, with revision 5 as the base. The exact creation configuration is `MISSION-A.json`. The other three functions and dependency graph are constrained to remain unchanged. The portable handle and all function, parameter, statement, and token identities remain stable.

The actual TypeScript handler and JSONL gateway completed discover, inspect, accepted non-mutating preview, atomic commit, and host validation. The resulting state is revision 6. The four-function independent observations and prefix replay evidence are in `mission-a-results.json`, `mission-a/revision-snapshots.json`, and `mission-a/independent-oracle-observations.json`.
