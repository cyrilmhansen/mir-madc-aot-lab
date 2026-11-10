# Cycle 38 pre-implementation audit

## Baseline

- HEAD: `a64a3efbaf13e50efae7591e5d06eda9fd205b20` (Cycle37).
- Branch: `experiment/mir-aot-correctness-cycle3`.
- Pre-existing worktree modifications/untracked evidence: MPDecimal logs/status, semantic-replay/control-flow artifacts, and earlier Pi preflight evidence. They are unrelated to Cycle38 and remain untouched.
- No inference is authorized.

## Existing responsibilities and history limits

Cycle19 owns typed constructor authorization, step progression and per-revision checkpoints. Cycle36 `verified_handoff.py` authenticates a creation-only operation stream and creation checkpoints. Its schema and verifier explicitly require every operation to correspond to one configured constructor step and final revision `1 + constructor_count`; treating a rename suffix as a creation handoff would weaken that contract.

Cycle37's v2 `Cycle26Gateway` verifies the Cycle36 creation handoff bound to a host-owned rename contract, replays it in a fresh Workspace, and uses the shared rename policy and transaction kernel. After commit it emits a full portable stream containing constructors plus one `rename_symbol`, a host validation receipt, and history. That output is not an authenticated destination for Cycle20: its creation handoff anchor binds the rename contract, not a later maintenance contract.

Cycle20 already accepts an operation stream/history/validation baseline and replays through `PortableReplay`, including a rename as the final operation. It also has a `verified_handoff` option, but that option intentionally calls the creation-only Cycle36 verifier. The direct stream arguments alone are not a provenance boundary. The v2 per-target policy, preview, commit revalidation, oracle and `SemanticTransactionKernel` are already suitable for the maintenance suffix.

The TypeScript extension already exposes five tools each for creation, rename and numeric maintenance. The production bridge tests execute their registered handlers through JSONL; no new model-facing operation is needed.

## Missing boundary

Cycle20 needs a host-authenticated baseline attestation for exactly: a verified Cycle36 creation handoff plus one committed and host-validated Cycle37 rename. It must verify that the post-rename history is the authenticated construction prefix plus the exact authorized rename, remap all live portable identities, preserve dependency edges, and compare fresh MIR observations with the creation receipt before activating a separate maintenance contract.

The Cycle36 creation handoff must remain creation-only. A valid creation or rename proof must not grant arbitrary maintenance rights.

## Pre-registered design decision

Chosen: **a host-only verified rename continuation receipt**, not a new version of the creation handoff. The receipt binds the source creation bundle and anchor, the rename contract and complete rename evidence, the final semantic fingerprint and identity/dependency ledger, and the destination maintenance contract. A separate host-controlled anchor binds the exact receipt. The receiving Cycle20 process rechecks all evidence, replays the combined history, runs both MIR engines against the authenticated independent construction oracle, and only then writes a small in-process baseline adapter consumed by Cycle20's existing stream loader.

This keeps provenance claims explicit and avoids making the generic creation verifier understand heterogeneous streams. It reuses `verify_handoff`, Cycle37's shared rename policy and transaction lifecycle, Cycle31 `replay_constructive_stream`, and Cycle20's current replay/maintenance implementation. The Cycle20 adapter is derived only after verification and is not accepted from the agent or as an unauthenticated input.

### Alternatives compared

| Approach | Reuse | Trust boundary | Cost/risk |
|---|---|---|---|
| Extend Cycle36 `verified_handoff` to accept rename | Could reuse parts of the creation verifier, but would change the meaning of the creation-only schema and weaken its constructor-count/revision invariant | Creation and rename provenance become one polymorphic proof | Rejected: couples Cycle36 to a new operation family and risks legacy consumers |
| Separate, narrow Cycle38 rename continuation verified by Cycle20 | Calls the existing Cycle36 verifier for the constructor prefix, existing Cycle37 contract/policy checks, shared replay, MIR execution and Cycle20 authorization | Explicit new proof shape, destination contract digest and external host anchor; no arbitrary Workspace transfer | Selected: 360 LOC new verifier and 52 LOC receiver adapter; one extra verification/replay pass, but no new authority framework |

Falsifiers recorded before implementation were: caller-provided mutable document accepted; self-hash mistaken for external trust; contract substitution accepted; maintenance activated before replay and oracle checks; or a second mission needing special runtime code.

## Anticipated impact and falsifiers

Expected: one bounded continuation verification/builder module, an opt-in Cycle20 initializer/CLI branch, bridge runner/tests/evidence. No Workspace primitive, tool, transaction lifecycle, or replay dispatcher. The design is falsified if the receiver accepts caller-supplied mutable program state; if it trusts self-hashed bundle contents without the separate host anchor; if a source handoff bound to another rename/destination contract passes; if Cycle20 activates before replay/oracle validation; or if both longitudinal missions need different production code.
