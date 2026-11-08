#!/usr/bin/env python3
"""Cycle 20 semantic edit gateway; Python Workspace and policy remain authoritative."""
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
    def __init__(self, output: Path, baseline_dir: Path = BASE):
        self.output = output.resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.baseline_dir = baseline_dir.resolve()
        self.lock = threading.RLock()
        self.ws = Workspace()
        self.doc = self.ws.create_empty_document("memory://cycle20/reconstructed.bas")["document_id"]
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
        self.executor = MirExecutionService(timeout=20)
        self.constructive_ops = []
        self._reconstruct_baseline()

    def record_gateway_timing(self, request: dict[str, Any], elapsed_ms: float):
        """Implement the shared Pi bridge instrumentation hook."""
        self._log(self.timing_path, {"request_id": request.get("request_id"),
            "method": request.get("method"), "elapsed_ms": round(elapsed_ms, 3),
            "observed_monotonic_ns": time.monotonic_ns()})

    def flush_trace(self):
        """Trace writes are append-and-close; present for bridge error handling."""
        return None

    @staticmethod
    def write_json(path: Path, value: Any):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _log(self, path: Path, row: dict[str, Any]):
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    def _emit(self, event: dict[str, Any]):
        self.seq += 1
        event.setdefault("presentation_sequence", self.seq)
        event.setdefault("event_id", f"cycle20-{self.seq}-{uuid.uuid4().hex[:8]}")
        event.setdefault("session_id", "cycle20-real-agent-01")
        event.setdefault("mission_id", MISSION_ID)
        self._log(self.visual_path, event)

    def _history(self, event: str, actor: str, **fields):
        self._log(self.trace_path, {"sequence": self.seq + 1, "event": event, "actor": actor,
            "mission_id": MISSION_ID, "observed_monotonic_ns": time.monotonic_ns(), **fields})

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
        self._history("session_started", "host", revision=3, mission_id=MISSION_ID, model_session="fresh_pi_session")
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
        return {"schema": "basic-workspace.mission-contract", "version": 1,
            "mission_id": MISSION_ID,
            "objective": "Change CLAMP_SCORE's upper cap from 100 to 50 so it returns min(50,max(0,X)); preserve IS_PASSING unchanged.",
            "base_document_revision": 3, "execution_profile_id": PROFILE_ID,
            "allowed_operation": "atomic_edit_two_numeric_literals_in_CLAMP_SCORE",
            "required_targets": 2, "required_expected_value": 100, "required_replacement_value": 50,
            "preserved_invariants": ["IS_PASSING normalized structure and binding unchanged",
                "CLAMP_SCORE structure unchanged except the two authorized numeric leaves",
                "CLAMP_SCORE-to-IS_PASSING call dependency unchanged", "one atomic revision increment"],
            "required_validation": {"engines": ["interp", "jit"], "inputs": list(INPUTS)},
            "trust_boundary": "Restrictions are enforced at this loopback MissionGateway only; unrestricted host access is outside this experiment."}

    def _run_observations(self, ws, doc, revision, aliases):
        results = {"interp": {}, "jit": {}}
        for engine in results:
            for value in INPUTS:
                results[engine][str(value)] = {
                    "clamp_score": self.executor.execute_function(ws, doc, revision, aliases["clamp_score.function"], [value], engine)["result"],
                    "is_passing": self.executor.execute_function(ws, doc, revision, aliases["is_passing.function"], [value], engine)["result"]}
        return results

    def _dependency_edges(self, state):
        return sorted(_call_edges(state), key=lambda edge: (edge["caller"], edge["callee"]))

    def dependencies(self):
        names = {fn["handle"]: fn["name"] for fn in self.baseline["functions"]}
        return [{"caller": names.get(edge["caller"], edge["caller"]),
                 "callee": names.get(edge["callee"], edge["callee"])}
                for edge in self._dependency_edges(self.baseline)]

    @staticmethod
    def _target_descriptor(function_handle, *, control_path=None, statement_handle=None,
                           expression_path, semantic_path):
        target = {"function_handle": function_handle, "expression_path": expression_path}
        if control_path is not None: target["control_path"] = control_path
        if statement_handle is not None: target["statement_handle"] = statement_handle
        return {"target": target, "semantic_path": semantic_path, "expected_value": 100.0}

    def _discover_authorized_targets(self):
        function = senior.find_function(self.baseline, "clamp_score.function")
        result = []
        # The exact Cycle 19B shape has one IF comparison with X > 100 and one
        # result assignment of 100 in its THEN block. Paths are derived from
        # the normalized typed function and guarded by complete baseline equality.
        statements = function["statements"]
        for index, item in enumerate(statements):
            if item.get("kind") != "if":
                continue
            condition = item.get("condition", {})
            children = condition.get("children", [])
            if (condition.get("kind") == "compare" and condition.get("value") == ">"
                    and len(children) == 2 and children[1].get("kind") == "number"
                    and float(children[1].get("value")) == 100.0):
                result.append(self._target_descriptor("clamp_score.function",
                    control_path=[{"block": "body", "index": index}], expression_path=[1],
                    semantic_path=["functions", 0, "statements", index, "condition", "children", 1, "value"]))
                for child_index, child in enumerate(item.get("then", [])):
                    expression = child.get("expression", {})
                    if (child.get("kind") == "assignment" and child.get("target_handle") == "clamp_score.function"
                            and expression.get("kind") == "number" and float(expression.get("value")) == 100.0):
                        result.append(self._target_descriptor("clamp_score.function",
                            statement_handle=child.get("statement_handle"), expression_path=[],
                            semantic_path=["functions", 0, "statements", index, "then", child_index, "expression", "value"]))
        if len(result) != 2 or any(row["target"].get("statement_handle") is None for row in result if "control_path" not in row["target"]):
            raise WorkspaceError("BASELINE_EDIT_TARGETS", "Baseline does not have exactly the two verified cap-100 expression locations")
        return result

    def _current_projection(self):
        return self._normalized(self.ws.get_revision(self.doc))

    def _inspect(self):
        return {"revision": self.ws.get_revision(self.doc), "structure": self._current_projection(),
            "editable_upper_bound_occurrences": [{"target": row["target"], "current_value": row["expected_value"],
                "expression_kind": "number"} for row in self.edit_targets],
            "identity_note": "Function, parameter, and assignment statement handles are stable Workspace semantic identities. IF condition selection is function identity plus verified ordered control-flow path; the IF node has no independent statement ID."}

    def _make_workspace_operations(self, request):
        if set(request) != {"expected_revision", "function_handle", "edits"}:
            raise WorkspaceError("INVALID_EDIT_REQUEST", "Edit request requires expected_revision, function_handle, and edits")
        revision = request["expected_revision"]
        if revision != self.ws.get_revision(self.doc):
            raise WorkspaceError("STALE_REVISION", "Edit base revision is stale")
        if self.committed:
            raise WorkspaceError("MISSION_EDIT_LIMIT", "Mission permits one atomic semantic edit")
        handle = request["function_handle"]
        if handle not in self.discovered:
            raise WorkspaceError("FUNCTION_NOT_DISCOVERED", "Discover CLAMP_SCORE before proposing the edit")
        if handle != "clamp_score.function":
            raise WorkspaceError("MISSION_EDIT_SCOPE", "Mission permits edits only within CLAMP_SCORE")
        edits = request["edits"]
        if not isinstance(edits, list) or len(edits) != 2:
            raise WorkspaceError("MISSION_EDIT_COUNT", "Both cap expressions must be edited in the same preview")
        authorized = {json.dumps(row["target"], sort_keys=True) for row in self.edit_targets}
        actual = [edit.get("target") for edit in edits if isinstance(edit, dict)]
        if len(actual) != len(edits):
            raise WorkspaceError("INVALID_EDIT_REQUEST", "Each edit requires a typed target")
        actual_keys = [json.dumps(target, sort_keys=True) for target in actual]
        if len(set(actual_keys)) != len(actual_keys):
            raise WorkspaceError("DUPLICATE_EDIT_TARGET", "The same semantic literal target was selected more than once")
        if set(actual_keys) != authorized:
            raise WorkspaceError("MISSION_EDIT_TARGETS", "Candidate must edit exactly the two discovered CLAMP_SCORE upper-bound literals")
        if any(edit.get("expected_value") != 100 or edit.get("replacement_value") != 50
               or isinstance(edit.get("expected_value"), bool) or isinstance(edit.get("replacement_value"), bool)
               for edit in edits):
            raise WorkspaceError("MISSION_LITERAL_VALUES", "Both authorized cap literals must change from 100 to 50")
        if not all(math.isfinite(float(edit["expected_value"])) and math.isfinite(float(edit["replacement_value"])) for edit in edits):
            raise WorkspaceError("INVALID_LITERAL_EDIT", "Literal values must be finite")
        operations = []
        target_map = {json.dumps(row["target"], sort_keys=True): row for row in self.edit_targets}
        for edit in edits:
            row = target_map[json.dumps(edit["target"], sort_keys=True)]
            target = row["target"]
            op = {"operation": "edit_numeric_literal_at_path", "function_id": self.aliases["clamp_score.function"],
                "expression_path": target["expression_path"], "expected_value": edit["expected_value"],
                "replacement_value": edit["replacement_value"]}
            if "control_path" in target:
                op.update(target_kind="if_condition_rhs", control_path=target["control_path"])
            else:
                statement_id = self.aliases.get(target["statement_handle"])
                if statement_id is None:
                    raise WorkspaceError("UNKNOWN_STATEMENT_HANDLE", "Assignment statement handle is not resolved")
                op.update(target_kind="assignment_rhs", statement_id=statement_id)
            operations.append(op)
        return operations

    def _authorize_candidate(self, request):
        if self.ws.get_revision(self.doc) != request["expected_revision"]:
            raise WorkspaceError("STALE_REVISION", "Workspace changed since this proposal was based")
        operations = self._make_workspace_operations(request)
        candidate_info = self.ws.preview_transaction_semantics(self.doc, request["expected_revision"], operations)
        candidate = senior.normalized_state(candidate_info["candidate_semantics"], self.aliases)
        expected = copy.deepcopy(self.baseline)
        for row in self.edit_targets:
            _set_semantic_path(expected, row["semantic_path"], 50.0, 100.0)
        if candidate != expected:
            raise WorkspaceError("MISSION_CANDIDATE_MISMATCH", "Typed candidate contains changes outside the two authorized cap literals")
        before_edges = self._dependency_edges(self.baseline)
        after_edges = self._dependency_edges(candidate)
        if before_edges != after_edges or before_edges != [{"caller": "is_passing.function", "callee": "clamp_score.function"}]:
            raise WorkspaceError("MISSION_DEPENDENCY_CHANGED", "Existing CLAMP_SCORE → IS_PASSING function binding must remain unchanged")
        preview = self.ws.preview_transaction(self.doc, request["expected_revision"], operations, include_diff=True)
        candidate_ws = copy.deepcopy(self.ws)
        before_tokens = {token.uid: token.text for token in self.ws.documents[self.doc].tokens}
        applied = candidate_ws.apply_transaction(self.doc, request["expected_revision"], operations)
        after_tokens = {token.uid: token.text for token in candidate_ws.documents[self.doc].tokens}
        changed_token_ids = sorted(uid for uid in before_tokens if before_tokens[uid] != after_tokens.get(uid))
        if set(after_tokens) != set(before_tokens) or len(changed_token_ids) != 2:
            raise WorkspaceError("LITERAL_IDENTITY_CHANGED", "Candidate must replace exactly two literal token values and preserve token identities")
        after = self._run_observations(candidate_ws, self.doc, applied["revision"], self.aliases)
        expected_after = {engine: {str(value): {"clamp_score": float(min(50, max(0, value)),), "is_passing": 0.0}
            for value in INPUTS} for engine in ("interp", "jit")}
        if after != expected_after:
            raise WorkspaceError("MISSION_PREVIEW_ORACLE", "Candidate execution does not match the requested cap behavior")
        names = {fn["handle"]: fn["name"] for fn in self.baseline["functions"]}
        indirect = sorted({edge["caller"] for edge in before_edges if edge["callee"] == "clamp_score.function"})
        impact = {"directly_changed_functions": ["CLAMP_SCORE"],
            "dependent_callers": [names.get(handle, handle) for handle in indirect],
            "dependency_edges_unchanged": True, "before_observations": self.baseline_observed,
            "candidate_observations": after, "changed_literal_token_ids": changed_token_ids,
            "scope_note": "Observed effect is measured on the listed finite test corpus; this is not a complete static behavior proof."}
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
            "title": "Two-location cap edit preview", "description": "Candidate changes both cap literals together. Committed code remains at revision 3 until commit.",
            "focus": {"handles": ["clamp_score.function", "clamp_score.statement.2"],
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
        self.constructive_ops.append({"operation": "edit_numeric_literals", "mission_id": MISSION_ID,
            "function_handle": "clamp_score.function", "edits": pending["request"]["edits"]})
        self.write_json(self.output / "constructive-operations.json", {
            "schema": "basic-workspace.constructive-metafile", "version": 1,
            "execution_profile_id": PROFILE_ID,
            "portable_handles": sorted(self.aliases), "operations": self.constructive_ops})
        code = self.ws.render_document(self.doc)
        self.write_json(self.output / "visual-source.json", {
            "schema": "basic-workspace.visual-source", "version": 1,
            "campaign": {"id": "cycle20-semantic-evolution", "title": "Cycle 20 · semantic evolution of CLAMP_SCORE", "filename": "SCORES.bas"},
            "initial": {"revision": 3, "code": self.initial_code, "dependencies": self.dependencies()},
            "snapshots": {"3": self.initial_code, "4": code}})
        self._history("transaction_committed", "mission_gateway", request_id=rid, transaction_id=txid,
            base_revision=revision, resulting_revision=applied["revision"], operation="edit_numeric_literals",
            changed_token_ids=changed_token_ids, affected_statement_ids=applied["affected_statement_ids"],
            alias_bindings=self.aliases, semantic_snapshot=committed, impact=impact)
        self._emit({"event_type": "commit", "revision": applied["revision"], "snapshot": code,
            "provenance": "Workspace atomic semantic transaction · genuine Pi commit request",
            "title": "CLAMP_SCORE cap edit committed", "description": "Both upper-bound literals changed from 100 to 50 in one revision-checked transaction; IS_PASSING code and call binding are unchanged.",
            "focus": {"handles": ["clamp_score.function", "clamp_score.statement.2"],
                "mapping": "verified_function_boundary", "semantic_paths": [row["target"] for row in pending["request"]["edits"]]},
            "impact": impact, "dependencies": self.dependencies(),
            "outcome": {"committed": True, "workspace_revision": applied["revision"],
                "atomic_edit_count": 2, "changed_token_ids": changed_token_ids}})
        return {"ok": True, "committed": True, "revision": applied["revision"],
            "atomic_edit_count": 2, "preserved_semantic_identities": len(self.aliases),
            "changed_token_ids": changed_token_ids}

    def _run_full_replay(self):
        stream = {"schema": "basic-workspace.constructive-metafile", "version": 1,
            "execution_profile_id": PROFILE_ID, "portable_handles": sorted(self.aliases),
            "operations": copy.deepcopy(self.constructive_ops)}
        ws = Workspace()
        doc = ws.create_empty_document("memory://cycle20/full-replay.bas")["document_id"]
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
                if item.get("function_handle") != "clamp_score.function" or item["function_handle"] not in aliases:
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
        # Recompute semantic paths on replay rather than carrying over transient IDs.
        state = senior.normalized_state(projection_semantics(build_projection(ws, doc, ws.get_revision(doc))), aliases)
        function = senior.find_function(state, "clamp_score.function")
        targets = self._derive_targets(function)
        target_by_key = {json.dumps(row["target"], sort_keys=True): row for row in targets}
        operations = []
        for edit in request["edits"]:
            row = target_by_key.get(json.dumps(edit["target"], sort_keys=True))
            if row is None:
                raise WorkspaceError("REPLAY_TARGET_MISSING", "Portable semantic edit target does not resolve in replay")
            target = row["target"]
            op = {"operation": "edit_numeric_literal_at_path", "function_id": aliases["clamp_score.function"],
                "expression_path": target["expression_path"], "expected_value": edit["expected_value"],
                "replacement_value": edit["replacement_value"]}
            if "control_path" in target:
                op.update(target_kind="if_condition_rhs", control_path=target["control_path"])
            else:
                op.update(target_kind="assignment_rhs", statement_id=aliases[target["statement_handle"]])
            operations.append(op)
        return operations

    @staticmethod
    def _derive_targets(function):
        rows = []
        for index, item in enumerate(function["statements"]):
            if item.get("kind") == "if":
                condition = item.get("condition", {})
                children = condition.get("children", [])
                if (condition.get("kind") == "compare" and condition.get("value") == ">"
                        and len(children) == 2 and children[1].get("kind") == "number"
                        and float(children[1].get("value")) == 100.0):
                    rows.append({"target": {"function_handle": "clamp_score.function",
                        "control_path": [{"block": "body", "index": index}], "expression_path": [1]},
                        "semantic_path": ["functions", 0, "statements", index, "condition", "children", 1, "value"],
                        "expected_value": 100.0})
                    for child_index, child in enumerate(item.get("then", [])):
                        expr = child.get("expression", {})
                        if (child.get("kind") == "assignment" and child.get("target_handle") == "clamp_score.function"
                                and expr.get("kind") == "number" and float(expr.get("value")) == 100.0):
                            rows.append({"target": {"function_handle": "clamp_score.function",
                                "statement_handle": child.get("statement_handle"), "expression_path": []},
                                "semantic_path": ["functions", 0, "statements", index, "then", child_index, "expression", "value"],
                                "expected_value": 100.0})
        return rows

    def validate_current(self, expected_revision, actor="host"):
        revision = self.ws.get_revision(self.doc)
        if expected_revision != revision:
            return {"reliable": False, "code": "STALE_VALIDATION_REVISION", "revision": revision,
                "requested_revision": expected_revision, "executed_revision": None, "mission_complete": False}
        if not self.committed:
            return {"reliable": True, "revision": revision, "executed_revision": revision,
                "mission_complete": False, "diagnostics": ["No semantic edit has committed"]}
        observed = self._run_observations(self.ws, self.doc, revision, self.aliases)
        expected = {engine: {str(value): {"clamp_score": float(min(50, max(0, value)),), "is_passing": 0.0}
            for value in INPUTS} for engine in ("interp", "jit")}
        normalized = self._normalized(revision)
        clamp = senior.find_function(normalized, "clamp_score.function")
        passing = senior.find_function(normalized, "is_passing.function")
        base_passing = senior.find_function(self.baseline, "is_passing.function")
        dep_before = self._dependency_edges(self.baseline)
        dep_after = self._dependency_edges(normalized)
        dependency_ok = dep_before == dep_after == [{"caller": "is_passing.function", "callee": "clamp_score.function"}]
        passing_unchanged = passing == base_passing
        expected_state = copy.deepcopy(self.baseline)
        for row in self.edit_targets:
            _set_semantic_path(expected_state, row["semantic_path"], 50.0, 100.0)
        structural_ok = normalized == expected_state
        engines_agree = observed["interp"] == observed["jit"]
        values_match = observed == expected
        complete = bool(values_match and engines_agree and dependency_ok and passing_unchanged and structural_ok)
        baseline_function_id = self.aliases["clamp_score.function"]
        current_statement_ids = {key: value for key, value in self.aliases.items() if ".statement." in key}
        result = {"schema": "basic-workspace.cycle20-validation", "version": 1, "actor": actor,
            "mission_id": MISSION_ID, "revision": revision, "requested_revision": expected_revision,
            "executed_revision": revision, "observed_results": observed, "expected_results": expected,
            "expectation_source": "independent host-owned oracle", "engines_agree": engines_agree,
            "values_match": values_match, "CLAMP_SCORE_matches_cap50_semantics": values_match,
            "IS_PASSING_all_zero_on_test_domain": all(row["is_passing"] == 0 for engine in observed.values() for row in engine.values()),
            "IS_PASSING_structurally_unchanged": passing_unchanged, "dependency_edges_unchanged": dependency_ok,
            "structural_change_scope_valid": structural_ok, "preserved_semantic_identity_count": len(current_statement_ids) + 4,
            "function_identity_preserved": baseline_function_id == self.aliases["clamp_score.function"],
            "mission_complete": complete, "diagnostics": [] if complete else ["Behavior, binding, or structural invariant failed"]}
        if complete:
            stream, replay_ws, replay_doc, replay_aliases, replay_norm, replay_obs, identity_map = self._run_full_replay()
            replay_passed = replay_norm == normalized and replay_obs == observed and replay_obs["interp"] == replay_obs["jit"]
            result["replay"] = {"structural_equivalence": replay_norm == normalized,
                "binding_equivalence": self._dependency_edges(replay_norm) == dep_after,
                "behavioral_equivalence": replay_obs == observed, "engine_agreement": replay_obs["interp"] == replay_obs["jit"],
                "identity_remappings": sum(row["remapped"] for row in identity_map),
                "identity_mapping": identity_map, "passed": replay_passed}
            result["mission_complete"] = bool(complete and replay_passed)
            self.write_json(self.output / "constructive-operations.json", stream)
            self.write_json(self.output / "equivalence.json", result)
            self.write_json(self.output / "full-replay-identity-mapping.json", {
                "schema": "basic-workspace.cycle20-replay-identities", "version": 1,
                "identity_count": len(identity_map), "all_remapped": all(row["remapped"] for row in identity_map),
                "mappings": identity_map})
        self.write_json(self.output / "validation.json", result)
        self._history("program_validated", actor, revision=revision, executed_revision=revision,
            passed=result["mission_complete"], engines_agree=engines_agree, diagnostics=result["diagnostics"])
        self._emit({"event_type": "validation", "revision": revision,
            "provenance": f"Independent {actor} MIR validation", "title": f"{actor.title()} validation {'passed' if complete else 'failed'}",
            "description": "Both MIR engines were checked against the independent cap-50 oracle and dependent caller invariants.",
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
        self._log(self.timing_path, {"request_id": request.get("request_id"),
            "tool_call_id": (request.get("params") or {}).get("toolCallId"), "method": request.get("method"),
            "elapsed_ms": round(elapsed_ms, 3), "agent_tool": request.get("method") in {
                "discover_functions", "inspect_program", "preview_semantic_edit", "commit_preview", "validate_mission"}})

    def handle(self, method, params, request_id):
        if method == "record_pi_event":
            return self.record_pi_event(params)
        if method == "get_status":
            return {"revision": self.ws.get_revision(self.doc), "committed": self.committed,
                "function_handles": sorted(h for h in self.aliases if h.endswith(".function")),
                "discovered": sorted(self.discovered)}
        if method == "discover_functions":
            functions = []
            for item in self.baseline["functions"]:
                handle = item["handle"]
                if handle in self.aliases:
                    self.discovered.add(handle)
                    functions.append({"handle": handle, "name": item["name"],
                        "parameters": item["parameters"], "return_type": item["return_type"]})
            self._history("symbol_discovered", "pi_model_tool", request_id=request_id, revision=self.ws.get_revision(self.doc), functions=functions)
            self._emit({"event_type": "selection", "revision": self.ws.get_revision(self.doc),
                "provenance": "Genuine Pi semantic discovery", "title": "Functions discovered",
                "description": "CLAMP_SCORE and IS_PASSING signatures and the existing call dependency were discovered from Workspace identities.",
                "focus": {"handles": ["clamp_score.function", "is_passing.function"], "mapping": "verified_function_boundary"},
                "dependencies": self.dependencies()})
            return {"revision": self.ws.get_revision(self.doc), "functions": functions}
        if method == "inspect_program":
            self._history("program_inspected", "pi_model_tool", request_id=request_id, revision=self.ws.get_revision(self.doc))
            return self._inspect()
        if method == "preview_semantic_edit":
            # Pi adds this transport correlation field to every tool payload. It
            # is metadata, not part of the semantic edit contract.
            semantic_request = dict(params)
            semantic_request.pop("toolCallId", None)
            return self._preview(semantic_request, request_id)
        if method == "commit_preview":
            return self._commit(params, request_id)
        if method == "validate_mission":
            return self.validate_current(params.get("expected_revision"), actor="pi_tool")
        if method == "host_validate":
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
        raise WorkspaceError("UNKNOWN_TOOL", f"Unsupported Cycle 20 tool {method}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=BASE)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    service = Cycle20Gateway(args.output, args.baseline)
    with Server(("127.0.0.1", args.port), service) as server:
        print(json.dumps({"ready": True, "host": "127.0.0.1", "port": server.server_address[1],
            "revision": service.ws.get_revision(service.doc), "baseline_verified": True,
            "checkpoint_fingerprint": service.revision2_fingerprint}), flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
