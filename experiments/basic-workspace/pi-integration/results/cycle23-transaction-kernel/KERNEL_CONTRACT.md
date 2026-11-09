# Shared transaction kernel contract

`SemanticTransactionKernel` is a small lifecycle service around one `Workspace` and document ID.

## Preview

The mission gateway first validates typed arguments and policy, builds exact Workspace operations and a normalized candidate, then calls `preview(operation_kind, base_revision, operations, candidate, metadata)`. The kernel checks the current revision, asks Workspace to validate and render the candidate diff, and stores deep copies under an opaque transaction ID. Canonical candidate and operation fingerprints are retained using deterministic JSON plus SHA-256. Preview does not apply operations or advance the revision.

## Commit

The gateway calls `commit(transaction_id, revalidate)`. The kernel verifies the stored preview and base revision, invokes the gateway-owned callback, compares the returned candidate and operation fingerprints with the accepted preview, checks the revision again, then calls `Workspace.apply_transaction` once. It returns a receipt with base/result revision, operation family, operations, candidate, adapter metadata and the Workspace result. The gateway then performs its existing family-specific post-commit checks and reporting.

## Ownership, failures and concurrency

- Workspace remains authoritative; the kernel stores only temporary preview records.
- Candidate metadata may include portable aliases or impact evidence, but the kernel does not interpret it.
- Mission authorization runs before preview and again in the commit callback.
- Missing transaction IDs return `PREVIEW_NOT_FOUND`; changed revisions return `STALE_REVISION`; candidate or operation changes return `PREVIEW_CANDIDATE_CHANGED`.
- A rejected preview or pre-apply commit failure leaves Workspace state unchanged.
- A post-apply integrity failure remains a gateway error after Workspace has committed; no rollback is claimed beyond Workspace's atomic transaction behavior.
- Calls are serialized by the gateway's existing request handling. The kernel itself does not promise parallel use.
- Mission/session transitions explicitly clear uncommitted previews in Cycle 19.
- Preview records currently live for the gateway process lifetime. A global quota, durable preview recovery, and idempotent replay of transport request IDs are not implemented.

Transport fields such as Pi `toolCallId` never enter semantic request objects or this API. JSONL request correlation and historical provenance remain owned by the bridge and campaign gateway.
