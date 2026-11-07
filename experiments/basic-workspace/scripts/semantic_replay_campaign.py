#!/usr/bin/env python3
"""Run a small semantic-contract, mission-gateway and portable replay campaign."""
from __future__ import annotations

import copy
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from basic_workspace.mir_execution import MirExecutionService
from basic_workspace.model import Workspace, WorkspaceError

OUT = ROOT / "results" / "semantic-replay"
PROFILE_REF = "basic-workspace.numeric-control.v1"
MISSION_ID = "mission.double-times-three.v1"
METAFILE_VERSION = "basic-workspace.constructive-metafile"


def load_json(name: str) -> dict[str, Any]:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def semantic_snapshot(workspace: Workspace, document_id: str,
                      aliases: dict[str, str]) -> dict[str, Any]:
    reverse = {opaque: handle for handle, opaque in aliases.items()}
    symbols = workspace.list_symbols(document_id)
    function_scopes = {row["symbol_id"]: row["scope_id"]
                       for row in workspace.get_document_structure(document_id)["functions"]}
    functions = []
    for function in (row for row in symbols if row["kind"] == "function"):
        statements = workspace.list_function_statements(document_id, function["symbol_id"])["items"]
        parameters = [row for row in symbols if row["kind"] == "parameter" and
                      row["scope_id"] == function_scopes.get(function["symbol_id"])]
        functions.append({
            "handle": reverse.get(function["symbol_id"], function["name"].casefold()),
            "name": function["name"],
            "parameters": [{"handle": reverse.get(p["symbol_id"], p["name"].casefold()),
                            "name": p["name"]} for p in parameters],
            "statements": [{"statement_handle": reverse.get(row["statement_id"]),
                            "kind": row["kind"],
                            "target_handle": reverse.get(row.get("target_symbol_id")),
                            "references": [reverse.get(x, "unmapped") for x in row.get("referenced_symbol_ids", [])],
                            "expression": row.get("expression_summary")}
                           for row in statements],
        })
    arrays = [{"handle": reverse.get(row["symbol_id"], row["name"].casefold()),
               "name": row["name"], "element_type": row.get("element_type"),
               "scope_id": "module" if row["scope_id"] == "module" else "function"}
              for row in symbols if row["kind"] == "array"]
    return {"functions": functions, "arrays": arrays,
            "diagnostics": workspace.get_diagnostics(document_id)}


def create_op() -> dict[str, Any]:
    return {
        "kind": "create_numeric_function",
        "arguments": {
            "name": "DOUBLE", "parameters": ["X"],
            "expression": {"kind": "binary", "operator": "*",
                           "left": {"kind": "local_ref", "name": "X"},
                           "right": {"kind": "number", "value": 2}},
        },
        "bindings": {
            "function": "double.function",
            "parameters": {"X": "double.parameter.x"},
            "result_statement": "double.result",
        },
    }


def edit_op() -> dict[str, Any]:
    return {
        "kind": "edit_assignment_expression",
        "target_handle": "double.result",
        "arguments": {"expression": {
            "kind": "binary", "operator": "*",
            "left": {"kind": "symbol_handle", "handle": "double.parameter.x"},
            "right": {"kind": "number", "value": 3},
        }},
    }


def metafile_operations() -> list[dict[str, Any]]:
    return [create_op(), edit_op()]


class EventWriter:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def emit(self, event: str, **data: Any) -> None:
        self.rows.append({"sequence": len(self.rows) + 1, "event": event,
                          "timestamp_utc": now(), **data})

    def write(self) -> None:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "history.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                    for row in self.rows), encoding="utf-8")


