#!/usr/bin/env python3
"""Create, edit, execute, and rename BASIC functions through semantic tools only."""
from __future__ import annotations

import json
from pathlib import Path

from basic_workspace.client import AgentToolAdapter, WorkspaceClient


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results/program-construction"


def main() -> None:
    with WorkspaceClient(timeout=10) as client:
        agent = AgentToolAdapter(client)
        created_doc = agent.call("workspace_create_empty", {})
        did = created_doc["document_id"]

        created_double = agent.call("workspace_create_function", {
            "expected_revision": 1, "name": "DOUBLE", "parameters": ["X"]})
        double = next(row for row in created_double["created_entities"] if row["kind"] == "function")
        x = next(row for row in created_double["created_entities"] if row["kind"] == "parameter")
        double_stmt = agent.call("workspace_statements", {"function_id": double["symbol_id"]})["items"][0]
        double_expr = {"kind": "binary", "operator": "*",
                       "left": {"kind": "symbol_ref", "symbol_id": x["symbol_id"]},
                       "right": {"kind": "number", "value": 2}}
        agent.call("workspace_edit_expression", {"expected_revision": 2,
            "statement_id": double_stmt["statement_id"], "expression": double_expr})
        double_18 = {engine: agent.call("workspace_execute_function", {
            "expected_revision": 3, "function_id": double["symbol_id"],
            "arguments": [9], "engine": engine}) for engine in ("interp", "jit")}

        created_calculate = agent.call("workspace_create_function", {
            "expected_revision": 3, "name": "CALCULATE", "parameters": ["Y"]})
        calculate = next(row for row in created_calculate["created_entities"] if row["kind"] == "function")
        y = next(row for row in created_calculate["created_entities"] if row["kind"] == "parameter")
        calculate_stmt = agent.call("workspace_statements", {
            "function_id": calculate["symbol_id"]})["items"][0]
        calculate_expr = {"kind": "binary", "operator": "+",
                          "left": {"kind": "call", "function_id": double["symbol_id"],
                                   "arguments": [{"kind": "symbol_ref", "symbol_id": y["symbol_id"]}]},
                          "right": {"kind": "number", "value": 3}}
        agent.call("workspace_edit_expression", {"expected_revision": 4,
            "statement_id": calculate_stmt["statement_id"], "expression": calculate_expr})
        calculate_21 = {engine: agent.call("workspace_execute_function", {
            "expected_revision": 5, "function_id": calculate["symbol_id"],
            "arguments": [9], "engine": engine}) for engine in ("interp", "jit")}

        triple_expr = {"kind": "binary", "operator": "*",
                       "left": {"kind": "symbol_ref", "symbol_id": x["symbol_id"]},
                       "right": {"kind": "number", "value": 3}}
        agent.call("workspace_edit_expression", {"expected_revision": 5,
            "statement_id": double_stmt["statement_id"], "expression": triple_expr})
        calculate_30 = {engine: agent.call("workspace_execute_function", {
            "expected_revision": 6, "function_id": calculate["symbol_id"],
            "arguments": [9], "engine": engine}) for engine in ("interp", "jit")}

        agent.call("workspace_commit", {"expected_revision": 6,
            "operations": [{"operation": "rename_symbol", "symbol_id": double["symbol_id"],
                            "new_name": "TRIPLE"}]})
        renamed_30 = {engine: agent.call("workspace_execute_function", {
            "expected_revision": 7, "function_id": calculate["symbol_id"],
            "arguments": [9], "engine": engine}) for engine in ("interp", "jit")}

        # Rendering is only an optional terminal artifact after all edits/runs.
        rendered = agent.call("workspace_render", {})["text"]
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "constructed.bas").write_text(rendered, encoding="utf-8")
        report = {
            "document_id": did,
            "revision": client.revision,
            "function_ids": {"DOUBLE_then_TRIPLE": double["symbol_id"],
                             "CALCULATE": calculate["symbol_id"]},
            "parameter_ids": {"X": x["symbol_id"], "Y": y["symbol_id"]},
            "statement_ids": {"DOUBLE_result": double_stmt["statement_id"],
                              "CALCULATE_result": calculate_stmt["statement_id"]},
            "values": {
                "DOUBLE_9": {engine: result["result"] for engine, result in double_18.items()},
                "CALCULATE_9_before_edit": {engine: result["result"] for engine, result in calculate_21.items()},
                "CALCULATE_9_after_expression_edit": {engine: result["result"] for engine, result in calculate_30.items()},
                "CALCULATE_9_after_function_rename": {engine: result["result"] for engine, result in renamed_30.items()},
            },
            "rendered_only_after_execution": rendered,
            "workspace_rpc_metrics": client.metrics,
            "timings": {"double": double_18, "calculate_21": calculate_21,
                        "calculate_30": calculate_30, "renamed_30": renamed_30},
        }
        (RESULTS / "demo.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
