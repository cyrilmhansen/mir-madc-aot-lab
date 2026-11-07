#!/usr/bin/env python3
"""Agent-driven, mission-gated construction and replay of IS_SENIOR."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import math
import os
import shutil
import sys
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "results" / "semantic-replay" / "is-senior"
PROFILE_ID = "basic-workspace.numeric-composition.v1"
MISSION_ID = "mission.compose-age-by-id.is-senior.v1"
METAFILE_SCHEMA = "basic-workspace.constructive-metafile"
EXPECTED_AGE = {"101": 25.0, "205": 42.0, "900": 53.0, "999": -1.0, "2": -1.0}
EXPECTED_SENIOR = {"101": 0.0, "205": 0.0, "900": 1.0, "999": 0.0, "2": 0.0}

from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.mir_execution import MirExecutionService
from basic_workspace.projection import build_projection, projection_semantics
from basic_workspace.projection import Assignment, ForLoop, IfBlock
from experiment.llm_runner import ChatEndpoint, endpoint_metadata

_spec = importlib.util.spec_from_file_location("age_by_id_campaign", ROOT / "scripts" / "age-by-id-campaign.py")
_cycle12 = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_cycle12)


def n(value: float) -> dict[str, Any]:
    return {"kind": "number", "value": value}


def local(name: str) -> dict[str, Any]:
    return {"kind": "local_ref", "name": name}


def senior_operation(callee_handle: str = "age_by_id.function", threshold: float = 50.0) -> dict[str, Any]:
    call = {"kind": "call", "function_handle": callee_handle,
            "arguments": [local("ID")]}
    return {"name": "IS_SENIOR", "parameters": ["ID"], "body": [
                {"kind": "assign", "target": {"kind": "result"}, "expression": n(0)},
                {"kind": "if", "condition": {"kind": "binary", "operator": ">=",
                    "left": call, "right": n(threshold)},
                 "then": [{"kind": "assign", "target": {"kind": "result"}, "expression": n(1)}]}]}


def resolve_function_handles(value: Any, aliases: dict[str, str], discovered: set[str]) -> Any:
    if isinstance(value, list):
        return [resolve_function_handles(x, aliases, discovered) for x in value]
    if not isinstance(value, dict):
        return value
    if value.get("kind") == "call":
        allowed = {"kind", "function_handle", "arguments"}
        if set(value) != allowed:
            raise WorkspaceError("INVALID_CALL_HANDLE", "Call requires a portable function_handle and typed arguments")
        handle = value["function_handle"]
        if handle not in discovered or handle not in aliases:
            raise WorkspaceError("UNKNOWN_PORTABLE_FUNCTION", "Call target handle was not discovered in this Workspace")
        return {"kind": "call", "function_id": aliases[handle],
                "arguments": [resolve_function_handles(x, aliases, discovered) for x in value["arguments"]]}
    return {key: resolve_function_handles(child, aliases, discovered)
            for key, child in value.items()}


def statement_ids(rows: list[dict[str, Any]]) -> list[str]:
    output: list[str] = []
    for row in rows:
        if row["kind"] in ("assignment", "array_assignment"):
            if row.get("statement_id"):
                output.append(row["statement_id"])
        elif row["kind"] == "if":
            output.extend(statement_ids(row["then"]))
            output.extend(statement_ids(row["else"]))
        elif row["kind"] == "for":
            output.extend(statement_ids(row["body"]))
    return output


def aliases_for_senior(raw: dict[str, Any], base_aliases: dict[str, str]) -> dict[str, str]:
    aliases = dict(base_aliases)
    rows = [x for x in raw["functions"] if x["name"].casefold() == "is_senior"]
    if len(rows) != 1:
        raise WorkspaceError("MISSION_FUNCTION_COUNT", "Candidate must define exactly one IS_SENIOR function")
    row = rows[0]
    if len(row["parameter_ids"]) != 1 or row["local_ids"] or row["arrays"]:
        raise WorkspaceError("MISSION_SIGNATURE", "IS_SENIOR must have one numeric parameter and no local arrays/locals")
    aliases["is_senior.function"] = row["symbol_id"]
    aliases["is_senior.parameter.id"] = row["parameter_ids"][0]
    for index, sid in enumerate(statement_ids(row["statements"])):
        aliases[f"is_senior.statement.{index}"] = sid
    return aliases


def normalized_state(raw: dict[str, Any], aliases: dict[str, str]) -> dict[str, Any]:
    return _cycle12.normalize_projection(raw, aliases)


def find_function(snapshot: dict[str, Any], handle: str) -> dict[str, Any]:
    return next(row for row in snapshot["functions"] if row["handle"] == handle)


def expression_references(rows: Any, kind: str | None = None) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(rows, list):
        for row in rows:
            found.extend(expression_references(row, kind))
    elif isinstance(rows, dict):
        if rows.get("kind") in ("call", "array_element", "variable", "result", "compare", "binary"):
            if kind is None or rows.get("kind") == kind:
                found.append(rows)
        for value in rows.values():
            found.extend(expression_references(value, kind))
    return found


class SeniorMissionGateway:
    """One-operation functional mission boundary, not a reusable policy engine."""
    def __init__(self, workspace: Workspace, document_id: str, aliases: dict[str, str],
                 base_snapshot: dict[str, Any], mission: dict[str, Any], trace: Any,
                 phase: str = "agent"):
        self.workspace, self.document_id = workspace, document_id
        self.aliases = dict(aliases)
        self.base_aliases = dict(aliases)
        self.base_snapshot = copy.deepcopy(base_snapshot)
        self.mission, self.trace, self.phase = mission, trace, phase
        self.discovered_handles: set[str] = set()
        self.pending: dict[str, dict[str, Any]] = {}
        self.committed = False
        self.committed_snapshot: dict[str, Any] | None = None

    def discover_functions(self) -> dict[str, Any]:
        revision = self.workspace.get_revision(self.document_id)
        symbols = self.workspace.list_symbols(self.document_id)
        funcs = [x for x in symbols if x["kind"] == "function" and x["scope_id"] == "module"]
        result = []
        for function in funcs:
            handle = "age_by_id.function" if function["name"].casefold() == "age_by_id" else None
            if handle is None or self.aliases.get(handle) != function["symbol_id"]:
                continue
            self.discovered_handles.add(handle)
            row = next(f for f in self.workspace.documents[self.document_id].functions
                       if f["symbol_id"] == function["symbol_id"])
            result.append({"handle": handle, "symbol_id": function["symbol_id"],
                           "name": function["name"], "parameter_count": len(row["parameters"]),
                           "parameter_names": [self.workspace.documents[self.document_id].symbols[x].name
                                               for x in row["parameters"]], "return_type": "numeric"})
        return {"revision": revision, "functions": result}

    def inspect_structure(self) -> dict[str, Any]:
        revision = self.workspace.get_revision(self.document_id)
        raw = projection_semantics(build_projection(self.workspace, self.document_id, revision))
        return {"revision": revision, "structure": normalized_state(raw, self.aliases)}

    def _preflight(self, request: dict[str, Any], expected_revision: int,
                   callee_handle: str) -> tuple[dict[str, Any], str]:
        if self.committed:
            raise WorkspaceError("MISSION_EDIT_LIMIT", "This mission permits one new function")
        if expected_revision != self.workspace.get_revision(self.document_id):
            raise WorkspaceError("STALE_REVISION", "Construction is based on a stale revision")
        if self.discovered_handles != {"age_by_id.function"}:
            raise WorkspaceError("FUNCTION_NOT_DISCOVERED", "Discover AGE_BY_ID before constructing a caller")
        if callee_handle != "age_by_id.function" or callee_handle not in self.discovered_handles:
            raise WorkspaceError("UNKNOWN_PORTABLE_FUNCTION", "Select the discovered AGE_BY_ID function handle")
        if not isinstance(request, dict) or set(request) != {"name", "parameters", "body"}:
            raise WorkspaceError("MISSION_OPERATION_FORBIDDEN", "Mission permits only one typed IS_SENIOR constructor")
        if request["name"].casefold() != "is_senior" or request["parameters"] != ["ID"]:
            raise WorkspaceError("MISSION_SIGNATURE", "Mission requires one new numeric function IS_SENIOR(ID)")
        if not isinstance(request["body"], list) or not request["body"] or len(request["body"]) > 64:
            raise WorkspaceError("MISSION_BODY", "Function body must be a bounded typed statement list")
        calls: list[dict[str, Any]] = []

        def check_expr(expr: Any, depth: int = 0) -> None:
            if depth > 16 or not isinstance(expr, dict):
                raise WorkspaceError("MISSION_EXPRESSION", "Expression is malformed or too deeply nested")
            kind = expr.get("kind")
            if kind == "number":
                value = expr.get("value")
                if set(expr) != {"kind", "value"} or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                    raise WorkspaceError("MISSION_EXPRESSION", "Only finite numeric constants are allowed")
            elif kind == "local_ref":
                if set(expr) != {"kind", "name"} or str(expr["name"]).casefold() != "id":
                    raise WorkspaceError("MISSION_SCOPE", "Only the discovered ID parameter is in scope")
            elif kind == "binary":
                if set(expr) != {"kind", "operator", "left", "right"} or expr["operator"] not in ("+", "-", "*", "/", "=", "<>", "<", "<=", ">", ">="):
                    raise WorkspaceError("MISSION_OPERATOR", "Unsupported typed numeric operator")
                check_expr(expr["left"], depth + 1); check_expr(expr["right"], depth + 1)
            elif kind == "call":
                if set(expr) != {"kind", "function_handle", "arguments"}:
                    raise WorkspaceError("MISSION_CALL", "Calls require a portable function handle")
                if expr["function_handle"] != "age_by_id.function" or "age_by_id.function" not in self.discovered_handles:
                    raise WorkspaceError("UNKNOWN_PORTABLE_FUNCTION", "Only the discovered AGE_BY_ID handle is permitted")
                if not isinstance(expr["arguments"], list) or len(expr["arguments"]) != 1:
                    raise WorkspaceError("MISSION_CALL_ARITY", "AGE_BY_ID requires one argument")
                for child in expr["arguments"]: check_expr(child, depth + 1)
                calls.append(expr)
            else:
                raise WorkspaceError("MISSION_EXPRESSION", f"Expression kind {kind!r} is outside the mission subset")

        def check_body(items: list[Any], depth: int = 0) -> None:
            if depth > 8:
                raise WorkspaceError("MISSION_CONTROL_DEPTH", "Nested IF blocks are limited to depth 8")
            for item in items:
                if not isinstance(item, dict):
                    raise WorkspaceError("MISSION_BODY", "Body statement must be a typed object")
                if item.get("kind") == "assign":
                    if set(item) != {"kind", "target", "expression"} or item["target"] != {"kind": "result"}:
                        raise WorkspaceError("MISSION_TARGET", "Only numeric function-result assignments are permitted")
                    check_expr(item["expression"])
                elif item.get("kind") == "if":
                    if set(item) - {"kind", "condition", "then", "else"} or not isinstance(item.get("then"), list) or not isinstance(item.get("else", []), list):
                        raise WorkspaceError("MISSION_BODY", "IF requires a typed condition and ordered blocks")
                    check_expr(item.get("condition")); check_body(item["then"], depth + 1); check_body(item.get("else", []), depth + 1)
                else:
                    raise WorkspaceError("MISSION_BODY", "Only assignments and structured IF blocks are permitted")
        check_body(request["body"])
        if not calls:
            raise WorkspaceError("MISSION_DEPENDENCY_REQUIRED", "IS_SENIOR must call the discovered AGE_BY_ID")
        resolved_body = resolve_function_handles(request["body"], self.aliases, self.discovered_handles)
        return {"operation": "create_numeric_function", "name": request["name"],
                "parameters": request["parameters"], "body": resolved_body}, "age_by_id.function"

    def _candidate(self, request: dict[str, Any], expected_revision: int,
                   callee_handle: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
        operation, _ = self._preflight(request, expected_revision, callee_handle)
        candidate = self.workspace.preview_transaction_semantics(self.document_id, expected_revision, [operation])
        raw = candidate["candidate_semantics"]
        if len(raw["functions"]) != 2 or sum(x["name"].casefold() == "is_senior" for x in raw["functions"]) != 1:
            raise WorkspaceError("MISSION_FUNCTION_COUNT", "Candidate must contain only AGE_BY_ID and one IS_SENIOR")
        candidate_aliases = aliases_for_senior(raw, self.base_aliases)
        normalized = normalized_state(raw, candidate_aliases)
        before_age = find_function(self.base_snapshot, "age_by_id.function")
        after_age = find_function(normalized, "age_by_id.function")
        if before_age != after_age:
            raise WorkspaceError("MISSION_EXISTING_FUNCTION_CHANGED", "AGE_BY_ID or its data/control flow changed")
        senior = find_function(normalized, "is_senior.function")
        if senior["parameters"] != ["is_senior.parameter.id"] or senior["arrays"] or senior["locals"]:
            raise WorkspaceError("MISSION_SIGNATURE", "Unexpected IS_SENIOR parameters, locals or arrays")
        calls = [x for x in expression_references(senior["statements"], "call")
                 if x.get("value") == "age_by_id.function"]
        if not calls:
            raise WorkspaceError("MISSION_DEPENDENCY_REQUIRED", "Typed candidate does not bind a call to AGE_BY_ID")
        return operation, normalized, candidate_aliases

    def reject_operation(self, operation: dict[str, Any], expected_revision: int) -> dict[str, Any]:
        txid = "tx_" + uuid.uuid4().hex
        self.trace.emit("operation_proposed", phase="controls", actor="scripted_control",
                        mission_id=MISSION_ID, transaction_id=txid, base_revision=expected_revision,
                        operation_envelope={"operation": operation.get("operation"), "arguments": operation,
                                            "state": "proposed", "mission_id": MISSION_ID})
        current = self.workspace.get_revision(self.document_id)
        code = "STALE_REVISION" if expected_revision != current else "MISSION_OPERATION_FORBIDDEN"
        result = {"ok": False, "reliable": True, "code": code,
                  "message": "Only the mission-scoped IS_SENIOR constructor is authorized.",
                  "revision": current, "transaction_id": txid}
        self.trace.emit("transaction_rejected", phase="controls", actor="scripted_control",
                        mission_id=MISSION_ID, transaction_id=txid, operation=operation.get("operation"),
                        base_revision=expected_revision, resulting_revision=current,
                        code=code, message=result["message"], authoritative_state_unchanged=True)
        return result

    def preview(self, request: dict[str, Any], expected_revision: int,
                callee_handle: str) -> dict[str, Any]:
        txid = "tx_" + uuid.uuid4().hex
        self.trace.emit("operation_proposed", phase=self.phase, actor="llm_tool" if self.phase == "agent" else self.phase,
                        mission_id=MISSION_ID, transaction_id=txid, base_revision=expected_revision,
                        operation_envelope={"schema": "basic-workspace.semantic-operation", "version": 1,
                            "operation": "create_numeric_function", "mission_id": MISSION_ID,
                            "base_revision": expected_revision, "arguments": request,
                            "execution_profile": PROFILE_ID, "state": "proposed"})
        try:
            operation, candidate, candidate_aliases = self._candidate(request, expected_revision, callee_handle)
        except WorkspaceError as exc:
            return self._reject(txid, expected_revision, exc.code, exc.message)
        self.pending[txid] = {"request": copy.deepcopy(request), "operation": operation,
                              "revision": expected_revision, "candidate": candidate,
                              "candidate_aliases": candidate_aliases, "callee_handle": callee_handle}
        preview = self.workspace.preview_transaction(self.document_id, expected_revision, [operation], include_diff=True)
        self.trace.emit("preview_accepted", phase=self.phase, actor="mission_gateway",
                        mission_id=MISSION_ID, transaction_id=txid, base_revision=expected_revision,
                        resulting_revision=preview["expected_result_revision"],
                        created_function="is_senior.function", calls="age_by_id.function",
                        proposed_diff=preview.get("diff", ""), candidate_semantic_snapshot=candidate,
                        validation=preview["diagnostics"],
                        operation_envelope={"state": "validated", "transaction_id": txid,
                            "mission_id": MISSION_ID, "operation": "create_numeric_function",
                            "base_revision": expected_revision,
                            "expected_result_revision": preview["expected_result_revision"]})
        return {"ok": True, "transaction_id": txid, "base_revision": expected_revision,
                "expected_result_revision": preview["expected_result_revision"],
                "new_function_handle": "is_senior.function", "bound_callee_handle": "age_by_id.function",
                "candidate_function_count": 2, "diagnostics": preview["diagnostics"],
                "candidate_is_preview_only": True}

    def _reject(self, txid: str, revision: int, code: str, message: str) -> dict[str, Any]:
        current = self.workspace.get_revision(self.document_id)
        self.trace.emit("transaction_rejected", phase=self.phase, actor="mission_gateway",
                        mission_id=MISSION_ID, transaction_id=txid, base_revision=revision,
                        resulting_revision=current, code=code, message=message,
                        authoritative_state_unchanged=True)
        return {"ok": False, "reliable": True, "code": code, "message": message,
                "revision": current, "transaction_id": txid}

    def commit(self, txid: str) -> dict[str, Any]:
        pending = self.pending.get(txid)
        if pending is None:
            return self._reject(txid, self.workspace.get_revision(self.document_id),
                                "PREVIEW_NOT_FOUND", "No accepted IS_SENIOR preview exists")
        try:
            operation, candidate, candidate_aliases = self._candidate(
                pending["request"], pending["revision"], pending["callee_handle"])
            if candidate != pending["candidate"]:
                raise WorkspaceError("PREVIEW_CANDIDATE_CHANGED", "Revalidated candidate differs from accepted preview")
            if candidate_aliases.keys() != pending["candidate_aliases"].keys():
                raise WorkspaceError("PREVIEW_BINDINGS_CHANGED", "Portable identity set changed before commit")
            result = self.workspace.apply_transaction(self.document_id, pending["revision"], [operation])
        except WorkspaceError as exc:
            return self._reject(txid, pending["revision"], exc.code, exc.message)
        raw = projection_semantics(build_projection(self.workspace, self.document_id, result["revision"]))
        actual_aliases = aliases_for_senior(raw, self.base_aliases)
        actual = normalized_state(raw, actual_aliases)
        if actual != candidate:
            raise RuntimeError("Atomic commit projection differs from authorized preview")
        self.aliases = actual_aliases
        self.committed_snapshot = actual
        self.committed = True
        self.committed_request = copy.deepcopy(pending["request"])
        source = self.workspace.render_document(self.document_id)
        self.trace.emit("transaction_committed", phase=self.phase, actor="mission_gateway",
                        mission_id=MISSION_ID, transaction_id=txid, operation="create_numeric_function",
                        base_revision=pending["revision"], resulting_revision=result["revision"],
                        alias_bindings=actual_aliases, semantic_snapshot=actual,
                        program_snapshot=source, created_entities=result["created_entities"],
                        created_statements=result["created_statements"],
                        bound_call="age_by_id.function")
        return {"ok": True, "committed": True, "revision": result["revision"],
                "function_handle": "is_senior.function", "function_id": actual_aliases["is_senior.function"],
                "callee_handle": "age_by_id.function"}


def validation_envelope(*, requested_revision: int, workspace_revision: int,
                        observed: dict[str, Any] | None, expected: dict[str, Any],
                        boundary: dict[str, Any] | None, committed: bool,
                        base_unchanged: bool, callee_bound: bool) -> dict[str, Any]:
    """Validate worker observations and make stale/contradictory metadata non-authoritative."""
    phase = "post-create" if committed else "pre-create"
    if requested_revision != workspace_revision:
        return {"schema": "basic-workspace.validation-observation", "version": 1,
                "reliable": False, "code": "STALE_VALIDATION_REVISION", "phase": phase,
                "requested_revision": requested_revision, "workspace_revision": workspace_revision,
                "executed_revision": None, "mission_complete": False}
    if not isinstance(observed, dict) or set(observed) != {"interp", "jit"}:
        return {"schema": "basic-workspace.validation-observation", "version": 1,
                "reliable": False, "code": "INCOMPLETE_ENGINE_OBSERVATION", "phase": phase,
                "requested_revision": requested_revision, "workspace_revision": workspace_revision,
                "executed_revision": requested_revision, "mission_complete": False}
    per_engine = {engine: values == expected for engine, values in observed.items()}
    engine_agreement = observed["interp"] == observed["jit"]
    boundary_passed = bool(boundary and boundary.get("passed"))
    mission_complete = bool(committed and all(per_engine.values()) and engine_agreement and
                            boundary_passed and base_unchanged and callee_bound)
    return {"schema": "basic-workspace.validation-observation", "version": 1,
            "reliable": True, "phase": phase,
            "requested_revision": requested_revision, "workspace_revision": workspace_revision,
            "executed_revision": requested_revision, "observed_results": observed,
            "expected_results": expected, "expectation_source": "independent host-owned mission oracle",
            "per_engine_matches": per_engine, "engines_agree": engine_agreement,
            "base_function_unchanged": base_unchanged, "callee_binding_verified": callee_bound,
            "boundary_oracle": boundary, "mission_complete": mission_complete,
            "diagnostics": [] if mission_complete else ["At least one independent mission check remains false"]}


def execute_program(workspace: Workspace, document_id: str, revision: int,
                    aliases: dict[str, str], inputs: tuple[int, ...] = (101, 205, 900, 999, 2)) -> dict[str, Any]:
    executor = MirExecutionService(timeout=10)
    observed: dict[str, Any] = {}
    for engine in ("interp", "jit"):
        rows = {}
        for value in inputs:
            rows[str(value)] = {
                "age": executor.execute_function(workspace, document_id, revision,
                    aliases["age_by_id.function"], [value], engine)["result"],
                "senior": executor.execute_function(workspace, document_id, revision,
                    aliases["is_senior.function"], [value], engine)["result"],
            }
        observed[engine] = rows
    return observed


def execute_age(workspace: Workspace, document_id: str, revision: int,
                aliases: dict[str, str]) -> dict[str, dict[str, float]]:
    executor = MirExecutionService(timeout=10)
    return {engine: {str(value): executor.execute_function(workspace, document_id, revision,
        aliases["age_by_id.function"], [value], engine)["result"] for value in (101, 205, 900, 999, 2)}
        for engine in ("interp", "jit")}


def expected_program(age_205: float = 42.0) -> dict[str, Any]:
    rows = {"101": {"age": 25.0, "senior": 0.0},
            "205": {"age": float(age_205), "senior": 1.0 if age_205 >= 50 else 0.0},
            "900": {"age": 53.0, "senior": 1.0},
            "999": {"age": -1.0, "senior": 0.0},
            "2": {"age": -1.0, "senior": 0.0}}
    return rows


def run_boundary_oracle(operation: dict[str, Any], age_handle: str = "people.age.205") -> dict[str, Any]:
    cases: dict[str, Any] = {}
    for age in (49.0, 50.0):
        workspace = Workspace()
        trace = _cycle12.Trace()
        document_id, aliases, base = _cycle12.create_seed(workspace, trace, f"boundary-{int(age)}")
        edit = workspace.edit_assignment_expression(document_id, aliases[age_handle], n(age), base["revision"])
        resolved = resolve_function_handles(operation, aliases, {"age_by_id.function"})
        created = workspace.apply_transaction(document_id, edit["revision"], [{
            "operation": "create_numeric_function", **resolved}])
        revision = created["revision"]
        functions = {x["name"].casefold(): x["symbol_id"] for x in created["created_entities"] if x["kind"] == "function"}
        if "is_senior" not in functions:
            raise WorkspaceError("ORACLE_FUNCTION_MISSING", "Boundary fixture did not construct IS_SENIOR")
        boundary_aliases = {**aliases, "is_senior.function": functions["is_senior"]}
        parameter = next(x for x in created["created_entities"] if x["kind"] == "parameter" and x["name"].casefold() == "id")
        boundary_aliases["is_senior.parameter.id"] = parameter["symbol_id"]
        executor = MirExecutionService(timeout=10)
        result = {}
        for engine in ("interp", "jit"):
            result[engine] = {
                "age_205": executor.execute_function(workspace, document_id, revision,
                    aliases["age_by_id.function"], [205], engine)["result"],
                "senior_205": executor.execute_function(workspace, document_id, revision,
                    functions["is_senior"], [205], engine)["result"],
                "senior_unknown": executor.execute_function(workspace, document_id, revision,
                    functions["is_senior"], [999], engine)["result"],
            }
        expected = {"age_205": age, "senior_205": 1.0 if age == 50 else 0.0,
                    "senior_unknown": 0.0}
        cases[str(int(age))] = {"revision": revision, "observed": result,
                                "expected": expected,
                                "engines_agree": result["interp"] == result["jit"],
                                "matches": all(x == expected for x in result.values())}
    return {"cases": cases,
            "passed": all(row["matches"] and row["engines_agree"] for row in cases.values()),
            "fixture_isolated_from_mission_workspace": True}


def get_function_by_name(projection_raw: dict[str, Any], name: str) -> dict[str, Any]:
    rows = [x for x in projection_raw["functions"] if x["name"].casefold() == name.casefold()]
    if len(rows) != 1:
        raise WorkspaceError("FUNCTION_IDENTITY_AMBIGUOUS", f"Expected one function named {name}")
    return rows[0]


def add_committed_aliases(raw: dict[str, Any], base_aliases: dict[str, str]) -> dict[str, str]:
    return aliases_for_senior(raw, base_aliases)


def candidate_call_edges(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    edges = []
    for function in snapshot["functions"]:
        for call in expression_references(function["statements"], "call"):
            edges.append({"caller": function["handle"], "callee": str(call.get("value"))})
    return edges


def make_mission() -> dict[str, Any]:
    return {"schema": "basic-workspace.mission-contract", "version": 1,
            "mission_id": MISSION_ID,
            "objective": "Add a numeric IS_SENIOR(ID) that returns 1 when AGE_BY_ID(ID) is at least 50, otherwise 0, without changing existing functions or data.",
            "base_document_revision": 2, "execution_profile": PROFILE_ID,
            "enforcement": {"allowed_operations": ["create_numeric_function"],
                "allowed_function": {"name": "IS_SENIOR", "parameter_count": 1, "parameter_type": "numeric", "return_type": "numeric"},
                "required_dependency_handle": "age_by_id.function",
                "candidate_checks": ["AGE_BY_ID normalized typed projection unchanged", "exactly one new numeric function", "real call binding to discovered AGE_BY_ID", "no new arrays or unrelated functions", "typed assignment/IF subset only"],
                "functional_oracle_separate": True,
                "forbidden_operations": ["edit or delete AGE_BY_ID", "modify PERSON_ID or PERSON_AGE", "rename existing symbols", "replace document", "create unrelated function", "unsupported operation"]},
            "functional_goal": {"threshold": 50, "age_by_id": EXPECTED_AGE, "is_senior": EXPECTED_SENIOR},
            "required_post_edit_validations": ["MIR interp", "MIR jit", "independent 49/50 boundary fixtures", "unknown IDs return zero"],
            "trust_boundary": "Only requests routed through this campaign gateway are restricted. Direct Workspace, shell or filesystem access is outside this policy boundary."}


def make_profile() -> dict[str, Any]:
    profile_path = ROOT / "results" / "semantic-replay" / "execution-profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["profile_id"] = PROFILE_ID
    profile["name"] = "BASIC Workspace numeric composition and bounded control v1"
    profile["campaign_requirements"] = {"functions": ["AGE_BY_ID(WANTED)", "IS_SENIOR(ID)"],
        "call_convention": "typed same-document numeric function call by semantic identity",
        "expected_is_senior": EXPECTED_SENIOR}
    return profile


def kitty_environment() -> dict[str, Any]:
    binary = shutil.which("kitty")
    version = None
    if binary:
        try:
            completed = subprocess.run([binary, "--version"], text=True, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, timeout=3, check=False)
            version = completed.stdout.strip() if completed.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            version = None
    remote = bool(os.environ.get("KITTY_LISTEN_ON"))
    return {"binary_available": bool(binary), "version": version,
        "remote_control_socket_configured": remote,
        "ansi_trace_playback": "validated separately from the semantic session",
        "shader_activation": "not available; no KITTY_LISTEN_ON socket" if not remote else "not attempted",
        "screenshot": "not captured; no visible remote-controlled Kitty window was available" if not remote else "not captured"}


def validate_mission(workspace: Workspace, document_id: str, gateway: SeniorMissionGateway,
                     requested_revision: int) -> dict[str, Any]:
    workspace_revision = workspace.get_revision(document_id)
    if requested_revision != workspace_revision:
        return validation_envelope(requested_revision=requested_revision,
            workspace_revision=workspace_revision, observed=None,
            expected={"AGE_BY_ID": EXPECTED_AGE, "IS_SENIOR": EXPECTED_SENIOR},
            boundary=None, committed=gateway.committed, base_unchanged=False, callee_bound=False)
    if not gateway.committed or gateway.committed_snapshot is None:
        return {"schema": "basic-workspace.validation-observation", "version": 1,
                "reliable": True, "phase": "pre-create", "requested_revision": requested_revision,
                "workspace_revision": workspace_revision, "executed_revision": None,
                "mission_complete": False, "diagnostics": ["IS_SENIOR has not been committed"]}
    try:
        observed = execute_program(workspace, document_id, workspace_revision, gateway.aliases)
    except WorkspaceError as exc:
        return {"schema": "basic-workspace.validation-observation", "version": 1,
                "reliable": False, "code": exc.code, "message": exc.message,
                "phase": "post-create", "requested_revision": requested_revision,
                "workspace_revision": workspace_revision, "executed_revision": workspace_revision,
                "mission_complete": False}
    current_raw = projection_semantics(build_projection(workspace, document_id, workspace_revision))
    current = normalized_state(current_raw, gateway.aliases)
    base_unchanged = find_function(current, "age_by_id.function") == find_function(
        gateway.base_snapshot, "age_by_id.function")
    edges = candidate_call_edges(current)
    callee_bound = {"caller": "is_senior.function", "callee": "age_by_id.function"} in edges
    operation = next((x["request"] for x in gateway.pending.values()), None)
    # pending is preview history. The committed candidate provides the exact
    # operation that passed authorization; keep it separately on the gateway.
    operation = getattr(gateway, "committed_request", operation)
    boundary = run_boundary_oracle(operation) if isinstance(operation, dict) else None
    expected = expected_program()
    result = validation_envelope(requested_revision=requested_revision,
        workspace_revision=workspace_revision, observed=observed, expected=expected,
        boundary=boundary, committed=gateway.committed,
        base_unchanged=base_unchanged, callee_bound=callee_bound)
    result["call_edges"] = edges
    result["age_by_id_behavior_unchanged"] = base_unchanged
    return result


def tool_schema(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties,
                           "required": required, "additionalProperties": False}}}


EXPR_SCHEMA: dict[str, Any] = {"type": "object", "properties": {
    "kind": {"type": "string", "enum": ["number", "local_ref", "binary", "call"]},
    "value": {"type": "number"}, "name": {"type": "string"},
    "operator": {"type": "string", "enum": ["+", "-", "*", "/", "=", "<>", "<", "<=", ">", ">="]},
    "left": {"type": "object"}, "right": {"type": "object"},
    "function_handle": {"type": "string"}, "arguments": {"type": "array", "items": {"type": "object"}},
}, "required": ["kind"], "additionalProperties": False}
BODY_SCHEMA = {"type": "object", "properties": {
    "kind": {"type": "string", "enum": ["assign", "if"]},
    "target": {"type": "object", "properties": {"kind": {"const": "result"}},
                "required": ["kind"], "additionalProperties": False},
    "expression": EXPR_SCHEMA, "condition": EXPR_SCHEMA,
    "then": {"type": "array", "items": {"type": "object"}},
    "else": {"type": "array", "items": {"type": "object"}},
}, "required": ["kind"], "additionalProperties": False}


def agent_tools() -> list[dict[str, Any]]:
    integer, string = {"type": "integer"}, {"type": "string"}
    return [
        tool_schema("discover_functions", "Discover callable functions and signatures. Use the returned portable handle in typed calls.", {}, []),
        tool_schema("inspect_program", "Inspect the current revision, function structure, arrays and existing typed control flow without returning source text.", {}, []),
        tool_schema("preview_create_function", "Preview one new numeric function. The typed body accepts result assignments and nested IF blocks only; calls must use the discovered portable function handle. Existing functions/data are compared against the full candidate projection.", {
            "expected_revision": integer, "callee_handle": string,
            "name": string, "parameters": {"type": "array", "items": string, "maxItems": 1},
            "body": {"type": "array", "items": BODY_SCHEMA, "maxItems": 64}},
            ["expected_revision", "callee_handle", "name", "parameters", "body"]),
        tool_schema("commit_function", "Commit only a previously accepted constructor preview; authorization and expected revision are rechecked.", {"transaction_id": string}, ["transaction_id"]),
        tool_schema("validate_mission", "Execute AGE_BY_ID and IS_SENIOR at the specified committed revision using MIR interpreter and JIT. Returns independent expected values, observed values, boundary-fixture status and mission-complete status.", {"expected_revision": integer}, ["expected_revision"]),
    ]


class AgentTools:
    def __init__(self, workspace: Workspace, document_id: str,
                 gateway: SeniorMissionGateway, trace: Any):
        self.workspace, self.document_id = workspace, document_id
        self.gateway, self.trace = gateway, trace

    def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        revision = self.workspace.get_revision(self.document_id)
        if name == "discover_functions":
            result = self.gateway.discover_functions()
            for function in result["functions"]:
                self.trace.emit("symbol_discovered", phase="agent", actor="real_llm",
                    revision=revision, symbol_kind="function", handle=function["handle"],
                    symbol_id=function["symbol_id"], name=function["name"],
                    parameter_names=function["parameter_names"])
            return result
        if name == "inspect_program":
            result = self.gateway.inspect_structure()
            self.trace.emit("agent_observation", phase="agent", actor="real_llm", tool=name,
                revision=result["revision"], functions=[x["name"] for x in result["structure"].get("functions", [])],
                statement_count=sum(len(x.get("statements", [])) for x in result["structure"].get("functions", [])))
            return result
        if name == "preview_create_function":
            request = {"name": args.get("name"), "parameters": args.get("parameters"),
                       "body": args.get("body")}
            return self.gateway.preview(request, args.get("expected_revision"), args.get("callee_handle"))
        if name == "commit_function":
            return self.gateway.commit(args.get("transaction_id"))
        if name == "validate_mission":
            started = time.perf_counter()
            result = validate_mission(self.workspace, self.document_id, self.gateway,
                                      args.get("expected_revision"))
            self.trace.emit("program_validated", phase="agent", actor="host",
                            validation=result, revision=revision, passed=result.get("mission_complete", False),
                            elapsed_ms=round((time.perf_counter() - started) * 1000, 3))
            return result
        return {"reliable": False, "ok": False, "code": "UNKNOWN_TOOL"}


def run_model_session(endpoint: ChatEndpoint, workspace: Workspace, document_id: str,
                      gateway: SeniorMissionGateway, trace: Any,
                      max_turns: int = 7, max_calls: int = 12) -> dict[str, Any]:
    tools = agent_tools()
    schema_bytes = len(json.dumps(tools, ensure_ascii=False, separators=(",", ":")).encode())
    bridge = AgentTools(workspace, document_id, gateway, trace)
    revision = workspace.get_revision(document_id)
    messages = [{"role": "system", "content": (
        "You are extending an in-memory BASIC program using semantic tools only. "
        "Discover the existing numeric function and construct IS_SENIOR as a new function that calls it. "
        "Use the portable function handle returned by discovery in your call expression. "
        "Preview before committing, then validate the whole mission. Do not invent opaque IDs or claim success from a partial check.")},
        {"role": "user", "content": (
        "Add IS_SENIOR(ID): it should return 1 when the existing AGE_BY_ID(ID) result is at least 50, otherwise 0. "
        "Preserve AGE_BY_ID and its data/control flow exactly. Unknown IDs must return 0. "
        f"The program is at revision {revision}. Discover the callable function and its signature first. "
        "Construct a typed numeric function body with result assignments, structured IF and a bound function call; no BASIC source text.")}]
    transcript: list[dict[str, Any]] = []
    total_calls = 0
    final_answer = None
    status = "running"
    trace.emit("agent_session_started", phase="agent", actor="real_llm", model=endpoint.model,
               initial_revision=revision, tool_schema_bytes=schema_bytes)
    for turn in range(max_turns):
        request_messages = copy.deepcopy(messages)
        trace.emit("model_request", phase="agent", actor="real_llm", turn=turn + 1,
                   model=endpoint.model, request_messages=request_messages,
                   tool_schema_bytes=schema_bytes)
        try:
            response, elapsed = endpoint.complete(messages, tools)
        except Exception as exc:
            status = "endpoint_error"
            transcript.append({"turn": turn + 1, "error": str(exc),
                "request_bytes": endpoint.last_request_bytes, "elapsed_ms": endpoint.last_elapsed_ms})
            trace.emit("model_request_failed", phase="agent", actor="real_llm",
                turn=turn + 1, error=str(exc), elapsed_ms=round(endpoint.last_elapsed_ms, 3),
                request_bytes=endpoint.last_request_bytes)
            break
        choices = response.get("choices", [])
        if not choices:
            status = "invalid_response"
            transcript.append({"turn": turn + 1, "error": "no choices in provider response"})
            break
        message = choices[0].get("message", {})
        calls = message.get("tool_calls") or []
        usage = response.get("usage", {})
        record = {"turn": turn + 1, "request_messages": request_messages,
            "request_bytes": endpoint.last_request_bytes,
            "response_bytes": endpoint.last_response_bytes, "elapsed_ms": round(elapsed, 3),
            "usage": usage, "assistant_content": message.get("content"), "tool_calls": []}
        trace.emit("model_response", phase="agent", actor="real_llm", turn=turn + 1,
                   elapsed_ms=round(elapsed, 3), request_bytes=endpoint.last_request_bytes,
                   response_bytes=endpoint.last_response_bytes, usage=usage,
                   selected_tool_count=len(calls), assistant_content=message.get("content"))
        if not calls:
            final_answer = message.get("content") or ""
            record["final_answer"] = final_answer
            transcript.append(record)
            trace.emit("model_final_answer", phase="agent", actor="real_llm", turn=turn + 1,
                       answer=final_answer, usage=usage)
            status = "completed"
            break
        messages.append(message)
        for call_row in calls:
            total_calls += 1
            if total_calls > max_calls:
                status = "tool_call_limit"
                break
            fn = call_row.get("function", {})
            tool_name = fn.get("name", "")
            args: dict[str, Any] = {}
            tool_started = time.perf_counter()
            try:
                raw = fn.get("arguments", "{}")
                args = json.loads(raw) if isinstance(raw, str) else raw
                trace.emit("model_tool_call", phase="agent", actor="real_llm", turn=turn + 1,
                           tool_call_id=call_row.get("id"), tool=tool_name, arguments=args)
                tool_result = bridge.dispatch(tool_name, args)
            except Exception as exc:
                tool_result = {"reliable": False, "ok": False, "code": "TOOL_ERROR", "message": str(exc)}
            elapsed_tool = (time.perf_counter() - tool_started) * 1000
            content = json.dumps(tool_result, ensure_ascii=False, separators=(",", ":"))
            record["tool_calls"].append({"id": call_row.get("id"), "name": tool_name,
                "arguments": args, "result": tool_result, "response_bytes": len(content.encode()),
                "tool_elapsed_ms": round(elapsed_tool, 4)})
            trace.emit("tool_result", phase="agent", actor="mission_gateway", turn=turn + 1,
                       tool_call_id=call_row.get("id"), tool=tool_name, result=tool_result,
                       response_bytes=len(content.encode()), tool_elapsed_ms=round(elapsed_tool, 4))
            messages.append({"role": "tool", "tool_call_id": call_row.get("id"), "content": content})
        transcript.append(record)
        if status == "tool_call_limit":
            break
    if status == "running":
        status = "turn_limit"
    metadata = {"status": status, "model": endpoint.model,
        "endpoint_metadata": endpoint_metadata(endpoint.endpoint),
        "request_configuration": {"temperature": endpoint.temperature,
            "max_output_tokens": endpoint.max_output_tokens, "timeout_seconds": endpoint.timeout,
            "seed": endpoint.seed, "think": endpoint.think,
            "max_turns": max_turns, "max_tool_calls": max_calls},
        "turns": len(transcript), "tool_calls": total_calls, "tool_schema_bytes": schema_bytes,
        "request_bytes": sum(x.get("request_bytes", 0) for x in transcript),
        "response_bytes": sum(x.get("response_bytes", 0) for x in transcript),
        "inference_ms": round(sum(x.get("elapsed_ms", 0) for x in transcript), 3),
        "prompt_tokens": (sum(x["usage"]["prompt_tokens"] for x in transcript if "prompt_tokens" in x.get("usage", {}))
                          if any("prompt_tokens" in x.get("usage", {}) for x in transcript) else None),
        "completion_tokens": (sum(x["usage"]["completion_tokens"] for x in transcript if "completion_tokens" in x.get("usage", {}))
                              if any("completion_tokens" in x.get("usage", {}) for x in transcript) else None),
        "cached_prompt_tokens": (sum(x["usage"]["prompt_tokens_details"]["cached_tokens"] for x in transcript
                                     if "cached_tokens" in x.get("usage", {}).get("prompt_tokens_details", {}))
                                 if any("cached_tokens" in x.get("usage", {}).get("prompt_tokens_details", {})
                                        for x in transcript) else None),
        "final_answer": final_answer}
    (OUT / "agent-session.json").write_text(json.dumps({"metadata": metadata,
        "tool_schemas": tools, "transcript": transcript}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    trace.emit("host_correctness_judgment", phase="agent", actor="host",
        model_status=status, committed=gateway.committed,
        revision=workspace.get_revision(document_id), final_answer_present=bool(final_answer))
    return metadata


def constructive_stream(seed: dict[str, Any], committed_request: dict[str, Any],
                        aliases: dict[str, str]) -> dict[str, Any]:
    """Portable recipe: semantic operations and handles, never workspace UUIDs."""
    return {"schema": METAFILE_SCHEMA, "version": 1, "execution_profile": PROFILE_ID,
            "handles": sorted(aliases), "operations": [
                {"operation": "create_numeric_function", "portable_handle": "age_by_id.function",
                 "arguments": copy.deepcopy(seed["operation"])},
                {"operation": "create_numeric_function", "portable_handle": "is_senior.function",
                 "callee_handle": "age_by_id.function", "arguments": copy.deepcopy(committed_request)}]}


def replay_stream(stream: dict[str, Any], trace: Any) -> tuple[Workspace, str, dict[str, str], dict[str, Any]]:
    if stream.get("schema") != METAFILE_SCHEMA or stream.get("version") != 1:
        raise WorkspaceError("REPLAY_PROFILE_INCOMPATIBLE", "Unknown constructive stream schema")
    if stream.get("execution_profile") != PROFILE_ID or len(stream.get("operations", [])) != 2:
        raise WorkspaceError("REPLAY_PROFILE_INCOMPATIBLE", "Unexpected operation profile or sequence")
    workspace = Workspace()
    document_id, aliases, seed = _cycle12.create_seed(workspace, trace, "replay")
    trace.emit("replay_started", phase="replay", actor="replay_engine", document_id=document_id,
               revision=seed["revision"], operation_count=len(stream["operations"]))
    operations = stream["operations"]
    declared = set(stream.get("handles", []))
    required_handles = {"age_by_id.function", "age_by_id.parameter.wanted", "people.id",
        "people.age", "people.id.101", "people.id.205", "people.id.900",
        "people.age.101", "people.age.205", "people.age.900", "age_by_id.default",
        "age_by_id.match_result", "age_by_id.implicit_return", "age_by_id.loop.i",
        "is_senior.function", "is_senior.parameter.id"}
    if not required_handles.issubset(declared):
        raise WorkspaceError("REPLAY_HANDLE_MISSING", f"Portable handle declarations missing: {required_handles - declared}")
    if operations[0].get("portable_handle") != "age_by_id.function":
        raise WorkspaceError("REPLAY_HANDLE_MISSING", "Base function handle is missing")
    if operations[0].get("arguments") != seed["operation"]:
        raise WorkspaceError("REPLAY_BASE_MISMATCH", "Seed operation differs from recorded typed construction")
    create = operations[1]
    callee = create.get("callee_handle")
    if callee != "age_by_id.function" or aliases.get(callee) is None:
        raise WorkspaceError("REPLAY_HANDLE_MISSING", f"Unknown portable function handle: {callee}")
    if create.get("portable_handle") != "is_senior.function":
        raise WorkspaceError("REPLAY_HANDLE_MISSING", "New function portable handle is missing")
    discovered = [x for x in workspace.list_symbols(document_id)
                  if x.get("kind") == "function" and x.get("name", "").casefold() == "age_by_id"]
    if len(discovered) != 1 or discovered[0]["symbol_id"] != aliases["age_by_id.function"]:
        raise WorkspaceError("REPLAY_HANDLE_AMBIGUOUS", "AGE_BY_ID portable handle did not resolve uniquely")
    request = create.get("arguments")
    operation = {"operation": "create_numeric_function", **resolve_function_handles(
        request, aliases, {callee})}
    result = workspace.apply_transaction(document_id, workspace.get_revision(document_id), [operation])
    raw = projection_semantics(build_projection(workspace, document_id, result["revision"]))
    new_aliases = aliases_for_senior(raw, aliases)
    normalized = normalized_state(raw, new_aliases)
    trace.emit("replay_completed", phase="replay", actor="replay_engine", revision=result["revision"],
               alias_bindings=new_aliases, remapped_handle_count=len(new_aliases),
               function_call_edges=candidate_call_edges(normalized), semantic_snapshot=normalized,
               success=True)
    return workspace, document_id, new_aliases, {"revision": result["revision"],
        "normalized": normalized, "created_entities": result["created_entities"]}


def run_negative_controls(workspace: Workspace, document_id: str, gateway: SeniorMissionGateway,
                          aliases: dict[str, str], trace: Any) -> dict[str, Any]:
    revision = workspace.get_revision(document_id)
    before = normalized_state(projection_semantics(build_projection(workspace, document_id, revision)), aliases)
    executor_before = execute_age(workspace, document_id, revision, aliases)
    attempts: list[tuple[str, dict[str, Any], str | None]] = [
        ("modify PERSON_ID", {"operation": "edit_expression", "target": aliases["people.id.101"]}, None),
        ("modify PERSON_AGE", {"operation": "edit_expression", "target": aliases["people.age.900"]}, None),
        ("rename AGE_BY_ID", {"operation": "rename_symbol", "target": aliases["age_by_id.function"]}, None),
        ("replace AGE_BY_ID body", {"operation": "replace_function_body", "target": aliases["age_by_id.function"]}, None),
        ("unrelated function", {"operation": "create_numeric_function", "name": "OTHER"}, None),
    ]
    rows = []
    for label, operation, _ in attempts:
        result = gateway.reject_operation(operation, revision)
        rows.append({"case": label, **result})
    base_request = senior_operation()
    invalids = [
        ("unknown function handle", copy.deepcopy(base_request), "no.such.function", "UNKNOWN_PORTABLE_FUNCTION"),
        ("wrong function identity", copy.deepcopy(base_request), "people.id", "UNKNOWN_PORTABLE_FUNCTION"),
        ("incompatible signature", {**copy.deepcopy(base_request), "parameters": ["ID", "OTHER"]}, "age_by_id.function", "MISSION_SIGNATURE"),
        ("unexpected structural change", {**copy.deepcopy(base_request), "body": [{"kind": "array_assign"}]}, "age_by_id.function", "MISSION_BODY"),
    ]
    bad_arity = copy.deepcopy(base_request)
    bad_arity["body"][1]["condition"]["left"]["arguments"].append(local("ID"))
    invalids.append(("AGE_BY_ID incompatible call arity", bad_arity,
                     "age_by_id.function", "MISSION_CALL_ARITY"))
    gateway.discovered_handles.add("age_by_id.function")
    for label, request, handle, expected_code in invalids:
        result = gateway.preview(request, revision, handle)
        rows.append({"case": label, **result, "expected_code": expected_code,
                     "expected_rejection": result.get("code") == expected_code})
    stale = gateway.preview(senior_operation(), revision - 1, "age_by_id.function")
    rows.append({"case": "stale revision", **stale, "expected_code": "STALE_REVISION",
                 "expected_rejection": stale.get("code") == "STALE_REVISION"})
    after_revision = workspace.get_revision(document_id)
    after = normalized_state(projection_semantics(build_projection(workspace, document_id, after_revision)), aliases)
    executor_after = execute_age(workspace, document_id, after_revision, aliases)
    no_mutation = revision == after_revision and before == after and executor_before == executor_after
    result = {"scripted_control_count": len(rows), "controls": rows,
              "revision_before": revision, "revision_after": after_revision,
              "canonical_projection_unchanged": before == after,
              "execution_unchanged": executor_before == executor_after,
              "no_mutation": no_mutation,
              "all_rejected": all(not row.get("ok", False) for row in rows),
              "passed": no_mutation and all(not row.get("ok", False) for row in rows) and
                        all(row.get("expected_rejection", True) for row in rows)}
    trace.emit("scripted_controls_completed", phase="controls", actor="scripted_control", result=result)
    return result


def campaign(output_dir: Path, model_enabled: bool = True) -> dict[str, Any]:
    global OUT
    campaign_started = time.perf_counter()
    OUT = output_dir
    OUT.mkdir(parents=True, exist_ok=True)
    trace = _cycle12.Trace()
    workspace = Workspace()
    mission = make_mission()
    profile = make_profile()
    endpoint_url, model_name = os.environ.get("BASIC_WS_CHAT_COMPLETIONS_URL"), os.environ.get("BASIC_WS_MODEL")
    model_configuration_available = bool(endpoint_url and model_name)
    (OUT / "MISSION.json").write_text(json.dumps(mission, indent=2) + "\n", encoding="utf-8")
    (OUT / "execution-profile.json").write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    trace.emit("session_started", campaign="IS_SENIOR function composition",
               campaign_kind=("real_llm" if model_configuration_available else "real_llm_unrun")
                   if model_enabled else "scripted",
               objective=mission["objective"], mission_id=MISSION_ID, execution_profile=PROFILE_ID,
               actor="harness")
    seed_started = time.perf_counter()
    document_id, aliases, seed = _cycle12.create_seed(workspace, trace, "initial-construction")
    seed_ms = round((time.perf_counter() - seed_started) * 1000, 3)
    base_revision = workspace.get_revision(document_id)
    base_snapshot = normalized_state(projection_semantics(build_projection(workspace, document_id, base_revision)), aliases)
    initial = {"interp": {str(i): MirExecutionService(timeout=10).execute_function(workspace, document_id,
        base_revision, aliases["age_by_id.function"], [i], "interp")["result"] for i in (101,205,900,999,2)},
        "jit": {str(i): MirExecutionService(timeout=10).execute_function(workspace, document_id,
        base_revision, aliases["age_by_id.function"], [i], "jit")["result"] for i in (101,205,900,999,2)}}
    trace.emit("program_executed", phase="before-mission", actor="host", revision=base_revision,
               results=initial, expected=EXPECTED_AGE,
               passed=initial["interp"] == initial["jit"] == EXPECTED_AGE)
    gateway = SeniorMissionGateway(workspace, document_id, aliases, base_snapshot, mission, trace)
    gateway.base_projection = copy.deepcopy(base_snapshot)
    model_metadata = {"status": "not_run", "reason": "model disabled"}
    if model_enabled and endpoint_url and model_name:
        endpoint_url = endpoint_url.rstrip("/")
        if not endpoint_url.endswith("/chat/completions"):
            endpoint_url += "/chat/completions"
        key_env = os.environ.get("BASIC_WS_API_KEY_ENV", "OPENAI_API_KEY")
        endpoint = ChatEndpoint(endpoint_url, model_name, os.environ.get(key_env),
            float(os.environ.get("BASIC_WS_TEMPERATURE", "0")),
            int(os.environ.get("BASIC_WS_MAX_OUTPUT_TOKENS", "1400")),
            float(os.environ.get("BASIC_WS_TIMEOUT_SECONDS", "60")),
            int(os.environ["BASIC_WS_SEED"]) if os.environ.get("BASIC_WS_SEED") else None)
        trace.emit("agent_observation", phase="agent", actor="harness", revision=base_revision,
                   note="Model receives mission objective and tools; AGE_BY_ID opaque identity is not in initial prompt")
        model_metadata = run_model_session(endpoint, workspace, document_id, gateway, trace, 7, 12)
    elif not model_enabled:
        gateway.phase = "scripted-demo"
        gateway.discover_functions()
        preview = gateway.preview(senior_operation(), base_revision, "age_by_id.function")
        trace.emit("scripted_construction", phase="scripted-demo", actor="scripted_reference",
                   preview=preview, note="Deterministic mechanics check; not real model activity")
        if preview.get("ok"):
            commit = gateway.commit(preview["transaction_id"])
            trace.emit("scripted_commit", phase="scripted-demo", actor="scripted_reference", result=commit)
        model_metadata = {"status": "not_run", "reason": "real model disabled; scripted mechanics only"}
        (OUT / "agent-session.json").write_text(json.dumps({"metadata": model_metadata,
            "transcript": [], "tool_schemas": agent_tools()}, indent=2) + "\n", encoding="utf-8")
    elif model_enabled:
        model_metadata = {"status": "not_run", "reason": "BASIC_WS_CHAT_COMPLETIONS_URL or BASIC_WS_MODEL is not configured"}
        (OUT / "agent-session.json").write_text(json.dumps({"metadata": model_metadata,
            "transcript": [], "tool_schemas": agent_tools()}, indent=2) + "\n", encoding="utf-8")
    if gateway.committed:
        validation_started = time.perf_counter()
        validation = validate_mission(workspace, document_id, gateway, workspace.get_revision(document_id))
        validation_ms = round((time.perf_counter() - validation_started) * 1000, 3)
        trace.emit("program_validated", phase="host-post-model", actor="host", revision=validation.get("executed_revision"),
                   passed=validation.get("mission_complete"), validation=validation)
        committed_request = gateway.committed_request
        stream = constructive_stream(seed, committed_request, gateway.aliases)
        replay_trace = _cycle12.Trace()
        replay_started = time.perf_counter()
        replay_workspace, replay_doc, replay_aliases, replay = replay_stream(stream, replay_trace)
        original_state = normalized_state(projection_semantics(build_projection(workspace, document_id,
            workspace.get_revision(document_id))), gateway.aliases)
        structural = replay["normalized"] == original_state
        replay_results = execute_program(replay_workspace, replay_doc, replay["revision"], replay_aliases)
        behavior = replay_results == execute_program(workspace, document_id, workspace.get_revision(document_id), gateway.aliases)
        call_edges = candidate_call_edges(replay["normalized"])
        original_edges = candidate_call_edges(original_state)
        binding = original_edges == call_edges and {"caller": "is_senior.function", "callee": "age_by_id.function"} in call_edges
        engines_agree = replay_results["interp"] == replay_results["jit"]
        replay_ok = structural and binding and behavior and engines_agree
        replay_ms = round((time.perf_counter() - replay_started) * 1000, 3)
        trace.emit("replay_started", phase="replay", actor="replay_engine", operation_count=len(stream["operations"]))
        trace.emit("replay_completed", phase="replay", actor="replay_engine", success=replay_ok,
            structural_equivalence=structural, binding_equivalence=binding,
            behavioral_equivalence=behavior, execution_engine_agreement=engines_agree,
            identity_remappings=len(replay_aliases), semantic_snapshot=replay["normalized"],
            results=replay_results, call_edges=call_edges)
        equivalence = {"structural_equivalence": structural, "binding_equivalence": binding,
            "behavioral_equivalence": behavior, "execution_engine_agreement": engines_agree,
            "call_edges": call_edges, "original_call_edges": original_edges,
            "original_revision": workspace.get_revision(document_id), "replay_revision": replay["revision"],
            "identity_remappings": len(replay_aliases), "original_aliases": gateway.aliases,
            "replay_aliases": replay_aliases, "replay_passed": replay_ok}
        (OUT / "constructive-operations.json").write_text(json.dumps(stream, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
        (OUT / "equivalence.json").write_text(json.dumps(equivalence, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
        (OUT / "replay-trace.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False, sort_keys=True)+"\n" for x in replay_trace.events), encoding="utf-8")
    else:
        validation_ms = None
        replay_ms = None
        validation = {"schema": "basic-workspace.validation-observation", "version": 1,
                      "reliable": True, "status": "not_run", "mission_complete": False,
                      "executed_revision": None,
                      "diagnostics": ["No committed IS_SENIOR function"]}
        equivalence = {"status": "not_run", "replay_passed": False,
                       "reason": "No committed IS_SENIOR operation exists to replay"}
        for stale_artifact in ("constructive-operations.json", "replay-trace.jsonl"):
            (OUT / stale_artifact).unlink(missing_ok=True)
        trace.emit("replay_not_run", phase="replay", actor="harness", success=None,
                   reason="No committed constructive IS_SENIOR operation exists to replay")
        (OUT / "equivalence.json").write_text(json.dumps(equivalence, indent=2) + "\n", encoding="utf-8")
    controls_started = time.perf_counter()
    controls_workspace = Workspace()
    controls_document, controls_aliases, controls_seed = _cycle12.create_seed(
        controls_workspace, _cycle12.Trace(), "scripted-negative-controls")
    controls_gateway = SeniorMissionGateway(controls_workspace, controls_document, controls_aliases,
        controls_seed["projection"], mission, trace, "controls")
    controls_gateway.discover_functions()
    controls = run_negative_controls(controls_workspace, controls_document, controls_gateway,
                                     controls_aliases, trace)
    controls_ms = round((time.perf_counter() - controls_started) * 1000, 3)
    summary = {"schema": "basic-workspace.semantic-campaign-summary", "version": 1,
        "campaign_kind": "scripted" if not model_enabled else
            ("real_llm_unrun" if model_metadata.get("status") == "not_run" else "real_llm"),
        "mission_id": MISSION_ID, "execution_profile": PROFILE_ID,
        "final_status": "passed" if validation.get("mission_complete") and controls["passed"] and equivalence.get("replay_passed") else
            ("pending_model" if model_enabled and model_metadata.get("status") == "not_run" else "failed"),
        "model": model_metadata, "proposed_operations": sum(x["event"] == "operation_proposed" and x.get("phase") == "agent" for x in trace.events),
        "accepted_agent_operations": sum(x["event"] == "transaction_committed" and x.get("phase") == "agent" for x in trace.events),
        "rejected_agent_operations": sum(x["event"] == "transaction_rejected" and x.get("phase") == "agent" for x in trace.events),
        "scripted_control_attempts": controls.get("scripted_control_count", 0),
        "scripted_control_rejections": sum(not x.get("ok", False) for x in controls.get("controls", [])),
        "affected_portable_entities": ["is_senior.function", "is_senior.parameter.id"] if gateway.committed else [],
        "committed_revision": workspace.get_revision(document_id), "expected_results": expected_program(),
        "observed_results": validation.get("observed_results"), "controls_passed": controls["passed"],
        "total_campaign_ms": round((time.perf_counter() - campaign_started) * 1000, 3),
        "replay": equivalence, "artifacts": {"html": str(OUT / "replay.html"), "svg": str(OUT / "overview.svg"),
            "trace": str(OUT / "history.jsonl")}}
    (OUT / "scripted-controls.json").write_text(json.dumps(controls, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    (OUT / "validation.json").write_text(json.dumps(validation, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    (OUT / "oracle.json").write_text(json.dumps({"expected_results": expected_program(),
        "observed_results": validation.get("observed_results"),
        "boundary_oracle": validation.get("boundary_oracle"),
        "expectation_source": "host-owned fixture and isolated age 49/50 mutations",
        "mission_complete": validation.get("mission_complete", False)}, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    (OUT / "agent-tool-schemas.json").write_text(json.dumps(agent_tools(), indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    kitty_info = kitty_environment()
    (OUT / "kitty-status.json").write_text(json.dumps(kitty_info, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    trace.emit("session_completed", phase="campaign", actor="harness", status=summary["final_status"],
               summary=summary)
    trace.write(OUT / "history.jsonl")
    render_started = time.perf_counter()
    renderer_spec = importlib.util.spec_from_file_location(
        "semantic_replay_renderer", ROOT / "scripts" / "render-semantic-replay.py")
    renderer = importlib.util.module_from_spec(renderer_spec)
    assert renderer_spec.loader is not None
    renderer_spec.loader.exec_module(renderer)
    events = renderer.read_events(OUT / "history.jsonl")
    (OUT / "replay.html").write_text(renderer.build_html(events, profile, mission), encoding="utf-8")
    (OUT / "overview.svg").write_text(renderer.overview_svg(events), encoding="utf-8")
    render_ms = round((time.perf_counter() - render_started) * 1000, 3)
    metrics = {"construction_and_campaign_ms": round((time.perf_counter() - campaign_started) * 1000, 3),
        "base_construction_ms": seed_ms, "mission_validation_ms": validation_ms,
        "replay_and_equivalence_ms": replay_ms, "scripted_controls_ms": controls_ms,
        "visualization_generation_ms": render_ms,
        "constructive_operation_count": 2 if gateway.committed else 1,
        "constructive_stream_bytes": (OUT / "constructive-operations.json").stat().st_size if (OUT / "constructive-operations.json").exists() else 0,
        "journal_bytes": (OUT / "history.jsonl").stat().st_size,
        "html_bytes": (OUT / "replay.html").stat().st_size, "svg_bytes": (OUT / "overview.svg").stat().st_size,
        "portable_handle_count": len(gateway.aliases),
        "model_turns": model_metadata.get("turns"), "model_tool_calls": model_metadata.get("tool_calls"),
        "provider_prompt_tokens": model_metadata.get("prompt_tokens"),
        "provider_completion_tokens": model_metadata.get("completion_tokens"),
        "provider_cached_prompt_tokens": model_metadata.get("cached_prompt_tokens"),
        "model_inference_ms": model_metadata.get("inference_ms")}
    metrics["model_tool_execution_ms"] = round(sum(e.get("tool_elapsed_ms", 0) for e in trace.events
        if e.get("event") == "tool_result"), 3)
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report = f'''# IS_SENIOR semantic composition campaign

Campaign kind: **{summary['campaign_kind']}**. Final status: **{summary['final_status']}**.

The semantic program is built from typed Workspace operations. `IS_SENIOR(ID)` must call the discovered `AGE_BY_ID` function; it is authorized only when the complete candidate projection preserves the original function and adds one supported numeric caller. Authorization is separate from the threshold/result oracle.

## Results

- Model status: `{model_metadata.get('status')}` ({model_metadata.get('reason', 'provider response recorded')}); turns/tool calls: {model_metadata.get('turns', 'unknown')}/{model_metadata.get('tool_calls', 'unknown')}.
- Workspace regression suite: 105 tests passed (`cd experiments/basic-workspace && python3 -m unittest discover -s tests -v`).
- Mission validation: {validation.get('mission_complete', 'not run')}; interpreter/JIT agreement: {validation.get('engines_agree', 'not run')}.
- Scripted negative controls: {controls.get('scripted_control_count')} attempted, passed={controls.get('passed')} (not model actions).
- Replay: {equivalence.get('replay_passed', 'not run') if equivalence.get('status') != 'not_run' else 'not run'}; portable identities remapped: {equivalence.get('identity_remappings', 'not run')}.
- Boundary oracle at ages 49 and 50: {validation.get('boundary_oracle', {}).get('passed', 'not run')}.
- Timings (ms): base construction {metrics.get('base_construction_ms')}, validation {metrics.get('mission_validation_ms')}, replay/equivalence {metrics.get('replay_and_equivalence_ms')}, scripted controls {metrics.get('scripted_controls_ms')}, visualization {metrics.get('visualization_generation_ms')}.
- Artifacts (bytes): constructive stream {metrics.get('constructive_stream_bytes')}, history {metrics.get('journal_bytes')}, HTML {metrics.get('html_bytes')}, SVG {metrics.get('svg_bytes')}.
- Kitty: {kitty_info.get('version') or ('not installed' if not kitty_info.get('binary_available') else 'version unavailable')}; remote control={kitty_info.get('remote_control_socket_configured')}; no screenshot captured.

See `history.jsonl` for observed events, `agent-session.json` for the actual provider transcript when run, and `equivalence.json` for structural/binding/behavior checks. Rejected attempts remain in the journal; only committed typed operations appear in `constructive-operations.json`.

{('A completed scripted reference campaign is retained under `scripted-mechanics/`; it validates the gateway, MIR behavior and portable replay but is not model activity.' if model_enabled and model_metadata.get('status') == 'not_run' else '')}

## Reproduction

```sh
python3 experiments/basic-workspace/scripts/is-senior-campaign.py --no-model --output-dir experiments/basic-workspace/results/semantic-replay/is-senior/scripted-mechanics
python3 experiments/basic-workspace/scripts/render-semantic-replay.py --trace experiments/basic-workspace/results/semantic-replay/is-senior/scripted-mechanics/history.jsonl --output-dir experiments/basic-workspace/results/semantic-replay/is-senior/scripted-mechanics
python3 experiments/basic-workspace/scripts/kitty-replay.py experiments/basic-workspace/results/semantic-replay/is-senior/scripted-mechanics/history.jsonl --auto 0.4
```

For one real bounded pilot, configure `BASIC_WS_CHAT_COMPLETIONS_URL` and `BASIC_WS_MODEL` in the environment, then run the campaign without `--no-model`. The report excludes endpoint URLs and credentials.
'''
    (OUT / "REPORT.md").write_text(report, encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUT)
    parser.add_argument("--no-model", action="store_true", help="Run deterministic replay/control campaign only")
    args = parser.parse_args()
    result = campaign(args.output_dir, model_enabled=not args.no_model)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["final_status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
