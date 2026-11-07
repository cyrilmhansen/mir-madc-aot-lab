#!/usr/bin/env python3
"""Fresh-worker string lookup timings at 3, 16 and 64 rows (30 calls each)."""
from __future__ import annotations

import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from basic_workspace.mir_execution import MirExecutionService
from basic_workspace.model import Workspace


def percentile(values, p):
    vals = sorted(values)
    return vals[min(len(vals) - 1, int((len(vals) - 1) * p))]


def create(n):
    ws = Workspace()
    did = ws.create_empty_document()["document_id"]
    body = []
    for i in range(n):
        body.extend([
            {"kind": "array_assign", "array_ref": {"kind": "local_ref", "name": "IDS"},
             "index": {"kind": "number", "value": i}, "expression": {"kind": "number", "value": 1000 + i * 11}},
            {"kind": "array_assign", "array_ref": {"kind": "local_ref", "name": "NAMES$"},
             "index": {"kind": "number", "value": i}, "expression": {"kind": "string", "value": f"Person {i}"}},
        ])
    body.extend([
        {"kind": "assign", "target": {"kind": "result"}, "expression": {"kind": "string", "value": ""}},
        {"kind": "for", "variable": "I", "start": {"kind": "number", "value": 0},
         "end": {"kind": "number", "value": n - 1}, "body": [{
             "kind": "if", "condition": {"kind": "binary", "operator": "=",
                 "left": {"kind": "array_element", "array_ref": {"kind": "local_ref", "name": "IDS"},
                          "index": {"kind": "local_ref", "name": "I"}},
                 "right": {"kind": "local_ref", "name": "WANTED"}},
             "then": [{"kind": "assign", "target": {"kind": "result"},
                 "expression": {"kind": "array_element",
                     "array_ref": {"kind": "local_ref", "name": "NAMES$"},
                     "index": {"kind": "local_ref", "name": "I"}}}]}]},
    ])
    made = ws.create_string_function(did, "LOOKUP$", ["WANTED"], 1,
        arrays=[{"name": "IDS", "upper_bound": n - 1}, {"name": "NAMES$", "upper_bound": n - 1}], body=body)
    function = ws.get_document_structure(did)["functions"][0]["symbol_id"]
    return ws, did, made["revision"], function


def main():
    samples = []
    executor = MirExecutionService()
    for n in (3, 16, 64):
        ws, did, revision, fid = create(n)
        for engine in ("interp", "jit"):
            rows = []
            expected = f"Person {n - 1}"
            for _ in range(30):
                started = time.perf_counter()
                result = executor.execute_function(ws, did, revision, fid, [1000 + (n - 1) * 11], engine)
                elapsed = (time.perf_counter() - started) * 1000
                if result["result"] != expected:
                    raise AssertionError((n, engine, result["result"], expected))
                rows.append({"wall_ms": elapsed, **result})
            def stats(key):
                values = [float(row["wall_ms"] if key == "wall_ms" else row["timings_ms"][key]) for row in rows]
                return {"median": statistics.median(values), "p95": percentile(values, .95)}
            samples.append({"rows": n, "engine": engine, "repetitions": 30,
                "expected_result": expected,
                "timings_ms": {key: stats(key) for key in
                    ("wall_ms", "projection", "serialization", "worker_compile_and_execute",
                     "mir_build", "mir_link", "mir_jit_compile", "mir_invoke", "result_copy_json")},
                "transport_bytes": rows[-1]["transport_bytes"],
                "response_bytes": rows[-1]["worker_response_bytes"],
                "result_utf8_bytes": rows[-1]["result_utf8_bytes"],
                "worker_maxrss_kib": max(int(row["worker_maxrss_kib"] or 0) for row in rows)})
    output = {"host": "Linux x86-64 native", "fresh_worker_per_call": True,
              "runs_per_case": 30, "capacity_is_number_of_records": True, "samples": samples}
    path = ROOT / "results/string-lookup/benchmark.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
