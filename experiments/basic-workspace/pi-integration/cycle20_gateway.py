#!/usr/bin/env python3
"""Contract-configured numeric literal maintenance gateway for semantic edits."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.projection import build_projection, projection_semantics
from basic_workspace.mir_execution import MirExecutionService
from pi_lifecycle import completion_states
from gateway import Server


def _load_senior():
    spec = importlib.util.spec_from_file_location("cycle20_senior", ROOT / "scripts/is-senior-campaign.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


senior = _load_senior()
BASE = HERE / "results/cycle19b-recovery/real-agent-02"
MISSION_ID = "cycle20.clamp-score-cap50.v1"
PROFILE_ID = "basic-workspace.numeric-composition.v1"
INPUTS = (-100, -1, 0, 1, 49, 50, 51, 59, 60, 80, 99, 100, 101, 200)
DEFAULT_CONTRACT = HERE / "contracts/numeric-edit/cycle20-cap50.json"
REVISION4_BASE = HERE / "results/cycle20b-semantic-edit-recovery/real-agent-02"


def _calls(value):
    if isinstance(value, list):
        for child in value:
            yield from _calls(child)
    elif isinstance(value, dict):
        if value.get("kind") == "call" and isinstance(value.get("function_handle"), str):
            yield value["function_handle"]
        for child in value.values():
            yield from _calls(child)


def _call_edges(state):
    return senior.candidate_call_edges(state)


def _set_semantic_path(root, path, value, expected):
    cursor = root
    for key in path[:-1]:
        cursor = cursor[key]
    leaf = path[-1]
    if not isinstance(cursor, dict) or cursor.get(leaf) != expected:
        raise WorkspaceError("MISSION_CANDIDATE_MISMATCH", "Candidate does not contain the authorized old literal")
    cursor[leaf] = value


class Cycle20Gateway:
    """One numeric-literal maintenance gateway configured by a host contract.

    ``baseline_dir`` retains the verified Cycle 19B seed adapter. A recorded
    constructive stream can instead seed a later mission through
    ``baseline_stream_path`` plus its commit and validation evidence.
    """
    def __init__(self, output: Path, baseline_dir: Path = BASE, *,
                 contract_path: Path = DEFAULT_CONTRACT,
                 baseline_stream_path: Path | None = None,
                 baseline_history_path: Path | None = None,
                 baseline_validation_path: Path | None = None):
        self.output = output.resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.baseline_dir = baseline_dir.resolve()
        self.contract_path = contract_path.resolve()
        self.contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        self._validate_contract_shape(self.contract)
        self.mission_id = self.contract["mission_id"]
        self.baseline_stream_path = baseline_stream_path.resolve() if baseline_stream_path else None
        self.baseline_history_path = baseline_history_path.resolve() if baseline_history_path else None
        self.baseline_validation_path = baseline_validation_path.resolve() if baseline_validation_path else None
        self.lock = threading.RLock()
        self.ws = Workspace()
        self.doc = self.ws.create_empty_document(f"memory://{self.mission_id}/reconstructed.bas")["document_id"]
        self.aliases: dict[str, str] = {}
        self.discovered: set[str] = set()
        self.preview_pending: dict[str, dict[str, Any]] = {}
        self.committed = False
        self.seq = 0
        self.pi_seen: set[str] = set()
        self.trace_path = self.output / "history.jsonl"
        self.visual_path = self.output / "visual-events.jsonl"
        self.timing_path = self.output / "gateway-tool-timings.jsonl"
        self.pi_path = self.output / "pi-tool-lifecycle.jsonl"
        # Use the actual campaign output identity so separate Cycle 20 runs
        # cannot be mislabeled as the original real-agent-01 session.
        # Keep the historical Cycle 20 presentation namespace stable; the
        # output directory still distinguishes later contract-driven runs.
        self.session_id = f"cycle20-{self.output.name}"
        self.executor = MirExecutionService(timeout=20)
        self.constructive_ops = []
        if self.baseline_stream_path:
            self._reconstruct_from_operation_stream()
        else:
            self._reconstruct_baseline()
        self.baseline_aliases = dict(self.aliases)
        self._validate_contract_against_baseline()

    def record_gateway_timing(self, request: dict[str, Any], elapsed_ms: float):
        """Implement the shared Pi bridge instrumentation hook."""
        method = request.get("method")
        self._log(self.timing_path, {"request_id": request.get("request_id"),
            "tool_call_id": (request.get("transport") or {}).get("tool_call_id"),
            "method": method, "agent_tool": method in {"discover_functions", "inspect_program",
                "preview_semantic_edit", "commit_preview", "validate_mission"},
            "elapsed_ms": round(elapsed_ms, 3),
            "observed_monotonic_ns": time.monotonic_ns()})

    def flush_trace(self):
        """Trace writes are append-and-close; present for bridge error handling."""
        return None

    @staticmethod
    def write_json(path: Path, value: Any):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _validate_contract_shape(contract):
        required = {"schema", "version", "mission_id", "objective", "base_document_revision",
            "execution_profile_id", "allowed_function_handles", "authorized_targets", "minimum_edits",
            "maximum_edits", "unchanged_function_handles", "required_dependency_edges",
            "revision_increment", "validation"}
        if not isinstance(contract, dict) or set(contract) != required:
            raise WorkspaceError("MISSION_CONTRACT_INVALID", "Maintenance contract has missing or unsupported fields")
        if contract["schema"] != "basic-workspace.numeric-literal-maintenance-contract" or contract["version"] != 1:
            raise WorkspaceError("MISSION_CONTRACT_VERSION", "Unsupported numeric-literal maintenance contract")
        if (not isinstance(contract["mission_id"], str) or not contract["mission_id"]
                or not isinstance(contract["objective"], str) or not contract["objective"]):
            raise WorkspaceError("MISSION_CONTRACT_INVALID", "Mission identifier and objective are required")
        for field in ("base_document_revision", "minimum_edits", "maximum_edits", "revision_increment"):
            if isinstance(contract[field], bool) or not isinstance(contract[field], int) or contract[field] < 0:
                raise WorkspaceError("MISSION_CONTRACT_INVALID", f"{field} must be a non-negative integer")
        if contract["minimum_edits"] < 1 or contract["maximum_edits"] < contract["minimum_edits"]:
            raise WorkspaceError("MISSION_CONTRACT_INVALID", "Contract edit bounds are inconsistent")
        for field in ("allowed_function_handles", "authorized_targets", "unchanged_function_handles", "required_dependency_edges"):
            if not isinstance(contract[field], list):
                raise WorkspaceError("MISSION_CONTRACT_INVALID", f"{field} must be an array")
        if not contract["allowed_function_handles"] or not contract["authorized_targets"]:
            raise WorkspaceError("MISSION_CONTRACT_INVALID", "At least one function and literal target must be authorized")
        if len(contract["authorized_targets"]) < contract["minimum_edits"]:
            raise WorkspaceError("MISSION_CONTRACT_INVALID", "Authorized target count is below the minimum edit count")
        validation = contract["validation"]
        if not isinstance(validation, dict) or set(validation) != {"inputs", "functions"}:
            raise WorkspaceError("MISSION_CONTRACT_INVALID", "Validation requires inputs and function oracle declarations")
        if not isinstance(validation["inputs"], list) or not validation["inputs"] or not isinstance(validation["functions"], list) or not validation["functions"]:
            raise WorkspaceError("MISSION_CONTRACT_INVALID", "Validation inputs and function oracles must be nonempty arrays")
        for oracle in validation["functions"]:
            if not isinstance(oracle, dict) or set(oracle) != {"function_handle", "result_key", "oracle"}:
                raise WorkspaceError("MISSION_CONTRACT_INVALID", "Each function oracle requires a handle, result key, and supported oracle")
            spec = oracle["oracle"]
            if not isinstance(spec, dict) or spec.get("kind") not in {"clamp", "threshold_call"}:
                raise WorkspaceError("MISSION_CONTRACT_ORACLE", "Only clamp and threshold_call host oracles are supported")
            expected_fields = ({"kind", "minimum", "maximum"} if spec["kind"] == "clamp" else
                {"kind", "callee_handle", "threshold", "true_value", "false_value"})
            if set(spec) != expected_fields:
                raise WorkspaceError("MISSION_CONTRACT_ORACLE", "Oracle declaration contains missing or unsupported fields")
            if spec["kind"] == "threshold_call" and not isinstance(spec["callee_handle"], str):
                raise WorkspaceError("MISSION_CONTRACT_ORACLE", "threshold_call requires a portable callee handle")
            numeric_fields = ("minimum", "maximum") if spec["kind"] == "clamp" else ("threshold", "true_value", "false_value")
            for field in numeric_fields:
                value = spec[field]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                    raise WorkspaceError("MISSION_CONTRACT_ORACLE", f"Oracle field {field} must be a finite number")
            if spec["kind"] == "clamp" and float(spec["minimum"]) > float(spec["maximum"]):
                raise WorkspaceError("MISSION_CONTRACT_ORACLE", "Clamp oracle bounds are inverted")

    def _oracle_value(self, function_handle, argument, active=None):
        active = set() if active is None else active
        if function_handle in active:
            raise WorkspaceError("MISSION_CONTRACT_ORACLE", "Recursive host oracle references are unsupported")
        row = next((item for item in self.contract["validation"]["functions"]
            if item["function_handle"] == function_handle), None)
        if row is None:
            raise WorkspaceError("MISSION_CONTRACT_ORACLE", f"No host oracle is configured for {function_handle}")
        spec = row["oracle"]
        if spec["kind"] == "clamp":
            return min(float(spec["maximum"]), max(float(spec["minimum"]), float(argument)))
        active.add(function_handle)
        observed = self._oracle_value(spec["callee_handle"], argument, active)
        active.remove(function_handle)
        return float(spec["true_value"] if observed >= float(spec["threshold"]) else spec["false_value"])

    def _log(self, path: Path, row: dict[str, Any]):
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    def _emit(self, event: dict[str, Any]):
        self.seq += 1
        event.setdefault("presentation_sequence", self.seq)
        event.setdefault("event_id", f"maintenance-{self.seq}-{uuid.uuid4().hex[:8]}")
        event.setdefault("session_id", self.session_id)
        event.setdefault("mission_id", self.mission_id)
        self._log(self.visual_path, event)

    def _history(self, event: str, actor: str, **fields):
        self._log(self.trace_path, {"sequence": self.seq + 1, "event": event, "actor": actor,
            "mission_id": self.mission_id, "observed_monotonic_ns": time.monotonic_ns(), **fields})

    def _normalized(self, revision: int | None = None):
        return senior.normalized_state(projection_semantics(build_projection(
            self.ws, self.doc, revision or self.ws.get_revision(self.doc))), self.aliases)

    @staticmethod
    def _fingerprint(normalized: dict[str, Any], revision: int):
        payload = json.dumps({"profile": PROFILE_ID, "revision": revision, "semantics": normalized},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        return hashlib.sha256(payload).hexdigest()

    def _reconstruct_baseline(self):
        stream_path = self.baseline_dir / "constructive-operations.json"
        checkpoint_path = self.baseline_dir / "mission-2-recovery-checkpoint.json"
        baseline_path = self.baseline_dir / "mission-2-baseline.json"
        host_validation_path = self.baseline_dir / "mission-2-host-validation.json"
        history_path = self.baseline_dir / "history.jsonl"
        for path in (stream_path, checkpoint_path, baseline_path, host_validation_path, history_path):
            if not path.is_file():
                raise WorkspaceError("BASELINE_EVIDENCE_MISSING", f"Required Cycle 19B evidence is missing: {path.name}")
        stream = json.loads(stream_path.read_text(encoding="utf-8"))
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        revision2_baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        previous_validation = json.loads(host_validation_path.read_text(encoding="utf-8"))
        events = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if stream.get("schema") != "basic-workspace.constructive-metafile" or stream.get("version") != 1:
            raise WorkspaceError("BASELINE_STREAM_SCHEMA", "Cycle 19B constructive stream has an unsupported schema")
        if stream.get("execution_profile_id") != PROFILE_ID or checkpoint.get("execution_profile_id") != PROFILE_ID:
            raise WorkspaceError("BASELINE_PROFILE_MISMATCH", "Cycle 19B stream/checkpoint use an unexpected execution profile")
        operations = stream.get("operations")
        if not isinstance(operations, list) or len(operations) != 2:
            raise WorkspaceError("BASELINE_OPERATION_COUNT", "The exact two-function Cycle 19B stream is required")
        expected_specs = [("clamp_score.function", "CLAMP_SCORE"), ("is_passing.function", "IS_PASSING")]
        for operation, (handle, name) in zip(operations, expected_specs):
            if operation.get("operation") != "create_numeric_function" or operation.get("portable_handle") != handle:
                raise WorkspaceError("BASELINE_OPERATION_ORDER", "Expected original CLAMP_SCORE then IS_PASSING operations")
            if operation.get("arguments", {}).get("name") != name:
                raise WorkspaceError("BASELINE_OPERATION_MISMATCH", f"Portable operation does not construct {name}")
        commit = [row for row in events if row.get("event") == "transaction_committed"
                  and row.get("mission_id") == "cycle19.classify-passing.v1"]
        if len(commit) != 1 or commit[0].get("resulting_revision") != 3:
            raise WorkspaceError("BASELINE_COMMIT_EVIDENCE", "Cycle 19B must contain one genuine revision-3 Mission 2 commit")
        # Replay the first genuine operation and check the verified recovery checkpoint
        # before applying the second operation.
        first = operations[0]
        args = senior.resolve_function_handles(first["arguments"], self.aliases, set())
        applied = self.ws.apply_transaction(self.doc, 1, [{"operation": "create_numeric_function", **args}])
        if applied["revision"] != 2:
            raise WorkspaceError("BASELINE_REVISION_MISMATCH", "CLAMP_SCORE replay did not produce revision 2")
        raw = projection_semantics(build_projection(self.ws, self.doc, 2))
        self.aliases = senior.aliases_for_new_function(raw, {}, "CLAMP_SCORE", first["portable_handle"])
        clamp_state = senior.normalized_state(raw, self.aliases)
        if clamp_state != revision2_baseline.get("normalized_program"):
            raise WorkspaceError("BASELINE_CLAMP_CHECKPOINT_MISMATCH", "CLAMP_SCORE differs from the revision-2 verified checkpoint")
        if self._fingerprint(clamp_state, 2) != checkpoint.get("semantic_fingerprint"):
            raise WorkspaceError("BASELINE_FINGERPRINT_MISMATCH", "Revision-2 semantic checkpoint fingerprint does not match replay")
        self.revision2_fingerprint = self._fingerprint(clamp_state, 2)
        if checkpoint.get("revision") != 2:
            raise WorkspaceError("BASELINE_CHECKPOINT_REVISION", "The recovery checkpoint must be bound to revision 2")
        self.constructive_ops.append(first)

        second = operations[1]
        call_handles = set(_calls(second["arguments"]))
        if call_handles != {"clamp_score.function"} or second.get("callee_handle") != "clamp_score.function":
            raise WorkspaceError("BASELINE_DEPENDENCY_HANDLE", "IS_PASSING must reference the portable CLAMP_SCORE handle")
        resolved = senior.resolve_function_handles(second["arguments"], self.aliases, call_handles)
        applied = self.ws.apply_transaction(self.doc, 2, [{"operation": "create_numeric_function", **resolved}])
        if applied["revision"] != 3:
            raise WorkspaceError("BASELINE_REVISION_MISMATCH", "IS_PASSING replay did not produce revision 3")
        raw = projection_semantics(build_projection(self.ws, self.doc, 3))
        self.aliases = senior.aliases_for_new_function(raw, self.aliases, "IS_PASSING", second["portable_handle"])
        self.baseline = senior.normalized_state(raw, self.aliases)
        if self.baseline != commit[0].get("semantic_snapshot"):
            raise WorkspaceError("BASELINE_SEMANTIC_MISMATCH", "Full replay differs from the genuine committed revision-3 snapshot")
        if revision2_baseline.get("revision") != 2 or revision2_baseline.get("semantic_fingerprint") != checkpoint.get("semantic_fingerprint"):
            raise WorkspaceError("BASELINE_CHECKPOINT_MISMATCH", "Mission 2 baseline and recovery checkpoint disagree")
        old_observed = self._run_observations(self.ws, self.doc, 3, self.aliases)
        recorded_observed = previous_validation.get("observed_results", {})
        recorded_inputs = set(recorded_observed.get("interp", {}))
        matching_subset = {engine: {value: old_observed[engine][value] for value in recorded_inputs}
            for engine in ("interp", "jit")}
        if matching_subset != recorded_observed:
            raise WorkspaceError("BASELINE_BEHAVIOR_MISMATCH", "Reconstructed behavior differs from the genuine host validation")
        if old_observed["interp"] != old_observed["jit"]:
            raise WorkspaceError("BASELINE_ENGINE_MISMATCH", "Reconstructed MIR engines disagree")
        self.constructive_ops.append(second)
        self.base_revision = 3
        self.baseline_observed = old_observed
        self.initial_code = self.ws.render_document(self.doc)
        self.edit_targets = self._discover_authorized_targets()
        self._check_baseline_identity_provenance()
        self._write_contracts(stream)
        self.write_json(self.output / "baseline-reconstruction.json", {
            "schema": "basic-workspace.cycle20-baseline-reconstruction", "version": 1,
            "source_stream": str(stream_path), "starting_document_empty": True,
            "replay_actor": "host_deterministic_replay", "resulting_revision": 3,
            "revision2_checkpoint_fingerprint_match": True,
            "revision3_normalized_semantics_match": True,
            "prior_interpreter_jit_results_match": True, "interpreter_jit_agree": True,
            "portable_identity_count": len(self.aliases),
            "identities_remapped_from_source": all(row["remapped"] for row in self.initial_identity_map),
            "identity_mapping": self.initial_identity_map,
            "dependencies": self.dependencies(), "passed": True})
        self.write_json(self.output / "mission.json", self.mission_contract())
        self.write_json(self.output / "execution-profile.json",
            json.loads((ROOT / "results/semantic-replay/execution-profile.json").read_text(encoding="utf-8")))
        self.write_json(self.output / "visual-source.json", {
            "schema": "basic-workspace.visual-source", "version": 1,
            "campaign": {"id": "cycle20-semantic-evolution", "title": "Cycle 20 · semantic evolution of CLAMP_SCORE", "filename": "SCORES.bas"},
            "initial": {"revision": 3, "code": self.initial_code, "dependencies": self.dependencies()},
            "snapshots": {"3": self.initial_code}})
        self.write_json(self.output / "baseline-observations.json", {
            "revision": 3, "actor": "host_validation_of_reconstruction", "observed_results": self.baseline_observed,
            "dependency_edges": self.dependencies(), "expectation_source": "independent host-owned pre-edit oracle"})
        self._history("program_reconstructed", "host_deterministic_replay", revision=3,
            source_operation_count=2, normalized_equivalence=True, checkpoint_fingerprint_match=True,
            behavior_match=True, identity_count=len(self.aliases))
        self._history("checkpoint_verified", "host_validation", revision=2,
            semantic_fingerprint=checkpoint["semantic_fingerprint"], before_second_constructor=True)
        self._history("session_started", "host", revision=3, mission_id=self.mission_id, model_session="fresh_pi_session")
        self._emit({"event_type": "initial", "revision": 3,
            "provenance": "Committed baseline after host deterministic replay; no Cycle 20 model action",
            "title": "Committed baseline · revision 3",
            "description": "The exact Cycle 19B two-function operation stream was rebuilt in an empty Workspace and independently verified. The Pi agent has not acted.",
            "mission_status": "Mission pending · committed revision 3", "snapshot": self.initial_code,
            "dependencies": self.dependencies(),
            "focus": {"handles": ["clamp_score.function", "is_passing.function"], "mapping": "verified_function_boundary"}})
        self._emit({"event_type": "reconstruction", "revision": 3,
            "provenance": "Committed baseline after verified host replay; no Cycle 20 model action yet",
            "title": "Verified two-function baseline reconstructed",
            "description": "Exact CLAMP_SCORE and IS_PASSING operations were replayed; revision-2 fingerprint, revision-3 semantics and MIR observations match the recorded evidence.",
            "mission_status": "Mission pending · committed revision 3", "snapshot": self.initial_code,
            "dependencies": self.dependencies(),
            "focus": {"handles": ["clamp_score.function", "is_passing.function"], "mapping": "verified_function_boundary"},
            "outcome": {"workspace_revision": 3, "normalized_equivalence": True, "behavior_match": True}})

    def _check_baseline_identity_provenance(self):
        old_ids: dict[str, str] = {}
        original = HERE / "results/cycle19-empty-workspace/real-agent-01/history.jsonl"
        cycle19b = self.baseline_dir / "history.jsonl"
        for path in (original, cycle19b):
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            for row in rows:
                if row.get("event") != "transaction_committed":
                    continue
                handle = row.get("portable_handle")
                if handle not in ("clamp_score.function", "is_passing.function"):
                    continue
                stem = handle.rsplit(".", 1)[0]
                for entity in row.get("created_entities", []):
                    if entity.get("kind") == "function": old_ids[handle] = entity["symbol_id"]
                    elif entity.get("kind") == "parameter": old_ids[f"{stem}.parameter.id"] = entity["symbol_id"]
                for index, statement in enumerate(row.get("created_statements", [])):
                    old_ids[f"{stem}.statement.{index}"] = statement["statement_id"]
        if set(old_ids) != set(self.aliases):
            raise WorkspaceError("BASELINE_IDENTITY_PROVENANCE", "Cycle 19B commits do not cover the stream's portable identity set")
        self.initial_identity_map = [{"portable_handle": handle, "source_workspace_id": old_ids[handle],
            "reconstructed_workspace_id": self.aliases[handle], "remapped": old_ids[handle] != self.aliases[handle]}
            for handle in sorted(self.aliases)]

    def _write_contracts(self, stream):
        contract = self.mission_contract()
        self.write_json(self.output / "MISSION.json", contract)
        self.write_json(self.output / "constructive-base.json", stream)

    def mission_contract(self):
        return copy.deepcopy(self.contract)

    @staticmethod
    def _find_assignment(items, statement_handle):
        for item in items:
            if item.get("kind") == "assignment" and item.get("statement_handle") == statement_handle:
                return item
            for block_name in ("then", "else", "body"):
                children = item.get(block_name)
                if isinstance(children, list):
                    found = Cycle20Gateway._find_assignment(children, statement_handle)
                    if found is not None:
                        return found
        return None

    @classmethod
    def _target_expression(cls, state, target):
        if not isinstance(target, dict) or "function_handle" not in target or not isinstance(target.get("expression_path"), list):
            raise WorkspaceError("MISSION_EDIT_TARGETS", "Target must use a function handle and explicit expression_path")
        allowed_shapes = (
            {"function_handle", "control_path", "expression_path"},
            {"function_handle", "statement_handle", "expression_path"})
        if set(target) not in allowed_shapes:
            raise WorkspaceError("MISSION_EDIT_TARGETS", "Target must be a typed control path or statement handle")
        function = next((row for row in state["functions"] if row.get("handle") == target["function_handle"]), None)
        if function is None:
            raise WorkspaceError("MISSION_EDIT_TARGETS", "Target function handle is unresolved")
        if "statement_handle" in target:
            statement = cls._find_assignment(function["statements"], target["statement_handle"])
            if statement is None or statement.get("target_handle") != target["function_handle"] or not statement.get("target_is_result"):
                raise WorkspaceError("MISSION_EDIT_TARGETS", "Statement handle is not an assignment to its function result")
            selected = statement.get("expression")
        else:
            path = target["control_path"]
            if not isinstance(path, list) or not path:
                raise WorkspaceError("MISSION_EDIT_TARGETS", "Control path must contain at least one typed step")
            block = function["statements"]
            statement = None
            for step_index, step in enumerate(path):
                if not isinstance(step, dict) or set(step) != {"block", "index"} or step["block"] not in {"body", "then", "else"}:
                    raise WorkspaceError("MISSION_EDIT_TARGETS", "Control path contains an unsupported block step")
                index = step["index"]
                if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(block):
                    raise WorkspaceError("MISSION_EDIT_TARGETS", "Control path index is missing or out of range")
                statement = block[index]
                if step_index + 1 < len(path):
                    next_block = path[step_index + 1].get("block")
                    block = statement.get(next_block) if next_block in {"then", "else", "body"} else None
                    if not isinstance(block, list):
                        raise WorkspaceError("MISSION_EDIT_TARGETS", "Intermediate control path does not select a structured block")
            if statement is None or statement.get("kind") != "if":
                raise WorkspaceError("MISSION_EDIT_TARGETS", "Control path does not resolve to an IF condition")
            condition = statement.get("condition", {})
            if condition.get("kind") != "compare" or len(condition.get("children", [])) != 2:
                raise WorkspaceError("MISSION_EDIT_TARGETS", "Only two-operand numeric comparisons are supported")
            selected = condition
        for child_index in target["expression_path"]:
            if isinstance(child_index, bool) or not isinstance(child_index, int):
                raise WorkspaceError("MISSION_EDIT_TARGETS", "Expression path indexes must be integers")
            children = selected.get("children", []) if isinstance(selected, dict) else []
            if not 0 <= child_index < len(children):
                raise WorkspaceError("MISSION_EDIT_TARGETS", "Expression path is ambiguous or out of range")
            selected = children[child_index]
        if not isinstance(selected, dict) or selected.get("kind") != "number" or "value" not in selected:
            raise WorkspaceError("MISSION_EDIT_TARGETS", "Selected expression is not a numeric literal")
        return function, statement, selected

    @classmethod
    def _set_target_value(cls, state, target, expected, replacement):
        _function, _statement, leaf = cls._target_expression(state, target)
        if float(leaf["value"]) != float(expected):
            raise WorkspaceError("MISSION_CANDIDATE_MISMATCH", "Candidate literal differs from its authorized expected value")
        leaf["value"] = float(replacement)

    def _reconstruct_from_operation_stream(self):
        if not self.baseline_stream_path or not self.baseline_history_path or not self.baseline_validation_path:
            raise WorkspaceError("BASELINE_EVIDENCE_MISSING", "Stream-based baseline requires its commit history and validation evidence")
        stream = json.loads(self.baseline_stream_path.read_text(encoding="utf-8"))
        history = [json.loads(line) for line in self.baseline_history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        recorded_validation = json.loads(self.baseline_validation_path.read_text(encoding="utf-8"))
        if stream.get("schema") != "basic-workspace.constructive-metafile" or stream.get("version") != 1 or stream.get("execution_profile_id") != PROFILE_ID:
            raise WorkspaceError("BASELINE_STREAM_SCHEMA", "Baseline constructive stream is unsupported")
        if recorded_validation.get("mission_complete") is not True or recorded_validation.get("replay", {}).get("passed") is not True:
            raise WorkspaceError("BASELINE_VALIDATION_FAILED", "Recorded revision-4 baseline did not pass its host validation and replay")
        self.constructive_ops = copy.deepcopy(stream["operations"])
        for op in stream["operations"]:
            if op.get("operation") == "create_numeric_function":
                handles = set(_calls(op.get("arguments", {})))
                if any(handle not in self.aliases for handle in handles):
                    raise WorkspaceError("REPLAY_HANDLE_MISSING", "Baseline constructor references an unresolved portable function")
                args = senior.resolve_function_handles(op["arguments"], self.aliases, handles)
                applied = self.ws.apply_transaction(self.doc, self.ws.get_revision(self.doc),
                    [{"operation": "create_numeric_function", **args}])
                raw = projection_semantics(build_projection(self.ws, self.doc, applied["revision"]))
                self.aliases = senior.aliases_for_new_function(raw, self.aliases, args["name"], op["portable_handle"])
            elif op.get("operation") == "edit_numeric_literals":
                operations = self._workspace_operations_for_edits(op["edits"], self.aliases)
                self.ws.apply_transaction(self.doc, self.ws.get_revision(self.doc), operations)
            else:
                raise WorkspaceError("REPLAY_OPERATION_UNSUPPORTED", "Baseline stream contains an unsupported operation")
        revision = self.ws.get_revision(self.doc)
        if revision != self.contract["base_document_revision"]:
            raise WorkspaceError("BASELINE_REVISION_MISMATCH", "Reconstructed stream does not produce the contract's base revision")
        committed = [row for row in history if row.get("event") == "transaction_committed" and row.get("resulting_revision") == revision]
        if len(committed) != 1:
            raise WorkspaceError("BASELINE_COMMIT_EVIDENCE", "Recorded baseline must identify one authoritative commit at the expected revision")
        self.baseline = self._normalized(revision)
        if self.baseline != committed[0].get("semantic_snapshot"):
            raise WorkspaceError("BASELINE_SEMANTIC_MISMATCH", "Fresh replay differs from the recorded committed semantic snapshot")
        self.base_revision = revision
        self.baseline_observed = self._run_observations(self.ws, self.doc, revision, self.aliases)
        if self.baseline_observed["interp"] != self.baseline_observed["jit"]:
            raise WorkspaceError("BASELINE_ENGINE_MISMATCH", "Baseline interpreter and JIT observations differ")
        self.initial_code = self.ws.render_document(self.doc)
        self.edit_targets = self._discover_authorized_targets()
        self.initial_identity_map = [{"portable_handle": handle, "reconstructed_workspace_id": value, "remapped": True}
            for handle, value in sorted(self.aliases.items())]
        self.write_json(self.output / "baseline-reconstruction.json", {
            "schema": "basic-workspace.semantic-maintenance-baseline", "version": 1,
            "source_stream": str(self.baseline_stream_path), "starting_document_empty": True,
            "resulting_revision": revision, "normalized_semantics_match": True,
            "recorded_checkpoint_validation_passed": True, "interpreter_jit_agree": True,
            "portable_identity_count": len(self.aliases), "identity_mapping": self.initial_identity_map,
            "dependencies": self.dependencies(), "passed": True})
        self.write_json(self.output / "constructive-base.json", stream)
        self.write_json(self.output / "execution-profile.json",
            json.loads((ROOT / "results/semantic-replay/execution-profile.json").read_text(encoding="utf-8")))
        self.write_json(self.output / "visual-source.json", {
            "schema": "basic-workspace.visual-source", "version": 1,
            "campaign": {"id": self.mission_id, "title": self.contract["objective"], "filename": "PROGRAM.bas"},
            "initial": {"revision": revision, "code": self.initial_code, "dependencies": self.dependencies()},
            "snapshots": {str(revision): self.initial_code}})
        self.write_json(self.output / "baseline-observations.json", {
            "revision": revision, "actor": "host_validation_of_reconstruction",
            "observed_results": self.baseline_observed, "dependency_edges": self.dependencies(),
            "expectation_source": "host execution of verified constructive baseline"})
        self._history("program_reconstructed", "host_deterministic_replay", revision=revision,
            source_operation_count=len(stream["operations"]), normalized_equivalence=True,
            recorded_snapshot_match=True, behavior_match=True, identity_count=len(self.aliases))
        self._history("session_started", "host", revision=revision, mission_id=self.mission_id,
            model_session="fresh_pi_session")
        self._emit({"event_type": "initial", "revision": revision,
            "provenance": "Committed baseline after host deterministic replay; no model action",
            "title": f"Verified committed baseline · revision {revision}",
            "description": "The supplied portable operation stream was replayed in an empty Workspace and matched its committed semantic snapshot.",
            "snapshot": self.initial_code, "dependencies": self.dependencies(),
            "focus": {"handles": sorted(self.aliases), "mapping": "verified_function_boundary"}})

    def _validate_contract_against_baseline(self):
        if self.contract["execution_profile_id"] != PROFILE_ID:
            raise WorkspaceError("BASELINE_PROFILE_MISMATCH", "Contract and program use different execution profiles")
        if self.base_revision != self.contract["base_document_revision"]:
            raise WorkspaceError("BASELINE_REVISION_MISMATCH", "Workspace revision does not match the mission contract")
        handles = set(self.aliases)
        if not set(self.contract["allowed_function_handles"] + self.contract["unchanged_function_handles"]).issubset(handles):
            raise WorkspaceError("MISSION_CONTRACT_HANDLE", "Contract contains a missing portable function handle")
        expected_edges = sorted([{"caller": edge["caller_handle"], "callee": edge["callee_handle"]}
            for edge in self.contract["required_dependency_edges"]], key=lambda row: (row["caller"], row["callee"]))
        if self._dependency_edges(self.baseline) != expected_edges:
            raise WorkspaceError("MISSION_CONTRACT_DEPENDENCY", "Baseline dependency bindings do not satisfy the contract")
        self._validate_unchanged_functions(self.baseline)

    def _validate_unchanged_functions(self, state):
        for handle in self.contract["unchanged_function_handles"]:
            if senior.find_function(state, handle) != senior.find_function(self.baseline, handle):
                raise WorkspaceError("MISSION_UNCHANGED_FUNCTION", f"Function {handle} changed outside the permitted edit scope")

    def _run_observations(self, ws, doc, revision, aliases):
        results = {"interp": {}, "jit": {}}
        for engine in results:
            for value in self.contract["validation"]["inputs"]:
                row = {}
                for function_spec in self.contract["validation"]["functions"]:
                    handle = function_spec["function_handle"]
                    row[function_spec["result_key"]] = self.executor.execute_function(
                        ws, doc, revision, aliases[handle], [value], engine)["result"]
                results[engine][str(value)] = row
        return results

    def _expected_observations(self):
        return {engine: {str(value): {item["result_key"]: self._oracle_value(item["function_handle"], value)
            for item in self.contract["validation"]["functions"]}
            for value in self.contract["validation"]["inputs"]} for engine in ("interp", "jit")}

    def _dependency_edges(self, state):
        return sorted(_call_edges(state), key=lambda edge: (edge["caller"], edge["callee"]))

    def dependencies(self):
        names = {fn["handle"]: fn["name"] for fn in self.baseline["functions"]}
        return [{"caller": names.get(edge["caller"], edge["caller"]),
                 "callee": names.get(edge["callee"], edge["callee"])}
                for edge in self._dependency_edges(self.baseline)]

    def _discover_authorized_targets(self):
        result = []
        seen = set()
        for spec in self.contract["authorized_targets"]:
            if not isinstance(spec, dict) or set(spec) != {"target", "expected_original_value", "replacement_constraint", "label"}:
                raise WorkspaceError("MISSION_CONTRACT_TARGET", "Each authorized target requires a typed target, old value, constraint, and label")
            target = spec["target"]
            if target.get("function_handle") not in self.contract["allowed_function_handles"]:
                raise WorkspaceError("MISSION_CONTRACT_TARGET", "Target function is outside the contract's allowed scope")
            key = json.dumps(target, sort_keys=True)
            if key in seen:
                raise WorkspaceError("MISSION_CONTRACT_TARGET", "Contract contains an ambiguous duplicate target")
            seen.add(key)
            original = spec["expected_original_value"]
            if isinstance(original, bool) or not isinstance(original, (int, float)) or not math.isfinite(float(original)):
                raise WorkspaceError("MISSION_CONTRACT_TARGET", "Expected original values must be finite numbers")
            constraint = spec["replacement_constraint"]
            if not isinstance(constraint, dict) or set(constraint) != {"kind", "values"} or constraint["kind"] != "one_of":
                raise WorkspaceError("MISSION_CONTRACT_CONSTRAINT", "Only a bounded one_of replacement constraint is supported")
            values = constraint["values"]
            if not isinstance(values, list) or not values or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) for v in values):
                raise WorkspaceError("MISSION_CONTRACT_CONSTRAINT", "one_of must list finite numeric replacement values")
            _fn, _statement, selected = self._target_expression(self.baseline, target)
            if float(selected["value"]) != float(original):
                raise WorkspaceError("MISSION_CONTRACT_BASELINE_TARGET", "Authorized target does not contain its expected original value")
            result.append({"target": copy.deepcopy(target), "expected_value": float(original),
                "replacement_constraint": copy.deepcopy(constraint), "label": spec["label"]})
        if len(result) < self.contract["minimum_edits"]:
            raise WorkspaceError("MISSION_CONTRACT_TARGET", "Not enough unambiguous targets are declared")
        return result

    def _current_projection(self):
        return self._normalized(self.ws.get_revision(self.doc))

    def _inspect(self):
        rows = [{"target": row["target"], "current_value": row["expected_value"],
            "expression_kind": "number", "label": row["label"]} for row in self.edit_targets]
        return {"revision": self.ws.get_revision(self.doc), "structure": self._current_projection(),
            "editable_numeric_literal_targets": rows,
            # Kept as a read-only compatibility alias for the original Cycle 20
            # agent prompt. New callers should use the semantically broader key.
            "editable_upper_bound_occurrences": rows,
            "identity_note": "Function, parameter, and assignment statement handles are stable Workspace identities. IF literals use a typed function-anchored control path and are verified against the current revision."}

    def _workspace_operations_for_edits(self, edits, aliases):
        operations = []
        for edit in edits:
            if not isinstance(edit, dict) or set(edit) != {"target", "expected_value", "replacement_value"}:
                raise WorkspaceError("INVALID_EDIT_REQUEST", "Each literal edit requires exactly target, expected_value, and replacement_value")
            target = edit["target"]
            function_id = aliases.get(target.get("function_handle")) if isinstance(target, dict) else None
            if function_id is None:
                raise WorkspaceError("UNKNOWN_FUNCTION_HANDLE", "Target function handle is not resolved")
            for value_name in ("expected_value", "replacement_value"):
                value = edit[value_name]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                    raise WorkspaceError("INVALID_LITERAL_EDIT", f"{value_name} must be a finite number")
            op = {"operation": "edit_numeric_literal_at_path", "function_id": function_id,
                "expression_path": target["expression_path"], "expected_value": edit["expected_value"],
                "replacement_value": edit["replacement_value"]}
            if "control_path" in target:
                op.update(target_kind="if_condition_rhs", control_path=target["control_path"])
            elif "statement_handle" in target:
                statement_id = aliases.get(target["statement_handle"])
                if statement_id is None:
                    raise WorkspaceError("UNKNOWN_STATEMENT_HANDLE", "Assignment statement handle is unresolved")
                op.update(target_kind="assignment_rhs", statement_id=statement_id)
            else:
                raise WorkspaceError("MISSION_EDIT_TARGETS", "Target must include a control path or statement handle")
            operations.append(op)
        return operations

    def _make_workspace_operations(self, request):
        if set(request) != {"expected_revision", "function_handle", "edits"}:
            raise WorkspaceError("INVALID_EDIT_REQUEST", "Edit request requires expected_revision, function_handle, and edits")
        revision = request["expected_revision"]
        if revision != self.ws.get_revision(self.doc):
            raise WorkspaceError("STALE_REVISION", "Edit base revision is stale")
        if self.committed:
            raise WorkspaceError("MISSION_EDIT_LIMIT", "Contract permits one committed atomic edit")
        handle = request["function_handle"]
        if handle not in self.discovered:
            raise WorkspaceError("FUNCTION_NOT_DISCOVERED", "Discover the target function before proposing an edit")
        if handle not in self.contract["allowed_function_handles"]:
            raise WorkspaceError("MISSION_EDIT_SCOPE", "Target function is outside the mission's allowed scope")
        edits = request["edits"]
        if not isinstance(edits, list) or not self.contract["minimum_edits"] <= len(edits) <= self.contract["maximum_edits"]:
            raise WorkspaceError("MISSION_EDIT_COUNT", "Edit count is outside the mission contract bounds")
        actual = [edit.get("target") for edit in edits if isinstance(edit, dict)]
        if len(actual) != len(edits):
            raise WorkspaceError("INVALID_EDIT_REQUEST", "Each edit requires a typed target")
        target_keys = [json.dumps(target, sort_keys=True) for target in actual]
        if len(set(target_keys)) != len(target_keys):
            raise WorkspaceError("DUPLICATE_EDIT_TARGET", "The same semantic literal target was selected more than once")
        target_map = {json.dumps(row["target"], sort_keys=True): row for row in self.edit_targets}
        if set(target_keys) != set(target_map):
            raise WorkspaceError("MISSION_EDIT_TARGETS", "Candidate must select exactly the authorized semantic literal targets")
        for edit, key in zip(edits, target_keys):
            target_spec = target_map[key]
            if edit["target"]["function_handle"] != handle:
                raise WorkspaceError("MISSION_EDIT_SCOPE", "Every edit must target the selected discovered function")
            if edit["expected_value"] != target_spec["expected_value"]:
                raise WorkspaceError("MISSION_LITERAL_VALUES", "Expected old value does not match the contract precondition")
            if edit["replacement_value"] not in target_spec["replacement_constraint"]["values"]:
                raise WorkspaceError("MISSION_LITERAL_VALUES", "Replacement value violates the host-owned mission constraint")
        return self._workspace_operations_for_edits(edits, self.aliases)

    def _authorize_candidate(self, request):
        if self.ws.get_revision(self.doc) != request["expected_revision"]:
            raise WorkspaceError("STALE_REVISION", "Workspace changed since this proposal was based")
        operations = self._make_workspace_operations(request)
        candidate_info = self.ws.preview_transaction_semantics(self.doc, request["expected_revision"], operations)
        candidate = senior.normalized_state(candidate_info["candidate_semantics"], self.aliases)
        expected = copy.deepcopy(self.baseline)
        target_map = {json.dumps(row["target"], sort_keys=True): row for row in self.edit_targets}
        for edit in request["edits"]:
            row = target_map[json.dumps(edit["target"], sort_keys=True)]
            self._set_target_value(expected, row["target"], row["expected_value"], edit["replacement_value"])
        if candidate != expected:
            raise WorkspaceError("MISSION_CANDIDATE_MISMATCH", "Typed candidate contains changes outside the authorized literal targets")
        for handle in self.contract["unchanged_function_handles"]:
            if senior.find_function(candidate, handle) != senior.find_function(self.baseline, handle):
                raise WorkspaceError("MISSION_UNCHANGED_FUNCTION", f"Function {handle} must remain structurally unchanged")
        before_edges = self._dependency_edges(self.baseline)
        after_edges = self._dependency_edges(candidate)
        required_edges = sorted([{"caller": row["caller_handle"], "callee": row["callee_handle"]}
            for row in self.contract["required_dependency_edges"]], key=lambda row: (row["caller"], row["callee"]))
        if before_edges != after_edges or after_edges != required_edges:
            raise WorkspaceError("MISSION_DEPENDENCY_CHANGED", "Required semantic function dependencies must remain unchanged")
        preview = self.ws.preview_transaction(self.doc, request["expected_revision"], operations, include_diff=True)
        candidate_ws = copy.deepcopy(self.ws)
        before_tokens = {token.uid: token.text for token in self.ws.documents[self.doc].tokens}
        applied = candidate_ws.apply_transaction(self.doc, request["expected_revision"], operations)
        after_tokens = {token.uid: token.text for token in candidate_ws.documents[self.doc].tokens}
        changed_token_ids = sorted(uid for uid in before_tokens if before_tokens[uid] != after_tokens.get(uid))
        if set(after_tokens) != set(before_tokens) or len(changed_token_ids) != len(request["edits"]):
            raise WorkspaceError("LITERAL_IDENTITY_CHANGED", "Edit must replace only its selected literal tokens and preserve token identities")
        after = self._run_observations(candidate_ws, self.doc, applied["revision"], self.aliases)
        expected_after = self._expected_observations()
        if after != expected_after:
            raise WorkspaceError("MISSION_PREVIEW_ORACLE", "Candidate execution does not match the independent contract oracle")
        names = {fn["handle"]: fn["name"] for fn in self.baseline["functions"]}
        affected = sorted({edit["target"]["function_handle"] for edit in request["edits"]})
        indirect = sorted({edge["caller"] for edge in before_edges if edge["callee"] in affected})
        impact = {"directly_changed_functions": [names.get(handle, handle) for handle in affected],
            "dependent_callers": [names.get(handle, handle) for handle in indirect],
            "dependency_edges_unchanged": True, "before_observations": self.baseline_observed,
            "candidate_observations": after, "changed_literal_token_ids": changed_token_ids,
            "scope_note": "Behavioral impact is measured on the contract input corpus, not proven for all numeric inputs."}
        return operations, candidate, preview, impact

    def _preview(self, params, rid):
        revision = self.ws.get_revision(self.doc)
        try:
            operations, candidate, preview, impact = self._authorize_candidate(params)
        except WorkspaceError as exc:
            result = {"ok": False, "code": exc.code, "message": str(exc), "revision": revision,
                "revision_unchanged": True, "authoritative_workspace_changed": False}
            self._history("transaction_rejected", "mission_gateway", request_id=rid, code=exc.code,
                authoritative_state_unchanged=True, revision=revision)
            self._emit({"event_type": "rejection", "revision": revision,
                "provenance": "MissionGateway rejected semantic edit proposal", "title": "Edit proposal rejected",
                "description": str(exc), "outcome": result})
            return result
        txid = "tx_" + uuid.uuid4().hex
        self.preview_pending[txid] = {"request": copy.deepcopy(params), "candidate": candidate,
            "operations": operations, "base_revision": revision, "impact": impact}
        self._history("operation_proposed", "pi_model_tool", request_id=rid, transaction_id=txid,
            base_revision=revision, operation="edit_numeric_literals", arguments=params)
        self._history("preview_accepted", "mission_gateway", transaction_id=txid, base_revision=revision,
            resulting_revision=revision + 1, diff=preview.get("diff"), impact=impact)
        self._emit({"event_type": "preview", "revision": revision,
            "provenance": "Genuine Pi semantic edit proposal · MissionGateway preview accepted",
            "title": f"{len(params['edits'])}-location numeric edit preview",
            "description": f"Candidate changes {len(params['edits'])} authorized numeric literal(s). Committed code remains at revision {revision} until commit.",
            "focus": {"handles": [params["function_handle"]] + [edit["target"].get("statement_handle") for edit in params["edits"] if edit["target"].get("statement_handle")],
                "mapping": "verified_function_boundary"},
            "preview": {"status": "accepted", "diff": preview.get("diff"),
                "edits": params["edits"], "candidate_revision": revision + 1},
            "impact": impact, "dependencies": self.dependencies(),
            "outcome": {"authorized": True, "committed": False}})
        return {"ok": True, "transaction_id": txid, "base_revision": revision,
            "expected_result_revision": revision + 1, "accepted": True,
            "atomic_edit_count": len(operations), "impact": impact,
            "candidate_is_preview_only": True, "diff": preview.get("diff")}

    def _commit(self, params, rid):
        revision = self.ws.get_revision(self.doc)
        txid = params.get("transaction_id")
        pending = self.preview_pending.get(txid)
        if pending is None:
            return {"ok": False, "committed": False, "code": "PREVIEW_NOT_FOUND", "revision": revision,
                "authoritative_workspace_changed": False}
        if pending["base_revision"] != revision:
            return {"ok": False, "committed": False, "code": "STALE_REVISION", "revision": revision,
                "authoritative_workspace_changed": False}
        try:
            operations, candidate, _preview, impact = self._authorize_candidate(pending["request"])
            if candidate != pending["candidate"] or operations != pending["operations"]:
                raise WorkspaceError("PREVIEW_CANDIDATE_CHANGED", "Candidate changed since accepted preview")
            before_aliases = dict(self.aliases)
            applied = self.ws.apply_transaction(self.doc, revision, operations)
            committed = self._normalized(applied["revision"])
            if committed != candidate:
                raise RuntimeError("Post-commit integrity error: committed projection differs from prevalidated candidate")
            if self.aliases != before_aliases:
                raise RuntimeError("Post-commit integrity error: literal editing changed semantic IDs")
            changed_token_ids = impact["changed_literal_token_ids"]
            self.base_revision_after = applied["revision"]
            self.committed = True
        except WorkspaceError as exc:
            return {"ok": False, "committed": False, "code": exc.code, "message": str(exc),
                "revision": revision, "authoritative_workspace_changed": False}
        self.constructive_ops.append({"operation": "edit_numeric_literals", "mission_id": self.mission_id,
            "function_handle": pending["request"]["function_handle"], "edits": pending["request"]["edits"]})
        self.write_json(self.output / "constructive-operations.json", {
            "schema": "basic-workspace.constructive-metafile", "version": 1,
            "execution_profile_id": PROFILE_ID,
            "portable_handles": sorted(self.aliases), "operations": self.constructive_ops})
        code = self.ws.render_document(self.doc)
        self.write_json(self.output / "visual-source.json", {
            "schema": "basic-workspace.visual-source", "version": 1,
            "campaign": {"id": self.mission_id, "title": self.contract["objective"], "filename": "PROGRAM.bas"},
            "initial": {"revision": self.base_revision, "code": self.initial_code, "dependencies": self.dependencies()},
            "snapshots": {str(self.base_revision): self.initial_code, str(applied["revision"]): code}})
        self._history("transaction_committed", "mission_gateway", request_id=rid, transaction_id=txid,
            base_revision=revision, resulting_revision=applied["revision"], operation="edit_numeric_literals",
            changed_token_ids=changed_token_ids, affected_statement_ids=applied["affected_statement_ids"],
            alias_bindings=self.aliases, semantic_snapshot=committed, impact=impact)
        changed_handles = sorted({edit["target"]["function_handle"] for edit in pending["request"]["edits"]})
        names = {fn["handle"]: fn["name"] for fn in self.baseline["functions"]}
        self._emit({"event_type": "commit", "revision": applied["revision"], "snapshot": code,
            "provenance": "Workspace atomic semantic transaction · genuine Pi commit request",
            "title": f"{', '.join(names.get(handle, handle) for handle in changed_handles)} edit committed",
            "description": f"{len(changed_token_ids)} authorized numeric literal(s) changed in one revision-checked transaction; unaffected functions and required bindings remain unchanged.",
            "focus": {"handles": changed_handles + [edit["target"].get("statement_handle") for edit in pending["request"]["edits"] if edit["target"].get("statement_handle")],
                "mapping": "verified_function_boundary", "semantic_paths": [row["target"] for row in pending["request"]["edits"]]},
            "impact": impact, "dependencies": self.dependencies(),
            "outcome": {"committed": True, "workspace_revision": applied["revision"],
                "atomic_edit_count": len(pending["request"]["edits"]), "changed_token_ids": changed_token_ids}})
        return {"ok": True, "committed": True, "revision": applied["revision"],
            "atomic_edit_count": len(pending["request"]["edits"]), "preserved_semantic_identities": len(self.aliases),
            "changed_token_ids": changed_token_ids}

    def _run_full_replay(self):
        stream = {"schema": "basic-workspace.constructive-metafile", "version": 1,
            "execution_profile_id": PROFILE_ID, "portable_handles": sorted(self.aliases),
            "operations": copy.deepcopy(self.constructive_ops)}
        ws = Workspace()
        doc = ws.create_empty_document("memory://numeric-maintenance/full-replay.bas")["document_id"]
        aliases: dict[str, str] = {}
        for item in stream["operations"]:
            if item["operation"] == "create_numeric_function":
                call_handles = set(_calls(item["arguments"]))
                if any(handle not in aliases for handle in call_handles):
                    raise WorkspaceError("REPLAY_HANDLE_MISSING", "Function call refers to an unresolved portable handle")
                args = senior.resolve_function_handles(item["arguments"], aliases, call_handles)
                applied = ws.apply_transaction(doc, ws.get_revision(doc), [{"operation": "create_numeric_function", **args}])
                raw = projection_semantics(build_projection(ws, doc, applied["revision"]))
                aliases = senior.aliases_for_new_function(raw, aliases, args["name"], item["portable_handle"])
            elif item["operation"] == "edit_numeric_literals":
                if item.get("function_handle") not in aliases:
                    raise WorkspaceError("REPLAY_HANDLE_MISSING", "Literal edit function handle is unresolved")
                replay_request = {"expected_revision": ws.get_revision(doc),
                    "function_handle": item["function_handle"], "edits": item["edits"]}
                operations = self._resolve_replay_edit_targets(ws, doc, aliases, replay_request)
                ws.apply_transaction(doc, ws.get_revision(doc), operations)
            else:
                raise WorkspaceError("REPLAY_OPERATION_UNSUPPORTED", f"Unsupported constructive operation {item['operation']}")
        revision = ws.get_revision(doc)
        normalized = senior.normalized_state(projection_semantics(build_projection(ws, doc, revision)), aliases)
        observations = self._run_observations(ws, doc, revision, aliases)
        identity_mapping = [{"portable_handle": handle, "committed_workspace_id": self.aliases[handle],
            "replay_workspace_id": aliases[handle], "remapped": self.aliases[handle] != aliases[handle]}
            for handle in sorted(self.aliases)]
        return stream, ws, doc, aliases, normalized, observations, identity_mapping

    def _resolve_replay_edit_targets(self, ws, doc, aliases, request):
        state = senior.normalized_state(projection_semantics(build_projection(ws, doc, ws.get_revision(doc))), aliases)
        for edit in request["edits"]:
            self._target_expression(state, edit["target"])
        return self._workspace_operations_for_edits(request["edits"], aliases)

    def validate_current(self, expected_revision, actor="host"):
        revision = self.ws.get_revision(self.doc)
        if expected_revision != revision:
            return {"reliable": False, "code": "STALE_VALIDATION_REVISION", "revision": revision,
                "requested_revision": expected_revision, "executed_revision": None, "mission_complete": False}
        if not self.committed:
            return {"reliable": True, "revision": revision, "executed_revision": revision,
                "mission_complete": False, "diagnostics": ["No semantic edit has committed"]}
        observed = self._run_observations(self.ws, self.doc, revision, self.aliases)
        expected = self._expected_observations()
        normalized = self._normalized(revision)
        expected_state = copy.deepcopy(self.baseline)
        committed_edit = next((row for row in reversed(self.constructive_ops)
            if row.get("operation") == "edit_numeric_literals" and row.get("mission_id") == self.mission_id), None)
        if committed_edit is None:
            raise WorkspaceError("CONSTRUCTIVE_EDIT_MISSING", "Committed semantic edit is absent from the constructive stream")
        target_map = {json.dumps(row["target"], sort_keys=True): row for row in self.edit_targets}
        for edit in committed_edit["edits"]:
            row = target_map.get(json.dumps(edit["target"], sort_keys=True))
            if row is None:
                raise WorkspaceError("CONSTRUCTIVE_TARGET_MISSING", "Committed target is missing from the mission contract")
            self._set_target_value(expected_state, row["target"], row["expected_value"], edit["replacement_value"])
        structural_ok = normalized == expected_state
        unchanged_ok = all(senior.find_function(normalized, handle) == senior.find_function(self.baseline, handle)
            for handle in self.contract["unchanged_function_handles"])
        expected_edges = sorted([{"caller": row["caller_handle"], "callee": row["callee_handle"]}
            for row in self.contract["required_dependency_edges"]], key=lambda row: (row["caller"], row["callee"]))
        dependency_ok = self._dependency_edges(self.baseline) == self._dependency_edges(normalized) == expected_edges
        engines_agree = observed["interp"] == observed["jit"]
        values_match = observed == expected
        identities_preserved = self.aliases == self.baseline_aliases
        complete = bool(values_match and engines_agree and dependency_ok and unchanged_ok and structural_ok and identities_preserved)
        result = {"schema": "basic-workspace.numeric-literal-maintenance-validation", "version": 1,
            "actor": actor, "mission_id": self.mission_id, "revision": revision,
            "requested_revision": expected_revision, "executed_revision": revision,
            "observed_results": observed, "expected_results": expected,
            "expectation_source": "independent host-owned contract oracle",
            "engines_agree": engines_agree, "values_match": values_match,
            "structural_change_scope_valid": structural_ok,
            "unchanged_functions_preserved": unchanged_ok,
            "dependency_edges_unchanged": dependency_ok,
            "preserved_semantic_identity_count": len(self.aliases),
            "mission_complete": complete,
            "diagnostics": [] if complete else ["Behavior, binding, identity, or structural invariant failed"]}
        changed_handles = {edit["target"]["function_handle"] for edit in committed_edit["edits"]}
        for function in self.baseline["functions"]:
            result[f"{function['name']}_structurally_unchanged"] = function["handle"] not in changed_handles
        if complete:
            stream, replay_ws, replay_doc, replay_aliases, replay_norm, replay_obs, identity_map = self._run_full_replay()
            structural = replay_norm == normalized
            binding = self._dependency_edges(replay_norm) == self._dependency_edges(normalized)
            behavior = replay_obs == observed
            replay_passed = structural and binding and behavior and replay_obs["interp"] == replay_obs["jit"]
            result["replay"] = {"structural_equivalence": structural, "binding_equivalence": binding,
                "behavioral_equivalence": behavior, "engine_agreement": replay_obs["interp"] == replay_obs["jit"],
                "identity_remappings": sum(row["remapped"] for row in identity_map),
                "identity_mapping": identity_map, "passed": replay_passed}
            result["mission_complete"] = bool(complete and replay_passed)
            self.write_json(self.output / "constructive-operations.json", stream)
            self.write_json(self.output / "equivalence.json", result)
            self.write_json(self.output / "full-replay-identity-mapping.json", {
                "schema": "basic-workspace.semantic-maintenance-replay-identities", "version": 1,
                "identity_count": len(identity_map), "all_remapped": all(row["remapped"] for row in identity_map),
                "mappings": identity_map})
        self.write_json(self.output / "validation.json", result)
        self._history("program_validated", actor, revision=revision, executed_revision=revision,
            passed=result["mission_complete"], engines_agree=engines_agree, diagnostics=result["diagnostics"])
        self._emit({"event_type": "validation", "revision": revision,
            "provenance": f"Independent {actor} MIR validation", "title": f"{actor.title()} validation {'passed' if result['mission_complete'] else 'failed'}",
            "description": "MIR interpreter and JIT were checked against the host-owned mission oracle, unchanged-function rules, and replay.",
            "dependencies": self.dependencies(), "observations": observed,
            "outcome": {"passed": result["mission_complete"], "executed_revision": revision}})
        return result

    def record_pi_event(self, params):
        row = dict(params)
        key = str(row.get("toolCallId") or row.get("request_id") or uuid.uuid4()) + ":" + str(row.get("type", ""))
        duplicate = key in self.pi_seen
        if not duplicate:
            self.pi_seen.add(key)
            row["observed_monotonic_ns"] = time.monotonic_ns()
            self._log(self.pi_path, row)
        if row.get("type") == "tool_inventory":
            self.write_json(self.output / "tool-inventory.json", {"tools": row.get("tools"), "source": row.get("source")})
            self.write_json(self.output / "tool-schemas.json", row.get("schemas", []))
        return {"ok": True, "deduplicated": duplicate}

    def record_timing(self, request, elapsed_ms):
        method = request.get("method")
        self._log(self.timing_path, {"request_id": request.get("request_id"),
            "tool_call_id": (request.get("transport") or {}).get("tool_call_id"), "method": method,
            "elapsed_ms": round(elapsed_ms, 3), "agent_tool": method in {
                "discover_functions", "inspect_program", "preview_semantic_edit", "commit_preview", "validate_mission"}})

    def handle(self, method, params, request_id):
        if method == "record_pi_event":
            return self.record_pi_event(params)
        if method == "get_status":
            if params:
                raise WorkspaceError("UNKNOWN_SEMANTIC_FIELD", "get_status accepts no semantic arguments")
            return {"revision": self.ws.get_revision(self.doc), "committed": self.committed,
                "function_handles": sorted(h for h in self.aliases if h.endswith(".function")),
                "discovered": sorted(self.discovered)}
        if method == "discover_functions":
            if params:
                raise WorkspaceError("UNKNOWN_SEMANTIC_FIELD", "discover_functions accepts no semantic arguments")
            functions = []
            for item in self.baseline["functions"]:
                handle = item["handle"]
                if handle in self.aliases:
                    self.discovered.add(handle)
                    functions.append({"handle": handle, "name": item["name"],
                        "parameters": item["parameters"], "return_type": item["return_type"]})
            self._history("symbol_discovered", "pi_model_tool", request_id=request_id, revision=self.ws.get_revision(self.doc), functions=functions)
            names = [item["name"] for item in functions]
            self._emit({"event_type": "selection", "revision": self.ws.get_revision(self.doc),
                "provenance": "Genuine Pi semantic discovery", "title": "Functions discovered",
                "description": f"Discovered callable signatures for {', '.join(names)} from Workspace identities.",
                "focus": {"handles": [item["handle"] for item in functions], "mapping": "verified_function_boundary"},
                "dependencies": self.dependencies()})
            return {"revision": self.ws.get_revision(self.doc), "functions": functions}
        if method == "inspect_program":
            if params:
                raise WorkspaceError("UNKNOWN_SEMANTIC_FIELD", "inspect_program accepts no semantic arguments")
            self._history("program_inspected", "pi_model_tool", request_id=request_id, revision=self.ws.get_revision(self.doc))
            return self._inspect()
        if method == "preview_semantic_edit":
            return self._preview(params, request_id)
        if method == "commit_preview":
            if set(params) != {"transaction_id"}:
                raise WorkspaceError("UNKNOWN_SEMANTIC_FIELD", "commit_preview requires only transaction_id")
            return self._commit(params, request_id)
        if method == "validate_mission":
            if set(params) != {"expected_revision"}:
                raise WorkspaceError("UNKNOWN_SEMANTIC_FIELD", "validate_mission requires only expected_revision")
            return self.validate_current(params.get("expected_revision"), actor="pi_tool")
        if method == "host_validate":
            if set(params) != {"expected_revision"}:
                raise WorkspaceError("UNKNOWN_SEMANTIC_FIELD", "host_validate requires only expected_revision")
            return self.validate_current(params.get("expected_revision"), actor="host")
        if method == "record_agent_status":
            self._emit({"event_type": "mission_status", "revision": self.ws.get_revision(self.doc),
                "provenance": "Host observation of Pi lifecycle", "title": str(params.get("state", "status")),
                "description": str((params.get("info") or {}).get("description", params.get("state", "status"))),
                "dependencies": self.dependencies()})
            return {"ok": True, "revision": self.ws.get_revision(self.doc)}
        if method == "finalize_session":
            lifecycle = params.get("pi_lifecycle") or {}
            validation = params.get("validation")
            states = completion_states(committed=self.committed, validation=validation,
                timed_out=bool(params.get("timed_out")), exit_code=params.get("pi_exit_code"),
                agent_end_seen=bool(lifecycle.get("agent_end_seen")),
                agent_settled_seen=bool(lifecycle.get("agent_settled_seen")),
                pending_tool_count=len(lifecycle.get("pending_tools", {})),
                authorization_status="authorized" if self.committed else "not_committed")
            self.write_json(self.output / "completion-states.json", {"completion_states": states, "lifecycle": lifecycle})
            self._history("session_completed", "host_lifecycle_classifier", completion_states=states)
            return {"completion_states": states}
        raise WorkspaceError("UNKNOWN_TOOL", f"Unsupported semantic maintenance tool {method}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=BASE)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--baseline-stream", type=Path)
    parser.add_argument("--baseline-history", type=Path)
    parser.add_argument("--baseline-validation", type=Path)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    service = Cycle20Gateway(args.output, args.baseline, contract_path=args.contract,
        baseline_stream_path=args.baseline_stream, baseline_history_path=args.baseline_history,
        baseline_validation_path=args.baseline_validation)
    with Server(("127.0.0.1", args.port), service) as server:
        print(json.dumps({"ready": True, "host": "127.0.0.1", "port": server.server_address[1],
            "revision": service.ws.get_revision(service.doc), "baseline_verified": True,
            "mission_id": service.mission_id, "contract_verified": True,
            "checkpoint_fingerprint": getattr(service, "revision2_fingerprint", None)}), flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
