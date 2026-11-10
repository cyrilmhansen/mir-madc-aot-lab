# Mission B — Rename in a multi-callee graph

The exact Cycle35 Mission B sequence creates HAS_CREDIT, IS_MINOR, CAN_APPLY, and APPROVAL_FLAG at revisions 2–5. CAN_APPLY retains its two incoming function dependencies, and APPROVAL_FLAG remains bound to CAN_APPLY.

The host contract in `RENAME-CONTRACT-B.json` permits `has_credit.function` to change source spelling from `HAS_CREDIT` to `HAS_NONNEGATIVE_CREDIT`, with revision 5 as the base. The exact creation configuration is `MISSION-B.json`. All other functions and dependency edges must remain unchanged. The portable handle and semantic entity identities are preserved.

This mission used the same Cycle36 handoff verifier, Cycle26Gateway v2 path, shared rename authorizer, transaction kernel, TypeScript schema, and portable replay dispatcher as Mission A. It completed at revision 6 with no Mission B-specific production code. Evidence is in `mission-b-results.json`, `mission-b/revision-snapshots.json`, and `mission-b/independent-oracle-observations.json`.
