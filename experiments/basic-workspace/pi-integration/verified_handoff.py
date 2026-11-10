"""Host-owned, evidence-bound handoff from Cycle35 creation to Cycle20 editing.

The handoff is metadata, never a serialized Workspace. The receiver verifies a
separate trust anchor and artifact hashes, then the existing Cycle20 loader
replays the referenced constructive stream into its own empty Workspace.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.projection import build_projection, projection_semantics
from basic_workspace.portable_replay import replay_constructive_stream

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROFILE = "basic-workspace.numeric-composition.v1"
SCHEMA = "basic-workspace.verified-creation-handoff"
VERSION = 1

_spec = importlib.util.spec_from_file_location("cycle36_semantic_normalizer", ROOT / "scripts/is-senior-campaign.py")
_normalizer = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
sys.modules[_spec.name] = _normalizer
_spec.loader.exec_module(_normalizer)


def _bytes(path: Path) -> bytes:
    return path.read_bytes()


def _sha(path: Path) -> str:
    return hashlib.sha256(_bytes(path)).hexdigest()


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode()).hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise WorkspaceError("HANDOFF_EVIDENCE_JSON", f"Could not read valid JSON evidence at {path.name}") from exc


def _safe_artifact(root: Path, relative: str) -> Path:
    if not isinstance(relative, str):
        raise WorkspaceError("HANDOFF_ARTIFACT_PATH", "Evidence paths must be strings")
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or not relative:
        raise WorkspaceError("HANDOFF_ARTIFACT_PATH", "Evidence references must be relative paths inside the source evidence root")
    result = (root / rel).resolve()
    try:
        result.relative_to(root.resolve())
    except ValueError as exc:
        raise WorkspaceError("HANDOFF_ARTIFACT_PATH", "Evidence reference escapes the source evidence root") from exc
    if not result.is_file():
        raise WorkspaceError("HANDOFF_ARTIFACT_MISSING", f"Required evidence artifact is missing: {relative}")
    return result


def _normalized(ws: Workspace, doc: str, revision: int, handles: dict[str, str]) -> dict[str, Any]:
    raw = projection_semantics(build_projection(ws, doc, revision))
    return _normalizer.normalized_state(raw, handles)


def _fingerprint(revision: int, normalized: dict[str, Any]) -> str:
    return _canonical_sha({"profile": PROFILE, "revision": revision, "semantics": normalized})


def _signatures(normalized: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"handle": row["handle"], "name": row["name"], "parameters": row["parameters"],
        "return_type": row["return_type"]} for row in normalized["functions"]]


def _dependencies(normalized: dict[str, Any]) -> list[dict[str, str]]:
    names = {row["handle"]: row["name"] for row in normalized["functions"]}
    edges = {(row["caller"], row["callee"]) for row in _normalizer.candidate_call_edges(normalized)}
    return [{"caller": names.get(caller, caller), "callee": names.get(callee, callee)}
        for caller, callee in sorted(edges)]


def build_handoff(source_root: Path, sequence_path: Path, maintenance_contract_path: Path,
                  handoff_path: Path, anchor_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build handoff and separate trust anchor after the sequence completed."""
    source_root = source_root.resolve()
    sequence_path = sequence_path.resolve()
    contract_path = maintenance_contract_path.resolve()
    sequence = _read_json(sequence_path)
    contract = _read_json(contract_path)
    step_count = len(sequence.get("steps", []))
    artifacts = {
        "constructive_stream": source_root / "constructive-operations.json",
        "history": source_root / "history.jsonl",
        "execution_profile": source_root / "execution-profile.json",
    }
    for index in range(1, step_count + 1):
        artifacts[f"checkpoint_{index}"] = source_root / f"checkpoint-step-{index:02d}.json"
        artifacts[f"validation_{index}"] = source_root / f"mission-{index + 2}-validation-host.json"
    # Cycle35 writes its source contract into the evidence directory. Bind that
    # exact copy as well as the host configuration used to start the gateway.
    copied_sequence = source_root / "creation-sequence.json"
    artifacts["creation_sequence"] = copied_sequence
    hashes: dict[str, dict[str, str]] = {}
    for key, raw_path in artifacts.items():
        path = Path(raw_path)
        if not path.is_absolute():
            path = source_root / path
        path = path.resolve()
        try:
            rel = path.relative_to(source_root)
        except ValueError as exc:
            raise WorkspaceError("HANDOFF_ARTIFACT_PATH", f"{key} is outside the source evidence root") from exc
        if not path.is_file():
            raise WorkspaceError("HANDOFF_ARTIFACT_MISSING", f"Required Cycle35 evidence is absent: {rel}")
        hashes[key] = {"path": rel.as_posix(), "sha256": _sha(path)}
    if _read_json(copied_sequence) != sequence:
        raise WorkspaceError("HANDOFF_SEQUENCE_COPY_MISMATCH", "Gateway sequence copy differs from host-owned sequence configuration")
    stream = _read_json(artifacts["constructive_stream"])
    final_checkpoint = _read_json(artifacts[f"checkpoint_{step_count}"])
    if (stream.get("schema") != "basic-workspace.constructive-metafile" or stream.get("version") != 1
            or stream.get("execution_profile_id") != PROFILE or len(stream.get("operations", [])) != step_count):
        raise WorkspaceError("HANDOFF_STREAM_INVALID", "Creation stream schema, profile, or operation count is invalid")
    if (final_checkpoint.get("sequence_id") != sequence.get("sequence_id")
            or final_checkpoint.get("active_step_id") is not None
            or final_checkpoint.get("revision") != 1 + step_count
            or len(final_checkpoint.get("completed_steps", [])) != step_count
            or any(row.get("validated") is not True for row in final_checkpoint.get("completed_steps", []))):
        raise WorkspaceError("HANDOFF_SEQUENCE_INCOMPLETE", "Final creation checkpoint does not attest a completed sequence")
    live = sorted(stream.get("portable_handles", []))
    retired = sorted(stream.get("retired_handles", []))
    if retired:
        raise WorkspaceError("HANDOFF_UNEXPECTED_RETIREMENT", "Creation-only sequence unexpectedly retires portable handles")
    bundle = {"schema": SCHEMA, "version": VERSION,
        "handoff_id": f"{sequence['sequence_id']}->{contract['mission_id']}",
        "source_sequence_id": sequence["sequence_id"], "execution_profile_id": PROFILE,
        "final_revision": final_checkpoint["revision"], "operation_count": step_count,
        "semantic_fingerprint": final_checkpoint["semantic_fingerprint"],
        "live_handles": live, "retired_handles": retired,
        "function_signatures": final_checkpoint["function_signatures"],
        "dependencies": final_checkpoint["dependencies"],
        "destination_contract_id": contract["mission_id"],
        "destination_contract_sha256": _sha(contract_path),
        "artifacts": hashes}
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    anchor = {"schema": "basic-workspace.verified-creation-handoff-anchor", "version": 1,
        "handoff_sha256": _sha(handoff_path), "source_sequence_id": sequence["sequence_id"],
        "execution_profile_id": PROFILE, "final_revision": final_checkpoint["revision"],
        "semantic_fingerprint": final_checkpoint["semantic_fingerprint"],
        "destination_contract_id": contract["mission_id"],
        "destination_contract_sha256": _sha(contract_path)}
    anchor_path.parent.mkdir(parents=True, exist_ok=True)
    anchor_path.write_text(json.dumps(anchor, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return bundle, anchor


def verify_handoff(handoff_path: Path, anchor_path: Path, evidence_root: Path,
                   maintenance_contract_path: Path) -> dict[str, Any]:
    """Authenticate evidence and verify every creation prefix before use."""
    handoff_path, anchor_path = handoff_path.resolve(), anchor_path.resolve()
    evidence_root, contract_path = evidence_root.resolve(), maintenance_contract_path.resolve()
    if not handoff_path.is_file():
        raise WorkspaceError("HANDOFF_MISSING", "Verified creation handoff bundle is missing")
    if not anchor_path.is_file():
        raise WorkspaceError("HANDOFF_ANCHOR_MISSING", "Independent host trust anchor is missing")
    bundle, anchor, contract = _read_json(handoff_path), _read_json(anchor_path), _read_json(contract_path)
    required_bundle = {"schema", "version", "handoff_id", "source_sequence_id", "execution_profile_id",
        "final_revision", "operation_count", "semantic_fingerprint", "live_handles", "retired_handles",
        "function_signatures", "dependencies", "destination_contract_id", "destination_contract_sha256", "artifacts"}
    if not isinstance(bundle, dict) or set(bundle) != required_bundle or bundle.get("schema") != SCHEMA or bundle.get("version") != VERSION:
        raise WorkspaceError("HANDOFF_SCHEMA", "Unsupported or malformed verified handoff")
    required_anchor = {"schema", "version", "handoff_sha256", "source_sequence_id", "execution_profile_id",
        "final_revision", "semantic_fingerprint", "destination_contract_id", "destination_contract_sha256"}
    if not isinstance(anchor, dict) or set(anchor) != required_anchor or anchor.get("schema") != "basic-workspace.verified-creation-handoff-anchor" or anchor.get("version") != 1:
        raise WorkspaceError("HANDOFF_ANCHOR_SCHEMA", "Unsupported or malformed trusted handoff anchor")
    for field in ("final_revision", "operation_count"):
        value = bundle.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise WorkspaceError("HANDOFF_SCHEMA", f"{field} must be a positive integer")
    if (not isinstance(bundle.get("live_handles"), list) or not isinstance(bundle.get("retired_handles"), list)
            or any(not isinstance(value, str) or not value for value in bundle["live_handles"] + bundle["retired_handles"])
            or len(set(bundle["live_handles"])) != len(bundle["live_handles"])
            or len(set(bundle["retired_handles"])) != len(bundle["retired_handles"])):
        raise WorkspaceError("HANDOFF_SCHEMA", "Live and retired handles must be unique nonempty string arrays")
    for field in ("semantic_fingerprint", "destination_contract_sha256"):
        value = bundle.get(field)
        if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise WorkspaceError("HANDOFF_SCHEMA", f"{field} must be a lowercase SHA-256 digest")
    if anchor["handoff_sha256"] != _sha(handoff_path):
        raise WorkspaceError("HANDOFF_TRUST_ANCHOR_MISMATCH", "Bundle digest differs from the independently supplied host trust anchor")
    expected_anchor = {"source_sequence_id": bundle["source_sequence_id"],
        "execution_profile_id": bundle["execution_profile_id"], "final_revision": bundle["final_revision"],
        "semantic_fingerprint": bundle["semantic_fingerprint"], "destination_contract_id": contract["mission_id"],
        "destination_contract_sha256": _sha(contract_path)}
    if any(anchor.get(key) != value for key, value in expected_anchor.items()):
        raise WorkspaceError("HANDOFF_TRUST_BINDING", "Trusted anchor does not bind this sequence, revision, fingerprint, and destination contract")
    if (bundle["execution_profile_id"] != PROFILE or bundle["destination_contract_id"] != contract.get("mission_id")
            or bundle["destination_contract_sha256"] != _sha(contract_path)):
        raise WorkspaceError("HANDOFF_DESTINATION_MISMATCH", "Handoff is not authorized as the baseline for this maintenance contract")
    artifacts = bundle["artifacts"]
    if not isinstance(artifacts, dict) or not {"creation_sequence", "constructive_stream", "history", "execution_profile"}.issubset(artifacts):
        raise WorkspaceError("HANDOFF_ARTIFACT_SET", "Handoff omits required source artifacts")
    resolved: dict[str, Path] = {}
    for key, record in artifacts.items():
        if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
            raise WorkspaceError("HANDOFF_ARTIFACT_RECORD", f"Malformed artifact record {key}")
        if (not isinstance(record["sha256"], str) or len(record["sha256"]) != 64
                or any(ch not in "0123456789abcdef" for ch in record["sha256"])):
            raise WorkspaceError("HANDOFF_ARTIFACT_RECORD", f"Artifact digest is malformed: {key}")
        path = _safe_artifact(evidence_root, record["path"])
        if _sha(path) != record["sha256"]:
            raise WorkspaceError("HANDOFF_ARTIFACT_DIGEST", f"Source artifact digest mismatch: {key}")
        resolved[key] = path
    sequence = _read_json(resolved["creation_sequence"])
    copied_sequence = sequence
    profile = _read_json(resolved["execution_profile"])
    stream = _read_json(resolved["constructive_stream"])
    history = [json.loads(line) for line in resolved["history"].read_text(encoding="utf-8").splitlines() if line.strip()]
    if copied_sequence.get("sequence_id") != bundle["source_sequence_id"]:
        raise WorkspaceError("HANDOFF_SEQUENCE_ID", "Source sequence contract and gateway evidence disagree")
    from cycle19_gateway import Cycle19Gateway
    Cycle19Gateway._validate_creation_sequence(sequence)
    if profile.get("schema") != "basic-workspace.execution-profile" or profile.get("version") != 1:
        raise WorkspaceError("HANDOFF_PROFILE", "Saved execution profile artifact has an unsupported schema")
    operations = stream.get("operations")
    step_count = bundle["operation_count"]
    expected_artifact_keys = {"creation_sequence", "constructive_stream", "history", "execution_profile"}
    for index in range(1, step_count + 1):
        expected_artifact_keys.update((f"checkpoint_{index}", f"validation_{index}"))
    if set(artifacts) != expected_artifact_keys:
        raise WorkspaceError("HANDOFF_ARTIFACT_SET", "Handoff contains missing or unrecognized evidence references")
    if (stream.get("schema") != "basic-workspace.constructive-metafile" or stream.get("version") != 1
            or stream.get("execution_profile_id") != PROFILE or not isinstance(operations, list)
            or len(operations) != step_count or step_count != len(sequence.get("steps", []))
            or bundle["final_revision"] != 1 + step_count):
        raise WorkspaceError("HANDOFF_REVISION_SEQUENCE", "Operation count or revision sequence differs from the host sequence contract")
    if bundle["handoff_id"] != f"{sequence['sequence_id']}->{contract['mission_id']}":
        raise WorkspaceError("HANDOFF_DESTINATION_MISMATCH", "Handoff identifier does not match source and destination contracts")
    if stream.get("retired_handles", []) != [] or sorted(stream.get("portable_handles", [])) != bundle["live_handles"]:
        raise WorkspaceError("HANDOFF_IDENTITY_LEDGER", "Portable live/retired handle ledger differs from the handoff")
    expected_op_handles = []
    for index, (operation, step) in enumerate(zip(operations, sequence["steps"])):
        handle = step["function"]["portable_handle"]
        if (operation.get("operation") != "create_numeric_function" or operation.get("portable_handle") != handle
                or operation.get("arguments", {}).get("name") != step["function"]["name"]
                or operation.get("arguments", {}).get("parameters") != step["function"]["parameters"]
                or step.get("expected_base_revision") != index + 1):
            raise WorkspaceError("HANDOFF_OPERATION_ORDER", f"Constructor {index} does not match the ordered host sequence")
        expected_op_handles.append(handle)
    if len(set(expected_op_handles)) != len(expected_op_handles):
        raise WorkspaceError("HANDOFF_IDENTITY_DUPLICATE", "Sequence reuses a function portable handle")
    commits = {row.get("resulting_revision"): row for row in history if row.get("event") == "transaction_committed"}
    # Reconstruct each prefix using the canonical dispatcher, then verify its
    # revision-bound checkpoint, semantic fingerprint, signatures and edges.
    for prefix in range(1, step_count + 1):
        key_cp, key_val = f"checkpoint_{prefix}", f"validation_{prefix}"
        if key_cp not in resolved or key_val not in resolved:
            raise WorkspaceError("HANDOFF_CHECKPOINT_MISSING", f"Missing checkpoint or host receipt for prefix {prefix}")
        checkpoint, receipt = _read_json(resolved[key_cp]), _read_json(resolved[key_val])
        revision = prefix + 1
        expected_completed = [{"step_id": row["step_id"], "mission_id": row["mission_id"],
            "revision": offset + 2, "validated": True} for offset, row in enumerate(sequence["steps"][:prefix])]
        expected_active = sequence["steps"][prefix]["step_id"] if prefix < step_count else None
        if (checkpoint.get("revision") != revision or checkpoint.get("sequence_id") != sequence["sequence_id"]
                or checkpoint.get("sequence_fingerprint") != _canonical_sha(sequence)
                or checkpoint.get("completed_steps") != expected_completed
                or checkpoint.get("active_step_id") != expected_active):
            # Final handle set is checked below; intermediate checkpoints carry
            # a strict prefix, not the final stream's full handle set.
            raise WorkspaceError("HANDOFF_CHECKPOINT_REVISION", f"Checkpoint does not attest revision {revision}")
        prefix_ws = Workspace()
        prefix_doc = prefix_ws.create_empty_document(f"memory://cycle36/handoff-prefix-{prefix}.bas")["document_id"]
        replay = replay_constructive_stream(prefix_ws, prefix_doc, operations[:prefix], expected_start_revision=1)
        normalized = _normalized(prefix_ws, prefix_doc, revision, dict(replay.live_handles))
        fingerprint = _fingerprint(revision, normalized)
        if (fingerprint != checkpoint.get("semantic_fingerprint")
                or sorted(replay.live_handles) != checkpoint.get("portable_handles")
                or _signatures(normalized) != checkpoint.get("function_signatures")
                or _dependencies(normalized) != checkpoint.get("dependencies")):
            raise WorkspaceError("HANDOFF_CHECKPOINT_SEMANTICS", f"Replayed prefix {revision} differs from its checkpoint")
        if prefix == step_count and checkpoint.get("portable_handles") != sorted(stream.get("portable_handles", [])):
            raise WorkspaceError("HANDOFF_FINAL_IDENTITIES", "Final checkpoint handles differ from the constructive stream")
        if commits.get(revision, {}).get("semantic_snapshot") != normalized:
            raise WorkspaceError("HANDOFF_COMMIT_SNAPSHOT", f"History has no matching semantic snapshot for revision {revision}")
        step = sequence["steps"][prefix - 1]
        commit = commits.get(revision, {})
        if (commit.get("actor") != "mission_gateway" or commit.get("operation") != "create_numeric_function"
                or commit.get("mission_id") != step["mission_id"] or commit.get("portable_handle") != step["function"]["portable_handle"]
                or commit.get("base_revision") != revision - 1):
            raise WorkspaceError("HANDOFF_COMMIT_PROVENANCE", f"Revision {revision} lacks the matching authorized constructor commit")
        expected = step["validation"]["expected_results"]
        expected_by_input = {str(value): expected[str(value)] for value in step["validation"]["inputs"]}
        if (receipt.get("actor") != "host" or receipt.get("mission_complete") is not True
                or receipt.get("executed_revision") != revision or receipt.get("revision") != revision
                or receipt.get("expected_results", {}).get("interp") != expected_by_input
                or receipt.get("expected_results", {}).get("jit") != expected_by_input
                or receipt.get("observed_results", {}).get("interp") != expected_by_input
                or receipt.get("observed_results", {}).get("jit") != expected_by_input
                or receipt.get("engines_agree") is not True or receipt.get("values_match") is not True
                or receipt.get("replay", {}).get("passed") is not True):
            raise WorkspaceError("HANDOFF_VALIDATION_RECEIPT", f"Host validation receipt for revision {revision} is incomplete or inconsistent")
    if (bundle["final_revision"] != step_count + 1 or bundle["semantic_fingerprint"] != fingerprint
            or bundle["function_signatures"] != _signatures(normalized)
            or bundle["dependencies"] != _dependencies(normalized)):
        raise WorkspaceError("HANDOFF_FINAL_STATE", "Final replay state differs from the authenticated handoff summary")
    final_validation = resolved[f"validation_{step_count}"]
    return {"passed": True, "source_sequence_id": bundle["source_sequence_id"],
        "revision": bundle["final_revision"], "semantic_fingerprint": bundle["semantic_fingerprint"],
        "portable_handle_count": len(bundle["live_handles"]), "checkpoint_count": step_count,
        "source_stream": str(resolved["constructive_stream"]), "source_history": str(resolved["history"]),
        "source_validation": str(final_validation), "contract_id": contract["mission_id"],
        "artifact_count": len(resolved)}
