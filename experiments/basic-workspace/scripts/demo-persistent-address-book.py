#!/usr/bin/env python3
"""Create and mutate a BASIC numeric component in persistent MIR workers."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from basic_workspace.mir_execution import PersistentExecutionService
from basic_workspace.model import Workspace, WorkspaceError


def main() -> None:
    workspace = Workspace()
    document_id = workspace.create_empty_document()["document_id"]
    revision = 1
    for name in ("PERSON_ID", "PERSON_AGE"):
        revision = workspace.declare_shared_numeric_array(
            document_id, name, 2, revision)["revision"]
    symbols = {row["name"]: row["symbol_id"] for row in workspace.list_symbols(document_id)}
    person_id, person_age = symbols["PERSON_ID"], symbols["PERSON_AGE"]

    def element(array_id: str, index: dict) -> dict:
        return {"kind": "array_element",
                "array_ref": {"kind": "symbol_ref", "symbol_id": array_id},
                "index": index}

    def array_write(array_id: str, index: int, value: int) -> dict:
        return {"kind": "array_assign",
                "array_ref": {"kind": "symbol_ref", "symbol_id": array_id},
                "index": {"kind": "number", "value": index},
                "expression": {"kind": "number", "value": value}}

    init_body = [array_write(person_id, i, value)
                 for i, value in enumerate((101, 205, 900))]
    init_body += [array_write(person_age, i, value)
                  for i, value in enumerate((25, 42, 53))]
    created = workspace.create_numeric_function(
        document_id, "INIT_COMPONENTS", [], revision,
        expression={"kind": "number", "value": 0}, body=init_body)
    revision = created["revision"]
    initializer_id = next(x["symbol_id"] for x in created["created_entities"]
                          if x["kind"] == "function")

    def make_function(name: str, parameters: list[str], expression: dict | None,
                      body: list[dict], arrays: list[dict] | None = None) -> str:
        nonlocal revision
        result = workspace.create_numeric_function(document_id, name, parameters,
            revision, expression=expression, body=body, arrays=arrays)
        revision = result["revision"]
        return next(x["symbol_id"] for x in result["created_entities"]
                    if x["kind"] == "function")

    def loop(parameter: str, body: list[dict]) -> dict:
        return {"kind": "for", "variable": "I",
                "start": {"kind": "number", "value": 0},
                "end": {"kind": "number", "value": 2},
                "body": [{"kind": "if",
                    "condition": {"kind": "binary", "operator": "=",
                        "left": element(person_id, {"kind": "local_ref", "name": "I"}),
                        "right": {"kind": "local_ref", "name": parameter}},
                    "then": body}]}

    get_id = make_function("GET_AGE", ["ID"], None, [
        {"kind": "assign", "target": {"kind": "result"},
         "expression": {"kind": "number", "value": -1}},
        loop("ID", [{"kind": "assign", "target": {"kind": "result"},
                     "expression": element(person_age, {"kind": "local_ref", "name": "I"})}])])
    set_id = make_function("SET_AGE", ["ID", "NEW_AGE"], None, [
        {"kind": "assign", "target": {"kind": "result"},
         "expression": {"kind": "number", "value": 0}},
        loop("ID", [
            {"kind": "array_assign",
             "array_ref": {"kind": "symbol_ref", "symbol_id": person_age},
             "index": {"kind": "local_ref", "name": "I"},
             "expression": {"kind": "local_ref", "name": "NEW_AGE"}},
            {"kind": "assign", "target": {"kind": "result"},
             "expression": {"kind": "number", "value": 1}}])])
    local_probe = make_function("LOCAL_PROBE", [],
        {"kind": "array_element", "array_ref": {"kind": "local_ref", "name": "TMP"},
         "index": {"kind": "number", "value": 0}},
        [{"kind": "array_assign", "array_ref": {"kind": "local_ref", "name": "TMP"},
          "index": {"kind": "number", "value": 0},
          "expression": {"kind": "binary", "operator": "+",
              "left": {"kind": "array_element",
                  "array_ref": {"kind": "local_ref", "name": "TMP"},
                  "index": {"kind": "number", "value": 0}},
              "right": {"kind": "number", "value": 1}}}],
        arrays=[{"name": "TMP", "upper_bound": 0}])

    if workspace.get_document_structure(document_id)["diagnostics"]:
        raise RuntimeError("constructed definition has diagnostics")
    output = {"document_id": document_id, "revision": revision,
              "arrays": {"PERSON_ID": person_id, "PERSON_AGE": person_age},
              "functions": {"INIT_COMPONENTS": initializer_id,
                            "GET_AGE": get_id, "SET_AGE": set_id,
                            "LOCAL_PROBE": local_probe},
              "engines": {}}
    service = PersistentExecutionService(timeout=5.0)
    try:
        for engine in ("interp", "jit"):
            module = service.prepare_module(workspace, document_id, revision, engine)
            a = service.create_instance(module["module_id"], initializer_id)
            b = service.create_instance(module["module_id"], initializer_id)
            aid, bid = a["instance_id"], b["instance_id"]
            def call(instance: str, function: str, args: list[float], rev: int = revision) -> float:
                return service.call_instance_function(instance, function, args, rev)["result"]
            try:
                call(aid, initializer_id, [])
                raise AssertionError("initializer ran twice")
            except WorkspaceError as exc:
                assert exc.code == "INITIALIZER_ALREADY_RAN"
            observed = {
                "initial_A": call(aid, get_id, [205]),
                "initial_B": call(bid, get_id, [205]),
                "set_A": call(aid, set_id, [205, 47]),
                "after_A": call(aid, get_id, [205]),
                "after_B": call(bid, get_id, [205]),
                "missing_A": call(aid, get_id, [999]),
                "missing_B": call(bid, get_id, [999]),
                "local_probe_first": call(aid, local_probe, []),
                "local_probe_second": call(aid, local_probe, []),
                "build_count": service.get_instance_info(aid)["mir_build_count"],
                "link_count": service.get_instance_info(aid)["mir_link_count"],
            }
            info = service.get_instance_info(aid)
            observed["projection_ms"] = info["projection_ms"]
            observed["worker_startup_ms"] = info["startup_ms"]
            observed["mir_build_ms"] = info["worker_timings_ms"].get("mir_build")
            observed["mir_link_ms"] = info["worker_timings_ms"].get("link")
            try:
                status = Path(f"/proc/{service.instances[aid].proc.pid}/status").read_text()
                observed["worker_rss_kib"] = int(next(line.split()[1] for line in status.splitlines()
                                                        if line.startswith("VmRSS:")))
            except (OSError, StopIteration, ValueError):
                observed["worker_rss_kib"] = None
            warm = {}
            for count in (1, 10, 100, 1000):
                t0 = time.perf_counter()
                for _ in range(count):
                    service.call_instance_function(aid, get_id, [205], revision)
                read_ms = (time.perf_counter() - t0) * 1000
                t0 = time.perf_counter()
                for _ in range(count):
                    service.call_instance_function(aid, set_id, [205, 47], revision)
                write_ms = (time.perf_counter() - t0) * 1000
                warm[str(count)] = {"read_total_ms": round(read_ms, 3),
                                    "read_mean_us": round(read_ms * 1000 / count, 3),
                                    "write_total_ms": round(write_ms, 3),
                                    "write_mean_us": round(write_ms * 1000 / count, 3)}
            observed["warm_calls"] = warm
            try:
                status_after = Path(f"/proc/{service.instances[aid].proc.pid}/status").read_text()
                observed["worker_rss_after_warm_kib"] = int(next(line.split()[1] for line in status_after.splitlines()
                                                                  if line.startswith("VmRSS:")))
            except (OSError, StopIteration, ValueError):
                observed["worker_rss_after_warm_kib"] = None
            expected = {"initial_A": 42.0, "initial_B": 42.0, "set_A": 1.0,
                        "after_A": 47.0, "after_B": 42.0,
                        "missing_A": -1.0, "missing_B": -1.0,
                        "local_probe_first": 1.0, "local_probe_second": 1.0,
                        "build_count": 1, "link_count": 1}
            assert all(observed[key] == value for key, value in expected.items()), observed
            old_revision = revision
            renamed = workspace.rename_symbol(document_id, get_id,
                "GET_AGE_V2" if engine == "interp" else "GET_AGE_V3", revision)
            new_revision = renamed["revision"]
            try:
                service.call_instance_function(aid, get_id, [205], new_revision)
                raise AssertionError("old instance accepted the new definition revision")
            except WorkspaceError as exc:
                assert exc.code == "STALE_REVISION"
            assert service.call_instance_function(aid, get_id, [205], old_revision)["result"] == 47.0
            assert service.call_instance_function(bid, get_id, [205], old_revision)["result"] == 42.0
            service.destroy_instance(aid)
            assert call(bid, get_id, [205]) == 42.0
            service.destroy_instance(bid)
            new_module = service.prepare_module(workspace, document_id, new_revision, engine)
            c = service.create_instance(new_module["module_id"], initializer_id)
            assert service.call_instance_function(c["instance_id"], get_id, [205], new_revision)["result"] == 42.0
            service.destroy_instance(c["instance_id"])
            service.release_module(module["module_id"])
            service.release_module(new_module["module_id"])
            revision = new_revision
            observed["new_instance_C"] = 42.0
            observed["old_revision"] = old_revision
            observed["new_revision"] = new_revision
            output["engines"][engine] = observed
        print(json.dumps(output, indent=2, sort_keys=True))
    finally:
        service.close()


if __name__ == "__main__":
    main()
