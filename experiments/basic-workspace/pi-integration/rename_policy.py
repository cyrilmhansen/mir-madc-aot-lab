"""Shared host-owned authorization for one semantic function rename.

This validates one canonical Workspace rename operation. It does not own
transport, mission progression, replay, or transaction lifecycle.
"""
from __future__ import annotations

import copy
import math
from typing import Any

from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.projection import build_projection, projection_semantics
from cycle20_gateway import senior

V2_SCHEMA = "basic-workspace.semantic-rename-contract"
V2_VERSION = 2
V2_FIELDS = {
    "schema", "version", "mission_id", "objective", "base_document_revision",
    "execution_profile_id", "target_handle", "expected_source_name", "new_source_name",
    "unchanged_function_handles", "unchanged_dependency_edges", "required_revision_increment",
    "validation_inputs",
}
REQUEST_FIELDS = {"expected_revision", "function_handle", "expected_name", "new_name"}


def validate_v2_contract(contract: Any) -> None:
    if not isinstance(contract, dict) or set(contract) != V2_FIELDS:
        raise WorkspaceError("RENAME_CONTRACT_SCHEMA", "Rename v2 contract has missing or unsupported fields")
    if contract.get("schema") != V2_SCHEMA or isinstance(contract.get("version"), bool) or contract.get("version") != V2_VERSION:
        raise WorkspaceError("RENAME_CONTRACT_VERSION", "Unsupported semantic rename contract")
    for key in ("mission_id", "objective", "execution_profile_id", "target_handle", "expected_source_name", "new_source_name"):
        if not isinstance(contract.get(key), str) or not contract[key]:
            raise WorkspaceError("RENAME_CONTRACT_SCHEMA", f"{key} must be a nonempty string")
    revision = contract.get("base_document_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise WorkspaceError("RENAME_CONTRACT_SCHEMA", "base_document_revision must be a positive integer")
    if contract["expected_source_name"] == contract["new_source_name"]:
        raise WorkspaceError("RENAME_CONTRACT_SCHEMA", "Rename contract must change the source spelling")
    if contract.get("unchanged_dependency_edges") is not True:
        raise WorkspaceError("RENAME_CONTRACT_SCHEMA", "Rename contract must preserve dependency identities")
    if contract.get("required_revision_increment") != 1 or isinstance(contract.get("required_revision_increment"), bool):
        raise WorkspaceError("RENAME_CONTRACT_SCHEMA", "Rename must advance exactly one Workspace revision")
    handles = contract.get("unchanged_function_handles")
    if (not isinstance(handles, list) or any(not isinstance(value, str) or not value for value in handles)
            or len(handles) != len(set(handles)) or contract["target_handle"] in handles):
        raise WorkspaceError("RENAME_CONTRACT_SCHEMA", "unchanged_function_handles must be unique and exclude the target")
    inputs = contract.get("validation_inputs")
    if (not isinstance(inputs, list) or not inputs or any(isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) for value in inputs)
            or len(inputs) != len(set(inputs))):
        raise WorkspaceError("RENAME_CONTRACT_SCHEMA", "validation_inputs must be a nonempty unique numeric array")


