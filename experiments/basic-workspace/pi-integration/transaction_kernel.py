"""Shared revision-checked preview/commit lifecycle for semantic gateways.

Mission gateways remain responsible for typed-operation validation,
authorization, candidate construction and post-commit semantic verification.
This module owns only the lifecycle around one already-authorized Workspace
transaction.
"""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from basic_workspace.model import Workspace, WorkspaceError


def _fingerprint(value: Any) -> str:
    try:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise WorkspaceError("INVALID_TRANSACTION_RECORD", "Candidate or operations are not canonical JSON") from exc
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class CommitReceipt:
    transaction_id: str
    operation_kind: str
    base_revision: int
    revision: int
    operations: list[dict[str, Any]]
    candidate: Any
    metadata: dict[str, Any]
    applied: dict[str, Any]


class SemanticTransactionKernel:
    """Common Workspace preview/commit lifecycle, with caller-owned policy.

    Calls must be serialized by the owning gateway (the production gateway
    servers already do this).  Each gateway supplies its own ``revalidate``
    callback, which must repeat all mission checks and return the exact
    operations and candidate authorized at preview time.
    """

    def __init__(self, workspace: Workspace, document_id: str):
        self.workspace = workspace
        self.document_id = document_id
        self._pending: dict[str, dict[str, Any]] = {}

    def clear(self) -> None:
        """Forget uncommitted previews at an explicit mission/session boundary."""
        self._pending.clear()

    def preview(self, *, operation_kind: str, base_revision: int,
                operations: list[dict[str, Any]], candidate: Any,
                metadata: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
        current = self.workspace.get_revision(self.document_id)
        if base_revision != current:
            raise WorkspaceError("STALE_REVISION", f"Expected revision {base_revision}, current revision {current}")
        if not operations or not isinstance(operation_kind, str) or not operation_kind:
            raise WorkspaceError("INVALID_TRANSACTION_RECORD", "A transaction needs a kind and at least one operation")
        # Workspace remains authoritative for whether these typed operations
        # form a valid candidate. No candidate is applied here.
        preview = self.workspace.preview_transaction(self.document_id, base_revision,
            copy.deepcopy(operations), include_diff=True)
        if self.workspace.get_revision(self.document_id) != current:
            raise RuntimeError("Workspace preview unexpectedly changed authoritative revision")
        txid = "tx_" + uuid.uuid4().hex
        record = {
            "transaction_id": txid,
            "operation_kind": operation_kind,
            "base_revision": base_revision,
            "operations": copy.deepcopy(operations),
            "candidate": copy.deepcopy(candidate),
            "candidate_fingerprint": _fingerprint(candidate),
            "operations_fingerprint": _fingerprint(operations),
            "metadata": copy.deepcopy(metadata or {}),
            "preview": copy.deepcopy(preview),
            "status": "previewed",
        }
        self._pending[txid] = record
        return txid, copy.deepcopy(preview)

    def commit(self, transaction_id: str,
               revalidate: Callable[[dict[str, Any], int], tuple[list[dict[str, Any]], Any, dict[str, Any] | None]]) -> CommitReceipt:
        record = self._pending.get(transaction_id)
        current = self.workspace.get_revision(self.document_id)
        if record is None:
            raise WorkspaceError("PREVIEW_NOT_FOUND", "No accepted preview exists for this transaction")
        if record["base_revision"] != current:
            raise WorkspaceError("STALE_REVISION", f"Preview is based on revision {record['base_revision']}; current revision is {current}")
        # This callback is deliberately mission-owned. It must recheck policy,
        # revision-bound semantic references and the complete candidate.
        operations, candidate, metadata = revalidate(copy.deepcopy(record), current)
        if _fingerprint(candidate) != record["candidate_fingerprint"]:
            raise WorkspaceError("PREVIEW_CANDIDATE_CHANGED", "Candidate changed since accepted preview")
        if _fingerprint(operations) != record["operations_fingerprint"]:
            raise WorkspaceError("PREVIEW_CANDIDATE_CHANGED", "Workspace operations changed since accepted preview")
        if self.workspace.get_revision(self.document_id) != current:
            raise WorkspaceError("STALE_REVISION", "Workspace changed during commit revalidation")
        applied = self.workspace.apply_transaction(self.document_id, current, copy.deepcopy(operations))
        record["status"] = "committed"
        record["result_revision"] = applied["revision"]
        return CommitReceipt(transaction_id=transaction_id,
            operation_kind=record["operation_kind"], base_revision=record["base_revision"],
            revision=applied["revision"], operations=copy.deepcopy(operations),
            candidate=copy.deepcopy(candidate), metadata=copy.deepcopy(metadata or record["metadata"]),
            applied=applied)

    def get(self, transaction_id: str) -> dict[str, Any] | None:
        record = self._pending.get(transaction_id)
        return copy.deepcopy(record) if record is not None else None

    @property
    def pending_count(self) -> int:
        return sum(row["status"] == "previewed" for row in self._pending.values())
