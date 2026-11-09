# Cycle 29 feasibility audit

## Baseline and evidence

The campaign reconstructs the ten authentic committed Cycle 28 operations into a new empty Workspace. The gateway requires revision 11, 23 portable handles, the saved normalized revision-11 commit snapshot, the saved execution profile, and host interpreter/JIT observations to match before it serves tools. It does not parse or import rendered BASIC source.

The selected first `SCORE_CLASS` statement is a typed `IfBlock`, but IF markers have no standalone statement identity. The gateway identifies it by function handle `score_class.function`, body path `[body, 0]`, portable typed-block fingerprint, and the two stable branch assignment handles. The branch result assignments target `SCORE_CLASS`'s result symbol, so they cannot be transplanted as assignments into the new helper's different result scope.

## Existing operation capabilities

- The function constructor already supports numeric parameters, typed calls, comparisons, IF branches, result assignments, binding, and canonical token emission.
- The shared `SemanticTransactionKernel` already supplies revision-bound preview records, candidate fingerprints, and atomic commit revalidation.
- The existing Workspace had condition replacement and typed IF insertion, but no operation to replace an existing IF block with statements in place.
- Decomposing block removal and statement insertion into separate commits would expose an invalid intermediate program and would not retire identities atomically.

## Narrow Workspace addition

The new `replace_typed_if_block` transaction operation is structural and typed. It resolves a revision-bound control path and stable in-block statement anchor, checks a fingerprint and the explicit retired-statement ID set, then emits typed result assignments through the existing expression parser, binder, token emitter, projection rebuild, and transaction engine. It rejects ambiguous paths, stale revisions, wrong anchors, mismatched retired IDs, comments or colon-separated syntax within the token span, unsupported block contents, and malformed replacements. The host Mission B contract compares the whole candidate against the captured revision-12 baseline and permits only the selected-block replacement and its associated dependency-edge migration.

The operation changes no unrelated function and does not reparse source text. The physical token span is located from canonical token structure; source rendering is used only by the viewer.

## Identity migration

The selected IF has no independent semantic ID. Its two branch assignments, `score_class.statement.0` and `.1`, are retired because their statements no longer exist. They are not moved to the helper: the helper has its own result scope and newly constructed assignments with fresh IDs. The replacement result assignment receives a fresh statement identity, `score_class.statement.extracted-base-call`. The helper, its parameter, and its three constructor-created statements receive new handles. Existing functions, parameters, later SCORE_CLASS statements, and unrelated statement identities remain live. Preview UUIDs are not reused at commit; committed IDs are obtained from the Workspace transaction receipt. The machine-readable migration is `identity-migration.json`.

The dependency graph changes intentionally. Before Mission B, `SCORE_CLASS → NORMALIZE_SCORE` supplied the first classification. After extraction, that edge is replaced by `SCORE_CLASS → BASE_SCORE_CLASS`, and the new helper has `BASE_SCORE_CLASS → NORMALIZE_SCORE`. The later calls to `IS_PASSING` and `IS_AT_CAP` remain unchanged.

## Production bridge preflight

The deterministic preflight invokes the registered Pi TypeScript tool handler, its actual TypeBox schema, the loopback JSONL bridge, and the same Python gateway methods used by Pi. It checks non-mutating previews, commits, validation, replay, duplicate commits, transport correlation, and mission denials. The first schema capture revealed that block replacement's assignment value schema omitted bound function calls. The production schema was corrected to permit a numeric literal, parameter reference, or bound call; gateway policy still validates discovery, signature, identity, scope, and complete candidate. The follow-up run in `deterministic-preflight/production-bridge-02/` passed both operation families. The earlier captured failure is retained in `production-bridge/` as diagnostic evidence; it is not model activity.

The two operation schemas expose 5 tools each. Follow-up TypeBox captures measure 6,927 compact / 29,009 pretty JSON bytes for function creation, and 2,704 compact / 7,218 pretty bytes for block replacement. Pretty captures include indentation; compact captures are serialized schema arrays. These are tool schema bytes, not provider token counts.

## Scope

No BASIC language feature, interpreter, JIT, or transaction lifecycle was added. One canonical typed block-splice operation was added and both Cycle 29 missions use the shared kernel. This is not evidence that arbitrary control-flow extraction is supported: the bounded operation currently accepts a verified IF block and typed result assignments, and the tested source-span restrictions are explicit.