class MissionGateway:
    """Narrow campaign boundary; callers must not also receive raw Workspace."""

    def __init__(self, workspace: Workspace, document_id: str,
                 mission: dict[str, Any], events: EventWriter,
                 phase: str, aliases: dict[str, str] | None = None):
        self.workspace = workspace
        self.document_id = document_id
        self.mission = mission
        self.events = events
        self.phase = phase
        self.aliases = aliases if aliases is not None else {}

    def _resolve_expression(self, value: Any) -> Any:
        if isinstance(value, list):
            return [self._resolve_expression(x) for x in value]
        if not isinstance(value, dict):
            return value
        if value.get("kind") == "symbol_handle":
            handle = value.get("handle")
            if handle not in self.aliases:
                raise WorkspaceError("REPLAY_HANDLE_MISSING", f"Unbound replay handle {handle!r}")
            return {"kind": "symbol_ref", "symbol_id": self.aliases[handle]}
        return {key: self._resolve_expression(item) for key, item in value.items()}

    def _authorize(self, envelope: dict[str, Any], resolved: dict[str, Any]) -> None:
        if envelope.get("schema") != "basic-workspace.semantic-operation" or envelope.get("version") != 1:
            raise WorkspaceError("OPERATION_SCHEMA", "Unsupported semantic operation envelope")
        if envelope.get("mission_id") != self.mission["mission_id"]:
            raise WorkspaceError("MISSION_MISMATCH", "Operation belongs to another mission")
        if envelope.get("execution_profile") != self.mission["execution_profile"]:
            raise WorkspaceError("PROFILE_MISMATCH", "Operation execution profile does not match mission")
        if envelope.get("base_revision") != self.workspace.get_revision(self.document_id):
            raise WorkspaceError("STALE_REVISION", "Envelope base revision is stale")
        kind = envelope.get("operation")
        if kind not in self.mission["enforcement"]["allowed_operations"]:
            raise WorkspaceError("MISSION_OPERATION_FORBIDDEN", f"Operation {kind!r} is forbidden by this mission")
        if kind == "create_numeric_function":
            expected = {"name": "DOUBLE", "parameters": ["X"],
                        "expression": {"kind": "binary", "operator": "*",
                                       "left": {"kind": "local_ref", "name": "X"},
                                       "right": {"kind": "number", "value": 2}}}
            if envelope.get("base_revision") != self.mission["base_document_revision"] or resolved != expected:
                raise WorkspaceError("MISSION_CONSTRAINT", "Only the contracted DOUBLE(X)=X*2 construction is allowed")
            bindings = envelope.get("bindings", {})
            if bindings != create_op()["bindings"]:
                raise WorkspaceError("MISSION_CONSTRAINT", "Construction must declare the required portable handles")
        elif kind == "edit_assignment_expression":
            target = envelope.get("target") or {}
            if target.get("handle") != "double.result":
                raise WorkspaceError("MISSION_TARGET_FORBIDDEN", "Only the DOUBLE result assignment may change")
            expected = {"expression": {
                "kind": "binary", "operator": "*",
                "left": {"kind": "symbol_ref", "symbol_id": self.aliases.get("double.parameter.x")},
                "right": {"kind": "number", "value": 3},
            }}
            if resolved != expected:
                raise WorkspaceError("MISSION_CONSTRAINT", "The only permitted edit changes the multiplier from 2 to 3")
            if self.aliases.get("double.result") != target.get("resolved_id"):
                raise WorkspaceError("MISSION_TARGET_MISMATCH", "Result handle no longer resolves to its original statement")

    def apply(self, op: dict[str, Any], base_revision: int,
              rationale: str | None = None) -> dict[str, Any]:
        tx_id = "tx_" + uuid.uuid4().hex
        kind = op["kind"]
        args = copy.deepcopy(op["arguments"])
        target_handle = op.get("target_handle")
        envelope = {
            "schema": "basic-workspace.semantic-operation", "version": 1,
            "transaction_id": tx_id, "mission_id": self.mission["mission_id"],
            "execution_profile": self.mission["execution_profile"],
            "base_revision": base_revision,
            "preconditions": {"document_revision": base_revision},
            "operation": kind,
            "target": ({"handle": target_handle,
                        "resolved_id": self.aliases.get(target_handle)} if target_handle else None),
            "arguments": copy.deepcopy(args),
            "bindings": copy.deepcopy(op.get("bindings")),
            "rationale": rationale,
            "state": "proposed",
        }
        self.events.emit("operation_proposed", phase=self.phase, transaction_id=tx_id,
                         mission_id=self.mission["mission_id"], base_revision=base_revision,
                         operation_envelope=envelope,
                         rationale_is_agent_claim=bool(rationale))
        try:
            if kind == "edit_assignment_expression":
                args["expression"] = self._resolve_expression(args["expression"])
            self._authorize(envelope, args)
            if kind == "create_numeric_function":
                workspace_operation = {"operation": kind, **args}
            elif kind == "edit_assignment_expression":
                if target_handle not in self.aliases:
                    raise WorkspaceError("REPLAY_HANDLE_MISSING", f"Unbound target handle {target_handle!r}")
                workspace_operation = {"operation": kind,
                                       "statement_id": self.aliases[target_handle], **args}
            else:
                raise WorkspaceError("MISSION_OPERATION_FORBIDDEN", f"Operation {kind!r} is forbidden")
            preview_started = time.perf_counter()
            preview = self.workspace.preview_transaction(self.document_id, base_revision,
                                                         [workspace_operation], include_diff=True)
            preview_ms = (time.perf_counter() - preview_started) * 1000
            validated_envelope = {**envelope, "state": "validated",
                                  "validation_outcome": {"valid": True,
                                                         "diagnostics": preview["diagnostics"]},
                                  "expected_result_revision": preview["expected_result_revision"]}
            self.events.emit("preview_accepted", phase=self.phase, transaction_id=tx_id,
                             mission_id=self.mission["mission_id"], base_revision=base_revision,
                             resulting_revision=preview["expected_result_revision"],
                             target_handle=target_handle,
                             target_id=self.aliases.get(target_handle) if target_handle else None,
                             operation=kind, preview_diff=preview.get("diff", ""),
                             operation_envelope=validated_envelope,
                             preview_timing_ms=round(preview_ms, 4),
                             validation=preview["diagnostics"])
            # Contract and revision checks deliberately run again immediately
            # before the existing atomic Workspace commit boundary.
            self._authorize(envelope, args)
            commit_started = time.perf_counter()
            result = self.workspace.apply_transaction(self.document_id, base_revision,
                                                      [workspace_operation])
            commit_ms = (time.perf_counter() - commit_started) * 1000
            if kind == "create_numeric_function":
                self._bind_created(op["bindings"], result)
            committed_envelope = {**validated_envelope, "state": "committed",
                                  "commit_outcome": {"committed": True,
                                                     "resulting_revision": result["revision"],
                                                     "created_entity_handles": dict(self.aliases)}}
            self.events.emit("transaction_committed", phase=self.phase,
                             transaction_id=tx_id, mission_id=self.mission["mission_id"],
                             base_revision=base_revision, resulting_revision=result["revision"],
                             operation=kind, target_handle=target_handle,
                             target_id=self.aliases.get(target_handle) if target_handle else None,
                             operation_envelope=committed_envelope,
                             alias_bindings=dict(self.aliases),
                             created_entities=result["created_entities"],
                             created_statements=result["created_statements"],
                             semantic_snapshot=semantic_snapshot(self.workspace, self.document_id, self.aliases),
                             program_snapshot=self.workspace.render_document(self.document_id),
                             commit_timing_ms=round(commit_ms, 4),
                             preview_diff=preview.get("diff", ""))
            envelope["state"] = "committed"
            envelope["resulting_revision"] = result["revision"]
            return {"envelope": envelope, "preview": preview, "commit": result,
                    "preview_timing_ms": preview_ms, "commit_timing_ms": commit_ms}
        except WorkspaceError as exc:
            current_revision = self.workspace.get_revision(self.document_id)
            unchanged = current_revision == base_revision
            if not unchanged:
                self.events.emit("commit_postcondition_failure", phase=self.phase,
                                 transaction_id=tx_id, mission_id=self.mission["mission_id"],
                                 base_revision=base_revision, resulting_revision=current_revision,
                                 operation=kind, code=exc.code, message=exc.message,
                                 state_may_have_changed=True)
                raise
            self.events.emit("transaction_rejected", phase=self.phase,
                             transaction_id=tx_id, mission_id=self.mission["mission_id"],
                             base_revision=base_revision, resulting_revision=current_revision,
                             operation=kind, target_handle=target_handle,
                             operation_envelope={**envelope, "state": "rejected",
                                                 "validation_outcome": {"valid": False,
                                                                        "diagnostic": {"code": exc.code,
                                                                                       "message": exc.message}}},
                             denied=True, code=exc.code, message=exc.message,
                             authoritative_state_unchanged=unchanged)
            envelope["state"] = "rejected"
            envelope["diagnostic"] = {"code": exc.code, "message": exc.message}
            return {"envelope": envelope, "rejected": True, "error": exc}

    def _bind_created(self, bindings: dict[str, Any], result: dict[str, Any]) -> None:
        found: dict[str, str] = {}
        for row in result["created_entities"]:
            if row["kind"] == "function" and row["name"].casefold() == "double":
                found["double.function"] = row["symbol_id"]
            if row["kind"] == "parameter" and row["name"].casefold() == "x":
                found["double.parameter.x"] = row["symbol_id"]
        for row in result["created_statements"]:
            if row["kind"] == "assignment" and row.get("target_name", "").casefold() == "double":
                found["double.result"] = row["statement_id"]
        if found.keys() != {"double.function", "double.parameter.x", "double.result"}:
            raise WorkspaceError("ALIAS_BINDING_FAILED", "Created semantic entities did not match declared handles")
        declared = [bindings.get("function"), bindings.get("result_statement"),
                    *bindings.get("parameters", {}).values()]
        if set(found) != set(declared):
            raise WorkspaceError("ALIAS_BINDING_FAILED", "Declared handles did not match created entities")
        self.aliases.update(found)


