# Cycle 33 baseline audit

## Repository state

Verified before implementation:

- HEAD: `51befa0003356d83cc51ae7bc89a98742104140e` (Cycle 32 evidence commit).
- Branch: `experiment/mir-aot-correctness-cycle3`.
- Existing unrelated MPDecimal and historical BASIC files were dirty/untracked. They are preserved and not included in Cycle 33 commits.

Cycle 32's pre-registered mission is in `../cycle32-marginal-mission/MISSION.md`; its blocker report remains unchanged.

## Responsibility boundaries

| Responsibility | Existing owner | Finding |
|---|---|---|
| Canonical program state and mutation | `basic_workspace/model.py` | Supports typed constructor, rename, and numeric literal edit operations with revision checks |
| Atomic preview / commit | `transaction_kernel.py` | Stores candidate/operation fingerprints, checks revision and invokes caller revalidation before one atomic Workspace application |
| Live authorization | `cycle19_gateway.py`, `cycle20_gateway.py`, `cycle26_gateway.py`, `cycle29_gateway.py` | Policies are correct for their campaigns, but their initialization, mission progression and target/oracle assumptions are specialized |
| Portable historical reconstruction | `basic_workspace/portable_replay.py` | One bounded dispatcher for six families; supports create, rename and multi-target numeric edit; it does not authorize live agent requests |
| Projection and binding | `projection.py`, semantic helpers loaded by legacy gateways | Gives normalized function structures and bound call edges |
| Independent execution | `mir_execution.py` | Executes either interpreter or JIT; host profiles must provide expected values independently |
| Transport | `extension.ts`, `gateway.py`, `cycle20b_dispatch_probe.ts` | Real TypeScript tool handlers communicate via loopback JSONL; tool schema/dispatch is mode-selected |
| Evidence attestation | campaign reports and tests | Checks stream against committed snapshots, identities and host observations; separate from replay dispatch |

## Baseline physical LOC

Rule: `wc -l` physical lines, comments and blanks included; generated outputs/tests excluded from production totals.

| Component | LOC at baseline |
|---|---:|
| Workspace core (`model.py`, `projection.py`, `typed_expr.py`, `mir_execution.py`) | 3,709 |
| Shared portable replay | 439 |
| Shared transaction kernel | 121 |
| JSONL gateway server/transport | 759 |
| Legacy mission gateways Cycle 19 / 20 / 26 / 29 | 2,970 |
| Pi TypeScript extension | 234 |
| Existing Cycle 23 production bridge preflight | 150 |

There is one independent portable replay dispatcher and one shared transaction kernel. There is no existing mission composition dispatcher. The relevant legacy policies correspond to creation, numeric maintenance, rename and extraction; their state progression is independent. Cycle 32's Cycle 23 production bridge test and the full 249-test baseline passed. Cycle32 also had 80 recorded subtests.

## Two implementation strategies

### A — Generalize legacy gateways

Would require untying Cycle19's fixed two-function phases from its empty seed; adapting Cycle20's Cycle19B-specific reconstruction and one-function edit request to accept cross-function edits; bringing Cycle26 rename policy into the same lifecycle; and providing ordered step progression. This touches multiple 800–1,100 LOC gateways and risks changing historical assumptions. The baseline gateways remain necessary for old campaigns, so a large in-place generalized implementation does not naturally delete them.

### B — Bounded coordinator (selected)

One host-owned coordinator supports exactly: `create_numeric_function`, `rename_symbol`, `edit_numeric_literals`, plus an explicit validation step. Its immutable JSON plan declares order, expected revision, handles/targets, function invariants and a host validation profile ID. Explicit Python branches validate each operation shape and authorize against the current projection; there is no user-supplied callback/policy code. It uses the existing `Workspace`, `SemanticTransactionKernel`, MIR service, projection helpers, JSONL `Server`, Pi extension, and `portable_replay` for reconstruction only. Legacy gateways stay unchanged.

Expected before implementation: approximately 350–550 net Python LOC plus a bounded TypeScript schema/tool branch and deterministic tests. One new gateway/coordinator class, no new transaction or replay class/family. Both validation profiles for Mission A and B will be present before either mission executes; Mission B should add only contract/evidence/test data and no production behavior.

## Design checkpoint / falsifiers

Selected approach: B. Intended changes: add the coordinator, two host-owned validation profile functions, one composable Pi preview schema/handler selection, deterministic fixture/preflight and tests. Existing shared components reused: Workspace mutations, `SemanticTransactionKernel`, Cycle31 portable replay, MIR executor, TypeScript bridge/server. No legacy runtime removal is planned because the old gateways remain historical campaign entry points.

Architecture benefit is falsified if the coordinator duplicates a full replay resolver, adds a second transaction lifecycle, exceeds the 700 net production LOC stop line, needs mission-name branches, changes historical gateway behavior, or Mission B requires additional production code after Mission A passes. If the TypeScript bridge cannot dispatch the same bounded operation schema for both missions, Level 3 fails.
