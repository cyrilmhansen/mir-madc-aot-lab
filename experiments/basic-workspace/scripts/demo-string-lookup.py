#!/usr/bin/env python3
"""Construct, execute, edit and re-execute a string lookup entirely in memory."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from basic_workspace.mir_execution import MirExecutionService
from basic_workspace.model import Workspace


def body():
    result = []
    for i, (entity, name) in enumerate(((101, "Alice"), (205, "Bob"), (900, "Chloé"))):
        result.extend([
            {"kind": "array_assign", "array_ref": {"kind": "local_ref", "name": "PERSON_ID"},
             "index": {"kind": "number", "value": i}, "expression": {"kind": "number", "value": entity}},
            {"kind": "array_assign", "array_ref": {"kind": "local_ref", "name": "PERSON_NAMES$"},
             "index": {"kind": "number", "value": i}, "expression": {"kind": "string", "value": name}},
        ])
    result += [
        {"kind": "assign", "target": {"kind": "result"}, "expression": {"kind": "string", "value": ""}},
        {"kind": "for", "variable": "I", "start": {"kind": "number", "value": 0},
         "end": {"kind": "number", "value": 2}, "body": [{
             "kind": "if", "condition": {"kind": "binary", "operator": "=",
                 "left": {"kind": "array_element", "array_ref": {"kind": "local_ref", "name": "PERSON_ID"},
                          "index": {"kind": "local_ref", "name": "I"}},
                 "right": {"kind": "local_ref", "name": "WANTED"}},
             "then": [{"kind": "assign", "target": {"kind": "result"},
                       "expression": {"kind": "array_element",
                           "array_ref": {"kind": "local_ref", "name": "PERSON_NAMES$"},
                           "index": {"kind": "local_ref", "name": "I"}}}]}]},
    ]
    return result


def main():
    workspace = Workspace()
    document_id = workspace.create_empty_document()["document_id"]
    created = workspace.create_string_function(document_id, "PERSON_NAME$", ["WANTED"], 1,
        arrays=[{"name": "PERSON_ID", "upper_bound": 2},
                {"name": "PERSON_NAMES$", "upper_bound": 2}], body=body())
    revision = created["revision"]
    structure = workspace.get_document_structure(document_id)
    function = next(f for f in structure["functions"] if f["name"] == "PERSON_NAME$")
    symbols = workspace.list_symbols(document_id)
    arrays = {s["name"]: s["symbol_id"] for s in symbols if s["kind"] == "array"}
    executor = MirExecutionService()
    trace = {"document_id": document_id, "revision_after_construction": revision,
             "function_id": function["symbol_id"], "array_ids": arrays, "engines": {}}
    for engine in ("interp", "jit"):
        rows = {}
        for entity_id in (101, 205, 900, 999, 2):
            rows[str(entity_id)] = executor.execute_function(workspace, document_id, revision,
                function["symbol_id"], [entity_id], engine)["result"]
        trace["engines"][engine] = rows

    statements = workspace.list_function_statements(document_id, function["symbol_id"])["items"]
    bob = next(row for row in statements if row["target_symbol_id"] == arrays["PERSON_NAMES$"]
               and row["expression_summary"] == '"Bob"')
    before_ids = [row["statement_id"] for row in statements]
    edited = workspace.edit_assignment_expression(document_id, bob["statement_id"],
        {"kind": "string", "value": "Robert"}, revision)
    revision = edited["revision"]
    trace["edit"] = {"statement_id": bob["statement_id"], "revision": revision,
                     "after": {engine: executor.execute_function(workspace, document_id, revision,
                         function["symbol_id"], [205], engine)["result"]
                         for engine in ("interp", "jit")}}
    trace["stable_identity_checks"] = {
        "function": function["symbol_id"] == workspace.get_document_structure(document_id)["functions"][0]["symbol_id"],
        "arrays": arrays == {s["name"]: s["symbol_id"] for s in workspace.list_symbols(document_id) if s["kind"] == "array"},
        "statements": set(before_ids).issubset({r["statement_id"] for r in
            workspace.list_function_statements(document_id, function["symbol_id"])["items"]}),
    }
    # Optional diagnostic rendering occurs only after compile/execute/edit.
    trace["rendered_diagnostic_only"] = workspace.render_document(document_id)
    out = ROOT / "results/string-lookup/structured-construction-trace.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"trace": str(out), "initial": trace["engines"], "edit": trace["edit"],
                      "identity_checks": trace["stable_identity_checks"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
