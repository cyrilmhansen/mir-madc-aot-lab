"""Host-anchored continuation from a verified creation handoff through one rename.

This record is intentionally narrower than a general operation-history format:
it accepts one Cycle36 creation handoff followed by exactly one Cycle37 rename.
It does not mutate a Workspace or grant the destination maintenance authority.
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.mir_execution import MirExecutionService
from basic_workspace.portable_replay import replay_constructive_stream
from basic_workspace.projection import build_projection, projection_semantics
from cycle20_gateway import senior
from rename_policy import validate_v2_contract
from verified_handoff import _dependencies, _fingerprint, _signatures, verify_handoff

SCHEMA = "basic-workspace.verified-rename-continuation"
VERSION = 1
PROFILE = "basic-workspace.numeric-composition.v1"
BUNDLE_FIELDS = {"schema", "version", "continuation_id", "source_sequence_id", "execution_profile_id",
    "source_creation_revision", "final_revision", "operation_count", "rename_contract_id",
    "rename_contract_sha256", "destination_contract_id", "destination_contract_sha256",
    "semantic_fingerprint", "live_handles", "retired_handles", "function_signatures", "dependencies",
    "source_evidence_root", "artifacts"}
ANCHOR_FIELDS = {"schema", "version", "bundle_sha256", "source_handoff_sha256", "source_anchor_sha256",
    "source_sequence_id", "rename_contract_id", "rename_contract_sha256", "destination_contract_id",
    "destination_contract_sha256", "final_revision", "semantic_fingerprint"}
ARTIFACTS = {"source_handoff", "source_anchor", "rename_contract", "rename_stream", "rename_history",
    "rename_validation", "rename_baseline", "destination_contract"}


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise WorkspaceError("CONTINUATION_EVIDENCE_JSON", f"Invalid continuation evidence: {path.name}") from exc


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise WorkspaceError("CONTINUATION_ARTIFACT_PATH", "Continuation artifact paths must stay inside the evidence package")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise WorkspaceError("CONTINUATION_ARTIFACT_PATH", "Continuation artifact escapes its evidence package") from exc
    if not path.is_file():
        raise WorkspaceError("CONTINUATION_ARTIFACT_MISSING", f"Missing continuation artifact: {relative}")
    return path


def _edges(normalized: dict[str, Any]) -> list[dict[str, str]]:
    """Dependency edges by portable identity, independent of source spelling."""
    return sorted(senior.candidate_call_edges(normalized), key=lambda row: (row["caller"], row["callee"]))


def _observe(ws: Workspace, doc: str, revision: int, aliases: dict[str, str], inputs: list[int | float]) -> dict[str, Any]:
    executor = MirExecutionService(timeout=20)
    return {engine: {str(value): {handle: executor.execute_function(ws, doc, revision, aliases[handle], [value], engine)["result"]
            for handle in sorted(aliases) if handle.endswith(".function")} for value in inputs}
        for engine in ("interp", "jit")}


def _validate_contents(root: Path, bundle: dict[str, Any], destination_contract_path: Path,
                       anchor: dict[str, Any] | None) -> dict[str, Any]:
    if set(bundle) != BUNDLE_FIELDS or bundle.get("schema") != SCHEMA or bundle.get("version") != VERSION:
        raise WorkspaceError("CONTINUATION_SCHEMA", "Unsupported or malformed rename continuation")
    if bundle["execution_profile_id"] != PROFILE:
        raise WorkspaceError("CONTINUATION_PROFILE", "Rename continuation uses an incompatible execution profile")
    if not isinstance(bundle["artifacts"], dict) or set(bundle["artifacts"]) != ARTIFACTS:
        raise WorkspaceError("CONTINUATION_ARTIFACT_SET", "Continuation artifact set is incomplete or contains unknown entries")
    if not isinstance(bundle["source_evidence_root"], str):
        raise WorkspaceError("CONTINUATION_ARTIFACT_PATH", "Source creation evidence root must be package-relative")
    files: dict[str, Path] = {}
    for key, row in bundle["artifacts"].items():
        if not isinstance(row, dict) or set(row) != {"path", "sha256"} or not isinstance(row["sha256"], str):
            raise WorkspaceError("CONTINUATION_ARTIFACT_RECORD", f"Malformed artifact record: {key}")
        path = _safe(root, row["path"])
        if _sha(path) != row["sha256"]:
            raise WorkspaceError("CONTINUATION_ARTIFACT_DIGEST", f"Continuation artifact digest mismatch: {key}")
        files[key] = path
    dest_sha = _sha(destination_contract_path)
    dest_contract = _read(destination_contract_path)
    if (dest_contract.get("mission_id") != bundle["destination_contract_id"]
            or dest_sha != bundle["destination_contract_sha256"]
            or _sha(files["destination_contract"]) != dest_sha):
        raise WorkspaceError("CONTINUATION_DESTINATION_MISMATCH", "Continuation is not anchored to this host-owned maintenance contract")
    rename_contract = _read(files["rename_contract"])
    validate_v2_contract(rename_contract)
    if (rename_contract.get("mission_id") != bundle["rename_contract_id"]
            or _sha(files["rename_contract"]) != bundle["rename_contract_sha256"]):
        raise WorkspaceError("CONTINUATION_RENAME_CONTRACT", "Rename contract identity or digest differs from continuation")
    source_handoff = _read(files["source_handoff"])
    source_anchor = _read(files["source_anchor"])
    if (source_handoff.get("source_sequence_id") != bundle["source_sequence_id"]
            or source_anchor.get("source_sequence_id") != bundle["source_sequence_id"]):
        raise WorkspaceError("CONTINUATION_SOURCE_ID", "Source handoff and continuation identify different creation sequences")
    source_rel = Path(bundle["source_evidence_root"])
    if source_rel.is_absolute() or ".." in source_rel.parts or not bundle["source_evidence_root"]:
        raise WorkspaceError("CONTINUATION_ARTIFACT_PATH", "Source evidence root must stay inside the package")
    source_root = (root / source_rel).resolve()
    try:
        source_root.relative_to(root.resolve())
    except ValueError as exc:
        raise WorkspaceError("CONTINUATION_ARTIFACT_PATH", "Source evidence root escapes its package") from exc
    if not source_root.is_dir():
        raise WorkspaceError("CONTINUATION_SOURCE_EVIDENCE", "Copied creation evidence root is not a directory")
    # Re-run Cycle36's strict creation-only verifier against the original anchor.
    source_verified = verify_handoff(files["source_handoff"], files["source_anchor"], source_root,
        files["rename_contract"])
    if source_verified["revision"] != bundle["source_creation_revision"]:
        raise WorkspaceError("CONTINUATION_SOURCE_REVISION", "Creation proof revision differs from continuation")

    stream = _read(files["rename_stream"])
    source_stream = _read(Path(source_verified["source_stream"]))
    operations = stream.get("operations")
    if (stream.get("schema") != "basic-workspace.constructive-metafile" or stream.get("version") != 1
            or stream.get("execution_profile_id") != PROFILE or not isinstance(operations, list)
            or len(operations) != len(source_stream["operations"]) + 1
            or operations[:-1] != source_stream["operations"]):
        raise WorkspaceError("CONTINUATION_HISTORY_ORDER", "Continuation must contain the authenticated creation prefix and exactly one rename suffix")
    expected_rename = {"operation": "rename_symbol", "target_handle": rename_contract["target_handle"],
        "expected_name": rename_contract["expected_source_name"], "new_name": rename_contract["new_source_name"]}
    if operations[-1] != expected_rename:
        raise WorkspaceError("CONTINUATION_RENAME_OPERATION", "Final operation does not match the authorized Cycle37 rename contract")
    if (stream.get("portable_handles") != source_stream.get("portable_handles")
            or stream.get("retired_handles", []) != source_stream.get("retired_handles", [])):
        raise WorkspaceError("CONTINUATION_IDENTITY_LEDGER", "Rename suffix changed the portable live/retired handle ledger")
    creation_revision = source_verified["revision"]
    final_revision = creation_revision + 1
    if (bundle.get("operation_count") != len(operations) or bundle.get("final_revision") != final_revision
            or rename_contract["base_document_revision"] != creation_revision):
        raise WorkspaceError("CONTINUATION_REVISION_SEQUENCE", "Rename must commit once after the authenticated creation revision")

    # Replay both prefixes from empty state, keeping transient Workspace IDs local.
    base_ws = Workspace(); base_doc = base_ws.create_empty_document("memory://cycle38/creation-prefix.bas")["document_id"]
    base_replay = replay_constructive_stream(base_ws, base_doc, source_stream["operations"],
        expected_final_handles=source_stream["portable_handles"], expected_start_revision=1)
    base_norm = senior.normalized_state(projection_semantics(build_projection(base_ws, base_doc, creation_revision)), base_replay.live_handles)
    final_ws = Workspace(); final_doc = final_ws.create_empty_document("memory://cycle38/renamed-baseline.bas")["document_id"]
    final_replay = replay_constructive_stream(final_ws, final_doc, operations,
        expected_final_handles=stream["portable_handles"], expected_retired_handles=stream.get("retired_handles", []),
        expected_start_revision=1)
    final_norm = senior.normalized_state(projection_semantics(build_projection(final_ws, final_doc, final_revision)), final_replay.live_handles)
    expected_norm = copy.deepcopy(base_norm)
    target = senior.find_function(expected_norm, rename_contract["target_handle"])
    if target is None or target.get("name") != rename_contract["expected_source_name"]:
        raise WorkspaceError("CONTINUATION_RENAME_TARGET", "Rename target does not match the source baseline")
    target["name"] = rename_contract["new_source_name"]
    if final_norm != expected_norm:
        raise WorkspaceError("CONTINUATION_UNRELATED_CHANGE", "Post-rename structure differs beyond the authorized source spelling")
    if _edges(base_norm) != _edges(final_norm):
        raise WorkspaceError("CONTINUATION_DEPENDENCY_CHANGE", "Rename changed a dependency identity edge")
    if (sorted(final_replay.live_handles) != sorted(bundle["live_handles"])
            or sorted(final_replay.retired_handles) != sorted(bundle["retired_handles"])):
        raise WorkspaceError("CONTINUATION_IDENTITY_LEDGER", "Replayed identity ledger differs from continuation")
    if (_fingerprint(final_revision, final_norm) != bundle["semantic_fingerprint"]
            or _signatures(final_norm) != bundle["function_signatures"]
            or _dependencies(final_norm) != bundle["dependencies"]):
        raise WorkspaceError("CONTINUATION_FINAL_STATE", "Final replay fingerprint, signatures, or dependency graph differs")

    history = [json.loads(line) for line in files["rename_history"].read_text(encoding="utf-8").splitlines() if line.strip()]
    commits = [row for row in history if row.get("event") == "transaction_committed" and row.get("resulting_revision") == final_revision]
    if (len(commits) != 1 or commits[0].get("operation") != "rename_symbol"
            or commits[0].get("actor") != "mission_gateway" or commits[0].get("base_revision") != creation_revision
            or commits[0].get("target_handle") != rename_contract["target_handle"]
            or commits[0].get("old_name") != rename_contract["expected_source_name"]
            or commits[0].get("new_name") != rename_contract["new_source_name"]
            or commits[0].get("preserved_alias_count") != len(final_replay.live_handles)):
        raise WorkspaceError("CONTINUATION_RENAME_COMMIT", "No matching authoritative rename commit exists at the expected revision")
    previews = [row for row in history if row.get("event") == "preview_accepted"
        and row.get("transaction_id") == commits[0].get("transaction_id")]
    if (len(previews) != 1 or previews[0].get("base_revision") != creation_revision
            or previews[0].get("resulting_revision") != final_revision
            or previews[0].get("function_handle") != rename_contract["target_handle"]):
        raise WorkspaceError("CONTINUATION_RENAME_PREVIEW", "Committed rename has no matching accepted preview record")
    host_events = [row for row in history if row.get("event") == "program_validated"
        and row.get("actor") == "host_validation" and row.get("revision") == final_revision and row.get("passed") is True]
    if len(host_events) != 1:
        raise WorkspaceError("CONTINUATION_RENAME_VALIDATION", "Rename history lacks exactly one successful host validation event")
    receipt = _read(files["rename_validation"])
    baseline_receipt = _read(files["rename_baseline"])
    baseline_map = baseline_receipt.get("identity_mapping")
    original_target_id = next((row.get("workspace_id") for row in baseline_map or []
        if row.get("portable_handle") == rename_contract["target_handle"]), None)
    if (baseline_receipt.get("revision") != creation_revision or baseline_receipt.get("authenticated_handoff") is not True
            or not isinstance(baseline_map, list) or len(baseline_map) != len(set(row.get("workspace_id") for row in baseline_map))
            or original_target_id is None or commits[0].get("preserved_function_id") != original_target_id):
        raise WorkspaceError("CONTINUATION_IDENTITY_PROVENANCE", "Rename commit target ID does not match the authenticated baseline mapping")
    receipt_checks = (receipt.get("mission_complete") is True and receipt.get("reliable") is True
        and receipt.get("revision") == final_revision and receipt.get("executed_revision") == final_revision
        and receipt.get("mission_id") == rename_contract["mission_id"]
        and receipt.get("target_handle") == rename_contract["target_handle"]
        and receipt.get("source_name") == rename_contract["new_source_name"]
        and receipt.get("interpreter_jit_agree") is True and receipt.get("behavior_unchanged") is True
        and receipt.get("normalized_structure_modulo_target_name") is True
        and receipt.get("all_portable_identities_preserved") is True
        and receipt.get("token_identity_set_preserved") is True
        and receipt.get("all_bound_target_tokens_renamed") is True
        and receipt.get("dependency_identity_edges_unchanged") is True
        and receipt.get("replay", {}).get("passed") is True)
    if not receipt_checks:
        raise WorkspaceError("CONTINUATION_RENAME_VALIDATION", "Cycle37 host receipt does not attest a complete rename validation")

    # In one Workspace, independently replay the constructor prefix and apply
    # the canonical rename to verify token and semantic entity continuity.
    continuity_ws = Workspace(); continuity_doc = continuity_ws.create_empty_document(
        "memory://cycle38/rename-identity-audit.bas")["document_id"]
    continuity_replay = replay_constructive_stream(continuity_ws, continuity_doc, source_stream["operations"],
        expected_final_handles=source_stream["portable_handles"], expected_start_revision=1)
    symbol_id = continuity_replay.live_handles[rename_contract["target_handle"]]
    symbol = continuity_ws.documents[continuity_doc].symbols[symbol_id]
    expected_changed = {symbol.declaration_token, *symbol.references}
    token_state_before = {token.uid: (token.text, token.kind) for token in continuity_ws.documents[continuity_doc].tokens}
    operation_result = continuity_ws.apply_transaction(continuity_doc, creation_revision,
        [{"operation": "rename_symbol", "symbol_id": symbol_id, "new_name": rename_contract["new_source_name"]}])
    token_state_after = {token.uid: (token.text, token.kind) for token in continuity_ws.documents[continuity_doc].tokens}
    changed_tokens = {uid for uid in token_state_before if token_state_before[uid] != token_state_after.get(uid)}
    continuity_norm = senior.normalized_state(projection_semantics(build_projection(continuity_ws, continuity_doc,
        operation_result["revision"])), continuity_replay.live_handles)
    expected_continuity = copy.deepcopy(base_norm)
    senior.find_function(expected_continuity, rename_contract["target_handle"])["name"] = rename_contract["new_source_name"]
    if (operation_result["revision"] != final_revision or set(token_state_before) != set(token_state_after)
            or changed_tokens != expected_changed or continuity_norm != expected_continuity
            or symbol_id != continuity_replay.live_handles[rename_contract["target_handle"]]
            or len(commits[0].get("changed_token_ids", [])) != len(expected_changed)):
        raise WorkspaceError("CONTINUATION_RENAME_IDENTITY", "Canonical rename did not preserve target entities and change only bound name tokens")

    inputs = rename_contract["validation_inputs"]
    base_observed = _observe(base_ws, base_doc, creation_revision, base_replay.live_handles, inputs)
    final_observed = _observe(final_ws, final_doc, final_revision, final_replay.live_handles, inputs)
    creation_receipt = _read(Path(source_verified["source_validation"]))
    expected_by_handle = {engine: {} for engine in ("interp", "jit")}
    base_names = {row["handle"]: row["name"].lower() for row in base_norm["functions"]}
    for value in inputs:
        key = str(value)
        for engine in ("interp", "jit"):
            source_row = creation_receipt["expected_results"][engine].get(key)
            if not isinstance(source_row, dict):
                raise WorkspaceError("CONTINUATION_CREATION_ORACLE", "Creation receipt lacks a row for the rename validation corpus")
            expected_by_handle[engine][key] = {handle: source_row[name] for handle, name in base_names.items() if name in source_row}
            if set(expected_by_handle[engine][key]) != set(base_names):
                raise WorkspaceError("CONTINUATION_CREATION_ORACLE", "Creation oracle omits a live function")
    if base_observed != expected_by_handle:
        raise WorkspaceError("CONTINUATION_CREATION_BEHAVIOR", "Fresh pre-rename MIR execution differs from the creation host oracle")
    if final_observed != base_observed or final_observed["interp"] != final_observed["jit"]:
        raise WorkspaceError("CONTINUATION_RENAME_BEHAVIOR", "Rename changed behavior or MIR engines disagree")
    receipt_observed = receipt.get("observed_results_by_portable_handle")
    receipt_expected = receipt.get("expected_results_by_portable_handle")
    if receipt_observed != receipt_expected or receipt_observed != final_observed:
        raise WorkspaceError("CONTINUATION_RENAME_BEHAVIOR", "Cycle37 receipt observations differ from independent replay execution")
    if anchor is not None:
        expected_anchor = {"schema": "basic-workspace.verified-rename-continuation-anchor", "version": 1,
            "bundle_sha256": _sha(_safe(root, "continuation.json")),
            "source_handoff_sha256": _sha(files["source_handoff"]), "source_anchor_sha256": _sha(files["source_anchor"]),
            "source_sequence_id": bundle["source_sequence_id"], "rename_contract_id": bundle["rename_contract_id"],
            "rename_contract_sha256": bundle["rename_contract_sha256"],
            "destination_contract_id": bundle["destination_contract_id"],
            "destination_contract_sha256": bundle["destination_contract_sha256"],
            "final_revision": final_revision, "semantic_fingerprint": bundle["semantic_fingerprint"]}
        if set(anchor) != ANCHOR_FIELDS or anchor != expected_anchor:
            raise WorkspaceError("CONTINUATION_TRUST_ANCHOR", "Continuation anchor does not bind this source, rename, state, and maintenance contract")
    return {"bundle": bundle, "source_verification": source_verified, "source_stream": stream,
        "source_history": history, "source_validation": receipt, "normalized": final_norm,
        "base_normalized": base_norm, "base_observations_by_handle": base_observed,
        "observations_by_handle": final_observed, "aliases": dict(final_replay.live_handles),
        "revision": final_revision, "fingerprint": bundle["semantic_fingerprint"],
        "dependency_edges": _dependencies(final_norm), "signatures": _signatures(final_norm),
        "changed_token_count": len(expected_changed),
        "all_checks_passed": True}


def verify_rename_continuation(bundle_path: Path, anchor_path: Path, evidence_root: Path,
                               destination_contract_path: Path) -> dict[str, Any]:
    bundle_path, anchor_path, root = bundle_path.resolve(), anchor_path.resolve(), evidence_root.resolve()
    bundle, anchor = _read(bundle_path), _read(anchor_path)
    if _sha(bundle_path) != anchor.get("bundle_sha256"):
        raise WorkspaceError("CONTINUATION_TRUST_ANCHOR", "Continuation bundle digest differs from independent host anchor")
    return _validate_contents(root, bundle, destination_contract_path.resolve(), anchor)


def build_rename_continuation(*, creation_handoff: Path, creation_anchor: Path, creation_evidence_root: Path,
                              rename_contract: Path, rename_evidence_root: Path, destination_contract: Path,
                              package_root: Path) -> dict[str, Any]:
    """Create a host continuation package only after re-verifying the rename stage."""
    package_root = package_root.resolve()
    if package_root.exists() and any(package_root.iterdir()):
        raise WorkspaceError("CONTINUATION_OUTPUT_EXISTS", "Refusing to overwrite continuation evidence")
    host_anchor_path = package_root.parent / f"{package_root.name}-host-trust-anchor.json"
    if host_anchor_path.exists():
        raise WorkspaceError("CONTINUATION_OUTPUT_EXISTS", "Refusing to overwrite the separately held host trust anchor")
    package_root.mkdir(parents=True, exist_ok=True)
    (package_root / "source/evidence").parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(creation_handoff, package_root / "source/handoff.json")
    shutil.copyfile(creation_anchor, package_root / "source/anchor.json")
    shutil.copytree(creation_evidence_root, package_root / "source/evidence")
    (package_root / "rename").mkdir(parents=True, exist_ok=True)
    for name in ("constructive-operations.json", "history.jsonl", "mission-validation-host.json"):
        shutil.copyfile(rename_evidence_root / name, package_root / "rename" / name)
    shutil.copyfile(rename_evidence_root / "baseline-reconstruction.json", package_root / "rename" / "baseline-reconstruction.json")
    shutil.copyfile(rename_contract, package_root / "rename-contract.json")
    shutil.copyfile(destination_contract, package_root / "maintenance-contract.json")
    artifact_paths = {"source_handoff": "source/handoff.json", "source_anchor": "source/anchor.json",
        "rename_contract": "rename-contract.json", "rename_stream": "rename/constructive-operations.json",
        "rename_history": "rename/history.jsonl", "rename_validation": "rename/mission-validation-host.json",
        "rename_baseline": "rename/baseline-reconstruction.json", "destination_contract": "maintenance-contract.json"}
    artifacts = {key: {"path": rel, "sha256": _sha(package_root / rel)} for key, rel in artifact_paths.items()}
    rename_con = _read(package_root / "rename-contract.json")
    creation_bundle = _read(package_root / "source/handoff.json")
    stream = _read(package_root / "rename/constructive-operations.json")
    revision = creation_bundle["final_revision"] + 1
    final_ws = Workspace(); final_doc = final_ws.create_empty_document("memory://cycle38/continuation-build.bas")["document_id"]
    replay = replay_constructive_stream(final_ws, final_doc, stream["operations"], expected_final_handles=stream["portable_handles"],
        expected_retired_handles=stream.get("retired_handles", []), expected_start_revision=1)
    normalized = senior.normalized_state(projection_semantics(build_projection(final_ws, final_doc, revision)), replay.live_handles)
    dest = _read(package_root / "maintenance-contract.json")
    bundle = {"schema": SCHEMA, "version": VERSION, "continuation_id": f"{creation_bundle['source_sequence_id']}->{rename_con['mission_id']}->{dest['mission_id']}",
        "source_sequence_id": creation_bundle["source_sequence_id"], "execution_profile_id": PROFILE,
        "source_creation_revision": creation_bundle["final_revision"], "final_revision": revision,
        "operation_count": len(stream["operations"]), "rename_contract_id": rename_con["mission_id"],
        "rename_contract_sha256": _sha(package_root / "rename-contract.json"),
        "destination_contract_id": dest["mission_id"], "destination_contract_sha256": _sha(package_root / "maintenance-contract.json"),
        "semantic_fingerprint": _fingerprint(revision, normalized), "live_handles": sorted(replay.live_handles),
        "retired_handles": sorted(replay.retired_handles), "function_signatures": _signatures(normalized),
        "dependencies": _dependencies(normalized), "source_evidence_root": "source/evidence", "artifacts": artifacts}
    _write(package_root / "continuation.json", bundle)
    # First validate all semantic/provenance conditions without trusting an
    # anchor; the anchor is only issued after the checks succeed.
    checked = _validate_contents(package_root, bundle, package_root / "maintenance-contract.json", None)
    anchor = {"schema": "basic-workspace.verified-rename-continuation-anchor", "version": 1,
        "bundle_sha256": _sha(package_root / "continuation.json"), "source_handoff_sha256": artifacts["source_handoff"]["sha256"],
        "source_anchor_sha256": artifacts["source_anchor"]["sha256"], "source_sequence_id": bundle["source_sequence_id"],
        "rename_contract_id": bundle["rename_contract_id"], "rename_contract_sha256": bundle["rename_contract_sha256"],
        "destination_contract_id": bundle["destination_contract_id"], "destination_contract_sha256": bundle["destination_contract_sha256"],
        "final_revision": bundle["final_revision"], "semantic_fingerprint": bundle["semantic_fingerprint"]}
    _write(host_anchor_path, anchor)
    # Verify the packaged artifact in the same way as the receiving process.
    verified = verify_rename_continuation(package_root / "continuation.json", host_anchor_path,
        package_root, package_root / "maintenance-contract.json")
    return {"checked": checked, "verified": verified, "bundle_path": package_root / "continuation.json",
        "anchor_path": host_anchor_path, "evidence_root": package_root}
