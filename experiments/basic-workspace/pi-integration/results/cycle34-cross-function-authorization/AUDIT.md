# Cycle 34 audit and pre-registration

## Baseline

- HEAD: `d039476604e67e0003ac2ef9055c03c4530a1ede`
- Branch: `experiment/mir-aot-correctness-cycle3`
- The working tree contains pre-existing unrelated BASIC visualization and MPDecimal modifications/untracked evidence. They are preserved and excluded from Cycle 34 staging.
- No Cycle 34 source changes had been made at the time of this audit.

## Responsibility map

| Layer | Existing implementation | Cycle 34 finding |
|---|---|---|
| Operation validity | `Workspace.preview_transaction_semantics` and `Workspace.apply_transaction` | Already accepts a list of canonical edits across function IDs and applies/rolls back the batch atomically. |
| Mission authorization | `Cycle20Gateway._discover_authorized_targets`, `_make_workspace_operations`, `_authorize_candidate` | Contract targets and edit conversion are per-target. `_make_workspace_operations` additionally requires one request-level `function_handle` and rejects any edit targeting another function. This is the concrete restriction. |
| Transaction lifecycle | `SemanticTransactionKernel` | Already provides preview, candidate fingerprinting, revision checks and commit revalidation. No change intended. |
| Portable replay | `PortableReplay.apply_operation` for `edit_numeric_literals` | Each edit already resolves its own target function handle and applies one canonical transaction. The envelope additionally requires a legacy top-level function handle. Clarify the envelope with an opt-in `per_target` form while preserving legacy records. |
| Presentation/host validation | Cycle20 preview, commit and `validate_current` | Most affected-function and target logic already reads each edit's target. Preview focus and the committed operation envelope still read the legacy top-level handle. |
| Tool transport | `extension.ts` and `cycle20b_dispatch_probe.ts` | The edit schema requires top-level `function_handle`; add a separate strict v2 authoring mode whose request has explicit `scope_mode: "per_target"`, and use the actual production handler/JSONL bridge. |
| Independent evidence | Cycle20 host oracle and replay verification | Existing `clamp` and `threshold_call` oracle types suffice for both contracts. No new oracle execution engine is needed. |

## Baseline code size (production files)

| File | Lines before |
|---|---:|
| `cycle20_gateway.py` | 1,161 |
| `transaction_kernel.py` | 121 |
| `basic_workspace/portable_replay.py` | 439 |
| `extension.ts` | 234 |
| `cycle20b_dispatch_probe.ts` deterministic bridge harness (not runtime) | 103 |

The edit authorization path is one implementation, but its request parser embeds a one-function invariant. The canonical mutation list, shared transaction kernel and replay dispatcher are already singular.

## Frozen minimal change

1. Keep version-1 contract and request fields unchanged and single-function scoped.
2. Add a strict version-2 contract field `scope_mode: "per_target"`. Its request shape is `{expected_revision, scope_mode, edits}`; no top-level function handle is accepted.
3. Extract the common per-edit/count/authorized-target validation into one helper. The v1 caller supplies its selected function scope; v2 supplies no global scope and validates every target against the complete contract allowlist and discovery set.
4. Store v2 history in the existing `edit_numeric_literals` operation family with an explicit `scope_mode: "per_target"` envelope and per-edit function handles. Replay supports both exact envelope shapes in the existing dispatcher.
5. Add one TypeScript mode/schema and deterministic production-path fixtures. No inference, new Workspace operation, gateway class, transaction lifecycle or replay dispatcher.

The top-level v1 `function_handle` will never grant v2 scope. V2 rejects a request containing it or any other unknown field. Exact target set, old-value, replacement, duplicate, count, dependency, token identity and host oracle checks remain host-owned.

## Falsification criteria

The reuse claim fails if v1 and v2 use separate authorization pipelines, if a mixed authorized/unauthorized batch mutates the Workspace, if replay requires a new operation family/dispatcher, or if the second contract requires production branching keyed to its mission ID. The Cycle 20 production bridge must pass both modes.
