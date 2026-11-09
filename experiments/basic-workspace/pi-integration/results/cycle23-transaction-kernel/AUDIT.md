# Cycle 23 transaction audit

## Verified baseline

The repository was at `3acb333b43e439a35e495ea38e5fff5b8b8969e1` on `experiment/mir-aot-correctness-cycle3`. Existing unrelated changes and untracked evidence were present before this cycle and remain outside the Cycle 23 staging set. The Cycle 22 report records 203 Workspace tests. No model inference was run.

## Responsibility map

| Component | Owns | Does not own |
|---|---|---|
| `extension.ts`, `gateway.py` | Pi tool registration, TypeBox request validation, loopback JSONL framing, request/tool-call correlation, transport timing | Mission authorization or semantic mutation rules |
| `cycle19_gateway.py` | Typed function construction, allowed signature/dependency, portable function/statement aliases, construction oracle, replay and creation-specific history | Canonical transaction implementation |
| `cycle20_gateway.py` | Host-owned numeric edit contract, typed target/path resolution, preserved-function/dependency checks, impact and candidate oracle, replay and maintenance evidence | Canonical transaction implementation |
| `transaction_kernel.py` (new) | Revision-checked Workspace preview, opaque preview ID, immutable candidate/operation snapshot, revalidation boundary, operation/candidate equality check, atomic `Workspace.apply_transaction` | Authorization, handles, mission policy, MIR or replay semantics, transport metadata, campaign reports |
| `draft_protocol.py` | Temporary graph draft and draft-local revision/batch semantics | Authoritative Workspace preview/commit lifecycle; its semantics intentionally remain separate |
| `Workspace` | Sole authoritative document revisions, semantic validation, atomic application, identity allocation | Mission-specific permission policy |

`gateway.py` is primarily a transport/seeding adapter. Its similarly named dispatch handlers delegate to campaign gateways and did not contain an equivalent independent preview/commit kernel. Draft protocol operations also have different lifecycle semantics and were not migrated.

## Before/after duplication

Before Cycle 23, Cycles 19 and 20 separately generated preview IDs, retained operation/candidate records, rejected stale commits, re-ran their own authorization, compared the preview candidate, and applied one Workspace transaction. They differed in candidate format, alias checks, semantic policy, preview evidence, and post-commit verification. Those differences remain in their gateways.

After Cycle 23, both gateways call `SemanticTransactionKernel.preview` and `SemanticTransactionKernel.commit`. Each supplies its own candidate builder and commit-time authorization callback. The kernel invokes the Workspace preview API exactly once and applies the authorized operations exactly once. Their result envelopes, mission history, visual events and identity checks remain campaign-specific.

The kernel does not deduplicate repeated preview requests: the existing protocol has no semantic operation idempotency key, and a transport request ID is not such a key. Recommitting the same accepted transaction after its first commit returns `STALE_REVISION`, matching both prior gateways. Transport correlation stays in the bridge/gateway journals and is not passed into semantic operation arguments.

## Presentation evidence

No visual-event schema was changed. Creation previews/commits and numeric edit previews/commits retain their existing fields and snapshots. The historical renderers remain covered by the Cycle 22 and prior campaign tests. Narrow viewport layout and edit-diff placement remain presentation issues, outside this transaction refactor.