def authorize_rename_candidate(workspace: Workspace, document_id: str, *, request: Any,
                               contract: dict[str, Any], aliases: dict[str, str],
                               discovered: set[str], baseline: dict[str, Any]) -> dict[str, Any]:
    """Build and fully compare the exact candidate allowed by the host contract."""
    if not isinstance(request, dict) or set(request) != REQUEST_FIELDS:
        raise WorkspaceError("INVALID_RENAME_REQUEST", "Rename request fields are expected_revision, function_handle, expected_name, and new_name")
    revision = workspace.get_revision(document_id)
    requested_revision = request.get("expected_revision")
    if isinstance(requested_revision, bool) or not isinstance(requested_revision, int):
        raise WorkspaceError("STALE_REVISION", "expected_revision must be the current integer revision")
    if requested_revision != revision or revision != contract.get("base_document_revision"):
        raise WorkspaceError("STALE_REVISION", f"Rename is bound to revision {contract.get('base_document_revision')}; current revision is {revision}")
    handle = contract["target_handle"]
    if handle not in discovered:
        raise WorkspaceError("FUNCTION_NOT_DISCOVERED", "Discover the authorized target before previewing its rename")
    if request.get("function_handle") != handle:
        raise WorkspaceError("MISSION_RENAME_SCOPE", "Only the contract-authorized portable function handle may be renamed")
    if handle not in aliases:
        raise WorkspaceError("RENAME_HANDLE_UNKNOWN", "Authorized portable target does not resolve in this Workspace")
    symbol_id = aliases[handle]
    document = workspace.documents.get(document_id)
    if document is None or symbol_id not in document.symbols:
        raise WorkspaceError("RENAME_HANDLE_UNKNOWN", "Portable target maps to no live Workspace symbol")
    symbol = document.symbols[symbol_id]
    expected_old = contract["expected_source_name"]
    expected_new = contract["new_source_name"]
    if request.get("expected_name") != expected_old or symbol.name != expected_old:
        raise WorkspaceError("RENAME_PRECONDITION_FAILED", "Current source name differs from the host-owned rename precondition")
    if request.get("new_name") != expected_new:
        raise WorkspaceError("MISSION_RENAME_NAME", "Proposed source name is not authorized by the host contract")

    live_function_handles = {row["handle"] for row in baseline.get("functions", [])}
    expected_unchanged = live_function_handles - {handle}
    declared_unchanged = set(contract["unchanged_function_handles"])
    if declared_unchanged != expected_unchanged:
        raise WorkspaceError("RENAME_CONTRACT_SCOPE", "Contract unchanged-function set does not match the authenticated baseline")

    tokens_before = {token.uid: (token.text, token.kind) for token in document.tokens}
    expected_token_ids = {symbol.declaration_token, *symbol.references}
    if not expected_token_ids.issubset(tokens_before):
        raise WorkspaceError("RENAME_REFERENCE_SET_MISMATCH", "Symbol declaration/reference graph contains an unknown token")
    candidate_workspace = copy.deepcopy(workspace)
    operation = {"operation": "rename_symbol", "symbol_id": symbol_id, "new_name": expected_new}
    applied = candidate_workspace.apply_transaction(document_id, revision, [operation])
    candidate_tokens = {token.uid: (token.text, token.kind) for token in candidate_workspace.documents[document_id].tokens}
    if set(tokens_before) != set(candidate_tokens):
        raise WorkspaceError("RENAME_IDENTITY_LOSS", "Rename changed the canonical token identity set")
    changed = {uid for uid, before in tokens_before.items() if candidate_tokens[uid] != before}
    if changed != expected_token_ids or any(candidate_tokens[uid][0] != expected_new for uid in expected_token_ids):
        raise WorkspaceError("RENAME_REFERENCE_SET_MISMATCH", "Rename must update exactly the declaration and bound reference tokens")
    if any(tokens_before[uid][1] != candidate_tokens[uid][1] for uid in expected_token_ids):
        raise WorkspaceError("RENAME_TOKEN_KIND_CHANGED", "Rename must preserve token kinds")

    raw = projection_semantics(build_projection(candidate_workspace, document_id, applied["revision"]))
    candidate_state = senior.normalized_state(raw, aliases)
    expected_state = copy.deepcopy(baseline)
    target = senior.find_function(expected_state, handle)
    if target is None or target.get("name") != expected_old:
        raise WorkspaceError("RENAME_BASELINE_TARGET", "Authenticated baseline target does not match the contract")
    target["name"] = expected_new
    if candidate_state != expected_state:
        raise WorkspaceError("RENAME_UNRELATED_CHANGE", "Candidate differs from baseline beyond the authorized source name")
    old_edges = {(row["caller"], row["callee"]) for row in senior.candidate_call_edges(baseline)}
    new_edges = {(row["caller"], row["callee"]) for row in senior.candidate_call_edges(candidate_state)}
    if old_edges != new_edges:
        raise WorkspaceError("RENAME_DEPENDENCY_CHANGED", "Rename changed a semantic dependency identity")
    return {"operations": [operation], "candidate": candidate_state, "candidate_workspace": candidate_workspace,
        "changed_token_ids": sorted(changed), "changed_bound_tokens": len(changed), "symbol_id": symbol_id,
        "old_name": expected_old, "new_name": expected_new, "revision": revision}