def make_envelope(op: dict[str, Any], revision: int) -> dict[str, Any]:
    return {"schema": "basic-workspace.semantic-operation", "version": 1,
            "transaction_id": "replay-op-" + op["kind"], "mission_id": MISSION_ID,
            "execution_profile": PROFILE_REF, "base_revision": revision,
            "preconditions": {"document_revision": revision},
            "operation": op["kind"], "target": {"handle": op.get("target_handle")} if op.get("target_handle") else None,
            "arguments": copy.deepcopy(op["arguments"]), "rationale": None}


def normalized_state(workspace: Workspace, document_id: str,
                     aliases: dict[str, str]) -> dict[str, Any]:
    reverse = {opaque: handle for handle, opaque in aliases.items()}
    symbols = workspace.list_symbols(document_id)
    fn = next(x for x in symbols if x["kind"] == "function" and x["name"].casefold() == "double")
    parameter = next(x for x in symbols if x["kind"] == "parameter" and x["name"].casefold() == "x")
    statements = workspace.list_function_statements(document_id, fn["symbol_id"])["items"]
    rows = [{"kind": row["kind"],
             "target_handle": reverse.get(row.get("target_symbol_id")),
             "references": sorted(reverse.get(ref, "unmapped") for ref in row.get("referenced_symbol_ids", [])),
             "expression": row.get("expression_summary")}
            for row in statements]
    return {"function": {"name": fn["name"], "kind": fn["kind"], "scope": "module"},
            "parameter": {"name": parameter["name"], "kind": parameter["kind"], "scope": "function:double"},
            "bindings": {"result_target": reverse.get(statements[0].get("target_symbol_id")),
                         "parameter_references": [reverse.get(ref) for ref in statements[0].get("referenced_symbol_ids", [])]},
            "statements": rows}


