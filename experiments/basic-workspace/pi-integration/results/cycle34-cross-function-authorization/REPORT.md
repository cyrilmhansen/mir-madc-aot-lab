# Cycle 34 report — shared cross-function edit authorization

## Outcome

The identified restriction was in Cycle20 request authorization, not the Workspace mutation API or transaction lifecycle. Each edit already resolved its own function identity, and the Workspace already applied operation lists atomically. The gateway imposed one extra global selected-function check.

That check is now isolated as a versioned compatibility boundary. Existing v1 requests still require a top-level selected function and remain single-function scoped. New v2 contracts opt into `per_target`; the request has no top-level function handle, and every edit is checked independently against discovered handles and the host contract's exact target set. Both paths use the same batch authorization helper, candidate verifier, oracle, and SemanticTransactionKernel.

## Primary mission

The production path reconstructed the authentic two-function Cycle19B baseline at revision 3. The TypeScript handler schema-checked three edits across `CLAMP_SCORE` and `IS_PASSING`, the gateway accepted preview without changing revision 3, and one commit moved the Workspace to revision 4.

The committed edits set both cap literals to 50 and the threshold to 45. The dependency edge remains `IS_PASSING → CLAMP_SCORE`. All 11 portable identities survived, no entity was created or retired, and exactly the three authorized literal tokens changed. The separate arithmetic oracle, MIR interpreter, MIR JIT, and fresh portable replay agree on all 16 inputs. The requested 15 inputs are included; 99 is retained as well to cover the authentic Cycle19B baseline evidence.

## Reusable configuration check

Mission B used a separately reconstructed revision-3 Workspace and a different contract: cap 80 and threshold 70. It passed through the same actual TypeScript handler, JSONL gateway, authorization helper, kernel and replay dispatcher. No mission-ID branch or extra production behavior was added. It reached revision 4 in one transaction, preserved all 11 handles, and matched the independent oracle and both MIR engines.

## Safety and compatibility

The real bridge rejected a mixed authorized/unauthorized batch before preview. The v2 TypeBox schema rejected both the old global `function_handle` field and leaked `toolCallId` metadata. Deterministic controls rejected invented handles, unauthorized paths, incomplete/extra/duplicate targets, wrong values, non-finite and Boolean numbers, stale revisions, unknown fields and altered commit revalidation without changing Workspace state. The transaction kernel also rejected a changed candidate fingerprint. Duplicate commit was rejected as stale without another revision.

Legacy Cycle20 requests and constructive streams keep their original shape and behavior. Cycle21 and Cycle23 TypeScript bridge preflights and all historical Workspace tests passed. The portable stream adds only an explicit `scope_mode: "per_target"` form under the existing `edit_numeric_literals` operation; V1 operations remain accepted in their old form.

## Architectural interpretation

This is a bounded positive result: one cross-function semantic edit capability was added to the production gateway that already owned numeric editing. There is still one Workspace, one transaction lifecycle and one replay dispatcher. The second different contract costs zero additional production LOC. The change adds 63 net production LOC across the existing gateway, replay and TypeScript schema; this is not a claim that all campaign gateways are now generic.

## Acceptance level

- **Level 1 — Cross-function atomic authorization:** passed.
- **Level 2 — Independent semantic/replay equivalence:** passed.
- **Level 3 — Production TypeScript-to-JSONL integration and historical regression:** passed.
- **Level 4 — Genuine agent demonstration:** not run; no inference was authorized.
- **Level 5 — Measured reusable authorization:** passed in the scoped numeric-edit domain. V1 and v2 share one authorization implementation; Mission B adds no runtime code. Broader gateway consolidation remains outside this experiment.

Full suite: 254 tests passed. No Pi/Sushi inference was performed. See `METRICS.md`, `REGRESSION.md`, the raw bridge outputs and full observation evidence for details.
