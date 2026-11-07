#!/usr/bin/env python3
"""Build and revise AGE_BY_ID using typed operations only; execute through MIR."""
from __future__ import annotations

import json
from pathlib import Path

from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.mir_execution import MirExecutionService


def number(value): return {"kind": "number", "value": value}
def local(name): return {"kind": "local_ref", "name": name}
def indexed(name, index):
    return {"kind": "array_element", "array_ref": local(name), "index": index}


def main() -> None:
    workspace = Workspace()
    document = workspace.create_empty_document()["document_id"]
    statements = []
    for name, column in (("PERSON_ID", 0), ("PERSON_AGE", 1)):
        for index, row in enumerate(((101, 25), (205, 42), (900, 53))):
            statements.append({"kind": "array_assign", "array_ref": local(name),
                "index": number(index), "expression": number(row[column])})
    condition = {"kind": "binary", "operator": "=",
        "left": indexed("PERSON_ID", local("I")), "right": local("WANTED")}
    statements.append({"kind": "assign", "target": {"kind": "result"}, "expression": number(-1)})
    statements.append({"kind": "for", "variable": "I", "start": number(0), "end": number(2),
        "body": [{"kind": "if", "condition": condition,
            "then": [{"kind": "assign", "target": {"kind": "result"},
                      "expression": indexed("PERSON_AGE", local("I"))}]}]})

    created = workspace.create_numeric_function(document, "AGE_BY_ID", ["WANTED"], 1,
        arrays=[{"name": "PERSON_ID", "upper_bound": 2},
                {"name": "PERSON_AGE", "upper_bound": 2}],
        body=statements)
    function = next(entity for entity in created["created_entities"] if entity["kind"] == "function")
    executor = MirExecutionService()
    trace = {"initial_revision": created["revision"], "function_id": function["symbol_id"],
             "construction_request": {"name": "AGE_BY_ID", "parameters": ["WANTED"],
                 "arrays": [{"name": "PERSON_ID", "upper_bound": 2},
                            {"name": "PERSON_AGE", "upper_bound": 2}],
                 "body": statements},
             "steps": [], "engines": ["interp", "jit"]}
    expected = {101: 25.0, 205: 42.0, 900: 53.0, 999: -1.0, 2: -1.0}
    for engine in trace["engines"]:
        results = {str(entity_id): executor.execute_function(workspace, document, 2,
            function["symbol_id"], [entity_id], engine)["result"] for entity_id in expected}
        if results != {str(k): v for k, v in expected.items()}:
            raise SystemExit(f"initial {engine} lookup mismatch: {results}")
        trace["steps"].append({"phase": "initial", "engine": engine, "results": results})

    rows = workspace.list_function_statements(document, function["symbol_id"])["items"]
    age_205 = next(row for row in rows if row["kind"] == "array_assignment" and
                   row["expression_summary"] == "42")
    edit = workspace.edit_assignment_expression(document, age_205["statement_id"], number(47), 2)
    trace["semantic_update"] = {"statement_id": age_205["statement_id"],
                                "expression": number(47), "revision": edit["revision"]}
    for engine in trace["engines"]:
        changed = executor.execute_function(workspace, document, edit["revision"],
            function["symbol_id"], [205], engine)["result"]
        unchanged = executor.execute_function(workspace, document, edit["revision"],
            function["symbol_id"], [101], engine)["result"]
        if (changed, unchanged) != (47.0, 25.0):
            raise SystemExit(f"revised {engine} behavior mismatch: {changed}, {unchanged}")
        trace["steps"].append({"phase": "age-update", "revision": edit["revision"],
                               "engine": engine, "age_205": changed, "age_101": unchanged})

    try:
        executor.execute_function(workspace, document, 2, function["symbol_id"], [205], "interp")
    except WorkspaceError as error:
        trace["stale_revision"] = {"code": error.code, "rejected": error.code == "STALE_REVISION"}
    if not trace.get("stale_revision", {}).get("rejected"):
        raise SystemExit("old revision was not rejected")
    trace["final_revision"] = edit["revision"]
    trace["rendered_diagnostic_only"] = workspace.render_document(document)
    output = Path(__file__).resolve().parent / "results/control-flow-lookup"
    output.mkdir(parents=True, exist_ok=True)
    (output / "construction-trace.json").write_text(json.dumps(trace, indent=2) + "\n")
    print(json.dumps({"document_id": document, "revision": edit["revision"],
                      "function_id": function["symbol_id"], "steps": trace["steps"],
                      "stale_revision": trace["stale_revision"]}, indent=2))


if __name__ == "__main__":
    main()
