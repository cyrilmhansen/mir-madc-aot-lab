# Cycle 33 architecture decision (pre-implementation)

## Selected: bounded mission coordinator

The new `ComposableMissionGateway` will be a narrow live authorization and progression adapter. It will not mutate tokens directly, interpret arbitrary plan code, or replay history. For every mutation it will:

1. Load and strictly validate one host-owned immutable mission plan.
2. Require the current step ID and exact expected Workspace revision.
3. Check operation fields against a fixed, versioned grammar.
4. Resolve portable handles to current Workspace IDs and require discovery for callable dependencies/targets.
5. Construct canonical Workspace operation(s) and validate the candidate through the Workspace preview/projection API.
6. Compare the complete candidate with the baseline plus only the step's allowed semantic delta.
7. Preview using `SemanticTransactionKernel`.
8. Recompute and reauthorize the same step in the kernel commit callback; atomically apply the one step transaction.
9. Record portable constructive operations only after a successful commit. Update identity maps after creation; rename preserves its handle; edits create/retire no identity.
10. Advance the plan only after the step's structural postcondition passes. An explicit final validation step runs an immutable host-owned validation profile over both MIR engines.

The plan contains data only. Validation profiles are selected from a host-owned fixed registry; contracts cannot supply Python callbacks or executable predicates. Step dispatch is an explicit three-case allowlist. Unknown keys, step kinds, profile IDs, target paths, aliases, revisions, or dependencies fail closed.

## Why not extend Cycle 19/20/26 directly?

The existing gateways combine transport handlers, a specific seed loader, mission policy, evidence naming, and campaign phase transitions. Strategy A would have to generalize all three and still add ordered cross-gateway progression. The specialized code would remain for historical evidence, creating parallel branches. Strategy B adds one bounded live adapter while retaining each legacy campaign untouched. Its success is judged by actual two-mission TypeScript/JSONL use and Mission B's zero added runtime logic, not by the class's existence.

## Boundaries retained

- Workspace is authoritative for state and canonical operation application.
- The existing transaction kernel remains the sole preview/commit lifecycle.
- Coordinator policy is host-owned and separate from operation syntax.
- Portable replay reconstructs committed history only; it is not used to authorize proposals.
- Evidence/oracle comparison is separate from replay and from model claims.
- TypeScript selects the coordinator's one preview tool in a dedicated mode; Python makes every authorization decision.

## Planned tool contract

The active Pi tools remain discover, inspect, preview, commit, validate. Preview carries `step_id`, `expected_revision`, and a typed discriminated operation for one of the three supported families. Create bodies use a bounded, finite-depth TypeBox expression grammar sufficient for the two registered programs; no `Type.Any`, arbitrary objects, source replacement, shell, file, or direct mutation tool is exposed. Edit requests can include multiple explicit function targets, but the gateway authorizes the complete batch as one candidate and one commit.

## Planned tests

Exercise contract parsing, step ordering, call discovery, renamed portable handles, multi-function edits, stale previews, tampered plans, invalid bodies/targets, unauthorized changes, no-mutation rejection, current revision progression, portable replay, independent oracles, and the actual extension handler through JSONL. Existing gateway/replay suites remain unchanged.
