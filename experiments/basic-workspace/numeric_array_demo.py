#!/usr/bin/env python3
"""Build and evolve numeric-array BASIC functions through semantic JSON-RPC tools."""
from __future__ import annotations

import json
from pathlib import Path

from basic_workspace.client import AgentToolAdapter, RpcError, WorkspaceClient


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results/numeric-arrays"


def created_entity(result: dict, kind: str, name: str | None = None) -> dict:
    return next(row for row in result["created_entities"]
                if row["kind"] == kind and (name is None or row["name"] == name))


def main() -> None:
    trace: dict = {"program": "typed numeric arrays; no BASIC source input"}
    with WorkspaceClient(timeout=10) as client:
        api = AgentToolAdapter(client)
        opened = api.call("workspace_create_empty", {})
        did = opened["document_id"]
        operation_trace = [{"method": "workspace_create_empty", "revision": opened["revision"]}]
        assignments = [
            {"array_ref": {"kind": "local_ref", "name": "VALUES"},
             "index": {"kind": "number", "value": index},
             "expression": {"kind": "number", "value": value}}
            for index, value in enumerate((11, 22, 33, 44))
        ]
        construction_request = {
            "expected_revision": 1, "name": "VALUE_AT", "parameters": ["I"],
            "arrays": [{"name": "VALUES", "upper_bound": 3}],
            "array_assignments": assignments,
            "expression": {"kind": "array_element",
                "array_ref": {"kind": "local_ref", "name": "VALUES"},
                "index": {"kind": "local_ref", "name": "I"}}}
        created = api.call("workspace_create_function", construction_request)
        function = created_entity(created, "function")
        array = created_entity(created, "array", "VALUES")
        initial = {}
        for engine in ("interp", "jit"):
            initial[engine] = {
                str(index): api.call("workspace_execute_function", {
                    "expected_revision": 2, "function_id": function["symbol_id"],
                    "arguments": [index], "engine": engine})["result"]
                for index in (0, 2, 3)}
        statement_rows = api.call("workspace_statements", {
            "function_id": function["symbol_id"]})["items"]
        value_statement = next(row for row in statement_rows
                               if row["kind"] == "array_assignment"
                               and row["expression_summary"] == "33")
        before_ids = [row["statement_id"] for row in statement_rows]
        edited = api.call("workspace_edit_expression", {
            "expected_revision": 2, "statement_id": value_statement["statement_id"],
            "expression": {"kind": "number", "value": 77}})
        operation_trace.extend([
            {"method": "workspace_create_function", "params": construction_request,
             "revision": created["revision"],
             "created_ids": {kind: [row["symbol_id"] for row in created["created_entities"]
                              if row["kind"] == kind]
                             for kind in ("function", "parameter", "array")}},
            {"method": "workspace_edit_expression",
             "params": {"expected_revision": 2,
                        "statement_id": value_statement["statement_id"],
                        "expression": {"kind": "number", "value": 77}},
             "revision": edited["revision"]},
        ])
        after_rows = api.call("workspace_statements", {
            "function_id": function["symbol_id"]})["items"]
        after_ids = [row["statement_id"] for row in after_rows]
        changed = {}
        for engine in ("interp", "jit"):
            changed[engine] = api.call("workspace_execute_function", {
                "expected_revision": 3, "function_id": function["symbol_id"],
                "arguments": [2], "engine": engine})["result"]
        try:
            api.call("workspace_execute_function", {
                "expected_revision": 3, "function_id": function["symbol_id"],
                "arguments": [4], "engine": "interp"})
            bounds_error = None
        except RpcError as exc:
            bounds_error = {"code": exc.code, "message": str(exc)}
        rendered = api.call("workspace_render", {})["text"]
        trace.update({
            "document_id": did, "revision": client.revision,
            "semantic_operations": operation_trace,
            "function_id": function["symbol_id"], "array": array,
            "initial_results": initial, "edited_value_results": changed,
            "out_of_range": bounds_error,
            "statement_ids_stable": before_ids == after_ids,
            "function_identity_stable": function["symbol_id"] in
                [row["symbol_id"] for row in client.workspace_symbols(kind="function")["items"]],
            "rendered_after_execution": rendered,
            "workspace_rpc_metrics": client.metrics,
        })

    # Separate, small ECS-oriented illustration: physical slot I selects an
    # age while the parallel ID column stores nonsequential logical IDs.
    with WorkspaceClient(timeout=10) as client:
        api = AgentToolAdapter(client)
        opened = api.call("workspace_create_empty", {})
        people = [("PERSON_ID", (101, 205, 900)),
                  ("PERSON_AGE", (31, 42, 53))]
        assignments = []
        for name, values in people:
            for slot, value in enumerate(values):
                assignments.append({"array_ref": {"kind": "local_ref", "name": name},
                    "index": {"kind": "number", "value": slot},
                    "expression": {"kind": "number", "value": value}})
        created = api.call("workspace_create_function", {
            "expected_revision": 1, "name": "AGE_AT", "parameters": ["I"],
            "arrays": [{"name": name, "upper_bound": 2} for name, _ in people],
            "array_assignments": assignments,
            "expression": {"kind": "array_element",
                "array_ref": {"kind": "local_ref", "name": "PERSON_AGE"},
                "index": {"kind": "local_ref", "name": "I"}}})
        age_function = created_entity(created, "function")
        index_parameter = created_entity(created, "parameter", "I")
        people_results = {engine: [api.call("workspace_execute_function", {
            "expected_revision": 2, "function_id": age_function["symbol_id"],
            "arguments": [slot], "engine": engine})["result"] for slot in range(3)]
            for engine in ("interp", "jit")}
        rows = api.call("workspace_statements", {"function_id": age_function["symbol_id"]})["items"]
        result_statement = next(row for row in rows if row["target_name"] == "AGE_AT")
        symbols = api.call("workspace_symbols", {"kind": "array"})["items"]
        id_array = next(row for row in symbols if row["name"] == "PERSON_ID")
        api.call("workspace_edit_expression", {"expected_revision": 2,
            "statement_id": result_statement["statement_id"],
            "expression": {"kind": "array_element",
                "array_ref": {"kind": "symbol_ref", "symbol_id": id_array["symbol_id"]},
                "index": {"kind": "symbol_ref", "symbol_id": index_parameter["symbol_id"]}}})
        logical_ids = {engine: api.call("workspace_execute_function", {
            "expected_revision": 3, "function_id": age_function["symbol_id"],
            "arguments": [2], "engine": engine})["result"] for engine in ("interp", "jit")}
        trace["people_arrays"] = {
            "revision": client.revision, "arrays": symbols,
            "ages_by_physical_slot": people_results,
            "person_id_at_physical_slot_2_after_semantic_edit": logical_ids,
            "rendered_after_execution": api.call("workspace_render", {})["text"],
        }

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "demo.json").write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "constructed-value-at.bas").write_text(
        trace["rendered_after_execution"], encoding="utf-8")
    (RESULTS / "constructed-people-arrays.bas").write_text(
        trace["people_arrays"]["rendered_after_execution"], encoding="utf-8")
    print(json.dumps(trace, indent=2))


if __name__ == "__main__":
    main()
