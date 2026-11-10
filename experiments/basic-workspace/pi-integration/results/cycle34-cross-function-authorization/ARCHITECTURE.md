# Cycle 34 architecture

## Chosen design

Generalize the Cycle20 numeric-maintenance gateway in place. Do not build the Cycle33 coordinator or a second gateway hierarchy.

The boundary is explicit:

1. **Workspace validity** parses/applies the typed `edit_numeric_literal_at_path` list. The Workspace owns atomic application and rollback.
2. **Mission authorization** in Cycle20 checks a host contract: exact target set, current revision, discovery, original values, replacements, whole candidate semantics, identities, dependency graph and independent oracle.
3. **Transaction lifecycle** stays in `SemanticTransactionKernel`, which fingerprints preview candidates and revalidates before the one atomic commit.
4. **Portable replay** reuses the existing `edit_numeric_literals` dispatcher. Each target resolves its own portable function handle.
5. **Transport** remains the Pi TypeScript handler and JSONL bridge. Version 1 keeps its single-function schema. Version 2 selects explicit per-target scope and has no global function handle.
6. **Historical attestation** remains the gateway's baseline/replay validation and saved host observations; it is not a source of permissions.

## Request contracts

Legacy v1 remains exactly:

```json
{"expected_revision":3,"function_handle":"clamp_score.function","edits":[...]}
```

V2 requires exactly:

```json
{"expected_revision":3,"scope_mode":"per_target","edits":[...]}
```

Each edit target carries its own discovered portable function handle. Unknown fields, a v1 global handle in a v2 request, and every scope mode except `per_target` are rejected. The v1 handler still checks that each edit targets the selected handle. Both routes call `_authorize_edit_batch`; only the v1 route supplies `scope_handle`.

The V2 stream uses the existing operation family and explicit scope envelope:

```json
{"operation":"edit_numeric_literals","mission_id":"...","scope_mode":"per_target","edits":[...]}
```

Historical V1 stream records with `function_handle` continue to replay unchanged. The single shared replay dispatcher accepts only these two exact envelope forms, then resolves every edit target independently. No operation family or replay mechanism was added.

## Commit lifecycle

The preview operation list includes all three edits. The kernel previews/fingerprints that complete candidate at revision 3. Commit calls the same authorization path again against the saved request and current document, then applies the entire Workspace transaction. An invalid member rejects the whole batch. The accepted batch advances revision once, to 4.

No new Workspace mutation operation, language feature, transaction lifecycle or identity resolver was introduced. The two function edits preserve the eleven portable identities and the existing `IS_PASSING → CLAMP_SCORE` dependency.

## Comparison considered

Extending configurable gateways could have meant separately broadening creation, maintenance and rename gateways. The required capability is only numeric multi-target authorization, so broadening multiple gateways would add unrelated policy code. A general coordinator would recreate the overlarge Cycle33 design. Reusing Cycle20's single gateway while extracting its common batch authorization is the smallest applicable change; it directly removes the `one selected function` assumption and keeps all existing policy/oracle code.

Mission B (cap 80 / threshold 70) uses the identical v2 mode and authorization method. It differs only in the host-owned target replacements and oracle contract.