def execute(workspace: Workspace, document_id: str, revision: int,
            function_id: str, arg: float) -> tuple[dict[str, Any], float]:
    service = MirExecutionService(timeout=10)
    all_results: dict[str, Any] = {}
    started = time.perf_counter()
    for engine in ("interp", "jit"):
        response = service.execute_function(workspace, document_id, revision,
                                            function_id, [arg], engine)
        all_results[engine] = {"result": response["result"],
                               "result_type": response["result_type"],
                               "timings_ms": response["timings_ms"]}
    return all_results, (time.perf_counter() - started) * 1000


def emit_run(events: EventWriter, workspace: Workspace, document_id: str,
             aliases: dict[str, str], revision: int, phase: str) -> dict[str, Any]:
    function_id = aliases["double.function"]
    function = workspace.find_definition(document_id, function_id)
    workspace.list_function_statements(document_id, function_id)
    events.emit("symbol_discovered", phase=phase, revision=revision,
                handle="double.function", symbol_id=function_id,
                name=function["name"], kind=function["kind"])
    diagnostic_started = time.perf_counter()
    diagnostics = workspace.get_diagnostics(document_id)
    validation_ms = (time.perf_counter() - diagnostic_started) * 1000
    errors = [x for x in diagnostics if x["severity"] == "error"]
    events.emit("program_validated", phase=phase, revision=revision,
                passed=not errors, diagnostics=diagnostics,
                validation_timing_ms=round(validation_ms, 4))
    if errors:
        raise RuntimeError(f"workspace diagnostics contain errors: {errors}")
    run_started = time.perf_counter()
    values, _ = execute(workspace, document_id, revision, function_id, 9)
    run_ms = (time.perf_counter() - run_started) * 1000
    events.emit("program_executed", phase=phase, revision=revision,
                function_handle="double.function", function_id=function_id,
                arguments=[9], outputs=values,
                engines_agree=values["interp"]["result"] == values["jit"]["result"],
                execution_timing_ms=round(run_ms, 4))
    return values


