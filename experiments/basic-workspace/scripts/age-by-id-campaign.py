#!/usr/bin/env python3
"""Construct, mission-gate, model-edit, replay and report AGE_BY_ID."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
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
from basic_workspace.projection import build_projection, projection_semantics
from basic_workspace.projection import Assignment, ForLoop, IfBlock
from experiment.llm_runner import ChatEndpoint, endpoint_metadata

OUT = ROOT / "results" / "semantic-replay" / "age-by-id"
PROFILE_ID = "basic-workspace.numeric-control.v1"
MISSION_ID = "mission.age-by-logical-id.205.v1"
METAFILE_SCHEMA = "basic-workspace.constructive-metafile"
EXPECTED = {101: 25.0, 205: 42.0, 900: 53.0, 999: -1.0, 2: -1.0}


def n(value: float) -> dict[str, Any]:
    return {"kind": "number", "value": value}


def local(name: str) -> dict[str, Any]:
    return {"kind": "local_ref", "name": name}


def array(name: str, index: Any) -> dict[str, Any]:
    return {"kind": "array_element", "array_ref": local(name), "index": index}


def seed_operation() -> dict[str, Any]:
    body: list[dict[str, Any]] = []
    rows = ((101, 25), (205, 42), (900, 53))
    for name, column in (("PERSON_ID", 0), ("PERSON_AGE", 1)):
        for slot, row in enumerate(rows):
            body.append({"kind": "array_assign", "array_ref": local(name),
                         "index": n(slot), "expression": n(row[column])})
    condition = {"kind": "binary", "operator": "=",
                 "left": array("PERSON_ID", local("I")),
                 "right": local("WANTED")}
    body.extend([
        {"kind": "assign", "target": {"kind": "result"}, "expression": n(-1)},
        {"kind": "for", "variable": "I", "start": n(0), "end": n(2),
         "body": [{"kind": "if", "condition": condition,
                   "then": [{"kind": "assign", "target": {"kind": "result"},
                             "expression": array("PERSON_AGE", local("I"))}]}]},
    ])
    return {"operation": "create_numeric_function",
            "name": "AGE_BY_ID", "parameters": ["WANTED"],
            "arrays": [{"name": "PERSON_ID", "upper_bound": 2},
                       {"name": "PERSON_AGE", "upper_bound": 2}],
            "body": body}


class Trace:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    @staticmethod
    def stamp() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    def emit(self, event: str, **data: Any) -> dict[str, Any]:
        row = {"sequence": len(self.events) + 1, "event": event,
               "timestamp_utc": self.stamp(), **data}
        self.events.append(row)
        return row

    def write(self, path: Path) -> None:
        path.write_text("".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n"
                                       for e in self.events), encoding="utf-8")


def walk_assignments(nodes: tuple[Any, ...] | list[Any]):
    for node in nodes:
        if isinstance(node, Assignment):
            yield node
        elif isinstance(node, IfBlock):
            yield from walk_assignments(node.then_body)
            yield from walk_assignments(node.else_body)
        elif isinstance(node, ForLoop):
            yield from walk_assignments(node.body)


def expr_constant(expr: Any) -> float | None:
    if expr is None:
        return None
    if expr.kind == "number":
        return float(expr.value)
    if expr.kind == "unary_minus" and expr.children[0].kind == "number":
        return -float(expr.children[0].value)
    return None


def create_seed(workspace: Workspace, trace: Trace, phase: str = "seed") -> tuple[str, dict[str, str], dict[str, Any]]:
    doc = workspace.create_empty_document()
    document_id = doc["document_id"]
    operation = seed_operation()
    base = workspace.get_revision(document_id)
    txid = "tx_seed_" + uuid.uuid4().hex
    trace.emit("operation_proposed", phase=phase, actor="harness_scripted_seed",
               transaction_id=txid, base_revision=base, operation_envelope={
                   "schema": "basic-workspace.semantic-operation", "version": 1,
                   "transaction_id": txid, "mission_id": None,
                   "execution_profile": PROFILE_ID, "base_revision": base,
                   "preconditions": {"document_revision": base},
                   "operation": operation["operation"], "arguments": operation,
                   "state": "proposed"})
    candidate = workspace.preview_transaction_semantics(document_id, base, [operation])
    trace.emit("preview_accepted", phase=phase, transaction_id=txid,
               base_revision=base, resulting_revision=candidate["preview"]["expected_result_revision"],
               candidate_semantic_snapshot=candidate["candidate_semantics"],
               validation=candidate["preview"]["diagnostics"])
    result = workspace.apply_transaction(document_id, base, [operation])
    projection = build_projection(workspace, document_id, result["revision"])
    function = projection.functions[0]
    created_entities = result["created_entities"]
    aliases: dict[str, str] = {}
    for entity in created_entities:
        kind, name = entity["kind"], entity["name"].casefold()
        if kind == "function" and name == "age_by_id":
            aliases["age_by_id.function"] = entity["symbol_id"]
        elif kind == "parameter" and name == "wanted":
            aliases["age_by_id.parameter.wanted"] = entity["symbol_id"]
        elif kind == "array" and name == "person_id":
            aliases["people.id"] = entity["symbol_id"]
        elif kind == "array" and name == "person_age":
            aliases["people.age"] = entity["symbol_id"]
        elif kind == "variable" and name == "i":
            aliases["age_by_id.loop.i"] = entity["symbol_id"]
    required_symbols = {"age_by_id.function", "age_by_id.parameter.wanted",
                        "people.id", "people.age", "age_by_id.loop.i"}
    if set(aliases) != required_symbols:
        raise RuntimeError(f"seed symbol handles not bound uniquely: {set(aliases)}")
    by_alias = {value: key for key, value in aliases.items()}

    id_by_slot: dict[int, int] = {}
    for assignment in walk_assignments(function.statements):
        if (assignment.target_is_array and assignment.target_symbol_id == aliases["people.id"]
                and assignment.target_index and assignment.target_index.kind == "number"):
            slot = int(float(assignment.target_index.value))
            entity_id = expr_constant(assignment.expression)
            if entity_id is None or entity_id != int(entity_id) or slot in id_by_slot:
                raise RuntimeError("PERSON_ID initialization is ambiguous")
            id_by_slot[slot] = int(entity_id)
    if id_by_slot != {0: 101, 1: 205, 2: 900}:
        raise RuntimeError(f"logical ID-to-slot map differs from fixture: {id_by_slot}")
    seen_statements: set[str] = set()
    for assignment in walk_assignments(function.statements):
        if not assignment.statement_id:
            # The projection appends one synthetic function-result terminal
            # after the explicit body. It has no canonical source statement.
            if assignment.expression.kind == "result" and assignment.target_symbol_id == aliases["age_by_id.function"]:
                continue
            raise RuntimeError("projected assignment lost its stable Workspace statement identity")
        if assignment.statement_id in seen_statements:
            raise RuntimeError("duplicate projected statement identity")
        seen_statements.add(assignment.statement_id)
        if assignment.target_is_array:
            slot = int(float(assignment.target_index.value)) if assignment.target_index and assignment.target_index.kind == "number" else None
            if assignment.target_symbol_id == aliases["people.id"] and slot is not None:
                value = expr_constant(assignment.expression)
                handle = f"people.id.{int(value)}" if value is not None else ""
            elif assignment.target_symbol_id == aliases["people.age"] and slot in id_by_slot:
                handle = f"people.age.{id_by_slot[slot]}"
            else:
                handle = ""
        elif assignment.target_symbol_id == aliases["age_by_id.function"]:
            if expr_constant(assignment.expression) == -1:
                handle = "age_by_id.default"
            elif (assignment.expression.kind == "array_element" and
                  assignment.expression.value == aliases["people.age"]):
                handle = "age_by_id.match_result"
            elif assignment.expression.kind == "result":
                handle = "age_by_id.implicit_return"
            else:
                handle = ""
        else:
            handle = ""
        if not handle or handle in aliases:
            raise RuntimeError("a seed assignment has missing or ambiguous semantic handle")
        aliases[handle] = assignment.statement_id
        by_alias[assignment.statement_id] = handle
    required = {"age_by_id.function", "age_by_id.parameter.wanted", "people.id", "people.age",
                "age_by_id.loop.i", "people.id.101", "people.id.205", "people.id.900",
                "people.age.101", "people.age.205", "people.age.900",
                "age_by_id.default", "age_by_id.match_result", "age_by_id.implicit_return"}
    if set(aliases) != required:
        raise RuntimeError(f"seed statement handles differ: {set(aliases) ^ required}")
    normalized = normalize_projection(projection_semantics(projection), aliases)
    trace.emit("transaction_committed", phase=phase, actor="harness_scripted_seed",
               transaction_id=txid, base_revision=base, resulting_revision=result["revision"],
               operation=operation["operation"], alias_bindings=dict(aliases),
               created_entities=created_entities, created_statements=result["created_statements"],
               semantic_snapshot=normalized,
               program_snapshot=workspace.render_document(document_id),
               binding_provenance={"entity IDs": "create transaction result",
                                   "statement handles": "projection statement IDs plus typed target/index/value",
                                   "logical ID slots": id_by_slot})
    trace.emit("program_validated", phase=phase, revision=result["revision"], passed=True,
               diagnostics=workspace.get_diagnostics(document_id))
    return document_id, aliases, {"operation": operation, "revision": result["revision"],
                                  "projection": normalized, "id_to_slot": id_by_slot}


def normalize_projection(raw: dict[str, Any], aliases: dict[str, str]) -> dict[str, Any]:
    reverse = {opaque: handle for handle, opaque in aliases.items()}

    def expr(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        kind, value = row["kind"], row.get("value")
        if kind in ("variable", "variable_string", "result", "result_string", "call",
                    "array_element", "array_element_string") and value is not None:
            if value not in reverse:
                raise WorkspaceError("REPLAY_HANDLE_MISSING", f"Projection reference {value} has no declared handle")
            value = reverse[value]
        return {"kind": kind, "value": value,
                "children": [expr(child) for child in row.get("children", [])]}

    def stmt(row: dict[str, Any]) -> dict[str, Any]:
        kind = row["kind"]
        if kind in ("assignment", "array_assignment"):
            statement_id = row.get("statement_id")
            if statement_id is None and row.get("target_is_result") and row.get("expression", {}).get("kind") == "result":
                return {"kind": "implicit_function_return", "expression": expr(row["expression"])}
            if statement_id not in reverse:
                raise WorkspaceError("REPLAY_HANDLE_MISSING", f"Assignment statement {statement_id} has no declared handle")
            target = row.get("target_symbol_id")
            if target not in reverse:
                raise WorkspaceError("REPLAY_HANDLE_MISSING", f"Assignment target {target} has no declared handle")
            return {"kind": kind, "statement_handle": reverse[statement_id],
                    "target_handle": reverse[target], "target_is_result": row["target_is_result"],
                    "target_index": expr(row.get("target_index")),
                    "expression": expr(row["expression"])}
        if kind == "if":
            return {"kind": "if", "condition": expr(row["condition"]),
                    "then": [stmt(x) for x in row["then"]],
                    "else": [stmt(x) for x in row["else"]]}
        if kind == "for":
            variable = row["variable_id"]
            if variable not in reverse:
                raise WorkspaceError("REPLAY_HANDLE_MISSING", f"Loop variable {variable} has no declared handle")
            return {"kind": "for", "variable_handle": reverse[variable],
                    "start": row["start"], "end": row["end"], "step": row["step"],
                    "iteration_limit": row["iteration_limit"],
                    "body": [stmt(x) for x in row["body"]]}
        raise WorkspaceError("REPLAY_STRUCTURE", f"Unsupported projected statement kind {kind}")

    functions = []
    for function in raw["functions"]:
        if function["symbol_id"] not in reverse:
            raise WorkspaceError("REPLAY_HANDLE_MISSING", "Function has no portable handle")
        for parameter in function["parameter_ids"] + function["local_ids"]:
            if parameter not in reverse:
                raise WorkspaceError("REPLAY_HANDLE_MISSING", f"Local/parameter {parameter} has no portable handle")
        arrays = []
        for array_row in function["arrays"]:
            if array_row["symbol_id"] not in reverse:
                raise WorkspaceError("REPLAY_HANDLE_MISSING", "Array has no portable handle")
            arrays.append({"handle": reverse[array_row["symbol_id"]], "name": array_row["name"],
                           "lower_bound": array_row["lower_bound"],
                           "upper_bound": array_row["upper_bound"],
                           "element_type": array_row["element_type"], "shared": array_row["shared"]})
        functions.append({"handle": reverse[function["symbol_id"]], "name": function["name"],
                          "parameters": [reverse[x] for x in function["parameter_ids"]],
                          "locals": [reverse[x] for x in function["local_ids"]],
                          "local_types": function["local_types"],
                          "return_type": function["return_type"], "arrays": arrays,
                          "statements": [stmt(x) for x in function["statements"]]})
    return {"functions": functions}


def binding_edges(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    def expr(node: Any, path: str) -> None:
        if isinstance(node, dict):
            if node.get("kind") in ("variable", "variable_string", "result", "result_string", "call", "array_element", "array_element_string"):
                edges.append({"path": path, "reference": str(node.get("value")), "kind": node["kind"]})
            for i, child in enumerate(node.get("children", [])):
                expr(child, f"{path}.{i}")
    def stmts(rows: list[dict[str, Any]], prefix: str) -> None:
        for i, row in enumerate(rows):
            path = f"{prefix}/{i}"
            if row["kind"] in ("assignment", "array_assignment"):
                edges.append({"path": path + "/target", "reference": row["target_handle"], "kind": "assignment_target"})
                expr(row.get("target_index"), path + "/index")
                expr(row.get("expression"), path + "/value")
            elif row["kind"] == "if":
                expr(row["condition"], path + "/condition")
                stmts(row["then"], path + "/then")
                stmts(row["else"], path + "/else")
            elif row["kind"] == "for":
                edges.append({"path": path + "/loop-variable", "reference": row["variable_handle"], "kind": "loop_variable"})
                stmts(row["body"], path + "/body")
    for function in snapshot["functions"]:
        edges.append({"path": "function", "reference": function["handle"], "kind": "function"})
        for index, handle in enumerate(function["parameters"]):
            edges.append({"path": f"parameter/{index}", "reference": handle, "kind": "parameter"})
        for index, array in enumerate(function["arrays"]):
            edges.append({"path": f"array/{index}", "reference": array["handle"], "kind": "array"})
        stmts(function["statements"], function["handle"])
    return edges


def find_statement(tree: Any, handle: str) -> dict[str, Any] | None:
    if isinstance(tree, list):
        for row in tree:
            found = find_statement(row, handle)
            if found is not None:
                return found
    elif isinstance(tree, dict):
        if tree.get("statement_handle") == handle:
            return tree
        for value in tree.values():
            found = find_statement(value, handle)
            if found is not None:
                return found
    return None


def expected_edit_snapshot(before: dict[str, Any], handle: str, new_age: float) -> dict[str, Any]:
    changed = copy.deepcopy(before)
    target = find_statement(changed, handle)
    if target is None:
        raise WorkspaceError("MISSION_TARGET_MISSING", "Authorized age assignment is absent from candidate projection")
    if (target["kind"] != "array_assignment" or target["target_handle"] != "people.age"
            or target["target_index"] != {"kind": "number", "value": 1.0, "children": []}
            or target["expression"] != {"kind": "number", "value": 42.0, "children": []}):
        raise WorkspaceError("MISSION_BASELINE_MISMATCH", "Age-205 statement no longer matches the verified ID-to-slot baseline")
    target["expression"] = {"kind": "number", "value": float(new_age), "children": []}
    return changed


class MissionGateway:
    """Single-campaign, revision-checked gateway; not a general policy engine."""

    def __init__(self, workspace: Workspace, document_id: str,
                 aliases: dict[str, str], base_snapshot: dict[str, Any],
                 mission: dict[str, Any], trace: Trace, phase: str):
        self.workspace, self.document_id = workspace, document_id
        self.aliases = aliases
        self.reverse = {opaque: handle for handle, opaque in aliases.items()}
        self.base_snapshot = base_snapshot
        self.mission, self.trace, self.phase = mission, trace, phase
        self.pending: dict[str, dict[str, Any]] = {}
        self.committed = False

    def _reject(self, txid: str, operation: str, statement_id: str | None,
                expected_revision: int, code: str, message: str) -> dict[str, Any]:
        current = self.workspace.get_revision(self.document_id)
        self.trace.emit("transaction_rejected", phase=self.phase, actor="mission_gateway",
                        mission_id=MISSION_ID, transaction_id=txid,
                        base_revision=expected_revision, resulting_revision=current,
                        operation=operation, statement_id=statement_id,
                        target_handle=self.reverse.get(statement_id), denied=True,
                        code=code, message=message,
                        authoritative_state_unchanged=True,
                        revision_unchanged_from_rejection_point=True,
                        stale_base=(current != expected_revision))
        return {"ok": False, "code": code, "message": message,
                "current_revision": current, "transaction_id": txid}

    def _candidate_check(self, expected_revision: int, statement_id: str,
                         value: float) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        if self.committed:
            raise WorkspaceError("MISSION_EDIT_LIMIT", "The mission permits one committed age update")
        if expected_revision != self.workspace.get_revision(self.document_id):
            raise WorkspaceError("STALE_REVISION", "The proposed edit is based on an obsolete document revision")
        target_handle = self.reverse.get(statement_id)
        if target_handle is None:
            raise WorkspaceError("UNKNOWN_SEMANTIC_TARGET", "Statement identity was not discovered or does not exist")
        allowed = self.mission["enforcement"]["allowed_target_handle"]
        if target_handle != allowed:
            raise WorkspaceError("MISSION_TARGET_FORBIDDEN", f"Only {allowed} may be edited in this mission")
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                not math.isfinite(float(value))):
            raise WorkspaceError("MISSION_VALUE_TYPE", "Age must be a finite numeric literal")
        limits = self.mission["enforcement"]["numeric_literal_range"]
        if not limits["minimum"] <= float(value) <= limits["maximum"]:
            raise WorkspaceError("MISSION_VALUE_RANGE", "Age literal is outside the permitted range")
        before = self.base_snapshot
        selected = find_statement(before, allowed)
        if selected is None or selected["target_handle"] != "people.age" or selected["target_index"]["value"] != 1.0:
            raise WorkspaceError("MISSION_ID_SLOT_UNVERIFIED", "The age target is not bound to the verified PERSON_ID slot")
        operation = {"operation": "edit_assignment_expression", "statement_id": statement_id,
                     "expression": n(float(value))}
        candidate = self.workspace.preview_transaction_semantics(
            self.document_id, expected_revision, [operation])
        candidate_snapshot = normalize_projection(candidate["candidate_semantics"], self.aliases)
        expected = expected_edit_snapshot(before, allowed, float(value))
        if candidate_snapshot != expected:
            raise WorkspaceError("MISSION_CHANGESET_FORBIDDEN",
                                 "Candidate changes declarations, bindings, control flow, or unrelated statements")
        if statement_id not in candidate["preview"]["affected_statement_ids"]:
            raise WorkspaceError("MISSION_TARGET_MISMATCH", "Workspace preview did not affect the requested statement")
        return operation, candidate, candidate_snapshot

    def preview(self, statement_id: str, new_age: Any,
                expected_revision: int) -> dict[str, Any]:
        txid = "tx_" + uuid.uuid4().hex
        handle = self.reverse.get(statement_id)
        operation_envelope = {"schema": "basic-workspace.semantic-operation", "version": 1,
                              "transaction_id": txid, "mission_id": MISSION_ID,
                              "execution_profile": PROFILE_ID,
                              "base_revision": expected_revision,
                              "preconditions": {"document_revision": expected_revision,
                                                "target_handle": handle},
                              "operation": "edit_assignment_expression",
                              "target": {"statement_id": statement_id,
                                         "handle": handle},
                              "arguments": {"expression": n(new_age) if isinstance(new_age, (int, float)) else new_age},
                              "rationale": None, "state": "proposed"}
        self.trace.emit("operation_proposed", phase=self.phase, actor="llm_tool" if self.phase == "agent" else "scripted_control",
                        mission_id=MISSION_ID, transaction_id=txid,
                        base_revision=expected_revision,
                        operation_envelope=operation_envelope)
        try:
            operation, candidate, candidate_snapshot = self._candidate_check(
                expected_revision, statement_id, new_age)
        except WorkspaceError as exc:
            return self._reject(txid, "edit_assignment_expression", statement_id,
                                expected_revision, exc.code, exc.message)
        preview_ms_started = time.perf_counter()
        diff_preview = self.workspace.preview_transaction(self.document_id, expected_revision,
                                                          [operation], include_diff=True)
        elapsed = (time.perf_counter() - preview_ms_started) * 1000
        self.pending[txid] = {"operation": operation, "statement_id": statement_id,
                              "expected_revision": expected_revision,
                              "new_age": float(new_age),
                              "candidate_snapshot": candidate_snapshot}
        self.trace.emit("preview_accepted", phase=self.phase, actor="mission_gateway",
                        mission_id=MISSION_ID, transaction_id=txid,
                        base_revision=expected_revision,
                        resulting_revision=diff_preview["expected_result_revision"],
                        operation="edit_assignment_expression", target_handle=handle,
                        new_age=float(new_age), authorized_literal_range={"min": 0, "max": 130},
                        proposed_diff=diff_preview.get("diff", ""),
                        candidate_semantic_snapshot=candidate_snapshot,
                        validation=diff_preview["diagnostics"], preview_ms=round(elapsed, 4),
                        operation_envelope={**operation_envelope, "state": "validated",
                                            "validation_outcome": {"valid": True,
                                                                   "expected_result_revision": diff_preview["expected_result_revision"]}})
        return {"ok": True, "transaction_id": txid,
                "base_revision": expected_revision,
                "expected_result_revision": diff_preview["expected_result_revision"],
                "target_handle": handle, "new_age": float(new_age),
                "allowed_but_goal_value": float(new_age) != float(self.mission["functional_goal"]["new_age"]),
                "semantic_change_set": [f"{handle}.expression: 42 -> {float(new_age)}"],
                "diagnostics": diff_preview["diagnostics"]}

    def commit(self, transaction_id: str) -> dict[str, Any]:
        pending = self.pending.get(transaction_id)
        if pending is None:
            return self._reject(transaction_id, "edit_assignment_expression", None,
                                self.workspace.get_revision(self.document_id),
                                "PREVIEW_NOT_FOUND", "No accepted preview exists for this transaction")
        expected_revision = pending["expected_revision"]
        statement_id = pending["statement_id"]
        # Authorization and candidate semantic delta are recomputed immediately
        # before the existing atomic Workspace commit, not trusted from preview.
        try:
            operation, _, expected_snapshot = self._candidate_check(
                expected_revision, statement_id, pending["new_age"])
            if expected_snapshot != pending["candidate_snapshot"]:
                raise WorkspaceError("PREVIEW_CANDIDATE_CHANGED", "Candidate differs from the accepted preview")
            result = self.workspace.apply_transaction(self.document_id, expected_revision, [operation])
        except WorkspaceError as exc:
            return self._reject(transaction_id, "edit_assignment_expression", statement_id,
                                expected_revision, exc.code, exc.message)
        projection = build_projection(self.workspace, self.document_id, result["revision"])
        actual_snapshot = normalize_projection(projection_semantics(projection), self.aliases)
        if actual_snapshot != expected_snapshot:
            self.trace.emit("commit_postcondition_failure", phase=self.phase,
                            transaction_id=transaction_id, mission_id=MISSION_ID,
                            resulting_revision=result["revision"], state_may_have_changed=True)
            raise RuntimeError("committed candidate differs from policy-validated projection")
        self.committed = True
        self.trace.emit("transaction_committed", phase=self.phase, actor="mission_gateway",
                        mission_id=MISSION_ID, transaction_id=transaction_id,
                        operation="edit_assignment_expression", target_handle="people.age.205",
                        target_statement_id=statement_id,
                        base_revision=expected_revision, resulting_revision=result["revision"],
                        new_age=pending["new_age"], affected_statement_ids=result["affected_statement_ids"],
                        alias_bindings=dict(self.aliases), semantic_snapshot=actual_snapshot,
                        program_snapshot=self.workspace.render_document(self.document_id),
                        operation_envelope={"schema": "basic-workspace.semantic-operation", "version": 1,
                                            "transaction_id": transaction_id, "mission_id": MISSION_ID,
                                            "execution_profile": PROFILE_ID,
                                            "base_revision": expected_revision,
                                            "operation": "edit_assignment_expression",
                                            "target": {"handle": "people.age.205", "statement_id": statement_id},
                                            "arguments": {"expression": n(pending["new_age"])},
                                            "state": "committed", "resulting_revision": result["revision"]})
        return {"ok": True, "committed": True, "revision": result["revision"],
                "target_handle": "people.age.205", "new_age": pending["new_age"]}

    def reject_non_edit(self, operation: str, target_id: str | None,
                        expected_revision: int) -> dict[str, Any]:
        txid = "tx_" + uuid.uuid4().hex
        self.trace.emit("operation_proposed", phase=self.phase, actor="scripted_control",
                        mission_id=MISSION_ID, transaction_id=txid,
                        base_revision=expected_revision,
                        operation_envelope={"schema": "basic-workspace.semantic-operation", "version": 1,
                                            "transaction_id": txid, "mission_id": MISSION_ID,
                                            "execution_profile": PROFILE_ID,
                                            "base_revision": expected_revision,
                                            "operation": operation,
                                            "target": {"id": target_id}, "state": "proposed"})
        return self._reject(txid, operation, target_id, expected_revision,
                            "MISSION_OPERATION_FORBIDDEN", f"Operation {operation!r} is outside the mission allowlist")


def execute_values(workspace: Workspace, document_id: str, aliases: dict[str, str],
                   revision: int) -> dict[str, dict[str, float]]:
    executor = MirExecutionService(timeout=10)
    out: dict[str, dict[str, float]] = {}
    for engine in ("interp", "jit"):
        out[engine] = {str(entity): executor.execute_function(
            workspace, document_id, revision, aliases["age_by_id.function"], [entity], engine)["result"]
            for entity in EXPECTED}
    return out


def semantic_snapshot(workspace: Workspace, document_id: str,
                      aliases: dict[str, str]) -> dict[str, Any]:
    return normalize_projection(projection_semantics(build_projection(workspace, document_id)), aliases)


def run_negative_controls(mission: dict[str, Any], trace: Trace) -> dict[str, Any]:
    workspace = Workspace()
    document_id, aliases, seed = create_seed(workspace, trace, "negative-controls")
    revision = seed["revision"]
    snapshot = seed["projection"]
    gateway = MissionGateway(workspace, document_id, aliases, snapshot, mission,
                             trace, "negative-controls")
    before_render = workspace.render_document(document_id)
    before_projection = semantic_snapshot(workspace, document_id, aliases)
    before_results = execute_values(workspace, document_id, aliases, revision)
    cases = [
        {"id": "function-rename", "operation": "rename_symbol", "target": "age_by_id.function", "value": None, "revision": revision},
        {"id": "entity-id-cell", "operation": "edit_assignment_expression", "target": "people.id.205", "value": 47, "revision": revision},
        {"id": "other-age-cell", "operation": "edit_assignment_expression", "target": "people.age.900", "value": 47, "revision": revision},
        {"id": "loop-bound", "operation": "edit_for_bound", "target": "age_by_id.function", "value": 3, "revision": revision},
        {"id": "if-condition", "operation": "edit_if_condition", "target": "age_by_id.match_condition", "value": 1, "revision": revision},
        {"id": "stale-revision", "operation": "edit_assignment_expression", "target": "people.age.205", "value": 47, "revision": revision - 1},
        {"id": "unknown-statement", "operation": "edit_assignment_expression", "target_id": "stmt_fabricated", "value": 47, "revision": revision},
        {"id": "out-of-range-age", "operation": "edit_assignment_expression", "target": "people.age.205", "value": 131, "revision": revision},
    ]
    results = []
    for case in cases:
        if case["operation"] != "edit_assignment_expression":
            response = gateway.reject_non_edit(case["operation"], aliases.get(case.get("target"), case.get("target_id")), case["revision"])
        else:
            target_id = case.get("target_id") or aliases[case["target"]]
            response = gateway.preview(target_id, case["value"], case["revision"])
        after_revision = workspace.get_revision(document_id)
        after_render = workspace.render_document(document_id)
        after_projection = semantic_snapshot(workspace, document_id, aliases)
        after_results = execute_values(workspace, document_id, aliases, after_revision)
        unchanged = (after_revision == revision and after_render == before_render and
                     after_projection == before_projection and after_results == before_results)
        if response.get("ok") or not unchanged:
            raise AssertionError(f"negative policy fixture {case['id']} had side effects or passed: {response}")
        results.append({"id": case["id"], "rejected": True,
                        "code": response["code"], "revision_unchanged": after_revision == revision,
                        "canonical_render_unchanged": after_render == before_render,
                        "bindings_and_structure_unchanged": after_projection == before_projection,
                        "execution_results_unchanged": after_results == before_results})
    # A different but valid age is authorized as a preview; task success is
    # evaluated separately and the preview is intentionally not committed.
    permitted = gateway.preview(aliases["people.age.205"], 48, revision)
    if not permitted.get("ok") or not permitted.get("allowed_but_goal_value"):
        raise AssertionError(f"policy overfit to the goal value instead of its declared range: {permitted}")
    no_mutation = (workspace.get_revision(document_id) == revision and
                   workspace.render_document(document_id) == before_render and
                   semantic_snapshot(workspace, document_id, aliases) == before_projection and
                   execute_values(workspace, document_id, aliases, revision) == before_results)
    if not no_mutation:
        raise AssertionError("age-48 preview changed the controlled program")
    return {"cases": results, "allowed_alternative_age_preview": permitted,
            "allowed_alternative_was_not_committed": no_mutation,
            "all_rejections_side_effect_free": all(x["revision_unchanged"] and
                x["canonical_render_unchanged"] and x["bindings_and_structure_unchanged"] and
                x["execution_results_unchanged"] for x in results)}


def tool_schema(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties,
                           "required": required, "additionalProperties": False}}}


def agent_tools() -> list[dict[str, Any]]:
    obj, string, integer, number = {"type": "object"}, {"type": "string"}, {"type": "integer"}, {"type": "number"}
    return [
        tool_schema("inspect_structure", "Inspect the committed AGE_BY_ID function, arrays, nested control flow and current revision.", {}, []),
        tool_schema("discover_symbols", "Discover function, parameter, array, loop and assignment symbols with their live opaque IDs.", {}, []),
        tool_schema("inspect_statements", "List typed assignment statements, targets, indices, values, nesting paths and statement IDs.", {}, []),
        tool_schema("inspect_references", "Inspect references to a symbol discovered from discover_symbols.", {"symbol_id": string}, ["symbol_id"]),
        tool_schema("preview_age_edit", "Ask the mission gateway to preview changing one discovered assignment to a finite age in [0,130]. Preview does not commit.", {"statement_id": string, "new_age": number, "expected_revision": integer}, ["statement_id", "new_age", "expected_revision"]),
        tool_schema("commit_age_edit", "Commit a transaction returned by a successful preview; gateway rechecks revision, scope and full semantic delta.", {"transaction_id": string}, ["transaction_id"]),
        tool_schema("run_lookup_checks", "Run the host's fixed AGE_BY_ID oracle under both MIR engines; this does not mutate the program.", {}, []),
    ]


def projection_tree(function: Any, depth: int = 0, path: str = "") -> list[dict[str, Any]]:
    rows = []
    for index, node in enumerate(function.statements):
        here = f"{path}{index}"
        if isinstance(node, Assignment):
            rows.append({"kind": "array_assignment" if node.target_is_array else "assignment",
                         "statement_id": node.statement_id, "target_symbol_id": node.target_symbol_id,
                         "target_is_result": node.target_is_result,
                         "target_index": projection_expr(node.target_index),
                         "expression": projection_expr(node.expression), "nesting_path": here})
        elif isinstance(node, IfBlock):
            rows.extend(projection_tree(type("Block", (), {"statements": node.then_body})(), depth + 1, here + ".then."))
            rows.extend(projection_tree(type("Block", (), {"statements": node.else_body})(), depth + 1, here + ".else."))
        elif isinstance(node, ForLoop):
            rows.extend(projection_tree(type("Block", (), {"statements": node.body})(), depth + 1, here + ".body."))
    return rows


def projection_expr(expr: Any) -> Any:
    if expr is None:
        return None
    return {"kind": expr.kind, "value": expr.value,
            "children": [projection_expr(child) for child in expr.children]}


class AgentGatewayTools:
    def __init__(self, workspace: Workspace, document_id: str, aliases: dict[str, str],
                 gateway: MissionGateway, executor: MirExecutionService, trace: Trace):
        self.workspace, self.document_id, self.aliases, self.gateway = workspace, document_id, aliases, gateway
        self.executor = executor
        self.trace = trace
        self.reverse = {v: k for k, v in aliases.items()}

    def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        revision = self.workspace.get_revision(self.document_id)
        projection = build_projection(self.workspace, self.document_id, revision)
        function = next((x for x in projection.functions if x.symbol_id == self.aliases["age_by_id.function"]), None)
        if name == "inspect_structure":
            return {"revision": revision, "functions": [{"name": function.name, "symbol_id": function.symbol_id,
                    "parameters": list(function.parameter_ids), "arrays": [
                        {"name": a.name, "symbol_id": a.symbol_id, "upper_bound": a.upper_bound,
                         "element_type": a.element_type, "lifetime": "function invocation"} for a in function.arrays],
                    "statement_tree": projection_semantics(projection)["functions"][0]["statements"]}]}
        if name == "discover_symbols":
            result = {"revision": revision, "symbols": [
                {"handle": handle, "symbol_id": symbol_id}
                for handle, symbol_id in sorted(self.aliases.items())
                if handle in {"age_by_id.function", "age_by_id.parameter.wanted", "people.id", "people.age", "age_by_id.loop.i"}]}
            for item in result["symbols"]:
                self.trace.emit("symbol_discovered", phase="agent", actor="real_llm", revision=revision,
                                handle=item["handle"], symbol_id=item["symbol_id"],
                                observed_through="discover_symbols")
            return result
        if name == "inspect_statements":
            rows = projection_tree(function)
            for row in rows:
                self.trace.emit("agent_observation", phase="agent", actor="real_llm", revision=revision,
                                observation="typed_statement_discovered", statement_id=row["statement_id"],
                                statement_handle=self.reverse.get(row["statement_id"]),
                                target_handle=self.reverse.get(row["target_symbol_id"]),
                                statement=row)
            return {"revision": revision, "statements": rows}
        if name == "inspect_references":
            symbol_id = args["symbol_id"]
            if symbol_id not in set(self.aliases.values()):
                return {"ok": False, "code": "UNKNOWN_SEMANTIC_TARGET", "message": "Discover the symbol first."}
            refs = self.workspace.find_references(self.document_id, symbol_id)
            return {"revision": revision, "references": refs}
        if name == "preview_age_edit":
            return self.gateway.preview(args["statement_id"], args["new_age"], args["expected_revision"])
        if name == "commit_age_edit":
            return self.gateway.commit(args["transaction_id"])
        if name == "run_lookup_checks":
            expected = dict(EXPECTED)
            if self.gateway.committed:
                expected[205] = self.gateway.mission["functional_goal"]["new_age"]
            results = execute_values(self.workspace, self.document_id, self.aliases, revision)
            expected = {str(k): float(v) for k, v in expected.items()}
            return {"revision": revision, "results": results, "expected": expected,
                    "passed": all(values == expected for values in results.values())}
        return {"ok": False, "code": "UNKNOWN_TOOL", "message": "Tool is not available in this mission."}


def run_model_session(endpoint: ChatEndpoint, workspace: Workspace, document_id: str,
                      aliases: dict[str, str], gateway: MissionGateway, trace: Trace,
                      max_turns: int = 6, max_calls: int = 14) -> dict[str, Any]:
    tools = agent_tools()
    tool_surface_bytes = len(json.dumps(tools, separators=(",", ":"), ensure_ascii=False).encode())
    bridge = AgentGatewayTools(workspace, document_id, aliases, gateway, MirExecutionService(timeout=10), trace)
    revision = workspace.get_revision(document_id)
    messages: list[dict[str, Any]] = [{"role": "system", "content": (
        "You are editing one in-memory BASIC program through mission-scoped semantic tools. "
        "Discover the correct age assignment by logical entity ID, preview an edit to 47, "
        "commit only after an accepted preview, then validate. The target statement ID is not provided. "
        "Only these tools exist; do not claim success without a committed revision and validation.")},
        {"role": "user", "content": (
            "Mission: update the age of the person whose logical ID is 205 from 42 to 47. "
            "Do not modify entity IDs, other ages, function interfaces, control flow or unrelated statements. "
            f"Current document revision is {revision}. The gateway permits only a finite age literal in [0,130] "
            "for the authorized assignment. Use discovery tools; do not guess opaque IDs.")}]
    transcript: list[dict[str, Any]] = []
    total_calls = 0
    final_text = None
    status = "running"
    trace.emit("agent_session_started", phase="agent", actor="real_llm", model=endpoint.model,
               tool_schema_bytes=tool_surface_bytes, initial_revision=revision)
    for turn in range(max_turns):
        started = time.perf_counter()
        request_messages = copy.deepcopy(messages)
        trace.emit("model_request", phase="agent", actor="real_llm", turn=turn + 1,
                   model=endpoint.model, request_messages=request_messages,
                   tool_schema_bytes=tool_surface_bytes)
        try:
            response, elapsed = endpoint.complete(messages, tools)
        except Exception as exc:
            status = "endpoint_error"
            transcript.append({"turn": turn + 1, "error": str(exc), "elapsed_ms": endpoint.last_elapsed_ms,
                               "request_bytes": endpoint.last_request_bytes})
            trace.emit("model_request_failed", phase="agent", actor="real_llm", turn=turn + 1,
                       elapsed_ms=round(endpoint.last_elapsed_ms, 3), request_bytes=endpoint.last_request_bytes,
                       error=str(exc))
            break
        choices = response.get("choices", [])
        if not choices:
            status = "invalid_response"
            transcript.append({"turn": turn + 1, "error": "response has no choices", "response_bytes": endpoint.last_response_bytes})
            break
        message = choices[0].get("message", {})
        tool_calls = message.get("tool_calls") or []
        usage = response.get("usage", {})
        turn_record = {"turn": turn + 1, "request_bytes": endpoint.last_request_bytes,
                       "response_bytes": endpoint.last_response_bytes, "elapsed_ms": round(elapsed, 3),
                       "usage": usage, "request_messages": request_messages,
                       "assistant_content": message.get("content"), "tool_calls": []}
        trace.emit("model_response", phase="agent", actor="real_llm", turn=turn + 1,
                   elapsed_ms=round(elapsed, 3), request_bytes=endpoint.last_request_bytes,
                   response_bytes=endpoint.last_response_bytes, usage=usage,
                   selected_tool_count=len(tool_calls), assistant_content=message.get("content"))
        if not tool_calls:
            final_text = message.get("content") or ""
            turn_record["final_answer"] = final_text
            transcript.append(turn_record)
            trace.emit("model_final_answer", phase="agent", actor="real_llm", turn=turn + 1,
                       answer=final_text, usage=usage)
            status = "completed"
            break
        messages.append(message)
        for call in tool_calls:
            total_calls += 1
            if total_calls > max_calls:
                status = "tool_call_limit"
                break
            function_row = call.get("function", {})
            name = function_row.get("name", "")
            raw_args = function_row.get("arguments", "{}")
            args: dict[str, Any] = {}
            tool_started = time.perf_counter()
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                trace.emit("model_tool_call", phase="agent", actor="real_llm", turn=turn + 1,
                           tool_call_id=call.get("id"), tool=name, arguments=args,
                           target_handle=bridge.reverse.get(args.get("statement_id")) if isinstance(args, dict) else None)
                result = bridge.dispatch(name, args)
            except Exception as exc:
                result = {"ok": False, "code": "TOOL_ERROR", "message": str(exc)}
            response_text = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
            tool_elapsed_ms = (time.perf_counter() - tool_started) * 1000
            turn_record["tool_calls"].append({"id": call.get("id"), "name": name, "arguments": args,
                                              "result": result, "response_bytes": len(response_text.encode()),
                                              "tool_elapsed_ms": round(tool_elapsed_ms, 4)})
            trace.emit("tool_result", phase="agent", actor="mission_gateway", turn=turn + 1,
                       tool_call_id=call.get("id"), tool=name, result=result,
                       response_bytes=len(response_text.encode()), tool_elapsed_ms=round(tool_elapsed_ms, 4))
            messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": response_text})
        transcript.append(turn_record)
        if status == "tool_call_limit":
            break
    if status == "running":
        status = "turn_limit"
    final = {"status": status, "model": endpoint.model,
             "endpoint_metadata": endpoint_metadata(endpoint.endpoint),
             "request_configuration": {"temperature": endpoint.temperature,
                 "max_output_tokens": endpoint.max_output_tokens, "timeout_seconds": endpoint.timeout,
                 "seed": endpoint.seed, "think": endpoint.think},
             "turns": len(transcript),
             "tool_calls": total_calls, "tool_schema_bytes": tool_surface_bytes,
             "request_bytes": sum(x.get("request_bytes", 0) for x in transcript),
             "response_bytes": sum(x.get("response_bytes", 0) for x in transcript),
             "inference_ms": round(sum(x.get("elapsed_ms", 0) for x in transcript), 3),
             "prompt_tokens": sum(x.get("usage", {}).get("prompt_tokens", 0) for x in transcript),
             "completion_tokens": sum(x.get("usage", {}).get("completion_tokens", 0) for x in transcript),
             "cached_prompt_tokens": sum(x.get("usage", {}).get("prompt_tokens_details", {}).get("cached_tokens", 0)
                                          for x in transcript),
             "final_answer": final_text}
    (OUT / "agent-session.json").write_text(json.dumps({"metadata": final, "transcript": transcript},
                                                       indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT / "agent-tool-schemas.json").write_text(json.dumps(tools, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    trace.emit("host_correctness_judgment", phase="agent", actor="host",
               model_status=status, committed=gateway.committed,
               revision=workspace.get_revision(document_id), final_answer_present=bool(final_text))
    return final


def make_mission() -> dict[str, Any]:
    return {"schema": "basic-workspace.mission-contract", "version": 1, "mission_id": MISSION_ID,
            "objective": "Update the age of the person whose logical ID is 205 from 42 to 47, without modifying entity IDs, other ages, function interfaces, control flow or unrelated statements.",
            "base_document_revision": 1, "execution_profile": PROFILE_ID,
            "enforcement": {"allowed_operations": ["edit_assignment_expression"],
                "allowed_target_handle": "people.age.205", "numeric_literal_range": {"minimum": 0, "maximum": 130},
                "target_resolution": "Resolve the unique logical ID 205 in PERSON_ID initial assignments, then authorize the corresponding PERSON_AGE slot; never equate entity ID with array index.",
                "candidate_invariants": ["all declarations and signatures unchanged", "all bindings unchanged",
                    "all control flow and statement ordering unchanged", "exactly one selected assignment RHS changes"],
                "commit_checks": ["mission id", "execution profile", "expected current revision", "discovered target identity",
                    "range check", "candidate projection semantic diff", "same checks repeated immediately before atomic commit"],
                "forbidden_operations": ["rename_symbol", "edit any other assignment", "edit condition or loop bounds", "arbitrary source replacement"]},
            "functional_goal": {"logical_id": 205, "old_age": 42, "new_age": 47},
            "required_invariants": ["PERSON_ID unchanged", "ages for 101 and 900 unchanged", "function signature and nested control flow unchanged"],
            "required_post_edit_validations": [{"engine": e, "function_handle": "age_by_id.function", "arguments": [205], "expected": 47.0} for e in ("interp", "jit")],
            "advisory_preferences": ["Use the smallest semantic edit."],
            "human_approval": {"required_for": [], "approval_token_supported": False},
            "trust_boundary": "Enforced only through the tools exposed by this campaign gateway; unrestricted Workspace, process, shell, filesystem or direct model access is outside this boundary."}


def make_profile() -> dict[str, Any]:
    source = ROOT / "results" / "semantic-replay" / "execution-profile.json"
    profile = json.loads(source.read_text(encoding="utf-8"))
    profile["profile_id"] = PROFILE_ID
    profile["name"] = "BASIC Workspace numeric arrays and bounded control v1"
    profile["campaign_requirements"] = {"function": "AGE_BY_ID(WANTED)", "expected_before": EXPECTED,
                                         "expected_after": {**EXPECTED, 205: 47.0}}
    return profile


def make_stream(seed: dict[str, Any], aliases: dict[str, str], committed_age: float | None) -> dict[str, Any]:
    ops = [{"operation": "create_numeric_function", "portable_handle": "age_by_id.function",
            "arguments": seed_operation()}]
    if committed_age is not None:
        ops.append({"operation": "edit_assignment_expression", "target_handle": "people.age.205",
                    "expression": n(committed_age)})
    return {"schema": METAFILE_SCHEMA, "version": 1, "execution_profile": PROFILE_ID,
            "document_identity": "age-by-id-lookup", "handles": [
                {"handle": h, "kind": h.split(".")[-2] if "." in h else "entity"}
                for h in sorted(aliases)],
            "operations": ops,
            "provenance": "Seed constructor plus only successful committed semantic edits; rejected proposals remain only in history.jsonl."}


def replay_stream(stream: dict[str, Any], mission: dict[str, Any], trace: Trace) -> tuple[Workspace, str, dict[str, str], dict[str, Any]]:
    if stream.get("execution_profile") != PROFILE_ID:
        raise WorkspaceError("EXECUTION_PROFILE_MISMATCH", "Metafile requires another execution profile")
    ws = Workspace()
    trace.emit("replay_started", phase="replay", workspace="fresh",
               declared_handle_count=len(stream["handles"]))
    doc, aliases, seed = create_seed(ws, trace, "replay")
    for operation in stream["operations"][1:]:
        handle = operation["target_handle"]
        if handle not in aliases:
            raise WorkspaceError("REPLAY_HANDLE_MISSING", f"Metafile target {handle} did not remap")
        gateway = MissionGateway(ws, doc, aliases, seed["projection"], mission, trace, "replay")
        preview = gateway.preview(aliases[handle], operation["expression"]["value"], ws.get_revision(doc))
        if not preview.get("ok"):
            raise WorkspaceError(preview["code"], preview["message"])
        commit = gateway.commit(preview["transaction_id"])
        if not commit.get("committed"):
            raise WorkspaceError(commit["code"], commit["message"])
    return ws, doc, aliases, seed


def safe_endpoint_summary(endpoint: str) -> dict[str, str]:
    return endpoint_metadata(endpoint)


def run_campaign(args: argparse.Namespace) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    trace = Trace()
    mission = make_mission()
    profile = make_profile()
    (OUT / "mission.json").write_text(json.dumps(mission, indent=2) + "\n", encoding="utf-8")
    (OUT / "execution-profile.json").write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    trace.emit("session_started", campaign_kind="real_llm" if not args.deterministic_only else "scripted",
               campaign="AGE_BY_ID semantic mission", mission_id=MISSION_ID, execution_profile=PROFILE_ID,
               objective=mission["objective"], scripted_seed=True)
    ws = Workspace()
    build_start = time.perf_counter()
    document_id, aliases, seed = create_seed(ws, trace)
    build_ms = (time.perf_counter() - build_start) * 1000
    revision = ws.get_revision(document_id)
    before = execute_values(ws, document_id, aliases, revision)
    trace.emit("program_executed", phase="original", actor="host", revision=revision,
               engine_results=before, expected={str(k): v for k, v in EXPECTED.items()},
               passed=all(before[e] == {str(k): v for k, v in EXPECTED.items()} for e in before))
    if not all(before[e] == {str(k): v for k, v in EXPECTED.items()} for e in before):
        raise RuntimeError("Initial MIR interpreter/JIT results did not match the independent oracle")
    gateway = MissionGateway(ws, document_id, aliases, seed["projection"], mission, trace, "agent")
    if args.deterministic_only:
        model_result = {"status": "not_run", "reason": "--deterministic-only"}
    elif not args.endpoint or not args.model:
        model_result = {"status": "not_run", "reason": "No endpoint/model configured"}
    else:
        endpoint = ChatEndpoint(args.endpoint, args.model, args.api_key, 0.0, 800, args.timeout, 17, think=False)
        model_result = run_model_session(endpoint, ws, document_id, aliases, gateway, trace)
        model_result["endpoint_metadata"] = safe_endpoint_summary(args.endpoint)
    committed = gateway.committed
    current_revision = ws.get_revision(document_id)
    after = execute_values(ws, document_id, aliases, current_revision)
    expected_after = dict(EXPECTED)
    if committed:
        expected_after[205] = 47.0
    after_expected = {str(k): float(v) for k, v in expected_after.items()}
    behavior_ok = all(after[engine] == after_expected for engine in after)
    mission_goal_passed = committed and behavior_ok
    trace.emit("program_executed", phase="original", actor="host", revision=current_revision,
               engine_results=after, expected=after_expected, passed=behavior_ok,
               validation_kind="post_agent_mission")
    negative_started = time.perf_counter()
    controls = run_negative_controls(mission, trace)
    negative_ms = (time.perf_counter() - negative_started) * 1000
    committed_age = gateway.pending[next(iter(gateway.pending))]["new_age"] if committed else None
    stream = make_stream(seed, aliases, committed_age)
    (OUT / "constructive-operations.json").write_text(json.dumps(stream, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    replay_started = time.perf_counter()
    replay_ws, replay_doc, replay_aliases, replay_seed = replay_stream(stream, mission, trace)
    replay_rev = replay_ws.get_revision(replay_doc)
    original_snapshot = semantic_snapshot(ws, document_id, aliases)
    replay_snapshot = semantic_snapshot(replay_ws, replay_doc, replay_aliases)
    replay_outputs = execute_values(replay_ws, replay_doc, replay_aliases, replay_rev)
    replay_ms = (time.perf_counter() - replay_started) * 1000
    structural = original_snapshot == replay_snapshot
    binding = binding_edges(original_snapshot) == binding_edges(replay_snapshot)
    behavioral = replay_outputs == after
    trace.emit("program_executed", phase="replay", actor="host", revision=replay_rev,
               engine_results=replay_outputs, expected=after_expected,
               passed=replay_outputs == after_expected)
    trace.emit("replay_completed" if structural and binding and behavioral else "replay_failed",
               phase="replay", structural_equivalence=structural, binding_equivalence=binding,
               behavioral_equivalence=behavioral, interpreter_jit_agreement=all(x == replay_outputs["interp"] for x in replay_outputs.values()),
               original_revision=current_revision, replay_revision=replay_rev,
               identifier_remapping_count=len(aliases), replay_outputs=replay_outputs)
    if not structural or not binding or not behavioral:
        trace.emit("replay_failed", phase="replay", error="semantic or behavioral equivalence mismatch")
    campaign_kind = "scripted" if args.deterministic_only else "real_llm" if args.endpoint and args.model else "not_run"
    final_ok = (structural and binding and behavioral and controls["all_rejections_side_effect_free"] and
                (args.deterministic_only or mission_goal_passed))
    trace.emit("session_completed", campaign_kind=campaign_kind,
               status="passed" if final_ok else "failed",
               final_revision=current_revision, replay_revision=replay_rev)
    trace.write(OUT / "history.jsonl")
    (OUT / "controls.json").write_text(json.dumps(controls, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    equivalence = {"schema": "basic-workspace.semantic-equivalence", "version": 1,
        "structural_equivalence": structural, "binding_equivalence": binding,
        "behavioral_equivalence": behavioral,
        "execution_engine_agreement": all(x == replay_outputs["interp"] for x in replay_outputs.values()),
        "original_revision": current_revision, "replay_revision": replay_rev,
        "identifier_remapping_count": len(aliases), "original_outputs": after, "replay_outputs": replay_outputs,
        "expected_outputs": after_expected,
        "remapping": {"original_aliases": sorted(aliases), "replay_aliases": sorted(replay_aliases),
                      "opaque_ids_reused": False}}
    (OUT / "equivalence.json").write_text(json.dumps(equivalence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    total_ms = (time.perf_counter() - started) * 1000
    summary = {"schema": "basic-workspace.semantic-campaign-summary", "version": 1,
        "campaign_kind": campaign_kind,
        "mission_id": MISSION_ID, "execution_profile": PROFILE_ID,
        "final_status": "passed" if final_ok else "failed",
        "proposed_operations": sum(1 for e in trace.events if e["event"] == "operation_proposed"),
        "accepted_previews": sum(1 for e in trace.events if e["event"] == "preview_accepted"),
        "rejected_operations": sum(1 for e in trace.events if e["event"] == "transaction_rejected"),
        "committed_operations": sum(1 for e in trace.events if e["event"] == "transaction_committed" and e.get("phase") in ("agent", "replay")),
        "committed_revision": current_revision, "functions_affected": ["AGE_BY_ID"],
        "arrays_affected": ["PERSON_AGE"] if committed else [], "expected_results": after_expected,
        "observed_results": after, "replay_correct": structural and binding and behavioral,
        "mission_goal_passed": mission_goal_passed,
        "policy_violations": controls["cases"], "model": model_result,
        "total_wall_ms": round(total_ms, 3), "artifacts": ["history.jsonl", "constructive-operations.json", "equivalence.json", "replay.html", "overview.svg"]}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    metrics = {"schema": "basic-workspace.semantic-replay-metrics", "version": 1,
        "construction_ms": round(build_ms, 4), "negative_controls_ms": round(negative_ms, 4),
        "replay_and_equivalence_ms": round(replay_ms, 4),
        "constructive_stream_bytes": (OUT / "constructive-operations.json").stat().st_size,
        "historical_journal_bytes": (OUT / "history.jsonl").stat().st_size,
        "portable_handle_count": len(aliases), "identifier_remappings": len(aliases),
        "model": model_result, "total_wall_ms": round(total_ms, 4)}
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    import subprocess
    renderer = Path(__file__).with_name("render-semantic-replay.py")
    subprocess.run([sys.executable, str(renderer), "--trace", str(OUT / "history.jsonl"), "--output-dir", str(OUT)], check=True)
    report = f'''# AGE_BY_ID semantic replay campaign

Campaign kind: **{summary['campaign_kind']}**. Final status: **{summary['final_status']}**.

The initial program was constructed from typed operations in an empty workspace. The model was only given the mission and constrained tools; the host verified the logical-ID-to-slot map from typed initializers. No historical BASIC FUNCTION/IF runner was used as an oracle because of its known defect.

## Results

- MIR interpreter and JIT before edit: {json.dumps(before, sort_keys=True)}
- MIR interpreter and JIT after edit: {json.dumps(after, sort_keys=True)}
- Fresh-workspace replay: structural={structural}, bindings={binding}, behavior={behavioral}; {len(aliases)} portable handles remapped.
- Scripted policy controls: {len(controls['cases'])} rejected without mutation; valid age 48 was preview-authorized without commit.
- Model status: `{model_result.get('status')}`; turns={model_result.get('turns','unknown')}, tool calls={model_result.get('tool_calls','unknown')}, prompt tokens={model_result.get('prompt_tokens','unknown')}, cached prompt tokens={model_result.get('cached_prompt_tokens','unknown')}.

## Reproduction

`python3 scripts/age-by-id-campaign.py --deterministic-only`

For the bounded real-model trial, configure `BASIC_WORKSPACE_LLM_ENDPOINT` and `BASIC_WORKSPACE_LLM_MODEL` in the environment, then run `python3 scripts/age-by-id-campaign.py`. The report stores only endpoint class metadata, not the endpoint URL or credentials.

## Trust boundary and limitations

Mission checks apply only to the tool gateway used by this run. They do not constrain unrestricted Workspace APIs or shell access. The semantic policy authorizes a numeric literal in [0,130] independently of the mission goal value 47; task correctness is checked separately. The replay stream stores only the constructor and successful committed edit; rejected attempts remain in the history. Agent claims are not hidden reasoning or independently verified rationale. This is one scenario and not a general policy or replay guarantee.
'''
    (OUT / "REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["final_status"] == "passed" else 1


def main() -> None:
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deterministic-only", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=OUT)
    parser.add_argument("--endpoint", default=os.environ.get("BASIC_WORKSPACE_LLM_ENDPOINT"))
    parser.add_argument("--model", default=os.environ.get("BASIC_WORKSPACE_LLM_MODEL"))
    parser.add_argument("--api-key", default=os.environ.get("BASIC_WORKSPACE_LLM_API_KEY"))
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    OUT = args.output_dir.resolve()
    raise SystemExit(run_campaign(args))


if __name__ == "__main__":
    main()
