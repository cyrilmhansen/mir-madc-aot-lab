#!/usr/bin/env python3
"""Fresh-worker characterization of generated ID-lookup loops."""
from __future__ import annotations

import json
import os
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from basic_workspace.model import Workspace
from basic_workspace.mir_execution import MirExecutionService, encode_projection
from basic_workspace.projection import build_projection


def num(value): return {"kind": "number", "value": value}
def local(name): return {"kind": "local_ref", "name": name}
def element(name, index): return {"kind": "array_element", "array_ref": local(name), "index": index}


def construct(capacity: int):
    workspace = Workspace()
    document = workspace.create_empty_document()["document_id"]
    body = []
    records = ((101, 25), (205, 42), (900, 53))
    for name, column in (("PERSON_ID", 0), ("PERSON_AGE", 1)):
        for index, row in enumerate(records):
            if index < capacity:
                body.append({"kind": "array_assign", "array_ref": local(name),
                    "index": num(index), "expression": num(row[column])})
    body.append({"kind": "assign", "target": {"kind": "result"}, "expression": num(-1)})
    body.append({"kind": "for", "variable": "I", "start": num(0),
        "end": num(capacity - 1), "body": [{"kind": "if",
            "condition": {"kind": "binary", "operator": "=",
                "left": element("PERSON_ID", local("I")), "right": local("WANTED")},
            "then": [{"kind": "assign", "target": {"kind": "result"},
                "expression": element("PERSON_AGE", local("I"))}]}]})
    created = workspace.create_numeric_function(document, "AGE_LOOKUP", ["WANTED"], 1,
        arrays=[{"name": "PERSON_ID", "upper_bound": capacity - 1},
                {"name": "PERSON_AGE", "upper_bound": capacity - 1}], body=body)
    function = next(entity for entity in created["created_entities"] if entity["kind"] == "function")
    return workspace, document, function["symbol_id"], created["revision"]


def median(rows, field):
    return round(statistics.median(float(row[field]) for row in rows), 6)


def main():
    reps = 30
    executor = MirExecutionService()
    output = {"method": "one warmup plus 30 fresh worker processes per engine/capacity",
        "worker_timeout_seconds": executor.timeout, "sizes": []}
    for capacity in (3, 16, 64):
        construction_started = time.perf_counter()
        workspace, document, function, revision = construct(capacity)
        constructor_ms = (time.perf_counter() - construction_started) * 1000
        projection = build_projection(workspace, document, revision)
        payload = encode_projection(projection, 0, [205], "jit")
        expected = 42.0
        for strategy, memory_mode in (("register-dispatch", "0"), ("stack-memory", "1")):
          os.environ["BASIC_WORKSPACE_MEMORY_ARRAYS"] = memory_mode
          for engine in ("interp", "jit"):
            warm = executor.execute_function(workspace, document, revision, function, [205], engine)
            if capacity < 3:
                expected = -1.0
            if warm["result"] != expected:
                raise SystemExit(f"capacity {capacity} {strategy}/{engine}: expected {expected}, got {warm['result']}")
            rows = []
            for _ in range(reps):
                rows.append(executor.execute_function(workspace, document, revision, function, [205], engine))
            output["sizes"].append({"capacity": capacity, "strategy": strategy, "engine": engine,
                "array_count": 2, "transport_bytes": len(payload), "repetitions": reps,
                "result": warm["result"], "constructor_commit_ms": round(constructor_ms, 6),
                "median_ms": {
                    "projection": round(statistics.median(r["timings_ms"]["projection"] for r in rows), 6),
                    "serialization": round(statistics.median(r["timings_ms"]["serialization"] for r in rows), 6),
                    "worker_process_inclusive": round(statistics.median(r["timings_ms"]["worker_compile_and_execute"] for r in rows), 6),
                    "mir_build": round(statistics.median(r["timings_ms"]["mir_build"] for r in rows), 6),
                    "mir_link": round(statistics.median(r["timings_ms"]["mir_link"] for r in rows), 6),
                    "mir_jit_compile": round(statistics.median(r["timings_ms"]["mir_jit_compile"] for r in rows), 6),
                    "mir_invoke": round(statistics.median(r["timings_ms"]["mir_invoke"] for r in rows), 6)},
                "maxrss_kib": max((r["worker_maxrss_kib"] or 0) for r in rows)})
            print(f"capacity {capacity} {strategy}/{engine} done", flush=True)
    os.environ.pop("BASIC_WORKSPACE_MEMORY_ARRAYS", None)
    target = ROOT / "results/control-flow-lookup/benchmark.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(target), "measurements": len(output["sizes"]),
                      "repetitions_each": reps}, indent=2))


if __name__ == "__main__":
    main()