def replay_operation(workspace: Workspace, document_id: str, gateway: MissionGateway,
                     op: dict[str, Any]) -> dict[str, Any]:
    revision = workspace.get_revision(document_id)
    envelope = make_envelope(op, revision)
    return gateway.apply(op, revision)


def run_campaign() -> dict[str, Any]:
    started = time.perf_counter()
    profile = load_json("execution-profile.json")
    mission = load_json("mission.json")
    if profile.get("profile_id") != PROFILE_REF or mission.get("execution_profile") != PROFILE_REF:
        raise RuntimeError("execution profile/mission mismatch")
    if not {"interp", "jit"}.issubset(set(profile["guaranteed"]["execution_engines"])):
        raise RuntimeError("profile does not satisfy the execution requirements")
    events = EventWriter()
    workspace = Workspace()
    document_id = workspace.create_empty_document()["document_id"]
    aliases: dict[str, str] = {}
    gateway = MissionGateway(workspace, document_id, mission, events, "original", aliases)
    events.emit("session_started", campaign="DOUBLE construction, mission edit and replay",
                session_kind="scripted", mission_id=MISSION_ID, document_id=document_id,
                revision=workspace.get_revision(document_id), execution_profile=PROFILE_REF,
                execution_profile_name=profile["name"])
    events.emit("checkpoint_created", phase="original", checkpoint="empty",
                revision=workspace.get_revision(document_id),
                semantic_snapshot=semantic_snapshot(workspace, document_id, aliases),
                program_snapshot=workspace.render_document(document_id))

    stream_ops = metafile_operations()
    constructive_stream = {"schema": METAFILE_VERSION, "version": 1,
                           "execution_profile": PROFILE_REF,
                           "mission_contract": MISSION_ID,
                           "identity_policy": "declared handles are rebound from committed creation results",
                           "operations": [make_envelope(op, 1 if i == 0 else 2) | {
                               "operation": op["kind"], "bindings": op.get("bindings"),
                               "target": {"handle": op["target_handle"]} if op.get("target_handle") else None,
                               "arguments": copy.deepcopy(op["arguments"])}
                               for i, op in enumerate(stream_ops)]}
    stream_path = OUT / "constructive-operations.json"
    stream_path.write_text(json.dumps(constructive_stream, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    stream_bytes = stream_path.stat().st_size
    serialized_stream = json.loads(stream_path.read_text(encoding="utf-8"))
    replay_ops = []
    for row in serialized_stream["operations"]:
        replay_op = {"kind": row["operation"], "arguments": row["arguments"]}
        if row.get("bindings") is not None:
            replay_op["bindings"] = row["bindings"]
        if row.get("target"):
            replay_op["target_handle"] = row["target"]["handle"]
        replay_ops.append(replay_op)

    op = stream_ops[0]
    result = gateway.apply(op, 1, rationale="Create the first executable numeric example.")
    if result.get("rejected"):
        raise result["error"]
    fn_id = aliases["double.function"]
    events.emit("checkpoint_created", phase="original", checkpoint="initial-program",
                revision=result["commit"]["revision"], alias_bindings=dict(aliases),
                semantic_snapshot=semantic_snapshot(workspace, document_id, aliases),
                program_snapshot=workspace.render_document(document_id))
    initial = emit_run(events, workspace, document_id, aliases, 2, "original-before-edit")

    op = stream_ops[1]
    edit_result = gateway.apply(op, 2, rationale="Increase the scale while preserving the function interface.")
    if edit_result.get("rejected"):
        raise edit_result["error"]
    edited_revision = edit_result["commit"]["revision"]
    updated = emit_run(events, workspace, document_id, aliases, edited_revision, "original-after-edit")

    before_forbidden = workspace.render_document(document_id)
    forbidden_revision = workspace.get_revision(document_id)
    forbidden = {
        "kind": "rename_symbol", "target_handle": "double.function",
        "arguments": {"new_name": "TRIPLE"},
    }
    denied = gateway.apply(forbidden, forbidden_revision,
                           rationale="Attempt an explicitly forbidden function rename.")
    if not denied.get("rejected"):
        raise AssertionError("forbidden rename unexpectedly committed")
    unchanged = (workspace.get_revision(document_id) == forbidden_revision and
                 workspace.render_document(document_id) == before_forbidden)
    if not unchanged:
        raise AssertionError("forbidden operation mutated authoritative Workspace")
    final_source = workspace.render_document(document_id)
    final_state = normalized_state(workspace, document_id, aliases)

    replay_start = time.perf_counter()
    replay_workspace = Workspace()
    replay_document = replay_workspace.create_empty_document()["document_id"]
    replay_aliases: dict[str, str] = {}
    replay_gateway = MissionGateway(replay_workspace, replay_document, mission, events,
                                    "replay", replay_aliases)
    events.emit("replay_started", mission_id=MISSION_ID,
                document_id=replay_document, base_revision=replay_workspace.get_revision(replay_document),
                stream_schema=constructive_stream["schema"], stream_version=constructive_stream["version"],
                operation_count=len(replay_ops), execution_profile=PROFILE_REF)
    if serialized_stream.get("execution_profile") != profile.get("profile_id"):
        events.emit("replay_failed", mission_id=MISSION_ID, code="PROFILE_MISMATCH",
                    message="Constructive stream requires an incompatible execution profile",
                    resulting_revision=replay_workspace.get_revision(replay_document))
        raise RuntimeError("constructive metafile execution profile mismatch")
    replay_outcomes = []
    for replay_op in replay_ops:
        outcome = replay_operation(replay_workspace, replay_document, replay_gateway, replay_op)
        if outcome.get("rejected"):
            raise outcome["error"]
        replay_outcomes.append(outcome)
    replay_revision = replay_workspace.get_revision(replay_document)
    replay_results = emit_run(events, replay_workspace, replay_document, replay_aliases,
                              replay_revision, "replay-final")
    replay_state = normalized_state(replay_workspace, replay_document, replay_aliases)
    replay_ms = (time.perf_counter() - replay_start) * 1000
    structural_equal = final_state == replay_state
    bindings_equal = (final_state["bindings"] == replay_state["bindings"] and
                      all(alias in replay_aliases for alias in aliases))
    behavior_equal = all(initial[engine]["result"] == 18.0 for engine in ("interp", "jit")) and all(
        updated[engine]["result"] == replay_results[engine]["result"] == 27.0
        for engine in ("interp", "jit"))
    engine_agreement = all(
        values["interp"]["result"] == values["jit"]["result"]
        for values in (initial, updated, replay_results))
    remapped = {handle: {"original_id": opaque, "replay_id": replay_aliases[handle],
                         "different": opaque != replay_aliases[handle]}
                for handle, opaque in aliases.items()}
    replay_ok = structural_equal and bindings_equal and behavior_equal and engine_agreement
    equivalence = {
        "schema": "basic-workspace.equivalence-report", "version": 1,
        "structural_equivalence": structural_equal,
        "binding_equivalence": bindings_equal,
        "behavioral_equivalence": behavior_equal,
        "execution_engine_agreement": engine_agreement,
        "initial_outputs": initial, "updated_outputs": updated,
        "replay_outputs": replay_results,
        "initial_expected": 18.0, "updated_expected": 27.0,
        "revision_original": edited_revision, "revision_replay": replay_revision,
        "original_rendered_diagnostic": final_source,
        "replay_rendered_diagnostic": replay_workspace.render_document(replay_document),
        "normalized_original": final_state, "normalized_replay": replay_state,
        "identity_remapping": remapped,
        "identifier_remapping_count": sum(item["different"] for item in remapped.values()),
        "mission_violation_rejected": True,
        "rejected_operation_preserved_revision": forbidden_revision,
        "rejected_operation_preserved_render": True,
        "replay_operation_count": len(stream_ops), "replay_failure_count": 0 if replay_ok else 1,
        "replay_ms": round(replay_ms, 4), "constructive_stream_bytes": stream_bytes,
    }
    (OUT / "equivalence.json").write_text(json.dumps(equivalence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    events.emit("replay_completed", mission_id=MISSION_ID, document_id=replay_document,
                revision=replay_revision, passed=replay_ok, equivalence={
                    "structural": structural_equal, "binding": bindings_equal,
                    "behavioral": behavior_equal, "engines_agree": engine_agreement},
                alias_bindings=replay_aliases, identity_remapping=remapped,
                replay_timing_ms=round(replay_ms, 4), operation_count=len(replay_ops), failure_count=0 if replay_ok else 1,
                semantic_snapshot=semantic_snapshot(replay_workspace, replay_document, replay_aliases),
                program_snapshot=replay_workspace.render_document(replay_document))
    events.emit("session_completed", mission_id=MISSION_ID, passed=replay_ok,
                original_revision=edited_revision, replay_revision=replay_revision,
                forbidden_rejection_preserved_state=True)
    total_ms = (time.perf_counter() - started) * 1000
    events.write()
    trace_bytes = (OUT / "history.jsonl").stat().st_size
    (OUT / "metrics.json").write_text(json.dumps({
        "schema": "basic-workspace.semantic-replay-metrics", "version": 1,
        "campaign_kind": "scripted", "operation_count": len(stream_ops),
        "replay_operation_count": len(stream_ops), "replay_failure_count": 0 if replay_ok else 1,
        "mission_violations_rejected": 1, "unexpected_model_differences": 0 if replay_ok else 1,
        "identifier_handles_remapped": len(remapped),
        "constructive_stream_bytes": stream_bytes, "historical_journal_bytes": trace_bytes,
        "campaign_total_ms": round(total_ms, 4), "replay_ms": round(replay_ms, 4),
        "kitty_version": "0.49.2", "kitty_shader_available_by_version": True,
        "kitty_remote_session_and_screenshot": "unavailable in non-TTY harness; not captured",
    }, indent=2) + "\n", encoding="utf-8")
    return equivalence


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    result = run_campaign()
    print(json.dumps({key: result[key] for key in (
        "structural_equivalence", "binding_equivalence", "behavioral_equivalence",
        "execution_engine_agreement", "identifier_remapping_count", "replay_ms")}, indent=2))
