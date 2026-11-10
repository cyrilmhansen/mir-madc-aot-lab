# Cycle 37 pre-implementation audit

## Repository baseline

- HEAD before changes: `58af97900d0f318144a97e1d98190be7cff84cc0` (Cycle 36).
- Branch: `experiment/mir-aot-correctness-cycle3`.
- The worktree already contains unrelated semantic-replay/control-flow artifacts and MPDecimal logs, plus earlier Cycle35/36 evidence. They are preserved and excluded from Cycle37 staging.
- No model inference is in scope.

## Existing rename responsibilities

`cycle26_gateway.py` is 335 lines and subclasses Cycle25. Its initializer reconstructs the authentic Cycle25 revision-8 SCORE_CLASS history, checks 18 identities and historical validation, and records display-format drift. These are campaign-specific bootstrap checks.

The candidate authorization is concentrated in `_candidate`: strict request keys, current revision, discovery, stable portable handle, expected old spelling, authorized new spelling, canonical Workspace `rename_symbol`, token-ID preservation, exact declaration/reference changes, full normalized comparison modulo one name, and dependency preservation. The last behavior is already a suitable reusable authorization core, but its inputs and expected name are module constants.

The preview/commit path uses `SemanticTransactionKernel`, and commit reruns candidate authorization before applying one canonical Workspace transaction. The rest of the gateway includes mission-specific inspection labels, validation function names, fixed revision/count reporting, visualization, history, and a replay wrapper.

The canonical Workspace rename operation resolves a bound symbol and updates its declaration and bound references. The existing TypeScript extension already exposes the strict `workspace_preview_rename` request shape; no schema change is needed.

Cycle31 `replay_constructive_stream` already handles constructor and rename operations. Cycle36 `verified_handoff.py` independently verifies a creation stream, every checkpoint and host receipt, then binds the destination by `mission_id` and exact contract digest. It has no numeric-maintenance-specific policy requirement. Its bundle format can therefore authenticate a rename contract as the destination without changing the handoff schema.

## Responsibility map

| Responsibility | Reusable source | Cycle26 specialization |
|---|---|---|
| Canonical rename and bound-reference update | Workspace `rename_symbol` | None |
| Portable operation replay | Cycle31 dispatcher | Cycle26 adds validation around a final rename |
| Transaction preview/commit | `SemanticTransactionKernel` | Rename-specific revalidation callback |
| Target authorization and exact candidate comparison | Cycle26 `_candidate` | Target/name/revision constants |
| Baseline authenticity | Cycle36 verified handoff | Cycle26 uses historical Cycle25 snapshots instead |
| Expected behavior | Host validation receipts + MIR engines | Fixed three-function result keys and counts |
| Tool schema/transport | Existing TypeScript rename tool and JSONL bridge | Existing `rename` authoring mode |

## Pre-registered design choice

Selected: **extend Cycle26Gateway with an explicit v2 verified-handoff initialization mode and extract its rename candidate authorization into one shared, contract-driven helper used by v1 and v2.** The legacy v1 initializer remains the default and keeps its historical source checks. V2 requires a separate trust anchor, a host-owned strict rename contract, and Cycle36 verification before any rename tool is available.

This is smaller than a new gateway or a shared mutable Workspace transfer. It preserves independent process reconstruction, reuses the Cycle36 verifier and Cycle31 replay, and keeps one rename authorization and transaction path. The v2 baseline oracle is the authenticated Cycle35 final host receipt, already checked against the sequence's independent expected results by Cycle36 verification; results are keyed by portable handle for before/after comparison.

The Cycle36 handoff schema will not be altered. The destination contract's own ID and bytes are already bound by the external anchor.

## Expected implementation and falsifiers

Expected production changes: a small shared rename-policy helper, a v2 initialization/validation path in the existing Cycle26 gateway, no TypeScript changes, no Workspace changes, no transaction/replay changes. No new gateway class.

The design is falsified if v2 needs duplicated handoff verification, mission-name branches, a second transaction callback/lifecycle, or if the legacy production preflight no longer reconstructs and authorizes only CLAMP_SCORE → NORMALIZE_SCORE. Identity/binding or oracle mismatch is a correctness blocker.
