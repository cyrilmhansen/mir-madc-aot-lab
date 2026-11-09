# Cycle 30 architecture and evidence audit

## Reused path

Cycle 30 uses [`cycle20_gateway.py`](../../cycle20_gateway.py) and its `Cycle20Gateway`. The host-owned JSON contract selects one function-anchored numeric literal target, expected value, replacement constraint, unchanged functions, dependency edges, and independent host oracle. Pi sees the same five semantic tools as Cycle 20B/21. The extension forwards `tool_call_id` as transport metadata; the JSONL server keeps that metadata outside `params`.

The gateway uses the existing Workspace `edit_numeric_literal_at_path` mutation and the shared `SemanticTransactionKernel`. No Cycle 30 mutation primitive, transaction lifecycle, TypeScript tool, or gateway class was added.

## Replay/bootstrap gap and narrow fix

The Cycle 20 numeric-maintenance bootstrap already replayed function constructors, numeric edits, inserted IF blocks, and renames, but it could not replay Cycle 28's typed IF condition edit or Cycle 29's `replace_typed_if_block`. It also treated every portable handle as active, so it had no explicit retired-handle ledger.

The bootstrap now resolves those two already-committed typed operations through current Workspace-local IDs, validates the expected typed block and fingerprint, checks removed statement identities, allocates the recorded new statement handle, and removes the two retired handles from the active alias map. It authenticates Cycle 29's first ten operations against Cycle 28, compares the revision-11 and revision-12 committed semantic snapshots, and requires the Cycle 29 revision-13 commit and host-validation retirement attestations. Rendered BASIC is never used as replay input.

The revision-14 full replay performs the same operation families from an empty Workspace, checks active and retired handle ledgers, and compares normalized structure, bindings, observations, and engine agreement.

The `score_class_call` host oracle gained an optional three-field cap branch so the Cycle 30 contract can describe the already-existing cap classification without a mission-specific Python validator. Existing contracts retain the original oracle shape and behavior.

## Identity semantics

Portable handles identify semantic entities across revisions; replay-local Workspace IDs are newly allocated. The two Cycle 29 retired statements are retained only in `retired_handles` and history. They are absent from current `aliases`, discovery and live target resolution. At revision 14, 27 live handles remain and no semantic entity is created or retired by the numeric edit.

The historical retired handles remain resolvable only when replaying their earlier operations up through revision 12. The extraction operation then retires them; the replacement statement receives its separate portable handle.

## Evidence sources

- Cycle 29's authentic 12-operation stream, commit history, validation and identity migration report.
- Cycle 28's authentic 10-operation prefix, revision-11 snapshot and validation.
- Pi's raw JSONL session and Pi tool lifecycle records for the new session.
- MissionGateway history, transaction timing and committed Workspace snapshots.
- Independent MIR interpreter/JIT observations from the host contract oracle.
- The generic code-first frame compiler and standalone HTML generated from the saved presentation events.

A one-run finite input oracle is experimental evidence for the declared corpus, not a proof for all numeric inputs.
